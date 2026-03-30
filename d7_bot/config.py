from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    database_url: str | None
    admin_ids: list[int]
    report_hour_utc: int
    google_sheet_id: str | None
    google_service_account_json: str | None
    web_session_secret: str
    web_enabled: bool = True


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        raise ValueError("BOT_TOKEN is required.")

    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()]

    # Support inline JSON string or file path for service account
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json and not sa_json.strip().startswith("{"):
        # Treat as file path
        try:
            with open(sa_json) as f:
                sa_json = f.read()
        except OSError:
            sa_json = None

    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "d7_bot.sqlite3"),
        database_url=os.getenv("DATABASE_URL"),
        admin_ids=admin_ids,
        report_hour_utc=int(os.getenv("REPORT_HOUR_UTC", "8")),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID"),
        google_service_account_json=sa_json,
        web_session_secret=os.getenv("WEB_SESSION_SECRET", "change-me-d7-web-session-secret"),
        web_enabled=os.getenv("WEB_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"},
    )
