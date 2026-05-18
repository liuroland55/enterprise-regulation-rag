"""
System Health Checks Module

This module provides utility functions to verify the health and availability
of external services (Ollama, OpenAI) and required models before running the RAG system.
"""

import requests
import time
from typing import Optional, List
from src.config.settings import config


class OllamaConnectionError(Exception):
    """Raised when Ollama service is not accessible."""
    pass


class ModelNotFoundError(Exception):
    """Raised when a required model is not found in Ollama."""
    pass


def check_ollama_connection(
    base_url: str = None, 
    timeout: int = 5, 
    max_retries: int = 3
) -> bool:
    """
    Check if Ollama service is running and accessible.
    
    This function pings the Ollama API to verify the service is responsive.
    It handles connection timeouts and provides helpful error messages.
    
    Args:
        base_url: Ollama base URL (defaults to config.OLLAMA_BASE_URL)
        timeout: Connection timeout in seconds
        max_retries: Number of retry attempts
        
    Returns:
        bool: True if Ollama is accessible
        
    Raises:
        OllamaConnectionError: If Ollama service cannot be reached
    """
    base_url = base_url or config.OLLAMA_BASE_URL
    url = f"{base_url}/api/tags"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            
            if response.status_code == 200:
                return True
            else:
                raise OllamaConnectionError(
                    f"Ollama service returned status {response.status_code}. "
                    f"Expected 200 OK."
                )
                
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {base_url}. "
                f"Please ensure Ollama is running.\n"
                f"Error: {str(e)}"
            )
            
        except requests.exceptions.Timeout as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise OllamaConnectionError(
                f"Connection to Ollama timed out after {timeout} seconds. "
                f"The service may be starting up or unresponsive."
            )
            
        except requests.exceptions.RequestException as e:
            raise OllamaConnectionError(
                f"Unexpected error connecting to Ollama: {str(e)}"
            )
    
    return False


def check_model_exists(
    model_name: str, 
    base_url: str = None
) -> bool:
    """
    Check if a specific model is available in Ollama.
    
    This function queries the Ollama API to list all available models
    and checks if the requested model exists.
    
    Args:
        model_name: Name of the model to check (e.g., "llama3:8b")
        base_url: Ollama base URL (defaults to config.OLLAMA_BASE_URL)
        
    Returns:
        bool: True if model exists
        
    Raises:
        OllamaConnectionError: If Ollama service is not accessible
        ModelNotFoundError: If the model is not found
    """
    base_url = base_url or config.OLLAMA_BASE_URL
    
    # First check connection
    check_ollama_connection(base_url)
    
    # Fetch list of available models
    url = f"{base_url}/api/tags"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        available_models = []
        
        if "models" in data:
            for model_info in data["models"]:
                # Model name can be in "name" field
                if "name" in model_info:
                    available_models.append(model_info["name"])
        
        # Check if requested model exists
        # Handle both exact match and partial match (e.g., "llama3" matches "llama3:8b")
        model_exists = any(
            model_name in available_model or available_model.startswith(model_name)
            for available_model in available_models
        )
        
        if not model_exists:
            raise ModelNotFoundError(
                f"Model '{model_name}' not found in Ollama.\n"
                f"Available models: {available_models}\n\n"
                f"To download this model, run:\n"
                f"  ollama pull {model_name}"
            )
        
        return True
        
    except requests.exceptions.RequestException as e:
        raise OllamaConnectionError(
            f"Error fetching model list from Ollama: {str(e)}"
        )


def check_local_mode_prerequisites() -> List[str]:
    """
    Perform comprehensive checks for LOCAL mode prerequisites.
    
    This function runs all necessary checks to ensure the system is ready
    to run in LOCAL mode, including:
    1. Ollama service connectivity
    2. Chat model availability
    3. Embedding model availability
    
    Returns:
        List[str]: List of success/check messages
        
    Raises:
        OllamaConnectionError: If Ollama service is not accessible
        ModelNotFoundError: If required models are not found
    """
    messages = []
    
    print("\n🔍 Checking LOCAL mode prerequisites...")
    
    # Check 1: Ollama Connection
    try:
        check_ollama_connection()
        messages.append("✅ Ollama service is running and accessible")
    except OllamaConnectionError as e:
        messages.append("❌ Ollama service check failed")
        raise
    
    # Check 2: Chat Model
    try:
        check_model_exists(config.OLLAMA_CHAT_MODEL)
        messages.append(f"✅ Chat model '{config.OLLAMA_CHAT_MODEL}' is available")
    except ModelNotFoundError as e:
        messages.append(f"❌ Chat model '{config.OLLAMA_CHAT_MODEL}' not found")
        raise
    
    # Check 3: Embedding Model
    try:
        check_model_exists(config.OLLAMA_EMBED_MODEL)
        messages.append(f"✅ Embedding model '{config.OLLAMA_EMBED_MODEL}' is available")
    except ModelNotFoundError as e:
        messages.append(f"❌ Embedding model '{config.OLLAMA_EMBED_MODEL}' not found")
        raise
    
    print("\n✨ All checks passed!")
    for msg in messages:
        print(f"  {msg}")
    print()
    
    return messages


def get_ollama_models(base_url: str = None) -> List[str]:
    """
    Get list of all available models in Ollama.
    
    Args:
        base_url: Ollama base URL (defaults to config.OLLAMA_BASE_URL)
        
    Returns:
        List[str]: List of model names
    """
    base_url = base_url or config.OLLAMA_BASE_URL
    
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        
        data = response.json()
        models = []
        
        if "models" in data:
            models = [model["name"] for model in data["models"]]
        
        return models
        
    except requests.exceptions.RequestException as e:
        raise OllamaConnectionError(
            f"Error fetching model list: {str(e)}"
        )


# Convenience exports
__all__ = [
    "check_ollama_connection",
    "check_model_exists",
    "check_local_mode_prerequisites",
    "get_ollama_models",
    "OllamaConnectionError",
    "ModelNotFoundError"
]