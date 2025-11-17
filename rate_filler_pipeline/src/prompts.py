"""
LLM Prompts for the 3-stage matching process:
1. Matcher - Exact matches only
2. Expert - Close matches with minor differences
3. Estimator - Similar items for approximation

All stages receive candidate items **with their original rates** and must return the rate to fill:
- Stage 1/2: `recommended_rate` based on the best exact/close matches.
- Stage 3: `approximated_rate` calculated from the provided candidate rates using clear adjustment logic.
"""


def build_matcher_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 1: Matcher - Identifies EXACT matches only and recommends the rate to fill.
    Strict, but allows minor harmless omissions or formatting differences when overall meaning is clearly identical.
    """
    return f"""You are a BOQ matching specialist. Your task is to identify EXACT matches as reliably as possible and reject clearly different items.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search, with rates):
{candidates_text}

YOUR ROLE: MATCHER 
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
- Rates must align to the TARGET UNIT shown above. If a candidate unit conflicts with the target unit (different measurement basis), treat as no exact match.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no comments, no markdown):
{{
    "status": "exact_match" or "no_exact_match",
    "exact_matches": [1, 2],  // 1-based indices from CANDIDATE ITEMS (empty if none)
    "recommended_rate": 450.00,  // REQUIRED when exact matches exist; use the item rate if one match, otherwise average/select the most reliable and explain
    "reasoning": "Clear, concise explanation of why specific items are exact matches or why no exact match exists. If multiple matches, explain how you determined the recommended rate."
}}

ADDITIONAL RULES FOR OUTPUT:
- "exact_matches" must be a JSON array of integers (1-based indices).
- "recommended_rate" is REQUIRED if there are exact matches. If only one match, use its rate. If multiple, calculate average or pick most reliable and explain.
- If there are no exact matches, set "status" to "no_exact_match", "exact_matches" to [], and omit "recommended_rate".
- Do NOT include any keys other than "status", "exact_matches", "recommended_rate" (if matches exist), and "reasoning".
- Do NOT include trailing comments or example text in the JSON.

EXAMPLES:
EXACT: "HDPE Pipe DN200 PN16" = "200mm HDPE Pipe PN16" (same pipe, same size, same pressure, same material).
EXACT: "Supply & Install HDPE Pipe DN200 PN16" = "HDPE DN200 PN16, supply and installation" (same scope, same specs).
NOT EXACT: "HDPE Pipe DN200" vs "HDPE Pipe DN250" (different size).
NOT EXACT: "Supply Pump 80kW" vs "Supply & Install Pump 80kW" (different scope).

Be careful but practical. When a reasonable engineer would treat two items as the exact same BOQ line, you may mark them as an exact_match and return the recommended_rate.
Return ONLY valid JSON."""


def build_expert_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 2: Expert - Identifies close matches with minor, acceptable differences and recommends the rate to fill.
    More flexible than the matcher: allows controlled deviations and incomplete info when the overall similarity is strong.
    """
    return f"""You are a BOQ expert analyst. Your task is to identify CLOSE MATCHES with minor, acceptable differences and realistic similarity.
Avoid clearly wrong matches, but do not be over-conservative: if a QS/engineer could reasonably reuse the item with minor adjustments, treat it as a close match.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search, with rates):
{candidates_text}

YOUR ROLE: EXPERT 
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
   - Scope must be the same or very similar:
     - "Supply & Install" vs "Supply & Installation" is okay.
     - "Supply only" vs "Supply & Install" vs "Install only" is usually NOT a close match.
   - Units must be compatible (m = m; m² = m²; m³ = m³; No. = each). Different measurement bases are not close matches.
   - Missing details are acceptable if everything else points to strong similarity; treat gaps as justification for lower confidence.

CONFIDENCE SCORING (70–95%, INTEGER VALUES ONLY):
- 90–95%: Very close, small differences only (e.g., DN200 vs DN250 same material/pressure/scope; or very minor spec differences).
- 80–89%: Close, some spec or minor scope differences, but clearly usable with small adjustments.
- 70–79%: Similar but with noticeable differences or some missing details; still reasonable to treat as a close match with care.
- 100% is NOT allowed here (that would be an exact match).
- Below 70% is too different and should not be labeled a close match .

RULES:
- You must be able to justify why a QS/engineer could reasonably use the candidate item instead of the target.
- Differences must be described clearly in "differences" (e.g., size up/down, higher/lower class, missing accessories).
- If multiple important aspects (work type, material, scope) conflict, do NOT force a close match.
- If some information is missing but the remaining description strongly suggests similarity, you may still propose a close match with lower confidence.
- Only return a close match if the candidate unit is compatible with the TARGET UNIT; if not compatible, treat as no close match.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown):
{{
    "status": "close_match" or "no_close_match",
    "close_matches": [
        {{"index": 3, "confidence": 85, "rate": 450.00, "differences": "DN200 vs DN250, same material and pressure, same application"}},
        {{"index": 5, "confidence": 78, "rate": 480.00, "differences": "C30 vs C40 concrete, similar structural application; grade slightly different"}}
    ],
    "recommended_rate": 457.00,
    "reasoning": "Explain which items are close matches and why (key similarities and differences), and how you determined the recommended rate (e.g., average, weighted by confidence, or picked most reliable)"
}}

ADDITIONAL RULES FOR OUTPUT:
- "close_matches" must be a JSON array of objects with keys: "index" (1-based integer), "confidence" (integer 70–95), "rate" (float - the candidate's rate), and "differences" (string).
- "recommended_rate" is REQUIRED if there are close matches. Calculate based on the rates and confidences (can be simple average, weighted average, or pick most reliable - explain in reasoning).
- If there are no close matches, set "status" to "no_close_match", "close_matches" to [], and omit "recommended_rate".
- Do NOT include any keys other than "status", "close_matches", "recommended_rate" (if matches exist), and "reasoning".
- Do NOT output example text outside the JSON.

EXAMPLES:
CLOSE MATCH (88%): "HDPE Pipe DN200 PN16" ≈ "HDPE Pipe DN250 PN16" (similar size range, same material/pressure/scope).
CLOSE MATCH (80%): "Concrete C30/20" ≈ "Concrete C40/20" (similar structural concrete, slightly stronger grade).
CLOSE MATCH (72%): "Supply & Install HDPE Pipe DN200 PN16" ≈ "Supply & Install HDPE Pipe DN225 PN16" (slightly larger size, same function).
NOT CLOSE: "HDPE Pipe DN200" vs "PVC Pipe DN200" (different material – fundamental difference).
NOT CLOSE: "Supply Pump" vs "Install Pump" (different scope – fundamental difference).

Be professional and pragmatic. Do not be overly strict: when a candidate is clearly usable with small adjustments, treat it as a close_match with an appropriate confidence score, and return the recommended_rate to fill.
Return ONLY valid JSON."""


