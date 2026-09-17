from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .config import Config
from .accounts import AccountError, AccountManager
from .files import FILE_ACCEPT, ALLOWED_EXTENSIONS, normalized_folder, unique_file_path, validate_upload
from .meta import MetaClient
from .store import Store


SESSION_COOKIE = "fraxler_admin"
SESSION_SECONDS = 12 * 60 * 60
MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_UPLOAD = MAX_FILE_SIZE + 2 * 1024 * 1024
PBKDF2_ROUNDS = 310_000

CSS = """
:root{color-scheme:dark;--bg:#0b0f17;--sidebar:#0d121c;--surface:#111824;--surface-2:#161f2e;--surface-3:#1c2738;--text:#f4f7fb;--muted:#8f9bb0;--line:#253044;--line-soft:#1d2736;--accent:#7567f8;--accent-hover:#8a7dfb;--accent-soft:#24214b;--ok:#34c98b;--ok-soft:#12372c;--warn:#f3b64b;--warn-soft:#3b3020;--bad:#ef6576;--bad-soft:#3f202a;--shadow:0 16px 40px rgba(0,0,0,.22)}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}a{color:#a99fff;text-decoration:none}button,input,textarea,select{font:inherit}.app-shell{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;padding:22px 16px;border-right:1px solid var(--line-soft);background:var(--sidebar);display:flex;flex-direction:column;z-index:30}.brand{display:flex;align-items:center;gap:11px;padding:4px 10px 22px;font-size:17px;font-weight:780;letter-spacing:-.02em;color:var(--text)}.brand-mark{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:linear-gradient(145deg,#8b7fff,#5d4ee7);color:white;font-weight:900;box-shadow:0 8px 24px rgba(117,103,248,.28)}.brand-copy small{display:block;color:var(--muted);font-size:12px;font-weight:560;letter-spacing:0}.nav{display:flex;flex-direction:column;gap:4px}.nav-link{display:flex;align-items:center;gap:11px;min-height:43px;padding:9px 11px;border-radius:10px;color:var(--muted);font-size:14px;font-weight:650;transition:.16s ease}.nav-link:hover{color:var(--text);background:var(--surface-2)}.nav-link.active{color:#fff;background:var(--accent-soft);box-shadow:inset 3px 0 var(--accent)}.nav-icon{width:20px;text-align:center;font-size:15px}.sidebar-actions{margin-top:auto;display:grid;gap:8px;padding-top:18px}.workspace{min-width:0;padding:30px clamp(20px,3vw,46px) 56px}.workspace-inner{width:min(100%,1320px);margin:0 auto}.mobile-bar{display:none}.panel{background:var(--surface);border:1px solid var(--line-soft);border-radius:16px;padding:22px;box-shadow:0 1px 0 rgba(255,255,255,.02)}.panel+.panel{margin-top:16px}.panel h1{font-size:26px;line-height:1.2;letter-spacing:-.035em;margin:0 0 18px}.panel h2{font-size:18px;letter-spacing:-.02em}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}.card{background:var(--surface-2);border:1px solid var(--line-soft);border-radius:14px;padding:18px;transition:border-color .16s ease,transform .16s ease}.card:hover{border-color:#384760;transform:translateY(-1px)}.card h3{font-size:16px;margin:0 0 6px;letter-spacing:-.015em}.muted{color:var(--muted)}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.between{justify-content:space-between}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}.btn,button{display:inline-flex;min-height:40px;align-items:center;justify-content:center;border:1px solid transparent;border-radius:10px;padding:8px 13px;background:var(--accent);color:#fff;font-weight:700;font-size:14px;cursor:pointer;transition:.16s ease}.btn:hover,button:hover{background:var(--accent-hover)}.btn.secondary,button.secondary{background:var(--surface-3);border-color:var(--line);color:var(--text)}.btn.ghost,button.ghost{background:transparent;border-color:var(--line);color:var(--muted)}.btn.ghost:hover,button.ghost:hover,.btn.secondary:hover,button.secondary:hover{background:var(--surface-3);color:var(--text)}.btn.danger,button.danger{background:var(--bad-soft);border-color:#69303d;color:#ffb6c0}.badge{display:inline-flex;align-items:center;min-height:24px;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:750}.on{background:var(--ok-soft);color:#71e0b1}.off{background:var(--bad-soft);color:#ff9dac}.archived{background:var(--warn-soft);color:#ffd27c}form.inline{display:inline}label{display:block;font-size:14px;font-weight:680;margin:15px 0 7px}input,textarea,select{width:100%;min-height:43px;border:1px solid var(--line);background:#0c121d;color:var(--text);border-radius:10px;padding:10px 12px;outline:none;transition:border-color .15s,box-shadow .15s}input:focus,textarea:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(117,103,248,.16)}textarea{min-height:96px;resize:vertical}.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.notice{padding:12px 14px;border:1px solid #31415e;border-radius:10px;margin-bottom:14px;background:#172238;color:#d7e4ff}.notice.error,.error{border-color:#64303c;background:var(--bad-soft);color:#ffc2ca}.okbox{border-color:#285d4d;background:var(--ok-soft);color:#b4f1d8}.service{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--line-soft)}.service:last-child{border-bottom:0}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}.stat{padding:17px;background:var(--surface-2);border:1px solid var(--line-soft);border-radius:13px}.stat strong{display:block;font-size:27px;line-height:1.15;letter-spacing:-.04em;margin-top:4px}.table-wrap{width:100%;overflow:auto;border:1px solid var(--line-soft);border-radius:12px;margin-top:16px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line-soft);vertical-align:top;white-space:nowrap}th{background:var(--surface-2);color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:rgba(255,255,255,.018)}td.wrap{white-space:normal;min-width:210px}.steps{display:flex;gap:5px}.step{width:10px;height:10px;border-radius:50%;background:#3c465d}.step.done{background:var(--ok)}progress{width:100%;height:5px;accent-color:var(--accent)}.chat{display:flex;flex-direction:column;gap:10px;max-height:540px;overflow:auto;padding:14px 2px}.bubble{max-width:min(75%,620px);padding:11px 14px;border-radius:14px 14px 14px 4px;background:var(--surface-3)}.bubble.out{align-self:flex-end;border-radius:14px 14px 4px 14px;background:#4d43b4}.bubble .meta{display:block;font-size:12px;color:#bdc5d4;margin-top:6px}.danger-zone{border-color:#5c2935;background:#24151b}.rule{border:1px solid var(--line);background:var(--surface-2);padding:16px;border-radius:12px;margin:10px 0}.empty{text-align:center;padding:44px 20px;color:var(--muted)}code{background:#090e16;border:1px solid var(--line-soft);padding:2px 6px;border-radius:6px}.hero{width:min(100% - 32px,460px);margin:9vh auto;text-align:left}.hero h1{font-size:28px}.auth-shell{min-height:100vh;display:grid;place-items:start center;padding:24px}.auth-shell .brand{justify-content:center}.toast{position:fixed;right:22px;bottom:22px;max-width:min(380px,calc(100vw - 32px));padding:13px 16px;border:1px solid #2f8068;border-radius:11px;background:#153d32;color:#c8f8e4;box-shadow:var(--shadow);z-index:1000;animation:toast-in .22s ease}.toast.error{border-color:#a84d61;background:#4b222c;color:#ffd1d8}@keyframes toast-in{from{transform:translateY(14px);opacity:0}to{transform:none;opacity:1}}
html[data-theme="light"]{color-scheme:light;--bg:#f5f7fb;--sidebar:#fff;--surface:#fff;--surface-2:#f8f9fc;--surface-3:#eef1f6;--text:#172033;--muted:#667085;--line:#d8dee9;--line-soft:#e7eaf0;--accent:#6254e7;--accent-hover:#5145cd;--accent-soft:#eeecff;--ok-soft:#e7f8f1;--warn-soft:#fff4dc;--bad-soft:#fff0f2;--shadow:0 16px 40px rgba(19,32,56,.13)}html[data-theme="light"] .nav-link.active{color:#5145cd}html[data-theme="light"] input,html[data-theme="light"] textarea,html[data-theme="light"] select{background:#fff}html[data-theme="light"] code{background:#f2f4f7}html[data-theme="light"] .bubble.out{color:#fff}html[data-theme="light"] tbody tr:hover{background:#fafbfc}.theme-short{display:none}
@media(max-width:860px){.app-shell{display:block}.sidebar{position:sticky;height:auto;top:0;padding:10px 12px;border-right:0;border-bottom:1px solid var(--line);display:block;overflow:hidden}.sidebar .brand{padding:0 4px 10px}.brand-copy small{display:none}.nav{flex-direction:row;overflow-x:auto;padding-bottom:3px;scrollbar-width:none}.nav::-webkit-scrollbar{display:none}.nav-link{flex:0 0 auto;min-height:40px;padding:8px 11px}.nav-link.active{box-shadow:inset 0 -2px var(--accent)}.sidebar-actions{position:absolute;right:12px;top:9px;display:flex;padding:0}.sidebar-actions .create-link,.sidebar-actions form{display:none}.theme-button{min-height:36px!important;padding:6px 10px!important}.theme-label{display:none}.theme-short{display:inline}.workspace{padding:20px 14px 42px}.workspace-inner{width:100%}.panel{padding:17px;border-radius:14px}.grid{grid-template-columns:1fr}.two{grid-template-columns:1fr;gap:0}.panel h1{font-size:23px}.table-wrap{margin-left:0;margin-right:0}.toast{right:16px;bottom:16px}.bubble{max-width:88%}.service{align-items:flex-start}.service small{display:block}.actions .btn,.actions button{flex-grow:1}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:460px){.brand-mark{width:31px;height:31px}.nav-link{font-size:13px}.nav-icon{display:none}.stats{grid-template-columns:1fr 1fr}.stat strong{font-size:23px}.row.between{align-items:flex-start}.panel{padding:15px}.btn,button{min-height:42px}.hero{margin-top:5vh}.chat{max-height:430px}}
.mobile-logout{display:none}.auth-shell>div{width:100%}@media(max-width:860px){.mobile-logout{display:block;position:absolute;right:58px;top:9px}.mobile-logout button{min-height:36px;padding:6px 10px}}
.guide-steps{display:grid;gap:12px;counter-reset:guide}.guide-step{position:relative;padding:16px 16px 16px 58px;background:var(--surface-2);border:1px solid var(--line-soft);border-radius:13px;min-height:62px}.guide-step:before{counter-increment:guide;content:counter(guide);position:absolute;left:16px;top:16px;display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:var(--accent-soft);color:#b8b0ff;font-weight:850}.guide-step strong{display:block;margin-bottom:3px}.guide-step p{margin:0;color:var(--muted)}.checklist{display:grid;gap:9px;margin-top:14px}.check-item{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line-soft)}.check-item:last-child{border-bottom:0}.help-anchor{scroll-margin-top:24px}.copy-field{flex:1;min-width:240px}.mini-nav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.mini-nav a{padding:7px 10px;border:1px solid var(--line);border-radius:9px;background:var(--surface-2)}
.instagram-identity{display:flex;align-items:center;gap:10px;margin:13px 0 12px;padding:9px 11px;border:1px solid var(--line-soft);border-radius:12px;background:rgba(8,13,22,.28)}.instagram-avatar{width:40px;height:40px;flex:0 0 40px;border-radius:50%;object-fit:cover;background:var(--surface-3);border:1px solid var(--line)}.instagram-avatar.fallback{display:grid;place-items:center;color:#d8d3ff;background:linear-gradient(145deg,#3b315f,#242c45);font-weight:850;text-transform:uppercase}.instagram-identity strong{display:block;line-height:1.25;overflow-wrap:anywhere}.instagram-identity small{display:block;color:var(--muted);font-size:12px;margin-top:2px}
.library-preview{display:block;height:210px;margin:-5px -5px 15px;border-radius:11px;overflow:hidden;background:var(--surface-3);border:1px solid var(--line-soft)}.library-preview img{display:block;width:100%;height:100%;object-fit:cover;transition:transform .2s ease}.library-preview:hover img{transform:scale(1.025)}
.usage-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-top:14px}.usage-metric{padding:13px;border:1px solid var(--line-soft);border-radius:11px;background:rgba(8,13,22,.25)}.usage-metric strong{display:block;font-size:22px;line-height:1.2;margin:3px 0}.usage-metric progress{display:block;margin:8px 0 5px}.usage-metric small{display:block;color:var(--muted)}.usage-warning{margin-top:12px;padding:10px 12px;border-radius:10px;background:var(--warn-soft);color:#ffd27c}.usage-warning.critical{background:var(--bad-soft);color:#ffb6c0}
.follower-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-top:16px}.follower-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.follower-metric{padding:12px 9px;border:1px solid var(--line-soft);border-radius:10px;background:rgba(8,13,22,.25);text-align:center}.follower-metric strong{display:block;font-size:22px;line-height:1.2}.follower-metric small{display:block;color:var(--muted);font-size:11px;margin-top:4px}.delta-positive{color:var(--ok)}.delta-negative{color:var(--bad)}
@media(max-width:600px){.guide-step{padding:14px 14px 14px 52px}.guide-step:before{left:13px;top:13px}.copy-field{min-width:100%}.mini-nav a{flex:1 1 45%;text-align:center}.library-preview{height:190px}}
@media(max-width:600px){.follower-grid{grid-template-columns:1fr}.follower-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def password_ok(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class AdminServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: Config, store: Store, meta: MetaClient,
                 accounts: AccountManager | None = None):
        super().__init__(address, AdminHandler)
        self.config = config
        self.store = store
        self.meta = meta
        self.accounts = accounts or AccountManager(config, store)
        self.allowed_networks = tuple(ipaddress.ip_network(value, strict=False) for value in config.admin_allowed_networks)
        self.guide_dir = config.db_path.parent / "guides"
        self.trash_dir = config.db_path.parent / "trash"
        self.backup_dir = config.db_path.parent / "backups"
        self._backup_lock = threading.Lock()
        self._backup_stop = threading.Event()
        self.guide_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        for automation in store.list_automations(True):
            store.ensure_document(str(automation["pdf_path"]))
            if not store.list_versions(int(automation["id"])):
                fields = ("name", "media_id", "media_permalink", "trigger_keywords", "confirmation_words",
                          "public_reply_text", "initial_dm_text", "guide_message_text", "pdf_path",
                          "conversation_rules", "require_follow", "follow_required_message", "enabled",
                          "instagram_account_id")
                store.save_version(int(automation["id"]), "published", {key: automation[key] for key in fields})
        self.ensure_daily_backup()
        self._backup_thread = threading.Thread(target=self._backup_loop, daemon=True)
        self._backup_thread.start()
        self._profile_thread = threading.Thread(
            target=self._refresh_instagram_profiles, daemon=True, name="instagram-profile-refresh"
        )
        self._profile_thread.start()

    def create_backup_bundle(self, label: str) -> Path:
        with self._backup_lock:
            database = self.store.create_backup(self.backup_dir, label)
            target = database.with_suffix(".zip")
            manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "documents": []}
            try:
                with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(database, "database.sqlite3")
                    for document in self.store.list_documents():
                        path = Path(str(document["file_path"]))
                        if not path.is_file():
                            continue
                        folder = str(document["folder"] or "")
                        stored = str(document["stored_name"] or f"file-{document['id']}.bin")
                        archive_name = f"documents/{folder + '/' if folder else ''}{document['id']}-{stored}"
                        archive.write(path, archive_name)
                        manifest["documents"].append({
                            "id": document["id"], "title": document["title"],
                            "original_name": document["original_name"], "archive_path": archive_name,
                        })
                    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                target.chmod(0o600)
                return target
            finally:
                database.unlink(missing_ok=True)

    def ensure_daily_backup(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if not list(self.backup_dir.glob(f"fraxler-auto-{today}-*.zip")):
            self.create_backup_bundle("auto")
        for old in sorted(self.backup_dir.glob("fraxler-auto-*.zip"), reverse=True)[14:]:
            old.unlink(missing_ok=True)

    def _backup_loop(self) -> None:
        while not self._backup_stop.wait(60 * 60):
            try:
                self.ensure_daily_backup()
            except OSError:
                pass

    def _refresh_instagram_profiles(self) -> None:
        # Give networking and the tunnel a moment to settle after Ubuntu starts.
        if self._backup_stop.wait(5):
            return
        while not self._backup_stop.is_set():
            for account in self.store.list_instagram_accounts(False):
                if self._backup_stop.is_set():
                    return
                try:
                    self.accounts.refresh_limits(int(account["id"]))
                except Exception:
                    # A temporary API outage must not prevent the local panel from starting.
                    continue
            # Follower figures are informational; a 30-minute refresh avoids needless API load.
            if self._backup_stop.wait(30 * 60):
                return

    def server_close(self) -> None:
        self._backup_stop.set()
        super().server_close()


class AdminHandler(BaseHTTPRequestHandler):
    server: AdminServer

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8", cookie: str | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data: https:; media-src https:")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _download(self, path: Path, filename: str, inline: bool = False) -> None:
        if not path.is_file():
            self._send(404, "Файл не знайдено")
            return
        body = path.read_bytes()
        self.send_response(200)
        content_type = mimetypes.guess_type(filename)[0] if inline else None
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        disposition = "inline" if inline else "attachment"
        self.send_header("Content-Disposition", f'{disposition}; filename="{filename}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _layout(self, title: str, content: str, authenticated: bool = True) -> str:
        query = parse_qs(urlparse(self.path).query)
        toast_text = query.get("ok", [""])[0] or query.get("err", [""])[0]
        toast_class = " error" if query.get("err") else ""
        toast = f'<div id="toast" class="toast{toast_class}">{esc(toast_text)}</div>' if toast_text else ""
        theme_script = "document.documentElement.dataset.theme=localStorage.getItem('fia-theme')||'dark';function toggleTheme(){const n=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=n;localStorage.setItem('fia-theme',n)}"
        if authenticated:
            path = urlparse(self.path).path
            links = (
                ("/admin/", "Автоматизації", "◫"), ("/admin/history", "Історія", "◷"),
                ("/admin/accounts", "Instagram-акаунти", "◉"), ("/admin/api-usage", "API-ліміти", "◴"),
                ("/admin/analytics", "Аналітика", "⌁"), ("/admin/users", "Користувачі", "◎"),
                ("/admin/errors", "Помилки", "!"), ("/admin/library", "Бібліотека", "▤"),
                ("/admin/backups", "Резервні копії", "↻"), ("/admin/settings", "Налаштування", "⚙"),
                ("/admin/help", "Довідка", "?"),
            )
            nav_items = []
            for href, label, icon in links:
                if href == "/admin/":
                    active = path == href or path.startswith("/admin/automation/")
                else:
                    active = path == href or path.startswith(href + "/")
                nav_items.append(f'<a class="nav-link{" active" if active else ""}" href="{href}"><span class="nav-icon">{icon}</span><span>{label}</span></a>')
            sidebar = f'''<aside class="sidebar"><a class="brand" href="/admin/"><span class="brand-mark">F</span><span class="brand-copy">Fraxler<small>Insta Automation</small></span></a><nav class="nav">{"".join(nav_items)}</nav><form class="mobile-logout" method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button class="ghost" title="Вийти">⎋</button></form><div class="sidebar-actions"><a class="btn create-link" href="/admin/automation/new">+ Нова автоматизація</a><button class="ghost theme-button" type="button" onclick="toggleTheme()" title="Змінити тему"><span class="theme-label">Світла / темна</span><span class="theme-short">◐</span></button><form method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button class="ghost" style="width:100%">Вийти</button></form></div></aside>'''
            body = f'<div class="app-shell">{sidebar}<main class="workspace"><div class="workspace-inner">{content}</div></main></div>'
        else:
            body = f'<main class="auth-shell"><div><div class="brand"><span class="brand-mark">F</span><span class="brand-copy">Fraxler<small>Insta Automation</small></span></div>{content}</div></main>'
        return f"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b0f17"><title>{esc(title)} — Fraxler Insta Automation</title><script>{theme_script}</script><style>{CSS}</style></head><body>{body}{toast}<script>const t=document.getElementById('toast');if(t)setTimeout(()=>t.remove(),4200)</script></body></html>"""

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
            return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else ""
        except Exception:
            return ""

    def _csrf(self) -> str:
        token = self._cookie_token()
        return self.server.store.session_csrf(token, int(time.time())) if token else "" or ""

    def _authenticated(self) -> bool:
        return bool(self._csrf())

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        self._redirect("/admin/login")
        return False

    def _client_allowed(self) -> bool:
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(address in network for network in self.server.allowed_networks)

    def _form(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_UPLOAD:
            raise ValueError("Файл або запит завеликий")
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=default).parsebytes(
                b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
            values: dict[str, str] = {}
            files: dict[str, tuple[str, bytes]] = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if not name:
                    continue
                if filename:
                    files[name] = (filename, payload)
                else:
                    values[name] = payload.decode(part.get_content_charset() or "utf-8", "replace")
            return values, files
        parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        return {key: value[-1] for key, value in parsed.items()}, {}

    def _valid_csrf(self, values: dict[str, str]) -> bool:
        expected = self._csrf()
        return bool(expected and secrets.compare_digest(values.get("csrf", ""), expected))

    def _folders(self) -> list[str]:
        folders = {""}
        for path in self.server.guide_dir.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                folders.add(path.relative_to(self.server.guide_dir).as_posix())
        return sorted(folders, key=lambda value: (value != "", value))

    def _folder_options(self, selected: str = "") -> str:
        return "".join(
            f'<option value="{esc(folder)}"{" selected" if folder == selected else ""}>{esc(folder or "Головна папка")}</option>'
            for folder in self._folders()
        )

    def do_GET(self) -> None:
        if not self._client_allowed():
            self._send(403, "Доступ до панелі дозволений лише з локальної мережі")
            return
        path = urlparse(self.path).path
        if path == "/":
            self._redirect("/admin/")
            return
        if path == "/admin/setup":
            self._setup_page()
            return
        if path == "/admin/login":
            self._login_page()
            return
        if not self.server.store.get_setting("admin_password"):
            self._redirect("/admin/setup")
            return
        if not self._require_auth():
            return
        if path == "/admin/":
            self._dashboard()
            return
        if path == "/admin/history":
            self._history()
            return
        if path == "/admin/accounts":
            self._accounts()
            return
        if path == "/admin/api-usage":
            self._api_usage()
            return
        if path == "/admin/help":
            self._help()
            return
        if path == "/admin/analytics":
            self._analytics()
            return
        if path == "/admin/library":
            self._library()
            return
        if path.startswith("/admin/library/preview/"):
            try:
                document = self.server.store.get_document(int(path.rsplit("/", 1)[-1]))
            except ValueError:
                document = None
            if document is None:
                self._send(404, "Зображення не знайдено")
                return
            file_path = Path(str(document["file_path"]))
            safe_name = Path(str(document["stored_name"] or file_path.name)).name
            if file_path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
                self._send(415, "Попередній перегляд доступний лише для зображень")
                return
            self._download(file_path, safe_name, inline=True)
            return
        if path.startswith("/admin/library/download/"):
            try:
                document = self.server.store.get_document(int(path.rsplit("/", 1)[-1]))
            except ValueError:
                document = None
            if document is None:
                self._send(404, "Файл не знайдено")
                return
            safe_name = Path(str(document["stored_name"] or document["file_path"])).name
            if (not safe_name.isascii() or Path(safe_name).suffix.casefold() not in ALLOWED_EXTENSIONS
                    or not all(ch.isalnum() or ch in "._-" for ch in safe_name)):
                safe_name = "file.bin"
            self._download(Path(str(document["file_path"])), safe_name)
            return
        if path == "/admin/backups":
            self._backups()
            return
        if path == "/admin/errors":
            self._errors()
            return
        if path == "/admin/users":
            self._users()
            return
        if path.startswith("/admin/users/"):
            self._user_detail(unquote(path.removeprefix("/admin/users/")))
            return
        if path == "/admin/settings":
            self._settings()
            return
        if path.startswith("/admin/backups/download/"):
            name = path.rsplit("/", 1)[-1]
            candidate = self.server.backup_dir / name
            if not name.endswith((".sqlite3", ".zip")) or candidate.parent != self.server.backup_dir:
                self._send(404, "Файл не знайдено")
                return
            self._download(candidate, name)
            return
        if path == "/admin/automation/new":
            self._automation_form(None)
            return
        if path.startswith("/admin/automation/") and path.endswith("/versions"):
            try:
                automation_id = int(path.split("/")[-2])
            except ValueError:
                self._send(404, "Не знайдено")
                return
            self._versions(automation_id)
            return
        if path.startswith("/admin/automation/"):
            try:
                automation_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._send(404, "Не знайдено")
                return
            row = self.server.store.get_automation(automation_id)
            if row is None:
                self._send(404, self._layout("Не знайдено", '<div class="panel">Автоматизацію не знайдено.</div>'))
                return
            submitted = None
            version_value = parse_qs(urlparse(self.path).query).get("version", [""])[0]
            if version_value:
                try:
                    version = self.server.store.get_version(int(version_value))
                    if version and version["automation_id"] == automation_id:
                        submitted = json.loads(str(version["snapshot"]))
                        submitted["id"] = automation_id
                except (ValueError, json.JSONDecodeError):
                    submitted = None
            self._automation_form(row, submitted=submitted)
            return
        self._send(404, "Не знайдено")

    def do_POST(self) -> None:
        if not self._client_allowed():
            self._send(403, "Доступ до панелі дозволений лише з локальної мережі")
            return
        path = urlparse(self.path).path
        try:
            values, files = self._form()
        except ValueError as exc:
            self._send(400, self._layout("Помилка", f'<div class="notice error">{esc(exc)}</div>', False))
            return
        if path == "/admin/setup":
            self._setup(values)
            return
        if path == "/admin/login":
            self._login(values)
            return
        if not self._require_auth() or not self._valid_csrf(values):
            self._send(403, "Недійсний або прострочений запит")
            return
        if path == "/admin/logout":
            token = self._cookie_token()
            if token:
                self.server.store.delete_session(token)
            self._redirect("/admin/login", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
            return
        if path == "/admin/automation/save":
            self._save_automation(values, files)
            return
        if path == "/admin/accounts/settings":
            self._account_settings(values)
            return
        if path == "/admin/accounts/connect":
            self._account_connect()
            return
        if path == "/admin/accounts/check":
            self._account_check(values)
            return
        if path == "/admin/accounts/default":
            self._account_default(values)
            return
        if path == "/admin/accounts/disconnect":
            self._account_disconnect(values)
            return
        if path == "/admin/api-usage/refresh":
            self._api_usage_refresh()
            return
        if path == "/admin/analytics/refresh":
            self._analytics_refresh()
            return
        if path == "/admin/automation/action":
            self._automation_action(values)
            return
        if path == "/admin/automation/check":
            self._check_automation(values)
            return
        if path == "/admin/library/upload":
            self._library_upload(values, files)
            return
        if path == "/admin/library/delete":
            self._library_delete(values)
            return
        if path == "/admin/library/folder":
            self._folder_create(values)
            return
        if path == "/admin/library/move":
            self._library_move(values)
            return
        if path == "/admin/backups/create":
            backup = self.server.create_backup_bundle("manual")
            self._redirect("/admin/backups?" + urlencode({"ok": f"Створено {backup.name}"}))
            return
        if path == "/admin/backups/delete":
            self._backup_delete(values)
            return
        if path == "/admin/errors/retry":
            self._retry_now(values)
            return
        if path == "/admin/users/save":
            self._user_save(values)
            return
        if path == "/admin/users/send":
            self._user_send(values)
            return
        if path == "/admin/users/delete":
            self._user_delete(values)
            return
        if path == "/admin/users/check-follow":
            self._user_check_follow(values)
            return
        if path == "/admin/settings/save":
            self._settings_save(values)
            return
        if path == "/admin/settings/test-telegram":
            self._telegram_test()
            return
        if path == "/admin/versions/restore":
            self._version_restore(values)
            return
        if path == "/admin/service/restart":
            self._restart_service(values.get("service", ""))
            return
        self._send(404, "Не знайдено")

    def _setup_page(self, error: str = "") -> None:
        if self.server.store.get_setting("admin_password"):
            self._redirect("/admin/login")
            return
        notice = f'<div class="notice error">{esc(error)}</div>' if error else ""
        content = f"""<section class="panel hero"><h1>Створення пароля</h1><p class="muted">Панель доступна лише на цьому ноутбуці. Створіть пароль довжиною щонайменше 10 символів.</p>{notice}
        <form method="post" action="/admin/setup"><label>Пароль</label><input type="password" name="password" minlength="10" required autofocus><label>Повторіть пароль</label><input type="password" name="confirm" minlength="10" required><div class="actions"><button>Створити й увійти</button></div></form></section>"""
        self._send(200, self._layout("Створення пароля", content, False))

    def _setup(self, values: dict[str, str]) -> None:
        if self.server.store.get_setting("admin_password"):
            self._redirect("/admin/login")
            return
        password = values.get("password", "")
        if len(password) < 10 or password != values.get("confirm", ""):
            self._setup_page("Паролі не збігаються або містять менше 10 символів.")
            return
        self.server.store.set_setting("admin_password", password_hash(password))
        self._new_session()

    def _login_page(self, error: str = "") -> None:
        if not self.server.store.get_setting("admin_password"):
            self._redirect("/admin/setup")
            return
        notice = f'<div class="notice error">{esc(error)}</div>' if error else ""
        content = f"""<section class="panel hero"><h1>Вхід</h1><p class="muted">Fraxler Insta Automation</p>{notice}<form method="post" action="/admin/login"><label>Пароль</label><input type="password" name="password" required autofocus><div class="actions"><button>Увійти</button></div></form></section>"""
        self._send(200, self._layout("Вхід", content, False))

    def _login(self, values: dict[str, str]) -> None:
        stored = self.server.store.get_setting("admin_password") or ""
        if not password_ok(values.get("password", ""), stored):
            time.sleep(0.4)
            self._login_page("Неправильний пароль.")
            return
        self._new_session()

    def _new_session(self) -> None:
        token, _ = self.server.store.create_session(int(time.time()) + SESSION_SECONDS)
        cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Strict"
        self._redirect("/admin/", cookie)

    @staticmethod
    def _service_state(name: str) -> str:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", name], capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip() or "невідомо"
        except (OSError, subprocess.TimeoutExpired):
            return "невідомо"

    def _dashboard(self) -> None:
        automations = self.server.store.list_automations(True)
        accounts = {
            int(account["id"]): account
            for account in self.server.store.list_instagram_accounts(True)
        }
        cards = []
        for row in automations:
            if row["archived"]:
                status = '<span class="badge archived">Архів</span>'
            elif row["enabled"]:
                status = '<span class="badge on">Увімкнено</span>'
            else:
                status = '<span class="badge off">Вимкнено</span>'
            link = f'<a href="{esc(row["media_permalink"])}" target="_blank">Відкрити публікацію ↗</a>' if row["media_permalink"] else f'<span class="muted">Media ID: {esc(row["media_id"])}</span>'
            actions = f'<a class="btn secondary" href="/admin/automation/{row["id"]}">Редагувати</a>'
            actions += f'<a class="btn ghost" href="/admin/automation/{row["id"]}/versions">Версії</a>'
            actions += self._check_form(row["id"])
            if row["archived"]:
                actions += self._action_form(row["id"], "restore", "Відновити", "ghost")
                actions += self._action_form(row["id"], "delete", "Видалити", "danger", "return confirm('Остаточно видалити автоматизацію? Файл залишиться в бібліотеці.');")
            else:
                actions += self._action_form(row["id"], "duplicate", "Дублювати", "ghost")
                label = "Вимкнути" if row["enabled"] else "Увімкнути"
                actions += self._action_form(row["id"], "toggle", label, "ghost")
                actions += self._action_form(row["id"], "archive", "В архів", "ghost")
            account_id = int(row["instagram_account_id"]) if row["instagram_account_id"] else 0
            identity = self._instagram_identity_html(accounts.get(account_id))
            cards.append(f"""<article class="card"><div class="row between"><h3>{esc(row['name'])}</h3>{status}</div>{identity}<div>{link}</div><p><strong>Ключові слова:</strong> {esc(row['trigger_keywords'])}</p><p class="muted">Файл: {esc(Path(row['pdf_path']).name)}</p><div class="actions">{actions}</div></article>""")
        cards_html = "".join(cards) if cards else '<div class="empty">Ще немає автоматизацій.</div>'
        bot_state = self._service_state("instagram-guide-bot.service")
        tunnel_state = self._service_state("instagram-guide-tunnel.service")
        health_rows = "".join(
            f'<div class="service"><span>{esc(item["key"])}<small class="muted"> · {esc(item["detail"])}</small></span><span class="badge {"on" if item["status"] == "ok" else ("archived" if item["status"] == "info" else "off")}">{esc(item["status"])}</span></div>'
            for item in self.server.store.list_health()
        )
        errors = len(self.server.store.list_retries(False))
        service_html = f"""<section class="panel" style="margin-bottom:16px"><div class="row between"><div><h2 style="margin:0">Стан системи</h2><span class="muted">Зміни сценаріїв застосовуються без перезапуску · <a href="/admin/errors">помилок у черзі: {errors}</a></span></div><div class="actions">{self._restart_form('instagram-guide-tunnel.service','Перезапустити тунель')}{self._restart_form('instagram-guide-bot.service','Перезапустити бот')}</div></div><div class="service"><span>Instagram-бот</span><span class="badge {'on' if bot_state == 'active' else 'off'}">{esc(bot_state)}</span></div><div class="service"><span>Cloudflare Tunnel</span><span class="badge {'on' if tunnel_state == 'active' else 'off'}">{esc(tunnel_state)}</span></div>{health_rows}</section>"""
        content = f'''{service_html}<section class="panel"><div class="row between"><div><h2 style="margin:0">Автоматизації</h2><span class="muted">Окремі слова, відповіді та файли для кожної публікації</span></div><a class="btn" href="/admin/automation/new">+ Створити</a></div><div class="grid" style="margin-top:18px">{cards_html}</div></section>'''
        self._send(200, self._layout("Автоматизації", content))

    @staticmethod
    def _instagram_identity_html(account: object | None) -> str:
        if account is None:
            return '<div class="instagram-identity"><span class="instagram-avatar fallback">?</span><div><strong>Акаунт не призначено</strong><small>Instagram</small></div></div>'
        username = str(account["username"] or account["instagram_user_id"] or "Instagram")
        picture = str(account["profile_picture_url"] or "").strip()
        parsed = urlparse(picture)
        if parsed.scheme == "https" and parsed.netloc:
            avatar = f'<img class="instagram-avatar" src="{esc(picture)}" alt="Фото профілю @{esc(username)}" loading="lazy" referrerpolicy="no-referrer">'
        else:
            initial = next((character for character in username if character.isalnum()), "I")
            avatar = f'<span class="instagram-avatar fallback" aria-hidden="true">{esc(initial)}</span>'
        return f'<div class="instagram-identity">{avatar}<div><strong>@{esc(username)}</strong><small>Instagram-акаунт</small></div></div>'

    @staticmethod
    def _usage_value(payload: object, *keys: str, recursive: bool = False) -> int | None:
        if isinstance(payload, list) and recursive:
            values = [
                result for child in payload
                for result in [AdminHandler._usage_value(child, *keys, recursive=True)]
                if result is not None
            ]
            return max(values) if values else None
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return max(0, min(100, round(value)))
        if recursive:
            values = [
                result for child in payload.values()
                for result in [AdminHandler._usage_value(child, *keys, recursive=True)]
                if result is not None
            ]
            return max(values) if values else None
        return None

    @staticmethod
    def _usage_metric(label: str, used: int | None) -> str:
        if used is None:
            return f'<div class="usage-metric"><span class="muted">{esc(label)}</span><strong>—</strong><small>Meta не повернула дані</small></div>'
        remaining = max(0, 100 - used)
        return f'<div class="usage-metric"><span class="muted">{esc(label)}</span><strong>{used}%</strong><progress max="100" value="{used}" aria-label="{esc(label)}: використано {used}%"></progress><small>Залишок приблизно {remaining}%</small></div>'

    def _api_usage(self) -> None:
        cards = []
        for account in self.server.store.list_instagram_accounts(False):
            usage = self.server.store.get_api_usage(int(account["id"]))
            try:
                app = json.loads(str(usage["app_usage_json"])) if usage else {}
            except json.JSONDecodeError:
                app = {}
            try:
                business = json.loads(str(usage["business_usage_json"])) if usage else {}
            except json.JSONDecodeError:
                business = {}
            calls = self._usage_value(app, "call_count", "call_volume")
            cpu = self._usage_value(app, "total_cputime", "cpu_time")
            total_time = self._usage_value(app, "total_time")
            business_calls = self._usage_value(
                business, "call_count", "call_volume", recursive=True
            )
            percentages = [value for value in (calls, cpu, total_time, business_calls) if value is not None]
            peak = max(percentages) if percentages else None
            warning = ""
            if peak is not None and peak >= 95:
                warning = '<div class="usage-warning critical"><strong>Критичний рівень.</strong> Meta може тимчасово обмежити нові API-запити.</div>'
            elif peak is not None and peak >= 80:
                warning = '<div class="usage-warning"><strong>Наближення до ліміту.</strong> Варто зменшити частоту необов’язкових запитів.</div>'
            publishing = '<div class="usage-metric"><span class="muted">Публікації за 24 години</span><strong>—</strong><small>Ліміт не отримано</small></div>'
            publishing_note = ""
            if usage and usage["publishing_usage"] is not None and usage["publishing_total"]:
                used = int(usage["publishing_usage"])
                total = int(usage["publishing_total"])
                percent = max(0, min(100, round(used * 100 / total)))
                publishing = f'<div class="usage-metric"><span class="muted">Публікації за 24 години</span><strong>{used} / {total}</strong><progress max="100" value="{percent}" aria-label="Публікації: використано {used} із {total}"></progress><small>Залишилося {max(0, total - used)} публікацій</small></div>'
            elif usage and usage["publishing_error"]:
                publishing_note = '<p class="muted">Ліміт публікацій недоступний. Зазвичай для нього потрібен дозвіл <code>instagram_business_content_publish</code>.</p>'
            observed = str(usage["observed_at"] or "ще не отримано") if usage else "ще не отримано"
            checked = str(usage["publishing_checked_at"] or "ще не перевірявся") if usage else "ще не перевірявся"
            identity = self._instagram_identity_html(account)
            metrics = "".join((
                self._usage_metric("API-запити застосунку", calls),
                self._usage_metric("Процесорний час", cpu),
                self._usage_metric("Загальний час", total_time),
                self._usage_metric("Business use case", business_calls),
                publishing,
            ))
            cards.append(f'<article class="card">{identity}<div class="usage-metrics">{metrics}</div>{warning}{publishing_note}<p class="muted" style="margin-bottom:0">API: {esc(observed)} · Публікації: {esc(checked)}</p></article>')
        empty = '<div class="empty">Спочатку підключіть Instagram-акаунт.</div>'
        intro = '<div class="notice">Загальні відсотки є спільними для Meta-застосунку; у картці показано останню відповідь, отриману через конкретний акаунт. Ліміт публікацій рахується окремо для акаунта. Залишок приблизний, а не гарантована кількість майбутніх операцій.</div>'
        form = f'<form method="post" action="/admin/api-usage/refresh"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button>Оновити ліміти</button></form>'
        content = f'<section class="panel"><div class="row between"><div><h1 style="margin:0">API-ліміти</h1><span class="muted">Використання ресурсів Meta для кожного підключеного акаунта</span></div>{form}</div><div style="margin-top:18px">{intro}</div><div class="grid" style="margin-top:16px">{"".join(cards) if cards else empty}</div></section>'
        self._send(200, self._layout("API-ліміти", content))

    def _api_usage_refresh(self) -> None:
        successes = 0
        for account in self.server.store.list_instagram_accounts(False):
            try:
                self.server.accounts.refresh_limits(int(account["id"]))
                successes += 1
            except Exception:
                continue
        total = len(self.server.store.list_instagram_accounts(False))
        if successes:
            message = f"Ліміти оновлено для {successes} із {total} акаунтів."
            self._redirect("/admin/api-usage?" + urlencode({"ok": message}))
        else:
            self._redirect("/admin/api-usage?" + urlencode({"err": "Meta не повернула дані. Перевірте токени та доступ до API."}))

    def _accounts(self) -> None:
        rows = []
        now = int(time.time())
        for account in self.server.store.list_instagram_accounts(True):
            status_class = "on" if account["status"] == "active" else ("archived" if account["status"] == "disconnected" else "off")
            status_label = {"active": "Підключено", "error": "Потрібна увага", "disconnected": "Відключено"}.get(str(account["status"]), str(account["status"]))
            expiry = "Не вказано"
            if account["token_expires_at"]:
                expiry = datetime.fromtimestamp(int(account["token_expires_at"]), timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
                if int(account["token_expires_at"]) <= now:
                    expiry += " · прострочено"
            buttons = ""
            if account["status"] != "disconnected":
                buttons += f'''<form class="inline" method="post" action="/admin/accounts/check"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{account['id']}"><button class="ghost">Перевірити API</button></form>'''
                if not account["is_default"]:
                    buttons += f'''<form class="inline" method="post" action="/admin/accounts/default"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{account['id']}"><button class="ghost">Зробити основним</button></form>'''
                buttons += f'''<form class="inline" method="post" action="/admin/accounts/disconnect" onsubmit="return confirm('Відключити акаунт і видалити його токен?');"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{account['id']}"><button class="danger">Відключити</button></form>'''
            error = f'<div class="notice error" style="margin-top:12px">{esc(account["last_error"])}</div>' if account["last_error"] else ""
            default = '<span class="badge archived">Основний</span>' if account["is_default"] else ""
            rows.append(f'''<article class="card"><div class="row between"><div><h3>@{esc(account['username'])}</h3><span class="muted">Instagram ID: {esc(account['instagram_user_id'])}</span></div><div>{default} <span class="badge {status_class}">{esc(status_label)}</span></div></div><p class="muted">Токен: зашифровано · Діє до: {esc(expiry)}</p><p class="muted">Остання перевірка: {esc(account['last_checked_at'] or 'ще не виконувалась')}</p>{error}<div class="actions">{buttons}</div></article>''')
        app_id = self.server.accounts.app_id
        callback = self.server.accounts.callback_url
        secret_ok = bool(self.server.config.app_secret)
        setup = f'''<section class="panel"><h1>Instagram-акаунти</h1><p class="muted">Підключення відбувається через офіційне вікно Instagram. Пароль Instagram і відкритий токен у панелі не зберігаються.</p><form method="post" action="/admin/accounts/settings"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><label>Instagram App ID (Client ID)</label><div class="row"><input style="max-width:420px" name="app_id" inputmode="numeric" value="{esc(app_id)}" placeholder="Цифровий App ID із Meta" required><button>Зберегти</button></div></form><label>OAuth Redirect URI для Meta</label><div class="row"><input id="callback-url" readonly value="{esc(callback)}"><button class="ghost" type="button" onclick="navigator.clipboard.writeText(document.getElementById('callback-url').value)">Копіювати</button></div><p class="muted">Додайте цю точну адресу в Meta → Instagram → API setup with Instagram login → Business login settings → Valid OAuth Redirect URIs.</p><div class="notice {'okbox' if secret_ok else 'error'}">Instagram App Secret: {'налаштовано в захищеному .env' if secret_ok else 'не налаштовано — підключення неможливе'}</div><form method="post" action="/admin/accounts/connect"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button {'disabled' if not app_id or not secret_ok else ''}>+ Підключити Instagram-акаунт</button></form></section>'''
        content = setup + f'''<section class="panel"><div class="row between"><h2 style="margin:0">Підключені акаунти</h2><span class="muted">{len(rows)} у списку</span></div><div class="grid" style="margin-top:18px">{''.join(rows) if rows else '<div class="empty">Акаунтів ще немає.</div>'}</div></section>'''
        self._send(200, self._layout("Instagram-акаунти", content))

    def _account_settings(self, values: dict[str, str]) -> None:
        app_id = values.get("app_id", "").strip()
        if not app_id.isdigit() or len(app_id) > 32:
            self._redirect("/admin/accounts?" + urlencode({"err": "Meta App ID має складатися лише з цифр."}))
            return
        self.server.store.set_setting("instagram_app_id", app_id)
        self._redirect("/admin/accounts?" + urlencode({"ok": "Meta App ID збережено."}))

    def _account_connect(self) -> None:
        try:
            self._redirect(self.server.accounts.authorization_url())
        except AccountError as exc:
            self._redirect("/admin/accounts?" + urlencode({"err": str(exc)}))

    def _account_check(self, values: dict[str, str]) -> None:
        try:
            account_id = int(values.get("id", ""))
            profile = self.server.accounts.check(account_id)
            message = f"API і вебхуки працюють для @{profile.get('username', profile.get('id', 'акаунта'))}."
            self._redirect("/admin/accounts?" + urlencode({"ok": message}))
        except (ValueError, AccountError, RuntimeError) as exc:
            self._redirect("/admin/accounts?" + urlencode({"err": f"Перевірка не пройшла: {str(exc)[:300]}"}))

    def _account_default(self, values: dict[str, str]) -> None:
        try:
            ok = self.server.store.set_default_instagram_account(int(values.get("id", "")))
        except ValueError:
            ok = False
        self._redirect("/admin/accounts?" + urlencode({"ok" if ok else "err": "Основний акаунт змінено." if ok else "Акаунт не знайдено."}))

    def _account_disconnect(self, values: dict[str, str]) -> None:
        try:
            ok, message = self.server.store.disconnect_instagram_account(int(values.get("id", "")))
        except ValueError:
            ok, message = False, "Некоректний ID акаунта."
        self._redirect("/admin/accounts?" + urlencode({"ok" if ok else "err": message}))

    def _help(self) -> None:
        callback = self.server.accounts.callback_url
        accounts = self.server.store.list_instagram_accounts(False)
        app_id_ready = bool(self.server.accounts.app_id)
        secret_ready = bool(self.server.config.app_secret)
        status_items = (
            (app_id_ready, "Instagram App ID збережено"),
            (secret_ready, "Instagram App Secret налаштовано"),
            (self.server.config.public_base_url.startswith("https://"), "Публічна HTTPS-адреса працює через Cloudflare"),
            (bool(accounts), f"Підключено Instagram-акаунтів: {len(accounts)}"),
        )
        status_html = "".join(
            f'<div class="check-item"><span>{"✅" if ok else "○"}</span><span>{esc(label)}</span></div>'
            for ok, label in status_items
        )
        steps = (
            ("Підготуйте Instagram-акаунт", "Він має бути професійним: Business або Creator. У налаштуваннях Instagram дозвольте доступ до повідомлень для підключених інструментів."),
            ("Надайте тестову роль, якщо Advanced Access ще немає", "Meta for Developers → ваш застосунок → App roles → Instagram Testers → Add People. Додайте точний Instagram-нік нового акаунта."),
            ("Прийміть запрошення Tester", "Увійдіть саме в новий Instagram-акаунт → Налаштування → Додатки й сайти → Запрошення тестувальника. Статус у Meta має змінитися з Pending на Accepted."),
            ("Відкрийте розділ Instagram-акаунти", "У локальній панелі перейдіть до «Instagram-акаунти». Переконайтеся, що введено Instagram App ID того самого застосунку Meta."),
            ("Запустіть підключення", "Натисніть «Підключити Instagram-акаунт». Відкриється офіційна сторінка Instagram — локальна панель не отримує ваш пароль."),
            ("Виберіть правильний профіль", "Якщо браузер уже авторизований в іншому профілі, спочатку перемкніться на потрібний. Перевірте назву акаунта у тексті запиту доступу."),
            ("Увімкніть усі потрібні дозволи", "Дозвольте профіль і медіафайли, коментарі, повідомлення та головний перемикач доступу до повідомлень. Натисніть «Дозволити»."),
            ("Дочекайтеся підтвердження", "Після авторизації з’явиться сторінка «Акаунт підключено». Закрийте її та поверніться до локальної панелі."),
            ("Перевірте API", "У картці нового акаунта натисніть «Перевірити API». Панель перевірить профіль, токен і підписку на події comments та messages."),
            ("Призначте акаунт автоматизації", "Створіть нову автоматизацію або відкрийте наявну, виберіть Instagram-акаунт, потім виберіть його публікацію, слова, відповіді та файл."),
        )
        steps_html = "".join(
            f'<div class="guide-step"><strong>{esc(title)}</strong><p>{esc(text)}</p></div>'
            for title, text in steps
        )
        content = f'''<section class="panel"><div class="row between"><div><h1 style="margin:0">Як додати Instagram-акаунт</h1><span class="muted">Покрокова інструкція для тестового та робочого режимів</span></div><a class="btn" href="/admin/accounts">Відкрити акаунти</a></div><nav class="mini-nav"><a href="#before">Перед початком</a><a href="#steps">10 кроків</a><a href="#access">Рівні доступу</a><a href="#errors">Якщо є помилка</a></nav></section>
        <section class="panel help-anchor" id="before"><h2>Перед початком</h2><div class="two"><div><h3>Стан цієї панелі</h3><div class="checklist">{status_html}</div></div><div><h3>OAuth Redirect URI</h3><p class="muted">Ця точна адреса має бути додана в Meta до Valid OAuth Redirect URIs.</p><div class="row"><input class="copy-field" id="help-callback" readonly value="{esc(callback)}"><button class="ghost" type="button" onclick="navigator.clipboard.writeText(document.getElementById('help-callback').value)">Копіювати</button></div><p><a href="https://developers.facebook.com/apps/" target="_blank" rel="noopener">Відкрити Meta for Developers ↗</a></p></div></div></section>
        <section class="panel help-anchor" id="steps"><h2>Додавання нового акаунта</h2><div class="guide-steps">{steps_html}</div></section>
        <section class="panel help-anchor" id="access"><h2>Tester чи Advanced Access?</h2><div class="grid"><article class="card"><h3>Для власних тестових акаунтів</h3><p>Додайте кожен акаунт як <strong>Instagram Tester</strong> і прийміть запрошення. Запис у розділі Instagram «Активні додатки й сайти» означає лише наданий OAuth-доступ і не замінює роль Tester.</p></article><article class="card"><h3>Для будь-яких клієнтських акаунтів</h3><p>Застосунок має бути Live і мати <strong>Advanced Access</strong> після App Review для <code>instagram_business_basic</code>, <code>instagram_business_manage_comments</code> та <code>instagram_business_manage_messages</code>.</p></article></div></section>
        <section class="panel help-anchor" id="errors"><h2>Якщо підключення не завершується</h2><div class="grid"><article class="card"><h3>Unsupported request: get/post</h3><p>Перевірте, що Tester має статус Accepted, доданий до того самого застосунку, чий Instagram App ID записаний у панелі. Якщо все правильно — видаліть застосунок з «Активні додатки й сайти», зачекайте кілька хвилин і авторизуйтеся заново.</p></article><article class="card"><h3>Публікації не завантажуються</h3><p>Натисніть «Перевірити API». Переконайтеся, що акаунт професійний і дозвіл на профіль та медіафайли не вимкнений.</p></article><article class="card"><h3>Коментар не запускає сценарій</h3><p>Перевірте, що автоматизація увімкнена, прив’язана саме до цього акаунта та публікації, а в коментарі є одне з ключових слів.</p></article><article class="card"><h3>Безпека</h3><p>Не вводьте пароль Instagram або відкритий access token у сторонні форми. У нашій панелі авторизація проходить через Instagram, а отриманий токен зберігається зашифрованим.</p></article></div><p class="muted" style="margin-top:18px"><a href="https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api" target="_blank" rel="noopener">Офіційна документація Instagram API ↗</a></p></section>'''
        self._send(200, self._layout("Довідка", content))

    def _errors(self) -> None:
        rows = []
        labels = {"public_reply": "Відповідь на коментар", "private_reply": "Перше Direct", "final_message": "Надсилання файлу"}
        for retry in self.server.store.list_retries(False):
            action = f'''<form method="post" action="/admin/errors/retry"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{retry['id']}"><button class="ghost">Повторити зараз</button></form>'''
            rows.append(f"""<tr><td><span class="badge {'off' if retry['state'] == 'failed' else 'archived'}">{esc(retry['state'])}</span></td><td>{esc(labels.get(retry['kind'], retry['kind']))}</td><td>{esc(retry['automation_name'] or '—')}</td><td>{retry['attempts']}/8</td><td class="wrap">{esc(retry['last_error'] or 'Очікує повтору')}</td><td>{action}</td></tr>""")
        empty = '<tr><td colspan="6" class="empty">Невирішених помилок немає.</td></tr>'
        content = f"""<section class="panel"><h1>Центр помилок</h1><p class="muted">Тимчасові збої повторюються автоматично: від 30 секунд до однієї години, максимум 8 спроб.</p><div class="table-wrap"><table><thead><tr><th>Стан</th><th>Операція</th><th>Автоматизація</th><th>Спроби</th><th>Причина</th><th>Дія</th></tr></thead><tbody>{''.join(rows) if rows else empty}</tbody></table></div></section>"""
        self._send(200, self._layout("Центр помилок", content))

    def _retry_now(self, values: dict[str, str]) -> None:
        try:
            self.server.store.retry_now(int(values.get("id", "")))
        except ValueError:
            self._send(400, "Некоректний ID")
            return
        self._redirect("/admin/errors?" + urlencode({"ok": "Повторну спробу поставлено в чергу."}))

    def _users(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        search = query.get("q", [""])[0]
        try:
            account_id = int(query.get("account", [""])[0]) or None
        except ValueError:
            account_id = None
        accounts = {int(row["id"]): row for row in self.server.store.list_instagram_accounts(False)}
        account_options = ['<option value="">Усі Instagram-акаунти</option>']
        for account in accounts.values():
            selected = " selected" if account_id == int(account["id"]) else ""
            account_options.append(
                f'<option value="{account["id"]}"{selected}>@{esc(account["username"] or account["instagram_user_id"])}</option>'
            )
        cards = []
        for user in self.server.store.list_users(search, account_id):
            name = f"@{user['username']}" if user["username"] else f"ID {user['recipient_id']}"
            mode = '<span class="badge archived">Ручний режим</span>' if user["manual_mode"] else '<span class="badge on">Автоматизація</span>'
            follow = self._follow_badge(user["follows_business"])
            user_account_id = int(user["instagram_account_id"]) if user["instagram_account_id"] else None
            identity = self._instagram_identity_html(accounts.get(user_account_id or 0))
            detail_query = urlencode({"account": user_account_id}) if user_account_id else ""
            cards.append(f"""<article class="card"><div class="row between"><h3>{esc(name)}</h3><div>{mode} {follow}</div></div>{identity}<p class="muted">Повідомлень: {user['message_count']} · Останнє: {esc(user['last_message_at'] or user['last_seen_at'])}</p><p>{esc(user['tags'] or 'Без міток')}</p><a class="btn secondary" href="/admin/users/{quote(str(user['recipient_id']), safe='')}?{detail_query}">Відкрити діалог</a></article>""")
        content = f"""<section class="panel"><div class="row between"><div><h1 style="margin:0">Користувачі</h1><span class="muted">Direct, нотатки та передавання діалогу людині окремо для кожного Instagram-акаунта</span></div><form method="get" class="row"><select name="account" style="width:auto;min-width:210px">{''.join(account_options)}</select><input style="width:240px" name="q" value="{esc(search)}" placeholder="Нік, ID або мітка"><button>Знайти</button></form></div><div class="grid" style="margin-top:18px">{''.join(cards) if cards else '<div class="empty">Для вибраного акаунта користувачів ще немає.</div>'}</div></section>"""
        self._send(200, self._layout("Користувачі", content))

    def _user_detail(self, recipient_id: str, error: str = "", account_id: int | None = None) -> None:
        if account_id is None:
            try:
                account_id = int(parse_qs(urlparse(self.path).query).get("account", [""])[0]) or None
            except ValueError:
                account_id = None
        user = self.server.store.get_user(recipient_id, account_id)
        if user is None:
            self._send(404, self._layout("Не знайдено", '<div class="notice error">Користувача не знайдено.</div>'))
            return
        account_id = int(user["instagram_account_id"]) if user["instagram_account_id"] else account_id
        messages = self.server.store.messages_for_user(recipient_id, account_id)
        account = self.server.store.get_instagram_account(account_id) if account_id else None
        identity = self._instagram_identity_html(account)
        account_hidden = f'<input type="hidden" name="instagram_account_id" value="{account_id}">' if account_id else ""
        back_query = "?" + urlencode({"account": account_id}) if account_id else ""
        bubble_list = []
        for item in messages:
            try:
                attachments = json.loads(str(item["attachments"] or "[]"))
            except json.JSONDecodeError:
                attachments = []
            attachment_html = "".join(self._attachment_html(value) for value in attachments if isinstance(value, dict))
            text_html = esc(item["text"]) if item["text"] else '<span class="muted">Вкладення без тексту</span>'
            bubble_list.append(f'''<div class="bubble {"out" if item["direction"] == "out" else "in"}">{text_html}{attachment_html}<span class="meta">{esc(item["created_at"])} · {esc(item["source"])} · {esc(item["state"])}</span></div>''')
        bubbles = "".join(bubble_list) or '<div class="empty">Історія Direct порожня.</div>'
        name = f"@{user['username']}" if user["username"] else f"Instagram ID {recipient_id}"
        notice = f'<div class="notice error">{esc(error)}</div>' if error else ""
        content = f"""{notice}<section class="panel" style="margin-bottom:16px"><div class="row between"><div><h1 style="margin:0">{esc(name)}</h1><span class="muted">{esc(recipient_id)}</span></div><span class="badge {'archived' if user['manual_mode'] else 'on'}">{'Ручний режим' if user['manual_mode'] else 'Автоматизація активна'}</span></div>{identity}<div class="chat">{bubbles}</div><form method="post" action="/admin/users/send"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="recipient_id" value="{esc(recipient_id)}">{account_hidden}<label>Ручна відповідь в Instagram Direct</label><textarea name="message" required maxlength="1000" placeholder="Meta може відхилити повідомлення, якщо відповідь зараз не дозволена для цього діалогу."></textarea><div class="actions"><button>Надіслати від імені цього акаунта</button><a class="btn ghost" href="/admin/users{back_query}">До користувачів</a></div></form></section>
        <section class="panel"><h2>Картка користувача</h2><div class="row"><span>Підписка:</span>{self._follow_badge(user['follows_business'])}<span class="muted">Остання перевірка: {esc(user['follow_checked_at'] or 'ще не виконувалась')}</span><form class="inline" method="post" action="/admin/users/check-follow"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="recipient_id" value="{esc(recipient_id)}">{account_hidden}<button class="ghost">Перевірити зараз</button></form></div><form method="post" action="/admin/users/save"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="recipient_id" value="{esc(recipient_id)}">{account_hidden}<label>Мітки</label><input name="tags" value="{esc(user['tags'])}" placeholder="лід, клієнт, консультація"><label>Внутрішні нотатки</label><textarea name="notes">{esc(user['notes'])}</textarea><label class="row"><input style="width:auto" type="checkbox" name="manual_mode" {'checked' if user['manual_mode'] else ''}> Передати діалог людині та зупинити автоматичні відповіді</label><div class="actions"><button>Зберегти</button></div></form></section>
        <section class="panel danger-zone" style="margin-top:16px"><h2>Персональні дані</h2><p>Видалити журнал коментарів, Direct, помилки, нотатки та картку цього користувача лише для зазначеного Instagram-акаунта.</p><form method="post" action="/admin/users/delete" onsubmit="return confirm('Безповоротно видалити дані користувача для цього Instagram-акаунта?');"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="recipient_id" value="{esc(recipient_id)}">{account_hidden}<button class="danger">Видалити дані користувача</button></form></section>"""
        self._send(200, self._layout(name, content))

    @staticmethod
    def _follow_badge(value: object) -> str:
        if value is None:
            return '<span class="badge off">Не перевірено</span>'
        if bool(value):
            return '<span class="badge on">Підписаний</span>'
        return '<span class="badge archived">Не підписаний</span>'

    @staticmethod
    def _attachment_html(item: dict) -> str:
        url = str(item.get("url", ""))
        kind = str(item.get("type", "attachment"))
        label = str(item.get("name") or item.get("title") or kind or "Вкладення")
        if not url.startswith(("https://", "http://")):
            return f'<div class="notice">📎 {esc(label)} — URL недоступний</div>'
        lower = kind.casefold()
        if "image" in lower or "photo" in lower or "sticker" in lower:
            return f'<div><a href="{esc(url)}" target="_blank" rel="noopener"><img src="{esc(url)}" alt="{esc(label)}" style="max-width:260px;max-height:260px;border-radius:10px;margin-top:8px"></a></div>'
        if "video" in lower or "audio" in lower:
            tag = "audio" if "audio" in lower else "video"
            return f'<div><{tag} controls src="{esc(url)}" style="max-width:280px;margin-top:8px"></{tag}></div>'
        return f'<div><a href="{esc(url)}" target="_blank" rel="noopener">📎 {esc(label)}</a></div>'

    def _user_save(self, values: dict[str, str]) -> None:
        recipient_id = values.get("recipient_id", "")
        try:
            account_id = int(values.get("instagram_account_id", "")) or None
        except ValueError:
            account_id = None
        if not self.server.store.get_user(recipient_id, account_id):
            self._send(404, "Користувача не знайдено")
            return
        self.server.store.update_user(
            recipient_id, tags=values.get("tags", "").strip(), notes=values.get("notes", "").strip(),
            manual_mode="manual_mode" in values, instagram_account_id=account_id,
        )
        self._redirect(f"/admin/users/{quote(recipient_id, safe='')}?" + urlencode({"account": account_id or "", "ok": "Картку користувача збережено."}))

    def _user_send(self, values: dict[str, str]) -> None:
        recipient_id = values.get("recipient_id", "")
        message = values.get("message", "").strip()
        try:
            account_id = int(values.get("instagram_account_id", "")) or None
        except ValueError:
            account_id = None
        if not self.server.store.get_user(recipient_id, account_id) or not message:
            self._send(400, "Некоректний запит")
            return
        user = self.server.store.get_user(recipient_id, account_id)
        self.server.store.update_user(
            recipient_id, tags=str(user["tags"]), notes=str(user["notes"]), manual_mode=True,
            instagram_account_id=account_id,
        )
        try:
            account_id = account_id or self.server.store.account_id_for_user(recipient_id)
            message_id = self.server.accounts.client(account_id).send_text(recipient_id, message[:1000])
            self.server.store.log_direct(recipient_id, "out", "manual", message[:1000], message_id,
                                         instagram_account_id=account_id)
            self._redirect(f"/admin/users/{quote(recipient_id, safe='')}?" + urlencode({"account": account_id or "", "ok": "Повідомлення надіслано в Instagram Direct."}))
        except Exception as exc:
            self.server.store.log_direct(recipient_id, "out", "manual", message[:1000], state="error", error=str(exc), instagram_account_id=account_id)
            self._user_detail(recipient_id, f"Instagram не прийняв повідомлення: {str(exc)[:500]}", account_id)

    def _user_delete(self, values: dict[str, str]) -> None:
        try:
            account_id = int(values.get("instagram_account_id", "")) or None
        except ValueError:
            account_id = None
        self.server.store.delete_user_data(values.get("recipient_id", ""), account_id)
        self._redirect("/admin/users?" + urlencode({"account": account_id or "", "ok": "Дані користувача видалено."}))

    def _user_check_follow(self, values: dict[str, str]) -> None:
        recipient_id = values.get("recipient_id", "")
        try:
            account_id = int(values.get("instagram_account_id", "")) or None
        except ValueError:
            account_id = None
        if not self.server.store.get_user(recipient_id, account_id):
            self._send(404, "Користувача не знайдено")
            return
        target = f"/admin/users/{quote(recipient_id, safe='')}?"
        try:
            account_id = account_id or self.server.store.account_id_for_user(recipient_id)
            profile = self.server.accounts.client(account_id).get_user_profile(recipient_id)
            follows = profile.get("is_user_follow_business")
            self.server.store.update_follow_status(
                recipient_id, follows if isinstance(follows, bool) else None,
                str(profile.get("username", "")), str(profile.get("profile_pic", "")),
                instagram_account_id=account_id,
            )
            if follows is True:
                message = "Instagram підтвердив підписку користувача."
            elif follows is False:
                message = "Instagram підтвердив, що користувач не підписаний."
            else:
                message = "Instagram не повернув статус підписки для цього користувача."
            self._redirect(target + urlencode({"account": account_id or "", "ok": message}))
        except Exception as exc:
            self.server.store.update_follow_status(recipient_id, None, instagram_account_id=account_id)
            self._redirect(target + urlencode({"account": account_id or "", "err": f"Не вдалося перевірити підписку: {str(exc)[:300]}"}))

    def _settings(self) -> None:
        enabled = self.server.store.get_setting("telegram_enabled") == "1"
        chat_id = self.server.store.get_setting("telegram_chat_id") or ""
        has_token = bool(self.server.store.get_setting("telegram_bot_token"))
        retention = self.server.store.get_setting("retention_days") or "90"
        content = f"""<section class="panel"><h1>Налаштування</h1><form method="post" action="/admin/settings/save"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><h2>Telegram-сповіщення</h2><label class="row"><input style="width:auto" type="checkbox" name="telegram_enabled" {'checked' if enabled else ''}> Сповіщати про запуск, зупинку, стан схеми, помилки та всі коментарі під відстежуваними публікаціями</label><div class="two"><div><label>Токен Telegram-бота</label><input type="password" name="telegram_bot_token" placeholder="{'Токен уже збережено; залиште порожнім без змін' if has_token else '123456:ABC...'}"></div><div><label>Chat ID</label><input name="telegram_chat_id" value="{esc(chat_id)}"></div></div><p class="muted">Токен зберігається лише в локальній базі з правами доступу 600 і не показується повторно.</p><h2>Конфіденційність</h2><label>Зберігати історію, днів</label><input type="number" name="retention_days" min="7" max="3650" value="{esc(retention)}"><div class="actions"><button>Зберегти</button></div></form><form method="post" action="/admin/settings/test-telegram"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button class="ghost">Надіслати тест у Telegram</button></form></section>"""
        self._send(200, self._layout("Налаштування", content))

    def _settings_save(self, values: dict[str, str]) -> None:
        try:
            retention = max(7, min(3650, int(values.get("retention_days", "90"))))
        except ValueError:
            retention = 90
        self.server.store.set_setting("retention_days", str(retention))
        self.server.store.set_setting("telegram_enabled", "1" if "telegram_enabled" in values else "0")
        self.server.store.set_setting("telegram_chat_id", values.get("telegram_chat_id", "").strip())
        if values.get("telegram_bot_token", "").strip():
            self.server.store.set_setting("telegram_bot_token", values["telegram_bot_token"].strip())
        self.server.store.cleanup_old_data(retention)
        self._redirect("/admin/settings?" + urlencode({"ok": "Налаштування збережено."}))

    def _telegram_test(self) -> None:
        ok = self.server.config and self.server.store.get_setting("telegram_enabled") == "1"
        from .notifications import TelegramNotifier
        sent = TelegramNotifier(self.server.store).send("🧪 Тестове повідомлення", "✅ Сповіщення налаштовані правильно.") if ok else False
        message = "Тестове повідомлення надіслано." if sent else "Не вдалося надіслати. Перевірте токен, Chat ID та увімкнення."
        self._redirect("/admin/settings?" + urlencode({"ok": message}))

    def _history(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        try:
            automation_id = int(query.get("automation", [""])[0]) or None
        except ValueError:
            automation_id = None
        status = query.get("status", [""])[0]
        rows = self.server.store.history(automation_id, status)
        options = ['<option value="">Усі автоматизації</option>']
        for item in self.server.store.list_automations(True):
            selected = " selected" if automation_id == item["id"] else ""
            options.append(f'<option value="{item["id"]}"{selected}>{esc(item["name"])}</option>')
        statuses = [("", "Усі статуси"), ("fulfilled", "Файл надіслано"),
                    ("waiting", "Очікує підтвердження"), ("partial", "Не завершено"), ("error", "Помилка")]
        status_options = "".join(f'<option value="{key}"{" selected" if status == key else ""}>{label}</option>' for key, label in statuses)
        body = []
        for row in rows:
            public = "done" if row["public_done"] else ""
            private = "done" if row["private_done"] else ""
            fulfilled = "done" if row["recipient_state"] == "fulfilled" else ""
            state = "Помилка" if row["last_error"] else ("Файл надіслано" if fulfilled else ("Очікує ГОТОВО" if private else "В обробці"))
            user = f"@{row['username']}" if row["username"] else "—"
            error = f'<div class="muted">{esc(row["last_error"])}</div>' if row["last_error"] else ""
            body.append(f"""<tr><td>{esc(row['created_at'])}</td><td><strong>{esc(user)}</strong></td>
            <td>{esc(row['automation_name'] or 'Видалена автоматизація')}</td><td class="wrap">{esc(row['comment_text'] or '—')}</td>
            <td><div class="steps" title="Коментар → Direct → файл"><span class="step {public}"></span><span class="step {private}"></span><span class="step {fulfilled}"></span></div>{esc(state)}{error}</td></tr>""")
        table = "".join(body) if body else '<tr><td colspan="5" class="empty">Записів не знайдено.</td></tr>'
        content = f"""<section class="panel"><div class="row between"><div><h1 style="margin:0">Історія</h1><span class="muted">Останні 200 спрацювань</span></div></div>
        <form method="get" class="two"><div><label>Автоматизація</label><select name="automation">{''.join(options)}</select></div><div><label>Статус</label><select name="status">{status_options}</select></div><div><button>Фільтрувати</button></div></form>
        <div class="table-wrap"><table><thead><tr><th>Час</th><th>Користувач</th><th>Автоматизація</th><th>Коментар</th><th>Статус</th></tr></thead><tbody>{table}</tbody></table></div></section>"""
        self._send(200, self._layout("Історія", content))

    def _analytics(self) -> None:
        summary, per = self.server.store.analytics()
        comments = int(summary["comments"] or 0)
        private = int(summary["private_sent"] or 0)
        fulfilled = int(summary["fulfilled"] or 0)
        confirmed_follows = int(summary["confirmed_follows"] or 0)
        conversion = round(fulfilled * 100 / comments, 1) if comments else 0
        rows = []
        for row in per:
            count = int(row["comments"] or 0)
            done = int(row["fulfilled"] or 0)
            percent = round(done * 100 / count, 1) if count else 0
            rows.append(f'''<tr><td>{esc(row['name'])}</td><td>{count}</td><td>{int(row['private_sent'] or 0)}</td><td>{done}</td><td>{int(row['confirmed_follows'] or 0)}</td><td>{percent}%<progress max="100" value="{percent}"></progress></td><td>{int(row['errors'] or 0)}</td></tr>''')

        follower_cards = []
        for account in self.server.store.list_instagram_accounts(False):
            snapshot = self.server.store.latest_follower_snapshot(int(account["id"]))

            def metric_value(key: str, signed: bool = False) -> tuple[str, str]:
                if snapshot is None or snapshot[key] is None:
                    return "—", ""
                value = int(snapshot[key])
                css = "delta-positive" if value > 0 else ("delta-negative" if value < 0 else "")
                return (f"{value:+d}" if signed else str(value)), css

            current, _ = metric_value("followers_count")
            gained, _ = metric_value("new_followers")
            lost, _ = metric_value("lost_followers")
            net, net_class = metric_value("net_change", signed=True)
            checked = esc(snapshot["recorded_at"] if snapshot else "ще не оновлювалося")
            insight_error = ""
            if snapshot and (snapshot["last_error"] or snapshot["new_followers"] is None
                             or snapshot["lost_followers"] is None):
                insight_error = '<div class="notice" style="margin-top:12px">Instagram не повернув денне розділення. Поточна кількість підписників при цьому може залишатися доступною.</div>'
            follower_cards.append(f'''<article class="card">{self._instagram_identity_html(account)}
                <div class="follower-metrics">
                  <div class="follower-metric"><strong>{current}</strong><small>Поточні</small></div>
                  <div class="follower-metric"><strong>{gained}</strong><small>Нові за день</small></div>
                  <div class="follower-metric"><strong>{lost}</strong><small>Втрачені за день</small></div>
                  <div class="follower-metric"><strong class="{net_class}">{net}</strong><small>Чистий приріст</small></div>
                </div>{insight_error}<p class="muted" style="margin-bottom:0">Оновлено: {checked}</p></article>''')

        refresh = f'''<form method="post" action="/admin/analytics/refresh"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button>Оновити показники</button></form>'''
        content = f"""<section class="panel"><div class="row between"><div><h1 style="margin:0">Підписники</h1><span class="muted">Показники окремо для кожного Instagram-акаунта</span></div>{refresh}</div>
        <div class="follower-grid">{''.join(follower_cards) if follower_cards else '<div class="empty">Немає підключених акаунтів.</div>'}</div></section>
        <section class="panel"><h1>Аналітика автоматизацій</h1><div class="stats">
        <div class="stat"><span class="muted">Коментарі</span><strong>{comments}</strong></div><div class="stat"><span class="muted">Direct</span><strong>{private}</strong></div>
        <div class="stat"><span class="muted">Файлів надіслано</span><strong>{fulfilled}</strong></div><div class="stat"><span class="muted">Конверсія</span><strong>{conversion}%</strong></div>
        <div class="stat"><span class="muted">Підтверджені підписки</span><strong>{confirmed_follows}</strong></div>
        <div class="stat"><span class="muted">Помилки</span><strong>{int(summary['errors'] or 0)}</strong></div></div>
        <div class="notice">Підтверджена підписка зараховується конкретній автоматизації лише коли Instagram спочатку підтвердив, що користувач не був підписаний, а після взаємодії — що він підписався. Через обмеження API це консервативний показник і він може бути нижчим за фактичний.</div>
        <div class="table-wrap"><table><thead><tr><th>Автоматизація</th><th>Коментарі</th><th>Direct</th><th>Файли</th><th>Підтверджені підписки</th><th>Конверсія</th><th>Помилки</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"""
        self._send(200, self._layout("Аналітика", content))

    def _analytics_refresh(self) -> None:
        successes = 0
        accounts = self.server.store.list_instagram_accounts(False)
        for account in accounts:
            try:
                self.server.accounts.refresh_limits(int(account["id"]))
                successes += 1
            except Exception:
                continue
        if successes:
            self._redirect("/admin/analytics?" + urlencode({
                "ok": f"Показники оновлено для {successes} із {len(accounts)} акаунтів."
            }))
        else:
            self._redirect("/admin/analytics?" + urlencode({
                "err": "Instagram не повернув показники. Перевірте підключення акаунтів і доступ до Insights."
            }))

    def _library(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        try:
            account_id = int(query.get("account", [""])[0]) or None
        except ValueError:
            account_id = None
        accounts = {int(row["id"]): row for row in self.server.store.list_instagram_accounts(False)}
        account_options = ['<option value="">Усі файли</option>']
        for account in accounts.values():
            selected = " selected" if account_id == int(account["id"]) else ""
            account_options.append(
                f'<option value="{account["id"]}"{selected}>Використовує @{esc(account["username"] or account["instagram_user_id"])}</option>'
            )
        notice = ""
        cards = []
        for document in self.server.store.list_documents(account_id):
            delete = ""
            if not document["use_count"]:
                delete = f'''<form class="inline" method="post" action="/admin/library/delete" onsubmit="return confirm('Видалити файл із бібліотеки?');"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{document['id']}"><button class="danger">Видалити</button></form>'''
            folder = str(document["folder"] or "")
            stored = str(document["stored_name"] or Path(str(document["file_path"])).name)
            file_type = Path(stored).suffix.upper().removeprefix(".") or "FILE"
            extension = Path(stored).suffix.casefold()
            preview = ""
            if extension in {".jpg", ".jpeg", ".png", ".webp"}:
                preview_url = f"/admin/library/preview/{document['id']}"
                preview = f'''<a class="library-preview" href="{preview_url}" target="_blank" title="Відкрити зображення"><img src="{preview_url}" alt="{esc(document['title'])}" loading="lazy"></a>'''
            move = f'''<form method="post" action="/admin/library/move"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{document['id']}"><label>Перемістити в папку</label><div class="row"><select style="width:auto;min-width:180px" name="folder">{self._folder_options(folder)}</select><button class="ghost">Перемістити</button></div></form>'''
            account_names = [value for value in str(document["account_names"] or "").split(",") if value]
            account_badges = "".join(f'<span class="badge on">@{esc(name)}</span>' for name in account_names)
            usage = account_badges or '<span class="muted">Ще не призначено жодній автоматизації</span>'
            cards.append(f"""<article class="card">{preview}<div class="row between"><h3>{esc(document['title'])}</h3><span class="badge archived">{esc(file_type)}</span></div><p class="muted">Збережено: <code>{esc((folder + '/') if folder else '')}{esc(stored)}</code></p><p class="muted">Оригінал: {esc(document['original_name'])} · {self._size(document['size_bytes'])}</p><p>Автоматизацій: {document['use_count']}</p><div class="row account-badges">{usage}</div>{move}<div class="actions"><a class="btn ghost" href="/admin/library/download/{document['id']}">Завантажити</a>{delete}</div></article>""")
        content = f"""{notice}<section class="panel" style="margin-bottom:16px"><div class="row between"><div><h1 style="margin:0">Бібліотека файлів</h1><span class="muted">Спільне сховище для всіх Instagram-акаунтів; один файл можна використати в кількох автоматизаціях.</span></div><form method="get" class="row"><select name="account" style="width:auto;min-width:250px">{''.join(account_options)}</select><button>Фільтрувати</button></form></div><div class="two" style="margin-top:18px"><form method="post" action="/admin/library/upload" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><h2>Завантажити файл</h2><label>Назва</label><input name="title" required><label>Файл до 100 МБ</label><input type="file" name="file" accept="{esc(FILE_ACCEPT)}" required><p class="muted">JPG, JPEG, PNG, WEBP, MP4, MOV, PDF, DOCX, XLSX, PPTX, TXT, MP3, WAV або ZIP.</p><label>Папка</label><select name="folder">{self._folder_options()}</select><div class="actions"><button>Додати в бібліотеку</button></div></form><form method="post" action="/admin/library/folder"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><h2>Створити папку</h2><label>Папка або шлях підпапок</label><input name="folder" required placeholder="Наприклад: Курси/Матеріали"><p class="muted">Кирилиця автоматично транслітерується: <code>Курси/Матеріали</code> → <code>kursy/materialy</code>.</p><div class="actions"><button class="secondary">Створити папку</button></div></form></div></section><section class="panel"><div class="grid">{''.join(cards) if cards else '<div class="empty">Для вибраного акаунта файлів ще немає.</div>'}</div></section>"""
        self._send(200, self._layout("Бібліотека файлів", content))

    def _backups(self) -> None:
        notice = ""
        rows = []
        paths = list(self.server.backup_dir.glob("*.zip")) + list(self.server.backup_dir.glob("*.sqlite3"))
        for path in sorted(paths, reverse=True):
            delete = f'''<form class="inline" method="post" action="/admin/backups/delete" onsubmit="return confirm('Видалити цю резервну копію?');"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="name" value="{esc(path.name)}"><button class="danger">Видалити</button></form>'''
            rows.append(f'<tr><td>{esc(path.name)}</td><td>{self._size(path.stat().st_size)}</td><td><a class="btn ghost" href="/admin/backups/download/{esc(path.name)}">Завантажити</a> {delete}</td></tr>')
        content = f"""{notice}<section class="panel"><div class="row between"><div><h1 style="margin:0">Резервні копії</h1><span class="muted">Автоматична копія створюється раз на день; зберігаються останні 14.</span></div><form method="post" action="/admin/backups/create"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><button>Створити зараз</button></form></div><div class="notice" style="margin-top:16px">ZIP-копія містить базу налаштувань, історію та всі файли бібліотеки. Зберігайте завантажені копії в безпечному місці.</div><div class="table-wrap"><table><thead><tr><th>Файл</th><th>Розмір</th><th>Дії</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"""
        self._send(200, self._layout("Резервні копії", content))

    @staticmethod
    def _size(value: int) -> str:
        if value >= 1024 * 1024:
            return f"{value / 1024 / 1024:.1f} МБ"
        return f"{max(1, value // 1024)} КБ"

    def _versions(self, automation_id: int) -> None:
        automation = self.server.store.get_automation(automation_id)
        if automation is None:
            self._send(404, "Автоматизацію не знайдено")
            return
        rows = []
        for version in self.server.store.list_versions(automation_id):
            try:
                snapshot = json.loads(str(version["snapshot"]))
                description = f"Слова: {snapshot.get('trigger_keywords', '—')} · Файл: {Path(str(snapshot.get('pdf_path', ''))).name}"
            except json.JSONDecodeError:
                description = "Пошкоджений знімок"
            restore = f'''<form class="inline" method="post" action="/admin/versions/restore" onsubmit="return confirm('Опублікувати цю версію?');"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{version['id']}"><button class="ghost">Відновити й опублікувати</button></form>'''
            rows.append(f'''<tr><td>{esc(version['created_at'])}</td><td><span class="badge {'archived' if version['status'] == 'draft' else 'on'}">{'Чернетка' if version['status'] == 'draft' else 'Опубліковано'}</span></td><td class="wrap">{esc(description)}</td><td><a class="btn ghost" href="/admin/automation/{automation_id}?version={version['id']}">Відкрити</a> {restore}</td></tr>''')
        content = f"""<section class="panel"><div class="row between"><div><h1 style="margin:0">Версії: {esc(automation['name'])}</h1><span class="muted">Чернетки не впливають на активний сценарій.</span></div><a class="btn secondary" href="/admin/automation/{automation_id}">Редагувати поточну</a></div><div class="table-wrap"><table><thead><tr><th>Час</th><th>Тип</th><th>Зміст</th><th>Дії</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="4" class="empty">Версій ще немає.</td></tr>'}</tbody></table></div></section>"""
        self._send(200, self._layout("Версії", content))

    def _version_restore(self, values: dict[str, str]) -> None:
        try:
            version = self.server.store.get_version(int(values.get("id", "")))
        except ValueError:
            version = None
        if version is None:
            self._send(404, "Версію не знайдено")
            return
        automation_id = int(version["automation_id"])
        current = self.server.store.get_automation(automation_id)
        try:
            snapshot = json.loads(str(version["snapshot"]))
            required = ("name", "media_id", "media_permalink", "trigger_keywords", "confirmation_words",
                        "public_reply_text", "initial_dm_text", "guide_message_text", "pdf_path", "enabled")
            optional = {
                "conversation_rules": "[]", "require_follow": 0,
                "follow_required_message": "Підпишіться на акаунт і повторіть відповідь.",
                "instagram_account_id": current["instagram_account_id"] if current is not None else None,
            }
            clean = {key: snapshot[key] for key in required}
            clean.update({key: snapshot.get(key, default) for key, default in optional.items()})
        except (json.JSONDecodeError, KeyError):
            self._send(400, "Версія пошкоджена")
            return
        if current is None or not Path(str(clean["pdf_path"])).is_file():
            self._send(409, "Автоматизація або її файл більше не існує")
            return
        current_values = {key: current[key] for key in (*required, *optional)}
        self.server.store.save_version(automation_id, "published", current_values)
        self.server.store.save_automation(clean, automation_id)
        self.server.store.save_version(automation_id, "published", clean)
        self._redirect("/admin/?" + urlencode({"ok": "Вибрану версію відновлено й опубліковано."}))

    def _action_form(self, automation_id: int, action: str, label: str, style: str, confirm: str = "") -> str:
        onsubmit = f' onsubmit="{esc(confirm)}"' if confirm else ""
        return f'<form class="inline" method="post" action="/admin/automation/action"{onsubmit}><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{automation_id}"><input type="hidden" name="action" value="{action}"><button class="{style}">{esc(label)}</button></form>'

    def _check_form(self, automation_id: int) -> str:
        return f'<form class="inline" method="post" action="/admin/automation/check"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{automation_id}"><button class="ghost">Перевірити</button></form>'

    def _restart_form(self, service: str, label: str) -> str:
        return f'<form class="inline" method="post" action="/admin/service/restart"><input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="service" value="{esc(service)}"><button class="ghost">{esc(label)}</button></form>'

    def _automation_form(self, row, error: str = "", submitted: dict[str, str] | None = None) -> None:
        default_account = self.server.store.default_instagram_account()
        data = dict(row) if row is not None else {
            "id": "", "name": "", "media_id": "", "media_permalink": "",
            "trigger_keywords": "гайд,гайда,гайду,гайдом,гайди",
            "confirmation_words": "готово", "public_reply_text": "Написав вам у Direct 😊",
            "initial_dm_text": "Привіт! Щоб отримати файл, підпишись на @your_account та напиши у відповідь слово «ГОТОВО».",
            "guide_message_text": "Ось твій файл", "pdf_path": "", "enabled": 1,
            "conversation_rules": "[]", "require_follow": 0,
            "follow_required_message": "Підписку поки не підтверджено. Підпишіться на акаунт і повторіть відповідь.",
            "instagram_account_id": int(default_account["id"]) if default_account else "",
        }
        if submitted:
            data.update(submitted)
        query_account = parse_qs(urlparse(self.path).query).get("account", [""])[0]
        if query_account:
            data["instagram_account_id"] = query_account
        try:
            selected_account_id = int(data.get("instagram_account_id") or 0) or None
        except (ValueError, TypeError):
            selected_account_id = None
        account_options = []
        for account in self.server.store.list_instagram_accounts(False):
            selected = " selected" if selected_account_id == int(account["id"]) else ""
            account_options.append(f'<option value="{account["id"]}"{selected}>@{esc(account["username"])} · {esc(account["instagram_user_id"])}</option>')
        posts: list[dict] = []
        api_error = ""
        try:
            posts = self.server.accounts.client(selected_account_id).list_media(50)
        except Exception as exc:
            api_error = str(exc)[:300]
        options = ['<option value="">— Виберіть зі списку або заповніть нижче —</option>']
        for post in posts:
            caption = (post.get("caption") or "Без підпису").replace("\n", " ")[:70]
            options.append(f'<option value="{esc(post.get("id"))}" data-url="{esc(post.get("permalink"))}">{esc(post.get("media_type"))} · {esc(caption)}</option>')
        notice = f'<div class="notice error">{esc(error)}</div>' if error else ""
        if api_error:
            notice += f'<div class="notice">Не вдалося завантажити список публікацій: {esc(api_error)}. Media ID можна ввести вручну.</div>'
        checked = "checked" if str(data.get("enabled", "1")) in {"1", "True", "true", "on"} else ""
        follow_checked = "checked" if str(data.get("require_follow", "0")) in {"1", "True", "true", "on"} else ""
        try:
            rules = json.loads(str(data.get("conversation_rules") or "[]"))
            if not isinstance(rules, list):
                rules = []
        except json.JSONDecodeError:
            rules = []
        rule_rows = []
        for index, rule in enumerate(rules):
            rule_rows.append(self._rule_row(index, rule))
        current_pdf = f'<p class="muted">Поточний файл: {esc(Path(str(data.get("pdf_path") or "")).name)}</p>' if data.get("pdf_path") else ""
        documents = ['<option value="">— Залишити поточний або завантажити новий —</option>']
        for document in self.server.store.list_documents():
            selected = " selected" if str(document["file_path"]) == str(data.get("pdf_path") or "") else ""
            documents.append(f'<option value="{document["id"]}"{selected}>{esc(document["title"])} · {esc(document["original_name"])}</option>')
        title = "Нова автоматизація" if row is None else "Редагування автоматизації"
        content = f"""{notice}<section class="panel"><h1>{title}</h1><form method="post" action="/admin/automation/save" enctype="multipart/form-data">
        <input type="hidden" name="csrf" value="{esc(self._csrf())}"><input type="hidden" name="id" value="{esc(data.get('id'))}"><input type="hidden" name="existing_pdf" value="{esc(data.get('pdf_path'))}">
        <label>Назва автоматизації</label><input name="name" value="{esc(data.get('name'))}" required placeholder="Наприклад: Гайд із читання">
        <label>Instagram-акаунт</label><select id="account-select" name="instagram_account_id" required>{''.join(account_options)}</select><small class="muted">Кожна автоматизація працює лише для вибраного акаунта.</small>
        <label>Вибрати публікацію Instagram</label><select id="post-select">{''.join(options)}</select>
        <div class="two"><div><label>Media ID публікації</label><input id="media-id" name="media_id" value="{esc(data.get('media_id'))}" placeholder="Заповниться після вибору зі списку"></div><div><label>Посилання на публікацію</label><input id="media-url" name="media_permalink" type="url" value="{esc(data.get('media_permalink'))}" placeholder="https://www.instagram.com/p/..."></div></div>
        <div class="two"><div><label>Ключові слова коментаря</label><input name="trigger_keywords" value="{esc(data.get('trigger_keywords'))}" required><small class="muted">Через кому; регістр не враховується.</small></div><div><label>Слова підтвердження</label><input name="confirmation_words" value="{esc(data.get('confirmation_words'))}" required></div></div>
        <label>Публічна відповідь на коментар</label><textarea name="public_reply_text" required>{esc(data.get('public_reply_text'))}</textarea>
        <label>Перше повідомлення в Direct</label><textarea name="initial_dm_text" required>{esc(data.get('initial_dm_text'))}</textarea>
        <label>Текст перед посиланням на файл</label><textarea name="guide_message_text" required>{esc(data.get('guide_message_text'))}</textarea>
        <section class="card" style="margin-top:18px"><h2>Перевірка підписки</h2><label class="row"><input style="width:auto" type="checkbox" name="require_follow" {follow_checked}> Перевіряти через Instagram User Profile API перед видачею файлу</label><label>Повідомлення, якщо підписку не підтверджено</label><textarea name="follow_required_message">{esc(data.get('follow_required_message'))}</textarea><p class="muted">Перевірка доступна для Instagram-користувача, який уже взаємодіє з професійним акаунтом у Direct.</p></section>
        <section class="card" style="margin-top:18px"><div class="row between"><div><h2 style="margin:0">Багатокрокові правила</h2><span class="muted">Декілька правил з одного стану створюють розгалуження.</span></div><button class="ghost" type="button" onclick="addRule()">+ Додати правило</button></div><input type="hidden" id="rule-count" name="rule_count" value="{len(rules)}"><div id="rules">{''.join(rule_rows)}</div><p class="muted">Для останнього правила позначте «Надіслати файл».</p></section>
        <div class="two"><div><label>Файл із бібліотеки</label><select name="document_id">{''.join(documents)}</select>{current_pdf}</div><div><label>Або завантажити новий файл</label><input type="file" name="file" accept="{esc(FILE_ACCEPT)}"><label>Папка для нового файлу</label><select name="upload_folder">{self._folder_options(str(data.get('upload_folder', '')))}</select><small class="muted">До 100 МБ. Назва автоматично зберігається латиницею; папки створюються в Бібліотеці.</small></div></div>
        <label class="row"><input style="width:auto" type="checkbox" name="enabled" {checked}> Увімкнути одразу після збереження</label>
        <div class="actions"><button name="mode" value="publish">Зберегти й опублікувати</button><button class="ghost" name="mode" value="draft">Зберегти чернетку</button><a class="btn secondary" href="/admin/">Скасувати</a></div></form></section>
        <script>const s=document.getElementById('post-select');s.addEventListener('change',()=>{{const o=s.options[s.selectedIndex];if(o.value){{document.getElementById('media-id').value=o.value;document.getElementById('media-url').value=o.dataset.url||'';}}}});const a=document.getElementById('account-select');a.addEventListener('change',()=>{{if(confirm('Завантажити публікації вибраного акаунта? Незбережені зміни форми буде скинуто.'))location.href=location.pathname+'?account='+encodeURIComponent(a.value);}});let rc={len(rules)};function addRule(){{const i=rc++;document.getElementById('rule-count').value=rc;document.getElementById('rules').insertAdjacentHTML('beforeend',`<div class="rule"><div class="two"><div><label>Поточний стан</label><input name="rule_state_${{i}}" value="waiting" required></div><div><label>Ключові слова</label><input name="rule_keywords_${{i}}" required></div></div><label>Відповідь або наступне запитання</label><textarea name="rule_reply_${{i}}"></textarea><div class="two"><div><label>Наступний стан</label><input name="rule_next_${{i}}" value="waiting"></div><label class="row"><input style="width:auto" type="checkbox" name="rule_pdf_${{i}}"> Надіслати файл і завершити</label></div><button class="danger" type="button" onclick="this.closest('.rule').remove()">Прибрати</button></div>`);}}</script>"""
        self._send(200, self._layout(title, content))

    def _rule_row(self, index: int, rule: dict) -> str:
        checked = "checked" if rule.get("send_pdf") else ""
        return f'''<div class="rule"><div class="two"><div><label>Поточний стан</label><input name="rule_state_{index}" value="{esc(rule.get('state', 'waiting'))}" required></div><div><label>Ключові слова</label><input name="rule_keywords_{index}" value="{esc(rule.get('keywords', ''))}" required></div></div><label>Відповідь або наступне запитання</label><textarea name="rule_reply_{index}">{esc(rule.get('reply_text', ''))}</textarea><div class="two"><div><label>Наступний стан</label><input name="rule_next_{index}" value="{esc(rule.get('next_state', 'waiting'))}"></div><label class="row"><input style="width:auto" type="checkbox" name="rule_pdf_{index}" {checked}> Надіслати файл і завершити</label></div><button class="danger" type="button" onclick="this.closest('.rule').remove()">Прибрати</button></div>'''

    def _save_automation(self, values: dict[str, str], files: dict[str, tuple[str, bytes]]) -> None:
        try:
            automation_id = int(values["id"]) if values.get("id") else None
        except ValueError:
            self._send(400, "Некоректний ID")
            return
        existing = self.server.store.get_automation(automation_id) if automation_id else None
        account_value = values.get("instagram_account_id", "")
        default_account = self.server.store.default_instagram_account()
        try:
            account_id = int(account_value) if account_value else (
                int(default_account["id"]) if default_account else None
            )
        except ValueError:
            account_id = None
        if account_value and (account_id is None or self.server.store.get_instagram_account(account_id) is None):
            self._automation_form(existing, "Виберіть підключений Instagram-акаунт.", values)
            return
        account_meta = self.server.accounts.client(account_id) if hasattr(self.server, "accounts") else self.server.meta
        required = ("name", "trigger_keywords", "confirmation_words", "public_reply_text", "initial_dm_text", "guide_message_text")
        if any(not values.get(field, "").strip() for field in required):
            self._automation_form(existing, "Заповніть усі обов’язкові поля.", values)
            return
        if not values.get("media_id", "").strip() and values.get("media_permalink", "").strip():
            wanted = values["media_permalink"].strip().rstrip("/")
            try:
                match = next(
                    (post for post in account_meta.list_media(100)
                     if str(post.get("permalink", "")).rstrip("/") == wanted),
                    None,
                )
            except Exception as exc:
                self._automation_form(existing, f"Не вдалося перевірити посилання через Instagram API: {str(exc)[:250]}", values)
                return
            if match:
                values["media_id"] = str(match.get("id", ""))
            else:
                self._automation_form(existing, "Публікацію за цим посиланням не знайдено серед останніх публікацій акаунта.", values)
                return
        if not values.get("media_id", "").strip():
            self._automation_form(existing, "Виберіть публікацію або введіть її Media ID/посилання.", values)
            return
        pdf_path = str(existing["pdf_path"]) if existing else ""
        if values.get("document_id"):
            try:
                document = self.server.store.get_document(int(values["document_id"]))
            except ValueError:
                document = None
            if document is None or not Path(str(document["file_path"])).is_file():
                self._automation_form(existing, "Вибраний файл відсутній у бібліотеці.", values)
                return
            pdf_path = str(document["file_path"])
        upload = files.get("file") or files.get("pdf")
        if upload and upload[1]:
            filename, body = upload
            if len(body) > MAX_FILE_SIZE:
                self._automation_form(existing, "Файл перевищує 100 МБ.", values)
                return
            valid, upload_error = validate_upload(filename, body)
            if not valid:
                self._automation_form(existing, upload_error, values)
                return
            try:
                folder = normalized_folder(values.get("upload_folder", ""))
            except ValueError as exc:
                self._automation_form(existing, str(exc), values)
                return
            path = unique_file_path(self.server.guide_dir, folder, filename)
            path.write_bytes(body)
            os.chmod(path, 0o600)
            pdf_path = str(path)
            self.server.store.add_document(
                values.get("name", "Файл").strip() or "Файл", filename, pdf_path, len(body),
                folder, path.name,
            )
        if not pdf_path:
            self._automation_form(existing, "Додайте файл.", values)
            return
        rules: list[dict] = []
        try:
            rule_count = max(0, min(50, int(values.get("rule_count", "0"))))
        except ValueError:
            rule_count = 0
        state_pattern = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
        for index in range(rule_count):
            state = values.get(f"rule_state_{index}", "").strip()
            keywords = self._clean_csv(values.get(f"rule_keywords_{index}", ""))
            reply = values.get(f"rule_reply_{index}", "").strip()[:1000]
            next_state = values.get(f"rule_next_{index}", "").strip() or "waiting"
            send_pdf = f"rule_pdf_{index}" in values
            if not state and not keywords and not reply:
                continue
            if not state_pattern.fullmatch(state) or not state_pattern.fullmatch(next_state):
                self._automation_form(existing, "Назви станів у багатокрокових правилах можуть містити лише латинські літери, цифри, _ та -.", values)
                return
            if not keywords:
                self._automation_form(existing, "У кожному багатокроковому правилі вкажіть ключові слова.", values)
                return
            if not send_pdf and not reply:
                self._automation_form(existing, "Правило без надсилання файлу повинно містити відповідь або наступне запитання.", values)
                return
            rules.append({
                "state": state, "keywords": keywords, "reply_text": reply,
                "next_state": next_state, "send_pdf": send_pdf,
            })
        follow_message = values.get("follow_required_message", "").strip()[:1000]
        if "require_follow" in values and not follow_message:
            self._automation_form(existing, "Додайте повідомлення для користувача без підтвердженої підписки.", values)
            return
        clean = {
            "name": values["name"].strip()[:120],
            "media_id": values["media_id"].strip()[:100],
            "media_permalink": values.get("media_permalink", "").strip()[:500],
            "trigger_keywords": self._clean_csv(values["trigger_keywords"]),
            "confirmation_words": self._clean_csv(values["confirmation_words"]),
            "public_reply_text": values["public_reply_text"].strip()[:1000],
            "initial_dm_text": values["initial_dm_text"].strip()[:1000],
            "guide_message_text": values["guide_message_text"].strip()[:1000],
            "pdf_path": pdf_path,
            "conversation_rules": json.dumps(rules, ensure_ascii=False),
            "require_follow": int("require_follow" in values),
            "follow_required_message": follow_message or "Підпишіться на акаунт і повторіть відповідь.",
            "enabled": int("enabled" in values),
            "instagram_account_id": account_id,
        }
        mode = values.get("mode", "publish")
        if mode == "draft":
            if automation_id is None:
                draft_values = dict(clean)
                draft_values["enabled"] = 0
                automation_id = self.server.store.save_automation(draft_values)
            self.server.store.save_version(automation_id, "draft", clean)
            self._redirect(f"/admin/automation/{automation_id}/versions?" + urlencode({"ok": "Чернетку збережено."}))
            return
        automation_id = self.server.store.save_automation(clean, automation_id)
        self.server.store.save_version(automation_id, "published", clean)
        self._redirect("/admin/?" + urlencode({"ok": "Автоматизацію опубліковано. Зміни вже діють."}))

    @staticmethod
    def _clean_csv(value: str) -> str:
        return ",".join(dict.fromkeys(item.strip().casefold() for item in value.split(",") if item.strip()))

    def _automation_action(self, values: dict[str, str]) -> None:
        try:
            automation_id = int(values.get("id", ""))
        except ValueError:
            self._send(400, "Некоректний ID")
            return
        action = values.get("action")
        row = self.server.store.get_automation(automation_id)
        if row is None:
            self._send(404, "Не знайдено")
            return
        message = "Готово."
        if action == "toggle":
            self.server.store.set_automation_flags(automation_id, enabled=not bool(row["enabled"]))
            message = "Статус автоматизації змінено."
        elif action == "archive":
            self.server.store.set_automation_flags(automation_id, enabled=False, archived=True)
            message = "Автоматизацію переміщено в архів."
        elif action == "restore":
            self.server.store.set_automation_flags(automation_id, archived=False)
            message = "Автоматизацію відновлено з архіву."
        elif action == "duplicate" and not row["archived"]:
            copy_id = self.server.store.duplicate_automation(automation_id)
            if copy_id is None:
                self._send(404, "Не знайдено")
                return
            self._redirect(f"/admin/automation/{copy_id}?" + urlencode({"ok": "Створено вимкнену копію автоматизації."}))
            return
        elif action == "delete" and row["archived"]:
            self.server.store.delete_automation(automation_id)
            message = "Автоматизацію видалено; її файл залишився в бібліотеці."
        else:
            self._send(400, "Недоступна дія")
            return
        self._redirect("/admin/?" + urlencode({"ok": message}))

    def _check_automation(self, values: dict[str, str]) -> None:
        try:
            automation_id = int(values.get("id", ""))
        except ValueError:
            self._send(400, "Некоректний ID")
            return
        row = self.server.store.get_automation(automation_id)
        if row is None:
            self._send(404, "Не знайдено")
            return
        results: list[tuple[bool, str]] = []
        results.append((bool(row["media_id"]), "Media ID задано"))
        keywords = set(self._clean_csv(str(row["trigger_keywords"])).split(",")) - {""}
        results.append((bool(keywords), "Є ключові слова коментаря"))
        pdf = Path(str(row["pdf_path"]))
        valid_file = False
        if pdf.is_file():
            try:
                valid_file, _ = validate_upload(pdf.name, pdf.read_bytes())
            except OSError:
                pass
        results.append((valid_file, "Файл існує та має правильний формат"))
        results.append((self.server.config.public_base_url.startswith("https://"), "Публічна HTTPS-адреса налаштована"))
        conflicts = []
        for other in self.server.store.active_automations_for_media(
            str(row["media_id"]), int(row["instagram_account_id"]) if row["instagram_account_id"] else None
        ):
            if other["id"] == row["id"]:
                continue
            other_words = set(self._clean_csv(str(other["trigger_keywords"])).split(","))
            common = keywords & other_words
            if common:
                conflicts.append(f"{other['name']}: {', '.join(sorted(common))}")
        results.append((not conflicts, "Немає конфлікту ключових слів" + (f" ({'; '.join(conflicts)})" if conflicts else "")))
        try:
            media = self.server.accounts.client(
                int(row["instagram_account_id"]) if row["instagram_account_id"] else None
            ).get_media(str(row["media_id"]))
            found = str(media.get("id")) == str(row["media_id"])
            results.append((found, "Публікацію знайдено через Instagram API"))
        except Exception as exc:
            results.append((False, f"Instagram API недоступний: {str(exc)[:180]}"))
        results.append((self._service_state("instagram-guide-tunnel.service") == "active", "Cloudflare Tunnel працює"))
        items = "".join(f'<div class="service"><span>{"✅" if ok else "❌"} {esc(label)}</span><span class="badge {"on" if ok else "off"}">{"OK" if ok else "Проблема"}</span></div>' for ok, label in results)
        total_ok = all(ok for ok, _ in results)
        headline = "Сценарій готовий до роботи" if total_ok else "Знайдено проблеми — виправте позначені пункти"
        content = f'''<section class="panel"><h1>{esc(row["name"])}</h1><div class="notice {"okbox" if total_ok else "error"}">{headline}</div>{items}<div class="actions"><a class="btn secondary" href="/admin/automation/{row["id"]}">Редагувати</a><a class="btn ghost" href="/admin/">Назад</a></div></section>'''
        self._send(200, self._layout("Перевірка сценарію", content))

    def _library_upload(self, values: dict[str, str], files: dict[str, tuple[str, bytes]]) -> None:
        title = values.get("title", "").strip()
        upload = files.get("file") or files.get("pdf")
        if not title or not upload or not upload[1]:
            self._send(400, self._layout("Помилка", '<div class="notice error">Вкажіть назву та файл.</div>'))
            return
        filename, body = upload
        if len(body) > MAX_FILE_SIZE:
            self._send(400, self._layout("Помилка", '<div class="notice error">Файл перевищує 100 МБ.</div>'))
            return
        valid, error = validate_upload(filename, body)
        if not valid:
            self._send(400, self._layout("Помилка", f'<div class="notice error">{esc(error)}</div>'))
            return
        try:
            folder = normalized_folder(values.get("folder", ""))
        except ValueError as exc:
            self._send(400, self._layout("Помилка", f'<div class="notice error">{esc(exc)}</div>'))
            return
        path = unique_file_path(self.server.guide_dir, folder, filename)
        path.write_bytes(body)
        path.chmod(0o600)
        self.server.store.add_document(title, filename, str(path), len(body), folder, path.name)
        self._redirect("/admin/library?" + urlencode({"ok": "Файл додано в бібліотеку."}))

    def _library_delete(self, values: dict[str, str]) -> None:
        try:
            document_id = int(values.get("id", ""))
        except ValueError:
            self._send(400, "Некоректний ID")
            return
        file_path = self.server.store.delete_document(document_id)
        if not file_path:
            self._send(409, self._layout("Не видалено", '<div class="notice error">Файл використовується автоматизацією або вже відсутній.</div>'))
            return
        path = Path(file_path)
        if path.is_file() and path.resolve().is_relative_to(self.server.guide_dir.resolve()):
            self.server.trash_dir.mkdir(parents=True, exist_ok=True)
            target = unique_file_path(self.server.trash_dir, "", path.name)
            shutil.move(str(path), target)
        self._redirect("/admin/library?" + urlencode({"ok": "Файл видалено з бібліотеки."}))

    def _folder_create(self, values: dict[str, str]) -> None:
        try:
            folder = normalized_folder(values.get("folder", ""))
        except ValueError as exc:
            self._send(400, self._layout("Помилка", f'<div class="notice error">{esc(exc)}</div>'))
            return
        if not folder:
            self._send(400, self._layout("Помилка", '<div class="notice error">Вкажіть назву папки.</div>'))
            return
        path = self.server.guide_dir / folder
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        for parent in [path, *path.parents]:
            if parent == self.server.guide_dir.parent:
                break
            if parent.is_relative_to(self.server.guide_dir):
                parent.chmod(0o700)
        self._redirect("/admin/library?" + urlencode({"ok": f"Створено папку {folder}."}))

    def _library_move(self, values: dict[str, str]) -> None:
        try:
            document = self.server.store.get_document(int(values.get("id", "")))
            folder = normalized_folder(values.get("folder", ""))
        except ValueError as exc:
            self._send(400, self._layout("Помилка", f'<div class="notice error">{esc(exc)}</div>'))
            return
        if document is None:
            self._send(404, "Файл не знайдено")
            return
        old_path = Path(str(document["file_path"]))
        if not old_path.is_file():
            self._send(409, self._layout("Помилка", '<div class="notice error">Фізичний файл відсутній.</div>'))
            return
        source_name = str(document["stored_name"] or document["original_name"] or old_path.name)
        new_path = unique_file_path(self.server.guide_dir, folder, source_name)
        if old_path.resolve().is_relative_to(self.server.guide_dir.resolve()):
            shutil.move(str(old_path), new_path)
        else:
            shutil.copy2(old_path, new_path)
        new_path.chmod(0o600)
        self.server.store.move_document(int(document["id"]), str(new_path), folder, new_path.name)
        self._redirect("/admin/library?" + urlencode({"ok": f"Файл переміщено: {(folder + '/') if folder else ''}{new_path.name}"}))

    def _backup_delete(self, values: dict[str, str]) -> None:
        name = values.get("name", "")
        path = self.server.backup_dir / name
        if not name.endswith((".sqlite3", ".zip")) or path.parent != self.server.backup_dir or not path.is_file():
            self._send(404, "Копію не знайдено")
            return
        path.unlink()
        self._redirect("/admin/backups?" + urlencode({"ok": "Резервну копію видалено."}))

    def _restart_service(self, service: str) -> None:
        allowed = {"instagram-guide-bot.service", "instagram-guide-tunnel.service"}
        if service not in allowed:
            self._send(400, "Недоступна служба")
            return
        def restart() -> None:
            time.sleep(0.5)
            subprocess.run(["systemctl", "--user", "--no-block", "restart", service], timeout=15)
        threading.Thread(target=restart, daemon=True).start()
        self._redirect("/admin/?" + urlencode({"ok": "Команду перезапуску надіслано."}))


def make_admin_server(config: Config, store: Store, meta: MetaClient,
                      accounts: AccountManager | None = None) -> AdminServer:
    return AdminServer((config.admin_host, config.admin_port), config, store, meta, accounts)
