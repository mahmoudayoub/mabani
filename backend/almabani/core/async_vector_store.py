"""
Async Vector Store Service for Pinecone.

Uses native PineconeAsyncio and IndexAsyncio for true async operations.
"""

import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import os

logger = logging.getLogger(__name__)


class AsyncVectorStoreService:
    """
    Native async Pinecone service using PineconeAsyncio.
    
    Usage:
        async with AsyncVectorStoreService(api_key=key, index_name=name) as service:
            results = await service.query(embedding, top_k=20)
            await service.upsert(vectors)
    """
    
    def __init__(
        self,
        api_key: str,
        index_name: str = 'almabani-pricecode',
        environment: str = 'us-east-1'
    ):
        self.api_key = api_key
        self.index_name = index_name
        self.environment = environment
        self._pc = None
        self._index = None
    
    async def __aenter__(self):
        """Async context manager entry - initialize async client."""
        from pinecone import PineconeAsyncio
        
        self._pc = PineconeAsyncio(api_key=self.api_key)
        self._index = self._pc.Index(self.index_name)
        logger.info(f"Connected to async Pinecone index: {self.index_name}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup."""
        if self._pc:
            await self._pc.close()
            self._pc = None
            self._index = None
        return False
    
    async def query(
        self,
        vector: List[float],
        top_k: int = 20,
        namespace: str = "",
        include_metadata: bool = True,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query vectors using native async.
        
        Returns list of matches with id, score, metadata.
        """
        if not self._index:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")
        
        results = await self._index.query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
            filter=filter_dict
        )
        
        matches = []
        for match in results.matches:
            matches.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {}
            })
        
        return matches
    
    async def upsert(
        self,
        vectors: List[Dict[str, Any]],
        namespace: str = "",
        batch_size: int = 100
    ) -> int:
        """
        Upsert vectors using native async.
        
        Args:
            vectors: List of dicts with 'id', 'values', 'metadata'
            namespace: Target namespace
            batch_size: Batch size for upserts
            
        Returns: Number of vectors upserted
        """
        if not self._index:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")
        
        count = 0
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            await self._index.upsert(vectors=batch, namespace=namespace)
            count += len(batch)
            logger.debug(f"Upserted batch {i//batch_size + 1}: {len(batch)} vectors")
        
        return count
    
    async def describe_index_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self._index:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")
        
        stats = await self._index.describe_index_stats()
        return {
            "total_vector_count": stats.total_vector_count,
            "dimension": stats.dimension,
            "namespaces": stats.namespaces
        }


@asynccontextmanager
async def get_async_vector_store(
    index_name: str = None
):
    """
    Convenience async context manager for getting vector store.
    
    Usage:
        async with get_async_vector_store('almabani-pricecode') as service:
            results = await service.query(embedding)
    """
    from almabani.config.settings import get_settings
    settings = get_settings()
    
    if index_name is None:
        index_name = os.getenv('PRICECODE_INDEX_NAME', 'almabani-pricecode')
    
    async with AsyncVectorStoreService(
        api_key=settings.pinecone_api_key,
        index_name=index_name,
        environment=settings.pinecone_environment
    ) as service:
        yield service
