from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import Config, get_config
from .admin import make_admin_server
from .accounts import AccountError, AccountManager
from .meta import MetaClient
from .monitor import HealthMonitor
from .notifications import TelegramNotifier
from .processor import Processor
from .store import Store


LOGGER = logging.getLogger("guide_bot")


class GuideBotServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: Config):
        super().__init__(address, RequestHandler)
        self.config = config
        self.store = Store(config.db_path)
        self.store.ensure_default_automations(
            config.allowed_media_ids,
            config.trigger_keywords,
            config.confirmation_words,
            config.public_reply_text,
            config.initial_dm_text,
            config.guide_message_text,
            config.guide_pdf_path,
        )
        self.accounts = AccountManager(config, self.store)
        try:
            self.meta = self.accounts.client()
        except AccountError:
            self.meta = MetaClient(config)
        self.notifier = TelegramNotifier(self.store)
        self.processor = Processor(
            config, self.store, self.meta, self.notifier,
            lambda database_id, instagram_id="": self.accounts.client(database_id, instagram_id),
        )
        self.monitor = HealthMonitor(self.store, self.meta, self.notifier, config.public_base_url)


class RequestHandler(BaseHTTPRequestHandler):
    server: GuideBotServer

    def log_message(self, fmt: str, *args) -> None:
        LOGGER.info("%s - %s", self.client_address[0], fmt % args)

    def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            missing = self.server.config.missing_required
            payload = {
                "status": "ready" if not missing and self.server.config.guide_pdf_path.is_file() else "needs_configuration",
                "missing": missing,
                "pdf_exists": self.server.config.guide_pdf_path.is_file(),
            }
            self._send(200, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if parsed.path == "/webhook":
            query = parse_qs(parsed.query)
            mode = query.get("hub.mode", [""])[0]
            token = query.get("hub.verify_token", [""])[0]
            challenge = query.get("hub.challenge", [""])[0]
            if mode == "subscribe" and hmac.compare_digest(token, self.server.config.verify_token):
                self._send(200, challenge.encode())
            else:
                self._send(HTTPStatus.FORBIDDEN, b"Verification failed")
            return
        if parsed.path == "/oauth/instagram/callback":
            query = parse_qs(parsed.query)
            if query.get("error"):
                message = query.get("error_description", query.get("error", ["Підключення скасовано"]))[0]
                self._oauth_result(False, message)
                return
            try:
                account = self.server.accounts.complete_oauth(
                    query.get("code", [""])[0], query.get("state", [""])[0]
                )
                self._oauth_result(True, f"Instagram-акаунт @{account.username} підключено. Поверніться до локальної вебпанелі.")
            except AccountError as exc:
                self._oauth_result(False, str(exc))
            return
        if parsed.path == "/files/guide.pdf":
            self._serve_file(self.server.config.guide_pdf_path)
            return
        if parsed.path.startswith("/files/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "files":
                try:
                    automation = self.server.store.get_automation(int(parts[1]))
                except ValueError:
                    automation = None
                if automation is not None:
                    self._serve_file(Path(str(automation["pdf_path"])))
                    return
            self._send(HTTPStatus.NOT_FOUND, b"File not found")
            return
        if parsed.path == "/privacy":
            self._serve_public_page("privacy.html")
            return
        if parsed.path == "/data-deletion":
            self._serve_public_page("data-deletion.html")
            return
        self._send(HTTPStatus.NOT_FOUND, b"Not found")

    def _oauth_result(self, success: bool, message: str) -> None:
        import html
        color = "#34c98b" if success else "#ef6576"
        title = "Акаунт підключено" if success else "Помилка підключення"
        body = f'''<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head><body style="margin:0;background:#0b0f17;color:#f4f7fb;font:16px system-ui;display:grid;place-items:center;min-height:100vh"><main style="width:min(520px,calc(100% - 32px));background:#111824;border:1px solid #253044;border-radius:18px;padding:28px"><div style="color:{color};font-size:42px">{'✓' if success else '!'}</div><h1>{title}</h1><p>{html.escape(message)}</p><p style="color:#8f9bb0">Цю вкладку можна закрити.</p></main></body></html>'''
        self._send(200 if success else 400, body.encode(), "text/html; charset=utf-8")

    def _serve_public_page(self, filename: str) -> None:
        path = Path(__file__).resolve().parent.parent / "assets" / filename
        if not path.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"Page not found")
            return
        self._send(200, path.read_bytes(), "text/html; charset=utf-8")

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"Guide file not found")
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        safe_name = path.name if path.name.isascii() and all(ch.isalnum() or ch in "._-" for ch in path.name) else "file"
        disposition = "inline" if content_type.startswith(("image/", "video/", "audio/", "text/")) or content_type == "application/pdf" else "attachment"
        self.send_header("Content-Disposition", f'{disposition}; filename="{safe_name}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/webhook":
            self._send(HTTPStatus.NOT_FOUND, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(HTTPStatus.BAD_REQUEST, b"Invalid content length")
            return
        if length <= 0 or length > 1_000_000:
            self._send(HTTPStatus.BAD_REQUEST, b"Invalid payload size")
            return
        body = self.rfile.read(length)
        if not self._valid_signature(body):
            self._send(HTTPStatus.FORBIDDEN, b"Invalid signature")
            return
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send(HTTPStatus.BAD_REQUEST, b"Invalid JSON")
            return
        self.server.store.record_webhook(payload)
        self._send(200, b"EVENT_RECEIVED")
        threading.Thread(target=self.server.processor.process, args=(payload,), daemon=True).start()

    def _valid_signature(self, body: bytes) -> bool:
        if not self.server.config.signature_required:
            return True
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256=") or not self.server.config.app_secret:
            return False
        expected = hmac.new(
            self.server.config.app_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature[7:], expected)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = get_config()
    server = GuideBotServer((config.host, config.port), config)
    admin_server = make_admin_server(config, server.store, server.meta, server.accounts)
    admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
    admin_thread.start()
    server.processor.start()
    server.monitor.start()
    stopping = threading.Event()

    def request_shutdown(signum, _frame) -> None:
        if stopping.is_set():
            return
        stopping.set()
        LOGGER.info("Received signal %s; stopping gracefully", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    LOGGER.info("Guide bot listening on http://%s:%s", config.host, config.port)
    LOGGER.info("Fraxler Insta Automation panel listening on http://%s:%s/admin/", config.admin_host, config.admin_port)
    if config.missing_required:
        LOGGER.warning("Missing configuration: %s", ", ".join(config.missing_required))
    def notify_started() -> None:
        # Ubuntu may start user services before DNS is ready. Retry silently.
        if stopping.wait(15):
            return
        for _attempt in range(6):
            if server.notifier.send(
                "🟢 Система запускається",
                "Ubuntu запущено, служба Instagram-бота почала роботу.",
            ):
                return
            if stopping.wait(30):
                return

    threading.Thread(target=notify_started, daemon=True, name="startup-notification").start()
    try:
        server.serve_forever()
    finally:
        server.processor.stop()
        server.monitor.stop()
        server.notifier.send(
            "⚫ Служба зупиняється",
            "Fraxler Insta Automation коректно завершує роботу.",
        )
        admin_server.shutdown()
        admin_server.server_close()
        server.server_close()


if __name__ == "__main__":
    main()
