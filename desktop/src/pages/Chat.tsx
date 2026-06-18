// desktop/src/pages/Chat.tsx
// 三栏布局容器：组合左/中/右三列，串联端到端数据流（任务 12.1）。
// - 左列：ProfileCard（职位 + 任务，数据来自 useSession 解码自 JWT）、
//   KbScopeSelector（本地 state 持有 options/selected）、SessionHistory（点击历史项重放问答）。
// - 中列：ChatWindow（消息流 + 输入框），onSubmit 调用 api.ask 并把结果作为 assistant 消息追加。
// - 右列：SourcePanel（由当前激活回答的 sources 映射为 SourceCard），
//   admin + developerMode 时额外渲染 DeveloperMetricsPanel。
// - 角色显隐统一通过 useDeveloperMode；DeveloperModeToggle 仅 admin 可见。
// 命名一律使用英文；注释默认中文。

import { useEffect, useRef, useState } from "react";
import { ThreeColumnLayout } from "../components/layout/ThreeColumnLayout";
import { ProfileCard } from "../components/left/ProfileCard";
import {
  KbScopeSelector,
  type KbScopeOption,
} from "../components/left/KbScopeSelector";
import { SessionHistory } from "../components/left/SessionHistory";
import { ChatWindow, type ChatMessage } from "../components/middle/ChatWindow";
import {
  SourcePanel,
  relevanceFromScore,
} from "../components/right/SourcePanel";
import { DeveloperMetricsPanel } from "../components/right/DeveloperMetricsPanel";
import { DeveloperModeToggle } from "../components/admin/DeveloperModeToggle";
import { api, UnauthorizedError } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";
import { useDeveloperMode } from "../hooks/useDeveloperMode";
import type {
  AskResponse,
  HistoryItem,
  SourceCard,
  SourceItem,
  TempDoc,
  ThinkingStep,
} from "../types/chat";

// ---------------------------------------------------------------------------
// 适配器：后端 AskResponse.sources（SourceItem {content, source}）
//        → SourcePanel 期望的 SourceCard {title, section, excerpt, relevance}。
// 映射规则：
//   - title    ← source（来源标识，如文件名/条例名）
//   - section  ← ""（后端当前未提供章/节信息，留空）
//   - excerpt  ← content（原文摘录）
//   - relevance← 若 SourceItem 携带可选 score 字段则用 relevanceFromScore 推导，
//               否则给默认 "中"（绝不向用户展示原始分数）。
// 说明：SourceItem 类型当前仅含 content/source；这里以宽松取值兼容后端未来可能
//      附带的 score 字段，避免引入对类型定义的破坏性改动。
// ---------------------------------------------------------------------------
function toSourceCard(item: SourceItem): SourceCard {
  // 兼容后端可能附带的可选相似度分数（当前类型未声明，运行时存在则使用）
  const maybeScore = (item as { score?: number }).score;
  const relevance =
    typeof maybeScore === "number" ? relevanceFromScore(maybeScore) : "中";
  return {
    title: item.source,
    section: "",
    excerpt: item.content,
    relevance,
  };
}

