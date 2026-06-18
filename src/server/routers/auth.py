"""认证路由（Auth Router）。

实现登录与令牌刷新两个端点（Task 7.1）：
- ``POST /auth/login``（OAuth2PasswordRequestForm）：按 username 查 User，
  使用 ``verify_password`` 校验密码；失败统一返回 HTTP 401 通用错误，
  避免泄露用户是否存在。成功则签发 access（claims：sub/username/role/
  position/tasks）+ refresh，并将 refresh token 持久化到 ``RefreshToken``
  表（含 ``expires_at``），返回 ``TokenResponse``。
- ``POST /auth/refresh``：接收 refresh_token，``decode_token`` 校验且要求
  ``type == "refresh"``；在 ``RefreshToken`` 表中查找该 token 且要求未吊销、
  未过期，命中则签发新的 access token；任何不满足条件的情况返回 HTTP 401。

约定：代码 / API 名称使用英文；注释使用中文。本任务不修改 models.py /
security.py 与 RAG 核心。

_Requirements: 4.1, 4.3, 4.4, 5.4, 5.5, 7.3_
"""

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from src.server.config import settings
from src.server.db import get_session
from src.server.models import RefreshToken, User
from src.server.schemas import RegisterRequest, TokenResponse, UserContext, UserOut
from src.server.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    enforce_password_policy,
    get_current_user,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

# 认证路由：路径中显式携带 /auth 前缀，与设计文档保持一致。
router = APIRouter(tags=["auth"])


# --------------------------------------------------------------------------- #
# 请求 / 响应 DTO
# --------------------------------------------------------------------------- #
class RefreshRequest(BaseModel):
    """``/auth/refresh`` 请求体：仅携带待校验的 refresh token。"""

    refresh_token: str


class AccessTokenResponse(BaseModel):
    """``/auth/refresh`` 响应体：返回新的 access token。"""

    access_token: str


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #
def _decode_user_tasks(raw: str) -> list[str]:
    """将 ``user.tasks``（JSON 编码的字符串列表）安全解码为 Python 列表。

    对空值 / 非法 JSON / 非列表结构一律降级为空列表 ``[]``，
    避免登录因脏数据而失败。
    """
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    # 仅保留字符串项，过滤异常结构
    return [item for item in decoded if isinstance(item, str)]


def _persist_refresh_token(session: Session, user_id: int, token: str) -> None:
    """将签发的 refresh token 持久化到 ``RefreshToken`` 表以支持吊销。

    ``expires_at`` 依据 ``settings.REFRESH_TOKEN_EXPIRE_DAYS`` 计算，
    与 ``create_refresh_token`` 内部的过期时间保持一致。
    """
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session.add(
        RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            revoked=False,
        )
    )
    session.commit()


# --------------------------------------------------------------------------- #
# 路由：登录
# --------------------------------------------------------------------------- #
@router.post("/auth/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> TokenResponse:
    """登录并签发双令牌。

    流程：按 username 查询用户 -> 校验密码 -> 签发 access + refresh ->
    持久化 refresh token -> 返回 ``TokenResponse``。
    登录失败（用户不存在或密码不匹配）统一返回 HTTP 401 通用错误，
    避免泄露用户存在性（Requirement 4.4）。
    """
    user = session.exec(select(User).where(User.username == form.username)).first()
    # 通用错误信息：不区分“用户不存在”与“密码错误”
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    # access token 声明：tasks 从 user.tasks（JSON）安全解码
    claims = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "position": user.position,
        "tasks": _decode_user_tasks(user.tasks),
    }
    access = create_access_token(claims)
    refresh = create_refresh_token(user.id)

    # 持久化 refresh token（含 expires_at）以支持吊销（Requirement 4.3）
    _persist_refresh_token(session, user.id, refresh)

    return TokenResponse(access_token=access, refresh_token=refresh, role=user.role)


