// desktop/src/auth/session.ts
// 会话 / 鉴权状态：内存 + 安全存储保存 JWT（access + refresh），
// 暴露 SessionProvider 与 useSession() 钩子；登录调用 api.login 并 setToken；
// 401（UnauthorizedError）触发刷新流程（调用 /auth/refresh；失败则登出）。
// 本模块仅负责会话/鉴权状态，不包含任何 UI 页面/组件（见任务 11.x）。
// 命名一律使用英文；注释默认中文。
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { api, setToken, UnauthorizedError } from "../api/client";

// 侧车仅绑定回环地址；刷新端点暂未封装进 api client，这里就地以 fetch 调用。
const BASE_URL = "http://127.0.0.1:8756";

// refresh token 在安全存储中的键名
const REFRESH_TOKEN_KEY = "rag2.refreshToken";

// ---------------------------------------------------------------------------
// 安全存储抽象
// 目前以 localStorage 作为回退实现；后续应替换为 Tauri 的安全存储/插件
// （如 tauri-plugin-stronghold 或 OS keychain），以避免明文持久化敏感令牌。
// TODO(tauri): 接入 Tauri secure storage 插件后替换 localStorageSecureStore。
// ---------------------------------------------------------------------------

// 安全存储接口：异步以兼容未来的 Tauri 插件实现
export interface SecureStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

// 基于浏览器 localStorage 的回退实现（开发期使用）
const localStorageSecureStore: SecureStore = {
  async get(key: string): Promise<string | null> {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      // localStorage 不可用（如隐私模式）时安全降级为内存无持久化
      return null;
    }
  },
  async set(key: string, value: string): Promise<void> {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // 忽略持久化失败，令牌仍保留在内存中
    }
  },
  async remove(key: string): Promise<void> {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      // 忽略
    }
  },
};

// ---------------------------------------------------------------------------
// JWT 工具：仅解码 payload 以还原 role/username 等声明（不做签名校验，校验在服务端）
// ---------------------------------------------------------------------------

// access token 中携带的声明（与服务端 create_access_token 注入的字段对齐）
interface JwtClaims {
  sub?: string;
  username?: string;
  role?: string;
  position?: string;
  tasks?: string[];
  type?: string;
  exp?: number;
}

// 解码 JWT payload（base64url）。解码失败返回空对象，绝不抛出。
function decodeJwtClaims(token: string): JwtClaims {
  try {
    const payload = token.split(".")[1];
    if (!payload) return {};
    // base64url -> base64
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(json) as JwtClaims;
  } catch {
    return {};
  }
}

// ---------------------------------------------------------------------------
// 刷新端点：/auth/refresh
// api client 当前未封装 refresh，这里就地以 fetch 调用，保持与 client.ts 的约定一致：
// 成功返回新的 access token；失败/吊销/过期 -> 抛出，由调用方触发登出。
// ---------------------------------------------------------------------------

interface RawRefreshResponse {
  access_token: string;
  // 后端可能附带 role；若缺省则从 access token 声明中解析
  role?: string;
}

async function callRefreshEndpoint(refreshToken: string): Promise<string> {
  const res = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  // 吊销/过期/无效 -> 401；其余非 2xx 同样视为刷新失败
  if (!res.ok) {
    throw new UnauthorizedError("Refresh failed");
  }
  const raw = (await res.json()) as RawRefreshResponse;
  return raw.access_token;
}

// ---------------------------------------------------------------------------
// Session Context
// ---------------------------------------------------------------------------

