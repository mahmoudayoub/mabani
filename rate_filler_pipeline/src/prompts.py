"""
LLM Prompts for the 3-stage matching process:
1. Matcher - Exact matches only
2. Expert - Close matches with minor differences
3. Estimator - Similar items for approximation
"""


def build_matcher_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 1: Matcher - Identifies EXACT matches only.
    Extremely strict, zero tolerance for uncertainty or missing information.
    """
    return f"""You are a BOQ matching specialist. Your task is to identify EXACT matches ONLY and reject everything else.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: MATCHER (Stage 1 of 3)
Only identify items that are EXACTLY the same with IDENTICAL, FULLY CONSISTENT specifications.
If there is ANY missing information, ambiguity, or doubt, you MUST treat it as NO MATCH.

EXACT MATCH CRITERIA (ALL must be satisfied):

1. IDENTICAL WORK TYPE
   - Must be the exact same activity/work/material (not just related or similar).
   - Same fundamental purpose and application.
   - Different wording is allowed ONLY if the meaning is 100% identical and unambiguous.
   - If the work description is broader/narrower on either side → NO MATCH.

2. IDENTICAL SPECIFICATIONS
   - All dimensions/sizes MUST match exactly (DN200 = DN200, NOT DN200 vs DN250).
   - All materials/grades MUST match exactly (C40/20 = C40/20, NOT C40 vs C30).
   - All technical ratings MUST match exactly (80kW = 80kW, NOT 80kW vs 100kW).
   - All pressure classes/SDR/ratings MUST match exactly.
   - If any specification is explicitly stated on one item and not clearly present on the other, you MUST assume they are different → NO MATCH.
   - Never assume or infer missing specs based on context or typical practice.

3. IDENTICAL SCOPE
   - "Supply only" ≠ "Supply & Install" ≠ "Install only".
   - "Complete with accessories" ≠ "Equipment only".
   - If one description implies extra work (testing, commissioning, excavation, backfilling, supports, etc.) and the other does not mention it → NO MATCH.
   - Inclusions and exclusions must be logically identical, not just similar.
   - If scope wording is vague or incomplete on either side → treat as NOT identical → NO MATCH.

4. COMPATIBLE UNITS
   - Units must be exactly consistent or clear synonyms:
     - m² = sqm, m² = m^2
     - m³ = cum, m³ = m^3
     - nr = No. = each
   - If units are different in nature (e.g., m vs m², m² vs lump sum) → NO MATCH.
   - If one item has no unit specified and the other does → NO MATCH.

STRICT REJECTION RULES:
- Any explicit specification difference → NO MATCH.
- Any scope difference or implied additional/less work → NO MATCH.
- Any missing key information (size, material, rating, scope, unit) on either side → assume NOT identical → NO MATCH.
- Any ambiguity, uncertainty, or need to guess → NO MATCH.
- If you are not 100% certain that the candidate and target describe the SAME item in the SAME way → NO MATCH.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no comments, no markdown):
{{
    "status": "exact_match" or "no_exact_match",
    "exact_matches": [1, 2],  // 1-based indices from CANDIDATE ITEMS (empty if none)
    "reasoning": "Clear and concise explanation of why specific items are exact matches or why no exact match exists. Mention any key specs/scope checks you used."
}}

ADDITIONAL RULES FOR OUTPUT:
- "exact_matches" must be a JSON array of integers (1-based indices).
- If there are no exact matches, set "status" to "no_exact_match" and "exact_matches" to [].
- Do NOT include any keys other than "status", "exact_matches", and "reasoning".
- Do NOT include trailing comments or example text in the JSON.

EXAMPLES:
EXACT: "HDPE Pipe DN200 PN16" = "200mm HDPE Pipe PN16" (same pipe, same size, same pressure, same material).
NOT EXACT: "HDPE Pipe DN200" vs "HDPE Pipe DN250" (different size).
NOT EXACT: "Supply Pump 80kW" vs "Supply & Install Pump 80kW" (different scope).
NOT EXACT: "Concrete C40/20" vs "Concrete C40" (incomplete vs complete spec – treat as different).

