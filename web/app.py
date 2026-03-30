from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote
from datetime import date, timedelta

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from d7_bot.config import load_config
from d7_bot.db import Database, moscow_today
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
app.add_middleware(SessionMiddleware, secret_key=load_config().web_session_secret)
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

    pg_ok = False
    pg_error: str | None = None
    sqlite_ok = False
    sqlite_error: str | None = None

    if _pg_session_factory is not None:
        try:
            async with _pg_session_factory() as session:
                await session.execute(text("SELECT 1"))
            pg_ok = True
        except Exception as exc:
            pg_error = str(exc)
            logger.error("Web Postgres init failed: %s", exc)

    try:
        await db.init()
        sqlite_ok = True
    except Exception as exc:
        sqlite_error = str(exc)
        logger.warning("Web SQLite init failed (legacy fallback unavailable): %s", exc)

    if _pg_session_factory is not None:
        if pg_ok:
            _db_ready = True
            _db_error = sqlite_error
            return True, sqlite_error
        _db_error = pg_error or sqlite_error
        return False, _db_error

    if sqlite_ok:
        _db_ready = True
        _db_error = None
        return True, None

    _db_error = sqlite_error
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


async def current_operator_id(request: Request) -> int | None:
    value = request.session.get("operator_telegram_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def require_operator(request: Request) -> int | RedirectResponse:
    operator_id = await current_operator_id(request)
    if operator_id is None:
        return RedirectResponse(url="/admin/login?message=Пожалуйста,+войдите", status_code=303)
    if operator_id in config.admin_ids:
        return operator_id
    try:
        if await db.is_admin(operator_id, config.admin_ids):
            return operator_id
    except Exception as exc:
        logger.warning("Admin fallback DB check failed for operator %s: %s", operator_id, exc)
    request.session.clear()
    return RedirectResponse(url="/admin/login?message=Нужен+доступ+администратора", status_code=303)


@app.on_event("startup")
async def startup() -> None:
    ok, err = await ensure_db()
    if ok:
        if err:
            logger.info("Web admin DB init complete (legacy SQLite fallback unavailable: %s)", err)
        else:
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


@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request, message: str | None = None):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "title": "Login", "message": message},
    )


@app.post("/admin/login")
async def login_action(request: Request, telegram_id: int = Form(...)):
    if telegram_id in config.admin_ids:
        request.session["operator_telegram_id"] = str(telegram_id)
        return RedirectResponse(url="/admin", status_code=303)
    try:
        ok, _ = await ensure_db()
        if ok and await db.is_admin(telegram_id, config.admin_ids):
            request.session["operator_telegram_id"] = str(telegram_id)
            return RedirectResponse(url="/admin", status_code=303)
    except Exception as exc:
        logger.warning("Admin login DB fallback failed for %s: %s", telegram_id, exc)
    return RedirectResponse(url="/admin/login?message=Неизвестный+или+неавторизованный+оператор", status_code=303)


@app.post("/admin/logout")
async def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login?message=Вы+вышли+из+системы", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

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
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "title": "Dashboard",
            "stats": stats,
            "role_counts": role_counts,
            "storage_mode": storage_mode,
            "operator_id": operator,
        },
    )


@app.get("/admin/employees", response_class=HTMLResponse)
async def employees_page(request: Request):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)

    if _pg_session_factory is not None:
        service = EmployeeService(PostgresEmployeeReadRepository(_pg_session_factory))
    else:
        service = EmployeeService(db)

    employees = await service.list_active()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="employees.html",
        context={"request": request, "title": "Сотрудники", "employees": employees, "operator_id": operator},
    )


