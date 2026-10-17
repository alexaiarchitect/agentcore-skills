---
type: regex
target: trace
pattern: "discover\\.py"
---

The router must run discovery before advising. This matches the execution
trace for an invocation of `discover.py`; it does not prove the output was
read, which `criteria.md` judges.
