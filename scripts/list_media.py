#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bot.config import get_config  # noqa: E402


def main() -> int:
    config = get_config()
    if not config.access_token:
        print("INSTAGRAM_ACCESS_TOKEN is missing in .env", file=sys.stderr)
        return 1
    query = urlencode(
        {"fields": "id,caption,media_type,permalink,timestamp", "limit": "25"}
    )
    url = f"{config.graph_base_url}/me/media?{query}"
    request = Request(url, headers={"Authorization": f"Bearer {config.access_token}"})
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Meta API HTTP {exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError) as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        return 1
    for item in data.get("data", []):
        caption = " ".join(str(item.get("caption", "")).split())[:90]
        print(f"ID: {item.get('id', '')}")
        print(f"Type: {item.get('media_type', '')}")
        print(f"Date: {item.get('timestamp', '')}")
        print(f"Caption: {caption}")
        print(f"Link: {item.get('permalink', '')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
