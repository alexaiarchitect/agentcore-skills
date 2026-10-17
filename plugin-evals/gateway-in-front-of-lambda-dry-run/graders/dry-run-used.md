---
type: regex
target: trace
pattern: "gateway_plan\\.py[^\\n]*--dry-run"
---

The write plan must come from the script's dry run. This matches an
invocation of `gateway_plan.py` carrying `--dry-run`.
