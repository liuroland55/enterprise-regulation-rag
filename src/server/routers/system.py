"""系统状态路由（System Router）。

实现系统健康检查与统计两个端点（Task 7.14）：
- ``GET /system/health``：直接复用现有 ``RAG2API().health_check()``，
  返回 RAG 核心的健康状态字典（status / mode / 初始化与子系统就绪标志等）。
- ``GET /system/stats``（需认证，``Depends(get_current_user)``）：复用现有
  ``RAG2API().get_statistics()`` 获取向量库统计，并按 CLOUD / LOCAL 运行模式
  标注 token cost / latency 的语义（CLOUD 下为有意义的用量指标；LOCAL 下
  仅供参考）。

设计约束（Requirement 18）：
- 仅通过现有 ``RAG2API`` 公共 API 访问 RAG 核心，不直接导入任何模型类
  （Requirement 18.1 / 18.4）；``RAG2API`` 已经过 settings 工厂统一路由。
- 不修改 RAG 核心（``src/api/rag_api.py`` 等）。
- ``RAG2API`` 在各处理函数内部**惰性构造**，确保导入本模块时无副作用
  （避免在 import 阶段就触发 Ollama / OpenAI 等外部依赖初始化）。

约定：代码 / API 名称使用英文；注释使用中文。

_Requirements: 18.1, 18.2, 18.3, 18.4_
"""

from fastapi import APIRouter, Depends

from src.server.config import settings
from src.server.env_file import set_env_vars
from src.server.schemas import ModeInfo, ModeUpdateRequest, ModeUpdateResult
from src.server.security import get_current_user

# 系统路由：路径中显式携带 /system 前缀，与其它路由模块保持一致（无额外 prefix）。
router = APIRouter(tags=["system"])

# 项目根目录的 RAG 核心配置文件（侧车以项目根为工作目录运行）。
# 模式切换只写此文件，绝不触碰侧车专属的 .env.server。
ENV_FILE_PATH = ".env"

# 各模式使用独立的向量库目录：LOCAL(Ollama, 768 维) 与 CLOUD(OpenAI, 1536 维) 嵌入
# 维度不同，复用同一 Chroma 目录会在查询时维度报错；按模式分目录可彻底规避冲突。
_PERSIST_DIRS = {"LOCAL": "./chroma_db_local", "CLOUD": "./chroma_db_cloud"}


def _persist_dir_for(mode: str) -> str:
    """返回某模式对应的向量库持久化目录（未知模式回退到默认 ./chroma_db）。"""
    return _PERSIST_DIRS.get(mode, "./chroma_db")


def _usage_metrics_semantics(mode: str) -> dict:
    """根据运行模式返回 token cost / latency 指标的语义说明。

    - CLOUD 模式：调用云端模型（如 OpenAI）会产生真实的按量计费与网络延迟，
      因此 token cost 与 latency 是**有意义的**用量指标（Requirement 18.2）；
    - LOCAL 模式：使用本地 Ollama 推理，无按量计费，延迟取决于本机算力，
      故这些指标**仅供参考**（Requirement 18.3）。
    """
    if mode == "CLOUD":
        return {
            "token_cost": "meaningful",
            "latency": "meaningful",
            "note": (
                "CLOUD mode: token cost and latency reflect real billable usage "
                "and network round-trips, and are meaningful usage metrics."
            ),
        }
    # 默认按 LOCAL 处理：本地推理无计费，指标仅供参考。
    return {
        "token_cost": "informational",
        "latency": "informational",
        "note": (
            "LOCAL mode: token cost and latency are informational only; "
            "local inference is not billed per token and latency depends on host."
        ),
    }


@router.get("/system/health")
def health() -> dict:
    """系统健康检查：直接复用现有 ``RAG2API`` 健康检查。

    惰性构造 ``RAG2API`` 单例（导入本模块时不触发初始化），并原样返回其
    ``health_check()`` 字典，避免对 RAG 核心做任何改动。
    """
    # 惰性导入：确保导入本模块无副作用（不在 import 阶段构造 RAG2API）。
    from src.api.rag_api import RAG2API

    return RAG2API().health_check()


@router.get("/system/stats", dependencies=[Depends(get_current_user)])
def stats() -> dict:
    """向量库统计：复用现有 ``RAG2API`` 统计，并附加运行模式上下文。

    需认证（``Depends(get_current_user)``）。在原始统计字典基础上追加：
    - ``mode``：当前运行模式（CLOUD / LOCAL）；
    - ``usage_metrics``：token cost / latency 指标在该模式下的语义说明，
      用以体现 CLOUD（有意义）与 LOCAL（仅供参考）的差异（Requirement 18.2 / 18.3）。
    """
    # 惰性导入：确保导入本模块无副作用（不在 import 阶段构造 RAG2API）。
    from src.api.rag_api import RAG2API

    result = RAG2API().get_statistics()

    # 附加运行模式上下文：以服务级配置中的 MODE 为准，标注用量指标语义。
    mode = settings.MODE
    result["mode"] = mode
    result["usage_metrics"] = _usage_metrics_semantics(mode)
    return result


# --------------------------------------------------------------------------- #
# 路由：读取 / 切换运行模式（LOCAL / CLOUD）
# --------------------------------------------------------------------------- #
@router.get("/system/mode", response_model=ModeInfo, dependencies=[Depends(get_current_user)])
def get_mode() -> ModeInfo:
    """返回当前**生效**的运行模式及其就绪信息（任意已认证用户可读）。

    - ``mode``：当前进程实际生效的模式（启动期由 .env 决定，切换后需重启才更新）；
    - ``cloud_ready``：是否已配置 ``OPENAI_API_KEY``（切到 CLOUD 的前置条件）；
    - ``persist_dir``：该模式建议使用的向量库目录。
    """
    return ModeInfo(
        mode=settings.MODE,
        cloud_ready=bool(settings.OPENAI_API_KEY.strip()),
        persist_dir=_persist_dir_for(settings.MODE),
    )


@router.post("/system/mode", response_model=ModeUpdateResult, dependencies=[Depends(get_current_user)])
def set_mode(body: ModeUpdateRequest) -> ModeUpdateResult:
    """切换全局运行模式（任意已认证用户可操作）。

    将目标 ``MODE`` 与对应的 ``CHROMA_PERSIST_DIR`` 写回项目根 ``.env``；由于 RAG 核心
    在**启动期**初始化模型与向量库，故切换**需重启侧车**才能生效（``restart_required`` 恒为 True）。
    切到 CLOUD 但缺少 ``OPENAI_API_KEY`` 时返回非阻断性 ``warning``。

    注意：模式是全局设置（单一后端），切换会影响所有用户。
    """
    # body.mode 已由 schema 校验并归一化为 "CLOUD" / "LOCAL"
    mode = body.mode
    persist_dir = _persist_dir_for(mode)

    # 仅写 RAG 核心的 .env（MODE + 按模式的向量库目录）；保留其余行与注释
    set_env_vars(ENV_FILE_PATH, {"MODE": mode, "CHROMA_PERSIST_DIR": persist_dir})

    # 切到 CLOUD 但未配置密钥：给出非阻断提示（仍允许写入，重启后健康检查会显示降级）
    warning = None
    if mode == "CLOUD" and not settings.OPENAI_API_KEY.strip():
        warning = (
            "OPENAI_API_KEY is not configured; CLOUD mode will run degraded "
            "until you set it in .env."
        )

    return ModeUpdateResult(mode=mode, restart_required=True, warning=warning)


__all__ = ["router"]
