output "alarm_topic_arn" {
  value      = aws_sns_topic.alarms.arn
  depends_on = [aws_sns_topic_policy.alarms]
}
output "dashboard_name" { value = aws_cloudwatch_dashboard.vault.dashboard_name }
