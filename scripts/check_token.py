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
    url = f"{config.graph_base_url}/me?{urlencode({'fields': 'id,username'})}"
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
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nCopy the value of 'id' into INSTAGRAM_ACCOUNT_ID in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
