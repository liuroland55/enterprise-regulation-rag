# RAG2 - Self-RAG System with Cloud/Local Dual Mode

A production-grade Self-RAG (Retrieval-Augmented Generation) system with seamless cloud/local mode switching, built with LangGraph and LangChain.

## 🎯 Key Features

- **Dual Mode Support**: Instantly switch between Cloud (OpenAI GPT-4o) and Local (Ollama) backends
- **Self-RAG Logic**: Automatic retrieval → generation → grading → query rewriting loop
- **Multi-hop Reasoning**: Handles complex questions requiring multiple retrieval iterations
- **JSON Resilience**: Robust parsing for local models with imperfect JSON output
- **Health Checks**: Automatic validation of Ollama service and model availability
- **Zero Business Logic Changes**: Switch modes without modifying any code

## 📁 Project Structure

```
RAG2/
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Dual-mode configuration factory
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py             # LangGraph state schema
│   │   ├── nodes.py             # RAG nodes (retrieve, generate, grade, rewrite)
│   │   └── workflow.py          # LangGraph workflow assembly
│   ├── ingestion/
│   │   ├── __init__.py
│   │   └── loader.py            # Document loading and vectorization
│   └── utils/
│       ├── __init__.py
│       ├── json_parser.py       # Local model JSON cleaning utilities
│       └── checks.py            # System health checks
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the System

Copy the example environment file:

```bash
cp .env.example .env
```

### 3. Choose Your Mode

#### 🌐 Cloud Mode (Default - Fast Development)

Edit `.env`:

```env
MODE=CLOUD
OPENAI_API_KEY=sk-your-actual-api-key-here
```

**Pros**: Fast, powerful reasoning, minimal setup
**Cons**: Requires OpenAI API key, data goes to cloud

---

#### 💻 Local Mode (Privacy & Cost-Free)

**Prerequisites**:
1. Install [Ollama](https://ollama.ai/)
2. Start Ollama service (usually starts automatically after installation)

Edit `.env`:

```env
MODE=LOCAL
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

**Download Required Models**:

```bash
# Chat model (for generation)
ollama pull llama3:8b

# Embedding model (for vectorization)
ollama pull nomic-embed-text
```

**Pros**: Free, offline, private, no API key needed
**Cons**: Slower, requires local hardware, lower reasoning quality

### 4. Run the System

**Quick Start with Launcher Scripts:**

**Windows:**
```bash
# Double-click start.bat or run:
start.bat
```

**Linux/Mac:**
```bash
# Make script executable (first time only)
chmod +x start.sh

# Run the script
./start.sh
```

**Manual Start:**
```bash
# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Run the system
python main.py
```

The system will automatically:
1. Detect your mode (Cloud or Local)
2. Run health checks (Local mode only)
3. Initialize the vector database
4. Start an interactive CLI for queries

---

## 🚀 Launcher Scripts

The project includes convenient launcher scripts for easy startup:

### start.bat (Windows)
- Automatically activates virtual environment
- Checks for required files (.env, venv)
- Creates .env from template if missing
- Provides clear error messages
- Pauses on exit for easy viewing

### start.sh (Linux/Mac)
- Same features as Windows version
- Bash-based with proper exit codes
- Auto-creates .env if missing
- Interactive prompts when needed

### First-Time Setup

1. **Create virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   
   # Linux/Mac
   python3 -m venv venv
   ```

2. **Install dependencies:**
   ```bash
   # Windows
   venv\Scripts\activate
   pip install -r requirements.txt
   
   # Linux/Mac
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   # Copy template and edit
   cp .env.example .env
   # Edit .env with your chosen mode
   ```

4. **Run with launcher:**
   ```bash
   # Windows
   start.bat
   
   # Linux/Mac
   ./start.sh
   ```

## ⚙️ Configuration Details

### Environment Variables

| Variable | Mode | Description | Default |
|----------|------|-------------|---------|
| `MODE` | Both | Operating mode: `CLOUD` or `LOCAL` | `CLOUD` |
| `OPENAI_API_KEY` | Cloud | OpenAI API key | (required) |
| `OLLAMA_BASE_URL` | Local | Ollama service URL | `http://localhost:11434` |
| `OLLAMA_CHAT_MODEL` | Local | Model for text generation | `llama3:8b` |
| `OLLAMA_EMBED_MODEL` | Local | Model for embeddings | `nomic-embed-text` |
| `CHROMA_PERSIST_DIR` | Both | Vector database path | `./chroma_db` |
| `MAX_ITERATIONS` | Both | Max retrieval loops | `3` |
| `RETRIEVAL_K` | Both | Documents per retrieval | `4` |

### Recommended Model Combinations

#### For Cloud Mode
- Chat: `gpt-4o` (automatically selected)
- Embeddings: `text-embedding-3-small` (automatically selected)

