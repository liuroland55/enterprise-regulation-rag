import { useEffect, useState } from "react";

import { SessionProvider, useSession } from "./auth/session";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { useI18n } from "./i18n";
import { Admin } from "./pages/Admin";
import { Chat } from "./pages/Chat";
import { Login } from "./pages/Login";
import type { ModeUpdateResult } from "./types/chat";

// 应用根组件：等待本地 FastAPI side-car 就绪后，渲染由 SessionProvider 包裹的应用外壳。
// 应用外壳（AppShell）依据登录态与角色进行导航：
//   - 未登录 -> <Login/>；
//   - 已登录 -> 顶部导航栏（对话 / 管理后台[仅 admin] / 退出）+ 主视图（Chat / Admin）。
// 路由以本地 tab state 实现，无需引入额外路由库。
// AppShell 必须在 SessionProvider 内部（useSession 依赖其上下文）。
// 命名一律使用英文；注释默认中文。

// side-car 仅绑定回环地址，端口固定为 8756（见 tauri.conf.json 与 Rust 外壳常量）
const SIDECAR_BASE_URL = "http://127.0.0.1:8756";

type SidecarStatus = "starting" | "ready" | "unreachable";

// 主视图标签：对话 / 管理后台
type MainTab = "chat" | "admin";

// 顶部导航栏样式
const navStyles = {
  bar: {
    display: "flex",
    alignItems: "center",
    gap: "1rem",
    padding: "0.5rem 1rem",
    background: "#111827",
    color: "#f9fafb",
    fontFamily: "system-ui, sans-serif",
    fontSize: "0.875rem",
  } as const,
  title: { fontWeight: 600, marginRight: "0.5rem" } as const,
  tab: (active: boolean) =>
    ({
      padding: "0.35rem 0.75rem",
      borderRadius: "0.375rem",
      border: "none",
      cursor: "pointer",
      fontSize: "0.8125rem",
      background: active ? "#2563eb" : "transparent",
      color: active ? "#ffffff" : "#d1d5db",
    }) as const,
  // 管理后台入口：刻意做成醒目的“后台/管理”入口（图标 + 描边 + 加粗），便于辨识。
  adminTab: (active: boolean) =>
    ({
      padding: "0.35rem 0.75rem",
      borderRadius: "0.375rem",
      border: "1px solid #f59e0b",
      cursor: "pointer",
      fontSize: "0.8125rem",
      fontWeight: 600,
      background: active ? "#b45309" : "transparent",
      color: active ? "#ffffff" : "#fbbf24",
    }) as const,
  spacer: { flex: "1 1 auto" } as const,
  user: { color: "#9ca3af", fontSize: "0.8125rem" } as const,
  logoutBtn: {
    padding: "0.35rem 0.75rem",
    borderRadius: "0.375rem",
    border: "1px solid #374151",
    background: "transparent",
    color: "#f9fafb",
    cursor: "pointer",
    fontSize: "0.8125rem",
  } as const,
};

// 应用外壳：登录态 + 角色驱动的导航与主视图切换
function AppShell() {
  const { isAuthenticated, username, role, logout } = useSession();
  const { t } = useI18n();
  const [tab, setTab] = useState<MainTab>("chat");
  // 运行模式切换后的「需重启生效」提示（含可选 warning）；null 表示无待生效变更
  const [modeNotice, setModeNotice] = useState<ModeUpdateResult | null>(null);

  // 未登录：渲染登录页（登录成功后 isAuthenticated 翻转，自动切换到主界面）
  if (!isAuthenticated) {
    return <Login />;
  }

  const isAdmin = role === "admin";
  // 防御：若非管理员却处于 admin 标签（如角色变化），回退到对话
  const activeTab: MainTab = tab === "admin" && !isAdmin ? "chat" : tab;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw" }}>
      {/* 顶部导航栏 */}
      <nav style={navStyles.bar}>
        <span style={navStyles.title}>{t("app.title")}</span>
        <button type="button" style={navStyles.tab(activeTab === "chat")} onClick={() => setTab("chat")}>
          {t("nav.chat")}
        </button>
        {isAdmin && (
          <button
            type="button"
            style={navStyles.adminTab(activeTab === "admin")}
            onClick={() => setTab("admin")}
            title={t("nav.admin")}
          >
            ⚙ {t("nav.admin")}
          </button>
        )}
        <span style={navStyles.spacer} />
        {/* 运行模式切换（LOCAL / API）：任意已认证用户可切换，切换后提示重启生效 */}
        <ModeSwitcher onChanged={setModeNotice} />
        {/* 语言切换器：登录后顶部导航可随时切换 */}
        <LanguageSwitcher variant="dark" />
        <span style={navStyles.user}>
          {t("nav.userInfo", { name: username ?? t("nav.defaultUser"), role: role ?? "employee" })}
        </span>
        <button type="button" style={navStyles.logoutBtn} onClick={() => void logout()}>
          {t("nav.logout")}
        </button>
      </nav>

      {/* 运行模式切换后的「需重启生效」横幅（含缺少密钥等可选 warning） */}
      {modeNotice && (
        <div
          role="status"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            padding: "0.5rem 1rem",
            background: "#fef3c7",
            color: "#92400e",
            borderBottom: "1px solid #fde68a",
            fontFamily: "system-ui, sans-serif",
            fontSize: "0.8125rem",
          }}
        >
          <span style={{ flex: "1 1 auto" }}>
            {t("mode.restartBanner", {
              mode: modeNotice.mode === "CLOUD" ? t("mode.api") : t("mode.local"),
            })}
            {modeNotice.warning ? ` ${t("mode.warningNoKey")}` : ""}
          </span>
          <button
            type="button"
            onClick={() => setModeNotice(null)}
            style={{
              padding: "0.2rem 0.6rem",
              borderRadius: "0.375rem",
              border: "1px solid #d97706",
              background: "transparent",
              color: "#92400e",
              cursor: "pointer",
              fontSize: "0.75rem",
            }}
          >
            {t("mode.dismiss")}
          </button>
        </div>
      )}

      {/* 主视图：根据标签切换 Chat / Admin */}
      <div style={{ flex: "1 1 auto", minHeight: 0, overflow: "auto" }}>
        {activeTab === "admin" ? <Admin /> : <Chat />}
      </div>
    </div>
  );
}

function App() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SidecarStatus>("starting");

  useEffect(() => {
    let cancelled = false;

    // 轮询 side-car 健康检查端点，确认 Rust 外壳已成功 spawn 子进程
    async function poll() {
      try {
        const res = await fetch(`${SIDECAR_BASE_URL}/system/health`);
        if (!cancelled && res.ok) {
          setStatus("ready");
          return;
        }
      } catch {
        // side-car 可能尚未就绪，继续重试
      }
      if (!cancelled) {
        setStatus((prev) => (prev === "ready" ? prev : "unreachable"));
        setTimeout(poll, 1000);
      }
    }

    void poll();
    return () => {
      cancelled = true;
    };
  }, []);

  // side-car 未就绪时展示状态提示
  if (status !== "ready") {
    return (
      <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
        <h1>{t("app.title")}</h1>
        <p>
          {t("connecting.prefix")}<strong>{status}</strong>
        </p>
      </main>
    );
  }

  // side-car 就绪：渲染由 SessionProvider 包裹的应用外壳（登录 / 角色导航）
  return (
    <SessionProvider>
      <AppShell />
    </SessionProvider>
  );
}

export default App;
