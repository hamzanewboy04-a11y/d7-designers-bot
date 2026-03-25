from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    admin_ids: list[int]
    report_hour_utc: int
    google_sheet_id: str | None
    google_service_account_json: str | None


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        raise ValueError(
            "BOT_TOKEN is required. Set BOT_TOKEN (or TELEGRAM_BOT_TOKEN) in environment variables."
        )

    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()]

    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "d7_bot.sqlite3"),
        admin_ids=admin_ids,
        report_hour_utc=int(os.getenv("REPORT_HOUR_UTC", "8")),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID"),
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
    )
