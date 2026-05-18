"""
LangGraph Workflow Assembly

This module assembles the Self-RAG workflow by connecting all nodes
into a directed graph with conditional edges and iteration loops.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import SelfRAGState
from src.graph.nodes import (
    retrieve_node,
    generate_and_grade_node,
    rewrite_query_node,
    should_continue_node
)


def create_self_rag_workflow(max_iterations: int = 3) -> StateGraph:
    """
    Create and compile the Self-RAG workflow graph.
    
    This function constructs the workflow:
    1. Start → Retrieve
    2. Retrieve → Generate & Grade
    3. Generate & Grade → Should Continue
    4. Should Continue → [YES/Max Iterations] → END
    5. Should Continue → [NO] → Rewrite Query
    6. Rewrite Query → Retrieve (loop back)
    
    Args:
        max_iterations: Maximum number of retrieval iterations
        
    Returns:
        Compiled LangGraph workflow ready for invocation
    """
    
    # Initialize the workflow graph
    workflow = StateGraph(SelfRAGState)
    
    # Add all nodes to the workflow
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate_and_grade", generate_and_grade_node)
    workflow.add_node("rewrite_query", rewrite_query_node)
    
    # Define the workflow edges
    
    # Start → Retrieve
    workflow.set_entry_point("retrieve")
    
    # Retrieve → Generate & Grade
    workflow.add_edge("retrieve", "generate_and_grade")
    
    # Generate & Grade → Should Continue (conditional)
    workflow.add_conditional_edges(
        "generate_and_grade",
        should_continue_node,
        {
            "end": END,           # Stop if quality is good or max iterations reached
            "continue": "rewrite_query"  # Continue if quality needs improvement
        }
    )
    
    # Rewrite Query → Retrieve (loop back)
    workflow.add_edge("rewrite_query", "retrieve")
    
    # Compile the workflow
    app = workflow.compile()
    
    return app


def initialize_state(question: str, max_iterations: int = 3) -> SelfRAGState:
    """
    Initialize the state for a new question.
    
    Args:
        question: User's question
        max_iterations: Maximum allowed iterations
        
    Returns:
        Initial state dictionary
    """
    return {
        "question": question,
        "current_query": question,
        "context": [],
        "answer": "",
        "grade": "NO",
        "reason": "",
        "iterations": 0,
        "max_iterations": max_iterations,
        "messages": []
    }


# Export functions
__all__ = [
    "create_self_rag_workflow",
    "initialize_state"
]