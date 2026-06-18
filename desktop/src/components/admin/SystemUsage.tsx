// desktop/src/components/admin/SystemUsage.tsx
// 系统监控 / 用量统计（管理员聚合视图）：
// - 以聚合方式呈现系统用量与成本，而非面向员工的逐条消息。
// - token cost / latency 在 CLOUD 模式下有实际意义；在 LOCAL（Ollama）模式下仅供参考。
// 数据来源：通过 props 接收（自包含、可编译）；实际数据接线留待后续任务。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";

// 模型运行模式：与后端 settings 的 CLOUD/LOCAL 对齐
export type ModelMode = "CLOUD" | "LOCAL";

// 系统用量聚合数据（管理员视角）
export interface SystemUsageData {
  mode: ModelMode; // 当前模型模式（CLOUD / LOCAL）
  totalQueries: number; // 累计查询次数
  totalUsers: number; // 活跃/累计用户数
  totalTokens?: number; // 累计 token 用量（LOCAL 仅供参考）
  totalCost?: number; // 累计成本（CLOUD 有意义；LOCAL 仅供参考）
  avgLatencyMs?: number; // 平均端到端延迟（CLOUD 有意义；LOCAL 仅供参考）
}

// 系统监控组件属性
export interface SystemUsageProps {
  usage?: SystemUsageData; // 可选用量数据；未提供时展示占位（数据接线留后续）
}

// 数字格式化：未提供数值时显示占位符 "—"
function formatNumber(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

// 成本格式化：未提供时显示占位符 "—"
function formatCost(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toFixed(4)}`;
}

// 系统监控 / 用量统计组件：渲染管理员聚合视图，并依据模式标注 cost/latency 的含义。
// 该组件自包含：无 props 时也可编译并渲染占位内容。
export function SystemUsage({ usage }: SystemUsageProps) {
  const { t } = useI18n();
  const mode: ModelMode = usage?.mode ?? "LOCAL";
  const isCloud = mode === "CLOUD";

  // 依据模式说明 token cost / latency 的含义（CLOUD 有意义；LOCAL 仅供参考）
  const costLatencyNote = isCloud ? t("system.note.cloud") : t("system.note.local");
  // LOCAL 模式下的“仅供参考”后缀
  const referenceSuffix = isCloud ? "" : t("system.referenceSuffix");

  return (
    <section className="system-usage" aria-label={t("system.ariaLabel")}>
      <h3 className="system-usage-title">{t("system.title")}</h3>

      {/* 当前模型模式 */}
      <div className="usage-mode" data-mode={mode}>
        {t("system.currentMode", { mode })}
      </div>

      {/* 聚合指标 */}
      <dl className="usage-metrics">
        <div className="usage-metric">
          <dt>{t("system.metric.totalQueries")}</dt>
          <dd>{formatNumber(usage?.totalQueries)}</dd>
        </div>
        <div className="usage-metric">
          <dt>{t("system.metric.totalUsers")}</dt>
          <dd>{formatNumber(usage?.totalUsers)}</dd>
        </div>
        <div className="usage-metric">
          <dt>{t("system.metric.totalTokens")}{referenceSuffix}</dt>
          <dd>{formatNumber(usage?.totalTokens)}</dd>
        </div>
        <div className="usage-metric">
          <dt>{t("system.metric.totalCost")}{referenceSuffix}</dt>
          <dd>{formatCost(usage?.totalCost)}</dd>
        </div>
        <div className="usage-metric">
          <dt>{t("system.metric.avgLatency")}{referenceSuffix}</dt>
          <dd>{usage?.avgLatencyMs === undefined ? "—" : `${usage.avgLatencyMs} ms`}</dd>
        </div>
      </dl>

      {/* 模式相关说明：明确 cost/latency 在不同模式下的含义 */}
      <p className="usage-note" data-mode-note={mode}>
        {costLatencyNote}
      </p>

      {/* 数据接线留待后续任务：无 usage 时给出明确提示 */}
      {usage === undefined && (
        <p className="usage-placeholder">{t("system.placeholder")}</p>
      )}
    </section>
  );
}

export default SystemUsage;
