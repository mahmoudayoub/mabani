"""
Vector-based Price Code Matcher – LLM judge for vector candidates.

Flow:
  1. Vector search returns top-K candidates from S3 Vectors
  2. This matcher asks the LLM to pick the best match (or reject all)
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .prompts import PRICECODE_VECTOR_MATCH_SYSTEM, PRICECODE_VECTOR_MATCH_USER

_LLM_MAX_RETRIES = 3
_LLM_BASE_DELAY = 1.0  # seconds; doubles each retry

# Discipline-letter labels (first token of a price code)
_DISC_LABELS = {
    "C": "Civil", "P": "Plumbing", "H": "HVAC",
    "F": "Fire", "Z": "Utilities", "E": "Electrical",
}

# Scope-letter labels (last char of 4th token)
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

logger = logging.getLogger(__name__)


class PriceCodeVectorMatcher:
    """
    LLM judge for vector-based price code candidates.

    Parameters
    ----------
    async_openai_client : AsyncOpenAI
        OpenAI async client.
    model : str | None
        Chat model override (defaults to ``settings.openai_chat_model``).
    """

    def __init__(self, async_openai_client, model: str = None):
        from almabani.config.settings import get_settings
        settings = get_settings()

        self.openai_client = async_openai_client
        self.model = model if model is not None else settings.openai_chat_model

    # ── public API ──────────────────────────────────────────────────────

    async def match(
        self,
        item: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Ask the LLM to pick the best candidate for *item*.

        Parameters
        ----------
        item : dict
            BOQ item with keys: description, parent, grandparent, unit,
            item_code, category_path.
        candidates : list[dict]
            Vector search results.  Each dict has ``score`` and ``metadata``
            (with price_code, description, source_file, sheet_name, unit,
            category_path, parent, grandparent).

        Returns
        -------
        dict  with  matched, price_code, confidence_level, reason, score, …
        """
        if not candidates:
            return {"matched": False, "reason": "No candidates found"}

        target_info = self._build_target_info(item)
        candidates_text = self._build_candidates_text(candidates)

        user_prompt = PRICECODE_VECTOR_MATCH_USER.format(
            target_info=target_info,
            candidates_text=candidates_text,
        )

        last_err: Optional[Exception] = None
        for attempt in range(_LLM_MAX_RETRIES):
            try:
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": PRICECODE_VECTOR_MATCH_SYSTEM},
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
                        meta = cand.get("metadata", {})
                        result["price_code"] = meta.get("price_code", "")
                        result["price_description"] = meta.get("description", "")
                        result["source_file"] = meta.get("source_file", "")
                        result["reference_sheet"] = meta.get("sheet_name", "")
                        result["score"] = cand.get("score", 0)
                    else:
                        result["matched"] = False
                        result["reason"] = f"LLM returned invalid index: {idx}"

                return result

            except Exception as e:
                last_err = e
                if attempt < _LLM_MAX_RETRIES - 1:
                    delay = _LLM_BASE_DELAY * (2 ** attempt)
                    cause_parts = [f"{type(e).__name__}: {e}"]
                    status = getattr(e, "status_code", None) or getattr(
                        e, "http_status", None
                    )
                    if status is not None:
                        cause_parts.append(f"HTTP {status}")
                    err_body = getattr(e, "body", None) or getattr(
                        e, "response", None
                    )
                    if err_body is not None:
                        body_text = (
                            getattr(err_body, "text", None)
                            if hasattr(err_body, "text")
                            else str(err_body)
                        )
                        if body_text:
                            cause_parts.append(f"body={body_text[:500]}")
                    logger.warning(
                        "LLM call failed (attempt %d/%d), retrying in %.1fs – %s",
                        attempt + 1,
                        _LLM_MAX_RETRIES,
                        delay,
                        " | ".join(cause_parts),
                    )
                    await asyncio.sleep(delay)

        # Final failure
        final_parts = [f"{type(last_err).__name__}: {last_err}"]
        status = getattr(last_err, "status_code", None) or getattr(
            last_err, "http_status", None
        )
        if status is not None:
            final_parts.append(f"HTTP {status}")
        logger.error(
            "LLM match failed after %d attempts – %s",
            _LLM_MAX_RETRIES,
            " | ".join(final_parts),
        )
        return {"matched": False, "reason": f"LLM error: {str(last_err)}"}

    # ── prompt helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_target_info(item: Dict[str, Any]) -> str:
        """Format the BOQ target item for the LLM prompt."""
        parts: List[str] = []

        # Context path > description
        context_prefix = ""
        category_path = item.get("category_path")
        parent = item.get("parent")
        grandparent = item.get("grandparent")

        if category_path:
            context_prefix = str(category_path).strip()
        elif parent or grandparent:
            segs = [s for s in [grandparent, parent] if s]
            context_prefix = " > ".join(str(s) for s in segs)

        description = item.get("description", "")
        if context_prefix:
            parts.append(f"Item: {context_prefix} > {description}")
        else:
            parts.append(f"Item: {description}")

        unit = item.get("unit")
        if unit:
            parts.append(f"Unit: {unit}")

        # Parsed specs (lightweight extraction without importing the heavy
        # lexical_search module – covers the most common spec patterns)
        all_text = " ".join(
            str(s)
            for s in [description, parent, grandparent, category_path]
            if s
        )
        specs = _extract_light_specs(all_text)
        if specs:
            parts.append(f"Specs: {specs}")

        return "\n".join(parts)

    @staticmethod
    def _build_candidates_text(candidates: List[Dict[str, Any]]) -> str:
        """Format vector candidates for the LLM prompt."""
        lines: List[str] = []
        for i, cand in enumerate(candidates, 1):
            meta = cand.get("metadata", {})
            code = meta.get("price_code", "NO_CODE")
            desc = meta.get("description", "")
            score = cand.get("score", 0)

            # Category path context
            cat_path = meta.get("category_path", "")
            path_tag = ""
            if cat_path:
                path_tag = f" {{{cat_path}}}"

            # Discipline from price code first letter
            code_parts = code.strip().split()
            disc_letter = code_parts[0].upper() if code_parts else ""
            disc_tag = ""
            if disc_letter in _DISC_LABELS:
                disc_tag = f" [{_DISC_LABELS[disc_letter]}]"

            # Scope annotation (last char of 4th token)
            scope_tag = ""
            if len(code_parts) >= 4 and len(code_parts[3]) >= 2:
                cat_str = code_parts[1] if len(code_parts) > 1 else ""
                scope_letter = code_parts[3][-1].upper()
                if scope_letter.isalpha():
                    if disc_letter == "C" and cat_str in (
                        "31", "21", "11", "10",
                    ):
                        label = _SCOPE_LABELS_CIVIL_CONCRETE.get(scope_letter)
                    else:
                        label = _SCOPE_LABELS_GENERIC.get(scope_letter)
                    if label:
                        scope_tag = f" [Scope: {label}]"

            # Unit from metadata
            unit = meta.get("unit", "")
            unit_tag = f" (Unit: {unit})" if unit else ""

            lines.append(
                f"[{i}] {code}{disc_tag}{scope_tag}{unit_tag}{path_tag}"
                f" {desc}  (sim={score:.3f})"
            )
        return "\n".join(lines)


