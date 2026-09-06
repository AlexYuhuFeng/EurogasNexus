#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env, fs,
    io::Read,
    net::TcpListener,
    path::PathBuf,
    process::Command,
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use tauri::Manager;

#[derive(Debug, Deserialize, Serialize)]
struct DeploymentConfig {
    schema_version: u8,
    role: String,
    api_base_url: String,
}

fn deployment_config_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = env::var_os("EUROGAS_NEXUS_CLIENT_CONFIG") {
        candidates.push(PathBuf::from(explicit));
    }
    if cfg!(target_os = "windows") {
        if let Some(program_data) = env::var_os("PROGRAMDATA") {
            candidates.push(
                PathBuf::from(program_data)
                    .join("Eurogas Nexus")
                    .join("Client")
                    .join("deployment.json"),
            );
        }
    } else {
        candidates.push(PathBuf::from("/etc/eurogas-nexus/client.json"));
    }
    candidates
}

#[tauri::command]
fn read_deployment_config() -> Result<Option<DeploymentConfig>, String> {
    for path in deployment_config_candidates() {
        if !path.is_file() {
            continue;
        }
        let payload = fs::read_to_string(&path)
            .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
        let config: DeploymentConfig = serde_json::from_str(&payload)
            .map_err(|error| format!("invalid {}: {error}", path.display()))?;
        return Ok(Some(config));
    }
    Ok(None)
}

#[derive(Default)]
struct LoopbackAuthState {
    listener: Mutex<Option<TcpListener>>,
    redirect_uri: Mutex<Option<String>>,
}

#[tauri::command]
fn start_loopback_auth(state: tauri::State<'_, LoopbackAuthState>) -> Result<String, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("cannot bind loopback listener: {error}"))?;
    listener
        .set_nonblocking(false)
        .map_err(|error| format!("cannot configure loopback listener: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| format!("cannot read loopback port: {error}"))?
        .port();
    let redirect_uri = format!("http://127.0.0.1:{port}/callback");
    *state.listener.lock().unwrap() = Some(listener);
    *state.redirect_uri.lock().unwrap() = Some(redirect_uri.clone());
    Ok(redirect_uri)
}

#[tauri::command]
fn open_browser_login_and_wait(
    state: tauri::State<'_, LoopbackAuthState>,
    authorization_url: String,
    expected_redirect_uri: String,
) -> Result<String, String> {
    let listener = state
        .listener
        .lock()
        .unwrap()
        .take()
        .ok_or_else(|| "loopback listener was not started".to_string())?;
    let registered_uri = state
        .redirect_uri
        .lock()
        .unwrap()
        .take()
        .unwrap_or_default();
    if registered_uri != expected_redirect_uri {
        return Err("redirect_uri does not match the started loopback listener".to_string());
    }
    listener
        .set_nonblocking(false)
        .map_err(|error| format!("cannot configure loopback listener: {error}"))?;

    thread::spawn(move || {
        let url = authorization_url.clone();
        #[cfg(target_os = "windows")]
        {
            let _ = Command::new("cmd")
                .args(["/C", "start", "", &url])
                .spawn();
        }
        #[cfg(not(target_os = "windows"))]
        {
            let _ = Command::new("xdg-open").arg(&url).spawn();
        }
    });

    let (mut stream, _) = listener
        .accept()
        .map_err(|error| format!("loopback accept failed: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(15)))
        .map_err(|error| format!("loopback timeout config failed: {error}"))?;
    let mut buffer = [0_u8; 8192];
    let read = stream
        .read(&mut buffer)
        .map_err(|error| format!("loopback read failed: {error}"))?;
    let request = String::from_utf8_lossy(&buffer[..read]);
    let path = request
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .unwrap_or("");
    if !path.starts_with("/callback?") {
        return Err("loopback callback did not include an authorization code".to_string());
    }
    let body = b"<html><body><h1>Eurogas Nexus login complete</h1><p>You may close this window and return to the desktop app.</p></body></html>";
    let _ = write_http_ok(&mut stream, body);
    Ok(path.trim_start_matches("/callback?").to_string())
}

fn write_http_ok(stream: &mut std::net::TcpStream, body: &[u8]) -> std::io::Result<()> {
    use std::io::Write;

    write!(
        stream,
        "HTTP/1.1 200 OK

Content-Type: text/html; charset=utf-8

Content-Length: {}

Connection: close



",
        body.len()
    )?;
    stream.write_all(body)?;
    stream.flush()
}

fn main() {
    tauri::Builder::default()
        .manage(LoopbackAuthState::default())
        .invoke_handler(tauri::generate_handler![
            read_deployment_config,
            start_loopback_auth,
            open_browser_login_and_wait
        ])
        .setup(|app| {
            let main_window = app
                .get_webview_window("main")
                .expect("main window is configured");
            let splashscreen = app
                .get_webview_window("splashscreen")
                .expect("splashscreen window is configured");

            tauri::async_runtime::spawn(async move {
                thread::sleep(Duration::from_millis(1200));
                let _ = main_window.show();
                let _ = main_window.set_focus();
                let _ = splashscreen.close();
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Eurogas Nexus desktop shell");
}
