"""
Document Loading and Vectorization Module

This module handles loading documents, splitting them into chunks,
generating embeddings, and storing them in ChromaDB.
"""

from typing import List
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from src.config.settings import get_embeddings, config
import os

# Supported file extensions for document loading
SUPPORTED_EXTENSIONS = ['.txt', '.md', '.rst', '.log']


# Sample technical documentation about Self-RAG and LangGraph
SAMPLE_DOCUMENTS = """
# Self-RAG: Self-Reflective Retrieval-Augmented Generation

## Overview
Self-RAG is an advanced framework that enhances traditional Retrieval-Augmented Generation (RAG) by incorporating self-reflection capabilities. Unlike standard RAG systems that perform a single retrieval followed by generation, Self-RAG implements an iterative process where the system evaluates its own outputs and decides whether additional retrieval is needed.

## Key Components

### 1. Retrieval Module
The retrieval module is responsible for fetching relevant documents from a vector database. It uses embeddings to find semantically similar documents based on the user's query. Modern retrieval systems often use dense vector representations with cosine similarity or other distance metrics.

### 2. Generation Module
The generation module uses a large language model to synthesize answers based on retrieved context. Unlike standard RAG, Self-RAG's generation module is designed to work with iterative refinement, allowing for multiple rounds of generation as new information is retrieved.

### 3. Reflection Module (Self-Grading)
This is the core innovation of Self-RAG. After generating an answer, the system evaluates:
- Completeness: Does the answer fully address the question?
- Relevance: Is the answer supported by the retrieved context?
- Confidence: How confident is the system about the quality of the answer?

Based on these evaluations, the system grades its output as either "GOOD" or "NEEDS IMPROVEMENT".

### 4. Query Rewriting
When the reflection module identifies that the answer needs improvement, the query rewriting component modifies the original query to:
- Focus on missing information
- Use different keywords or terminology
- Break down complex questions into simpler components
- Target aspects that were not adequately covered in previous retrievals

## Multi-Hop Reasoning
Self-RAG supports multi-hop reasoning, which is essential for answering complex questions that require connecting information from multiple documents. For example, a question like "What are the key differences between Self-RAG and standard RAG?" might require:
1. First retrieval about Self-RAG features
2. Second retrieval about standard RAG features
3. Third retrieval about comparison methodologies

The system automatically performs these hops by iteratively refining queries based on what information is missing from the current context.

## Advantages of Self-RAG

1. **Improved Accuracy**: By iteratively refining answers, Self-RAG achieves higher accuracy on complex questions.
2. **Better Context Utilization**: The system makes better use of available information by identifying gaps and filling them.
3. **Reduced Hallucinatiosys**: Self-grading helps prevent the model from generating unsupported claims.
4. **Adaptive Retrieval**: The system retrieves exactly what it needs rather than using fixed retrieval parameters.

## Implementation Considerations

When implementing Self-RAG, consider:
- Maximum iteration limits to prevent infinite loops
- Thresholds for self-grading to balance quality and efficiency
- Latency trade-offs between single-pass and multi-pass approaches
- Computational resource requirements for repeated LLM calls

# LangGraph: Building Stateful AI Applications

## Introduction
LangGraph is a library for building stateful, multi-actor applications with LLMs, built on top of LangChain. It's particularly well-suited for creating agentic workflows where AI applications need to maintain state across multiple steps and decisions.

## Core Concepts

### 1. Graph Structure
LangGraph models applications as directed graphs where nodes represent processing steps and edges represent the flow of control. This makes it easy to visualize and reason about complex workflows.

### 2. State Management
Unlike simple chains, LangGraph maintains a shared state that's passed between nodes. This state can accumulate information, track iteration counts, and carry context across the entire workflow.

### 3. Conditional Routing
LangGraph supports conditional edges that can route the workflow based on the current state. This is crucial for implementing self-reflection loops where the next action depends on the quality of previous outputs.

### 4. Persistence
LangGraph supports checkpointing, which allows workflows to be paused, resumed, and inspected at any point. This is essential for debugging and for applications that need to maintain state across sessions.

## Key Features

### StateGraph
The StateGraph class is the primary building block for creating workflows. It's parameterized by a state type (TypedDict) that defines what information flows through the graph.

### Node Functions
Nodes are Python functions that receive the current state and return updates to that state. This functional approach makes nodes easy to test and reason about.

### Edges
Edges define how control flows between nodes:
- **Regular edges**: Always go from node A to node B
- **Conditional edges**: Route based on state or function output
- **Entry points**: Where the workflow begins
- **END**: Special node representing workflow completion

## Self-RAG Implementation with LangGraph

LangGraph is particularly well-suited for implementing Self-RAG because:

1. **Natural State Representation**: The iterative refinement process naturally maps to state updates
2. **Conditional Loops**: The decision to continue or stop based on grading is a perfect use case for conditional edges
3. **Visualization**: The retrieval → generate → grade → rewrite cycle is easy to understand when represented as a graph
4. **Debugging**: Checkpoints allow inspection of the state at each iteration, making it easy to diagnose issues

## Workflow Pattern
A typical Self-RAG workflow in LangGraph follows this pattern:
1. **Retrieve Node**: Fetch documents based on current query
2. **Generate Node**: Create answer using LLM
3. **Grade Node**: Evaluate answer quality
4. **Conditional Edge**: Route based on grade (continue if NO, stop if YES)
5. **Rewrite Node**: Improve query if continuing
6. **Loop Back**: Return to retrieve with new query

## Best Practices

1. **Keep Nodes Focused**: Each node should do one thing well
2. **Use Clear State Transitions**: Document how each node modifies the state
3. **Implement Timeouts**: Prevent infinite loops in iterative workflows
4. **Add Logging**: Log state changes for debugging
5. **Test Independently**: Test nodes in isolation before integrating

## Performance Considerations

- **Node Latency**: Minimize work in each node to keep overall latency low
- **State Size**: Keep state payloads reasonable to avoid memory issues
- **Parallelism**: Where possible, use parallel edges for concurrent operations
- **Caching**: Cache expensive operations like embeddings

## Future Directions

LangGraph continues to evolve with features like:
- Distributed graph execution for scalability
- Built-in monitoring and observability
- Integration with more orchestration frameworks
- Enhanced debugging tools and visualizations
"""


