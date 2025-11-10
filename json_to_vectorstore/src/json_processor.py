"""
JSON processor for extracting items from hierarchical JSON files.
Traverses the hierarchy and extracts only items with their metadata.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .models import VectorStoreItem, VectorStoreDocument


logger = logging.getLogger(__name__)


class JSONProcessor:
    """
    Processes hierarchical JSON files and extracts items for vector store.
    Only items with item_type='item' are extracted.
    C-levels and subcategories are included in the category path for proper categorization.
    """
    
    def __init__(self):
        """Initialize the JSON processor."""
        self.items_extracted = 0
    
    def process_file(self, json_path: Path) -> VectorStoreDocument:
        """
        Process a single JSON file and extract all items.
        
        Args:
            json_path: Path to the JSON file
            
        Returns:
            VectorStoreDocument containing all extracted items
        """
        logger.info(f"Processing JSON file: {json_path.name}")
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Get source name (sheet name)
            source_name = data.get('sheet_name', json_path.stem)
            
            # Extract items from hierarchy
            items = []
            hierarchy = data.get('hierarchy', [])
            
            # Build category path and extract items
            self._traverse_hierarchy(
                hierarchy, 
                items=items,
                category_path=[],
                source_name=source_name
            )
            
            logger.info(f"Extracted {len(items)} items from {source_name}")
            
            document = VectorStoreDocument(
                source_name=source_name,
                items=items,
                total_items=len(items)
            )
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing {json_path}: {e}", exc_info=True)
            raise
    
    def _traverse_hierarchy(
        self, 
        nodes: List[Dict[str, Any]], 
        items: List[VectorStoreItem],
        category_path: List[str],
        source_name: str,
        parent_level: Optional[int] = None,
        parent_description: Optional[str] = None,
        grandparent_description: Optional[str] = None
    ):
        """
        Recursively traverse the hierarchy and extract items.
        
        Args:
            nodes: List of hierarchy nodes to traverse
            items: List to append extracted items to
            category_path: Current category path (for metadata)
            source_name: Name of the source sheet
            parent_level: Parent numeric level
            parent_description: Description of the immediate parent
            grandparent_description: Description of the grandparent
        """
        for node in nodes:
            item_type = node.get('item_type', 'unknown')
            level = node.get('level')
            
            # Determine current category path for this node
            current_path = category_path.copy()
            
            # Track parent/grandparent for this branch
            current_parent = parent_description
            current_grandparent = grandparent_description
            
            # Update category path for numeric levels and c-levels
            is_c_level = (str(level).lower().strip() == 'c')
            
            if item_type == 'numeric_level':
                description = node.get('description', '')
                if description and description not in current_path:
                    current_path.append(description)
                
                # Update parent level
                if level is not None:
                    try:
                        parent_level = int(level)
                    except (ValueError, TypeError):
                        pass
                
                # This numeric level becomes the parent for its children
                current_grandparent = current_parent
                current_parent = description
            
            elif is_c_level or item_type == 'subcategory':
                # Include c-levels and subcategories in category path
                description = node.get('description', '')
                if description and description not in current_path:
                    current_path.append(description)
                
                # This c-level/subcategory becomes the parent for its children
                current_grandparent = current_parent
                current_parent = description
            
            # Extract items (not categories)
            if item_type == 'item':
                item = self._extract_item(
                    node, 
                    current_path, 
                    source_name,
                    parent_level,
                    current_parent,
                    current_grandparent
                )
                if item:
                    items.append(item)
            
            # Recursively process children with the updated path and parent info
            children = node.get('children', [])
            if children:
                self._traverse_hierarchy(
                    children, 
                    items, 
                    current_path,
                    source_name,
                    parent_level,
                    current_parent,
                    current_grandparent
                )
    
    def _is_header_row(self, node: Dict[str, Any]) -> bool:
        """
        Check if a node is a header row (not actual data).
        
        Header rows typically have:
        - item_code = "Item" or "item_code"
        - unit = "Unit" 
        - description = "Bill description" or "Description"
        
        Args:
            node: The node to check
            
        Returns:
            True if this is a header row, False otherwise
        """
        item_code = str(node.get('item_code', '')).lower()
        unit = str(node.get('unit', '')).lower()
        description = str(node.get('description', '')).lower()
        
        # Check for common header patterns
        header_indicators = [
            item_code in ['item', 'item_code', 'code'],
            unit in ['unit', 'units', 'uom'],
            description in ['description', 'bill description', 'item description'],
        ]
        
        # If 2 or more indicators match, it's likely a header
        return sum(header_indicators) >= 2
    
    def _extract_item(
        self, 
        node: Dict[str, Any], 
        category_path: List[str],
        source_name: str,
        parent_level: Optional[int],
        parent_description: Optional[str] = None,
        grandparent_description: Optional[str] = None
    ) -> Optional[VectorStoreItem]:
        """
        Extract a single item from a node.
        
        Args:
            node: The node containing item data
            category_path: Current category path
            source_name: Source sheet name
            parent_level: Parent numeric level
            parent_description: Description of the immediate parent
            grandparent_description: Description of the grandparent
            category_path: Current category path
            source_name: Source sheet name
            parent_level: Parent numeric level
            
        Returns:
            VectorStoreItem or None if description is missing or is a header row
        """
        # Skip header rows
        if self._is_header_row(node):
            logger.debug(f"Skipping header row: {node.get('description', 'unknown')}")
            return None
        
        # Get description (required for embedding)
        description = node.get('description') or node.get('full_description')
        
        if not description:
            logger.debug(f"Skipping item without description: {node.get('item_code', 'unknown')}")
            return None
        
        # Build enriched text for embedding with parent and grandparent context
        text_parts = []
        
        # Add grandparent if available
        if grandparent_description:
            text_parts.append(grandparent_description)
        
        # Add parent if available
        if parent_description:
            text_parts.append(parent_description)
        
        # Add the main description
        text_parts.append(description)
        
        # Combine all parts (just values separated by |, no labels)
        enriched_text = " | ".join(text_parts)
        
        # Create unique ID
        item_code = node.get('item_code', 'unknown')
        row_number = node.get('row_number', 0)
        item_id = self._generate_id(source_name, parent_level, item_code, row_number)
        
        # Build metadata
        metadata = {
            'source_sheet': source_name,
            'category_path': ' > '.join(category_path) if category_path else 'Root',
        }
        
        # Add all available fields to metadata
        if node.get('item_code'):
            metadata['item_code'] = node['item_code']
        if node.get('unit'):
            metadata['unit'] = node['unit']
        if node.get('rate') is not None:
            metadata['rate'] = node['rate']
        if parent_level is not None:
            metadata['level'] = parent_level
        if node.get('trade'):
            metadata['trade'] = node['trade']
        if node.get('code'):
            metadata['code'] = node['code']
        if node.get('row_number'):
            metadata['row_number'] = node['row_number']
        if node.get('full_description') and node.get('full_description') != description:
            metadata['full_description'] = node['full_description']
        
        # Store parent and grandparent in metadata for reference
        if parent_description:
            metadata['parent'] = parent_description
        if grandparent_description:
            metadata['grandparent'] = grandparent_description
        
        # Create VectorStoreItem with enriched text
        item = VectorStoreItem(
            id=item_id,
            text=enriched_text,
            metadata=metadata
        )
        
        self.items_extracted += 1
        return item
    
    def _generate_id(
        self, 
        source_name: str, 
        level: Optional[int], 
        item_code: str,
        row_number: int
    ) -> str:
        """
        Generate a unique ID for an item.
        
        Args:
            source_name: Source sheet name
            level: Numeric level
            item_code: Item code
            row_number: Row number in original file
            
        Returns:
            Unique identifier string
        """
        # Sanitize source name
        safe_source = source_name.replace(' ', '_').replace('-', '_').lower()
        safe_source = ''.join(c for c in safe_source if c.isalnum() or c == '_')
        
        # Build ID
        parts = [safe_source]
        
        if level is not None:
            parts.append(f"l{level}")
        
        if item_code and item_code != 'unknown':
            safe_code = str(item_code).replace(' ', '_')
            parts.append(safe_code)
        
        if row_number:
            parts.append(f"r{row_number}")
        
        return '_'.join(parts)
    
    def process_directory(self, input_dir: Path) -> List[VectorStoreDocument]:
        """
        Process all JSON files in a directory.
        
        Args:
            input_dir: Directory containing JSON files
            
        Returns:
            List of VectorStoreDocument objects
        """
        logger.info(f"Processing directory: {input_dir}")
        
        # Find all JSON files
        json_files = list(input_dir.glob('*.json'))
        
        if not json_files:
            logger.warning(f"No JSON files found in {input_dir}")
            return []
        
        logger.info(f"Found {len(json_files)} JSON file(s)")
        
        documents = []
        
        for json_file in json_files:
            try:
                doc = self.process_file(json_file)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to process {json_file.name}: {e}")
                continue
        
        total_items = sum(len(doc.items) for doc in documents)
        logger.info(f"Processed {len(documents)} documents with {total_items} total items")
        
        return documents
