#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, fs, path::PathBuf, thread, time::Duration};

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

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![read_deployment_config])
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