# --------------------------------------------------------------------------- #
# 路由：自助注册（公开）
# --------------------------------------------------------------------------- #
@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    """公开自助注册：创建普通员工账户并直接签发双令牌（注册即登录）。

    流程：重名校验（409）-> 强制密码策略（不满足 422）-> 密码哈希 ->
    **role 硬编码 "employee"**（绝不接受客户端指定角色，杜绝自助提权）->
    tasks JSON 编码存储 -> 持久化 refresh token -> 返回 ``TokenResponse``。

    管理员账户只能由现有管理员在后台创建或将员工提升（见 admin 路由），
    本端点不提供任何途径创建 admin。
    """
    # 重名校验：用户名已存在则返回 409 冲突
    existing = session.exec(
        select(User).where(User.username == body.username)
    ).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")

    # 强制密码策略：不满足时返回 HTTP 422
    try:
        enforce_password_policy(body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # 创建员工账户：role 固定为 "employee"，密码哈希后落库，tasks JSON 编码
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="employee",
        position=body.position,
        tasks=json.dumps(body.tasks),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # 注册即登录：签发 access + refresh 并持久化 refresh（与 login 一致）
    claims = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "position": user.position,
        "tasks": _decode_user_tasks(user.tasks),
    }
    access = create_access_token(claims)
    refresh = create_refresh_token(user.id)
    _persist_refresh_token(session, user.id, refresh)

    return TokenResponse(access_token=access, refresh_token=refresh, role=user.role)


# --------------------------------------------------------------------------- #
# 路由：当前用户资料（资料双端同步的真相源）
# --------------------------------------------------------------------------- #
@router.get("/auth/me", response_model=UserOut)
def me(
    user: UserContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserOut:
    """返回当前登录用户的最新资料（直接读自数据库）。

    身份取自 JWT 还原的 ``user.id``（绝不信任客户端入参）。前端据此实时刷新
    职位 / 任务 / 角色等画像，使桌面端与网页端在管理员改动资料后保持一致，
    而无需等待 access token 过期重签。用户不存在返回 404。
    """
    row = session.get(User, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserOut(
        id=row.id,
        username=row.username,
        role=row.role,
        position=row.position,
        tasks=_decode_user_tasks(row.tasks),
        is_active=row.is_active,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# 路由：刷新 access token
# --------------------------------------------------------------------------- #
@router.post("/auth/refresh", response_model=AccessTokenResponse)
def refresh(
    body: RefreshRequest,
    session: Session = Depends(get_session),
) -> AccessTokenResponse:
    """使用有效的 refresh token 换取新的 access token。

    校验链路：
    1) ``decode_token`` 校验签名与过期时间（失败抛 HTTP 401）；
    2) 要求 ``type == "refresh"``，否则 401；
    3) 在 ``RefreshToken`` 表中查找该 token，要求存在、未吊销、未过期，
       否则 401（Requirement 5.5）；
    4) 命中则依据 token 中的 ``sub`` 还原用户并签发新的 access token
       （Requirement 5.4）。
    """
    # 1) 解码并校验令牌（无效 / 过期由 decode_token 抛 401）
    payload = decode_token(body.refresh_token)

    # 2) 必须为 refresh 类型
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    # 3) 在持久化表中查找该 refresh token 行
    stored = session.exec(
        select(RefreshToken).where(RefreshToken.token == body.refresh_token)
    ).first()
    if (
        stored is None
        or stored.revoked
        or stored.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    # 4) 还原用户并签发新的 access token
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    claims = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "position": user.position,
        "tasks": _decode_user_tasks(user.tasks),
    }
    access = create_access_token(claims)
    return AccessTokenResponse(access_token=access)


# 说明（首登强制改密标记）：
# 当前 User 模型未定义 must_change_password 字段，且本任务约定不修改 models.py
# 以避免与并行任务冲突。bootstrap admin 首次登录强制改密的能力，需要在后续任务中
# 为 User 增加相应列（如 must_change_password: bool）后再在登录响应中暴露该标记。
# TODO(后续任务): 为 User 增加 must_change_password 列，并在 TokenResponse / 登录
#   响应中返回该标记，以支持首次登录强制改密流程。


__all__ = ["router"]
