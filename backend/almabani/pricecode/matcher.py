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
                "score": score,
                "metadata": metadata
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
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
        unit: Optional[str] = None,
        item_code: Optional[str] = None,
        category_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ask LLM to identify the best match using strict structured prompts.
        """
        if not candidates:
            return {"matched": False, "reason": "No candidates"}

        # Build prompt using helper methods
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent, category_path)
        candidates_text = self._build_candidates_text(candidates)
        
        system_prompt = PRICECODE_MATCH_SYSTEM
        
        user_prompt = PRICECODE_MATCH_USER.format(
            target_info=target_info,
            candidates_text=candidates_text
        )

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1.0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Find the matched candidate to extract metadata using INDEX
            if result.get("matched") and result.get("match_index"):
                idx = result["match_index"]
                if isinstance(idx, int) and 1 <= idx <= len(candidates):
                    # Candidates are 1-based in prompt, 0-based in list
                    cand = candidates[idx - 1]
                    
                    # Merge metadata
                    result["price_code"] = cand.get("price_code")
                    result["price_description"] = cand.get("description")
                    result["score"] = cand.get("score")
                    
                    # Extract reference metadata if present
                    meta = cand.get("metadata", {}) or {}
                    result["source_file"] = meta.get("source_file")
                    result["reference_sheet"] = meta.get("reference_sheet")
                    result["reference_category"] = meta.get("reference_category")
                    result["reference_row"] = meta.get("reference_row")
                else:
                    # Invalid index
                    result["matched"] = False
                    result["reason"] = f"LLM returned invalid index: {idx}"
            
            return result
        
        except Exception as e:
            logger.error(f"LLM match error: {e}")
            return {
                "matched": False,
                "reason": f"LLM error: {str(e)}"
            }

    @staticmethod
    def _context_tail_from_path(category_path: str) -> str:
        """
        Return a context string starting from the third level of the path (drop the first two segments).
        If fewer than 3 segments exist, return the available tail.
        """
        if not category_path:
            return ""
        parts = [p.strip() for p in category_path.split('>') if p.strip()]
        if len(parts) > 2:
            parts = parts[2:]
        return ' > '.join(parts)

    def _build_target_info(
        self,
        description: str,
        unit: Optional[str],
        item_code: Optional[str],
        parent: Optional[str],
        grandparent: Optional[str],
        category_path: Optional[str] = None
    ) -> str:
        """
        Build target item information string for LLM prompts.
        Structure matches the unit rate pipeline logic.
        """
        parts = []
        
        # Build hierarchy string
        hierarchy_parts = []
        if grandparent:
            hierarchy_parts.append(str(grandparent))
        if parent:
            hierarchy_parts.append(str(parent))
        if hierarchy_parts:
            parts.append(f"Hierarchy: {' > '.join(hierarchy_parts)}")
        
        # Context tail from category path
        if category_path:
            context_tail = self._context_tail_from_path(category_path)
            if context_tail:
                parts.append(f"Context: {context_tail}")

        # Description (required)
        parts.append(f"Description: {description}")
        
        # Unit (required and emphasized - this is the TARGET UNIT that candidates must match)
        if unit:
            parts.append(f"TARGET UNIT: {unit}")
        else:
            parts.append("TARGET UNIT: (not specified)")
        
        # Item code (optional)
        if item_code:
            parts.append(f"Item Code: {item_code}")
        
        return '\n'.join(parts)
    
    def _build_candidates_text(self, candidates: List[Dict]) -> str:
        """
        Build candidates text for LLM prompts.
        Format: [Index] [Code] Description
        """
        lines = []
        for i, cand in enumerate(candidates, 1):
            code = cand.get('price_code', 'NO_CODE')
            desc = cand.get('description', '')
            lines.append(f"[{i}] [{code}] {desc}")
        return "\n".join(lines)

    
            
    async def match(
        self,
        description: str,
        namespace: str = "",
        filter_dict: Optional[Dict[str, Any]] = None,
        vector_store: Any = None,
        # New context fields
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
        unit: Optional[str] = None,
        item_code: Optional[str] = None,
        category_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Match a description to a price code.
        """
        # 1. Search candidates (using description + context)
        # Enrich query with hierarchy if available (Unit Rate logic)
        query_parts = []
        hierarchy_parts = []
        if grandparent:
            hierarchy_parts.append(str(grandparent))
        if parent:
            hierarchy_parts.append(str(parent))
        
        if hierarchy_parts:
            query_parts.append(f"Category: {' > '.join(hierarchy_parts)}")
        
        query_parts.append(description)
        
        # Add Unit to query for strict matching
        if unit:
            query_parts.append(f"Unit: {unit}")
        
        search_query = ". ".join(query_parts)

        candidates = await self.search_candidates(
            search_query, 
            namespace=namespace, 
            filter_dict=filter_dict,
            vector_store=vector_store
        )
        
        if not candidates:
            return {
                "matched": False,
                "reason": "No candidates found"
            }
        
        # 2. LLM Match with hierarchy context
        return await self.llm_match(
            description, 
            candidates, 
            parent=parent, 
            grandparent=grandparent, 
            unit=unit, 
            item_code=item_code, 
            category_path=category_path
        )
    
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
