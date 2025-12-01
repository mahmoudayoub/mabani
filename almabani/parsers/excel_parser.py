"""
BOQ Excel Parser - Parse Excel files into hierarchical JSON.
Uses shared models and Excel I/O from core modules.
"""
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import pandas as pd
import re

from almabani.core.models import HierarchyItem, SheetData, WorkbookData, ItemType
from almabani.core.excel import ExcelIO

logger = logging.getLogger(__name__)


class ExcelParser:
    """Parses Excel files and extracts hierarchical data."""
    
    def __init__(self, subcategory_indicator: str = 'c'):
        """
        Initialize the Excel parser.
        
        Args:
            subcategory_indicator: Character indicating subcategory levels
        """
        self.subcategory_indicator = subcategory_indicator
        self.numeric_pattern = re.compile(r'^[0-9]+$')
        self.excel_io = ExcelIO()
    
    def parse_workbook(self, file_path: Path) -> WorkbookData:
        """
        Parse an entire Excel workbook.
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            WorkbookData object containing all sheets
        """
        logger.info(f"Parsing workbook: {file_path}")
        
        try:
            # Use shared ExcelIO to read all sheets
            sheets_data = self.excel_io.read_excel(str(file_path))
            
            workbook = WorkbookData(
                filename=file_path.name,
                metadata={
                    "total_sheets": len(sheets_data),
                    "sheet_names": list(sheets_data.keys())
                }
            )
            
            for sheet_name, (df, header_idx) in sheets_data.items():
                logger.info(f"Processing sheet: {sheet_name}")
                sheet_data = self.parse_sheet(df, sheet_name, header_idx)
                if sheet_data:
                    workbook.sheets.append(sheet_data)
            
            logger.info(f"Successfully parsed {len(workbook.sheets)} sheets from {file_path.name}")
            return workbook
            
        except Exception as e:
            logger.error(f"Error parsing workbook {file_path}: {e}", exc_info=True)
            raise
    
    def parse_sheet(self, df: pd.DataFrame, sheet_name: str, header_row_index: int) -> Optional[SheetData]:
        """
        Parse a single sheet DataFrame.
        
        Args:
            df: DataFrame containing sheet data
            sheet_name: Name of the sheet
            header_row_index: Index of the header row
            
        Returns:
            SheetData object or None if sheet is empty
        """
        try:
            if df.empty:
                logger.warning(f"Sheet {sheet_name} is empty, skipping")
                return None
            
            # Detect columns
            columns = self.excel_io.detect_columns(df)
            
            # Extract raw items
            raw_items = self._extract_raw_items(df, columns, header_row_index)
            
            sheet_data = SheetData(
                sheet_name=sheet_name,
                metadata={
                    "total_rows": len(df),
                    "total_items": len(raw_items),
                    "header_row": header_row_index
                }
            )
            
            sheet_data.hierarchy = raw_items
            
            return sheet_data
            
        except Exception as e:
            logger.error(f"Error parsing sheet {sheet_name}: {e}", exc_info=True)
            return None
    
    def _extract_raw_items(
        self,
        df: pd.DataFrame,
        columns: Dict[str, str],
        header_row_index: int
    ) -> List[HierarchyItem]:
        """
        Extract raw items from the dataframe.
        
        Args:
            df: DataFrame containing sheet data
            columns: Column name mappings
            header_row_index: Index of header row
            
        Returns:
            List of HierarchyItem objects
        """
        items = []
        
        # Get column names
        level_col = columns.get('level')
        item_col = columns.get('item')
        desc_col = columns.get('description')
        unit_col = columns.get('unit')
        rate_col = columns.get('rate')
        trade_col = columns.get('trade')
        code_col = columns.get('code')
        full_desc_col = columns.get('full_description')
        
        # Process rows after header
        for idx in range(header_row_index + 1, len(df)):
            row = df.iloc[idx]
            
            # Skip empty rows
            if row.isna().all():
                continue
            
            # Extract values safely
            level_val = row.get(level_col) if level_col else None
            item_val = row.get(item_col) if item_col else None
            desc_val = row.get(desc_col) if desc_col else None
            unit_val = row.get(unit_col) if unit_col else None
            rate_val = row.get(rate_col) if rate_col else None
            trade_val = row.get(trade_col) if trade_col else None
            code_val = row.get(code_col) if code_col else None
            full_desc_val = row.get(full_desc_col) if full_desc_col else None
            
            # Clean None values
            level_val = None if pd.isna(level_val) else level_val
            item_val = None if pd.isna(item_val) else item_val
            desc_val = None if pd.isna(desc_val) else desc_val
            unit_val = None if pd.isna(unit_val) else unit_val
            rate_val = None if pd.isna(rate_val) else rate_val
            trade_val = None if pd.isna(trade_val) else trade_val
            code_val = None if pd.isna(code_val) else code_val
            full_desc_val = None if pd.isna(full_desc_val) else full_desc_val
            
            # Determine item type
            item_type = self._determine_item_type(level_val, item_val)
            
            # Skip completely empty rows
            if item_type == ItemType.UNKNOWN and not any([level_val, item_val, desc_val]):
                continue
            
            # Create HierarchyItem
            item = HierarchyItem(
                level=level_val,
                item_code=item_val,
                description=desc_val,
                unit=unit_val,
                rate=rate_val,
                trade=trade_val,
                code=code_val,
                full_description=full_desc_val,
                item_type=item_type,
                row_number=idx
            )
            
            items.append(item)
        
        return items
    
    def _determine_item_type(self, level_val: Any, item_val: Any) -> ItemType:
        """Determine the type of an item based on its values."""
        # Check if level is numeric
        if level_val is not None:
            level_str = str(level_val).strip()
            if self.numeric_pattern.match(level_str):
                return ItemType.NUMERIC_LEVEL
            # Treat level indicator (e.g., 'c') as subcategory when no numeric match
            if level_str.lower() == self.subcategory_indicator:
                return ItemType.SUBCATEGORY
        
        # Check if item is subcategory indicator
        if item_val is not None:
            item_str = str(item_val).strip().lower()
            if item_str == self.subcategory_indicator:
                return ItemType.SUBCATEGORY
        
        # Check if it's an actual item (has item code or description)
        if item_val is not None or (level_val is None and item_val):
            return ItemType.ITEM
        
        return ItemType.UNKNOWN