#### For Local Mode
**High Quality** (8GB+ RAM):
- Chat: `llama3:8b` or `mistral:7b`
- Embeddings: `nomic-embed-text`

**Balanced** (4-8GB RAM):
- Chat: `llama3:8b` (quantized) or `phi3:mini`
- Embeddings: `nomic-embed-text`

**Lightweight** (<4GB RAM):
- Chat: `tinyllama:1.1b` or `gemma2:2b`
- Embeddings: `all-minilm:33m`

## 🔍 System Architecture

### Self-RAG Workflow

```
Start → Retrieve → Generate & Grade → [Check Grade]
                                    ↓
                        [YES: Quality Good] → End
                                    ↓
                        [NO: Quality Low] → Rewrite Query → Retrieve
                                                   ↑
                                                   |
                                    [Loop until max_iterations]
```

### Dual-Mode Architecture

```
Business Logic (nodes.py, workflow.py)
         ↓
   settings.get_llm() / get_embeddings()
         ↓
    ┌────┴────┐
    ↓         ↓
Cloud      Local
(OpenAI)   (Ollama)
```

**Key Design Principle**: Business logic never imports model classes directly. Always use the factory functions from `settings.py`.

## 🛠️ Troubleshooting

### Local Mode Issues

**Ollama not running**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama (Windows)
ollama serve

# Start Ollama (Mac/Linux)
ollama serve
```

**Model not found**:
```bash
# List available models
ollama list

# Pull required model
ollama pull llama3:8b
ollama pull nomic-embed-text
```

**JSON parsing errors**: The system includes automatic JSON cleaning for local models. Check logs for details.

### Cloud Mode Issues

**API key invalid**: Verify your OpenAI API key is valid and has credits.

**Rate limiting**: OpenAI has rate limits. Consider upgrading your plan or switching to local mode.

## 📚 How It Works

### 1. Document Ingestion
- Load documents from files
- Split into chunks
- Generate embeddings (cloud or local)
- Store in ChromaDB vector database

### 2. Query Processing
- User asks a question
- System retrieves relevant documents
- LLM generates answer based on context
- System grades answer quality
- If low quality, rewrites query and repeats

### 3. Self-Grading
The system evaluates:
- Answer completeness
- Information accuracy
- Need for additional retrieval

## 🔒 Privacy & Security

- **Cloud Mode**: Data sent to OpenAI servers. Review OpenAI's privacy policy.
- **Local Mode**: All processing stays on your machine. No data leaves your system.

## 📝 TODO (Next Steps)

- [x] Implement Step 3: Self-RAG Core Logic (LangGraph)
- [x] Implement Step 4: Data Ingestion & Main Entry Point
- [ ] Add web search capability (DuckDuckGo)
- [ ] Implement caching for repeated queries
- [ ] Add evaluation metrics (RAGAS)
- [ ] Create web UI (Streamlit/Gradio)

---

## 💻 Usage Examples

### Example 1: Basic Question (Single Iteration)

```
📝 Question: What is Self-RAG?

🔄 Iteration 1/3
──────────────────────────────────────────────────────────────────────
🔍 Retrieval
   Retrieved 4 documents

   [Document 1] # Self-RAG: Self-Reflective Retrieval-Augmented Generation
   ## Overview
   Self-RAG is an advanced framework that enhances traditional...
   [Document 2] The retrieval module is responsible for fetching...

💭 Generation & Grading
   Grade: ✅ YES
   Reason: The answer is complete and directly addresses the question

   Answer Preview: Self-RAG is an advanced framework that enhances
   traditional Retrieval-Augmented Generation (RAG) by incorporating
   self-reflection capabilities...

✨ Final Answer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Self-RAG is an advanced framework that enhances traditional
Retrieval-Augmented Generation (RAG) by incorporating self-reflection
capabilities. Unlike standard RAG systems that perform a single
retrieval followed by generation, Self-RAG implements an iterative
process where the system evaluates its own outputs and decides whether
additional retrieval is needed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Metadata:
   Iterations: 1
   Final Grade: ✅ YES
   Reason: Answer quality is good
```

### Example 2: Multi-Hop Question (Multiple Iterations)

```
📝 Question: What are the advantages of using LangGraph for Self-RAG?

🔄 Iteration 1/3
──────────────────────────────────────────────────────────────────────
🔍 Retrieval
   Retrieved 4 documents

💭 Generation & Grading
   Grade: ❌ NO
   Reason: The answer discusses LangGraph features but doesn't specifically
   mention advantages for Self-RAG implementation

   Answer Preview: LangGraph is a library for building stateful applications...

✏️ Query Rewriting
   Old Query: What are the advantages of using LangGraph for Self-RAG?
   New Query: LangGraph advantages for implementing Self-RAG systems

🔄 Iteration 2/3
──────────────────────────────────────────────────────────────────────
🔍 Retrieval
   Retrieved 4 documents

