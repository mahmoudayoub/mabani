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
        namespace: str = '',
        category_path: Optional[str] = None
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
            else:
                logger.info("  ⚠ Target has no unit; will be treated as no_match without LLM calls")
        
        # If the target does not have a unit, we cannot safely compare or reuse rates.
        # In this case, short-circuit and treat as no match without invoking any LLM stages.
        if not item_unit or not str(item_unit).strip():
            return {
                'status': 'no_match',
                'match_type': 'none',
                'matches': [],
                'unit': None,
                'rate': None,
                'reasoning': 'Target item has no unit; strict unit matching requires a defined unit',
                'candidates': []
            }
        
        # Step 1: Vector search with enriched context (async)
        candidates = await self._search_similar_items_async(
            item_description, item_unit, parent, grandparent, namespace
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
        
        # Step 2: 3-Stage LLM Validation - sequential with early exit
        logger.info("  Running 3-stage LLM validation sequentially with early exit...")
        
        # STAGE 1: MATCHER (exact)
        matcher_result = await self._call_matcher_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent, category_path
        )
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
        
        # STAGE 2: EXPERT (close) - only if no exact match
        expert_result = await self._call_expert_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent, category_path
        )
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
        
        # STAGE 3: ESTIMATOR (approximation) - only if no close match
        estimator_result = await self._call_estimator_stage_async(
            item_description, item_unit, item_code, candidates, parent, grandparent, category_path
        )
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
        unit: str,
        parent: Optional[str],
        grandparent: Optional[str],
        namespace: str
    ) -> List[Dict[str, Any]]:
        """
        Async wrapper around vector search.
        
        Builds the query text using the same structure as vector-store embeddings:
        "Category: A > B. Description. Unit: X"
        """
        # Build enriched query text aligned with embedding format
        query_parts = []
        
        category_segments: List[str] = []
        if grandparent:
            category_segments.append(str(grandparent))
        if parent and parent not in category_segments:
            category_segments.append(str(parent))
        if category_segments:
            query_parts.append(f"Category: {' > '.join(category_segments)}")
        
        query_parts.append(description)
        
        unit_str = str(unit).strip()
        if unit_str:
            query_parts.append(f"Unit: {unit_str}")
        
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
                meta = result['metadata']
                candidates.append({
                    'description': meta.get('description', result['text']),
                    'unit': meta.get('unit', ''),
                    'rate': meta.get('rate'),
                    'similarity': result['score'],
                    'source': meta.get('sheet_name', ''),
                    'category': meta.get('category_path', ''),
                    'parent': meta.get('parent', ''),
                    'grandparent': meta.get('grandparent', ''),
                    'metadata': meta
                })
        return candidates
    
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
    
    async def _call_matcher_stage_async(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str],
        category_path: Optional[str] = None
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent, category_path)
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
        grandparent: Optional[str],
        category_path: Optional[str] = None
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent, category_path)
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
        grandparent: Optional[str],
        category_path: Optional[str] = None
    ) -> Dict[str, Any]:
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent, category_path)
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
        grandparent: Optional[str],
        category_path: Optional[str] = None
    ) -> str:
        """
        Build target item information string for LLM prompts.
        
        Structure matches the candidate format for consistency:
        - Hierarchy (grandparent > parent)
        - Description
        - Unit (required and emphasized)
        - Item Code (optional)
        - Context (tail of category path if available)
        """
        parts = []
        
        # Build hierarchy string (same format as candidates)
        hierarchy_parts = []
        if grandparent:
            hierarchy_parts.append(str(grandparent))
        if parent:
            hierarchy_parts.append(str(parent))
        if hierarchy_parts:
            parts.append(f"Hierarchy: {' > '.join(hierarchy_parts)}")
        
        # Context tail from category path (starting from 3rd level if present)
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
        
        Structure matches the target format exactly:
        - Index
        - Hierarchy (grandparent > parent) - only 2 levels, same as target
        - Description
        - Unit
        - Rate
        - Similarity score
        """
        lines = []
        for i, cand in enumerate(candidates, 1):
            parent = cand.get('parent') or ''
            grandparent = cand.get('grandparent') or ''
            category_path = cand.get('category') or (cand.get('metadata') or {}).get('category_path', '')
            context_tail = self._context_tail_from_path(category_path)
            
            # Build hierarchy string - only 2 levels (grandparent > parent), same as target
            hierarchy_parts = []
            if grandparent:
                hierarchy_parts.append(grandparent)
            if parent and parent not in hierarchy_parts:
                hierarchy_parts.append(parent)
            
            hierarchy_str = ' > '.join(hierarchy_parts) if hierarchy_parts else ''
            context_line = f"Context: {context_tail}\n" if context_tail else ''
            
            # Unit is required - show N/A if missing
            unit_val = cand.get('unit', '')
            unit_str = str(unit_val).strip() if unit_val else 'N/A'
            
            # Rate - show actual value or N/A
            rate_val = cand.get('rate')
            rate_str = f"{rate_val}" if rate_val is not None else 'N/A'
            
            # Format: same structure as target (Hierarchy, Description, Unit)
            if hierarchy_str:
                block = f"[{i}] Hierarchy: {hierarchy_str}\n"
                if context_line:
                    block += f"    {context_line}"
                block += (
                    f"    Description: {cand['description']}\n"
                    f"    Unit: {unit_str} | Rate: {rate_str} | Similarity: {cand.get('similarity', 0):.2f}"
                )
                lines.append(block)
            else:
                block = f"[{i}] "
                if context_line:
                    block += f"{context_line}"
                else:
                    block += "\n"
                block += (
                    f"    Description: {cand['description']}\n"
                    f"    Unit: {unit_str} | Rate: {rate_str} | Similarity: {cand.get('similarity', 0):.2f}"
                )
                lines.append(block)
        return '\n\n'.join(lines)
    
    def _get_consensus_unit(self, matches: List[Dict]) -> str:
        """Get consensus unit from matches."""
        units = [m.get('unit', '') for m in matches if m.get('unit')]
        if not units:
            return ''
        # Return most common unit
        return max(set(units), key=units.count)
    
    def _build_reference_string(self, matches: List[Dict]) -> str:
        """Build reference string from matches with key context."""
        refs = []
        for match in matches:
            source = match.get('source', 'Unknown')
            parent = match.get('parent') or ''
            grandparent = match.get('grandparent') or ''
            desc = match.get('description', '')[:50]
            unit = match.get('unit') or ''
            rate = match.get('rate')
            row = (match.get('metadata') or {}).get('row_number')
            
            parts = [f"Sheet={source}"]
            if grandparent:
                parts.append(f"GP={grandparent}")
            if parent:
                parts.append(f"P={parent}")
            parts.append(f"Desc={desc}")
            if unit:
                parts.append(f"Unit={unit}")
            if rate is not None:
                parts.append(f"Rate={rate}")
            if row is not None:
                parts.append(f"Row={row}")
            
            refs.append('; '.join(parts))
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
                    namespace=namespace,
                    category_path=item.get('category_path')
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
