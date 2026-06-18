// desktop/src/components/admin/UserManagement.tsx
// 用户管理（仅 admin）：用户列表 + 创建 + 行内编辑（position/tasks/role）+ 删除。
// - 挂载时 api.listUsers() 拉取用户表（username/role/position/tasks/active）。
// - 创建表单：username/password/role(select)/position/tasks（逗号或换行分隔 → string[]）。
//   409 -> “用户名已存在”；422 -> 密码策略提示。
// - 行内编辑 position/tasks/role -> api.updateUser；删除 -> api.deleteUser（带确认）。
// - 所有受保护调用统一经 useSession().callWithRefresh 包装（遇 401 自动刷新重试）。
//   变更后刷新列表。
// 自包含、可独立编译；样式沿用项目内联样式风格。
// 命名一律使用英文；注释默认中文。

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import { useSession } from "../../auth/session";
import { useI18n } from "../../i18n";
import type { I18nContextValue } from "../../i18n";
import type { UserOut } from "../../types/chat";

// 角色选项（与后端约定一致）
const ROLE_OPTIONS = ["employee", "admin"] as const;

// 将“逗号或换行分隔”的文本解析为去空白、去空项的字符串数组
function parseTasks(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// 将 ApiError 映射为可读的本地化文案（用户管理场景，通过传入的 t 函数翻译）
function toUserErrorMessage(
  err: unknown,
  context: "load" | "create" | "update" | "delete",
  t: I18nContextValue["t"]
): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return t("users.error.conflict");
    if (err.status === 422) return t("users.error.weakPassword");
    if (err.status === 404) return t("users.error.notFound");
    if (err.status === 403) return t("users.error.forbidden");
    return t("users.error.statusCode", { status: err.status });
  }
  const fallbackKey: Record<typeof context, string> = {
    load: "users.error.load",
    create: "users.error.create",
    update: "users.error.update",
    delete: "users.error.delete",
  };
  return t(fallbackKey[context]);
}

