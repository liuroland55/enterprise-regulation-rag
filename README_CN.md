# 企业条例 RAG 助手

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)

[English](README.md) · 中文

用自然语言提问公司规章,拿到**有据可循、附来源**的答案,并按员工岗位个性化。系统在规章知识库上跑自我校正的 Self-RAG 闭环(LangGraph),配合本地模型可**完全离线**运行。

桌面端(Tauri + React)连接一个本地 FastAPI 侧车,侧车封装 Self-RAG 内核。云端用 OpenAI、本地用 Ollama,任你选。

## 功能

- **Self-RAG** —— 检索 → 生成 → 自评 → 改写,直到答案站得住脚。
- **职位感知** —— 每次提问都带上用户的岗位与任务做查询增强。
- **云端或本地** —— OpenAI GPT-4o 或本机 Ollama,界面内可切换。
- **账户与角色** —— JWT 鉴权,员工自助注册,管理员管理用户。
- **知识库** —— 上传、重建索引,并自动同步 `data/` 目录。
- **历史与审计** —— 按用户隔离的私有历史,外加按账号分组的管理员审计。
- **默认隐私** —— 后端只监听本机;本地模式数据不出机器。

## 快速开始

需要 Python 3.10+、Node 18+,以及一个 OpenAI Key 或本地 [Ollama](https://ollama.com)。

```bash
# Windows
start_desktop.bat
# Linux / macOS
./start_desktop.sh
```

脚本会准备好 env 文件(自动生成随机 JWT 密钥与管理员密码,均打印到控制台),启动侧车与网页界面,并打开:

- 网页界面 —— http://localhost:5173
- API 文档 —— http://127.0.0.1:8756/docs

<details>
<summary>手动启动</summary>

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env               # MODE / OPENAI_API_KEY 或 Ollama
copy .env.server.example .env.server
python -m src.server.main            # 127.0.0.1:8756

cd desktop && npm install && npm run dev   # http://localhost:5173
```
</details>

## 工作原理

```
React / Tauri  →  FastAPI 侧车 (127.0.0.1:8756)  →  RAG2API (Self-RAG · LangGraph)  →  OpenAI | Ollama + ChromaDB
```

侧车在零改动复用的 RAG 内核之上,叠加了账户系统、职位感知查询增强与知识库管理。Tauri 外壳负责拉起并托管侧车;同一套前端也能在普通浏览器里运行。

## 配置

两份刻意分开的 env 文件:

- **`.env`** —— RAG 内核:`MODE`(`CLOUD` / `LOCAL`),以及 `OPENAI_API_KEY` 或 `OLLAMA_*` 设置。
- **`.env.server`** —— 侧车:`JWT_SECRET`、初始管理员、端口。首次运行自动生成。

切换模式会改写 `.env`,重启侧车后生效。云端与本地嵌入维度不同,因此各自保留独立向量库,首次使用时从 `data/` 重建。

## 许可证

MIT,见 [LICENSE](LICENSE)。