@app.get("/admin/employees/{telegram_id}", response_class=HTMLResponse)
async def employee_detail_page(request: Request, telegram_id: int):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok and _pg_session_factory is None:
        return HTMLResponse(f"<h1>D7 Админка</h1><p>База недоступна</p><pre>{err}</pre>", status_code=503)

    if _pg_session_factory is not None:
        employee_service = EmployeeService(PostgresEmployeeReadRepository(_pg_session_factory))
        employees = await employee_service.list_active()
        employee = next((item for item in employees if item.telegram_id == telegram_id), None)
    else:
        employee = await db.get_employee_by_telegram_id(telegram_id)

    if not employee:
        return HTMLResponse("<h1>Сотрудник не найден</h1>", status_code=404)

    payment = {"paid_usdt": 0.0, "pending_usdt": 0.0, "report_count": 0}
    reports: list[dict] = []
    try:
        payment = await db.get_designer_payment_summary(telegram_id)
        raw_reports = await db.list_designer_reports(telegram_id, limit=50)
        reports = [
            {
                "report_date": row[0],
                "task_code": row[1],
                "cost_usdt": float(row[2]),
                "payment_status": row[3],
                "payment_comment": row[4] or "",
            }
            for row in raw_reports
        ]
    except Exception as exc:
        logger.warning("Legacy designer report data unavailable for %s: %s", telegram_id, exc)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="employee_detail.html",
        context={
            "request": request,
            "title": f"Сотрудник {employee.display_name}",
            "employee": employee,
            "payment": payment,
            "reports": reports,
            "operator_id": operator,
        },
    )


@app.get("/admin/legacy-reports", response_class=HTMLResponse)
async def legacy_reports_page(request: Request):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    pending: list[dict] = []
    recent_paid: list[dict] = []
    try:
        pending_rows = await db.get_pending_payments()
        pending = [
            {
                "designer_id": row[0],
                "d7_nick": row[1],
                "wallet": row[2],
                "report_date": row[3],
                "task_count": int(row[4]),
                "total_usdt": float(row[5]),
            }
            for row in pending_rows
        ]
        paid_rows = await db.get_paid_summary(moscow_today() - timedelta(days=14))
        recent_paid = [
            {
                "designer_id": row[0],
                "d7_nick": row[1],
                "report_date": row[2],
                "task_count": int(row[3]),
                "total_usdt": float(row[4]),
            }
            for row in paid_rows[:30]
        ]
    except Exception as exc:
        logger.warning("Legacy reports page data unavailable: %s", exc)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="legacy_reports.html",
        context={
            "request": request,
            "title": "Legacy-отчёты",
            "pending": pending,
            "recent_paid": recent_paid,
            "operator_id": operator,
        },
    )


@app.get("/admin/legacy-daily", response_class=HTMLResponse)
async def legacy_daily_reports_page(request: Request, report_date: str | None = None, designer_id: int | None = None):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    selected_date = report_date or moscow_today().isoformat()
    rows: list[dict] = []
    try:
        parsed_date = date.fromisoformat(selected_date)
        raw_rows = await db.list_tasks_by_date_for_web(parsed_date, designer_id)
        rows = [
            {
                "designer_id": row[0],
                "d7_nick": row[1],
                "wallet": row[2],
                "task_code": row[3],
                "cost_usdt": float(row[4]),
                "payment_status": row[5],
            }
            for row in raw_rows
        ]
    except Exception as exc:
        logger.warning("Legacy daily reports unavailable: %s", exc)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="legacy_daily_reports.html",
        context={
            "request": request,
            "title": "Legacy-отчёты за день",
            "report_date": selected_date,
            "designer_id": designer_id,
            "rows": rows,
            "operator_id": operator,
        },
    )


@app.get("/admin/smm/assignments", response_class=HTMLResponse)
async def smm_assignments_page(request: Request, message: str | None = None):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = SmmService(PostgresSmmReadRepository(_pg_session_factory)) if _pg_session_factory is not None else SmmService(db)
    employee_service = EmployeeService(PostgresEmployeeReadRepository(_pg_session_factory)) if _pg_session_factory is not None else EmployeeService(db)
    assignments = await service.list_assignments()
    smm_employees = [employee for employee in await employee_service.list_active() if employee.role == "smm"]
    return TEMPLATES.TemplateResponse(
        request=request,
        name="smm_assignments.html",
        context={
            "request": request,
            "title": "SMM Assignments",
            "assignments": assignments,
            "smm_employees": smm_employees,
            "message": message,
            "operator_id": operator,
        },
    )


