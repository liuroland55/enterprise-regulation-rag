# Implementation Plan: Enterprise Regulation RAG Desktop

## Overview

本实现计划将设计文档（`design.md`）转化为可增量实现的编码任务。整体策略为 **测试驱动、自底向上**：
先搭建脚手架与依赖，再实现配置/数据库层、安全鉴权层，然后是纯函数 `build_augmented_query`、
DTO schemas、各路由（auth / query+history / history / admin / kb / system）、FastAPI 应用装配与
side-car 打包；最后构建 Tauri + React 桌面客户端（API client → 会话/鉴权 → 三栏布局组件 → 角色门控
→ 集成联调与端到端集成测试）。

关键约束 **Zero RAG Core Changes**：`src/api/rag_api.py`、`src/graph/*`、`src/config/settings.py`、
`src/ingestion/loader.py` 一律不得修改。所有涉及 RAG 核心的测试均通过 **mock/stub `RAG2API.ask`**
（以及 stub ingestion loader）保持确定性。

属性测试库：Python 侧用 `hypothesis`，前端 TypeScript 侧用 `fast-check`（hypothesis 的 TS 等价物），
每个属性测试至少运行 100 次迭代，并以 **Feature: enterprise-regulation-rag-desktop, Property N** 标记。

## Tasks

- [x] 1. 项目脚手架与依赖
  - [x] 1.1 添加 Python 依赖并创建 side-car 包骨架
    - 在 `requirements.txt` 追加 `fastapi`、`uvicorn`、`python-jose[cryptography]`、`passlib[bcrypt]`、`sqlmodel`、`python-multipart`、`hypothesis`、`pytest`（pin 到具体版本）
    - 创建 `src/server/` 包结构：`__init__.py`、`config.py`、`db.py`、`models.py`、`schemas.py`、`security.py`、`injection.py`、`routers/__init__.py` 等空模块占位
    - 不改动任何 RAG 核心文件（rag_api / graph / settings / loader）
    - _Requirements: 1.2, 18.1, 18.4_

  - [ ]* 1.2 搭建 pytest + hypothesis 测试脚手架
    - 创建 `tests/server/` 目录与 `conftest.py`（内存 SQLite fixture、`RAG2API.ask` 的 stub fixture）
    - 配置 hypothesis profile（最少 100 次迭代）
    - _Requirements: 1.2_

- [x] 2. 服务级配置与数据库层
  - [x] 2.1 实现 `src/server/config.py`
    - 从环境变量/本地安全文件加载 `JWT_SECRET`（HS256），禁止硬编码；定义 access/refresh 过期时间
    - 定义绑定地址 `127.0.0.1:8756`、`BOOTSTRAP_ADMIN_USER/PASSWORD`、模型 mode（CLOUD/LOCAL）读取
    - _Requirements: 1.2, 17.1, 17.2_

  - [x] 2.2 实现 `src/server/models.py`（SQLModel 表模型）
    - 定义 `User`（含 `password_hash`、`role`、`position`、`tasks` JSON 字符串）、`RefreshToken`、`QueryHistory`（`user_id` 索引、`question` 存原始问题）
    - _Requirements: 2.2, 4.3, 10.2, 10.3, 12.2_

  - [x] 2.3 实现 `src/server/db.py`（engine / session / init_db / seed_admin）
    - 实现 `init_db()` 建表、`get_session()` 依赖、`seed_admin()` 仅在无 admin 时从 env 播种单一 admin
    - _Requirements: 7.1, 7.2_

  - [ ]* 2.4 编写 seed_admin 幂等性单元测试
    - 验证无 admin 时创建一个 admin；已存在 admin 时不再创建
    - _Requirements: 7.1, 7.2_

