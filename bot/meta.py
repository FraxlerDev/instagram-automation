from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import Config


class MetaAPIError(RuntimeError):
    pass


class MetaClient:
    def __init__(self, config: Config, access_token: str | None = None, account_id: str | None = None,
                 usage_callback: Callable[[dict], None] | None = None):
        self.config = config
        self.access_token = access_token or config.access_token
        self.account_id = account_id or config.account_id
        self.usage_callback = usage_callback
        self.latest_usage: dict = {}

    def _capture_usage(self, headers) -> None:
        usage: dict[str, object] = {}
        for header, key in (("x-app-usage", "app"), ("x-business-use-case-usage", "business")):
            raw = headers.get(header, "")
            if not raw:
                continue
            try:
                usage[key] = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if usage:
            self.latest_usage = usage
            if self.usage_callback:
                self.usage_callback(usage)

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.config.graph_base_url}/{path.lstrip('/')}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "User-Agent": "SingularityAGIGuideBot/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
                self._capture_usage(response.headers)
                return result
        except HTTPError as exc:
            self._capture_usage(exc.headers)
            body = exc.read().decode("utf-8", errors="replace")
            raise MetaAPIError(f"Meta API HTTP {exc.code}: {body}") from exc
        except (URLError, TimeoutError) as exc:
            raise MetaAPIError(f"Meta API connection failed: {exc}") from exc

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.config.graph_base_url}/{path.lstrip('/')}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": "FraxlerInstaAutomation/1.0",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
                self._capture_usage(response.headers)
                return result
        except HTTPError as exc:
            self._capture_usage(exc.headers)
            body = exc.read().decode("utf-8", errors="replace")
            raise MetaAPIError(f"Meta API HTTP {exc.code}: {body}") from exc
        except (URLError, TimeoutError) as exc:
            raise MetaAPIError(f"Meta API connection failed: {exc}") from exc

    def list_media(self, limit: int = 50) -> list[dict]:
        result = self._get(
            f"{quote(self.account_id, safe='')}/media",
            {"fields": "id,caption,media_type,permalink,timestamp", "limit": str(limit)},
        )
        return list(result.get("data", []))

    def get_media(self, media_id: str) -> dict:
        return self._get(
            quote(media_id, safe=""),
            {"fields": "id,caption,media_type,permalink,timestamp"},
        )

    def get_account(self) -> dict:
        return self._get(
            quote(self.account_id, safe=""),
            {"fields": "id,username,account_type,profile_picture_url,followers_count"},
        )

    def get_follower_insights(self) -> dict:
        return self._get(
            f"{quote(self.account_id, safe='')}/insights",
            {"metric": "follows_and_unfollows", "period": "day"},
        )

    def get_content_publishing_limit(self) -> dict:
        result = self._get(
            f"{quote(self.account_id, safe='')}/content_publishing_limit",
            {"fields": "quota_usage,config"},
        )
        rows = result.get("data", [])
        return dict(rows[0]) if rows else {}

    def get_user_profile(self, instagram_scoped_id: str) -> dict:
        return self._get(
            quote(instagram_scoped_id, safe=""),
            {"fields": "id,name,username,profile_pic,is_user_follow_business,is_business_follow_user"},
        )

    def reply_to_comment(self, comment_id: str, message: str) -> str:
        result = self._post(f"{quote(comment_id, safe='')}/replies", {"message": message})
        return str(result.get("id", ""))

    def send_private_reply(self, comment_id: str, message: str) -> str:
        result = self._post(
            f"{quote(self.account_id, safe='')}/messages",
            {"recipient": {"comment_id": comment_id}, "message": {"text": message}},
        )
        recipient_id = result.get("recipient_id")
        if not recipient_id:
            raise MetaAPIError(f"Meta response has no recipient_id: {result}")
        return str(recipient_id)

    def send_text(self, recipient_id: str, message: str) -> str:
        result = self._post(
            f"{quote(self.account_id, safe='')}/messages",
            {
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": {"text": message},
            },
        )
        message_id = result.get("message_id")
        if not message_id:
            raise MetaAPIError(f"Meta response has no message_id: {result}")
        return str(message_id)

    def subscribe_webhooks(self) -> bool:
        result = self._post(
            f"{quote(self.account_id, safe='')}/subscribed_apps",
            {"subscribed_fields": "comments,messages"},
        )
        return bool(result.get("success"))
