"""Utilities for working with FAISS indexes stored in S3."""

import json
import os
import pickle
import tempfile
from typing import Any, Dict, List, Tuple

import boto3
# Lazy imports for numpy and faiss to avoid import errors at module load time


class FAISSService:
    """Create, persist, and query FAISS indexes."""

    def __init__(self, embedding_dimension: int = 1024):
        self.embedding_dimension = embedding_dimension
        self.bucket_name = os.environ.get("KB_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("KB_BUCKET_NAME environment variable is required")

        self.s3_client = boto3.client("s3")
        self.bedrock_client = boto3.client("bedrock-runtime")

    def create_embedding(
        self, *, text: str, model_id: str = "amazon.titan-embed-text-v2:0"
    ) -> List[float]:
        body = json.dumps({"inputText": text})
        max_retries = 5
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=model_id,
                    body=body,
                    contentType="application/json",
                    accept="application/json",
                )
                payload = json.loads(response["body"].read())
                return payload.get("embedding", [])
            except Exception as e:
                import time
                error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
                if attempt < max_retries - 1 and error_code in [
                    "ThrottlingException",
                    "TooManyRequestsException",
                ]:
                    delay = base_delay * (2**attempt)
                    print(
                        f"Throttling on create_embedding, retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                else:
                    print(f"Failed to create embedding after {attempt + 1} attempts: {e}")
                    raise e
        return []

    def create_embeddings_batch(
        self,
        *,
        texts: List[str],
        model_id: str = "amazon.titan-embed-text-v2:0",
        batch_size: int = 25,
    ) -> List[List[float]]:
        embeddings: List[List[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            for text in batch:
                embeddings.append(self.create_embedding(text=text, model_id=model_id))
        return embeddings

    def create_index(self, embeddings: List[List[float]]):
        # Lazy import to avoid numpy/faiss import errors at module load time
        import faiss
        import numpy as np

        index = faiss.IndexFlatL2(self.embedding_dimension)
        vectors = np.array(embeddings, dtype=np.float32)
        index.add(vectors)
        return index

    def _kb_prefix(self, *, kb_id: str, user_id: str) -> str:
        return f"knowledge-bases/{user_id}/{kb_id}"

    def save_index_to_s3(
        self,
        *,
        index,
        metadata: List[Dict[str, Any]],
        kb_id: str,
        user_id: str,
    ):
        # Lazy import to avoid numpy/faiss import errors at module load time
        import faiss

        prefix = self._kb_prefix(kb_id=kb_id, user_id=user_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".index") as index_file:
            index_path = index_file.name
            faiss.write_index(index, index_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as meta_file:
            metadata_path = meta_file.name
            with open(metadata_path, "wb") as handle:
                pickle.dump(metadata, handle)

        try:
            self.s3_client.upload_file(
                index_path, self.bucket_name, f"{prefix}/faiss.index"
            )
            self.s3_client.upload_file(
                metadata_path, self.bucket_name, f"{prefix}/metadata.pkl"
            )
            config = {
                "dimension": self.embedding_dimension,
                "count": index.ntotal,
                "metadata_count": len(metadata),
            }
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{prefix}/config.json",
                Body=json.dumps(config),
                ContentType="application/json",
            )
        finally:
            os.unlink(index_path)
            os.unlink(metadata_path)

    def load_index_from_s3(
        self, *, kb_id: str, user_id: str
    ) -> Tuple[Any, List[Dict[str, Any]]]:
        # Lazy import to avoid numpy/faiss import errors at module load time
        import faiss

        prefix = self._kb_prefix(kb_id=kb_id, user_id=user_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".index") as index_file:
            index_path = index_file.name
            self.s3_client.download_file(
                self.bucket_name, f"{prefix}/faiss.index", index_path
            )
            index = faiss.read_index(index_path)
        os.unlink(index_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as meta_file:
            metadata_path = meta_file.name
            self.s3_client.download_file(
                self.bucket_name, f"{prefix}/metadata.pkl", metadata_path
            )
            with open(metadata_path, "rb") as handle:
                metadata = pickle.load(handle)
        os.unlink(metadata_path)

        return index, metadata

    def search(
        self,
        *,
        index,
        metadata: List[Dict[str, Any]],
        query_embedding: List[float],
        k: int = 5,
        distance_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        # Lazy import to avoid numpy/faiss import errors at module load time
        import numpy as np

        query_vector = np.array([query_embedding], dtype=np.float32)
        distances, indices = index.search(query_vector, k)

        results: List[Dict[str, Any]] = []
        for rank, (distance, idx) in enumerate(zip(distances[0], indices[0]), start=1):
            if distance_threshold is not None and distance > distance_threshold:
                continue
            if idx >= len(metadata):
                continue
            results.append(
                {
                    "rank": rank,
                    "distance": float(distance),
                    "metadata": metadata[idx],
                }
            )
        return results

    def delete_index_from_s3(self, *, kb_id: str, user_id: str):
        prefix = self._kb_prefix(kb_id=kb_id, user_id=user_id)
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                self.s3_client.delete_object(
                    Bucket=self.bucket_name, Key=obj.get("Key", "")
                )
