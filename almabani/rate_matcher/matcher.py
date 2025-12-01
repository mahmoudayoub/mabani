"""
Rate Matcher - LLM-powered 3-stage matching system.
Stages: 1) Matcher (exact), 2) Expert (close), 3) Estimator (approximation)
"""
import asyncio
import logging
import json
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from almabani.config.settings import get_settings
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.core.rate_limits import async_chat_rate_limiter
from almabani.rate_matcher.prompts import (
    build_matcher_prompt,
    build_expert_prompt,
    build_estimator_prompt,
    MATCHER_SYSTEM_MESSAGE,
    EXPERT_SYSTEM_MESSAGE,
    ESTIMATOR_SYSTEM_MESSAGE
)

logger = logging.getLogger(__name__)


class RateMatcher:
    """Match BOQ items and fill missing rates using vector search + 3-stage LLM."""
    
    def __init__(
        self,
        embeddings_service: EmbeddingsService,
        vector_store_service: VectorStoreService,
        async_openai_client: Optional[AsyncOpenAI] = None,
        similarity_threshold: float = 0.5,
        top_k: int = 6,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        verbose_logging: bool = True,
        async_rate_limiter=async_chat_rate_limiter
    ):
        """
        Initialize rate matcher.
        
        Args:
            embeddings_service: Service for generating embeddings
            vector_store_service: Service for vector store operations
            similarity_threshold: Minimum similarity score
            top_k: Number of candidates to retrieve
            model: OpenAI model for LLM calls (defaults to settings.openai_chat_model)
            temperature: LLM temperature (defaults to settings.openai_temperature)
            verbose_logging: Enable detailed logging
        """
        settings = get_settings()
        self.async_client = async_openai_client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries
        )
        self.embeddings = embeddings_service
        self.vector_store = vector_store_service
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.model = model if model is not None else settings.openai_chat_model
        self.temperature = temperature if temperature is not None else settings.openai_temperature
        self.verbose_logging = verbose_logging
        self.async_rate_limiter = async_rate_limiter
        
        logger.info(f"Rate matcher initialized with 3-stage approach")
        logger.info(f"  - Similarity threshold: {similarity_threshold}")
        logger.info(f"  - Top-K candidates: {top_k}")
        logger.info(f"  - Model: {self.model}")
        logger.info(f"  - Temperature: {self.temperature}")
    
    async def find_match(
        self,
        item_description: str,
        item_unit: str = '',
        item_code: str = '',
        parent: Optional[str] = None,
        grandparent: Optional[str] = None,
        namespace: str = ''
    ) -> Dict[str, Any]:
        """
        Find matching items for a given description with hierarchical context.
        
        Process:
        1. Build enriched query text (matching vector store format)
        2. Search vector store for top-K similar items (score > threshold)
        3. Pass candidates through 3-stage LLM validation
        4. Return matched items with rates
        
        Args:
            item_description: Item description to match
            item_unit: Unit of the target item
            item_code: Optional item code
            parent: Parent description (immediate level above)
            grandparent: Grandparent description (two levels above)
            namespace: Pinecone namespace
            
        Returns:
            Dictionary with match results
        """
        logger.info(f"Finding match for: {item_description[:60]}...")
        if self.verbose_logging:
            if parent:
                logger.info(f"  Parent: {parent[:60]}...")
            if item_unit:
                logger.info(f"  Unit: {item_unit}")
        
        # Step 1: Vector search with enriched context (async)
        candidates = await self._search_similar_items_async(
            item_description, parent, grandparent, namespace
        )
        
        if not candidates:
            logger.info("  No candidates found above threshold")
            return {
                'status': 'no_match',
                'match_type': 'none',
                'matches': [],
                'unit': None,
                'rate': None,
                'reasoning': 'No candidates found above similarity threshold',
                'candidates': []
            }
        
        logger.info(f"  Found {len(candidates)} candidates")
        
        # Step 2: 3-Stage LLM Validation - RUN ALL IN PARALLEL for speed
        logger.info("  Running 3-stage LLM validation in parallel...")
        
        # Run all 3 stages concurrently
        matcher_task = self._call_matcher_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent
        )
        expert_task = self._call_expert_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent
        )
        estimator_task = self._call_estimator_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent
        )
        
        # Wait for all to complete
        matcher_result, expert_result, estimator_result = await asyncio.gather(
            matcher_task, expert_task, estimator_task
        )
        
        # Process results in priority order: exact > close > approximation
        
        # STAGE 1: Check MATCHER result (exact matches)
        if matcher_result['status'] == 'exact_match':
            match_indices = matcher_result.get('exact_matches', [])
            matches = [candidates[i-1] for i in match_indices if 0 < i <= len(candidates)]
            
            if matches:
                unit = self._get_consensus_unit(matches)
                rate = matcher_result.get('recommended_rate')
                reference = self._build_reference_string(matches)
                
                if self.verbose_logging:
                    logger.info(f"  ✓ EXACT match found: {unit} @ {rate}")
                
                return {
                    'status': 'match',
                    'match_type': 'exact',
                    'stage': 'matcher',
                    'matches': matches,
                    'unit': unit,
                    'rate': rate,
                    'reference': reference,
                    'reasoning': matcher_result.get('reasoning', ''),
                    'confidence': 100,
                    'candidates': candidates
                }
        
        # STAGE 2: Check EXPERT result (close matches)
        if expert_result['status'] == 'close_match':
            close_matches_data = expert_result.get('close_matches', [])
            
            if close_matches_data:
                matches = []
                confidences = []
                for match_data in close_matches_data:
                    idx = match_data.get('index', 0)
                    confidence = match_data.get('confidence', 0)
                    
                    if 0 < idx <= len(candidates):
                        match = candidates[idx - 1].copy()
                        match['confidence'] = confidence
                        matches.append(match)
                        confidences.append(confidence)
                
                if matches:
                    unit = self._get_consensus_unit(matches)
                    rate = expert_result.get('recommended_rate')
                    avg_confidence = sum(confidences) / len(confidences)
                    reference = self._build_reference_string(matches)
                    
                    if self.verbose_logging:
                        logger.info(f"  ✓ CLOSE match found: {unit} @ {rate} ({avg_confidence:.0f}%)")
                    
                    return {
                        'status': 'match',
                        'match_type': 'close',
                        'stage': 'expert',
                        'matches': matches,
                        'unit': unit,
                        'rate': rate,
                        'reference': reference,
                        'reasoning': expert_result.get('reasoning', ''),
                        'confidence': avg_confidence,
                        'candidates': candidates
                    }
        
        # STAGE 3: Check ESTIMATOR result (approximation)
        if estimator_result['status'] == 'approximated':
            rate = estimator_result.get('approximated_rate')
            unit = estimator_result.get('unit', item_unit)
            reference_indices = estimator_result.get('reference_items', [])
            references = [candidates[i-1] for i in reference_indices if 0 < i <= len(candidates)]
            reference = self._build_reference_string(references) if references else ''
            
            if self.verbose_logging:
                logger.info(f"  ~ APPROXIMATED: {unit} @ {rate}")
            
            return {
                'status': 'match',
                'match_type': 'approximation',
                'stage': 'estimator',
                'matches': references,
                'unit': unit,
                'rate': rate,
                'reference': reference,
                'reasoning': estimator_result.get('reasoning', ''),
                'confidence': 60,
                'candidates': candidates
            }
        
        # No match found at any stage
        logger.info("  ✗ No match found at any stage")
        return {
            'status': 'no_match',
            'match_type': 'none',
            'matches': [],
            'unit': None,
            'rate': None,
            'reasoning': 'No acceptable match found at any stage',
            'candidates': candidates
        }

    
    async def _search_similar_items_async(
        self,
        description: str,
        parent: Optional[str],
        grandparent: Optional[str],
        namespace: str
    ) -> List[Dict[str, Any]]:
        """Async wrapper around vector search using asyncio.to_thread."""
        # Build enriched query text
        query_parts = []
        if grandparent:
            query_parts.append(f"Category: {grandparent}")
        if parent:
            query_parts.append(f"Category: {parent}")
        query_parts.append(description)
        query_text = '. '.join(query_parts)
        
        query_embedding = await self.embeddings.generate_embedding_async(query_text)
        
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
            filter_dict=None,
            namespace=namespace,
            include_metadata=True
        )
        
        candidates = []
        for result in results:
            if result['score'] >= self.similarity_threshold:
                candidates.append({
                    'description': result['metadata'].get('description', result['text']),
                    'unit': result['metadata'].get('unit', ''),
                    'rate': result['metadata'].get('rate'),
                    'similarity': result['score'],
                    'source': result['metadata'].get('sheet_name', ''),
                    'category': result['metadata'].get('category_path', ''),
                    'metadata': result['metadata']
                })
        return candidates
    
    async def _call_matcher_stage_async(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        prompt = build_matcher_prompt(target_info, candidates_text)
        return await self._call_llm_stage_async(MATCHER_SYSTEM_MESSAGE, prompt, stage_name="MATCHER")
    
    async def _call_expert_stage_async(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        prompt = build_expert_prompt(target_info, candidates_text)
        return await self._call_llm_stage_async(EXPERT_SYSTEM_MESSAGE, prompt, stage_name="EXPERT")
    
    async def _call_estimator_stage_async(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        prompt = build_estimator_prompt(target_info, candidates_text)
        return await self._call_llm_stage_async(ESTIMATOR_SYSTEM_MESSAGE, prompt, stage_name="ESTIMATOR")
    
    async def _call_llm_stage_async(self, system_message: str, prompt: str, stage_name: str = "LLM") -> Dict[str, Any]:
        """Async LLM call with JSON parsing and timing instrumentation."""
        import time
        start_time = time.perf_counter()
        logger.info(f"  [{stage_name}] ⏱ Started at {start_time:.3f}")
        try:
            await self.async_rate_limiter.acquire()
            acquire_time = time.perf_counter()
            logger.info(f"  [{stage_name}] Rate limiter acquired after {(acquire_time - start_time)*1000:.1f}ms")
            
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature
            )
            api_time = time.perf_counter()
            logger.info(f"  [{stage_name}] API responded after {(api_time - acquire_time)*1000:.1f}ms")
            
            content = response.choices[0].message.content
            if not content:
                logger.error(f"[{stage_name}] LLM returned empty content")
                return {'status': 'no_match'}
            try:
                result = json.loads(content)
                end_time = time.perf_counter()
                logger.info(f"  [{stage_name}] ✓ Completed in {(end_time - start_time)*1000:.1f}ms total")
                return result
            except json.JSONDecodeError:
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    return json.loads(json_str)
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    return json.loads(json_str)
                logger.error(f"[{stage_name}] Failed to parse LLM response: {content}")
                return {'status': 'no_match'}
        except Exception as e:
            end_time = time.perf_counter()
            logger.error(f"[{stage_name}] LLM call failed after {(end_time - start_time)*1000:.1f}ms: {e}")
            return {'status': 'no_match'}
    
    def _build_target_info(
        self,
        description: str,
        unit: str,
        item_code: str,
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> str:
        """Build target item information string."""
        parts = [f"Description: {description}"]
        if unit:
            parts.append(f"Unit: {unit}")
        if item_code:
            parts.append(f"Item Code: {item_code}")
        if parent:
            parts.append(f"Parent Category: {parent}")
        if grandparent:
            parts.append(f"Grandparent Category: {grandparent}")
        return '\n'.join(parts)
    
    def _build_candidates_text(self, candidates: List[Dict]) -> str:
        """Build candidates text for LLM."""
        lines = []
        for i, cand in enumerate(candidates, 1):
            lines.append(
                f"{i}. {cand['description']} | "
                f"Unit: {cand.get('unit', 'N/A')} | "
                f"Rate: {cand.get('rate', 'N/A')} | "
                f"Similarity: {cand.get('similarity', 0):.2f}"
            )
        return '\n'.join(lines)
    
    def _get_consensus_unit(self, matches: List[Dict]) -> str:
        """Get consensus unit from matches."""
        units = [m.get('unit', '') for m in matches if m.get('unit')]
        if not units:
            return ''
        # Return most common unit
        return max(set(units), key=units.count)
    
    def _build_reference_string(self, matches: List[Dict]) -> str:
        """Build reference string from matches."""
        refs = []
        for match in matches:
            source = match.get('source', 'Unknown')
            desc = match.get('description', '')[:50]
            refs.append(f"{source}: {desc}")
        return ' | '.join(refs)


async def process_items_parallel(
    rate_matcher: RateMatcher,
    items: List[Dict[str, Any]],
    max_workers: int = 100,
    namespace: str = ''
) -> List[Dict[str, Any]]:
    """
    Process multiple items in parallel using asyncio.
    
    Args:
        rate_matcher: RateMatcher instance
        items: List of items to process
        max_workers: Number of parallel workers (concurrency limit)
        namespace: Pinecone namespace
        
    Returns:
        List of results
    """
    logger.info(f"Processing {len(items)} items with {max_workers} workers...")
    
    results: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(max_workers)
    
    async def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            try:
                result = await rate_matcher.find_match(
                    item_description=item['description'],
                    item_unit=item.get('unit', ''),
                    item_code=item.get('item_code', ''),
                    parent=item.get('parent'),
                    grandparent=item.get('grandparent'),
                    namespace=namespace
                )
                result['item'] = item
                return result
            except Exception as e:
                logger.error(f"Error processing item: {e}")
                return {
                    'status': 'error',
                    'item': item,
                    'error': str(e)
                }
    
    results = await asyncio.gather(*[process_item(item) for item in items])
    
    logger.info(f"✓ Processed {len(results)} items")
    return list(results)
