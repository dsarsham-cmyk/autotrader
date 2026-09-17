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

import webview

DASHBOARD_URL = "https://dsarsham-cmyk.github.io/autotrader/"
WINDOW_TITLE = "Auto Trader — Control Center"
WIDTH, HEIGHT = 1280, 860
MIN_WIDTH, MIN_HEIGHT = 860, 600


def main() -> None:
    webview.create_window(
        WINDOW_TITLE,
        DASHBOARD_URL,
        width=WIDTH,
        height=HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        background_color="#0f1115",
    )

    # `edgechromium` uses Windows' built-in Edge WebView2 (no extra install).
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
