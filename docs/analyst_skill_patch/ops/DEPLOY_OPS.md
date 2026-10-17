# Deploy operations ledger (Cursor ↔ Grok Bot)

Не заменяет `SAFE_DEPLOY.md`. Не меняет инструкции ботов.  
Цель: убрать неопределённость «webhook 200, а статуса нет» и запретить
параллельные apply к одному baseline.

## Статусы (обязательные в status/*.md handoff)

| status | смысл |
|--------|--------|
| `submitted` | webhook принят (есть runUuid); ещё нет accept исполнителя |
| `accepted` | Регулятор назначил владельца; handoff.md создан |
| `running` | исполнитель начал шаги SAFE_DEPLOY |
| `applied` | skill зарегистрирован + патчи применены; MANIFEST_AFTER ok |
| `verified` | smoke/синтетика или явный «ожидает команду Даниила» |
| `failed` | ошибка до/во время apply |
| `rolled_back` | выполнен 10a/10b |
| `cancelled` | владелец/Регулятор отменил; **не возобновлять** |

## Поля каждой операции

В `status/<id>.md` и RESULT обязательны:

```text
deploy_op_id: pa-<YYYYMMDD>-<short>
ref: cur-...
runUuid: ...
target_sha: <full>
baseline: AUDIT_BASELINE @ <note>
supersedes: <prior ref or none>
статус: <one of table>
```

`deploy_op_id` уникален. Новый apply к тому же baseline **запрещён**, пока
предыдущий op в `{submitted,accepted,running,applied}` и не `cancelled` /
`failed` / `rolled_back` / `verified`.

## Anti-parallel

1. Перед submit — диагностика: нет active op, live = baseline или
   документированное post-install состояние.
2. Один `deploy_op_id` на одну попытку.
3. Повторный webhook с тем же `deploy_op_id` — идемпотентный отказ.
4. Отмена (`cancelled`) обязательна текстом владельца или Регулятора в RESULT.

## Подтверждение приёма

Исполнитель в течение ~2 мин после HANDOFF пишет `status/*.md` со
`статус: accepted` (или `blocked` с причиной).  
Отсутствие accepted > 10 мин при живом webhook → считать маршрутизацию
сломанной; **не** слать второй apply вслепую.

## Где лежит ledger в репо

Краткие записи попыток: `docs/analyst_skill_patch/ops/ledger.md`
(дополняет Cursor после каждого handoff; не секретные данные).
