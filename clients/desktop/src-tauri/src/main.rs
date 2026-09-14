#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env, fs,
    io::Read,
    net::TcpListener,
    path::PathBuf,
    process::Command,
    sync::mpsc::{self, Sender},
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use tauri::Manager;

/// Upper bound for waiting on the Web workspace readiness signal. A backend that
/// cannot be reached must still reveal the sign-in screen instead of trapping the
/// user on the splashscreen.
const CLIENT_READY_FALLBACK: Duration = Duration::from_secs(15);

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

/// One-shot readiness signal from the shared Web workspace.
///
/// The desktop shell keeps the splashscreen in front until the Web app reports
/// that it has resolved identity - which includes rendering the sign-in screen -
/// so the terminal and its protected panels are never shown to an unauthenticated
/// visitor during startup.
#[derive(Default)]
struct ClientReadiness {
    sender: Mutex<Option<Sender<()>>>,
}

#[tauri::command]
fn notify_client_ready(state: tauri::State<'_, ClientReadiness>) -> Result<(), String> {
    let guard = state
        .sender
        .lock()
        .map_err(|error| format!("client readiness lock poisoned: {error}"))?;
    if let Some(sender) = guard.as_ref() {
        // A closed receiver means the fallback already revealed the window.
        let _ = sender.send(());
    }
    Ok(())
}

/// Drop the WebView's cookies, caches and local storage after a sign-out.
///
/// The backend session is revoked and the client clears its stored credentials
/// before this runs, so this only removes what the shared workspace kept on the
/// workstation. Non-secret preferences (theme, language, map tiles) are cleared
/// with it, which is the intended behaviour on a shared machine.
#[tauri::command]
fn clear_client_session_data(window: tauri::WebviewWindow) -> Result<(), String> {
    window
        .clear_all_browsing_data()
        .map_err(|error| format!("cannot clear WebView browsing data: {error}"))
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
        .manage(ClientReadiness::default())
        .invoke_handler(tauri::generate_handler![
            read_deployment_config,
            start_loopback_auth,
            open_browser_login_and_wait,
            notify_client_ready,
            clear_client_session_data
        ])
        .setup(|app| {
            let main_window = app
                .get_webview_window("main")
                .expect("main window is configured");
            let splashscreen = app
                .get_webview_window("splashscreen")
                .expect("splashscreen is configured");

            let (sender, receiver) = mpsc::channel::<()>();
            *app.state::<ClientReadiness>()
                .sender
                .lock()
                .expect("client readiness state is available") = Some(sender);

            tauri::async_runtime::spawn(async move {
                // Wait for the Web workspace to report identity resolution (the
                // sign-in screen counts), then reveal it. The bounded fallback keeps
                // an unreachable backend from trapping the user on the splashscreen.
                let _ = receiver.recv_timeout(CLIENT_READY_FALLBACK);
                let _ = main_window.show();
                let _ = main_window.set_focus();
                let _ = splashscreen.close();
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Eurogas Nexus desktop shell");
}
