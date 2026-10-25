# Decision: Permission A @ 8c8e9a2

- **date:** 2026-10-15
- **owner:** Даниил (dapetun)
- **repo:** dapetun/moex-investment
- **branch:** feature/headless-cli-grok-bot
- **SHA:** `8c8e9a2d3f15ea9645f8ef58dd33c6715fed3260`
- **prior review:** `cur-20261015-1105` ACCEPT WITH NOTES (no blockers)
- **prior hung deploy:** `cur-20261015-1115` / runUuid `5e41ecd5-5717-4b88-a8a6-2e53eed6353d`
- **diagnostic:** `cur-20261015-1335` — live = baseline 8/8, skill absent;
  Regulator stopped 1115; Песочница RESULT BLOCKED «ничего не выполнялось»;
  task closed, will not resume.

## Approve

Permission A **approved** for synthetic-only wiring of `cli-analyst-bundle`
to the live Analyst at the SHA above.

## Cancel

`cur-20261015-1115` is **cancelled**. Do not resume it. Do not run a second
apply in parallel with any other Permission A deploy op.

## Deploy window

One controlled retry allowed only with:

- unique `deploy_op_id` (see `DEPLOY_OPS.md`);
- executor that has platform **create/delete/get skill** tools;
- Песочница (or same executor) for live_patches + manifests;
- statuses written to bot-handoffs: submitted → accepted → … → verified|failed|rolled_back.

## Scope / non-scope

Allowed: skill register + OPT/POS/QC/profile/SPEC patches per SAFE_DEPLOY @ SHA;
synthetic checks; backups under `/workspace/handoffs/backups/`.

Forbidden: Permission B / real CSV; `optimizer.yaml` enable; ISS in CLI;
cron/routines/broker; PR #2 merge; deleting a pre-existing same-named skill.
