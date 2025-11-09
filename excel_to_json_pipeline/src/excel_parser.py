"""
Excel parser module for reading and parsing Excel workbooks.
Extracts data from sheets and creates initial HierarchyItem objects.
"""
import pandas as pd
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import re

from models import HierarchyItem, SheetData, WorkbookData, ItemType


logger = logging.getLogger(__name__)


class ExcelParser:
    """Parses Excel files and extracts hierarchical data."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Excel parser with configuration.
        
        Args:
            config: Configuration dictionary containing parsing settings
        """
        self.config = config
        self.excel_config = config.get('excel', {})
        self.hierarchy_config = config.get('hierarchy', {})
        
        # Column indices
        self.level_col = self.excel_config.get('level_column_index', 0)
        self.item_col = self.excel_config.get('item_column_index', 1)
        self.desc_col = self.excel_config.get('description_column_index', 2)
        self.unit_col = self.excel_config.get('unit_column_index', 3)
        self.rate_col = self.excel_config.get('rate_column_index', 4)
        
        # Patterns
        self.subcategory_indicator = self.hierarchy_config.get('subcategory_indicator', 'c')
        self.numeric_pattern = re.compile(self.hierarchy_config.get('numeric_level_pattern', r'^[0-9]+$'))
    
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
            xl_file = pd.ExcelFile(file_path)
            workbook = WorkbookData(
                filename=file_path.name,
                metadata={
                    "total_sheets": len(xl_file.sheet_names),
                    "sheet_names": xl_file.sheet_names
                }
            )
            
            for sheet_name in xl_file.sheet_names:
                logger.info(f"Processing sheet: {sheet_name}")
                sheet_data = self.parse_sheet(file_path, sheet_name)
                if sheet_data:
                    workbook.sheets.append(sheet_data)
            
            logger.info(f"Successfully parsed {len(workbook.sheets)} sheets from {file_path.name}")
            return workbook
            
        except Exception as e:
            logger.error(f"Error parsing workbook {file_path}: {e}", exc_info=True)
            raise
    
    def parse_sheet(self, file_path: Path, sheet_name: str) -> Optional[SheetData]:
        """
        Parse a single sheet from the Excel file.
        
        Args:
            file_path: Path to the Excel file
            sheet_name: Name of the sheet to parse
            
        Returns:
            SheetData object or None if sheet is empty
        """
        try:
            # Read sheet without headers
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            
            if df.empty:
                logger.warning(f"Sheet {sheet_name} is empty, skipping")
                return None
            
            # Extract raw items
            raw_items = self._extract_raw_items(df)
            
            sheet_data = SheetData(
                sheet_name=sheet_name,
                metadata={
                    "total_rows": len(df),
                    "total_items": len(raw_items)
                }
            )
            
            # Store raw items for hierarchy processing
            sheet_data.hierarchy = raw_items
            
            return sheet_data
            
        except Exception as e:
            logger.error(f"Error parsing sheet {sheet_name}: {e}", exc_info=True)
            return None
    
    def _extract_raw_items(self, df: pd.DataFrame) -> List[HierarchyItem]:
        """
        Extract raw items from the dataframe.
        
        Args:
            df: DataFrame containing sheet data
            
        Returns:
            List of HierarchyItem objects
        """
        items = []
        
        for idx, row in df.iterrows():
            # Skip empty rows
            if row.isna().all():
                continue
            
            # Extract values safely
            level_val = self._get_value(row, self.level_col)
            item_val = self._get_value(row, self.item_col)
            desc_val = self._get_value(row, self.desc_col)
            unit_val = self._get_value(row, self.unit_col)
            rate_val = self._get_value(row, self.rate_col)
            
            # Determine item type
            item_type = self._determine_item_type(level_val, item_val)
            
            # Skip completely empty rows
            if item_type == ItemType.UNKNOWN and not any([level_val, item_val, desc_val]):
                continue
            
            # Extract additional columns if they exist (Trade, Code, Full Description)
            trade_val = self._get_value(row, 5) if len(row) > 5 else None
            code_val = self._get_value(row, 6) if len(row) > 6 else None
            full_desc_val = self._get_value(row, 7) if len(row) > 7 else None
            
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
                row_number=int(idx) + 1  # 1-based row numbering
            )
            
            items.append(item)
        
        logger.debug(f"Extracted {len(items)} items")
        return items
    
    def _get_value(self, row: pd.Series, col_index: int) -> Optional[Any]:
        """
        Safely get a value from a row at a specific column index.
        
        Args:
            row: Pandas Series representing a row
            col_index: Column index to extract
            
        Returns:
            Value at the column or None
        """
        try:
            if col_index >= len(row):
                return None
            
            val = row.iloc[col_index]
            
            # Handle NaN values
            if pd.isna(val):
                return None
            
            # Convert to string and strip whitespace for string values
            if isinstance(val, str):
                val = val.strip()
                return val if val else None
            
            return val
            
        except Exception:
            return None
    
    def _determine_item_type(self, level_val: Any, item_val: Any) -> ItemType:
        """
        Determine the type of item based on level and item values.
        
        Args:
            level_val: Value in the level column
            item_val: Value in the item column
            
        Returns:
            ItemType enum value
        """
        # Check for numeric level
        if level_val is not None:
            level_str = str(level_val).strip()
            if self.numeric_pattern.match(level_str):
                return ItemType.NUMERIC_LEVEL
            
            # Check for subcategory indicator
            if level_str.lower() == self.subcategory_indicator.lower():
                return ItemType.SUBCATEGORY
        
        # Check for item code
        if item_val is not None:
            item_str = str(item_val).strip()
            # If it's a simple letter or alphanumeric code, it's likely an item
            if item_str and len(item_str) <= 50:  # Reasonable length for item code
                return ItemType.ITEM
        
        return ItemType.UNKNOWN
