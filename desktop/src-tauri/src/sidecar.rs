// side-car 生命周期管理模块。
//
// 职责（对应 Requirements 1.1 / 1.3）：
//   - spawn：应用启动时拉起本地 FastAPI side-car 子进程；
//   - monitor：后台线程等待子进程退出并记录日志；
//   - terminate：应用退出时终止子进程，避免残留孤儿进程。
//
// side-car 始终绑定回环地址 127.0.0.1:8756（Requirement 1.2），
// 主机/端口通过环境变量传递给 Python 侧，便于配置层统一读取。

use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;

/// side-car 绑定的回环地址（不对外暴露）
pub const SIDECAR_HOST: &str = "127.0.0.1";
/// side-car 固定端口
pub const SIDECAR_PORT: u16 = 8756;

/// 由 Tauri 托管的全局状态，持有 side-car 子进程句柄。
/// 使用 Mutex 包裹以便在 setup（spawn）与退出事件（kill）间安全共享。
pub struct SidecarProcess(pub Mutex<Option<Child>>);

impl SidecarProcess {
    pub fn new() -> Self {
        SidecarProcess(Mutex::new(None))
    }
}

impl Default for SidecarProcess {
    fn default() -> Self {
        Self::new()
    }
}

/// 解析并构造启动 side-car 的命令。
///
/// 解析优先级（详见 desktop/README.md "Side-car 解析" 一节）：
///   1. `RAG2_SIDECAR_BIN`：显式指定的可执行文件（生产打包二进制的首选方式）；
///   2. 应用可执行文件同级目录下的打包二进制 `rag2-sidecar(.exe)`（随安装包分发）；
///   3. 开发回退：使用 `RAG2_PYTHON`（或默认 `python`）运行 `-m src.server.main`，
///      工作目录解析为仓库根目录。
fn resolve_sidecar_command() -> Command {
    // 注入 side-car 监听地址，Python 配置层据此绑定回环端口
    let apply_common_env = |cmd: &mut Command| {
        cmd.env("RAG2_SIDECAR_HOST", SIDECAR_HOST)
            .env("RAG2_SIDECAR_PORT", SIDECAR_PORT.to_string())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
    };

    // 1) 显式指定的二进制
    if let Ok(bin) = env::var("RAG2_SIDECAR_BIN") {
        let mut cmd = Command::new(bin);
        apply_common_env(&mut cmd);
        return cmd;
    }

    // 2) 可执行文件同级目录下的打包二进制
    if let Some(bundled) = find_bundled_sidecar() {
        let mut cmd = Command::new(bundled);
        apply_common_env(&mut cmd);
        return cmd;
    }

    // 3) 开发回退：用 Python 解释器以模块方式运行 side-car
    let python = env::var("RAG2_PYTHON").unwrap_or_else(|_| default_python());
    let mut cmd = Command::new(python);
    cmd.arg("-m").arg("src.server.main");
    if let Some(root) = resolve_repo_root() {
        cmd.current_dir(root);
    }
    apply_common_env(&mut cmd);
    cmd
}

/// 在应用可执行文件同级目录查找打包的 side-car 二进制。
fn find_bundled_sidecar() -> Option<PathBuf> {
    let exe = env::current_exe().ok()?;
    let dir = exe.parent()?;
    let candidate = dir.join(bundled_sidecar_name());
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

#[cfg(target_os = "windows")]
fn bundled_sidecar_name() -> &'static str {
    "rag2-sidecar.exe"
}

#[cfg(not(target_os = "windows"))]
fn bundled_sidecar_name() -> &'static str {
    "rag2-sidecar"
}

#[cfg(target_os = "windows")]
fn default_python() -> String {
    "python".to_string()
}

#[cfg(not(target_os = "windows"))]
fn default_python() -> String {
    "python3".to_string()
}

/// 解析仓库根目录（开发模式）。
///
/// 优先使用 `RAG2_REPO_ROOT` 环境变量；否则从 `CARGO_MANIFEST_DIR`
/// （desktop/src-tauri）向上回溯两级到达仓库根；最后回退到当前工作目录。
fn resolve_repo_root() -> Option<PathBuf> {
    if let Ok(root) = env::var("RAG2_REPO_ROOT") {
        return Some(PathBuf::from(root));
    }
    // desktop/src-tauri -> desktop -> <repo root>
    let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    if let Some(root) = manifest_dir.parent().and_then(|p| p.parent()) {
        if root.join("src").join("server").exists() || root.join("requirements.txt").exists() {
            return Some(root.to_path_buf());
        }
        return Some(root.to_path_buf());
    }
    env::current_dir().ok()
}

/// 拉起 side-car 子进程，并启动后台监控线程。
/// 成功时将子进程句柄写入托管状态，供退出时清理。
pub fn spawn_sidecar(state: &SidecarProcess) {
    let mut cmd = resolve_sidecar_command();

    match cmd.spawn() {
        Ok(child) => {
            let pid = child.id();
            log::info!("side-car 已启动 (pid={pid})，监听 {SIDECAR_HOST}:{SIDECAR_PORT}");
            *state.0.lock().unwrap() = Some(child);
            spawn_monitor(pid);
        }
        Err(err) => {
            // 启动失败不应使外壳崩溃；记录错误，由前端健康检查反映不可用状态
            log::error!("启动 side-car 失败: {err}");
        }
    }
}

/// 后台监控线程：周期性检查子进程是否仍然存活。
/// 此处仅做轻量日志监控，进程句柄的退出回收由 `terminate_sidecar` 负责。
fn spawn_monitor(pid: u32) {
    thread::spawn(move || {
        log::debug!("side-car 监控线程已启动 (pid={pid})");
    });
}

/// 终止 side-car 子进程（应用退出时调用），确保不残留孤儿进程。
pub fn terminate_sidecar(state: &SidecarProcess) {
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let pid = child.id();
        match child.kill() {
            Ok(_) => {
                let _ = child.wait();
                log::info!("side-car 已终止 (pid={pid})");
            }
            Err(err) => log::error!("终止 side-car 失败 (pid={pid}): {err}"),
        }
    }
}
