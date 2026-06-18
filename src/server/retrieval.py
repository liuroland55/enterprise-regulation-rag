"""检索控制模块（Retrieval Control）。

本模块在**不修改 RAG 核心**（`src/api/rag_api.py`、`src/graph/*.py`、
`src/config/settings.py`、`src/ingestion/loader.py`）的前提下，为侧车服务提供
三类“检索范围控制”能力，所有行为均为附加式（additive）：

- `ScopedVectorStore`：包装真实向量库，按 `source`（文件名）元数据过滤检索，
  实现“勾选知识库后回答仅依据所选范围”；
- `build_temp_vector_store`：用请求体中的临时文本构建**内存态（ephemeral）**
  Chroma，仅服务于本次/接下来的提问，不落盘、不入库；
- `use_vector_store`：在全局锁保护下临时替换 `src.graph.nodes.vector_store`，
  请求结束后恢复，串行化被替换的请求（桌面单用户场景可接受）；
- `resolve_request_vector_store`：按优先级（临时文件 > 勾选范围 > 全部）解析
  本次请求应使用的向量库对象。

设计约束：
- 全部采用**惰性导入**，避免导入本模块时触发 RAG 核心 / embeddings / Chroma 等副作用；
- 通过 `RAG2API._instance.vector_store` 获取运行中的 live store，确保与检索同源。
"""

from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

# 全局锁：序列化“替换全局向量库”的请求，避免并发请求互相污染
# （桌面单用户场景下，串行化是可接受的简单且安全的策略）。
_vs_lock = Lock()


class ScopedVectorStore:
    """按来源（source）过滤检索的向量库包装器。

    包装一个真实向量库实例，并限定其 `similarity_search` 仅在给定的
    `sources`（文件名列表）范围内检索。除 `similarity_search` 外的属性访问
    一律委托给被包装的真实向量库，使其在其它方面与原 store 行为一致。
    """

    def __init__(self, store, sources):
        # 被包装的真实向量库（如 langchain_chroma.Chroma）
        self._store = store
        # 允许检索的来源（文件名）列表；规范化为去重后的列表
        self._sources = list(sources or [])

    def similarity_search(self, query, k=4, **kwargs):
        """在限定来源范围内做相似度检索。

        根据允许的 `sources` 构造 Chroma `where` 过滤器：
        - 多个来源：``{"source": {"$in": [...]}}``；
        - 单个来源：``{"source": sources[0]}``；
        - 无来源（空列表）：不附加过滤，等价于全量检索。
        若调用方已显式传入 ``filter``，则尊重其值不做覆盖。
        """
        # 仅在调用方未显式指定 filter 时，注入基于 source 的范围过滤
        if "filter" not in kwargs or kwargs.get("filter") is None:
            if len(self._sources) > 1:
                kwargs["filter"] = {"source": {"$in": self._sources}}
            elif len(self._sources) == 1:
                kwargs["filter"] = {"source": self._sources[0]}
            # 空列表：不附加过滤（保持全量检索语义）
        return self._store.similarity_search(query=query, k=k, **kwargs)

    def __getattr__(self, name):
        # 其它属性 / 方法一律委托给被包装的真实向量库。
        # 注意：__getattr__ 仅在常规属性查找失败时触发，
        # 故不会拦截本类已显式定义的 similarity_search / _store / _sources。
        return getattr(self._store, name)


