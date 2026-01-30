"""
Chat API Lambda Handler - Natural language interface for price codes and unit rates.

Uses the same matching logic as the batch processing pipelines:
- Price Code: Strict matching with unit/specificity checks
- Unit Rate: 3-stage matching (Matcher → Expert → Estimator)

Endpoint: POST /chat
"""

import os
import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get model from environment (same as pipelines)
OPENAI_CHAT_MODEL = os.environ.get('OPENAI_CHAT_MODEL', 'gpt-4o-mini')

# Initialize clients lazily
_openai_client = None
_pinecone_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        # Set timeout to 55 seconds (Lambda is 60s, leave 5s buffer)
        _openai_client = OpenAI(
            api_key=os.environ['OPENAI_API_KEY'],
            timeout=55.0  # seconds
        )
    return _openai_client


def get_pinecone_client():
    global _pinecone_client
    if _pinecone_client is None:
        from pinecone import Pinecone
        _pinecone_client = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
    return _pinecone_client


def cors_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return response WITHOUT explicit CORS headers (handled by Function URL).
    We kept the function name to minimize code changes.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body)
    }


def create_embedding(text: str) -> List[float]:
    """Create embedding using OpenAI."""
    client = get_openai_client()
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def parse_llm_json(response_text: str) -> Dict[str, Any]:
    """Strip markdown and parse JSON from LLM response with multiple fallback strategies."""
    logger.info(f"[DEBUG] Raw LLM response (first 500 chars): {repr(response_text[:500])}")
    
    # Strategy 1: Try parsing as-is (already clean JSON)
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass  # Try other strategies
    
    # Strategy 2: Strip markdown code fences
    cleaned = response_text.strip()
    # Remove ```json or ``` at the start
    cleaned = re.sub(r'^```(?:json)?[\s\n]*', '', cleaned, flags=re.IGNORECASE)
    # Remove ``` at the end
    cleaned = re.sub(r'[\s\n]*```$', '', cleaned)
    cleaned = cleaned.strip()
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass  # Try other strategies
    
    # Strategy 3: Find JSON object in the text (between first { and last })
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Strategy 4: Find JSON array in the text (between first [ and last ])
    match = re.search(r'\[.*\]', response_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return {"matches": json.loads(json_str)}
        except json.JSONDecodeError:
            pass
    
    # All strategies failed
    logger.error(f"FAILED TO PARSE JSON after all strategies")
    logger.error(f"Original text: {response_text}")
    logger.error(f"Cleaned text: {cleaned}")
    return {"status": "error", "message": "Failed to parse AI response", "matches": [], "matched": False}

# =============================================================================
# VALIDATION PROMPT - Check if input is construction/BOQ related
# =============================================================================
VALIDATION_SYSTEM = """You are a construction industry expert / BOQ Assistant. Your task is to determine if the user's query is related to construction items, materials, services, or works.

1. GREETINGS ("hello", "hi", "good morning"):
   - Set "valid": false
   - Set "reason": "Hello! I am your Almabani BOQ Assistant. Please enter a construction item or work description you would like to find."

2. VALID CONSTRUCTION QUERIES:
   - Materials (concrete, steel, pipes)
   - Works (excavation, tiling, painting)
   - MEP items, Civil works, etc.
   - Set "valid": true

3. INVALID / OFF-TOPIC:
   - General questions like "how are you", "what is the weather"
   - Vague inputs without context
   - Set "valid": false
   - Set "reason": "I can only help with construction and BOQ items. Please ask about a price code or unit rate."

Respond in JSON format:
{
    "valid": true/false,
    "reason": "Message to show the user if invalid",
    "refined_query": "Cleaned up query text for searching (if valid)"
}

CRITICAL: Return ONLY raw JSON. Do NOT use markdown code blocks or triple backticks.
"""


def validate_construction_query(message: str) -> Dict[str, Any]:
    """Validate that the query is construction/BOQ related."""
    client = get_openai_client()
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": VALIDATION_SYSTEM},
                {"role": "user", "content": message}
            ],

            response_format={"type": "json_object"}
        )
        result = parse_llm_json(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {"valid": True, "refined_query": message}


def search_pinecone(query: str, chat_type: str, top_k: int = None) -> List[Dict]:
    """Search Pinecone index for candidates."""
    pc = get_pinecone_client()
    
    # Set top_k based on type (price code needs more candidates)
    if top_k is None:
        top_k = 150 if chat_type == "pricecode" else 10
    
    # Select index based on type
    if chat_type == "pricecode":
        index_name = os.environ.get('PRICECODE_INDEX_NAME', 'almabani-pricecode')
    else:  # unitrate
        index_name = os.environ.get('PINECONE_INDEX_NAME', 'almabani-1')
    
    index = pc.Index(index_name)
    embedding = create_embedding(query)
    
    results = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=""
    )
    
    return results.matches


