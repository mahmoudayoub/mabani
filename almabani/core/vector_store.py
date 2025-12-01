"""
Vector store service using Pinecone.
Handles index management, uploading, and querying.
Includes async helpers (uses asyncio.to_thread for Pinecone ops).
"""
import asyncio
import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Manage Pinecone vector store operations."""
    
    def __init__(
        self,
        client: Optional[Pinecone] = None,
        api_key: Optional[str] = None,
        index_name: str = 'almabani',
        environment: str = 'us-east-1'
    ):
        """
        Initialize vector store service.
        
        Args:
            client: Pinecone client instance (if None, creates from api_key)
            api_key: Pinecone API key (if None, must provide client)
            index_name: Name of the index to use/create
            environment: Pinecone environment/region
        """
        if client:
            self.pc = client
        elif api_key:
            self.pc = Pinecone(api_key=api_key)
        else:
            raise ValueError("Must provide either client or api_key")
        
        self.index_name = index_name
        self.environment = environment
        self.index = None
        
        logger.info(f"Initialized vector store service")
        logger.info(f"Environment: {environment}, Index: {index_name}")
    
    @staticmethod
    def sanitize_id(id_str: str) -> str:
        """
        Sanitize vector ID to contain only ASCII characters.
        Pinecone requires vector IDs to be ASCII-only.
        
        Args:
            id_str: Original ID string
            
        Returns:
            ASCII-safe ID string
        """
        # Normalize Unicode (decompose accented characters)
        normalized = unicodedata.normalize('NFKD', id_str)
        
        # Remove combining marks (accents)
        ascii_str = ''.join(c for c in normalized if not unicodedata.combining(c))
        
        # Replace any remaining non-ASCII characters with underscore
        ascii_str = ascii_str.encode('ascii', 'replace').decode('ascii')
        ascii_str = ascii_str.replace('?', '_')
        
        # Clean up multiple consecutive underscores
        ascii_str = re.sub(r'_+', '_', ascii_str)
        
        return ascii_str
    
    async def create_index(
        self,
        dimension: int = 1536,
        metric: str = 'cosine',
        cloud: str = 'aws',
        region: Optional[str] = None
    ):
        """
        Create a new Pinecone index (async wrapper).
        """
        if region is None:
            region = self.environment
        
        existing_indexes = await asyncio.to_thread(self.pc.list_indexes)
        index_names = [idx.name for idx in existing_indexes]
        
        if self.index_name in index_names:
            logger.info(f"Index '{self.index_name}' already exists")
            self.index = self.pc.Index(self.index_name)
            stats = await asyncio.to_thread(self.index.describe_index_stats)
            logger.info(f"Current index stats: {stats.get('total_vector_count', 0)} vectors")
            return
        
        logger.info(f"Creating new index '{self.index_name}'...")
        logger.info(f"Dimension: {dimension}, Metric: {metric}")
        
        await asyncio.to_thread(
            self.pc.create_index,
            name=self.index_name,
            dimension=dimension,
            metric=metric,
            spec=ServerlessSpec(
                cloud=cloud,
                region=region
            )
        )
        
        logger.info("Waiting for index to be ready...")
        while True:
            ready = await asyncio.to_thread(
                lambda: self.pc.describe_index(self.index_name).status['ready']
            )
            if ready:
                break
            await asyncio.sleep(1)
        
        self.index = self.pc.Index(self.index_name)
        logger.info(f"Index '{self.index_name}' created successfully")
    
    def get_index(self):
        """Get or initialize index connection."""
        if not self.index:
            self.index = self.pc.Index(self.index_name)
        return self.index
    
    def prepare_vectors(
        self,
        items: List[Dict[str, Any]],
        id_field: str = 'id',
        embedding_field: str = 'embedding',
        text_field: str = 'text',
        metadata_field: str = 'metadata'
    ) -> List[tuple]:
        """
        Prepare items for Pinecone upload.
        
        Args:
            items: List of items with embeddings
            id_field: Field containing unique ID
            embedding_field: Field containing embedding vector
            text_field: Field containing original text
            metadata_field: Field containing metadata dict
            
        Returns:
            List of (id, embedding, metadata) tuples
        """
        vectors = []
        
        for item in items:
            # Get original ID and sanitize it for Pinecone
            original_id = str(item.get(id_field, ''))
            item_id = self.sanitize_id(original_id)
            
            embedding = item.get(embedding_field, [])
            
            # Build metadata (include text for retrieval)
            metadata = item.get(metadata_field, {}).copy()
            metadata['text'] = item.get(text_field, '')
            
            # Store original ID in metadata if it was changed
            if original_id != item_id:
                metadata['original_id'] = original_id
            
            # Pinecone metadata limits: values must be strings, numbers, or booleans
            # Convert any complex types to strings
            clean_metadata = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_metadata[key] = value
                elif value is None:
                    continue
                else:
                    clean_metadata[key] = str(value)
            
            vectors.append((item_id, embedding, clean_metadata))
        
        return vectors
    
    async def upload_vectors(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = 300,
        namespace: str = '',
        max_workers: int = 100
    ) -> Dict[str, Any]:
        """
        Async upload using asyncio.to_thread for Pinecone calls.
        """
        index = self.get_index()
        logger.info(f"[async] Preparing {len(items)} vectors for upload...")
        vectors = self.prepare_vectors(items)
        logger.info(f"[async] Uploading {len(vectors)} vectors to Pinecone...")
        batches = [vectors[i:i + batch_size] for i in range(0, len(vectors), batch_size)]
        semaphore = asyncio.Semaphore(max(1, max_workers))
        
        async def _upsert_batch(batch):
            async with semaphore:
                await asyncio.to_thread(index.upsert, vectors=batch, namespace=namespace)
                return len(batch)
        
        uploaded_counts = await asyncio.gather(*[_upsert_batch(batch) for batch in batches])
        uploaded_count = sum(uploaded_counts)
        
        stats = await asyncio.to_thread(index.describe_index_stats)
        result = {
            'uploaded_count': uploaded_count,
            'total_vectors_in_index': stats.get('total_vector_count', 0),
            'index_name': self.index_name,
            'namespace': namespace
        }
        
        logger.info(f"[async] Upload complete! {uploaded_count} vectors uploaded")
        logger.info(f"[async] Total vectors in index: {result['total_vectors_in_index']}")
        return result
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        namespace: str = '',
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors (async wrapper over Pinecone client).
        """
        index = self.get_index()
        results = await asyncio.to_thread(
            index.query,
            vector=query_embedding,
            top_k=top_k,
            filter=filter_dict,
            namespace=namespace,
            include_metadata=include_metadata
        )
        
        matches = []
        result_matches = results.matches if hasattr(results, 'matches') else results.get('matches', [])
        
        for match in result_matches:
            match_id = match.id if hasattr(match, 'id') else match.get('id')
            match_score = match.score if hasattr(match, 'score') else match.get('score')
            match_metadata = match.metadata if hasattr(match, 'metadata') else match.get('metadata', {})
            
            matches.append({
                'id': match_id,
                'score': match_score,
                'text': match_metadata.get('text', ''),
                'metadata': match_metadata
            })
        
        return matches
    
    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace."""
        index = self.get_index()
        logger.warning(f"Deleting namespace '{namespace}'...")
        index.delete(delete_all=True, namespace=namespace)
        logger.info(f"Namespace '{namespace}' deleted")
    
    def delete_index(self):
        """Delete the index (use with caution!)."""
        logger.warning(f"Deleting index '{self.index_name}'...")
        self.pc.delete_index(self.index_name)
        self.index = None
        logger.info(f"Index '{self.index_name}' deleted")
    
    def get_stats(self, namespace: str = '') -> Dict[str, Any]:
        """Get index statistics."""
        index = self.get_index()
        stats = index.describe_index_stats()
        
        return {
            'total_vectors': stats.get('total_vector_count', 0),
            'dimension': stats.get('dimension', 0),
            'index_name': self.index_name,
            'namespace': namespace
        }
