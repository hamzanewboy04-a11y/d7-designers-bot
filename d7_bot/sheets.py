from __future__ import annotations

import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from d7_bot.db import Designer


class GoogleSheetsExporter:
    def __init__(self, sheet_id: str | None, service_account_json: str | None) -> None:
        self.sheet_id = sheet_id
        self.service_account_json = service_account_json
        self.is_enabled = bool(sheet_id and service_account_json)
        self._client = None

    def _get_client(self):
        if not self.is_enabled:
            return None
        if self._client:
            return self._client
        info = json.loads(self.service_account_json)
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._client = gspread.authorize(creds)
        return self._client

    async def sync_designers(self, designers: list[Designer]) -> None:
        client = self._get_client()
        if not client:
            return
        sh = client.open_by_key(self.sheet_id)
        ws = sh.worksheet("designers") if "designers" in [w.title for w in sh.worksheets()] else sh.add_worksheet("designers", rows=200, cols=10)
        rows = [["telegram_id", "username", "d7_nick", "experience", "formats", "portfolio", "wallet"]]
        for d in designers:
            rows.append([
                d.telegram_id,
                d.username or "",
                d.d7_nick,
                d.experience,
                ", ".join(d.formats),
                ", ".join(d.portfolio),
                d.wallet,
            ])
        ws.clear()
        ws.update(rows)

    async def append_report_rows(self, designer: Designer, report_date: str, lines: list[str]) -> None:
        client = self._get_client()
        if not client:
            return
        sh = client.open_by_key(self.sheet_id)
        ws = sh.worksheet("reports") if "reports" in [w.title for w in sh.worksheets()] else sh.add_worksheet("reports", rows=1000, cols=8)
        if ws.row_count == 1000 and ws.acell("A1").value is None:
            ws.append_row(["created_at", "report_date", "designer", "task_code", "cost", "wallet"])

        for line in lines:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            task_code, cost = parts
            ws.append_row([
                datetime.utcnow().isoformat(),
                report_date,
                designer.d7_nick,
                task_code,
                cost,
                designer.wallet,
            ])
