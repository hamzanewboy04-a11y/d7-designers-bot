from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from d7_bot.config import load_config
from d7_bot.db import Database
from services.employees import EmployeeService
from services.payroll import PayrollService
from services.reviewer import ReviewerService
from services.reviewer_domain import ReviewerDomainService
from services.smm import SmmService
from services.smm_domain import SmmDomainService
from storage.repositories import (
    PostgresDashboardReadRepository,
    PostgresEmployeeReadRepository,
    PostgresReviewerReadRepository,
    PostgresSmmReadRepository,
)
from storage.repositories.reviewer_domain import PostgresReviewerDomainRepository
from storage.repositories.smm_domain import PostgresSmmDomainRepository
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


def reviewer_read_service() -> ReviewerService:
    if _pg_session_factory is not None:
        return ReviewerService(PostgresReviewerReadRepository(_pg_session_factory))
    return ReviewerService(db)


def reviewer_domain_service() -> ReviewerDomainService:
    if _pg_session_factory is not None:
        return ReviewerDomainService(PostgresReviewerDomainRepository(_pg_session_factory, admin_fallback=db))
    return ReviewerDomainService(db)


def smm_domain_service() -> SmmDomainService:
    if _pg_session_factory is not None:
        return SmmDomainService(PostgresSmmDomainRepository(_pg_session_factory, admin_fallback=db))
    return SmmDomainService(db)


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
    storage_mode = {
        "reviewer": "postgres" if _pg_session_factory is not None else "sqlite",
        "smm": "postgres" if _pg_session_factory is not None else "sqlite",
        "legacy": "sqlite",
        "web_reads": "postgres" if _pg_session_factory is not None else "sqlite",
    }
    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "stats": stats,
            "role_counts": role_counts,
            "storage_mode": storage_mode,
        },
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
    service = SmmService(PostgresSmmReadRepository(_pg_session_factory)) if _pg_session_factory is not None else SmmService(db)
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
    service = reviewer_read_service()
    entries = await service.pending_entries()
    return TEMPLATES.TemplateResponse(
        "reviewer_entries.html",
        {"request": request, "title": "Reviewer Entries", "entries": entries},
    )


@app.get("/admin/reviewer/entries/{review_entry_id}", response_class=HTMLResponse)
async def reviewer_entry_detail_page(request: Request, review_entry_id: int, message: str | None = None):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = reviewer_domain_service()
    entry = await service.get_review_entry_detail(review_entry_id)
    if not entry:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return TEMPLATES.TemplateResponse(
        "reviewer_entry_detail.html",
        {"request": request, "title": f"Reviewer Entry {review_entry_id}", "entry": entry, "message": message},
    )


@app.post("/admin/reviewer/entries/{review_entry_id}/verify")
async def reviewer_entry_verify(review_entry_id: int):
    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.verify_review_entry(review_entry_id, 0)
    message = "Entry verified." if result else "Entry not found or already processed."
    return RedirectResponse(url=f"/admin/reviewer/entries/{review_entry_id}?message={message}", status_code=303)


@app.post("/admin/reviewer/entries/{review_entry_id}/reject")
async def reviewer_entry_reject(review_entry_id: int, comment: str = Form(default="")):
    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.reject_review_entry(review_entry_id, 0, comment.strip())
    message = "Entry rejected." if result else "Entry not found or already processed."
    return RedirectResponse(url=f"/admin/reviewer/entries/{review_entry_id}?message={message}", status_code=303)


@app.get("/admin/payouts", response_class=HTMLResponse)
async def payouts_page(request: Request, message: str | None = None):
    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    reviewer = reviewer_domain_service()
    smm = smm_domain_service()
    return TEMPLATES.TemplateResponse(
        "payouts.html",
        {
            "request": request,
            "title": "Payouts",
            "message": message,
            "reviewer_batches": await reviewer.list_pending_reviewer_batches(),
            "smm_batches": await smm.list_pending_smm_batches(),
            "reviewer_history": await reviewer.list_recent_reviewer_batches(limit=10),
            "smm_history": await smm.list_recent_smm_batches(limit=10),
        },
    )


@app.post("/admin/payouts/reviewer/{batch_id}/paid")
async def reviewer_batch_paid(batch_id: int):
    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.mark_reviewer_batch_paid(batch_id, 0)
    message = "Reviewer batch marked as paid." if result else "Reviewer batch not found or already closed."
    return RedirectResponse(url=f"/admin/payouts?message={message}", status_code=303)


@app.post("/admin/payouts/smm/{batch_id}/paid")
async def smm_batch_paid(batch_id: int):
    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = smm_domain_service()
    result = await service.mark_smm_batch_paid(batch_id, 0)
    message = "SMM batch marked as paid." if result else "SMM batch not found or already closed."
    return RedirectResponse(url=f"/admin/payouts?message={message}", status_code=303)
