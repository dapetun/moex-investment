# Permission A deploy ledger

| deploy_op_id | ref | runUuid | target_sha | supersedes | status | notes |
|--------------|-----|---------|------------|------------|--------|-------|
| pa-20261015-1115 | cur-20261015-1115 | 5e41ecd5-5717-4b88-a8a6-2e53eed6353d | 8c8e9a2 | — | cancelled | Accepted→stopped (no decision). Песочница BLOCKED, nothing applied. Diag 1335. |
| pa-20261015-1335 | cur-20261015-1335 | 8390bae6-0684-48e5-bab0-cc89e4ed6023 | 8c8e9a2 | 1115 | verified | Diagnostic; live baseline 8/8; 1115 closed. |
| pa-20261015-1345 | cur-20261015-1345 | a909f719-b17e-4b42-8046-07229c1387ee | 8c8e9a2 | 1115 | cancelled | Accepted Песочнице, never ran; probe 1355 cancelled. Wrong executor (no create). |
| pa-20261015-1405 | cur-20261015-1405 | dde2dea0-cb68-48c4-8a0f-9497b5463520 | 8c8e9a2 | 1345 | rolled_back | Create ok; SAFE_DEPLOY 4b/4c FAIL (BL7 symlink, BL8 fail-open, BL9 paths, 4c frontmatter). Skill deleted; baseline restored. Evidence cur-20261015-1445. |
| — (fix only) | cur-20261015-1605 | — | 657b041 | 1405 | submitted | BL10+N34/N35/N36 after REJECT@00eb032. **No redeploy** until ACCEPT. |