def load_documents_from_directory(directory: str = "./data") -> List[Document]:
    """
    Load all supported text documents from a directory.
    
    This function scans the specified directory for files with supported
    extensions (.txt, .md, .rst, .log) and loads them as Document
    objects with metadata including source filename and path.
    
    Args:
        directory: Path to the directory containing documents
        
    Returns:
        List of Document objects with metadata
    """
    documents = []
    
    if not os.path.exists(directory):
        print(f"⚠️  Directory '{directory}' not found")
        return documents
    
    if not os.path.isdir(directory):
        print(f"⚠️  '{directory}' is not a directory")
        return documents
    
    print(f"📁 Scanning directory: {directory}")
    
    # Get all files in directory
    try:
        files = os.listdir(directory)
    except PermissionError:
        print(f"⚠️  Permission denied accessing '{directory}'")
        return documents
    
    # Filter and load supported files
    loaded_count = 0
    skipped_count = 0
    
    for filename in files:
        filepath = os.path.join(directory, filename)
        
        # Skip if not a file
        if not os.path.isfile(filepath):
            continue
        
        # Check file extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            skipped_count += 1
            continue
        
        # Try to load the file
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create document with metadata
            doc = Document(
                page_content=content,
                metadata={
                    "source": filename,
                    "filepath": filepath,
                    "filetype": ext,
                    "size": len(content)
                }
            )
            documents.append(doc)
            loaded_count += 1
            print(f"   ✅ Loaded: {filename} ({len(content)} chars)")
            
        except UnicodeDecodeError:
            print(f"   ⚠️  Skipped (encoding error): {filename}")
            skipped_count += 1
        except Exception as e:
            print(f"   ⚠️  Skipped ({str(e)}): {filename}")
            skipped_count += 1
    
    print(f"📊 Loading summary: {loaded_count} files loaded, {skipped_count} files skipped")
    return documents


