# Inputs for the persistent stack. No secret, endpoint, account id, or email is a
# literal here or elsewhere in the config (INV-1); real values come from a
# git-ignored terraform.tfvars (see terraform.tfvars.example). project_tag is
# injected from config.project_tag via TF_VAR_project_tag by the Make targets.

variable "aws_region" {
  description = "AWS region for the data stack."
  type        = string
}

variable "account_id" {
  description = "AWS account id, used to build Glue and DynamoDB resource ARNs and the budget (never read via aws_caller_identity, so plan stays offline)."
  type        = string
}

variable "project_tag" {
  description = "Cost-allocation tag value, single-sourced from config.project_tag via TF_VAR_project_tag."
  type        = string
}

variable "iceberg_warehouse_bucket" {
  description = "S3 bucket name for the Iceberg aggregate-of-record warehouse."
  type        = string
}

variable "raw_s3_bucket" {
  description = "S3 bucket name for the append-only raw store."
  type        = string
}

variable "dynamo_table" {
  description = "DynamoDB serving-store table name (matches the P2-T1 serving store)."
  type        = string
}

variable "iceberg_namespace" {
  description = "Glue catalog database name holding the Iceberg table. Mirrors config.iceberg_namespace (the production catalog the P2-T1 adapter targets)."
  type        = string
  default     = "climate_index"
}

variable "iceberg_table" {
  description = "Iceberg table name in the Glue database. Mirrors config.iceberg_table."
  type        = string
  default     = "climate_index"
}

variable "notification_email" {
  description = "Email address that receives the billing tripwire alert."
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly cost ceiling in USD (ADR-0003)."
  type        = number
  default     = 50
}

variable "budget_alert_usd" {
  description = "Early-warning threshold in USD; an alert above this almost certainly means a costly resource was left running (ADR-0003)."
  type        = number
  default     = 12
}

variable "force_destroy_buckets" {
  description = "When true, terraform destroy empties the buckets first. Left false so a destroy of durable data is a deliberate, empty-first action (ADR-0005)."
  type        = bool
  default     = false
}
