"""
State Schema for Self-RAG LangGraph Workflow

This module defines the state structure used throughout the Self-RAG workflow.
The state is passed between nodes and contains all information needed for
multi-hop retrieval and generation.
"""

from typing import List, Literal, TypedDict, Annotated
from langgraph.graph import add_messages


class SelfRAGState(TypedDict):
    """
    State for the Self-RAG workflow.
    
    This state tracks the entire multi-hop retrieval process:
    - Original question and current query (may be rewritten)
    - Retrieved context documents
    - Generated answer
    - Self-grading results (YES/NO)
    - Iteration tracking to prevent infinite loops
    """
    
    # User's original question (immutable)
    question: str
    
    # Current query for retrieval (may be rewritten)
    current_query: str
    
    # Retrieved documents from vector database
    context: List[str]
    
    # Generated answer
    answer: str
    
    # Self-grading result: YES (quality good) or NO (needs improvement)
    grade: Literal["YES", "NO"]
    
    # Reasoning for the grade
    reason: str
    
    # Current iteration count
    iterations: int
    
    # Maximum allowed iterations (prevents infinite loops)
    max_iterations: int
    
    # Messages for LangGraph (optional, for future extensions)
    messages: Annotated[list, add_messages]