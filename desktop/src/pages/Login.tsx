// desktop/src/pages/Login.tsx
// 登录 / 注册页：同一卡片内通过 mode 切换「登录」与「自助注册」两种表单。
// - 登录：用户名 / 密码，调用 useSession().login(u, p)。
// - 注册：用户名 / 密码 / 确认密码 / 职位(可选)，调用 useSession().register(u, p, position)，
//   成功即自动登录（后端强制角色为普通员工）。
// 登录/注册成功后 SessionProvider 的 isAuthenticated 变为 true，App 外壳自动切换到主界面；
// 失败给出本地化错误提示；提交期间禁用按钮，避免重复提交。
// 命名一律使用英文；注释默认中文。

import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError, UnauthorizedError } from "../api/client";
import { useSession } from "../auth/session";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { useI18n } from "../i18n";
import type { I18nContextValue } from "../i18n";

// 表单模式：登录 / 注册
type AuthMode = "login" | "register";

// 将登录异常映射为可读的本地化提示（通过传入的 t 函数翻译）
function toLoginErrorMessage(err: unknown, t: I18nContextValue["t"]): string {
  // 401：凭据无效（用户名或密码错误）
  if (err instanceof UnauthorizedError) {
    return t("login.error.invalidCredentials");
  }
  if (err instanceof ApiError) {
    // 400/401 一般也表示凭据问题；422 表示请求体不合法
    if (err.status === 400 || err.status === 401) {
      return t("login.error.invalidCredentials");
    }
    if (err.status === 422) {
      return t("login.error.missingCredentials");
    }
    return t("login.error.statusCode", { status: err.status });
  }
  // 网络/侧车不可达等
  return t("login.error.network");
}

// 将注册异常映射为可读的本地化提示
function toRegisterErrorMessage(err: unknown, t: I18nContextValue["t"]): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return t("register.error.conflict"); // 用户名已存在
    if (err.status === 422) return t("register.error.weakPassword"); // 密码不满足策略
    return t("login.error.statusCode", { status: err.status });
  }
  // 网络/侧车不可达 / 其它异常
  return t("register.error.failed");
}

// 通用输入框样式
const inputStyle: React.CSSProperties = {
  padding: "0.5rem 0.625rem",
  border: "1px solid #d1d5db",
  borderRadius: "0.375rem",
  fontSize: "0.875rem",
  width: "100%",
  boxSizing: "border-box",
};

