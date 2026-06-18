// desktop/src/components/middle/ConfidenceBadge.tsx
// 可信度徽章：由 RAG 的 grade + iterations 推导人类可读的可信度（高/中/低），
// 绝不展示原始分数。
// - grade !== "YES"：渲染 低 + 人工确认提示（"⚠ 未找到明确依据，建议人工确认"）。
// - grade === "YES"：渲染 "✓ 已核验，依据 N 条条例"。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";
import type { ConfidenceLevel } from "../../types/chat";

// 与 RAG 核心的 max_iterations 对齐：迭代上限
const MAX_ITERATIONS = 3;

// 将内部可信度等级（高/中/低）映射为本地化字典 key（绝不改变内部 token 值）
export function confidenceLevelKey(level: ConfidenceLevel): string {
  return level === "高" ? "confidence.high" : level === "中" ? "confidence.medium" : "confidence.low";
}

// 将 RAG 的 grade + iterations 映射为人类可读的可信度等级，绝不暴露原始分数。
// 该函数为纯函数，便于在 task 11.5 中用 fast-check 做属性测试。
export function deriveConfidence(grade: string, iterations: number): ConfidenceLevel {
  // 未找到明确依据：grade 非 "YES" 一律视为 低
  if (grade?.toUpperCase() !== "YES") return "低";
  // 已核验：迭代越少越说明一次命中，置信度越高；接近上限说明反复修正
  return iterations <= 1 ? "高" : iterations < MAX_ITERATIONS ? "中" : "中";
}

// 可信度徽章组件属性
export interface ConfidenceBadgeProps {
  grade: string; // RAG 的判定结果："YES" | "NO"
  iterations: number; // RAG 的迭代次数
  sourceCount: number; // 依据条例数量（来源卡片数）
}

// 可信度徽章组件：仅依据 grade + iterations + sourceCount 渲染，不暴露任何原始分数
export function ConfidenceBadge({ grade, iterations, sourceCount }: ConfidenceBadgeProps) {
  const { t } = useI18n();
  const level = deriveConfidence(grade, iterations);
  const verified = grade?.toUpperCase() === "YES";
  // 已核验：显示“✓ 已核验，依据 N 条条例”；未核验：显示“⚠ 未找到明确依据，建议人工确认”
  const label = verified
    ? t("badge.verified", { n: sourceCount })
    : t("badge.unverified");
  // 本地化的可信度等级显示文案（内部 token 与 className 后缀保持不变）
  const localizedLevel = t(confidenceLevelKey(level));
  return (
    <span
      className={`badge badge-${level}`}
      title={t("confidence.title", { level: localizedLevel })}
      data-confidence={level}
    >
      {label}
    </span>
  );
}

export default ConfidenceBadge;
