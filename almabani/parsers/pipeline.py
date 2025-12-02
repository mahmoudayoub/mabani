"""
Excel to JSON Pipeline - Main orchestrator.
Parses Excel BOQ files into hierarchical JSON format.
"""
import logging
from pathlib import Path
from typing import List, Optional

from almabani.core.models import WorkbookData
from almabani.parsers.excel_parser import ExcelParser
from almabani.parsers.hierarchy_processor import HierarchyProcessor
from almabani.parsers.json_exporter import JsonExporter

logger = logging.getLogger(__name__)


class ExcelToJsonPipeline:
    """Main pipeline for converting Excel BOQ to JSON."""
    
    def __init__(self, subcategory_indicator: str = 'c'):
        """
        Initialize the pipeline.
        
        Args:
            subcategory_indicator: Character indicating subcategory levels
        """
        self.parser = ExcelParser(subcategory_indicator=subcategory_indicator)
        self.processor = HierarchyProcessor(subcategory_indicator=subcategory_indicator)
        self.exporter = JsonExporter()
        
        logger.info("Excel to JSON Pipeline initialized")
    
    def process_file(
        self,
        input_file: Path,
        output_mode: str = 'multiple',
        output_dir: Optional[Path] = None,
        sheets: Optional[List[str]] = None
    ) -> List[Path]:
        """
        Process a single Excel file through the pipeline.
        
        Args:
            input_file: Path to input Excel file
            output_mode: Deprecated, always uses 'multiple' (one JSON per sheet)
            output_dir: Output directory (if None, uses input file directory)
            sheets: Optional list of specific sheet names to process
            
        Returns:
            List of paths to generated JSON files
        """
        logger.info(f"Processing file: {input_file}")
        
        try:
            # Step 1: Parse the Excel file
            logger.info("Step 1: Parsing Excel file...")
            workbook = self.parser.parse_workbook(input_file)
            
            # Filter sheets if specified
            if sheets:
                workbook.sheets = [s for s in workbook.sheets if s.sheet_name in sheets]
                logger.info(f"Filtered to {len(workbook.sheets)} specified sheets")
            
            # Step 2: Process hierarchy for each sheet
            logger.info("Step 2: Processing hierarchies...")
            for sheet in workbook.sheets:
                self.processor.process_sheet(sheet)
            
            # Step 3: Export to JSON (one file per sheet)
            logger.info("Step 3: Exporting to JSON...")
            
            if output_dir is None:
                output_dir = input_file.parent / 'output'
            
            output_files = self.exporter.export_multiple_files(workbook, output_dir)
            
            logger.info(f"✓ Pipeline complete! Generated {len(output_files)} JSON file(s)")
            return output_files
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise
    
    def process_directory(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        file_pattern: str = '*.xlsx'
    ) -> List[Path]:
        """
        Process all Excel files in a directory.
        
        Args:
            input_dir: Directory containing Excel files
            output_dir: Output directory
            file_pattern: Glob pattern for files to process
            
        Returns:
            List of all generated JSON file paths
        """
        logger.info(f"Processing directory: {input_dir}")
        logger.info(f"File pattern: {file_pattern}")
        
        excel_files = list(input_dir.glob(file_pattern))
        logger.info(f"Found {len(excel_files)} Excel files")
        
        all_output_files = []
        
        for excel_file in excel_files:
            try:
                output_files = self.process_file(excel_file, output_dir=output_dir)
                all_output_files.extend(output_files)
            except Exception as e:
                logger.error(f"Failed to process {excel_file}: {e}")
                continue
        
        logger.info(f"✓ Directory processing complete! Generated {len(all_output_files)} JSON files total")
        return all_output_files
