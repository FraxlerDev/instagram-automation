from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    """Load a small, conventional .env file without third-party packages."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _csv(name: str) -> frozenset[str]:
    return frozenset(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


def _path(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


@dataclass(frozen=True)
class Config:
    access_token: str
    account_id: str
    app_secret: str
    verify_token: str
    public_base_url: str
    allowed_media_ids: frozenset[str]
    trigger_keywords: frozenset[str]
    confirmation_words: frozenset[str]
    public_reply_text: str
    initial_dm_text: str
    guide_message_text: str
    graph_api_version: str
    host: str
    port: int
    admin_port: int
    guide_pdf_path: Path
    db_path: Path
    signature_required: bool
    admin_host: str = "127.0.0.1"
    admin_allowed_networks: tuple[str, ...] = ("127.0.0.0/8",)
    instagram_app_id: str = ""

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.instagram.com/{self.graph_api_version}"

    @property
    def guide_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/files/guide.pdf"

    @property
    def missing_required(self) -> list[str]:
        values = {
            "INSTAGRAM_ACCESS_TOKEN": self.access_token,
            "INSTAGRAM_ACCOUNT_ID": self.account_id,
            "INSTAGRAM_APP_SECRET": self.app_secret,
            "WEBHOOK_VERIFY_TOKEN": self.verify_token,
            "PUBLIC_BASE_URL": self.public_base_url,
            "ALLOWED_MEDIA_IDS": self.allowed_media_ids,
        }
        return [name for name, value in values.items() if not value]


def get_config() -> Config:
    load_dotenv()
    return Config(
        access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        account_id=os.getenv("INSTAGRAM_ACCOUNT_ID", ""),
        app_secret=os.getenv("INSTAGRAM_APP_SECRET", ""),
        verify_token=os.getenv("WEBHOOK_VERIFY_TOKEN", ""),
        public_base_url=os.getenv("PUBLIC_BASE_URL", ""),
        allowed_media_ids=_csv("ALLOWED_MEDIA_IDS"),
        trigger_keywords=_csv("TRIGGER_KEYWORDS"),
        confirmation_words=_csv("CONFIRMATION_WORDS"),
        public_reply_text=os.getenv("PUBLIC_REPLY_TEXT", "Написав вам у Direct 😊"),
        initial_dm_text=os.getenv(
            "INITIAL_DM_TEXT",
            "Привіт! Щоб отримати файл, підпишись на @your_account "
            "та напиши у відповідь слово «ГОТОВО».",
        ),
        guide_message_text=os.getenv("GUIDE_MESSAGE_TEXT", "Ось твій файл"),
        graph_api_version=os.getenv("GRAPH_API_VERSION", "v26.0"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        admin_port=int(os.getenv("ADMIN_PORT", "8795")),
        guide_pdf_path=_path("GUIDE_PDF_PATH", "assets/guide.pdf"),
        db_path=_path("DB_PATH", "data/bot.sqlite3"),
        signature_required=os.getenv("SIGNATURE_REQUIRED", "true").casefold() in {"1", "true", "yes"},
        admin_host=os.getenv("ADMIN_HOST", "127.0.0.1"),
        admin_allowed_networks=tuple(
            item.strip() for item in os.getenv("ADMIN_ALLOWED_NETWORKS", "127.0.0.0/8").split(",")
            if item.strip()
        ),
        instagram_app_id=os.getenv("INSTAGRAM_APP_ID", ""),
    )
