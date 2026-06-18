// desktop/src/api/client.ts
// API 客户端：统一附加 Bearer JWT，BASE_URL 指向本地侧车（仅回环地址）。
// 命名一律使用英文；注释默认中文。
import type {
  AskResponse,
  HistoryItem,
  HistoryListResponse,
  KbEntry,
  KbListResponse,
  ModeInfo,
  ModeUpdateResult,
  ReindexResult,
  RegisterInput,
  SystemStats,
  TempDoc,
  ThinkingStep,
  TokenResponse,
  UploadResult,
  UserCreateInput,
  UserOut,
  UserUpdateInput,
} from "../types/chat";

const BASE_URL = "http://127.0.0.1:8756"; // 侧车仅绑定回环地址

// ---------------------------------------------------------------------------
// 错误类型
// ---------------------------------------------------------------------------

// 401 未授权：令牌缺失/失效/过期时抛出，供会话层触发刷新或重新登录
export class UnauthorizedError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

// 非 2xx（且非 401）通用 API 错误：携带 HTTP 状态码与响应体文本
export class ApiError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`API error ${status}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// 令牌状态
// ---------------------------------------------------------------------------

let accessToken: string | null = null;

// 设置/清除当前 access token；后续请求自动附带 Authorization 头
export function setToken(t: string | null): void {
  accessToken = t;
}

// ---------------------------------------------------------------------------
// 底层请求封装
// ---------------------------------------------------------------------------

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // 统一附加 Bearer JWT；401 抛出 UnauthorizedError，其余非 2xx 抛出 ApiError
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  // FormData 由浏览器自动设置 multipart 边界，不能手动覆盖 Content-Type
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) throw new ApiError(res.status, await res.text());
  // 204 No Content（如 DELETE）无响应体
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// 后端原始响应（snake_case）→ 前端类型（camelCase）映射
// 后端 DTO 为 snake_case，前端在边界处统一转换为 camelCase。
// ---------------------------------------------------------------------------

interface RawTokenResponse {
  access_token: string;
  refresh_token: string;
  role: string;
}

interface RawHistoryItem {
  id: number;
  question: string;
  answer: string;
  grade: string;
  iterations: number;
  success: boolean;
  source_count: number;
  created_at: string;
  // 审计字段（可选）：仅 /admin/history 返回
  user_id?: number | null;
  username?: string | null;
}

interface RawHistoryListResponse {
  items: RawHistoryItem[];
  page: number;
  page_size: number;
  total: number;
}

interface RawUserOut {
  id: number;
  username: string;
  role: string;
  position: string;
  tasks: string[];
  is_active: boolean;
}

interface RawUploadResult {
  filename: string;
  chunks_added: number;
}

interface RawReindexResult {
  files: number;
  chunks_added: number;
  cleared: boolean;
}

interface RawKbEntry {
  doc_id: string;
  filename: string;
  filetype: string;
  size: number;
  modified_at: string;
}

interface RawKbListResponse {
  items: RawKbEntry[];
  total: number;
}

interface RawModeInfo {
  mode: string;
  cloud_ready: boolean;
  persist_dir: string;
}

interface RawModeUpdateResult {
  mode: string;
  restart_required: boolean;
  warning?: string | null;
}

function mapToken(r: RawTokenResponse): TokenResponse {
  return { accessToken: r.access_token, refreshToken: r.refresh_token, role: r.role };
}

function mapHistoryItem(r: RawHistoryItem): HistoryItem {
  return {
    id: r.id,
    question: r.question,
    answer: r.answer,
    grade: r.grade,
    iterations: r.iterations,
    success: r.success,
    sourceCount: r.source_count,
    createdAt: r.created_at,
    // 审计字段：snake_case -> camelCase；缺省（普通 /history）保持 undefined
    ...(r.user_id != null ? { userId: r.user_id } : {}),
    ...(r.username != null ? { username: r.username } : {}),
  };
}

function mapHistoryList(r: RawHistoryListResponse): HistoryListResponse {
  return {
    items: r.items.map(mapHistoryItem),
    page: r.page,
    pageSize: r.page_size,
    total: r.total,
  };
}

function mapUser(r: RawUserOut): UserOut {
  return {
    id: r.id,
    username: r.username,
    role: r.role,
    position: r.position,
    tasks: r.tasks,
    isActive: r.is_active,
  };
}

function mapUpload(r: RawUploadResult): UploadResult {
  return { filename: r.filename, chunksAdded: r.chunks_added };
}

// 重建索引结果映射：snake_case -> camelCase
function mapReindex(r: RawReindexResult): ReindexResult {
  return { files: r.files, chunksAdded: r.chunks_added, cleared: r.cleared };
}

// 知识库条目映射：snake_case -> camelCase
function mapKbEntry(r: RawKbEntry): KbEntry {
  return {
    docId: r.doc_id,
    filename: r.filename,
    filetype: r.filetype,
    size: r.size,
    modifiedAt: r.modified_at,
  };
}

function mapKbList(r: RawKbListResponse): KbListResponse {
  return { items: r.items.map(mapKbEntry), total: r.total };
}

// 运行模式信息映射：snake_case -> camelCase
function mapModeInfo(r: RawModeInfo): ModeInfo {
  return { mode: r.mode, cloudReady: r.cloud_ready, persistDir: r.persist_dir };
}

// 切换模式结果映射：snake_case -> camelCase（warning 为 null 时归一化为 undefined）
function mapModeUpdate(r: RawModeUpdateResult): ModeUpdateResult {
  return {
    mode: r.mode,
    restartRequired: r.restart_required,
    ...(r.warning ? { warning: r.warning } : {}),
  };
}

// ---------------------------------------------------------------------------
// 对外 API
// ---------------------------------------------------------------------------

export const api = {
  // 登录：使用 application/x-www-form-urlencoded（OAuth2 兼容），签发 access+refresh
  login: async (username: string, password: string): Promise<TokenResponse> => {
    const raw = await request<RawTokenResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
    return mapToken(raw);
  },

  // 自助注册：创建普通员工账户并直接返回双令牌（注册即登录）。
  // 重名 -> 409；密码不满足策略 -> 422（由调用方映射为提示）。角色由后端强制为 employee。
  register: async (input: RegisterInput): Promise<TokenResponse> => {
    const raw = await request<RawTokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: input.username,
        password: input.password,
        position: input.position ?? "",
        tasks: input.tasks ?? [],
      }),
    });
    return mapToken(raw);
  },

  // 当前用户最新资料（GET /auth/me）：资料双端同步的真相源，供前端实时刷新画像。
  me: async (): Promise<UserOut> => {
    const raw = await request<RawUserOut>("/auth/me");
    return mapUser(raw);
  },

  // 提问：JSON 提交问题，后端做职位感知查询增强后返回结构化答案。
  // opts 可选：kbSources（勾选的知识库范围）/ tempDocs（临时文件）。
  // 检索优先级（后端实现）：临时文件 > 勾选范围 > 全部。向后兼容：不传 opts 即旧行为。
  ask: (
    question: string,
    opts?: { kbSources?: string[]; tempDocs?: TempDoc[]; lang?: string }
  ): Promise<AskResponse> =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        ...(opts?.kbSources ? { kb_sources: opts.kbSources } : {}),
        ...(opts?.tempDocs ? { temp_context: opts.tempDocs } : {}),
        ...(opts?.lang ? { lang: opts.lang } : {}),
      }),
    }),

  // 流式提问：实时接收后台“思考过程”（检索/生成评分/重写），思考完成后给出最终答案。
  // 通过 SSE（text/event-stream）逐帧解析；onStep 收到中间步骤，onFinal 收到最终 AskResponse。
  // 401 抛 UnauthorizedError（可被会话层 callWithRefresh 捕获重试）；其余非 2xx 抛 ApiError。
  askStream: async (
    question: string,
    handlers: {
      onStep: (step: ThinkingStep) => void;
      onFinal: (answer: AskResponse) => void;
      onError?: (message: string) => void;
    },
    opts?: { kbSources?: string[]; tempDocs?: TempDoc[]; lang?: string },
    signal?: AbortSignal
  ): Promise<void> => {
    const headers = new Headers({
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    });
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

    const res = await fetch(`${BASE_URL}/ask/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        question,
        ...(opts?.kbSources ? { kb_sources: opts.kbSources } : {}),
        ...(opts?.tempDocs ? { temp_context: opts.tempDocs } : {}),
        ...(opts?.lang ? { lang: opts.lang } : {}),
      }),
      signal,
    });
    if (res.status === 401) throw new UnauthorizedError();
    if (!res.ok) throw new ApiError(res.status, await res.text());
    if (!res.body) {
      // 无流式正文：降级为错误回调
      handlers.onError?.("空响应流");
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // 解析一段 SSE 缓冲：以空行分隔事件，取 data: 后的 JSON 分派
    const dispatch = (raw: string) => {
      const line = raw.split("\n").find((l) => l.startsWith("data:"));
      if (!line) return;
      const jsonText = line.slice("data:".length).trim();
      if (!jsonText) return;
      let evt: Record<string, unknown>;
      try {
        evt = JSON.parse(jsonText);
      } catch {
        return; // 跳过无法解析的帧
      }
      const kind = evt.kind;
      if (kind === "step") {
        handlers.onStep({
          type: evt.type as ThinkingStep["type"],
          iteration: Number(evt.iteration ?? 0),
          docs: typeof evt.docs === "number" ? evt.docs : undefined,
          grade: typeof evt.grade === "string" ? evt.grade : undefined,
          reason: typeof evt.reason === "string" ? evt.reason : undefined,
          query: typeof evt.query === "string" ? evt.query : undefined,
        });
      } else if (kind === "final") {
        const rawSources = Array.isArray(evt.sources) ? (evt.sources as Array<{ content?: string; source?: string }>) : [];
        handlers.onFinal({
          answer: String(evt.answer ?? ""),
          grade: String(evt.grade ?? "NO"),
          reason: String(evt.reason ?? ""),
          iterations: Number(evt.iterations ?? 0),
          success: Boolean(evt.success),
          sources: rawSources.map((s) => ({ content: s.content ?? "", source: s.source ?? "" })),
        });
      } else if (kind === "error") {
        handlers.onError?.(String(evt.message ?? "未知错误"));
      }
    };

    // 持续读取直到流结束；按空行切分 SSE 事件
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (chunk.trim()) dispatch(chunk);
      }
    }
    // 处理可能残留的最后一帧
    if (buffer.trim()) dispatch(buffer);
  },

  // 历史列表：仅当前用户、倒序分页
  listHistory: async (page = 1, pageSize = 20): Promise<HistoryListResponse> => {
    const raw = await request<RawHistoryListResponse>(
      `/history?page=${page}&page_size=${pageSize}`
    );
    return mapHistoryList(raw);
  },

  // 单条历史：仅本人可读，否则后端返回 404
  getHistory: async (id: number): Promise<HistoryItem> => {
    const raw = await request<RawHistoryItem>(`/history/${id}`);
    return mapHistoryItem(raw);
  },

  // 删除历史：仅本人可删，否则后端返回 404
  deleteHistory: (id: number): Promise<void> =>
    request<void>(`/history/${id}`, { method: "DELETE" }),

  // 管理员审计：列出所有用户历史（GET /admin/history），倒序分页。
  // 可选 userId 过滤；返回项额外携带 userId/username 以标识提问者身份。
  adminListHistory: async (
    page = 1,
    pageSize = 20,
    userId?: number
  ): Promise<HistoryListResponse> => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (userId !== undefined) params.set("user_id", String(userId));
    const raw = await request<RawHistoryListResponse>(`/admin/history?${params.toString()}`);
    return mapHistoryList(raw);
  },

  // 管理员：列出全部用户
  listUsers: async (): Promise<UserOut[]> => {
    const raw = await request<RawUserOut[]>("/admin/users");
    return raw.map(mapUser);
  },

  // 管理员：创建用户（POST /admin/users）。
  // 重名 -> 409；密码不满足策略 -> 422（由调用方映射为中文提示）。
  createUser: async (input: UserCreateInput): Promise<UserOut> => {
    const raw = await request<RawUserOut>("/admin/users", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return mapUser(raw);
  },

  // 管理员：读取单个用户（GET /admin/users/{id}）；不存在 -> 404。
  getUser: async (id: number): Promise<UserOut> => {
    const raw = await request<RawUserOut>(`/admin/users/${id}`);
    return mapUser(raw);
  },

  // 管理员：更新用户（PUT /admin/users/{id}）；仅提交提供的字段。
  updateUser: async (id: number, patch: UserUpdateInput): Promise<UserOut> => {
    const raw = await request<RawUserOut>(`/admin/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    return mapUser(raw);
  },

  // 管理员：删除用户（DELETE /admin/users/{id}）；返回 204 无内容。
  deleteUser: (id: number): Promise<void> =>
    request<void>(`/admin/users/${id}`, { method: "DELETE" }),

  // 系统统计（需认证，GET /system/stats）。
  // 后端返回自由格式的字典（含 mode / usage_metrics 等），此处以 SystemStats（宽松类型）返回。
  getStats: (): Promise<SystemStats> =>
    request<SystemStats>("/system/stats"),

  // 读取当前生效的运行模式（需认证，GET /system/mode）。
  getMode: async (): Promise<ModeInfo> => {
    const raw = await request<RawModeInfo>("/system/mode");
    return mapModeInfo(raw);
  },

  // 切换全局运行模式（需认证，POST /system/mode）。
  // 写回 .env 并返回是否需重启；切到 CLOUD 缺密钥时返回 warning。
  setMode: async (mode: string): Promise<ModeUpdateResult> => {
    const raw = await request<RawModeUpdateResult>("/system/mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    return mapModeUpdate(raw);
  },

  // 管理员：上传知识库文档（multipart/form-data）
  uploadDoc: async (file: File): Promise<UploadResult> => {
    const fd = new FormData();
    fd.append("file", file);
    const raw = await request<RawUploadResult>("/kb/upload", {
      method: "POST",
      body: fd,
    });
    return mapUpload(raw);
  },

  // 知识库列表（任意已认证用户，GET /kb/list）。
  listKb: async (): Promise<KbListResponse> => {
    const raw = await request<RawKbListResponse>("/kb/list");
    return mapKbList(raw);
  },

  // 管理员：删除知识库条目（DELETE /kb/{docId}）。
  // 后端返回 200 + DeleteResponse（doc_id/deleted/note），此处不关心响应体，统一忽略。
  deleteKb: async (docId: string): Promise<void> => {
    await request<unknown>(`/kb/${encodeURIComponent(docId)}`, {
      method: "DELETE",
    });
  },

  // 管理员：重建持久化索引（POST /kb/reindex）。
  // 从 ./data 重新加载并切块写入向量库；返回处理文件数 / 新增分块数 / 是否清空旧向量。
  reindex: async (): Promise<ReindexResult> => {
    const raw = await request<RawReindexResult>("/kb/reindex", {
      method: "POST",
    });
    return mapReindex(raw);
  },
};
