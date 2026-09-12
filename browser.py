"""Browser automation helper (Playwright + headless Chromium).

Provides a simple interface for controlling a real Chromium browser: fetch
page text/HTML, take screenshots, click, fill forms, and evaluate JavaScript.
Used for research and for automating sites that have no API.

Usage:
    from browser import Browser
    with Browser() as b:
        text = b.text("https://example.com")          # visible text
        b.screenshot("https://example.com", "shot.png")
        b.click("https://example.com", "text=More info")
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright


class Browser:
    """A thin wrapper around a headless Chromium browser."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw = None
        self._browser = None

    def __enter__(self) -> "Browser":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _page(self, url: str):
        page = self._browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page

    def text(self, url: str) -> str:
        """Return the visible text of a page."""
        page = self._page(url)
        try:
            return page.inner_text("body")
        finally:
            page.close()

    def html(self, url: str) -> str:
        """Return the full HTML of a page."""
        page = self._page(url)
        try:
            return page.content()
        finally:
            page.close()

    def screenshot(self, url: str, path: str, full_page: bool = False) -> str:
        """Navigate to a URL and save a screenshot. Returns the path."""
        page = self._page(url)
        try:
            page.screenshot(path=path, full_page=full_page)
            return path
        finally:
            page.close()

    def click(self, url: str, selector: str) -> None:
        """Navigate to a URL and click an element matching `selector`."""
        page = self._page(url)
        try:
            page.click(selector)
        finally:
            page.close()

    def fill(self, url: str, selector: str, value: str) -> None:
        """Navigate to a URL and fill an input matching `selector`."""
        page = self._page(url)
        try:
            page.fill(selector, value)
        finally:
            page.close()


if __name__ == "__main__":
    with Browser() as b:
        print(b.text("https://example.com")[:200])
