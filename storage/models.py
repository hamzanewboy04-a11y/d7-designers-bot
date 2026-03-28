from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from storage.base import Base


class EmployeeModel(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64))
    wallet: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SmmAssignmentModel(Base):
    __tablename__ = "smm_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smm_employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    channel_name: Mapped[str] = mapped_column(String(255))
    geo: Mapped[str] = mapped_column(String(64), default="")
    daily_rate_usdt: Mapped[float] = mapped_column(Float, default=0)
    active_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    comment: Mapped[str] = mapped_column(Text, default="")


class ReviewRateRuleModel(Base):
    __tablename__ = "review_rate_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_type: Mapped[str] = mapped_column(String(64), unique=True)
    default_unit_price: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")


class ReviewEntryModel(Base):
    __tablename__ = "review_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    report_date: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    verified_by_pm: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items: Mapped[list["ReviewEntryItemModel"]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class ReviewEntryItemModel(Base):
    __tablename__ = "review_entry_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_entry_id: Mapped[int] = mapped_column(ForeignKey("review_entries.id", ondelete="CASCADE"))
    review_type: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    total_usdt: Mapped[float] = mapped_column(Float, default=0)
    comment: Mapped[str] = mapped_column(Text, default="")

    entry: Mapped[ReviewEntryModel] = relationship(back_populates="items")


class SmmDailyEntryModel(Base):
    __tablename__ = "smm_daily_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smm_employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    entered_by_pm_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    report_date: Mapped[str] = mapped_column(String(32))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("smm_assignments.id", ondelete="SET NULL"), nullable=True)
    channel_name_snapshot: Mapped[str] = mapped_column(String(255), default="")
    geo_snapshot: Mapped[str] = mapped_column(String(64), default="")
    daily_rate_snapshot: Mapped[float] = mapped_column(Float, default=0)
    total_usdt: Mapped[float] = mapped_column(Float, default=0)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentBatchModel(Base):
    __tablename__ = "payment_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    payout_mode: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_usdt: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    paid_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentBatchItemModel(Base):
    __tablename__ = "payment_batch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_batches.id", ondelete="CASCADE"))
    source_table: Mapped[str] = mapped_column(String(64))
    source_entry_id: Mapped[int] = mapped_column(Integer)
    amount_usdt: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
