---
type: llm
---

PASS if the response:

- gives the total as AgentCore lines only, with the per-service split;
- points out that short-term Memory switches from per-1,000-events to per-GB
  pricing on 2026-10-06, and that going live next week means the new card
  applies (ideally having re-run with `--as-of`);
- lists what is not priced (Lambda, API Gateway, CloudWatch, X-Ray, DynamoDB);
- notes the prices are list prices from a page that does not publish
  per-region rates.

FAIL if it calls the total "the bill", or prices model tokens it was not given.
