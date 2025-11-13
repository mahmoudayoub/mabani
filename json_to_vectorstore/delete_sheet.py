"""
Delete all vectors from a specific sheet in Pinecone index.

Usage:
    python json_to_vectorstore/delete_sheet.py
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from root .env
load_dotenv(Path(__file__).parent.parent / '.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def delete_sheet_from_index(sheet_name: str):
    """
    Delete all vectors from a specific sheet.
    
    Args:
        sheet_name: Name of the sheet to delete (e.g., "1-master_no_ur", "9-PA")
    """
    # Get Pinecone credentials
    api_key = os.getenv('PINECONE_API_KEY')
    index_name = os.getenv('PINECONE_INDEX_NAME', 'almabani-boq')
    
    if not api_key:
        logger.error("PINECONE_API_KEY not found in environment variables")
        return
    
    try:
        # Initialize Pinecone
        logger.info("Connecting to Pinecone...")
        pc = Pinecone(api_key=api_key)
        index = pc.Index(index_name)
        
        # Get index stats before deletion
        stats = index.describe_index_stats()
        total_before = stats.total_vector_count
        logger.info(f"Total vectors in index before deletion: {total_before}")
        
        # Delete vectors by metadata filter
        logger.info(f"Deleting all vectors from sheet: {sheet_name}")
        
        # Use delete with filter
        index.delete(
            filter={"source_sheet": {"$eq": sheet_name}}
        )
        
        logger.info(f"✅ Successfully deleted all vectors from sheet '{sheet_name}'")
        
        # Get index stats after deletion
        stats = index.describe_index_stats()
        total_after = stats.total_vector_count
        deleted_count = total_before - total_after
        
        logger.info(f"Total vectors in index after deletion: {total_after}")
        logger.info(f"Vectors deleted: {deleted_count}")
        
    except Exception as e:
        logger.error(f"Error deleting sheet from index: {e}")
        raise


def main():
    """Main function."""
    print("\n" + "="*60)
    print("Delete Sheet from Pinecone Index")
    print("="*60 + "\n")
    
    # Ask user for sheet name
    sheet_name = input("Enter the sheet name to delete (e.g., '1-master_no_ur', '9-PA'): ").strip()
    
    if not sheet_name:
        logger.error("Sheet name cannot be empty")
        return
    
    # Confirm deletion
    confirm = input(f"\n⚠️  Are you sure you want to delete all vectors from sheet '{sheet_name}'? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        logger.info("Deletion cancelled")
        return
    
    # Delete the sheet
    delete_sheet_from_index(sheet_name)
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
