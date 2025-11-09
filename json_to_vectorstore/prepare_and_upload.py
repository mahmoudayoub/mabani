"""
Complete pipeline: JSON → Embeddings → Pinecone
End-to-end script to prepare and upload BOQ items to vector store.
"""
import sys
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from embeddings_generator import EmbeddingsGenerator
from pinecone_uploader import PineconeUploader

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_jsonl(file_path: Path):
    """Load items from JSONL file."""
    items = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            items.append(json.loads(line))
    return items


def main():
    """Main pipeline."""
    print("=" * 80)
    print("Vector Store Preparation & Upload Pipeline")
    print("OpenAI Embeddings → Pinecone")
    print("=" * 80)
    
    # Load environment variables
    load_dotenv()
    
    # Check for required env vars
    if not os.getenv('OPENAI_API_KEY'):
        print("\n❌ Error: OPENAI_API_KEY not found in .env file")
        print("Please create a .env file with your API keys")
        return 1
    
    if not os.getenv('PINECONE_API_KEY'):
        print("\n❌ Error: PINECONE_API_KEY not found in .env file")
        print("Please create a .env file with your API keys")
        return 1
    
    # Find latest JSONL file
    output_dir = Path(__file__).parent / 'output'
    jsonl_files = sorted(output_dir.glob('vectorstore_items_*.jsonl'), reverse=True)
    
    if not jsonl_files:
        print(f"\n❌ No JSONL files found in {output_dir}")
        print("Please run prepare_vectorstore.py first")
        return 1
    
    input_file = jsonl_files[0]
    print(f"\n📁 Input file: {input_file.name}")
    
    # Load items
    print("\n📥 Loading items...")
    items = load_jsonl(input_file)
    print(f"✓ Loaded {len(items):,} items")
    
    # Show sample
    if items:
        sample = items[0]
        print(f"\n📋 Sample item:")
        print(f"   ID: {sample.get('id')}")
        print(f"   Text: {sample.get('text')[:80]}...")
        print(f"   Metadata keys: {list(sample.get('metadata', {}).keys())}")
    
    # Initialize embeddings generator
    print("\n🤖 Initializing OpenAI embeddings...")
    embedder = EmbeddingsGenerator(
        model='text-embedding-3-small',  # Recommended: good quality, low cost
        batch_size=100
    )
    
    # Show cost estimate
    cost_info = embedder.estimate_cost(len(items))
    print(f"\n💰 Cost Estimate:")
    print(f"   Items: {cost_info['total_items']:,}")
    print(f"   Estimated tokens: {cost_info['estimated_tokens']:,}")
    print(f"   Model: text-embedding-3-small")
    print(f"   Estimated cost: ${cost_info['estimated_cost_usd']} USD")
    
    # Confirm before proceeding
    response = input("\n⚠️  Proceed with embedding generation? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return 0
    
    # Generate embeddings
    print("\n🔄 Generating embeddings...")
    items_with_embeddings = embedder.embed_items(items, show_progress=True)
    print(f"✓ Generated {len(items_with_embeddings):,} embeddings")
    
    # Initialize Pinecone
    print("\n📤 Initializing Pinecone...")
    uploader = PineconeUploader()
    
    # Create/connect to index
    print("\n🔧 Setting up Pinecone index...")
    uploader.create_index(
        dimension=embedder.get_dimensions(),
        metric='cosine'
    )
    
    # Upload to Pinecone
    print("\n⬆️  Uploading to Pinecone...")
    result = uploader.upload_vectors(
        items_with_embeddings,
        batch_size=100,
        show_progress=True
    )
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ SUCCESS!")
    print("=" * 80)
    print(f"\n📊 Upload Summary:")
    print(f"   Uploaded: {result['uploaded_count']:,} vectors")
    print(f"   Index: {result['index_name']}")
    print(f"   Total vectors in index: {result['total_vectors_in_index']:,}")
    print(f"   Dimensions: {embedder.get_dimensions()}")
    
    print(f"\n🎉 Your vector store is ready!")
    print(f"\nNext steps:")
    print(f"   1. Test search: python search_example.py")
    print(f"   2. View in Pinecone console: https://app.pinecone.io/")
    print(f"   3. Build your search interface!")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
