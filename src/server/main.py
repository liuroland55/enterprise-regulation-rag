"""FastAPI 应用工厂与 side-car 启动入口（Task 8.1）。

本模块负责把已实现的各路由（auth / query / history / admin / kb / system）装配为
一个 FastAPI 应用，并完成启动期的基础设施初始化：

- ``create_app() -> FastAPI``：
  - 创建 FastAPI app 并 ``include`` 全部 router；
  - 通过现代 ``lifespan`` 上下文管理器注册启动钩子：依次执行 ``init_db()`` 建表、
    ``seed_admin()`` 播种初始管理员；
  - 可选地在启动期惰性初始化 ``RAG2API`` 单例，但**必须容错**：若 RAG 核心初始化失败
    （如 Ollama / OpenAI / ChromaDB 等外部依赖不可用），**绝不阻止服务启动**——仅记录
    warning 并继续，让 ``GET /system/health`` 如实反映降级（degraded）状态；
  - 配置 CORS，允许本地 Tauri webview 来源（``http://localhost`` 及 ``tauri://`` 来源）。

- side-car 入口（``if __name__ == "__main__":``）：使用 uvicorn 运行，**仅绑定回环地址**
  ``settings.SIDECAR_HOST`` (127.0.0.1) 与 ``settings.SIDECAR_PORT`` (8756)，
  与 Tauri ``sidecar.rs`` 的开发回退命令 ``python -m src.server.main`` 保持一致
  （Requirement 1.2 / 17.1）。

设计约束（Zero RAG Core Changes）：本模块仅通过现有 ``RAG2API`` 公共 API 访问 RAG 核心，
绝不修改 ``src/api/rag_api.py`` 等核心文件；``RAG2API`` 在启动钩子内部**惰性导入**，
确保导入本模块本身无外部副作用。

约定：代码 / API 名称使用英文；注释使用中文。

_Requirements: 1.1, 1.2, 7.1, 7.2, 17.1, 18.1_
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.server.config import settings
from src.server.db import init_db, seed_admin

# 自托管的 Swagger UI 静态资源目录（随包附带），用于离线 / CDN 受限环境（如中国大陆）。
# 默认 /docs 会从 cdn.jsdelivr.net 加载 swagger 资源，在被墙网络下页面空白；
# 这里改为从本地 /static 提供，确保 OAuth2 / API 文档页始终可用。
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# 项目根目录（.../src/server/main.py -> 上溯两级）。/favicon.ico 路由从此目录读取图标文件，
# 未放置时优雅返回 204（不显示图标）。
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 站点图标目录：项目根下的 FAV/，内含 favicon.ico + favicon-16x16.png + favicon-32x32.png。
# 存在时挂载到 /fav 并供 /docs 引用（zero 外链）；不存在则回退到根目录图标或 204。
_FAV_DIR = os.path.join(_PROJECT_ROOT, "FAV")

# 各路由模块均导出名为 ``router`` 的 APIRouter。
# 路径前缀已在各模块内部声明（如 /auth、/ask、/history、/admin、/kb、/system），
# 因此这里 include 时不再追加额外 prefix（kb 路由自带 prefix="/kb"）。
from src.server.routers.admin import router as admin_router
from src.server.routers.auth import router as auth_router
from src.server.routers.history import router as history_router
from src.server.routers.kb import router as kb_router
from src.server.routers.query import router as query_router
from src.server.routers.system import router as system_router

logger = logging.getLogger(__name__)


def _try_initialize_rag() -> None:
    """启动期惰性初始化 ``RAG2API`` 单例（容错，绝不阻止服务启动）。

    设计要点：
    - ``RAG2API`` 在此**惰性导入**，避免导入 ``main`` 模块时即触发外部依赖加载；
    - 优先尝试**完整初始化**（auto_init=True，加载 ChromaDB / 编译 LangGraph 工作流）；
    - 初始化失败（如本地 Ollama / 云端 OpenAI / 向量库不可用）时，**仅记录 warning**
      并继续启动，使 ``GET /system/health`` 能如实反映 unhealthy / degraded 状态，
      而不是让整个服务无法启动（Requirement 1.1 / 18.1）；
    - 失败后再以 ``auto_init=False`` 构造单例，把实例标记为已初始化但组件为空，
      从而让后续 ``health_check()`` 返回 “unhealthy 但成功响应” 的降级状态，
      避免健康检查端点因重复触发失败初始化而抛出 500。
    """
    # 惰性导入：确保导入本模块无外部副作用（不在 import 阶段构造 RAG2API）。
    from src.api.rag_api import RAG2API

    try:
        # 尝试完整初始化（单例：成功后全局复用，避免重复加载向量库 / 工作流）
        RAG2API()
        logger.info("RAG2API singleton initialized successfully at startup.")
    except Exception:  # noqa: BLE001 - 初始化失败不得阻止服务启动
        logger.warning(
            "RAG2API initialization failed at startup; the service will continue in a "
            "degraded mode. /system/health will reflect the unhealthy status. "
            "Verify the configured model backend (Ollama/OpenAI) and ChromaDB.",
            exc_info=True,
        )
        # 降级兜底：以 auto_init=False 构造单例并标记为已初始化（组件为空），
        # 使健康检查可如实返回 degraded，而非反复触发失败初始化导致 500。
        try:
            RAG2API(auto_init=False)
        except Exception:  # noqa: BLE001 - 兜底本身失败也不得阻止启动
            logger.warning(
                "Failed to construct a degraded RAG2API singleton; "
                "/system/health may surface initialization errors.",
                exc_info=True,
            )


def _get_live_vector_store():
    """获取运行中的 live 向量库（``RAG2API._instance.vector_store``）。

    采用惰性导入；单例不存在或解析失败时返回 None（调用方据此跳过同步）。
    与 ``retrieval`` / ``kb`` 中的取法保持一致，确保与检索同源。
    """
    try:
        from src.api.rag_api import RAG2API

        inst = getattr(RAG2API, "_instance", None)
        return getattr(inst, "vector_store", None) if inst is not None else None
    except Exception:  # noqa: BLE001 - 解析失败时安全返回 None
        return None


def _start_incremental_indexing():
    """启动期增量索引：先对 ./data 做一次同步，再启动文件系统监听器（容错）。

    - 通过惰性导入 ``src.server.indexing``，避免导入 ``main`` 时引入额外副作用；
    - 启动同步在 live store 可用时执行一次，记录简要摘要；
    - 监听器以 ``_get_live_vector_store`` 作为惰性取数回调，未安装 watchdog /
      目录缺失时返回 None（优雅 no-op）；
    - 整个过程以 try/except 兜底，绝不阻止服务启动。返回 observer（或 None）。
    """
    observer = None
    try:
        from src.server.indexing import start_data_watcher, sync_data_folder

        # 启动期一次性增量同步（仅在 live store 就绪时）
        live = _get_live_vector_store()
        if live is not None:
            summary = sync_data_folder(live)
            logger.info(
                "Startup incremental sync: added=%d, updated=%d, removed=%d, "
                "unchanged=%d, chunks_added=%d",
                len(summary.get("added", [])),
                len(summary.get("updated", [])),
                len(summary.get("removed", [])),
                summary.get("unchanged", 0),
                summary.get("chunks_added", 0),
            )
        else:
            logger.info("Startup incremental sync skipped: live vector store not available.")

        # 启动文件系统监听器（惰性取 live store）
        observer = start_data_watcher(_get_live_vector_store)
    except Exception:  # noqa: BLE001 - 启动期增量索引绝不阻止服务启动
        logger.warning("Failed to start incremental indexing; continuing.", exc_info=True)
    return observer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期钩子（现代 lifespan 上下文管理器）。

    启动阶段（yield 之前）依次执行：
    1. ``init_db()``：依据 SQLModel 元数据建表（幂等，Requirement 7.1 的前置）；
    2. ``seed_admin()``：仅在不存在任何 admin 时播种初始管理员（幂等，Requirement 7.1 / 7.2）；
    3. ``_try_initialize_rag()``：容错地惰性初始化 RAG 核心单例（Requirement 1.1 / 18.1）；
    4. ``_start_incremental_indexing()``：对 ./data 做一次增量同步并启动文件系统监听器（容错）。

    关闭阶段（yield 之后）停止文件系统监听器；SQLite 连接随进程结束释放，
    RAG2API 单例无显式释放需求。
    """
    # 1) 建表（幂等）
    init_db()
    # 2) 播种初始管理员（幂等；无 BOOTSTRAP_ADMIN_PASSWORD 时安全跳过）
    seed_admin()
    # 3) 容错初始化 RAG 核心（失败不阻止启动）
    _try_initialize_rag()
    # 4) 启动期对 ./data 执行一次增量同步，并启动文件系统监听器（容错，绝不阻止启动）
    observer = _start_incremental_indexing()
    # 将 observer 挂到 app.state，供关闭阶段停止
    app.state.data_watcher = observer

    yield

    # 关闭阶段：停止文件系统监听器（尽力而为，绝不抛出）。
    try:
        from src.server.indexing import stop_data_watcher

        stop_data_watcher(getattr(app.state, "data_watcher", None))
    except Exception:  # noqa: BLE001 - 关闭期兜底，绝不影响进程退出
        logger.warning("Failed to stop data watcher during shutdown.", exc_info=True)
    logger.info("Sidecar service shutting down.")


