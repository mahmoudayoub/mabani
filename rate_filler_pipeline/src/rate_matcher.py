"""
Rate Matcher - Find matching items using vector search + 3-stage LLM validation.
Stages: 1) Matcher (exact), 2) Expert (close), 3) Estimator (approximation)
"""
import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
import json

# Import from vector store using absolute imports
from json_to_vectorstore.src.embeddings_generator import EmbeddingsGenerator
from json_to_vectorstore.src.pinecone_uploader import PineconeUploader

# Import prompts
from .prompts import (
    build_matcher_prompt,
    build_expert_prompt,
    build_estimator_prompt,
    MATCHER_SYSTEM_MESSAGE,
    EXPERT_SYSTEM_MESSAGE,
    ESTIMATOR_SYSTEM_MESSAGE
)

logger = logging.getLogger(__name__)


class RateMatcher:
    """Match items and fill missing rates using vector search + 3-stage LLM."""
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        similarity_threshold: float = 0.7,
        top_k: int = 6,
        verbose_logging: bool = True
    ):
        """
        Initialize rate matcher.
        
        Args:
            openai_api_key: OpenAI API key
            similarity_threshold: Minimum similarity score
            top_k: Number of candidates to retrieve
            verbose_logging: Enable detailed logging during processing
        """
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not provided")
        
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.verbose_logging = verbose_logging
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.openai_api_key)
        
        # Initialize vector search
        logger.info("Initializing vector search...")
        self.embedder = EmbeddingsGenerator(api_key=self.openai_api_key)
        self.uploader = PineconeUploader()
        self.uploader.index = self.uploader.pc.Index(self.uploader.index_name)
        
        logger.info(f"Rate matcher initialized with 3-stage approach")
        logger.info(f"  - Similarity threshold: {similarity_threshold}")
        logger.info(f"  - Top-K candidates: {top_k}")
    
    def find_matches(
        self,
        item_description: str,
        item_unit: str = '',
        item_code: str = '',
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Find matching items for a given description with hierarchical context.
        
        Process:
        1. Build enriched query text (matching vector store format)
        2. Search vector store for top-K similar items (score > threshold)
        3. Pass candidates to LLM for exact match validation
        4. Return matched items with rates
        
        Args:
            item_description: Item description to match
            item_unit: Unit of the target item
            item_code: Optional item code
            parent: Parent description (immediate level above)
            grandparent: Grandparent description (two levels above)
            
        Returns:
            Dictionary with match results:
            {
                'status': 'match' | 'no_match',
                'matches': [...],  # List of exact matches (if found)
                'unit': str,       # Consensus unit (if matched)
                'rate': float,     # LLM-calculated/recommended rate (if matched)
                'candidates': [...] # Retrieved candidates
            }
        """
        logger.info(f"Finding matches for: {item_description[:60]}...")
        if self.verbose_logging:
            if parent:
                logger.info(f"  Parent: {parent[:60]}...")
            if grandparent:
                logger.info(f"  Grandparent: {grandparent[:60]}...")
            if item_unit:
                logger.info(f"  Unit: {item_unit}")
        
        # Step 1: Vector search with enriched context
        candidates = self._search_similar_items(item_description, parent, grandparent)
        
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
            item_description,
            item_unit,
            item_code,
            candidates,
            parent,
            grandparent
        )
        
        if matcher_result['status'] == 'exact_match':
            match_indices = matcher_result.get('exact_matches', [])
            matches = [candidates[i-1] for i in match_indices if 0 < i <= len(candidates)]
            
            if matches:
                unit = self._get_consensus_unit(matches)
                # Get LLM-calculated recommended rate (required)
                rate = matcher_result.get('recommended_rate')
                if rate is None or rate <= 0:
                    logger.error("  ✗ LLM did not provide valid recommended_rate for exact match")
                    raise ValueError("Matcher stage must return a valid recommended_rate > 0")
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
                    'candidates': candidates
                }
        
        if self.verbose_logging:
            logger.info("  No exact matches found, proceeding to Expert stage...")
        
        # STAGE 2: EXPERT - Check for close matches
        if self.verbose_logging:
            logger.info("  Stage 2: EXPERT - Checking for close matches...")
        expert_result = self._call_expert_stage(
            item_description,
            item_unit,
            item_code,
            candidates,
            parent,
            grandparent
        )
        
        if expert_result['status'] == 'close_match':
            close_matches_data = expert_result.get('close_matches', [])
            
            if close_matches_data:
                matches = []
                confidences = []
                for match_data in close_matches_data:
                    idx = match_data.get('index', 0)
                    confidence = match_data.get('confidence', 0)
                    differences = match_data.get('differences', '')
                    
                    if 0 < idx <= len(candidates):
                        match = candidates[idx - 1].copy()
                        match['confidence'] = confidence
                        match['differences'] = differences
                        matches.append(match)
                        confidences.append(confidence)
            
                if matches:
                    unit = self._get_consensus_unit(matches)
                    # Get LLM-calculated recommended rate (required)
                    rate = expert_result.get('recommended_rate')
                    if rate is None or rate <= 0:
                        logger.error("  ✗ LLM did not provide valid recommended_rate for close match")
                        raise ValueError("Expert stage must return a valid recommended_rate > 0")
                    reference = self._build_reference_string(matches)
                    avg_confidence = round(sum(confidences) / len(confidences), 1)
                    
                    if self.verbose_logging:
                        logger.info(f"  ≈ CLOSE match found: {unit} @ {rate} (confidence: {avg_confidence}%)")
                    
                    return {
                        'status': 'match',
                        'match_type': 'close',
                        'stage': 'expert',
                        'matches': matches,
                        'unit': unit,
                        'rate': rate,
                        'reference': reference,
                        'confidence': avg_confidence,
                        'reasoning': expert_result.get('reasoning', ''),
                        'candidates': candidates
                    }
        
        if self.verbose_logging:
            logger.info("  No close matches found, proceeding to Estimator stage...")
        
        # STAGE 3: ESTIMATOR - Check for approximations
        if self.verbose_logging:
            logger.info("  Stage 3: ESTIMATOR - Checking for approximations...")
        estimator_result = self._call_estimator_stage(
            item_description,
            item_unit,
            item_code,
            candidates,
            parent,
            grandparent
        )
        
        if estimator_result['status'] == 'approximation':
            approximations_data = estimator_result.get('approximations', [])
            best_entry = None

            # Pick the highest-confidence approximation that has a valid rate
            for approx_data in approximations_data:
                approx_rate = approx_data.get('approximated_rate')
                if isinstance(approx_rate, (int, float)) and approx_rate > 0:
                    if best_entry is None or approx_data.get('confidence', 0) > best_entry.get('confidence', 0):
                        best_entry = approx_data

            if best_entry:
                idx = best_entry.get('index', 0)
                if 0 < idx <= len(candidates):
                    match = candidates[idx - 1].copy()
                    match['confidence'] = best_entry.get('confidence', 0)
                    match['approximated_rate'] = best_entry.get('approximated_rate')
                    match['adjustment'] = best_entry.get('adjustment', '')
                    match['limitations'] = best_entry.get('limitations', '')

                    unit = self._get_consensus_unit([match])
                    rate = round(float(match['approximated_rate']), 2)
                    if rate == 0:
                        logger.error("  ✗ LLM provided approximated_rate of 0")
                        raise ValueError("Estimator stage approximated_rate must be > 0")
                    reference = self._build_reference_string([match])
                    confidence = match.get('confidence', 0)

                    if self.verbose_logging:
                        logger.info(f"  ~ APPROXIMATION found: {unit} @ {rate} (confidence: {confidence}%)")
                        logger.info(f"    Adjustment: {match.get('adjustment', 'N/A')}")

                    return {
                        'status': 'match',
                        'match_type': 'approximation',
                        'stage': 'estimator',
                        'matches': [match],
                        'unit': unit,
                        'rate': rate,
                        'reference': reference,
                        'confidence': confidence,
                        'adjustment': match.get('adjustment', ''),
                        'reasoning': estimator_result.get('reasoning', ''),
                        'candidates': candidates
                    }
        
        # No matches found in any stage
        if self.verbose_logging:
            logger.info("  ✗ No matches found in any stage")
        reasoning_parts = [
            f"Matcher: {matcher_result.get('reasoning', 'N/A')}",
            f"Expert: {expert_result.get('reasoning', 'N/A')}",
            f"Estimator: {estimator_result.get('reasoning', 'N/A')}"
        ]
        
        return {
            'status': 'no_match',
            'match_type': 'none',
            'stage': 'none',
            'matches': [],
            'unit': None,
            'rate': None,
            'reasoning': ' | '.join(reasoning_parts),
            'candidates': candidates
        }
    
    def _call_matcher_stage(
        self,
        target_description: str,
        target_unit: str,
        target_code: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stage 1: Matcher - Check for exact matches and calculate recommended rate."""
        # Build target info
        target_info = self._build_target_info(target_description, target_unit, target_code, parent, grandparent)
        
        # Build candidates text WITH RATES for the Matcher stage
        candidates_text = self._build_candidates_text(candidates, include_rates=True)
        
        # Build prompt
        prompt = build_matcher_prompt(target_info, candidates_text)
        
        return self._call_llm(prompt, MATCHER_SYSTEM_MESSAGE, "Matcher")
    
    def _call_expert_stage(
        self,
        target_description: str,
        target_unit: str,
        target_code: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stage 2: Expert - Check for close matches with minor differences and calculate recommended rate."""
        # Build target info
        target_info = self._build_target_info(target_description, target_unit, target_code, parent, grandparent)
        
        # Build candidates text WITH RATES for the Expert stage
        candidates_text = self._build_candidates_text(candidates, include_rates=True)
        
        # Build prompt
        prompt = build_expert_prompt(target_info, candidates_text)
        
        return self._call_llm(prompt, EXPERT_SYSTEM_MESSAGE, "Expert")
    
    def _call_estimator_stage(
        self,
        target_description: str,
        target_unit: str,
        target_code: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stage 3: Estimator - Check for approximation possibilities and calculate approximated rates."""
        # Build target info
        target_info = self._build_target_info(target_description, target_unit, target_code, parent, grandparent)
        
        # Build candidates text WITH RATES for the Estimator stage
        candidates_text = self._build_candidates_text(candidates, include_rates=True)
        
        # Build prompt
        prompt = build_estimator_prompt(target_info, candidates_text)
        
        return self._call_llm(prompt, ESTIMATOR_SYSTEM_MESSAGE, "Estimator")
    
    def _call_llm(
        self,
        prompt: str,
        system_message: str,
        stage_name: str
    ) -> Dict[str, Any]:
        """Call LLM with given prompt and system message."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini-2025-08-07",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                logger.error(f"{stage_name} returned empty response")
                return {'status': 'error', 'reasoning': 'Empty response from LLM'}
            
            result = json.loads(result_text)
            
            logger.info(f"  {stage_name} Response - Status: {result.get('status', 'unknown')}")
            logger.info(f"  {stage_name} Response - Reasoning: {result.get('reasoning', 'N/A')[:100]}...")
            
            return result
            
        except Exception as e:
            logger.error(f"{stage_name} error: {e}")
            return {'status': 'error', 'reasoning': f'LLM error: {str(e)}'}
    
    def _build_target_info(
        self,
        description: str,
        unit: str,
        code: str,
        parent: Optional[str],
        grandparent: Optional[str]
    ) -> str:
        """Build target item info string."""
        code_info = f" (Code: {code})" if code else ""
        unit_info = f"\nUnit: {unit}" if unit else ""
        target_info = f"Description: {description}{code_info}{unit_info}"
        
        if parent:
            target_info = f"Parent: {parent}\n{target_info}"
        if grandparent:
            target_info = f"Grandparent: {grandparent}\n{target_info}"
        
        return target_info
    
    def _build_candidates_text(self, candidates: List[Dict[str, Any]], include_rates: bool = False) -> str:
        """
        Build candidates text for prompt.
        
        Args:
            candidates: List of candidate items
            include_rates: If True, include rate information (used in all stages so LLM can calculate the fill rate)
        """
        candidates_text = ""
        
        for i, cand in enumerate(candidates, 1):
            cand_parent = cand.get('parent', '')
            cand_grandparent = cand.get('grandparent', '')
            cand_rate = cand.get('rate', 0)
            
            cand_text = f"{i}. Description: {cand['description']}\n   Unit: {cand['unit']}"
            
            if include_rates and cand_rate:
                cand_text += f"\n   Rate: {cand_rate:.2f}"
            
            if cand_parent:
                cand_text += f"\n   Parent: {cand_parent}"
            if cand_grandparent:
                cand_text += f"\n   Grandparent: {cand_grandparent}"
            
            candidates_text += f"\n{cand_text}\n"
        
        return candidates_text
    
    def _search_similar_items(
        self,
        description: str,
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search vector store for similar items using enriched context.
        
        Builds query in same format as vector store embeddings:
        "[grandparent] | [parent] | [description]"
        
        Args:
            description: Item description
            parent: Parent description (optional)
            grandparent: Grandparent description (optional)
            
        Returns:
            List of similar items above threshold
        """
        # Build enriched query text (same format as vector store - just values, no labels)
        text_parts = []
        if grandparent:
            text_parts.append(grandparent)
        if parent:
            text_parts.append(parent)
        text_parts.append(description)
        
        enriched_query = " | ".join(text_parts)
        
        logger.debug(f"Enriched query: {enriched_query[:100]}...")
        
        # Generate embedding for enriched query
        query_vector = self.embedder.generate_embedding(enriched_query)
        
        # Search Pinecone
        results = self.uploader.search(
            query_embedding=query_vector,
            top_k=self.top_k
        )
        
        # Filter by threshold AND only include items with valid rates
        candidates = []
        for result in results:
            score = result.get('score', 0)
            if score >= self.similarity_threshold:
                metadata = result.get('metadata', {})
                rate = metadata.get('rate', 0)
                
                # Only include candidates that have a valid rate
                if rate and rate > 0:
                    candidates.append({
                        'description': result.get('text', ''),
                        'unit': metadata.get('unit', ''),
                        'rate': rate,
                        'code': metadata.get('item_code', ''),
                        'project': metadata.get('source_sheet', ''),
                        'row_number': metadata.get('row_number', ''),
                        'parent': metadata.get('parent', ''),
                        'grandparent': metadata.get('grandparent', ''),
                        'score': score
                    })
        
        return candidates
    
    def _get_consensus_unit(self, matches: List[Dict[str, Any]]) -> str:
        """
        Get consensus unit from matched items.
        
        Args:
            matches: List of matched items
            
        Returns:
            Most common unit
        """
        units = [m.get('unit', '') for m in matches if m.get('unit')]
        if not units:
            return ''
        
        # Return most common
        from collections import Counter
        return Counter(units).most_common(1)[0][0]
    
    def _build_reference_string(self, matches: List[Dict[str, Any]]) -> str:
        """
        Build reference string with source info for each matched item.
        
        Format: "Grandparent > Parent > Description [Sheet1-Row25@450.00]; ..."
        
        Args:
            matches: List of matched items
            
        Returns:
            Reference string with source info
        """
        references = []
        for match in matches:
            # Get hierarchy info
            grandparent = match.get('grandparent', '')
            parent = match.get('parent', '')
            description = match.get('description', '')
            
            # Extract just the description part (remove enriched parent/grandparent if present)
            # The description might be in format "GP | P | Desc", extract last part
            if ' | ' in description:
                parts = description.split(' | ')
                description = parts[-1]  # Get the actual description (last part)
            
            # Build hierarchy path
            hierarchy_parts = []
            if grandparent:
                hierarchy_parts.append(grandparent)
            if parent:
                hierarchy_parts.append(parent)
            if description:
                hierarchy_parts.append(description)
            
            hierarchy_path = " > ".join(hierarchy_parts) if hierarchy_parts else "Unknown"
            
            # Get source info
            project = match.get('project', 'Unknown')
            row_num = match.get('row_number', '')
            rate = match.get('rate', 0)
            
            # Build reference
            if row_num:
                ref = f"{hierarchy_path} [{project}-Row{row_num}@{rate:.2f}]"
            else:
                ref = f"{hierarchy_path} [{project}@{rate:.2f}]"
            
            references.append(ref)
        
        return "; ".join(references)
