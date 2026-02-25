"""
Vector store service using Amazon S3 Vectors.
Handles index management, uploading, and querying.
Replaces the previous OpenSearch Serverless implementation for cost savings.
"""
import asyncio
import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional

import boto3

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Manage S3 Vectors vector store operations."""
    
    def __init__(
        self,
        bucket_name: str,
        region: str = 'eu-west-1',
        index_name: str = 'almabani'
    ):
        """
        Initialize vector store service.
        
        Args:
            bucket_name: S3 Vectors bucket name
            region: AWS region
            index_name: Name of the vector index
        """
        if not bucket_name:
            raise ValueError("Must provide S3 Vectors bucket name")
            
        self.bucket_name = bucket_name
        self.region = region
        self.index_name = index_name
        self._client = None
        
        logger.info(f"Initialized S3 Vectors store service")
        logger.info(f"Bucket: {bucket_name}, Index: {index_name}")
    
    @staticmethod
    def sanitize_id(id_str: str) -> str:
        """
        Sanitize document ID / vector key.
        S3 Vectors keys must be unique within an index.
        """
        normalized = unicodedata.normalize('NFKD', id_str)
        ascii_str = ''.join(c for c in normalized if not unicodedata.combining(c))
        ascii_str = ascii_str.encode('ascii', 'replace').decode('ascii')
        ascii_str = ascii_str.replace('?', '_')
        ascii_str = re.sub(r'_+', '_', ascii_str)
        return ascii_str
        
    def get_client(self):
        """Get the S3 Vectors boto3 client."""
        if self._client is not None:
            return self._client
        self._client = boto3.client('s3vectors', region_name=self.region)
        return self._client
    
    def _get_target_index(self, namespace: str) -> str:
        """
        Map namespace to index name.
        If namespace is provided, append it to the base index name.
        """
        if namespace:
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
        Create a new S3 Vectors index.
        Will also create the vector bucket if it doesn't exist.
        """
        client = self.get_client()
        
        # 1. Create the vector bucket (idempotent)
        try:
            await asyncio.to_thread(
                client.create_vector_bucket,
                vectorBucketName=self.bucket_name
            )
            logger.info(f"Vector bucket '{self.bucket_name}' created (or already exists)")
        except client.exceptions.ConflictException:
            logger.info(f"Vector bucket '{self.bucket_name}' already exists")
        except Exception as e:
            if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
                logger.info(f"Vector bucket '{self.bucket_name}' already exists")
            else:
                raise
        
        # 2. Create the vector index
        # Map metric name
        distance_metric = 'cosine'
        if metric == 'euclidean' or metric == 'l2':
            distance_metric = 'euclidean'
            
        try:
            await asyncio.to_thread(
                client.create_index,
                vectorBucketName=self.bucket_name,
                indexName=self.index_name,
                dimension=dimension,
                distanceMetric=distance_metric,
                dataType='float32',
                metadataConfiguration={
                    'nonFilterableMetadataKeys': ['text', 'original_id', 'pinecone_namespace']
                }
            )
            logger.info(f"Index '{self.index_name}' created successfully")
        except client.exceptions.ConflictException:
            logger.info(f"Index '{self.index_name}' already exists")
        except Exception as e:
            if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
                logger.info(f"Index '{self.index_name}' already exists")
            else:
                raise
    
    def prepare_vectors(
        self,
        items: List[Dict[str, Any]],
        id_field: str = 'id',
        embedding_field: str = 'embedding',
        text_field: str = 'text',
        metadata_field: str = 'metadata'
    ) -> List[tuple]:
        """Keep identical exact signature as previous implementation."""
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
        batch_size: int = 50,
        namespace: str = '',
        max_workers: int = 200
    ) -> Dict[str, Any]:
        """
        Upload documents to S3 Vectors using put_vectors.
        S3 Vectors put_vectors has a limit on payload size,
        so we batch into smaller chunks.
        """
        client = self.get_client()
        target_index = self._get_target_index(namespace)
        
        # Ensure index exists for namespaces
        if target_index != self.index_name:
            await self._ensure_index(target_index)

        logger.info(f"[async] Preparing {len(items)} vectors for upload...")
        vectors = self.prepare_vectors(items)
        logger.info(f"[async] Uploading {len(vectors)} vectors to S3 Vectors ({target_index})...")
        
        success_count = 0
        
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            
            s3_vectors = []
            for vec_id, embedding, metadata in batch:
                s3_vectors.append({
                    'key': vec_id,
                    'data': {'float32': embedding},
                    'metadata': metadata
                })
            
            try:
                await asyncio.to_thread(
                    client.put_vectors,
                    vectorBucketName=self.bucket_name,
                    indexName=target_index,
                    vectors=s3_vectors
                )
                success_count += len(batch)
            except Exception as e:
                logger.error(f"Error uploading batch {i//batch_size}: {e}")
        
        result = {
            'uploaded_count': success_count,
            'total_vectors_in_index': success_count,
            'index_name': self.index_name,
            'namespace': namespace
        }
        
        logger.info(f"[async] Upload complete! {success_count} vectors uploaded")
        return result
    
    async def _ensure_index(self, target_index: str, dimension: int = 1536):
        """Helper to create sub-indexes on demand."""
        client = self.get_client()
        try:
            await asyncio.to_thread(
                client.create_index,
                vectorBucketName=self.bucket_name,
                indexName=target_index,
                dimension=dimension,
                distanceMetric='cosine',
                dataType='float32',
                metadataConfiguration={
                    'nonFilterableMetadataKeys': ['text', 'original_id', 'pinecone_namespace']
                }
            )
            logger.info(f"Sub-index '{target_index}' created")
        except Exception as e:
            if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
                pass  # Already exists, fine
            else:
                logger.warning(f"Error creating sub-index (might already exist): {e}")
    
    def _convert_pinecone_filter(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert Pinecone mongo-like filter syntax to S3 Vectors filter format.
        
        S3 Vectors filter syntax: 
        - {"key": {"$eq": "value"}} 
        - {"$and": [{"key1": {"$eq": "val1"}}, {"key2": {"$eq": "val2"}}]}
        - {"key": {"$in": ["val1", "val2"]}}
        
        Pinecone syntax is similar, so mostly pass-through, but we normalize.
        """
        if not filter_dict:
            return None
            
        # S3 Vectors supports similar filter syntax to Pinecone
        # The $in, $eq operators are directly compatible
        # We wrap multiple conditions in $and
        conditions = []
        for field, condition in filter_dict.items():
            if isinstance(condition, dict):
                # Already in operator format: {"$in": [...]} or {"$eq": "..."}
                conditions.append({field: condition})
            elif isinstance(condition, (str, int, float, bool)):
                # Implicit equality
                conditions.append({field: {"$eq": condition}})
                
        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return {"$and": conditions}
        return None
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        namespace: str = '',
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors using S3 Vectors query_vectors.
        Returns results matching the previous interface.
        """
        client = self.get_client()
        target_index = self._get_target_index(namespace)
        
        try:
            kwargs = {
                'vectorBucketName': self.bucket_name,
                'indexName': target_index,
                'topK': top_k,
                'queryVector': {'float32': query_embedding},
                'returnMetadata': include_metadata,
                'returnDistance': True
            }
            
            # Apply metadata filter
            s3_filter = self._convert_pinecone_filter(filter_dict)
            if s3_filter:
                kwargs['filter'] = s3_filter
                
            response = await asyncio.to_thread(client.query_vectors, **kwargs)
            
            matches = []
            for vec in response.get('vectors', []):
                metadata = vec.get('metadata', {}) or {}
                matches.append({
                    'id': vec.get('key', ''),
                    'score': 1.0 - vec.get('distance', 1.0),  # Convert distance to similarity score
                    'text': metadata.get('text', ''),
                    'metadata': metadata
                })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error executing search against {target_index}: {str(e)}")
            return []
    
    async def delete_by_metadata(
        self,
        filter_dict: Dict[str, Any],
        namespace: str = ''
    ) -> int:
        """
        Delete vectors matching a metadata filter.
        S3 Vectors doesn't support delete_by_query, so we:
        1. Query to find matching vector keys  
        2. Delete by keys
        """
        client = self.get_client()
        target_index = self._get_target_index(namespace)
        
        # Use a dummy zero vector for the query - we just want to find matching keys
        # We'll use list_vectors with pagination instead if possible
        deleted_count = 0
        
        try:
            # List all vectors and filter manually, or query with a large topK
            # S3 Vectors list_vectors + get_vectors approach
            paginator = client.get_paginator('list_vectors')
            keys_to_delete = []
            
            for page in paginator.paginate(
                vectorBucketName=self.bucket_name,
                indexName=target_index
            ):
                for vec in page.get('vectors', []):
                    vec_key = vec.get('key', '')
                    keys_to_delete.append(vec_key)
            
            # Now get metadata for each batch to filter
            batch_size = 100
            matching_keys = []
            
            for i in range(0, len(keys_to_delete), batch_size):
                batch_keys = keys_to_delete[i:i + batch_size]
                get_resp = await asyncio.to_thread(
                    client.get_vectors,
                    vectorBucketName=self.bucket_name,
                    indexName=target_index,
                    keys=batch_keys,
                    returnMetadata=True
                )
                
                for vec in get_resp.get('vectors', []):
                    metadata = vec.get('metadata', {}) or {}
                    # Check if this vector matches the filter
                    if self._metadata_matches_filter(metadata, filter_dict):
                        matching_keys.append(vec.get('key'))
            
            # Delete matching vectors in batches
            for i in range(0, len(matching_keys), batch_size):
                batch = matching_keys[i:i + batch_size]
                await asyncio.to_thread(
                    client.delete_vectors,
                    vectorBucketName=self.bucket_name,
                    indexName=target_index,
                    keys=batch
                )
                deleted_count += len(batch)
                
            logger.info(f"Deleted {deleted_count} vectors matching filter from {target_index}")
            
        except Exception as e:
            logger.error(f"Error deleting by metadata: {e}")
        
        return deleted_count
    
    def _metadata_matches_filter(self, metadata: Dict, filter_dict: Dict) -> bool:
        """Check if vector metadata matches a Pinecone-style filter."""
        for field, condition in filter_dict.items():
            value = metadata.get(field)
            if isinstance(condition, dict):
                for op, expected in condition.items():
                    if op == '$eq' and value != expected:
                        return False
                    elif op == '$in' and value not in expected:
                        return False
                    elif op == '$ne' and value == expected:
                        return False
            elif value != condition:
                return False
        return True
    
    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace (= delete the sub-index)."""
        logger.warning(f"Deleting namespace '{namespace}'...")
        target_index = self._get_target_index(namespace)
        
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
        
        if target_index != self.index_name:
            # Delete the entire sub-index
            try:
                await asyncio.to_thread(
                    client.delete_index,
                    vectorBucketName=self.bucket_name,
                    indexName=target_index
                )
            except Exception as e:
                logger.warning(f"Error deleting index {target_index}: {e}")
        else:
            # Delete all vectors in the main index via list+delete
            try:
                paginator = client.get_paginator('list_vectors')
                for page in paginator.paginate(
                    vectorBucketName=self.bucket_name,
                    indexName=target_index
                ):
                    keys = [v['key'] for v in page.get('vectors', [])]
                    if keys:
                        await asyncio.to_thread(
                            client.delete_vectors,
                            vectorBucketName=self.bucket_name,
                            indexName=target_index,
                            keys=keys
                        )
            except Exception as e:
                logger.warning(f"Error clearing index {target_index}: {e}")
                
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
        try:
            await asyncio.to_thread(
                client.delete_index,
                vectorBucketName=self.bucket_name,
                indexName=self.index_name
            )
        except Exception as e:
            logger.warning(f"Error deleting index: {e}")
        self._client = None
        logger.info(f"Index '{self.index_name}' deleted")
    
    def get_stats(self, namespace: str = '') -> Dict[str, Any]:
        """Get index statistics."""
        target_index = self._get_target_index(namespace)
        stats = {'total_vectors': 0, 'dimension': 0}
        
        try:
            client = self.get_client()
            resp = client.get_index(
                vectorBucketName=self.bucket_name,
                indexName=target_index
            )
            stats['total_vectors'] = resp.get('index', {}).get('vectorCount', 0)
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
        
        return {
            'total_vectors': stats['total_vectors'],
            'dimension': 1536,
            'index_name': self.index_name,
            'namespace': namespace
        }