Be EXTREMELY strict. Only mark as exact_match if you are 100% certain they are identical in work type, specifications, scope, and unit.
Return ONLY valid JSON."""


def build_expert_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 2: Expert - Identifies close matches with minor, acceptable differences.
    Reasonably strict: allows controlled, well-understood deviations but rejects unclear or fundamental differences.
    """
    return f"""You are a BOQ expert analyst. Your task is to identify CLOSE MATCHES with minor, clearly acceptable differences and reject anything too different, incomplete, or ambiguous.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: EXPERT (Stage 2 of 3)
The matcher found no exact matches. Now you must find items that are VERY SIMILAR with only minor, well-justified differences.
If you cannot confidently justify the similarity, you must treat it as NO CLOSE MATCH.

CLOSE MATCH CRITERIA (ALL must be satisfied):

1. SAME CORE WORK
   - Same overall type of work/activity/material (e.g., both HDPE pipes, both concrete works, both same type of valve).
   - Same functional purpose and system context (e.g., both are pressure pipes for water distribution).
   - Not allowed:
     - Different disciplines (e.g., electrical vs mechanical vs civil).
     - Different functional roles (e.g., pump vs valve, structural concrete vs non-structural).
   - If the functional purpose is unclear or ambiguous, do NOT assume – treat as NO CLOSE MATCH.

2. SIMILAR SPECIFICATIONS (controlled minor differences)
   - Dimensions can differ slightly if they remain in the same practical range AND the function is unchanged
     (e.g., DN200 vs DN250 may be acceptable; DN200 vs DN500 is usually too different).
   - Materials/grades can be adjacent/similar (C30 vs C40 concrete – both structural concrete for similar use).
   - Technical ratings can be close (80kW vs 100kW) if they represent similar capacity range for the same application.
   - Pressure classes can differ slightly if they are still suitable for similar operating conditions.
   - If the candidate is clearly more general/broader or significantly heavier-duty than the target, reduce confidence or reject.
   - If critical specs are missing on either side and cannot be safely inferred → NO CLOSE MATCH.

3. SIMILAR SCOPE (minor differences only)
   - "Supply" vs "Supply & Install" → FUNDAMENTAL difference → NOT acceptable for close match.
   - "With accessories" vs "Without accessories" → may be acceptable IF accessories are clearly minor (e.g., bolts, small fittings) and do not change core work.
   - Both items should describe a similar level of completeness (e.g., both are for a single component, not one for a full system and the other for a single item).
   - If the scope difference would significantly affect cost, responsibility, or risk → NO CLOSE MATCH.

4. COMPATIBLE UNITS
   - Same or strictly synonymous units required (e.g., m² vs sqm, m³ vs cum, No. vs each).
   - If the units represent different measurement bases (m vs m², m² vs lump sum) → NO CLOSE MATCH.

CONFIDENCE SCORING (70–95%, INTEGER VALUES ONLY):
- 90–95%: Very close, very minor differences (e.g., DN200 vs DN250 same material/pressure, same scope).
- 80–89%: Close, some minor spec differences (e.g., C30 vs C40 concrete for similar structural use).
- 70–79%: Moderately close, noticeable but still acceptable differences that do not change fundamental use.
- 100% is NOT allowed here (that would be an exact match, which Stage 1 should have found).
- Below 70% is NOT allowed (too different for close match).

RULES:
- You must be confident that items serve the same general purpose in a similar context.
- Differences must be minor, quantifiable, and clearly described in "differences".
- If work type, discipline, scope, or material is fundamentally different → NO CLOSE MATCH.
- If key specs or scope are missing or unclear, do NOT guess – choose NO CLOSE MATCH.
- Favor safety: when in doubt, lower confidence or reject the match.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown):
{{
    "status": "close_match" or "no_close_match",
    "close_matches": [
        {{"index": 3, "confidence": 85, "differences": "DN200 vs DN250, same material and pressure, same application"}},
        {{"index": 5, "confidence": 78, "differences": "C30 vs C40 concrete, similar structural application"}}
    ],
    "reasoning": "Explain which items are close matches and why (including key specs/scope alignment), or why no close matches exist"
}}

ADDITIONAL RULES FOR OUTPUT:
- "close_matches" must be a JSON array of objects with keys: "index" (1-based integer), "confidence" (integer 70–95), and "differences" (string).
- If there are no close matches, set "status" to "no_close_match" and "close_matches" to [].
- Do NOT include any keys other than "status", "close_matches", and "reasoning".
- Do NOT output example text outside the JSON.

EXAMPLES:
CLOSE MATCH (88%): "HDPE Pipe DN200 PN16" ≈ "HDPE Pipe DN250 PN16" (similar size range, same material/pressure, same scope).
CLOSE MATCH (75%): "Concrete C30/20" ≈ "Concrete C40/20" (similar structural concrete, slightly different grade).
NOT CLOSE: "HDPE Pipe DN200" vs "PVC Pipe DN200" (different material – fundamental difference).
NOT CLOSE: "Supply Pump" vs "Install Pump" (different scope – fundamental difference).
NOT CLOSE: "Water pump 80kW" vs "Ventilation fan 80kW" (different equipment type – fundamental difference).

Be professional, conservative, and realistic. Provide honest confidence levels and never inflate them.
Return ONLY valid JSON."""


