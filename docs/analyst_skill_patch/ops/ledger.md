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
| — (N52–N55) | cur-20261017-2145 | — | 122def2 | 2115 | submitted | EXPECT_HEAD/GUARDS shell pin; raw sha; pytest raw read. |

| — (N52-N55) | cur-20261017-2145 | — | 78ae4f7 | 2115 | rejected | N59 pyc; N58 later. |
| — (N58-N60) | cur-20261017-2215 | — | a5a59ba | 2145 | rejected | N59 shadow pkg; N60 replace/fsmonitor. |
| — (N59-N60b) | cur-20261017-2235 | — | (tip) | 2215 | submitted | importlib GUARDS; EXPECT_TREE; isolated git; per-step cache. |

## Pin values (N47) — только из задания Permission A (N61)

- EXPECT_HEAD / EXPECT_TREE = tip из задания
- EXPECT_DOC = `f70f6504442279f6e146ba0569a8d2bfc4febd1ba99ccc4a198a013c30ddca67`
- EXPECT_FIX = `5f19a158194eda7dfd919f1f3a6f4d67239876aa5cec4b7842414eb93fb9f887`
- EXPECT_GUARDS = `bd4d6f3f38bb2a57dc125c102923c541aa7b09d35fd4b5b061a2311e5c4ec880`