# ── lightweight spec extraction ─────────────────────────────────────────
# Covers the most common construction spec patterns without pulling in the
# full 4000-line lexical_search module.

def _extract_light_specs(text: str) -> str:
    """Return a compact spec string (e.g. 'DN=150 | MPa=40')."""
    if not text:
        return ""
    low = text.lower()
    parts: List[str] = []

    # DN
    dns = set(re.findall(r"\bdn\s*[-:]?\s*(\d{2,4})\b", low))
    if dns:
        parts.append(f"DN={','.join(sorted(dns, key=int))}")

    # Diameter (Ø)
    dias = set()
    for m in re.finditer(r"[Øø]\s*(\d{2,4})\b", text):
        dias.add(m.group(1))
    for m in re.finditer(r"\b(?:dia|diameter)\s*[:\-]?\s*(\d{2,4})\b", low):
        dias.add(m.group(1))
    if dias:
        parts.append(f"Dia={','.join(sorted(dias, key=int))}")

    # MPa / concrete grade
    mpas: Set[str] = set()
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*mpa\b", low):
        mpas.add(m.group(1))
    for m in re.finditer(r"\bc\s*(\d{1,2})\s*/\s*(\d{1,2})\b", low):
        for g in (1, 2):
            v = int(m.group(g))
            if 10 <= v <= 80:
                mpas.add(str(v))
    if mpas:
        parts.append(f"MPa={','.join(sorted(mpas))}")

    # kV
    kvs = set(re.findall(r"\b(\d+(?:\.\d+)?)\s*kv\b", low))
    if kvs:
        parts.append(f"kV={','.join(sorted(kvs))}")

    # mm² (cable cross-section)
    mm2s = set(re.findall(r"\b(\d+)\s*(?:mm2|mm²|sqmm)\b", low))
    if mm2s:
        parts.append(f"mm²={','.join(sorted(mm2s, key=int))}")

    # Cores
    cores = set(re.findall(r"\b(\d{1,2})\s*core\b", low))
    if cores:
        parts.append(f"Cores={','.join(sorted(cores, key=int))}")

    # Thickness
    thks = set(re.findall(r"\b(\d+)\s*mm\s*(?:thk|thick)\b", low))
    if thks:
        parts.append(f"Thk={','.join(sorted(thks, key=int))}mm")

    return " | ".join(parts)
