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
        _openai_client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    return _openai_client


def get_pinecone_client():
    global _pinecone_client
    if _pinecone_client is None:
        from pinecone import Pinecone
        _pinecone_client = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
    return _pinecone_client


def cors_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Return response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
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


# =============================================================================
# VALIDATION PROMPT - Check if input is construction/BOQ related
# =============================================================================
VALIDATION_SYSTEM = """You are a construction industry expert. Your task is to determine if the user's query is related to construction items, materials, services, or works that would appear in a BOQ (Bill of Quantities).

Valid queries include:
- Construction materials (concrete, steel, pipes, cables, etc.)
- Construction works (excavation, formwork, reinforcement, plastering, etc.)
- MEP items (electrical, plumbing, HVAC equipment)
- Finishing works (painting, tiling, flooring, etc.)
- Civil works (roads, drainage, foundations, etc.)

Invalid queries include:
- General conversation or greetings
- Non-construction topics
- Vague queries without any construction context

Respond in JSON format:
{
    "valid": true/false,
    "reason": "Brief explanation if invalid",
    "refined_query": "Cleaned up query text for searching (if valid)"
}
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
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
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
# PRICE CODE MATCHING (Same logic as pipeline)
# =============================================================================
PRICECODE_MATCH_SYSTEM = (
    "You are a Price Code allocation expert. "
    "Your task is to identify the correct Price Code for a BOQ item from a list of candidates.\n"
    "Rules:\n"
    "1. MATCHING IS STRICT & CONSERVATIVE. Better to return 'matched': false than a wrong price code.\n"
    "2. UNIT COMPATIBILITY (Critical): The Candidate Unit must be convertible or identical to the Target Unit.\n"
    "3. NO ASSUMPTIONS: If Target is VAGUE and Candidate is SPECIFIC, REJECT IT.\n"
    "4. FULL COVERAGE: The Candidate must cover the entire scope of the Target.\n"
    "5. CONFIDENCE Levels:\n"
    "   - 'EXACT': Perfect symmetry in scope, material, and constraints.\n"
    "   - 'HIGH': Essential scope is identical with minor non-restrictive differences.\n"
    "6. Return strict JSON."
)

PRICECODE_MATCH_USER = """TARGET ITEM (from user query):
{target_info}

CANDIDATES (from database):
{candidates_text}

INSTRUCTIONS:
Perform logical elimination:
1. UNIT CHECK: Filter out candidates with incompatible units.
2. HIERARCHY CHECK: Filter out candidates from wrong trades.
3. SCOPE CHECK: Does Work Type and Material match?
4. SPECIFICITY CHECK: Does Candidate impose constraints not in Target? -> REJECT.

Select the best matching candidate.

OUTPUT JSON:
{{
    "matched": true/false,
    "match_index": 1,  // 1-based index (if matched)
    "confidence_level": "EXACT" | "HIGH",  // if matched
    "reason": "Step-by-step reasoning explaining the match or why no match was found"
}}
"""


def match_pricecode(user_query: str, candidates: List[Dict]) -> Dict[str, Any]:
    """Apply Price Code matching logic."""
    client = get_openai_client()
    
    # Format candidates
    candidates_text = ""
    for i, c in enumerate(candidates, 1):
        meta = c.metadata or {}
        candidates_text += f"{i}. Code: {meta.get('price_code', 'N/A')}\n"
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
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
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
    except Exception as e:
        logger.error(f"Price code matching error: {e}")
        return {"matched": False, "reason": f"Matching error: {str(e)}"}


# =============================================================================
# UNIT RATE MATCHING (Same 3-stage logic as pipeline)
# =============================================================================
UNITRATE_MATCH_SYSTEM = (
    "You are a BOQ matching specialist. Your task is to identify items that are effectively "
    "the SAME as the target and return the best match with its rate.\n"
    "Rules:\n"
    "1. SAME WORK TYPE: Must be the same activity/work/material.\n"
    "2. SAME SPECIFICATIONS: All critical specs must match (dimensions, materials, grades).\n"
    "3. SAME SCOPE: Supply & Install vs Supply only are DIFFERENT.\n"
    "4. COMPATIBLE UNITS: Units must be the same or clear synonyms.\n"
    "Return strict JSON."
)

UNITRATE_MATCH_USER = """TARGET ITEM (from user query):
{target_info}

CANDIDATES (from database with rates):
{candidates_text}

INSTRUCTIONS:
Find the best matching item. Consider:
1. Is it the same work type?
2. Are specifications compatible?
3. Is the scope the same?
4. Are units compatible?

