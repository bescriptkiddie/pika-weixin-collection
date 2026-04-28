use std::{
    net::TcpStream,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(PathBuf::from)
        .expect("src-tauri should live under frontend/src-tauri")
}

fn backend_is_running() -> bool {
    "127.0.0.1:8000"
        .parse()
        .ok()
        .and_then(|addr| TcpStream::connect_timeout(&addr, Duration::from_millis(200)).ok())
        .is_some()
}

fn spawn_backend() -> Result<Option<Child>, String> {
    if backend_is_running() {
        return Ok(None);
    }

    let root = repo_root();
    Command::new("uv")
        .args([
            "run",
            "uvicorn",
            "api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ])
        .current_dir(root)
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(Some)
        .map_err(|err| format!("failed to start FastAPI backend with uv: {err}"))
}

fn stop_backend(state: &BackendProcess) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let child = spawn_backend().map_err(|err| err.to_string())?;
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let state = window.state::<BackendProcess>();
                stop_backend(&state);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
