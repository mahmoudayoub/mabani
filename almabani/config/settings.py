"""
Centralized configuration management using Pydantic.
All environment variables and settings are defined here.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ==================== API Keys ====================
    openai_api_key: str = Field(..., env='OPENAI_API_KEY')
    pinecone_api_key: str = Field(..., env='PINECONE_API_KEY')
    
    # ==================== OpenAI Settings ====================
    openai_embedding_model: str = Field(
        default='text-embedding-3-small',
        env='OPENAI_EMBEDDING_MODEL'
    )
    openai_chat_model: str = Field(
        default='gpt-4o-mini',
        env='OPENAI_CHAT_MODEL'
    )
    openai_temperature: float = Field(default=0.0, env='OPENAI_TEMPERATURE')
    openai_max_retries: int = Field(default=3, env='OPENAI_MAX_RETRIES')
    openai_timeout: int = Field(default=60, env='OPENAI_TIMEOUT')
    
    # ==================== Pinecone Settings ====================
    pinecone_environment: str = Field(
        default='us-east-1',
        env='PINECONE_ENVIRONMENT'
    )
    pinecone_index_name: str = Field(
        default='almabani',
        env='PINECONE_INDEX_NAME'
    )
    pinecone_namespace: Optional[str] = Field(default=None, env='PINECONE_NAMESPACE')
    pinecone_dimension: int = Field(default=1536, env='PINECONE_DIMENSION')
    pinecone_metric: str = Field(default='cosine', env='PINECONE_METRIC')
    pinecone_cloud: str = Field(default='aws', env='PINECONE_CLOUD')
    
    # ==================== Vector Search Settings ====================
    similarity_threshold: float = Field(default=0.7, env='SIMILARITY_THRESHOLD')
    top_k: int = Field(default=6, env='TOP_K')
    
    # ==================== Processing Settings ====================
    batch_size: int = Field(default=500, env='BATCH_SIZE')
    max_workers: int = Field(default=5, env='MAX_WORKERS')
    
    # ==================== Logging Settings ====================
    log_level: str = Field(default='INFO', env='LOG_LEVEL')
    log_format: str = Field(
        default='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        env='LOG_FORMAT'
    )
    
    # ==================== File Paths ====================
    # These are computed from the project root
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
        """Pydantic configuration."""
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False
        # Look for .env in project root
        env_file = str(Path(__file__).parent.parent.parent / '.env')


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures we only load settings once and reuse the same instance.
    """
    return Settings()


# Convenience function to get specific setting values
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
