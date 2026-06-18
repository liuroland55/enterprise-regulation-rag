"""查询路由（Query Router）。

实现单个员工提问的端到端编排（Task 7.3）：
- ``POST /ask``（``Depends(get_current_user)`` + ``Depends(get_session)``）：
  从已校验的 JWT 用户上下文构造 ``UserProfile``（position + tasks），经
  ``build_augmented_query`` 做职位感知查询增强，再调用现有
  ``RAG2API().ask(augmented, return_context=req.return_context)``，将结果映射为
  ``AskResponse``（answer / grade / reason / iterations / success，sources 取自
  ``result["context"]``）。当 RAG 返回 ``success=false`` 时，仍以 HTTP 200 返回并
  携带 ``success=false``、错误文本置于 ``answer``（Requirement 9.3）。
- best-effort 持久化 ``QueryHistory``：记录**原始问题** ``req.question``（绝非增强后的
  查询），以及 answer / grade / iterations / success / source_count。写库失败仅
  ``logger.exception`` 并回滚，``/ask`` 响应不受影响（Requirement 10.4）。

设计约束（Zero RAG Core Changes）：
- 仅通过现有 ``RAG2API`` 公共 API 访问 RAG 核心，绝不修改 ``src/api/rag_api.py``；
- ``RAG2API`` 在处理函数内部**惰性导入并构造**，确保导入本模块时无副作用
  （不在 import 阶段触发 Ollama / OpenAI / ChromaDB 等外部依赖初始化）。

约定：代码 / API 名称使用英文；注释使用中文。

_Requirements: 8.1, 8.6, 9.1, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4_
"""

import logging
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from src.server.db import engine, get_session
from src.server.injection import build_augmented_query
from src.server.models import QueryHistory
from src.server.schemas import AskRequest, AskResponse, SourceItem, UserContext, UserProfile
from src.server.security import get_current_user

logger = logging.getLogger(__name__)

# 查询路由：路径中显式携带 /ask，与其它路由模块保持一致（无额外 prefix）。
router = APIRouter(tags=["query"])


def _map_sources(context: object) -> list[SourceItem]:
    """将 RAG 返回的 context 项稳健地映射为 ``SourceItem`` 列表。

    ``RAG2API.ask`` 在 ``return_context=True`` 时返回 ``result["context"]``，其元素
    通常为 ``{"content": ..., "source": ...}`` 形式的字典；但为兼容直接返回
    Document-like 对象（带 ``page_content`` / ``metadata``）的情形，这里做防御式处理：
    - dict：优先取 ``content`` / ``source`` 键；
    - 对象：回退到 ``page_content`` 与 ``metadata["source"]``（或 ``source`` 属性）。
    任何无法识别的项都会被安全跳过，避免因单条脏数据导致整个响应失败。
    """
    if not context:
        return []

    sources: list[SourceItem] = []
    for item in context:
        try:
            if isinstance(item, dict):
                # 字典形式：标准的 {"content": ..., "source": ...}
                content = item.get("content", "")
                source = item.get("source", "Unknown")
            else:
                # Document-like 对象：回退到 page_content / metadata
                content = getattr(item, "page_content", "")
                metadata = getattr(item, "metadata", None)
                if isinstance(metadata, dict):
                    source = metadata.get("source", "Unknown")
                else:
                    source = getattr(item, "source", "Unknown")

            sources.append(
                SourceItem(
                    content="" if content is None else str(content),
                    source="Unknown" if source is None else str(source),
                )
            )
        except Exception:  # noqa: BLE001 - 单条映射失败不应影响整体响应
            # 跳过无法识别的 context 项，保持映射稳健。
            logger.warning("Skipping unmappable context item during /ask source mapping.")
            continue

    return sources


