"""数据库层（SQLite via SQLModel）。

本模块负责账户系统的持久化基础设施：
- `engine`：基于 `settings.SQLITE_URL` 创建的 SQLModel/SQLAlchemy 引擎
  （SQLite 需设置 `check_same_thread=False` 以支持 FastAPI 多线程访问）；
- `init_db()`：依据模型元数据创建所有表（幂等）；
- `get_session()`：FastAPI 依赖，按请求提供数据库会话；
- `seed_admin()`：首次启动时，仅在不存在任何 admin 账户时，
  从 `settings.BOOTSTRAP_ADMIN_USER` / `BOOTSTRAP_ADMIN_PASSWORD` 播种单一 admin（幂等）。

字段/接口命名保持英文；注释使用中文，遵循项目约定。

_Requirements: 7.1, 7.2_
"""

import logging
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine, select

from src.server.config import settings

# 导入模型以确保其在 SQLModel.metadata 中注册（建表所需）
from src.server.models import QueryHistory, RefreshToken, User  # noqa: F401

logger = logging.getLogger(__name__)


# SQLite 引擎：check_same_thread=False 允许跨线程共享连接，
# 这是在 FastAPI（多线程）中使用 SQLite 的标准做法。
engine = create_engine(
    settings.SQLITE_URL,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """创建所有表（幂等）。

    依据已注册的 SQLModel 元数据创建表；若表已存在则不重复创建。
    """
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：按请求提供数据库会话并在结束后自动关闭。"""
    with Session(engine) as session:
        yield session


def seed_admin() -> None:
    """首次启动时播种初始 admin 账户（仅当不存在任何 admin 时）。

    设计要点：
    - 幂等：仅当数据库中不存在任何 `role == "admin"` 的用户时才创建；
    - 安全：密码必须经 bcrypt 哈希后存储，绝不写入明文；
    - 健壮：若 `BOOTSTRAP_ADMIN_PASSWORD` 为空，则记录告警并跳过播种，
      绝不创建空密码的 admin 账户。

    注：`hash_password` 在此处**延迟导入**，以避免模块加载期的循环依赖
    （security 模块可能反向依赖 db / config）。
    """
    # 空密码保护：不允许播种空密码 admin
    if not settings.BOOTSTRAP_ADMIN_PASSWORD or not settings.BOOTSTRAP_ADMIN_PASSWORD.strip():
        logger.warning(
            "BOOTSTRAP_ADMIN_PASSWORD is empty; skipping admin seeding. "
            "Set BOOTSTRAP_ADMIN_PASSWORD to enable initial admin bootstrap."
        )
        return

    # 延迟导入以规避循环依赖（security 由并行任务实现）
    from src.server.security import hash_password

    with Session(engine) as session:
        # 幂等检查：已存在任意 admin 则不再播种（满足 Requirement 7.2）
        existing_admin = session.exec(
            select(User).where(User.role == "admin")
        ).first()
        if existing_admin is not None:
            return

        # 不存在 admin：从配置播种单一 admin（满足 Requirement 7.1）
        admin = User(
            username=settings.BOOTSTRAP_ADMIN_USER,
            password_hash=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
            role="admin",
        )
        session.add(admin)
        session.commit()
        logger.info(
            "Seeded initial admin account '%s' from bootstrap configuration.",
            settings.BOOTSTRAP_ADMIN_USER,
        )


__all__ = ["engine", "init_db", "get_session", "seed_admin"]