# =============================================================================
# PRICE CODE MATCHING (Aligned with pipeline logic)
# =============================================================================
PRICECODE_MATCH_SYSTEM = (
    "You are a Price Code allocation expert. "
    "Your task is to identify the correct Price Code for a BOQ item from a list of candidates.\n"
    "Rules:\n"
    "1. MATCHING IS STRICT & CONSERVATIVE. Better to return 'matched': false than a wrong price code.\n"
    "2. UNIT COMPATIBILITY (Critical): The Candidate Unit must be convertible or identical to the Target Unit. (e.g. m2 cannot match m3).\n"
    "3. NO ASSUMPTIONS (Specificity Check): \n"
    "   - If Target is VAGUE (e.g. 'Excavation') and Candidate is SPECIFIC (e.g. 'Excavation depth > 2m'), REJECT IT.\n"
    "   - You cannot assume the Target implies the specific constraints of the Candidate.\n"
    "4. FULL COVERAGE:\n"
    "   - The Candidate must cover the *entire scope* of the Target.\n"
    "   - The Target must not contain requirements missing from the Candidate.\n"
    "5. CONFIDENCE Levels:\n"
    "   - 'EXACT' (Green): PERFECT SYMMETRY. Target and Candidate describe exactly the same scope, material, and constraints. No extra info on either side.\n"
    "   - 'HIGH' (Yellow): SAFE MATCH. Essential scope is identical, but one side contains minor non-restrictive info (e.g. brand name, trivial spec detail) that does not alter the cost basis significantly.\n"
    "6. Return strict JSON. Do NOT use markdown code blocks."
)

PRICECODE_MATCH_USER = """TARGET ITEM:
{target_info}

CANDIDATES:
{candidates_text}

INSTRUCTIONS:
Perform a logical elimination process:
1. UNIT CHECK: Filter out candidates with incompatible units.
2. HIERARCHY CHECK: Filter out candidates from wrong trades (e.g. Electrical vs Civil).
3. SCOPE CHECK: 
   - Does the Work Type match? (Excavation != Disposal)
   - Does the Material match? (C25/30 != C40/50)
4. SPECIFICITY CHECK (The "No Assumptions" Rule):
   - Does the Candidate impose a constraint (depth, width, type) NOT mentioned in the Target? -> REJECT.
   - Does the Target require a spec NOT in the Candidate? -> REJECT.

Select the best surviving candidate index (1-based).

OUTPUT JSON (raw JSON only, NO markdown):
{{
    "matched": true,
    "match_index": 1,
    "confidence_level": "EXACT",
    "reason": "Step-by-step reasoning: 1. Unit Check... 2. Scope... 3. Specificity..."
}}

If no candidate survives all checks, return: {{"matched": false, "reason": "..."}}
"""



def match_pricecode(user_query: str, candidates: List[Dict]) -> Dict[str, Any]:
    """Apply Price Code matching logic."""
    client = get_openai_client()
    
    # Format candidates
    candidates_text = ""
    for i, c in enumerate(candidates, 1):
        meta = c.metadata or {}
        score = c.get("score", 0)
        candidates_text += f"{i}. Code: {meta.get('price_code', 'N/A')} (Similarity: {score:.2f})\n"
        candidates_text += f"   Description: {meta.get('description', meta.get('text', 'N/A'))}\n"
        candidates_text += f"   Category: {meta.get('category', 'N/A')}\n"
        candidates_text += f"   Source: {meta.get('source_file', 'N/A')}\n\n"
    
    prompt = PRICECODE_MATCH_USER.format(
        target_info=user_query,
        candidates_text=candidates_text
    )
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": PRICECODE_MATCH_SYSTEM},
                {"role": "user", "content": prompt}
            ],

            response_format={"type": "json_object"}
        )
        result = parse_llm_json(response.choices[0].message.content)
        
        # Add matched candidate details with full reference info
        if result.get("matched") and result.get("match_index"):
            idx = result["match_index"] - 1
            if 0 <= idx < len(candidates):
                meta = candidates[idx].metadata or {}
                result["best_match"] = {
                    # Core info
                    "code": meta.get("price_code", "N/A"),
                    "description": meta.get("description", meta.get("text", "N/A")),
                    # Reference info
                    "sheet_name": meta.get("reference_sheet", meta.get("category", "")),
                    "source_file": meta.get("source_file", ""),
                    "row_number": meta.get("reference_row", ""),
                    "category": meta.get("category", meta.get("reference_category", ""))
                }
        
        return result
        return result
    except Exception as e:
        logger.error(f"Price code matching error: {e}")
        return {"matched": False, "reason": f"Matching error: {str(e)}"}
    finally:
        # Fallback: If no match, provide top 3 candidates as potential options
        if locals().get('result') and not result.get('matched') and candidates:
            potential = []
            for i in range(min(3, len(candidates))):
                c = candidates[i]
                meta = c.get('metadata', {})
                potential.append({
                    "code": meta.get("price_code", "N/A"),
                    "description": meta.get("description", meta.get("text", "N/A")),
                    "match_type": "potential",
                    "reasoning": "Potential match based on vector similarity.",
                    "reference": {
                        "source_file": meta.get("source_file", ""),
                        "sheet_name": meta.get("sheet_name", meta.get("reference_sheet", "")),
                        "category": meta.get("category", ""),
                        "row_number": meta.get("row_number", meta.get("reference_row", ""))
                    },
                    "score": c.get("score", 0)
                })
            if locals().get('result'):
                result["potential_matches"] = potential

