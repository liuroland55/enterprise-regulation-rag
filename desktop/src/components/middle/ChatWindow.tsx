// desktop/src/components/middle/ChatWindow.tsx
// 聊天窗口：消息流 + 输入框。
// - 展示用户/助手消息；
// - 助手消息下方渲染 ConfidenceBadge（仅依据 grade + iterations + sourceCount，不暴露原始分数）。
// 本组件自包含：输入框使用本地受控 state，提交时通过 onSubmit 回调上抛问题。
// 命名一律使用英文；注释默认中文。

import { useState, type FormEvent } from "react";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { useI18n } from "../../i18n";
import type { I18nContextValue } from "../../i18n";
import type { ThinkingStep } from "../../types/chat";

// 将单步思考事件渲染为人类可读的本地化文案（通过传入的 t 函数翻译）
function thinkingStepLabel(step: ThinkingStep, t: I18nContextValue["t"]): string {
  switch (step.type) {
    case "retrieve":
      return t("chat.step.retrieve", { n: step.iteration, k: step.docs ?? 0 });
    case "generate":
      return step.grade === "YES"
        ? t("chat.step.generateYes", { n: step.iteration })
        : t("chat.step.generateNo", { n: step.iteration });
    case "rewrite":
      return t("chat.step.rewrite", { n: step.iteration });
    default:
      return t("chat.step.default");
  }
}

// 单条聊天消息：区分用户/助手；助手消息可携带用于徽章推导的 RAG 字段。
export interface ChatMessage {
  role: "user" | "assistant"; // 消息角色
  content: string; // 消息正文
  // 以下字段仅在 role === "assistant" 时有意义，用于推导可信度徽章
  grade?: string; // RAG 判定结果："YES" | "NO"
  iterations?: number; // RAG 迭代次数
  sourceCount?: number; // 依据条例数量
}

// 聊天窗口属性
export interface ChatWindowProps {
  // 消息流：按时间顺序排列的用户/助手消息
  messages: ChatMessage[];
  // 提交问题的回调；由调用方负责实际发起 /ask 请求
  onSubmit: (question: string) => void;
  // 是否处于加载态（如等待 /ask 响应）；用于禁用输入并提示
  loading?: boolean;
  // 是否正在“思考”（流式中）；为 true 时在消息流底部展示思考过程，完成后由调用方置 false 使其消失
  thinking?: boolean;
  // 实时思考步骤（检索/生成评分/重写）；仅在 thinking 为 true 时展示
  thinkingSteps?: ThinkingStep[];
}

// 闪动的 “thinking....” 指示器（纯 CSS 动画通过内联 keyframes 注入）
function ThinkingIndicator({ steps }: { steps: ThinkingStep[] }) {
  const { t } = useI18n();
  return (
    <div
      aria-label="thinking-indicator"
      aria-live="polite"
      style={{
        alignSelf: "flex-start",
        maxWidth: "80%",
        background: "#f8fafc",
        border: "1px dashed #cbd5e1",
        borderRadius: 8,
        padding: "0.625rem 0.75rem",
        color: "#475569",
        fontSize: "0.8125rem",
      }}
    >
      {/* 注入闪动动画的 keyframes（组件内联，便于自包含） */}
      <style>
        {`@keyframes rag2-blink { 0%,100% { opacity: .25 } 50% { opacity: 1 } }`}
      </style>
      <div style={{ fontWeight: 600, marginBottom: steps.length ? "0.375rem" : 0 }}>
        <span style={{ animation: "rag2-blink 1.2s ease-in-out infinite" }}>
          {t("chat.thinking")}
        </span>
      </div>
      {/* 实时步骤列表（思考完成后整块随 thinking=false 一起消失） */}
      {steps.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          {steps.map((s, i) => (
            <li key={i} style={{ lineHeight: 1.5 }}>
              {thinkingStepLabel(s, t)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// 聊天窗口组件
export function ChatWindow({
  messages,
  onSubmit,
  loading = false,
  thinking = false,
  thinkingSteps = [],
}: ChatWindowProps) {
  const { t } = useI18n();
  // 输入框本地受控 state
  const [input, setInput] = useState("");

  // 提交处理：去除首尾空白后非空才上抛，随后清空输入框
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = input.trim();
    if (!question || loading) return;
    onSubmit(question);
    setInput("");
  };

  return (
    <div
      aria-label="chat-window"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      {/* 消息流：占据剩余空间，可滚动 */}
      <div
        aria-label="message-list"
        style={{
          flex: "1 1 auto",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          paddingBottom: "0.75rem",
        }}
      >
        {messages.length === 0 ? (
          // 空状态占位
          <p style={{ color: "#9ca3af", textAlign: "center", marginTop: "2rem" }}>
            {t("chat.empty")}
          </p>
        ) : (
          messages.map((message, index) => {
            const isUser = message.role === "user";
            return (
              <div
                key={index}
                aria-label={isUser ? "user-message" : "assistant-message"}
                style={{
                  alignSelf: isUser ? "flex-end" : "flex-start",
                  maxWidth: "80%",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.375rem",
                }}
              >
                {/* 消息气泡 */}
                <div
                  style={{
                    background: isUser ? "#2563eb" : "#f3f4f6",
                    color: isUser ? "#ffffff" : "#111827",
                    borderRadius: 8,
                    padding: "0.5rem 0.75rem",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {message.content}
                </div>

                {/* 助手消息下方渲染可信度徽章：仅当存在 grade 时 */}
                {!isUser && message.grade !== undefined && (
                  <ConfidenceBadge
                    grade={message.grade}
                    iterations={message.iterations ?? 0}
                    sourceCount={message.sourceCount ?? 0}
                  />
                )}
              </div>
            );
          })
        )}

        {/* 思考过程：流式中展示 “thinking....” 与实时步骤；完成后由 thinking=false 整块消失 */}
        {thinking && <ThinkingIndicator steps={thinkingSteps} />}
      </div>

      {/* 输入区：表单提交（回车或点击按钮） */}
      <form
        onSubmit={handleSubmit}
        style={{
          display: "flex",
          gap: "0.5rem",
          borderTop: "1px solid #e5e7eb",
          paddingTop: "0.75rem",
        }}
      >
        <input
          type="text"
          aria-label="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("chat.inputPlaceholder")}
          disabled={loading}
          style={{
            flex: "1 1 auto",
            padding: "0.5rem 0.75rem",
            border: "1px solid #d1d5db",
            borderRadius: 6,
            boxSizing: "border-box",
          }}
        />
        <button
          type="submit"
          disabled={loading || input.trim().length === 0}
          style={{
            cursor: loading ? "not-allowed" : "pointer",
            padding: "0.5rem 1rem",
            border: "1px solid #2563eb",
            borderRadius: 6,
            background: "#2563eb",
            color: "#ffffff",
          }}
        >
          {loading ? t("chat.querying") : t("chat.send")}
        </button>
      </form>
    </div>
  );
}

export default ChatWindow;
