"""Auto Trader — native Windows desktop app.

Opens the live control-center dashboard in a native desktop window (using
Windows' built-in Edge WebView2, so no browser is required). The dashboard
auto-refreshes every 60s, so this window is always up to date.

Run directly:
    python desktop_app.py

Or build a standalone .exe with:
    build_windows.bat
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import webview

if sys.platform == "win32":
    import winreg

DASHBOARD_URL = "https://dsarsham-cmyk.github.io/autotrader/"
WINDOW_TITLE = "Auto Trader — Control Center"
WIDTH, HEIGHT = 1280, 860
MIN_WIDTH, MIN_HEIGHT = 860, 600
APP_NAME = "AutoTrader"
APP_VERSION = "2.0"


def executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.executable).resolve()


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{executable_path()}" --startup'
    script = Path(__file__).resolve()
    pythonw = executable_path().with_name("pythonw.exe")
    return f'"{pythonw}" "{script}" --startup'


class AppApi:
    """Small native bridge exposed only inside the Windows desktop shell."""

    registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def startup_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_path) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False

    def get_app_status(self) -> dict:
        return {
            "desktop": True,
            "version": APP_VERSION,
            "startup_enabled": self.startup_enabled(),
            "executable": str(executable_path()),
        }

    def set_startup(self, enabled: bool) -> dict:
        if sys.platform != "win32":
            return self.get_app_status()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.registry_path) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return self.get_app_status()


def already_running() -> bool:
    """Use a named Windows mutex so startup and manual launch make one window."""
    if sys.platform != "win32":
        return False
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AutoTraderDesktopApp")
    return ctypes.windll.kernel32.GetLastError() == 183


def main() -> None:
    api = AppApi()
    if "--enable-startup" in sys.argv:
        api.set_startup(True)
        return
    if "--disable-startup" in sys.argv:
        api.set_startup(False)
        return
    if already_running():
        return

    webview.create_window(
        WINDOW_TITLE,
        DASHBOARD_URL,
        width=WIDTH,
        height=HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        background_color="#0f1115",
        js_api=api,
    )

    # `edgechromium` uses Windows' built-in Edge WebView2 (no extra install).
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
