from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .store import Store


LOGGER = logging.getLogger("guide_bot")


class TelegramNotifier:
    def __init__(self, store: Store):
        self.store = store

    def enabled(self) -> bool:
        return self.store.get_setting("telegram_enabled") == "1"

    def send(self, title: str, detail: str) -> bool:
        if not self.enabled():
            return False
        token = self.store.get_setting("telegram_bot_token") or ""
        chat_id = self.store.get_setting("telegram_chat_id") or ""
        if not token or not chat_id:
            return False
        body = json.dumps({
            "chat_id": chat_id,
            "text": f"🤖 Fraxler Insta Automation\n\n{title}\n{detail}"[:4000],
            "disable_web_page_preview": True,
        }).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "FraxlerInstaAutomation/1.0"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                return bool(result.get("ok"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            LOGGER.warning("Telegram notification failed: %s", type(exc).__name__)
            return False
