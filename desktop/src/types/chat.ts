// desktop/src/types/chat.ts
// 前端共享类型：与后端 FastAPI 侧车的 DTO（schemas.py）对齐。
// 命名一律使用英文；注释默认中文。
// 注意：后端响应字段为 snake_case，但前端类型在边界处统一映射为 camelCase
// （如 source_count -> sourceCount, page_size -> pageSize, created_at -> createdAt）。

// 单条溯源/依据项：与后端 AskResponse.sources 元素对齐
export interface SourceItem {
  content: string; // 原文摘录
  source: string; // 来源标识（文件/条例）
}

// 临时文件：前端在客户端读取文本后随提问请求上送，仅用于本次/接下来的提问，不入库。
// 与后端 schemas.py 的 TempDoc 对齐。
export interface TempDoc {
  name: string; // 文件名
  content: string; // 文件文本内容
}

// 与后端 AskResponse 对齐（参见 schemas.py）
export interface AskResponse {
  answer: string;
  grade: string; // "YES" | "NO"
  reason: string;
  iterations: number;
  success: boolean;
  sources: SourceItem[];
  // 可选工程字段：仅在开发者模式下展示；后端需扩展后才会返回
  metrics?: DeveloperMetrics;
}

// 人类可读的相关性/可信度等级（绝不暴露原始分数）
export type ConfidenceLevel = "高" | "中" | "低";

// 后台“思考过程”单步事件（来自 /ask/stream 的 Self-RAG 节点流）。
// - retrieve：完成一次检索（docs 为召回条数）
// - generate：生成并自评分（grade YES/NO + reason）
// - rewrite：重写查询（query 为新查询）
export interface ThinkingStep {
  type: "retrieve" | "generate" | "rewrite";
  iteration: number;
  docs?: number;
  grade?: string;
  reason?: string;
  query?: string;
}

// 溯源/依据卡片：供 SourcePanel 渲染（相关性用 高/中/低 表达，不暴露原始分数）
export interface SourceCard {
  title: string; // 条例标题
  section: string; // 章/节
  excerpt: string; // 原文摘录
  relevance: ConfidenceLevel; // 由 cosine 分数翻译而来的人类可读相关性
}

// 查询历史条目：与后端 HistoryItem (schemas.py) 对齐
export interface HistoryItem {
  id: number;
  question: string; // 原始问题（非增强查询）
  answer: string;
  grade: string; // "YES" | "NO"
  iterations: number;
  success: boolean;
  sourceCount: number; // 后端 source_count（驼峰映射）
  createdAt: string; // ISO 时间字符串（后端 created_at）
  // 审计字段（可选）：仅管理员审计端点 /admin/history 返回，标识提问者身份；
  // 按用户隔离的 /history 端点不返回，故二者为 undefined（保持隐私隔离）。
  userId?: number; // 提问者 id（后端 user_id）
  username?: string; // 提问者用户名（后端 username）
}

// 分页历史响应：与后端 HistoryListResponse 对齐
export interface HistoryListResponse {
  items: HistoryItem[];
  page: number;
  pageSize: number; // 后端 page_size
  total: number;
}

// 仅开发者模式可见的工程指标（后端可选扩展字段）
export interface DeveloperMetrics {
  retrievedChunks: number; // 召回片段数
  rawScores: number[]; // 原始相似度分数
  tokenCost?: number; // token 成本（CLOUD 模式有意义；LOCAL 仅供参考）
  latencyMs?: number; // 端到端延迟
  retrievalMs?: number; // 检索耗时
}

// 登录返回的双令牌：与后端 /auth/login 响应对齐
export interface TokenResponse {
  accessToken: string; // 后端 access_token
  refreshToken: string; // 后端 refresh_token
  role: string; // "admin" | "employee"
}

// 用户视图对象：与后端 UserOut（admin 用户管理）对齐
export interface UserOut {
  id: number;
  username: string;
  role: string; // "admin" | "employee"
  position: string; // 职位
  tasks: string[]; // 任务列表
  isActive: boolean; // 后端 is_active
}

// 知识库上传结果：与后端 /kb/upload 响应对齐
export interface UploadResult {
  filename: string;
  chunksAdded: number; // 后端 chunks_added
}

// 知识库重建索引结果：与后端 /kb/reindex 响应对齐（chunks_added -> chunksAdded）
export interface ReindexResult {
  files: number; // 处理的文件数
  chunksAdded: number; // 新增分块数（后端 chunks_added）
  cleared: boolean; // 是否清空了旧向量
}

// 创建用户的输入：与后端 UserCreate（POST /admin/users）对齐
export interface UserCreateInput {
  username: string;
  password: string;
  role: string; // "admin" | "employee"
  position: string; // 职位
  tasks: string[]; // 任务列表
}

// 更新用户的补丁：与后端 UserUpdate（PUT /admin/users/{id}）对齐，所有字段可选
export interface UserUpdateInput {
  position?: string;
  tasks?: string[];
  role?: string;
}

// 自助注册输入：与后端 RegisterRequest（POST /auth/register）对齐。
// 注意：注册一律创建为普通员工，无 role 字段（角色由后端强制）。
export interface RegisterInput {
  username: string;
  password: string;
  position?: string; // 可选职位
  tasks?: string[]; // 可选任务列表
}

// 运行模式信息：与后端 ModeInfo（GET /system/mode）对齐。
export interface ModeInfo {
  mode: string; // 当前生效模式 "CLOUD" | "LOCAL"
  cloudReady: boolean; // 是否已配置 OPENAI_API_KEY（后端 cloud_ready）
  persistDir: string; // 该模式的向量库目录（后端 persist_dir）
}

// 切换模式结果：与后端 ModeUpdateResult（POST /system/mode）对齐。
export interface ModeUpdateResult {
  mode: string; // 写入的目标模式
  restartRequired: boolean; // 是否需重启侧车生效（后端 restart_required）
  warning?: string; // 非阻断性提示（如缺少 OPENAI_API_KEY）
}

// 系统统计：/system/stats 返回的自由格式响应。
// 后端会附带 mode / usage_metrics 以及 RAG2API.get_statistics() 的统计字段，
// 不同后端 / 模式下字段并不固定，故此处保持宽松（可选 + 索引签名）。
export interface SystemStats {
  documents?: number; // 文档数量（若后端提供）
  chunks?: number; // 向量分块数量（若后端提供）
  mode?: string; // 运行模式（CLOUD / LOCAL）
  [k: string]: unknown; // 其余自由格式字段（如 usage_metrics、total_* 等）
}

// 单条知识库条目：与后端 /kb/list 的 KBEntry 对齐
export interface KbEntry {
  docId: string; // 文档标识（后端 doc_id，即文件名）
  filename: string; // 文件名
  filetype: string; // 扩展名（小写含点，如 ".md"）
  size: number; // 文件字节大小
  modifiedAt: string; // 最近修改时间（后端 modified_at，ISO 字符串）
}

// 知识库列表响应：与后端 /kb/list 的 KBListResponse 对齐
export interface KbListResponse {
  items: KbEntry[];
  total: number;
}
