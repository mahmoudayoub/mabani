"""
Embeddings service using OpenAI API.
Generates vector embeddings from text with retry logic and batch processing.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from openai import OpenAI
import time

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """Generate embeddings using OpenAI API with retry logic and batching."""
    
    # Model information
    MODEL_INFO = {
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
    
    def __init__(
        self,
        client: Optional[OpenAI] = None,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        batch_size: int = 500,
        max_workers: int = 5
    ):
        """
        Initialize embeddings service.
        
        Args:
            client: OpenAI client instance (if None, creates from api_key)
            api_key: OpenAI API key (if None, must provide client)
            model: Embedding model to use
            batch_size: Number of texts to process at once
            max_workers: Number of threads for parallel embedding calls
        """
        if client:
            self.client = client
        elif api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError("Must provide either client or api_key")
        
        self.model = model
        self.batch_size = batch_size
        self.max_workers = max_workers
        
        logger.info(f"Initialized embeddings service: {model}")
        logger.info(f"Dimensions: {self.get_dimensions()}, Batch size: {batch_size}")
        logger.info(f"Max workers: {max_workers}")
    
    def get_dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        return self.MODEL_INFO.get(self.model, {}).get('dimensions', 1536)
    
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
        cost_per_1k = self.MODEL_INFO.get(self.model, {}).get('cost_per_1k', 0.00002)
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
        retry_on_error: bool = True,
        max_retries: int = 3,
        max_workers: Optional[int] = None
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches using a thread pool.
        
        Args:
            texts: List of texts to embed
            retry_on_error: Retry on API errors
            max_retries: Maximum retry attempts
            max_workers: Override default worker count
            
        Returns:
            List of embedding vectors
        """
        embeddings: List[List[float]] = []
        
        batches: List[List[str]] = [
            texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]
        
        if not batches:
            return embeddings
        
        effective_workers = max_workers if max_workers is not None else self.max_workers
        effective_workers = max(1, effective_workers)
        
        def _embed_batch(batch: List[str]) -> List[List[float]]:
            for attempt in range(max_retries):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch
                    )
                    return [item.embedding for item in response.data]
                except Exception as e:
                    if attempt < max_retries - 1 and retry_on_error:
                        wait_time = 2 ** attempt
                        logger.warning(f"API error, retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Failed to generate embeddings for batch: {e}")
                        raise
            return []
        
        batch_results: List[Optional[List[List[float]]]] = [None] * len(batches)
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_idx = {
                executor.submit(_embed_batch, batch): idx
                for idx, batch in enumerate(batches)
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                batch_results[idx] = future.result()
        
        for batch_embedding in batch_results:
            if batch_embedding:
                embeddings.extend(batch_embedding)
        
        return embeddings
    
    def embed_items(
        self,
        items: List[Dict[str, Any]],
        text_field: str = 'text',
        max_workers: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Add embeddings to items.
        
        Args:
            items: List of items with text field
            text_field: Name of field containing text to embed
            max_workers: Override default worker count for embedding threads
            
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
        embeddings = self.generate_embeddings_batch(
            texts,
            max_workers=max_workers
        )
        
        # Add embeddings to items
        items_with_embeddings = []
        for item, embedding in zip(items, embeddings):
            item_copy = item.copy()
            item_copy['embedding'] = embedding
            items_with_embeddings.append(item_copy)
        
        logger.info(f"Successfully embedded {len(items_with_embeddings)} items")
        
        return items_with_embeddings
