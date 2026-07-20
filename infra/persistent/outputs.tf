# Outputs consumed by the ephemeral stack at apply time (P2-T3). They are wired
# in as input variables there (not read via a terraform_remote_state data source),
# so each stack validates and plans standalone and offline.

output "processor_role_name" {
  description = "Name of the processor role the ephemeral instance profile assumes."
  value       = aws_iam_role.processor.name
}

output "processor_role_arn" {
  description = "ARN of the processor role."
  value       = aws_iam_role.processor.arn
}

output "dashboard_role_arn" {
  description = "ARN of the read-only dashboard role (matrix fidelity; app-level on the single box)."
  value       = aws_iam_role.dashboard.arn
}

output "iceberg_warehouse_bucket" {
  description = "Iceberg warehouse bucket name (set CII_ICEBERG_WAREHOUSE_BUCKET from this)."
  value       = aws_s3_bucket.iceberg_warehouse.id
}

output "raw_s3_bucket" {
  description = "Raw store bucket name (set CII_RAW_S3_BUCKET from this)."
  value       = aws_s3_bucket.raw.id
}

output "dynamo_table" {
  description = "DynamoDB serving-store table name (set CII_DYNAMO_TABLE from this)."
  value       = aws_dynamodb_table.serving.name
}

output "glue_database" {
  description = "Glue catalog database name (set CII_ICEBERG_NAMESPACE from this)."
  value       = aws_glue_catalog_database.iceberg.name
}
