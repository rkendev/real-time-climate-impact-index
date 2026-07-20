# Inputs for the ephemeral stack. The owner IP, AMI id, and processor role name
# are not literals here (INV-1); real values come from a git-ignored
# terraform.tfvars (see terraform.tfvars.example). project_tag is injected from
# config.project_tag via TF_VAR_project_tag by the Make targets. The bucket,
# table, namespace, and role-name values are wired from the persistent stack's
# outputs at apply time (P2-T3), passed as variables rather than read through a
# terraform_remote_state data source so this stack validates and plans standalone.

variable "aws_region" {
  description = "AWS region for the compute stack."
  type        = string
}

variable "project_tag" {
  description = "Cost-allocation tag value, single-sourced from config.project_tag via TF_VAR_project_tag."
  type        = string
}

variable "owner_ip" {
  description = "Owner IP in CIDR form (for example 203.0.113.4/32) allowed to reach the dashboard port. No other ingress is opened."
  type        = string
}

variable "dashboard_port" {
  description = "TCP port the read-only dashboard listens on."
  type        = number
  default     = 8501
}

variable "ami_id" {
  description = "ARM (t4g-compatible) AMI id. Passed as a variable rather than an aws_ami data source so plan stays offline."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type. Defaults to a t4g (ARM) size with headroom for the full container stack under the cost ceiling."
  type        = string
  default     = "t4g.medium"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for the single public subnet."
  type        = string
  default     = "10.0.1.0/24"
}

variable "processor_role_name" {
  description = "Name of the processor IAM role from the persistent stack output; the instance profile assumes it."
  type        = string
}

variable "iceberg_warehouse_bucket" {
  description = "Iceberg warehouse bucket name from the persistent stack output; passed to the container stack as CII_ICEBERG_WAREHOUSE_BUCKET."
  type        = string
}

variable "raw_s3_bucket" {
  description = "Raw store bucket name from the persistent stack output; passed as CII_RAW_S3_BUCKET."
  type        = string
}

variable "dynamo_table" {
  description = "DynamoDB serving table name from the persistent stack output; passed as CII_DYNAMO_TABLE."
  type        = string
}

variable "iceberg_namespace" {
  description = "Glue catalog database name; passed as CII_ICEBERG_NAMESPACE. Mirrors config.iceberg_namespace."
  type        = string
  default     = "climate_index"
}
