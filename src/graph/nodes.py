"""
Self-RAG Nodes Implementation

This module contains all the node functions that make up the Self-RAG workflow.
Each node performs a specific task in the retrieval-augmented generation cycle.

Nodes:
- retrieve_node: Fetches relevant documents from the vector database
- generate_and_grade_node: Generates an answer and self-grades the quality
- rewrite_query_node: Rewrites the query when the answer quality is low
- should_continue_node: Determines whether to continue or stop the iteration
"""

from typing import Dict, Any
from langchain_chroma import Chroma
from langchain_core.documents import Document
from src.graph.state import SelfRAGState
from src.config.settings import get_llm, config
from src.utils.json_parser import parse_json_safely, validate_json_structure


# Global vector store reference (will be set by main.py)
vector_store: Chroma = None


def retrieve_node(state: SelfRAGState) -> SelfRAGState:
    """
    Retrieve relevant documents from vector database based on current query.
    
    Args:
        state: Current state containing the query to search for
        
    Returns:
        Updated state with retrieved Document objects and incremented iteration count
    """
    current_query = state["current_query"]
    
    # Increment iteration count at the start of each retrieval cycle
    iterations = state["iterations"] + 1
    
    # Perform similarity search
    results = vector_store.similarity_search(
        query=current_query,
        k=config.RETRIEVAL_K
    )
    
    # Return full Document objects (with metadata) instead of just content
    context = results
    
    return {
        **state,
        "context": context,
        "iterations": iterations
    }


def generate_and_grade_node(state: SelfRAGState) -> SelfRAGState:
    """
    Generate an answer based on the retrieved context and self-grade its quality.
    Optimized for:
    1. Strict adherence to context (Preventing hallucination on unrelated topics like 'radish')
    2. Robust JSON parsing for local models
    3. Clear grading criteria
    """
    query = state["current_query"]
    context = state["context"]
    question = state["question"]
    
    # Format context clearly with separators
    if not context:
        context_text = "No relevant documents were retrieved."
    else:
        # context is now a list of Document objects, not strings
        context_text = "\n\n---\n".join([f"[Document {i+1}]\n{doc.page_content}" for i, doc in enumerate(context)])
    
    # --- OPTIMIZED PROMPT START ---
    prompt = f"""You are a rigorous RAG (Retrieval-Augmented Generation) assistant. Your goal is to answer questions using ONLY the provided context.

### Context Data:
{context_text}

### User Question:
{question}

### Instructions (Follow Strictly):
1. **Evidence Check**: Before answering, check if the Context Data contains information about the specific entities mentioned in the User Question (e.g., if asked about "radishes", check if any document mentions "radishes").
2. **Strict Adherence**: 
   - If the context contains the answer: Provide a comprehensive answer citing the documents.
   - If the context does NOT contain the answer (or talks about completely different topics): You MUST state clearly that the information is missing. **DO NOT** use your own external knowledge. **DO NOT** try to force an answer using unrelated documents.
3. **Grading**:
   - Grade "YES" only if: The answer is complete, accurate, and derived 100% from the provided context.
   - Grade "NO" if: The context is missing key info, the documents are irrelevant to the question, or you had to speculate.
4.language: using the language of the question
### Output Format:
You must output ONLY a valid JSON object. Do not use markdown code blocks (no ```json). Do not add any text before or after the JSON.

Schema:
{{
    "answer": "String: Your direct answer. If info is missing, explicitly say 'The provided context does not contain information about [Entity]'.",
    "grade": "String: 'YES' or 'NO'",
    "reason": "String: Briefly explain why. For 'NO', specify what is missing or why the retrieved docs are irrelevant."
}}

### Response:"""
    # --- OPTIMIZED PROMPT END ---

    llm = get_llm()
    
    # Try to generate and parse response with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt)
            response_text = response.content
            
            # Enhanced cleaning for local models
            # Remove markdown blocks if the model ignores the instruction
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = parse_json_safely(response_text)
            
            # Validate structure
            validate_json_structure(result, ["answer", "grade", "reason"])
            
            # Normalize grade
            grade = str(result.get("grade", "")).strip().upper()
            if grade not in ["YES", "NO"]:
                # If the model hallucinated a grade, default to NO for safety
                grade = "NO"
                if "reason" in result:
                    result["reason"] += " (Grade normalized to NO due to invalid format)"
                else:
                    result["reason"] = "Invalid grade format detected."
            
            # Safety Check: If context was empty but model said YES, force NO
            if not context and grade == "YES":
                grade = "NO"
                result["reason"] = "Auto-corrected: Cannot grade YES with empty context."
                result["answer"] = "No relevant documents were found to answer this question."

            return {
                **state,
                "answer": result["answer"],
                "grade": grade,
                "reason": result["reason"]
            }
            
        except Exception as e:
            if attempt == max_retries - 1:
                return {
                    **state,
                    "answer": "System Error: Unable to generate a valid response due to processing issues.",
                    "grade": "NO",
                    "reason": f"Parser failed after {max_retries} attempts: {str(e)}"
                }
            continue

