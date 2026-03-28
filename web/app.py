from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from d7_bot.config import load_config
from d7_bot.db import Database
from services.employees import EmployeeService
from services.payroll import PayrollService
from services.reviewer import ReviewerService
from services.smm import SmmService
from storage.repositories import PostgresDashboardReadRepository, PostgresEmployeeReadRepository
from storage.session import create_session_factory

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)

app = FastAPI(title="D7 Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

config = load_config()
db = Database(config.db_path)
_db_ready = False
_db_error: str | None = None
_pg_engine = None
_pg_session_factory = None

if config.database_url:
    _pg_engine, _pg_session_factory = create_session_factory(config.database_url)


async def ensure_db() -> tuple[bool, str | None]:
    global _db_ready, _db_error
    if _db_ready:
        return True, None
    try:
        if _pg_session_factory is not None:
            async with _pg_session_factory() as session:
                await session.execute(text("SELECT 1"))
        else:
            await db.init()
        _db_ready = True
        _db_error = None
        return True, None
    except Exception as exc:
        _db_error = str(exc)
        logger.error("Web DB init failed: %s", exc)
        return False, _db_error


@app.on_event("startup")
async def startup() -> None:
    ok, err = await ensure_db()
    if ok:
        logger.info("Web admin DB init complete.")
    else:
        logger.warning("Web admin started in degraded mode (db unavailable): %s", err)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _pg_engine is not None:
        await _pg_engine.dispose()


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    ok, _ = await ensure_db()
    return "ok" if ok else "degraded"


@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)

    if _pg_session_factory is not None:
        payroll = PayrollService(PostgresDashboardReadRepository(_pg_session_factory))
        employees = EmployeeService(PostgresEmployeeReadRepository(_pg_session_factory))
    else:
        payroll = PayrollService(db)
        employees = EmployeeService(db)

    stats = await payroll.dashboard_stats()
    role_counts = await employees.role_counts()
    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": "Dashboard", "stats": stats, "role_counts": role_counts},
    )


@app.get("/admin/employees", response_class=HTMLResponse)
async def employees_page(request: Request):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)

    if _pg_session_factory is not None:
        service = EmployeeService(PostgresEmployeeReadRepository(_pg_session_factory))
    else:
        service = EmployeeService(db)

    employees = await service.list_active()
    return TEMPLATES.TemplateResponse(
        "employees.html",
        {"request": request, "title": "Employees", "employees": employees},
    )


@app.get("/admin/smm/assignments", response_class=HTMLResponse)
async def smm_assignments_page(request: Request):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = SmmService(db)
    assignments = await service.list_assignments()
    return TEMPLATES.TemplateResponse(
        "smm_assignments.html",
        {"request": request, "title": "SMM Assignments", "assignments": assignments},
    )


@app.get("/admin/reviewer/entries", response_class=HTMLResponse)
async def reviewer_entries_page(request: Request):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = ReviewerService(db)
    entries = await service.pending_entries()
    return TEMPLATES.TemplateResponse(
        "reviewer_entries.html",
        {"request": request, "title": "Reviewer Entries", "entries": entries},
    )


@app.get("/admin/payouts", response_class=HTMLResponse)
async def payouts_page(request: Request):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    reviewer = ReviewerService(db)
    smm = SmmService(db)
    return TEMPLATES.TemplateResponse(
        "payouts.html",
        {
            "request": request,
            "title": "Payouts",
            "reviewer_batches": await reviewer.pending_batches(),
            "smm_batches": await smm.pending_batches(),
        },
    )