// 会话对外暴露的状态与操作
export interface SessionContextValue {
  // 当前用户角色（"admin" | "employee"），未登录为 null
  role: string | null;
  // 当前用户名，未登录为 null
  username: string | null;
  // 当前用户职位（从 access token 声明解码），未登录或未填写为空字符串
  position: string;
  // 当前用户任务列表（从 access token 声明解码），未登录或未填写为空数组
  tasks: string[];
  // 是否已认证（存在有效 access token）
  isAuthenticated: boolean;
  // 当前 access token（内存态），未登录为 null
  accessToken: string | null;
  // 登录：调用 api.login 并设置内存/存储令牌
  login: (username: string, password: string) => Promise<void>;
  // 自助注册：调用 api.register 创建员工账户并直接建立会话（注册即登录）
  register: (username: string, password: string, position?: string) => Promise<void>;
  // 登出：清除内存与安全存储中的令牌
  logout: () => Promise<void>;
  // 刷新当前用户资料：调用 /auth/me 拉取最新画像（职位/任务/角色/用户名），
  // 使桌面端与网页端在管理员改动资料后保持一致（窗口 focus 与会话建立时自动触发）。
  refreshProfile: () => Promise<void>;
  // 刷新会话：用 refresh token 换取新的 access token；失败则登出并返回 false
  refreshSession: () => Promise<boolean>;
  // 执行受保护调用：遇 401（UnauthorizedError）自动刷新并重试一次；再失败则登出并抛出
  callWithRefresh: <T>(fn: () => Promise<T>) => Promise<T>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// 内部会话状态（用于一次性 setState）
interface SessionState {
  accessToken: string | null;
  role: string | null;
  username: string | null;
  // 职位/任务由 access token 声明解码而来，供 ProfileCard 等消费
  position: string;
  tasks: string[];
}

const EMPTY_STATE: SessionState = {
  accessToken: null,
  role: null,
  username: null,
  position: "",
  tasks: [],
};

// SessionProvider Props
export interface SessionProviderProps {
  children: ReactNode;
  // 允许注入自定义安全存储（测试或后续 Tauri 实现）；默认 localStorage 回退
  store?: SecureStore;
}

// 会话 Provider：管理令牌生命周期，并将内存 token 同步到 api client（setToken）
export function SessionProvider(props: SessionProviderProps): ReactNode {
  const store = props.store ?? localStorageSecureStore;
  const [state, setState] = useState<SessionState>(EMPTY_STATE);

  // 以 ref 保存 refresh token（内存态），避免触发不必要的重渲染
  const refreshTokenRef = useRef<string | null>(null);

  // 统一应用一个新的 access token：同步内存态、api client 与派生声明
  const applyAccessToken = useCallback((accessToken: string) => {
    const claims = decodeJwtClaims(accessToken);
    setToken(accessToken); // 让 api client 在后续请求自动附带 Bearer 头
    setState({
      accessToken,
      role: claims.role ?? null,
      username: claims.username ?? null,
      position: claims.position ?? "",
      tasks: claims.tasks ?? [],
    });
  }, []);

  // 清理所有令牌（内存 + api client + 安全存储），回到未认证态
  const clearSession = useCallback(async () => {
    refreshTokenRef.current = null;
    setToken(null);
    setState(EMPTY_STATE);
    await store.remove(REFRESH_TOKEN_KEY);
  }, [store]);

  // 登录：api.login -> 设置 access token（内存 + client），持久化 refresh token
  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await api.login(username, password);
      refreshTokenRef.current = tokens.refreshToken;
      await store.set(REFRESH_TOKEN_KEY, tokens.refreshToken);
      // 优先采用登录响应中的 role；同时用 access token 声明补全 username
      const claims = decodeJwtClaims(tokens.accessToken);
      setToken(tokens.accessToken);
      setState({
        accessToken: tokens.accessToken,
        role: tokens.role ?? claims.role ?? null,
        username: claims.username ?? username,
        position: claims.position ?? "",
        tasks: claims.tasks ?? [],
      });
    },
    [store]
  );

  // 自助注册：api.register -> 设置 access token（内存 + client），持久化 refresh token。
  // 与 login 路径一致；后端强制角色为 employee，注册成功即进入已认证态。
  const register = useCallback(
    async (username: string, password: string, position?: string) => {
      const tokens = await api.register({ username, password, position: position ?? "" });
      refreshTokenRef.current = tokens.refreshToken;
      await store.set(REFRESH_TOKEN_KEY, tokens.refreshToken);
      const claims = decodeJwtClaims(tokens.accessToken);
      setToken(tokens.accessToken);
      setState({
        accessToken: tokens.accessToken,
        role: tokens.role ?? claims.role ?? null,
        username: claims.username ?? username,
        position: claims.position ?? "",
        tasks: claims.tasks ?? [],
      });
    },
    [store]
  );

  // 登出
  const logout = useCallback(async () => {
    await clearSession();
  }, [clearSession]);

  // 刷新会话：调用 /auth/refresh；成功更新 access token，失败登出
  const refreshSession = useCallback(async (): Promise<boolean> => {
    const refreshToken = refreshTokenRef.current;
    if (!refreshToken) {
      await clearSession();
      return false;
    }
    try {
      const newAccess = await callRefreshEndpoint(refreshToken);
      applyAccessToken(newAccess);
      return true;
    } catch {
      // 刷新失败（吊销/过期/无效）-> 登出
      await clearSession();
      return false;
    }
  }, [applyAccessToken, clearSession]);

  // 受保护调用包装：遇 401 自动刷新并重试一次
  const callWithRefresh = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      try {
        return await fn();
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          const ok = await refreshSession();
          if (ok) {
            // 刷新成功后重试一次；若再次 401 则向上抛出（调用方处理）
            return await fn();
          }
        }
        throw err;
      }
    },
    [refreshSession]
  );

  // 刷新当前用户资料：调用 /auth/me 拉取最新画像并合并入会话态。
  // 经 callWithRefresh 包装（遇 401 自动刷新重试）；失败静默（不影响当前视图）。
  const refreshProfile = useCallback(async () => {
    try {
      const me = await callWithRefresh(() => api.me());
      setState((prev) =>
        // 仅在仍处于已认证态时合并，避免覆盖刚登出的空态
        prev.accessToken
          ? {
              ...prev,
              role: me.role,
              username: me.username,
              position: me.position,
              tasks: me.tasks,
            }
          : prev
      );
    } catch {
      // 静默：401 已由 callWithRefresh 处理（必要时登出），其余错误不打断使用
    }
  }, [callWithRefresh]);

  // 会话建立 / access token 变化（登录、注册、刷新、启动恢复）后拉取一次最新资料
  useEffect(() => {
    if (state.accessToken) void refreshProfile();
  }, [state.accessToken, refreshProfile]);

  // 窗口获得焦点时刷新资料：实现桌面端与网页端切回即同步（管理员改动资料后两端一致）
  useEffect(() => {
    const onFocus = () => {
      void refreshProfile();
    };
    globalThis.addEventListener?.("focus", onFocus);
    return () => globalThis.removeEventListener?.("focus", onFocus);
  }, [refreshProfile]);

  // 启动时尝试从安全存储恢复会话：读取 refresh token 并换取新的 access token
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const stored = await store.get(REFRESH_TOKEN_KEY);
      if (cancelled || !stored) return;
      refreshTokenRef.current = stored;
      try {
        const newAccess = await callRefreshEndpoint(stored);
        if (!cancelled) applyAccessToken(newAccess);
      } catch {
        if (!cancelled) await clearSession();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [store, applyAccessToken, clearSession]);

  const value = useMemo<SessionContextValue>(
    () => ({
      role: state.role,
      username: state.username,
      position: state.position,
      tasks: state.tasks,
      isAuthenticated: state.accessToken !== null,
      accessToken: state.accessToken,
      login,
      register,
      logout,
      refreshProfile,
      refreshSession,
      callWithRefresh,
    }),
    [state, login, register, logout, refreshProfile, refreshSession, callWithRefresh]
  );

  // 以 createElement 渲染 Provider（本文件为 .ts，不使用 JSX）
  return createElement(SessionContext.Provider, { value }, props.children);
}

// useSession()：读取会话上下文；必须在 SessionProvider 内使用
export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return ctx;
}
