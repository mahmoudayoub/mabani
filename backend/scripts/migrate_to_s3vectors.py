"""
Migrate vectors from Pinecone to S3 Vectors.
Reads from the existing Pinecone index and writes to S3 Vectors.
"""
import os
import sys
import boto3
from tqdm import tqdm

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))

# Config
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "almabani-1")
S3_VECTORS_BUCKET = os.environ.get("S3_VECTORS_BUCKET", "almabani-vectors")
REGION = os.environ.get("AWS_REGION", "eu-west-1")

BATCH_SIZE = 50  # S3 Vectors put_vectors batch limit
FETCH_BATCH_SIZE = 100  # Pinecone fetch batch size


def get_pinecone_index(index_name):
    """Get Pinecone index for reading source data."""
    from pinecone import Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(index_name)


def get_s3vectors_client():
    """Get S3 Vectors client."""
    return boto3.client('s3vectors', region_name=REGION)


def create_s3_vector_index(s3v_client, index_name, dimension=1536):
    """Create a vector bucket and index in S3 Vectors."""
    # Create bucket
    try:
        s3v_client.create_vector_bucket(vectorBucketName=S3_VECTORS_BUCKET)
        print(f"Created vector bucket: {S3_VECTORS_BUCKET}")
    except Exception as e:
        if 'Conflict' in str(e) or 'already exists' in str(e).lower():
            print(f"Vector bucket '{S3_VECTORS_BUCKET}' already exists")
        else:
            raise
    
    # Create index
    try:
        s3v_client.create_index(
            vectorBucketName=S3_VECTORS_BUCKET,
            indexName=index_name,
            dimension=dimension,
            distanceMetric='cosine',
            dataType='float32',
            metadataConfiguration={
                'nonFilterableMetadataKeys': [
                    'text', 'description', 'category_path', 'full_description',
                    'parent', 'grandparent', 'trade', 'code', 'unit',
                    'original_id'
                ]
            }
        )
        print(f"Created index: {index_name}")
    except Exception as e:
        if 'Conflict' in str(e) or 'already exists' in str(e).lower():
            print(f"Index '{index_name}' already exists")
        else:
            raise


def migrate_namespace(pinecone_index, s3v_client, s3v_index_name, namespace="", total_hint=0):
    """Migrate all vectors from a Pinecone namespace to S3 Vectors."""
    ns_label = namespace if namespace else "(default)"
    print(f"\n  Namespace: {ns_label}")
    
    migrated = 0
    errors = 0
    
    with tqdm(total=total_hint, desc=f"  Migrating {ns_label}") as pbar:
        # Use list_paginated to stream IDs page by page
        pagination_token = None
        
        while True:
            # Get a page of IDs
            list_kwargs = dict(namespace=namespace, limit=100)
            if pagination_token:
                list_kwargs['pagination_token'] = pagination_token
            
            try:
                page = pinecone_index.list_paginated(**list_kwargs)
            except Exception as e:
                print(f"\n  Error listing vectors: {e}")
                break
            
            page_ids = [v.id for v in (page.vectors or [])]
            
            if not page_ids:
                break
            
            # Fetch full vectors for this page
            try:
                fetch_response = pinecone_index.fetch(ids=page_ids, namespace=namespace)
            except Exception as e:
                print(f"\n  Error fetching batch: {e}")
                errors += len(page_ids)
                pbar.update(len(page_ids))
                pagination_token = page.pagination and page.pagination.next
                if not pagination_token:
                    break
                continue
            
            # Support both dict and FetchResponse object
            vectors_dict = fetch_response.vectors if hasattr(fetch_response, 'vectors') else fetch_response.get('vectors', {})
            
            # Build S3 Vectors batch
            s3v_batch = []
            for vec_id, vec_data in vectors_dict.items():
                # Support both dict and Vector object
                if hasattr(vec_data, 'values'):
                    embedding = list(vec_data.values)
                    metadata = dict(vec_data.metadata) if vec_data.metadata else {}
                else:
                    embedding = vec_data.get('values', [])
                    metadata = vec_data.get('metadata', {}) or {}
                
                if not embedding:
                    continue
                
                if namespace:
                    metadata['pinecone_namespace'] = namespace
                
                s3v_batch.append({
                    'key': vec_id,
                    'data': {'float32': embedding},
                    'metadata': metadata
                })
            
            # Upload to S3 Vectors in sub-batches
            for j in range(0, len(s3v_batch), BATCH_SIZE):
                sub_batch = s3v_batch[j:j + BATCH_SIZE]
                try:
                    s3v_client.put_vectors(
                        vectorBucketName=S3_VECTORS_BUCKET,
                        indexName=s3v_index_name,
                        vectors=sub_batch
                    )
                    migrated += len(sub_batch)
                except Exception as e:
                    errors += len(sub_batch)
                    print(f"\n  Error uploading batch: {e}")
            
            pbar.update(len(page_ids))
            
            # Check for next page
            pagination_token = page.pagination and page.pagination.next
            if not pagination_token:
                break
    
    print(f"  Done: {migrated} migrated, {errors} errors")
    return migrated


