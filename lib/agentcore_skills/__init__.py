"""Stdlib-only helpers shared by the `agentcore` plugin's skill scripts.

Nothing in this package imports `boto3`, `botocore` or any AWS SDK. Terraform,
CDK and agent code are *read*, never executed, so every check runs in a bare
Python 3.10+ interpreter on a laptop with no AWS credentials. Anything that has
to touch AWS is emitted as an `aws` CLI or `terraform` command for the user to
run after confirming; the one script that talks to a network endpoint
(`agentcore-verify/scripts/verify.py`) uses `urllib` against a URL the user
names.

Every constant below that describes Amazon Bedrock AgentCore was read on the
date in `DOCS_CHECKED` from the pages listed in `.dev/VERIFIED-FACTS.md`, and
the tabular facts (regions, pricing, quotas, Terraform coverage, MCP revisions)
live as data files under `data/`, each carrying its own `source` and `checked`.
"""

__version__ = "0.2.0"

#: The date the AgentCore developer guide, pricing page and quotas were read.
DOCS_CHECKED = "2026-10-05"

#: The hashicorp/aws provider release whose documentation the generated
#: Terraform was checked against (the docs on `main`, with 6.65.0 unreleased at
#: the top of CHANGELOG.md), and the oldest release the generators assume.
#: 6.55.0 is what the first real user has locked.
PROVIDER_CHECKED = "6.64.0"
PROVIDER_MIN_ASSUMED = "6.55.0"

#: MCP protocol revisions AgentCore Gateway accepts (developer guide,
#: "Use an AgentCore gateway", read 2026-10-05). 2026-07-28 is opt-in through
#: `protocolConfiguration.mcp.supportedVersions`; a request with no version
#: header is treated as 2025-03-26.
GATEWAY_MCP_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")
GATEWAY_MCP_DEFAULT_WHEN_HEADER_MISSING = "2025-03-26"
MCP_STATELESS_REVISION = "2026-07-28"

#: The plugin's default latency budget, from the Alexa+ add-on requirement the
#: first user brought: the whole tool call, end to end, in half a second.
DEFAULT_BUDGET_MS = 500

#: Tool names on a gateway are `${target_name}___${tool_name}`.
GATEWAY_TOOL_SEPARATOR = "___"
