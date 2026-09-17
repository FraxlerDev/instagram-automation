import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bot.accounts import AccountError, AccountManager, TokenVault
from bot.admin import AdminHandler
from bot.config import Config
from bot.meta import MetaClient
from bot.processor import Processor
from bot.store import Store


def config(root: Path) -> Config:
    return Config(
        access_token="first-secret-token", account_id="ig-first", app_secret="app-secret",
        verify_token="verify", public_base_url="https://bot.example.test",
        allowed_media_ids=frozenset(), trigger_keywords=frozenset(), confirmation_words=frozenset(),
        public_reply_text="public", initial_dm_text="private", guide_message_text="file",
        graph_api_version="v26.0", host="127.0.0.1", port=0, admin_port=0,
        guide_pdf_path=root / "guide.pdf", db_path=root / "bot.sqlite3", signature_required=True,
        instagram_app_id="123456789",
    )


class FakeMeta:
    def __init__(self, recipient):
        self.recipient = recipient
        self.public = []
        self.private = []

    def reply_to_comment(self, comment_id, message):
        self.public.append((comment_id, message))

    def send_private_reply(self, comment_id, message):
        self.private.append((comment_id, message))
        return self.recipient


class AccountTests(unittest.TestCase):
    def test_tokens_are_encrypted_and_oauth_state_is_one_time(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            self.assertNotIn(cfg.access_token, str(account["access_token_encrypted"]))
            self.assertEqual(manager.vault.decrypt(str(account["access_token_encrypted"])), cfg.access_token)
            url = manager.authorization_url()
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query["client_id"], [cfg.instagram_app_id])
            self.assertIn("instagram_business_manage_messages", query["scope"][0])
            import hashlib
            state_hash = hashlib.sha256(query["state"][0].encode()).hexdigest()
            self.assertTrue(store.consume_oauth_state(state_hash, 0))
            self.assertFalse(store.consume_oauth_state(state_hash, 0))

    def test_follow_insight_response_shapes_are_parsed(self):
        payload = {"data": [{"name": "follows_and_unfollows", "values": [{"value": {
            "follows": 12, "unfollows": 4,
        }}]}]}
        self.assertEqual(AccountManager._follow_counts(payload), (12, 4))
        breakdown = {"data": [{"total_value": {"breakdowns": [{"results": [
            {"dimension_values": ["follow"], "value": 9},
            {"dimension_values": ["unfollow"], "value": 3},
        ]}]}}]}
        self.assertEqual(AccountManager._follow_counts(breakdown), (9, 3))

    def test_analytics_page_shows_follower_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            account_id = int(account["id"])
            store.update_instagram_account_profile(account_id, "metrics_account")
            store.save_follower_snapshot(account_id, "2026-09-11", 1250, 18, 5)
            handler = object.__new__(AdminHandler)
            handler.path = "/admin/analytics"
            handler.server = type("Server", (), {"store": store})()
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content: content
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._analytics()
            page = response[0][1]
            self.assertIn("@metrics_account", page)
            self.assertIn("1250", page)
            self.assertIn("Нові за день", page)
            self.assertIn("Втрачені за день", page)
            self.assertIn("+13", page)
            self.assertIn("Підтверджені підписки", page)

    def test_comment_webhook_uses_automation_account(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = config(root)
            store = Store(cfg.db_path)
            vault = TokenVault(cfg.app_secret)
            first_id = store.bootstrap_instagram_account("ig-first", vault.encrypt("one"), "first")
            second_id = store.save_instagram_account("ig-second", "second", vault.encrypt("two"), None, "")
            pdf = root / "guide.pdf"
            pdf.write_bytes(b"%PDF-test")
            for account_id, media in ((first_id, "media-one"), (second_id, "media-two")):
                store.save_automation({
                    "name": media, "media_id": media, "media_permalink": "", "trigger_keywords": "гайд",
                    "confirmation_words": "готово", "public_reply_text": media,
                    "initial_dm_text": media, "guide_message_text": "file", "pdf_path": str(pdf),
                    "enabled": 1, "instagram_account_id": account_id,
                })
            clients = {first_id: FakeMeta("person-one"), second_id: FakeMeta("person-two")}
            processor = Processor(cfg, store, clients[first_id], account_client=lambda account_id, _ig: clients[account_id])
            processor.process({"object": "instagram", "entry": [{"id": "ig-second", "field": "comments", "value": {
                "id": "comment-two", "text": "гайд", "media": {"id": "media-two"},
            }}]})
            self.assertEqual(clients[first_id].public, [])
            self.assertEqual(clients[second_id].public, [("comment-two", "media-two")])
            self.assertEqual(store.recipient_context("person-two")["instagram_account_id"], second_id)

    def test_accounts_page_never_renders_plain_token(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            handler = object.__new__(AdminHandler)
            handler.path = "/admin/accounts"
            handler.server = type("Server", (), {"store": store, "accounts": manager, "config": cfg})()
            handler._csrf = lambda: "csrf"
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._accounts()
            self.assertEqual(response[0][0], 200)
            self.assertIn("Instagram-акаунти", response[0][1])
            self.assertIn("зашифровано", response[0][1])
            self.assertNotIn(cfg.access_token, response[0][1])

    def test_account_profile_picture_is_saved_and_rendered_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            store.update_instagram_account_profile(
                int(account["id"]), "fraxler_test", "https://cdn.example.test/profile.jpg"
            )
            account = store.get_instagram_account(int(account["id"]))
            card = AdminHandler._instagram_identity_html(account)
            self.assertIn("@fraxler_test", card)
            self.assertIn('src="https://cdn.example.test/profile.jpg"', card)
            store.update_instagram_account_profile(
                int(account["id"]), "fraxler_test", "javascript:alert(1)"
            )
            unsafe_card = AdminHandler._instagram_identity_html(
                store.get_instagram_account(int(account["id"]))
            )
            self.assertNotIn("javascript:", unsafe_card)
            self.assertIn("fallback", unsafe_card)

    def test_dashboard_uses_account_linked_to_each_automation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = config(root)
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            account_id = int(account["id"])
            store.update_instagram_account_profile(
                account_id, "linked_account", "https://cdn.example.test/linked.jpg"
            )
            pdf = root / "guide.pdf"
            pdf.write_bytes(b"%PDF-test")
            store.save_automation({
                "name": "Пов'язана автоматизація", "media_id": "media-one",
                "media_permalink": "", "trigger_keywords": "гайд",
                "confirmation_words": "готово", "public_reply_text": "public",
                "initial_dm_text": "private", "guide_message_text": "file",
                "pdf_path": str(pdf), "enabled": 1, "instagram_account_id": account_id,
            })
            handler = object.__new__(AdminHandler)
            handler.path = "/admin/"
            handler.server = type("Server", (), {"store": store})()
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content: content
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._dashboard()
            self.assertEqual(response[0][0], 200)
            self.assertIn("Пов&#x27;язана автоматизація", response[0][1])
            self.assertIn("@linked_account", response[0][1])
            self.assertIn("https://cdn.example.test/linked.jpg", response[0][1])

    def test_library_filters_files_and_shows_accounts_using_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = config(root)
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            first = store.default_instagram_account()
            first_id = int(first["id"])
            store.update_instagram_account_profile(first_id, "first_account")
            second_id = store.save_instagram_account("ig-second", "second_account", "encrypted", None, "")
            first_file = root / "first.pdf"
            second_file = root / "second.pdf"
            first_file.write_bytes(b"%PDF-first")
            second_file.write_bytes(b"%PDF-second")
            for account_id, file_path, media in (
                (first_id, first_file, "media-first"),
                (second_id, second_file, "media-second"),
            ):
                store.ensure_document(str(file_path), media)
                store.save_automation({
                    "name": media, "media_id": media, "media_permalink": "",
                    "trigger_keywords": "гайд", "confirmation_words": "готово",
                    "public_reply_text": "public", "initial_dm_text": "private",
                    "guide_message_text": "file", "pdf_path": str(file_path),
                    "enabled": 1, "instagram_account_id": account_id,
                })
            handler = object.__new__(AdminHandler)
            handler.path = f"/admin/library?account={first_id}"
            handler.server = type("Server", (), {"store": store, "guide_dir": root})()
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content: content
            handler._folder_options = lambda _selected="": '<option value="">Головна папка</option>'
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._library()
            self.assertIn("media-first", response[0][1])
            self.assertIn("@first_account", response[0][1])
            self.assertNotIn("media-second</h3>", response[0][1])

    def test_users_page_filters_and_labels_destination_account(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            first = store.default_instagram_account()
            first_id = int(first["id"])
            store.update_instagram_account_profile(first_id, "first_account")
            second_id = store.save_instagram_account("ig-second", "second_account", "encrypted", None, "")
            store.log_direct("person-first", "in", "instagram", "hello", instagram_account_id=first_id)
            store.log_direct("person-second", "in", "instagram", "hello", instagram_account_id=second_id)
            handler = object.__new__(AdminHandler)
            handler.path = f"/admin/users?account={first_id}"
            handler.server = type("Server", (), {"store": store})()
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content: content
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._users()
            self.assertIn("person-first", response[0][1])
            self.assertIn("@first_account", response[0][1])
            self.assertNotIn("person-second", response[0][1])

    def test_meta_usage_headers_are_captured_and_stored(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            account_id = int(account["id"])
            client = MetaClient(
                cfg, usage_callback=lambda usage: store.record_api_usage(account_id, usage)
            )
            client._capture_usage({
                "x-app-usage": '{"call_volume":37,"cpu_time":12,"total_time":9}',
                "x-business-use-case-usage": '{"ig-first":[{"call_count":44}]}'
            })
            store.update_publishing_usage(account_id, 8, 100, 86400)
            usage = store.get_api_usage(account_id)
            self.assertEqual(json.loads(usage["app_usage_json"])["call_volume"], 37)
            self.assertEqual(json.loads(usage["business_usage_json"])["ig-first"][0]["call_count"], 44)
            self.assertEqual(usage["publishing_usage"], 8)

    def test_api_usage_page_shows_remaining_limits_per_account(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            account = store.default_instagram_account()
            account_id = int(account["id"])
            store.update_instagram_account_profile(account_id, "limits_account")
            store.record_api_usage(account_id, {
                "app": {"call_volume": 84, "cpu_time": 18, "total_time": 7},
                "business": {"ig-first": [{"call_count": 31}]},
            })
            store.update_publishing_usage(account_id, 12, 100, 86400)
            handler = object.__new__(AdminHandler)
            handler.path = "/admin/api-usage"
            handler.server = type("Server", (), {"store": store})()
            handler._csrf = lambda: "csrf"
            handler._layout = lambda _title, content: content
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._api_usage()
            page = response[0][1]
            self.assertIn("@limits_account", page)
            self.assertIn("84%", page)
            self.assertIn("Залишок приблизно 16%", page)
            self.assertIn("12 / 100", page)
            self.assertIn("Наближення до ліміту", page)

    def test_help_page_contains_complete_account_guide(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            store = Store(cfg.db_path)
            manager = AccountManager(cfg, store)
            handler = object.__new__(AdminHandler)
            handler.path = "/admin/help"
            handler.server = type("Server", (), {"store": store, "accounts": manager, "config": cfg})()
            handler._csrf = lambda: "csrf"
            response = []
            handler._send = lambda status, body: response.append((status, body))
            handler._help()
            page = response[0][1]
            self.assertEqual(response[0][0], 200)
            self.assertIn("Як додати Instagram-акаунт", page)
            self.assertIn("Instagram Tester", page)
            self.assertIn("Advanced Access", page)
            self.assertIn(manager.callback_url, page)

    def test_long_token_exchange_retries_post_when_meta_rejects_get(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = AccountManager(config(Path(temp)), Store(Path(temp) / "bot.sqlite3"))
            calls = []
            def request(url, values, method="GET"):
                calls.append((url, values, method))
                if method == "GET":
                    raise AccountError('Instagram OAuth HTTP 400: "Unsupported request - method type: get"')
                return {"access_token": "long", "expires_in": 100}
            manager._request_json = request
            result = manager._exchange_long_token("short")
            self.assertEqual(result["access_token"], "long")
            self.assertEqual([call[2] for call in calls], ["GET", "POST"])
            self.assertEqual(calls[1][1]["access_token"], "short")

    def test_long_token_exchange_explains_missing_tester_or_advanced_access(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = AccountManager(config(Path(temp)), Store(Path(temp) / "bot.sqlite3"))
            manager._request_json = lambda _url, _values, method="GET": (_ for _ in ()).throw(
                AccountError(f'Instagram OAuth HTTP 400: "Unsupported request - method type: {method.casefold()}"')
            )
            with self.assertRaisesRegex(AccountError, "Instagram Tester"):
                manager._exchange_long_token("short")


if __name__ == "__main__":
    unittest.main()
