import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.notifications import TelegramNotifier
from bot.store import Store


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true}'


class NotificationTests(unittest.TestCase):
    def test_disabled_notifications_do_not_call_network(self):
        with tempfile.TemporaryDirectory() as temp:
            notifier = TelegramNotifier(Store(Path(temp) / "bot.sqlite3"))
            with patch("bot.notifications.urlopen") as request:
                self.assertFalse(notifier.send("Старт", "Тест"))
                request.assert_not_called()

    def test_enabled_notification_uses_saved_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "bot.sqlite3")
            store.set_setting("telegram_enabled", "1")
            store.set_setting("telegram_bot_token", "secret-token")
            store.set_setting("telegram_chat_id", "123")
            with patch("bot.notifications.urlopen", return_value=FakeResponse()) as request:
                self.assertTrue(TelegramNotifier(store).send("Старт", "Тест"))
                sent = request.call_args.args[0]
                self.assertIn(b'"chat_id": "123"', sent.data)
                self.assertNotIn(b"secret-token", sent.data)


if __name__ == "__main__":
    unittest.main()
