"""侧车服务 API 路由子包。

后续任务（Task 7.x）将在此子包内实现各路由模块：
- `auth.py`：/auth/register、/auth/login、/auth/refresh；
- `query.py`：/ask（成功 / 失败后写入 QueryHistory）；
- `history.py`：/history 列表 / 获取 / 删除（+ 可选 /admin/history 审计）；
- `admin.py`：/admin/users CRUD；
- `kb.py`：/kb 上传 / 列表 / 删除；
- `system.py`：/system/health、/system/stats。

注意：本文件仅为子包初始化占位。
"""
