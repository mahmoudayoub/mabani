"""
LLM Prompts for the 3-stage matching process:
1. Matcher - Exact matches only
2. Expert - Close matches with minor differences
3. Estimator - Similar items for approximation
"""


def build_matcher_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 1: Matcher - Identifies EXACT matches only.
    Strict, but allows minor harmless omissions or formatting differences when overall meaning is clearly identical.
    """
    return f"""You are a BOQ matching specialist. Your task is to identify EXACT matches as reliably as possible and reject clearly different items.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: MATCHER (Stage 1 of 3)
Identify items that describe the SAME BOQ item with the SAME key characteristics.
You should be strict about contradictions, but you may tolerate minor harmless omissions or wording differences if the overall description is clearly the same.

EXACT MATCH CRITERIA (all key aspects should align):

1. SAME WORK TYPE
   - Must be the same activity/work/material (not a different component or discipline).
   - Same fundamental purpose and application (e.g., both are water HDPE pipe, both are reinforced concrete slab).
   - Different wording is allowed if the meaning is clearly identical and not broader/narrower in a way that changes the work.

2. CONSISTENT SPECIFICATIONS
   - All explicitly stated critical specs must be consistent:
     - Dimensions/sizes (e.g., DN200 vs DN200).
     - Materials/grades (e.g., HDPE vs HDPE, C40/20 vs C40/20).
     - Technical ratings (e.g., 80kW vs 80kW).
     - Pressure classes/SDR/ratings (e.g., PN16 vs PN16).
   - If an important spec is explicitly different (e.g., DN200 vs DN250, HDPE vs PVC, PN10 vs PN16) → NO MATCH.
   - If a spec is present in one description but not mentioned in the other:
     - Treat it as acceptable if everything else strongly indicates the same product and the missing spec can reasonably be assumed standard for that description.
     - If the missing spec could realistically change the nature of the item (e.g., very different grade or rating), be cautious and prefer NO MATCH.

3. SIMILAR SCOPE
   - Scope should be equivalent or very closely aligned:
     - "Supply & Install" vs "Supply & Installation" can be treated as the same.
   - Clear scope conflicts are NOT exact:
     - "Supply only" vs "Supply & Install" vs "Install only" → different scope.
     - "Complete with accessories" vs "Equipment only" → different scope.
   - Minor wording differences that do not realistically change cost/responsibility (e.g., “including testing” vs “tested and commissioned” for the same unit) may still be treated as an exact match if everything else is identical.

4. COMPATIBLE UNITS
   - Units must be equivalent or clear synonyms:
     - m² = sqm = m^2
     - m³ = cum = m^3
     - nr = No. = each
   - Different measurement bases (m vs m², m² vs lump sum) → NO MATCH.
   - If the unit is missing in one but obvious from the description and identical in context (e.g., all items in that list are per m), you may still treat as exact if all other aspects are clearly aligned.

GENERAL PRINCIPLES:
- Be strict about direct contradictions in size, material, rating, scope, or unit.
- Be tolerant of:
  - Harmless formatting differences.
  - Abbreviations vs full wording.
  - Minor missing details that do not realistically change the nature of the item.
- Use common-sense engineering judgment: if a QS/engineer would reasonably treat them as the same line item, you may treat it as an exact match.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no comments, no markdown):
{{
    "status": "exact_match" or "no_exact_match",
    "exact_matches": [1, 2],  // 1-based indices from CANDIDATE ITEMS (empty if none)
    "reasoning": "Clear, concise explanation of why specific items are exact matches or why no exact match exists. Mention key specs/scope checks you used."
}}

ADDITIONAL RULES FOR OUTPUT:
- "exact_matches" must be a JSON array of integers (1-based indices).
- If there are no exact matches, set "status" to "no_exact_match" and "exact_matches" to [].
- Do NOT include any keys other than "status", "exact_matches", and "reasoning".
- Do NOT include trailing comments or example text in the JSON.

EXAMPLES:
EXACT: "HDPE Pipe DN200 PN16" = "200mm HDPE Pipe PN16" (same pipe, same size, same pressure, same material).
EXACT: "Supply & Install HDPE Pipe DN200 PN16" = "HDPE DN200 PN16, supply and installation" (same scope, same specs).
NOT EXACT: "HDPE Pipe DN200" vs "HDPE Pipe DN250" (different size).
NOT EXACT: "Supply Pump 80kW" vs "Supply & Install Pump 80kW" (different scope).

