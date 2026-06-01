#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{thread, time::Duration};

use tauri::Manager;

fn main() {
    tauri::Builder::default()
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
