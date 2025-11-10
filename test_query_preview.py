#!/usr/bin/env python3
"""
Test script to preview what gets sent to embedding API and LLM
WITHOUT actually making the requests.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from rate_filler_pipeline.src.excel_reader import ExcelReader
from dotenv import load_dotenv

load_dotenv()

def preview_queries(excel_file: str, sheet_name: str, num_samples: int = 5):
    """Preview what queries will be sent."""
    
    print("=" * 80)
    print("QUERY PREVIEW - What Gets Sent to APIs")
    print("=" * 80)
    
    # Read Excel
    input_dir = Path(__file__).parent / 'rate_filler_pipeline' / 'input'
    input_path = input_dir / excel_file
    
    print(f"\nReading: {input_path}")
    print(f"Sheet: {sheet_name}")
    
    reader = ExcelReader()
    sheets = reader.read_excel(str(input_path), sheet_name)
    
    # Get the sheet data
    if sheet_name not in sheets:
        print(f"Sheet '{sheet_name}' not found!")
        return
    
    df, header_row_idx = sheets[sheet_name]
    
    # Extract items that need filling (same as pipeline does)
    extraction_result = reader.extract_items_for_filling(df, header_row_idx)
    items_list = extraction_result['items']
    
    print(f"\nTotal items to process: {len(items_list)}")
    print(f"  - Missing unit: {extraction_result['needs_unit']}")
    print(f"  - Missing rate: {extraction_result['needs_rate']}")
    print(f"\nShowing first {min(num_samples, len(items_list))} items:\n")
    
    for idx, item in enumerate(items_list[:num_samples], 1):
        print("=" * 80)
        print(f"ITEM {idx}")
        print("=" * 80)
        
        description = item.get('description', '')
        parent = item.get('parent', '')
        grandparent = item.get('grandparent', '')
        unit = item.get('unit', '')
        
        print(f"\n📋 ITEM DETAILS:")
        print(f"   Description: {description}")
        print(f"   Unit: {unit or 'EMPTY'}")
        print(f"   Parent: {parent or 'NONE'}")
        print(f"   Grandparent: {grandparent or 'NONE'}")
        
        # Build embedding query (same as rate_matcher.py does)
        text_parts = []
        if grandparent:
            text_parts.append(grandparent)
        if parent:
            text_parts.append(parent)
        text_parts.append(description)
        
        enriched_query = " | ".join(text_parts)
        
        print(f"\n🔍 EMBEDDING QUERY (sent to OpenAI embeddings API):")
        print(f"   '{enriched_query}'")
        print(f"\n   Length: {len(enriched_query)} characters")
        
        # Show what would be in LLM prompt (target section)
        print(f"\n🤖 LLM VALIDATION PROMPT (TARGET SECTION):")
        print("   " + "-" * 76)
        
        target_info = f"   Description: {description}"
        if parent:
            target_info = f"   Parent: {parent}\n{target_info}"
        if grandparent:
            target_info = f"   Grandparent: {grandparent}\n{target_info}"
        
        print(target_info)
        print("   " + "-" * 76)
        
        print(f"\n   Note: After vector search, LLM will also receive 6 candidates")
        print(f"         (each with description, unit, parent, grandparent)")
        
        print("\n")
    
    if len(items_list) > num_samples:
        print(f"... and {len(items_list) - num_samples} more items\n")
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total items: {len(items_list)}")
    print(f"Each item will:")
    print(f"  1. Generate embedding for: [grandparent] | [parent] | [description]")
    print(f"  2. Search vector store (similarity threshold: 0.7)")
    print(f"  3. Send top 6 candidates to LLM with hierarchical context")
    print(f"  4. LLM validates matches using description + unit + hierarchy")
    print("=" * 80)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python test_query_preview.py <filename.xlsx> <sheet_name> [num_samples]")
        print("\nExample:")
        print("  python test_query_preview.py Book_2.xlsx '9-PA' 10")
        sys.exit(1)
    
    filename = sys.argv[1]
    sheet = sys.argv[2]
    num = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    preview_queries(filename, sheet, num)
