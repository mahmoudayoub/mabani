"""
Rate Matcher - LLM-powered 3-stage matching system.
Stages: 1) Matcher (exact), 2) Expert (close), 3) Estimator (approximation)
"""
import logging
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
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
        openai_client: OpenAI,
        embeddings_service: EmbeddingsService,
        vector_store_service: VectorStoreService,
        similarity_threshold: float = 0.7,
        top_k: int = 6,
        model: str = "gpt-4o-mini",
        verbose_logging: bool = True
    ):
        """
        Initialize rate matcher.
        
        Args:
            openai_client: OpenAI client instance
            embeddings_service: Service for generating embeddings
            vector_store_service: Service for vector store operations
            similarity_threshold: Minimum similarity score
            top_k: Number of candidates to retrieve
            model: OpenAI model for LLM calls
            verbose_logging: Enable detailed logging
        """
        self.client = openai_client
        self.embeddings = embeddings_service
        self.vector_store = vector_store_service
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.model = model
        self.verbose_logging = verbose_logging
        
        logger.info(f"Rate matcher initialized with 3-stage approach")
        logger.info(f"  - Similarity threshold: {similarity_threshold}")
        logger.info(f"  - Top-K candidates: {top_k}")
        logger.info(f"  - Model: {model}")
    
    def find_match(
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
        
        # Step 1: Vector search with enriched context
        candidates = self._search_similar_items(
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
        
        # Step 2: 3-Stage LLM Validation
        logger.info("  Starting 3-stage LLM validation...")
        
        # STAGE 1: MATCHER - Check for exact matches
        logger.info("  Stage 1: MATCHER - Checking for exact matches...")
        matcher_result = self._call_matcher_stage(
            item_description, item_unit, item_code, candidates, parent, grandparent
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
        
        if self.verbose_logging:
            logger.info("  No exact matches found, proceeding to Expert stage...")
        
        # STAGE 2: EXPERT - Check for close matches
        if self.verbose_logging:
            logger.info("  Stage 2: EXPERT - Checking for close matches...")
        expert_result = self._call_expert_stage(
            item_description, item_unit, item_code, candidates, parent, grandparent
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
        
        if self.verbose_logging:
            logger.info("  No close matches found, proceeding to Estimator stage...")
        
        # STAGE 3: ESTIMATOR - Approximate from similar items
        if self.verbose_logging:
            logger.info("  Stage 3: ESTIMATOR - Approximating rate...")
        estimator_result = self._call_estimator_stage(
            item_description, item_unit, item_code, candidates, parent, grandparent
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
    
    def _search_similar_items(
        self,
        description: str,
        parent: Optional[str],
        grandparent: Optional[str],
        namespace: str
    ) -> List[Dict[str, Any]]:
        """Search vector store for similar items."""
        # Build enriched query (matching vector store format)
        query_parts = []
        
        if grandparent:
            query_parts.append(f"Category: {grandparent}")
        if parent:
            query_parts.append(f"Category: {parent}")
        
        query_parts.append(description)
        query_text = '. '.join(query_parts)
        
        # Generate embedding for query
        query_embedding = self.embeddings.generate_embedding(query_text)
        
        # Search vector store
        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
            namespace=namespace,
            include_metadata=True
        )
        
        # Filter by similarity threshold and format
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
    
    def _call_matcher_stage(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        """Call Stage 1: Matcher."""
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        
        prompt = build_matcher_prompt(target_info, candidates_text)
        
        return self._call_llm_stage(MATCHER_SYSTEM_MESSAGE, prompt)
    
    def _call_expert_stage(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        """Call Stage 2: Expert."""
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        
        prompt = build_expert_prompt(target_info, candidates_text)
        
        return self._call_llm_stage(EXPERT_SYSTEM_MESSAGE, prompt)
    
    def _call_estimator_stage(
        self,
        description: str,
        unit: str,
        item_code: str,
        candidates: List[Dict],
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> Dict[str, Any]:
        """Call Stage 3: Estimator."""
        target_info = self._build_target_info(description, unit, item_code, parent, grandparent)
        candidates_text = self._build_candidates_text(candidates)
        
        prompt = build_estimator_prompt(target_info, candidates_text)
        
        return self._call_llm_stage(ESTIMATOR_SYSTEM_MESSAGE, prompt)
    
    def _call_llm_stage(self, system_message: str, prompt: str) -> Dict[str, Any]:
        """Call LLM and parse JSON response."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            
            content = response.choices[0].message.content
            
            # Try to parse JSON
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result
                else:
                    logger.error(f"Failed to parse LLM response: {content}")
                    return {'status': 'no_match'}
        
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
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


def process_items_parallel(
    rate_matcher: RateMatcher,
    items: List[Dict[str, Any]],
    max_workers: int = 5,
    namespace: str = ''
) -> List[Dict[str, Any]]:
    """
    Process multiple items in parallel using ThreadPoolExecutor.
    
    Args:
        rate_matcher: RateMatcher instance
        items: List of items to process
        max_workers: Number of parallel workers
        namespace: Pinecone namespace
        
    Returns:
        List of results
    """
    logger.info(f"Processing {len(items)} items with {max_workers} workers...")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_item = {
            executor.submit(
                rate_matcher.find_match,
                item['description'],
                item.get('unit', ''),
                item.get('item_code', ''),
                item.get('parent'),
                item.get('grandparent'),
                namespace
            ): item
            for item in items
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                result = future.result()
                result['item'] = item
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing item: {e}")
                results.append({
                    'status': 'error',
                    'item': item,
                    'error': str(e)
                })
    
    logger.info(f"✓ Processed {len(results)} items")
    return results
