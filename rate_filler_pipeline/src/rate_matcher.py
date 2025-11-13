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
        similarity_threshold: float = 0.7,
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
            item_code: Optional item code
            parent: Parent description (immediate level above)
            grandparent: Grandparent description (two levels above)
            
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
        if parent:
            logger.info(f"  Parent: {parent[:60]}...")
        if grandparent:
            logger.info(f"  Grandparent: {grandparent[:60]}...")
        
        # Step 1: Vector search with enriched context
        candidates = self._search_similar_items(item_description, parent, grandparent)
        
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
        
        # Step 2: LLM validation with hierarchical context
        llm_result = self._validate_with_llm(
            item_description,
            item_code,
            candidates,
            parent,
            grandparent
        )
        
        # Handle exact matches
        if llm_result['status'] == 'exact_match':
            match_indices = llm_result.get('exact_matches', [])
            # Indices are 1-based in the prompt, convert to 0-based
            matches = [candidates[i-1] for i in match_indices if 0 < i <= len(candidates)]
            
            if not matches:
                # Check for similar matches if no exact matches
                if llm_result.get('similar_matches'):
                    return self._handle_similar_matches(llm_result, candidates)
                
                logger.info("  No valid matches after index conversion")
                return {
                    'status': 'no_match',
                    'match_type': 'none',
                    'matches': [],
                    'unit': None,
                    'rate': None,
                    'reasoning': llm_result.get('reasoning', ''),
                    'candidates': candidates
                }
            
            # Calculate consensus unit and average rate
            unit = self._get_consensus_unit(matches)
            rate = self._calculate_average_rate(matches)
            
            # Build reference string with source info
            reference = self._build_reference_string(matches)
            
            logger.info(f"  ✓ Exact match found: {unit} @ {rate}")
            
            return {
                'status': 'match',
                'match_type': 'exact',
                'matches': matches,
                'unit': unit,
                'rate': rate,
                'reference': reference,
                'reasoning': llm_result.get('reasoning', ''),
                'candidates': candidates
            }
        
        # Handle similar matches
        elif llm_result['status'] == 'similar_match':
            return self._handle_similar_matches(llm_result, candidates)
        
        # No match
        else:
            logger.info("  ✗ No match")
            return {
                'status': 'no_match',
                'match_type': 'none',
                'matches': [],
                'unit': None,
                'rate': None,
                'reasoning': llm_result.get('reasoning', ''),
                'candidates': candidates
            }
    
    def _handle_similar_matches(
        self,
        llm_result: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle similar matches with confidence levels."""
        similar_matches_data = llm_result.get('similar_matches', [])
        
        if not similar_matches_data:
            return {
                'status': 'no_match',
                'match_type': 'none',
                'matches': [],
                'unit': None,
                'rate': None,
                'reasoning': llm_result.get('reasoning', ''),
                'candidates': candidates
            }
        
        # Extract matches with confidence
        matches = []
        confidences = []
        for match_data in similar_matches_data:
            idx = match_data.get('index', 0)
            confidence = match_data.get('confidence', 0)
            
            if 0 < idx <= len(candidates):
                match = candidates[idx - 1].copy()
                match['confidence'] = confidence
                matches.append(match)
                confidences.append(confidence)
        
        if not matches:
            logger.info("  No valid similar matches after index conversion")
            return {
                'status': 'no_match',
                'match_type': 'none',
                'matches': [],
                'unit': None,
                'rate': None,
                'reasoning': llm_result.get('reasoning', ''),
                'candidates': candidates
            }
        
        # Calculate consensus unit and average rate
        unit = self._get_consensus_unit(matches)
        rate = self._calculate_average_rate(matches)
        
        # Build reference string
        reference = self._build_reference_string(matches)
        
        # Calculate average confidence
        avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0
        
        logger.info(f"  ≈ Similar match found: {unit} @ {rate} (confidence: {avg_confidence}%)")
        
        return {
            'status': 'match',
            'match_type': 'similar',
            'matches': matches,
            'unit': unit,
            'rate': rate,
            'reference': reference,
            'confidence': avg_confidence,
            'reasoning': llm_result.get('reasoning', ''),
            'candidates': candidates
        }
    
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
    
    def _validate_with_llm(
        self,
        target_description: str,
        target_code: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Use LLM to validate if candidates are exact matches.
        
        Args:
            target_description: Item to match
            target_code: Item code (optional)
            candidates: Retrieved candidates
            parent: Parent description (optional)
            grandparent: Grandparent description (optional)
            
        Returns:
            {'status': 'match'|'no_match', 'matches': [...]}
        """
        # Log candidates being evaluated
        logger.info(f"LLM Validation - Target: {target_description}")
        logger.info(f"LLM Validation - Evaluating {len(candidates)} candidates:")
        for i, cand in enumerate(candidates, 1):
            cand_parent = cand.get('parent', '')
            cand_grandparent = cand.get('grandparent', '')
            logger.info(f"  Candidate {i}: {cand['description']}")
            logger.info(f"    Unit: {cand['unit']}, Rate: {cand.get('rate', 'N/A')}")
            if cand_parent:
                logger.info(f"    Parent: {cand_parent}")
            if cand_grandparent:
                logger.info(f"    Grandparent: {cand_grandparent}")
        
        # Build prompt with parent/grandparent context
        prompt = self._build_validation_prompt(
            target_description,
            target_code,
            candidates,
            parent,
            grandparent
        )
        
        try:
            # Call OpenAI
            response = self.client.chat.completions.create(
                model="gpt-5-mini-2025-08-07",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in construction BOQ (Bill of Quantities) analysis. Your task is to identify exact matches and similar matches between construction items."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=1,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            if not result_text:
                logger.error("LLM returned empty response")
                return {'status': 'no_match', 'exact_matches': [], 'similar_matches': []}
            
            result = json.loads(result_text)
            
            # Log LLM reasoning
            logger.info(f"LLM Response - Status: {result.get('status', 'unknown')}")
            logger.info(f"LLM Response - Exact Matches: {result.get('exact_matches', [])}")
            logger.info(f"LLM Response - Similar Matches: {result.get('similar_matches', [])}")
            logger.info(f"LLM Response - Reasoning: {result.get('reasoning', 'N/A')}")
            
            logger.debug(f"LLM full response: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            return {'status': 'no_match', 'exact_matches': [], 'similar_matches': []}
    
    def _build_validation_prompt(
        self,
        target_description: str,
        target_code: str,
        candidates: List[Dict[str, Any]],
        parent: Optional[str] = None,
        grandparent: Optional[str] = None
    ) -> str:
        """Build prompt for LLM validation with hierarchical context."""
        
        code_info = f" (Code: {target_code})" if target_code else ""
        
        # Build target item info with hierarchy
        target_info = f"Description: {target_description}{code_info}"
        if parent:
            target_info = f"Parent: {parent}\n{target_info}"
        if grandparent:
            target_info = f"Grandparent: {grandparent}\n{target_info}"
        
        candidates_text = ""
        for i, cand in enumerate(candidates, 1):
            # Extract parent/grandparent from metadata if available
            cand_parent = cand.get('parent', '')
            cand_grandparent = cand.get('grandparent', '')
            
            cand_text = f"{i}. Description: {cand['description']}\n   Unit: {cand['unit']}"
            if cand_parent:
                cand_text += f"\n   Parent: {cand_parent}"
            if cand_grandparent:
                cand_text += f"\n   Grandparent: {cand_grandparent}"
            
            candidates_text += f"\n{cand_text}\n"
        
        prompt = f"""You are analyzing a construction BOQ (Bill of Quantities) item to find matches from a database.

TARGET ITEM TO MATCH:
{target_info}

CANDIDATE ITEMS (from vector search):
{candidates_text}

TASK:
Determine which candidates are EXACT MATCHES or SIMILAR MATCHES to the target item.

MATCH TYPES:

1. EXACT MATCH - Items are the same with identical specifications:
   - Same type of work, material, equipment, or activity
   - All critical specifications match (size, grade, rating, material, etc.)
   - Same scope of work
   - Compatible units
   - Wording variations OK if meaning is identical

2. SIMILAR MATCH - Items are very similar but not identical:
   - Same type of work/activity but with minor specification differences
   - Similar but not identical dimensions (e.g., DN200 vs DN250, but both HDPE pipes)
   - Similar grade/class (e.g., C30 vs C40 concrete, both concrete)
   - Similar scope with minor differences
   - Confidence level: 70-95% (you must provide confidence percentage)

MATCHING RULES:

SPECIFICATIONS:
- Exact specifications → EXACT MATCH
- Similar but different specifications (same category) → SIMILAR MATCH with confidence level
- Completely different specifications → NO MATCH

SCOPE:
- Identical scope → EXACT MATCH
- Similar scope with minor differences → SIMILAR MATCH
- Different scope (supply vs install) → NO MATCH

UNITS:
- Same or synonym units (m = m, m² = sqm) → Compatible
- Different units → Check if makes sense for SIMILAR MATCH

INTERPRETATION:
- Normalize abbreviations: No./nr/each; sqm/m²; cum/m³; DN = nominal diameter
- Consider if items could reasonably substitute each other → SIMILAR MATCH
- If critical details missing/unclear → NO MATCH

OUTPUT FORMAT (strict JSON):
{{
    "status": "exact_match" or "similar_match" or "no_match",
    "exact_matches": [1, 2],  // 1-based indices of exact matches (empty if none)
    "similar_matches": [
        {{"index": 3, "confidence": 85}},  // confidence must be 70-95%
        {{"index": 4, "confidence": 72}}
    ],
    "reasoning": "Explain which items are exact matches, which are similar (with confidence %), and why"
}}

EXAMPLES:
EXACT: "EXCAVATION depth 2m" = "Excavation 2m deep" (same work, same spec)
SIMILAR: "EXCAVATION depth 2m" ≈ "EXCAVATION depth 2.5m" (similar depth, 80% confidence)
NO MATCH: "EXCAVATION depth 2m" ≠ "BACKFILL depth 2m" (different work)

EXACT: "Concrete C40/20" = "C40/20 Concrete" (identical grade)
SIMILAR: "Concrete C40/20" ≈ "Concrete C30/20" (similar grade, 75% confidence)
NO MATCH: "Concrete C40" ≠ "Steel reinforcement" (different material)

EXACT: "HDPE Pipe DN200" = "200mm HDPE Pipe" (same pipe, same size)
SIMILAR: "HDPE Pipe DN200" ≈ "HDPE Pipe DN250" (same material, similar size, 82% confidence)
NO MATCH: "HDPE Pipe DN200" ≠ "PVC Pipe DN200" (different material)

Analyze carefully and return only valid JSON."""
        
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