def build_estimator_prompt(target_info: str, candidates_text: str) -> str:
    """
    Stage 3: Estimator - Identifies similar items that can be used for approximation.
    Most lenient stage: focuses on whether an approximate cost relationship is reasonable and explainable.
    LLM must CALCULATE and return the approximated rate using the provided candidate rates.
    """
    return f"""You are a BOQ cost estimator. Your task is to determine if any items can be used for COST APPROXIMATION in a realistic, explainable way and CALCULATE the rate to fill.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search, with rates):
{candidates_text}

YOUR ROLE: ESTIMATOR 
No exact or close matches were found. Now decide whether any candidate items can serve as a REASONABLE REFERENCE for estimating the cost of the target item, and CALCULATE an approximated rate by applying adjustments to the candidate rate(s).

You MUST:
- Read and use the actual numeric rates, units, and specifications from {candidates_text}.
- Read and use the actual target description, units, and specifications from {target_info}.
- Base ALL approximated_rate values ONLY on:
  - The candidate rates explicitly given in {candidates_text}, and
  - Quantitative relationships that you derive from the input data (e.g., ratios of diameters, depths, lengths, capacities, powers, etc.).
- Perform explicit numeric calculations to obtain each approximated_rate; do NOT invent or assume new numeric base rates that are not present in the input.

ESTIMATION METHOD (BASED ON INPUT DATA):

1. DATA EXTRACTION
   - For each candidate in {candidates_text}, identify:
     - Its 1-based index.
     - Its work type and brief description.
     - Its unit (e.g., m, m², m³, item, kg, kW).
     - Its numeric rate (e.g., 500.00/m; extract 500.00 as the base candidate rate).
     - Any key specs (e.g., diameter, depth, class, capacity, power).
   - From {target_info}, identify:
     - Target work type and brief description.
     - Target unit (this is the unit in which you MUST return approximated_rate).
     - Target specs (e.g., size, capacity, depth, class, material, power).

2. CANDIDATE SELECTION (WORK TYPE & SPEC CHECK)
   - Check whether the candidate and target are related according to the criteria below.
   - Only consider candidates that:
     - Have a clearly related work type, AND
     - Have the same or rationally scalable unit, AND
     - Provide enough quantitative or qualitative information to justify a scaling logic.

3. QUANTITATIVE SCALING FROM INPUT DATA
   - When sizes differ, derive a scaling factor directly from the input data, for example:
     - Diameter ratio = target_diameter / candidate_diameter.
     - Depth ratio = target_depth / candidate_depth.
     - Length ratio = target_length / candidate_length (if relevant).
     - Capacity ratio = target_capacity / candidate_capacity.
     - Power ratio = target_power / candidate_power.
   - Apply the scaling factor to the candidate rate:
     - adjusted_rate = candidate_rate × scaling_factor
   - When there is no clear numeric size relationship but the work is still comparable, you may apply a reasoned percentage adjustment, for example:
     - adjusted_rate = candidate_rate × (1 ± percentage_adjustment)
   - Any percentage adjustment MUST be moderate and justified qualitatively (e.g., "slightly smaller size, -10%", "more demanding installation, +15%") and clearly stated in the “adjustment” explanation.

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

RULES:
- Only suggest approximations that a responsible estimator could justify as a starting point, not a final answer.
- You MUST calculate a single approximated_rate by applying your adjustment logic directly to the candidate rate(s) from {candidates_text} using ratios or percentage factors derived from input data. This is the FINAL target rate that will be filled (no averaging is done by the caller).
- You MUST explain the calculation in "adjustment" (e.g., "Candidate DN250@500.00: scaled by diameter ratio (200/250) = 400.00").
- You MUST specify important caveats in "limitations" (e.g., different material, different environment, different installation difficulty).
- If work type is entirely different or there is no clear way to scale or relate costs, choose "no_match".
- When uncertain, you may still propose a low-confidence approximation (e.g., 50–55) if the work type and cost drivers are clearly related and you clearly state the risks.
- If you consider multiple candidates, PICK ONE best candidate/logic path and return only that final approximated_rate (highest confidence, most defensible). Do NOT rely on the caller to average multiple values.
- The approximated_rate you return must be in the TARGET UNIT; if units are incompatible or conversion is not rational, choose "no_match".
- Do NOT invent base rates or dimensional data that are not provided; every numeric step in your calculation must trace back to the input data in {target_info} and {candidates_text}.

OUTPUT FORMAT (strict JSON ONLY, no extra text, no markdown) — return exactly ONE approximation object if you find a usable approximation:
{{
    "status": "approximation" or "no_match",
    "approximations": [
        {{
            "index": 2,
            "confidence": 65,
            "approximated_rate": 400.00,
            "adjustment": "Candidate DN250@500.00: scaled by diameter ratio (200/250) = 400.00",
            "limitations": "Wall thickness, pressure class, and installation conditions may differ; treat as a starting reference only"
        }}
    ],
    "reasoning": "Explain which items can be used for approximation, how you calculated the approximated rate, and key risks, or why no approximation is possible"
}}

ADDITIONAL RULES FOR OUTPUT:
- "approximations" must be a JSON array with exactly ONE object when status="approximation", with keys: "index" (1-based integer), "confidence" (integer 50–69), "approximated_rate" (float), "adjustment" (string), and "limitations" (string).
- "approximated_rate" MUST be the final calculated target rate (e.g., 400.00), NOT the original candidate rate. It will be used directly with no further averaging.
- If there is no reasonable approximation, set "status" to "no_match" and "approximations" to [].
- Do NOT include any keys other than "status", "approximations", and "reasoning".
- Do NOT output example text outside the JSON.

EXAMPLES:
APPROXIMATION (65%): Target "Excavation depth 2m", Candidate "Excavation depth 2.5m @ 50.00/m³" → approximated_rate: 40.00 (scaled by depth ratio 2/2.5 = 0.8).
APPROXIMATION (60%): Target "HDPE DN200 PN10", Candidate "HDPE DN250 PN16 @ 500.00/m" → approximated_rate: 400.00 (scaled by diameter ratio 200/250 = 0.8).
APPROXIMATION (55%): Target "Cast in-situ concrete slab", Candidate "Cast in-situ concrete beam @ 150.00/m³" → approximated_rate: 150.00 (same m³ rate, but note geometry difference).
NO MATCH: "Concrete work" vs "Steel fabrication" (completely different work types and cost drivers).
NO MATCH: "Supply equipment" vs "Civil earthworks" (no reasonable relationship for scaling).

Be realistic and practical. This stage is allowed to make approximate, lower-confidence suggestions as long as you clearly explain adjustment logic and limitations, and you must return the approximated_rate to fill.
Return ONLY valid JSON."""



# System messages for each stage
MATCHER_SYSTEM_MESSAGE = (
    "You are an expert BOQ matcher specializing in identifying exact matches. "
    "You are strict about contradictions in specs, scope, and units, but practical about minor wording and harmless omissions. "
    "When multiple exact matches exist, you determine and return the most appropriate rate."
)

EXPERT_SYSTEM_MESSAGE = (
    "You are an expert BOQ analyst specializing in finding close matches with minor differences. "
    "You are professional and pragmatic: you avoid clearly wrong matches, but you do not reject reasonable, usable similarities. "
    "You calculate and return recommended rates considering confidence levels and differences."
)

ESTIMATOR_SYSTEM_MESSAGE = (
    "You are an expert cost estimator specializing in making reasonable approximations and calculating approximated rates. "
    "You apply logical scaling and adjustment to candidate rates, explaining calculations and limitations clearly."
)
