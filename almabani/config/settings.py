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
    - PINECONE_API_KEY env var -> pinecone_api_key field
    etc. (case-insensitive matching)
    """
    
    # ==================== API Keys ====================
    openai_api_key: str
    pinecone_api_key: str
    
    # ==================== OpenAI Settings ====================
    openai_embedding_model: str = 'text-embedding-3-small'
    openai_chat_model: str = 'gpt-4o-mini'
    openai_temperature: float = 0.0
    openai_max_retries: int = 3
    openai_timeout: int = 60
    
    # ==================== Pinecone Settings ====================
    pinecone_environment: str = 'us-east-1'
    pinecone_index_name: str = 'almabani'
    pinecone_namespace: Optional[str] = None
    pinecone_dimension: int = 1536
    pinecone_metric: str = 'cosine'
    pinecone_cloud: str = 'aws'
    
    # ==================== Vector Search Settings ====================
    similarity_threshold: float = 0.5
    top_k: int = 6
    
    # ==================== Processing Settings ====================
    batch_size: int = 500
    max_workers: int = 100
    pinecone_batch_size: int = 300
    
    # ==================== Rate Limits ====================
    embeddings_rpm: int = 3000
    chat_rpm: int = 5000
    
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


def get_pinecone_client():
    """Get configured Pinecone client."""
    from pinecone import Pinecone
    settings = get_settings()
    return Pinecone(api_key=settings.pinecone_api_key)
