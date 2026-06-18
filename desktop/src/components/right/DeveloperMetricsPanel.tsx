// desktop/src/components/right/DeveloperMetricsPanel.tsx
// 开发者指标面板：展示工程指标（召回片段数 chunks、原始相似度分数 rawScores、
// token 成本 tokenCost、端到端延迟 latencyMs、检索耗时 retrievalMs）。
// 数据来自 AskResponse.metrics（后端可选扩展字段，需扩展后才会返回）。
// 关键约束：可见性由父组件按 role + developerMode 门控（仅 admin + 开发者模式）；
// 但本面板自身在 answer 为空或 metrics 缺失时也应安全降级（不渲染敏感工程信息）。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";
import type { AskResponse } from "../../types/chat";

// 开发者指标面板组件属性
export interface DeveloperMetricsPanelProps {
  answer: AskResponse | null; // 当前激活的回答；为空时不渲染
}

// 开发者指标面板组件：渲染 answer.metrics（若存在）。
export function DeveloperMetricsPanel({ answer }: DeveloperMetricsPanelProps) {
  const { t } = useI18n();
  // answer 为空或后端未返回 metrics 时安全降级：不渲染任何工程指标
  const metrics = answer?.metrics;
  if (!metrics) return null;

  return (
    <div className="developer-metrics-panel">
      <h4 className="title">{t("devMetrics.title")}</h4>
      <ul className="metrics">
        <li className="metric metric-chunks">
          {t("devMetrics.chunks", { n: metrics.retrievedChunks })}
        </li>
        <li className="metric metric-raw-scores">
          {t("devMetrics.rawScores", { scores: metrics.rawScores.join(t("common.listSeparator")) })}
        </li>
        {metrics.tokenCost !== undefined && (
          <li className="metric metric-token-cost">
            {t("devMetrics.tokenCost", { n: metrics.tokenCost })}
          </li>
        )}
        {metrics.latencyMs !== undefined && (
          <li className="metric metric-latency">
            {t("devMetrics.latency", { n: metrics.latencyMs })}
          </li>
        )}
        {metrics.retrievalMs !== undefined && (
          <li className="metric metric-retrieval">
            {t("devMetrics.retrieval", { n: metrics.retrievalMs })}
          </li>
        )}
      </ul>
    </div>
  );
}

export default DeveloperMetricsPanel;
