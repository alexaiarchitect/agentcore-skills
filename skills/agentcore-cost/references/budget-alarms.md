# Budget and alarm

`gen_budget.py` writes `agentcore-budget/` with two guards.

## The budget

```hcl
resource "aws_budgets_budget" "agentcore" {
  name         = "${var.name}-agentcore"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "Service"
    values = var.cost_explorer_services   # default ["Amazon Bedrock AgentCore"]
  }
  notification { … 80 % FORECASTED … }
  notification { … 100 % ACTUAL … }
}
```

The service filter value is the name Cost Explorer shows for AgentCore. It
was **not confirmed** for this plugin; once the first AgentCore charge posts,
check the Service dimension in Cost Explorer and set
`cost_explorer_services` to exactly that string. A wrong value produces a
budget that never alerts.

Notifications go to the e-mail addresses given and, if `alarm_topic_arn` is
set, to an SNS topic whose policy allows `budgets.amazonaws.com` to publish
(the first user's observability module already has one with that statement).

This budget is filtered to AgentCore only; keep the account-wide budget the
project may already have (`CST010`).

## The alarm

Budgets data lags by hours. A runaway client is caught faster by usage:

```hcl
resource "aws_cloudwatch_metric_alarm" "gateway_invocations" {
  namespace           = "AWS/Bedrock-AgentCore"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = 3600
  threshold           = <hourly volume from the profile x 3>
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
```

With `--profile`, the threshold is requests per day × (tool calls + list
calls) / 24 × 3, at least 10. Add the gateway's `dimensions` after listing
them (`aws cloudwatch list-metrics --namespace AWS/Bedrock-AgentCore`);
without dimensions the alarm watches the namespace total for the account.

## What these cost

AWS Budgets and CloudWatch alarms are billed at their own prices (not
modelled here); both are small next to what they protect.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://aws.amazon.com/bedrock/agentcore/pricing/ (read 2026-10-05). The `aws_budgets_budget` and
`aws_cloudwatch_metric_alarm` arguments are the hashicorp/aws resources' standard ones, not re-read for this plugin.
