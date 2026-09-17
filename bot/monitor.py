from __future__ import annotations

import subprocess
import threading
from datetime import date
from urllib.error import URLError
from urllib.request import Request, urlopen

from .meta import MetaClient
from .notifications import TelegramNotifier
from .store import Store


class HealthMonitor:
    def __init__(self, store: Store, meta: MetaClient, notifier: TelegramNotifier,
                 public_base_url: str):
        self.store = store
        self.meta = meta
        self.notifier = notifier
        self.public_base_url = public_base_url.rstrip("/")
        self._stop = threading.Event()
        self._cleanup_date: date | None = None
        self._overall_state: str | None = None

    def start(self) -> None:
        self.store.set_health("bot", "ok", "Процес бота працює")
        self.store.set_health("tunnel", "info", "Очікування мережі й запуску тунелю")
        self.store.set_health("public_webhook", "info", "Перевірка після готовності мережі")
        self.store.set_health("instagram_api", "info", "Перевірка після готовності мережі")
        threading.Thread(target=self._loop, daemon=True, name="instagram-health").start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # The user service can start a few seconds before Ubuntu's DNS resolver.
        if self._stop.wait(15):
            return
        while not self._stop.is_set():
            healthy = self.run_once()
            if self._stop.wait(5 * 60 if healthy else 30):
                return

    def run_once(self) -> bool:
        healthy = True
        failures: list[str] = []
        self._record("bot", "ok", "Процес бота працює")
        tunnel = self._service_state("instagram-guide-tunnel.service")
        self._record("tunnel", "ok" if tunnel == "active" else "error", f"Стан служби: {tunnel}")
        healthy = healthy and tunnel == "active"
        if tunnel != "active":
            failures.append(f"Cloudflare Tunnel: {tunnel}")
        try:
            request = Request(f"{self.public_base_url}/health", headers={"User-Agent": "FraxlerHealth/1.0"})
            with urlopen(request, timeout=15) as response:
                public_ok = response.status == 200
            self._record("public_webhook", "ok" if public_ok else "error", f"Публічна адреса повернула HTTP {response.status}")
            healthy = healthy and public_ok
            if not public_ok:
                failures.append(f"Публічний webhook: HTTP {response.status}")
        except (URLError, TimeoutError, OSError) as exc:
            self._record("public_webhook", "error", f"Публічна адреса недоступна: {str(exc)[:400]}")
            healthy = False
            failures.append(f"Публічний webhook: {str(exc)[:180]}")
        try:
            account = self.meta.get_account()
            detail = f"API доступний: @{account.get('username', 'акаунт')}"
            self._record("instagram_api", "ok", detail)
        except Exception as exc:
            self._record("instagram_api", "error", str(exc)[:500])
            healthy = False
            failures.append(f"Instagram API: {str(exc)[:180]}")
        last = self.store.latest_webhook_at()
        self._record("webhook_events", "ok" if last else "info", f"Остання подія: {last or 'ще не отримувалась'}")
        if self._cleanup_date != date.today():
            try:
                days = int(self.store.get_setting("retention_days") or "90")
            except ValueError:
                days = 90
            self.store.cleanup_old_data(days)
            self._cleanup_date = date.today()
        self._notify_overall(failures)
        return healthy

    def _record(self, key: str, status: str, detail: str) -> None:
        self.store.set_health(key, status, detail)

    def _notify_overall(self, failures: list[str]) -> None:
        if not failures:
            state = "healthy"
            title = "✅ Схему повністю відновлено" if self._overall_state in {"degraded", "unavailable"} else "✅ Схема працює"
            detail = "Instagram API, Cloudflare Tunnel і публічний webhook доступні."
        elif len(failures) >= 3:
            state = "unavailable"
            title = "🔴 Схема не працює"
            detail = "Недоступні всі зовнішні компоненти:\n• " + "\n• ".join(failures)
        else:
            state = "degraded"
            title = "🟠 Схема працює частково"
            detail = "Виявлено проблеми:\n• " + "\n• ".join(failures)
        if state == self._overall_state:
            return
        self._overall_state = state
        self.notifier.send(title, detail)

    @staticmethod
    def _service_state(name: str) -> str:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", name], capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() or "невідомо"
        except (OSError, subprocess.TimeoutExpired):
            return "невідомо"
