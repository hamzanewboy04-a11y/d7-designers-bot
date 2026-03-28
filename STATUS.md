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
1. Add user-facing notifications for new payout batch flows.
2. Introduce service layer for payroll/reviewer/smm domains.
3. Start web admin panel groundwork.
4. Reduce legacy reviewer flow after confidence period.

## Риск
Если дальше просто наращивать handlers без service layer, проект снова быстро уйдёт в спутанную бизнес-логику.
