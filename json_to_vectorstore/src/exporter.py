"""
Exporter for vector store prepared data.
Supports multiple output formats for different vector stores.
"""
import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from .models import VectorStoreDocument, VectorStoreBatch


logger = logging.getLogger(__name__)


class VectorStoreExporter:
    """
    Exports prepared data in formats suitable for vector stores.
    """
    
    def __init__(self, output_dir: Path):
        """
        Initialize the exporter.
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_json(
        self, 
        documents: List[VectorStoreDocument],
        filename: str = None
    ) -> Path:
        """
        Export documents as JSON.
        
        Args:
            documents: List of documents to export
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vectorstore_items_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        logger.info(f"Exporting to JSON: {output_path}")
        
        # Create batch
        batch = VectorStoreBatch(documents=documents)
        
        # Export
        data = batch.to_dict()
        data['export_metadata'] = {
            'exported_at': datetime.now().isoformat(),
            'format': 'json',
            'total_documents': len(documents),
            'total_items': sum(len(doc.items) for doc in documents)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(documents)} documents to {output_path}")
        return output_path
    
    def export_jsonl(
        self, 
        documents: List[VectorStoreDocument],
        filename: str = None
    ) -> Path:
        """
        Export as JSON Lines (one item per line).
        Common format for many vector stores.
        
        Args:
            documents: List of documents to export
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vectorstore_items_{timestamp}.jsonl"
        
        output_path = self.output_dir / filename
        
        logger.info(f"Exporting to JSONL: {output_path}")
        
        item_count = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            for doc in documents:
                for item in doc.items:
                    # Each line is a complete JSON object
                    line_data = {
                        'id': item.id,
                        'text': item.text,
                        'metadata': item.metadata
                    }
                    f.write(json.dumps(line_data, ensure_ascii=False) + '\n')
                    item_count += 1
        
        logger.info(f"Exported {item_count} items to {output_path}")
        return output_path
    
    def export_csv(
        self, 
        documents: List[VectorStoreDocument],
        filename: str = None
    ) -> Path:
        """
        Export as CSV.
        Metadata is serialized as JSON string.
        
        Args:
            documents: List of documents to export
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vectorstore_items_{timestamp}.csv"
        
        output_path = self.output_dir / filename
        
        logger.info(f"Exporting to CSV: {output_path}")
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow(['id', 'text', 'metadata_json'])
            
            # Write items
            item_count = 0
            for doc in documents:
                for item in doc.items:
                    writer.writerow([
                        item.id,
                        item.text,
                        json.dumps(item.metadata, ensure_ascii=False)
                    ])
                    item_count += 1
        
        logger.info(f"Exported {item_count} items to {output_path}")
        return output_path
    
    def export_separate_documents(
        self, 
        documents: List[VectorStoreDocument],
        format: str = 'json'
    ) -> List[Path]:
        """
        Export each document as a separate file.
        
        Args:
            documents: List of documents to export
            format: Output format ('json' or 'jsonl')
            
        Returns:
            List of paths to exported files
        """
        logger.info(f"Exporting {len(documents)} documents as separate files")
        
        output_paths = []
        
        for doc in documents:
            # Create safe filename from source name
            safe_name = doc.source_name.replace(' ', '_').replace('-', '_').lower()
            safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
            
            if format == 'all':
                # Export all formats for this document
                all_exports = self.export_all_formats([doc], safe_name)
                output_paths.extend(all_exports.values())
            else:
                filename = f"{safe_name}_vectorstore.{format}"
                
                if format == 'json':
                    output_path = self.export_json([doc], filename)
                elif format == 'jsonl':
                    output_path = self.export_jsonl([doc], filename)
                elif format == 'csv':
                    output_path = self.export_csv([doc], filename)
                else:
                    raise ValueError(f"Unsupported format: {format}")
                
                output_paths.append(output_path)
        
        logger.info(f"Exported {len(output_paths)} separate files")
        return output_paths
    
    def export_all_formats(
        self, 
        documents: List[VectorStoreDocument],
        prefix: str = "vectorstore_items"
    ) -> Dict[str, Path]:
        """
        Export in all supported formats.
        
        Args:
            documents: List of documents to export
            prefix: Filename prefix
            
        Returns:
            Dictionary mapping format to file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        exports = {}
        
        # JSON
        json_file = f"{prefix}_{timestamp}.json"
        exports['json'] = self.export_json(documents, json_file)
        
        # JSONL
        jsonl_file = f"{prefix}_{timestamp}.jsonl"
        exports['jsonl'] = self.export_jsonl(documents, jsonl_file)
        
        # CSV
        csv_file = f"{prefix}_{timestamp}.csv"
        exports['csv'] = self.export_csv(documents, csv_file)
        
        logger.info(f"Exported all formats: {list(exports.keys())}")
        return exports
