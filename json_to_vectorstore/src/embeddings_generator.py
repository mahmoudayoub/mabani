"""
OpenAI Embeddings Generator
Generates vector embeddings from text using OpenAI's API.
"""
import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from tqdm import tqdm
import time

logger = logging.getLogger(__name__)


class EmbeddingsGenerator:
    """Generate embeddings using OpenAI API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        batch_size: int = 100
    ):
        """
        Initialize embeddings generator.
        
        Args:
            api_key: OpenAI API key (if None, reads from env)
            model: Embedding model to use
            batch_size: Number of texts to process at once
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not provided and not found in environment")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.batch_size = batch_size
        
        # Model info
        self.model_info = {
            'text-embedding-3-small': {
                'dimensions': 1536,
                'max_tokens': 8191,
                'cost_per_1k': 0.00002  # $0.02 per 1M tokens
            },
            'text-embedding-3-large': {
                'dimensions': 3072,
                'max_tokens': 8191,
                'cost_per_1k': 0.00013  # $0.13 per 1M tokens
            },
            'text-embedding-ada-002': {
                'dimensions': 1536,
                'max_tokens': 8191,
                'cost_per_1k': 0.0001  # $0.10 per 1M tokens
            }
        }
        
        logger.info(f"Initialized OpenAI embeddings with model: {model}")
        logger.info(f"Dimensions: {self.get_dimensions()}, Batch size: {batch_size}")
    
    def get_dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        return self.model_info.get(self.model, {}).get('dimensions', 1536)
    
    def estimate_cost(self, num_items: int, avg_tokens_per_item: int = 13) -> Dict[str, float]:
        """
        Estimate cost for embedding items.
        
        Args:
            num_items: Number of items to embed
            avg_tokens_per_item: Average tokens per item
            
        Returns:
            Dictionary with cost estimates
        """
        total_tokens = num_items * avg_tokens_per_item
        cost_per_1k = self.model_info.get(self.model, {}).get('cost_per_1k', 0.00002)
        total_cost = (total_tokens / 1000) * cost_per_1k
        
        return {
            'total_items': num_items,
            'estimated_tokens': total_tokens,
            'cost_per_1k_tokens': cost_per_1k,
            'estimated_cost_usd': round(total_cost, 4)
        }
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector)
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        show_progress: bool = True,
        retry_on_error: bool = True,
        max_retries: int = 3
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            show_progress: Show progress bar
            retry_on_error: Retry on API errors
            max_retries: Maximum retry attempts
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        # Process in batches
        iterator = range(0, len(texts), self.batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Generating embeddings", unit="batch")
        
        for i in iterator:
            batch = texts[i:i + self.batch_size]
            
            # Retry logic
            for attempt in range(max_retries):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch
                    )
                    
                    # Extract embeddings in order
                    batch_embeddings = [item.embedding for item in response.data]
                    embeddings.extend(batch_embeddings)
                    break
                    
                except Exception as e:
                    if attempt < max_retries - 1 and retry_on_error:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"API error, retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Failed to generate embeddings for batch: {e}")
                        raise
        
        return embeddings
    
    def embed_items(
        self,
        items: List[Dict[str, Any]],
        text_field: str = 'text',
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Add embeddings to items.
        
        Args:
            items: List of items with text field
            text_field: Name of field containing text to embed
            show_progress: Show progress bar
            
        Returns:
            Items with 'embedding' field added
        """
        logger.info(f"Embedding {len(items)} items...")
        
        # Show cost estimate
        cost_info = self.estimate_cost(len(items))
        logger.info(f"Estimated cost: ${cost_info['estimated_cost_usd']} USD")
        logger.info(f"Estimated tokens: {cost_info['estimated_tokens']:,}")
        
        # Extract texts
        texts = [item.get(text_field, '') for item in items]
        
        # Generate embeddings
        embeddings = self.generate_embeddings_batch(texts, show_progress=show_progress)
        
        # Add embeddings to items
        items_with_embeddings = []
        for item, embedding in zip(items, embeddings):
            item_copy = item.copy()
            item_copy['embedding'] = embedding
            items_with_embeddings.append(item_copy)
        
        logger.info(f"Successfully embedded {len(items_with_embeddings)} items")
        
        return items_with_embeddings
