#!/usr/bin/env python3
"""
Delete Pinecone Index and Reprocess All JSON Files
This script will:
1. Delete the existing Pinecone index
2. Process all JSON files from excel_to_json_pipeline output
3. Generate embeddings
4. Upload to fresh Pinecone index
"""
import sys
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from json_processor import JSONProcessor
from embeddings_generator import EmbeddingsGenerator
from pinecone_uploader import PineconeUploader
from exporter import VectorStoreExporter
from pinecone import Pinecone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def delete_index(index_name: str = 'almabani'):
    """Delete the Pinecone index if it exists."""
    load_dotenv()
    
    api_key = os.getenv('PINECONE_API_KEY')
    if not api_key:
        print("❌ Error: PINECONE_API_KEY not found in .env file")
        return False
    
    try:
        pc = Pinecone(api_key=api_key)
        existing_indexes = pc.list_indexes()
        index_names = [idx.name for idx in existing_indexes]
        
        if index_name in index_names:
            print(f"\n🗑️  Deleting index '{index_name}'...")
            pc.delete_index(index_name)
            print(f"✓ Index '{index_name}' deleted successfully")
            return True
        else:
            print(f"\nℹ️  Index '{index_name}' does not exist (nothing to delete)")
            return True
            
    except Exception as e:
        print(f"❌ Error deleting index: {e}")
        return False


def find_json_files():
    """Find all JSON files from excel_to_json_pipeline output."""
    # Check excel_to_json_pipeline output directory
    excel_pipeline_output = Path(__file__).parent.parent / 'excel_to_json_pipeline' / 'output'
    
    if not excel_pipeline_output.exists():
        print(f"\n❌ Error: Excel pipeline output directory not found:")
        print(f"   {excel_pipeline_output}")
        return []
    
    json_files = list(excel_pipeline_output.glob('*.json'))
    
    if not json_files:
        print(f"\n❌ Error: No JSON files found in:")
        print(f"   {excel_pipeline_output}")
        return []
    
    return json_files


def process_json_files(json_files):
    """Process JSON files and extract items."""
    processor = JSONProcessor()
    all_items = []
    
    print(f"\n📂 Processing {len(json_files)} JSON files...")
    
    for json_file in json_files:
        print(f"\n  Processing: {json_file.name}")
        
        try:
            items = processor.process_file(str(json_file))
            all_items.extend(items)
            print(f"    ✓ Extracted {len(items)} items")
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
            continue
    
    return all_items


def export_to_jsonl(items, output_dir):
    """Export items to JSONL format."""
    exporter = VectorStoreExporter(output_dir=output_dir)
    output_file = exporter.export_to_jsonl(items)
    return output_file


def generate_embeddings(items):
    """Generate embeddings for all items."""
    embedder = EmbeddingsGenerator(
        model='text-embedding-3-small',
        batch_size=100
    )
    
    # Show cost estimate
    cost_info = embedder.estimate_cost(len(items))
    print(f"\n💰 Cost Estimate:")
    print(f"   Items: {cost_info['total_items']:,}")
    print(f"   Estimated tokens: {cost_info['estimated_tokens']:,}")
    print(f"   Model: text-embedding-3-small")
    print(f"   Estimated cost: ${cost_info['estimated_cost_usd']} USD")
    
    print("\n🔄 Generating embeddings...")
    items_with_embeddings = embedder.embed_items(items, show_progress=True)
    print(f"✓ Generated {len(items_with_embeddings):,} embeddings")
    
    return items_with_embeddings, embedder


def upload_to_pinecone(items_with_embeddings, embedder):
    """Upload vectors to Pinecone."""
    uploader = PineconeUploader()
    
    print("\n🔧 Creating Pinecone index...")
    uploader.create_index(
        dimension=embedder.get_dimensions(),
        metric='cosine'
    )
    
    print("\n⬆️  Uploading to Pinecone...")
    result = uploader.upload_vectors(
        items_with_embeddings,
        batch_size=100,
        show_progress=True
    )
    
    return result


def main():
    """Main pipeline."""
    print("=" * 80)
    print("DELETE AND REPROCESS PIPELINE")
    print("Pinecone Index → Fresh Start")
    print("=" * 80)
    
    # Load environment variables
    load_dotenv()
    
    # Check for required env vars
    if not os.getenv('OPENAI_API_KEY'):
        print("\n❌ Error: OPENAI_API_KEY not found in .env file")
        return 1
    
    if not os.getenv('PINECONE_API_KEY'):
        print("\n❌ Error: PINECONE_API_KEY not found in .env file")
        return 1
    
    # Warning
    print("\n⚠️  WARNING: This will DELETE all existing vectors in Pinecone!")
    print("⚠️  All previous data will be LOST and replaced with fresh data.")
    print("\nThis script will:")
    print("  1. Delete the 'almabani' Pinecone index")
    print("  2. Process all JSON files from excel_to_json_pipeline/output/")
    print("  3. Generate fresh embeddings")
    print("  4. Upload to a new Pinecone index")
    
    response = input("\n❓ Are you sure you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("\n❌ Cancelled by user")
        return 0
    
    # Step 1: Delete existing index
    print("\n" + "=" * 80)
    print("STEP 1: Delete Existing Index")
    print("=" * 80)
    
    if not delete_index():
        print("\n❌ Failed to delete index")
        return 1
    
    # Step 2: Find JSON files
    print("\n" + "=" * 80)
    print("STEP 2: Find JSON Files")
    print("=" * 80)
    
    json_files = find_json_files()
    if not json_files:
        return 1
    
    print(f"\n✓ Found {len(json_files)} JSON files:")
    for jf in json_files:
        print(f"   - {jf.name}")
    
    # Step 3: Process JSON files
    print("\n" + "=" * 80)
    print("STEP 3: Extract Items from JSON")
    print("=" * 80)
    
    all_items = process_json_files(json_files)
    
    if not all_items:
        print("\n❌ No items extracted")
        return 1
    
    print(f"\n✓ Total items extracted: {len(all_items):,}")
    
    # Step 4: Export to JSONL
    print("\n" + "=" * 80)
    print("STEP 4: Export to JSONL")
    print("=" * 80)
    
    output_dir = Path(__file__).parent / 'output'
    output_file = export_to_jsonl(all_items, str(output_dir))
    print(f"\n✓ Exported to: {output_file}")
    
    # Step 5: Generate embeddings
    print("\n" + "=" * 80)
    print("STEP 5: Generate Embeddings")
    print("=" * 80)
    
    response = input("\n⚠️  Proceed with embedding generation? (y/n): ")
    if response.lower() != 'y':
        print("\n❌ Cancelled by user")
        return 0
    
    items_with_embeddings, embedder = generate_embeddings(all_items)
    
    # Step 6: Upload to Pinecone
    print("\n" + "=" * 80)
    print("STEP 6: Upload to Pinecone")
    print("=" * 80)
    
    result = upload_to_pinecone(items_with_embeddings, embedder)
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ SUCCESS - FRESH START COMPLETE!")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   JSON files processed: {len(json_files)}")
    print(f"   Items extracted: {len(all_items):,}")
    print(f"   Vectors uploaded: {result['uploaded_count']:,}")
    print(f"   Index: {result['index_name']}")
    print(f"   Total vectors in index: {result['total_vectors_in_index']:,}")
    print(f"   Dimensions: {embedder.get_dimensions()}")
    
    print(f"\n🎉 Your vector store has been completely refreshed!")
    print(f"\nNext steps:")
    print(f"   1. Test with rate_filler_pipeline")
    print(f"   2. View in Pinecone console: https://app.pinecone.io/")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