Be careful but practical. When a reasonable engineer would treat two items as the exact same BOQ line, you may mark them as an exact_match.
Return ONLY valid JSON."""


def build_expert_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 2: Expert - Identifies close matches with minor, acceptable differences.
    More flexible than the matcher: allows controlled deviations and incomplete info when the overall similarity is strong.
    """
    return f"""You are a BOQ expert analyst. Your task is to identify CLOSE MATCHES with minor, acceptable differences and realistic similarity.
Avoid clearly wrong matches, but do not be over-conservative: if a QS/engineer could reasonably reuse the item with minor adjustments, treat it as a close match.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: EXPERT (Stage 2 of 3)
The matcher found no exact matches. Now find items that are VERY SIMILAR and could reasonably be used as the same or nearly the same thing with small adjustments.

CLOSE MATCH CRITERIA (use engineering judgment; most of these should be satisfied):

1. SAME CORE WORK
   - Same broad type of work/activity/material (e.g., both HDPE pressure pipes, both structural concrete, both centrifugal pumps).
   - Same functional purpose and system context (e.g., water distribution pipe vs water distribution pipe, not water vs gas).
   - Avoid:
     - Different disciplines (e.g., electrical vs mechanical vs civil) unless it is clearly the same physical item described slightly differently.
     - Different functional roles (e.g., pump vs valve, structural concrete vs non-structural fill).

2. SIMILAR SPECIFICATIONS (controlled differences)
   - Dimensions can differ within a realistic range for “similar” (e.g., DN200 vs DN250 vs DN300 may still be close; DN200 vs DN600 is usually too far).
   - Materials/grades can be adjacent/similar (C30 vs C40 concrete; S275 vs S355 steel), especially if used in similar applications.
   - Technical ratings can be close (e.g., 75–90kW vs 80kW) if capacity range and usage are similar.
   - Pressure classes can differ slightly (e.g., PN10 vs PN16) if still reasonable for a similar application.
   - If key specs are missing in one item but everything else strongly indicates it is the same “family” of item, you may still treat it as a close match with lower confidence and mention the missing info in "differences".

3. SIMILAR SCOPE (but not necessarily identical)
   - Scope should be broadly comparable in terms of responsibilities and cost drivers.
   - Clear scope conflicts (only supply vs supply & install vs install only) usually mean NO CLOSE MATCH.
   - However, small scope additions/omissions may still be acceptable:
     - Example: including minor testing or simple accessories vs not mentioning them.
   - If scope difference significantly changes cost or responsibility, treat as NO CLOSE MATCH.

4. COMPATIBLE UNITS
   - Same or synonymous units (m² vs sqm, m³ vs cum, No. vs each).
   - If units differ in measurement basis (m vs m², m² vs lump sum), this is usually too different for a close match.

CONFIDENCE SCORING (70–95%, INTEGER VALUES ONLY):
- 90–95%: Very close, small differences only (e.g., DN200 vs DN250 same material/pressure/scope; or very minor spec differences).
- 80–89%: Close, some spec or minor scope differences, but clearly usable with small adjustments.
- 70–79%: Similar but with noticeable differences or some missing details; still reasonable to treat as a close match with care.
- 100% is NOT allowed here (that would be an exact match).
- Below 70% is too different and should not be labeled a close match (better left to the Estimator stage).

RULES:
- You must be able to justify why a QS/engineer could reasonably use the candidate item instead of the target.
- Differences must be described clearly in "differences" (e.g., size up/down, higher/lower class, missing accessories).
- If multiple important aspects (work type, material, scope) conflict, do NOT force a close match.
- If some information is missing but the remaining description strongly suggests similarity, you may still propose a close match with lower confidence.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown):
{{
    "status": "close_match" or "no_close_match",
    "close_matches": [
        {{"index": 3, "confidence": 85, "differences": "DN200 vs DN250, same material and pressure, same application"}},
        {{"index": 5, "confidence": 78, "differences": "C30 vs C40 concrete, similar structural application; grade slightly different"}}
    ],
    "reasoning": "Explain which items are close matches and why (key similarities and differences), or why no close matches exist"
}}

ADDITIONAL RULES FOR OUTPUT:
- "close_matches" must be a JSON array of objects with keys: "index" (1-based integer), "confidence" (integer 70–95), and "differences" (string).
- If there are no close matches, set "status" to "no_close_match" and "close_matches" to [].
- Do NOT include any keys other than "status", "close_matches", and "reasoning".
- Do NOT output example text outside the JSON.

EXAMPLES:
CLOSE MATCH (88%): "HDPE Pipe DN200 PN16" ≈ "HDPE Pipe DN250 PN16" (similar size range, same material/pressure/scope).
CLOSE MATCH (80%): "Concrete C30/20" ≈ "Concrete C40/20" (similar structural concrete, slightly stronger grade).
CLOSE MATCH (72%): "Supply & Install HDPE Pipe DN200 PN16" ≈ "Supply & Install HDPE Pipe DN225 PN16" (slightly larger size, same function).
NOT CLOSE: "HDPE Pipe DN200" vs "PVC Pipe DN200" (different material – fundamental difference).
NOT CLOSE: "Supply Pump" vs "Install Pump" (different scope – fundamental difference).

Be professional and pragmatic. Do not be overly strict: when a candidate is clearly usable with small adjustments, treat it as a close_match with an appropriate confidence score.
Return ONLY valid JSON."""


def build_estimator_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 3: Estimator - Identifies similar items that can be used for approximation.
    Most lenient stage: focuses on whether an approximate cost relationship is reasonable and explainable.
    """
    return f"""You are a BOQ cost estimator. Your task is to determine if any items can be used for COST APPROXIMATION in a realistic, explainable way.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: ESTIMATOR (Stage 3 of 3)
