// desktop/src/components/left/SessionHistory.tsx
// 左列「历史会话」组件：接 GET /history（经 api.listHistory），
// 仅拉取当前用户自己的历史（身份由后端依据 JWT 推导），倒序展示。
// 每条历史以独立的「带边框卡片」呈现：卡片主体展示问题摘要（点击重放 → onSelect），
// 卡片右上角提供删除按钮（× / 🗑）：点击需阻止冒泡，二次确认后调用 api.deleteHistory，
// 删除成功后重新拉取列表；失败展示瞬时错误提示（均本地化）。
// 命名一律使用英文；注释默认中文。

import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useSession } from "../../auth/session";
import { useI18n } from "../../i18n";
import type { HistoryItem } from "../../types/chat";

// 组件属性：点击历史项时回调，交由上层把该问答（问题 + 答案 + 徽章/溯源）重放到聊天区
export interface SessionHistoryProps {
  onSelect: (item: HistoryItem) => void;
}

// 卡片相关内联样式（沿用项目内联样式风格）
const cardStyle: React.CSSProperties = {
  position: "relative",
  border: "1px solid #e5e7eb",
  borderRadius: "0.5rem",
  padding: "0.625rem 2rem 0.625rem 0.75rem", // 右侧留出删除按钮空间
  marginBottom: "0.5rem",
  background: "#ffffff",
  cursor: "pointer",
  transition: "background 0.15s, box-shadow 0.15s, border-color 0.15s",
};

const deleteBtnStyle: React.CSSProperties = {
  position: "absolute",
  top: "0.25rem",
  right: "0.25rem",
  width: "1.25rem",
  height: "1.25rem",
  lineHeight: "1.25rem",
  padding: 0,
  border: "none",
  borderRadius: "0.25rem",
  background: "transparent",
  color: "#9ca3af",
  fontSize: "0.875rem",
  cursor: "pointer",
  textAlign: "center",
};

// 历史会话列表组件
export function SessionHistory({ onSelect }: SessionHistoryProps) {
  const { t } = useI18n();
  // 受保护调用包装：遇 401 自动刷新并重试一次
  const { callWithRefresh } = useSession();
  // 历史条目（倒序由后端保证：created_at DESC）
  const [items, setItems] = useState<HistoryItem[]>([]);
  // 加载态：用于最小化的加载提示
  const [loading, setLoading] = useState<boolean>(true);
  // 错误态：拉取失败时展示降级提示，绝不让组件崩溃
  const [error, setError] = useState<boolean>(false);
  // 删除失败的瞬时错误提示（本地化），成功或下次操作时清除
  const [deleteError, setDeleteError] = useState<boolean>(false);
  // 悬停高亮的卡片 id（用于 subtle hover 效果）
  const [hoverId, setHoverId] = useState<number | null>(null);

  // 拉取历史列表：仅当前用户自己的历史（第 1 页，20 条），倒序由后端返回
  const reload = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await api.listHistory(1, 20);
      setItems(res.items);
    } catch {
      // 捕获网络/鉴权等异常，标记错误态而非抛出，保证健壮性
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 删除单条历史：阻止冒泡（不触发重放）→ 二次确认 → 调用删除 → 重新拉取
  const handleDelete = useCallback(
    async (e: React.MouseEvent, item: HistoryItem) => {
      // 阻止冒泡，避免触发卡片主体的 onSelect 重放
      e.stopPropagation();
      setDeleteError(false);
      // 二次确认（本地化）；用户取消则直接返回
      const ok = globalThis.confirm?.(t("history.confirmDelete"));
      if (!ok) return;
      try {
        // 删除受保护调用，遇 401 自动刷新重试
        await callWithRefresh(() => api.deleteHistory(item.id));
        // 删除成功后重新拉取列表
        await reload();
      } catch {
        // 失败展示瞬时本地化错误提示（不崩溃）
        setDeleteError(true);
      }
    },
    [callWithRefresh, reload, t]
  );

  // 加载中：最小化提示
  if (loading) {
    return <div className="session-history session-history--loading">{t("history.loading")}</div>;
  }

  // 拉取失败：降级提示（不崩溃）
  if (error) {
    return <div className="session-history session-history--error">{t("history.error")}</div>;
  }

  // 空态：暂无历史
  if (items.length === 0) {
    return <div className="session-history session-history--empty">{t("history.empty")}</div>;
  }

  // 正常态：每条历史以带边框卡片展示；点击卡片主体重放该条问答
  return (
    <div className="session-history">
      {/* 删除失败的瞬时错误提示（本地化） */}
      {deleteError && (
        <div
          role="alert"
          className="session-history__delete-error"
          style={{ color: "#b91c1c", fontSize: "0.75rem", marginBottom: "0.5rem" }}
        >
          {t("history.deleteFailed")}
        </div>
      )}
      {items.map((it) => (
        <div
          key={it.id}
          className="session-history__card"
          style={{
            ...cardStyle,
            // subtle hover：悬停时轻微高亮背景与边框
            ...(hoverId === it.id ? { background: "#f9fafb", borderColor: "#d1d5db" } : {}),
          }}
          onClick={() => onSelect(it)}
          onMouseEnter={() => setHoverId(it.id)}
          onMouseLeave={() => setHoverId((prev) => (prev === it.id ? null : prev))}
          title={it.createdAt}
        >
          {/* 删除按钮：右上角，阻止冒泡，避免触发重放 */}
          <button
            type="button"
            className="session-history__delete"
            style={deleteBtnStyle}
            aria-label={t("history.deleteAria")}
            title={t("history.delete")}
            onClick={(e) => void handleDelete(e, it)}
          >
            ×
          </button>

          {/* 卡片主体：问题摘要（点击重放） */}
          <div className="session-history__question" style={{ fontSize: "0.8125rem", color: "#111827", paddingRight: "0.25rem" }}>
            {it.question}
          </div>

          {/* 元信息行：创建时间 + 等级指示 */}
          <div
            className="session-history__meta"
            style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.375rem", fontSize: "0.6875rem", color: "#6b7280" }}
          >
            <span className="session-history__time">{new Date(it.createdAt).toLocaleString()}</span>
            {/* 等级徽章标记：YES -> ok，其余 -> warn */}
            <span className={`badge badge-${it.grade === "YES" ? "ok" : "warn"}`} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default SessionHistory;
