---
type: llm
---

PASS if the response:

- says the MCP Lambda is in PassThrough mode and will not start a segment;
- says the HTTP API cannot be X-Ray traced and how its share is measured
  instead (access log latency);
- says DynamoDB and Secrets Manager calls will be invisible without ADOT or a
  tracer, and names the ADOT layer approach;
- does not hold the export worker to the same rule;
- offers to generate the tracing changes, with a cost tier, and asks first.

FAIL if it edits files or claims API Gateway HTTP APIs support X-Ray.
