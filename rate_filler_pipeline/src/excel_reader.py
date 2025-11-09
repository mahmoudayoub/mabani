"""
Excel Reader - Read and parse Excel files for rate filling.
Processes rows based on Level column and Item presence.
"""
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class ExcelReader:
    """Read Excel files and identify items that need rate filling."""
    
    def __init__(self):
        self.logger = logger
    
    def read_excel(
        self,
        file_path: str,
        sheet_name: Optional[str] = None
    ) -> Dict[str, Tuple[pd.DataFrame, int]]:
        """
        Read Excel file and return DataFrames with header row index.
        
        Args:
            file_path: Path to Excel file
            sheet_name: Specific sheet to read (None = all sheets)
            
        Returns:
            Dictionary of {sheet_name: (DataFrame, header_row_index)}
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {file_path}")
        
        logger.info(f"Reading Excel file: {path.name}")
        
        # Read all sheets without assuming header location
        if sheet_name:
            raw_df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            df, header_idx = self._process_sheet(raw_df)
            sheets = {sheet_name: (df, header_idx)}
            logger.info(f"Read sheet '{sheet_name}': {len(df)} rows, header at row {header_idx}")
        else:
            all_sheets = pd.read_excel(file_path, sheet_name=None, header=None)
            sheets = {}
            for name, raw_df in all_sheets.items():
                df, header_idx = self._process_sheet(raw_df)
                sheets[name] = (df, header_idx)
                logger.info(f"Read sheet '{name}': {len(df)} rows, header at row {header_idx}")
        
        return sheets
    
    def _process_sheet(self, raw_df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """
        Process raw sheet to detect header and preserve all rows.
        
        Args:
            raw_df: Raw DataFrame with no header
            
        Returns:
            Tuple of (processed DataFrame, header row index)
        """
        # Find header row
        header_idx = self._find_header_row(raw_df)
        
        if header_idx is None:
            logger.warning("No header row detected, using first row")
            header_idx = 0
        
        # Create DataFrame with proper header
        df = raw_df.copy()
        df.columns = raw_df.iloc[header_idx].values
        
        # Handle duplicate column names by renaming them
        cols = pd.Series(df.columns)
        for dup in cols[cols.duplicated()].unique():
            # Find indices of duplicate columns
            dup_indices = cols[cols == dup].index.tolist()
            # Rename duplicates with suffix
            for i, idx in enumerate(dup_indices[1:], start=2):
                cols.iloc[idx] = f"{dup}_{i}"
        df.columns = cols
        
        # Keep ALL rows including header (we'll need original structure)
        # But mark the data start
        df['_header_row_index'] = header_idx
        
        return df, header_idx
    
    def _find_header_row(self, raw_df: pd.DataFrame) -> Optional[int]:
        """
        Find the row containing column headers.
        Looks for keywords: Level, Item, Bill description, Unit, Rate
        """
        keywords = ['level', 'item', 'description', 'unit', 'rate']
        
        for idx in range(min(10, len(raw_df))):
            row_values = [str(val).strip().lower() for val in raw_df.iloc[idx].values 
                         if pd.notna(val) and str(val).strip()]
            
            # Count matches
            matches = sum(1 for keyword in keywords 
                         if any(keyword in val for val in row_values))
            
            if matches >= 3:
                logger.info(f"Detected header row at index {idx}")
                return idx
        
        return None
    
    def extract_items_for_filling(
        self,
        df: pd.DataFrame,
        header_row_index: int
    ) -> Dict[str, Any]:
        """
        Extract items that need filling based on Level column logic.
        
        Logic:
        - If Level is EMPTY and row contains an Item → Process for filling
        - Extract: row_index, description, current_unit, current_rate
        
        Args:
            df: DataFrame with all rows
            header_row_index: Index of the header row
            
        Returns:
            Dictionary with items needing filling and full dataframe
        """
        # Detect column names
        columns = self._detect_columns(df)
        
        logger.info(f"Detected columns: {columns}")
        
        items_to_fill = []
        
        # Start processing after header row
        for idx in range(header_row_index + 1, len(df)):
            try:
                row = df.iloc[idx]
                
                # Get Level column value
                level_value = None
                if columns['level'] and columns['level'] in df.columns:
                    level_value = row[columns['level']]
                
                # Get Item column value
                item_value = None
                if columns['item'] and columns['item'] in df.columns:
                    item_value = row[columns['item']]
                
                # Check if Level is empty/NaN AND Item has a value
                try:
                    level_is_empty = pd.isna(level_value) or str(level_value).strip() == ''
                except:
                    level_is_empty = True
                
                try:
                    item_exists = not (pd.isna(item_value) or str(item_value).strip() == '')
                except:
                    item_exists = False
                
                if not (level_is_empty and item_exists):
                    continue
                
                # This is an item row that needs processing
                description_val = row[columns['description']] if columns['description'] and columns['description'] in df.columns else ''
                try:
                    description = '' if pd.isna(description_val) else str(description_val).strip()
                except:
                    description = str(description_val).strip() if description_val else ''
                
                unit_val = row[columns['unit']] if columns['unit'] and columns['unit'] in df.columns else ''
                try:
                    unit = '' if pd.isna(unit_val) else str(unit_val).strip()
                except:
                    unit = str(unit_val).strip() if unit_val else ''
                
                rate_val = row[columns['rate']] if columns['rate'] and columns['rate'] in df.columns else None
                rate = None
                if rate_val is not None:
                    try:
                        if not pd.isna(rate_val) and str(rate_val).strip() != '':
                            rate = float(rate_val)
                    except:
                        rate = None
                
                # Determine what needs filling
                needs_unit = not unit
                needs_rate = rate is None
                
                if needs_unit or needs_rate:
                    item = {
                        'row_index': idx,  # Original row index in DataFrame
                        'item_code': str(item_value).strip(),
                        'description': description,
                        'current_unit': unit if unit else None,
                        'current_rate': rate,
                        'needs_unit': needs_unit,
                        'needs_rate': needs_rate
                    }
                    items_to_fill.append(item)
                    
                    logger.debug(f"Row {idx}: Item {item['item_code']} needs "
                               f"{'unit' if needs_unit else ''}"
                               f"{' and ' if needs_unit and needs_rate else ''}"
                               f"{'rate' if needs_rate else ''}")
            
            except Exception as e:
                logger.error(f"ERROR processing row {idx}: {e}", exc_info=True)
                continue
        
        result = {
            'items': items_to_fill,
            'dataframe': df,
            'header_row_index': header_row_index,
            'columns': columns,
            'total_items': len(items_to_fill),
            'needs_unit': sum(1 for item in items_to_fill if item['needs_unit']),
            'needs_rate': sum(1 for item in items_to_fill if item['needs_rate'])
        }
        
        logger.info(f"Found {result['total_items']} items needing filling:")
        logger.info(f"  - Missing unit: {result['needs_unit']}")
        logger.info(f"  - Missing rate: {result['needs_rate']}")
        
        return result
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Detect column names for Level, Item, Description, Unit, Rate.
        
        Returns:
            Dictionary mapping field names to actual column names
        """
        columns = {
            'level': None,
            'item': None,
            'description': None,
            'unit': None,
            'rate': None
        }
        
        # Get column names (from DataFrame columns)
        col_names = [str(col).strip() if not pd.isna(col) else '' 
                    for col in df.columns]
        
        for col in col_names:
            col_lower = col.lower()
            
            # Detect Level
            if 'level' in col_lower and not columns['level']:
                columns['level'] = col
            
            # Detect Item/Code
            elif 'item' in col_lower and not columns['item']:
                columns['item'] = col
            elif 'code' in col_lower and not 'description' in col_lower and not columns['item']:
                columns['item'] = col
            
            # Detect Description
            elif 'description' in col_lower and not columns['description']:
                columns['description'] = col
            
            # Detect Unit
            elif col_lower == 'unit' and not columns['unit']:
                columns['unit'] = col
            
            # Detect Rate
            elif 'rate' in col_lower and not columns['rate']:
                columns['rate'] = col
        
        return columns
