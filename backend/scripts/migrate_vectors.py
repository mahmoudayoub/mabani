import os
import sys
import asyncio
from typing import List, Dict, Any
import pinecone
from tqdm import tqdm
from dotenv import load_dotenv

# Add backend dir to path so we can import almabani
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from almabani.core.vector_store import VectorStoreService

# Load environment variables (make sure to use a .env that STILL has PINECONE_API_KEY)
load_dotenv()

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENV = os.environ.get("PINECONE_ENVIRONMENT", "gcp-starter") 
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT")

if not PINECONE_API_KEY:
    print("Error: PINECONE_API_KEY environment variable is required for migration.")
    sys.exit(1)

if not OPENSEARCH_ENDPOINT:
    print("Error: OPENSEARCH_ENDPOINT environment variable is required for migration.")
    sys.exit(1)

async def migrate_index(pinecone_index_name: str, opensearch_index_name: str, batch_size: int = 100):
    """
    Migrate data from a single Pinecone index to an OpenSearch index.
    Note: This uses the pinecone client directly for extraction.
    """
    print(f"\nMigration Status:")
    print(f"Source (Pinecone): {pinecone_index_name}")
    print(f"Destination (OpenSearch): {opensearch_index_name}")

    # Initialize Pinecone
    try:
        # For pinecone >= 3.0.0
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(pinecone_index_name)
    except Exception as e:
        print(f"Failed to initialize Pinecone: {e}")
        return

    # Initialize OpenSearch
    print(f"Initializing OpenSearch connection to {OPENSEARCH_ENDPOINT}...")
    vector_store = VectorStoreService(
        endpoint=OPENSEARCH_ENDPOINT,
        index_name=opensearch_index_name
    )
    
    # Create the index if it doesn't exist
    await vector_store.create_index()

    # Get Pinecone stats to know how many vectors we have
    stats = index.describe_index_stats()
    total_vectors = stats.total_vector_count
    
    if total_vectors == 0:
        print(f"No vectors found in Pinecone index '{pinecone_index_name}'. Skipping.")
        return
        
    print(f"Found {total_vectors} vectors to migrate.")

    # In Pinecone, fetching requires IDs. If we don't know the IDs, 
    # we have to use the `list` mechanism (available in newer SDKs/Serverless)
    # OR we can iterate through a known set of metadata (e.g., sheets)
    # The new Pinecone SDK has a `list` operation
    
    try:
        migrated_count = 0
        failed_count = 0
        
        # We need to iterate over all namespaces. Default is often ""
        namespaces = list(stats.namespaces.keys())
        if not namespaces:
            namespaces = [""]
            
        for namespace in namespaces:
            print(f"Processing namespace: '{namespace}'")
            
            # Using the pagination token list approach
            pagination_token = None
            
            with tqdm(total=stats.namespaces.get(namespace, {}).get("vector_count", total_vectors)) as pbar:
                while True:
                    # List IDs
                    list_response = index.list(namespace=namespace, limit=batch_size, pagination_token=pagination_token)
                    vector_ids = list_response.vectors
                    
                    if not vector_ids:
                        break
                        
                    # Fetch actual vectors with metadata
                    fetch_response = index.fetch(ids=vector_ids, namespace=namespace)
                    
                    # Prepare for OpenSearch
                    os_docs = []
                    for vec_id, vec_data in fetch_response.vectors.items():
                        doc = {
                            "metadata": vec_data.get('metadata', {}),
                            **vec_data.get('metadata', {}) # flatten for easier searching in OS
                        }
                        # Add text field if it doesn't exist but description does
                        if 'text' not in doc and 'description' in doc:
                            doc['text'] = doc['description']
                        elif 'text' not in doc and 'item_description' in doc:
                            doc['text'] = doc['item_description']
                            
                        # Keep the ID for reference, but VectorStoreService handles ID generation internally
                        # if we use upload_vectors without explicit IDs. 
                        # To maintain exact IDs, we'd need to modify VectorStoreService, 
                        # but typically we just re-index with the metadata.
                        
                        # Add original ID to metadata just in case
                        doc["metadata"]["pinecone_id"] = vec_id
                        if namespace:
                             doc["metadata"]["pinecone_namespace"] = namespace
                        
                        os_docs.append(doc)
                        
                    # We need the raw embeddings to re-upload using the VectorStoreService interface, 
                    # but VectorStoreService.upload_vectors expects a list of dicts that have the embedding inside,
                    # OR we can use the client directly to bulk index.
                    
                    actions = []
                    os_client = vector_store.get_client()
                    
                    for vec_id, vec_data in fetch_response.vectors.items():
                         metadata = vec_data.get('metadata', {})
                         metadata['pinecone_namespace'] = namespace
                         
                         source_data = {
                             "vector_field": vec_data.values,
                             "text": metadata.get('text', metadata.get('description', '')),
                             **metadata
                         }
                         
                         actions.append(
                             {"index": {"_index": opensearch_index_name, "_id": vec_id}},
                             source_data
                         )
                         
                    # Execute bulk request directly via client for more control during migration
                    try:
                        resp = await os_client.bulk(body=actions)
                        if resp.get('errors'):
                             failed_count += len([i for i in resp['items'] if 'error' in i.get('index', {})])
                             # Successfully migrated in this batch
                             successful = len(actions) // 2 - failed_count 
                             migrated_count += successful
                        else:
                             migrated_count += len(actions) // 2
                    except Exception as e:
                        print(f"\nError uploading batch: {e}")
                        failed_count += len(actions) // 2
                        
                    pbar.update(len(vector_ids))
                    
                    # Check for next page
                    pagination_token = list_response.pagination.get("next")
                    if not pagination_token:
                        break
                        
        print(f"\nMigration complete for {pinecone_index_name} -> {opensearch_index_name}")
        print(f"Successfully migrated: {migrated_count}")
        print(f"Failed: {failed_count}")
        
    except Exception as e:
        print(f"\nMigration failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    print("Starting Pinecone to OpenSearch Migration...")
    
    # Standard vectors
    pinecone_main = os.environ.get("PINECONE_INDEX_NAME", "almabani-1")
    os_main = os.environ.get("OPENSEARCH_INDEX_NAME", "almabani")
    
    # Price code vectors
    pinecone_pc = os.environ.get("PRICECODE_INDEX_NAME", "almabani-pricecode")
    os_pc = os.environ.get("PRICECODE_INDEX_NAME", "almabani-pricecode") # usually same name 
    
    # Migrate Main 
    await migrate_index(pinecone_main, os_main)
    
    print("-" * 50)
    
    # Migrate Price Codes
    if pinecone_pc != pinecone_main: # If they used different indexes
        await migrate_index(pinecone_pc, os_pc)

if __name__ == "__main__":
    asyncio.run(main())
