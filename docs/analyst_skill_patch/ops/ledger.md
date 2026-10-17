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
| — (N47/N49 fix) | cur-20261017-2115 | — | 24e7770 | 2045 | rejected | N52 guards not pinned; N54 pytest read_text; N55 LF pad. |
| — (N52–N55) | cur-20261017-2145 | — | (tip) | 2115 | submitted | EXPECT_HEAD/GUARDS shell pin; raw sha; pytest raw read. |

## Pin values (N47) — источник: задание Permission A (не checkout)

Передавать каждому исполнителю явно:

- EXPECT_HEAD: tip SHA после merge этого коммита
- EXPECT_DOC (SAFE_DEPLOY.md): 35d55bd8dee081a4126d7f60a3283f30ee8df3cf2c92023cc86d9cf27ada57c5
- EXPECT_FIX (safe_deploy_block_hashes.json): 8366cc3ac1a3998b7f54d42bf1d1834b046e75482c06e40fee807b1bfd92fc6b
- EXPECT_GUARDS (safe_deploy_guards.py): 18dcc687673b001cdda0d07f7606e9cc43445c09abc6168051175a367fe5a146
