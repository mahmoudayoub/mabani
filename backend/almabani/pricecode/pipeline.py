"""
Price Code Pipeline - Process Excel files to allocate price codes.
"""

import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import asyncio
from datetime import datetime

from .matcher import PriceCodeMatcher

logger = logging.getLogger(__name__)


class PriceCodePipeline:
    """
    Process Excel BOQ files to allocate price codes.
    
    Reads Excel files with:
    - 'Bill description' or similar column with item descriptions
    - 'Code' column to be filled with price codes
    - 'Description' column to be filled with price code descriptions
    """
    
    # Common column name variations
    DESCRIPTION_COLS = ['bill description', 'description', 'item description', 'work description']
    CODE_COLS = ['code', 'price code', 'ai code']
    CODE_DESC_COLS = ['description', 'code description', 'price description']
    
    def __init__(self, matcher: PriceCodeMatcher):
        self.matcher = matcher
    
    def detect_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Detect the relevant columns in the DataFrame.
        
        Returns dict with keys: 'description', 'code', 'code_description'
        """
        columns = {}
        df_cols_lower = {col: col.lower().strip() for col in df.columns}
        
        # Find description column (the source text to match)
        for col, col_lower in df_cols_lower.items():
            for pattern in self.DESCRIPTION_COLS:
                if pattern in col_lower:
                    # Prefer 'bill description' over just 'description'
                    if 'bill' in col_lower or columns.get('description') is None:
                        columns['description'] = col
                    break
        
        # Find code column (to fill with price code)
        for col, col_lower in df_cols_lower.items():
            for pattern in self.CODE_COLS:
                if pattern in col_lower and 'description' not in col_lower:
                    columns['code'] = col
                    break
        
        # Find code description column
        # This is tricky - need to find the 'Description' that's meant for price code output
        # Usually it's a column after the Code column
        code_col_idx = None
        if columns.get('code'):
            code_col_idx = list(df.columns).index(columns['code'])
        
        # Look for description column that's different from the input description
        for col, col_lower in df_cols_lower.items():
            if 'description' in col_lower and col != columns.get('description'):
                # Prefer columns after the code column
                col_idx = list(df.columns).index(col)
                if code_col_idx is not None and col_idx > code_col_idx:
                    columns['code_description'] = col
                    break
                elif columns.get('code_description') is None:
                    columns['code_description'] = col
        
        logger.info(f"Detected columns: {columns}")
        return columns
    
    def find_header_row(self, df: pd.DataFrame) -> int:
        """Find the row containing column headers"""
        for idx in range(min(10, len(df))):
            row = df.iloc[idx]
            row_str = ' '.join(str(v).lower() for v in row.values if pd.notna(v))
            if any(pattern in row_str for pattern in self.DESCRIPTION_COLS + self.CODE_COLS):
                return idx
        return 0
    
    def extract_items_for_allocation(
        self,
        df: pd.DataFrame,
        columns: Dict[str, str],
        header_row: int
    ) -> List[Dict[str, Any]]:
        """
        Extract items that need price code allocation.
        
        Returns list of dicts with 'row_idx', 'description', existing 'code'
        """
        items = []
        desc_col = columns.get('description')
        code_col = columns.get('code')
        
        if not desc_col:
            logger.error("No description column found")
            return items
        
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            description = row.get(desc_col)
            existing_code = row.get(code_col) if code_col else None
            
            # Skip if no description
            if pd.isna(description) or str(description).strip() == '':
                continue
            
            description = str(description).strip()
            
            # Skip if already has a code (unless it's empty-like)
            if existing_code and pd.notna(existing_code):
                code_str = str(existing_code).strip()
                if code_str and code_str.lower() not in ['nan', 'none', '']:
                    continue
            
            items.append({
                'row_idx': idx,
                'description': description
            })
        
        logger.info(f"Found {len(items)} items needing price code allocation")
        return items
    
    async def process_file(
        self,
        input_file: Path,
        output_file: Optional[Path] = None,
        namespace: str = "",
        max_concurrent: int = 20
    ) -> Dict[str, Any]:
        """
        Process an Excel file to allocate price codes.
        
        Returns report with statistics.
        """
        start_time = datetime.now()
        
        if output_file is None:
            output_file = input_file.parent / f"{input_file.stem}_pricecode.xlsx"
        
        # Read Excel
        logger.info(f"Reading {input_file}...")
        xls = pd.ExcelFile(input_file)
        sheet_name = xls.sheet_names[0]  # Process first sheet
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        # Find header and detect columns
        header_row = self.find_header_row(df)
        
        # Re-read with correct header
        df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
        columns = self.detect_columns(df)
        
        if not columns.get('description'):
            raise ValueError(f"Could not find description column in {input_file}")
        
        # Extract items
        items = self.extract_items_for_allocation(df, columns, 0)
        
        if not items:
            logger.warning("No items found for allocation")
            return {
                "total_items": 0,
                "matched": 0,
                "not_matched": 0,
                "output_file": str(output_file)
            }
        
        # Match items
        logger.info(f"Matching {len(items)} items...")
        
        matched_count = 0
        not_matched_count = 0
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_item(item):
            async with semaphore:
                result = await self.matcher.match(item['description'], namespace)
                return item, result
        
        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)
        
        # Update DataFrame with results
        code_col = columns.get('code')
        desc_col = columns.get('code_description')
        
        for item, result in results:
            row_idx = item['row_idx']
            
            if result['matched']:
                matched_count += 1
                if code_col:
                    df.at[row_idx, code_col] = result['price_code']
                if desc_col:
                    df.at[row_idx, desc_col] = result['price_description']
            else:
                not_matched_count += 1
        
        # Save output
        logger.info(f"Saving to {output_file}...")
        df.to_excel(output_file, sheet_name=sheet_name, index=False)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        report = {
            "total_items": len(items),
            "matched": matched_count,
            "not_matched": not_matched_count,
            "match_rate": matched_count / len(items) if items else 0,
            "elapsed_seconds": elapsed,
            "output_file": str(output_file)
        }
        
        logger.info(f"Completed: {matched_count}/{len(items)} matched ({report['match_rate']:.1%})")
        
        return report