export function Chat() {
  // 会话信息：role/position/tasks 均解码自 access token（JWT 声明）
  const { role, position, tasks, callWithRefresh, logout } = useSession();
  const { t, lang } = useI18n();
  // 角色门控：开发者模式仅 admin 生效，员工恒为 false
  const { developerMode } = useDeveloperMode();

  // 聊天消息流（用户 + 助手）
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // 当前激活回答：驱动右列溯源面板与开发者指标面板
  const [activeAnswer, setActiveAnswer] = useState<AskResponse | null>(null);
  // ask 请求加载态：用于禁用输入并提示
  const [loading, setLoading] = useState(false);
  // 思考态与实时思考步骤（流式）：思考完成后清空，使思考区消失
  const [thinking, setThinking] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  // 错误提示文案（鉴权失败/网络异常等）
  const [errorText, setErrorText] = useState<string | null>(null);

  // 知识库范围（多选，可选）：选项由 /kb/list 拉取（含内置与已上传的文件）。
  // 注意：当前“选择范围”仅用于前端展示/勾选；按范围过滤检索需后端支持，
  // 属后续功能（见说明）。这里至少保证文件列表正确显示并可勾选。
  const [kbOptions, setKbOptions] = useState<KbScopeOption[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);

  // 临时文件（一次性上下文）：前端在客户端读取文本后随提问上送，不入库。
  // 发送成功（onFinal）后清空，使其仅作用于本次/接下来的提问。
  const [tempDocs, setTempDocs] = useState<TempDoc[]>([]);
  // 隐藏的原生文件输入引用：由自定义本地化按钮转发点击（原生按钮文案无法本地化）
  const tempFileInputRef = useRef<HTMLInputElement | null>(null);

  // 挂载后拉取知识库文件列表填充选择器（经 callWithRefresh 处理 401 刷新）
  useEffect(() => {
    let active = true;
    callWithRefresh(() => api.listKb())
      .then((res) => {
        if (!active) return;
        // KbEntry{docId, filename} → KbScopeOption{id, label}
        setKbOptions(res.items.map((e) => ({ id: e.docId, label: e.filename })));
      })
      .catch(() => {
        // 列表拉取失败时静默降级为空（不阻断聊天主流程）
      });
    return () => {
      active = false;
    };
  }, [callWithRefresh]);

  // 读取选择的临时文件为文本，追加到 tempDocs 状态（支持多选）。
  // 仅接受文本类扩展名；读取失败的文件静默跳过，不阻断其它文件。
  const handleAttachTempFiles = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    const read: TempDoc[] = [];
    for (const f of files) {
      try {
        const content = await f.text();
        read.push({ name: f.name, content });
      } catch {
        // 单个文件读取失败：跳过，不影响其它文件
      }
    }
    if (read.length > 0) {
      setTempDocs((prev) => [...prev, ...read]);
    }
    // 重置 input，允许再次选择同名文件
    e.target.value = "";
  };

  // 移除某个已附加的临时文件
  const handleRemoveTempDoc = (name: string) => {
    setTempDocs((prev) => prev.filter((d) => d.name !== name));
  };

  // 提交问题：流式调用 /ask/stream → 实时展示思考过程 → 思考完成后追加助手消息并清空思考区
  const handleSubmit = async (question: string) => {
    // 先把用户消息落入消息流
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);
    setThinking(true);
    setThinkingSteps([]);
    setErrorText(null);
    try {
      // 经 callWithRefresh 包装：遇 401 自动刷新并重试一次
      // 传入检索范围（勾选的知识库）与临时文件；优先级：临时文件 > 勾选范围 > 全部。
      await callWithRefresh(() =>
        api.askStream(
          question,
          {
            // 收到一步思考：追加到思考步骤列表（实时展示）
            onStep: (step) => setThinkingSteps((prev) => [...prev, step]),
            // 思考完成：追加助手消息（含徽章字段），刷新右列，并清空/隐藏思考区
            onFinal: (answer) => {
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: answer.answer,
                  grade: answer.grade,
                  iterations: answer.iterations,
                  sourceCount: answer.sources.length,
                },
              ]);
              setActiveAnswer(answer);
              setThinking(false);
              setThinkingSteps([]);
              // 发送成功后清空临时文件：临时文件仅作用于本次提问
              setTempDocs([]);
            },
            // 流式错误：给出降级提示并结束思考
            onError: (message) => {
              setErrorText(t("chat.error.queryFailedWithMessage", { message }));
              setThinking(false);
            },
          },
          {
            kbSources: selectedKbIds,
            tempDocs,
            // 让回答语言跟随当前 UI 语言（透传到后端注入语言指令）
            lang,
          }
        )
      );
    } catch (err) {
      // 刷新仍失败的 401：登出回到登录态；其余异常给出降级提示
      if (err instanceof UnauthorizedError) {
        setErrorText(t("chat.error.sessionExpired"));
        await logout();
      } else {
        setErrorText(t("chat.error.queryFailed"));
      }
      setThinking(false);
    } finally {
      setLoading(false);
    }
  };

  // 新建对话：清空当前会话的全部临时状态，回到空白聊天界面。
  // 注意：仅重置前端会话视图，不影响已持久化的历史记录（左列 SessionHistory）。
  const handleNewConversation = () => {
    setMessages([]);
    setActiveAnswer(null);
    setThinking(false);
    setThinkingSteps([]);
    setErrorText(null);
    // 临时文件仅作用于具体提问，新建对话时一并清空
    setTempDocs([]);
  };

  // 点击历史项：把该问答重新载入聊天区（问题 + 答案 + 徽章字段）。
  // 历史条目不含 sources 明细，故右列溯源面板对历史重放重置为空（仅展示问答与徽章）。
  const handleSelectHistory = (item: HistoryItem) => {
    setMessages([
      { role: "user", content: item.question },
      {
        role: "assistant",
        content: item.answer,
        grade: item.grade,
        iterations: item.iterations,
        sourceCount: item.sourceCount,
      },
    ]);
    setActiveAnswer(null);
    setErrorText(null);
    // 重放历史时清空并隐藏思考区
    setThinking(false);
    setThinkingSteps([]);
  };

  // 当前激活回答的溯源卡片（经适配器映射）
  const sourceCards: SourceCard[] = (activeAnswer?.sources ?? []).map(toSourceCard);

  return (
    <ThreeColumnLayout
      // 左列：用户画像卡 + 知识库选择 + 历史会话
      left={
        <>
          {/* 用户画像卡：职位 + 任务（员工只读）。
              TODO(profile): useSession 的 position/tasks 解码自 JWT；
              若后端未在 token 注入这些声明，则显示占位文案，由管理后台维护档案。 */}
          <ProfileCard position={position} tasks={tasks} role={role ?? "employee"} />
          {/* 知识库选择（多选，可选）：选项/已选由本地 state 持有 */}
          <KbScopeSelector
            options={kbOptions}
            selectedIds={selectedKbIds}
            onChange={setSelectedKbIds}
          />
          {/* 检索范围提示：说明勾选与临时文件的优先级规则 */}
          <p style={{ fontSize: "0.6875rem", color: "#6b7280", margin: "0.25rem 0 0.5rem", lineHeight: 1.5 }}>
            {t("chat.scopeHint")}
          </p>
          {/* 历史会话：点击某项把该问答重放到聊天区 */}
          <SessionHistory onSelect={handleSelectHistory} />
        </>
      }
      // 中列：聊天窗口（onSubmit 调用 api.ask）+ 开发者模式开关（仅 admin 可见）
      middle={
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          {/* 顶部工具条：新建对话按钮 + 开发者模式开关（员工不渲染开关） */}
          <div
            style={{
              marginBottom: "0.5rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.5rem",
            }}
          >
            {/* 新建对话：清空当前会话视图，回到空白聊天 */}
            <button
              type="button"
              onClick={handleNewConversation}
              style={{
                padding: "0.3rem 0.7rem",
                background: "#ffffff",
                color: "#2563eb",
                border: "1px solid #2563eb",
                borderRadius: "0.375rem",
                fontSize: "0.75rem",
                cursor: "pointer",
              }}
            >
              ＋ {t("chat.newConversation")}
            </button>
            <DeveloperModeToggle />
          </div>
          {/* 临时文件附加区：读取文本作为一次性上下文（不入库） */}
          <div style={{ marginBottom: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              {/* 原生 <input type="file"> 的按钮文案无法本地化，视觉隐藏后用自定义按钮转发点击 */}
              <input
                ref={tempFileInputRef}
                type="file"
                accept=".txt,.md,.rst,.log"
                multiple
                onChange={(e) => void handleAttachTempFiles(e)}
                style={{ display: "none" }}
              />
              <button
                type="button"
                onClick={() => tempFileInputRef.current?.click()}
                style={{
                  padding: "0.3rem 0.7rem",
                  background: "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "0.375rem",
                  fontSize: "0.75rem",
                  cursor: "pointer",
                }}
              >
                {t("chat.attachTempFile")}
              </button>
            </div>
            {/* 已附加文件 chips（可移除） */}
            {tempDocs.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: "0.375rem" }}>
                {tempDocs.map((d) => (
                  <span
                    key={d.name}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      background: "#eff6ff",
                      border: "1px solid #bfdbfe",
                      borderRadius: "9999px",
                      padding: "0.125rem 0.5rem",
                      fontSize: "0.75rem",
                      color: "#1e40af",
                    }}
                  >
                    {d.name}
                    <button
                      type="button"
                      aria-label={t("chat.removeTempFile", { name: d.name })}
                      onClick={() => handleRemoveTempDoc(d.name)}
                      style={{
                        border: "none",
                        background: "transparent",
                        cursor: "pointer",
                        color: "#1e40af",
                        fontSize: "0.875rem",
                        lineHeight: 1,
                        padding: 0,
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p style={{ fontSize: "0.6875rem", color: "#6b7280", margin: "0.375rem 0 0" }}>
              {t("chat.tempFileNote")}
            </p>
          </div>
          {/* 错误提示（鉴权失效/网络异常等） */}
          {errorText && (
            <div
              role="alert"
              style={{
                color: "#b91c1c",
                fontSize: "0.8125rem",
                marginBottom: "0.5rem",
              }}
            >
              {errorText}
            </div>
          )}
          {/* 聊天窗口：消息流 + 输入框 */}
          <div style={{ flex: "1 1 auto", minHeight: 0 }}>
            <ChatWindow
              messages={messages}
              onSubmit={handleSubmit}
              loading={loading}
              thinking={thinking}
              thinkingSteps={thinkingSteps}
            />
          </div>
        </div>
      }
      // 右列：溯源面板（默认）+ 开发者指标面板（仅 admin + 开发者模式）
      right={
        <>
          {/* 溯源面板：由当前激活回答的 sources 映射为 SourceCard */}
          <SourcePanel sources={sourceCards} />
          {/* 开发者指标面板：仅 admin 且开启开发者模式时渲染 */}
          {role === "admin" && developerMode && (
            <DeveloperMetricsPanel answer={activeAnswer} />
          )}
        </>
      }
      // 右列可折叠
      rightCollapsible
    />
  );
}

export default Chat;
