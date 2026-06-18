// desktop/src/i18n/index.tsx
// 轻量、零依赖的 i18n 运行时：LanguageProvider（React 上下文）+ useI18n() 钩子。
// - 默认语言为英文（en）；用户选择持久化到 localStorage 键 "rag2.lang"。
// - t(key, vars) 查表顺序：messages[lang][key] -> messages["en"][key] -> key 本身；
//   并以 vars 替换 {x} 形式的占位符。
// - setLang 写入 localStorage 并更新 state，触发整棵树实时重渲染。
// 命名一律使用英文；注释默认中文。

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import { messages } from "./messages";
import type { Lang } from "./types";

// 语言选择在 localStorage 中的键名
const LANG_STORAGE_KEY = "rag2.lang";

// 默认语言：英文
const DEFAULT_LANG: Lang = "en";

// 校验任意值是否为受支持的语言
function isLang(value: unknown): value is Lang {
  return value === "en" || value === "zh";
}

// 读取初始语言：localStorage 缺失/非法时回退英文
function readInitialLang(): Lang {
  try {
    const stored = globalThis.localStorage?.getItem(LANG_STORAGE_KEY);
    if (isLang(stored)) return stored;
  } catch {
    // localStorage 不可用（隐私模式等）时安全回退默认语言
  }
  return DEFAULT_LANG;
}

// 占位符替换：把文案中的 {key} 依据 vars 替换为对应值
function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}

// i18n 上下文对外暴露的能力
export interface I18nContextValue {
  // 当前语言
  lang: Lang;
  // 切换语言：持久化并实时更新
  setLang: (lang: Lang) => void;
  // 翻译函数：查表 + 占位符替换
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// LanguageProvider Props
export interface LanguageProviderProps {
  children: ReactNode;
}

// 语言 Provider：持有当前语言状态，向下提供 lang/setLang/t
export function LanguageProvider({ children }: LanguageProviderProps) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  // 切换语言：写入 localStorage 并更新 state（触发实时重渲染）
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      globalThis.localStorage?.setItem(LANG_STORAGE_KEY, next);
    } catch {
      // 持久化失败忽略（隐私模式等），内存态仍然生效
    }
  }, []);

  // 翻译函数：messages[lang][key] -> messages["en"][key] -> key 本身
  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const template = messages[lang]?.[key] ?? messages.en[key] ?? key;
      return interpolate(template, vars);
    },
    [lang]
  );

  const value = useMemo<I18nContextValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// useI18n()：读取 i18n 上下文；必须在 LanguageProvider 内使用
export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within a LanguageProvider");
  }
  return ctx;
}
