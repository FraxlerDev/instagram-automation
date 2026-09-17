import tempfile
import unittest
from pathlib import Path

from bot.monitor import HealthMonitor
from bot.store import Store


class CapturingNotifier:
    def __init__(self):
        self.messages = []

    def send(self, title, detail):
        self.messages.append((title, detail))
        return True


class MonitorNotificationTests(unittest.TestCase):
    def test_overall_status_uses_emojis_and_only_reports_transitions(self):
        with tempfile.TemporaryDirectory() as temp:
            notifier = CapturingNotifier()
            monitor = HealthMonitor(Store(Path(temp) / "bot.sqlite3"), None, notifier, "https://example.test")
            monitor._notify_overall([])
            monitor._notify_overall([])
            monitor._notify_overall(["Cloudflare Tunnel: inactive"])
            monitor._notify_overall(["Tunnel", "Webhook", "Instagram API"])
            monitor._notify_overall([])
            titles = [title for title, _detail in notifier.messages]
            self.assertEqual(len(titles), 4)
            self.assertTrue(titles[0].startswith("✅"))
            self.assertTrue(titles[1].startswith("🟠"))
            self.assertTrue(titles[2].startswith("🔴"))
            self.assertEqual(titles[3], "✅ Схему повністю відновлено")


if __name__ == "__main__":
    unittest.main()
