"""
Streamlit GUI for RAG2 Self-RAG System

This is a modern graphical user interface that wraps the existing RAG2 logic.
It provides a chat interface, knowledge base management, and system configuration.

Requirements:
    pip install streamlit>=1.28.0 pypdf>=3.0.0

Usage:
    streamlit run app.py
"""

import streamlit as st
import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any
import io

# Import existing RAG2 modules
from src.config.settings import config, get_llm, get_embeddings
from src.ingestion.loader import get_vector_store, split_documents
from src.graph.workflow import create_self_rag_workflow, initialize_state
from src.graph.nodes import vector_store
from src.utils.checks import check_local_mode_prerequisites, check_ollama_connection

# Page configuration
st.set_page_config(
    page_title="RAG2 - Self-RAG System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================

def init_session_state():
    """Initialize all session state variables."""
    
    # Configuration
    if "mode" not in st.session_state:
        st.session_state.mode = "LOCAL"
    
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    
    if "local_model" not in st.session_state:
        st.session_state.local_model = "qwen3-vl:8b"
    
    if "embed_model" not in st.session_state:
        st.session_state.embed_model = "nomic-embed-text"
    
    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "current_question" not in st.session_state:
        st.session_state.current_question = ""
    
    # Vector store state
    if "vector_store" not in st.session_state:
        st.session_state.vector_store = None
    
    if "documents_count" not in st.session_state:
        st.session_state.documents_count = 0
    
    if "chunks_count" not in st.session_state:
        st.session_state.chunks_count = 0
    
    # Bad cases (marked as no answer/hallucination)
    if "bad_cases" not in st.session_state:
        st.session_state.bad_cases = []


# ============================================================================
# CONFIGURATION SYNC
# ============================================================================

def sync_config():
    """
    Sync Streamlit session_state configuration with RAG system.
    
    This ensures that when users change settings in the sidebar,
    the RAG system uses the updated configuration.
    """
    # Import here to avoid circular imports
    import os
    from dotenv import load_dotenv
    
    # Load .env file
    load_dotenv()
    
    # Update environment variables based on session_state
    if st.session_state.mode == "CLOUD":
        os.environ["MODE"] = "CLOUD"
        if st.session_state.api_key:
            os.environ["OPENAI_API_KEY"] = st.session_state.api_key
    else:  # LOCAL mode
        os.environ["MODE"] = "LOCAL"
        os.environ["OLLAMA_CHAT_MODEL"] = st.session_state.local_model
        os.environ["OLLAMA_EMBED_MODEL"] = st.session_state.embed_model


# ============================================================================
# RAG ENGINE LOGIC
# ============================================================================

def initialize_rag_system():
    """
    Initialize the RAG system with current configuration.
    
    Syncs session_state configuration with the RAG system and initializes
    the vector store with the appropriate embedding model.
    """
    if st.session_state.vector_store is None:
        with st.spinner("🔄 Initializing RAG system..."):
            try:
                # Sync configuration from session_state
                sync_config()
                
                # Run health checks for Local mode
                if st.session_state.mode == "LOCAL":
                    try:
                        check_local_mode_prerequisites()
                    except Exception as e:
                        st.error(f"❌ Local mode prerequisites not met: {str(e)}")
                        st.stop()
                
                # Get embeddings based on current mode
                embeddings = get_embeddings()
                
                # Get or create vector store
                vs = get_vector_store()
                
                # Store in session state and update nodes module
                st.session_state.vector_store = vs
                from src.graph import nodes
                nodes.vector_store = vs
                
                # Get actual counts from vector store
                try:
                    collection_data = vs.get()
                    st.session_state.documents_count = len(collection_data["metadatas"]) if collection_data["metadatas"] else 0
                    st.session_state.chunks_count = len(collection_data["documents"]) if collection_data["documents"] else 0
                except Exception:
                    # If vector store is empty or error occurs
                    st.session_state.documents_count = 0
                    st.session_state.chunks_count = 0
                
                st.success(f"✅ RAG system initialized ({st.session_state.mode} mode)")
                st.info(f"📊 Loaded {st.session_state.documents_count} documents ({st.session_state.chunks_count} chunks)")
                
            except Exception as e:
                st.error(f"❌ Failed to initialize RAG system: {str(e)}")
                import traceback
                st.error(traceback.format_exc())
                st.stop()


def process_question_stream(question: str):
    """
    Process a user question through Self-RAG workflow with detailed streaming output.
    
    Displays each iteration step (retrieve, generate, rewrite) in real-time
    and returns the final answer with complete iteration history.
    """
    if not st.session_state.vector_store:
        st.error("❌ Vector store not initialized. Please check your configuration.")
        return None, []
    
    try:
        # Sync configuration before processing
        sync_config()
        
        # Initialize state with config.MAX_ITERATIONS
        max_iterations = getattr(config, 'MAX_ITERATIONS', 3)
        state = initialize_state(question, max_iterations=max_iterations)
        
        # Create workflow
        workflow = create_self_rag_workflow(max_iterations=max_iterations)
        
        # Create a container for iteration display
        iteration_container = st.container()
        
        # Stream workflow execution with detailed output
        with st.status(f"🔄 Processing question with Self-RAG...", expanded=True) as status:
            iteration_info = []
            
            for step in workflow.stream(state):
                for node_name, node_state in step.items():
                    
                    if node_name == "retrieve":
                        iteration = node_state["iterations"]
                        context = node_state["context"]
                        context_count = len(context)
                        
                        # Display retrieval step
                        status.write(f"\n{'─' * 60}")
                        st.write(f"📖 **Iteration {iteration}/{max_iterations}: Retrieval**")
                        st.info(f"🔍 Retrieved {context_count} documents")
                        
                        # Show retrieved documents
                        for i, ctx in enumerate(context):
                            with st.expander(f"📄 Document {i+1}", expanded=False):
                                source = ctx.metadata.get("source", "Unknown")
                                st.caption(f"Source: {source}")
                                preview = ctx.page_content[:200] + "..." if len(ctx.page_content) > 200 else ctx.page_content
                                st.write(preview)
                        
                        iteration_info.append({
                            "type": "retrieve",
                            "iteration": iteration,
                            "context_count": context_count,
                            "context": context
                        })
                    
                    elif node_name == "generate_and_grade":
                        iteration = node_state["iterations"]
                        answer = node_state["answer"]
                        grade = node_state["grade"]
                        reason = node_state["reason"]
                        
                        # Display generation step
                        st.write(f"\n💭 **Iteration {iteration}/{max_iterations}: Generation & Grading**")
                        
                        # Show grade with color
                        if grade == "YES":
                            st.success(f"✅ Grade: {grade}")
                        else:
                            st.warning(f"❌ Grade: {grade}")
                        
                        st.caption(f"Reason: {reason}")
                        
                        # Show answer preview
                        answer_preview = answer[:200] + "..." if len(answer) > 200 else answer
                        with st.expander("📝 Answer Preview", expanded=False):
                            st.write(answer_preview)
                        
                        iteration_info.append({
                            "type": "generate",
                            "iteration": iteration,
                            "answer": answer,
                            "grade": grade,
                            "reason": reason
                        })
                    
                    elif node_name == "rewrite_query":
                        iteration = node_state["iterations"]
                        old_query = question
                        new_query = node_state["current_query"]
                        
                        # Display rewrite step
                        st.write(f"\n✏️ **Iteration {iteration}: Query Rewrite**")
                        st.info(f"🔄 Query rewritten to improve retrieval")
                        
                        with st.expander("📋 Query Comparison", expanded=False):
                            st.write(f"**Old Query:** {old_query}")
                            st.write(f"**New Query:** {new_query}")
                        
                        iteration_info.append({
                            "type": "rewrite",
                            "iteration": iteration,
                            "old_query": old_query,
                            "new_query": new_query
                        })
                    
                    # Update final state
                    final_state = node_state
            
            # Summary
            st.write(f"\n{'━' * 60}")
            st.success(f"✨ Completed {final_state['iterations']} iteration(s)")
            if final_state['grade'] == "YES":
                st.info("🎯 Answer quality is satisfactory")
            else:
                st.warning(f"⚠️ Reached max iterations ({max_iterations})")
        
        return final_state, iteration_info
    
    except Exception as e:
        st.error(f"❌ Error processing question: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None, []


def process_uploaded_file(uploaded_file):
    """
    Process an uploaded file and add to vector store.
    
    Uses current mode's embedding model and configured chunking parameters.
    """
    try:
        # Sync configuration before processing
        sync_config()
        
        # Read file content based on type
        if uploaded_file.type == "application/pdf":
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            text = ""
            page_count = len(reader.pages)
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n\n[Page {i+1}]\n{page_text}"
            st.write(f"📄 Extracted {page_count} pages from PDF")
        else:
            # Text or Markdown file
            text = uploaded_file.read().decode("utf-8")
            line_count = len(text.splitlines())
            st.write(f"📄 Loaded {line_count} lines from text file")
        
        # Validate content
        if not text or len(text.strip()) < 50:
            st.error(f"❌ File '{uploaded_file.name}' appears to be empty or too short")
            return
        
        # Create document object with basic metadata
        from langchain_core.documents import Document
        doc = Document(
            page_content=text,
            metadata={
                "source": uploaded_file.name,
                "filetype": os.path.splitext(uploaded_file.name)[1].lower(),
                "size": len(text)
            }
        )
        
        # Split into chunks using configured parameters
        # Get chunk size and overlap from config if available, otherwise use defaults
        chunk_size = getattr(config, 'CHUNK_SIZE', 500) if hasattr(config, 'CHUNK_SIZE') else 500
        chunk_overlap = getattr(config, 'CHUNK_OVERLAP', 50) if hasattr(config, 'CHUNK_OVERLAP') else 50
        
        chunks = split_documents([doc], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Add to vector store with current embedding model
        with st.spinner(f"🔄 Creating embeddings for {len(chunks)} chunks..."):
            # Get embeddings based on current mode
            embeddings = get_embeddings()
            
            # Add to existing vector store or create new one
            from langchain_chroma import Chroma
            
            if st.session_state.vector_store is not None:
                # Add to existing collection
                st.session_state.vector_store.add_documents(chunks)
                vs = st.session_state.vector_store
            else:
                # Create new collection
                vs = Chroma.from_documents(
                    documents=chunks,
                    embedding=embeddings,
                    persist_directory="./chroma_db"
                )
            
            # Update vector store reference
            st.session_state.vector_store = vs
            from src.graph import nodes
            nodes.vector_store = vs
            
            # Update counts
            st.session_state.documents_count += 1
            st.session_state.chunks_count += len(chunks)
        
        st.success(f"✅ Successfully processed '{uploaded_file.name}'")
        st.info(f"📊 Created {len(chunks)} chunks (size: {chunk_size}, overlap: {chunk_overlap})")
        
        # Show sample chunk
        if chunks:
            with st.expander("🔍 Sample Chunk Preview", expanded=False):
                st.write(f"**First chunk ({len(chunks[0].page_content)} chars):**")
                st.write(chunks[0].page_content[:500] + "..." if len(chunks[0].page_content) > 500 else chunks[0].page_content)
        
    except Exception as e:
        st.error(f"❌ Failed to process file '{uploaded_file.name}': {str(e)}")
        import traceback
        st.error(traceback.format_exc())


# ===============================v=============================================
# UI RENDERING FUNCTIONS
# ============================================================================

def render_sidebar():
    """Render the sidebar configuration panel."""
    
    st.sidebar.title("⚙️ Configuration")
    st.sidebar.divider()
    
    # Mode selection
    st.sidebar.subheader("🌐 API Mode")
    mode = st.sidebar.radio(
        "Select Mode",
        ["LOCAL", "CLOUD"],
        label_visibility="collapsed",
        help="LOCAL: Use Ollama (offline, free) | CLOUD: Use OpenAI (faster, better)"
    )
    st.session_state.mode = mode
    
    st.sidebar.divider()
    
    # Mode-specific configuration
    if mode == "LOCAL":
        st.sidebar.subheader("💻 Local Mode Settings")
        
        local_model = st.sidebar.text_input(
            "Chat Model",
            value=st.session_state.local_model,
            help="Ollama model name (e.g., llama3:8b, mistral:7b)"
        )
        st.session_state.local_model = local_model
        
        embed_model = st.sidebar.text_input(
            "Embedding Model",
            value=st.session_state.embed_model,
            help="Ollama embedding model (e.g., nomic-embed-text)"
        )
        st.session_state.embed_model = embed_model
        
        # Test connection button
        if st.sidebar.button("🔍 Test Ollama Connection"):
            with st.sidebar:
                try:
                    check_ollama_connection()
                    st.success("✅ Ollama is running and accessible")
                except Exception as e:
                    st.error(f"❌ {str(e)}")
    
    else:  # CLOUD mode
        st.sidebar.subheader("☁️ Cloud Mode Settings")
        
        api_key = st.sidebar.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.api_key,
            help="Your OpenAI API key"
        )
        st.session_state.api_key = api_key
        
        if not api_key:
            st.sidebar.warning("⚠️ API key is required for Cloud mode")
    
    st.sidebar.divider()
    
    # System controls
    st.sidebar.subheader("🔧 System Controls")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("🗑️ Clear Vector DB", use_container_width=True):
            if st.sidebar.checkbox("Confirm deletion", key="confirm_delete"):
                try:
                    if os.path.exists("./chroma_db"):
                        shutil.rmtree("./chroma_db")
                        st.session_state.vector_store = None
                        st.session_state.documents_count = 0
                        st.session_state.chunks_count = 0
                        st.success("✅ Vector database cleared")
                    else:
                        st.info("📭 Vector database not found")
                except Exception as e:
                    st.error(f"❌ Failed to clear vector DB: {str(e)}")
    
    with col2:
        if st.button("📥 Export Chat", use_container_width=True):
            export_chat_history()
    
    st.sidebar.divider()
    
    # Statistics
    st.sidebar.subheader("📊 Statistics")
    st.sidebar.metric("Documents", st.session_state.documents_count)
    st.sidebar.metric("Chunks", st.session_state.chunks_count)
    
    # Bad cases counter
    if st.session_state.bad_cases:
        st.sidebar.metric("Bad Cases", len(st.session_state.bad_cases), delta_color="inverse")


def render_main_chat():
    """Render the main chat interface."""
    
    st.title("💬 RAG2 Self-RAG Chat")
    st.divider()
    
    # Chat messages
    chat_container = st.container()
    
    with chat_container:
        # Display message history
        for idx, message in enumerate(st.session_state.messages):
            with st.chat_message(name=message["role"], avatar=message.get("avatar", None)):
                st.write(message["content"])
                
                # Show sources for assistant messages
                if message["role"] == "assistant" and "sources" in message:
                    with st.expander("📚 Source Documents", expanded=False):
                        for source in message["sources"]:
                            st.info(f"**{source.get('source', 'Unknown')}**\n\n{source.get('content', '')[:200]}...")
                
                # Show no answer button for assistant messages
                if message["role"] == "assistant":
                    if st.button(
                        "🚩 Mark as No Answer/Hallucination",
                        key=f"mark_bad_{idx}",
                        type="secondary"
                    ):
                        mark_as_bad_case(message["content"])
                        st.rerun()
    
    # New message input
    st.divider()
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_input = st.chat_input("Ask a question about your documents...", key="user_input")
    
    with col2:
        send_button = st.button("Send", type="primary", use_container_width=True)
    
    # Process new message
    if (user_input or send_button) and user_input:
        if not user_input.strip():
            st.warning("⚠️ Please enter a question")
            return
        
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "avatar": "👤"
        })
        
        # Process question
        final_state, iteration_info = process_question_stream(user_input)
        
        if final_state:
            # Add assistant message with iteration details
            assistant_content = final_state["answer"]
            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "avatar": "🤖",
                "iterations": final_state["iterations"],
                "grade": final_state["grade"],
                "reason": final_state.get("reason", ""),
                "sources": [
                    {"source": f"Document {i+1}", "content": ctx.page_content[:500]}
                    for i, ctx in enumerate(final_state.get("context", [])[:3])
                ],
                "iteration_info": iteration_info
            }
            
            st.session_state.messages.append(assistant_message)
        
        # Clear input and rerun
        st.session_state.current_question = ""
        st.rerun()
    
    # New conversation button
    if st.button("🔄 New Conversation", type="secondary"):
        st.session_state.messages = []
        st.rerun()


