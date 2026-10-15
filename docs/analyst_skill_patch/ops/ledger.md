# Permission A deploy ledger

| deploy_op_id | ref | runUuid | target_sha | supersedes | status | notes |
|--------------|-----|---------|------------|------------|--------|-------|
| pa-20261015-1115 | cur-20261015-1115 | 5e41ecd5-5717-4b88-a8a6-2e53eed6353d | 8c8e9a2 | — | cancelled | Accepted then stopped: no owner decision file. Песочница BLOCKED, nothing applied. Diag cur-20261015-1335. |
| pa-20261015-1335 | cur-20261015-1335 | 8390bae6-0684-48e5-bab0-cc89e4ed6023 | 8c8e9a2 | 1115 | verified | Diagnostic only; SAFE_TO_RETRY after cancel; live baseline 8/8. |

| pa-20261015-1345 | cur-20261015-1345 | a909f719-b17e-4b42-8046-07229c1387ee | 8c8e9a2 | cur-20261015-1115 | submitted→unacked | Webhook 200; after 15m still no bot-handoffs status (same class as 1115). Probe cur-20261015-1355. NO second apply. |
