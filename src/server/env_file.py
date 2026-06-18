"""`.env` 文件安全读改写工具（仅供侧车层使用）。

用于在不重启进程的前提下，把运行配置（如 ``MODE`` / ``CHROMA_PERSIST_DIR``）
持久化回项目根目录的 ``.env``，供下次启动时被 RAG 核心读取。

设计要点：
- **逐行保留**：仅替换匹配 ``KEY=`` 的那一行，其余行（含注释、空行、顺序）原样保留；
  不存在的键追加到文件末尾。避免破坏用户手写的注释与排版。
- **仅操作传入路径**：模式切换只写 RAG 核心的 ``.env``，绝不触碰 ``.env.server``
  （侧车专属密钥），二者职责分离。
- **容错**：目标文件不存在时按"全部追加"处理；写入使用 UTF-8。

约定：代码 / API 名称使用英文；注释使用中文。本模块不修改 RAG 核心。
"""

from __future__ import annotations

import os
import re

__all__ = ["set_env_vars"]


def set_env_vars(path: str, updates: dict[str, str]) -> None:
    """把 ``updates`` 中的键值写入 ``path`` 指向的 .env 文件（就地更新或追加）。

    Args:
        path: 目标 .env 文件路径（如项目根目录的 ``.env``）。
        updates: 待写入的 ``{KEY: VALUE}`` 映射；已存在的键替换其行，否则追加。

    行为：
    - 保留文件中其余行（注释 / 空行 / 未涉及的键）及其顺序；
    - 同名键仅替换**首个**匹配行（与 dotenv "先出现者生效" 的常见语义一致），
      其余重复行保持不变；
    - 文件不存在时，等价于创建并写入全部 ``updates``。
    """
    # 读取既有行（保留行尾结构由我们统一处理；不存在则视为空文件）
    lines: list[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    remaining = dict(updates)  # 尚未写入（用于决定哪些需要追加）
    # 形如 KEY= 的行匹配：允许 KEY 前有空白；按当前主流 .env 不支持行内键空格
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        for key in list(remaining.keys()):
            if re.match(rf"^{re.escape(key)}\s*=", stripped):
                lines[idx] = f"{key}={remaining.pop(key)}"
                break  # 一行最多匹配一个键

    # 仍未写入的键：追加到文件末尾（保持稳定的插入顺序）
    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    # 统一以 \n 结尾写回（末尾补一个换行，符合 POSIX 文本文件惯例）
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
