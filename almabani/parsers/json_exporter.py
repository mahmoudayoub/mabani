"""
JSON exporter - Export workbook data to JSON files.
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List

from almabani.core.models import WorkbookData, SheetData

logger = logging.getLogger(__name__)


class JsonExporter:
    """Export workbook data to JSON format."""
    
    def export_single_file(self, workbook: WorkbookData, output_path: Path) -> Path:
        """
        Export entire workbook to a single JSON file.
        
        Args:
            workbook: WorkbookData to export
            output_path: Path to output JSON file
            
        Returns:
            Path to created file
        """
        logger.info(f"Exporting workbook to single JSON file: {output_path}")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = workbook.to_dict()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Successfully exported to {output_path}")
        return output_path
    
    def export_multiple_files(self, workbook: WorkbookData, output_dir: Path) -> List[Path]:
        """
        Export each sheet to a separate JSON file.
        
        Args:
            workbook: WorkbookData to export
            output_dir: Directory for output files
            
        Returns:
            List of paths to created files
        """
        logger.info(f"Exporting workbook sheets to separate JSON files in {output_dir}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_files = []
        
        for sheet in workbook.sheets:
            # Create filename based on original workbook and sheet name
            filename = f"{workbook.filename.replace('.xlsx', '')}_{sheet.sheet_name}.json"
            # Sanitize filename
            filename = self._sanitize_filename(filename)
            output_path = output_dir / filename
            
            # Export sheet
            data = sheet.to_dict()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            output_files.append(output_path)
            logger.info(f"Exported sheet '{sheet.sheet_name}' to {output_path}")
        
        logger.info(f"Successfully exported {len(output_files)} sheets")
        return output_files
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove invalid characters."""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
