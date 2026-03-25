from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from d7_bot.db import Designer

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsExporter:
    def __init__(self, sheet_id: str | None, service_account_json: str | None) -> None:
        self.sheet_id = sheet_id
        self.service_account_json = service_account_json
        self.is_enabled = bool(sheet_id and service_account_json)
        self._client: gspread.Client | None = None

    # ── internal helpers ───────────────────────────────────────────────────

    def _get_client(self) -> gspread.Client | None:
        if not self.is_enabled:
            return None
        if self._client:
            return self._client
        info = json.loads(self.service_account_json)  # type: ignore[arg-type]
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
        self._client = gspread.authorize(creds)
        return self._client

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous gspread call in the default executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    def _get_or_create_worksheet(
        self, sh: gspread.Spreadsheet, title: str, rows: int = 1000, cols: int = 10
    ) -> gspread.Worksheet:
        existing_titles = [w.title for w in sh.worksheets()]
        if title in existing_titles:
            return sh.worksheet(title)
        return sh.add_worksheet(title, rows=rows, cols=cols)

    # ── public API ─────────────────────────────────────────────────────────

    async def sync_designers(self, designers: list[Designer]) -> None:
        """Overwrite the 'designers' sheet with current designer list."""
        client = self._get_client()
        if not client:
            return

        def _sync() -> None:
            sh = client.open_by_key(self.sheet_id)  # type: ignore[arg-type]
            ws = self._get_or_create_worksheet(sh, "designers", rows=500, cols=8)
            rows = [
                ["telegram_id", "username", "d7_nick", "role", "wallet", "updated_at"]
            ]
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            for d in designers:
                rows.append(
                    [
                        d.telegram_id,
                        d.username or "",
                        d.d7_nick,
                        d.role or "",
                        d.wallet,
                        now_iso,
                    ]
                )
            ws.clear()
            ws.update(rows)

        try:
            await self._run(_sync)
        except Exception as exc:
            logger.error("GoogleSheets sync_designers failed: %s", exc)

    async def append_report_rows(
        self, designer: Designer, report_date: str, lines: list[str]
    ) -> None:
        """Append task rows to the 'reports' sheet."""
        client = self._get_client()
        if not client:
            return

        now_iso = datetime.now(tz=timezone.utc).isoformat()

        def _append() -> None:
            sh = client.open_by_key(self.sheet_id)  # type: ignore[arg-type]
            ws = self._get_or_create_worksheet(sh, "reports", rows=5000, cols=12)

            # Check if header row exists (cell A1 is empty → write header)
            header_cell = ws.acell("A1").value
            if not header_cell:
                ws.append_row(
                    [
                        "created_at", "report_date", "designer", "task_code",
                        "cost_usdt", "wallet", "payment_status", "paid_at", "paid_by",
                        "payment_comment",
                    ]
                )

            for line in lines:
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                task_code, cost_str = parts
                try:
                    cost = float(cost_str)
                except ValueError:
                    cost = cost_str  # type: ignore[assignment]
                ws.append_row(
                    [
                        now_iso, report_date, designer.d7_nick, task_code,
                        cost, designer.wallet, "pending", "", "", "",
                    ]
                )

        try:
            await self._run(_append)
        except Exception as exc:
            logger.error("GoogleSheets append_report_rows failed: %s", exc)

    async def update_payment_status(
        self,
        designer_nick: str,
        report_date: str,
        status: str,
        paid_at: str,
        paid_by: str,
        payment_comment: str = "",
    ) -> None:
        """Update payment_status, paid_at, paid_by, payment_comment for matching rows in 'reports' sheet."""
        client = self._get_client()
        if not client:
            return

        def _update() -> None:
            sh = client.open_by_key(self.sheet_id)  # type: ignore[arg-type]
            ws = self._get_or_create_worksheet(sh, "reports", rows=5000, cols=12)

            all_values = ws.get_all_values()
            if not all_values:
                return

            header = all_values[0]
            try:
                col_designer = header.index("designer")
                col_date = header.index("report_date")
                col_status = header.index("payment_status")
                col_paid_at = header.index("paid_at")
                col_paid_by = header.index("paid_by")
            except ValueError:
                # Header not set up correctly, skip
                return

            # payment_comment column may not exist in old sheets — handle gracefully
            col_comment: int | None = None
            if "payment_comment" in header:
                col_comment = header.index("payment_comment")

            updates = []
            for i, row in enumerate(all_values[1:], start=2):
                if len(row) > max(col_designer, col_date):
                    if row[col_designer] == designer_nick and row[col_date] == report_date:
                        updates.append((i, col_status + 1, status))
                        updates.append((i, col_paid_at + 1, paid_at))
                        updates.append((i, col_paid_by + 1, paid_by))
                        if col_comment is not None:
                            updates.append((i, col_comment + 1, payment_comment))

            for row_i, col_i, val in updates:
                ws.update_cell(row_i, col_i, val)

        try:
            await self._run(_update)
        except Exception as exc:
            logger.error("GoogleSheets update_payment_status failed: %s", exc)
