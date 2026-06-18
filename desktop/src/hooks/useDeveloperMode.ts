// desktop/src/hooks/useDeveloperMode.ts
// 角色门控 + 开发者模式状态：将开发者模式的可见性逻辑集中在一处。
// - developerMode = role === "admin" && enabled（员工恒为 false）。
// - canToggleDeveloperMode = role === "admin"（仅 admin 可切换）。
// - toggle() 仅对 admin 生效；员工调用无效，无法开启。
// 命名一律使用英文；注释默认中文。

import { useCallback, useState } from "react";

import { useSession } from "../auth/session";

// useDeveloperMode 返回的状态与操作
export interface UseDeveloperModeResult {
  // 当前用户角色（"admin" | "employee"），未登录为 null
  role: string | null;
  // 是否处于开发者模式（仅 admin 且已开启时为 true，员工恒为 false）
  developerMode: boolean;
  // 是否允许切换开发者模式（仅 admin 为 true）
  canToggleDeveloperMode: boolean;
  // 切换开发者模式：仅 admin 生效，员工调用无任何效果
  toggle: () => void;
}

// 角色门控钩子：基于 useSession 的 role 派生开发者模式状态。
export function useDeveloperMode(): UseDeveloperModeResult {
  const { role } = useSession(); // "admin" | "employee" | null
  const [enabled, setEnabled] = useState(false);

  // 开发者模式开关只对 admin 生效；员工永远拿到 false，无法开启
  const developerMode = role === "admin" && enabled;
  const canToggleDeveloperMode = role === "admin";

  // 仅 admin 可切换；员工调用 toggle 不改变任何状态
  const toggle = useCallback(() => {
    if (role === "admin") setEnabled((v) => !v);
  }, [role]);

  return { role, developerMode, canToggleDeveloperMode, toggle };
}

export default useDeveloperMode;
