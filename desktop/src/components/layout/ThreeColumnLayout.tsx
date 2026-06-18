// desktop/src/components/layout/ThreeColumnLayout.tsx
// 通用三栏布局骨架（左 / 中 / 右），右列可折叠。
// 本组件仅负责布局结构与折叠交互，不感知任何业务内容，
// 三列内容通过 ReactNode 插槽（slot）由调用方注入。
// 命名一律使用英文；注释默认中文。

import { useState, type ReactNode } from "react";

// 三栏布局属性：左/中/右三列均为可注入的 ReactNode 插槽
export interface ThreeColumnLayoutProps {
  // 左列内容（如：用户画像卡 / 知识库选择 / 历史会话）
  left: ReactNode;
  // 中列内容（如：聊天窗口 + 可信度徽章）
  middle: ReactNode;
  // 右列内容（如：溯源面板 / 开发者指标面板）
  right: ReactNode;
  // 右列是否可折叠；为 true 时渲染折叠开关，默认 false（始终展开）
  rightCollapsible?: boolean;
}

// 通用三栏骨架组件
export function ThreeColumnLayout({
  left,
  middle,
  right,
  rightCollapsible = false,
}: ThreeColumnLayoutProps) {
  // 右列折叠状态的本地 state；初始为展开
  const [rightCollapsed, setRightCollapsed] = useState(false);

  // 仅当允许折叠且当前处于折叠态时，右列才隐藏内容
  const isRightHidden = rightCollapsible && rightCollapsed;

  return (
    <div
      style={{
        display: "flex",
        height: "100%",
        width: "100%",
        boxSizing: "border-box",
      }}
    >
      {/* 左列 */}
      <aside
        aria-label="left-column"
        style={{
          flex: "0 0 280px",
          minWidth: 240,
          borderRight: "1px solid #e5e7eb",
          overflowY: "auto",
          padding: "1rem",
          boxSizing: "border-box",
        }}
      >
        {left}
      </aside>

      {/* 中列：占据剩余空间 */}
      <section
        aria-label="middle-column"
        style={{
          flex: "1 1 auto",
          minWidth: 320,
          overflowY: "auto",
          padding: "1rem",
          boxSizing: "border-box",
        }}
      >
        {middle}
      </section>

      {/* 右列：可折叠 */}
      <aside
        aria-label="right-column"
        style={{
          flex: isRightHidden ? "0 0 40px" : "0 0 340px",
          minWidth: isRightHidden ? 40 : 300,
          borderLeft: "1px solid #e5e7eb",
          overflowY: "auto",
          padding: isRightHidden ? "0.5rem 0.25rem" : "1rem",
          boxSizing: "border-box",
          transition: "flex-basis 0.2s ease",
        }}
      >
        {/* 折叠开关：仅在允许折叠时渲染 */}
        {rightCollapsible && (
          <button
            type="button"
            onClick={() => setRightCollapsed((prev) => !prev)}
            aria-expanded={!rightCollapsed}
            aria-label={rightCollapsed ? "expand-right-column" : "collapse-right-column"}
            style={{
              cursor: "pointer",
              marginBottom: "0.75rem",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              background: "#f9fafb",
              padding: "0.25rem 0.5rem",
            }}
          >
            {/* 折叠时显示展开箭头，展开时显示折叠箭头 */}
            {rightCollapsed ? "«" : "»"}
          </button>
        )}

        {/* 折叠态下不渲染右列内容，仅保留窄条与开关 */}
        {!isRightHidden && right}
      </aside>
    </div>
  );
}

export default ThreeColumnLayout;
