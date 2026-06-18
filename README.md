# Enterprise Regulation RAG

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)

English · [中文](README_CN.md)

Ask questions about your company's regulations and get grounded, source-backed answers — tailored to each employee's role. It runs a self-correcting Self-RAG loop (LangGraph) over a regulation knowledge base, and works fully offline with local models.

A desktop app (Tauri + React) talks to a local FastAPI sidecar that wraps the Self-RAG core. Use OpenAI in the cloud or Ollama on-device — your call.

## Features

- **Self-RAG** — retrieve → generate → self-grade → rewrite, until the answer holds up.
- **Role-aware answers** — each query is augmented with the user's position and tasks.
- **Cloud or local** — OpenAI GPT-4o or on-device Ollama, switchable from the UI.
- **Accounts & roles** — JWT auth, employee self-registration, admin-managed users.
- **Knowledge base** — upload, reindex, and auto-sync the `data/` folder.
- **History & audit** — private per user, plus an admin audit grouped by account.
- **Private by default** — the backend listens on localhost only; local mode never leaves your machine.

## Quick start

You'll need Python 3.10+, Node 18+, and either an OpenAI key or a local [Ollama](https://ollama.com).

```bash
# Windows
start_desktop.bat
# Linux / macOS
./start_desktop.sh
```

That sets up the env files (generating a random JWT secret and an admin password, both printed to the console), starts the sidecar and the web UI, and opens:

- Web UI — http://localhost:5173
- API docs — http://127.0.0.1:8756/docs

<details>
<summary>Manual start</summary>

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env               # MODE / OPENAI_API_KEY or Ollama settings
copy .env.server.example .env.server
python -m src.server.main            # 127.0.0.1:8756

cd desktop && npm install && npm run dev   # http://localhost:5173
```
</details>

## How it works

```
React / Tauri  →  FastAPI sidecar (127.0.0.1:8756)  →  RAG2API (Self-RAG · LangGraph)  →  OpenAI | Ollama + ChromaDB
```

The sidecar adds the account system, role/position-aware query augmentation, and knowledge-base management on top of the RAG core, which it reuses unchanged. The Tauri shell launches and supervises the sidecar; the same frontend also runs in a plain browser.

## Configuration

Two env files, kept separate on purpose:

- **`.env`** — the RAG core: `MODE` (`CLOUD` / `LOCAL`), plus `OPENAI_API_KEY` or the `OLLAMA_*` settings.
- **`.env.server`** — the sidecar: `JWT_SECRET`, the bootstrap admin, ports. Auto-generated on first run.

Switching mode rewrites `.env` and applies after a sidecar restart. Cloud and local use different embedding sizes, so each keeps its own vector store and rebuilds from `data/` on first use.

## License

MIT — see [LICENSE](LICENSE).
