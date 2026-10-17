# Permission A deploy ledger

| deploy_op_id | ref | runUuid | target_sha | supersedes | status | notes |
|--------------|-----|---------|------------|------------|--------|-------|
| pa-20261015-1405 | cur-20261015-1405 | dde2dea0-cb68-48c4-8a0f-9497b5463520 | 8c8e9a2 | 1345 | rolled_back | Create ok; SAFE_DEPLOY FAIL BL7-BL9+4c; rolled back. |
| — (N39 doc pin) | cur-20261017-2015 | — | efd5d7e | 1745 | accepted_notes | document+fences; NOTES N46-N49. |
| — (N46-N49) | cur-20261017-2045 | — | 1f109a8 | 2015 | rejected | N49/N47 incomplete. |
| — (N47/N49 fix) | cur-20261017-2115 | — | 24e7770 | 2045 | rejected | N52/N54/N55. |
| — (N52-N55) | cur-20261017-2145 | — | 78ae4f7 | 2115 | rejected | N59 pyc hijack; N58 git status fail-open. |
| — (N58-N60) | cur-20261017-2215 | — | (tip) | 2145 | submitted | PYTHONPYCACHEPREFIX; fail-closed git; skip-worktree check. |

## Pin values (N47) — только из задания Permission A

Не хранить EXPECT_HEAD в ledger как self-hash (N61). В задании передать:

- EXPECT_HEAD = tip SHA пакета
- EXPECT_DOC = d489019c11ce6759a760bf8753a3f17af50480a53f7ce376f54b32c2e51474dd
- EXPECT_FIX = ab2f57d30687dc50b7ff00af20d461151176b5b1f57ae3c874bb376473c5cdea
- EXPECT_GUARDS = 18dcc687673b001cdda0d07f7606e9cc43445c09abc6168051175a367fe5a146
