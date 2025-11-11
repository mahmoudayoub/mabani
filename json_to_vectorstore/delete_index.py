#!/usr/bin/env python3
"""
Delete Pinecone Index Only
Simple script to delete the Pinecone index without reprocessing.
Use this if you just want to clear the vector database.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone

def main():
    """Delete the Pinecone index."""
    print("=" * 80)
    print("DELETE PINECONE INDEX")
    print("=" * 80)
    
    # Load environment variables from root .env
    env_file = Path(__file__).parent.parent / '.env'
    load_dotenv(env_file)
    
    api_key = os.getenv('PINECONE_API_KEY')
    if not api_key:
        print("\n❌ Error: PINECONE_API_KEY not found in .env file")
        return 1
    
    index_name = 'almabani'
    
    print(f"\n⚠️  WARNING: This will DELETE the '{index_name}' index!")
    print("⚠️  All vectors will be permanently removed.")
    print("\nYou will need to run process_json_to_vectorstore.py")
    print("to rebuild the vector database.")
    
    response = input(f"\n❓ Delete index '{index_name}'? (yes/no): ")
    if response.lower() != 'yes':
        print("\n❌ Cancelled by user")
        return 0
    
    try:
        pc = Pinecone(api_key=api_key)
        existing_indexes = pc.list_indexes()
        index_names = [idx.name for idx in existing_indexes]
        
        if index_name in index_names:
            print(f"\n🗑️  Deleting index '{index_name}'...")
            pc.delete_index(index_name)
            print(f"\n✅ Index '{index_name}' deleted successfully!")
            print("\nThe vector database is now empty.")
            print("Run this to rebuild:")
            print("  .venv/bin/python json_to_vectorstore/process_json_to_vectorstore.py")
        else:
            print(f"\nℹ️  Index '{index_name}' does not exist")
            print("Nothing to delete.")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
