"""自动增量索引模块（Automatic Incremental Indexing）。

本模块在**不修改 RAG 核心**（`src/api/rag_api.py`、`src/graph/*.py`、
`src/config/settings.py`、`src/ingestion/loader.py`）的前提下，为侧车服务提供
对 ``./data`` 目录的**增量同步**与**文件系统监听**能力，所有行为均为附加式（additive）：

- `sync_data_folder(vector_store, data_dir)`：对比磁盘文件与向量库现状，按
  “来源是否存在 + 文本字符数（size）是否变化”判定 NEW / CHANGED / UNCHANGED /
  DELETED，仅对增量部分做删除 + 重新写入，避免全量重建与重复分块；
- `start_data_watcher(get_live_store)`：基于 `watchdog` 监听 ``./data`` 的增删改，
  带去抖（debounce）后惰性获取 live store 并触发一次增量同步；若未安装
  `watchdog` 或目录缺失，则记录 warning 并优雅返回 None（no-op）；
- `stop_data_watcher(observer)`：尽力而为地停止并 join 观察者。

设计约束：
- 全部采用**惰性导入**（loader / watchdog），避免导入本模块时触发 RAG 核心 /
  embeddings / Chroma / watchdog 等副作用；
- 所有向量库变更（delete / add）均在 `src.server.retrieval._vs_lock` 保护下进行，
  与“范围检索临时替换全局向量库”的操作串行化，避免并发污染；
- 一切操作**尽力而为**：以 try/except 兜底并记录日志，绝不向外抛出异常导致启动 /
  监听线程崩溃。

约定：代码 / API 名称使用英文；注释使用中文。
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

# 受支持扩展名以 extract 模块为权威来源（在 loader 纯文本集合之上额外支持 .pdf/.docx）。
# 注：.doc（旧版二进制 Word）有意不在其中。
from src.server.extract import SUPPORTED_EXTENSIONS

# 监听去抖间隔（秒）：文件系统事件往往成簇到达，等待一段空窗后再统一同步一次。
_DEBOUNCE_SECONDS = 1.5


def _scan_disk_files(data_dir: str) -> dict:
    """扫描 data_dir，返回 ``{filename: char_size}``。

    - 仅纳入扩展名 ∈ SUPPORTED_EXTENSIONS（含 .pdf/.docx）的常规文件；
    - char_size 取“抽取文本的字符数”（经 `extract.extract_text`，与 extract_single /
      索引写入的元数据 ``size`` 同口径）；
    - 不支持的类型（UnsupportedDocError）或抽取失败的文件直接跳过（仅记录一次日志）。

    说明：抽取在每次同步时执行一遍（对小型 KB 可接受）；如后续 KB 增大可引入
    mtime / size 缓存以减少重复抽取开销。
    """
    # 惰性导入 extract：避免导入本模块时引入 pypdf / python-docx 等可选依赖
    from src.server import extract

    result: dict[str, int] = {}
    if not os.path.isdir(data_dir):
        return result

    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        try:
            text = extract.extract_text(path)
        except extract.UnsupportedDocError:
            # 明确不支持的类型：跳过（不索引）
            logger.warning("Incremental sync: skipped (unsupported type): %s", name)
            continue
        except Exception:  # noqa: BLE001 - 抽取异常时跳过该文件，不影响其它文件
            logger.warning("Incremental sync: skipped (extract error): %s", name, exc_info=True)
            continue
        result[name] = len(text)

    return result


def _read_index_state(vector_store) -> dict:
    """读取向量库现状，返回 ``{source: {"ids": [...], "size": int | None}}``。

    通过 ``vector_store.get()`` 获取全部 ids / metadatas，按 ``source`` 聚合每个来源的
    chunk ids；``size`` 取该来源任一 chunk 元数据中的 ``size``（loader 写入的字符数）。
    底层不支持 ``get()`` 或调用失败时返回空字典（视为“索引为空”，退化为全量新增）。
    """
    state: dict[str, dict] = {}
    try:
        data = vector_store.get()
    except Exception:  # noqa: BLE001 - get 不被支持或失败：视为空索引
        logger.warning("Incremental sync: vector_store.get() unavailable; treating index as empty.")
        return state

    ids = (data or {}).get("ids") or []
    metadatas = (data or {}).get("metadatas") or []

    for idx, meta in enumerate(metadatas):
        meta = meta or {}
        source = meta.get("source")
        if source is None:
            continue
        entry = state.get(source)
        if entry is None:
            entry = {"ids": [], "size": None}
            state[source] = entry
        # 收集该来源对应的 chunk id（防御性地按下标对齐）
        if idx < len(ids):
            entry["ids"].append(ids[idx])
        # size 取任一 chunk 的元数据值（同一来源各 chunk 的 size 相同）
        if entry["size"] is None and "size" in meta:
            entry["size"] = meta.get("size")

    return state


def sync_data_folder(vector_store, data_dir: str = "./data") -> dict:
    """对 ``data_dir`` 执行一次**增量同步**到给定向量库。

    变更判定规则（change-detection）：以“来源（文件名）是否已在索引中” +
    “磁盘文本字符数与索引中记录的 size 是否一致”为准：
    - NEW：磁盘存在、索引中无该来源；
    - CHANGED：索引中已有该来源，但磁盘 char_size != 索引记录的 size；
    - UNCHANGED：来源存在且 size 一致；
    - DELETED：索引中存在、但磁盘上已无对应文件。

    处理流程：
    1. CHANGED + DELETED：收集其在索引中的 chunk ids 并 ``vector_store.delete(ids=...)``；
    2. NEW + CHANGED：经 ``load_documents_from_directory`` 读取后按目标来源过滤，
       ``split_documents`` 切块，``vector_store.add_documents(chunks)`` 写入。
    所有变更均在 `retrieval._vs_lock` 保护下进行（与范围检索的全局替换串行化）。

    返回：``{"added": [...], "updated": [...], "removed": [...], "unchanged": int,
    "chunks_added": int}``。本函数**尽力而为**，任何异常都被捕获并记录，不向外抛出；
    异常情况下返回已累计的（或空的）结果，保证调用方（启动钩子 / 监听回调）不崩溃。
    """
    result = {
        "added": [],
        "updated": [],
        "removed": [],
        "unchanged": 0,
        "chunks_added": 0,
    }

    if vector_store is None:
        # 无可用 live store（如单例尚未初始化）：跳过本次同步
        logger.info("Incremental sync skipped: vector store is not available.")
        return result

    try:
        # 惰性导入：避免导入本模块时触发 embeddings / Chroma 初始化等副作用
        from src.ingestion.loader import split_documents
        # 惰性导入 extract：富文本（PDF/DOCX）+ 纯文本统一抽取入口
        from src.server import extract
        # 惰性导入全局锁：与 retrieval 的范围替换共享同一把锁
        from src.server.retrieval import _vs_lock

        # 1) 扫描磁盘与索引现状
        disk_files = _scan_disk_files(data_dir)
        index_state = _read_index_state(vector_store)

        # 2) 判定增量集合
        new_sources: list[str] = []
        changed_sources: list[str] = []
        unchanged_count = 0
        for filename, char_size in disk_files.items():
            if filename not in index_state:
                new_sources.append(filename)
            else:
                indexed_size = index_state[filename].get("size")
                # size 缺失（旧索引未记录）或不一致 -> 视为 CHANGED，触发重建
                if indexed_size is None or indexed_size != char_size:
                    changed_sources.append(filename)
                else:
                    unchanged_count += 1

        # DELETED：索引中存在但磁盘已不存在的来源
        deleted_sources = [src for src in index_state if src not in disk_files]

        result["unchanged"] = unchanged_count

        # 目标重建集合（NEW + CHANGED）；以集合便于过滤
        target_sources = set(new_sources) | set(changed_sources)

        # 3) 在全局锁保护下执行所有变更（删除 + 写入）
        with _vs_lock:
            # 3a) 先删除 CHANGED 与 DELETED 来源的旧 chunk
            ids_to_delete: list[str] = []
            for src in changed_sources + deleted_sources:
                ids_to_delete.extend(index_state.get(src, {}).get("ids") or [])
            if ids_to_delete:
                try:
                    vector_store.delete(ids=ids_to_delete)
                except Exception:  # noqa: BLE001 - 删除不被支持 / 失败：记录后继续
                    logger.warning(
                        "Incremental sync: failed to delete %d stale chunks; continuing.",
                        len(ids_to_delete),
                        exc_info=True,
                    )

            # 3b) 写入 NEW + CHANGED 来源的新 chunk
            chunks_added = 0
            if target_sources:
                # 逐个目标来源经 extract 抽取为 Document（富文本/纯文本统一入口）
                target_docs = []
                for src in target_sources:
                    doc = extract.extract_single(os.path.join(data_dir, src))
                    if doc is not None:
                        target_docs.append(doc)
                if target_docs:
                    chunks = split_documents(target_docs)
                    if chunks:
                        try:
                            vector_store.add_documents(chunks)
                            chunks_added = len(chunks)
                        except Exception:  # noqa: BLE001 - 写入失败：记录后返回已知结果
                            logger.exception(
                                "Incremental sync: failed to add documents to the vector store."
                            )
                            chunks_added = 0

        # 4) 汇总结果
        result["added"] = new_sources
        result["updated"] = changed_sources
        result["removed"] = deleted_sources
        result["chunks_added"] = chunks_added

        logger.info(
            "Incremental sync done: added=%d, updated=%d, removed=%d, unchanged=%d, chunks_added=%d",
            len(result["added"]),
            len(result["updated"]),
            len(result["removed"]),
            result["unchanged"],
            result["chunks_added"],
        )
    except Exception:  # noqa: BLE001 - 顶层兜底：增量同步绝不向外抛出
        logger.exception("Incremental sync failed unexpectedly; returning best-effort result.")

    return result


def start_data_watcher(get_live_store, data_dir: str = "./data"):
    """启动对 ``data_dir`` 的文件系统监听，触发去抖后的增量同步。

    参数：
        get_live_store: 无参可调用对象，返回当前 live 向量库或 None（惰性，每次同步前调用）；
        data_dir: 被监听的目录（默认 ``./data``）。

    行为：
    - 惰性导入 `watchdog`；若未安装或 ``data_dir`` 不存在，记录 warning 并返回 None（no-op）；
    - 任意 create / modify / move / delete 事件都会重置一个 ``threading.Timer``，
      在 ~1.5s 空窗后调用 ``sync_data_folder(get_live_store())``；
    - 若届时 ``get_live_store()`` 返回 None（单例未就绪），则跳过本次同步；
    - 返回 watchdog ``Observer`` 实例，供 `stop_data_watcher` 停止。
    """
    # 目录缺失：无可监听对象，优雅 no-op
    if not os.path.isdir(data_dir):
        logger.warning("Data watcher not started: directory '%s' does not exist.", data_dir)
        return None

    # 惰性导入 watchdog；未安装则优雅降级
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception:  # noqa: BLE001 - 未安装 watchdog：记录后返回 None
        logger.warning(
            "Data watcher not started: 'watchdog' package is not available. "
            "Install it to enable automatic incremental indexing."
        )
        return None

    # 去抖定时器与锁（事件回调可能来自不同线程）
    debounce_lock = threading.Lock()
    timer_holder: dict[str, threading.Timer | None] = {"timer": None}

    def _trigger_sync() -> None:
        """去抖窗口结束后的实际同步动作（惰性取 live store）。"""
        try:
            store = get_live_store() if callable(get_live_store) else None
            if store is None:
                logger.info("Data watcher: live store not ready; skip this sync.")
                return
            sync_data_folder(store, data_dir)
        except Exception:  # noqa: BLE001 - 回调内兜底，绝不让监听线程崩溃
            logger.exception("Data watcher: sync callback failed.")

    def _schedule() -> None:
        """收到事件时重置去抖定时器。"""
        with debounce_lock:
            existing = timer_holder.get("timer")
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(_DEBOUNCE_SECONDS, _trigger_sync)
            timer.daemon = True
            timer_holder["timer"] = timer
            timer.start()

    class _DebouncedHandler(FileSystemEventHandler):
        """将所有文件系统事件归并为一次去抖同步。"""

        def on_any_event(self, event):  # noqa: D401 - watchdog 回调
            # 忽略目录自身的事件噪声，仅在收到任意变更时调度去抖同步
            _schedule()

    try:
        observer = Observer()
        observer.schedule(_DebouncedHandler(), data_dir, recursive=False)
        observer.daemon = True
        observer.start()
        logger.info("Data watcher started on '%s' (debounce=%.1fs).", data_dir, _DEBOUNCE_SECONDS)
        return observer
    except Exception:  # noqa: BLE001 - 启动失败：优雅返回 None
        logger.warning("Data watcher failed to start on '%s'.", data_dir, exc_info=True)
        return None


def stop_data_watcher(observer) -> None:
    """尽力而为地停止并 join 观察者；observer 为 None 时直接返回。"""
    if observer is None:
        return
    try:
        observer.stop()
        observer.join(timeout=5)
        logger.info("Data watcher stopped.")
    except Exception:  # noqa: BLE001 - 停止失败不影响关闭流程
        logger.warning("Failed to stop data watcher cleanly.", exc_info=True)


__all__ = [
    "sync_data_folder",
    "start_data_watcher",
    "stop_data_watcher",
]
