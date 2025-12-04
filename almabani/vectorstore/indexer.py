"""
JSON to Vector Store Pipeline.
Processes hierarchical JSON BOQ files and prepares them for vector store indexing.
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from almabani.core.models import VectorStoreItem, VectorStoreDocument
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


class JSONProcessor:
    """Extract items from hierarchical JSON files for vector indexing."""
    
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
    
    def process_directory(self, input_dir: Path) -> List[VectorStoreDocument]:
        """Process all JSON files in a directory."""
        logger.info(f"Processing directory: {input_dir}")
        
        json_files = list(input_dir.glob('*.json'))
        logger.info(f"Found {len(json_files)} JSON files")
        
        documents = []
        for json_file in json_files:
            try:
                doc = self.process_file(json_file)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to process {json_file}: {e}")
                continue
        
        return documents
    
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
        """Recursively traverse the hierarchy and extract items."""
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
            
            # Recursively process children
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
    
    def _extract_item(
        self,
        node: Dict[str, Any],
        category_path: List[str],
        source_name: str,
        parent_level: Optional[int],
        parent_description: Optional[str],
        grandparent_description: Optional[str]
    ) -> Optional[VectorStoreItem]:
        """Extract a single item from a node."""
        description = node.get('description')
        if not description:
            return None
        
        # Build comprehensive text for embedding
        # Use only 2 levels (grandparent > parent) to match query structure
        text_parts = []
        
        # Add category (only grandparent + parent, max 2 levels)
        category_segments = []
        if grandparent_description:
            category_segments.append(grandparent_description)
        if parent_description and parent_description not in category_segments:
            category_segments.append(parent_description)
        if category_segments:
            text_parts.append(f"Category: {' > '.join(category_segments)}")
        
        # Add description
        text_parts.append(description)
        
        # Add unit if exists
        unit = node.get('unit')
        if unit:
            text_parts.append(f"Unit: {unit}")
        
        text = '. '.join(text_parts)
        
        # Build unique ID
        item_code = node.get('item_code', '')
        row_number = node.get('row_number', 0)
        item_id = f"{source_name}_{parent_level or 'root'}_{item_code}_{row_number}"
        
        # Build metadata
        metadata = {
            'item_code': str(item_code) if item_code else '',
            'description': description,
            'unit': str(unit) if unit else '',
            'rate': float(node.get('rate')) if node.get('rate') else None,
            'level': parent_level,
            'category_path': ' > '.join(category_path) if category_path else '',
            'sheet_name': source_name,
            'parent': parent_description or '',
            'grandparent': grandparent_description or '',
            'row_number': row_number
        }
        
        # Add optional fields
        for field in ['trade', 'code', 'full_description']:
            value = node.get(field)
            if value:
                metadata[field] = str(value)
        
        return VectorStoreItem(
            id=item_id,
            text=text,
            metadata=metadata
        )


class VectorStoreIndexer:
    """Index items into vector store with embeddings (async only)."""
    
    def __init__(
        self,
        embeddings_service: EmbeddingsService,
        vector_store_service: VectorStoreService
    ):
        self.embeddings = embeddings_service
        self.vector_store = vector_store_service
    
    async def index_documents(
        self,
        documents: List[VectorStoreDocument],
        embedding_batch_size: int = 500,
        upsert_batch_size: int = 300,
        namespace: str = '',
        max_workers: int = 100
    ) -> Dict[str, Any]:
        """
        Async variant of index_documents using async embeddings and uploads.
        """
        logger.info(f"[async] Indexing {len(documents)} documents...")
        
        all_items = []
        for doc in documents:
            all_items.extend([item.model_dump() for item in doc.items])
        
        logger.info(f"[async] Total items to index: {len(all_items)}")
        
        items_with_embeddings = await self.embeddings.embed_items(
            all_items,
            text_field='text',
            max_workers=max_workers
        )
        
        result = await self.vector_store.upload_vectors(
            items_with_embeddings,
            batch_size=upsert_batch_size,
            namespace=namespace,
            max_workers=max_workers
        )
        
        logger.info(f"[async] ✓ Indexing complete!")
        return result
