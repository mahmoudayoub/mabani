"""
Vector store service using Amazon S3 Vectors.
Handles index management, uploading, and querying.
Uses aioboto3 for fully async operations — no thread pool bottleneck.
"""
import asyncio
import logging
import re
import unicodedata
from typing import List, Dict, Any, Optional, Set

import boto3
import aioboto3

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
        self._sync_client = None
        self._session = aioboto3.Session()
        self._validated_indexes: Set[str] = set()
        self._index_check_locks: Dict[str, asyncio.Lock] = {}
        
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
        """Get the synchronous S3 Vectors boto3 client (for sync-only contexts)."""
        if self._sync_client is not None:
            return self._sync_client
        self._sync_client = boto3.client('s3vectors', region_name=self.region)
        return self._sync_client

    def _get_target_index(self, namespace: str) -> str:
        """
        Map namespace to index name.
        If namespace is provided, append it to the base index name.
        """
        if namespace:
            clean_ns = namespace.lower().replace(" ", "-")
            return f"{self.index_name}-{clean_ns}"
        return self.index_name

    async def _get_index_or_raise(self, client: Any, target_index: str) -> None:
        """Perform a single get_index call and raise explicit errors for missing index."""
        try:
            await client.get_index(
                vectorBucketName=self.bucket_name,
                indexName=target_index
            )
        except Exception as e:
            msg = str(e).lower()
            if 'notfound' in msg or 'not found' in msg or 'resource not found' in msg:
                raise RuntimeError(
                    f"S3 Vectors index '{target_index}' does not exist in bucket "
                    f"'{self.bucket_name}'. Create/provision indexes before query/upload/delete."
                ) from e
            raise

    async def _assert_index_exists(
        self,
        target_index: str,
        client: Optional[Any] = None,
        force_refresh: bool = False
    ) -> None:
        """
        Fail fast if target index does not exist.

        Uses per-index in-memory caching to avoid repeated get_index calls on hot paths.
        """
        if not force_refresh and target_index in self._validated_indexes:
            return

        lock = self._index_check_locks.setdefault(target_index, asyncio.Lock())
        async with lock:
            if not force_refresh and target_index in self._validated_indexes:
                return

            if client is not None:
                await self._get_index_or_raise(client, target_index)
            else:
                async with self._session.client('s3vectors', region_name=self.region) as owned_client:
                    await self._get_index_or_raise(owned_client, target_index)

            self._validated_indexes.add(target_index)

    async def ensure_index_exists(self, namespace: str = '') -> None:
        """Public index existence check for callers that need explicit verification."""
        target_index = self._get_target_index(namespace)
        await self._assert_index_exists(target_index)
    
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
        distance_metric = 'cosine'
        if metric == 'euclidean' or metric == 'l2':
            distance_metric = 'euclidean'
        
        async with self._session.client('s3vectors', region_name=self.region) as client:
            # 1. Create the vector bucket (idempotent)
            try:
                await client.create_vector_bucket(
                    vectorBucketName=self.bucket_name
                )
                logger.info(f"Vector bucket '{self.bucket_name}' created (or already exists)")
            except Exception as e:
                if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
                    logger.info(f"Vector bucket '{self.bucket_name}' already exists")
                else:
                    raise
            
            # 2. Create the vector index
            try:
                await client.create_index(
                    vectorBucketName=self.bucket_name,
                    indexName=self.index_name,
                    dimension=dimension,
                    distanceMetric=distance_metric,
                    dataType='float32',
                    metadataConfiguration={
                        'nonFilterableMetadataKeys': [
                            'text', 'description', 'category_path', 'full_description',
                            'parent', 'grandparent', 'trade', 'code', 'unit',
                            'original_id'
                        ]
                    }
                )
                logger.info(f"Index '{self.index_name}' created successfully")
            except Exception as e:
                if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
                    logger.info(f"Index '{self.index_name}' already exists")
                else:
                    raise
        self._validated_indexes.add(self.index_name)
    
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
        Fully async — no thread pool bottleneck.
        """
        target_index = self._get_target_index(namespace)

        logger.info(f"[async] Preparing {len(items)} vectors for upload...")
        vectors = self.prepare_vectors(items)
        logger.info(f"[async] Uploading {len(vectors)} vectors to S3 Vectors ({target_index})...")
        
        success_count = 0

        async with self._session.client('s3vectors', region_name=self.region) as client:
            await self._assert_index_exists(target_index, client=client)
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
                    await client.put_vectors(
                        vectorBucketName=self.bucket_name,
                        indexName=target_index,
                        vectors=s3_vectors
                    )
                    success_count += len(batch)
                except Exception as e:
                    batch_no = (i // batch_size) + 1
                    logger.error(
                        f"Upload failed at batch {batch_no} "
                        f"({len(batch)} vectors) for index {target_index}: {e}"
                    )
                    raise RuntimeError(
                        f"Upload failed at batch {batch_no} for index '{target_index}'"
                    ) from e
        
        result = {
            'uploaded_count': success_count,
            'total_vectors_in_index': success_count,
            'index_name': self.index_name,
            'namespace': namespace
        }
        
        logger.info(f"[async] Upload complete! {success_count} vectors uploaded")
        return result
    
    def _convert_filter(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert filter dict to S3 Vectors filter format.
        
        Supported syntax:
        - {"key": {"$eq": "value"}}
        - {"key": {"$in": ["val1", "val2"]}}
        - {"$and": [{"key1": {"$eq": "val1"}}, {"key2": {"$eq": "val2"}}]}
        - {"$or": [{"key1": {"$eq": "val1"}}, {"key2": {"$eq": "val2"}}]}
        - {"$not": {"key": {"$eq": "value"}}}

        Raises:
            ValueError: If filter syntax is invalid or uses unsupported operators.
        """
        if not filter_dict:
            return None
        if not isinstance(filter_dict, dict):
            raise ValueError("Filter must be a dictionary")
        return self._normalize_filter(filter_dict)

    def _normalize_filter(self, filter_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize filter into explicit logical/operator format."""
        if not isinstance(filter_obj, dict) or not filter_obj:
            raise ValueError("Filter object must be a non-empty dictionary")

        logical_ops = {'$and', '$or', '$not'}
        present_logical = [k for k in filter_obj.keys() if k in logical_ops]

        # Logical object: must contain only one logical operator.
        if present_logical:
            if len(filter_obj) != 1:
                raise ValueError(
                    "Logical filter object must contain exactly one key: $and, $or, or $not"
                )
            op = present_logical[0]
            value = filter_obj[op]

            if op in {'$and', '$or'}:
                if not isinstance(value, list) or not value:
                    raise ValueError(f"{op} must be a non-empty list of filter objects")
                return {op: [self._normalize_filter(item) for item in value]}

            if op == '$not':
                if not isinstance(value, dict):
                    raise ValueError("$not must wrap a single filter object")
                return {'$not': self._normalize_filter(value)}

        # Field conditions.
        supported_field_ops = {'$eq', '$ne', '$in', '$nin', '$gt', '$gte', '$lt', '$lte'}
        conditions = []
        for field, condition in filter_obj.items():
            if str(field).startswith('$'):
                raise ValueError(f"Unsupported logical/operator key at this level: {field}")

            # Implicit equality.
            if isinstance(condition, (str, int, float, bool)):
                conditions.append({field: {'$eq': condition}})
                continue

            if condition is None:
                conditions.append({field: {'$eq': None}})
                continue

            if not isinstance(condition, dict) or not condition:
                raise ValueError(
                    f"Field '{field}' must map to a scalar or non-empty operator object"
                )

            # Expand multi-operator field conditions into $and for explicit semantics.
            field_clauses = []
            for op, expected in condition.items():
                if op not in supported_field_ops:
                    raise ValueError(f"Unsupported operator '{op}' for field '{field}'")
                if op in {'$in', '$nin'} and not isinstance(expected, list):
                    raise ValueError(f"Operator '{op}' for field '{field}' requires a list")
                field_clauses.append({field: {op: expected}})

            if len(field_clauses) == 1:
                conditions.append(field_clauses[0])
            else:
                conditions.append({'$and': field_clauses})

        if len(conditions) == 1:
            return conditions[0]
        return {'$and': conditions}
    
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
        Fully async — no thread pool bottleneck.
        """
        target_index = self._get_target_index(namespace)

        kwargs = {
            'vectorBucketName': self.bucket_name,
            'indexName': target_index,
            'topK': top_k,
            'queryVector': {'float32': query_embedding},
            'returnMetadata': include_metadata,
            'returnDistance': True
        }
        
        # Apply metadata filter
        s3_filter = self._convert_filter(filter_dict)
        if s3_filter:
            kwargs['filter'] = s3_filter

        async with self._session.client('s3vectors', region_name=self.region) as client:
            await self._assert_index_exists(target_index, client=client)
            response = await client.query_vectors(**kwargs)
        
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
    
    async def delete_by_metadata(
        self,
        filter_dict: Dict[str, Any],
        namespace: str = ''
    ) -> int:
        """
        Delete vectors matching a metadata filter.
        S3 Vectors doesn't support delete_by_query, so we:
        1. List all vector keys  
        2. Get metadata in batches
        3. Filter and delete matching keys
        """
        target_index = self._get_target_index(namespace)
        deleted_count = 0

        async with self._session.client('s3vectors', region_name=self.region) as client:
            await self._assert_index_exists(target_index, client=client)
            # List all vectors
            paginator = client.get_paginator('list_vectors')
            keys_to_check = []
            
            async for page in paginator.paginate(
                vectorBucketName=self.bucket_name,
                indexName=target_index
            ):
                for vec in page.get('vectors', []):
                    keys_to_check.append(vec.get('key', ''))
            
            # Get metadata for each batch to filter
            batch_size = 100
            matching_keys = []
            
            for i in range(0, len(keys_to_check), batch_size):
                batch_keys = keys_to_check[i:i + batch_size]
                get_resp = await client.get_vectors(
                    vectorBucketName=self.bucket_name,
                    indexName=target_index,
                    keys=batch_keys,
                    returnMetadata=True
                )
                
                for vec in get_resp.get('vectors', []):
                    metadata = vec.get('metadata', {}) or {}
                    if self._metadata_matches_filter(metadata, filter_dict):
                        matching_keys.append(vec.get('key'))
            
            # Delete matching vectors in batches
            for i in range(0, len(matching_keys), batch_size):
                batch = matching_keys[i:i + batch_size]
                await client.delete_vectors(
                    vectorBucketName=self.bucket_name,
                    indexName=target_index,
                    keys=batch
                )
                deleted_count += len(batch)

        logger.info(f"Deleted {deleted_count} vectors matching filter from {target_index}")
        
        return deleted_count
    
    def _metadata_matches_filter(self, metadata: Dict, filter_dict: Dict) -> bool:
        """
        Check if vector metadata matches a filter dict.

        Uses the same normalized syntax accepted by query filters, including
        nested $and/$or/$not.
        """
        normalized = self._convert_filter(filter_dict)
        if not normalized:
            return True
        return self._evaluate_filter(metadata, normalized)

    def _evaluate_filter(self, metadata: Dict[str, Any], filter_obj: Dict[str, Any]) -> bool:
        """Evaluate normalized filter object against metadata."""
        if '$and' in filter_obj:
            return all(self._evaluate_filter(metadata, clause) for clause in filter_obj['$and'])
        if '$or' in filter_obj:
            return any(self._evaluate_filter(metadata, clause) for clause in filter_obj['$or'])
        if '$not' in filter_obj:
            return not self._evaluate_filter(metadata, filter_obj['$not'])

        for field, condition in filter_obj.items():
            value = metadata.get(field)

            # Backward compatibility for already-normalized scalar equality.
            if not isinstance(condition, dict):
                if value != condition:
                    return False
                continue

            for op, expected in condition.items():
                if op == '$eq':
                    if value != expected:
                        return False
                elif op == '$ne':
                    if value == expected:
                        return False
                elif op == '$in':
                    if value not in expected:
                        return False
                elif op == '$nin':
                    if value in expected:
                        return False
                elif op == '$gt':
                    if not self._compare_values(value, expected, 'gt'):
                        return False
                elif op == '$gte':
                    if not self._compare_values(value, expected, 'gte'):
                        return False
                elif op == '$lt':
                    if not self._compare_values(value, expected, 'lt'):
                        return False
                elif op == '$lte':
                    if not self._compare_values(value, expected, 'lte'):
                        return False
                else:
                    raise ValueError(f"Unsupported operator '{op}'")

        return True

    @staticmethod
    def _compare_values(value: Any, expected: Any, op: str) -> bool:
        """Type-safe scalar comparisons for range operators."""
        try:
            if op == 'gt':
                return value > expected
            if op == 'gte':
                return value >= expected
            if op == 'lt':
                return value < expected
            if op == 'lte':
                return value <= expected
        except TypeError:
            return False
        return False
    
    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace (= delete the sub-index), synchronously."""
        logger.warning(f"Deleting namespace '{namespace}'...")
        target_index = self._get_target_index(namespace)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._delete_namespace_async(target_index, namespace))
            return

        raise RuntimeError(
            "delete_namespace() called while an event loop is running. "
            "Use await delete_namespace_async(...) instead."
        )

    async def delete_namespace_async(self, namespace: str):
        """Async deletion of all vectors in a namespace."""
        target_index = self._get_target_index(namespace)
        await self._delete_namespace_async(target_index, namespace)
            
    async def _delete_namespace_async(self, target_index: str, namespace: str):
        async with self._session.client('s3vectors', region_name=self.region) as client:
            if target_index != self.index_name:
                # Delete the entire sub-index
                await client.delete_index(
                    vectorBucketName=self.bucket_name,
                    indexName=target_index
                )
            else:
                # Delete all vectors in the main index via list+delete
                paginator = client.get_paginator('list_vectors')
                async for page in paginator.paginate(
                    vectorBucketName=self.bucket_name,
                    indexName=target_index
                ):
                    keys = [v['key'] for v in page.get('vectors', [])]
                    if keys:
                        await client.delete_vectors(
                            vectorBucketName=self.bucket_name,
                            indexName=target_index,
                            keys=keys
                        )
                    
        self._validated_indexes.discard(target_index)
        logger.info(f"Namespace '{namespace}' deleted")
    
    def delete_index(self):
        """Delete the base index, synchronously."""
        logger.warning(f"Deleting index '{self.index_name}'...")

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._delete_index_async())
            return

        raise RuntimeError(
            "delete_index() called while an event loop is running. "
            "Use await delete_index_async() instead."
        )

    async def delete_index_async(self):
        """Async deletion of the base index."""
        await self._delete_index_async()
            
    async def _delete_index_async(self):
        async with self._session.client('s3vectors', region_name=self.region) as client:
            await client.delete_index(
                vectorBucketName=self.bucket_name,
                indexName=self.index_name
            )
        self._sync_client = None
        self._validated_indexes.discard(self.index_name)
        logger.info(f"Index '{self.index_name}' deleted")
    
    def get_stats(self, namespace: str = '') -> Dict[str, Any]:
        """Get index statistics (sync — used in Flask routes)."""
        target_index = self._get_target_index(namespace)
        client = self.get_client()
        resp = client.get_index(
            vectorBucketName=self.bucket_name,
            indexName=target_index
        )
        total_vectors = resp.get('index', {}).get('vectorCount', 0)
        
        return {
            'total_vectors': total_vectors,
            'dimension': 1536,
            'index_name': self.index_name,
            'namespace': namespace
        }