- [x] 3. 安全与鉴权（`src/server/security.py`）
  - [x] 3.1 实现密码哈希/校验与密码策略
    - `hash_password` / `verify_password`（passlib bcrypt），绝不存储或记录明文
    - 实现密码策略：长度≥8 且至少含一个字母与一个数字
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 17.4_

  - [ ]* 3.2 编写密码 hash/verify 往返属性测试
    - **Property 1: Password hash/verify round-trip**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 3.3 编写密码策略属性测试
    - **Property 2: Password policy acceptance**
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 3.4 实现 JWT 令牌与 `get_current_user`
    - `create_access_token`（注入 id/username/role/position/tasks、type=access）、`create_refresh_token`、`decode_token`（HS256，失败 401）、`get_current_user`（校验 type=access 并还原 `UserContext`）
    - _Requirements: 4.2, 5.1, 5.2, 5.3, 17.2, 17.3_

  - [ ]* 3.5 编写 access-token 声明往返属性测试
    - **Property 3: Access-token claim round-trip**
    - **Validates: Requirements 4.2, 5.1, 17.3**

  - [x] 3.6 实现 `require_role` 依赖工厂
    - 角色不在允许集合时返回 HTTP 403；已认证但无特定角色要求时放行
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 3.7 编写 RBAC 单调性属性测试
    - **Property 4: RBAC role-gating monotonicity**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 12.1, 12.5, 13.1, 13.6**

- [x] 4. Checkpoint - 确保安全/数据库层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Profile 注入（`src/server/injection.py`）
  - [x] 5.1 实现 `build_augmented_query`（纯函数）
    - 保留 trim 后的原始问题作为主导子句；按 position/tasks 追加引导上下文；空档案仍含原始问题
    - 纯函数：确定性、无 I/O；过滤空白 task 条目；增强查询传给未改动的 RAG_Core
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 5.2 编写"增强查询保留原始问题"属性测试
    - **Property 5: Augmented query preserves the original question**
    - **Validates: Requirements 8.2, 8.4**

  - [ ]* 5.3 编写"增强查询确定性且纯"属性测试
    - **Property 6: Query augmentation is deterministic and pure**
    - **Validates: Requirements 8.3**

  - [ ]* 5.4 编写"空白 task 被排除"属性测试
    - **Property 7: Whitespace-only tasks are excluded from augmentation**
    - **Validates: Requirements 8.5**

- [x] 6. DTO Schemas（`src/server/schemas.py`）
  - [x] 6.1 实现 Pydantic DTO
    - `UserProfile`、`UserContext`、`AskRequest`（含 question 去空白后非空校验）、`SourceItem`、`AskResponse`、`HistoryItem`、`HistoryListResponse`、`TokenResponse`、`UserCreate/UserUpdate/UserOut`
    - _Requirements: 4.1, 9.4, 11.x_

  - [ ]* 6.2 编写空问题拒绝单元/属性测试
    - **Property 9: Empty-question rejection**（`AskRequest` 对空/纯空白 question 触发 422）
    - **Validates: Requirements 9.2**

