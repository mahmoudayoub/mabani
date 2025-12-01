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
            
            elif item.item_type == ItemType.SUBCATEGORY:
                # Handle 'c' subcategory levels with consecutive c-level logic
                logger.debug(f"Processing 'c' level at row {item.row_number}: {item.description}")
                
                # Look ahead to see if next item is also a c-level
                next_item = self._find_next_significant_item(items, i + 1)
                next_is_c_level = (next_item and next_item.item_type == ItemType.SUBCATEGORY)
                
                if next_is_c_level:
                    # Consecutive c-levels: current c is PARENT of next c
                    # Clear c_level_stack to start fresh parent-child relationship
                    c_level_stack = []
                    
                    # Add this c-level to numeric level's children
                    if level_stack:
                        level_stack[-1].children.append(item)
                    else:
                        root_items.append(item)
                    
                    # This becomes the new c-parent
                    c_level_stack.append(item)
                    logger.debug(f"  → Parent c-level (followed by another c)")
                else:
                    # NOT followed by another c-level (items follow)
                    # This is a SIBLING of previous c-level
                    
                    if len(c_level_stack) >= 2:
                        # Pop the last c (it was only for its own items)
                        c_level_stack.pop()
                    
                    # Add as child of remaining stack or numeric level
                    if c_level_stack:
                        # Add as child of parent c-level
                        c_level_stack[-1].children.append(item)
                        logger.debug(f"  → Child of c-level: {c_level_stack[-1].description}")
                    elif level_stack:
                        # No c-parent, add to numeric level
                        level_stack[-1].children.append(item)
                        logger.debug(f"  → Child of numeric level: {level_stack[-1].description}")
                    else:
                        root_items.append(item)
                    
                    # Add to c_level_stack for its own children
                    c_level_stack.append(item)
            
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
            
            else:
                # Unknown items - try to add to current context
                if c_level_stack:
                    c_level_stack[-1].children.append(item)
                elif level_stack:
                    level_stack[-1].children.append(item)
                else:
                    root_items.append(item)
            
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
