"""
Migrate vectors from OpenSearch Serverless to S3 Vectors.
Reads from the existing OpenSearch collection and writes to S3 Vectors.
"""
import os
import sys
import boto3
from tqdm import tqdm

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))

# OpenSearch source config
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "https://l1247qcv6ah7atd18f9e.eu-west-1.aoss.amazonaws.com")
S3_VECTORS_BUCKET = os.environ.get("S3_VECTORS_BUCKET", "almabani-vectors")
REGION = os.environ.get("AWS_REGION", "eu-west-1")

BATCH_SIZE = 50  # S3 Vectors put_vectors batch limit


def get_opensearch_client():
    """Get OpenSearch client for reading source data."""
    from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, REGION, "aoss")
    return OpenSearch(
        hosts=[OPENSEARCH_ENDPOINT],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
        max_retries=3,
        retry_on_timeout=True
    )


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
                'nonFilterableMetadataKeys': ['text', 'original_id', 'pinecone_namespace']
            }
        )
        print(f"Created index: {index_name}")
    except Exception as e:
        if 'Conflict' in str(e) or 'already exists' in str(e).lower():
            print(f"Index '{index_name}' already exists")
        else:
            raise


def scroll_opensearch(os_client, index_name, batch_size=500):
    """Scroll through all documents in an OpenSearch index."""
    query = {
        "size": batch_size,
        "_source": True,
        "query": {"match_all": {}}
    }
    
    # Initial search
    response = os_client.search(index=index_name, body=query, scroll='5m')
    scroll_id = response.get('_scroll_id')
    hits = response.get('hits', {}).get('hits', [])
    
    while hits:
        yield hits
        response = os_client.scroll(scroll_id=scroll_id, scroll='5m')
        scroll_id = response.get('_scroll_id')
        hits = response.get('hits', {}).get('hits', [])
    
    # Clean up scroll
    try:
        os_client.clear_scroll(scroll_id=scroll_id)
    except:
        pass


def migrate_index(os_client, s3v_client, os_index_name, s3v_index_name):
    """Migrate a single OpenSearch index to S3 Vectors."""
    print(f"\n--- Migrating {os_index_name} → {s3v_index_name} ---")
    
    # Check if source index exists
    if not os_client.indices.exists(index=os_index_name):
        print(f"Source index {os_index_name} does not exist, skipping")
        return
    
    # Get count
    count = os_client.count(index=os_index_name).get('count', 0)
    print(f"Source has {count} vectors")
    
    if count == 0:
        print("No vectors to migrate")
        return
    
    # Create target S3 Vectors index
    create_s3_vector_index(s3v_client, s3v_index_name)
    
    migrated = 0
    errors = 0
    
    with tqdm(total=count, desc=f"Migrating {s3v_index_name}") as pbar:
        for hits in scroll_opensearch(os_client, os_index_name):
            batch = []
            for hit in hits:
                source = hit.get('_source', {})
                embedding = source.pop('embedding', None)
                
                if embedding is None:
                    continue
                    
                # Use OpenSearch _id or original_id from metadata as key
                vec_key = source.get('original_id', hit.get('_id', ''))
                if not vec_key:
                    continue
                    
                # Build metadata (everything except the embedding)
                metadata = {k: v for k, v in source.items() if k != 'embedding'}
                
                batch.append({
                    'key': vec_key,
                    'data': {'float32': embedding},
                    'metadata': metadata
                })
            
            # Upload in sub-batches of BATCH_SIZE
            for i in range(0, len(batch), BATCH_SIZE):
                sub_batch = batch[i:i + BATCH_SIZE]
                try:
                    s3v_client.put_vectors(
                        vectorBucketName=S3_VECTORS_BUCKET,
                        indexName=s3v_index_name,
                        vectors=sub_batch
                    )
                    migrated += len(sub_batch)
                except Exception as e:
                    errors += len(sub_batch)
                    print(f"\nError uploading batch: {e}")
                
                pbar.update(len(sub_batch))
    
    print(f"Migration complete: {migrated} migrated, {errors} errors")


def main():
    print("=== OpenSearch → S3 Vectors Migration ===\n")
    
    os_client = get_opensearch_client()
    s3v_client = get_s3vectors_client()
    
    # Discover all indices in OpenSearch
    indices = os_client.cat.indices(format='json')
    
    print(f"Found {len(indices)} indices in OpenSearch:")
    for idx in indices:
        print(f"  - {idx['index']}: {idx.get('docs.count', '?')} docs")
    
    for idx in indices:
        index_name = idx['index']
        # Use same index name in S3 Vectors
        migrate_index(os_client, s3v_client, index_name, index_name)
    
    print("\n=== Migration Complete ===")
    print(f"Your OpenSearch collection can now be safely deleted from the AWS console.")
    print(f"Go to OpenSearch Service → Serverless → Collections → Delete 'almabani-vectors'")


if __name__ == "__main__":
    main()
