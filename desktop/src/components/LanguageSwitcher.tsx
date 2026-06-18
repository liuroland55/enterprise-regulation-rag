// desktop/src/components/LanguageSwitcher.tsx
// 语言切换器：在英文（EN）与中文（中文）之间切换，绑定 useI18n().setLang。
// 同时用于登录前界面与登录后的顶部导航，便于用户随时切换。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../i18n";
import type { Lang } from "../i18n/types";

// 切换器配色变体：dark 适配深色导航栏，light 适配浅色登录页
export interface LanguageSwitcherProps {
  variant?: "dark" | "light";
}

// 单个语言选项的展示文案（语言名本身不翻译）
const LANG_LABELS: Record<Lang, string> = {
  en: "EN",
  zh: "中文",
};

export function LanguageSwitcher({ variant = "dark" }: LanguageSwitcherProps) {
  const { lang, setLang, t } = useI18n();

  // 依据变体选择激活/未激活按钮的配色
  const isDark = variant === "dark";
  const activeColor = "#2563eb";
  const inactiveColor = isDark ? "#d1d5db" : "#6b7280";

  // 渲染单个语言按钮
  const renderButton = (target: Lang) => {
    const active = lang === target;
    return (
      <button
        type="button"
        onClick={() => setLang(target)}
        aria-pressed={active}
        style={{
          border: "none",
          background: active ? activeColor : "transparent",
          color: active ? "#ffffff" : inactiveColor,
          borderRadius: "0.25rem",
          padding: "0.15rem 0.4rem",
          fontSize: "0.75rem",
          cursor: "pointer",
        }}
      >
        {LANG_LABELS[target]}
      </button>
    );
  };

  return (
    <span
      aria-label={t("lang.ariaLabel")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.125rem",
        fontSize: "0.75rem",
        color: inactiveColor,
      }}
    >
      <span aria-hidden="true" style={{ marginRight: "0.125rem" }}>
        🌐
      </span>
      {renderButton("en")}
      <span aria-hidden="true">|</span>
      {renderButton("zh")}
    </span>
  );
}

export default LanguageSwitcher;
