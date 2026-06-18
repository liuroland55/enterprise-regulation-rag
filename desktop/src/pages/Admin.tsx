// desktop/src/pages/Admin.tsx
// 管理后台（仅 admin 可见）：用户管理 + 知识库管理 + 高级设置 + 系统监控。
// - 角色守卫：role !== "admin" 时渲染“无权限”提示（纵深防御；App 外壳同样会隐藏入口）。
// - 用户管理：复用 <UserManagement/>（自包含的用户 CRUD 组件）。
// - 知识库：文件上传（api.uploadDoc）+ 列表（api.listKb）+ 删除（api.deleteKb，带确认）。
// - 高级设置：复用 <AdvancedSettings/>，本地 state + localStorage 持久化；
//   这些为前瞻性特性开关（feature flag），RAG 核心当前可忽略。
//   TODO(persist): 后续可改为持久化到后端 settings 端点（当前仅本地保存）。
// - 系统监控：复用 <SystemUsage/>，从 api.getStats() 自由格式字典中尽力映射用量数据。
// 所有受保护调用统一经 useSession().callWithRefresh 包装（遇 401 自动刷新重试）。
// 样式沿用项目其它组件的内联样式风格。
// 命名一律使用英文；注释默认中文。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";
import type { I18nContextValue } from "../i18n";
import {
  AdvancedSettings,
  type AdvancedSettingsState,
} from "../components/admin/AdvancedSettings";
import {
  SystemUsage,
  type ModelMode,
  type SystemUsageData,
} from "../components/admin/SystemUsage";
import { UserManagement } from "../components/admin/UserManagement";
import type { KbEntry, HistoryItem, SystemStats } from "../types/chat";

// localStorage 持久化键：高级设置
const ADVANCED_SETTINGS_KEY = "rag2.advancedSettings";

// 高级设置默认值（首次进入或读取失败时使用）
const DEFAULT_ADVANCED_SETTINGS: AdvancedSettingsState = {
  topK: 4,
  enableReranker: false,
  enableHybridSearch: false,
};

// ---------------------------------------------------------------------------
// 辅助：从 localStorage 读取高级设置（容错，失败回退默认值）
// ---------------------------------------------------------------------------
function loadAdvancedSettings(): AdvancedSettingsState {
  try {
    const raw = globalThis.localStorage?.getItem(ADVANCED_SETTINGS_KEY);
    if (!raw) return DEFAULT_ADVANCED_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AdvancedSettingsState>;
    return {
      topK:
        typeof parsed.topK === "number" && !Number.isNaN(parsed.topK)
          ? parsed.topK
          : DEFAULT_ADVANCED_SETTINGS.topK,
      enableReranker: Boolean(parsed.enableReranker),
      enableHybridSearch: Boolean(parsed.enableHybridSearch),
    };
  } catch {
    return DEFAULT_ADVANCED_SETTINGS;
  }
}

// ---------------------------------------------------------------------------
// 辅助：从自由格式 stats 字典尽力映射出 SystemUsageData
// - mode 来自 stats.mode（CLOUD / LOCAL），无法识别时回退 LOCAL；
// - totalQueries / totalUsers 缺失时回退 0（类型要求为 number）；
// - totalTokens / totalCost / avgLatencyMs 缺失时保持 undefined。
// ---------------------------------------------------------------------------
function toSystemUsage(stats: SystemStats | null): SystemUsageData | undefined {
  if (!stats) return undefined;

  const rawMode = typeof stats.mode === "string" ? stats.mode.toUpperCase() : "";
  const mode: ModelMode = rawMode === "CLOUD" ? "CLOUD" : "LOCAL";

  // 安全读取数值字段：仅当为有限数字时采用
  const num = (key: string): number | undefined => {
    const v = stats[key];
    return typeof v === "number" && Number.isFinite(v) ? v : undefined;
  };

  return {
    mode,
    // 不同后端可能用不同键名，尽量兼容；缺失则回退 0
    totalQueries: num("total_queries") ?? num("totalQueries") ?? 0,
    totalUsers: num("total_users") ?? num("totalUsers") ?? 0,
    totalTokens: num("total_tokens") ?? num("totalTokens"),
    totalCost: num("total_cost") ?? num("totalCost"),
    avgLatencyMs: num("avg_latency_ms") ?? num("avgLatencyMs"),
  };
}

