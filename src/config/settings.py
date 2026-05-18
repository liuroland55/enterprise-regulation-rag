"""
Configuration Module for RAG2 System

This module provides a dual-mode configuration system that allows seamless switching
between Cloud (OpenAI) and Local (Ollama) LLM backends without changing any business logic.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings


class Settings(BaseSettings):
    """
    Centralized configuration for the RAG2 system.
    Loads values from environment variables using Pydantic.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    # Operating Mode
    MODE: Literal["CLOUD", "LOCAL"] = "CLOUD"
    
    # Cloud Mode Configuration (OpenAI)
    OPENAI_API_KEY: str = ""
    
    # Local Mode Configuration (Ollama)
    # Note: Ollama does NOT require an API key
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    
    # Vector Database Configuration
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    
    # RAG System Parameters
    MAX_ITERATIONS: int = 3
    RETRIEVAL_K: int = 4


# Global settings instance
config = Settings()


def get_llm() -> BaseChatModel:
    """
    Factory function to create LLM instance based on current mode.
    
    Returns:
        BaseChatModel: Configured LLM instance (ChatOpenAI or ChatOllama)
        
    Raises:
        ValueError: If required configuration is missing for the selected mode
    """
    if config.MODE == "CLOUD":
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when MODE=CLOUD. "
                "Please set it in your .env file."
            )
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=config.OPENAI_API_KEY,
        )
    
    elif config.MODE == "LOCAL":
        # Critical: Ollama does NOT need an API key
        # We only pass model and base_url
        return ChatOllama(
            model=config.OLLAMA_CHAT_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            temperature=0,
        )
    
    else:
        raise ValueError(f"Invalid MODE: {config.MODE}. Must be 'CLOUD' or 'LOCAL'.")


def get_embeddings() -> Embeddings:
    """
    Factory function to create embeddings instance based on current mode.
    
    Returns:
        Embeddings: Configured embeddings instance (OpenAIEmbeddings or OllamaEmbeddings)
        
    Raises:
        ValueError: If required configuration is missing for the selected mode
    """
    if config.MODE == "CLOUD":
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when MODE=CLOUD. "
                "Please set it in your .env file."
            )
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=config.OPENAI_API_KEY,
        )
    
    elif config.MODE == "LOCAL":
        # Critical: Ollama does NOT need an API key
        return OllamaEmbeddings(
            model=config.OLLAMA_EMBED_MODEL,
            base_url=config.OLLAMA_BASE_URL,
        )
    
    else:
        raise ValueError(f"Invalid MODE: {config.MODE}. Must be 'CLOUD' or 'LOCAL'.")


def get_mode_display() -> str:
    """
    Returns a human-readable display string for the current mode.
    """
    if config.MODE == "CLOUD":
        return "🌐 Cloud Mode (OpenAI GPT-4o)"
    else:
        return f"💻 Local Mode (Ollama {config.OLLAMA_CHAT_MODEL})"


# Convenience exports
__all__ = ["config", "get_llm", "get_embeddings", "get_mode_display"]