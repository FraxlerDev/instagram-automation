import sqlite3
import tempfile
import unittest
from pathlib import Path

from bot.store import Store


class StoreFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root / "guide.pdf"
        self.pdf.write_bytes(b"%PDF-test")
        self.store = Store(self.root / "bot.sqlite3")
        self.automation_id = self.store.save_automation({
            "name": "Тест", "media_id": "media-1", "media_permalink": "https://example.test/p/1",
            "trigger_keywords": "гайд", "confirmation_words": "готово",
            "public_reply_text": "public", "initial_dm_text": "private",
            "guide_message_text": "file", "pdf_path": str(self.pdf), "enabled": 1,
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_history_statuses_and_analytics(self):
        self.store.ensure_comment("comment-1", "media-1", "reader", self.automation_id, "Хочу гайд")
        self.store.mark_public_done("comment-1")
        self.store.mark_private_done("comment-1", "person-1", self.automation_id)
        self.store.mark_fulfilled("person-1")
        self.store.ensure_comment("comment-2", "media-1", "reader", self.automation_id, "Ще раз")
        self.store.mark_private_done("comment-2", "person-1", self.automation_id)
        history = self.store.history(status="fulfilled")
        self.assertEqual(history[0]["comment_text"], "Хочу гайд")
        self.assertIsNotNone(history[0]["fulfilled_at"])
        summary, per = self.store.analytics()
        self.assertEqual(summary["comments"], 2)
        self.assertEqual(summary["fulfilled"], 1)
        self.assertEqual(per[0]["fulfilled"], 1)

    def test_follower_snapshots_and_confirmed_automation_conversion(self):
        self.store.save_follower_snapshot(7, "2026-09-10", 100, 5, 2)
        self.store.save_follower_snapshot(7, "2026-09-11", 104, 7, 3)
        snapshot = self.store.latest_follower_snapshot(7)
        self.assertEqual(snapshot["followers_count"], 104)
        self.assertEqual(snapshot["new_followers"], 7)
        self.assertEqual(snapshot["lost_followers"], 3)
        self.assertEqual(snapshot["net_change"], 4)

        self.store.record_follow_baseline(self.automation_id, "new-reader", 7, False)
        self.assertTrue(self.store.record_follow_conversion(
            self.automation_id, "new-reader", 7, True
        ))
        self.assertFalse(self.store.record_follow_conversion(
            self.automation_id, "new-reader", 7, True
        ))
        self.store.record_follow_baseline(self.automation_id, "old-reader", 7, True)
        self.assertFalse(self.store.record_follow_conversion(
            self.automation_id, "old-reader", 7, True
        ))
        summary, per = self.store.analytics()
        self.assertEqual(summary["confirmed_follows"], 1)
        self.assertEqual(per[0]["confirmed_follows"], 1)

    def test_duplicate_and_document_library(self):
        document_id = self.store.ensure_document(str(self.pdf), "Посібник")
        self.assertIsNotNone(document_id)
        duplicate_id = self.store.duplicate_automation(self.automation_id)
        duplicate = self.store.get_automation(duplicate_id)
        self.assertEqual(duplicate["enabled"], 0)
        self.assertEqual(duplicate["pdf_path"], str(self.pdf))
        documents = self.store.list_documents()
        self.assertEqual(documents[0]["use_count"], 2)
        self.assertIsNone(self.store.delete_document(document_id))

    def test_sqlite_backup_is_consistent(self):
        backup = self.store.create_backup(self.root / "backups", "test")
        db = sqlite3.connect(backup)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM automations").fetchone()[0], 1)
        finally:
            db.close()
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_retry_queue_user_handoff_and_messages(self):
        self.store.ensure_comment("comment-1", "media-1", "reader", self.automation_id, "гайд")
        self.store.mark_private_done("comment-1", "person-1", self.automation_id)
        self.store.log_direct("person-1", "in", "instagram", "Готово", "mid-1")
        user = self.store.get_user("person-1")
        self.assertEqual(user["username"], "reader")
        self.store.update_user("person-1", tags="лід", notes="Передзвонити", manual_mode=True)
        self.assertTrue(self.store.user_manual_mode("person-1"))
        self.store.schedule_retry(
            "final:mid-1", "final_message", {"sender_id": "person-1"},
            self.automation_id, "person-1", "temporary",
        )
        retry = self.store.due_retries(0)[0]
        self.store.fail_retry(retry["id"], 1, 100, "again")
        self.assertEqual(len(self.store.due_retries(99)), 0)
        self.store.retry_now(retry["id"])
        self.assertEqual(len(self.store.due_retries(0)), 1)
        self.store.delete_user_data("person-1")
        self.assertIsNone(self.store.get_user("person-1"))
        self.assertEqual(self.store.messages_for_user("person-1"), [])

    def test_drafts_and_versions(self):
        automation = self.store.get_automation(self.automation_id)
        values = {key: automation[key] for key in (
            "name", "media_id", "media_permalink", "trigger_keywords", "confirmation_words",
            "public_reply_text", "initial_dm_text", "guide_message_text", "pdf_path", "enabled",
        )}
        values["public_reply_text"] = "Нова чернетка"
        version_id = self.store.save_version(self.automation_id, "draft", values)
        version = self.store.get_version(version_id)
        self.assertEqual(version["status"], "draft")
        self.assertEqual(len(self.store.list_versions(self.automation_id)), 1)


if __name__ == "__main__":
    unittest.main()
