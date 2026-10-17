# Quotas that matter at deploy time

Checked 2026-10-05 against the AgentCore service quotas page. "Adjustable"
means a Service Quotas increase request, which takes time: file it before the
deploy that needs it.

## Gateway

| Quota | Value | Adjustable |
|---|---|---|
| gateways per account | 1,000 | yes |
| targets per gateway | 100 | yes (`DPL002`) |
| tools per target | 1,000 | yes (`DPL002`) |
| tool name length | 256 | yes |
| invocation timeout | 15 min | yes |
| tools/call + tools/list | 200 TPS per gateway and per account | yes |
| concurrent connections | 5,000 per gateway and per account | yes |
| Create/Update/Delete gateway | 5 TPS | yes |

The 200 TPS account-level tool-call rate is shared by every gateway in the
account and region; a load test against one gateway can throttle another.

## Runtime

| Quota | Value | Adjustable |
|---|---|---|
| active session workloads | 5,000 (US East/West), 2,500 (other regions, including eu-central-1) | yes |
| new sessions | 25 TPS | yes |
| data plane | 1,000 TPS | yes |
| agents / versions / endpoints | 1,000 / 1,000 / 10 | yes |
| image size | 2 GB | no |
| hardware per session | 2 vCPU / 8 GB | no |
| control-plane mutations | 50 TPS | no |

## Memory

| Quota | Value | Adjustable |
|---|---|---|
| memories per region | 150 | yes |
| strategies per memory | 6 | no |
| CreateMemory / UpdateMemory / DeleteMemory | 3 TPS | yes |

## Identity

| Quota | Value | Adjustable |
|---|---|---|
| workload identities | 11,000 | yes |
| OAuth2 / API key providers | 50 / 50 | yes |
| token APIs | 200 TPS | yes |

## Checking an account

```bash
aws service-quotas list-service-quotas --service-code bedrock-agentcore --region "$AWS_REGION" \
  --query 'Quotas[].{name:QuotaName,value:Value,adjustable:Adjustable}' --output table
```

The service code is assumed to be `bedrock-agentcore`; if the call returns
nothing, list codes with `aws service-quotas list-services`.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