// ---------------------------------------------------------------------------
// 内联样式常量（沿用项目内联样式风格）
// ---------------------------------------------------------------------------
const styles = {
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
  input: {
    padding: "0.375rem 0.5rem",
    border: "1px solid #d1d5db",
    borderRadius: "0.375rem",
    fontSize: "0.8125rem",
    width: "100%",
    boxSizing: "border-box" as const,
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
  subtleBtn: {
    padding: "0.3rem 0.6rem",
    background: "#f3f4f6",
    color: "#374151",
    border: "1px solid #d1d5db",
    borderRadius: "0.375rem",
    fontSize: "0.75rem",
    cursor: "pointer",
  } as const,
};

// 行编辑草稿：每行可独立进入编辑（position/tasks/role）
interface EditDraft {
  position: string;
  tasksText: string; // 逗号/换行分隔文本
  role: string;
}

export function UserManagement() {
  const { callWithRefresh } = useSession();
  const { t } = useI18n();

  // 用户列表与加载态
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 创建表单状态
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<string>("employee");
  const [newPosition, setNewPosition] = useState("");
  const [newTasksText, setNewTasksText] = useState("");
  const [createPending, setCreatePending] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  // 是否显示新建用户的密码明文
  const [showNewPassword, setShowNewPassword] = useState(false);

  // 行编辑状态
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [rowSuccess, setRowSuccess] = useState<string | null>(null);

  // 加载用户列表（经 callWithRefresh 包装）
  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const userList = await callWithRefresh(() => api.listUsers());
      setUsers(userList);
    } catch (err) {
      setLoadError(toUserErrorMessage(err, "load", t));
    } finally {
      setLoading(false);
    }
  }, [callWithRefresh, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 创建用户
  const handleCreate = async () => {
    if (createPending) return;
    setCreateError(null);
    setCreateSuccess(null);

    // 基础前置校验（后端仍会强制密码策略）
    if (newUsername.trim() === "" || newPassword === "") {
      setCreateError(t("users.error.missingFields"));
      return;
    }

    setCreatePending(true);
    try {
      await callWithRefresh(() =>
        api.createUser({
          username: newUsername.trim(),
          password: newPassword,
          role: newRole,
          position: newPosition.trim(),
          tasks: parseTasks(newTasksText),
        })
      );
      setCreateSuccess(t("users.createSuccess", { name: newUsername.trim() }));
      // 重置表单
      setNewUsername("");
      setNewPassword("");
      setNewRole("employee");
      setNewPosition("");
      setNewTasksText("");
      await reload();
    } catch (err) {
      setCreateError(toUserErrorMessage(err, "create", t));
    } finally {
      setCreatePending(false);
    }
  };

  // 进入行编辑
  const startEdit = (user: UserOut) => {
    setRowError(null);
    setRowSuccess(null);
    setEditingId(user.id);
    setEditDraft({
      position: user.position,
      tasksText: user.tasks.join(", "),
      role: user.role,
    });
  };

  // 取消行编辑
  const cancelEdit = () => {
    setEditingId(null);
    setEditDraft(null);
  };

  // 保存行编辑（更新 position/tasks/role）
  const saveEdit = async (id: number) => {
    if (!editDraft) return;
    setRowError(null);
    setRowSuccess(null);
    try {
      await callWithRefresh(() =>
        api.updateUser(id, {
          position: editDraft.position.trim(),
          tasks: parseTasks(editDraft.tasksText),
          role: editDraft.role,
        })
      );
      setRowSuccess(t("users.updateSuccess"));
      setEditingId(null);
      setEditDraft(null);
      await reload();
    } catch (err) {
      setRowError(toUserErrorMessage(err, "update", t));
    }
  };

  // 删除用户（带确认）
  const handleDelete = async (user: UserOut) => {
    setRowError(null);
    setRowSuccess(null);
    const ok = globalThis.confirm?.(t("users.confirmDelete", { name: user.username }));
    if (!ok) return;
    try {
      await callWithRefresh(() => api.deleteUser(user.id));
      setRowSuccess(t("users.deleteSuccess", { name: user.username }));
      await reload();
    } catch (err) {
      setRowError(toUserErrorMessage(err, "delete", t));
    }
  };

  return (
    <div aria-label={t("admin.section.users")}>
      {loadError && (
        <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
          {loadError}
        </div>
      )}
      {rowError && (
        <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
          {rowError}
        </div>
      )}
      {rowSuccess && (
        <div style={{ color: "#047857", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
          {rowSuccess}
        </div>
      )}

      {/* 用户表 */}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>{t("users.col.id")}</th>
            <th style={styles.th}>{t("users.col.username")}</th>
            <th style={styles.th}>{t("users.col.role")}</th>
            <th style={styles.th}>{t("users.col.position")}</th>
            <th style={styles.th}>{t("users.col.tasks")}</th>
            <th style={styles.th}>{t("users.col.status")}</th>
            <th style={styles.th}>{t("users.col.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {users.length === 0 && !loading && (
            <tr>
              <td style={styles.td} colSpan={7}>
                {t("users.empty")}
              </td>
            </tr>
          )}
          {users.map((user) => {
            const isEditing = editingId === user.id && editDraft !== null;
            return (
              <tr key={user.id}>
                <td style={styles.td}>{user.id}</td>
                <td style={styles.td}>{user.username}</td>
                <td style={styles.td}>
                  {isEditing ? (
                    <select
                      value={editDraft.role}
                      onChange={(e) => setEditDraft({ ...editDraft, role: e.target.value })}
                      style={styles.input}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  ) : (
                    user.role
                  )}
                </td>
                <td style={styles.td}>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editDraft.position}
                      onChange={(e) => setEditDraft({ ...editDraft, position: e.target.value })}
                      style={styles.input}
                    />
                  ) : (
                    user.position || t("users.placeholder.dash")
                  )}
                </td>
                <td style={styles.td}>
                  {isEditing ? (
                    <textarea
                      value={editDraft.tasksText}
                      onChange={(e) => setEditDraft({ ...editDraft, tasksText: e.target.value })}
                      rows={2}
                      placeholder={t("users.tasksPlaceholder")}
                      style={{ ...styles.input, resize: "vertical" }}
                    />
                  ) : user.tasks.length > 0 ? (
                    user.tasks.join(t("common.listSeparator"))
                  ) : (
                    t("users.placeholder.dash")
                  )}
                </td>
                <td style={styles.td}>{user.isActive ? t("users.status.active") : t("users.status.inactive")}</td>
                <td style={styles.td}>
                  {isEditing ? (
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button type="button" style={styles.primaryBtn} onClick={() => void saveEdit(user.id)}>
                        {t("users.save")}
                      </button>
                      <button type="button" style={styles.subtleBtn} onClick={cancelEdit}>
                        {t("users.cancel")}
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button type="button" style={styles.subtleBtn} onClick={() => startEdit(user)}>
                        {t("users.edit")}
                      </button>
                      <button type="button" style={styles.dangerBtn} onClick={() => void handleDelete(user)}>
                        {t("users.delete")}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* 创建用户表单 */}
      <div style={{ marginTop: "1.25rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: 600, margin: "0 0 0.5rem" }}>{t("users.create.title")}</h4>
        {createError && (
          <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
            {createError}
          </div>
        )}
        {createSuccess && (
          <div style={{ color: "#047857", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
            {createSuccess}
          </div>
        )}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
            gap: "0.75rem",
            alignItems: "start",
          }}
        >
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <span style={{ fontSize: "0.75rem", color: "#374151" }}>{t("users.field.username")}</span>
            <input type="text" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} style={styles.input} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <span style={{ fontSize: "0.75rem", color: "#374151" }}>{t("users.field.password")}</span>
            {/* 输入框 + 显示/隐藏切换按钮 */}
            <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
              <input
                type={showNewPassword ? "text" : "password"}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={{ ...styles.input, paddingRight: "3.25rem" }}
              />
              <button
                type="button"
                onClick={() => setShowNewPassword((v) => !v)}
                aria-label={showNewPassword ? t("common.hidePassword") : t("common.showPassword")}
                aria-pressed={showNewPassword}
                tabIndex={-1}
                style={{
                  position: "absolute",
                  right: "0.375rem",
                  padding: "0.15rem 0.4rem",
                  fontSize: "0.7rem",
                  color: "#2563eb",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                {showNewPassword ? t("common.hide") : t("common.show")}
              </button>
            </div>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <span style={{ fontSize: "0.75rem", color: "#374151" }}>{t("users.field.role")}</span>
            <select value={newRole} onChange={(e) => setNewRole(e.target.value)} style={styles.input}>
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            {/* 提示：选择 admin 即可创建管理员账号（现有账号亦可在行内编辑中提升为 admin） */}
            <span style={{ fontSize: "0.6875rem", color: "#6b7280" }}>{t("users.create.roleHint")}</span>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <span style={{ fontSize: "0.75rem", color: "#374151" }}>{t("users.field.position")}</span>
            <input type="text" value={newPosition} onChange={(e) => setNewPosition(e.target.value)} style={styles.input} />
          </label>
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.25rem",
              gridColumn: "1 / -1",
            }}
          >
            <span style={{ fontSize: "0.75rem", color: "#374151" }}>{t("users.field.tasks")}</span>
            <textarea
              value={newTasksText}
              onChange={(e) => setNewTasksText(e.target.value)}
              rows={2}
              style={{ ...styles.input, resize: "vertical" }}
            />
          </label>
        </div>
        <div style={{ marginTop: "0.75rem" }}>
          <button
            type="button"
            style={{
              ...styles.primaryBtn,
              background: createPending ? "#9ca3af" : "#2563eb",
              cursor: createPending ? "not-allowed" : "pointer",
            }}
            disabled={createPending}
            onClick={() => void handleCreate()}
          >
            {createPending ? t("users.create.creating") : t("users.create.button")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default UserManagement;
