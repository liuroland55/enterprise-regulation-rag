"""SQLModel 表模型定义。

本模块定义账户系统所需的三张 SQLite 表：
- `User`：员工/管理员账户（密码以 bcrypt 哈希存储，绝不存明文）；
- `RefreshToken`：持久化的 refresh token，用于支持吊销；
- `QueryHistory`：按 `user_id` 隔离的提问历史（`question` 仅存原始问题，绝非增强后的查询）。

字段命名保持英文；注释使用中文，遵循项目约定。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """用户账户表。"""

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)  # 用户名，唯一且建立索引
    password_hash: str  # bcrypt 哈希，绝不存储明文
    role: str = Field(default="employee")  # 角色："admin" | "employee"
    position: str = Field(default="")  # 职位
    tasks: str = Field(default="[]")  # 任务，JSON 编码的字符串列表
    is_active: bool = Field(default=True)  # 账户是否启用
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 创建时间
    updated_at: datetime = Field(default_factory=datetime.utcnow)  # 更新时间


class RefreshToken(SQLModel, table=True):
    """Refresh token 表，持久化以支持吊销。"""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)  # 所属用户外键
    token: str = Field(index=True, unique=True)  # token 值，唯一且建立索引
    expires_at: datetime  # 过期时间
    revoked: bool = Field(default=False)  # 是否已吊销


class QueryHistory(SQLModel, table=True):
    """提问历史表，按用户隔离（私有）。"""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)  # 历史按用户隔离（私有）
    question: str  # 员工原始问题（绝非增强后的查询）
    answer: str  # RAG 答案文本
    grade: str  # "YES" | "NO"
    iterations: int  # 自我修正迭代次数
    success: bool  # RAG 是否成功
    source_count: int = Field(default=0)  # 可选：依据条数；不存向量/分块原文
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 创建时间
