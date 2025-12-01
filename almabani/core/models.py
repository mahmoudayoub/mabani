"""
Shared data models for Almabani.
Consolidates models from all pipelines.
"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ==================== Parser Models ====================

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


# ==================== Vector Store Models ====================

class VectorStoreItem(BaseModel):
    """
    Represents an item prepared for vector store ingestion.
    The description will be embedded, and all other fields stored as metadata.
    """
    # The text to be embedded
    text: str = Field(description="The description text to be embedded")
    
    # Metadata fields
    metadata: Dict[str, Any] = Field(default_factory=dict, description="All item metadata")
    
    # Unique identifier
    id: str = Field(description="Unique identifier for this item")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "sheet1_level2_itemA",
                "text": "Manual excavation in all types of soil",
                "metadata": {
                    "item_code": "A",
                    "unit": "m3",
                    "rate": 50.0,
                    "level": 3,
                    "category_path": "Site Work > Earthwork > Excavation",
                    "sheet_name": "3-Hilton",
                    "trade": "X",
                    "code": "X3123160",
                    "row_number": 25
                }
            }
        }


class VectorStoreDocument(BaseModel):
    """
    Represents a collection of items from a single source (sheet).
    """
    source_name: str = Field(description="Name of the source (sheet name)")
    items: List[VectorStoreItem] = Field(default_factory=list)
    total_items: int = Field(default=0, description="Total number of items")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "source_name": self.source_name,
            "total_items": len(self.items),
            "items": [
                {
                    "id": item.id,
                    "text": item.text,
                    "metadata": item.metadata
                }
                for item in self.items
            ]
        }


class VectorStoreBatch(BaseModel):
    """
    Represents a batch of documents ready for vector store ingestion.
    """
    documents: List[VectorStoreDocument] = Field(default_factory=list)
    total_documents: int = Field(default=0)
    total_items: int = Field(default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "total_documents": len(self.documents),
            "total_items": sum(len(doc.items) for doc in self.documents),
            "documents": [doc.to_dict() for doc in self.documents]
        }


# ==================== Rate Matcher Models ====================

class MatchStatus(str, Enum):
    """Status of a match attempt."""
    EXACT_MATCH = "exact_match"  # Matcher stage
    EXPERT_MATCH = "expert_match"  # Expert stage
    ESTIMATED = "estimated"  # Estimator stage
    NO_MATCH = "no_match"  # No valid match found


class MatchResult(BaseModel):
    """Result of matching a single BOQ item."""
    # Input item info
    item_code: str
    description: str
    unit: Optional[str] = None
    original_rate: Optional[float] = None
    
    # Match result
    status: MatchStatus
    matched_rate: Optional[float] = None
    confidence: Optional[float] = None
    
    # Matching details
    matched_description: Optional[str] = None
    matched_item_id: Optional[str] = None
    similarity_score: Optional[float] = None
    
    # LLM reasoning
    reasoning: Optional[str] = None
    stage: Optional[str] = None  # "matcher", "expert", "estimator"
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


class ProcessingReport(BaseModel):
    """Summary report of processing results."""
    total_items: int = 0
    processed_items: int = 0
    exact_matches: int = 0
    expert_matches: int = 0
    estimates: int = 0
    no_matches: int = 0
    errors: int = 0
    
    # Statistics
    avg_confidence: Optional[float] = None
    avg_similarity: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    
    # Details
    error_items: List[str] = Field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "exact_matches": self.exact_matches,
            "expert_matches": self.expert_matches,
            "estimates": self.estimates,
            "no_matches": self.no_matches,
            "errors": self.errors,
            "avg_confidence": self.avg_confidence,
            "avg_similarity": self.avg_similarity,
            "processing_time_seconds": self.processing_time_seconds,
            "error_items": self.error_items
        }
