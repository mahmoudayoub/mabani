#!/usr/bin/env python3
"""
Simple script to process JSON files and upload to Pinecone.
Automatically finds JSON files from excel_to_json_pipeline/output
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Set up path for package imports
json_to_vectorstore_dir = Path(__file__).parent
sys.path.insert(0, str(json_to_vectorstore_dir.parent))

# Now import from the package
from json_to_vectorstore.src.pipeline import VectorStorePreparationPipeline
from json_to_vectorstore.src.embeddings_generator import EmbeddingsGenerator
from json_to_vectorstore.src.pinecone_uploader import PineconeUploader

def main():
    """Main pipeline."""
    print("=" * 80)
    print("Vector Store Preparation & Upload Pipeline")
    print("OpenAI Embeddings → Pinecone (with Enriched Embeddings)")
    print("=" * 80)
    
    # Load environment variables from root .env
    load_dotenv(Path(__file__).parent.parent / '.env')
    
    # Check for required env vars
    if not os.getenv('OPENAI_API_KEY'):
        print("\n❌ Error: OPENAI_API_KEY not found in .env file")
        return 1
    
    if not os.getenv('PINECONE_API_KEY'):
        print("\n❌ Error: PINECONE_API_KEY not found in .env file")
        return 1
    
    # Find JSON files
    excel_output = Path(__file__).parent.parent / 'excel_to_json_pipeline' / 'output'
    json_files = list(excel_output.glob('*.json'))
    
    if not json_files:
        print(f"\n❌ No JSON files found in {excel_output}")
        print("Please run excel_to_json_pipeline first")
        return 1
    
    print(f"\n📁 Found {len(json_files)} JSON file(s) in excel_to_json_pipeline/output")
    
    # Process JSON files and collect all items
    print(f"\n🔄 Step 1: Processing JSON files to extract items...")
    output_dir = Path(__file__).parent / 'output'
    pipeline = VectorStorePreparationPipeline(output_dir=output_dir)
    
    all_items = []
    
    for json_file in json_files:
        print(f"   Processing: {json_file.name}")
        # Process file but don't export yet
        from json_to_vectorstore.src.json_processor import JSONProcessor
        processor = JSONProcessor()
        doc = processor.process_file(json_file)
        all_items.extend(doc.items)
        print(f"      → Extracted {len(doc.items)} items")
    
    if not all_items:
        print("\n❌ No items extracted")
        return 1
    
    print(f"\n✓ Total items extracted: {len(all_items):,}")
    
    # Export ALL items to ONE combined JSONL file
    print(f"\n💾 Step 2: Exporting to single JSONL file...")
    from json_to_vectorstore.src.exporter import VectorStoreExporter
    from json_to_vectorstore.src.models import VectorStoreDocument
    
    exporter = VectorStoreExporter(output_dir=output_dir)
    combined_doc = VectorStoreDocument(
        source_name="combined_all_sheets",
        items=all_items
    )
    output_file = exporter.export_jsonl([combined_doc])
    print(f"✓ Created: {output_file.name} ({len(all_items):,} items)")
    
    # Load items for embedding
    print(f"\n📥 Step 3: Loading items for embedding...")
    import json as json_module
    items = []
    with open(output_file, 'r') as f:
        items = [json_module.loads(line) for line in f]
    
    print(f"✓ Loaded {len(items):,} items")
    
    # Show sample
    if items:
        sample = items[0]
        print(f"\n📋 Sample item:")
        print(f"   ID: {sample.get('id')}")
        text = sample.get('text', '')
        print(f"   Text: {text[:100]}...")
        print(f"   Metadata keys: {list(sample.get('metadata', {}).keys())}")
    
    # Initialize embeddings generator
    print(f"\n🤖 Step 4: Initializing OpenAI embeddings...")
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
    print(f"   Estimated cost: ${cost_info['estimated_cost_usd']:.4f} USD")
    
    # Confirm before proceeding
    response = input("\n⚠️  Proceed with embedding generation and upload? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return 0
    
    # Generate embeddings
    print(f"\n🔄 Step 5: Generating embeddings...")
    items_with_embeddings = embedder.embed_items(items, show_progress=True)
    print(f"✓ Generated {len(items_with_embeddings):,} embeddings")
    
    # Initialize Pinecone
    print(f"\n📤 Step 6: Initializing Pinecone...")
    uploader = PineconeUploader()
    
    # Create/connect to index
    print(f"\n🔧 Setting up Pinecone index...")
    uploader.create_index(
        dimension=embedder.get_dimensions(),
        metric='cosine'
    )
    
    # Upload to Pinecone
    print(f"\n⬆️  Step 7: Uploading to Pinecone...")
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
    print(f"\n🎉 Your enriched vector store is ready!")
    print(f"   All items now include parent/grandparent context in embeddings")
    print(f"\nNext steps:")
    print(f"   1. Test the rate filler pipeline with enriched search")
    print(f"   2. View in Pinecone console: https://app.pinecone.io/")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
