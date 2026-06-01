"""Client release-surface contracts for Web and Windows shells."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_client_wraps_shared_web_workspace() -> None:
    config = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )

    assert config["build"]["frontendDist"] == "../../web/dist"
    assert config["build"]["beforeBuildCommand"] == "npm --prefix ../web run build"
    assert config["build"]["devUrl"] == "http://127.0.0.1:3000"
    assert config["app"]["windows"][0]["label"] == "main"
    assert config["app"]["windows"][0]["decorations"] is False
    assert config["app"]["windows"][0]["fullscreen"] is True
    assert config["app"]["windows"][0]["visible"] is False
    assert config["bundle"]["active"] is True


def test_windows_client_uses_startup_splash_window() -> None:
    config = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    main_rs = (
        ROOT / "clients" / "desktop" / "src-tauri" / "src" / "main.rs"
    ).read_text(encoding="utf-8")

    windows = {window["label"]: window for window in config["app"]["windows"]}
    assert windows["splashscreen"]["visible"] is True
    assert windows["splashscreen"]["decorations"] is False
    assert windows["splashscreen"]["fullscreen"] is False
    assert 'get_webview_window("main")' in main_rs
    assert 'get_webview_window("splashscreen")' in main_rs
    assert "main_window.show()" in main_rs
    assert "splashscreen.close()" in main_rs


def test_windows_client_has_minimal_safe_permissions() -> None:
    capability = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "capabilities" / "default.json")
        .read_text(encoding="utf-8")
    )
    config_text = (
        ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json"
    ).read_text(encoding="utf-8")

    assert capability["permissions"] == ["core:default"]
    assert "postgres" not in config_text.lower()
    assert "DATABASE_URL" not in config_text
    assert ".env" not in config_text
    assert "connect-src 'self' http://localhost:* http://127.0.0.1:*" in config_text


def test_client_dependency_policy_excludes_disallowed_frameworks() -> None:
    web_package = json.loads(
        (ROOT / "clients" / "web" / "package.json").read_text(encoding="utf-8")
    )
    desktop_package = json.loads(
        (ROOT / "clients" / "desktop" / "package.json").read_text(encoding="utf-8")
    )
    names = set(web_package.get("dependencies", {}))
    names |= set(web_package.get("devDependencies", {}))
    names |= set(desktop_package.get("dependencies", {}))
    names |= set(desktop_package.get("devDependencies", {}))

    forbidden = {
        "electron",
        "next",
        "tailwindcss",
        "@mui/material",
        "antd",
        "bootstrap",
        "redux",
    }
    assert names.isdisjoint(forbidden)
    assert "@tauri-apps/cli" in names


def test_web_client_uses_api_only_and_supports_mandarin_theme() -> None:
    api_client = (
        ROOT / "clients" / "web" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert 'const BASE = "/api/v1";' in api_client
    assert "postgres" not in api_client.lower()
    assert "RUNTIME_STORE_DATABASE_URL" not in api_client
    assert zh["nav.sources"] == "数据源"
    assert zh["theme.dark"] == "深色"
    assert '<option value="zh-CN">中文</option>' in app
