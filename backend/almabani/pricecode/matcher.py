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
from .lexical_search import LexicalMatcher

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
                        meta = cand.get("metadata", {}) or {}
                        result["source_file"] = meta.get("source_file")
                        result["reference_sheet"] = meta.get("reference_sheet")
                        result["reference_category"] = meta.get("reference_category")
                        result["reference_row"] = meta.get("reference_row")
                    else:
                        result["matched"] = False
                        result["reason"] = f"LLM returned invalid index: {idx}"

                return result

            except Exception as e:
                last_err = e
                if attempt < _LLM_MAX_RETRIES - 1:
                    delay = _LLM_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{_LLM_MAX_RETRIES}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)

        logger.error(f"LLM match error after {_LLM_MAX_RETRIES} attempts: {last_err}")
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

        # Build a single "Target Item:" line: category_path > description
        context_prefix = ""
        if category_path:
            context_prefix = category_path.strip()
        elif parent or grandparent:
            # Fallback when no category_path: grandparent > parent
            segs = [s for s in [grandparent, parent] if s]
            context_prefix = " > ".join(str(s) for s in segs)

        if context_prefix:
            parts.append(f"Target Item: {context_prefix} > {description}")
        else:
            parts.append(f"Target Item: {description}")

        if unit:
            parts.append(f"TARGET UNIT: {unit}")
        else:
            parts.append("TARGET UNIT: (not specified)")
        return "\n".join(parts)

    @staticmethod
    def _build_candidates_text(candidates: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        # Compact code regex: e.g. p1316ACC, h3713B01
        _compact_re = re.compile(
            r'^[A-Za-z](\d{2})(\d{2})([A-Za-z])([A-Za-z0-9])([A-Za-z0-9])$'
        )
        for i, cand in enumerate(candidates, 1):
            code = cand.get("price_code", "NO_CODE")
            desc = cand.get("description", "")
            leaf = cand.get("leaf_description", "")
            category = cand.get("category", "")
            tag = f" ({category})" if category else ""

            # ── Structured prefix / leaf display ────────────────────────
            # desc is the full prefixed_description, e.g.
            # "Ready Mix Concrete ; Cast In Situ ; Concrete For Footing ..."
            # Split into prefix hierarchy + leaf so the LLM sees the
            # classification path explicitly.
            prefix_tag = ""
            display_desc = desc
            if leaf and desc and ";" in desc:
                segments = [s.strip() for s in desc.split(";")]
                if len(segments) > 1:
                    prefix_segments = segments[:-1]
                    prefix_tag = " {" + " > ".join(prefix_segments) + "}"
                    display_desc = segments[-1]

            # ── Scope annotation ────────────────────────────────────────
            # Parse price code suffix to extract the scope letter and
            # append a human-readable label so the LLM explicitly sees
            # what each scope variant means.
            scope_tag = ""
            parts = code.strip().split()
            disc_letter = ""
            cat_str = ""
            scope_letter = None

            decoded_tag = ""  # human-readable decomposition for compact codes

            if len(parts) >= 4 and len(parts[3]) >= 2:
                # Spaced format: C 31 13 CGA
                disc_letter = parts[0].upper()
                cat_str = parts[1] if len(parts) >= 2 else ""
                scope_letter = parts[3][-1].upper()
            else:
                # Try compact format: p1316ACC
                cm = _compact_re.match(code.strip())
                if cm:
                    disc_letter = code.strip()[0].upper()
                    cat_str = cm.group(1)
                    subcat_str = cm.group(2)
                    scope_letter = cm.group(5).upper()
                    # If last char is numeric, try first suffix char
                    if not scope_letter.isalpha():
                        scope_letter = cm.group(3).upper()
                    # Build human-readable decomposition
                    disc_name = _DISC_LABELS.get(disc_letter, disc_letter)
                    decoded_tag = f" (={disc_name} {cat_str}-{subcat_str})"
                elif code.strip() and code.strip()[0].upper() in _DISC_LABELS:
                    # Fallback: at least extract discipline from first char
                    disc_letter = code.strip()[0].upper()

            if scope_letter and scope_letter.isalpha():
                if disc_letter == "C" and cat_str in ("31", "21", "11", "10"):
                    label = _SCOPE_LABELS_CIVIL_CONCRETE.get(scope_letter)
                else:
                    label = _SCOPE_LABELS_GENERIC.get(scope_letter)
                if label:
                    scope_tag = f" [Scope {scope_letter}: {label}]"

            # ── Discipline annotation ───────────────────────────────────
            disc_tag = ""
            if disc_letter in _DISC_LABELS:
                disc_tag = f" [Disc: {_DISC_LABELS[disc_letter]}]"

            lines.append(f"[{i}] [{code}]{decoded_tag}{disc_tag}{scope_tag}{prefix_tag}{tag} {display_desc}")
        return "\n".join(lines)
