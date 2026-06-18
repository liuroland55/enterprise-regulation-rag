"""KB 路由单元测试。

使用标准库 `unittest` 与 FastAPI `TestClient`（基于 httpx），覆盖：
- 扩展名过滤：不支持 -> 415；支持 -> 200（向量化通过 monkeypatch 桩替身完成，离线可跑）；
- `/kb/list` 枚举 ./data 中受支持的文件并返回基础元数据；
- `/kb/{doc_id}` 删除：存在 -> 200；不存在 -> 404；
- 路径穿越防护 -> 400；
- RBAC：employee 访问 admin 限定路由 -> 403。

说明：测试将 `kb.DATA_DIR` 指向临时目录，避免污染真实 ./data；
并将 loader 的 `get_vector_store` 等替换为桩替身，避免触发真实 embeddings/Chroma。
"""

import os
import tempfile
import unittest

# 确保导入期 JWT_SECRET 可用（config 在生产缺失会报错；此处显式提供，稳定可重复）
os.environ.setdefault("JWT_SECRET", "unit-test-secret")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

import src.ingestion.loader as loader  # noqa: E402
import src.server.routers.kb as kb  # noqa: E402
from src.server.schemas import UserContext  # noqa: E402
from src.server.security import get_current_user  # noqa: E402


def _admin() -> UserContext:
    return UserContext(id=1, username="admin", role="admin", position="", tasks=[])


def _employee() -> UserContext:
    return UserContext(id=2, username="emp", role="employee", position="", tasks=[])


class _FakeVectorStore:
    """记录 add_documents 调用的向量库桩替身。"""

    def __init__(self):
        self.added = []

    def add_documents(self, docs):
        self.added.extend(docs)


class KBRouterTestBase(unittest.TestCase):
    def setUp(self):
        # 临时数据目录，隔离真实 ./data
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self._orig_data_dir = kb.DATA_DIR
        kb.DATA_DIR = self.data_dir

        # 保存并桩替 loader 的向量化相关函数
        self._orig_get_vs = loader.get_vector_store
        self._orig_load = loader.load_documents_from_directory
        self.fake_vs = _FakeVectorStore()
        loader.get_vector_store = lambda *a, **k: self.fake_vs

        # 构造仅挂载 kb 路由的最小 app
        self.app = FastAPI()
        self.app.include_router(kb.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        kb.DATA_DIR = self._orig_data_dir
        loader.get_vector_store = self._orig_get_vs
        loader.load_documents_from_directory = self._orig_load
        self.app.dependency_overrides.clear()
        self._tmp.cleanup()

    def _as_admin(self):
        self.app.dependency_overrides[get_current_user] = _admin

    def _as_employee(self):
        self.app.dependency_overrides[get_current_user] = _employee


class TestUpload(KBRouterTestBase):
    def test_unsupported_extension_returns_415(self):
        self._as_admin()
        resp = self.client.post(
            "/kb/upload",
            files={"file": ("evil.exe", b"binary", "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 415)

    def test_supported_extension_vectorizes_and_returns_chunks(self):
        self._as_admin()
        # 桩替 loader：返回与上传文件 source 匹配的文档
        loader.load_documents_from_directory = lambda directory=".": [
            Document(page_content="hello world", metadata={"source": "doc.md"})
        ]
        resp = self.client.post(
            "/kb/upload",
            files={"file": ("doc.md", b"hello world", "text/markdown")},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["filename"], "doc.md")
        self.assertGreaterEqual(body["chunks_added"], 1)
        # 文件确实落盘
        self.assertTrue(os.path.isfile(os.path.join(self.data_dir, "doc.md")))
        # 向量库收到分块
        self.assertGreaterEqual(len(self.fake_vs.added), 1)

    def test_path_traversal_filename_rejected(self):
        self._as_admin()
        resp = self.client.post(
            "/kb/upload",
            files={"file": ("../../etc/passwd", b"x", "text/plain")},
        )
        # basename 归一化后为 "passwd"（无扩展名）-> 415；关键是不会写到 ./data 之外
        self.assertIn(resp.status_code, (400, 415))

    def test_employee_forbidden(self):
        self._as_employee()
        resp = self.client.post(
            "/kb/upload",
            files={"file": ("doc.md", b"x", "text/markdown")},
        )
        self.assertEqual(resp.status_code, 403)


class TestList(KBRouterTestBase):
    def test_lists_supported_files_only(self):
        # 准备：1 个支持文件 + 1 个不支持文件
        with open(os.path.join(self.data_dir, "a.md"), "w", encoding="utf-8") as f:
            f.write("# title")
        with open(os.path.join(self.data_dir, "b.exe"), "wb") as f:
            f.write(b"\x00\x01")

        self._as_employee()  # 任意已认证用户即可
        resp = self.client.get("/kb/list")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        names = {item["filename"] for item in body["items"]}
        self.assertIn("a.md", names)
        self.assertNotIn("b.exe", names)
        self.assertEqual(body["total"], len(body["items"]))


class TestDelete(KBRouterTestBase):
    def test_delete_existing_returns_200(self):
        path = os.path.join(self.data_dir, "del.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("content")

        self._as_admin()
        resp = self.client.delete("/kb/del.txt")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["deleted"])
        self.assertFalse(os.path.isfile(path))

    def test_delete_missing_returns_404(self):
        self._as_admin()
        resp = self.client.delete("/kb/nope.txt")
        self.assertEqual(resp.status_code, 404)

    def test_employee_forbidden(self):
        self._as_employee()
        resp = self.client.delete("/kb/whatever.txt")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