def create_app() -> FastAPI:
    """FastAPI 应用工厂：创建 app、配置 CORS、挂载全部 router。

    Returns:
        组装完成的 ``FastAPI`` 实例，已注册 lifespan 启动钩子与全部业务路由。
    """
    app = FastAPI(
        title="Enterprise Regulation RAG Sidecar",
        description=(
            "本地 FastAPI 侧车服务：账户系统 + 职位感知检索 + 知识库管理，"
            "包装既有 RAG2API（Self-RAG）核心。仅绑定回环地址，不对外暴露。"
        ),
        version="1.0.0",
        lifespan=lifespan,
        # 关闭默认的 CDN 版文档页（jsdelivr，在中国大陆常被墙导致空白）；
        # 下方改为自托管的 Swagger UI（/docs 由本地静态资源驱动）。Redoc 同样依赖 CDN，禁用。
        docs_url=None,
        redoc_url=None,
    )

    # --- CORS：允许本地 Tauri webview 来源 ---
    # Tauri 桌面端 webview 的来源在不同平台 / 模式下不一致：
    # - 开发模式：Vite dev server 通常为 http://localhost:<port>（端口可变）；
    # - 生产模式：Windows 上为 https://tauri.localhost，其它平台为 tauri://localhost。
    # 使用正则匹配本地回环来源（任意端口）+ tauri 自定义协议来源，
    # 既覆盖上述场景，又不放开非本地来源（服务本身仅监听回环，进一步收敛暴露面）。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        # 允许本地回环（http/https，任意端口）与 tauri:// 自定义协议来源
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://.*)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- 挂载全部业务路由（各模块已自带路径前缀） ---
    app.include_router(auth_router)
    app.include_router(query_router)
    app.include_router(history_router)
    app.include_router(admin_router)
    app.include_router(kb_router)
    app.include_router(system_router)

    # --- 站点图标：挂载 FAV/ 目录并提供根 /favicon.ico（无外链；缺省时 204） ---
    has_fav = os.path.isdir(_FAV_DIR)
    if has_fav:
        # 挂载 FAV/ 到 /fav：三个文件（favicon.ico + 16x16 + 32x32 png）均可按名访问
        app.mount("/fav", StaticFiles(directory=_FAV_DIR), name="fav")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        """提供站点图标，供浏览器默认的根 /favicon.ico 请求使用（零外部请求）。

        优先 ``FAV/favicon.ico``，再回退项目根的 ``favicon.ico`` / ``favicon.png``；
        均不存在时返回 204 No Content，浏览器将优雅地不显示图标，绝不报错。
        """
        candidates = ("FAV/favicon.ico", "favicon.ico", "favicon.png")
        for rel in candidates:
            path = os.path.join(_PROJECT_ROOT, *rel.split("/"))
            if os.path.isfile(path):
                return FileResponse(path)
        return Response(status_code=204)

    # --- 自托管 Swagger UI（离线 / CDN 受限可用） ---
    # 仅当静态资源目录存在时挂载；否则跳过（不影响其它接口与服务启动）。
    if os.path.isdir(_STATIC_DIR):
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

        # Swagger 单一 favicon 指向 .ico（含多尺寸）：FAV/ 存在用 /fav/favicon.ico，否则根 /favicon.ico
        favicon_url = "/fav/favicon.ico" if has_fav else "/favicon.ico"

        @app.get("/docs", include_in_schema=False)
        def custom_swagger_ui_html():
            """自托管的 OAuth2 / API 文档页：Swagger 资源全部取自本地 /static。

            替代 FastAPI 默认从 cdn.jsdelivr.net 加载的实现，确保在离线或被墙网络下
            （如中国大陆）``/docs`` 仍可正常渲染并使用 OAuth2 授权登录。
            当 ``FAV/`` 存在时额外注入 16x16 / 32x32 PNG 图标链接，使三个图标文件均被引用。
            """
            html = get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - Swagger UI",
                swagger_js_url="/static/swagger-ui-bundle.js",
                swagger_css_url="/static/swagger-ui.css",
                swagger_favicon_url=favicon_url,
            )
            if has_fav:
                # 在 </head> 前注入 PNG 图标链接（保留 FastAPI 生成的 .ico shortcut icon）
                extra = (
                    '<link rel="icon" type="image/png" sizes="32x32" href="/fav/favicon-32x32.png">'
                    '<link rel="icon" type="image/png" sizes="16x16" href="/fav/favicon-16x16.png">'
                )
                body = html.body.decode("utf-8").replace("</head>", extra + "</head>", 1)
                return HTMLResponse(body)
            return html

    return app


# 模块级 app 实例：供 uvicorn 以 "src.server.main:app" 方式导入（如打包二进制 / 部署）。
app = create_app()


def main() -> None:
    """side-car 进程入口：用 uvicorn 运行应用，仅绑定回环地址。

    与 Tauri ``sidecar.rs`` 的开发回退命令 ``python -m src.server.main`` 对齐；
    绑定 ``settings.SIDECAR_HOST`` (127.0.0.1) 与 ``settings.SIDECAR_PORT`` (8756)，
    确保服务不可从主机之外访问（Requirement 1.2 / 17.1）。
    """
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting sidecar service on %s", settings.bind_address)

    uvicorn.run(
        app,
        host=settings.SIDECAR_HOST,
        port=settings.SIDECAR_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()


__all__ = ["create_app", "app", "main"]
