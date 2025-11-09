"""
Data models for the Excel to JSON pipeline.
Defines the structure of hierarchy items, categories, and sheets.
"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class ItemType(str, Enum):
    """Types of items in the hierarchy."""
    NUMERIC_LEVEL = "numeric_level"  # 1, 2, 3, etc.
    SUBCATEGORY = "subcategory"  # 'c' character
    ITEM = "item"  # A, B, C or actual items with codes
    UNKNOWN = "unknown"


class HierarchyItem(BaseModel):
    """
    Represents a single item in the hierarchy.
    Can be a category, subcategory, or an actual item with details.
    """
    level: Optional[Any] = None
    item_code: Optional[Any] = None  # Can be string or number
    description: Optional[Any] = None  # Can be string or number
    unit: Optional[Any] = None  # Can be string or number
    rate: Optional[float] = None
    trade: Optional[Any] = None  # Can be string or number
    code: Optional[Any] = None  # Can be string or number
    full_description: Optional[Any] = None  # Can be string or number
    item_type: ItemType = ItemType.UNKNOWN
    row_number: Optional[int] = None
    children: List["HierarchyItem"] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True
        
    @field_validator('rate', mode='before')
    @classmethod
    def validate_rate(cls, v):
        """Convert rate to float, handling various formats."""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
    
    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values and empty children."""
        data = {
            "level": self.level,
            "item_code": self.item_code,
            "description": self.description,
            "unit": self.unit,
            "rate": self.rate,
            "trade": self.trade,
            "code": self.code,
            "full_description": self.full_description,
            "item_type": self.item_type,
            "row_number": self.row_number,
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        # Add children if requested and present
        if include_children and self.children:
            data["children"] = [child.to_dict() for child in self.children]
        
        return data


class SheetData(BaseModel):
    """Represents data from a single Excel sheet."""
    sheet_name: str
    hierarchy: List[HierarchyItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "sheet_name": self.sheet_name,
            "hierarchy": [item.to_dict() for item in self.hierarchy],
            "metadata": self.metadata
        }


class WorkbookData(BaseModel):
    """Represents data from an entire Excel workbook."""
    filename: str
    sheets: List[SheetData] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "filename": self.filename,
            "sheets": [sheet.to_dict() for sheet in self.sheets],
            "metadata": self.metadata
        }


# Update forward references
HierarchyItem.model_rebuild()
