# Permission A deploy ledger

| deploy_op_id | ref | runUuid | target_sha | supersedes | status | notes |
|--------------|-----|---------|------------|------------|--------|-------|
| pa-20261015-1115 | cur-20261015-1115 | 5e41ecd5-5717-4b88-a8a6-2e53eed6353d | 8c8e9a2 | — | cancelled | Accepted→stopped (no decision). Песочница BLOCKED, nothing applied. Diag 1335. |
| pa-20261015-1335 | cur-20261015-1335 | 8390bae6-0684-48e5-bab0-cc89e4ed6023 | 8c8e9a2 | 1115 | verified | Diagnostic; live baseline 8/8; 1115 closed. |
| pa-20261015-1345 | cur-20261015-1345 | a909f719-b17e-4b42-8046-07229c1387ee | 8c8e9a2 | 1115 | cancelled | Accepted Песочнице, never ran; probe 1355 cancelled. Wrong executor (no create). |
| pa-20261015-1405 | cur-20261015-1405 | dde2dea0-cb68-48c4-8a0f-9497b5463520 | 8c8e9a2 | 1345 | rolled_back | Create ok; SAFE_DEPLOY 4b/4c FAIL (BL7 symlink, BL8 fail-open, BL9 paths, 4c frontmatter). Skill deleted; baseline restored. Evidence cur-20261015-1445. |
| — (fix only) | cur-20261015-1625 | — | 38087e9 | 1405 | submitted | BL10 inline after REJECT@657b041. **No redeploy** until ACCEPT. |
| — (notes fix) | cur-20261015-1640 | — | 3a3561b | 1625 | submitted | Close N39/N41/N43/N44; review then Permission A apply. |
| — (BL11+N39) | cur-20261015-1655 | — | 034b17f | 1640 | submitted | Fix BL11 export + N39 execute SD preamble after REJECT. |
| — (N39+N45) | cur-20261015-1710 | — | 4edde39 | 1655 | submitted | Integrity M1-M4 + strict agent id after REJECT@034b17f. |
| — (N45+M4-9) | cur-20261015-1730 | — | 9a701a7 | 1710 | submitted | Parent agents/ + integrity M4-M9 after REJECT@4edde39. |
| — (N39 hashes) | cur-20261015-1745 | — | a813540 | 1730 | rejected | Pin 9 blocks; REJECT A1–A18 вне pin (result a813540). |
| — (N39 doc pin) | cur-20261017-2015 | — | efd5d7e | 1745 | accepted_notes | document+fences pin; ACCEPT WITH NOTES N46–N49. |
| — (N46–N49) | cur-20261017-2045 | — | (tip) | 2015 | submitted | Restore warnings, check-hashes §0, reject CR, ledger UTF-8. |

## Pin values (N47)

Сверять до Permission A apply (tip после N46–N49):

- `SAFE_DEPLOY.md` `document_sha256`: `af72f1b3354bd40d9732ba4c39125678aab7683b6e51498e2c0c006684162f86`
- `tests/fixtures/safe_deploy_block_hashes.json` sha256: `50d5be251db7d1ec847e5404bb1b87832b8e4f654b7fb079c016e29a128be1f0`