- [x] 7. API 路由实现
  - [x] 7.1 实现 Auth 路由（`routers/auth.py`）
    - `/auth/login`（校验密码，签发 access+refresh，持久化 refresh token，返回 role；失败 401 通用错误）、`/auth/refresh`（有效未吊销 refresh 签发新 access；吊销/过期 401）、首登强制改密标记
    - _Requirements: 4.1, 4.3, 4.4, 5.4, 5.5, 7.3_

  - [ ]* 7.2 编写 Auth 路由单元测试
    - 无效凭据 401、refresh 成功/吊销/过期分支（stub DB）
    - _Requirements: 4.4, 5.4, 5.5_

  - [x] 7.3 实现 Query 路由 `/ask`（`routers/query.py`）含历史持久化
    - 从 JWT 取 profile → `build_augmented_query` → 调用 stub/真实 `RAG2API.ask` → 映射 `AskResponse`（含 sources）；success=false 时 HTTP 200 携带 success=false
    - best-effort 写入 `QueryHistory`（存**原始问题**、answer/grade/iterations/success/source_count）；写库失败仅记录日志、响应不变
    - _Requirements: 8.1, 8.6, 9.1, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4_

  - [ ]* 7.4 编写 `/ask` 响应保真属性测试（mock `RAG2API.ask`）
    - **Property 8: /ask response fidelity**
    - **Validates: Requirements 9.1, 9.3, 9.4**

  - [ ]* 7.5 编写"历史保存原始问题"属性测试（mock `RAG2API.ask`）
    - **Property 10: Original-question fidelity in history**
    - **Validates: Requirements 10.2**

  - [ ]* 7.6 编写"best-effort 持久化不影响响应"属性测试（mock DB 写入失败）
    - **Property 11: Best-effort persistence never alters the response**
    - **Validates: Requirements 10.1, 10.4**

  - [x] 7.7 实现 History 路由（`routers/history.py`）
    - `/history` 列表（仅当前用户、按 created_at 倒序分页）、`/history/{id}` get、`/history/{id}` delete（非本人或不存在均 404）、可选 `/admin/history` 审计（require_role admin）
    - 身份一律取自 JWT，绝不信任客户端传入 user_id
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ]* 7.8 编写历史隔离属性测试
    - **Property 12: Query history isolation**
    - **Validates: Requirements 11.1, 11.3, 11.4, 11.5, 11.6**

  - [ ]* 7.9 编写历史排序属性测试
    - **Property 13: Query history ordering**
    - **Validates: Requirements 11.2**

  - [x] 7.10 实现 Admin 用户 CRUD 路由（`routers/admin.py`）
    - `/admin/users` 创建/列表/读取/更新/删除（全部 require_role admin）；持久化 position 与 tasks；重名 409
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 7.11 编写档案持久化往返属性测试
    - **Property 14: Profile persistence round-trip**
    - **Validates: Requirements 12.2, 12.3**

  - [x] 7.12 实现 KB 路由（`routers/kb.py`）
    - `/kb/upload`（admin，扩展名校验，复用 ingestion loader 向量化，返回 filename+chunks_added；不支持扩展名 415）、`/kb/list`（任意已认证用户）、`/kb/{id}` delete（admin）
    - loader 调用在测试中被 stub，不触碰 RAG 核心
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [ ]* 7.13 编写上传扩展名分类属性测试（stub loader）
    - **Property 15: Upload extension classification**
    - **Validates: Requirements 13.2, 13.3**

  - [x] 7.14 实现 System 路由（`routers/system.py`）
    - `/system/health`、`/system/stats` 复用 `RAG2API` 既有方法；按 CLOUD/LOCAL mode 标注 token cost/latency 的含义
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

- [x] 8. FastAPI 应用装配与 side-car 打包（`src/server/main.py`）
  - [x] 8.1 实现 app 工厂与启动装配
    - 创建 FastAPI app、挂载全部 router、startup 执行 `init_db()` / `seed_admin()` / 初始化 `RAG2API` 单例；uvicorn 仅绑定 `127.0.0.1:8756`；提供 side-car 启动入口脚本
    - _Requirements: 1.1, 1.2, 7.1, 7.2, 17.1, 18.1_

  - [ ]* 8.2 集成测试：login → ask → 收到答案（mock `RAG2API.ask`）
    - 端到端走 TestClient，校验鉴权链路与响应结构
    - _Requirements: 4.1, 8.1, 9.1_

  - [ ]* 8.3 集成测试：admin upload → list 反映新文档（stub loader）
    - _Requirements: 13.1, 13.2, 13.4_

- [x] 9. Checkpoint - 确保 side-car 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 桌面客户端脚手架与基础设施
  - [x] 10.1 搭建 Tauri + React + TypeScript 工程与 side-car 生命周期
    - 初始化 `desktop/`（`src-tauri/` + `src/`）；Rust 外壳 spawn/monitor side-car 子进程
    - _Requirements: 1.1, 1.3_

  - [x] 10.2 实现 API client 与共享类型（`desktop/src/api/client.ts`、`types/chat.ts`）
    - 统一附加 `Authorization: Bearer`，BASE_URL 指向 `http://127.0.0.1:8756`，封装 login/ask/history/users/kb 调用；定义 `AskResponse`、`HistoryItem` 等类型
    - _Requirements: 1.4, 1.5_

  - [x] 10.3 实现会话/鉴权状态（`desktop/src/auth/session.ts`）
    - 内存 + 安全存储保存 JWT；提供 `useSession()`（role 等）；401 触发刷新流程
    - _Requirements: 1.5, 5.1_

