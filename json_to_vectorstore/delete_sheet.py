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
    import time
    
    # Get Pinecone credentials
    api_key = os.getenv('PINECONE_API_KEY')
    index_name = os.getenv('PINECONE_INDEX_NAME', 'almabani')
    
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
        
        # Verify the sheet exists by sampling
        logger.info(f"Verifying sheet '{sheet_name}' exists...")
        sample = index.query(
            vector=[0.0] * 1536,
            top_k=100,
            include_metadata=True,
            filter={"source_sheet": {"$eq": sheet_name}}
        )
        
        if not sample.matches:
            logger.warning(f"⚠️  No vectors found for sheet '{sheet_name}'")
            logger.info("Getting list of available sheets...")
            
            # Get all unique sheets from a sample
            all_sample = index.query(vector=[0.0] * 1536, top_k=100, include_metadata=True)
            available_sheets = set()
            for match in all_sample.matches:
                sheet = match.metadata.get('source_sheet')
                if sheet:
                    available_sheets.add(sheet)
            
            if available_sheets:
                logger.info(f"Available sheets: {', '.join(sorted(available_sheets))}")
            return
        
        logger.info(f"Found {len(sample.matches)} vectors (sample) for sheet '{sheet_name}'")
        
        # Delete vectors by metadata filter
        logger.info(f"Deleting all vectors from sheet: {sheet_name}")
        
        # Use delete with filter
        result = index.delete(
            filter={"source_sheet": {"$eq": sheet_name}}
        )
        
        logger.info(f"✅ Delete operation submitted: {result}")
        
        # Wait for deletion to complete (Pinecone may take a moment)
        logger.info("Waiting 3 seconds for deletion to process...")
        time.sleep(3)
        
        # Get index stats after deletion
        stats = index.describe_index_stats()
        total_after = stats.total_vector_count
        deleted_count = total_before - total_after
        
        if deleted_count > 0:
            logger.info(f"✅ Successfully deleted {deleted_count} vectors from sheet '{sheet_name}'")
        else:
            logger.warning(f"⚠️  No vectors were deleted. This may indicate the sheet name doesn't match.")
        
        logger.info(f"Total vectors in index after deletion: {total_after}")
        
    except Exception as e:
        logger.error(f"Error deleting sheet from index: {e}")
        raise


def main():
    """Main function."""
    print("\n" + "="*60)
    print("Delete Sheet from Pinecone Index")
    print("="*60 + "\n")
    
    # Ask user for sheet name
    sheet_name = input("Enter the sheet name to delete (e.g., '2-Terminal', '3-Hilton'): ").strip()
    
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
