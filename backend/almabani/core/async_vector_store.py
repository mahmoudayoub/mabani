"""
Async vector store wrapper for S3 Vectors.
Provides a context manager interface used by the pricecode pipeline.
"""
import os
from contextlib import asynccontextmanager
from almabani.core.vector_store import VectorStoreService


class AsyncVectorStore:
    """
    Async wrapper around VectorStoreService.
    
    Provides the query() and upload_vectors() interface
    expected by the pricecode pipeline.
    """
    
    def __init__(self, service: VectorStoreService):
        self._service = service
    
    async def query(
        self,
        vector,
        top_k: int = 10,
        namespace: str = '',
        include_metadata: bool = True,
        filter_dict=None
    ):
        """
        Query vectors by similarity.
        Delegates to VectorStoreService.search().
        """
        return await self._service.search(
            query_embedding=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata,
            filter_dict=filter_dict
        )
    
    async def upload_vectors(self, items, batch_size=50, namespace='', max_workers=200):
        """Upload vectors. Delegates to VectorStoreService.upload_vectors()."""
        return await self._service.upload_vectors(
            items=items,
            batch_size=batch_size,
            namespace=namespace,
            max_workers=max_workers
        )


@asynccontextmanager
async def get_async_vector_store(index_name: str = None):
    """
    Async context manager that yields an AsyncVectorStore instance.
    
    Usage:
        async with get_async_vector_store() as vs:
            results = await vs.query(vector=embedding, top_k=20)
    """
    bucket_name = os.environ.get('S3_VECTORS_BUCKET', 'almabani-vectors')
    region = os.environ.get('AWS_REGION', 'eu-west-1')
    
    if index_name is None:
        index_name = os.environ.get('PRICECODE_INDEX_NAME', 'almabani-pricecode')
    
    service = VectorStoreService(
        bucket_name=bucket_name,
        region=region,
        index_name=index_name
    )
    
    yield AsyncVectorStore(service)
