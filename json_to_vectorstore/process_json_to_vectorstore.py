#!/usr/bin/env python3
"""
Simple script to process JSON files and upload to Pinecone.
Automatically finds JSON files from excel_to_json_pipeline/output
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
    print()
    workers_input = input("Number of parallel workers for processing (default: 5, recommended: 3-10): ").strip()
    max_workers = 5
    if workers_input:
        try:
            max_workers = int(workers_input)
            if max_workers < 1:
                print("Invalid number, using default: 5")
                max_workers = 5
            elif max_workers > 20:
                print("⚠️  Warning: High worker count may hit API rate limits. Using 20 as maximum.")
                max_workers = 20
        except ValueError:
            print("Invalid input, using default: 5")
            max_workers = 5
    
    print(f"Using {max_workers} parallel workers")
    print()
    
    response = input("⚠️  Proceed with embedding generation and upload? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return 0
    
    # Initialize Pinecone first
    print(f"\n📤 Step 5: Initializing Pinecone...")
    uploader = PineconeUploader()
    
    # Create/connect to index
    print(f"\n🔧 Setting up Pinecone index...")
    uploader.create_index(
        dimension=embedder.get_dimensions(),
        metric='cosine'
    )
    
    # Split items into chunks for parallel processing
    chunk_size = max(100, len(items) // max_workers)  # At least 100 items per chunk
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
    
    print(f"\n🔄 Step 6: Processing {len(chunks)} chunks in parallel ({max_workers} workers)...")
    print(f"   Chunk size: ~{chunk_size} items per chunk")
    
    # Thread-safe counters
    progress_lock = threading.Lock()
    total_embedded = 0
    total_uploaded = 0
    
    def process_chunk(chunk_items, chunk_idx):
        """Process a chunk: generate embeddings and upload to Pinecone."""
        try:
            # Generate embeddings for this chunk
            chunk_with_embeddings = embedder.embed_items(chunk_items, show_progress=False)
            
            # Upload to Pinecone immediately
            chunk_result = uploader.upload_vectors(
                chunk_with_embeddings,
                batch_size=100,
                show_progress=False
            )
            
            return {
                'chunk_idx': chunk_idx,
                'embedded': len(chunk_with_embeddings),
                'uploaded': chunk_result['uploaded_count'],
                'success': True
            }
        except Exception as e:
            return {
                'chunk_idx': chunk_idx,
                'embedded': 0,
                'uploaded': 0,
                'success': False,
                'error': str(e)
            }
    
    # Process chunks in parallel with progress tracking
    from tqdm import tqdm
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all chunks
        future_to_chunk = {
            executor.submit(process_chunk, chunk, idx): idx
            for idx, chunk in enumerate(chunks)
        }
        
        # Track progress
        with tqdm(total=len(items), desc="  Processing items", unit="item") as pbar:
            for future in as_completed(future_to_chunk):
                result = future.result()
                results.append(result)
                
                if result['success']:
                    with progress_lock:
                        total_embedded += result['embedded']
                        total_uploaded += result['uploaded']
                    pbar.update(result['embedded'])
                else:
                    print(f"\n⚠️  Chunk {result['chunk_idx']} failed: {result.get('error', 'Unknown error')}")
                    pbar.update(len(chunks[result['chunk_idx']]))
    
    # Check for failures
    failed_chunks = [r for r in results if not r['success']]
    if failed_chunks:
        print(f"\n⚠️  Warning: {len(failed_chunks)} chunks failed")
        for failed in failed_chunks:
            print(f"   Chunk {failed['chunk_idx']}: {failed.get('error', 'Unknown error')}")
    
    print(f"\n✓ Embedded: {total_embedded:,} items")
    print(f"✓ Uploaded: {total_uploaded:,} vectors")
    
    # Get final index stats
    print(f"\n📊 Step 7: Getting final index stats...")
    if uploader.index is None:
        raise RuntimeError("Pinecone index not initialized")
    index_stats = uploader.index.describe_index_stats()
    total_in_index = index_stats.total_vector_count
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ SUCCESS!")
    print("=" * 80)
    print(f"\n📊 Upload Summary:")
    print(f"   Embedded: {total_embedded:,} items")
    print(f"   Uploaded: {total_uploaded:,} vectors")
    print(f"   Index: {uploader.index_name}")
    print(f"   Total vectors in index: {total_in_index:,}")
    print(f"   Dimensions: {embedder.get_dimensions()}")
    if failed_chunks:
        print(f"   ⚠️  Failed chunks: {len(failed_chunks)}")
    print(f"\n🎉 Your enriched vector store is ready!")
    print(f"   All items now include parent/grandparent context in embeddings")
    print(f"\nNext steps:")
    print(f"   1. Test the rate filler pipeline with enriched search")
    print(f"   2. View in Pinecone console: https://app.pinecone.io/")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