def _persist_history(
    session: Session,
    user_id: int,
    original_question: str,
    response: AskResponse,
) -> None:
    """best-effort 持久化一条查询历史。

    存储**原始问题**（绝非增强后的查询）以及 answer / grade / iterations /
    success / source_count（Requirement 10.2 / 10.3）。
    写库失败仅记录异常并回滚，绝不向上抛出，从而保证 ``/ask`` 响应不受影响
    （Requirement 10.4）。
    """
    try:
        record = QueryHistory(
            user_id=user_id,
            question=original_question,  # 原始问题，绝非增强查询
            answer=response.answer,
            grade=response.grade,
            iterations=response.iterations,
            success=response.success,
            source_count=len(response.sources),
        )
        session.add(record)
        session.commit()
    except Exception:  # noqa: BLE001 - best-effort：失败仅记录日志并回滚
        # 写库失败不影响响应：记录完整堆栈并回滚事务。
        logger.exception("Failed to persist QueryHistory; response is unaffected.")
        try:
            session.rollback()
        except Exception:  # noqa: BLE001 - 回滚本身失败也不得影响响应
            logger.exception("Rollback after QueryHistory persistence failure also failed.")


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    user: UserContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AskResponse:
    """处理单个员工提问并返回结构化答案。

    流程（对应 Flow 2 / Requirement 8 & 9 & 10）：
    1) 从已校验 JWT 用户上下文构造 ``UserProfile``（position + tasks），
       绝不信任客户端传入的 profile（Requirement 8.1）；
    2) ``build_augmented_query`` 做职位感知查询增强（Requirement 8.2 ~ 8.6）；
    3) 调用未改动的 ``RAG2API().ask(augmented, return_context=...)``（Requirement 8.6 / 9.1）；
    4) 映射为 ``AskResponse``，sources 取自 ``result["context"]``（Requirement 9.4）；
       RAG 失败时仍以 HTTP 200 携带 ``success=false``（Requirement 9.3）；
    5) best-effort 写入 ``QueryHistory``（原始问题），失败不影响响应（Requirement 10.x）。
    """
    # 1) 从 JWT 用户上下文构造画像（职位 + 任务）——绝不取自请求体
    profile = UserProfile(position=user.position, tasks=user.tasks)

    # 2) 职位感知查询增强（纯函数）；透传 lang 以便注入语言指令
    augmented_query = build_augmented_query(profile, req.question, req.lang)

    # 3) 惰性导入并调用 RAG 核心（确保导入本模块无副作用，不修改 RAG 核心）
    from src.api.rag_api import RAG2API
    from src.server.retrieval import resolve_request_vector_store, use_vector_store

    # 解析本次请求应使用的向量库（优先级：临时文件 > 勾选范围 > 全部）。
    scoped = resolve_request_vector_store(
        req.kb_sources,
        [d.model_dump() for d in (req.temp_context or [])],
    )

    if scoped is not None:
        # 在锁保护下临时替换全局向量库，使本次检索仅依据范围/临时库
        with use_vector_store(scoped):
            result = RAG2API().ask(augmented_query, return_context=req.return_context)
    else:
        # 未附加临时文件且未勾选范围：沿用全局向量库（检索全部）
        result = RAG2API().ask(augmented_query, return_context=req.return_context)

    # 4) 映射 RAG 结果为 AskResponse；缺失字段使用安全默认值。
    #    success=false 时不抛错，照常以 HTTP 200 返回（Requirement 9.3）。
    response = AskResponse(
        answer=result.get("answer", ""),
        grade=result.get("grade", "NO"),
        reason=result.get("reason", ""),
        iterations=int(result.get("iterations", 0) or 0),
        success=bool(result.get("success", False)),
        sources=_map_sources(result.get("context")),
    )

    # 5) best-effort 持久化历史：存原始问题（req.question），失败不影响响应。
    _persist_history(session, user.id, req.question, response)

    return response


