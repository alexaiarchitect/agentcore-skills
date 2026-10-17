# Framework signatures

Discovery labels a project's agent framework from imports, never from file
names or README text. Python is parsed with `ast`, so the labels below are
exact for Python; JavaScript and TypeScript are matched by import pattern.

| Label | Python import | JS/TS import or dependency |
|---|---|---|
| `strands` | `strands` | `@strands-agents/sdk` |
| `langgraph` | `langgraph` | `@langchain/langgraph` |
| `langchain` | `langchain` | — |
| `claude-agent-sdk` | `claude_agent_sdk` | `@anthropic-ai/claude-agent-sdk` |
| `crewai` | `crewai` | — |
| `llamaindex` | `llama_index` | — |
| `google-adk` | `google.adk` | — |
| `openai-agents` | `from agents import Agent` | `@openai/agents` |
| `autogen` | `autogen` | — |
| `pydantic-ai` | `pydantic_ai` | — |
| `mastra` | — | `@mastra/core` |

`openai-agents` needs `agents.Agent` specifically, because a top-level
package called `agents` is common in unrelated projects.

## AgentCore-specific signals

| Signal | What it implies |
|---|---|
| `from bedrock_agentcore.runtime import BedrockAgentCoreApp` + `@app.entrypoint` | an HTTP-protocol Runtime agent; `/invocations` and `/ping` are served by the wrapper |
| `from bedrock_agentcore.memory import MemoryClient` | short/long-term memory in use |
| `@requires_access_token(provider_name=..., auth_flow="M2M"\|"USER_FEDERATION")` | outbound OAuth through AgentCore Identity |
| `@requires_api_key(...)` | outbound API key through AgentCore Identity |
| `FastMCP(..., stateless_http=True)` + `mcp.run(transport="streamable-http")` | an MCP-protocol Runtime server |
| `aws-opentelemetry-distro` in requirements; `opentelemetry-instrument` in `CMD` | ADOT instrumentation for AgentCore observability |

## Tracing libraries

| Label | Evidence |
|---|---|
| `aws-xray-sdk` | `aws-xray-sdk-core`, `aws_xray_sdk` (maintenance mode since 2026-02-25, end of support 2027-02-25) |
| `powertools-tracer` | `@aws-lambda-powertools/tracer` |
| `opentelemetry` | `@opentelemetry/*`, `opentelemetry` |
| `adot` | `aws-opentelemetry-distro`, the ADOT Node autoinstrumentation package |

The AWS reference sample `aws-samples/sample-strands-agent-with-agentcore`
combines Strands with Runtime, Gateway (Lambda MCP tools, JWT), Memory,
Identity (3LO), Code Interpreter, Browser, Registry and Observability, and
deploys with Terraform (`infra/modules/`, `infra/environments/dev/`); it is a
useful shape to compare a project against.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-authentication.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-eos.html,
https://github.com/aws-samples/sample-strands-agent-with-agentcore (read 2026-10-05).
