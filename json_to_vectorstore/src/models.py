"""
Data models for vector store preparation.
Defines the structure of items to be embedded and their metadata.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


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
