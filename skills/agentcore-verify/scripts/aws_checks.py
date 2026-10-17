#!/usr/bin/env python3
"""Emit the aws CLI commands that verify what verify.py cannot see from outside.

Some post-deploy facts live only behind AWS APIs: that the gateway is READY
and its targets synchronised, that the credential provider and workload
identity exist, that the Runtime answers InvokeAgentRuntime, that traces for
the last few minutes reached X-Ray, and what the gateway's own Latency and
TargetExecutionTime metrics say. This script reads the project's Terraform
for the names and region, and prints those commands with the identifiers
filled in where they could be resolved. It runs nothing: every command is for
you to run (cost tier `aws`: reads are cheap, but they are your account's API
calls).

    aws_checks.py <project> [--gateway-id ID] [--runtime-arn ARN] [--region R]
                  [--service-name NAME] [--minutes 15] [--budget-ms 500] [--json]

Exit codes: 0 commands emitted, 2 bad arguments.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DEFAULT_BUDGET_MS, cli  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_OK, EXIT_USAGE  # noqa: E402


def commands(*, region: str, gateway_id: str, runtime_arn: str | None, service: str, minutes: int,
             budget_ms: float, providers: list[str]) -> list[dict[str, str]]:
    window = (f"--start-time $(date -u -d '-{minutes} minutes' +%s 2>/dev/null || date -u -v-{minutes}M +%s) "
              f"--end-time $(date -u +%s)")
    out = [
        {"check": "gateway is READY", "cmd": f"aws bedrock-agentcore-control get-gateway --region {region} "
         f"--gateway-identifier {gateway_id} --query '{{status:status,url:gatewayUrl,versions:protocolConfiguration.mcp.supportedVersions,authorizer:authorizerType}}'"},
        {"check": "targets are READY and synchronised", "cmd": f"aws bedrock-agentcore-control list-gateway-targets "
         f"--region {region} --gateway-identifier {gateway_id} --query 'items[].{{name:name,status:status}}'"},
        {"check": "OAuth2 credential providers exist", "cmd": f"aws bedrock-agentcore-control list-oauth2-credential-providers "
         f"--region {region} --query 'credentialProviders[].name'"},
        {"check": "API key credential providers exist", "cmd": f"aws bedrock-agentcore-control list-api-key-credential-providers "
         f"--region {region} --query 'credentialProviders[].name'"},
        {"check": "workload identities", "cmd": f"aws bedrock-agentcore-control list-workload-identities --region {region}"},
        {"check": f"traces in the last {minutes} min over {budget_ms:g} ms",
         "cmd": f"aws xray get-trace-summaries --region {region} {window} "
                f"--filter-expression 'service(\"{service}\") AND responsetime > {budget_ms / 1000:g}' "
                "--query 'TraceSummaries[].{id:Id,rt:ResponseTime}'"},
        {"check": "trace count in the window (any latency)",
         "cmd": f"aws xray get-trace-summaries --region {region} {window} --filter-expression 'service(\"{service}\")' "
                "--query 'length(TraceSummaries)'"},
        {"check": "gateway Latency and TargetExecutionTime (p50/p95, 5-minute periods)",
         "cmd": f"aws cloudwatch get-metric-statistics --region {region} --namespace AWS/Bedrock-AgentCore "
                f"--metric-name Latency --extended-statistics p50 p95 --period 300 "
                f"--start-time $(date -u -d '-{minutes} minutes' +%FT%TZ 2>/dev/null || date -u -v-{minutes}M +%FT%TZ) "
                "--end-time $(date -u +%FT%TZ)  # add --dimensions after listing them: aws cloudwatch list-metrics "
                "--namespace AWS/Bedrock-AgentCore"},
    ]
    for name in providers:
        out.append({"check": f"provider {name}", "cmd": f"aws bedrock-agentcore-control get-oauth2-credential-provider "
                    f"--region {region} --name {name}"})
    if runtime_arn:
        out.append({"check": "runtime answers", "cmd": f"aws bedrock-agentcore invoke-agent-runtime --region {region} "
                    f"--agent-runtime-arn {runtime_arn} --runtime-session-id $(python3 -c 'import uuid;print(uuid.uuid4().hex+\"-verify\")') "
                    "--payload '{\"prompt\": \"ping\"}' --cli-binary-format raw-in-base64-out /dev/stdout"})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--gateway-id", default="$GATEWAY_ID")
    parser.add_argument("--runtime-arn", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--service-name", default=None, help="X-Ray service name, e.g. the Lambda function name")
    parser.add_argument("--minutes", type=int, default=15)
    parser.add_argument("--budget-ms", type=float, default=float(DEFAULT_BUDGET_MS))
    cli.add_format(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return EXIT_USAGE
    project = load(root)
    region = args.region or project.primary_region() or "$AWS_REGION"
    service = args.service_name
    if not service:
        names = [b.get("function_name") for b in project.lambdas()]
        service = (names[0] or "").strip('"') if names and names[0] and "${" not in names[0] else "<lambda function name>"
    providers = [str(b.literal("name")) for b in project.tf.resources_of("aws_bedrockagentcore_oauth2_credential_provider")
                 if isinstance(b.literal("name"), str)]
    cmds = commands(region=region, gateway_id=args.gateway_id, runtime_arn=args.runtime_arn, service=service,
                    minutes=args.minutes, budget_ms=args.budget_ms, providers=providers)
    if args.format == "json":
        print(json.dumps({"region": region, "commands": cmds, "note": "nothing was run"}, indent=2))
    else:
        print(f"# agentcore-verify: AWS-side checks ({region})\n\nNothing was run. Each command is read-only.\n")
        for item in cmds:
            print(f"## {item['check']}\n\n```bash\n{item['cmd']}\n```\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
