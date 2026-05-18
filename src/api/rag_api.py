"""
RAG2 API Module - Simplified Interface for Integration

This module provides a clean, simple interface for integrating the RAG2 Self-RAG
system into other Python projects. It abstracts away the complexity of the
underlying LangGraph workflow and provides easy-to-use methods.

Features:
    - Singleton pattern for efficient resource usage
    - Simple ask() method for single questions
    - batch_ask() for processing multiple questions
    - Health check and statistics methods
    - Comprehensive error handling
"""

from typing import Dict, List, Optional, Union
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RAG2API:
    """
    RAG2 Self-RAG System API Wrapper
    
    This class provides a simplified interface to the RAG2 Self-RAG system.
    It implements the singleton pattern to ensure efficient resource usage.
    
    Usage:
        >>> api = RAG2API()
        >>> result = api.ask("What is Self-RAG?")
        >>> print(result['answer'])
    
    Attributes:
        max_iterations (int): Maximum number of retrieval iterations
        vector_store: ChromaDB vector store instance
        workflow: Compiled LangGraph workflow
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """
        Implement singleton pattern to ensure only one instance exists.
        
        This prevents multiple initializations of the vector store and workflow,
        which would be wasteful and could cause conflicts.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_iterations: int = 3, auto_init: bool = True):
        """
        Initialize the RAG2 API.
        
        Args:
            max_iterations: Maximum number of retrieval iterations (default: 3)
            auto_init: Whether to automatically initialize the system (default: True)
            
        Note:
            If auto_init is False, you must call initialize() manually before
            using other methods.
        """
        # Skip if already initialized (singleton pattern)
        if self._initialized:
            return
        
        self.max_iterations = max_iterations
        self.vector_store = None
        self.workflow = None
        self._config = None
        
        if auto_init:
            self.initialize()
        
        self._initialized = True
    
    def initialize(self):
        """
        Initialize the RAG2 system components.
        
        This method performs the following:
        1. Loads configuration from .env file
        2. Initializes the ChromaDB vector store
        3. Sets up the global vector store reference
        4. Creates and compiles the LangGraph workflow
        
        Raises:
            Exception: If initialization fails
        """
        try:
            logger.info("Initializing RAG2 system...")
            
            # Lazy imports to avoid loading modules at module import time
            from src.ingestion.loader import get_vector_store
            from src.graph.workflow import create_self_rag_workflow
            from src.config.settings import config
            
            # Store configuration
            self._config = config
            
            # Initialize vector store
            logger.info("Loading vector store...")
            self.vector_store = get_vector_store()
            
            # Set global vector store reference for nodes module
            import src.graph.nodes as nodes_module
            nodes_module.vector_store = self.vector_store
            
            # Create and compile workflow
            logger.info("Compiling Self-RAG workflow...")
            self.workflow = create_self_rag_workflow(max_iterations=self.max_iterations)
            
            mode_display = "LOCAL" if config.MODE == "LOCAL" else "CLOUD"
            logger.info(f"✅ RAG2 system initialized successfully (Mode: {mode_display})")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize RAG2 system: {str(e)}")
            raise RuntimeError(f"RAG2 initialization failed: {str(e)}") from e
    
    def ask(
        self,
        question: str,
        return_context: bool = False,
        return_metadata: bool = False
    ) -> Dict:
        """
        Ask a question and get an answer from the RAG2 system.
        
        This is the main method for interacting with the system. It processes
        a single question through the Self-RAG workflow and returns the answer
        along with metadata.
        
        Args:
            question: The user's question (required)
            return_context: Whether to include retrieved document content (default: False)
            return_metadata: Whether to include full document metadata (default: False)
            
        Returns:
            A dictionary containing:
                - question (str): The original question
                - answer (str): The generated answer
                - grade (str): Self-grading result ("YES" or "NO")
                - reason (str): Explanation for the grade
                - iterations (int): Number of retrieval iterations performed
                - success (bool): Whether the operation was successful
                - context (list, optional): Retrieved documents if return_context=True
                - error (str, optional): Error message if success=False
            
        Example:
            >>> api = RAG2API()
            >>> result = api.ask("What is Self-RAG?")
            >>> if result['success']:
            ...     print(f"Answer: {result['answer']}")
            ...     print(f"Grade: {result['grade']}")
        """
        # Ensure system is initialized
        if not self.workflow:
            self.initialize()
        
        try:
            # Lazy imports
            from src.graph.workflow import initialize_state
            from src.config.settings import config
            
            logger.info(f"Processing question: {question[:50]}...")
            
            # Initialize state for this question
            state = initialize_state(
                question, 
                max_iterations=config.MAX_ITERATIONS
            )
            
            # Execute workflow
            final_state = None
            for step in self.workflow.stream(state):
                for node_name, node_state in step.items():
                    final_state = node_state
            
            # Build basic result
            result = {
                "question": final_state["question"],
                "answer": final_state["answer"],
                "grade": final_state["grade"],
                "reason": final_state["reason"],
                "iterations": final_state["iterations"],
                "max_iterations": final_state["max_iterations"],
                "success": True
            }
            
            # Optionally include retrieved documents
            if return_context or return_metadata:
                context_data = []
                for doc in final_state["context"]:
                    ctx_item = {
                        "content": doc.page_content,
                        "source": doc.metadata.get("source", "Unknown")
                    }
                    if return_metadata:
                        ctx_item["metadata"] = doc.metadata
                    context_data.append(ctx_item)
                result["context"] = context_data
            
            logger.info(f"✅ Question processed successfully (Grade: {result['grade']}, Iterations: {result['iterations']})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error processing question: {str(e)}")
            return {
                "question": question,
                "answer": f"Failed to process question: {str(e)}",
                "grade": "NO",
                "reason": "System error",
                "iterations": 0,
                "success": False,
                "error": str(e)
            }
    
    def batch_ask(
        self,
        questions: List[str],
        return_context: bool = False
    ) -> List[Dict]:
        """
        Process multiple questions in batch.
        
        This method processes a list of questions sequentially and returns
        a list of results in the same order.
        
        Args:
            questions: List of questions to process
            return_context: Whether to include retrieved document content (default: False)
            
        Returns:
            A list of result dictionaries, one for each question.
            
        Example:
            >>> api = RAG2API()
            >>> questions = ["What is Self-RAG?", "What is LangGraph?"]
            >>> results = api.batch_ask(questions)
            >>> for q, r in zip(questions, results):
            ...     print(f"Q: {q}")
            ...     print(f"A: {r['answer']}")
        """
        logger.info(f"Processing batch of {len(questions)} questions...")
        results = []
        
        for i, question in enumerate(questions, 1):
            logger.info(f"Processing question {i}/{len(questions)}")
            result = self.ask(question, return_context=return_context)
            results.append(result)
        
        logger.info(f"✅ Batch processing completed ({len(results)} results)")
        return results
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the vector database.
        
        Returns:
            A dictionary containing:
                - documents (int): Number of documents in the database
                - chunks (int): Number of text chunks
                - success (bool): Whether the operation was successful
                - error (str, optional): Error message if success=False
        """
        try:
            if not self.vector_store:
                self.initialize()
            
            logger.info("Fetching vector database statistics...")
            collection_data = self.vector_store.get()
            
            result = {
                "documents": len(collection_data["metadatas"]) if collection_data["metadatas"] else 0,
                "chunks": len(collection_data["documents"]) if collection_data["documents"] else 0,
                "success": True
            }
            
            logger.info(f"✅ Statistics: {result['documents']} documents, {result['chunks']} chunks")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error fetching statistics: {str(e)}")
            return {
                "documents": 0,
                "chunks": 0,
                "success": False,
                "error": str(e)
            }
    
    def health_check(self) -> Dict:
        """
        Check the health status of the RAG2 system.
        
        Returns:
            A dictionary containing:
                - status (str): "healthy" or "unhealthy"
                - mode (str): "LOCAL" or "CLOUD"
                - initialized (bool): Whether the system is initialized
                - workflow_ready (bool): Whether the workflow is ready
                - vector_store_ready (bool): Whether the vector store is ready
                - success (bool): Whether the check was successful
                - error (str, optional): Error message if success=False
        """
        try:
            from src.config.settings import config
            
            result = {
                "status": "healthy",
                "mode": config.MODE,
                "initialized": self._initialized,
                "workflow_ready": self.workflow is not None,
                "vector_store_ready": self.vector_store is not None,
                "success": True
            }
            
            if not all([result['initialized'], result['workflow_ready'], result['vector_store_ready']]):
                result['status'] = "unhealthy"
            
            logger.info(f"Health check: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "success": False
            }
    
    def reset(self):
        """
        Reset the API instance.
        
        This method clears the current instance and allows re-initialization.
        Useful for testing or when configuration changes.
        """
        logger.info("Resetting RAG2 API instance...")
        
        self._instance = None
        self._initialized = False
        self.vector_store = None
        self.workflow = None
        self._config = None
        
        logger.info("✅ API instance reset complete")


def ask_question(question: str, **kwargs) -> Dict:
    """
    Convenience function for quick single-question answering.
    
    This function creates a temporary API instance, asks the question,
    and returns the result. It's useful for one-off questions.
    
    Args:
        question: The user's question
        **kwargs: Additional arguments to pass to ask() method
        
    Returns:
        Result dictionary (same as RAG2API.ask())
        
    Example:
        >>> from src.api.rag_api import ask_question
        >>> result = ask_question("What is Self-RAG?")
        >>> print(result['answer'])
    """
    api = RAG2API(auto_init=True)
    return api.ask(question, **kwargs)


# Export public interface
__all__ = ["RAG2API", "ask_question"]