- [x] 11. 三栏布局、组件与角色门控
  - [x] 11.1 实现 `ThreeColumnLayout` 与 `pages/Chat.tsx` 组合
    - 左/中/右三列骨架，右列可折叠
    - _Requirements: 14.1_

  - [x] 11.2 实现 `ProfileCard` 与 `KbScopeSelector`
    - 画像卡展示职位+任务（员工只读）；KB scope 多选（可选）
    - _Requirements: 14.2_

  - [x] 11.3 实现 `SessionHistory`（接 `GET /history`）
    - 拉取当前用户历史（倒序），点击项重新载入该问答到聊天区
    - _Requirements: 14.3, 14.4_

  - [x] 11.4 实现 `ChatWindow` 与 `ConfidenceBadge`（`deriveConfidence`）
    - 由 grade + iterations 推导可信度，绝不展示原始分数；grade≠YES 渲染 低 + 人工确认提示
    - _Requirements: 15.1, 15.2_

  - [ ]* 11.5 编写可信度徽章映射属性测试（fast-check）
    - **Property 16: Confidence badge mapping**
    - **Validates: Requirements 15.1, 15.2**

  - [x] 11.6 实现 `SourcePanel`（`relevanceFromScore`）
    - cosine 分数翻译为 高/中/低 相关性标签，绝不展示原始分数
    - _Requirements: 15.3, 15.4_

  - [ ]* 11.7 编写溯源相关性单调性属性测试（fast-check）
    - **Property 17: Source relevance monotonicity**
    - **Validates: Requirements 15.3, 15.4**

  - [x] 11.8 实现 `useDeveloperMode` 钩子、`DeveloperModeToggle`、`DeveloperMetricsPanel`
    - 开发者模式仅 admin 生效；员工恒为 false 且隐藏开关与指标面板
    - _Requirements: 16.1, 16.2, 16.3_

  - [ ]* 11.9 编写开发者模式 admin 门控属性测试（fast-check）
    - **Property 18: Developer mode is admin-gated**
    - **Validates: Requirements 16.1, 16.2, 16.3**

  - [x] 11.10 实现 `AdvancedSettings` 与 `SystemUsage`
    - 高级设置（top_k / reranker / hybrid，标注未来能力）与系统监控/用量视图，仅 admin
    - _Requirements: 16.4, 16.5_

- [x] 12. 集成联调（前后端打通）
  - [x] 12.1 串联 Chat 页端到端数据流
    - 登录态下 ask → 渲染答案 + 徽章 + 溯源；点击历史项重放问答；按角色显隐开发者模式
    - _Requirements: 1.5, 14.1, 14.3, 15.1_

  - [ ]* 12.2 编写前端集成测试（mock API client）
    - 覆盖登录→提问→历史重放主流程
    - _Requirements: 14.3, 14.4_

- [x] 13. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务（unit / property / integration），可跳过以加速 MVP；顶层任务不带 `*`。
- 每个任务都标注了对应的 EARS 需求编号以保证可追溯性；属性测试任务额外标注其 Property 编号。
- Python 侧属性测试使用 `hypothesis`，前端 TypeScript 侧使用 `fast-check`（hypothesis 的 TS 等价物）。
- 所有涉及 RAG 核心的任务均为 **集成-only**，通过 mock/stub `RAG2API.ask` 与 ingestion loader 保持确定性，**绝不修改 RAG 核心**。
- Checkpoint 任务用于增量验证；Property 1-18 全部映射到具体实现任务旁，便于早发现错误。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "10.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2", "6.1", "10.2"] },
    { "id": 2, "tasks": ["2.3", "3.1", "5.1", "6.2", "10.3"] },
    { "id": 3, "tasks": ["2.4", "3.2", "3.3", "3.4", "5.2", "5.3", "5.4", "11.1", "11.2"] },
    { "id": 4, "tasks": ["3.5", "3.6", "11.3", "11.4", "11.6", "11.8", "11.10"] },
    { "id": 5, "tasks": ["3.7", "7.1", "7.3", "7.7", "7.10", "7.12", "7.14", "11.5", "11.7", "11.9"] },
    { "id": 6, "tasks": ["7.2", "7.4", "7.5", "7.6", "7.8", "7.9", "7.11", "7.13", "12.1"] },
    { "id": 7, "tasks": ["8.1", "12.2"] },
    { "id": 8, "tasks": ["8.2", "8.3"] }
  ]
}
```
