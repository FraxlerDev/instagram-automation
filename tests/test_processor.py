import tempfile
import threading
import unittest
from pathlib import Path

from bot.config import Config
from bot.processor import Processor
from bot.store import Store


class FakeMeta:
    def __init__(self):
        self.public = []
        self.private = []
        self.direct = []
        self.follows = True

    def reply_to_comment(self, comment_id, message):
        self.public.append((comment_id, message))
        return "reply-1"

    def send_private_reply(self, comment_id, message):
        self.private.append((comment_id, message))
        return "person-1"

    def send_text(self, recipient_id, message):
        self.direct.append((recipient_id, message))
        return "message-2"

    def get_user_profile(self, recipient_id):
        return {
            "id": recipient_id,
            "username": "reader",
            "profile_pic": "https://example.test/avatar.jpg",
            "is_user_follow_business": self.follows,
        }


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.sent = threading.Event()

    def enabled(self):
        return True

    def send(self, title, detail):
        self.messages.append((title, detail))
        self.sent.set()
        return True


def config(root: Path) -> Config:
    return Config(
        access_token="secret",
        account_id="account-1",
        app_secret="app-secret",
        verify_token="verify",
        public_base_url="https://example.test",
        allowed_media_ids=frozenset({"media-1"}),
        trigger_keywords=frozenset({"гайд", "гайду"}),
        confirmation_words=frozenset({"готово"}),
        public_reply_text="public",
        initial_dm_text="private",
        guide_message_text="file",
        graph_api_version="v26.0",
        host="127.0.0.1",
        port=8000,
        admin_port=8795,
        guide_pdf_path=root / "guide.pdf",
        db_path=root / "bot.sqlite3",
        signature_required=True,
    )


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = config(root)
        self.meta = FakeMeta()
        self.store = Store(self.config.db_path)
        self.store.ensure_default_automations(
            self.config.allowed_media_ids,
            self.config.trigger_keywords,
            self.config.confirmation_words,
            self.config.public_reply_text,
            self.config.initial_dm_text,
            self.config.guide_message_text,
            self.config.guide_pdf_path,
        )
        self.processor = Processor(self.config, self.store, self.meta)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_flow_and_idempotency(self):
        comment = {
            "object": "instagram",
            "entry": [{
                "field": "comments",
                "value": {
                    "id": "comment-1",
                    "text": "Можна гайд?",
                    "from": {"username": "reader"},
                    "media": {"id": "media-1"},
                },
            }],
        }
        self.processor.process(comment)
        self.processor.process(comment)
        self.assertEqual(len(self.meta.public), 1)
        self.assertEqual(len(self.meta.private), 1)

        ready = {
            "object": "instagram",
            "entry": [{"messaging": [{
                "sender": {"id": "person-1"},
                "recipient": {"id": "account-1"},
                "message": {"mid": "message-1", "text": "ГОТОВО, дякую"},
            }]}],
        }
        self.processor.process(ready)
        self.processor.process(ready)
        self.assertEqual(len(self.meta.direct), 1)
        self.assertIn("https://example.test/files/1/guide.pdf", self.meta.direct[0][1])

    def test_ignores_unselected_media(self):
        self.processor.process({
            "object": "instagram",
            "entry": [{
                "field": "comments",
                "value": {
                    "id": "comment-2",
                    "text": "гайд",
                    "media": {"id": "different-media"},
                },
            }],
        })
        self.assertEqual(self.meta.public, [])
        self.assertEqual(self.meta.private, [])

    def test_telegram_receives_one_message_per_comment_and_auto_reply_only_on_match(self):
        notifier = FakeNotifier()
        self.processor.notifier = notifier
        no_match = {
            "object": "instagram",
            "entry": [{
                "field": "comments",
                "value": {
                    "id": "comment-without-trigger",
                    "text": "Дуже корисна публікація",
                    "from": {"username": "reader"},
                    "media": {"id": "media-1"},
                },
            }],
        }
        self.processor.process(no_match)
        self.assertTrue(notifier.sent.wait(1))
        self.processor.process(no_match)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("Дуже корисна публікація", notifier.messages[0][1])
        self.assertNotIn("🤖 Автоматична відповідь", notifier.messages[0][1])
        self.assertNotIn("⚙️ Автоматизація публікації", notifier.messages[0][1])
        self.assertIn("🎯 Збіг сценарію: ні — автоматична відповідь не запускається", notifier.messages[0][1])
        notifier.sent.clear()
        payload = {
            "object": "instagram",
            "entry": [{
                "field": "comments",
                "value": {
                    "id": "comment-with-trigger",
                    "text": "Хочу гайд",
                    "from": {"username": "reader"},
                    "media": {"id": "media-1"},
                },
            }],
        }
        self.processor.process(payload)
        self.assertTrue(notifier.sent.wait(1))
        self.processor.process(payload)
        self.assertEqual(len(notifier.messages), 2)
        title, detail = notifier.messages[1]
        self.assertIn("💬", title)
        self.assertIn("@reader", detail)
        self.assertIn("Хочу гайд", detail)
        self.assertIn("⚙️ Автоматизація публікації:", detail)
        self.assertIn("🤖 Автоматична відповідь: public", detail)
        self.assertNotIn("🎯 Збіг сценарію: ні", detail)
        self.assertEqual(len(self.meta.public), 1)
        self.assertEqual(len(self.meta.private), 1)

    def test_own_public_reply_is_ignored_by_telegram_and_automation(self):
        account_id = self.store.bootstrap_instagram_account("account-1", "encrypted", "business_account")
        notifier = FakeNotifier()
        self.processor.notifier = notifier
        self.processor.process({
            "object": "instagram",
            "entry": [{
                "id": "account-1",
                "field": "comments",
                "value": {
                    "id": "own-reply-comment",
                    "text": "public",
                    "from": {"id": "account-1", "username": "business_account"},
                    "media": {"id": "media-1"},
                },
            }],
        })
        self.assertIsNotNone(account_id)
        self.assertEqual(notifier.messages, [])
        self.assertEqual(self.meta.public, [])
        self.assertEqual(self.meta.private, [])

    def test_accepts_scoped_messaging_account_ids(self):
        self.processor.process({
            "object": "instagram",
            "entry": [{
                "field": "comments",
                "value": {
                    "id": "comment-scoped",
                    "text": "гайд",
                    "from": {"username": "reader"},
                    "media": {"id": "media-1"},
                },
            }],
        })
        self.processor.process({
            "object": "instagram",
            "entry": [{
                "id": "different-entry-scoped-id",
                "messaging": [{
                    "sender": {"id": "person-1"},
                    "recipient": {"id": "different-scoped-id"},
                    "message": {"mid": "message-scoped", "text": "Готово"},
                }],
            }],
        })
        self.assertEqual(len(self.meta.direct), 1)

    def test_uses_separate_configuration_for_another_post(self):
        second_pdf = Path(self.temp.name) / "second.pdf"
        second_pdf.write_bytes(b"%PDF-second")
        self.store.save_automation({
            "name": "Чекліст",
            "media_id": "media-2",
            "media_permalink": "https://instagram.test/p/second",
            "trigger_keywords": "чекліст",
            "confirmation_words": "хочу",
            "public_reply_text": "second-public",
            "initial_dm_text": "second-private",
            "guide_message_text": "second-file",
            "pdf_path": str(second_pdf),
            "enabled": 1,
        })
        self.processor.process({
            "object": "instagram",
            "entry": [{"field": "comments", "value": {
                "id": "comment-3", "text": "Чекліст", "from": {"username": "reader"},
                "media": {"id": "media-2"},
            }}],
        })
        self.assertEqual(self.meta.public[-1][1], "second-public")
        self.assertEqual(self.meta.private[-1][1], "second-private")
        self.processor.process({
            "object": "instagram",
            "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "message-3", "text": "ХОЧУ"},
            }]}],
        })
        self.assertIn("second-file", self.meta.direct[-1][1])
        self.assertIn("/files/2/second.pdf", self.meta.direct[-1][1])

    def test_manual_handoff_stops_automatic_final_message(self):
        self.processor.process({
            "object": "instagram", "entry": [{"field": "comments", "value": {
                "id": "comment-manual", "text": "гайд", "from": {"username": "reader"},
                "media": {"id": "media-1"},
            }}],
        })
        self.store.update_user("person-1", tags="", notes="", manual_mode=True)
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "manual-mid", "text": "ГОТОВО"},
            }]}],
        })
        self.assertEqual(self.meta.direct, [])
        self.assertEqual(self.store.message_state("manual-mid"), "manual")
        self.assertEqual(self.store.messages_for_user("person-1")[-1]["text"], "ГОТОВО")

    def test_failed_private_reply_is_queued_and_retried(self):
        original = self.meta.send_private_reply
        self.meta.send_private_reply = lambda *_: (_ for _ in ()).throw(RuntimeError("temporary"))
        self.processor.process({
            "object": "instagram", "entry": [{"field": "comments", "value": {
                "id": "comment-retry", "text": "гайд", "from": {"username": "reader"},
                "media": {"id": "media-1"},
            }}],
        })
        retries = self.store.due_retries(0)
        self.assertEqual(retries[0]["kind"], "private_reply")
        self.meta.send_private_reply = original
        self.processor._run_retry(retries[0])
        self.assertEqual(self.store.list_retries(False), [])
        self.assertEqual(self.store.history()[0]["private_done"], 1)

    def test_multi_step_branch_reaches_pdf(self):
        automation = self.store.get_automation(1)
        values = dict(automation)
        values["conversation_rules"] = """[
          {"state":"waiting","keywords":"так","reply_text":"Оберіть тему: книги або бізнес","next_state":"topic","send_pdf":false},
          {"state":"topic","keywords":"книги","reply_text":"Ваш книжковий гайд","next_state":"fulfilled","send_pdf":true}
        ]"""
        self.store.save_automation(values, 1)
        self.processor.process({
            "object": "instagram", "entry": [{"field": "comments", "value": {
                "id": "comment-branch", "text": "гайд", "from": {"username": "reader"},
                "media": {"id": "media-1"},
            }}],
        })
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "branch-1", "text": "так"},
            }]}],
        })
        self.assertIn("Оберіть тему", self.meta.direct[-1][1])
        self.assertEqual(self.store.recipient_context("person-1")["recipient_state"], "topic")
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "branch-2", "text": "книги"},
            }]}],
        })
        self.assertIn("Ваш книжковий гайд", self.meta.direct[-1][1])
        self.assertIn("/files/1/guide.pdf", self.meta.direct[-1][1])
        self.assertEqual(self.store.recipient_context("person-1")["recipient_state"], "fulfilled")

    def test_follow_is_checked_before_pdf(self):
        automation = self.store.get_automation(1)
        values = dict(automation)
        values["require_follow"] = 1
        values["follow_required_message"] = "Спершу підпишіться"
        self.store.save_automation(values, 1)
        self.processor.process({
            "object": "instagram", "entry": [{"field": "comments", "value": {
                "id": "comment-follow", "text": "гайд", "from": {"username": "reader"},
                "media": {"id": "media-1"},
            }}],
        })
        self.meta.follows = False
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "follow-1", "text": "готово"},
            }]}],
        })
        self.assertEqual(self.meta.direct[-1][1], "Спершу підпишіться")
        self.assertEqual(self.store.get_user("person-1")["follows_business"], 0)
        self.assertEqual(self.store.recipient_context("person-1")["recipient_state"], "waiting")
        self.meta.follows = True
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"}, "message": {"mid": "follow-2", "text": "готово"},
            }]}],
        })
        self.assertIn("/files/1/guide.pdf", self.meta.direct[-1][1])
        self.assertEqual(self.store.get_user("person-1")["follows_business"], 1)

    def test_new_follow_is_attributed_to_the_automation(self):
        self.meta.follows = False
        self.processor.process({
            "object": "instagram", "entry": [{"field": "comments", "value": {
                "id": "comment-conversion", "text": "гайд", "from": {"username": "reader"},
                "media": {"id": "media-1"},
            }}],
        })
        self.meta.follows = True
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "person-1"},
                "message": {"mid": "conversion-message", "text": "готово"},
            }]}],
        })
        summary, per = self.store.analytics()
        self.assertEqual(summary["confirmed_follows"], 1)
        self.assertEqual(per[0]["confirmed_follows"], 1)

    def test_inbound_direct_attachment_is_saved(self):
        self.processor.process({
            "object": "instagram", "entry": [{"messaging": [{
                "sender": {"id": "attachment-user"},
                "message": {"mid": "attachment-1", "attachments": [{
                    "type": "image", "payload": {"url": "https://example.test/photo.jpg"},
                }]},
            }]}],
        })
        message = self.store.messages_for_user("attachment-user")[0]
        self.assertIn("photo.jpg", message["attachments"])
        self.assertEqual(self.store.message_state("attachment-1"), "ignored")


if __name__ == "__main__":
    unittest.main()
