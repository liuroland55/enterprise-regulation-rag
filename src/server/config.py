"""侧车服务级配置模块（Server-level configuration）。

本模块为新增的 FastAPI 侧车服务提供独立于 RAG 核心的服务级配置，
与现有 `src/config/settings.py` 的 pydantic-settings 风格保持一致，
并从项目根目录的 `.env` 文件 / 环境变量加载。

职责：
- 从环境变量 / 本地安全文件加载 `JWT_SECRET`（HS256 签名密钥），**禁止硬编码**；
- 定义 access / refresh 令牌过期时间；
- 定义侧车绑定地址（仅回环 `127.0.0.1:8756`）；
- 读取 `BOOTSTRAP_ADMIN_USER` / `BOOTSTRAP_ADMIN_PASSWORD`（首次启动播种管理员）；
- 读取模型运行模式 `MODE`（CLOUD / LOCAL）。

注意：本模块为**新增的独立配置**，不会修改 RAG 核心（`src/config/settings.py`）。

_Requirements: 1.2, 17.1, 17.2_
"""

import logging
import secrets
from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class ServerSettings(BaseSettings):
    """FastAPI 侧车服务的集中式配置。

    所有值均通过环境变量 / `.env` 文件加载（与 RAG 核心保持一致的加载方式）。
    其中 `JWT_SECRET` 严禁硬编码：生产环境必须显式提供，否则启动即报错。
    """

    model_config = SettingsConfigDict(
        # 同时读取 .env（共享项，如 MODE）与 .env.server（side-car 专属项）。
        # 关键：side-car 专属键（JWT_SECRET 等）放在 .env.server，避免污染 RAG 核心
        # 的 .env —— 后者的 Settings 禁止额外键（extra="forbid"），混入会导致核心初始化失败。
        # 后出现的文件优先级更高。
        env_file=(".env", ".env.server"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        # 忽略 .env 中属于 RAG 核心的其它变量，避免校验报错
        extra="ignore",
    )

    # --- 运行环境 ---
    # 用于区分生产 / 开发：生产环境下缺失 JWT_SECRET 将直接报错
    ENVIRONMENT: Literal["development", "production"] = "development"

    # --- JWT 鉴权配置 ---
    # HS256 签名密钥：必须来自环境变量 / 安全文件，禁止硬编码默认值。
    # 开发环境若缺失，将生成临时随机密钥并告警（重启后失效）。
    JWT_SECRET: Optional[str] = None
    # 签名算法固定为 HS256
    JWT_ALGORITHM: str = "HS256"
    # access token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # refresh token 过期时间（天）
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- 侧车绑定地址（仅回环，禁止对外暴露） ---
    SIDECAR_HOST: str = "127.0.0.1"
    SIDECAR_PORT: int = 8756

    # --- 初始管理员播种（首次启动从 env 读取） ---
    BOOTSTRAP_ADMIN_USER: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # --- 账户数据库（SQLite） ---
    SQLITE_URL: str = "sqlite:///./accounts.db"

    # --- 模型运行模式（与 RAG 核心同源，读取同一 .env 变量） ---
    MODE: Literal["CLOUD", "LOCAL"] = "CLOUD"

    # --- 云端密钥（与 RAG 核心同源，仅用于侧车侧的"就绪/缺失"提示） ---
    # 侧车不直接调用 OpenAI；此字段仅供 /system/mode 判断切换到 CLOUD 前是否已配置密钥。
    OPENAI_API_KEY: str = ""

    @model_validator(mode="after")
    def _ensure_jwt_secret(self) -> "ServerSettings":
        """确保 JWT_SECRET 可用且未被硬编码。

        - 生产环境：缺失 `JWT_SECRET` 直接抛错，强制运维显式配置；
        - 开发环境：缺失时生成临时随机密钥并发出告警（仅供本地调试，重启失效）。
        """
        if not self.JWT_SECRET or not self.JWT_SECRET.strip():
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    "JWT_SECRET is required in production. "
                    "Set it via the JWT_SECRET environment variable or a secure local file. "
                    "Hard-coded secrets are forbidden."
                )
            # 开发环境：生成临时密钥，避免硬编码同时保证可启动
            generated = secrets.token_urlsafe(48)
            logger.warning(
                "JWT_SECRET is not set; generated an EPHEMERAL development secret. "
                "Tokens will be invalidated on restart. "
                "Set JWT_SECRET in your environment for stable sessions."
            )
            # 绕过验证赋值（model_validator(after) 阶段对象已构建）
            object.__setattr__(self, "JWT_SECRET", generated)
        return self

    @property
    def bind_address(self) -> str:
        """返回侧车绑定地址字符串，例如 `127.0.0.1:8756`。"""
        return f"{self.SIDECAR_HOST}:{self.SIDECAR_PORT}"


# 全局唯一的服务级配置实例（供 security / db / main 等模块导入使用）
settings = ServerSettings()


__all__ = ["ServerSettings", "settings"]
