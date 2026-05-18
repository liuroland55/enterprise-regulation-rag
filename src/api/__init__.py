"""
RAG2 API Module

This module provides a simplified interface for integrating the RAG2 Self-RAG system
into other Python projects.

Main Components:
    - RAG2API: Main API class for interacting with the RAG2 system
    - ask_question: Quick function for single question answering

Usage:
    >>> from src.api.rag_api import RAG2API, ask_question
    >>> 
    >>> # Using the class (recommended for multiple questions)
    >>> api = RAG2API()
    >>> result = api.ask("What is Self-RAG?")
    >>> print(result['answer'])
    >>> 
    >>> # Using the quick function (for single question)
    >>> result = ask_question("What is LangGraph?")
    >>> print(result['answer'])
"""

from src.api.rag_api import RAG2API, ask_question

__all__ = ["RAG2API", "ask_question"]