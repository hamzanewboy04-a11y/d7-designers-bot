from storage.repositories.dashboard import PostgresDashboardReadRepository
from storage.repositories.employees import PostgresEmployeeReadRepository
from storage.repositories.reviewer import PostgresReviewerReadRepository
from storage.repositories.smm import PostgresSmmReadRepository

__all__ = [
    "PostgresDashboardReadRepository",
    "PostgresEmployeeReadRepository",
    "PostgresReviewerReadRepository",
    "PostgresSmmReadRepository",
]