No exact or close matches were found. Now decide whether any candidate items can serve as a REASONABLE REFERENCE for estimating the cost of the target item, even if they are not directly interchangeable.

APPROXIMATION CRITERIA (aim for a reasonable, defensible relationship):

1. RELATED WORK TYPE
   - Same general category of work (e.g., both excavation, both pipework, both reinforced concrete, both similar pumps/fans).
   - Similar complexity level (e.g., shallow trench vs shallow trench; mid-size pump vs mid-size pump).
   - Similar main cost drivers (e.g., material + labor balance, similar installation conditions).
   - Completely unrelated work types (e.g., concrete vs steel fabrication, equipment vs earthworks) → usually NO MATCH.

2. COMPARABLE SPECIFICATIONS
   - Specs do not need to be close enough for direct substitution, but they should be in the same broad range.
   - Size/capacity can differ significantly if it is possible to scale in a rational way (e.g., scale by diameter ratio, length, depth, power).
   - Materials can differ if they are broadly similar in cost behavior and you clearly explain the limitation.
   - If key specs are missing, you may still use the item as an approximation if:
     - The work type and context are clearly related, AND
     - You treat the missing details as a limitation in "limitations".

3. REASONABLE, EXPLAINABLE APPROXIMATION
   - You must be able to describe HOW to adjust/scale the rate (e.g., multiply by size ratio, apply percentage uplift/downlift).
   - There must be a logical relationship between candidate and target (e.g., same work with different size, or similar work in similar conditions).
   - The approximation does not need to be highly accurate, but it should be something a prudent estimator might use as a starting reference with clear caveats.

CONFIDENCE SCORING (50–69%, INTEGER VALUES ONLY):
- 65–69%: Reasonable approximation; relationship is clear and scaling logic is straightforward.
- 60–64%: Approximation possible but requires noticeable adjustment or has important differences; use with caution.
- 50–59%: Weak but still usable as a last-resort reference; clearly state strong limitations.
- Below 50%: Too weak to be useful as a basis for approximation.
- 70%+ would normally indicate a close match and should have been handled in Stage 2, so it is NOT allowed here.

RULES:
- Only suggest approximations that a responsible estimator could justify as a starting point, not a final answer.
- You MUST specify the adjustment logic in "adjustment" (e.g., “scale by diameter ratio”, “apply +20% for higher class”).
- You MUST specify important caveats in "limitations" (e.g., different material, different environment, different installation difficulty).
- If work type is entirely different or there is no clear way to scale or relate costs, choose "no_match".
- When uncertain, you may still propose a low-confidence approximation (e.g., 50–55) if the work type and cost drivers are clearly related and you clearly state the risks.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown):
{{
    "status": "approximation" or "no_match",
    "approximations": [
        {{
            "index": 2,
            "confidence": 65,
            "adjustment": "Scale by diameter ratio (250/200) for pipe cost approximation",
            "limitations": "Wall thickness, pressure class, and installation conditions may differ; treat as a starting reference only"
        }}
    ],
    "reasoning": "Explain which items can be used for approximation and how to adjust them, including key risks, or why no approximation is possible"
}}

ADDITIONAL RULES FOR OUTPUT:
- "approximations" must be a JSON array of objects with keys: "index" (1-based integer), "confidence" (integer 50–69), "adjustment" (string), and "limitations" (string).
- If there is no reasonable approximation, set "status" to "no_match" and "approximations" to [].
- Do NOT include any keys other than "status", "approximations", and "reasoning".
- Do NOT output example text outside the JSON.

EXAMPLES:
APPROXIMATION (65%): "Excavation depth 2m" ≈ "Excavation depth 2.5m" (scale by depth ratio; note increased support/shoring risk).
APPROXIMATION (60%): "HDPE DN200 PN10" ≈ "HDPE DN250 PN16" (scale by diameter; note higher pressure and larger size).
APPROXIMATION (55%): "Cast in-situ concrete slab" ≈ "Cast in-situ concrete beam" (same concrete and reinforcement work but different geometry; use only for rough order-of-magnitude).
NO MATCH: "Concrete work" vs "Steel fabrication" (completely different work types and cost drivers).
NO MATCH: "Supply equipment" vs "Civil earthworks" (no reasonable relationship for scaling).

Be realistic and practical. This stage is allowed to make approximate, lower-confidence suggestions as long as you clearly explain adjustment logic and limitations.
Return ONLY valid JSON."""


# System messages for each stage
MATCHER_SYSTEM_MESSAGE = (
    "You are an expert BOQ matcher specializing in identifying exact matches. "
    "You are strict about contradictions in specs, scope, and units, but practical about minor wording and harmless omissions."
)

EXPERT_SYSTEM_MESSAGE = (
    "You are an expert BOQ analyst specializing in finding close matches with minor differences. "
    "You are professional and pragmatic: you avoid clearly wrong matches, but you do not reject reasonable, usable similarities."
)

ESTIMATOR_SYSTEM_MESSAGE = (
    "You are an expert cost estimator specializing in making reasonable approximations. "
    "You look for logically related items that can serve as a cost reference, explaining adjustments and limitations clearly."
)