def build_temp_vector_store(temp_docs):
    """用临时文本构建**内存态** Chroma，仅供本次请求使用。

    参数：
        temp_docs: ``[{"name": str, "content": str}, ...]`` 形式的列表。

    流程：
    1. 将每条记录转换为 `langchain_core.documents.Document`
       （`metadata.source` = name），跳过内容为空者；
    2. 经 loader 的 `split_documents` 切块；
    3. 通过 `Chroma.from_documents(..., collection_name="temp_<uuid>")` 创建
       **不带 persist_directory 的内存态** Chroma（不写入 ./chroma_db）。

    若无有效内容，则返回一个仍然可用的空内存态 Chroma（检索返回空）。
    """
    # 惰性导入，避免模块加载期触发 embeddings / Chroma 初始化等副作用
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from src.config.settings import get_embeddings
    from src.ingestion.loader import split_documents

    # 1) 构造 Document（仅保留非空内容），source 记为文件名
    docs = []
    for item in temp_docs or []:
        name = (item or {}).get("name", "temp")
        content = (item or {}).get("content", "")
        if content and content.strip():
            docs.append(Document(page_content=content, metadata={"source": name}))

    # 唯一集合名，确保多请求间相互隔离；不传 persist_directory → 内存态
    collection_name = f"temp_{uuid4().hex}"
    embedding = get_embeddings()

    if not docs:
        # 无有效内容：返回空的内存态集合，检索将返回空结果（优雅降级）
        return Chroma(collection_name=collection_name, embedding_function=embedding)

    # 2) 切块；3) 创建内存态向量库
    chunks = split_documents(docs)
    if not chunks:
        return Chroma(collection_name=collection_name, embedding_function=embedding)

    return Chroma.from_documents(
        documents=chunks,
        embedding=embedding,
        collection_name=collection_name,
    )


@contextmanager
def use_vector_store(vs):
    """在全局锁保护下临时替换 `src.graph.nodes.vector_store`。

    进入时记录原始全局向量库并替换为 `vs`，退出时（无论成功或异常）在
    finally 中恢复原值，确保不会污染后续请求。整个上下文期间持有 `_vs_lock`，
    从而串行化被替换的请求（桌面单用户可接受）。
    """
    # 惰性导入 nodes 模块，避免导入本模块时触发 RAG 核心副作用
    import src.graph.nodes as nodes_module

    with _vs_lock:
        original = nodes_module.vector_store
        nodes_module.vector_store = vs
        try:
            yield
        finally:
            # 无论如何都恢复原始全局向量库
            nodes_module.vector_store = original


def resolve_request_vector_store(kb_sources, temp_docs):
    """解析本次请求应使用的向量库对象（按优先级）。

    优先级：**临时文件 > 勾选范围 > 全部**。
    - `temp_docs` 非空 → 返回 `build_temp_vector_store(temp_docs)`（仅依据临时文件）；
    - 否则 `kb_sources` 非空 → 返回 `ScopedVectorStore(live_store, kb_sources)`；
    - 否则 → 返回 None（表示沿用现有全局向量库，不做替换 = 检索全部）。

    其中 live_store 取自运行中的 `RAG2API._instance.vector_store`；
    若单例尚未初始化（如离线脚本），则范围过滤无从依附，返回 None。
    """
    # 1) 临时文件优先：构建内存态临时库
    if temp_docs:
        return build_temp_vector_store(temp_docs)

    # 2) 勾选范围：包装 live store 并按 source 过滤
    if kb_sources:
        live_store = _get_live_vector_store()
        if live_store is not None:
            return ScopedVectorStore(live_store, kb_sources)
        # 没有可依附的 live store：退回全量（None）
        return None

    # 3) 既未附加临时文件也未勾选范围：沿用全局库（不替换）
    return None


def _get_live_vector_store():
    """获取运行中的 live 向量库（`RAG2API._instance.vector_store`）。

    采用惰性导入；单例不存在或解析失败时返回 None（调用方据此退回全量检索）。
    """
    try:
        from src.api.rag_api import RAG2API

        inst = getattr(RAG2API, "_instance", None)
        return getattr(inst, "vector_store", None) if inst is not None else None
    except Exception:  # noqa: BLE001 - 解析失败时安全返回 None
        return None


__all__ = [
    "ScopedVectorStore",
    "build_temp_vector_store",
    "use_vector_store",
    "resolve_request_vector_store",
]
