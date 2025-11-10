"""
Main pipeline orchestrator for the Excel to JSON conversion.
Coordinates all modules and provides the main entry point.
"""
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
from datetime import datetime

from excel_parser import ExcelParser
from hierarchy_processor import HierarchyProcessor
from json_exporter import JsonExporter
from models import WorkbookData


class Pipeline:
    """Main pipeline orchestrator for Excel to JSON conversion."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the pipeline with configuration.
        
        Args:
            config_path: Path to configuration YAML file
        """
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'settings.yaml'
        
        self.config = self._load_config(config_path)
        
        # Setup logging
        self._setup_logging()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 80)
        self.logger.info("Excel to JSON Pipeline Initialized")
        self.logger.info("=" * 80)
        
        # Initialize components
        self.parser = ExcelParser(self.config)
        self.processor = HierarchyProcessor(self.config)
        self.exporter = JsonExporter(self.config)
    
    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"Configuration file not found: {config_path}")
            print("Using default configuration")
            return self._get_default_config()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            print("Using default configuration")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration if config file is not available."""
        return {
            'input_directory': 'input',
            'output_directory': 'output',
            'log_directory': 'logs',
            'excel': {
                'level_column_index': 0,
                'item_column_index': 1,
                'description_column_index': 2,
                'unit_column_index': 3,
                'rate_column_index': 4,
                'data_start_row': 1,
                'skip_empty_rows': True
            },
            'hierarchy': {
                'subcategory_indicator': 'c',
                'numeric_level_pattern': '^[0-9]+$',
                'item_pattern': '^[A-Za-z0-9]+.*$'
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'file_prefix': 'pipeline'
            }
        }
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_config = self.config.get('logging', {})
        log_level = log_config.get('level', 'INFO')
        log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Get the pipeline directory (parent of src directory)
        pipeline_dir = Path(__file__).parent.parent
        
        # Use absolute path to log directory within the pipeline module
        log_dir_name = self.config.get('log_directory', 'logs')
        log_dir = pipeline_dir / log_dir_name
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = log_dir / f"{log_config.get('file_prefix', 'pipeline')}_{timestamp}.log"
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=log_format,
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def process_file(self, 
                    input_file: Path, 
                    output_mode: str = 'multiple',
                    sheets: Optional[List[str]] = None) -> List[Path]:
        """
        Process a single Excel file through the pipeline.
        
        Args:
            input_file: Path to input Excel file
            output_mode: 'single' for one JSON file, 'multiple' for one per sheet
            sheets: Optional list of specific sheet names to process
            
        Returns:
            List of paths to generated JSON files
        """
        self.logger.info(f"Processing file: {input_file}")
        self.logger.info(f"Output mode: {output_mode}")
        
        try:
            # Step 1: Parse the Excel file
            self.logger.info("Step 1: Parsing Excel file...")
            workbook = self.parser.parse_workbook(input_file)
            
            # Filter sheets if specified
            if sheets:
                workbook.sheets = [s for s in workbook.sheets if s.sheet_name in sheets]
                self.logger.info(f"Filtered to {len(workbook.sheets)} sheets: {sheets}")
            
            # Step 2: Process hierarchy for each sheet
            self.logger.info("Step 2: Processing hierarchies...")
            for sheet in workbook.sheets:
                self.processor.process_sheet(sheet)
            
            # Step 3: Export to JSON
            self.logger.info("Step 3: Exporting to JSON...")
            output_paths = []
            
            if output_mode == 'single':
                # Export all sheets in one file
                output_path = self.exporter.export_workbook(workbook)
                output_paths.append(output_path)
            elif output_mode == 'multiple':
                # Export each sheet to separate files
                output_paths = self.exporter.export_workbook_by_sheets(workbook)
            else:
                raise ValueError(f"Invalid output_mode: {output_mode}. Use 'single' or 'multiple'")
            
            self.logger.info("=" * 80)
            self.logger.info("Processing completed successfully!")
            self.logger.info(f"Generated {len(output_paths)} JSON file(s):")
            for path in output_paths:
                self.logger.info(f"  - {path}")
            self.logger.info("=" * 80)
            
            return output_paths
            
        except Exception as e:
            self.logger.error(f"Pipeline processing failed: {e}", exc_info=True)
            raise
    
    def process_directory(self, 
                         input_dir: Optional[Path] = None,
                         output_mode: str = 'multiple',
                         pattern: str = '*.xlsx') -> Dict[str, List[Path]]:
        """
        Process all Excel files in a directory.
        
        Args:
            input_dir: Path to input directory (uses config default if None)
            output_mode: 'single' or 'multiple'
            pattern: Glob pattern for Excel files
            
        Returns:
            Dictionary mapping input filenames to output file paths
        """
        if input_dir is None:
            input_dir = Path(self.config.get('input_directory', 'input'))
        
        input_dir = Path(input_dir)
        
        self.logger.info(f"Processing directory: {input_dir}")
        self.logger.info(f"Pattern: {pattern}")
        
        # Find all Excel files
        excel_files = list(input_dir.glob(pattern))
        
        if not excel_files:
            self.logger.warning(f"No Excel files found in {input_dir} matching pattern {pattern}")
            return {}
        
        self.logger.info(f"Found {len(excel_files)} Excel file(s)")
        
        results = {}
        
        for excel_file in excel_files:
            try:
                self.logger.info(f"\n{'=' * 80}")
                self.logger.info(f"Processing: {excel_file.name}")
                self.logger.info(f"{'=' * 80}")
                
                output_paths = self.process_file(excel_file, output_mode)
                results[excel_file.name] = output_paths
                
            except Exception as e:
                self.logger.error(f"Failed to process {excel_file.name}: {e}")
                results[excel_file.name] = []
        
        # Summary
        self.logger.info("\n" + "=" * 80)
        self.logger.info("BATCH PROCESSING SUMMARY")
        self.logger.info("=" * 80)
        successful = sum(1 for paths in results.values() if paths)
        self.logger.info(f"Total files processed: {len(excel_files)}")
        self.logger.info(f"Successful: {successful}")
        self.logger.info(f"Failed: {len(excel_files) - successful}")
        self.logger.info("=" * 80)
        
        return results


def main():
    """Main entry point for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert Excel files with hierarchical data to JSON format'
    )
    parser.add_argument(
        'input',
        type=str,
        nargs='?',
        help='Input Excel file or directory path'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--output-mode',
        choices=['single', 'multiple'],
        default='multiple',
        help='Output mode: multiple (one per sheet, default) or single JSON file'
    )
    parser.add_argument(
        '--sheets',
        type=str,
        nargs='+',
        help='Specific sheet names to process (optional)'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Process all Excel files in the input directory'
    )
    parser.add_argument(
        '--pattern',
        type=str,
        default='*.xlsx',
        help='File pattern for batch processing (default: *.xlsx)'
    )
    
    args = parser.parse_args()
    
    # Initialize pipeline
    config_path = Path(args.config) if args.config else None
    pipeline = Pipeline(config_path)
    
    try:
        if args.batch or (args.input and Path(args.input).is_dir()):
            # Batch processing
            input_dir = Path(args.input) if args.input else None
            pipeline.process_directory(
                input_dir=input_dir,
                output_mode=args.output_mode,
                pattern=args.pattern
            )
        elif args.input:
            # Single file processing
            input_file = Path(args.input)
            if not input_file.exists():
                print(f"Error: Input file not found: {input_file}")
                sys.exit(1)
            
            pipeline.process_file(
                input_file=input_file,
                output_mode=args.output_mode,
                sheets=args.sheets
            )
        else:
            # No input specified, process default input directory
            pipeline.process_directory(output_mode=args.output_mode, pattern=args.pattern)
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
