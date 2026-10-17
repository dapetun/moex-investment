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
| — (N46–N49) | cur-20261017-2045 | — | 1f109a8 | 2015 | rejected | N49 read_text CR; N47 fixture CRLF + comment-only expect. |
| — (N47/N49 fix) | cur-20261017-2115 | — | (tip) | 2045 | submitted | raw-bytes read; EXPECT_DOC/FIX; .gitattributes eol=lf. |

## Pin values (N47)

Сверять до Permission A apply; передавать как EXPECT_DOC / EXPECT_FIX каждому исполнителю:

- SAFE_DEPLOY.md document_sha256: d27360604cdf77a8356d6658b8a15b34affe53441c15f5bf865979bc70c336db
- tests/fixtures/safe_deploy_block_hashes.json sha256: 736e9b7b774f0a96ca81afb3945a6cdfa2a7bd4d94257361992238fa6c95dca7
