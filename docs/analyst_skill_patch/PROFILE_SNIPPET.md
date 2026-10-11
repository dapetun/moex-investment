# Фрагмент для profile Аналитика (не применять без approve)

```text
## CLI portfolio analysis (optional skill)

When the user explicitly asks to analyse their portfolio via CLI:
use skill `cli-analyst-bundle`.

Contract: moex_analyst_bundle.v1
(docs in dapetun/moex-investment: ANALYST_BUNDLE_CONTRACT.md).

Never enable optimizer.yaml. Never call MOEX ISS.
Never place real portfolio/price files into git or public handoffs.
```

Unified diff (иллюстративный, целевой путь зависит от workspace бота):

```diff
--- a/profile.md
+++ b/profile.md
@@
+## CLI portfolio analysis (optional skill)
+
+When the user explicitly asks to analyse their portfolio via CLI:
+use skill `cli-analyst-bundle`.
+
+Contract: moex_analyst_bundle.v1.
+Never enable optimizer.yaml. Never call MOEX ISS.
+Never place real portfolio/price files into git or public handoffs.
```