// 将知识库相关 ApiError 映射为可读文案（通过传入的 t 函数翻译）
function toKbErrorMessage(
  err: unknown,
  context: "load" | "upload" | "delete",
  t: I18nContextValue["t"]
): string {
  if (err instanceof ApiError) {
    if (err.status === 415) return t("admin.kb.error.unsupportedType");
    if (err.status === 404) return t("admin.kb.error.notFound");
    if (err.status === 403) return t("admin.kb.error.forbidden");
    if (err.status === 400) return t("admin.kb.error.badRequest");
    return t("admin.kb.error.statusCode", { status: err.status });
  }
  const fallbackKey: Record<typeof context, string> = {
    load: "admin.kb.error.load",
    upload: "admin.kb.error.upload",
    delete: "admin.kb.error.delete",
  };
  return t(fallbackKey[context]);
}

// 文件大小格式化
function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// 内联样式常量（沿用项目内联样式风格）
// ---------------------------------------------------------------------------
const styles = {
  page: {
    fontFamily: "system-ui, sans-serif",
    padding: "1.5rem",
    maxWidth: "1100px",
    margin: "0 auto",
    color: "#111827",
  } as const,
  section: {
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "0.5rem",
    padding: "1rem 1.25rem",
    marginBottom: "1.5rem",
  } as const,
  sectionTitle: {
    fontSize: "1rem",
    fontWeight: 600,
    margin: "0 0 0.75rem",
  } as const,
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
    fontSize: "0.8125rem",
  } as const,
  th: {
    textAlign: "left" as const,
    borderBottom: "2px solid #e5e7eb",
    padding: "0.5rem",
    color: "#374151",
  } as const,
  td: {
    borderBottom: "1px solid #f3f4f6",
    padding: "0.5rem",
    verticalAlign: "top" as const,
  } as const,
  primaryBtn: {
    padding: "0.4rem 0.75rem",
    background: "#2563eb",
    color: "#ffffff",
    border: "none",
    borderRadius: "0.375rem",
    fontSize: "0.8125rem",
    cursor: "pointer",
  } as const,
  dangerBtn: {
    padding: "0.3rem 0.6rem",
    background: "#dc2626",
    color: "#ffffff",
    border: "none",
    borderRadius: "0.375rem",
    fontSize: "0.75rem",
    cursor: "pointer",
  } as const,
};

