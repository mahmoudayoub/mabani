"""
Centralized configuration management using Pydantic.
All environment variables and settings are defined here.
"""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache
from dotenv import load_dotenv


def _find_and_load_dotenv():
    """Find and load .env file from multiple possible locations."""
    possible_paths = [
        Path.cwd() / '.env',  # Current working directory
        Path(__file__).parent.parent.parent / '.env',  # Project root
        Path(__file__).parent.parent.parent.parent / '.env',  # One more level up
    ]
    
    for path in possible_paths:
        if path.exists():
            load_dotenv(path, override=True)
            return path
    
    return None


# Load .env BEFORE importing pydantic_settings
_env_path = _find_and_load_dotenv()

# Now import pydantic after env is loaded
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    Pydantic-settings automatically maps:
    - OPENAI_API_KEY env var -> openai_api_key field
    - S3_VECTORS_BUCKET env var -> s3_vectors_bucket field
    etc. (case-insensitive matching)
    """
    
    # ==================== API Keys ====================
    openai_api_key: str
    
    # ==================== OpenAI Settings ====================
    openai_embedding_model: str = 'text-embedding-3-small'
    openai_chat_model: str = 'gpt-5-mini-2025-08-07'
    openai_temperature: float = 1.0
    openai_max_retries: int = 3
    openai_timeout: int = 60
    
    # ==================== S3 Vectors Settings ====================
    s3_vectors_bucket: str = 'almabani-vectors'
    s3_vectors_index_name: str = 'almabani'
    s3_vectors_dimension: int = 1536
    
    # ==================== Storage Settings ====================
    storage_type: str = 's3'  # 'local' or 's3'
    s3_bucket_name: Optional[str] = None
    aws_region: str = 'eu-west-1'
    
    # ==================== Vector Search Settings ====================
    similarity_threshold: float = 0.5
    top_k: int = 10  # Rate filler default
    
    # ==================== Processing Settings ====================
    batch_size: int = 500
    max_workers: int = 200
    max_concurrent: int = 20  # Max concurrent matching tasks
    
    # ==================== Rate Limits ====================
    embeddings_rpm: int = 3000
    chat_rpm: int = 5000
    
    # ==================== Price Code Settings ====================
    pricecode_index_name: str = 'almabani-pricecode'
    pricecode_top_k: int = 150  # Price code uses more candidates
    pricecode_batch_size: int = 100
    pricecode_max_concurrent: int = 200
    pricecode_max_candidates: int = 1  # Lexical candidates to send to LLM
    pricecode_index_db: str = '/tmp/pricecode_index.db'  # SQLite index path
    
    # ==================== Logging Settings ====================
    log_level: str = 'INFO'
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # ==================== File Paths ====================
    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent.parent
    
    @property
    def input_dir(self) -> Path:
        """Default input directory."""
        return self.project_root / "input"
    
    @property
    def output_dir(self) -> Path:
        """Default output directory."""
        return self.project_root / "output"
    
    @property
    def logs_dir(self) -> Path:
        """Default logs directory."""
        return self.project_root / "logs"
    
    class Config:
        """Pydantic-settings v2 configuration."""
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False
        extra = 'ignore'


# Use a simple cache - don't use @lru_cache as it can cause issues
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get settings instance (created once, reused after).
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reset_settings():
    """Reset settings cache (useful for testing or reloading)."""
    global _settings_instance
    _settings_instance = None


def get_openai_client():
    """Get configured OpenAI client."""
    from openai import OpenAI
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries
    )


def get_vector_store():
    """Get configured vector store client (S3 Vectors)."""
    from almabani.core.vector_store import VectorStoreService
    settings = get_settings()
    return VectorStoreService(
        bucket_name=settings.s3_vectors_bucket,
        region=settings.aws_region,
        index_name=settings.s3_vectors_index_name
    )
