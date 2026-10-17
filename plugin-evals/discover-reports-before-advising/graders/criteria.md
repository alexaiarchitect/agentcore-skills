---
type: llm
---

PASS if the response:

- names the region as eu-central-1 and says where that came from (the
  provider's variable default, Terragrunt);
- says Gateway and Memory are available there, citing the discovery output;
- lists what exists: the HTTP API with a JWT authorizer, the MCP Lambda
  (nodejs24.x, arm64), the Cognito pool and its clients, the provider lock
  6.55.0, Terragrunt;
- notes the Lambda is not actively traced.

FAIL if it answers availability without running discovery, or invents
resources.