// ---------------------------------------------------------------------------
// 知识库管理子区：上传 + 列表 + 删除（自包含，使用父级注入的 callWithRefresh）
// ---------------------------------------------------------------------------
function KnowledgeBaseSection() {
  const { callWithRefresh } = useSession();
  const { t } = useI18n();

  const [items, setItems] = useState<KbEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  // 已选择的文件名（用于在自定义上传按钮旁展示）
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // 加载知识库列表
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await callWithRefresh(() => api.listKb());
      setItems(res.items);
    } catch (err) {
      setError(toKbErrorMessage(err, "load", t));
    } finally {
      setLoading(false);
    }
  }, [callWithRefresh, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 选择文件后上传
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setSuccess(null);
    setSelectedName(file.name);
    setUploading(true);
    try {
      const result = await callWithRefresh(() => api.uploadDoc(file));
      setSuccess(t("admin.kb.uploadSuccess", { filename: result.filename, count: result.chunksAdded }));
      await reload();
    } catch (err) {
      setError(toKbErrorMessage(err, "upload", t));
    } finally {
      setUploading(false);
      // 重置 input，允许再次选择同名文件
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // 删除文档（带确认）
  const handleDelete = async (entry: KbEntry) => {
    setError(null);
    setSuccess(null);
    const ok = globalThis.confirm?.(t("admin.kb.confirmDelete", { filename: entry.filename }));
    if (!ok) return;
    try {
      await callWithRefresh(() => api.deleteKb(entry.docId));
      setSuccess(t("admin.kb.deleteSuccess", { filename: entry.filename }));
      await reload();
    } catch (err) {
      setError(toKbErrorMessage(err, "delete", t));
    }
  };

  // 重建索引：从 ./data 重新加载并写入向量库，完成后刷新列表
  const handleReindex = async () => {
    setError(null);
    setSuccess(null);
    setReindexing(true);
    try {
      const result = await callWithRefresh(() => api.reindex());
      setSuccess(t("admin.kb.reindexSuccess", { files: result.files, count: result.chunksAdded }));
      await reload();
    } catch (err) {
      setError(toKbErrorMessage(err, "load", t));
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div aria-label={t("admin.section.kb")}>
      {error && (
        <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
          {error}
        </div>
      )}
      {success && (
        <div style={{ color: "#047857", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>{success}</div>
      )}

      {/* 上传：原生 <input type="file"> 的按钮文案由 OS/浏览器渲染、无法本地化，
          因此将其视觉隐藏（display:none），改用自定义本地化按钮转发点击。 */}
      <div style={{ marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.rst,.log,.pdf,.docx"
          disabled={uploading}
          onChange={(e) => void handleFileChange(e)}
          style={{ display: "none" }}
        />
        {/* 自定义本地化按钮：点击转发到隐藏的原生 input */}
        <button
          type="button"
          style={styles.primaryBtn}
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {t("admin.kb.uploadButton")}
        </button>
        {/* 已选择的文件名（成功消息之外的即时反馈） */}
        {selectedName && (
          <span style={{ fontSize: "0.8125rem", color: "#374151" }}>{selectedName}</span>
        )}
        {uploading && <span style={{ fontSize: "0.8125rem", color: "#6b7280" }}>{t("admin.kb.uploading")}</span>}
        <button
          type="button"
          style={styles.primaryBtn}
          disabled={reindexing}
          onClick={() => void handleReindex()}
        >
          {reindexing ? t("admin.kb.reindexing") : t("admin.kb.reindex")}
        </button>
      </div>

      {/* 列表 */}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>{t("admin.kb.col.filename")}</th>
            <th style={styles.th}>{t("admin.kb.col.type")}</th>
            <th style={styles.th}>{t("admin.kb.col.size")}</th>
            <th style={styles.th}>{t("admin.kb.col.modified")}</th>
            <th style={styles.th}>{t("admin.kb.col.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && !loading && (
            <tr>
              <td style={styles.td} colSpan={5}>
                {t("admin.kb.empty")}
              </td>
            </tr>
          )}
          {items.map((entry) => (
            <tr key={entry.docId}>
              <td style={styles.td}>{entry.filename}</td>
              <td style={styles.td}>{entry.filetype}</td>
              <td style={styles.td}>{formatSize(entry.size)}</td>
              <td style={styles.td}>{new Date(entry.modifiedAt).toLocaleString()}</td>
              <td style={styles.td}>
                <button type="button" style={styles.dangerBtn} onClick={() => void handleDelete(entry)}>
                  {t("admin.kb.delete")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.5rem" }}>
        {t("admin.kb.note")}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 答案截断长度（超出则提供展开/收起）
// ---------------------------------------------------------------------------
const ANSWER_TRUNCATE_LENGTH = 120;

// ---------------------------------------------------------------------------
// 提问记录审计单行：展示问题、答案（可展开）、评级、时间。
// 用户名不在行内展示（已上移到所属账号的分组头），答案默认截断、超长可展开/收起。
// ---------------------------------------------------------------------------
function AuditHistoryRow({ item }: { item: HistoryItem }) {
  const { t } = useI18n();
  // 单行答案的展开/收起状态
  const [expanded, setExpanded] = useState(false);
  const answer = item.answer ?? "";
  const isLong = answer.length > ANSWER_TRUNCATE_LENGTH;
  const shown = expanded || !isLong ? answer : `${answer.slice(0, ANSWER_TRUNCATE_LENGTH)}…`;

  return (
    <tr>
      <td style={styles.td}>{item.question}</td>
      <td style={styles.td}>
        <span>{shown}</span>
        {isLong && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            style={{
              marginLeft: "0.375rem",
              padding: 0,
              border: "none",
              background: "transparent",
              color: "#2563eb",
              fontSize: "0.75rem",
              cursor: "pointer",
            }}
          >
            {expanded ? t("adminHistory.collapse") : t("adminHistory.expand")}
          </button>
        )}
      </td>
      <td style={styles.td}>
        {/* 评级徽章：YES -> ok，其余 -> warn */}
        <span className={`badge badge-${item.grade === "YES" ? "ok" : "warn"}`}>{item.grade}</span>
      </td>
      <td style={styles.td}>{new Date(item.createdAt).toLocaleString()}</td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// 审计分组：按账号聚合的一组历史记录（提问者 + 其全部提问，倒序）。
// ---------------------------------------------------------------------------
interface UserHistoryGroup {
  key: string; // 分组唯一键（优先 userId，回退 username）
  username: string; // 展示用的用户名
  items: HistoryItem[]; // 该用户的历史记录（全局倒序保证组内亦为倒序）
  latest: number; // 该用户最近一次提问的时间戳（毫秒），用于「最新提问」排序
}

// 审计排序方式：按用户名 / 按最新提问时间
type AuditSort = "name" | "latest";

// 安全解析 createdAt 为毫秒时间戳（非法时回退 0，避免 NaN 干扰排序）
function toTime(iso: string): number {
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : 0;
}

// 将扁平历史记录按账号分组（userId 优先，回退 username）。
function groupByUser(items: HistoryItem[], unknownLabel: string): UserHistoryGroup[] {
  const map = new Map<string, UserHistoryGroup>();
  for (const it of items) {
    const username = it.username ?? unknownLabel;
    const key = it.userId != null ? `id:${it.userId}` : `name:${username}`;
    const existing = map.get(key);
    const ts = toTime(it.createdAt);
    if (existing) {
      existing.items.push(it);
      if (ts > existing.latest) existing.latest = ts;
    } else {
      map.set(key, { key, username, items: [it], latest: ts });
    }
  }
  return [...map.values()];
}

// ---------------------------------------------------------------------------
// 单个账号分组：可折叠卡片。组头展示用户名 + 记录数 + 最新提问时间，
// 点击组头展开/收起该账号的全部提问记录（复用 AuditHistoryRow）。
// ---------------------------------------------------------------------------
function AuditUserGroup({
  group,
  expanded,
  onToggle,
}: {
  group: UserHistoryGroup;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.5rem",
        marginBottom: "0.5rem",
        overflow: "hidden",
      }}
    >
      {/* 组头：点击展开/收起 */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          padding: "0.625rem 0.75rem",
          background: "#f9fafb",
          border: "none",
          borderBottom: expanded ? "1px solid #e5e7eb" : "none",
          cursor: "pointer",
          textAlign: "left",
          fontSize: "0.8125rem",
          color: "#111827",
        }}
      >
        {/* 展开指示三角 */}
        <span style={{ width: "0.75rem", color: "#6b7280" }}>{expanded ? "▾" : "▸"}</span>
        <span style={{ fontWeight: 600 }}>{group.username}</span>
        <span style={{ color: "#6b7280" }}>
          {t("adminHistory.group.count", { count: group.items.length })}
        </span>
        <span style={{ marginLeft: "auto", color: "#6b7280", fontSize: "0.75rem" }}>
          {t("adminHistory.group.latest", {
            time: new Date(group.latest).toLocaleString(),
          })}
        </span>
      </button>

      {/* 展开内容：该账号的全部提问记录（问题 / 回答 / 评级 / 时间） */}
      {expanded && (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>{t("adminHistory.col.question")}</th>
              <th style={styles.th}>{t("adminHistory.col.answer")}</th>
              <th style={styles.th}>{t("adminHistory.col.grade")}</th>
              <th style={styles.th}>{t("adminHistory.col.time")}</th>
            </tr>
          </thead>
          <tbody>
            {group.items.map((item) => (
              <AuditHistoryRow key={item.id} item={item} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// 审计分页抓取：每页大小与最大页数上限（防止数据量极大时无限抓取）
const AUDIT_PAGE_SIZE = 100;
const AUDIT_MAX_PAGES = 50;

// ---------------------------------------------------------------------------
// 提问记录审计子区：按【账号】分组展示所有用户历史，仅 admin 可见。
// - 抓取：分页拉取全部 /admin/history（上限 AUDIT_MAX_PAGES 页），客户端按账号聚合。
// - 分组：每个账号一张可折叠卡片，展开后列出该账号的全部提问记录（倒序）。
// - 排序：账号可按「用户名」或「最新提问时间（最新优先）」排序；并支持按用户名检索。
// 经 callWithRefresh 包装（遇 401 自动刷新重试）；处理加载/空/错误态。
// 隐私说明：该审计为产品有意设计，管理员可审阅；常规 /history 端点仍按用户隔离。
// ---------------------------------------------------------------------------
function AuditHistorySection() {
  const { callWithRefresh } = useSession();
  const { t } = useI18n();

  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 账号检索关键字（按用户名子串匹配，大小写不敏感）
  const [search, setSearch] = useState("");
  // 账号排序方式：用户名 / 最新提问时间
  const [sort, setSort] = useState<AuditSort>("latest");
  // 已展开的分组键集合（支持同时展开多个账号）
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  // 加载全部用户历史：分页抓取直至取完（或达页数上限）；经 callWithRefresh 包装
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const first = await callWithRefresh(() => api.adminListHistory(1, AUDIT_PAGE_SIZE));
      const all = [...first.items];
      const totalPages = Math.min(
        Math.ceil(first.total / AUDIT_PAGE_SIZE),
        AUDIT_MAX_PAGES
      );
      for (let page = 2; page <= totalPages; page++) {
        const res = await callWithRefresh(() => api.adminListHistory(page, AUDIT_PAGE_SIZE));
        all.push(...res.items);
      }
      setItems(all);
    } catch {
      setError(t("adminHistory.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [callWithRefresh, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 切换某分组的展开/收起
  const toggleGroup = useCallback((key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // 分组 + 检索过滤 + 排序（派生数据，随依赖变化重算）
  const groups = useMemo(() => {
    const grouped = groupByUser(items, t("adminHistory.unknownUser"));
    const keyword = search.trim().toLowerCase();
    const filtered = keyword
      ? grouped.filter((g) => g.username.toLowerCase().includes(keyword))
      : grouped;
    const sorted = [...filtered];
    if (sort === "name") {
      // 按用户名升序（本地化比较）
      sorted.sort((a, b) => a.username.localeCompare(b.username));
    } else {
      // 按最新提问时间降序（最新在前）
      sorted.sort((a, b) => b.latest - a.latest);
    }
    return sorted;
  }, [items, search, sort, t]);

  return (
    <div aria-label={t("admin.section.history")}>
      {error && (
        <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
          {error}
        </div>
      )}

      {/* 工具条：刷新 + 用户名检索 + 排序方式 */}
      <div
        style={{
          marginBottom: "0.75rem",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <button type="button" style={styles.primaryBtn} disabled={loading} onClick={() => void reload()}>
          {loading ? t("adminHistory.loading") : t("adminHistory.refresh")}
        </button>
        {/* 按用户名检索 */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("adminHistory.searchPlaceholder")}
          style={{
            padding: "0.375rem 0.5rem",
            border: "1px solid #d1d5db",
            borderRadius: "0.375rem",
            fontSize: "0.8125rem",
            minWidth: "12rem",
          }}
        />
        {/* 排序方式 */}
        <label style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.8125rem", color: "#374151" }}>
          {t("adminHistory.sort.label")}
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as AuditSort)}
            style={{
              padding: "0.375rem 0.5rem",
              border: "1px solid #d1d5db",
              borderRadius: "0.375rem",
              fontSize: "0.8125rem",
            }}
          >
            <option value="latest">{t("adminHistory.sort.latest")}</option>
            <option value="name">{t("adminHistory.sort.name")}</option>
          </select>
        </label>
      </div>

      {/* 空态：无记录或检索无匹配 */}
      {groups.length === 0 && !loading && (
        <div style={{ fontSize: "0.8125rem", color: "#6b7280" }}>
          {items.length === 0 ? t("adminHistory.empty") : t("adminHistory.noMatch")}
        </div>
      )}

      {/* 分组列表：每个账号一张可折叠卡片 */}
      {groups.map((group) => (
        <AuditUserGroup
          key={group.key}
          group={group}
          expanded={expandedKeys.has(group.key)}
          onToggle={() => toggleGroup(group.key)}
        />
      ))}
    </div>
  );
}

export function Admin() {
  const { role, callWithRefresh } = useSession();
  const { t } = useI18n();

  // 统计数据（自由格式字典）
  const [stats, setStats] = useState<SystemStats | null>(null);

  // 高级设置（本地 state + localStorage 持久化）
  const [advanced, setAdvanced] = useState<AdvancedSettingsState>(loadAdvancedSettings);

  // 高级设置变化时持久化（前瞻性 feature flag，核心当前可忽略）
  const handleAdvancedChange = useCallback((next: AdvancedSettingsState) => {
    setAdvanced(next);
    try {
      globalThis.localStorage?.setItem(ADVANCED_SETTINGS_KEY, JSON.stringify(next));
    } catch {
      // 持久化失败忽略（隐私模式等），状态仍保留在内存
    }
  }, []);

  // 加载系统统计（best-effort：失败兜底为 null，不阻断其它区块）
  const loadStats = useCallback(async () => {
    try {
      const statsData = await callWithRefresh(() => api.getStats());
      setStats(statsData);
    } catch {
      setStats(null);
    }
  }, [callWithRefresh]);

  useEffect(() => {
    // 仅 admin 拉取统计
    if (role === "admin") void loadStats();
  }, [role, loadStats]);

  // 由 stats 映射出系统用量数据
  const usage = useMemo(() => toSystemUsage(stats), [stats]);

  // 角色守卫：纵深防御。App 外壳已隐藏入口，这里再次拦截非管理员访问。
  if (role !== "admin") {
    return (
      <div style={styles.page}>
        <h2 style={{ fontSize: "1.25rem", marginTop: 0 }}>{t("admin.title")}</h2>
        <div role="alert" style={{ color: "#b91c1c", fontSize: "0.875rem" }}>
          {t("admin.noPermission")}
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <h2 style={{ fontSize: "1.25rem", marginTop: 0 }}>{t("admin.title")}</h2>

      {/* 用户管理 */}
      <section style={styles.section} aria-label={t("admin.section.users")}>
        <h3 style={styles.sectionTitle}>{t("admin.section.users")}</h3>
        <UserManagement />
      </section>

      {/* 知识库管理 */}
      <section style={styles.section} aria-label={t("admin.section.kb")}>
        <h3 style={styles.sectionTitle}>{t("admin.section.kb")}</h3>
        <KnowledgeBaseSection />
      </section>

      {/* 提问记录审计：列出所有用户历史（仅 admin 可见，有意为之的审计能力） */}
      <section style={styles.section} aria-label={t("admin.section.history")}>
        <h3 style={styles.sectionTitle}>{t("admin.section.history")}</h3>
        <AuditHistorySection />
      </section>

      {/* 高级设置 */}
      <section style={styles.section} aria-label={t("advanced.ariaLabel")}>
        <AdvancedSettings value={advanced} onChange={handleAdvancedChange} />
        <p style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.5rem" }}>
          {t("admin.advancedNote")}
        </p>
      </section>

      {/* 系统监控 / 用量统计 */}
      <section style={styles.section} aria-label={t("system.ariaLabel")}>
        <SystemUsage usage={usage} />
      </section>
    </div>
  );
}

export default Admin;
