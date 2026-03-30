# STATUS.md

## Состояние
Проект перешёл из простого Telegram report bot в transition-stage internal ops/payroll system.

## Что уже собрано
- Legacy designer flow стабилен.
- SMM / PM weekly cycle реализован end-to-end.
- Reviewer v2 cycle реализован end-to-end.
- Next-gen domain tables введены параллельно legacy-модели.
- Базовый smoke-test coverage есть.

## Что остаётся главным техническим долгом
1. `db.py` всё ещё перегружен.
2. Нет service layer между handlers и DB.
3. README только что синхронизирован, но продукт ещё в transition-mode.
4. Нет web admin panel.
5. Нет расширенного тестового покрытия на edge cases / business policies.

## Следующий рекомендуемый этап
1. Stabilize mixed-mode runtime and validate reviewer/SMM PostgreSQL-backed bot flows in production.
2. Keep legacy designer/admin/task layer frozen as compatibility layer unless a full migration is explicitly chosen.
3. Continue web admin groundwork on top of the newer shared domain storage.
4. Expand regression coverage and operational notes.

## Обновление 2026-03-30
Production deploy был восстановлен после серии fixes в SQLite -> PostgreSQL import path и Railway runtime command.
После этого были выполнены следующие шаги:
- web read-path переведён на PostgreSQL repositories для текущих admin views;
- reviewer bot domain получил PostgreSQL-backed adapter/service path;
- SMM bot domain получил PostgreSQL-backed adapter/service path;
- добавлены regression tests для reviewer и SMM domain services;
- зафиксирована стратегия не мигрировать legacy designer/admin/task слой преждевременно.

## Текущее состояние архитектуры
- Reviewer и SMM next-gen flows движутся в сторону PostgreSQL-backed runtime.
- Web admin current reads уже опираются на PostgreSQL path при наличии `DATABASE_URL`.
- Legacy designer/admin/task flow остаётся контролируемым SQLite compatibility layer.

## Риск
Главный риск теперь не аварийный deploy, а mixed-mode complexity: часть проекта уже modernized, а legacy слой ещё живёт отдельно. Это управляемо, если не смешивать новые фичи с преждевременной миграцией legacy.
