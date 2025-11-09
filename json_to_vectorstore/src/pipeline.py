"""
Main pipeline for preparing JSON data for vector store ingestion.
"""
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from .json_processor import JSONProcessor
from .exporter import VectorStoreExporter
from .models import VectorStoreDocument


class VectorStorePreparationPipeline:
    """Main pipeline for preparing data for vector stores."""
    
    def __init__(self, output_dir: Path = None):
        """
        Initialize the pipeline.
        
        Args:
            output_dir: Directory for output files
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'output'
        
        self.output_dir = Path(output_dir)
        self.processor = JSONProcessor()
        self.exporter = VectorStoreExporter(self.output_dir)
        
        # Setup logging
        self._setup_logging()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 80)
        self.logger.info("Vector Store Preparation Pipeline Initialized")
        self.logger.info("=" * 80)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_dir = Path(__file__).parent.parent / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"vectorstore_prep_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def process_file(
        self, 
        json_file: Path,
        export_format: str = 'all'
    ) -> Dict[str, Path]:
        """
        Process a single JSON file.
        
        Args:
            json_file: Path to JSON file
            export_format: Format to export ('json', 'jsonl', 'csv', or 'all')
            
        Returns:
            Dictionary mapping format to output path
        """
        self.logger.info(f"Processing file: {json_file}")
        
        # Process JSON to extract items
        document = self.processor.process_file(json_file)
        
        # Export
        if export_format == 'all':
            exports = self.exporter.export_all_formats([document])
        elif export_format == 'json':
            path = self.exporter.export_json([document])
            exports = {'json': path}
        elif export_format == 'jsonl':
            path = self.exporter.export_jsonl([document])
            exports = {'jsonl': path}
        elif export_format == 'csv':
            path = self.exporter.export_csv([document])
            exports = {'csv': path}
        else:
            raise ValueError(f"Unsupported format: {export_format}")
        
        self.logger.info(f"Exported {len(document.items)} items")
        return exports
    
    def process_directory(
        self, 
        input_dir: Path = None,
        export_format: str = 'jsonl',
        combine: bool = True
    ) -> Dict[str, Any]:
        """
        Process all JSON files in a directory.
        
        Args:
            input_dir: Directory containing JSON files
            export_format: Format to export
            combine: If True, combine all into one file; if False, separate files
            
        Returns:
            Dictionary with export information
        """
        if input_dir is None:
            input_dir = Path(__file__).parent.parent / 'input'
        
        input_dir = Path(input_dir)
        
        self.logger.info(f"Processing directory: {input_dir}")
        
        # Process all JSON files
        documents = self.processor.process_directory(input_dir)
        
        if not documents:
            self.logger.warning("No documents processed")
            return {}
        
        # Export
        if combine:
            self.logger.info(f"Combining {len(documents)} documents into single file")
            
            if export_format == 'all':
                exports = self.exporter.export_all_formats(documents)
            elif export_format == 'json':
                path = self.exporter.export_json(documents)
                exports = {'json': path}
            elif export_format == 'jsonl':
                path = self.exporter.export_jsonl(documents)
                exports = {'jsonl': path}
            elif export_format == 'csv':
                path = self.exporter.export_csv(documents)
                exports = {'csv': path}
            else:
                raise ValueError(f"Unsupported format: {export_format}")
        else:
            self.logger.info(f"Exporting {len(documents)} documents as separate files")
            paths = self.exporter.export_separate_documents(documents, export_format)
            exports = {f'{export_format}_files': paths}
        
        total_items = sum(len(doc.items) for doc in documents)
        
        result = {
            'exports': exports,
            'total_documents': len(documents),
            'total_items': total_items
        }
        
        self.logger.info("=" * 80)
        self.logger.info("Processing Complete!")
        self.logger.info(f"Documents processed: {len(documents)}")
        self.logger.info(f"Total items extracted: {total_items}")
        self.logger.info(f"Output files: {list(exports.keys())}")
        self.logger.info("=" * 80)
        
        return result


def main():
    """Main entry point for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Prepare JSON hierarchy data for vector store ingestion'
    )
    parser.add_argument(
        'input',
        type=str,
        nargs='?',
        help='Input JSON file or directory path'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'jsonl', 'csv', 'all'],
        default='jsonl',
        help='Output format (default: jsonl)'
    )
    parser.add_argument(
        '--separate',
        action='store_true',
        help='Export each source as separate file (default: combine all)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output directory'
    )
    
    args = parser.parse_args()
    
    # Initialize pipeline
    output_dir = Path(args.output) if args.output else None
    pipeline = VectorStorePreparationPipeline(output_dir=output_dir)
    
    try:
        if args.input:
            input_path = Path(args.input)
            
            if input_path.is_file():
                # Process single file
                pipeline.process_file(input_path, export_format=args.format)
            elif input_path.is_dir():
                # Process directory
                pipeline.process_directory(
                    input_dir=input_path,
                    export_format=args.format,
                    combine=not args.separate
                )
            else:
                print(f"Error: Invalid input path: {input_path}")
                sys.exit(1)
        else:
            # Use default input directory
            pipeline.process_directory(
                export_format=args.format,
                combine=not args.separate
            )
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
