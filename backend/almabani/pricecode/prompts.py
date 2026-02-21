"""
LLM Prompts for Price Code allocation.
Single-step logic with strict confidence levels (EXACT, HIGH).
Includes detailed criteria and rejection rules to ensure high accuracy.
"""

PRICECODE_MATCH_SYSTEM = (
    "You are a Price Code allocation expert. "
    "Your job is to identify a matching Price Code for a BOQ item from a list of candidates.\n"
    "You must return a single JSON object with the best match, or indicate no match.\n\n"
    "MATCHING PHILOSOPHY: STRICT & CONSERVATIVE\n"
    "- Better to return 'matched': false than a wrong price code.\n"
    "- Do not guess. Do not assume missing specifications.\n"
    "- Do not force a match if the unit or scope is incompatible.\n"
)

PRICECODE_MATCH_USER = """TARGET ITEM:
{target_info}

CANDIDATES:
{candidates_text}

INSTRUCTIONS:
Perform a logical elimination process to find the best match.

1. UNIT COMPATIBILITY CHECK (CRITICAL - DO THIS FIRST):
   - Look at the TARGET UNIT specified above.
   - For EACH candidate, check if the candidate's unit matches or is compatible with the TARGET UNIT.
   - STRICT RULE: If a candidate's unit is fundamentally different from the TARGET UNIT, REJECT that candidate immediately.
   - Examples of INCOMPATIBLE units (must REJECT):
     * Target 'm3' (volume) vs Candidate 'm2' (area) → REJECT
     * Target 'm' (length) vs Candidate 'kg' (weight) → REJECT
     * Target 'Item' vs Candidate 'm' → REJECT (ambiguous conversion)
     * Target 'set' vs Candidate 'pc' → REJECT (unless clearly equivalent)
   - Examples of COMPATIBLE units (may accept):
     * Target 'm3' vs Candidate 'cu.m' or 'cubic meter' → OK (same dimension)
     * Target 'm2' vs Candidate 'sq.m' or 'sqm' → OK (same dimension)
     * Target 'L.M.' vs Candidate 'm' → OK (linear meter)

2. SCOPE & WORK TYPE CHECK:
   - Must be the same fundamental activity (e.g., 'Excavation' is not 'Disposal').
   - Must be the same material class (e.g., 'PVC' is not 'HDPE').
   - Candidate must cover the *entire* scope required by the Target.

3. SPECIFICITY CHECK (NO ASSUMPTIONS):
   - If Target is SPECIFIC (e.g., 'Depth > 2m') and Candidate is VAGUE (e.g., 'Excavation'), REJECT.
   - If Target is VAGUE and Candidate is SPECIFIC (implying extra constraints), REJECT.
   - Exception: Harmless differences (brand, color) are allowed for HIGH confidence.

CONFIDENCE LEVELS:
- "EXACT" (Green): Functionally IDENTICAL.
  * Same work, same specs, same scope, same unit.
  * Example: "DN200 Pipe" == "200mm Pipe".
- "HIGH" (Yellow): SAFE match with minor deviations.
  * Minor spec variance that doesn't change cost basis significantly (e.g., "C30" vs "C35", "150mm" vs "200mm" for non-critical dimensions).
  * Difference in non-critical attributes (e.g., "Schedule 40" vs "Standard", brand names).
  * Equivalent or interchangeable materials (e.g., "galvanized steel" vs "GI steel").
  * Slightly broader or narrower scope when the core work is identical (e.g., "depth 1-2m" vs "depth up to 2m").
  * Missing minor details in one side that don't affect the fundamental pricing.
- "NO MATCH" (Red):
  * Different material, incompatible unit, unsupported scope, or risky assumptions.

OUTPUT JSON:
{{
    "matched": true/false,
    "match_index": 1,  // 1-based index (if matched)
    "confidence_level": "EXACT" | "HIGH", // (if matched)
    "reason": "Brief explanation: 'EXACT match on work/specs' OR 'HIGH confidence due to minor diff [X]' OR 'REJECTED due to unit mismatch'."
}}
"""
