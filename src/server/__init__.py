"""企业条例 RAG 桌面应用 —— FastAPI 侧车服务包。

本包在不改动 RAG 核心（`src/api/rag_api.py`、`src/graph/*`、
`src/config/settings.py`、`src/ingestion/loader.py`）的前提下，
以增量方式提供：本地账号系统、JWT 双令牌鉴权、基于角色的访问控制（RBAC）、
职位感知的查询增强、按用户隔离的查询历史，以及知识库管理等能力。

注意：本文件仅为包初始化占位，后续任务将逐步填充各子模块的实现。
"""