def load_sample_data() -> List[Document]:
    """
    Load documents for the RAG system.
    
    This function implements a smart loading strategy:
    1. First, tries to load from './data/' directory if it exists
    2. Falls back to built-in sample documents if directory is empty or missing
    
    Returns:
        List of Document objects
    """
    data_directory = "./data"
    
    # Try to load from data directory first
    if os.path.exists(data_directory) and os.path.isdir(data_directory):
        print("\n" + "="*60)
        print("📚 Loading documents from directory...")
        print("="*60 + "\n")
        
        documents = load_documents_from_directory(data_directory)
        
        if documents:
            print(f"\n✅ Successfully loaded {len(documents)} documents from '{data_directory}'")
            return documents
        else:
            print(f"\n⚠️  No supported documents found in '{data_directory}'")
            print(f"   Falling back to sample documents...\n")
    
    # Fall back to sample documents
    print("="*60)
    print("📚 Loading built-in sample documents...")
    print("="*60 + "\n")
    
    doc = Document(
        page_content=SAMPLE_DOCUMENTS.strip(),
        metadata={
            "source": "sample_documents",
            "filepath": "built-in",
            "filetype": ".txt",
            "size": len(SAMPLE_DOCUMENTS)
        }
    )
    
    print("✅ Loaded sample documentation (Self-RAG & LangGraph)\n")
    return [doc]


def split_documents(documents: List[Document], chunk_size: int = 500, chunk_overlap: int = 50) -> List[Document]:
    """
    Split documents into smaller chunks for better retrieval.
    
    Args:
        documents: List of documents to split
        chunk_size: Size of each chunk in characters
        chunk_overlap: Overlap between consecutive chunks
        
    Returns:
        List of chunked documents
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    chunks = text_splitter.split_documents(documents)
    print(f"✅ Split documents into {len(chunks)} chunks")
    return chunks


def create_vector_store(persist_directory: str = None) -> Chroma:
    """
    Create or load the ChromaDB vector store with sample data.
    
    This function:
    1. Checks if vector store already exists
    2. If not, creates new store with sample documents
    3. Generates embeddings using the configured backend
    4. Persists the store for future use
    
    Args:
        persist_directory: Directory to store the vector database
        
    Returns:
        Configured ChromaDB vector store
    """
    persist_directory = persist_directory or config.CHROMA_PERSIST_DIR
    
    # Create directory if it doesn't exist
    os.makedirs(persist_directory, exist_ok=True)
    
    # Check if vector store already exists
    collection_path = os.path.join(persist_directory, "chroma.sqlite3")
    
    if os.path.exists(collection_path):
        print(f"📂 Loading existing vector store from {persist_directory}")
        vector_store = Chroma(
            persist_directory=persist_directory,
            embedding_function=get_embeddings()
        )
        print(f"✅ Vector store loaded successfully")
    else:
        print(f"📄 Creating new vector store with sample data...")
        
        # Load and split documents
        documents = load_sample_data()
        chunks = split_documents(documents)
        
        # Create vector store with embeddings
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=get_embeddings(),
            persist_directory=persist_directory
        )
        
        print(f"✅ Vector store created and saved to {persist_directory}")
        print(f"   - Total chunks: {len(chunks)}")
        print(f"   - Embedding model: {'OpenAI' if config.MODE == 'CLOUD' else 'Ollama'}")
    
    return vector_store


def get_vector_store(persist_directory: str = None) -> Chroma:
    """
    Get or create the vector store.
    
    This is a convenience function that handles the common case of
    getting the vector store without worrying about whether it exists.
    
    Args:
        persist_directory: Directory for vector store persistence
        
    Returns:
        Configured ChromaDB vector store
    """
    return create_vector_store(persist_directory)


# Export functions
__all__ = [
    "load_sample_data",
    "split_documents",
    "create_vector_store",
    "get_vector_store"
]