💭 Generation & Grading
   Grade: ✅ YES
   Reason: The answer now covers the specific advantages of LangGraph
   for Self-RAG implementation

   Answer Preview: LangGraph is particularly well-suited for implementing
   Self-RAG because it provides natural state representation, conditional
   loops, and visualization capabilities...

✨ Final Answer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LangGraph is particularly well-suited for implementing Self-RAG because:

1. Natural State Representation: The iterative refinement process naturally
   maps to state updates in LangGraph's stateful workflow model.

2. Conditional Loops: The decision to continue or stop based on grading
   is a perfect use case for LangGraph's conditional edges.

3. Visualization: The retrieval → generate → grade → rewrite cycle is
   easy to understand when represented as a graph.

4. Debugging: Checkpoints allow inspection of the state at each iteration,
   making it easy to diagnose issues in the self-reflection loop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Metadata:
   Iterations: 2
   Final Grade: ✅ YES
   Reason: Answer quality is good
```

---

## 🔧 Advanced Configuration

### Customizing Iterations

Edit `.env`:
```env
# Allow more iterations for complex questions
MAX_ITERATIONS=5

# Retrieve more documents per query
RETRIEVAL_K=8
```

### Adding Custom Documents

The system now supports loading documents from a `./data/` folder! No code changes required.

#### Easy Method (Recommended)

1. **Create a data folder:**
   ```bash
   mkdir data
   ```

2. **Add your documents:**
   ```
   data/
   ├── doc1.txt
   ├── doc2.md
   └── technical.rst
   ```

   **Supported formats:** `.txt`, `.md`, `.rst`, `.log`

3. **Delete old vector database:**
   ```bash
   # Windows
   rmdir /s /q chroma_db
   
   # Linux/Mac
   rm -rf chroma_db
   ```

4. **Run the system:**
   ```bash
   python main.py
   ```

   The system will automatically detect and load your documents!

#### Advanced Method (Code Modification)

If you need custom loading logic, modify `src/ingestion/loader.py`:

```python
def load_sample_data() -> List[Document]:
    # Load from custom sources
    documents = []
    
    # Load from API
    # documents.append(Document(page_content=fetch_from_api()))
    
    # Load from database
    # for record in db.query():
    #     documents.append(Document(page_content=record['content']))
    
    return documents
```

Then delete the existing vector database to force regeneration.

---

## 📁 Document Loading Features

### Smart Loading Strategy

The system automatically chooses the best source:

```
1. Check ./data/ folder
   ↓ exists and has files?
   YES → Load from folder
   NO  → Use built-in sample documents
```

### Document Metadata

Each loaded document includes metadata:

```python
{
    "source": "filename.txt",
    "filepath": "/path/to/file.txt",
    "filetype": ".txt",
    "size": 12345
}
```

### Error Handling

- ✅ Skips unsupported file types
- ⚠️  Warns about encoding errors
- ✅ Handles permission issues gracefully
- ✅ Provides detailed loading summary

### Loading Example Output

```
📚 Loading documents from directory...

📁 Scanning directory: ./data
   ✅ Loaded: doc1.txt (5234 chars)
   ✅ Loaded: doc2.md (3421 chars)
   ⚠️  Skipped (encoding error): doc3.txt
� Loading summary: 2 files loaded, 1 files skipped

✅ Successfully loaded 2 documents from './data'
```

---

## 🎨 CLI Features

### Verbose Mode (Default)

The CLI shows detailed information about each step:
- � Iteration progress
- 🔍 Retrieved documents (showing first 2)
- � Generated answer and grading
- ✏️ Query rewriting when needed
- ✨ Final answer with metadata

### Color Legend

- � **Green**: Success, positive grade
- 🔴 **Red**: Negative grade, needs improvement
- 🔵 **Blue**: Information, retrieval, generation
- 🟡 **Yellow**: Warnings, reasons, metadata
- 🟣 **Purple**: Iterations, query rewriting
- ⚪ **Gray**: Separators, additional info

---

## � Performance Tips

### Cloud Mode
- Use `gpt-4o` for best reasoning
- Increase `MAX_ITERATIONS` for complex queries
- Consider batching multiple questions

### Local Mode
- Use quantized models for faster inference (e.g., `llama3:8b-q4_K_M`)
- Lower `MAX_ITERATIONS` to reduce latency
- Ensure sufficient RAM (8GB+ recommended for 8B models)
- Consider using smaller models like `phi3:mini` for faster responses

### Vector Database
- ChromaDB persists automatically in `./chroma_db`
- First run will be slower (embedding generation)
- Subsequent runs will be instant (cache hit)

## 🤝 Contributing

This is a demonstration project. Feel free to fork and adapt for your use case.

## � License

MIT License

## 🙏 Acknowledgments

- LangChain team for excellent abstractions
- Ollama team for democratizing local LLMs
- LangGraph team for the workflow orchestration framework