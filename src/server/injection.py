"""职位感知查询增强（position-aware retrieval）。

策略：在 API 层对问题做"查询加权增强"。原始问题始终作为主导子句保留，
职位（position）与任务（tasks）作为检索引导上下文附加，借助语义相似度
加权相关公司条例。该方式不触碰 RAG 核心：`retrieve_node` 会以（增强后的）
`question` 字符串初始化 `current_query`，因此仅改写问题文本即可引导检索。

对应需求：Requirement 8.2 / 8.3 / 8.4 / 8.5 / 8.6。
"""

from src.server.schemas import UserProfile


def build_augmented_query(
    profile: UserProfile, question: str, lang: str | None = None
) -> str:
    """根据用户档案（职位 + 任务）对问题做查询增强，实现职位感知检索。

    设计要点：
    - 原始问题作为主导子句保留，保证不偏离用户真实意图（Req 8.2）。
    - 职位/任务作为"检索引导上下文"附加，借助语义相似度加权相关条例。
    - 空档案（空 position 且空 tasks）仍包含原始问题（Req 8.4）。
    - 过滤空白/whitespace-only 的 task 条目（Req 8.5）。
    - 纯函数：确定性、无副作用、无 I/O，便于属性测试（Req 8.3）。
    - 语言指令（可选）：当 lang 为 "zh"/"en" 时，在末尾追加一条语言指令，
      使回答语言跟随 UI 语言；其它值或 None 时不追加（向后兼容）。该指令
      追加在既有检索引导句之后，不替换它。

    增强查询稍后由 Query_Service 原样传给未改动的 RAG 核心（Req 8.6）。

    参数：
        profile: 用户画像（职位 + 任务）。
        question: 员工的原始问题。
        lang: 期望的回答语言（"en" | "zh"）；其它值或 None 时不注入语言指令。

    返回：
        增强后的查询字符串；始终逐字包含 trim 后的原始问题。
    """
    # trim 后的原始问题始终逐字出现在输出中（主导子句）
    question = question.strip()
    parts: list[str] = []

    position = (profile.position or "").strip()
    # 过滤空字符串与仅含空白的 task 条目
    tasks = [t.strip() for t in (profile.tasks or []) if t and t.strip()]

    # 仅当档案信息存在时才注入，避免污染空档案用户的查询
    if position:
        parts.append(f"[岗位背景] 提问者职位为：{position}。")
    if tasks:
        parts.append(f"[职责背景] 其主要任务包括：{'、'.join(tasks)}。")

    parts.append(f"[问题] {question}")
    parts.append("请优先检索与上述岗位职责最相关的公司条例并据此作答。")

    # 语言指令：追加在既有检索引导句之后（不替换），其它值/None 保持向后兼容
    if lang == "zh":
        parts.append("请用中文回答。")
    elif lang == "en":
        parts.append("Please answer in English.")

    return "\n".join(parts)