def render_knowledge_base():
    """Render the knowledge base management section."""
    
    st.subheader("📚 Knowledge Base Management")
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("💡 Upload documents to expand your knowledge base")
        st.write("Supported formats: **PDF, TXT, MD**")
    
    with col2:
        st.info("📊 Current statistics")
        st.metric("Documents", st.session_state.documents_count)
        st.metric("Chunks", st.session_state.chunks_count)
    
    st.divider()
    
    # File upload
    uploaded_files = st.file_uploader(
        "Upload Documents",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        help="Upload PDF, text, or markdown files to add to your knowledge base"
    )
    
    # Process uploaded files
    if uploaded_files:
        for uploaded_file in uploaded_files:
            with st.status(f"🔄 Processing '{uploaded_file.name}'..."):
                process_uploaded_file(uploaded_file)
        
        st.success(f"✅ All files processed successfully!")
        st.rerun()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def mark_as_bad_case(answer: str):
    """Mark an answer as a bad case (no answer or hallucination)."""
    bad_case = {
        "timestamp": datetime.now().isoformat(),
        "question": "",
        "answer": answer,
        "reason": "Marked as no answer/hallucination by user"
    }
    
    # Find the corresponding question
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "assistant" and msg["content"] == answer:
            if i > 0 and st.session_state.messages[i-1]["role"] == "user":
                bad_case["question"] = st.session_state.messages[i-1]["content"]
            break
    
    st.session_state.bad_cases.append(bad_case)
    
    # Save to file
    try:
        with open("bad_cases.json", "w", encoding="utf-8") as f:
            json.dump(st.session_state.bad_cases, f, indent=2, ensure_ascii=False)
        st.success("✅ Bad case recorded to 'bad_cases.json'")
    except Exception as e:
        st.error(f"❌ Failed to save bad case: {str(e)}")


