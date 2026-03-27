from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import partial
from typing import TYPE_CHECKING, Any

import gspread
from google.oauth2.service_account import Credentials

from d7_bot.db import Designer

if TYPE_CHECKING:
    from d7_bot.handlers.report import ParsedTask
    from d7_bot.db import ReviewerEntry

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
        self, sh: gspread.Spreadsheet, title: str, rows: int = 1000, cols: int = 13
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
        self,
        designer: Designer,
        report_date: str,
        parsed_tasks: list["ParsedTask"],
    ) -> None:
        """Append task rows to the 'reports' sheet (v7: includes task_prefix/group/geo).

        Robustness guarantees:
        - Creates the 'reports' sheet if it does not exist.
        - Writes the canonical header exactly once (only when A1 is empty).
        - Always maps row values to the current header order to avoid column drift.
        """
        client = self._get_client()
        if not client:
            return

        now_iso = datetime.now(tz=timezone.utc).isoformat()

        _CANONICAL_HEADER = [
            "created_at", "report_date", "designer", "task_code",
            "cost_usdt", "wallet", "payment_status", "paid_at", "paid_by",
            "payment_comment", "task_prefix", "task_group", "task_geo",
        ]

        def _append() -> None:
            sh = client.open_by_key(self.sheet_id)  # type: ignore[arg-type]
            ws = self._get_or_create_worksheet(sh, "reports", rows=5000, cols=len(_CANONICAL_HEADER))

            # Determine current header; write canonical header if A1 is empty.
            header_cell = ws.acell("A1").value
            if not header_cell:
                ws.update("A1", [_CANONICAL_HEADER])
                header = _CANONICAL_HEADER[:]
            else:
                # Read the full first row to respect any existing column order.
                header = ws.row_values(1)

            # Build a lookup from column name → 0-based index in header.
            col_idx: dict[str, int] = {name: i for i, name in enumerate(header)}

            for pt in parsed_tasks:
                data_map = {
                    "created_at":      now_iso,
                    "report_date":     report_date,
                    "designer":        designer.d7_nick,
                    "task_code":       pt.task_code,
                    "cost_usdt":       pt.cost_usdt,
                    "wallet":          designer.wallet,
                    "payment_status":  "pending",
                    "paid_at":         "",
                    "paid_by":         "",
                    "payment_comment": "",
                    "task_prefix":     pt.task_prefix,
                    "task_group":      pt.task_group,
                    "task_geo":        pt.task_geo,
                }
                row = [""] * len(header)
                for col_name, value in data_map.items():
                    if col_name in col_idx:
                        row[col_idx[col_name]] = value
                ws.append_row(row, value_input_option="USER_ENTERED")

        try:
            await self._run(_append)
        except Exception as exc:
            logger.error("GoogleSheets append_report_rows failed: %s", exc)

    async def append_reviewer_row(
        self,
        designer: Designer,
        report_date: str,
        review_geo: str,
        review_count: int,
        unit_price: float,
        total_usdt: float,
        comment: str = "",
    ) -> None:
        client = self._get_client()
        if not client:
            return

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        _CANONICAL_HEADER = [
            "created_at", "report_date", "designer", "entry_type", "task_code",
            "cost_usdt", "wallet", "payment_status", "paid_at", "paid_by",
            "payment_comment", "task_prefix", "task_group", "task_geo",
            "review_geo", "review_count", "unit_price", "comment",
        ]

        def _append() -> None:
            sh = client.open_by_key(self.sheet_id)  # type: ignore[arg-type]
            ws = self._get_or_create_worksheet(sh, "reports", rows=5000, cols=len(_CANONICAL_HEADER))
            header_cell = ws.acell("A1").value
            if not header_cell:
                ws.update("A1", [_CANONICAL_HEADER])
                header = _CANONICAL_HEADER[:]
            else:
                header = ws.row_values(1)
            col_idx: dict[str, int] = {name: i for i, name in enumerate(header)}
            data_map = {
                "created_at": now_iso,
                "report_date": report_date,
                "designer": designer.d7_nick,
                "entry_type": "reviewer_piecework",
                "task_code": f"reviews:{review_geo}:{review_count}",
                "cost_usdt": total_usdt,
                "wallet": designer.wallet,
                "payment_status": "pending",
                "paid_at": "",
                "paid_by": "",
                "payment_comment": "",
                "task_prefix": "",
                "task_group": "",
                "task_geo": "",
                "review_geo": review_geo,
                "review_count": review_count,
                "unit_price": unit_price,
                "comment": comment,
            }
            row = [""] * len(header)
            for col_name, value in data_map.items():
                if col_name in col_idx:
                    row[col_idx[col_name]] = value
            ws.append_row(row, value_input_option="USER_ENTERED")

        try:
            await self._run(_append)
        except Exception as exc:
            logger.error("GoogleSheets append_reviewer_row failed: %s", exc)

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
            ws = self._get_or_create_worksheet(sh, "reports", rows=5000, cols=13)

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
