"""
Hierarchy processor module for building tree structures from flat data.
Processes items based on levels and subcategory indicators to create nested hierarchies.
"""
import logging
from typing import List, Optional, Dict, Any

from models import HierarchyItem, ItemType, SheetData


logger = logging.getLogger(__name__)


class HierarchyProcessor:
    """Processes flat lists of items into hierarchical tree structures."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the hierarchy processor with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.hierarchy_config = config.get('hierarchy', {})
        self.subcategory_indicator = self.hierarchy_config.get('subcategory_indicator', 'c')
    
    def process_sheet(self, sheet_data: SheetData) -> SheetData:
        """
        Process a sheet's flat items into a hierarchical structure.
        
        Args:
            sheet_data: SheetData containing flat list of items
            
        Returns:
            SheetData with processed hierarchical structure
        """
        logger.info(f"Processing hierarchy for sheet: {sheet_data.sheet_name}")
        
        if not sheet_data.hierarchy:
            logger.warning(f"No items to process in sheet {sheet_data.sheet_name}")
            return sheet_data
        
        try:
            # Build the hierarchy
            root_items = self._build_hierarchy(sheet_data.hierarchy)
            sheet_data.hierarchy = root_items
            
            logger.info(f"Built hierarchy with {len(root_items)} root items for sheet {sheet_data.sheet_name}")
            return sheet_data
            
        except Exception as e:
            logger.error(f"Error processing hierarchy for sheet {sheet_data.sheet_name}: {e}", exc_info=True)
            raise
    
    def _build_hierarchy(self, items: List[HierarchyItem]) -> List[HierarchyItem]:
        """
        Build hierarchical structure from flat list of items.
        
        Logic:
        - Numeric levels (1, 2, 3...) define the main hierarchy depth
        - 'c' levels are IGNORED - items go directly under numeric levels
        - Items (A, B, C, etc.) are leaf nodes
        
        Args:
            items: Flat list of HierarchyItem objects
            
        Returns:
            List of root-level HierarchyItem objects with children attached
        """
        root_items = []
        level_stack = []  # Stack to track current position in hierarchy
        current_level = 0
        
        i = 0
        while i < len(items):
            item = items[i]
            
            if item.item_type == ItemType.NUMERIC_LEVEL:
                # Handle numeric level
                new_level = self._extract_numeric_level(item.level)
                
                if new_level is not None:
                    # Adjust level stack based on new level
                    if new_level > current_level:
                        # Going deeper - add current item
                        if level_stack:
                            level_stack[-1].children.append(item)
                        else:
                            root_items.append(item)
                        level_stack.append(item)
                    elif new_level == current_level:
                        # Same level - replace last item at this level
                        if len(level_stack) > 0:
                            level_stack.pop()
                        
                        if level_stack:
                            level_stack[-1].children.append(item)
                        else:
                            root_items.append(item)
                        level_stack.append(item)
                    else:
                        # Going up - pop stack to appropriate level
                        while len(level_stack) >= new_level and level_stack:
                            level_stack.pop()
                        
                        if level_stack:
                            level_stack[-1].children.append(item)
                        else:
                            root_items.append(item)
                        level_stack.append(item)
                    
                    current_level = new_level
            
            elif item.item_type == ItemType.SUBCATEGORY:
                # IGNORE 'c' subcategory levels - skip them
                logger.debug(f"Skipping 'c' level at row {item.row_number}: {item.description}")
                pass
            
            elif item.item_type == ItemType.ITEM:
                # Handle actual items (A, B, C, etc.)
                # Add directly to the current numeric level
                
                if level_stack:
                    # Add to the current numeric level
                    level_stack[-1].children.append(item)
                else:
                    # No parent, add to root
                    root_items.append(item)
            
            else:
                # Unknown items - try to add to current context
                if level_stack:
                    level_stack[-1].children.append(item)
                else:
                    root_items.append(item)
            
            i += 1
        
        return root_items
    
    def _extract_numeric_level(self, level_val: Any) -> Optional[int]:
        """
        Extract numeric level from a value.
        
        Args:
            level_val: Value that might contain a numeric level
            
        Returns:
            Integer level or None
        """
        try:
            return int(level_val)
        except (ValueError, TypeError):
            return None
    
    def _find_next_significant_item(self, items: List[HierarchyItem], start_idx: int) -> Optional[HierarchyItem]:
        """
        Find the next item that is not UNKNOWN type.
        
        Args:
            items: List of all items
            start_idx: Index to start searching from
            
        Returns:
            Next significant HierarchyItem or None
        """
        for i in range(start_idx, len(items)):
            if items[i].item_type != ItemType.UNKNOWN:
                return items[i]
        return None
    
    def _is_empty_or_separator(self, item: HierarchyItem) -> bool:
        """
        Check if an item is empty or just a separator.
        
        Args:
            item: HierarchyItem to check
            
        Returns:
            True if item is empty/separator
        """
        return (
            item.item_type == ItemType.UNKNOWN and
            not item.description and
            not item.item_code
        )
