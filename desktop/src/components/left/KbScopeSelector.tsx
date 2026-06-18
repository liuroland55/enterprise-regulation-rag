// desktop/src/components/left/KbScopeSelector.tsx
// 知识库选择器（左列）：在可用的知识库范围中进行多选（可选，可一个都不选）。
// 受控组件：可选项与已选值均由 props 注入，选择变化通过 onChange 回调上抛。
// 组件自包含、可独立编译；与 Chat 页面的接线由后续任务（12.1）完成。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";

// 单个知识库范围选项
export interface KbScopeOption {
  // 选项唯一标识（与后端知识库条目 id 对齐）
  id: string;
  // 选项展示名称（如条例集合 / 文档分类名称）
  label: string;
}

// 知识库选择器属性
export interface KbScopeSelectorProps {
  // 可用的知识库范围选项列表
  options: KbScopeOption[];
  // 已选中的选项 id 列表（受控值）；空数组表示未选择任何范围
  selectedIds: string[];
  // 选择变化回调：上抛最新的已选 id 列表
  onChange: (selectedIds: string[]) => void;
}

// 知识库范围多选组件
export function KbScopeSelector({
  options,
  selectedIds,
  onChange,
}: KbScopeSelectorProps) {
  const { t } = useI18n();
  // 以 Set 加速选中判断
  const selectedSet = new Set(selectedIds);

  // 切换单个选项的选中状态，并保持原有顺序输出最新选中列表
  const toggle = (id: string) => {
    const next = new Set(selectedSet);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    // 依据 options 顺序整理输出，保证结果稳定可预测
    const ordered = options.map((o) => o.id).filter((oid) => next.has(oid));
    onChange(ordered);
  };

  return (
    <section
      aria-label="kb-scope-selector"
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: "0.875rem",
        marginBottom: "1rem",
        boxSizing: "border-box",
      }}
    >
      {/* 标题区：标识知识库选择，并提示“可选” */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "0.625rem",
        }}
      >
        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#374151" }}>
          {t("kbScope.title")}
        </span>
        <span style={{ fontSize: "0.6875rem", color: "#9ca3af" }}>{t("kbScope.optional")}</span>
      </header>

      {/* 选项列表；无可用选项时给出占位文案 */}
      {options.length > 0 ? (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.25rem",
          }}
        >
          {options.map((option) => {
            const checked = selectedSet.has(option.id);
            return (
              <li key={option.id}>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.8125rem",
                    color: "#374151",
                    cursor: "pointer",
                    padding: "0.25rem 0.375rem",
                    borderRadius: 4,
                    background: checked ? "#eff6ff" : "transparent",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(option.id)}
                    aria-label={`kb-scope-option-${option.id}`}
                  />
                  <span>{option.label}</span>
                </label>
              </li>
            );
          })}
        </ul>
      ) : (
        <div style={{ fontSize: "0.8125rem", color: "#9ca3af" }}>
          {t("kbScope.empty")}
        </div>
      )}

      {/* 选择状态提示：未选择时说明默认检索全部范围 */}
      <p
        style={{
          margin: "0.625rem 0 0",
          fontSize: "0.6875rem",
          color: "#6b7280",
          lineHeight: 1.4,
        }}
      >
        {selectedIds.length > 0
          ? t("kbScope.selected", { n: selectedIds.length })
          : t("kbScope.none")}
      </p>
    </section>
  );
}

export default KbScopeSelector;
