"""Trade alerts via Telegram and/or Discord webhooks.

Credentials are read from environment variables (see .env.example) so they
never live in config or source control.
"""
from __future__ import annotations

import os
import urllib.request
import urllib.parse


class AlertManager:
    """Sends notifications. Each channel is optional and enabled only if
    its credentials are present."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        # Comma-separated list of chat IDs (private chat + groups).
        raw_chats = os.getenv("TELEGRAM_CHAT_ID", "")
        self.telegram_chat_ids = [
            c.strip() for c in raw_chats.split(",") if c.strip()
        ]
        self.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.ntfy_topic = os.getenv("NTFY_TOPIC", "")

    @property
    def any_configured(self) -> bool:
        return (bool(self.telegram_token and self.telegram_chat_ids)
                or bool(self.discord_webhook) or bool(self.ntfy_topic))

    def send(self, message: str) -> None:
        if not self.enabled:
            return
        if self.telegram_token and self.telegram_chat_ids:
            self._send_telegram(message)
        if self.discord_webhook:
            self._send_discord(message)
        if self.ntfy_topic:
            self._send_ntfy(message)

    def _send_telegram(self, message: str) -> None:
        url = (
            f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        )
        for chat_id in self.telegram_chat_ids:
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": message,
            }).encode()
            try:
                req = urllib.request.Request(url, data=data)
                urllib.request.urlopen(req, timeout=10)
            except Exception as e:  # never crash the bot on alert failure
                print(f"[alerts] telegram error (chat {chat_id}): {e}")

    def _send_discord(self, message: str) -> None:
        import json
        payload = json.dumps({"content": message}).encode()
        req = urllib.request.Request(
            self.discord_webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[alerts] discord error: {e}")

    def _send_ntfy(self, message: str) -> None:
        url = f"https://ntfy.sh/{self.ntfy_topic}"
        req = urllib.request.Request(url, data=message.encode(), method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[alerts] ntfy error: {e}")
