"""
Price Code Matcher – Lexical candidate search + LLM one-shot matching.

Flow:
  1. Lexical search via ``LexicalMatcher`` (SQLite, no embeddings)
  2. LLM structured decision: match or no match
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .prompts import PRICECODE_MATCH_SYSTEM, PRICECODE_MATCH_USER
from .lexical_search import LexicalMatcher, extract_specs

_LLM_MAX_RETRIES = 3
_LLM_BASE_DELAY = 1.0  # seconds; doubles each retry

# Scope letter meanings appended to each candidate line so the LLM can
# directly see what each scope variant represents.
_SCOPE_LABELS_CIVIL_CONCRETE = {
    "A": "Concrete Only",
    "B": "+Reinforcement",
    "C": "+Formwork",
    "D": "Conc+Rebar",
    "E": "Supply Only",
    "F": "Supply+Install",
}
_SCOPE_LABELS_GENERIC = {
    "E": "Supply Only",
    "F": "Supply+Install",
}

_DISC_LABELS = {
    "C": "Civil", "P": "Plumbing", "H": "HVAC",
    "F": "Fire", "Z": "Utilities", "E": "Electrical",
}

logger = logging.getLogger(__name__)


class PriceCodeMatcher:
    """
    Match BOQ item descriptions to price codes using lexical search + LLM.

    Parameters
    ----------
    async_openai_client : AsyncOpenAI
        OpenAI async client for the LLM judge step.
    lexical_matcher : LexicalMatcher
        Pre-initialised lexical search engine (with optional source-file filter).
    model : str | None
        Chat model override (defaults to ``settings.openai_chat_model``).
    """

    def __init__(
        self,
        async_openai_client,
        lexical_matcher: LexicalMatcher,
        model: str = None,
    ):
        from almabani.config.settings import get_settings
        settings = get_settings()

        self.openai_client = async_openai_client
        self.lexical_matcher = lexical_matcher
        self.model = model if model is not None else settings.openai_chat_model

    # ── public API ──────────────────────────────────────────────────────

    async def match(
        self,
        description: str,
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
        unit: Optional[str] = None,
        item_code: Optional[str] = None,
        category_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Match a single BOQ item description to a price code."""

        # 1. Lexical search (async via aiosqlite)
        item = {
            "description": description,
            "parent": parent,
            "grandparent": grandparent,
            "unit": unit,
            "item_code": item_code,
            "category_path": category_path,
        }
        candidates = await self.lexical_matcher.search(item)

        if not candidates:
            return {"matched": False, "reason": "No candidates found"}

        # 2. LLM one-shot decision
        return await self.llm_match(
            description,
            candidates,
            parent=parent,
            grandparent=grandparent,
            unit=unit,
            item_code=item_code,
            category_path=category_path,
        )

    # ── LLM matching (unchanged from original) ─────────────────────────

    async def llm_match(
        self,
        description: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
        unit: Optional[str] = None,
        item_code: Optional[str] = None,
        category_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ask the LLM to pick the best match from the candidate list."""
        if not candidates:
            return {"matched": False, "reason": "No candidates"}

        target_info = self._build_target_info(
            description, unit, item_code, parent, grandparent, category_path
        )
        candidates_text = self._build_candidates_text(candidates)

        user_prompt = PRICECODE_MATCH_USER.format(
            target_info=target_info,
            candidates_text=candidates_text,
        )

        last_err: Optional[Exception] = None
        for attempt in range(_LLM_MAX_RETRIES):
            try:
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": PRICECODE_MATCH_SYSTEM},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=1,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content
                result = json.loads(content)

                # Merge metadata from the matched candidate
                if result.get("matched") and result.get("match_index"):
                    idx = result["match_index"]
                    if isinstance(idx, int) and 1 <= idx <= len(candidates):
                        cand = candidates[idx - 1]
                        result["price_code"] = cand.get("price_code")
                        result["price_description"] = cand.get("description")
                        result["score"] = cand.get("score")
                        result["source_file"] = cand.get("source_file")
                        result["reference_sheet"] = cand.get("sheet_name")
                    else:
                        result["matched"] = False
                        result["reason"] = f"LLM returned invalid index: {idx}"

                return result

            except Exception as e:
                last_err = e
                if attempt < _LLM_MAX_RETRIES - 1:
                    delay = _LLM_BASE_DELAY * (2 ** attempt)
                    # Build detailed cause string for logs
                    cause_parts = [f"{type(e).__name__}: {e}"]
                    status = getattr(e, "status_code", None) or getattr(e, "http_status", None)
                    if status is not None:
                        cause_parts.append(f"HTTP {status}")
                    err_body = getattr(e, "body", None) or getattr(e, "response", None)
                    if err_body is not None:
                        body_text = getattr(err_body, "text", None) if hasattr(err_body, "text") else str(err_body)
                        if body_text:
                            cause_parts.append(f"body={body_text[:500]}")
                    logger.warning(
                        "LLM call failed (attempt %d/%d), retrying in %.1fs \u2013 %s",
                        attempt + 1, _LLM_MAX_RETRIES, delay,
                        " | ".join(cause_parts),
                    )
                    await asyncio.sleep(delay)

        # Final failure \u2013 log with full detail
        final_parts = [f"{type(last_err).__name__}: {last_err}"]
        status = getattr(last_err, "status_code", None) or getattr(last_err, "http_status", None)
        if status is not None:
            final_parts.append(f"HTTP {status}")
        logger.error(
            "LLM match failed after %d attempts \u2013 %s",
            _LLM_MAX_RETRIES, " | ".join(final_parts),
        )
        return {"matched": False, "reason": f"LLM error: {str(last_err)}"}

    # ── prompt helpers (unchanged) ──────────────────────────────────────

    @staticmethod
    def _context_tail_from_path(category_path: str) -> str:
        if not category_path:
            return ""
        parts = [p.strip() for p in category_path.split(">") if p.strip()]
        if len(parts) > 2:
            parts = parts[2:]
        return " > ".join(parts)

    def _build_target_info(
        self,
        description: str,
        unit: Optional[str],
        item_code: Optional[str],
        parent: Optional[str],
        grandparent: Optional[str],
        category_path: Optional[str] = None,
    ) -> str:
        parts: List[str] = []

        # Context path > description
        context_prefix = ""
        if category_path:
            context_prefix = category_path.strip()
        elif parent or grandparent:
            segs = [s for s in [grandparent, parent] if s]
            context_prefix = " > ".join(str(s) for s in segs)

        if context_prefix:
            parts.append(f"Item: {context_prefix} > {description}")
        else:
            parts.append(f"Item: {description}")

        if unit:
            parts.append(f"Unit: {unit}")

        # Parsed specs
        all_text = " ".join(
            str(s) for s in [description, parent, grandparent, category_path] if s
        )
        specs = extract_specs(all_text)
        _SPEC_LABELS = {
            "dn": "DN", "dia": "Dia", "mpa": "MPa", "kv": "kV",
            "mm2": "mm²", "cores": "Cores", "pn": "PN", "thk": "Thk",
            "pipe_mat": "Material", "valve_type": "Valve",
            "concrete_elem": "Element", "concrete_scope": "Scope",
        }
        spec_parts = []
        for key, label in _SPEC_LABELS.items():
            vals = specs.get(key, ())
            if vals:
                spec_parts.append(f"{label}={','.join(vals)}")
        if spec_parts:
            parts.append(f"Specs: {' | '.join(spec_parts)}")

        return "\n".join(parts)

    @staticmethod
    def _build_candidates_text(candidates: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for i, cand in enumerate(candidates, 1):
            code = cand.get("price_code", "NO_CODE")
            desc = cand.get("description", "")
            leaf = cand.get("leaf_description", "")

            # Show hierarchy path + leaf separately when available
            display_desc = desc
            prefix_tag = ""
            if leaf and desc and ";" in desc:
                segments = [s.strip() for s in desc.split(";")]
                if len(segments) > 1:
                    prefix_tag = " {" + " > ".join(segments[:-1]) + "}"
                    display_desc = segments[-1]

            # Discipline from price code (first letter, already normalised)
            code_parts = code.strip().split()
            disc_letter = code_parts[0].upper() if code_parts else ""
            disc_tag = ""
            if disc_letter in _DISC_LABELS:
                disc_tag = f" [{_DISC_LABELS[disc_letter]}]"

            # Scope annotation (last char of suffix)
            scope_tag = ""
            if len(code_parts) >= 4 and len(code_parts[3]) >= 2:
                cat_str = code_parts[1]
                scope_letter = code_parts[3][-1].upper()
                if scope_letter.isalpha():
                    if disc_letter == "C" and cat_str in ("31", "21", "11", "10"):
                        label = _SCOPE_LABELS_CIVIL_CONCRETE.get(scope_letter)
                    else:
                        label = _SCOPE_LABELS_GENERIC.get(scope_letter)
                    if label:
                        scope_tag = f" [Scope: {label}]"

            # Spec tags from search engine
            spec_tags = ""
            _spec_keys = [
                ("dn_csv", "DN"), ("dia_csv", "Dia"), ("mpa_csv", "MPa"),
                ("kv_csv", "kV"), ("mm2_csv", "mm²"), ("core_csv", "Cores"),
                ("pn_csv", "PN"), ("thk_csv", "Thk"),
                ("pipe_mat_csv", "Mat"), ("valve_type_csv", "Valve"),
                ("concrete_elem_csv", "Elem"),
            ]
            st_parts = []
            for k, label in _spec_keys:
                v = cand.get(k, "")
                if v:
                    st_parts.append(f"{label}:{v}")
            if st_parts:
                spec_tags = " [" + ", ".join(st_parts) + "]"

            lines.append(
                f"[{i}] {code}{disc_tag}{scope_tag}{spec_tags}{prefix_tag} {display_desc}"
            )
        return "\n".join(lines)
