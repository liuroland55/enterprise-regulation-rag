"""安全与鉴权模块。

本模块按任务拆分为若干清晰分区，便于后续增量实现：
- `hash_password` / `verify_password`（passlib bcrypt），绝不存储或记录明文；
- 密码策略（长度 >= 8 且至少含一个字母与一个数字）；
- `create_access_token` / `create_refresh_token` / `decode_token`（HS256）；
- `get_current_user`（校验 type=access 并还原 `UserContext`）；
- `require_role` 依赖工厂（角色不匹配返回 HTTP 403）。

实现进度：
- Task 3.1（本文件已实现）：密码哈希/校验与密码策略；
- Task 3.4（已实现）：JWT 令牌与 `get_current_user`；
- Task 3.6（已实现）：`require_role` 依赖工厂。
"""

import re
import uuid
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.server.config import settings
from src.server.schemas import UserContext

# ---------------------------------------------------------------------------
# Section 1: 密码哈希与校验（Task 3.1）
# ---------------------------------------------------------------------------

# 全局密码上下文：使用 bcrypt 方案；deprecated="auto" 允许未来平滑迁移哈希算法。
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """使用 bcrypt 生成密码哈希。

    注意：绝不存储或记录明文密码，仅返回哈希值供持久化。
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    """校验明文密码与已存储哈希是否匹配。

    当且仅当 `plain` 是产生 `password_hash` 的原始明文时返回 True；
    其余情况（含哈希格式非法）一律返回 False，绝不抛出明文相关异常。
    """
    try:
        return pwd_context.verify(plain, password_hash)
    except (ValueError, TypeError):
        # 哈希格式不可识别时视为校验失败，避免泄露内部错误细节。
        return False


# ---------------------------------------------------------------------------
# Section 2: 密码策略（Task 3.1）
# ---------------------------------------------------------------------------

# 密码策略规则（服务端强制）：
# - 长度至少 8 个字符；
# - 至少包含一个字母（a-z / A-Z）；
# - 至少包含一个数字（0-9）。
MIN_PASSWORD_LENGTH = 8
_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"\d")


def validate_password_policy(password: str) -> bool:
    """检查密码是否满足策略，返回布尔结果（不抛异常）。

    满足以下全部条件时返回 True：长度 >= 8、至少含一个字母、至少含一个数字。
    供下游 auth/admin 路由在接受密码前调用。
    """
    if not isinstance(password, str):
        return False
    if len(password) < MIN_PASSWORD_LENGTH:
        return False
    if _LETTER_RE.search(password) is None:
        return False
    if _DIGIT_RE.search(password) is None:
        return False
    return True


def enforce_password_policy(password: str) -> None:
    """密码策略的抛错变体：不满足时抛出 ValueError。

    便于路由层在校验失败时直接转换为 HTTP 422/400 错误响应。
    """
    if not validate_password_policy(password):
        raise ValueError(
            "密码不符合策略：长度需至少 8 位，且至少包含一个字母与一个数字。"
        )


# ---------------------------------------------------------------------------
# Section 3: JWT 令牌与 get_current_user（Task 3.4）
# ---------------------------------------------------------------------------

# OAuth2 Bearer 方案：tokenUrl 指向登录端点，供 FastAPI 自动从
# Authorization: Bearer <token> 请求头提取访问令牌。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(
    claims: dict,
    expires_minutes: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    """签发短期 access token（HS256）。

    将调用方传入的 claims（如 sub/username/role/position/tasks）注入令牌，
    并附加过期时间 `exp` 与令牌类型 `type="access"`。
    """
    to_encode = claims.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode["type"] = "access"
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: int,
    expires_days: int = settings.REFRESH_TOKEN_EXPIRE_DAYS,
) -> str:
    """签发长期 refresh token（HS256）。

    携带 `sub`（用户 id）、`type="refresh"`、过期时间 `exp` 与随机 `jti`（JWT ID）；
    由调用方持久化到 SQLite 以支持吊销。

    `jti` 必不可少：refresh token 以其字符串值作为持久化表的唯一键，而 `exp` 仅精确到秒；
    若不加随机 `jti`，同一用户在同一秒内两次签发（如注册后立即登录、双击登录、多标签页）
    会产生完全相同的 token，导致 UNIQUE 约束冲突。`jti` 确保每次签发都唯一。
    """
    to_encode = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=expires_days),
        # 随机 JWT ID：保证每次签发的 token 字符串唯一（避免同秒内重复签发冲突）
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证令牌签名与过期时间。

    校验失败（签名无效 / 已过期 / 格式非法）一律抛出 HTTP 401，
    不泄露内部错误细节。
    """
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserContext:
    """从已校验的 access token 声明中还原已认证用户上下文。

    流程：解码令牌 -> 校验 `type=="access"`（否则 401）->
    还原 `UserContext`（id/username/role/position/tasks），供 profile 注入使用。
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")
    return UserContext(
        id=int(payload["sub"]),
        username=payload["username"],
        role=payload["role"],
        position=payload.get("position", ""),
        tasks=payload.get("tasks", []),
    )


# ---------------------------------------------------------------------------
# Section 4: require_role 依赖工厂（Task 3.6）
# ---------------------------------------------------------------------------


def require_role(*roles: str):
    """角色限定依赖工厂：返回一个 FastAPI 依赖以按角色门控路由。

    用法：在路由上声明 `dependencies=[Depends(require_role("admin"))]`。
    内部复用 `get_current_user` 还原已认证用户上下文：
    - 当 `user.role` 不在允许的 `roles` 中时抛出 HTTP 403（Insufficient role）；
    - 否则原样返回该 `UserContext`，供路由按需注入。
    """

    async def _dep(user: UserContext = Depends(get_current_user)) -> UserContext:
        # 角色不匹配则拒绝访问；命中任一允许角色即放行。
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep
