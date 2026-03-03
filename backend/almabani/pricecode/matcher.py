"""
Price Code Matcher – Lexical candidate search + LLM one-shot matching.

Flow:
  1. Lexical search via ``LexicalMatcher`` (SQLite, no embeddings)
  2. LLM structured decision: match or no match
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .prompts import PRICECODE_MATCH_SYSTEM, PRICECODE_MATCH_USER
from .lexical_search import LexicalMatcher

_LLM_MAX_RETRIES = 3
_LLM_BASE_DELAY = 1.0  # seconds; doubles each retry

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
        hierarchy_parts: List[str] = []
        if grandparent:
            hierarchy_parts.append(str(grandparent))
        if parent:
            hierarchy_parts.append(str(parent))
        if hierarchy_parts:
            parts.append(f"Hierarchy: {' > '.join(hierarchy_parts)}")
        if category_path:
            tail = self._context_tail_from_path(category_path)
            if tail:
                parts.append(f"Context: {tail}")
        parts.append(f"Description: {description}")
        if unit:
            parts.append(f"TARGET UNIT: {unit}")
        else:
            parts.append("TARGET UNIT: (not specified)")
        if item_code:
            parts.append(f"Item Code: {item_code}")
        return "\n".join(parts)

    @staticmethod
    def _build_candidates_text(candidates: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for i, cand in enumerate(candidates, 1):
            code = cand.get("price_code", "NO_CODE")
            desc = cand.get("description", "")
            category = cand.get("category", "")
            tag = f" ({category})" if category else ""
            lines.append(f"[{i}] [{code}]{tag} {desc}")
        return "\n".join(lines)
