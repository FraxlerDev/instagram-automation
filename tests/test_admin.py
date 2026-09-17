import http.client
import ipaddress
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from bot.admin import AdminHandler, AdminServer, CSS, password_hash, password_ok
from bot.config import Config
from bot.store import Store


class FakeMeta:
    def list_media(self, limit=50):
        return []


def config(root: Path) -> Config:
    return Config(
        access_token="secret", account_id="account", app_secret="secret", verify_token="verify",
        public_base_url="https://example.test", allowed_media_ids=frozenset({"media-1"}),
        trigger_keywords=frozenset({"гайд"}), confirmation_words=frozenset({"готово"}),
        public_reply_text="public", initial_dm_text="private", guide_message_text="file",
        graph_api_version="v26.0", host="127.0.0.1", port=0, admin_port=0,
        guide_pdf_path=root / "guide.pdf", db_path=root / "bot.sqlite3", signature_required=True,
    )


class AdminTests(unittest.TestCase):
    def test_password_hash(self):
        stored = password_hash("довгий-пароль")
        self.assertTrue(password_ok("довгий-пароль", stored))
        self.assertFalse(password_ok("інший-пароль", stored))

    def test_first_run_setup_and_dashboard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = config(root)
            cfg.guide_pdf_path.write_bytes(b"%PDF-test")
            store = Store(cfg.db_path)
            store.ensure_default_automations(
                cfg.allowed_media_ids, cfg.trigger_keywords, cfg.confirmation_words,
                cfg.public_reply_text, cfg.initial_dm_text, cfg.guide_message_text, cfg.guide_pdf_path,
            )
            try:
                server = AdminServer(("127.0.0.1", 0), cfg, store, FakeMeta())
            except PermissionError:
                self.skipTest("Socket creation is disabled in the test sandbox")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                body = urlencode({"password": "пароль-довший-10", "confirm": "пароль-довший-10"})
                connection.request("POST", "/admin/setup", body, {"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 303)
                cookie = response.getheader("Set-Cookie").split(";", 1)[0]
                connection.request("GET", "/admin/", headers={"Cookie": cookie})
                response = connection.getresponse()
                page = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertIn("Гайд — поточна автоматизація", page)
            finally:
                server.shutdown()
                server.server_close()

    def test_backup_bundle_contains_database_and_pdf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "guide.pdf"
            pdf.write_bytes(b"%PDF-test")
            store = Store(root / "bot.sqlite3")
            store.ensure_document(str(pdf), "Гайд")
            server = object.__new__(AdminServer)
            server.store = store
            server.backup_dir = root / "backups"
            server.backup_dir.mkdir()
            server._backup_lock = threading.Lock()
            archive_path = server.create_backup_bundle("test")
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIn("database.sqlite3", archive.namelist())
                self.assertTrue(any(name.startswith("documents/1-") and name.endswith(".pdf") for name in archive.namelist()))
                self.assertIn("manifest.json", archive.namelist())

    def test_light_theme_and_bottom_right_toast_are_rendered(self):
        handler = object.__new__(AdminHandler)
        handler.path = "/admin/?ok=Автоматизацію+відновлено+з+архіву."
        handler._csrf = lambda: "csrf-test"
        page = handler._layout("Тест", "<p>Вміст</p>")
        self.assertIn('class="toast"', page)
        self.assertIn("Автоматизацію відновлено з архіву.", page)
        self.assertIn("localStorage.getItem('fia-theme')", page)
        self.assertIn("html[data-theme=\"light\"]", CSS)
        self.assertIn("right:22px;bottom:22px", CSS)

    def test_attachment_renderer_rejects_unsafe_url(self):
        html = AdminHandler._attachment_html({"type": "image", "url": "javascript:alert(1)", "name": "Фото"})
        self.assertIn("URL недоступний", html)
        self.assertNotIn("javascript:", html)

    def test_library_accepts_image_and_transliterates_its_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "bot.sqlite3")
            handler = object.__new__(AdminHandler)
            handler.server = SimpleNamespace(store=store, guide_dir=root / "library")
            handler.path = "/admin/library"
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content, *_args: content
            redirects = []
            handler._redirect = redirects.append
            handler._send = lambda *_args: self.fail("Valid PNG upload was rejected")
            handler._library_upload(
                {"title": "Обкладинка", "folder": "Фото/Книги"},
                {"file": ("Моя обкладинка.PNG", b"\x89PNG\r\n\x1a\ndata")},
            )
            document = store.list_documents()[0]
            self.assertEqual(document["stored_name"], "moia-obkladynka.png")
            self.assertEqual(document["folder"], "foto/knyhy")
            self.assertTrue(Path(document["file_path"]).is_file())
            self.assertIn("ok=", redirects[0])
            handler.path = "/admin/library"
            handler._folder_options = lambda _selected="": '<option value="">Головна папка</option>'
            rendered = []
            handler._send = lambda status, body: rendered.append((status, body))
            handler._library()
            self.assertIn(f'/admin/library/preview/{document["id"]}', rendered[0][1])
            self.assertIn('class="library-preview"', rendered[0][1])

    def test_admin_access_is_limited_to_configured_lan(self):
        handler = object.__new__(AdminHandler)
        handler.server = SimpleNamespace(allowed_networks=(
            ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("192.168.0.0/24"),
        ))
        handler.client_address = ("192.168.0.42", 50000)
        self.assertTrue(handler._client_allowed())
        handler.client_address = ("203.0.113.10", 50000)
        self.assertFalse(handler._client_allowed())

    def test_automation_form_saves_rules_and_follow_requirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "guide.pdf"
            pdf.write_bytes(b"%PDF-test")
            store = Store(root / "bot.sqlite3")
            document_id = store.add_document("Гайд", "guide.pdf", str(pdf), pdf.stat().st_size)
            handler = object.__new__(AdminHandler)
            handler.server = SimpleNamespace(store=store, guide_dir=root, meta=FakeMeta())
            redirects = []
            handler._redirect = redirects.append
            handler._automation_form = lambda *args, **kwargs: self.fail(f"Unexpected form error: {args}")
            handler._save_automation({
                "name": "Сценарій", "media_id": "media-1", "media_permalink": "",
                "trigger_keywords": "Гайд", "confirmation_words": "Готово",
                "public_reply_text": "Відповідь", "initial_dm_text": "Direct",
                "guide_message_text": "PDF", "document_id": str(document_id), "enabled": "on",
                "require_follow": "on", "follow_required_message": "Спершу підпишіться",
                "rule_count": "1", "rule_state_0": "waiting", "rule_keywords_0": "Так, Цікавить",
                "rule_reply_0": "Оберіть тему", "rule_next_0": "topic", "mode": "publish",
            }, {})
            saved = store.get_automation(1)
            rules = json.loads(saved["conversation_rules"])
            self.assertEqual(rules[0]["keywords"], "так,цікавить")
            self.assertEqual(rules[0]["next_state"], "topic")
            self.assertEqual(saved["require_follow"], 1)
            self.assertIn("ok=", redirects[0])


if __name__ == "__main__":
    unittest.main()
