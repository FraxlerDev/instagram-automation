from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, definition: str) -> None:
        name = definition.split()[0]
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS automations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    media_permalink TEXT NOT NULL DEFAULT '',
                    trigger_keywords TEXT NOT NULL,
                    confirmation_words TEXT NOT NULL,
                    public_reply_text TEXT NOT NULL,
                    initial_dm_text TEXT NOT NULL,
                    guide_message_text TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    conversation_rules TEXT NOT NULL DEFAULT '[]',
                    require_follow INTEGER NOT NULL DEFAULT 0,
                    follow_required_message TEXT NOT NULL DEFAULT 'Підпишіться на акаунт і повторіть відповідь.',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS comment_jobs (
                    comment_id TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    username TEXT,
                    public_done INTEGER NOT NULL DEFAULT 0,
                    private_done INTEGER NOT NULL DEFAULT 0,
                    recipient_id TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS recipients (
                    recipient_id TEXT PRIMARY KEY,
                    comment_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS message_events (
                    message_id TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    entry_count INTEGER NOT NULL,
                    comment_count INTEGER NOT NULL,
                    messaging_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS notification_events (
                    event_key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS admin_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    folder TEXT NOT NULL DEFAULT '',
                    stored_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS retry_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_key TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    automation_id INTEGER,
                    recipient_id TEXT,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS message_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE,
                    recipient_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'sent',
                    last_error TEXT,
                    attachments TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_profiles (
                    recipient_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    manual_mode INTEGER NOT NULL DEFAULT 0,
                    follows_business INTEGER,
                    follow_checked_at TEXT,
                    profile_pic_url TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS health_checks (
                    key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS automation_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    automation_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS instagram_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instagram_user_id TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL DEFAULT '',
                    profile_picture_url TEXT NOT NULL DEFAULT '',
                    access_token_encrypted TEXT NOT NULL DEFAULT '',
                    token_expires_at INTEGER,
                    scopes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    last_checked_at TEXT,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS api_usage (
                    instagram_account_id INTEGER PRIMARY KEY,
                    app_usage_json TEXT NOT NULL DEFAULT '{}',
                    business_usage_json TEXT NOT NULL DEFAULT '{}',
                    publishing_usage INTEGER,
                    publishing_total INTEGER,
                    publishing_duration INTEGER,
                    publishing_error TEXT NOT NULL DEFAULT '',
                    observed_at TEXT,
                    publishing_checked_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS follower_snapshots (
                    instagram_account_id INTEGER NOT NULL,
                    snapshot_date TEXT NOT NULL,
                    followers_count INTEGER,
                    new_followers INTEGER,
                    lost_followers INTEGER,
                    net_change INTEGER,
                    last_error TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(instagram_account_id, snapshot_date)
                );
                CREATE TABLE IF NOT EXISTS automation_follow_tracking (
                    automation_id INTEGER NOT NULL,
                    recipient_id TEXT NOT NULL,
                    instagram_account_id INTEGER NOT NULL DEFAULT 0,
                    baseline_follows INTEGER,
                    converted_at TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    checked_at TEXT,
                    PRIMARY KEY(automation_id, recipient_id, instagram_account_id)
                );
                """
            )
            self._ensure_column(db, "comment_jobs", "automation_id INTEGER")
            self._ensure_column(db, "comment_jobs", "comment_text TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "comment_jobs", "public_sent_at TEXT")
            self._ensure_column(db, "comment_jobs", "private_sent_at TEXT")
            self._ensure_column(db, "comment_jobs", "fulfilled_at TEXT")
            self._ensure_column(db, "recipients", "automation_id INTEGER")
            self._ensure_column(db, "recipients", "fulfilled_at TEXT")
            self._ensure_column(db, "documents", "folder TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "documents", "stored_name TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "automations", "conversation_rules TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "automations", "require_follow INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "automations", "follow_required_message TEXT NOT NULL DEFAULT 'Підпишіться на акаунт і повторіть відповідь.'")
            self._ensure_column(db, "message_log", "attachments TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "user_profiles", "follows_business INTEGER")
            self._ensure_column(db, "user_profiles", "follow_checked_at TEXT")
            self._ensure_column(db, "user_profiles", "profile_pic_url TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "automations", "instagram_account_id INTEGER")
            self._ensure_column(db, "comment_jobs", "instagram_account_id INTEGER")
            self._ensure_column(db, "recipients", "instagram_account_id INTEGER")
            self._ensure_column(db, "message_log", "instagram_account_id INTEGER")
            self._ensure_column(db, "user_profiles", "instagram_account_id INTEGER")
            self._ensure_column(db, "instagram_accounts", "profile_picture_url TEXT NOT NULL DEFAULT ''")
            db.execute("""UPDATE comment_jobs SET fulfilled_at = COALESCE(
                           (SELECT r.fulfilled_at FROM recipients r WHERE r.comment_id = comment_jobs.comment_id),
                           updated_at)
                       WHERE fulfilled_at IS NULL AND EXISTS (
                           SELECT 1 FROM recipients r
                           WHERE r.comment_id = comment_jobs.comment_id AND r.state = 'fulfilled'
                       )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_automations_media ON automations(media_id, enabled, archived)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON admin_sessions(expires_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_comment_jobs_created ON comment_jobs(created_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_retry_due ON retry_jobs(state, next_attempt_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON message_log(recipient_id, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_messages_account_user ON message_log(instagram_account_id, recipient_id, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_users_account ON user_profiles(instagram_account_id, last_seen_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_versions_automation ON automation_versions(automation_id, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_automations_account_media ON automations(instagram_account_id, media_id, enabled, archived)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON instagram_accounts(instagram_user_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_follow_tracking_automation_converted ON automation_follow_tracking(automation_id, converted_at)")
            db.execute(
                """INSERT INTO user_profiles(recipient_id, username, last_seen_at)
                   SELECT r.recipient_id, COALESCE(j.username, ''), r.updated_at
                   FROM recipients r LEFT JOIN comment_jobs j ON j.comment_id = r.comment_id
                   WHERE r.recipient_id IS NOT NULL
                   ON CONFLICT(recipient_id) DO UPDATE SET
                   username = CASE WHEN excluded.username != '' THEN excluded.username ELSE user_profiles.username END"""
            )
            db.execute("PRAGMA optimize")

    def bootstrap_instagram_account(self, instagram_user_id: str, encrypted_token: str,
                                    username: str = "Поточний акаунт") -> int:
        with self._connect() as db:
            row = db.execute("SELECT id FROM instagram_accounts WHERE instagram_user_id = ?", (instagram_user_id,)).fetchone()
            if row:
                account_id = int(row["id"])
            else:
                is_default = int(db.execute("SELECT COUNT(*) FROM instagram_accounts").fetchone()[0] == 0)
                cursor = db.execute(
                    """INSERT INTO instagram_accounts(instagram_user_id, username, access_token_encrypted, is_default)
                       VALUES (?, ?, ?, ?)""",
                    (instagram_user_id, username, encrypted_token, is_default),
                )
                account_id = int(cursor.lastrowid)
            db.execute("UPDATE automations SET instagram_account_id = ? WHERE instagram_account_id IS NULL", (account_id,))
            db.execute("UPDATE comment_jobs SET instagram_account_id = ? WHERE instagram_account_id IS NULL", (account_id,))
            db.execute("UPDATE recipients SET instagram_account_id = ? WHERE instagram_account_id IS NULL", (account_id,))
            db.execute("UPDATE message_log SET instagram_account_id = ? WHERE instagram_account_id IS NULL", (account_id,))
            db.execute("UPDATE user_profiles SET instagram_account_id = ? WHERE instagram_account_id IS NULL", (account_id,))
            return account_id

    def save_instagram_account(self, instagram_user_id: str, username: str, encrypted_token: str,
                               token_expires_at: int | None, scopes: str,
                               profile_picture_url: str = "") -> int:
        with self._connect() as db:
            default = int(db.execute("SELECT COUNT(*) FROM instagram_accounts").fetchone()[0] == 0)
            db.execute(
                """INSERT INTO instagram_accounts(instagram_user_id, username, profile_picture_url,
                          access_token_encrypted, token_expires_at, scopes, status, is_default, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, '')
                   ON CONFLICT(instagram_user_id) DO UPDATE SET username = excluded.username,
                   profile_picture_url = CASE WHEN excluded.profile_picture_url != ''
                       THEN excluded.profile_picture_url ELSE instagram_accounts.profile_picture_url END,
                   access_token_encrypted = excluded.access_token_encrypted,
                   token_expires_at = excluded.token_expires_at, scopes = excluded.scopes,
                   status = 'active', last_error = '', updated_at = CURRENT_TIMESTAMP""",
                (instagram_user_id, username[:200], profile_picture_url[:2000], encrypted_token,
                 token_expires_at, scopes, default),
            )
            return int(db.execute("SELECT id FROM instagram_accounts WHERE instagram_user_id = ?", (instagram_user_id,)).fetchone()[0])

    def list_instagram_accounts(self, include_disconnected: bool = True) -> list[sqlite3.Row]:
        where = "" if include_disconnected else " WHERE status != 'disconnected'"
        with self._connect() as db:
            return list(db.execute("SELECT * FROM instagram_accounts" + where + " ORDER BY is_default DESC, username, id"))

    def get_instagram_account(self, account_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM instagram_accounts WHERE id = ?", (account_id,)).fetchone()

    def get_instagram_account_by_user_id(self, instagram_user_id: str) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM instagram_accounts WHERE instagram_user_id = ?", (instagram_user_id,)).fetchone()

    def default_instagram_account(self) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM instagram_accounts WHERE status != 'disconnected' ORDER BY is_default DESC, id LIMIT 1").fetchone()

    def set_default_instagram_account(self, account_id: int) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT id FROM instagram_accounts WHERE id = ? AND status != 'disconnected'", (account_id,)).fetchone()
            if not row:
                return False
            db.execute("UPDATE instagram_accounts SET is_default = 0")
            db.execute("UPDATE instagram_accounts SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (account_id,))
            return True

    def update_instagram_account_profile(self, account_id: int, username: str,
                                         profile_picture_url: str = "") -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE instagram_accounts SET username = ?, profile_picture_url = CASE WHEN ? != ''
                       THEN ? ELSE profile_picture_url END,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (username[:200], profile_picture_url[:2000], profile_picture_url[:2000], account_id),
            )

    def update_instagram_account_check(self, account_id: int, ok: bool, error: str) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE instagram_accounts SET status = ?, last_error = ?, last_checked_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                ("active" if ok else "error", error[:500], account_id),
            )

    def record_api_usage(self, account_id: int, usage: dict) -> None:
        app = usage.get("app") if isinstance(usage.get("app"), dict) else {}
        business = usage.get("business") if isinstance(usage.get("business"), dict) else {}
        with self._connect() as db:
            db.execute(
                """INSERT INTO api_usage(instagram_account_id, app_usage_json, business_usage_json, observed_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(instagram_account_id) DO UPDATE SET
                   app_usage_json = CASE WHEN excluded.app_usage_json != '{}' THEN excluded.app_usage_json ELSE api_usage.app_usage_json END,
                   business_usage_json = CASE WHEN excluded.business_usage_json != '{}' THEN excluded.business_usage_json ELSE api_usage.business_usage_json END,
                   observed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP""",
                (account_id, json.dumps(app, ensure_ascii=False), json.dumps(business, ensure_ascii=False)),
            )

    def update_publishing_usage(self, account_id: int, usage: int | None, total: int | None,
                                duration: int | None, error: str = "") -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO api_usage(instagram_account_id, publishing_usage, publishing_total,
                          publishing_duration, publishing_error, publishing_checked_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(instagram_account_id) DO UPDATE SET
                   publishing_usage = excluded.publishing_usage,
                   publishing_total = excluded.publishing_total,
                   publishing_duration = excluded.publishing_duration,
                   publishing_error = excluded.publishing_error,
                   publishing_checked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP""",
                (account_id, usage, total, duration, error[:500]),
            )

    def get_api_usage(self, account_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM api_usage WHERE instagram_account_id = ?", (account_id,)).fetchone()

    def save_follower_snapshot(self, account_id: int, snapshot_date: str,
                               followers_count: int | None, new_followers: int | None,
                               lost_followers: int | None, error: str = "") -> None:
        with self._connect() as db:
            previous = db.execute(
                """SELECT followers_count FROM follower_snapshots
                   WHERE instagram_account_id = ? AND snapshot_date < ? AND followers_count IS NOT NULL
                   ORDER BY snapshot_date DESC LIMIT 1""",
                (account_id, snapshot_date),
            ).fetchone()
            net_change = None
            if new_followers is not None and lost_followers is not None:
                net_change = new_followers - lost_followers
            elif followers_count is not None and previous and previous["followers_count"] is not None:
                net_change = followers_count - int(previous["followers_count"])
            db.execute(
                """INSERT INTO follower_snapshots(instagram_account_id, snapshot_date,
                          followers_count, new_followers, lost_followers, net_change, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(instagram_account_id, snapshot_date) DO UPDATE SET
                   followers_count = COALESCE(excluded.followers_count, follower_snapshots.followers_count),
                   new_followers = COALESCE(excluded.new_followers, follower_snapshots.new_followers),
                   lost_followers = COALESCE(excluded.lost_followers, follower_snapshots.lost_followers),
                   net_change = COALESCE(excluded.net_change, follower_snapshots.net_change),
                   last_error = excluded.last_error, recorded_at = CURRENT_TIMESTAMP""",
                (account_id, snapshot_date, followers_count, new_followers,
                 lost_followers, net_change, error[:500]),
            )

    def latest_follower_snapshot(self, account_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute(
                """SELECT * FROM follower_snapshots WHERE instagram_account_id = ?
                   ORDER BY snapshot_date DESC LIMIT 1""", (account_id,),
            ).fetchone()

    def record_follow_baseline(self, automation_id: int, recipient_id: str,
                               account_id: int | None, follows: bool | None) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO automation_follow_tracking(
                       automation_id, recipient_id, instagram_account_id, baseline_follows, checked_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(automation_id, recipient_id, instagram_account_id) DO UPDATE SET
                   baseline_follows = CASE
                       WHEN automation_follow_tracking.baseline_follows IS NULL
                       THEN excluded.baseline_follows ELSE automation_follow_tracking.baseline_follows END,
                   checked_at = CURRENT_TIMESTAMP""",
                (automation_id, recipient_id, account_id or 0,
                 None if follows is None else int(follows)),
            )

    def record_follow_conversion(self, automation_id: int, recipient_id: str,
                                 account_id: int | None, follows: bool | None) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE automation_follow_tracking SET converted_at = CURRENT_TIMESTAMP,
                       checked_at = CURRENT_TIMESTAMP
                   WHERE automation_id = ? AND recipient_id = ? AND instagram_account_id = ?
                     AND baseline_follows = 0 AND converted_at IS NULL AND ? = 1""",
                (automation_id, recipient_id, account_id or 0,
                 None if follows is None else int(follows)),
            )
            return cursor.rowcount == 1

    def disconnect_instagram_account(self, account_id: int) -> tuple[bool, str]:
        with self._connect() as db:
            used = db.execute("SELECT COUNT(*) FROM automations WHERE instagram_account_id = ? AND archived = 0", (account_id,)).fetchone()[0]
            if used:
                return False, f"Акаунт використовується у {used} неархівованих автоматизаціях. Спершу перенесіть або архівуйте їх."
            db.execute(
                """UPDATE instagram_accounts SET status = 'disconnected', access_token_encrypted = '',
                   is_default = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?""", (account_id,),
            )
            replacement = db.execute("SELECT id FROM instagram_accounts WHERE status != 'disconnected' ORDER BY id LIMIT 1").fetchone()
            if replacement and not db.execute("SELECT 1 FROM instagram_accounts WHERE is_default = 1").fetchone():
                db.execute("UPDATE instagram_accounts SET is_default = 1 WHERE id = ?", (replacement["id"],))
            return True, "Instagram-акаунт безпечно відключено, його токен видалено."

    def create_oauth_state(self, state_hash: str, expires_at: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (int(datetime.now(timezone.utc).timestamp()),))
            db.execute("INSERT INTO oauth_states(state_hash, expires_at) VALUES (?, ?)", (state_hash, expires_at))

    def consume_oauth_state(self, state_hash: str, now: int) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT expires_at FROM oauth_states WHERE state_hash = ?", (state_hash,)).fetchone()
            db.execute("DELETE FROM oauth_states WHERE state_hash = ?", (state_hash,))
            return bool(row and int(row["expires_at"]) >= now)

    def ensure_default_automations(
        self,
        media_ids: frozenset[str],
        trigger_keywords: frozenset[str],
        confirmation_words: frozenset[str],
        public_reply_text: str,
        initial_dm_text: str,
        guide_message_text: str,
        pdf_path: Path,
    ) -> None:
        with self._connect() as db:
            if db.execute("SELECT COUNT(*) FROM automations").fetchone()[0]:
                return
            for index, media_id in enumerate(sorted(media_ids), 1):
                name = "Гайд — поточна автоматизація" if len(media_ids) == 1 else f"Гайд — автоматизація {index}"
                db.execute(
                    """INSERT INTO automations(
                           name, media_id, trigger_keywords, confirmation_words,
                           public_reply_text, initial_dm_text, guide_message_text, pdf_path
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, media_id, ",".join(sorted(trigger_keywords)), ",".join(sorted(confirmation_words)),
                     public_reply_text, initial_dm_text, guide_message_text, str(pdf_path)),
                )

    def list_automations(self, include_archived: bool = True) -> list[sqlite3.Row]:
        query = "SELECT * FROM automations"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY archived, enabled DESC, updated_at DESC, id DESC"
        with self._connect() as db:
            return list(db.execute(query))

    def get_automation(self, automation_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM automations WHERE id = ?", (automation_id,)).fetchone()

    def active_automations_for_media(self, media_id: str, instagram_account_id: int | None = None) -> list[sqlite3.Row]:
        with self._connect() as db:
            account_clause = " AND instagram_account_id = ?" if instagram_account_id is not None else ""
            params: tuple[object, ...] = (media_id, instagram_account_id) if instagram_account_id is not None else (media_id,)
            return list(db.execute(
                "SELECT * FROM automations WHERE media_id = ?" + account_clause + " AND enabled = 1 AND archived = 0 ORDER BY id",
                params,
            ))

    def save_automation(self, values: dict, automation_id: int | None = None) -> int:
        fields = ("name", "media_id", "media_permalink", "trigger_keywords", "confirmation_words",
                  "public_reply_text", "initial_dm_text", "guide_message_text", "pdf_path",
                  "conversation_rules", "require_follow", "follow_required_message", "enabled", "instagram_account_id")
        defaults = {"conversation_rules": "[]", "require_follow": 0,
                    "follow_required_message": "Підпишіться на акаунт і повторіть відповідь."}
        params = [values.get(field, defaults.get(field)) for field in fields]
        with self._connect() as db:
            if automation_id is None:
                marks = ", ".join("?" for _ in fields)
                cursor = db.execute(f"INSERT INTO automations({', '.join(fields)}) VALUES ({marks})", params)
                return int(cursor.lastrowid)
            assignments = ", ".join(f"{field} = ?" for field in fields)
            db.execute(
                f"UPDATE automations SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*params, automation_id),
            )
            return automation_id

    def duplicate_automation(self, automation_id: int) -> int | None:
        row = self.get_automation(automation_id)
        if row is None:
            return None
        values = {key: row[key] for key in (
            "media_id", "media_permalink", "trigger_keywords", "confirmation_words",
            "public_reply_text", "initial_dm_text", "guide_message_text", "pdf_path",
            "conversation_rules", "require_follow", "follow_required_message", "instagram_account_id",
        )}
        values.update(name=f"{row['name']} — копія", enabled=0)
        return self.save_automation(values)

    def set_automation_flags(self, automation_id: int, *, enabled: bool | None = None, archived: bool | None = None) -> None:
        updates: list[str] = []
        params: list[object] = []
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(int(enabled))
        if archived is not None:
            updates.append("archived = ?")
            params.append(int(archived))
        if not updates:
            return
        updates.append("updated_at = CURRENT_TIMESTAMP")
        with self._connect() as db:
            db.execute(f"UPDATE automations SET {', '.join(updates)} WHERE id = ?", (*params, automation_id))

    def delete_automation(self, automation_id: int) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT pdf_path FROM automations WHERE id = ?", (automation_id,)).fetchone()
            if not row:
                return None
            db.execute("DELETE FROM automation_versions WHERE automation_id = ?", (automation_id,))
            db.execute("DELETE FROM automation_follow_tracking WHERE automation_id = ?", (automation_id,))
            db.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
            return str(row["pdf_path"])

    def record_webhook(self, payload: dict) -> None:
        entries = payload.get("entry", [])
        comment_count = 0
        messaging_count = 0
        for entry in entries:
            if entry.get("field") == "comments":
                comment_count += 1
            comment_count += sum(1 for change in entry.get("changes", []) if change.get("field") == "comments")
            messaging_count += len(entry.get("messaging", []))
        with self._connect() as db:
            db.execute(
                "INSERT INTO webhook_deliveries(object_type, entry_count, comment_count, messaging_count) VALUES (?, ?, ?, ?)",
                (str(payload.get("object", "")), len(entries), comment_count, messaging_count),
            )

    def claim_notification(self, event_key: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO notification_events(event_key) VALUES (?)",
                (event_key[:500],),
            )
            return cursor.rowcount == 1

    def release_notification(self, event_key: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM notification_events WHERE event_key = ?", (event_key[:500],))

    def ensure_comment(self, comment_id: str, media_id: str, username: str, automation_id: int,
                       comment_text: str = "", instagram_account_id: int | None = None) -> sqlite3.Row:
        with self._connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO comment_jobs(
                       comment_id, media_id, username, automation_id, comment_text, instagram_account_id
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (comment_id, media_id, username, automation_id, comment_text[:2000], instagram_account_id),
            )
            return db.execute("SELECT * FROM comment_jobs WHERE comment_id = ?", (comment_id,)).fetchone()

    def mark_public_done(self, comment_id: str) -> None:
        self._update_comment(comment_id, "public_done = 1, public_sent_at = CURRENT_TIMESTAMP, last_error = NULL")

    def mark_private_done(self, comment_id: str, recipient_id: str, automation_id: int,
                          instagram_account_id: int | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE comment_jobs SET private_done = 1, recipient_id = ?, automation_id = ?, instagram_account_id = ?,
                   private_sent_at = CURRENT_TIMESTAMP, last_error = NULL,
                   updated_at = CURRENT_TIMESTAMP WHERE comment_id = ?""",
                (recipient_id, automation_id, instagram_account_id, comment_id),
            )
            db.execute(
                """INSERT INTO recipients(recipient_id, comment_id, automation_id, state, instagram_account_id)
                   VALUES (?, ?, ?, 'waiting', ?)
                   ON CONFLICT(recipient_id) DO UPDATE SET comment_id = excluded.comment_id,
                   automation_id = excluded.automation_id, instagram_account_id = excluded.instagram_account_id,
                   state = 'waiting', updated_at = CURRENT_TIMESTAMP""",
                (recipient_id, comment_id, automation_id, instagram_account_id),
            )
            username_row = db.execute("SELECT username FROM comment_jobs WHERE comment_id = ?", (comment_id,)).fetchone()
            username = str(username_row["username"] or "") if username_row else ""
            db.execute(
                """INSERT INTO user_profiles(recipient_id, username, instagram_account_id) VALUES (?, ?, ?)
                   ON CONFLICT(recipient_id) DO UPDATE SET
                   instagram_account_id = COALESCE(excluded.instagram_account_id, user_profiles.instagram_account_id),
                   username = CASE WHEN excluded.username != '' THEN excluded.username ELSE user_profiles.username END,
                   last_seen_at = CURRENT_TIMESTAMP""", (recipient_id, username, instagram_account_id),
            )

    def mark_comment_error(self, comment_id: str, error: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE comment_jobs SET last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE comment_id = ?",
                (error[:1000], comment_id),
            )

    def _update_comment(self, comment_id: str, expression: str) -> None:
        with self._connect() as db:
            db.execute(
                f"UPDATE comment_jobs SET {expression}, updated_at = CURRENT_TIMESTAMP WHERE comment_id = ?",
                (comment_id,),
            )

    def recipient_context(self, recipient_id: str, instagram_account_id: int | None = None) -> sqlite3.Row | None:
        with self._connect() as db:
            clause = " AND r.instagram_account_id = ?" if instagram_account_id is not None else ""
            params: tuple[object, ...] = (recipient_id, instagram_account_id) if instagram_account_id is not None else (recipient_id,)
            return db.execute(
                """SELECT r.state AS recipient_state, r.automation_id AS selected_automation_id,
                          r.comment_id AS selected_comment_id,
                          COALESCE(u.manual_mode, 0) AS manual_mode, a.*
                   FROM recipients r JOIN automations a ON a.id = r.automation_id
                   LEFT JOIN user_profiles u ON u.recipient_id = r.recipient_id
                   WHERE r.recipient_id = ?""" + clause,
                params,
            ).fetchone()

    def mark_fulfilled(self, recipient_id: str, comment_id: str | None = None) -> None:
        with self._connect() as db:
            if comment_id:
                db.execute("""UPDATE recipients SET state = 'fulfilled', fulfilled_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP WHERE recipient_id = ? AND comment_id = ?""",
                           (recipient_id, comment_id))
            else:
                db.execute("""UPDATE recipients SET state = 'fulfilled', fulfilled_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP WHERE recipient_id = ?""", (recipient_id,))
            if comment_id:
                db.execute("""UPDATE comment_jobs SET fulfilled_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP WHERE comment_id = ?""", (comment_id,))
            else:
                db.execute(
                    """UPDATE comment_jobs SET fulfilled_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP WHERE comment_id =
                       (SELECT comment_id FROM recipients WHERE recipient_id = ?)""",
                    (recipient_id,),
                )

    def set_recipient_state(self, recipient_id: str, state: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE recipients SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE recipient_id = ?",
                       (state[:100], recipient_id))

    def history(self, automation_id: int | None = None, status: str = "", limit: int = 200) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[object] = []
        if automation_id:
            clauses.append("j.automation_id = ?")
            params.append(automation_id)
        if status == "error":
            clauses.append("j.last_error IS NOT NULL")
        elif status == "fulfilled":
            clauses.append("j.fulfilled_at IS NOT NULL")
        elif status == "waiting":
            clauses.append("j.private_done = 1 AND j.fulfilled_at IS NULL AND COALESCE(r.state, '') = 'waiting'")
        elif status == "partial":
            clauses.append("(j.public_done = 0 OR j.private_done = 0) AND j.last_error IS NULL")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with self._connect() as db:
            return list(db.execute(
                """SELECT j.*, a.name AS automation_name, a.media_permalink,
                          CASE WHEN j.fulfilled_at IS NOT NULL THEN 'fulfilled' ELSE r.state END AS recipient_state,
                          j.fulfilled_at
                   FROM comment_jobs j
                   LEFT JOIN automations a ON a.id = j.automation_id
                   LEFT JOIN recipients r ON r.comment_id = j.comment_id""" + where +
                " ORDER BY j.created_at DESC, j.comment_id DESC LIMIT ?", params,
            ))

    def analytics(self) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
        summary_sql = """SELECT COUNT(*) AS comments,
                   COALESCE(SUM(public_done), 0) AS public_sent,
                   COALESCE(SUM(private_done), 0) AS private_sent,
                   COALESCE(SUM(CASE WHEN j.fulfilled_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS fulfilled,
                   COALESCE(SUM(CASE WHEN j.last_error IS NOT NULL THEN 1 ELSE 0 END), 0) AS errors,
                   (SELECT COUNT(*) FROM automation_follow_tracking t
                    WHERE t.converted_at IS NOT NULL) AS confirmed_follows
               FROM comment_jobs j LEFT JOIN recipients r ON r.comment_id = j.comment_id"""
        per_sql = """SELECT a.id, a.name, COUNT(j.comment_id) AS comments,
                   COALESCE(SUM(j.private_done), 0) AS private_sent,
                   COALESCE(SUM(CASE WHEN j.fulfilled_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS fulfilled,
                   COALESCE(SUM(CASE WHEN j.last_error IS NOT NULL THEN 1 ELSE 0 END), 0) AS errors,
                   (SELECT COUNT(*) FROM automation_follow_tracking t
                    WHERE t.automation_id = a.id AND t.converted_at IS NOT NULL) AS confirmed_follows
               FROM automations a
               LEFT JOIN comment_jobs j ON j.automation_id = a.id
               LEFT JOIN recipients r ON r.comment_id = j.comment_id
               GROUP BY a.id ORDER BY comments DESC, a.name"""
        with self._connect() as db:
            return db.execute(summary_sql).fetchone(), list(db.execute(per_sql))

    def add_document(self, title: str, original_name: str, file_path: str, size_bytes: int,
                     folder: str = "", stored_name: str = "") -> int:
        with self._connect() as db:
            db.execute(
                """INSERT INTO documents(title, original_name, file_path, size_bytes, folder, stored_name)
                   VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(file_path) DO UPDATE SET
                   title = excluded.title, original_name = excluded.original_name,
                   size_bytes = excluded.size_bytes, folder = excluded.folder,
                   stored_name = excluded.stored_name""",
                (title[:120], original_name[:255], file_path, size_bytes, folder[:800], stored_name[:255]),
            )
            return int(db.execute("SELECT id FROM documents WHERE file_path = ?", (file_path,)).fetchone()[0])

    def ensure_document(self, file_path: str, title: str | None = None) -> int | None:
        path = Path(file_path)
        if not path.is_file():
            return None
        return self.add_document(title or path.stem, path.name, str(path), path.stat().st_size,
                                 "", path.name)

    def list_documents(self, instagram_account_id: int | None = None) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute(
                """SELECT d.*,
                          (SELECT COUNT(*) FROM automations a WHERE a.pdf_path = d.file_path) AS use_count,
                          (SELECT GROUP_CONCAT(DISTINCT ia.username)
                           FROM automations a JOIN instagram_accounts ia ON ia.id = a.instagram_account_id
                           WHERE a.pdf_path = d.file_path) AS account_names,
                          (SELECT GROUP_CONCAT(DISTINCT ia.id)
                           FROM automations a JOIN instagram_accounts ia ON ia.id = a.instagram_account_id
                           WHERE a.pdf_path = d.file_path) AS account_ids
                   FROM documents d
                   WHERE (? IS NULL OR EXISTS (
                       SELECT 1 FROM automations a
                       WHERE a.pdf_path = d.file_path AND a.instagram_account_id = ?
                   ))
                   ORDER BY d.created_at DESC, d.id DESC""",
                (instagram_account_id, instagram_account_id),
            ))

    def get_document(self, document_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()

    def delete_document(self, document_id: int) -> str | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT d.file_path, COUNT(a.id) AS use_count FROM documents d
                   LEFT JOIN automations a ON a.pdf_path = d.file_path
                   WHERE d.id = ? GROUP BY d.id""", (document_id,),
            ).fetchone()
            if row is None or row["use_count"]:
                return None
            db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return str(row["file_path"])

    def move_document(self, document_id: int, new_path: str, folder: str, stored_name: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT file_path FROM documents WHERE id = ?", (document_id,)).fetchone()
            if row is None:
                return None
            old_path = str(row["file_path"])
            db.execute("UPDATE automations SET pdf_path = ?, updated_at = CURRENT_TIMESTAMP WHERE pdf_path = ?",
                       (new_path, old_path))
            db.execute("""UPDATE documents SET file_path = ?, folder = ?, stored_name = ?
                       WHERE id = ?""", (new_path, folder[:800], stored_name[:255], document_id))
            return old_path

    def create_backup(self, directory: Path, label: str = "manual") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = directory / f"fraxler-{label}-{stamp}.sqlite3"
        source = self._connect()
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        target.chmod(0o600)
        return target

    def message_state(self, message_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT state FROM message_events WHERE message_id = ?", (message_id,)).fetchone()
            return row["state"] if row else None

    def mark_message(self, message_id: str, sender_id: str, state: str, error: str | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO message_events(message_id, sender_id, state, last_error) VALUES (?, ?, ?, ?)
                   ON CONFLICT(message_id) DO UPDATE SET state = excluded.state,
                   last_error = excluded.last_error, updated_at = CURRENT_TIMESTAMP""",
                (message_id, sender_id, state, error[:1000] if error else None),
            )

    def schedule_retry(self, unique_key: str, kind: str, payload: dict,
                       automation_id: int | None, recipient_id: str | None, error: str) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO retry_jobs(unique_key, kind, payload, automation_id, recipient_id, last_error)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(unique_key) DO UPDATE SET state = 'pending', last_error = excluded.last_error,
                   next_attempt_at = 0, updated_at = CURRENT_TIMESTAMP""",
                (unique_key, kind, json.dumps(payload, ensure_ascii=False), automation_id,
                 recipient_id, error[:1000]),
            )

    def due_retries(self, now: int, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute(
                """SELECT * FROM retry_jobs WHERE state = 'pending' AND next_attempt_at <= ?
                   ORDER BY next_attempt_at, id LIMIT ?""", (now, limit),
            ))

    def complete_retry(self, retry_id: int) -> None:
        with self._connect() as db:
            db.execute("UPDATE retry_jobs SET state = 'done', last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (retry_id,))

    def fail_retry(self, retry_id: int, attempts: int, next_attempt_at: int, error: str) -> None:
        state = "failed" if attempts >= 8 else "pending"
        with self._connect() as db:
            db.execute(
                """UPDATE retry_jobs SET state = ?, attempts = ?, next_attempt_at = ?,
                   last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (state, attempts, next_attempt_at, error[:1000], retry_id),
            )

    def list_retries(self, include_done: bool = False, limit: int = 200) -> list[sqlite3.Row]:
        where = "" if include_done else " WHERE r.state != 'done'"
        with self._connect() as db:
            return list(db.execute(
                """SELECT r.*, a.name AS automation_name FROM retry_jobs r
                   LEFT JOIN automations a ON a.id = r.automation_id""" + where +
                " ORDER BY CASE r.state WHEN 'failed' THEN 0 ELSE 1 END, r.updated_at DESC LIMIT ?", (limit,),
            ))

    def retry_now(self, retry_id: int) -> None:
        with self._connect() as db:
            db.execute("""UPDATE retry_jobs SET state = 'pending', attempts = 0,
                       next_attempt_at = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?""", (retry_id,))

    def log_direct(self, recipient_id: str, direction: str, source: str, text: str,
                   message_id: str | None = None, state: str = "sent", error: str | None = None,
                   attachments: list[dict] | None = None, instagram_account_id: int | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO message_log(message_id, recipient_id, direction, source, text, state, last_error, attachments, instagram_account_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(message_id) DO NOTHING""",
                (message_id, recipient_id, direction, source, text[:4000], state,
                 error[:1000] if error else None, json.dumps(attachments or [], ensure_ascii=False), instagram_account_id),
            )
            db.execute(
                """INSERT INTO user_profiles(recipient_id, instagram_account_id) VALUES (?, ?)
                   ON CONFLICT(recipient_id) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP,
                   instagram_account_id = COALESCE(excluded.instagram_account_id, user_profiles.instagram_account_id)""",
                (recipient_id, instagram_account_id),
            )

    def account_id_for_user(self, recipient_id: str) -> int | None:
        with self._connect() as db:
            row = db.execute("SELECT instagram_account_id FROM user_profiles WHERE recipient_id = ?", (recipient_id,)).fetchone()
            return int(row[0]) if row and row[0] is not None else None

    def messages_for_user(self, recipient_id: str, instagram_account_id: int | None = None,
                          limit: int = 300) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute(
                """SELECT * FROM message_log WHERE recipient_id = ?
                   AND (? IS NULL OR instagram_account_id = ?)
                   ORDER BY id ASC LIMIT ?""",
                (recipient_id, instagram_account_id, instagram_account_id, limit),
            ))

    def list_users(self, search: str = "", instagram_account_id: int | None = None) -> list[sqlite3.Row]:
        pattern = f"%{search}%"
        with self._connect() as db:
            return list(db.execute(
                """SELECT u.*, COUNT(m.id) AS message_count,
                          MAX(m.created_at) AS last_message_at,
                          ia.username AS account_username,
                          ia.profile_picture_url AS account_profile_picture_url
                   FROM user_profiles u
                   LEFT JOIN message_log m ON m.recipient_id = u.recipient_id
                       AND (u.instagram_account_id IS NULL OR m.instagram_account_id = u.instagram_account_id)
                   LEFT JOIN instagram_accounts ia ON ia.id = u.instagram_account_id
                   WHERE (? = '' OR u.username LIKE ? OR u.recipient_id LIKE ? OR u.tags LIKE ?)
                     AND (? IS NULL OR u.instagram_account_id = ?)
                   GROUP BY u.recipient_id
                   ORDER BY COALESCE(MAX(m.created_at), u.last_seen_at) DESC""",
                (search, pattern, pattern, pattern, instagram_account_id, instagram_account_id),
            ))

    def get_user(self, recipient_id: str, instagram_account_id: int | None = None) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute(
                """SELECT u.*, ia.username AS account_username,
                          ia.profile_picture_url AS account_profile_picture_url
                   FROM user_profiles u LEFT JOIN instagram_accounts ia ON ia.id = u.instagram_account_id
                   WHERE u.recipient_id = ? AND (? IS NULL OR u.instagram_account_id = ?)""",
                (recipient_id, instagram_account_id, instagram_account_id),
            ).fetchone()

    def update_user(self, recipient_id: str, *, tags: str, notes: str, manual_mode: bool,
                    instagram_account_id: int | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE user_profiles SET tags = ?, notes = ?, manual_mode = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE recipient_id = ?
                   AND (? IS NULL OR instagram_account_id = ?)""",
                (tags[:500], notes[:3000], int(manual_mode), recipient_id,
                 instagram_account_id, instagram_account_id),
            )

    def user_manual_mode(self, recipient_id: str) -> bool:
        row = self.get_user(recipient_id)
        return bool(row and row["manual_mode"])

    def update_follow_status(self, recipient_id: str, follows: bool | None,
                             username: str = "", profile_pic_url: str = "",
                             instagram_account_id: int | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO user_profiles(recipient_id, username, follows_business,
                          follow_checked_at, profile_pic_url, instagram_account_id)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                   ON CONFLICT(recipient_id) DO UPDATE SET
                   follows_business = excluded.follows_business,
                   follow_checked_at = CURRENT_TIMESTAMP,
                   username = CASE WHEN excluded.username != '' THEN excluded.username ELSE user_profiles.username END,
                   profile_pic_url = CASE WHEN excluded.profile_pic_url != '' THEN excluded.profile_pic_url ELSE user_profiles.profile_pic_url END,
                   instagram_account_id = COALESCE(excluded.instagram_account_id, user_profiles.instagram_account_id)""",
                (recipient_id, username[:200], None if follows is None else int(follows),
                 profile_pic_url[:1000], instagram_account_id),
            )

    def delete_user_data(self, recipient_id: str, instagram_account_id: int | None = None) -> None:
        with self._connect() as db:
            comment_ids = [row[0] for row in db.execute(
                """SELECT comment_id FROM comment_jobs WHERE recipient_id = ?
                     AND (? IS NULL OR instagram_account_id = ?)
                   UNION SELECT comment_id FROM recipients WHERE recipient_id = ?
                     AND (? IS NULL OR instagram_account_id = ?)""",
                (recipient_id, instagram_account_id, instagram_account_id,
                 recipient_id, instagram_account_id, instagram_account_id),
            )]
            db.execute("DELETE FROM message_log WHERE recipient_id = ? AND (? IS NULL OR instagram_account_id = ?)",
                       (recipient_id, instagram_account_id, instagram_account_id))
            db.execute("""DELETE FROM retry_jobs WHERE recipient_id = ? AND (? IS NULL OR automation_id IN (
                       SELECT id FROM automations WHERE instagram_account_id = ?))""",
                       (recipient_id, instagram_account_id, instagram_account_id))
            db.execute("DELETE FROM recipients WHERE recipient_id = ? AND (? IS NULL OR instagram_account_id = ?)",
                       (recipient_id, instagram_account_id, instagram_account_id))
            if comment_ids:
                marks = ",".join("?" for _ in comment_ids)
                db.execute(f"DELETE FROM comment_jobs WHERE comment_id IN ({marks})", comment_ids)
            db.execute("DELETE FROM user_profiles WHERE recipient_id = ? AND (? IS NULL OR instagram_account_id = ?)",
                       (recipient_id, instagram_account_id, instagram_account_id))
            db.execute(
                """DELETE FROM automation_follow_tracking WHERE recipient_id = ?
                   AND (? IS NULL OR instagram_account_id = ?)""",
                (recipient_id, instagram_account_id, instagram_account_id),
            )
            if instagram_account_id is None:
                db.execute("DELETE FROM message_events WHERE sender_id = ?", (recipient_id,))

    def set_health(self, key: str, status: str, detail: str) -> str | None:
        with self._connect() as db:
            previous = db.execute("SELECT status FROM health_checks WHERE key = ?", (key,)).fetchone()
            db.execute(
                """INSERT INTO health_checks(key, status, detail) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET status = excluded.status, detail = excluded.detail,
                   checked_at = CURRENT_TIMESTAMP""", (key, status, detail[:1000]),
            )
            return str(previous["status"]) if previous else None

    def list_health(self) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute("SELECT * FROM health_checks ORDER BY key"))

    def latest_webhook_at(self) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT MAX(created_at) AS value FROM webhook_deliveries").fetchone()
            return str(row["value"]) if row and row["value"] else None

    def save_version(self, automation_id: int, status: str, values: dict) -> int:
        snapshot = json.dumps(values, ensure_ascii=False)
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO automation_versions(automation_id, status, snapshot) VALUES (?, ?, ?)",
                (automation_id, status, snapshot),
            )
            return int(cursor.lastrowid)

    def list_versions(self, automation_id: int) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute(
                "SELECT * FROM automation_versions WHERE automation_id = ? ORDER BY id DESC",
                (automation_id,),
            ))

    def get_version(self, version_id: int) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM automation_versions WHERE id = ?", (version_id,)).fetchone()

    def cleanup_old_data(self, days: int) -> dict[str, int]:
        days = max(7, min(days, 3650))
        modifier = f"-{days} days"
        counts: dict[str, int] = {}
        with self._connect() as db:
            for table in ("message_log", "message_events", "webhook_deliveries", "retry_jobs", "notification_events"):
                cursor = db.execute(f"DELETE FROM {table} WHERE created_at < datetime('now', ?)", (modifier,))
                counts[table] = cursor.rowcount
            old_comments = [row[0] for row in db.execute(
                "SELECT comment_id FROM comment_jobs WHERE created_at < datetime('now', ?)", (modifier,)
            )]
            if old_comments:
                marks = ",".join("?" for _ in old_comments)
                db.execute(f"DELETE FROM recipients WHERE comment_id IN ({marks})", old_comments)
                db.execute(f"DELETE FROM comment_jobs WHERE comment_id IN ({marks})", old_comments)
            counts["comment_jobs"] = len(old_comments)
            cursor = db.execute(
                """DELETE FROM user_profiles WHERE last_seen_at < datetime('now', ?)
                   AND NOT EXISTS (SELECT 1 FROM message_log m WHERE m.recipient_id = user_profiles.recipient_id)
                   AND NOT EXISTS (SELECT 1 FROM recipients r WHERE r.recipient_id = user_profiles.recipient_id)""",
                (modifier,),
            )
            counts["user_profiles"] = cursor.rowcount
            db.execute("DELETE FROM admin_sessions WHERE expires_at < strftime('%s','now')")
        return counts

    def get_setting(self, key: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT value FROM admin_settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO admin_settings(key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )

    def create_session(self, expires_at: int) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            db.execute("DELETE FROM admin_sessions WHERE expires_at < strftime('%s','now')")
            db.execute("INSERT INTO admin_sessions(token_hash, csrf_token, expires_at) VALUES (?, ?, ?)",
                       (token_hash, csrf, expires_at))
        return token, csrf

    def session_csrf(self, token: str, now: int) -> str | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT csrf_token FROM admin_sessions WHERE token_hash = ? AND expires_at >= ?",
                (token_hash, now),
            ).fetchone()
            return str(row["csrf_token"]) if row else None

    def delete_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            db.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))
