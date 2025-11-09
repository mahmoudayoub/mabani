"""
JSON to Vector Store Preparation Module
Extracts items from hierarchical JSON for vector store ingestion.
"""
__version__ = '1.0.0'

from .models import VectorStoreItem, VectorStoreDocument, VectorStoreBatch
from .json_processor import JSONProcessor
from .exporter import VectorStoreExporter
from .pipeline import VectorStorePreparationPipeline
from .embeddings_generator import EmbeddingsGenerator
from .pinecone_uploader import PineconeUploader

__all__ = [
    'VectorStoreItem',
    'VectorStoreDocument',
    'VectorStoreBatch',
    'JSONProcessor',
    'VectorStoreExporter',
    'VectorStorePreparationPipeline',
    'EmbeddingsGenerator',
    'PineconeUploader',
]
