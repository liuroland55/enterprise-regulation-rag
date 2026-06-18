// desktop/src/components/left/ProfileCard.tsx
// 用户画像卡（左列顶部）：突出展示当前登录员工的职位（position）+ 任务（tasks）。
// 这是产品核心卖点的可视化呼应——“检索结果依据岗位职责定制”。
// 对 employee 角色一律只读（无编辑控件）；职位/任务的维护由管理后台负责（任务 11.x）。
// 数据通过 props 注入以保持组件解耦、可独立编译；Chat 页面后续（任务 12.1）传入真实数据。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";

// 画像卡属性：职位、任务列表与角色由调用方注入
export interface ProfileCardProps {
  // 职位（职位名称），可能为空字符串（档案未填写时）
  position: string;
  // 任务列表，可能为空数组
  tasks: string[];
  // 当前用户角色（"admin" | "employee"）；employee 时一律只读
  role: string;
}

// 用户画像卡组件
export function ProfileCard({ position, tasks, role }: ProfileCardProps) {
  const { t } = useI18n();
  // 仅保留非空白任务条目，避免渲染空项
  const visibleTasks = tasks.filter((task) => task && task.trim().length > 0);

  // employee 角色为只读视图（无编辑入口）；其余角色当前同样只读（编辑见管理后台）
  const isReadOnly = role === "employee";

  return (
    <section
      aria-label="profile-card"
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        // 以柔和的强调色背景突出画像卡，呼应“基于岗位筛条例”的核心卖点
        background: "linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%)",
        padding: "0.875rem",
        marginBottom: "1rem",
        boxSizing: "border-box",
      }}
    >
      {/* 标题区：标识这是“岗位画像”，并以小标签提示只读 */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "0.625rem",
        }}
      >
        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#4338ca" }}>
          {t("profile.title")}
        </span>
        {isReadOnly && (
          <span
            aria-label="read-only-badge"
            style={{
              fontSize: "0.6875rem",
              color: "#6b7280",
              border: "1px solid #d1d5db",
              borderRadius: 9999,
              padding: "0.0625rem 0.5rem",
              background: "#ffffff",
            }}
          >
            {t("profile.readOnly")}
          </span>
        )}
      </header>

      {/* 职位：核心字段，醒目展示 */}
      <div style={{ marginBottom: "0.75rem" }}>
        <div
          style={{
            fontSize: "0.6875rem",
            color: "#6b7280",
            marginBottom: "0.125rem",
          }}
        >
          {t("profile.position")}
        </div>
        <div
          aria-label="profile-position"
          style={{ fontSize: "1.0625rem", fontWeight: 700, color: "#111827" }}
        >
          {/* 档案未填写职位时给出占位文案 */}
          {position.trim() ? position : t("profile.noPosition")}
        </div>
      </div>

      {/* 任务：以列表呈现，强调“检索将围绕这些职责定制” */}
      <div>
        <div
          style={{
            fontSize: "0.6875rem",
            color: "#6b7280",
            marginBottom: "0.25rem",
          }}
        >
          {t("profile.mainTasks")}
        </div>
        {visibleTasks.length > 0 ? (
          <ul
            aria-label="profile-tasks"
            style={{
              margin: 0,
              paddingLeft: "1.1rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.125rem",
            }}
          >
            {visibleTasks.map((task, index) => (
              <li
                key={`${index}-${task}`}
                style={{ fontSize: "0.8125rem", color: "#374151" }}
              >
                {task}
              </li>
            ))}
          </ul>
        ) : (
          // 无任务时的占位文案
          <div style={{ fontSize: "0.8125rem", color: "#9ca3af" }}>{t("profile.noTasks")}</div>
        )}
      </div>

      {/* 卖点提示：说明岗位画像如何影响检索 */}
      <p
        style={{
          margin: "0.75rem 0 0",
          fontSize: "0.6875rem",
          color: "#6366f1",
          lineHeight: 1.4,
        }}
      >
        {t("profile.hint")}
      </p>
    </section>
  );
}

export default ProfileCard;
