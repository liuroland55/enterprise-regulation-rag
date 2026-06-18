"""知识库管理路由（KB Router）。

实现 Component 5（KB Router）与 Flow 3（管理员知识库上传），在不修改 RAG 核心 /
ingestion loader 的前提下，复用现有摄取逻辑完成文档的入库、列举与删除：

- `POST /kb/upload`（仅 admin）：校验扩展名 ∈ Supported_Extension（.txt/.md/.rst/.log）；
  不支持 -> HTTP 415；将文件保存到 ./data；复用
  `load_documents_from_directory` + `split_documents` + `get_vector_store().add_documents`
  完成向量化；返回 `{filename, chunks_added}`。
- `GET /kb/list`（任意已认证用户）：枚举 ./data 中受支持的文件并返回基础元数据。
- `DELETE /kb/{doc_id}`（仅 admin）：`doc_id` 即文件名，删除 ./data 中对应源文件。

设计要点：
- **零核心改动**：不修改 `src/ingestion/loader.py` 与 RAG 核心；仅复用其导出函数。
- **延迟导入**：loader / get_vector_store 在各 handler 内部延迟导入，避免模块加载期触发
  embeddings / Chroma 初始化（带来昂贵副作用或对外部模型的依赖）。
- **路径穿越防护**：上传 / 删除一律对文件名取 `os.path.basename`，拒绝绝对路径与 `..`。
- **Chroma 删除说明**：langchain_chroma 的删除接口以 id 为单位，按来源（source）整体清理
  并非平凡操作，故本路由对“从向量库移除”采取**尽力而为 / 超出范围**策略——优先删除
  ./data 中的源文件，并提示需要重建索引（re-index）后向量层才会完全一致。

_Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.server.security import get_current_user, require_role
# 受支持扩展名以 extract 模块为权威来源：在 loader 的纯文本集合之上，
# 额外支持富文本（.pdf/.docx）。注意：.doc（旧版二进制 Word）有意不在其中。
from src.server.extract import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# 知识库源文件目录（与 RAG 核心约定一致：默认 ./data）
DATA_DIR = "./data"

router = APIRouter(prefix="/kb", tags=["kb"])


# --------------------------------------------------------------------------- #
# 响应 DTO（仅 KB 路由使用，故就近定义；字段名英文，注释中文）
# --------------------------------------------------------------------------- #
class UploadResponse(BaseModel):
    """上传成功响应：文件名与本次新增的分块（chunk）数量。"""

    filename: str
    chunks_added: int


class KBEntry(BaseModel):
    """单条知识库条目（来源于 ./data 中受支持的文件）及其基础元数据。"""

    doc_id: str  # 文档标识：即文件名（与删除接口的 path 参数一致）
    filename: str  # 文件名
    filetype: str  # 扩展名（小写，含点，如 ".md"）
    size: int  # 文件字节大小
    modified_at: datetime  # 最近修改时间


class KBListResponse(BaseModel):
    """知识库条目列表响应。"""

    items: list[KBEntry]
    total: int


class DeleteResponse(BaseModel):
    """删除响应：返回被删除的文件名，并附带向量层一致性提示（re-index caveat）。"""

    doc_id: str
    deleted: bool
    note: str


class ReindexResponse(BaseModel):
    """重建索引响应：本次处理的文件数、新增分块数，以及是否清空了旧向量。"""

    files: int  # 从 ./data 加载的文件数量
    chunks_added: int  # 本次写入向量库的分块数量
    cleared: bool  # 是否成功清空旧向量（best-effort，失败为 False）


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _safe_basename(filename: str) -> str:
    """将任意文件名归一化为纯 basename，杜绝路径穿越。

    - 取 `os.path.basename`（同时处理 Windows 反斜杠分隔）；
    - 文件名为空、或仍包含分隔符 / `..` 时拒绝（HTTP 400）。
    """
    if not filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filename must not be empty")
    # 兼容 Windows 反斜杠：先统一替换再取 basename
    candidate = os.path.basename(filename.replace("\\", "/"))
    if not candidate or candidate in {".", ".."} or "/" in candidate or "\\" in candidate:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")
    return candidate


def _resolve_live_vector_store(fallback_get_vector_store):
    """返回当前应写入的向量库实例（关键修复）。

    优先使用**运行中的 `RAG2API` 单例**所持有的 `vector_store`——它与检索时
    `nodes.vector_store` 为同一对象，因此上传文档后当前检索可**立即**看到新内容；
    若单例尚未初始化（如离线脚本 / 单元测试场景），则回退到 loader 的
    `get_vector_store()`（仅写盘，不保证当前进程的检索器即时可见）。

    采用惰性导入，避免模块加载期触发 RAG 核心的外部依赖初始化。
    """
    try:
        from src.api.rag_api import RAG2API

        inst = getattr(RAG2API, "_instance", None)
        live = getattr(inst, "vector_store", None) if inst is not None else None
        if live is not None:
            return live
    except Exception:  # noqa: BLE001 - 解析失败时安全回退，不影响上传主流程
        pass
    return fallback_get_vector_store()


def _delete_existing_chunks_by_source(vector_store, source: str) -> None:
    """删除向量库中 ``metadata.source == source`` 的全部旧 chunk（幂等上传的关键）。

    优先用 ``vector_store.get(where={"source": source})`` 精确取回 ids；若底层不支持
    ``where`` 过滤，则回退为扫描 ``vector_store.get()`` 的全部 metadatas 自行匹配。
    取得 ids 后调用 ``vector_store.delete(ids=...)`` 删除。

    本函数**尽力而为**：桩替身（fake store）可能缺少 ``get`` / ``delete``，
    或底层调用失败——一律以 try/except 兜底并记录日志，绝不影响上传主流程。
    """
    try:
        ids_to_delete: list = []
        # 1) 优先尝试基于 metadata 的精确过滤
        try:
            filtered = vector_store.get(where={"source": source})
            ids_to_delete = (filtered or {}).get("ids") or []
        except Exception:  # noqa: BLE001 - where 过滤不被支持：回退为全量扫描
            data = vector_store.get()
            ids = (data or {}).get("ids") or []
            metadatas = (data or {}).get("metadatas") or []
            for idx, meta in enumerate(metadatas):
                if (meta or {}).get("source") == source and idx < len(ids):
                    ids_to_delete.append(ids[idx])

        if ids_to_delete:
            vector_store.delete(ids=ids_to_delete)
    except Exception:  # noqa: BLE001 - 桩替身缺少 get/delete 或删除失败：跳过即可
        logger.warning(
            "Idempotent upload: failed to delete existing chunks for source '%s'; "
            "proceeding to add (store may not support get/delete).",
            source,
            exc_info=True,
        )


# --------------------------------------------------------------------------- #
# POST /kb/upload —— 仅 admin（Requirements 13.1, 13.2, 13.3, 13.6）
# --------------------------------------------------------------------------- #
@router.post(
    "/upload",
    response_model=UploadResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    """上传并向量化一篇知识库文档。

    流程：
    1. 校验扩展名 ∈ SUPPORTED_EXTENSIONS（含 .pdf/.docx），不支持 -> HTTP 415；
       对旧版 .doc 返回 415 并附带“请转换为 .docx 或 PDF”的提示信息；
    2. 将上传内容以 basename 保存到 ./data（防路径穿越）；
    3. 经 `extract.extract_single(dest)` 抽取为单个 Document（PDF/DOCX 走富文本抽取，
       纯文本走 utf-8 读取）；若抽取失败 / 内容为空，返回 chunks_added=0；
    4. 幂等：写入前先删除该来源（同名文件）已有的旧 chunk；
    5. `loader.split_documents([doc])` 切块后写入“运行中的 live 向量库”（与检索同源）；
    6. 返回 `{filename, chunks_added}`。
    """
    # 归一化文件名并校验扩展名（在任何 I/O 之前完成，未支持的类型直接 415）
    filename = _safe_basename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()

    # 旧版 .doc：明确不支持，返回 415 并提示转换格式
    if ext == ".doc":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Legacy .doc is not supported; please convert to .docx or PDF.",
        )
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported extension: {ext or '(none)'}",
        )

    # 延迟导入：避免模块加载期触发 embeddings / Chroma 初始化等副作用
    from src.ingestion.loader import get_vector_store, split_documents

    from src.server import extract

    # 确保目标目录存在并保存文件（以二进制写入，原样落盘——PDF/DOCX 必须二进制保存）
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # 经 extract 抽取为单个 Document（富文本/纯文本统一入口）
    doc = extract.extract_single(dest)

    # 若文件不可读 / 内容为空，则视为新增 0 个分块
    if doc is None:
        logger.warning(
            "Uploaded file '%s' was saved but could not be extracted for vectorization.",
            filename,
        )
        return UploadResponse(filename=filename, chunks_added=0)

    chunks = split_documents([doc])
    if chunks:
        # 关键修复：写入“运行中的 RAG2API 单例”所持有的向量库（与检索同一对象），
        # 确保上传文档对当前检索立即可见；单例未初始化时回退到 get_vector_store()。
        vector_store = _resolve_live_vector_store(get_vector_store)
        # 幂等保证：写入前先删除该来源（同名文件）已有的旧 chunk，避免重复上传产生重复向量。
        _delete_existing_chunks_by_source(vector_store, filename)
        vector_store.add_documents(chunks)

    return UploadResponse(filename=filename, chunks_added=len(chunks))


# --------------------------------------------------------------------------- #
# GET /kb/list —— 任意已认证用户（Requirement 13.4）
# --------------------------------------------------------------------------- #
@router.get("/list", response_model=KBListResponse)
async def list_kb(_user=Depends(get_current_user)) -> KBListResponse:
    """列举知识库条目。

    保持简单：枚举 ./data 中扩展名受支持的文件，返回文件名 / 类型 / 大小 / 修改时间。
    任意持有有效 access token 的用户均可访问（无特定角色要求）。
    """
    items: list[KBEntry] = []

    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            path = os.path.join(DATA_DIR, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            stat = os.stat(path)
            items.append(
                KBEntry(
                    doc_id=name,
                    filename=name,
                    filetype=ext,
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                )
            )

    return KBListResponse(items=items, total=len(items))


# --------------------------------------------------------------------------- #
# POST /kb/reindex —— 仅 admin：从 ./data 重建持久化索引
# --------------------------------------------------------------------------- #
@router.post(
    "/reindex",
    response_model=ReindexResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def reindex() -> ReindexResponse:
    """从 ./data 重建持久化向量索引。

    流程：
    1. 经 `extract.load_documents_any(DATA_DIR)` 加载全部源文件（含 .pdf/.docx），
       再 `split_documents` 切块；
    2. 解析“运行中的 live 向量库”（与检索同源），先**尽力而为**清空已有向量
       （`live_vs.get()` 取 ids 后 `live_vs.delete(ids=...)`），以避免重复 reindex
       造成向量无限累积；若底层不支持删除则跳过并在响应中标记 `cleared=False`；
    3. 将新切块写入 live 向量库；
    4. 返回 `{files, chunks_added, cleared}`。

    本实现采用延迟导入并对每一步做异常兜底，保证健壮、不崩溃。
    """
    # 延迟导入：避免模块加载期触发 embeddings / Chroma 初始化等副作用
    from src.ingestion.loader import get_vector_store, split_documents

    from src.server import extract

    # 1) 经 extract 加载 ./data 中的全部受支持文档（含 .pdf/.docx）并切块
    docs = extract.load_documents_any(DATA_DIR)
    file_count = len(docs)
    chunks = split_documents(docs) if docs else []

    # 解析当前应写入的 live 向量库（与检索同源；未初始化时回退 get_vector_store）
    live_vs = _resolve_live_vector_store(get_vector_store)

    # 2) best-effort 清空旧向量：先取既有 ids，再删除
    cleared = False
    try:
        existing = live_vs.get()
        existing_ids = (existing or {}).get("ids") or []
        if existing_ids:
            live_vs.delete(ids=existing_ids)
            cleared = True
    except Exception:  # noqa: BLE001 - 删除不被支持或失败时跳过，仅追加新向量
        logger.warning("Reindex: clearing existing vectors not supported or failed; proceeding to add only.")
        cleared = False

    # 3) 写入新切块
    chunks_added = 0
    if chunks:
        try:
            live_vs.add_documents(chunks)
            chunks_added = len(chunks)
        except Exception:  # noqa: BLE001 - 写入失败时记录日志，返回 0 而非崩溃
            logger.exception("Reindex: failed to add documents to the vector store.")
            chunks_added = 0

    return ReindexResponse(files=file_count, chunks_added=chunks_added, cleared=cleared)


# --------------------------------------------------------------------------- #
# DELETE /kb/{doc_id} —— 仅 admin（Requirements 13.5, 13.6）
# --------------------------------------------------------------------------- #
@router.delete(
    "/{doc_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_kb(doc_id: str) -> DeleteResponse:
    """删除指定知识库条目（`doc_id` 即文件名）。

    行为：删除 ./data 中对应的源文件；文件不存在 -> HTTP 404。

    关于向量库（Chroma）一致性：
    - 从 Chroma 中按来源整体移除并非平凡操作（其删除以 id 为单位），
      故此处采取**尽力而为 / 超出范围**策略：仅删除源文件；
    - 之前已写入的向量在重建索引（re-index）前可能仍然存在，响应的 `note` 字段对此作出提示。
    """
    filename = _safe_basename(doc_id)
    path = os.path.join(DATA_DIR, filename)

    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document not found: {filename}")

    os.remove(path)

    return DeleteResponse(
        doc_id=filename,
        deleted=True,
        note=(
            "Source file removed from ./data. Existing vectors in the store are not "
            "deleted here (best-effort/out-of-scope); re-index to fully sync the vector store."
        ),
    )


__all__ = ["router", "SUPPORTED_EXTENSIONS", "DATA_DIR"]
