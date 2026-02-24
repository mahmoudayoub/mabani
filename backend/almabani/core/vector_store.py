"""
Vector store service using OpenSearch Serverless.
Handles index management, uploading, and querying.
Matches the original Pinecone interface for backward compatibility.
"""
import asyncio
import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional

import boto3
from opensearchpy import AsyncOpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Manage OpenSearch Serverless vector store operations."""
    
    def __init__(
        self,
        endpoint: str,
        region: str = 'eu-west-1', # Default to regional setup
        index_name: str = 'almabani'
    ):
        """
        Initialize vector store service.
        
        Args:
            endpoint: OpenSearch collection endpoint (e.g., https://xyz.region.aoss.amazonaws.com)
            region: AWS region
            index_name: Name of the index to use/create
        """
        if not endpoint:
            raise ValueError("Must provide OpenSearch endpoint")
            
        # Clean up endpoint if it has no protocol
        if not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"
            
        self.endpoint = endpoint
        self.region = region
        self.index_name = index_name
        self.client = None
        
        logger.info(f"Initialized OpenSearch vector store service")
        logger.info(f"Endpoint: {endpoint}, Index: {index_name}")
    
    @staticmethod
    def sanitize_id(id_str: str) -> str:
        """
        Sanitize document ID.
        OpenSearch is more permissive than Pinecone, but keeping this
        for backward compatibility.
        """
        normalized = unicodedata.normalize('NFKD', id_str)
        ascii_str = ''.join(c for c in normalized if not unicodedata.combining(c))
        ascii_str = ascii_str.encode('ascii', 'replace').decode('ascii')
        ascii_str = ascii_str.replace('?', '_')
        ascii_str = re.sub(r'_+', '_', ascii_str)
        return ascii_str
        
    def get_client(self) -> AsyncOpenSearch:
        """Initialize the OpenSearch client with AWS Auth."""
        if self.client is not None:
            return self.client
            
        credentials = boto3.Session().get_credentials()
        # Ensure we use the proper service name 'aoss' for Serverless OpenSearch
        auth = AWSV4SignerAuth(credentials, self.region, "aoss")
        
        self.client = AsyncOpenSearch(
            hosts=[self.endpoint],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20
        )
        return self.client
        
    def _get_target_index(self, namespace: str) -> str:
        """
        Map Pinecone namespace to OpenSearch index name.
        If namespace is provided, append it to the base index name.
        """
        if namespace:
            # OpenSearch index names must be lowercase and have no spaces
            clean_ns = namespace.lower().replace(" ", "-")
            return f"{self.index_name}-{clean_ns}"
        return self.index_name
    
    async def create_index(
        self,
        dimension: int = 1536,
        metric: str = 'cosine',
        cloud: str = 'aws',
        region: Optional[str] = None
    ):
        """
        Create a new OpenSearch index with kNN mapping.
        """
        client = self.get_client()
        
        # In this implementation, we map Pinecone 'namespaces' to actual indices 
        # when upload/search happens, but we create the default/base index here.
        index_name = self.index_name
        
        exists = await client.indices.exists(index=index_name)
        if exists:
            logger.info(f"Index '{index_name}' already exists")
            stats = await client.count(index=index_name)
            logger.info(f"Current index stats: {stats.get('count', 0)} vectors")
            return
            
        logger.info(f"Creating new index '{index_name}'...")
        logger.info(f"Dimension: {dimension}, Metric: {metric}")
        
        # Map metric parameter (Pinecone 'cosine' -> OS 'cosinesimil')
        space_type = 'cosinesimil'
        if metric == 'euclidean':
            space_type = 'l2'
        elif metric == 'dotproduct':
            space_type = 'innerproduct'
            
        # Define settings and mapping for kNN
        body = {
            "settings": {
                "index.knn": True
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": dimension,
                        "method": {
                            "engine": "faiss",
                            "name": "hnsw",
                            "space_type": space_type
                        }
                    },
                    "text": { "type": "text" }
                }
            }
        }
        
        await client.indices.create(index=index_name, body=body)
        logger.info(f"Index '{index_name}' created successfully")
    
    def prepare_vectors(
        self,
        items: List[Dict[str, Any]],
        id_field: str = 'id',
        embedding_field: str = 'embedding',
        text_field: str = 'text',
        metadata_field: str = 'metadata'
    ) -> List[tuple]:
        """Keep identical exact signature as Pinecone implementation."""
        vectors = []
        for item in items:
            original_id = str(item.get(id_field, ''))
            item_id = self.sanitize_id(original_id)
            embedding = item.get(embedding_field, [])
            
            metadata = item.get(metadata_field, {}).copy()
            metadata['text'] = item.get(text_field, '')
            if original_id != item_id:
                metadata['original_id'] = original_id
                
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
        max_workers: int = 200
    ) -> Dict[str, Any]:
        """
        Upload documents to OpenSearch Serverless using the bulk API.
        """
        client = self.get_client()
        target_index = self._get_target_index(namespace)
        
        # Ensure index exists before uploading (for namespaces acting as indexes)
        if target_index != self.index_name:
            if not await client.indices.exists(index=target_index):
                logger.info(f"[async] Auto-creating sub-index/namespace: {target_index}")
                await self._create_sub_index(client, target_index)

        logger.info(f"[async] Preparing {len(items)} vectors for upload...")
        vectors = self.prepare_vectors(items)
        logger.info(f"[async] Uploading {len(vectors)} vectors to OpenSearch ({target_index})...")
        
        from opensearchpy.helpers.async_actions import async_bulk
        
        # Format for OpenSearch bulk API
        actions = []
        for vec_id, embedding, metadata in vectors:
            doc = metadata.copy()
            doc['embedding'] = embedding
            
            action = {
                "_index": target_index,
                "_id": vec_id,
                "_source": doc
            }
            actions.append(action)
            
        success, _ = await async_bulk(client, actions, chunk_size=batch_size)
        
        # Wait a moment for Near-Real-Time indexing to settle
        await asyncio.sleep(2)
        
        stats = await client.count(index=target_index)
        result = {
            'uploaded_count': success,
            'total_vectors_in_index': stats.get('count', 0),
            'index_name': self.index_name,
            'namespace': namespace
        }
        
        logger.info(f"[async] Upload complete! {success} vectors uploaded")
        logger.info(f"[async] Total vectors in index: {result['total_vectors_in_index']}")
        return result
        
    async def _create_sub_index(self, client, target_index: str, dimension: int = 1536):
        """Helper to create sub-indexes with the proper mapping on demand."""
        try:
            body = {
                "settings": {"index.knn": True},
                "mappings": {
                    "properties": {
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": dimension,
                            "method": {
                                "engine": "faiss",
                                "name": "hnsw",
                                "space_type": "cosinesimil"
                            }
                        },
                        "text": { "type": "text" }
                    }
                }
            }
            await client.indices.create(index=target_index, body=body)
        except Exception as e:
            logger.warning(f"Error creating sub-index (might already exist): {e}")
    
    def _convert_pinecone_filter(self, filter_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Pinecone mongo-like filter syntax to OpenSearch query DSL.
        Example Pinecone: {"sheet_name": {"$in": ["MEP", "Civil"]}}
        Equivalent OS: {"terms": {"sheet_name": ["MEP", "Civil"]}}
        """
        if not filter_dict:
            return {}
            
        must_clauses = []
        for field, condition in filter_dict.items():
            if isinstance(condition, dict):
                for op, val in condition.items():
                    if op == "$in":
                        must_clauses.append({"terms": {field: val}})
                    elif op == "$eq":
                        must_clauses.append({"term": {field: val}})
            elif isinstance(condition, str) or isinstance(condition, int):
                # Implicit equality
                must_clauses.append({"term": {field: condition}})
                
        return {"bool": {"must": must_clauses}} if must_clauses else {}
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        namespace: str = '',
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in OpenSearch.
        Matches Pinecone's exact return dictionary structure.
        """
        client = self.get_client()
        target_index = self._get_target_index(namespace)
        
        try:
            # Check if index exists to prevent 404 errors during search
            if not await client.indices.exists(index=target_index):
                logger.warning(f"Cannot search: Index {target_index} does not exist yet")
                return []
                
            query = {
                "size": top_k,
                "_source": include_metadata,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": query_embedding,
                            "k": top_k
                        }
                    }
                }
            }
            
            # Apply metadata filtering if provided
            os_filter = self._convert_pinecone_filter(filter_dict)
            if os_filter:
                query["query"]["knn"]["embedding"]["filter"] = os_filter
                
            response = await client.search(index=target_index, body=query)
            
            matches = []
            hits = response.get('hits', {}).get('hits', [])
            
            for hit in hits:
                source = hit.get('_source', {})
                # OS returns score differently (typically 1.0 + something, we extract original metric)
                # But we just pass the raw score it gives us.
                
                # Separate system fields from metadata
                metadata = {k: v for k, v in source.items() if k != 'embedding'}
                
                matches.append({
                    'id': hit.get('_id'),
                    'score': hit.get('_score', 0.0),
                    'text': metadata.get('text', ''),
                    'metadata': metadata
                })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error executing search against {target_index}: {str(e)}")
            return []
    
    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace."""
        logger.warning(f"Deleting namespace '{namespace}'...")
        target_index = self._get_target_index(namespace)
        
        # We need to run sync from async (or just wrap in a loop to match original sync signature)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._delete_namespace_async(target_index, namespace))
            else:
                loop.run_until_complete(self._delete_namespace_async(target_index, namespace))
        except Exception as e:
            logger.error(f"Error running delete_namespace: {e}")
            
    async def _delete_namespace_async(self, target_index: str, namespace: str):
        client = self.get_client()
        exists = await client.indices.exists(index=target_index)
        if not exists:
            return
            
        if target_index != self.index_name:
            # If it's a dedicated sub-index, just delete the index
            await client.indices.delete(index=target_index)
        else:
            # If it's the main index (empty namespace), delete all docs
            await client.delete_by_query(
                index=target_index,
                body={"query": {"match_all": {}}}
            )
        logger.info(f"Namespace '{namespace}' deleted")
    
    def delete_index(self):
        """Delete the base index."""
        logger.warning(f"Deleting index '{self.index_name}'...")
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._delete_index_async())
            else:
                loop.run_until_complete(self._delete_index_async())
        except Exception as e:
            logger.error(f"Error running delete_index: {e}")
            
    async def _delete_index_async(self):
        client = self.get_client()
        exists = await client.indices.exists(index=self.index_name)
        if exists:
            await client.indices.delete(index=self.index_name)
        self.client = None
        logger.info(f"Index '{self.index_name}' deleted")
    
    def get_stats(self, namespace: str = '') -> Dict[str, Any]:
        """Get index statistics."""
        target_index = self._get_target_index(namespace)
        stats = {'total_vectors': 0, 'dimension': 0}
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We can't block easily here if returning a dict right away.
                # Usually get_stats is called via CLI which isn't already running a loop 
                # or from a sync endpoint.
                pass 
            else:
                count_resp = loop.run_until_complete(self._get_stats_async(target_index))
                stats['total_vectors'] = count_resp
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
        
        return {
            'total_vectors': stats['total_vectors'],
            'dimension': 1536,
            'index_name': self.index_name,
            'namespace': namespace
        }
        
    async def _get_stats_async(self, target_index: str) -> int:
        client = self.get_client()
        if await client.indices.exists(index=target_index):
            resp = await client.count(index=target_index)
            return resp.get('count', 0)
        return 0
