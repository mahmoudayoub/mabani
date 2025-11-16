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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from rate_filler_pipeline.src import ExcelReader, RateMatcher, ExcelWriter

# Load environment variables from root .env
load_dotenv(Path(__file__).parent.parent / '.env')

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
    top_k: int = 6,
    max_workers: int = 5
) -> str:
    """
    Run the rate filling pipeline on a specific sheet.
    
    Args:
        input_excel: Path to input Excel file
        sheet_name: Name of the sheet to process
        output_excel: Path to output Excel file (auto-generated if None)
        similarity_threshold: Minimum similarity score for candidates
        top_k: Number of candidates to retrieve
        max_workers: Number of parallel workers for processing items (default: 5)
        
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
    print(f"📄 Sheet:  {sheet_name}")
    print(f"📤 Output: {output_excel}")
    print(f"🎯 Settings:")
    print(f"   - Similarity threshold: {similarity_threshold}")
    print(f"   - Top-K candidates: {top_k}")
    print(f"   - Parallel workers: {max_workers}")
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
        
        # Process items in parallel
        filled_items = []
        
        # Thread-safe counter for logging
        progress_lock = threading.Lock()
        
        def process_single_item(item: Dict[str, Any]) -> Dict[str, Any]:
            """
            Process a single item (runs in parallel thread).
            Returns filled_item dictionary.
            """
            try:
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
                    filled_item['match_type'] = match_result.get('match_type', 'exact')
                    
                    if item['needs_unit'] and match_result['unit']:
                        filled_item['filled_unit'] = match_result['unit']
                    
                    if item['needs_rate'] and match_result['rate'] is not None:
                        filled_item['filled_rate'] = match_result['rate']
                    
                    # Add reference string
                    filled_item['reference'] = match_result.get('reference', '')
                    
                    # Add reasoning
                    filled_item['reasoning'] = match_result.get('reasoning', '')
                    
                    # Add stage information
                    filled_item['stage'] = match_result.get('stage', 'matcher')
                    
                    # Add confidence for close/approximation matches
                    match_type = match_result.get('match_type', 'exact')
                    if match_type in ['close', 'approximation']:
                        filled_item['confidence'] = match_result.get('confidence', 0)
                    
                    # Add adjustment for approximation matches
                    if match_type == 'approximation':
                        filled_item['adjustment'] = match_result.get('adjustment', '')
                    
                    # Add match info for report
                    filled_item['match_info'] = {
                        'source': match_result['matches'][0].get('project', 'Unknown') if match_result['matches'] else 'Unknown',
                        'reasoning': match_result.get('reasoning', 'Matched by LLM validation'),
                        'num_matches': len(match_result['matches']),
                        'match_type': match_type,
                        'stage': match_result.get('stage', 'matcher'),
                        'confidence': match_result.get('confidence', 100) if match_type == 'exact' else match_result.get('confidence', 0),
                        'adjustment': match_result.get('adjustment', '') if match_type == 'approximation' else ''
                    }
                    
                else:
                    # Not filled - mark for red coloring
                    filled_item['status'] = 'not_filled'
                    filled_item['match_type'] = 'none'
                    filled_item['reference'] = ''
                    filled_item['reasoning'] = match_result.get('reasoning', 'No candidates above similarity threshold' if not match_result.get('candidates') else 'No match found by LLM')
                    filled_item['reason'] = 'No candidates above similarity threshold' if not match_result.get('candidates') else 'No match found by LLM'
                
                return filled_item
                
            except Exception as e:
                # Handle errors gracefully - return not_filled status
                logger.error(f"Error processing item {item.get('item_code', 'unknown')}: {e}", exc_info=True)
                return {
                    'row_index': item['row_index'],
                    'item_code': item['item_code'],
                    'description': item['description'],
                    'needs_unit': item['needs_unit'],
                    'needs_rate': item['needs_rate'],
                    'status': 'not_filled',
                    'match_type': 'error',
                    'reference': '',
                    'reasoning': f'Error during processing: {str(e)}',
                    'reason': f'Error: {str(e)}'
                }
        
        print(f"\n  Processing items in parallel ({max_workers} workers)...")
        
        # Use ThreadPoolExecutor for parallel processing
        # Store results with their original index to maintain order
        results_with_index = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all items and track their original order
            future_to_index = {
                executor.submit(process_single_item, item): idx 
                for idx, item in enumerate(items_to_fill)
            }
            
            # Process completed futures with progress bar
            with tqdm(total=len(items_to_fill), desc=f"  {sheet_name}", unit="item") as pbar:
                for future in as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        filled_item = future.result()
                        results_with_index.append((idx, filled_item))
                        
                        # Update counters
                        if filled_item['status'] == 'filled':
                            with progress_lock:
                                total_filled += 1
                        else:
                            with progress_lock:
                                total_not_filled += 1
                        
                    except Exception as e:
                        logger.error(f"Future failed for item at index {idx}: {e}")
                        # Create error result
                        item = items_to_fill[idx]
                        error_result = {
                            'row_index': item['row_index'],
                            'item_code': item['item_code'],
                            'description': item['description'],
                            'needs_unit': item['needs_unit'],
                            'needs_rate': item['needs_rate'],
                            'status': 'not_filled',
                            'match_type': 'error',
                            'reference': '',
                            'reasoning': f'Processing error: {str(e)}',
                            'reason': f'Error: {str(e)}'
                        }
                        results_with_index.append((idx, error_result))
                        with progress_lock:
                            total_not_filled += 1
                    
                    pbar.update(1)
        
        # Sort results by original index to maintain order
        results_with_index.sort(key=lambda x: x[0])
        filled_items = [result for _, result in results_with_index]
        
        # Store results for this sheet
        sheet_results[sheet_name] = {
            'dataframe': extraction_result['dataframe'],
            'header_row_index': header_row_idx,
            'columns': extraction_result['columns'],
            'filled_items': filled_items
        }
        
        total_items += len(items_to_fill)
        
        # Count exact and similar matches
        exact_matches = sum(1 for i in filled_items if i['status'] == 'filled' and i.get('match_type') == 'exact')
        close_matches = sum(1 for i in filled_items if i['status'] == 'filled' and i.get('match_type') == 'close')
        approx_matches = sum(1 for i in filled_items if i['status'] == 'filled' and i.get('match_type') == 'approximation')
        
        print(f"\n  ✓ Sheet processed:")
        print(f"    - Exact matches: {exact_matches}")
        print(f"    - Close matches: {close_matches}")
        print(f"    - Approximation matches: {approx_matches}")
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
    
    # Count total exact, close, and approximation matches
    total_exact = sum(sum(1 for i in result['filled_items'] if i['status'] == 'filled' and i.get('match_type') == 'exact') 
                      for result in sheet_results.values())
    total_close = sum(sum(1 for i in result['filled_items'] if i['status'] == 'filled' and i.get('match_type') == 'close') 
                      for result in sheet_results.values())
    total_approx = sum(sum(1 for i in result['filled_items'] if i['status'] == 'filled' and i.get('match_type') == 'approximation') 
                       for result in sheet_results.values())
    
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
    print(f"     - Exact matches: {total_exact} ({total_exact/total_items*100:.1f}%)")
    print(f"     - Close matches: {total_close} ({total_close/total_items*100:.1f}%)")
    print(f"     - Approximation matches: {total_approx} ({total_approx/total_items*100:.1f}%)")
    print(f"   Not filled: {total_not_filled} ({total_not_filled/total_items*100:.1f}%)")
    print(f"\n📤 Output files:")
    print(f"   Excel: {output_path}")
    print(f"   Report: {report_file}")
    print(f"\n💡 Check the Excel file:")
    print(f"   🟢 Green cells = Exact match")
    print(f"   🟡 Yellow cells = Close match (70-95% confidence)")
    print(f"   🔵 Blue cells = Approximation match (50-69% confidence)")
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