@app.post("/admin/smm/assignments")
async def smm_assignment_create(
    request: Request,
    smm_employee_id: int = Form(...),
    channel_name: str = Form(...),
    geo: str = Form(default=""),
    daily_rate_usdt: float = Form(...),
    active_from: str = Form(default=""),
    comment: str = Form(default=""),
):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = smm_domain_service()
    await service.add_smm_assignment(
        smm_employee_id=smm_employee_id,
        channel_name=channel_name.strip(),
        geo=geo.strip().upper(),
        daily_rate_usdt=daily_rate_usdt,
        active_from=active_from.strip() or None,
        comment=comment.strip(),
    )
    return RedirectResponse(url="/admin/smm/assignments?message=Назначение+создано.", status_code=303)


@app.get("/admin/reviewer/entries", response_class=HTMLResponse)
async def reviewer_entries_page(request: Request):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = reviewer_read_service()
    entries = await service.pending_entries()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="reviewer_entries.html",
        context={"request": request, "title": "Reviewer Entries", "entries": entries, "operator_id": operator},
    )


@app.get("/admin/reviewer/entries/{review_entry_id}", response_class=HTMLResponse)
async def reviewer_entry_detail_page(request: Request, review_entry_id: int, message: str | None = None):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    service = reviewer_domain_service()
    entry = await service.get_review_entry_detail(review_entry_id)
    if not entry:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="reviewer_entry_detail.html",
        context={"request": request, "title": f"Reviewer Entry {review_entry_id}", "entry": entry, "message": message, "operator_id": operator},
    )


@app.post("/admin/reviewer/entries/{review_entry_id}/verify")
async def reviewer_entry_verify(request: Request, review_entry_id: int):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.verify_review_entry(review_entry_id, operator)
    message = "Отчёт+подтверждён." if result else "Отчёт+не+найден+или+уже+обработан."
    return RedirectResponse(url=f"/admin/reviewer/entries/{review_entry_id}?message={quote(message)}", status_code=303)


@app.post("/admin/reviewer/entries/{review_entry_id}/reject")
async def reviewer_entry_reject(request: Request, review_entry_id: int, comment: str = Form(default="")):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.reject_review_entry(review_entry_id, operator, comment.strip())
    message = "Отчёт+отклонён." if result else "Отчёт+не+найден+или+уже+обработан."
    return RedirectResponse(url=f"/admin/reviewer/entries/{review_entry_id}?message={quote(message)}", status_code=303)


@app.get("/admin/payouts", response_class=HTMLResponse)
async def payouts_page(request: Request, message: str | None = None):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, err = await ensure_db()
    if not ok:
        return HTMLResponse(f"<h1>D7 Admin</h1><p>DB unavailable</p><pre>{err}</pre>", status_code=503)
    reviewer = reviewer_domain_service()
    smm = smm_domain_service()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="payouts.html",
        context={
            "request": request,
            "title": "Payouts",
            "message": message,
            "reviewer_batches": await reviewer.list_pending_reviewer_batches(),
            "smm_batches": await smm.list_pending_smm_batches(),
            "reviewer_history": await reviewer.list_recent_reviewer_batches(limit=10),
            "smm_history": await smm.list_recent_smm_batches(limit=10),
            "operator_id": operator,
        },
    )


@app.post("/admin/payouts/reviewer/{batch_id}/paid")
async def reviewer_batch_paid(request: Request, batch_id: int):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = reviewer_domain_service()
    result = await service.mark_reviewer_batch_paid(batch_id, operator)
    message = "Выплата+отзовику+отмечена+как+оплаченная." if result else "Batch+отзовика+не+найден+или+уже+закрыт."
    return RedirectResponse(url=f"/admin/payouts?message={quote(message)}", status_code=303)


@app.post("/admin/payouts/smm/{batch_id}/paid")
async def smm_batch_paid(request: Request, batch_id: int):
    operator = await require_operator(request)
    if isinstance(operator, RedirectResponse):
        return operator

    ok, _ = await ensure_db()
    if not ok:
        return HTMLResponse("DB unavailable", status_code=503)
    service = smm_domain_service()
    result = await service.mark_smm_batch_paid(batch_id, operator)
    message = "Выплата+SMM+отмечена+как+оплаченная." if result else "Batch+SMM+не+найден+или+уже+закрыт."
    return RedirectResponse(url=f"/admin/payouts?message={quote(message)}", status_code=303)
