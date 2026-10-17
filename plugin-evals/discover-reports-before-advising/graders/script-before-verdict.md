---
type: regex
target: trace
pattern: "discover\\.py[^\\n]*"
---

Availability must come from the regions table through `discover.py`, not from
memory. This proves the script ran; the llm grader checks the answer used it.
