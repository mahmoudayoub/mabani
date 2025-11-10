#!/usr/bin/env python3
"""
Rate Filler Pipeline - Main Script
Auto-fill missing unit rates in Excel BOQ using vector search + LLM validation.

New Logic:
- Reads Excel file (like excel_to_json_pipeline input)
- For each row where Level is EMPTY and Item exists:
  - Embed description
  - Search top-K similar items (>0.76 similarity)
  - LLM validates based on description + unit only
  - Fill unit and/or rate if matched
  - Mark red if not matched
"""
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from tqdm import tqdm

from rate_filler_pipeline.src import ExcelReader, RateMatcher, ExcelWriter

# Load environment variables
load_dotenv()

# Setup logging - logs go to rate_filler_pipeline/logs/
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"rate_filler_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def run_pipeline(
    input_excel: str,
    sheet_name: str,
    output_excel: Optional[str] = None,
    similarity_threshold: float = 0.7,
    top_k: int = 6
) -> str:
    """
    Run the rate filling pipeline on a specific sheet.
    
    Args:
        input_excel: Path to input Excel file
        sheet_name: Name of the sheet to process
        output_excel: Path to output Excel file (auto-generated if None)
        similarity_threshold: Minimum similarity score for candidates
        top_k: Number of candidates to retrieve
        
    Returns:
        Path to output Excel file
    """
    print("=" * 80)
    print("BOQ RATE FILLER PIPELINE")
    print("Vector Search + LLM Validation + Hierarchical Context")
    print("=" * 80)
    
    input_path = Path(input_excel)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_excel}")
    
    # Generate output filename if not provided
    if output_excel is None:
        output_dir = Path(__file__).parent / 'output'
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_excel = str(output_dir / f"{input_path.stem}_filled_{timestamp}.xlsx")
    
    print(f"\n📥 Input:  {input_path}")
    print(f"� Sheet:  {sheet_name}")
    print(f"�📤 Output: {output_excel}")
    print(f"🎯 Settings:")
    print(f"   - Similarity threshold: {similarity_threshold}")
    print(f"   - Top-K candidates: {top_k}")
    print(f"   - Using enriched embeddings (with parent/grandparent context)")
    
    # Step 1: Read Excel
    print("\n" + "=" * 80)
    print("STEP 1: Reading Excel File")
    print("=" * 80)
    
    reader = ExcelReader()
    sheets = reader.read_excel(str(input_path), sheet_name=sheet_name)
    
    if not sheets:
        logger.error("No sheets found in Excel file")
        sys.exit(1)
    
    # Step 2: Initialize Rate Matcher
    print("\n" + "=" * 80)
    print("STEP 2: Initializing Rate Matcher")
    print("=" * 80)
    
    matcher = RateMatcher(
        similarity_threshold=similarity_threshold,
        top_k=top_k
    )
    
    print("✓ Rate matcher ready")
    
    # Step 3: Process each sheet
    print("\n" + "=" * 80)
    print("STEP 3: Processing Sheets")
    print("=" * 80)
    
    sheet_results = {}
    total_items = 0
    total_filled = 0
    total_not_filled = 0
    
    for sheet_name, (df, header_row_idx) in sheets.items():
        print(f"\n📄 Sheet: '{sheet_name}'")
        
        # Extract items that need filling
        extraction_result = reader.extract_items_for_filling(df, header_row_idx)
        
        items_to_fill = extraction_result['items']
        if not items_to_fill:
            print(f"  ℹ️  No items need filling in this sheet")
            continue
        
        print(f"  Found {len(items_to_fill)} items needing filling")
        print(f"    - Missing unit: {extraction_result['needs_unit']}")
        print(f"    - Missing rate: {extraction_result['needs_rate']}")
        
        # Process each item
        filled_items = []
        
        print(f"\n  Processing items...")
        for item in tqdm(items_to_fill, desc=f"  {sheet_name}", unit="item"):
            # Search for matches with enriched context
            match_result = matcher.find_matches(
                item_description=item['description'],
                item_code=item['item_code'],
                parent=item.get('parent'),
                grandparent=item.get('grandparent')
            )
            
            filled_item = {
                'row_index': item['row_index'],
                'item_code': item['item_code'],
                'description': item['description'],
                'needs_unit': item['needs_unit'],
                'needs_rate': item['needs_rate']
            }
            
            if match_result['status'] == 'match':
                # Fill unit and/or rate
                filled_item['status'] = 'filled'
                
                if item['needs_unit'] and match_result['unit']:
                    filled_item['filled_unit'] = match_result['unit']
                
                if item['needs_rate'] and match_result['rate'] is not None:
                    filled_item['filled_rate'] = match_result['rate']
                
                # Add match info for report
                filled_item['match_info'] = {
                    'source': match_result['matches'][0].get('project', 'Unknown') if match_result['matches'] else 'Unknown',
                    'reasoning': match_result.get('reasoning', 'Matched by LLM validation'),
                    'num_matches': len(match_result['matches'])
                }
                
                total_filled += 1
                
            else:
                # Not filled - mark for red coloring
                filled_item['status'] = 'not_filled'
                filled_item['reason'] = 'No candidates above similarity threshold' if not match_result.get('candidates') else 'No exact match found by LLM'
                total_not_filled += 1
            
            filled_items.append(filled_item)
        
        # Store results for this sheet
        sheet_results[sheet_name] = {
            'dataframe': extraction_result['dataframe'],
            'header_row_index': header_row_idx,
            'columns': extraction_result['columns'],
            'filled_items': filled_items
        }
        
        total_items += len(items_to_fill)
        
        print(f"\n  ✓ Sheet processed:")
        print(f"    - Filled: {sum(1 for i in filled_items if i['status'] == 'filled')}")
        print(f"    - Not filled: {sum(1 for i in filled_items if i['status'] == 'not_filled')}")
    
    if total_items == 0:
        print("\n❌ No items found needing filling in any sheet")
        sys.exit(1)
    
    # Step 4: Write output Excel
    print("\n" + "=" * 80)
    print("STEP 4: Writing Output")
    print("=" * 80)
    
    writer = ExcelWriter()
    
    # Write filled Excel with color coding
    output_path = writer.write_filled_excel(
        input_file=str(input_path),
        output_file=str(output_excel),
        sheet_results=sheet_results
    )
    
    # Write text report
    report_file = str(output_excel).replace('.xlsx', '_report.txt')
    writer.write_report(
        output_file=report_file,
        sheet_results=sheet_results,
        summary={
            'total_items': total_items,
            'filled': total_filled,
            'not_filled': total_not_filled
        }
    )
    
    # Final summary
    print("\n" + "=" * 80)
    print("✅ PIPELINE COMPLETE")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   Total items processed: {total_items}")
    print(f"   Successfully filled: {total_filled} ({total_filled/total_items*100:.1f}%)")
    print(f"   Not filled: {total_not_filled} ({total_not_filled/total_items*100:.1f}%)")
    print(f"\n📤 Output files:")
    print(f"   Excel: {output_path}")
    print(f"   Report: {report_file}")
    print(f"\n💡 Check the Excel file:")
    print(f"   🟢 Green cells = Successfully filled")
    print(f"   🔴 Red cells = No match found")
    
    return output_path


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python fill_rates.py <input_excel> <sheet_name> [output_excel]")
        print("\nExample: python fill_rates.py input.xlsx 'Terminal' output.xlsx")
        sys.exit(1)
    
    input_excel = sys.argv[1]
    sheet_name = sys.argv[2]
    output_excel = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        run_pipeline(input_excel, sheet_name, output_excel)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
