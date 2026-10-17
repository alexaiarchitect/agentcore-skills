---
type: regex
target: last_message
pattern: "ACR043|OBS012|PassThrough"
---

The Lambda behind `POST /mcp` has `tracing_config { mode = "PassThrough" }`.
The final answer must name it, by id or by mode.
