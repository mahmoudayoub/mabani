"""
Rate Filler Pipeline - Fill missing rates in BOQ Excel files.
Uses Excel I/O, vector search, and 3-stage LLM matching.
Supports async processing to better utilize OpenAI RPM-limited throughput.
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from almabani.config.settings import get_settings
from almabani.core.excel import ExcelIO
from almabani.core.models import MatchResult, MatchStatus, ProcessingReport, ItemType
from almabani.parsers.excel_parser import ExcelParser
from almabani.parsers.hierarchy_processor import HierarchyProcessor
from almabani.rate_matcher.matcher import RateMatcher

logger = logging.getLogger(__name__)


class RateFillerPipeline:
    """Main pipeline for filling missing rates in BOQ Excel files."""
    
    def __init__(self, rate_matcher: RateMatcher, subcategory_indicator: str = 'c'):
        """
        Initialize the pipeline.
        
        Args:
            rate_matcher: Configured RateMatcher instance
            subcategory_indicator: Character indicating subcategory levels
        """
        self.rate_matcher = rate_matcher
        self.excel_io = ExcelIO()
        self.excel_parser = ExcelParser(subcategory_indicator=subcategory_indicator)
        self.hierarchy_processor = HierarchyProcessor(subcategory_indicator=subcategory_indicator)
        
        logger.info("Rate Filler Pipeline initialized")
    
    async def process_file(
        self,
        input_file: Path,
        sheet_name: Optional[str] = None,
        output_file: Optional[Path] = None,
        namespace: str = '',
        workers: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Async variant of process_file using asyncio + RateMatcher async calls.
        """
        settings = get_settings()
        workers = workers if workers is not None else settings.max_workers
        start_time = time.perf_counter()
        
        logger.info(f"[async] Processing file: {input_file}")
        logger.info(f"[async] Using {workers} workers")
        sheets_data = await asyncio.to_thread(self.excel_io.read_excel, str(input_file), sheet_name=sheet_name)
        if not sheets_data:
            raise ValueError(f"No sheets found in {input_file}")
        
        selected_sheet = sheet_name or next(iter(sheets_data.keys()))
        if selected_sheet not in sheets_data:
            raise ValueError(f"Sheet '{selected_sheet}' not found in {input_file}")
        
        df, header_row_idx = sheets_data[selected_sheet]
        columns = self.excel_io.detect_columns(df)
        
        parent_map = await asyncio.to_thread(self._build_parent_map, df, header_row_idx, columns)
        items_to_fill = await asyncio.to_thread(self._extract_items_for_filling, df, header_row_idx, columns, parent_map)
        
        if not items_to_fill:
            logger.warning("[async] No items need filling")
            return {
                'input_file': str(input_file),
                'sheet_name': selected_sheet,
                'items_processed': 0,
                'output_file': None
            }
        
        report = ProcessingReport(total_items=len(items_to_fill))
        worker_count = max(1, workers)
        semaphore = asyncio.Semaphore(worker_count)
        filled_items: List[Dict[str, Any]] = []
        
        async def handle_item(item: Dict[str, Any]):
            nonlocal filled_items
            async with semaphore:
                try:
                    filled_item, result = await self._process_single_item_async(item, namespace)
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
                    logger.error(f"[async] Error processing item {item.get('row_index')}: {e}")
                    report.errors += 1
                    report.error_items.append(str(item.get('row_index')))
        
        await asyncio.gather(*(handle_item(item) for item in items_to_fill))
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = input_file.parent / f"{input_file.stem}_filled_{timestamp}.xlsx"
        
        sheet_results = {
            selected_sheet: {
                'header_row_index': header_row_idx,
                'columns': columns,
                'filled_items': filled_items
            }
        }
        
        output_path = await asyncio.to_thread(
            self.excel_io.write_filled_excel,
            str(input_file),
            str(output_file),
            sheet_results
        )
        
        # Generate summary file
        summary_file = output_file.with_suffix('.txt')
        processing_seconds = time.perf_counter() - start_time
        report.processing_time_seconds = processing_seconds
        summary_content = self._generate_summary(
            input_file=input_file,
            output_file=output_file,
            sheet_name=selected_sheet,
            report=report,
            processing_seconds=processing_seconds
        )
        await asyncio.to_thread(self._write_summary_file, summary_file, summary_content)
        
        logger.info(f"[async] ✓ Pipeline complete!")
        return {
            'input_file': str(input_file),
            'sheet_name': selected_sheet,
            'output_file': output_path,
            'summary_file': str(summary_file),
            'report': report.to_dict()
        }
    
    def _extract_items_for_filling(
        self,
        df,
        header_row_idx: int,
        columns: Dict[str, str],
        parent_map: Dict[int, Dict[str, Optional[str]]]
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
            
            # Extract items needing filling (Level is empty, has Item OR Description)
            has_level = level_val is not None and str(level_val).strip() != ''
            has_item_code = item_val is not None and str(item_val).strip() != ''
            has_desc = desc_val is not None and str(desc_val).strip() != ''
            if (not has_level) and (has_item_code or has_desc):
                parent = None
                grandparent = None
                category_path = None
                map_key = idx + 1  # parent_map uses 1-based row_number
                if map_key in parent_map:
                    parent = parent_map[map_key].get('parent')
                    grandparent = parent_map[map_key].get('grandparent')
                    category_path = parent_map[map_key].get('category_path')
                
                items.append({
                    'row_index': idx,
                    'item_code': str(item_val).strip() if item_val else '',
                    'description': str(desc_val).strip() if desc_val else '',
                    'current_unit': str(unit_val) if unit_val else '',
                    'current_rate': float(rate_val) if rate_val and rate_val != '' else None,
                    'parent': parent,
                    'grandparent': grandparent,
                    'category_path': category_path
                })
        
        return items
    
    def _build_parent_map(
        self,
        df,
        header_row_idx: int,
        columns: Dict[str, str]
    ) -> Dict[int, Dict[str, Optional[str]]]:
        """
        Build a mapping of row_index -> {'parent': ..., 'grandparent': ..., 'category_path': ...}
        using the same hierarchy logic as the parser.
        """
        parser = self.excel_parser
        hierarchy_processor = self.hierarchy_processor
        
        raw_items = parser._extract_raw_items(df, columns, header_row_idx)
        tree = hierarchy_processor._build_hierarchy(raw_items)
        
        parent_map: Dict[int, Dict[str, Optional[str]]] = {}
        
        def walk(nodes: List, parent_desc: Optional[str], grandparent_desc: Optional[str], path: List[str]):
            for node in nodes:
                node_parent = parent_desc
                node_grandparent = grandparent_desc
                path_added = False
                
                # Update lineage if this node is a parent type
                if node.item_type in (ItemType.NUMERIC_LEVEL, ItemType.SUBCATEGORY):
                    node_grandparent = parent_desc
                    node_parent = node.description
                    if node.description:
                        path.append(str(node.description))
                        path_added = True
                
                if node.item_type == ItemType.ITEM and node.row_number is not None:
                    parent_map[node.row_number] = {
                        'parent': node_parent,
                        'grandparent': node_grandparent,
                        'category_path': ' > '.join(path) if path else None
                    }
                
                # Recurse into children
                if node.children:
                    walk(node.children, node_parent, node_grandparent, path)
                
                # Pop path if we added for this node
                if path_added:
                    path.pop()
        
        walk(tree, None, None, [])
        return parent_map

    async def _process_single_item_async(self, item: Dict[str, Any], namespace: str) -> tuple:
        """
        Async variant of _process_single_item.
        """
        result = await self.rate_matcher.find_match(
            item_description=item['description'],
            item_unit=item.get('current_unit', ''),
            item_code=item.get('item_code', ''),
            parent=item.get('parent'),
            grandparent=item.get('grandparent'),
            namespace=namespace,
            category_path=item.get('category_path')
        )
        filled_item = self._process_match_result(item, result)
        return filled_item, result
    
    def _process_match_result(self, item: Dict, result: Dict) -> Dict[str, Any]:
        """Process match result and prepare for Excel writing."""
        filled_item = {
            'row_index': item['row_index'],
            'item_code': item['item_code'],
            'description': item['description'],
            'filled_rate': None,
            'status': 'not_filled',
            'match_type': result.get('match_type', 'none'),
            'reference': '',
            'reasoning': result.get('reasoning', ''),
            'confidence': result.get('confidence', 0)
        }
        
        if result['status'] == 'match':
            filled_item['status'] = 'filled'
            filled_item['filled_rate'] = result.get('rate')
            filled_item['reference'] = result.get('reference', '')
        
        return filled_item

    def _generate_summary(
        self,
        input_file: Path,
        output_file: Path,
        sheet_name: str,
        report: ProcessingReport,
        processing_seconds: Optional[float] = None
    ) -> str:
        """Generate a text summary of the processing results."""
        lines = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration_str = None
        if processing_seconds is not None:
            total_seconds = int(round(processing_seconds))
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"
        
        # Header
        lines.append("=" * 70)
        lines.append("ALMABANI BOQ RATE FILLER - PROCESSING SUMMARY")
        lines.append("=" * 70)
        lines.append("")
        
        # File info
        lines.append("FILE INFORMATION")
        lines.append("-" * 40)
        lines.append(f"  Input File:    {input_file.name}")
        lines.append(f"  Output File:   {output_file.name}")
        lines.append(f"  Sheet:         {sheet_name}")
        lines.append(f"  Generated:     {timestamp}")
        if duration_str:
            lines.append(f"  Processing Time: {duration_str}")
        lines.append("")
        
        # Statistics
        lines.append("PROCESSING STATISTICS")
        lines.append("-" * 40)
        lines.append(f"  Total Items:     {report.total_items}")
        lines.append(f"  Processed:       {report.processed_items}")
        lines.append(f"  Exact Matches:   {report.exact_matches}")
        lines.append(f"  Expert Matches:  {report.expert_matches}")
        lines.append(f"  Estimates:       {report.estimates}")
        lines.append(f"  No Matches:      {report.no_matches}")
        lines.append(f"  Errors:          {report.errors}")
        lines.append("")
        
        # Success rate and ratios
        if report.processed_items > 0:
            filled = report.exact_matches + report.expert_matches + report.estimates
            success_rate = (filled / report.processed_items) * 100
            lines.append(f"  Fill Rate:       {success_rate:.1f}%")
        if report.total_items > 0:
            total = report.total_items
            lines.append("  Ratios over total items:")
            lines.append(f"    Exact:         {(report.exact_matches/total)*100:.1f}%")
            lines.append(f"    Expert:        {(report.expert_matches/total)*100:.1f}%")
            lines.append(f"    Estimates:     {(report.estimates/total)*100:.1f}%")
            lines.append(f"    No Match:      {(report.no_matches/total)*100:.1f}%")
            lines.append(f"    Errors:        {(report.errors/total)*100:.1f}%")
        lines.append("")
        
        # Footer
        lines.append("=" * 70)
        lines.append("END OF SUMMARY")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def _write_summary_file(self, file_path: Path, content: str) -> None:
        """Write summary content to a text file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Summary written to: {file_path}")
