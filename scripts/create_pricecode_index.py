
import os
import sys
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec, PodSpec
from dotenv import load_dotenv

# Load env from root
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(env_path, override=True)

api_key = os.getenv('PINECONE_API_KEY')
index_name = os.getenv('PRICECODE_INDEX_NAME', 'almabani-pricecode')
environment = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1')

print(f"Creating index: {index_name}")
print(f"Environment: {environment}")

pc = Pinecone(api_key=api_key)

# Check if exists
existing = pc.list_indexes().names()
if index_name in existing:
    print(f"Index {index_name} already exists.")
    sys.exit(0)

# Create Serverless Index (AWS/us-east-1)
try:
    pc.create_index(
        name=index_name,
        dimension=1536, # text-embedding-3-small
        metric='cosine',
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )
    print(f"Successfully created index: {index_name}")
except Exception as e:
    print(f"Failed to create index: {e}")
    sys.exit(1)
