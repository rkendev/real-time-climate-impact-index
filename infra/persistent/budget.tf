# Billing tripwire (ADR-0003), codified so it exists before anything spends. A
# monthly cost ceiling with an early-warning alert well below it: at this scale an
# actual spend above the alert almost certainly means a costly resource (a NAT
# gateway, a lingering public IPv4 address, or the instance) was left running
# rather than legitimate usage. AWS Budgets is free.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project_tag}-monthly"
  account_id   = var.account_id
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.budget_alert_usd
    threshold_type             = "ABSOLUTE_VALUE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.notification_email]
  }
}
