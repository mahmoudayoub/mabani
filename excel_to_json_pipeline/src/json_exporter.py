"""
JSON exporter module for saving processed data to JSON files.
Handles serialization with proper formatting and validation.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from models import WorkbookData, SheetData


logger = logging.getLogger(__name__)


class JsonExporter:
    """Exports processed data to JSON format."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the JSON exporter with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.output_dir = Path(config.get('output_directory', 'output'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_workbook(self, workbook: WorkbookData, output_filename: Optional[str] = None) -> Path:
        """
        Export workbook data to a JSON file.
        
        Args:
            workbook: WorkbookData object to export
            output_filename: Optional custom filename
            
        Returns:
            Path to the exported JSON file
        """
        if not output_filename:
            # Generate filename from workbook filename
            base_name = Path(workbook.filename).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{base_name}_{timestamp}.json"
        
        output_path = self.output_dir / output_filename
        
        logger.info(f"Exporting workbook to: {output_path}")
        
        try:
            # Convert to dictionary
            data = workbook.to_dict()
            
            # Add export metadata
            data['export_metadata'] = {
                'exported_at': datetime.now().isoformat(),
                'total_sheets': len(workbook.sheets)
            }
            
            # Write to file with pretty formatting
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully exported workbook to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting workbook to JSON: {e}", exc_info=True)
            raise
    
    def export_sheet(self, sheet: SheetData, output_filename: Optional[str] = None) -> Path:
        """
        Export a single sheet to a JSON file.
        
        Args:
            sheet: SheetData object to export
            output_filename: Optional custom filename
            
        Returns:
            Path to the exported JSON file
        """
        if not output_filename:
            # Generate filename from sheet name
            safe_name = self._sanitize_filename(sheet.sheet_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{safe_name}_{timestamp}.json"
        
        output_path = self.output_dir / output_filename
        
        logger.info(f"Exporting sheet '{sheet.sheet_name}' to: {output_path}")
        
        try:
            # Convert to dictionary
            data = sheet.to_dict()
            
            # Add export metadata
            data['export_metadata'] = {
                'exported_at': datetime.now().isoformat()
            }
            
            # Write to file with pretty formatting
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully exported sheet to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting sheet to JSON: {e}", exc_info=True)
            raise
    
    def export_workbook_by_sheets(self, workbook: WorkbookData) -> List[Path]:
        """
        Export each sheet in a workbook to separate JSON files.
        
        Args:
            workbook: WorkbookData object to export
            
        Returns:
            List of Paths to exported JSON files
        """
        logger.info(f"Exporting workbook '{workbook.filename}' as separate sheet files")
        
        output_paths = []
        base_name = Path(workbook.filename).stem
        
        for sheet in workbook.sheets:
            safe_sheet_name = self._sanitize_filename(sheet.sheet_name)
            filename = f"{base_name}_{safe_sheet_name}.json"
            path = self.export_sheet(sheet, filename)
            output_paths.append(path)
        
        logger.info(f"Exported {len(output_paths)} sheets")
        return output_paths
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a string to be used as a filename.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Replace spaces and special characters
        safe = filename.replace(' ', '_')
        safe = ''.join(c for c in safe if c.isalnum() or c in ('_', '-'))
        return safe.lower()

