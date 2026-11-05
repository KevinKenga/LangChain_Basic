"""
Configuration Management Module.
This code uses pydantic-settings to safely load and validate your .env file.
This module is responsible for loading, validating, and providing access to 
application settings and secrets. It uses Pydantic's BaseSettings to 
automatically read from environment variables and the .env file.

Usage:
    from src.shared.config import settings
    print(settings.openai_api_key)
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """
    Application Settings Schema.
    
    Attributes:
        openai_api_key (str): Key for accessing OpenAI models.
        openai_model_name (str): Model identifier (e.g., 'gpt-4o').
        firecrawl_api_key (str): Key for the Firecrawl web scraping service.
        langchain_api_key (Optional[str]): Key for LangSmith observability.
        langchain_tracing_v2 (bool): Flag to enable/disable tracing.
    """

    # --- AI Configuration (The Brain) ---
    openai_api_key: str = Field(
        ..., 
        description="OpenAI API Key for the LLM agents."
    )
    openai_model_name: str = Field(
        "gpt-4o", 
        description="The OpenAI model to use for agents."
    )

    # --- Tool Configuration (The Eyes) ---
    firecrawl_api_key: str = Field(
        ..., 
        description="API Key for Firecrawl scraping service."
    )

    # --- Observability Configuration (The Microscope) ---
    langchain_tracing_v2: bool = Field(
        False, 
        description="Enable LangSmith tracing."
    )
    langchain_api_key: Optional[str] = Field(
        None, 
        description="LangSmith API Key (required if tracing is True)."
    )

    # --- Azure Infrastructure (The Body) ---
    azure_postgres_connection_string: Optional[str] = Field(
        None, 
        description="Connection string for Azure PostgreSQL Database."
    )
    azure_blob_storage_connection_string: Optional[str] = Field(
        None, 
        description="Connection string for Azure Blob Storage."
    )

    # Pydantic Config: Tells it to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra keys in .env
    )

@lru_cache()
def get_settings() -> Settings:
    """
    Creates and caches the Settings object.

    Using lru_cache ensures we only read the .env file once on startup,
    improving performance.

    Returns:
        Settings: The validated application configuration.
    """
    return Settings()

# Instantiate the settings object for easy import
settings = get_settings()