# =============================================================================
# =============================================================================
UNITRATE_MATCH_SYSTEM = """You are an expert BOQ matching specialist. Your task is to find the BEST matching candidates for the target item.

You use a 3-STAGE approach - evaluate in order and return matches from the FIRST successful stage:

STAGE 1 - EXACT MATCH (confidence: 100%):
- CRITERIA:
  1. SAME WORK TYPE: Must be the same activity/material/purpose. Different wording allowed if meaning is identical.
  2. SAME SPECS: Critical specs (size, material, rating, pressure) must be identical (e.g., DN200=DN200, PN16=PN16).
  3. SAME SCOPE: "Supply & Install" = "Supply & Install". Scope conflicts (Supply only vs S&I) are NOT exact.
  4. UNIT COMPATIBILITY: Unit must be effectively identical (m3=cum, nr=each).
- GOAL: Identify items a QS would use with the SAME rate without adjustment.

STAGE 2 - CLOSE MATCH (confidence: 70-95%):
- CRITERIA:
  1. SAME CORE WORK: Same broad type/function (e.g. both HDPE pipes), but with minor differences.
  2. SIMILAR SPECS: Controlled differences allowed (e.g. DN200 vs DN250, C30 vs C40) if usage is similar.
  3. COST ADJUSTMENT: You must be able to justify why it's usable with a rate adjustment.
  4. UNIT COMPATIBILITY: Must use the same unit basis.
- GOAL: Identify items that are VERY SIMILAR and could be used with small adjustments.

STAGE 3 - APPROXIMATION (confidence: 50-69%):
- CRITERIA:
  1. RELATED WORK: Same general category (e.g. excavation vs excavation, concrete vs concrete).
  2. SCALING LOGIC: Rate can be derived by scaling (e.g. diameter ratio, depth ratio, percentage uplift).
  3. JUSTIFICATION: Must explain the calculation (e.g. "Scaled by size ratio 200/250").
- GOAL: Calculate an approximated_rate from valid reference items.

IMPORTANT RULES:
- Units MUST match (or be synonyms). Do not convert measurement bases (m vs m2).
- "Supply & Install" vs "Supply only" = DIFFERENT scope.
- Be practical: if a QS would reasonably use the item, include it.
- Return strict JSON only, no markdown code blocks.
"""

UNITRATE_MATCH_USER = """TARGET ITEM:
{target_info}

CANDIDATES (with rates):
{candidates_text}

Find ALL usable matches. Be practical - include items a QS would reasonably consider.

For each match, specify:
- match_index: 1-based candidate index
- stage: "matcher" (exact) | "expert" (close) | "estimator" (approx)
- status: "exact_match" | "close_match" | "approximation"  
- rate: the rate to use (from candidate, or calculated for approximation)
- unit: the unit
- confidence: 100 for exact, 70-95 for close, 50-69 for approx
- reason: brief explanation

OUTPUT JSON (raw JSON, NO markdown):
{{
    "matches": [
        {{
            "match_index": 1,
            "stage": "matcher",
            "status": "exact_match",
            "rate": 450.00,
            "unit": "m3",
            "confidence": 100,
            "reason": "Same HDPE DN200 PN16, identical specs and scope"
        }}
    ],
    "best_match_index": 1,
    "summary_reason": "Found exact match with identical specifications"
}}

If NO usable match exists at any stage, return empty matches array.
"""



