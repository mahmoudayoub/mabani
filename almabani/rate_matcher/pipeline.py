"""
Rate Filler Pipeline - Fill missing rates in BOQ Excel files.
Uses Excel I/O, vector search, and 3-stage LLM matching.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from almabani.core.excel import ExcelIO
from almabani.core.models import MatchResult, MatchStatus, ProcessingReport
from almabani.rate_matcher.matcher import RateMatcher

logger = logging.getLogger(__name__)


class RateFillerPipeline:
    """Main pipeline for filling missing rates in BOQ Excel files."""
    
    def __init__(self, rate_matcher: RateMatcher):
        """
        Initialize the pipeline.
        
        Args:
            rate_matcher: Configured RateMatcher instance
        """
        self.rate_matcher = rate_matcher
        self.excel_io = ExcelIO()
        
        logger.info("Rate Filler Pipeline initialized")
    
    def process_file(
        self,
        input_file: Path,
        sheet_name: Optional[str] = None,
        output_file: Optional[Path] = None,
        namespace: str = '',
        workers: int = 5
    ) -> Dict[str, Any]:
        """
        Process a single Excel file and fill missing rates.
        
        Args:
            input_file: Path to input Excel file
            sheet_name: Name of the sheet to process (None = first sheet)
            output_file: Path to output file (auto-generated if None)
            namespace: Pinecone namespace for searching
            workers: Number of threads for parallel matching
            
        Returns:
            Processing results and statistics
        """
        logger.info(f"Processing file: {input_file}")
        logger.info(f"Sheet: {sheet_name if sheet_name else 'first sheet'}")
        
        # Read Excel file
        sheets_data = self.excel_io.read_excel(str(input_file), sheet_name=sheet_name)
        
        if not sheets_data:
            raise ValueError(f"No sheets found in {input_file}")
        
        selected_sheet = sheet_name
        if selected_sheet is None:
            selected_sheet = next(iter(sheets_data.keys()))
        
        if selected_sheet not in sheets_data:
            raise ValueError(f"Sheet '{selected_sheet}' not found in {input_file}")
        
        df, header_row_idx = sheets_data[selected_sheet]
        columns = self.excel_io.detect_columns(df)
        
        logger.info(f"Detected columns: {columns}")
        
        # Extract items needing filling
        items_to_fill = self._extract_items_for_filling(df, header_row_idx, columns)
        
        logger.info(f"Found {len(items_to_fill)} items needing rate filling")
        
        if not items_to_fill:
            logger.warning("No items need filling")
            return {
                'input_file': str(input_file),
                'sheet_name': sheet_name,
                'items_processed': 0,
                'output_file': None
            }
        
        # Process items (find matches)
        filled_items = []
        report = ProcessingReport(total_items=len(items_to_fill))
        
        worker_count = max(1, workers)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_item = {
                executor.submit(self._process_single_item, item, namespace): item
                for item in items_to_fill
            }
            
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    filled_item, result = future.result()
                    filled_items.append(filled_item)
                    
                    report.processed_items += 1
                    if result['status'] == 'match':
                        if result['match_type'] == 'exact':
                            report.exact_matches += 1
                        elif result['match_type'] == 'close':
                            report.expert_matches += 1
                        elif result['match_type'] == 'approximation':
                            report.estimates += 1
                    else:
                        report.no_matches += 1
                except Exception as e:
                    logger.error(f"Error processing item {item.get('row_index')}: {e}")
                    report.errors += 1
                    report.error_items.append(str(item.get('row_index')))
        
        # Generate output file path if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = input_file.parent / f"{input_file.stem}_filled_{timestamp}.xlsx"
        
        # Write filled Excel
        sheet_results = {
            selected_sheet: {
                'header_row_index': header_row_idx,
                'columns': columns,
                'filled_items': filled_items
            }
        }
        
        output_path = self.excel_io.write_filled_excel(
            str(input_file),
            str(output_file),
            sheet_results
        )
        
        logger.info(f"✓ Pipeline complete!")
        logger.info(f"  Processed: {report.processed_items}/{report.total_items}")
        logger.info(f"  Exact matches: {report.exact_matches}")
        logger.info(f"  Expert matches: {report.expert_matches}")
        logger.info(f"  Estimates: {report.estimates}")
        logger.info(f"  No matches: {report.no_matches}")
        logger.info(f"  Errors: {report.errors}")
        logger.info(f"  Output: {output_path}")
        
        return {
            'input_file': str(input_file),
            'sheet_name': selected_sheet,
            'output_file': output_path,
            'report': report.to_dict()
        }
    
    def _extract_items_for_filling(
        self,
        df,
        header_row_idx: int,
        columns: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract items that need rate filling.
        
        Logic: If Level is EMPTY and row contains an Item → Process for filling
        """
        items = []
        
        level_col = columns.get('level')
        item_col = columns.get('item')
        desc_col = columns.get('description')
        unit_col = columns.get('unit')
        rate_col = columns.get('rate')
        
        # Parent tracking stacks
        level_stack = []
        c_level_stack = []
        
        for idx in range(header_row_idx + 1, len(df)):
            row = df.iloc[idx]
            
            level_val = row.get(level_col) if level_col else None
            item_val = row.get(item_col) if item_col else None
            desc_val = row.get(desc_col) if desc_col else None
            unit_val = row.get(unit_col) if unit_col else None
            rate_val = row.get(rate_col) if rate_col else None
            
            # Clean None/NaN values
            import pandas as pd
            level_val = None if pd.isna(level_val) else level_val
            item_val = None if pd.isna(item_val) else item_val
            desc_val = None if pd.isna(desc_val) else desc_val
            unit_val = None if pd.isna(unit_val) else unit_val
            rate_val = None if pd.isna(rate_val) else rate_val
            
            # Update parent stacks
            if level_val is not None:
                level_str = str(level_val).strip()
                
                # Check if numeric level
                if level_str.isdigit():
                    # Update level stack
                    level_num = int(level_str)
                    while level_stack and level_stack[-1][0] >= level_num:
                        level_stack.pop()
                    if desc_val:
                        level_stack.append((level_num, desc_val))
                    c_level_stack = []
                
                # Check if c-level
                elif level_str.lower() == 'c':
                    if desc_val:
                        c_level_stack.append(desc_val)
            
            # Extract items needing filling (Level is empty, has Item)
            if (level_val is None or str(level_val).strip() == '') and item_val is not None:
                # Get parent/grandparent
                parent = c_level_stack[-1] if c_level_stack else (level_stack[-1][1] if level_stack else None)
                grandparent = None
                if len(c_level_stack) >= 2:
                    grandparent = c_level_stack[-2]
                elif c_level_stack and len(level_stack) >= 1:
                    grandparent = level_stack[-1][1]
                elif len(level_stack) >= 2:
                    grandparent = level_stack[-2][1]
                
                items.append({
                    'row_index': idx,
                    'item_code': str(item_val) if item_val else '',
                    'description': str(desc_val) if desc_val else '',
                    'current_unit': str(unit_val) if unit_val else '',
                    'current_rate': float(rate_val) if rate_val and rate_val != '' else None,
                    'parent': parent,
                    'grandparent': grandparent
                })
        
        return items
    
    def _process_single_item(self, item: Dict[str, Any], namespace: str) -> tuple:
        """
        Process a single item through the rate matcher.
        
        Returns:
            Tuple of (filled_item, match_result)
        """
        result = self.rate_matcher.find_match(
            item_description=item['description'],
            item_unit=item.get('current_unit', ''),
            item_code=item.get('item_code', ''),
            parent=item.get('parent'),
            grandparent=item.get('grandparent'),
            namespace=namespace
        )
        
        filled_item = self._process_match_result(item, result)
        return filled_item, result
    
    def _process_match_result(self, item: Dict, result: Dict) -> Dict[str, Any]:
        """Process match result and prepare for Excel writing."""
        filled_item = {
            'row_index': item['row_index'],
            'item_code': item['item_code'],
            'description': item['description'],
            'filled_unit': None,
            'filled_rate': None,
            'status': 'not_filled',
            'match_type': result.get('match_type', 'none'),
            'reference': '',
            'reasoning': result.get('reasoning', ''),
            'confidence': result.get('confidence', 0)
        }
        
        if result['status'] == 'match':
            filled_item['status'] = 'filled'
            filled_item['filled_unit'] = result.get('unit', item.get('current_unit'))
            filled_item['filled_rate'] = result.get('rate')
            filled_item['reference'] = result.get('reference', '')
        
        return filled_item
