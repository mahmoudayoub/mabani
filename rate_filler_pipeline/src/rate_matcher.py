"""
Rate Matcher - Find matching items using vector search + LLM validation.
"""
import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
import json

# Import from vector store using absolute imports
from json_to_vectorstore.src.embeddings_generator import EmbeddingsGenerator
from json_to_vectorstore.src.pinecone_uploader import PineconeUploader

logger = logging.getLogger(__name__)


class RateMatcher:
    """Match items and fill missing rates using vector search + LLM."""
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        similarity_threshold: float = 0.76,
        top_k: int = 6
    ):
        """
        Initialize rate matcher.
        
        Args:
            openai_api_key: OpenAI API key
            similarity_threshold: Minimum similarity score
            top_k: Number of candidates to retrieve
        """
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not provided")
        
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.openai_api_key)
        
        # Initialize vector search
        logger.info("Initializing vector search...")
        self.embedder = EmbeddingsGenerator(api_key=self.openai_api_key)
        self.uploader = PineconeUploader()
        self.uploader.index = self.uploader.pc.Index(self.uploader.index_name)
        
        logger.info(f"Rate matcher initialized")
        logger.info(f"  - Similarity threshold: {similarity_threshold}")
        logger.info(f"  - Top-K candidates: {top_k}")
    
    def find_matches(
        self,
        item_description: str,
        item_code: str = ''
    ) -> Dict[str, Any]:
        """
        Find matching items for a given description.
        
        Process:
        1. Search vector store for top-K similar items (score > threshold)
        2. Pass candidates to LLM for exact match validation
        3. Return matched items with rates
        
        Args:
            item_description: Item description to match
            item_code: Optional item code
            
        Returns:
            Dictionary with match results:
            {
                'status': 'match' | 'no_match',
                'matches': [...],  # List of exact matches (if found)
                'unit': str,       # Consensus unit (if matched)
                'rate': float,     # Average rate (if matched)
                'candidates': [...] # Retrieved candidates
            }
        """
        logger.info(f"Finding matches for: {item_description[:60]}...")
        
        # Step 1: Vector search
        candidates = self._search_similar_items(item_description)
        
        if not candidates:
            logger.info("  No candidates found above threshold")
            return {
                'status': 'no_match',
                'matches': [],
                'unit': None,
                'rate': None,
                'candidates': []
            }
        
        logger.info(f"  Found {len(candidates)} candidates")
        
        # Step 2: LLM validation
        llm_result = self._validate_with_llm(
            item_description,
            item_code,
            candidates
        )
        
        if llm_result['status'] == 'match':
            # Convert indices to actual candidates
            match_indices = llm_result.get('matches', [])
            # Indices are 1-based in the prompt, convert to 0-based
            matches = [candidates[i-1] for i in match_indices if 0 < i <= len(candidates)]
            
            if not matches:
                logger.info("  No valid matches after index conversion")
                return {
                    'status': 'no_match',
                    'matches': [],
                    'unit': None,
                    'rate': None,
                    'candidates': candidates
                }
            
            # Calculate consensus unit and average rate
            unit = self._get_consensus_unit(matches)
            rate = self._calculate_average_rate(matches)
            
            logger.info(f"  ✓ Match found: {unit} @ {rate}")
            
            return {
                'status': 'match',
                'matches': matches,
                'unit': unit,
                'rate': rate,
                'candidates': candidates
            }
        else:
            logger.info("  ✗ No exact match")
            return {
                'status': 'no_match',
                'matches': [],
                'unit': None,
                'rate': None,
                'candidates': candidates
            }
    
    def _search_similar_items(
        self,
        description: str
    ) -> List[Dict[str, Any]]:
        """
        Search vector store for similar items.
        
        Args:
            description: Item description
            
        Returns:
            List of similar items above threshold
        """
        # Generate embedding
        query_vector = self.embedder.generate_embedding(description)
        
        # Search Pinecone
        results = self.uploader.search(
            query_embedding=query_vector,
            top_k=self.top_k
        )
        
        # Filter by threshold
        candidates = []
        for result in results:
            score = result.get('score', 0)
            if score >= self.similarity_threshold:
                candidates.append({
                    'description': result.get('text', ''),
                    'unit': result.get('metadata', {}).get('unit', ''),
                    'rate': result.get('metadata', {}).get('rate', 0),
                    'code': result.get('metadata', {}).get('item_code', ''),
                    'project': result.get('metadata', {}).get('source_sheet', ''),
                    'score': score
                })
        
        return candidates
    
    def _validate_with_llm(
        self,
        target_description: str,
        target_code: str,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Use LLM to validate if candidates are exact matches.
        
        Args:
            target_description: Item to match
            target_code: Item code (optional)
            candidates: Retrieved candidates
            
        Returns:
            {'status': 'match'|'no_match', 'matches': [...]}
        """
        # Build prompt
        prompt = self._build_validation_prompt(
            target_description,
            target_code,
            candidates
        )
        
        try:
            # Call OpenAI
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in construction BOQ (Bill of Quantities) analysis. Your task is to identify exact matches between construction items, even if the wording differs."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            if not result_text:
                logger.error("LLM returned empty response")
                return {'status': 'no_match', 'matches': []}
            
            result = json.loads(result_text)
            
            logger.debug(f"LLM response: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            return {'status': 'no_match', 'matches': []}
    
    def _build_validation_prompt(
        self,
        target_description: str,
        target_code: str,
        candidates: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for LLM validation - only descriptions and units."""
        
        code_info = f" (Code: {target_code})" if target_code else ""
        
        candidates_text = ""
        for i, cand in enumerate(candidates, 1):
            candidates_text += f"""
{i}. Description: {cand['description']}
   Unit: {cand['unit']}
"""
        
        prompt = f"""You are analyzing a construction BOQ item to find exact matches from a database.

TARGET ITEM TO MATCH:
Description: {target_description}{code_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

TASK:
Determine which candidates (if any) are EXACT MATCHES to the target item based on description and unit.

EXACT MATCH means:
- Same construction work/item (even if wording differs)
- Same specifications (materials, dimensions, standards)
- Same scope of work
- Compatible units (m², m³, No., LS, ha, ton, etc.)

NOT an exact match if:
- Different materials or specifications
- Different scope (e.g., "supply only" vs "supply & install")
- Different quality/grade
- Incompatible units

OUTPUT FORMAT (JSON):
{{
    "status": "match" or "no_match",
    "matches": [1, 3, 5],  // Indices of matching candidates (empty if no match)
    "reasoning": "Brief explanation of why items match or don't match"
}}

Examples:
- "EXCAVATION FOR FOUNDATIONS" matches "EXCAVATION IN FOUNDATION AREAS" ✓
- "CONCRETE C40" does NOT match "CONCRETE C30" ✗
- "SUPPLY PUMPING STATION 80KW" matches "PUMPING STATION 80KW SUPPLY & INSTALL" (if specs same) ✓

Analyze carefully and return JSON only."""
        
        return prompt
    
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
    
    def _calculate_average_rate(self, matches: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate average rate from matched items.
        
        Args:
            matches: List of matched items
            
        Returns:
            Average rate (or None if no rates)
        """
        rates = [m.get('rate', 0) for m in matches if m.get('rate')]
        if not rates:
            return None
        
        return round(sum(rates) / len(rates), 2)
