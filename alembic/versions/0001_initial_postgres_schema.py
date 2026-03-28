"""initial postgres schema scaffold

Revision ID: 0001_initial_postgres_schema
Revises: None
Create Date: 2026-03-28 12:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0001_initial_postgres_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'employees',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('telegram_id', sa.Integer(), nullable=True, unique=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=64), nullable=False),
        sa.Column('wallet', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'smm_assignments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('smm_employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_name', sa.String(length=255), nullable=False),
        sa.Column('geo', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('daily_rate_usdt', sa.Float(), nullable=False, server_default='0'),
        sa.Column('active_from', sa.String(length=32), nullable=True),
        sa.Column('active_to', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
    )

    op.create_table(
        'review_rate_rules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_type', sa.String(length=64), nullable=False, unique=True),
        sa.Column('default_unit_price', sa.Float(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
    )

    op.create_table(
        'review_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report_date', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
        sa.Column('verified_by_pm', sa.Integer(), sa.ForeignKey('employees.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verified_at', sa.String(length=64), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'review_entry_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_entry_id', sa.Integer(), sa.ForeignKey('review_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('review_type', sa.String(length=64), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit_price', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_usdt', sa.Float(), nullable=False, server_default='0'),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
    )

    op.create_table(
        'smm_daily_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('smm_employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entered_by_pm_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report_date', sa.String(length=32), nullable=False),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('smm_assignments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('channel_name_snapshot', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('geo_snapshot', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('daily_rate_snapshot', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_usdt', sa.Float(), nullable=False, server_default='0'),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'payment_batches',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payout_mode', sa.String(length=32), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('period_start', sa.String(length=32), nullable=True),
        sa.Column('period_end', sa.String(length=32), nullable=True),
        sa.Column('total_usdt', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('paid_at', sa.String(length=64), nullable=True),
        sa.Column('paid_by', sa.Integer(), sa.ForeignKey('employees.id', ondelete='SET NULL'), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'payment_batch_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('payment_batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_table', sa.String(length=64), nullable=False),
        sa.Column('source_entry_id', sa.Integer(), nullable=False),
        sa.Column('amount_usdt', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('payment_batch_items')
    op.drop_table('payment_batches')
    op.drop_table('smm_daily_entries')
    op.drop_table('review_entry_items')
    op.drop_table('review_entries')
    op.drop_table('review_rate_rules')
    op.drop_table('smm_assignments')
    op.drop_table('employees')
