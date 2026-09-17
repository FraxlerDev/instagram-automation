from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from urllib.parse import quote
from collections.abc import Callable

from .config import Config
from .meta import MetaClient
from .notifications import TelegramNotifier
from .store import Store
from .text import contains_any_word


LOGGER = logging.getLogger("guide_bot")


class Processor:
    def __init__(self, config: Config, store: Store, meta: MetaClient,
                 notifier: TelegramNotifier | None = None,
                 account_client: Callable[[int | None, str], MetaClient] | None = None):
        self.config = config
        self.store = store
        self.meta = meta
        self.notifier = notifier or TelegramNotifier(store)
        self.account_client = account_client
        # Meta may redeliver the same event before the first request finishes.
        # Serial processing plus SQLite state prevents duplicate replies.
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._retry_loop, daemon=True, name="instagram-retries").start()

    def stop(self) -> None:
        self._stop.set()

    def process(self, payload: dict) -> None:
        with self._lock:
            if payload.get("object") != "instagram":
                return
            for entry in payload.get("entry", []):
                entry_account_id = str(entry.get("id", ""))
                account = self.store.get_instagram_account_by_user_id(entry_account_id) if entry_account_id else None
                database_account_id = int(account["id"]) if account else None
                for field, value in self._changes(entry):
                    if field == "comments":
                        self._comment(value, database_account_id, entry_account_id)
                for event in entry.get("messaging", []):
                    self._message(event, database_account_id, entry_account_id)

    @staticmethod
    def _changes(entry: dict):
        if "field" in entry and "value" in entry:
            yield entry.get("field"), entry.get("value", {})
        for change in entry.get("changes", []):
            yield change.get("field"), change.get("value", {})

    def _client(self, database_account_id: int | None, instagram_user_id: str = "") -> MetaClient:
        if self.account_client:
            return self.account_client(database_account_id, instagram_user_id)
        return self.meta

    def _comment(self, value: dict, database_account_id: int | None = None,
                 instagram_user_id: str = "") -> None:
        comment_id = str(value.get("id", ""))
        media_id = str(value.get("media", {}).get("id", ""))
        text = str(value.get("text", ""))
        username = str(value.get("from", {}).get("username", ""))
        author_id = str(value.get("from", {}).get("id", ""))
        if not comment_id:
            return
        automations = self.store.active_automations_for_media(media_id, database_account_id)
        if not automations:
            return
        if database_account_id is None and automations[0]["instagram_account_id"] is not None:
            database_account_id = int(automations[0]["instagram_account_id"])
        account = self.store.get_instagram_account(database_account_id) if database_account_id else None
        own_author = bool(account and (
            (author_id and author_id == str(account["instagram_user_id"]))
            or (username and username.casefold() == str(account["username"] or "").casefold())
        ))
        own_reply_text = any(
            text.strip() == str(item["public_reply_text"] or "").strip()
            for item in automations
        )
        if own_author or own_reply_text:
            LOGGER.info("Ignoring own Instagram comment reply %s", comment_id)
            return
        automation = next(
            (
                item for item in automations
                if contains_any_word(text, self._csv(item["trigger_keywords"]))
            ),
            None,
        )
        if automation is None:
            self._notify_comment(
                comment_id, media_id, username, text, automations, None, database_account_id
            )
            return
        if database_account_id is None and automation["instagram_account_id"] is not None:
            database_account_id = int(automation["instagram_account_id"])

        job = self.store.ensure_comment(
            comment_id, media_id, username, int(automation["id"]), text, database_account_id
        )
        meta = self._client(database_account_id, instagram_user_id)
        if not job["public_done"]:
            try:
                meta.reply_to_comment(comment_id, str(automation["public_reply_text"]))
                self.store.mark_public_done(comment_id)
            except Exception as exc:
                self.store.mark_comment_error(comment_id, str(exc))
                self.store.schedule_retry(
                    f"public:{comment_id}", "public_reply",
                    {"comment_id": comment_id, "message": str(automation["public_reply_text"])},
                    int(automation["id"]), None, str(exc),
                )
                LOGGER.exception("Could not reply publicly to comment %s", comment_id)
        if not job["private_done"]:
            try:
                recipient_id = meta.send_private_reply(comment_id, str(automation["initial_dm_text"]))
                self.store.mark_private_done(comment_id, recipient_id, int(automation["id"]), database_account_id)
                self.store.log_direct(recipient_id, "out", "automation", str(automation["initial_dm_text"]),
                                      instagram_account_id=database_account_id)
                self._capture_follow_state(
                    meta, recipient_id, int(automation["id"]), database_account_id, baseline=True
                )
            except Exception as exc:
                self.store.mark_comment_error(comment_id, str(exc))
                self.store.schedule_retry(
                    f"private:{comment_id}", "private_reply",
                    {"comment_id": comment_id, "message": str(automation["initial_dm_text"])},
                    int(automation["id"]), None, str(exc),
                )
                LOGGER.exception("Could not send private reply for comment %s", comment_id)
        self._notify_comment(
            comment_id, media_id, username, text, automations, automation, database_account_id
        )
        LOGGER.info("Comment %s handled for @%s by automation %s", comment_id, username, automation["id"])

    def _notify_comment(self, comment_id: str, media_id: str, username: str, text: str,
                        automations: list, matched, account_id: int | None) -> None:
        if not self.notifier.enabled():
            return
        event_key = f"instagram-comment:{comment_id}"
        if not self.store.claim_notification(event_key):
            return
        account = self.store.get_instagram_account(account_id) if account_id else None
        account_name = str(account["username"] or account["instagram_user_id"]) if account else "не визначено"
        permalink = next((str(item["media_permalink"]) for item in automations if item["media_permalink"]), "")
        publication = permalink or f"Media ID: {media_id or 'не визначено'}"
        author = f"@{username}" if username else "ім’я не передано Instagram"
        if matched is None:
            scenario = "🎯 Збіг сценарію: ні — автоматична відповідь не запускається"
        else:
            scenario = (
                f"⚙️ Автоматизація публікації: {str(matched['name'])}\n"
                f"🤖 Автоматична відповідь: {str(matched['public_reply_text'])[:1000]}"
            )
        detail = (
            f"📱 Акаунт: @{account_name}\n"
            f"🖼 Публікація: {publication}\n"
            f"👤 Автор: {author}\n"
            f"💬 Коментар: {text[:1200] or 'без тексту'}\n"
            f"{scenario}"
        )

        def send() -> None:
            if not self.notifier.send("💬 Новий коментар в Instagram", detail):
                self.store.release_notification(event_key)

        threading.Thread(target=send, daemon=True, name="telegram-comment").start()

    def _message(self, event: dict, database_account_id: int | None = None,
                 entry_account_id: str = "") -> None:
        message = event.get("message") or {}
        if message.get("is_echo"):
            return
        message_id = str(message.get("mid", ""))
        sender_id = str(event.get("sender", {}).get("id", ""))
        text = str(message.get("text", ""))
        attachments = self._attachments(message)
        if not message_id or not sender_id:
            return
        # The request is already authenticated by Meta's HMAC signature.
        # Instagram IDs inside messaging webhooks can use a different scoped
        # namespace than the account ID returned during setup. The stored
        # sender state below is therefore the reliable conversation match.
        LOGGER.info("Inbound Instagram message %s received", message_id)
        database_account_id = database_account_id or self.store.account_id_for_user(sender_id)
        self.store.log_direct(sender_id, "in", "instagram", text, message_id, attachments=attachments,
                              instagram_account_id=database_account_id)
        if self.store.message_state(message_id) not in {None, "error"}:
            return
        context = self.store.recipient_context(sender_id, database_account_id)
        if context is None or context["recipient_state"] == "fulfilled":
            self.store.mark_message(message_id, sender_id, "ignored")
            return
        if context["manual_mode"]:
            self.store.mark_message(message_id, sender_id, "manual")
            return
        context_account_id = int(context["instagram_account_id"]) if context["instagram_account_id"] else database_account_id
        meta = self._client(context_account_id, entry_account_id)
        try:
            rules = json.loads(str(context["conversation_rules"] or "[]"))
        except json.JSONDecodeError:
            rules = []
        matching_rule = next((
            rule for rule in rules
            if str(rule.get("state", "waiting")) == str(context["recipient_state"])
            and contains_any_word(text, self._csv(str(rule.get("keywords", ""))))
        ), None)
        if matching_rule is not None:
            if matching_rule.get("send_pdf"):
                self._send_guide(sender_id, message_id, context, str(matching_rule.get("reply_text", "")), meta)
                return
            reply = str(matching_rule.get("reply_text", "")).strip()
            try:
                if reply:
                    outgoing_id = meta.send_text(sender_id, reply)
                    self.store.log_direct(sender_id, "out", "automation", reply, outgoing_id,
                                          instagram_account_id=database_account_id)
                self.store.set_recipient_state(sender_id, str(matching_rule.get("next_state", "waiting")))
                self.store.mark_message(message_id, sender_id, "done")
            except Exception as exc:
                self.store.mark_message(message_id, sender_id, "error", str(exc))
            return
        if context["recipient_state"] != "waiting" or not contains_any_word(text, self._csv(context["confirmation_words"])):
            self.store.mark_message(message_id, sender_id, "ignored")
            return
        self._send_guide(sender_id, message_id, context, meta=meta)

    def _send_guide(self, sender_id: str, message_id: str, context, prefix: str = "",
                    meta: MetaClient | None = None) -> None:
        meta = meta or self._client(context["instagram_account_id"])
        if context["require_follow"]:
            try:
                profile = meta.get_user_profile(sender_id)
                follows = profile.get("is_user_follow_business")
                self.store.update_follow_status(
                    sender_id, follows if isinstance(follows, bool) else None,
                    str(profile.get("username", "")), str(profile.get("profile_pic", "")),
                    instagram_account_id=context["instagram_account_id"],
                )
                self.store.record_follow_conversion(
                    int(context["id"]), sender_id, context["instagram_account_id"],
                    follows if isinstance(follows, bool) else None,
                )
                if follows is not True:
                    reminder = str(context["follow_required_message"])
                    outgoing_id = meta.send_text(sender_id, reminder)
                    self.store.log_direct(sender_id, "out", "automation", reminder, outgoing_id,
                                          instagram_account_id=context["instagram_account_id"])
                    self.store.mark_message(message_id, sender_id, "follow_required")
                    return
            except Exception as exc:
                self.store.update_follow_status(
                    sender_id, None, instagram_account_id=context["instagram_account_id"]
                )
                self.store.mark_message(message_id, sender_id, "error", f"Follow check: {exc}")
                self.notifier.send("⚠️ Не вдалося перевірити підписку", str(exc)[:500])
                return

        try:
            filename = Path(str(context["pdf_path"])).name or "file"
            guide_url = f"{self.config.public_base_url.rstrip('/')}/files/{context['id']}/{quote(filename)}"
            message_text = prefix.strip() or str(context["guide_message_text"])
            outgoing = f"{message_text}:\n{guide_url}"
            outgoing_id = meta.send_text(sender_id, outgoing)
            self.store.mark_fulfilled(sender_id, str(context["selected_comment_id"]))
            self.store.mark_message(message_id, sender_id, "done")
            self.store.log_direct(sender_id, "out", "automation", outgoing, outgoing_id,
                                  instagram_account_id=context["instagram_account_id"])
            if not context["require_follow"]:
                self._capture_follow_state(
                    meta, sender_id, int(context["id"]), context["instagram_account_id"], baseline=False
                )
            LOGGER.info("Guide sent to Instagram-scoped user %s", sender_id)
        except Exception as exc:
            self.store.mark_message(message_id, sender_id, "error", str(exc))
            self.store.schedule_retry(
                f"final:{message_id}", "final_message",
                {"sender_id": sender_id, "message_id": message_id,
                 "comment_id": str(context["selected_comment_id"]), "message": outgoing},
                int(context["id"]), sender_id, str(exc),
            )
            LOGGER.exception("Could not send guide to %s", sender_id)

    def _capture_follow_state(self, meta: MetaClient, recipient_id: str, automation_id: int,
                              account_id: int | None, *, baseline: bool) -> None:
        try:
            profile = meta.get_user_profile(recipient_id)
            follows = profile.get("is_user_follow_business")
            follows_value = follows if isinstance(follows, bool) else None
            self.store.update_follow_status(
                recipient_id, follows_value, str(profile.get("username", "")),
                str(profile.get("profile_pic", "")), instagram_account_id=account_id,
            )
            if baseline:
                self.store.record_follow_baseline(automation_id, recipient_id, account_id, follows_value)
            else:
                self.store.record_follow_conversion(automation_id, recipient_id, account_id, follows_value)
        except Exception as exc:
            LOGGER.info("Follow attribution is unavailable for %s: %s", recipient_id, exc)

    @staticmethod
    def _attachments(message: dict) -> list[dict]:
        result: list[dict] = []
        for item in list(message.get("attachments") or []) + list(message.get("shares") or []):
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
            nested = next((payload.get(key) for key in ("image_data", "video_data")
                           if isinstance(payload.get(key), dict)), {})
            url = payload.get("url") or payload.get("file_url") or nested.get("url") \
                or nested.get("preview_url") or nested.get("animated_gif_url") or ""
            result.append({
                "type": str(item.get("type") or payload.get("type") or "attachment")[:50],
                "url": str(url)[:2000],
                "name": str(payload.get("name") or item.get("name") or "")[:255],
                "title": str(payload.get("title") or item.get("title") or "")[:255],
            })
        return result[:20]

    def _retry_loop(self) -> None:
        while not self._stop.wait(10):
            with self._lock:
                for retry in self.store.due_retries(int(time.time())):
                    self._run_retry(retry)

    def _run_retry(self, retry) -> None:
        try:
            payload = json.loads(str(retry["payload"]))
            kind = str(retry["kind"])
            automation = self.store.get_automation(int(retry["automation_id"])) if retry["automation_id"] else None
            account_id = int(automation["instagram_account_id"]) if automation and automation["instagram_account_id"] else None
            meta = self._client(account_id)
            if kind == "public_reply":
                meta.reply_to_comment(payload["comment_id"], payload["message"])
                self.store.mark_public_done(payload["comment_id"])
            elif kind == "private_reply":
                recipient_id = meta.send_private_reply(payload["comment_id"], payload["message"])
                self.store.mark_private_done(payload["comment_id"], recipient_id, int(retry["automation_id"]), account_id)
                self.store.log_direct(recipient_id, "out", "automation", payload["message"], instagram_account_id=account_id)
                self._capture_follow_state(
                    meta, recipient_id, int(retry["automation_id"]), account_id, baseline=True
                )
            elif kind == "final_message":
                outgoing_id = meta.send_text(payload["sender_id"], payload["message"])
                self.store.mark_fulfilled(payload["sender_id"], payload.get("comment_id"))
                self.store.mark_message(payload["message_id"], payload["sender_id"], "done")
                self.store.log_direct(payload["sender_id"], "out", "automation", payload["message"], outgoing_id,
                                      instagram_account_id=account_id)
                if automation and not automation["require_follow"]:
                    self._capture_follow_state(
                        meta, payload["sender_id"], int(automation["id"]), account_id, baseline=False
                    )
            else:
                raise ValueError(f"Unknown retry kind: {kind}")
            self.store.complete_retry(int(retry["id"]))
            LOGGER.info("Retry %s completed", retry["id"])
        except Exception as exc:
            attempts = int(retry["attempts"]) + 1
            delay = min(3600, 30 * (2 ** min(attempts - 1, 7)))
            self.store.fail_retry(int(retry["id"]), attempts, int(time.time()) + delay, str(exc))
            if attempts in {1, 8}:
                self.notifier.send(
                    "🔴 Помилка Instagram API",
                    f"Операція {retry['kind']}, спроба {attempts}: {str(exc)[:500]}",
                )
            LOGGER.exception("Retry %s failed", retry["id"])

    @staticmethod
    def _csv(value: str) -> frozenset[str]:
        return frozenset(item.strip() for item in value.split(",") if item.strip())