def export_chat_history():
    """Export chat history to a file."""
    if not st.session_state.messages:
        st.warning("⚠️ No chat history to export")
        return
    
    try:
        # Create JSON export
        export_data = {
            "export_time": datetime.now().isoformat(),
            "messages": st.session_state.messages,
            "bad_cases": st.session_state.bad_cases,
            "statistics": {
                "total_messages": len(st.session_state.messages),
                "total_bad_cases": len(st.session_state.bad_cases),
                "documents_count": st.session_state.documents_count,
                "chunks_count": st.session_state.chunks_count
            }
        }
        
        # Write to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_export_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        st.success(f"✅ Chat history exported to '{filename}'")
        
        # Offer download
        st.download_button(
            label="📥 Download Export",
            data=json.dumps(export_data, indent=2, ensure_ascii=False),
            file_name=filename,
            mime="application/json"
        )
        
    except Exception as e:
        st.error(f"❌ Failed to export chat history: {str(e)}")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    
    # Initialize session state
    init_session_state()
    
    # Render sidebar
    render_sidebar()
    
    # Create tabs
    tab1, tab2 = st.tabs(["💬 Chat", "📚 Knowledge Base"])
    
    with tab1:
        # Initialize RAG system if needed
        if st.session_state.vector_store is None:
            initialize_rag_system()
        
        # Render main chat interface
        render_main_chat()
    
    with tab2:
        render_knowledge_base()
    
    # Footer
    st.divider()
    st.caption("💡 RAG2 - Self-RAG System | Powered by LangChain & Streamlit")


if __name__ == "__main__":
    main()