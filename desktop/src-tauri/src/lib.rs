// Tauri 应用库入口。
// main.rs 仅转发到此处的 run()，便于在桌面/移动目标间复用。

mod sidecar;

use sidecar::{SidecarProcess, SIDECAR_HOST, SIDECAR_PORT};
use tauri::{Manager, RunEvent};

/// 暴露给前端的命令：返回 side-car 的回环地址，供 API client 拼接 BASE_URL。
#[tauri::command]
fn sidecar_base_url() -> String {
    format!("http://{SIDECAR_HOST}:{SIDECAR_PORT}")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // 托管 side-car 进程状态，供 setup 与退出事件共享
        .manage(SidecarProcess::new())
        .invoke_handler(tauri::generate_handler![sidecar_base_url])
        .setup(|app| {
            // 启动钩子：应用初始化时拉起本地 FastAPI side-car 子进程（Requirement 1.1）
            let state = app.state::<SidecarProcess>();
            sidecar::spawn_sidecar(state.inner());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败")
        .run(|app_handle, event| {
            // 退出钩子：应用退出时终止 side-car，避免孤儿进程（Requirement 1.3）
            if let RunEvent::ExitRequested { .. } = event {
                let state = app_handle.state::<SidecarProcess>();
                sidecar::terminate_sidecar(state.inner());
            }
        });
}
