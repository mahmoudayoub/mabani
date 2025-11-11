#!/usr/bin/env python3
"""
Simple script to query the vector store.
Usage: python3 json_to_vectorstore/query_vectorstore.py "your search text"
"""
import sys
import os
from pathlib import Path
from openai import OpenAI
from pinecone import Pinecone
from dotenv import load_dotenv

# Load environment from root .env
load_dotenv(Path(__file__).parent.parent / '.env')


def query_vectorstore(query_text: str, top_k: int = 5):
    """
    Query the vector store with text.
    
    Args:
        query_text: Text to search for
        top_k: Number of results to return
    """
    print("=" * 80)
    print("VECTOR STORE QUERY")
    print("=" * 80)
    print(f"\nQuery: {query_text}")
    print(f"Top-K: {top_k}")
    print()
    
    # Check API keys
    openai_key = os.getenv('OPENAI_API_KEY')
    pinecone_key = os.getenv('PINECONE_API_KEY')
    
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not found in .env file")
        return
    
    if not pinecone_key:
        print("❌ Error: PINECONE_API_KEY not found in .env file")
        return
    
    # Initialize OpenAI
    print("🔧 Initializing OpenAI...")
    openai_client = OpenAI(api_key=openai_key)
    
    # Initialize Pinecone
    print("🔧 Initializing Pinecone...")
    pc = Pinecone(api_key=pinecone_key)
    index = pc.Index("almabani")
    
    # Generate embedding for query
    print("🤖 Generating embedding...")
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query_text
    )
    query_vector = response.data[0].embedding
    
    # Search
    print("🔍 Searching...")
    search_results = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True
    )
    
    # Display results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    if not search_results.matches:
        print("\n❌ No results found")
        return
    
    for i, match in enumerate(search_results.matches, 1):
        score = match.score
        metadata = match.metadata
        text = metadata.get('text', 'N/A')
        
        print(f"\n{i}. Score: {score:.4f}")
        print(f"   Description: {text}")
        print(f"   Unit: {metadata.get('unit', 'N/A')}")
        print(f"   Rate: {metadata.get('rate', 'N/A')}")
        print(f"   Code: {metadata.get('item_code', 'N/A')}")
        print(f"   Project: {metadata.get('source_sheet', 'N/A')}")
        print("-" * 80)
    
    print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python query_vectorstore.py \"your search text\" [top_k]")
        print()
        print("Examples:")
        print('  python query_vectorstore.py "concrete foundation"')
        print('  python query_vectorstore.py "excavation" 10')
        print()
        return 1
    
    query_text = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    query_vectorstore(query_text, top_k)
    return 0


if __name__ == '__main__':
    sys.exit(main())
