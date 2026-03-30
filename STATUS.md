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
1. Stabilize production deploy conventions and smoke-check key flows.
2. Complete storage cutover so bot + web share one source of truth.
3. Introduce real service/repository boundaries for payroll/reviewer/smm domains.
4. Continue web admin groundwork only after storage path is clarified.
5. Reduce legacy reviewer flow after confidence period.

## Обновление 2026-03-30
Production deploy был восстановлен после серии fixes в SQLite -> PostgreSQL import path и Railway runtime command.
Сейчас главный незавершённый риск — bot runtime всё ещё в основном опирается на SQLite, тогда как PostgreSQL path уже частично введён.

## Риск
Если дальше просто наращивать handlers без service layer и без завершения storage cutover, проект снова быстро уйдёт в спутанную бизнес-логику и рассинхрон данных.