def migrate_index(pinecone_index_name, s3v_index_name):
    """Migrate a single Pinecone index to S3 Vectors."""
    print(f"\n{'='*60}")
    print(f"Migrating Pinecone index: {pinecone_index_name} → S3 Vectors: {s3v_index_name}")
    print(f"{'='*60}")
    
    pinecone_index = get_pinecone_index(pinecone_index_name)
    s3v_client = get_s3vectors_client()
    
    # Get index stats to find namespaces and dimensions
    stats = pinecone_index.describe_index_stats()
    dimension = stats.get('dimension', 1536)
    total_vectors = stats.get('total_vector_count', 0)
    namespaces = stats.get('namespaces', {})
    
    print(f"Dimension: {dimension}")
    print(f"Total vectors: {total_vectors}")
    print(f"Namespaces: {list(namespaces.keys()) if namespaces else ['(default)']}")
    
    if total_vectors == 0:
        print("No vectors to migrate")
        return
    
    # Create target S3 Vectors index
    create_s3_vector_index(s3v_client, s3v_index_name, dimension=dimension)
    
    total_migrated = 0
    
    if namespaces:
        for ns_name, ns_info in namespaces.items():
            ns_count = ns_info.get('vector_count', 0) if isinstance(ns_info, dict) else 0
            count = migrate_namespace(pinecone_index, s3v_client, s3v_index_name, namespace=ns_name, total_hint=ns_count)
            total_migrated += count
    else:
        total_migrated = migrate_namespace(pinecone_index, s3v_client, s3v_index_name, namespace="", total_hint=total_vectors)
    
    print(f"\nTotal migrated for {pinecone_index_name}: {total_migrated}")


def main():
    print("=== Pinecone → S3 Vectors Migration ===\n")
    
    if not PINECONE_API_KEY:
        print("ERROR: PINECONE_API_KEY not set in environment")
        sys.exit(1)
    
    print(f"Target: S3 Vectors bucket '{S3_VECTORS_BUCKET}'")
    print(f"Region: {REGION}")
    print()
    
    # almabani-1 → almabani: ALREADY MIGRATED (56033 vectors)
    print("✅ almabani-1 → almabani: already migrated, skipping\n")
    
    # Migrate pricecode index
    migrate_index("almabani-pricecode", "almabani-pricecode")
    
    print("\n=== Migration Complete ===")
    print("Next steps:")
    print("1. Verify data in S3 Vectors via AWS Console")
    print("2. Deploy the S3 Vectors version: git checkout main && cd infra && cdk deploy --all")
    print("3. Delete the Pinecone indexes if no longer needed")


if __name__ == "__main__":
    main()
