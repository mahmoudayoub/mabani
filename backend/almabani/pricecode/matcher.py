"""
Price Code Matcher - One-shot matching of descriptions to price codes.

Uses native async Pinecone operations.
"""

import logging
import json
from typing import Dict, Any, Optional, List
import asyncio

from .prompts import PRICECODE_MATCH_SYSTEM, PRICECODE_MATCH_USER
from almabani.core.async_vector_store import get_async_vector_store

logger = logging.getLogger(__name__)


class PriceCodeMatcher:
    """
    Match BOQ item descriptions to price codes using vector search + LLM.
    
    Flow:
    1. Embed the input description
    2. Vector search with top_k=20 (native async)
    3. LLM one-shot decision: match or no match
    """
    
    def __init__(
        self,
        async_openai_client,
        embeddings_service,
        top_k: int = None,
        model: str = None
    ):
        # Load defaults from settings if not provided
        from almabani.config.settings import get_settings
        settings = get_settings()
        
        self.openai_client = async_openai_client
        self.embeddings_service = embeddings_service
        self.top_k = top_k if top_k is not None else settings.pricecode_top_k
        self.model = model if model is not None else settings.openai_chat_model
    
    async def search_candidates(
        self,
        description: str,
        namespace: str = "",
        filter_dict: Optional[Dict[str, Any]] = None,
        vector_store: Any = None
    ) -> List[Dict[str, Any]]:
        """
        Search for candidate price codes using native async vector similarity.
        
        Args:
            filter_dict: Optional Pinecone filter
            vector_store: Optional shared AsyncVectorStore instance
        
        Returns list of candidates with price_code, description, score
        """
        # Embed the description
        embeddings = await self.embeddings_service.generate_embeddings_batch([description])
        query_embedding = embeddings[0]
        
        # Search Pinecone (reuse shared connection or create new one)
        if vector_store:
            matches = await vector_store.query(
                vector=query_embedding,
                top_k=self.top_k,
                namespace=namespace,
                include_metadata=True,
                filter_dict=filter_dict
            )
        else:
            async with get_async_vector_store() as vs:
                matches = await vs.query(
                    vector=query_embedding,
                    top_k=self.top_k,
                    namespace=namespace,
                    include_metadata=True,
                    filter_dict=filter_dict
                )
        
        candidates = []
        for match in matches:
            metadata = match.get('metadata', {})
            score = match.get('score', 0)
            
            candidates.append({
                "price_code": metadata.get("price_code", ""),
                "description": metadata.get("description", ""),
                "category": metadata.get("category", ""),
                "score": score
            })
        
        return candidates
    
    def format_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        """Format candidates for LLM prompt"""
        lines = []
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i}. [{c['price_code']}] {c['description']} (similarity: {c['score']:.3f})")
        return "\n".join(lines)
    
    async def llm_match(
        self,
        description: str,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Use LLM to determine if any candidate matches the description.
        
        Returns:
        {
            "matched": bool,
            "price_code": str or None,
            "price_description": str or None,
            "confidence": float,
            "reason": str
        }
        """
        if not candidates:
            return {
                "matched": False,
                "price_code": None,
                "price_description": None,
                "confidence": 0.0,
                "reason": "No candidates found in vector search"
            }
        
        candidates_text = self.format_candidates(candidates)
        
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PRICECODE_MATCH_SYSTEM},
                    {"role": "user", "content": PRICECODE_MATCH_USER.format(
                        description=description,
                        candidates=candidates_text
                    )}
                ],
                temperature=1.0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            # Find the matched candidate to extract metadata
            matched_candidate = None
            if result.get("matched") and result.get("price_code"):
                code = result["price_code"]
                # Look for exact match first
                for cand in candidates:
                    if cand["metadata"].get("price_code") == code:
                        matched_candidate = cand
                        break
            
            # Extract reference metadata
            ref_sheet = None
            ref_category = None
            ref_row = None
            
            if matched_candidate:
                meta = matched_candidate["metadata"]
                ref_sheet = meta.get("reference_sheet") or meta.get("category")
                ref_category = meta.get("reference_category") or meta.get("category")
                ref_row = meta.get("reference_row")

            return {
                "matched": result.get("matched", False),
                "price_code": result.get("price_code"),
                "price_description": result.get("price_description"),
                "confidence": result.get("confidence", 0.0),
                "reason": result.get("reason", ""),
                # Add reference metadata
                "reference_sheet": ref_sheet,
                "reference_category": ref_category,
                "reference_row": ref_row
            }
            
        except Exception as e:
            logger.error(f"LLM matching error: {e}")
            return {
                "matched": False,
                "price_code": None,
                "price_description": None,
                "confidence": 0.0,
                "reason": f"LLM error: {str(e)}"
            }
    
    async def match(
        self,
        description: str,
        namespace: str = "",
        filter_dict: Optional[Dict[str, Any]] = None,
        vector_store: Any = None
    ) -> Dict[str, Any]:
        """
        Match a description to a price code.
        
        Args:
            filter_dict: Optional filter, e.g., {"source_file": {"$in": ["AI Codes - Civil"]}}
            vector_store: Optional shared AsyncVectorStore instance
        
        Full flow:
        1. Vector search for candidates (native async)
        2. LLM decision
        
        Returns:
        {
            "matched": bool,
            "price_code": str or None,
            "price_description": str or None,
            "confidence": float,
            "reason": str,
            "candidates_count": int
        }
        """
        logger.debug(f"Matching: {description[:100]}...")
        
        # Get candidates
        candidates = await self.search_candidates(
            description, 
            namespace, 
            filter_dict,
            vector_store=vector_store
        )
        
        # LLM match
        result = await self.llm_match(description, candidates)
        result["candidates_count"] = len(candidates)
        
        if result["matched"]:
            logger.info(f"Matched: {result['price_code']} (confidence: {result['confidence']:.2f})")
        else:
            logger.debug(f"No match found: {result['reason']}")
        
        return result
    
    async def match_batch(
        self,
        descriptions: List[str],
        namespace: str = "",
        filter_dict: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Match multiple descriptions concurrently.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def match_one(desc):
            async with semaphore:
                return await self.match(desc, namespace, filter_dict)
        
        tasks = [match_one(desc) for desc in descriptions]
        results = await asyncio.gather(*tasks)
        
        return results
