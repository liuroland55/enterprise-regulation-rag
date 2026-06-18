import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { LanguageProvider } from "./i18n";

// 前端入口：将 React 应用挂载到 index.html 的 #root 节点
// LanguageProvider 包裹在最外层（位于 App / SessionProvider 之上），
// 使所有组件（含登录前界面）都能通过 useI18n() 访问语言上下文。
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <LanguageProvider>
      <App />
    </LanguageProvider>
  </React.StrictMode>
);
