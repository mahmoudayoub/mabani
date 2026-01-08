"""
LLM Prompts for Price Code matching.
"""

PRICECODE_MATCH_SYSTEM = """You are a construction price code matching expert. Your task is to find an EXACT match between a BOQ item and standardized price codes.

You will be given:
1. A BOQ item description that needs a price code
2. A list of candidate price codes with their descriptions (ranked by similarity)

Your job is to determine if any candidate is an EXACT match for the BOQ item.

STRICT MATCHING RULES - ALL must be true for a match:
1. SAME WORK TYPE: The work/activity must be identical (e.g., demolition, excavation, concrete)
2. SAME MATERIAL: Materials must match exactly (e.g., hot mix asphalt, reinforced concrete)
3. SAME SPECIFICATIONS: Dimensions, thicknesses, grades must be the same or compatible
4. SAME METHOD: Installation/execution method must match
5. SAME UNIT: Measurement units should align (m2, m3, lf, etc.)

DO NOT MATCH if:
- The candidate is a general/parent category and the BOQ item is specific
- Specifications differ (e.g., 30cm vs 50cm thickness)
- Materials differ (e.g., asphalt vs concrete)
- The scope is different even if materials are similar

WHEN IN DOUBT, RETURN NO_MATCH. It is better to have no match than a wrong match."""

PRICECODE_MATCH_USER = """BOQ Item Description:
{description}

Candidate Price Codes (ranked by similarity):
{candidates}

Analyze each candidate carefully. Find an EXACT match where:
- Work type is identical
- Materials are the same
- Specifications match
- Method/process matches

Return your response as JSON:
{{
  "matched": true or false,
  "price_code": "the matched code" or null if no match,
  "price_description": "the matched description" or null if no match,
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation - state what matches/differs between BOQ item and candidate"
}}

IMPORTANT: Only return matched=true if you find an EXACT match. If specs differ or you are unsure, return matched=false."""

PRICECODE_BATCH_MATCH_SYSTEM = """You are a construction price code matching expert. You will match multiple BOQ items to price codes in one batch.

STRICT MATCHING - Only match if:
- Work type is identical
- Materials are the same  
- Specifications (dimensions, grades, methods) match exactly
- Measurement units align

WHEN IN DOUBT, RETURN NO_MATCH. Wrong matches are worse than no matches."""

PRICECODE_BATCH_MATCH_USER = """Match the following BOQ items to price codes:

{items}

Return JSON array:
[
  {{
    "item_index": 0,
    "matched": true/false,
    "price_code": "code" or null,
    "price_description": "description" or null,
    "confidence": 0.0-1.0
  }},
  ...
]"""