def rewrite_query_node(state: SelfRAGState) -> SelfRAGState:
    """
    Rewrite query when answer quality is insufficient.
    
    This node:
    1. Analyzes the grading reason to understand what's missing
    2. Rewrites the query to focus on missing information
    3. Creates a new query that will likely retrieve better context
    
    Note: Iteration count is incremented in retrieve_node(), not here.
    
    Args:
        state: Current state with original question and grading reason
        
    Returns:
        Updated state with rewritten query
    """
    question = state["question"]
    reason = state["reason"]
    current_query = state["current_query"]
    # Note: iterations is already incremented in retrieve_node()
    
    # Prompt to rewrite the query based on what was missing
    prompt = f"""You are a query optimization specialist. Your task is to rewrite a query to retrieve better information.

Original Question: {question}
Current Query: {current_query}

Grading Reason (what was missing): {reason}

Task:
Analyze what information was missing from the context and rewrite the query to:
1. Be more specific about the missing information
2. Use different keywords or terminology
3. Break down complex questions into clearer components
4. Focus on the aspects that were not adequately covered

Guidelines:
- Keep the rewritten query concise (1-2 sentences)
- Make it specific enough to retrieve relevant documents
- Avoid changing the original intent of the question
- Use synonyms and related terms if the original didn't work

Output ONLY the rewritten query, no other text:"""

    llm = get_llm()
    
    try:
        response = llm.invoke(prompt)
        new_query = response.content.strip()
        
        # Clean up any markdown or extra formatting
        new_query = new_query.replace('"""', '').replace("'''", '')
        
        # Fallback if query is empty or too short
        if len(new_query) < 10:
            new_query = f"{question} more details about {reason.split()[-3:]}"
        
    except Exception as e:
        # Fallback: add "more information" to original query
        new_query = f"{question} detailed explanation"
    
    return {
        **state,
        "current_query": new_query
        # Note: iterations is already incremented in retrieve_node()
    }


def should_continue_node(state: SelfRAGState) -> str:
    """
    Decide whether to continue the iteration or stop.
    
    This node implements the stopping logic:
    - Stop if the answer quality is good (grade == "YES")
    - Stop if we've reached maximum iterations (prevents infinite loops)
    - Continue if the answer quality is low and we haven't reached the limit
    
    Args:
        state: Current state with grade and iteration count
        
    Returns:
        "continue" or "end" string indicating the next action
    """
    grade = state["grade"]
    iterations = state["iterations"]
    max_iterations = state["max_iterations"]
    
    # Stop if answer quality is good
    if grade == "YES":
        return "end"
    
    # Stop if we've reached maximum iterations
    if iterations >= max_iterations:
        return "end"
    
    # Continue iteration
    return "continue"


# Export functions
__all__ = [
    "vector_store",
    "retrieve_node",
    "generate_and_grade_node",
    "rewrite_query_node",
    "should_continue_node"
]