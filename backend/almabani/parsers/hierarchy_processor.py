"""
Hierarchy processor - Build tree structures from flat BOQ data.
Processes items based on levels and subcategory indicators to create nested hierarchies.
"""
import logging
from typing import List, Optional

from almabani.core.models import HierarchyItem, ItemType, SheetData

logger = logging.getLogger(__name__)


class HierarchyProcessor:
    """Processes flat lists of items into hierarchical tree structures."""
    
    def __init__(self, subcategory_indicator: str = 'c'):
        """
        Initialize the hierarchy processor.
        
        Args:
            subcategory_indicator: Character indicating subcategory levels
        """
        self.subcategory_indicator = subcategory_indicator
    
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
        - 'c' levels create sub-hierarchies based on consecutive pairs
        - Items (A, B, C, etc.) are leaf nodes
        
        Args:
            items: Flat list of HierarchyItem objects
            
        Returns:
            List of root-level HierarchyItem objects with children attached
        """
        root_items = []
        level_stack = []  # Stack to track current position in numeric hierarchy
        c_level_stack = []  # Stack to track c-level hierarchy
        current_level = 0
        prev_item_type: Optional[ItemType] = None
        
        i = 0
        while i < len(items):
            item = items[i]
            
            if item.item_type == ItemType.NUMERIC_LEVEL:
                # Handle numeric level - clear c-level stack
                c_level_stack = []
                
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
                prev_item_type = ItemType.NUMERIC_LEVEL
            
            elif item.item_type == ItemType.SUBCATEGORY:
                logger.debug(f"Processing 'c' level at row {item.row_number}: {item.description}")
                
                current_numeric_parent = level_stack[-1] if level_stack else None
                current_c_parent = c_level_stack[-1] if c_level_stack else None
                parent_for_c = None
                
                if prev_item_type == ItemType.SUBCATEGORY:
                    # Previous was c → current is child of previous c
                    parent_for_c = current_c_parent or current_numeric_parent
                elif prev_item_type == ItemType.ITEM:
                    # Previous was an item → make this c a sibling of the last c (i.e., child of its parent)
                    if len(c_level_stack) > 1:
                        parent_for_c = c_level_stack[-2]
                    else:
                        parent_for_c = current_numeric_parent
                else:
                    # Previous was numeric or unknown
                    parent_for_c = current_c_parent or current_numeric_parent
                
                if parent_for_c:
                    parent_for_c.children.append(item)
                else:
                    root_items.append(item)
                
                # Reset c stack to the new branch
                c_level_stack = c_level_stack[:-1] if prev_item_type == ItemType.ITEM and len(c_level_stack) > 1 else []
                c_level_stack.append(item)
                
                prev_item_type = ItemType.SUBCATEGORY
            
            elif item.item_type == ItemType.ITEM:
                # Handle actual items (A, B, C, etc.)
                # Add to c-level if exists, otherwise to numeric level
                
                if c_level_stack:
                    # Add to the current c-level
                    c_level_stack[-1].children.append(item)
                    logger.debug(f"Adding item to c-level: {c_level_stack[-1].description}")
                elif level_stack:
                    # Add to the current numeric level
                    level_stack[-1].children.append(item)
                    logger.debug(f"Adding item to numeric level: {level_stack[-1].description}")
                else:
                    # No parent, add to root
                    root_items.append(item)
                prev_item_type = ItemType.ITEM
            
            else:
                # Unknown items - try to add to current context
                if c_level_stack:
                    c_level_stack[-1].children.append(item)
                elif level_stack:
                    level_stack[-1].children.append(item)
                else:
                    root_items.append(item)
                prev_item_type = ItemType.UNKNOWN
            
            i += 1
        
        return root_items
    
    def _extract_numeric_level(self, level_val) -> Optional[int]:
        """Extract numeric level from a value."""
        try:
            return int(level_val)
        except (ValueError, TypeError):
            return None
    
    def _find_next_significant_item(self, items: List[HierarchyItem], start_idx: int) -> Optional[HierarchyItem]:
        """Find the next item that is not UNKNOWN type."""
        for i in range(start_idx, len(items)):
            if items[i].item_type != ItemType.UNKNOWN:
                return items[i]
        return None
