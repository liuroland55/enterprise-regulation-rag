"""管理员用户管理路由（Admin Router）。

实现管理后台的用户 CRUD（Task 7.10），全部端点仅限 admin 角色访问
（``dependencies=[Depends(require_role("admin"))]``）：

- ``POST /admin/users``（``UserCreate``）：重名返回 409；创建前强制密码策略
  （``enforce_password_policy``，不满足返回 422）；密码经 ``hash_password`` 哈希；
  ``tasks`` 以 JSON 编码后存储；返回 ``UserOut``。
- ``GET /admin/users``：列出所有用户（``UserOut`` 列表，绝不含 password_hash）。
- ``GET /admin/users/{user_id}``：读取单个用户；不存在返回 404。
- ``PUT /admin/users/{user_id}``（``UserUpdate``）：仅更新提供的字段
  （position / tasks / role）并刷新 ``updated_at``；不存在返回 404。
- ``DELETE /admin/users/{user_id}``：删除用户；不存在返回 404。

约定：代码 / API 名称使用英文；注释使用中文。本任务不修改 models.py /
security.py 与 RAG 核心。

_Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from src.server.db import get_session
from src.server.models import User
from src.server.schemas import UserCreate, UserOut, UserUpdate
from src.server.security import enforce_password_policy, hash_password, require_role

# 管理路由：路径中显式携带 /admin 前缀；整个路由统一要求 admin 角色。
router = APIRouter(
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
)


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #
def _decode_tasks(raw: str) -> list[str]:
    """将 ``user.tasks``（JSON 编码的字符串列表）安全解码为 Python 列表。

    对空值 / 非法 JSON / 非列表结构一律降级为空列表 ``[]``，
    并仅保留字符串项，避免脏数据导致响应序列化失败。
    """
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, str)]


def to_user_out(user: User) -> UserOut:
    """将 ``User`` 表模型映射为对外视图 ``UserOut``。

    关键点：解码 ``tasks`` JSON -> ``list[str]``，且绝不暴露 password_hash。
    """
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        position=user.position,
        tasks=_decode_tasks(user.tasks),
        is_active=user.is_active,
        created_at=user.created_at,
    )


# --------------------------------------------------------------------------- #
# 路由：创建用户
# --------------------------------------------------------------------------- #
@router.post("/admin/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    session: Session = Depends(get_session),
) -> UserOut:
    """创建用户。

    流程：重名校验（409）-> 强制密码策略（不满足 422）-> 密码哈希 ->
    tasks JSON 编码存储 -> 持久化 -> 返回 ``UserOut``（Requirement 12.2 / 12.4）。
    """
    # 重名校验：用户名已存在则返回 409 冲突（Requirement 12.4）
    existing = session.exec(
        select(User).where(User.username == body.username)
    ).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")

    # 强制密码策略：不满足时返回 HTTP 422（不可预处理实体）
    try:
        enforce_password_policy(body.password)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
        ) from exc

    # 密码哈希 + tasks JSON 编码后落库（绝不存明文）
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        position=body.position,
        tasks=json.dumps(body.tasks),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return to_user_out(user)


# --------------------------------------------------------------------------- #
# 路由：列出所有用户
# --------------------------------------------------------------------------- #
@router.get("/admin/users", response_model=list[UserOut])
def list_users(
    session: Session = Depends(get_session),
) -> list[UserOut]:
    """列出所有用户（``UserOut`` 列表，绝不含 password_hash）。"""
    users = session.exec(select(User)).all()
    return [to_user_out(u) for u in users]


# --------------------------------------------------------------------------- #
# 路由：读取单个用户
# --------------------------------------------------------------------------- #
@router.get("/admin/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    session: Session = Depends(get_session),
) -> UserOut:
    """读取单个用户；不存在返回 404。"""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return to_user_out(user)


# --------------------------------------------------------------------------- #
# 路由：更新用户
# --------------------------------------------------------------------------- #
@router.put("/admin/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    session: Session = Depends(get_session),
) -> UserOut:
    """更新用户：仅更新提供（非 None）的字段并刷新 ``updated_at``。

    可更新字段：position / tasks / role；``tasks`` 不为 None 时以 JSON 编码存储。
    用户不存在返回 404（Requirement 12.3）。
    """
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # 仅更新显式提供的字段（None 表示不修改）
    if body.position is not None:
        user.position = body.position
    if body.tasks is not None:
        user.tasks = json.dumps(body.tasks)
    if body.role is not None:
        user.role = body.role

    # 刷新更新时间
    user.updated_at = datetime.utcnow()

    session.add(user)
    session.commit()
    session.refresh(user)

    return to_user_out(user)


# --------------------------------------------------------------------------- #
# 路由：删除用户
# --------------------------------------------------------------------------- #
@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
) -> None:
    """删除用户；不存在返回 404。"""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    session.delete(user)
    session.commit()


__all__ = ["router", "to_user_out"]