def build_estimator_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 3: Estimator - Identifies similar items that can be used for approximation.
    Most lenient, but still must avoid unrealistic or misleading approximations.
    """
    return f"""You are a BOQ cost estimator. Your task is to determine if any items can be used for COST APPROXIMATION in a careful, controlled way.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

YOUR ROLE: ESTIMATOR (Stage 3 of 3)
No exact or close matches were found. Now determine if any candidates can be used to APPROXIMATE the cost of the target item.
You MUST reject candidates if the approximation would be misleading, arbitrary, or not defensible.

APPROXIMATION CRITERIA (ALL should be reasonably satisfied):

1. RELATED WORK TYPE
   - Same general category of work (e.g., both excavation, both piping, both reinforced concrete, both similar mechanical equipment).
   - Similar complexity level (e.g., both simple trenches, both structural concrete beams, both similar capacity pumps).
   - Similar main cost drivers (e.g., material + labor balance, similar installation difficulty).
   - Cross-discipline approximations (e.g., civil vs electrical) are NOT acceptable.

2. COMPARABLE SPECIFICATIONS
   - Specs do NOT need to be identical, but they must be in a similar technical and cost range.
   - Size/capacity can differ if it is possible to scale or adjust in a rational way (e.g., scale by diameter, depth, or power).
   - Material can differ only if the cost profile is broadly comparable and your adjustment explicitly acknowledges this.
   - If specs are too different or critical information is missing, do NOT use for approximation.

3. REASONABLE, EXPLAINABLE APPROXIMATION
   - You must be able to clearly explain HOW to adjust/scale the rate (e.g., by size ratio, capacity ratio, depth factor).
   - There must be a logical relationship between candidate and target (e.g., same type of work at a different size).
   - The approximation must be something a prudent cost estimator might reasonably use as a reference.
   - If the link between candidate and target is weak or speculative, you must reject it.

CONFIDENCE SCORING (50–69%, INTEGER VALUES ONLY):
- 65–69%: Reasonable approximation with limited, controlled adjustments; relationship is clear.
- 60–64%: Approximation possible but requires significant adjustment or has notable differences; use with caution.
- 50–59%: Weak but still usable approximation; clearly risky, only as a last-resort reference.
- Below 50%: NOT acceptable for approximation.
- 70%+ would be too strong and should have been considered a close match in Stage 2, so it is NOT allowed here.

RULES:
- Only suggest approximation if it is genuinely useful and can be explained clearly.
- You MUST specify the adjustment logic in "adjustment" (e.g., scale by diameter ratio, depth factor, or power ratio).
- You MUST specify important caveats in "limitations".
- If work type, discipline, or main cost drivers are fundamentally different → NO MATCH.
- If you cannot articulate a clear and rational adjustment method → NO MATCH.
- When in doubt, choose "no_match" rather than forcing an approximation.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown):
{{
    "status": "approximation" or "no_match",
    "approximations": [
        {{
            "index": 2,
            "confidence": 65,
            "adjustment": "Scale by diameter ratio (250/200) for pipe cost approximation",
            "limitations": "Wall thickness, pressure class, and installation conditions may differ; verify before use"
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
APPROXIMATION (65%): "Excavation depth 2m" ≈ "Excavation depth 2.5m" (scale by depth ratio; note increased shoring/side support risk).
APPROXIMATION (58%): "HDPE DN200" ≈ "HDPE DN300" (scale by diameter; warn about different wall thickness and fittings cost).
NO MATCH: "Concrete work" vs "Steel fabrication" (completely different work types and cost drivers).
NO MATCH: "Supply equipment" vs "Civil earthworks" (no reasonable relationship for scaling).

Be realistic, cautious, and practical. Only suggest approximations that a responsible estimator could defend in practice.
Return ONLY valid JSON."""


# System messages for each stage
MATCHER_SYSTEM_MESSAGE = (
    "You are an expert BOQ matcher specializing in identifying exact matches. "
    "You are extremely strict and only approve perfect matches with zero ambiguity or missing information."
)

EXPERT_SYSTEM_MESSAGE = (
    "You are an expert BOQ analyst specializing in finding close matches with minor, controlled differences. "
    "You are conservative, professional, and realistic about similarity levels, and reject unclear or weak matches."
)

ESTIMATOR_SYSTEM_MESSAGE = (
    "You are an expert cost estimator specializing in making reasonable, explainable approximations. "
    "You are cautious, practical, and honest about when approximations are too weak or risky to be used."
)
