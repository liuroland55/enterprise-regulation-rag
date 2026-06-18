// desktop/src/components/right/SourcePanel.tsx
// 溯源面板：渲染依据卡片（条例标题 title、章/节 section、原文摘录 excerpt、
// 相关性标签 高/中/低）。
// 关键约束：绝不向用户展示原始 cosine 分数，仅以人类可读的相关性等级表达可信度。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";
import { confidenceLevelKey } from "../middle/ConfidenceBadge";
import type { ConfidenceLevel, SourceCard } from "../../types/chat";

// 将原始 cosine 相似度分数翻译为人类可读的相关性等级（员工不可见原始分数）。
// 该函数为纯函数，便于在 task 11.7 中用 fast-check 做属性测试。
// 单调性：分数越高，相关性等级不会降低（score >= 0.75 → 高；>= 0.5 → 中；否则 低）。
export function relevanceFromScore(score: number): ConfidenceLevel {
  if (score >= 0.75) return "高";
  if (score >= 0.5) return "中";
  return "低";
}

// 溯源面板组件属性
export interface SourcePanelProps {
  sources: SourceCard[]; // 依据卡片列表（相关性已为 高/中/低，不含原始分数）
}

// 溯源面板组件：逐条渲染依据卡片，仅展示相关性等级标签，绝不暴露原始分数
export function SourcePanel({ sources }: SourcePanelProps) {
  const { t } = useI18n();
  // 渲染依据卡片：条例标题、章/节、原文摘录、相关性标签（高/中/低）
  return (
    <div className="source-panel">
      {sources.map((s, i) => (
        <article key={i} className="source-card">
          <h4 className="title">{s.title}</h4>
          <p className="section">{s.section}</p>
          <blockquote className="excerpt">{s.excerpt}</blockquote>
          <span
            className={`relevance relevance-${s.relevance}`}
            data-relevance={s.relevance}
          >
            {t("source.relevance", { level: t(confidenceLevelKey(s.relevance)) })}
          </span>
        </article>
      ))}
    </div>
  );
}

export default SourcePanel;
