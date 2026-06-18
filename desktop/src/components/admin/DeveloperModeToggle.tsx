// desktop/src/components/admin/DeveloperModeToggle.tsx
// 开发者模式开关：仅 admin 可见（员工不渲染开关）。
// 关键约束：员工角色直接返回 null，UI 上完全不暴露该开关；
// 切换逻辑统一由 useDeveloperMode 提供（toggle 仅对 admin 生效）。
// 命名一律使用英文；注释默认中文。

import { useI18n } from "../../i18n";
import { useDeveloperMode } from "../../hooks/useDeveloperMode";

// 开发者模式开关组件：基于 useDeveloperMode 的角色门控渲染。
export function DeveloperModeToggle() {
  const { t } = useI18n();
  const { developerMode, canToggleDeveloperMode, toggle } = useDeveloperMode();

  // 仅 admin 可切换；员工（或未登录）不渲染开关，避免暴露任何工程入口
  if (!canToggleDeveloperMode) return null;

  return (
    <label className="developer-mode-toggle">
      <input
        type="checkbox"
        checked={developerMode}
        onChange={toggle}
        aria-label={t("developer.mode")}
      />
      <span className="label">{t("developer.mode")}</span>
    </label>
  );
}

export default DeveloperModeToggle;
