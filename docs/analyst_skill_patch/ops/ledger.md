# Permission A deploy ledger

| deploy_op_id | ref | runUuid | target_sha | supersedes | status | notes |
|--------------|-----|---------|------------|------------|--------|-------|
| pa-20261015-1115 | cur-20261015-1115 | 5e41ecd5-5717-4b88-a8a6-2e53eed6353d | 8c8e9a2 | — | cancelled | Accepted→stopped (no decision). Песочница BLOCKED, nothing applied. Diag 1335. |
| pa-20261015-1335 | cur-20261015-1335 | 8390bae6-0684-48e5-bab0-cc89e4ed6023 | 8c8e9a2 | 1115 | verified | Diagnostic; live baseline 8/8; 1115 closed. |
| pa-20261015-1345 | cur-20261015-1345 | a909f719-b17e-4b42-8046-07229c1387ee | 8c8e9a2 | 1115 | cancelled | Accepted Песочнице, never ran; probe 1355 cancelled. Wrong executor (no create). |
| pa-20261015-1405 | cur-20261015-1405 | dde2dea0-cb68-48c4-8a0f-9497b5463520 | 8c8e9a2 | 1345 | blocked | Split ready; Regulator waits Daniil chat confirm «да, деплой pa-20261015-1405». Live untouched. |
