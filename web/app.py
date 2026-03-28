from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from d7_bot.config import load_config
from d7_bot.db import Database
from services.employees import EmployeeService
from services.payroll import PayrollService
from services.reviewer import ReviewerService
from services.smm import SmmService

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="D7 Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

config = load_config()
db = Database(config.db_path)


@app.on_event("startup")
async def startup() -> None:
    await db.init()


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
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
    service = EmployeeService(db)
    employees = await service.list_active()
    return TEMPLATES.TemplateResponse(
        "employees.html",
        {"request": request, "title": "Employees", "employees": employees},
    )


@app.get("/admin/smm/assignments", response_class=HTMLResponse)
async def smm_assignments_page(request: Request):
    service = SmmService(db)
    assignments = await service.list_assignments()
    return TEMPLATES.TemplateResponse(
        "smm_assignments.html",
        {"request": request, "title": "SMM Assignments", "assignments": assignments},
    )


@app.get("/admin/reviewer/entries", response_class=HTMLResponse)
async def reviewer_entries_page(request: Request):
    service = ReviewerService(db)
    entries = await service.pending_entries()
    return TEMPLATES.TemplateResponse(
        "reviewer_entries.html",
        {"request": request, "title": "Reviewer Entries", "entries": entries},
    )


@app.get("/admin/payouts", response_class=HTMLResponse)
async def payouts_page(request: Request):
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