export function Login() {
  const { login, register } = useSession();
  const { t } = useI18n();

  // 当前表单模式
  const [mode, setMode] = useState<AuthMode>("login");

  // 表单状态
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [position, setPosition] = useState("");
  // 提交中（禁用按钮）与错误提示
  const [pending, setPending] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  // 是否显示密码明文
  const [showPassword, setShowPassword] = useState(false);

  const isRegister = mode === "register";

  // 切换登录/注册模式：清空错误与确认密码，避免串场
  const switchMode = (next: AuthMode) => {
    setMode(next);
    setErrorText(null);
    setConfirmPassword("");
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (pending) return;
    setErrorText(null);

    const u = username.trim();
    if (u === "" || password === "") {
      setErrorText(t("login.error.missingCredentials"));
      return;
    }
    // 注册模式：前端先校验两次密码一致（后端仍会强制密码策略）
    if (isRegister && password !== confirmPassword) {
      setErrorText(t("register.error.passwordMismatch"));
      return;
    }

    setPending(true);
    try {
      if (isRegister) {
        await register(u, password, position.trim());
      } else {
        await login(u, password);
      }
      // 成功：无需手动跳转，App 外壳会因 isAuthenticated 变化而重渲染
    } catch (err) {
      setErrorText(
        isRegister ? toRegisterErrorMessage(err, t) : toLoginErrorMessage(err, t)
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f3f4f6",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: "320px",
          background: "#ffffff",
          padding: "2rem",
          borderRadius: "0.75rem",
          boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <h1 style={{ fontSize: "1.25rem", margin: 0, color: "#111827" }}>
          {t("app.title")}
        </h1>
        <p style={{ fontSize: "0.8125rem", color: "#6b7280", margin: 0 }}>
          {isRegister ? t("register.subtitle") : t("login.subtitle")}
        </p>

        {/* 语言切换器：登录前即可切换界面语言 */}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <LanguageSwitcher variant="light" />
        </div>

        {/* 用户名 */}
        <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <span style={{ fontSize: "0.8125rem", color: "#374151" }}>{t("login.username")}</span>
          <input
            type="text"
            value={username}
            autoComplete="username"
            disabled={pending}
            onChange={(e) => setUsername(e.target.value)}
            style={inputStyle}
          />
        </label>

        {/* 密码 */}
        <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <span style={{ fontSize: "0.8125rem", color: "#374151" }}>{t("login.password")}</span>
          {/* 输入框 + 显示/隐藏切换按钮 */}
          <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              autoComplete={isRegister ? "new-password" : "current-password"}
              disabled={pending}
              onChange={(e) => setPassword(e.target.value)}
              style={{ ...inputStyle, padding: "0.5rem 3.25rem 0.5rem 0.625rem" }}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t("common.hidePassword") : t("common.showPassword")}
              aria-pressed={showPassword}
              tabIndex={-1}
              style={{
                position: "absolute",
                right: "0.375rem",
                padding: "0.2rem 0.4rem",
                fontSize: "0.75rem",
                color: "#2563eb",
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              {showPassword ? t("common.hide") : t("common.show")}
            </button>
          </div>
        </label>

        {/* 注册专属字段：确认密码 + 职位(可选) */}
        {isRegister && (
          <>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <span style={{ fontSize: "0.8125rem", color: "#374151" }}>
                {t("register.confirmPassword")}
              </span>
              <input
                type={showPassword ? "text" : "password"}
                value={confirmPassword}
                autoComplete="new-password"
                disabled={pending}
                onChange={(e) => setConfirmPassword(e.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <span style={{ fontSize: "0.8125rem", color: "#374151" }}>
                {t("register.position")}
              </span>
              <input
                type="text"
                value={position}
                disabled={pending}
                onChange={(e) => setPosition(e.target.value)}
                style={inputStyle}
              />
            </label>
            <p style={{ fontSize: "0.6875rem", color: "#6b7280", margin: 0 }}>
              {t("register.roleNote")}
            </p>
          </>
        )}

        {/* 错误提示 */}
        {errorText && (
          <div role="alert" style={{ color: "#b91c1c", fontSize: "0.8125rem" }}>
            {errorText}
          </div>
        )}

        {/* 提交按钮：提交中禁用 */}
        <button
          type="submit"
          disabled={pending || username.trim() === "" || password === ""}
          style={{
            padding: "0.5rem 0.75rem",
            background: pending ? "#9ca3af" : "#2563eb",
            color: "#ffffff",
            border: "none",
            borderRadius: "0.375rem",
            fontSize: "0.875rem",
            cursor: pending ? "not-allowed" : "pointer",
          }}
        >
          {isRegister
            ? pending
              ? t("register.submitting")
              : t("register.submit")
            : pending
              ? t("login.signingIn")
              : t("login.signIn")}
        </button>

        {/* 登录/注册切换入口 */}
        <button
          type="button"
          onClick={() => switchMode(isRegister ? "login" : "register")}
          disabled={pending}
          style={{
            background: "transparent",
            border: "none",
            color: "#2563eb",
            fontSize: "0.8125rem",
            cursor: pending ? "not-allowed" : "pointer",
            padding: 0,
            alignSelf: "center",
          }}
        >
          {isRegister ? t("login.toggleToLogin") : t("login.toggleToRegister")}
        </button>
      </form>
    </main>
  );
}

export default Login;
