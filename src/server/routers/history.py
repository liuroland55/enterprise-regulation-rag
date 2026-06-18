"""查询历史路由（History Router）。

实现按用户隔离的查询历史检索与管理（Task 7.7）：
- ``GET /history``：仅返回当前用户自己的历史（``QueryHistory.user_id == user.id``），
  按 ``created_at`` 倒序分页，返回 ``HistoryListResponse(items, page, page_size, total)``；
- ``GET /history/{history_id}``：仅本人记录返回；不存在或他人记录一律返回 HTTP 404，
  避免跨用户存在性泄露（no cross-user disclosure）；
- ``DELETE /history/{history_id}``：仅本人可删（HTTP 204）；否则返回 HTTP 404；
- ``GET /admin/history``（``require_role("admin")``，可选 ``user_id`` 过滤）：审计能力，
  列出所有用户历史，非员工常规界面。

安全约定：身份一律取自 JWT 还原的 ``user.id``，绝不信任客户端传入的 user_id。
代码 / API 名称使用英文；注释使用中文。本任务不修改 RAG 核心。

_Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from src.server.db import get_session
from src.server.models import QueryHistory, User
from src.server.schemas import HistoryItem, HistoryListResponse, UserContext
from src.server.security import get_current_user, require_role

# History 路由：路径中显式携带 /history 与 /admin/history 前缀，与设计文档保持一致。
router = APIRouter(tags=["history"])


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #
def to_history_item(row: QueryHistory, username: str | None = None) -> HistoryItem:
    """将 ``QueryHistory`` 表行映射为对外的 ``HistoryItem`` DTO。

    仅暴露查询历史所需字段；``question`` 为员工原始问题（绝非增强后的查询）。

    可选 ``username``：仅管理员审计端点会传入提问者用户名，此时同时回填
    ``user_id`` 以标识提问者；按用户隔离的常规端点不传，二者保持为 None。
    """
    return HistoryItem(
        id=row.id,
        question=row.question,
        answer=row.answer,
        grade=row.grade,
        iterations=row.iterations,
        success=row.success,
        source_count=row.source_count,
        created_at=row.created_at,
        # 仅当显式传入 username（管理员审计）时回填提问者身份，否则保持 None
        user_id=row.user_id if username is not None else None,
        username=username,
    )


# --------------------------------------------------------------------------- #
# 路由：列出当前用户历史（分页、倒序）
# --------------------------------------------------------------------------- #
@router.get("/history", response_model=HistoryListResponse)
def list_history(
    page: int = 1,
    page_size: int = 20,
    user: UserContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HistoryListResponse:
    """列出当前用户自己的查询历史。

    仅返回 ``user_id`` 等于 JWT 还原身份的记录（Requirement 11.1），
    按 ``created_at`` 倒序排列并应用分页（Requirement 11.2）。
    """
    # 仅限定为当前用户自己的历史（身份取自 JWT，绝不信任客户端入参）
    base = select(QueryHistory).where(QueryHistory.user_id == user.id)
    total = len(session.exec(base).all())
    rows = session.exec(
        base.order_by(QueryHistory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return HistoryListResponse(
        items=[to_history_item(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


# --------------------------------------------------------------------------- #
# 路由：获取单条历史（仅本人）
# --------------------------------------------------------------------------- #
@router.get("/history/{history_id}", response_model=HistoryItem)
def get_history(
    history_id: int,
    user: UserContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HistoryItem:
    """获取单条查询历史，仅当记录属于当前用户时返回。

    记录不存在或属于其他用户时一律返回 HTTP 404，避免跨用户存在性泄露
    （Requirement 11.3 / 11.4）。
    """
    row = session.get(QueryHistory, history_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "History not found")
    return to_history_item(row)


# --------------------------------------------------------------------------- #
# 路由：删除单条历史（仅本人）
# --------------------------------------------------------------------------- #
@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(
    history_id: int,
    user: UserContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """删除当前用户自己的单条查询历史。

    记录不存在或属于其他用户时一律返回 HTTP 404（Requirement 11.5 / 11.6）。
    """
    row = session.get(QueryHistory, history_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "History not found")
    session.delete(row)
    session.commit()


# --------------------------------------------------------------------------- #
# 路由：管理员审计 —— 列出所有用户历史（可选 user_id 过滤）
# --------------------------------------------------------------------------- #
@router.get(
    "/admin/history",
    response_model=HistoryListResponse,
    dependencies=[Depends(require_role("admin"))],
)
def admin_list_history(
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    session: Session = Depends(get_session),
) -> HistoryListResponse:
    """审计能力：管理员可查看所有用户历史（Requirement 11.7）。

    由 ``require_role("admin")`` 门控；当提供 ``user_id`` 时按该用户过滤，
    否则列出全部用户历史。按 ``created_at`` 倒序分页。
    """
    base = select(QueryHistory)
    if user_id is not None:
        base = base.where(QueryHistory.user_id == user_id)
    total = len(session.exec(base).all())
    rows = session.exec(
        base.order_by(QueryHistory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # 审计增强：一次性查询 User 表构建 {id: username} 映射，
    # 为每条返回项补充 user_id / username，使管理员可识别提问者身份。
    # 仅在本管理员端点附加身份字段；按用户隔离的 /history 端点保持 None。
    asker_ids = {r.user_id for r in rows}
    username_map: dict[int, str] = {}
    if asker_ids:
        users = session.exec(select(User).where(User.id.in_(asker_ids))).all()
        username_map = {u.id: u.username for u in users}

    items = [
        to_history_item(r, username=username_map.get(r.user_id))
        for r in rows
    ]
    return HistoryListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


__all__ = ["router", "to_history_item"]
