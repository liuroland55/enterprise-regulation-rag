// desktop/src/components/admin/AdvancedSettings.tsx
// 高级设置（仅 admin 可见、可配置的全局/默认调参）：
// - topK（number）：检索召回数量的默认值。
// - enableReranker（boolean）：重排序开关，标注为“未来能力（feature flag）”。
// - enableHybridSearch（boolean）：混合检索开关，标注为“未来能力（feature flag）”。
// 说明：reranker / hybrid search 在当前 RAG 核心尚未实现，仅作为管理员特性开关存在；
//      API 可携带这些标志，但核心当前可忽略，直到后续实现。绝不修改 RAG 核心。
// 受控组件：通过 value + onChange 由父级管理状态。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";

// 高级设置状态：仅 admin 可配置的全局/默认调参
export interface AdvancedSettingsState {
  topK: number; // 检索召回数量的默认值（top_k）
  enableReranker: boolean; // 重排序开关（未来能力，核心当前可忽略）
  enableHybridSearch: boolean; // 混合检索开关（未来能力，核心当前可忽略）
}

// 高级设置组件属性（受控）
export interface AdvancedSettingsProps {
  value: AdvancedSettingsState; // 当前设置值（由父级持有）
  onChange: (next: AdvancedSettingsState) => void; // 值变更回调
  disabled?: boolean; // 可选：禁用所有输入（如非 admin 或保存中）
}

// 高级设置组件：渲染 top_k 数字输入 + 两个标注为“未来能力”的开关。
// 该组件为纯受控组件：自身不持有状态，所有变更通过 onChange 上抛。
export function AdvancedSettings({ value, onChange, disabled = false }: AdvancedSettingsProps) {
  const { t } = useI18n();
  // 更新 topK：解析为整数；非法输入回退为 0，交由父级做进一步约束
  const handleTopKChange = (raw: string) => {
    const parsed = Number.parseInt(raw, 10);
    const topK = Number.isNaN(parsed) ? 0 : parsed;
    onChange({ ...value, topK });
  };

  // 更新 reranker 开关（未来能力）
  const handleRerankerChange = (checked: boolean) => {
    onChange({ ...value, enableReranker: checked });
  };

  // 更新 hybrid search 开关（未来能力）
  const handleHybridSearchChange = (checked: boolean) => {
    onChange({ ...value, enableHybridSearch: checked });
  };

  return (
    <section className="advanced-settings" aria-label={t("advanced.ariaLabel")}>
      <h3 className="advanced-settings-title">{t("advanced.title")}</h3>

      {/* top_k：检索召回数量默认值 */}
      <div className="setting-row">
        <label className="setting-label" htmlFor="advanced-settings-top-k">
          {t("advanced.topK")}
        </label>
        <input
          id="advanced-settings-top-k"
          className="setting-input"
          type="number"
          min={1}
          step={1}
          value={value.topK}
          disabled={disabled}
          onChange={(e) => handleTopKChange(e.target.value)}
        />
      </div>

      {/* reranker：未来能力（feature flag），核心当前可忽略 */}
      <div className="setting-row">
        <label className="setting-label" htmlFor="advanced-settings-reranker">
          {t("advanced.reranker")}
          <span className="future-flag" data-future-flag="true">
            {t("advanced.futureFlag")}
          </span>
        </label>
        <input
          id="advanced-settings-reranker"
          className="setting-toggle"
          type="checkbox"
          checked={value.enableReranker}
          disabled={disabled}
          onChange={(e) => handleRerankerChange(e.target.checked)}
        />
        <p className="setting-hint">
          {t("advanced.featureHint")}
        </p>
      </div>

      {/* hybrid search：未来能力（feature flag），核心当前可忽略 */}
      <div className="setting-row">
        <label className="setting-label" htmlFor="advanced-settings-hybrid">
          {t("advanced.hybrid")}
          <span className="future-flag" data-future-flag="true">
            {t("advanced.futureFlag")}
          </span>
        </label>
        <input
          id="advanced-settings-hybrid"
          className="setting-toggle"
          type="checkbox"
          checked={value.enableHybridSearch}
          disabled={disabled}
          onChange={(e) => handleHybridSearchChange(e.target.checked)}
        />
        <p className="setting-hint">
          {t("advanced.featureHint")}
        </p>
      </div>
    </section>
  );
}

export default AdvancedSettings;
