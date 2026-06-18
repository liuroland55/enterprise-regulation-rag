#!/usr/bin/env bash
# Enterprise Regulation RAG Desktop - Turnkey DEV Launcher for Linux/macOS
# 启动本地 FastAPI 侧车（后台）与桌面端 Vite 开发服务器（前台）。
# Ctrl+C 退出时会一并停止侧车。
set -euo pipefail

echo "========================================================"
echo "   Enterprise Regulation RAG Desktop - DEV Launcher"
echo "========================================================"
echo

# 解析仓库根目录（脚本所在目录），确保从任意位置调用都正确。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 强制 Python 以 UTF-8 输出 stdout，避免非 UTF-8 终端无法编码 RAG 核心 print() 中的
# emoji 而导致初始化抛 UnicodeEncodeError（Zero RAG Core Changes：不改核心代码）。
export PYTHONUTF8=1

# ---- [1/6] Check Python virtual environment ----
if [ ! -f "venv/bin/activate" ]; then
  echo "[ERROR] Virtual environment not found!"
  echo "Please create it first:"
  echo "  python3 -m venv venv"
  echo "  source venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi
echo "[1/6] Virtual environment found."
# shellcheck disable=SC1091
source venv/bin/activate

# ---- [2/6] Check Node.js / npm toolchain ----
if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] Node.js not found on PATH. Install Node.js (https://nodejs.org) and retry."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm not found on PATH. Reinstall Node.js and retry."
  exit 1
fi
echo "[2/6] Node.js / npm found."

# ---- [3/6] Ensure RAG core config (.env) exists ----
# .env        -> RAG 核心配置 (MODE / OPENAI_API_KEY / Ollama)
# .env.server -> 侧车配置 (JWT_SECRET / BOOTSTRAP_ADMIN_* 等)
# 二者必须分离：侧车键不能放入 .env，否则 RAG 核心校验 (extra="forbid") 会失败。
if [ ! -f ".env" ]; then
  echo
  echo "[WARNING] .env not found. Creating from .env.example..."
  cp .env.example .env
  echo "[IMPORTANT] Edit .env for the RAG core: MODE / OPENAI_API_KEY or Ollama settings."
fi
echo "[3/6] RAG core config (.env) ready."

# ---- [4/6] Ensure side-car config (.env.server) with auto-generated secrets ----
# 首次运行自动生成：高强度随机 JWT_SECRET + 满足密码策略的初始管理员密码，
# 不再停下来等待手动编辑（生成的管理员密码会打印在下方）。
if [ ! -f ".env.server" ]; then
  echo
  echo "[WARNING] .env.server not found. Generating with random JWT_SECRET and admin password..."
  JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
  ADMIN_PW="Admin-$(python -c 'import secrets;print(secrets.token_hex(6))')"
  # 基于模板替换 JWT_SECRET 与 BOOTSTRAP_ADMIN_PASSWORD 两行后写入 .env.server。
  sed -e "s#^JWT_SECRET=.*#JWT_SECRET=${JWT_SECRET}#" \
      -e "s#^BOOTSTRAP_ADMIN_PASSWORD=.*#BOOTSTRAP_ADMIN_PASSWORD=${ADMIN_PW}#" \
      .env.server.example > .env.server
  echo
  echo "  ============================================================"
  echo "    Initial admin credentials (save these now):"
  echo "      username: admin"
  echo "      password: ${ADMIN_PW}"
  echo "  ============================================================"
  echo "  (Stored in .env.server; change after first login.)"
  echo
else
  echo "[4/6] Side-car config (.env.server) already exists - keeping it."
fi
echo "[4/6] Side-car config (.env.server) ready."

# ---- [5/6] Install Python deps and start the FastAPI side-car (background) ----
echo
echo "[5/6] Installing Python dependencies (idempotent) and starting side-car..."
pip install -q -r requirements.txt
python -m src.server.main &
SIDECAR_PID=$!
echo "Side-car started (PID ${SIDECAR_PID}) on http://127.0.0.1:8756"

# 脚本退出时确保侧车一并停止。
cleanup() {
  echo
  echo "Stopping side-car (PID ${SIDECAR_PID})..."
  kill "${SIDECAR_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---- [6/6] Install front-end deps and start the Vite dev server (foreground) ----
echo
echo "[6/6] Preparing desktop front-end..."
cd desktop
if [ ! -d "node_modules" ]; then
  echo "Installing front-end dependencies (npm install)..."
  npm install
fi

echo
echo "The web UI will be available at: http://localhost:5173"
echo "NOTE: For the native Tauri window (requires Rust toolchain),"
echo "      run 'npm run tauri:dev' in the desktop/ directory instead."
echo "Press Ctrl+C to stop the dev server (the side-car will also be stopped)."
echo
npm run dev
