# Third-party notices

This plugin is original work released under the Apache License 2.0 (see
`LICENSE`). It distils facts from the sources below; it redistributes none of
their files. Every claim in a reference names the page it came from in that
reference's `Sources:` footer, and the maintainer's verified-facts ledger
(`.dev/`, working notes not shipped with the plugin) records what was read,
from where, and when (2026-10-05).

## Amazon Bedrock AgentCore documentation

    © Amazon Web Services, Inc. or its affiliates.
    https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/

Read 2026-10-05: gateway (overview, targets, inbound and outbound auth,
interceptors, sessions, semantic search, using MCP), identity (terminology,
authentication, Cognito getting started), runtime (service, HTTP and MCP
protocol contracts, sessions), memory (types, strategies, built-in
strategies), observability (configuration, gateway metrics), evaluations,
regions, quotas and release notes. Also the AgentCore pricing page
(https://aws.amazon.com/bedrock/agentcore/pricing/), the AWS Machine Learning
blog post "How AgentCore Gateway supports the MCP 2026-07-28 spec", the
CloudFormation `AWS::BedrockAgentCore` type list, the X-Ray, Lambda, API
Gateway and CloudWatch Application Signals pages named in the references, and
the ADOT documentation at https://aws-otel.github.io/. No documentation text
is reproduced beyond short quotations for citation.

## Terraform AWS Provider (`hashicorp/terraform-provider-aws`)

    Copyright (c) HashiCorp, Inc.
    Licensed under the Mozilla Public License 2.0
    https://github.com/hashicorp/terraform-provider-aws

Resource documentation (`website/docs/r/bedrockagentcore_*.html.markdown`) and
`CHANGELOG.md` on `main` were read on 2026-10-05 (6.64.0 released, 6.65.0
unreleased). Generated Terraform uses the provider's resource and argument
names; no provider source is included.

## AWS agent toolkit (`aws/agent-toolkit-for-aws`)

    Copyright Amazon.com, Inc. or its affiliates.
    https://github.com/aws/agent-toolkit-for-aws

The `aws-agents` plugin's README and its `agents-connect` skill were read on
2026-10-05 to describe what that plugin covers, so this one can refer to it
instead of duplicating it. Nothing is copied.

## Claude plugins directory (`anthropics/claude-plugins-official`)

    Copyright (c) Anthropic, PBC
    https://github.com/anthropics/claude-plugins-official

The marketplace manifest was read on 2026-10-05 for the `aws-agents` entry.

## AgentCore CLI (`aws/agentcore-cli`) and starter toolkit

    https://github.com/aws/agentcore-cli (Apache-2.0)
    https://github.com/aws/bedrock-agentcore-starter-toolkit, https://pypi.org/project/bedrock-agentcore-starter-toolkit/

Read on 2026-10-05 for command names, the `agentcore.json` project file and
the starter toolkit's deprecation notice. Nothing is copied.

## Strands + AgentCore reference (`aws-samples/sample-strands-agent-with-agentcore`)

    https://github.com/aws-samples/sample-strands-agent-with-agentcore

Read on 2026-10-05 as a reference architecture (Strands on Runtime with
Gateway, Memory, Identity, Code Interpreter, Browser and Observability,
deployed with Terraform). The Strands fixture in `tests/` is original.

## Model Context Protocol specification

    https://modelcontextprotocol.io/specification/2025-11-25/server/tools

The tool-name guidance (1–128 characters of A–Z a–z 0–9 _ - .) used by
`tool_names.py` was read on 2026-10-05.

## Third-party write-ups consulted

- Classmethod, "I tried enabling MCP 2026-07-28 in Amazon Bedrock AgentCore
  Gateway" (2026-07-30) — request shapes and observed response fields.
- DEV Community, "MCP new specs in practice … on AWS AgentCore Gateway"
  (2026-08-01) — observed dual-version behaviour.
- awsfundamentals.com, Bedrock AgentCore Terraform resource list.

Each is cited where used and treated as observation, not specification.

## Not included

Fixtures, templates, scripts, references and eval cases are original work
written for this plugin. `tests/fixtures/projects/vault_envs` is derived from
the first user's own Terraform with every name, domain and account id replaced.
