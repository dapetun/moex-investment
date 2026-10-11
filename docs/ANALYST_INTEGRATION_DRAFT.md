# Черновик постоянной интеграции «Аналитик портфеля» ↔ CLI

**Статус:** только проект для утверждения. Рабочие profiles/skills/`optimizer.yaml` **не изменены**.

Контракт данных: `docs/ANALYST_BUNDLE_CONTRACT.md` (`moex_analyst_bundle.v1`).

## 1. Минимальные изменения skills/profile (после approve)

Добавить skill (черновик имени: `cli-analyst-bundle`):

1. При явном запросе пользователя на анализ портфеля через CLI — читать последний `moex_analyst_bundle.v1` (путь из задания / outbox).
2. Не запускать Streamlit и не включать `optimizer.yaml` (`enabled` остаётся `false`).
3. Разделять блоки: числа CLI vs оценки радара (`equity_assessment` / события).
4. В отчёте всегда: `run_id`, `event_id`, пути артефактов, `synthetic` flag.
5. Запрет: выдавать materiality/direction радара за результат Max Sharpe.

Опционально в profile: ссылка на контракт bundle и команду запуска CLI (см. §2).

## 2. Правила запуска CLI

Разрешено только по **явному** запросу пользователя в сообщении (формулировки вроде «запусти optimize», «собери bundle»).

Запрещено:

- фоновые routines/cron;
- автозапуск при появлении файла новостей;
- вызов ISS (`MOEX_ISS_ENABLED` не включать из инструкций бота).

Рекомендуемая последовательность (когда пользователь просит полный цикл):

```text
check-portfolio-ready → adapt-portfolio --write-holdings → validate-data
→ optimize --allow-optimize → compare → ingest-events [--test-events]
→ build-analyst-bundle → отчёт по bundle
```

## 3. Ошибки, устаревание, отсутствие target

| Ситуация | Поведение Аналитика |
|---|---|
| QC `ok=false` / stale | Не интерпретировать target; сообщить blockers; не выдумывать веса |
| `last_target` отсутствует или `success!=true` | Compare/ребаланс недоступны; сказать что нужно |
| Bundle `synthetic=true` | Явный дисклеймер: не реальный портфель |
| События без `event_id`/url | Не ссылаться; отметить пробел |
| Расхождение weight vs MV в bundle | Предупредить; не рекомендовать сделки |

## 4. Проверка чисел и ссылок

- Любая цифра веса/drift/Sharpe — только из bundle/CLI JSON.
- Каждое корпоративное утверждение — с `event_id` + `source`/`url`.
- Каждый вычислительный шаг — с `run_id` из `runs[]` или outbox.
- Не округлять так, чтобы менялся знак отклонения относительно порога.

## 5. Радар ≠ оптимизатор

Корпоративные события — качественный блок. Не переводить direction/confidence в expected return, constraints solver или торговые ордера.

## 6. Развёртывание и откат

1. Утвердить этот черновик (Даниил).
2. Внести skill в профиль Аналитика (отдельный commit в bot workspace, не в moex-investment).
3. One-shot прогон на синтетическом bundle + сверка claims.
4. One-shot на user_csv + реальный портфель (вне репо).
5. Откат: удалить/отключить skill; `optimizer.yaml` не трогался — откат не затрагивает.

## 7. Текст one-shot задания для проверки черновика

```text
Роль: Аналитик портфеля. Не меняй profile/skills.
Прочитай docs/ANALYST_INTEGRATION_DRAFT.md и docs/examples/analyst_bundle_e2e_synthetic.json.
Сформируй пользовательский отчёт строго по правилам черновика.
Отдельно: (a) список мест, где черновик противоречит текущим skills;
(b) пробелы, из-за которых постоянное подключение ещё нельзя включать;
(c) сверка 10 ключевых чисел bundle с текстом отчёта.
```