def match_unitrate(user_query: str, candidates: List[Dict]) -> Dict[str, Any]:
    """Apply Unit Rate matching logic."""
    client = get_openai_client()
    
    # Format candidates
    candidates_text = ""
    for i, c in enumerate(candidates, 1):
        meta = c.metadata or {}
        rate = meta.get('rate', 'N/A')
        unit = meta.get('unit', 'N/A')
        candidates_text += f"{i}. Description: {meta.get('description', meta.get('text', 'N/A'))}\n"
        candidates_text += f"   Rate: {rate} / {unit}\n"
        candidates_text += f"   Sheet: {meta.get('sheet_name', meta.get('source_name', 'N/A'))}\n\n"
    
    prompt = UNITRATE_MATCH_USER.format(
        target_info=user_query,
        candidates_text=candidates_text
    )
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": UNITRATE_MATCH_SYSTEM},
                {"role": "user", "content": prompt}
            ],

            response_format={"type": "json_object"}
        )
        result = parse_llm_json(response.choices[0].message.content)
        
        # DEBUG: Log what LLM returned
        logger.info(f"[UNITRATE DEBUG] LLM result: {json.dumps(result, default=str)[:1000]}")
        logger.info(f"[UNITRATE DEBUG] Number of candidates provided: {len(candidates)}")
        
        # Parse matches
        parsed_matches = []
        raw_matches = result.get("matches", [])
        
        logger.info(f"[UNITRATE DEBUG] Raw matches count: {len(raw_matches)}")
        
        # If the LLM returns the old format (single object), handle it
        if not raw_matches and result.get("match_index"):
            raw_matches = [result]
        
        # Map status to match_type for display
        status_to_type = {
            "exact_match": "exact",
            "close_match": "close", 
            "approximation": "approximation"
        }
        
        for m in raw_matches:
            idx = m.get("match_index")
            if idx and 0 <= (idx - 1) < len(candidates):
                cand = candidates[idx - 1]
                meta = cand.metadata or {}
                status = m.get("status", "")
                match_type = status_to_type.get(status, "close")
                
                parsed_matches.append({
                    "data": {
                        "item_code": meta.get("item_code", ""),
                        "description": meta.get("description", meta.get("text", "N/A")),
                        "rate": m.get("rate") or meta.get("rate", "N/A"),  # Use LLM rate if approximated
                        "unit": m.get("unit") or meta.get("unit", "N/A"),
                        "match_type": match_type,
                        "stage": m.get("stage", "matcher"),
                        "confidence": m.get("confidence", 100 if match_type == "exact" else 80)
                    },
                    "reference": {
                        "sheet_name": meta.get("sheet_name", meta.get("source_name", "")),
                        "row_number": meta.get("row_number", ""),
                        "category_path": meta.get("category_path", ""),
                        "parent": meta.get("parent", ""),
                        "grandparent": meta.get("grandparent", "")
                    },
                    "reason": m.get("reason", "")
                })

        # Sort by stage priority: exact (matcher) > close (expert) > approximation (estimator)
        stage_priority = {"matcher": 0, "expert": 1, "estimator": 2}
        parsed_matches.sort(key=lambda x: (stage_priority.get(x["data"]["stage"], 3), -x["data"]["confidence"]))
        
        # Policy: Return matches from the best stage found
        # - If exact matches exist, return up to 5
        # - If only close matches, return up to 3
        # - If only approximations, return up to 2
        exact_matches = [m for m in parsed_matches if m["data"]["match_type"] == "exact"]
        close_matches = [m for m in parsed_matches if m["data"]["match_type"] == "close"]
        approx_matches = [m for m in parsed_matches if m["data"]["match_type"] == "approximation"]
        
        final_matches = []
        if exact_matches:
            final_matches = exact_matches[:5]
        elif close_matches:
            final_matches = close_matches[:3]
        elif approx_matches:
            final_matches = approx_matches[:2]

        return {
            "matches": final_matches,
            "count": len(final_matches),
            "summary_reason": result.get("summary_reason", "")
        }

    except Exception as e:
        logger.error(f"Unit rate matching error: {e}")
        return {"matches": [], "error": str(e)}


import traceback

