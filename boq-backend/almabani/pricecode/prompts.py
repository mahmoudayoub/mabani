"""
LLM Prompts for Price Code allocation.
Simplified single-step: choose the exact match from candidates.
"""

PRICECODE_MATCH_SYSTEM = (
    "You are a construction price code matcher. "
    "Given a BOQ target item and a list of rate-book candidates, "
    "pick the candidate that is the exact match for the target item. "
    "Return a single JSON object."
)

PRICECODE_MATCH_USER = """TARGET:
{target_info}

CANDIDATES:
{candidates_text}

Pick the candidate that exactly matches the target item.
Compare work type, material, scope, and specifications.
Construction descriptions are often abbreviated — different wording for the same item is normal.

Rules:
- Evaluate every candidate; the best match can be at any position.
- A match is valid when the core work, material, and scope align.
- Pick one match unless none of the candidates describe the same work at all.

Return JSON:
{{
  "matched": true,
  "match_index": <1-based index>,
  "confidence_level": "EXACT" or "HIGH",
  "reason": "one sentence"
}}
If no candidate matches: {{ "matched": false, "reason": "..." }}
"""
