"""Pydantic DTO（请求 / 响应数据传输对象）。

本模块定义 side-car 服务对外的所有数据契约（DTO），与设计文档
`PART 2 — Low-Level Design / Core Interfaces / Types` 保持一致：

- `UserProfile` / `UserContext`：用户画像与已认证用户上下文；
- `AskRequest`（含 question 去空白后非空校验）/ `SourceItem` / `AskResponse`：问答契约；
- `HistoryItem` / `HistoryListResponse`：查询历史契约；
- `TokenResponse`：登录令牌契约；
- `UserCreate` / `UserUpdate` / `UserOut`：管理后台用户 CRUD 契约。

约定：代码与字段名使用英文；注释默认中文。使用 Pydantic v2 风格。
"""

from datetime import datetime

from pydantic import BaseModel, field_validator


# --------------------------------------------------------------------------- #
# 用户画像 / 上下文
# --------------------------------------------------------------------------- #
class UserProfile(BaseModel):
    """用于查询增强的用户画像：职位（position）+ 任务（tasks）。"""

    position: str
    tasks: list[str]


class UserContext(BaseModel):
    """从已校验的 access token 声明中还原的已认证用户上下文。"""

    id: int
    username: str
    role: str  # "admin" | "employee"
    position: str
    tasks: list[str]


# --------------------------------------------------------------------------- #
# 问答（/ask）契约
# --------------------------------------------------------------------------- #
class TempDoc(BaseModel):
    """单个临时文件（前端在客户端读取文本后随请求体上送）。

    仅用于本次/接下来的提问作为一次性上下文，绝不入库（不写入持久化向量库）。
    """

    name: str  # 文件名（作为检索来源 source 标识）
    content: str  # 文件文本内容


class AskRequest(BaseModel):
    """提问请求体。

    校验规则：`question` 去除首尾空白后不能为空（支撑 Requirement 9.2 /
    Property 9），否则触发 Pydantic 校验错误（路由层映射为 HTTP 422）。

    可选检索控制字段（附加式，向后兼容）：
    - `kb_sources`：勾选的知识库来源（文件名）列表，用于限定检索范围；
    - `temp_context`：临时文件列表，作为一次性上下文（优先级最高）。
    - `lang`：期望的回答语言（"en" | "zh"）；其它值或 None 时不注入语言指令（向后兼容）。
    """

    question: str
    return_context: bool = True
    kb_sources: list[str] | None = None
    temp_context: list[TempDoc] | None = None
    lang: str | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # 问题去除首尾空白后不能为空
        if not v or not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


class SourceItem(BaseModel):
    """单条溯源依据：原文片段（content）与来源标识（source）。"""

    content: str
    source: str


class AskResponse(BaseModel):
    """问答响应体。

    字段映射自 RAG_Core 返回结果；`success=false` 时仍以 HTTP 200 返回，
    并在 `answer` 中携带错误文本（见 Requirement 9.3）。
    """

    answer: str
    grade: str
    reason: str
    iterations: int
    success: bool
    sources: list[SourceItem] = []


# --------------------------------------------------------------------------- #
# 查询历史契约
# --------------------------------------------------------------------------- #
class HistoryItem(BaseModel):
    """单条查询历史；`question` 为员工的原始问题（绝非增强后的查询）。

    `user_id` / `username` 为可选审计字段：仅在管理员审计端点（``GET /admin/history``）
    填充以标识提问者身份；按用户隔离的 ``/history`` 与 ``/history/{id}`` 端点保持为 None，
    因此不会暴露提问者身份（保持向后兼容与隐私隔离）。
    """

    id: int
    question: str
    answer: str
    grade: str
    iterations: int
    success: bool
    source_count: int = 0
    created_at: datetime
    user_id: int | None = None  # 提问者 id（仅管理员审计端点填充）
    username: str | None = None  # 提问者用户名（仅管理员审计端点填充）


class HistoryListResponse(BaseModel):
    """分页查询历史列表响应。"""

    items: list[HistoryItem]
    page: int
    page_size: int
    total: int


# --------------------------------------------------------------------------- #
# 认证令牌契约
# --------------------------------------------------------------------------- #
class TokenResponse(BaseModel):
    """登录成功返回的双令牌与角色。"""

    access_token: str
    refresh_token: str
    role: str


# --------------------------------------------------------------------------- #
# 管理后台用户 CRUD 契约
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    """管理员创建用户请求体；`tasks` 为字符串列表（由模型层 JSON 编码存储）。"""

    username: str
    password: str
    role: str
    position: str
    tasks: list[str]


# --------------------------------------------------------------------------- #
# 自助注册契约
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    """公开自助注册请求体。

    安全约定：**绝不接受客户端指定角色** —— 自助注册一律创建为 `employee`，
    管理员账户只能由现有管理员在后台创建或提升（见 admin 路由）。
    `position` / `tasks` 为可选画像信息，缺省为空。

    校验规则：`username` / `password` 去除首尾空白后不能为空（路由层另行强制密码策略）。
    """

    username: str
    password: str
    position: str = ""
    tasks: list[str] = []

    @field_validator("username", "password")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # 用户名 / 密码去除首尾空白后不能为空
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip() if isinstance(v, str) else v


# --------------------------------------------------------------------------- #
# 运行模式（LOCAL / CLOUD）切换契约
# --------------------------------------------------------------------------- #
class ModeInfo(BaseModel):
    """当前运行模式信息（`GET /system/mode`）。

    - `mode`：当前生效模式（CLOUD / LOCAL，取自服务级配置）；
    - `cloud_ready`：CLOUD 模式所需的 `OPENAI_API_KEY` 是否已配置；
    - `persist_dir`：当前向量库持久化目录（不同模式建议使用不同目录以避免嵌入维度冲突）。
    """

    mode: str
    cloud_ready: bool
    persist_dir: str


class ModeUpdateRequest(BaseModel):
    """切换运行模式请求体（`POST /system/mode`）。"""

    mode: str

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        # 仅接受 CLOUD / LOCAL（大小写不敏感，归一化为大写）
        normalized = (v or "").strip().upper()
        if normalized not in {"CLOUD", "LOCAL"}:
            raise ValueError("mode must be 'CLOUD' or 'LOCAL'")
        return normalized


class ModeUpdateResult(BaseModel):
    """切换运行模式响应体。

    - `mode`：写入后的目标模式；
    - `restart_required`：是否需要重启侧车才能生效（恒为 True：RAG 核心在启动期初始化）；
    - `warning`：非阻断性提示（如切到 CLOUD 但缺少 `OPENAI_API_KEY`），无则为 None。
    """

    mode: str
    restart_required: bool = True
    warning: str | None = None


class UserUpdate(BaseModel):
    """管理员更新用户请求体；所有字段可选，仅更新提供的字段。"""

    position: str | None = None
    tasks: list[str] | None = None
    role: str | None = None


class UserOut(BaseModel):
    """对外暴露的用户视图（绝不包含 password_hash）。"""

    id: int
    username: str
    role: str
    position: str
    tasks: list[str]
    is_active: bool
    created_at: datetime
