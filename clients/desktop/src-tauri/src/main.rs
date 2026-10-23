#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env, fs,
    io::{self, Read},
    net::TcpListener,
    path::PathBuf,
    process::Command,
    sync::mpsc::{self, Sender},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};
use tauri::{Emitter, Manager};

/// Upper bound for waiting on the Web workspace readiness signal. A backend that
/// cannot be reached must still reveal the sign-in screen instead of trapping the
/// user on the splashscreen.
const CLIENT_READY_FALLBACK: Duration = Duration::from_secs(15);
// Match the backend authorization-state lifetime; a cancelled browser login
// must release the one-shot listener and let the user retry.
const LOOPBACK_AUTH_TIMEOUT: Duration = Duration::from_secs(300);

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
async fn open_browser_login_and_wait(
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
    // Async Tauri commands keep the window event loop responsive; all socket
    // waits run on the blocking pool rather than an async executor thread.
    tauri::async_runtime::spawn_blocking(move || {
        wait_for_browser_login(listener, authorization_url)
    })
    .await
    .map_err(|error| format!("desktop login task failed: {error}"))?
}

fn wait_for_browser_login(
    listener: TcpListener,
    authorization_url: String,
) -> Result<String, String> {
    let url = validate_browser_login_url(&authorization_url)?;
    #[cfg(target_os = "windows")]
    let launch = Command::new("rundll32.exe")
        .arg("url.dll,FileProtocolHandler")
        .arg(&url)
        .spawn();
    #[cfg(target_os = "macos")]
    let launch = Command::new("open").arg(&url).spawn();
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    let launch = Command::new("xdg-open").arg(&url).spawn();
    launch.map_err(|error| format!("cannot open sign-in browser: {error}"))?;

    let mut stream = accept_loopback_callback(&listener, LOOPBACK_AUTH_TIMEOUT)
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

fn validate_browser_login_url(value: &str) -> Result<String, String> {
    let url = tauri::Url::parse(value).map_err(|_| "invalid sign-in URL".to_string())?;
    if !matches!(url.scheme(), "https" | "http")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("sign-in requires an HTTP(S) URL without embedded credentials".to_string());
    }
    Ok(url.to_string())
}

fn accept_loopback_callback(
    listener: &TcpListener,
    timeout: Duration,
) -> io::Result<std::net::TcpStream> {
    listener.set_nonblocking(true)?;
    let started = Instant::now();
    loop {
        if started.elapsed() >= timeout {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "desktop login timed out; please sign in again",
            ));
        }
        match listener.accept() {
            Ok((stream, _)) => {
                stream.set_nonblocking(false)?;
                return Ok(stream);
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(
                    Duration::from_millis(25).min(timeout - started.elapsed().min(timeout)),
                );
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
}

fn write_http_ok(stream: &mut std::net::TcpStream, body: &[u8]) -> std::io::Result<()> {
    use std::io::Write;

    write!(
        stream,
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    stream.write_all(body)?;
    stream.flush()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_response_has_valid_headers_and_exact_body() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            write_http_ok(&mut stream, b"login complete").unwrap();
        });
        let mut client = std::net::TcpStream::connect(address).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut response = String::new();
        client.read_to_string(&mut response).unwrap();
        server.join().unwrap();
        assert_eq!(
            response,
            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: 14\r\nConnection: close\r\n\r\nlogin complete"
        );
    }
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
        .on_menu_event(|app, event| {
            let id = event.id().as_ref();
            if let Some(window) = app.get_webview_window("main") {
                match id {
                    "window.fullscreen" => {
                        let _ = window.set_fullscreen(!window.is_fullscreen().unwrap_or(false));
                    }
                    "window.minimize" => {
                        let _ = window.minimize();
                    }
                    "window.maximize" => {
                        if window.is_maximized().unwrap_or(false) {
                            let _ = window.unmaximize();
                        } else {
                            let _ = window.maximize();
                        }
                    }
                    "palette.toggle"
                    | "navigate.primary.market"
                    | "navigate.primary.portfolio"
                    | "navigate.primary.strategy"
                    | "navigate.primary.decision"
                    | "navigate.primary.system"
                    | "navigate.primary.administration" => {
                        let _ = window.emit("workstation-command", id);
                    }
                    _ => {}
                }
            }
        })
        .setup(|app| {
            let main_window = app
                .get_webview_window("main")
                .expect("main window is configured");
            // Native window commands work even when the API is unavailable.
            // Navigation remains a permission-checked command in the shared client.
            let workspace_menu = SubmenuBuilder::new(app, "Workspace")
                .text("palette.toggle", "Search commands…")
                .separator()
                .text("navigate.primary.market", "Market")
                .text("navigate.primary.portfolio", "Portfolio")
                .text("navigate.primary.strategy", "Strategy Lab")
                .text("navigate.primary.decision", "Decision Center")
                .text("navigate.primary.system", "System")
                .text("navigate.primary.administration", "Administration")
                .build()?;
            let edit_menu = SubmenuBuilder::new(app, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .select_all()
                .build()?;
            let fullscreen = MenuItemBuilder::with_id("window.fullscreen", "Toggle full screen")
                .accelerator("F11")
                .build(app)?;
            let window_menu = SubmenuBuilder::new(app, "Window")
                .item(&fullscreen)
                .text("window.minimize", "Minimize")
                .text("window.maximize", "Maximize / Restore")
                .build()?;
            let menu = MenuBuilder::new(app)
                .item(&workspace_menu)
                .item(&edit_menu)
                .item(&window_menu)
                .build()?;
            main_window.set_menu(menu)?;
            let splashscreen = app
                .get_webview_window("splashscreen")
                .expect("splashscreen is configured");

            let (sender, receiver) = mpsc::channel::<()>();
            *app.state::<ClientReadiness>()
                .sender
                .lock()
                .expect("client readiness state is available") = Some(sender);

            tauri::async_runtime::spawn_blocking(move || {
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
#[test]
fn loopback_accept_times_out_without_callback_and_releases_port() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let error = accept_loopback_callback(&listener, Duration::from_millis(30)).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    drop(listener);
    assert!(TcpListener::bind(address).is_ok());
}

#[test]
fn loopback_accept_receives_a_real_callback_connection() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let _client = std::net::TcpStream::connect(address).unwrap();
    let stream = accept_loopback_callback(&listener, Duration::from_secs(5)).unwrap();
    assert_eq!(stream.local_addr().unwrap(), address);
}

#[test]
fn browser_login_refuses_local_commands_and_embedded_credentials() {
    for value in [
        "file:///tmp/run",
        "javascript:alert(1)",
        "--help",
        "https://user:secret@example.test/",
    ] {
        assert!(validate_browser_login_url(value).is_err());
    }
    assert_eq!(
        validate_browser_login_url("https://idp.example.test/authorize?state=a&nonce=b").unwrap(),
        "https://idp.example.test/authorize?state=a&nonce=b"
    );
}