def _sse(payload: dict) -> str:
    """将一条事件序列化为 SSE（Server-Sent Events）数据帧。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _emit_step(node_name: str, node_state: dict):
    """根据工作流节点产出对应的 SSE 步骤帧（生成器）。

    将 Self-RAG 各节点（检索 / 生成评分 / 重写查询）的中间进展映射为前端可消费的
    step 事件；无需推送的节点不产出任何帧。抽取为独立函数以便在“替换向量库”与
    “不替换”两条分支中复用，保持 SSE 事件语义完全一致。
    """
    if node_name == "retrieve":
        yield _sse({
            "kind": "step",
            "type": "retrieve",
            "iteration": node_state.get("iterations", 0),
            "docs": len(node_state.get("context") or []),
        })
    elif node_name == "generate_and_grade":
        yield _sse({
            "kind": "step",
            "type": "generate",
            "iteration": node_state.get("iterations", 0),
            "grade": node_state.get("grade", ""),
            "reason": node_state.get("reason", ""),
        })
    elif node_name == "rewrite_query":
        yield _sse({
            "kind": "step",
            "type": "rewrite",
            "iteration": node_state.get("iterations", 0),
            "query": node_state.get("current_query", ""),
        })


@router.post("/ask/stream")
def ask_stream(
    req: AskRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """流式返回 Self-RAG 的“后台思考过程”，思考完成后给出最终答案。

    与 ``/ask`` 相同地做职位感知查询增强，但改为逐节点流式推送中间步骤
    （检索 / 生成评分 / 重写查询），最后推送 ``final`` 事件携带完整 ``AskResponse``。
    历史照常 best-effort 持久化（存原始问题）。

    事件格式（SSE，每帧一个 JSON）：
      - {"kind":"step","type":"retrieve","iteration":N,"docs":K}
      - {"kind":"step","type":"generate","iteration":N,"grade":"YES|NO","reason":"..."}
      - {"kind":"step","type":"rewrite","iteration":N,"query":"..."}
      - {"kind":"final", answer/grade/reason/iterations/success/sources}
      - {"kind":"error","message":"..."}

    设计约束：仅使用 ``RAG2API`` 已编译的 workflow 与 ``initialize_state``，
    不修改 RAG 核心。``RAG2API`` 惰性导入。
    """
    # 身份与画像取自 JWT（绝不信任请求体）；在进入生成器前先固定下来。
    profile = UserProfile(position=user.position, tasks=user.tasks)
    augmented_query = build_augmented_query(profile, req.question, req.lang)
    original_question = req.question
    user_id = user.id
    # 检索控制字段（在进入生成器前固定）：勾选范围 + 临时文件
    kb_sources = req.kb_sources
    temp_context = [d.model_dump() for d in (req.temp_context or [])]

    def event_gen():
        # 惰性导入，避免模块加载期触发 RAG 核心外部依赖初始化。
        from src.api.rag_api import RAG2API
        from src.graph.workflow import initialize_state
        from src.config.settings import config
        from src.server.retrieval import (
            resolve_request_vector_store,
            use_vector_store,
        )

        try:
            api = RAG2API()
            if api.workflow is None:
                api.initialize()

            state = initialize_state(
                augmented_query, max_iterations=config.MAX_ITERATIONS
            )

            # 解析本次请求应使用的向量库（优先级：临时文件 > 勾选范围 > 全部）。
            scoped = resolve_request_vector_store(kb_sources, temp_context)

            final_state = None
            if scoped is not None:
                # 在锁保护下临时替换全局向量库，整个流式期间持锁（桌面单用户可接受）。
                with use_vector_store(scoped):
                    for step in api.workflow.stream(state):
                        for node_name, node_state in step.items():
                            final_state = node_state
                            for frame in _emit_step(node_name, node_state):
                                yield frame
            else:
                # 未附加临时文件且未勾选范围：沿用全局向量库（检索全部）。
                for step in api.workflow.stream(state):
                    for node_name, node_state in step.items():
                        final_state = node_state
                        for frame in _emit_step(node_name, node_state):
                            yield frame

            if final_state is None:
                yield _sse({"kind": "error", "message": "No result produced"})
                return

            # 组装最终响应（与 /ask 一致的字段语义）。
            response = AskResponse(
                answer=final_state.get("answer", ""),
                grade=final_state.get("grade", "NO"),
                reason=final_state.get("reason", ""),
                iterations=int(final_state.get("iterations", 0) or 0),
                success=True,
                sources=_map_sources(final_state.get("context")),
            )

            # best-effort 持久化历史：流式场景用独立 Session，避免跨请求生命周期问题。
            try:
                with Session(engine) as s:
                    _persist_history(s, user_id, original_question, response)
            except Exception:  # noqa: BLE001 - 持久化失败不影响最终答案推送
                logger.exception("History persistence failed in /ask/stream; ignored.")

            yield _sse({
                "kind": "final",
                "answer": response.answer,
                "grade": response.grade,
                "reason": response.reason,
                "iterations": response.iterations,
                "success": response.success,
                "sources": [{"content": s.content, "source": s.source} for s in response.sources],
            })
        except Exception as e:  # noqa: BLE001 - 流式过程中的任何错误以 error 事件告知前端
            logger.exception("Streaming /ask failed")
            yield _sse({"kind": "error", "message": str(e)})

    # text/event-stream + 关闭缓冲，保证逐帧实时下发。
    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
