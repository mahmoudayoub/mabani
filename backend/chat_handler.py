"""
Chat API Lambda Handler - Natural language interface for price codes and unit rates.

Endpoint: POST /chat
Supports queries for both 'pricecode' and 'unitrate' types.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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


def validate_query(message: str, chat_type: str, history: List[Dict]) -> Dict[str, Any]:
    """Validate and refine user query using OpenAI."""
    client = get_openai_client()
    
    type_context = {
        "pricecode": "price codes for construction items (e.g., concrete, steel, pipes)",
        "unitrate": "unit rates for construction work items (e.g., excavation, formwork, reinforcement)"
    }
    
    system_prompt = f"""You are a helpful assistant for querying {type_context.get(chat_type, 'construction data')}.

Your job is to:
1. Determine if the user query is clear enough to search for matches
2. If unclear, ask for clarification
3. If clear, extract the search query

Respond in JSON format:
- If valid: {{"valid": true, "query": "refined search query"}}
- If needs clarification: {{"valid": false, "reason": "Please specify..."}}

Examples of valid queries:
- "25mm copper pipe" -> {{"valid": true, "query": "25mm copper pipe plumbing"}}
- "concrete for foundations" -> {{"valid": true, "query": "foundation concrete structural"}}
- "steel" -> {{"valid": false, "reason": "Please be more specific. What type of steel? (e.g., reinforcement bars, structural steel, steel pipes)"}}
"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history
    for h in history[-4:]:  # Last 4 messages for context
        messages.append({"role": h["role"], "content": h["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {"valid": True, "query": message}  # Fallback to original query


def search_pinecone(query: str, chat_type: str, top_k: int = 5) -> List[Dict]:
    """Search Pinecone index for matches."""
    pc = get_pinecone_client()
    
    # Select index based on type
    if chat_type == "pricecode":
        index_name = os.environ.get('PRICECODE_INDEX_NAME', 'almabani-pricecode')
    else:  # unitrate
        index_name = os.environ.get('PINECONE_INDEX_NAME', 'almabani-1')
    
    index = pc.Index(index_name)
    
    # Create embedding for query
    embedding = create_embedding(query)
    
    # Query Pinecone
    results = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=""
    )
    
    return results.matches


def format_matches(matches: List, chat_type: str) -> List[Dict]:
    """Format Pinecone matches for response."""
    formatted = []
    for match in matches:
        metadata = match.metadata or {}
        
        if chat_type == "pricecode":
            formatted.append({
                "code": metadata.get("price_code", "N/A"),
                "description": metadata.get("description", metadata.get("text", "N/A")),
                "category": metadata.get("category", ""),
                "source": metadata.get("source_file", ""),
                "score": round(match.score, 3)
            })
        else:  # unitrate
            formatted.append({
                "code": metadata.get("item_code", "N/A"),
                "description": metadata.get("description", metadata.get("text", "N/A")),
                "unit": metadata.get("unit", ""),
                "rate": metadata.get("rate", ""),
                "source": metadata.get("sheet_name", ""),
                "score": round(match.score, 3)
            })
    
    return formatted


def generate_answer(message: str, matches: List[Dict], chat_type: str, history: List[Dict]) -> str:
    """Generate natural language answer using OpenAI."""
    client = get_openai_client()
    
    if not matches:
        return "I couldn't find any matching items. Please try a different search term or provide more details."
    
    # Build context from matches
    context_lines = []
    for i, m in enumerate(matches[:5], 1):
        if chat_type == "pricecode":
            context_lines.append(f"{i}. Code: {m['code']} - {m['description']} (Score: {m['score']})")
        else:
            rate_info = f" @ {m['rate']}/{m['unit']}" if m.get('rate') and m.get('unit') else ""
            context_lines.append(f"{i}. {m['code']} - {m['description']}{rate_info} (Score: {m['score']})")
    
    context = "\n".join(context_lines)
    
    system_prompt = f"""You are a helpful construction cost estimating assistant.
Based on the search results below, provide a helpful answer to the user's question.
Be concise but informative. If the top match seems very relevant (score > 0.8), recommend it confidently.
If scores are lower, mention that these are approximate matches.

Search Results:
{context}
"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # Add history
    for h in history[-4:]:
        messages.append({"role": h["role"], "content": h["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Answer generation error: {e}")
        # Fallback to simple response
        top = matches[0]
        return f"The best match I found is {top['code']}: {top['description']} (confidence: {top['score']*100:.0f}%)"


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
        history = body.get("history", [])
        
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
        
        # Stage 1: Validate query
        validation = validate_query(message, chat_type, history)
        
        if not validation.get("valid", True):
            return cors_response(200, {
                "status": "clarification",
                "message": validation.get("reason", "Please provide more details.")
            })
        
        search_query = validation.get("query", message)
        
        # Stage 2: Search Pinecone
        matches = search_pinecone(search_query, chat_type, top_k=5)
        formatted_matches = format_matches(matches, chat_type)
        
        # Stage 3: Generate answer
        answer = generate_answer(message, formatted_matches, chat_type, history)
        
        return cors_response(200, {
            "status": "success",
            "message": answer,
            "matches": formatted_matches
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
