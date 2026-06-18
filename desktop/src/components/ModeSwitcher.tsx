// desktop/src/components/ModeSwitcher.tsx
// 顶栏运行模式切换器（LOCAL / API[CLOUD]）：任意已认证用户可切换。
// - 挂载时拉取当前生效模式（GET /system/mode）。
// - 切换前二次确认（提示：全局设置、影响所有用户、需重启侧车生效）。
// - 切换成功后通过 onChanged 通知上层展示「重启生效」横幅；切到 CLOUD 缺密钥时带 warning。
// 由于 RAG 核心在启动期初始化，模式切换需重启侧车才会真正生效，故后端 GET 在重启前
// 仍返回旧的「生效模式」；本组件用 pendingMode 反映用户刚选择的目标模式。
// 命名一律使用英文；注释默认中文。

import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";
import type { ModeUpdateResult } from "../types/chat";

export interface ModeSwitcherProps {
  // 切换成功回调：交由上层（App）展示需重启的横幅
  onChanged?: (result: ModeUpdateResult) => void;
}

export function ModeSwitcher({ onChanged }: ModeSwitcherProps) {
  const { callWithRefresh } = useSession();
  const { t } = useI18n();

  // 后端当前「生效」模式（重启前不随切换改变）
  const [activeMode, setActiveMode] = useState<string | null>(null);
  // 用户刚选择、尚待重启生效的目标模式
  const [pendingMode, setPendingMode] = useState<string | null>(null);
  // 切换请求进行中
  const [busy, setBusy] = useState(false);

  // 挂载时拉取当前生效模式
  useEffect(() => {
    let active = true;
    callWithRefresh(() => api.getMode())
      .then((info) => {
        if (active) setActiveMode(info.mode);
      })
      .catch(() => {
        // 拉取失败静默：不阻断导航栏其它功能
      });
    return () => {
      active = false;
    };
  }, [callWithRefresh]);

  // 下拉当前展示的取值：优先未生效的目标，其次生效模式
  const selected = pendingMode ?? activeMode ?? "LOCAL";

  // 模式 -> 本地化标签
  const label = (mode: string) => (mode === "CLOUD" ? t("mode.api") : t("mode.local"));

  const handleChange = async (next: string) => {
    if (busy || next === selected) return;
    // 二次确认：明确全局影响与需重启
    const ok = globalThis.confirm?.(t("mode.confirmSwitch", { mode: label(next) }));
    if (!ok) return;
    setBusy(true);
    try {
      const result = await callWithRefresh(() => api.setMode(next));
      setPendingMode(result.mode);
      onChanged?.(result);
    } catch {
      // 失败提示（不改变下拉选中，保持与生效态一致）
      globalThis.alert?.(t("mode.switchFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.375rem",
        color: "#9ca3af",
        fontSize: "0.8125rem",
      }}
      title={t("mode.label")}
    >
      <span>{t("mode.label")}</span>
      <select
        value={selected}
        disabled={busy}
        onChange={(e) => void handleChange(e.target.value)}
        style={{
          padding: "0.2rem 0.4rem",
          borderRadius: "0.375rem",
          border: "1px solid #374151",
          background: "#1f2937",
          color: "#f9fafb",
          fontSize: "0.8125rem",
          cursor: busy ? "not-allowed" : "pointer",
        }}
      >
        <option value="LOCAL">{t("mode.local")}</option>
        <option value="CLOUD">{t("mode.api")}</option>
      </select>
    </label>
  );
}

export default ModeSwitcher;
