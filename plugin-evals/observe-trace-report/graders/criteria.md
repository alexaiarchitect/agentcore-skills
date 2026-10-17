---
type: llm
---

PASS if the response, using the script's numbers:

- gives total p95 (513 ms) against the 500 ms budget, with 3 of 30 traces
  over;
- names DynamoDB as the owner of the time in the over-budget requests, by
  self time;
- mentions cold starts (3 of 30, about 310 ms of Initialization);
- recommends a fix for DynamoDB specifically (the query or access pattern),
  not a generic list.

FAIL if it invents numbers, or blames the Lambda's own code without evidence.