If exact match found, return it. If only close/approximate matches, indicate that.

OUTPUT JSON:
{{
    "status": "exact_match" | "close_match" | "no_match",
    "match_index": 1,  // 1-based index of best match (if any match)
    "rate": 150.00,  // Rate from matched item
    "unit": "m3",  // Unit
    "confidence": 95,  // 70-100 for matches
    "reason": "Brief explanation of the match quality and any differences"
}}
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
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        # Add matched candidate details with full reference info
        if result.get("status") != "no_match" and result.get("match_index"):
            idx = result["match_index"] - 1
            if 0 <= idx < len(candidates):
                meta = candidates[idx].metadata or {}
                result["best_match"] = {
                    # Core info
                    "item_code": meta.get("item_code", ""),
                    "description": meta.get("description", meta.get("text", "N/A")),
                    "rate": meta.get("rate", "N/A"),
                    "unit": meta.get("unit", "N/A"),
                    # Reference info
                    "sheet_name": meta.get("sheet_name", meta.get("source_name", "")),
                    "row_number": meta.get("row_number", ""),
                    "category_path": meta.get("category_path", ""),
                    "parent": meta.get("parent", ""),
                    "grandparent": meta.get("grandparent", "")
                }
        
        return result
    except Exception as e:
        logger.error(f"Unit rate matching error: {e}")
        return {"status": "no_match", "reason": f"Matching error: {str(e)}"}


# =============================================================================
# MAIN HANDLER
# =============================================================================
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return cors_response(200, {"message": "OK"})
    
    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        
        chat_type = body.get("type", "").lower()
        message = body.get("message", "").strip()
        
        # Validate inputs
        if chat_type not in ["pricecode", "unitrate"]:
            return cors_response(400, {
                "status": "error",
                "message": "Invalid type. Must be 'pricecode' or 'unitrate'."
            })
        
        if not message:
            return cors_response(400, {
                "status": "error",
                "message": "Message is required."
            })
        
        # Stage 1: Validate query is construction-related
        validation = validate_construction_query(message)
        
        if not validation.get("valid", True):
            return cors_response(200, {
                "status": "clarification",
                "message": validation.get("reason", "Please enter a construction-related item or work description.")
            })
        
        search_query = validation.get("refined_query", message)
        
        # Stage 2: Search Pinecone for candidates
        candidates = search_pinecone(search_query, chat_type)
        
        if not candidates:
            return cors_response(200, {
                "status": "no_match",
                "message": "No matching items found in the database. Please try a different description."
            })
        
        # Stage 3: Apply matching logic (same as pipelines)
        if chat_type == "pricecode":
            match_result = match_pricecode(message, candidates)
            
            if match_result.get("matched") and match_result.get("best_match"):
                best = match_result["best_match"]
                confidence = match_result.get("confidence_level", "HIGH").lower()
                return cors_response(200, {
                    "status": "success",
                    "message": f"Found {confidence} match: **{best['code']}** - {best['description']}",
                    "match": {
                        "code": best["code"],
                        "description": best["description"],
                        "match_type": confidence
                    },
                    "reference": {
                        "source_file": best["source_file"],
                        "sheet_name": best["sheet_name"],
                        "category": best["category"],
                        "row_number": best["row_number"]
                    },
                    "reasoning": match_result.get("reason", "")
                })
            else:
                return cors_response(200, {
                    "status": "no_match",
                    "message": "Could not find a confident match for your query."
                })
        
        else:  # unitrate
            match_result = match_unitrate(message, candidates)
            
            if match_result.get("status") != "no_match" and match_result.get("best_match"):
                best = match_result["best_match"]
                match_type = "exact" if match_result["status"] == "exact_match" else "close"
                return cors_response(200, {
                    "status": "success",
                    "message": f"Found {match_type} match: {best['description']} @ {best['rate']}/{best['unit']}",
                    "match": {
                        "item_code": best["item_code"],
                        "description": best["description"],
                        "rate": best["rate"],
                        "unit": best["unit"],
                        "match_type": match_type
                    },
                    "reference": {
                        "sheet_name": best["sheet_name"],
                        "row_number": best["row_number"],
                        "category_path": best["category_path"],
                        "parent": best["parent"],
                        "grandparent": best["grandparent"]
                    },
                    "reasoning": match_result.get("reason", "")
                })
            else:
                return cors_response(200, {
                    "status": "no_match",
                    "message": "Could not find a confident match for your query."
                })
        
    except json.JSONDecodeError:
        return cors_response(400, {
            "status": "error",
            "message": "Invalid JSON in request body."
        })
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return cors_response(500, {
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        })
