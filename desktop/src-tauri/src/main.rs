// 阻止 Windows 发布版弹出额外的控制台窗口
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// 入口仅转发到库中的 run()，应用逻辑集中在 lib.rs
fn main() {
    enterprise_regulation_rag_lib::run();
}
