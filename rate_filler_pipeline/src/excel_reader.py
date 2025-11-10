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
        - Extract: row_index, description, current_unit, current_rate, parent, grandparent
        - Track parent hierarchy using same rules as excel_to_json_pipeline
        
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
        
        # Parent tracking stacks (following hierarchy_processor.py logic)
        level_stack = []  # Stack for numeric level hierarchy [(level_num, description), ...]
        c_level_stack = []  # Stack for c-level hierarchy [description, ...]
        
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
                
                # Get description for hierarchy tracking
                description_val = row[columns['description']] if columns['description'] and columns['description'] in df.columns else ''
                try:
                    description = '' if pd.isna(description_val) else str(description_val).strip()
                except:
                    description = str(description_val).strip() if description_val else ''
                
                # Check if this is a c-level (level value = 'c')
                is_c_level = False
                if level_value is not None:
                    try:
                        is_c_level = (str(level_value).lower().strip() == 'c')
                    except:
                        pass
                
                # Check if Level is empty/NaN
                try:
                    level_is_empty = pd.isna(level_value) or str(level_value).strip() == ''
                except:
                    level_is_empty = True
                
                # Check if Item has a value
                try:
                    item_exists = not (pd.isna(item_value) or str(item_value).strip() == '')
                except:
                    item_exists = False
                
                # Update parent hierarchy stacks
                if not level_is_empty and not item_exists:
                    # This is a parent row (has Level, no Item)
                    
                    if is_c_level:
                        # Handle c-level hierarchy (same logic as hierarchy_processor.py)
                        # Check if next row is also a c-level
                        next_is_c = False
                        if idx + 1 < len(df):
                            next_row = df.iloc[idx + 1]
                            next_level = None
                            if columns['level'] and columns['level'] in df.columns:
                                next_level = next_row[columns['level']]
                            if next_level is not None:
                                try:
                                    next_is_c = (str(next_level).lower().strip() == 'c')
                                except:
                                    pass
                        
                        if next_is_c:
                            # This c is parent of next c
                            if c_level_stack:
                                # Clear c-stack to make this a sibling
                                c_level_stack = []
                            # This becomes the new c-parent
                            c_level_stack.append(description)
                        else:
                            # This c is NOT followed by another c
                            if len(c_level_stack) >= 1:
                                # Replace the most recent c-level
                                if len(c_level_stack) > 1:
                                    c_level_stack.pop()
                                c_level_stack.append(description)
                            else:
                                # Start new c-stack
                                c_level_stack.append(description)
                    
                    else:
                        # Numeric level - clear c-level stack
                        c_level_stack = []
                        
                        # Extract numeric level
                        numeric_level = self._extract_numeric_level(level_value)
                        if numeric_level is not None:
                            # Update level_stack based on depth
                            # Keep only levels less than current level
                            while level_stack and level_stack[-1][0] >= numeric_level:
                                level_stack.pop()
                            
                            # Add this level
                            level_stack.append((numeric_level, description))
                
                # If this is an item row (empty Level, has Item), extract it
                if level_is_empty and item_exists:
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
                        # Extract parent and grandparent from stacks
                        parent = None
                        grandparent = None
                        
                        if c_level_stack:
                            # Use c-level hierarchy
                            if len(c_level_stack) >= 1:
                                parent = c_level_stack[-1]  # Most recent c-level
                            if len(c_level_stack) >= 2:
                                grandparent = c_level_stack[-2]  # Previous c-level
                            elif len(level_stack) >= 1:
                                # If only one c-level, use numeric level as grandparent
                                grandparent = level_stack[-1][1]
                        elif level_stack:
                            # Use numeric level hierarchy
                            if len(level_stack) >= 1:
                                parent = level_stack[-1][1]  # Most recent numeric level
                            if len(level_stack) >= 2:
                                grandparent = level_stack[-2][1]  # Previous numeric level
                        
                        item = {
                            'row_index': idx,  # Original row index in DataFrame
                            'item_code': str(item_value).strip(),
                            'description': description,
                            'parent': parent,
                            'grandparent': grandparent,
                            'current_unit': unit if unit else None,
                            'current_rate': rate,
                            'needs_unit': needs_unit,
                            'needs_rate': needs_rate
                        }
                        items_to_fill.append(item)
                        
                        logger.debug(f"Row {idx}: Item {item['item_code']} needs "
                                   f"{'unit' if needs_unit else ''}"
                                   f"{' and ' if needs_unit and needs_rate else ''}"
                                   f"{'rate' if needs_rate else ''} "
                                   f"[Parent: {parent}, Grandparent: {grandparent}]")
            
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
    
    def _extract_numeric_level(self, level_value: Any) -> Optional[float]:
        """
        Extract numeric level from level value.
        Handles: "1", "2", "2.1", "8.1", etc.
        
        Args:
            level_value: Level value from Excel
            
        Returns:
            Numeric level as float, or None if not numeric
        """
        if level_value is None or pd.isna(level_value):
            return None
        
        try:
            level_str = str(level_value).strip()
            if not level_str:
                return None
            
            # Try to convert to float
            level_num = float(level_str)
            return level_num
        except (ValueError, TypeError):
            return None
    
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
