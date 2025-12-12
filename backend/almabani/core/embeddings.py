"""
Embeddings service using OpenAI API.
Generates vector embeddings from text with retry logic and batch processing.
Includes async helpers with RPM-aware throttling.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from almabani.config.settings import get_settings
from almabani.core.rate_limits import async_embedding_rate_limiter

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
        async_client: Optional[AsyncOpenAI] = None,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        batch_size: int = 500,
        max_workers: Optional[int] = None,
        async_rate_limiter=async_embedding_rate_limiter
    ):
        """
        Initialize embeddings service.
        
        Args:
            async_client: Async OpenAI client instance (optional)
            api_key: OpenAI API key (optional if async_client provided)
            model: Embedding model to use
            batch_size: Number of texts to process at once
            max_workers: Concurrency cap for async embedding calls (defaults to settings.max_workers)
        """
        settings = get_settings()
        if async_client:
            self.async_client = async_client
        else:
            key = api_key or settings.openai_api_key
            self.async_client = AsyncOpenAI(
                api_key=key,
                timeout=settings.openai_timeout,
                max_retries=settings.openai_max_retries
            )
        
        self.model = model
        self.batch_size = batch_size
        self.max_workers = max_workers if max_workers is not None else settings.max_workers
        self.async_rate_limiter = async_rate_limiter
        
        logger.info(f"Initialized embeddings service: {model}")
        logger.info(f"Dimensions: {self.get_dimensions()}, Batch size: {batch_size}")
        logger.info(f"Max workers: {self.max_workers}")
    
    def get_dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        return self.MODEL_INFO.get(self.model, {}).get('dimensions', 1536)
    
    def estimate_cost(self, num_items: int, avg_tokens_per_item: int = 13) -> Dict[str, float]:
        """
        Estimate cost for embedding items.
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
    
    async def generate_embedding_async(self, text: str) -> List[float]:
        """Async single embedding with RPM throttling."""
        await self.async_rate_limiter.acquire()
        response = await self.async_client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    async def generate_embedding(self, text: str) -> List[float]:
        """Backward-compatible wrapper for async embedding."""
        return await self.generate_embedding_async(text)
    
    async def generate_embeddings_batch(
        self,
        texts: List[str],
        retry_on_error: bool = True,
        max_retries: int = 3,
        max_workers: Optional[int] = None
    ) -> List[List[float]]:
        """
        Async variant of batch embedding with RPM-aware limiter.
        """
        embeddings: List[Optional[List[float]]] = [None] * len(texts)
        batches: List[List[str]] = [
            texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]
        if not batches:
            return []
        
        effective_workers = max(1, max_workers if max_workers is not None else self.max_workers)
        semaphore = asyncio.Semaphore(effective_workers)
        
        async def _embed_batch(batch_idx: int, batch: List[str]) -> None:
            for attempt in range(max_retries):
                try:
                    await self.async_rate_limiter.acquire()
                    response = await self.async_client.embeddings.create(
                        model=self.model,
                        input=batch
                    )
                    start = batch_idx * self.batch_size
                    for offset, item in enumerate(response.data):
                        embeddings[start + offset] = item.embedding
                    return
                except Exception as e:
                    if attempt < max_retries - 1 and retry_on_error:
                        wait_time = 2 ** attempt
                        logger.warning(f"[async] API error, retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[async] Failed to generate embeddings for batch: {e}")
                        raise
        
        tasks = []
        for idx, batch in enumerate(batches):
            async def bound_embed(batch_idx=idx, b=batch):
                async with semaphore:
                    await _embed_batch(batch_idx, b)
            tasks.append(bound_embed())
        
        await asyncio.gather(*tasks)
        if any(e is None for e in embeddings):
            raise ValueError("Embedding generation incomplete in async_generate_embeddings_batch")
        return embeddings  # type: ignore
    
    async def embed_items(
        self,
        items: List[Dict[str, Any]],
        text_field: str = 'text',
        max_workers: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Add embeddings to items (async only).
        """
        logger.info(f"[async] Embedding {len(items)} items...")
        cost_info = self.estimate_cost(len(items))
        logger.info(f"[async] Estimated cost: ${cost_info['estimated_cost_usd']} USD")
        logger.info(f"[async] Estimated tokens: {cost_info['estimated_tokens']:,}")
        
        texts = [item.get(text_field, '') for item in items]
        embeddings = await self.generate_embeddings_batch(
            texts,
            max_workers=max_workers
        )
        
        items_with_embeddings = []
        for item, embedding in zip(items, embeddings):
            item_copy = item.copy()
            item_copy['embedding'] = embedding
            items_with_embeddings.append(item_copy)
        
        logger.info(f"[async] Successfully embedded {len(items_with_embeddings)} items")
        return items_with_embeddings