# =============================================================================
# MAIN HANDLER
# =============================================================================
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler."""
    # 1. Define Standard Headers (No CORS - handled by Function URL)
    headers = {
        "Content-Type": "application/json"
    }

    try:
        # 2. Handle OPTIONS (Pre-flight) - OPTIONAL now as AWS handles it, 
        # but kept empty just in case request reaches here.
        if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
            return { "statusCode": 200, "headers": headers, "body": "" }
            
        logger.info(f"Received event: {json.dumps(event)}")
        
        # 3. Parse Body Safely
        body_str = event.get("body", "{}")
        if not body_str:
            body_str = "{}"
        
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({"status": "error", "message": "Invalid JSON body"})
            }
            
        # 4. HANDLE WARMUP (Critical Fix)
        if body.get("warmup") is True or body.get("message") == "__warmup__":
            logger.info("Warmup request received.")
            
            # Trigger lazy imports/loading
            try:
                get_openai_client()
                get_pinecone_client()
                logger.info("Libraries warmed up.")
            except Exception as e:
                logger.warning(f"Warmup library load warning: {e}")
                
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({"status": "success", "message": "Warmed up"})
            }

        # 5. Extract Inputs Safely (Use .get to avoid crashes)
        chat_type = body.get("type", "pricecode").lower()
        message = body.get("message", "").strip()
        history = body.get("history", [])  # <--- Fixes missing history crash!
        
        # Validate inputs
        if chat_type not in ["pricecode", "unitrate"]:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "status": "error",
                    "message": "Invalid type. Must be 'pricecode' or 'unitrate'."
                })
            }
        
        if not message:
             return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "status": "error",
                    "message": "Message is required."
                })
            }
        
        # Stage 1: Validate query is construction-related
        validation = validate_construction_query(message)
        
        if not validation.get("valid", True):
             return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "status": "clarification",
                    "message": validation.get("reason", "Please enter a construction-related item or work description.")
                })
            }
        
        search_query = validation.get("refined_query", message)
        
        # Stage 2: Search Pinecone for candidates
        candidates = search_pinecone(search_query, chat_type)
        
        if not candidates:
             return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "status": "no_match",
                    "message": "No matching items found in the database. Please try a different description."
                })
            }
        
        # Stage 3: Apply matching logic (same as pipelines)
        if chat_type == "pricecode":
            match_result = match_pricecode(message, candidates)
            
            if match_result.get("matched") and match_result.get("best_match"):
                best = match_result["best_match"]
                confidence = match_result.get("confidence_level", "HIGH").lower()
                 
                return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "status": "success",
                        "message": f"Found {confidence} match: **{best['code']}** - {best['description']}",
                        "matches": [{
                            "code": best["code"],
                            "description": best["description"],
                            "match_type": confidence,
                            "reasoning": match_result.get("reason", ""),
                            "reference": {
                                "source_file": best["source_file"],
                                "sheet_name": best["sheet_name"],
                                "category": best["category"],
                                "row_number": best["row_number"]
                            }
                        }]
                    })
                }
            elif match_result.get("potential_matches"):
                best = match_result["potential_matches"][0]
                return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "status": "success",
                        "message": f"No confident match, but found potential option: **{best['code']}**",
                        "matches": [{
                            "code": best["code"],
                            "description": best["description"],
                            "match_type": "potential",
                            "reasoning": match_result.get("reason", "Using best available candidate (Low Confidence)."),
                            "reference": best.get("reference", {})
                        }]
                    })
                }
            
            else:
                 return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "status": "no_match",
                        "message": "Could not find a confident match for your query."
                    })
                }
        
        else:  # unitrate
            match_result = match_unitrate(message, candidates)
            matches = match_result.get("matches", [])
            
            if matches:
                # Use the first match as "primary" for backward compat / simple display
                best = matches[0]
                count = len(matches)
                match_type = best["data"]["match_type"]
                
                msg = f"Found {count} {match_type} match{'es' if count > 1 else ''}."
                if match_type == "exact":
                    msg += f" Top match: {best['data']['description']} @ {best['data']['rate']}"
                else:
                    msg += " Displaying best available options."

                # Construct response
                # Flatten matches for API: combine data + match_type + reference + reason
                api_matches = []
                for m in matches:
                    item = m["data"].copy()
                    item["reference"] = m["reference"]
                    item["reasoning"] = m["reason"]
                    api_matches.append(item)

                return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "status": "success",
                        "message": msg,
                        "matches": api_matches,
                        # Backward compat: populate 'match' with the first one
                        "match": api_matches[0], 
                        "reference": api_matches[0]["reference"],
                        "reasoning": api_matches[0]["reasoning"]
                    })
                }
            else:
                 return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "status": "no_match",
                        "message": "Could not find a confident match for your query."
                    })
                }
        
    except Exception as e:
        # 7. GLOBAL ERROR CATCHER (Prevents 502)
        logger.error(f"CRITICAL ERROR: {str(e)}")
        traceback.print_exc() # Log full stack trace to CloudWatch
        
        return {
            "statusCode": 500, # Return 500 but WITH HEADERS
            "headers": headers,
            "body": json.dumps({
                "status": "error",
                "message": f"Server Error: {str(e)}"
            })
        }
