from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken

from .config import Config
from .meta import MetaClient
from .store import Store


SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_comments",
    "instagram_business_manage_messages",
    "instagram_business_content_publish",
)


class AccountError(RuntimeError):
    pass


class TokenVault:
    def __init__(self, app_secret: str):
        if not app_secret:
            raise AccountError("У конфігурації відсутній Instagram App Secret.")
        digest = hashlib.sha256(("fraxler-instagram-token-v1:" + app_secret).encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, token: str) -> str:
        return self._fernet.encrypt(token.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise AccountError("Не вдалося розшифрувати токен акаунта.") from exc


@dataclass(frozen=True)
class ConnectedAccount:
    database_id: int
    instagram_user_id: str
    username: str


class AccountManager:
    def __init__(self, config: Config, store: Store):
        self.config = config
        self.store = store
        self.vault = TokenVault(config.app_secret)
        if config.account_id and config.access_token:
            self.store.bootstrap_instagram_account(
                config.account_id, self.vault.encrypt(config.access_token), "Поточний акаунт"
            )

    @property
    def app_id(self) -> str:
        return self.store.get_setting("instagram_app_id") or self.config.instagram_app_id

    @property
    def callback_url(self) -> str:
        return f"{self.config.public_base_url.rstrip('/')}/oauth/instagram/callback"

    def authorization_url(self) -> str:
        if not self.app_id:
            raise AccountError("Спочатку збережіть Meta App ID.")
        state = secrets.token_urlsafe(32)
        self.store.create_oauth_state(hashlib.sha256(state.encode()).hexdigest(), int(time.time()) + 600)
        query = urlencode({
            "client_id": self.app_id,
            "redirect_uri": self.callback_url,
            "response_type": "code",
            "scope": ",".join(SCOPES),
            "force_reauth": "true",
            "state": state,
        })
        return f"https://www.instagram.com/oauth/authorize?{query}"

    def complete_oauth(self, code: str, state: str) -> ConnectedAccount:
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        if not state or not self.store.consume_oauth_state(state_hash, int(time.time())):
            raise AccountError("Стан підключення недійсний або прострочений. Почніть підключення ще раз.")
        short = self._request_json(
            "https://api.instagram.com/oauth/access_token",
            {"client_id": self.app_id, "client_secret": self.config.app_secret,
             "grant_type": "authorization_code", "redirect_uri": self.callback_url, "code": code},
            method="POST",
        )
        short_token = str(short.get("access_token", ""))
        user_id = str(short.get("user_id", ""))
        if not short_token or not user_id:
            raise AccountError("Instagram не повернув токен або ID акаунта.")
        long_data = self._exchange_long_token(short_token)
        token = str(long_data.get("access_token") or short_token)
        expires_in = int(long_data.get("expires_in") or 0)
        client = MetaClient(self.config, token, user_id)
        profile = client.get_account()
        username = str(profile.get("username") or user_id)
        profile_picture_url = str(profile.get("profile_picture_url") or "")
        database_id = self.store.save_instagram_account(
            user_id, username, self.vault.encrypt(token),
            int(time.time()) + expires_in if expires_in else None,
            ",".join(SCOPES),
            profile_picture_url,
        )
        client.usage_callback = lambda usage: self.store.record_api_usage(database_id, usage)
        if client.latest_usage:
            self.store.record_api_usage(database_id, client.latest_usage)
        try:
            client.subscribe_webhooks()
            self.store.update_instagram_account_check(database_id, True, "")
        except Exception as exc:
            self.store.update_instagram_account_check(database_id, False, f"Webhook: {str(exc)[:500]}")
        return ConnectedAccount(database_id, user_id, username)

    def _exchange_long_token(self, short_token: str) -> dict:
        values = {
            "grant_type": "ig_exchange_token",
            "client_secret": self.config.app_secret,
            "access_token": short_token,
        }
        try:
            return self._request_json(
                f"https://graph.instagram.com/access_token?{urlencode(values)}", None, method="GET"
            )
        except AccountError as exc:
            # Meta currently serves accounts through more than one rollout of
            # this endpoint. Some reject GET with IGApiException code 100,
            # while older ones require it. Retry only this method mismatch.
            message = str(exc).casefold()
            if "unsupported request" not in message or "method type" not in message or "get" not in message:
                raise
            try:
                return self._request_json(
                    "https://graph.instagram.com/access_token", values, method="POST"
                )
            except AccountError as post_exc:
                post_message = str(post_exc).casefold()
                if "unsupported request" in post_message and "method type" in post_message:
                    raise AccountError(
                        "Instagram надав доступ, але Meta не дозволила обміняти токен. "
                        "Перевірте, що цей Instagram-акаунт має прийняту роль Instagram Tester "
                        "у застосунку, або що застосунок отримав Advanced Access для трьох "
                        "instagram_business_* дозволів. Запис у «Активні додатки й сайти» "
                        "сам по собі не є роллю Tester."
                    ) from post_exc
                raise

    def client(self, database_id: int | None = None, instagram_user_id: str = "") -> MetaClient:
        row = None
        if instagram_user_id:
            row = self.store.get_instagram_account_by_user_id(instagram_user_id)
        if row is None and database_id:
            row = self.store.get_instagram_account(database_id)
        if row is None:
            row = self.store.default_instagram_account()
        if row is None or row["status"] == "disconnected" or not row["access_token_encrypted"]:
            raise AccountError("Instagram-акаунт не підключено або його токен видалено.")
        database_id = int(row["id"])
        return MetaClient(
            self.config,
            self.vault.decrypt(str(row["access_token_encrypted"])),
            str(row["instagram_user_id"]),
            lambda usage: self.store.record_api_usage(database_id, usage),
        )

    def check(self, database_id: int) -> dict:
        try:
            profile = self.refresh_profile(database_id)
            client = self.client(database_id)
            client.subscribe_webhooks()
            self.store.update_instagram_account_check(database_id, True, "")
            return profile
        except Exception as exc:
            self.store.update_instagram_account_check(database_id, False, str(exc)[:500])
            raise

    def refresh_profile(self, database_id: int) -> dict:
        profile = self.client(database_id).get_account()
        self.store.update_instagram_account_profile(
            database_id,
            str(profile.get("username") or profile.get("id") or ""),
            str(profile.get("profile_picture_url") or ""),
        )
        return profile

    def refresh_limits(self, database_id: int) -> dict:
        client = self.client(database_id)
        # Any successful request refreshes the general x-app-usage percentages.
        profile = client.get_account()
        self.store.update_instagram_account_profile(
            database_id, str(profile.get("username") or profile.get("id") or ""),
            str(profile.get("profile_picture_url") or ""),
        )
        follower_insights: dict = {}
        follower_error = ""
        try:
            follower_insights = client.get_follower_insights()
        except Exception as exc:
            follower_error = str(exc)
        new_followers, lost_followers = self._follow_counts(follower_insights)
        raw_count = profile.get("followers_count")
        self.store.save_follower_snapshot(
            database_id, datetime.now().astimezone().date().isoformat(),
            int(raw_count) if raw_count is not None else None,
            new_followers, lost_followers, follower_error,
        )
        publishing: dict = {}
        try:
            publishing = client.get_content_publishing_limit()
            config = publishing.get("config") if isinstance(publishing.get("config"), dict) else {}
            usage = publishing.get("quota_usage")
            total = config.get("quota_total")
            duration = config.get("quota_duration")
            self.store.update_publishing_usage(
                database_id,
                int(usage) if usage is not None else None,
                int(total) if total is not None else None,
                int(duration) if duration is not None else None,
            )
        except Exception as exc:
            self.store.update_publishing_usage(database_id, None, None, None, str(exc))
        return {"profile": profile, "publishing": publishing, "followers": follower_insights}

    @staticmethod
    def _follow_counts(payload: dict) -> tuple[int | None, int | None]:
        """Extract today's follows/unfollows from the response shapes used by Meta."""
        follows: int | None = None
        unfollows: int | None = None

        def assign(label: str, value: object) -> None:
            nonlocal follows, unfollows
            if not isinstance(value, (int, float)):
                return
            normalized = label.casefold().replace("-", "_").replace(" ", "_")
            if "unfollow" in normalized or normalized in {"lost", "lost_followers"}:
                unfollows = int(value)
            elif normalized in {"follow", "follows", "new_followers", "follower"}:
                follows = int(value)

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key in ("follows", "follow", "new_followers", "unfollows", "lost_followers"):
                    if key in value:
                        assign(key, value[key])
                labels = value.get("dimension_values")
                if isinstance(labels, list) and labels:
                    assign(str(labels[-1]), value.get("value"))
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return follows, unfollows

    @staticmethod
    def _request_json(url: str, values: dict | None, method: str = "GET") -> dict:
        data = urlencode(values).encode() if values is not None else None
        request = Request(url, data=data, method=method, headers={"User-Agent": "FraxlerInstaAutomation/1.0"})
        try:
            with urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise AccountError(f"Instagram OAuth HTTP {exc.code}: {body[:500]}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AccountError(f"Instagram OAuth недоступний: {exc}") from exc
