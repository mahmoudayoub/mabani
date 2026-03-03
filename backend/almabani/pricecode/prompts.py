"""
LLM Prompts for Price Code allocation.
Single-step logic with strict confidence levels (EXACT, HIGH).
Includes detailed criteria and rejection rules to ensure high accuracy.
"""

PRICECODE_MATCH_SYSTEM = (
    "You are a Price Code allocation expert for construction BOQ (Bill of Quantities) items. "
    "Your job is to identify the best matching Price Code from a list of candidates.\n"
    "You must return a single JSON object with the best match, or indicate no match.\n\n"
    "MATCHING PHILOSOPHY: PRACTICAL & ACCURATE\n"
    "- Your goal is to find the correct price code, not to prove that nothing matches.\n"
    "- Construction BOQ descriptions are often abbreviated or use different naming conventions for the same item.\n"
    "- Focus on the CORE WORK being described, not superficial wording differences.\n"
    "- A match is valid when the fundamental work, material, and scope align.\n"
)

PRICECODE_MATCH_USER = """TARGET ITEM:
{target_info}

CANDIDATES:
{candidates_text}

INSTRUCTIONS:
Perform a logical evaluation to find the best match.

1. CORE WORK IDENTIFICATION:
   - What is the fundamental work or material described in the target?
   - Which candidates describe the same fundamental work or material?
   - Ignore differences in naming convention (e.g., "Power Supply Cable" = "LV Power Cable" = "XLPE Cable" when specs match).

2. SPECIFICATION MATCH:
   - Compare key specifications: size, rating, material type, core count.
   - Example: "1x150 mm2" matches "1C x 150 mm2" (same cable cross-section).
   - Minor spec differences (e.g., insulation brand, jacket type) are acceptable for HIGH confidence.

3. UNIT COMPATIBILITY:
   - Check the TARGET UNIT against the likely unit of the candidate based on its description.
   - Note: Candidate units are not explicitly listed; infer from context (cables → m, concrete → m3, etc.).
   - If the candidate clearly implies an incompatible unit, reject it.

4. SCOPE CHECK — USE THE HIERARCHY:
   - The target's Hierarchy tells you the SCOPE (what work is being priced).
   - Read the hierarchy carefully:
     * "Supply ready mix concrete" → the target is SUPPLY of concrete material (not placing/installation).
     * "High yield steel bar reinforcement" → the target is REINFORCEMENT, not concrete.
     * "Supply and installation of formwork/shuttering" → the target is FORMWORK (supply + install).
   - Many candidates share the same element (raft, column, wall) but differ in SCOPE VARIANT (last letter of price code):
     * Codes ending in A = Concrete Only
     * Codes ending in B = With Reinforcement Only
     * Codes ending in C = With Formwork Only
     * Codes ending in D = Concrete + Reinforcement
     * Codes ending in E = Supply Only (material supply, no installation)
     * Codes ending in F = Supply + Installation (full scope)
   - MATCH THE SCOPE to the hierarchy context:
     * If hierarchy says "Supply ready mix concrete" → pick a Supply-related scope (E or A), NOT an installation scope.
     * If hierarchy says "Supply and installation" → pick a full-scope variant (F or D).
     * If hierarchy says "reinforcement" → pick the reinforcement variant (B).
     * If hierarchy says "formwork/shuttering" → pick a formwork variant (C).

5. SUBCATEGORY SPECIFICITY:
   - Codes with subcategory "00" (e.g., C 31 00 xxx) are generic templates.
   - Codes with a specific subcategory (e.g., C 31 13 xxx) are project-specific.
   - ALWAYS prefer a specific subcategory over "00" when both match the same work.

CONFIDENCE LEVELS:
- "EXACT" (Green): Functionally IDENTICAL.
  * Same work, same specs, same scope.
  * Example: "1x150 mm2 cable" == "1C x 150 mm2 cable".
  * Example: "DN200 HDPE Pipe" == "200mm HDPE Pipe".
- "HIGH" (Yellow): SAFE match with minor deviations.
  * Same core work but minor spec or naming differences.
  * Example: "Power Supply Cable 1x150 mm2" matched to "XLPE Cable 1C x 150 mm2" (same cable, different naming).
  * Example: "Concrete C30" vs "Concrete C35" for non-structural use.
  * Slightly different scope descriptions when the priced work is the same.
- "NO MATCH" (Red): Genuinely different work.
  * Different material type, fundamentally different scope, or clearly incompatible specifications.
  * Example: "Earthing cable" vs "Power cable" when specs don't align.

OUTPUT JSON:
{{
    "matched": true/false,
    "match_index": 1,  // 1-based index (if matched)
    "confidence_level": "EXACT" | "HIGH", // (if matched)
    "reason": "Brief explanation of match logic or rejection reason."
}}
"""
