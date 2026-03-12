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
                new_level = self._extract_numeric_level(item.level)
                
                if new_level is not None:
                    # ── If c-levels precede this numeric (no items in between),
                    # attach to the deepest c-level so the c's act as a bridge
                    # between the numeric above and this numeric below.
                    if c_level_stack and prev_item_type == ItemType.SUBCATEGORY:
                        c_level_stack[-1].children.append(item)
                        # Clear c stack — the bridge is consumed
                        c_level_stack = []
                        level_stack.append(item)
                        current_level = new_level
                        prev_item_type = ItemType.NUMERIC_LEVEL
                        i += 1
                        continue

                    # Normal numeric handling (no preceding c-levels)
                    c_level_stack = []

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
                parent_for_c = None
                
                if prev_item_type == ItemType.SUBCATEGORY:
                    # ── Rule 1: consecutive c's nest (parent→child) ──
                    # Previous was also a c → current becomes child of that c.
                    # Stack preserves the full chain so ancestors are reachable.
                    parent_for_c = c_level_stack[-1] if c_level_stack else current_numeric_parent
                    # Append to stack (keep entire chain: c1, c2, c3, …)
                    if parent_for_c:
                        parent_for_c.children.append(item)
                    else:
                        root_items.append(item)
                    c_level_stack.append(item)
                
                elif prev_item_type == ItemType.ITEM:
                    # After items we need lookahead to distinguish Rule 2 vs Rule 3.
                    next_sig = self._find_next_significant_item(items, i + 1)
                    next_is_c = (next_sig is not None
                                 and next_sig.item_type == ItemType.SUBCATEGORY)
                    
                    if next_is_c:
                        # ── Rule 3: items → consecutive c's → RESET ──
                        # Two or more c's after items: reset c_level_stack,
                        # attach to the numeric parent, start fresh chain.
                        parent_for_c = current_numeric_parent
                        if parent_for_c:
                            parent_for_c.children.append(item)
                        else:
                            root_items.append(item)
                        c_level_stack = [item]
                    else:
                        # ── Rule 2: items → single c → sibling of last c ──
                        # Pop the leaf c, make new c a sibling (child of
                        # the leaf's parent in the c stack).
                        if len(c_level_stack) > 1:
                            c_level_stack.pop()           # remove leaf
                            parent_for_c = c_level_stack[-1]
                        else:
                            parent_for_c = current_numeric_parent
                        if parent_for_c:
                            parent_for_c.children.append(item)
                        else:
                            root_items.append(item)
                        c_level_stack.append(item)
                
                else:
                    # Previous was numeric or unknown → first c under numeric
                    parent_for_c = current_numeric_parent
                    if parent_for_c:
                        parent_for_c.children.append(item)
                    else:
                        root_items.append(item)
                    c_level_stack = [item]
                
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
