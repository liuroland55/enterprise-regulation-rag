# Enterprise Regulation RAG — Desktop（Tauri + React + TypeScript）

企业条例 RAG 系统的桌面客户端外壳。Rust 外壳（Tauri）负责原生窗口与本地
FastAPI side-car 子进程的生命周期；React + TypeScript 前端渲染界面。

> 本目录由任务 10.1 创建，仅完成 **工程脚手架 + side-car 生命周期** 接线。
> API client、会话管理与三栏布局页面分别在任务 10.2 / 10.3 / 11.x 实现。

## 目录结构

```
desktop/
├─ index.html               # Vite 入口 HTML
├─ package.json             # 前端依赖与脚本（React + Vite + @tauri-apps/*）
├─ tsconfig.json            # TypeScript 配置
├─ vite.config.ts           # Vite 配置（开发端口 5173，对应 tauri devUrl）
├─ src/                     # React 前端
│  ├─ main.tsx              # React 挂载入口
│  ├─ App.tsx               # 占位组件：轮询 side-car 健康检查
│  └─ vite-env.d.ts
└─ src-tauri/               # Rust 外壳
   ├─ Cargo.toml
   ├─ build.rs
   ├─ tauri.conf.json       # 窗口、构建命令、打包配置
   ├─ capabilities/
   │  └─ default.json       # Tauri v2 权限能力集
   ├─ icons/                # 打包所需图标（见 icons/README.md）
   └─ src/
      ├─ main.rs            # 入口，转发到 lib::run()
      ├─ lib.rs             # Tauri builder + setup（spawn）+ run（退出时终止）
      └─ sidecar.rs         # side-car 生命周期：解析 / 启动 / 监控 / 终止
```

## Side-car 生命周期

- **启动（spawn）**：Tauri `setup` 钩子在应用初始化时调用 `sidecar::spawn_sidecar`，
  拉起本地 FastAPI 服务子进程（Requirement 1.1）。子进程句柄保存在 Tauri 托管状态
  `SidecarProcess` 中。
- **绑定地址**：side-car 仅绑定回环地址 `127.0.0.1:8756`（Requirement 1.2）。外壳通过
  环境变量 `RAG2_SIDECAR_HOST` / `RAG2_SIDECAR_PORT` 将地址传给 Python 侧。
- **监控（monitor）**：启动后开启后台监控线程记录子进程状态（Requirement 1.3）。
- **终止（terminate）**：监听 `RunEvent::ExitRequested`，应用退出时 `kill` 子进程并
  `wait` 回收，避免残留孤儿进程。

### Side-car 命令解析顺序

`sidecar.rs::resolve_sidecar_command` 按以下优先级解析如何启动 side-car：

1. **`RAG2_SIDECAR_BIN`（环境变量）**：显式指定的可执行文件路径。生产环境优先方式，
   通常指向用 PyInstaller 等工具打包的独立二进制。
2. **同级目录打包二进制**：应用可执行文件同级目录下的 `rag2-sidecar`
   （Windows 为 `rag2-sidecar.exe`）。随安装包一起分发时使用。
3. **开发回退（Python 模块）**：以 `RAG2_PYTHON`（默认 Windows `python` /
   其它平台 `python3`）运行 `python -m src.server.main`，工作目录解析为仓库根目录
   （可用 `RAG2_REPO_ROOT` 覆盖，否则从 `src-tauri` 向上回溯两级定位）。

> `src/server/main.py`（side-car 的 uvicorn 启动入口）由后端任务 8.1 提供，
> 其需读取 `RAG2_SIDECAR_HOST` / `RAG2_SIDECAR_PORT` 并仅绑定回环地址。

## 开发与构建

需要的工具链：**Node.js + npm**、**Rust/Cargo**、**Tauri CLI**。

```bash
# 安装前端依赖
npm install

# 仅运行前端（浏览器调试）
npm run dev

# 运行桌面应用（自动构建前端 + 拉起 Rust 外壳 + side-car）
npm run tauri:dev

# 打包桌面安装包
npm run tauri:build
```

> 注意：本工程文件为手工创建。若当前环境缺少 Rust/Cargo 或 Tauri CLI，需先安装：
> Rust 见 <https://rustup.rs>，随后 `tauri dev` 会自动拉取 Rust 依赖。
> 前端依赖通过 `npm install` 安装。

## 快速开始 / Quick Start

一键启动脚本位于**仓库根目录**，会自动拉起本地 FastAPI side-car 与前端开发服务器。

### Windows

```bat
REM 在仓库根目录执行
start_desktop.bat
```

### Linux / macOS

```bash
# 在仓库根目录执行
chmod +x start_desktop.sh
./start_desktop.sh
```

脚本行为：

1. 检查并激活虚拟环境 `venv`（不存在时给出创建指引）。
2. 若 `.env` 缺失，则从 `.env.example` 复制，并提示设置 `JWT_SECRET` 与
   `BOOTSTRAP_ADMIN_PASSWORD`（首次登录所需）。
3. `pip install -r requirements.txt`（幂等）。
4. 启动 FastAPI side-car：`python -m src.server.main`（仅绑定 `127.0.0.1:8756`）。
5. 进入 `desktop/`，必要时 `npm install`，随后 `npm run dev` 启动 Vite 开发服务器
   （默认 <http://localhost:5173>）。

> 原生窗口：安装 Rust 工具链后，可在 `desktop/` 下改用 `npm run tauri:dev`
> 构建并打开原生 Tauri 窗口（脚本默认走 Vite Web 调试以保持简单）。

### 登录与导航流程

- 应用启动后先轮询 side-car 健康检查；就绪后展示**登录页**。
- 使用 `.env` 中 `BOOTSTRAP_ADMIN_USER` / `BOOTSTRAP_ADMIN_PASSWORD` 对应的初始管理员登录。
- 登录成功后顶部导航栏出现：**对话**（Chat）；当角色为 `admin` 时额外出现
  **管理后台**（Admin）；以及**退出**按钮。
- 管理后台包含：用户管理（增删改查）、知识库管理（上传 / 列表 / 删除）、
  高级设置（前瞻性 feature flag）、系统监控（用量统计）。
