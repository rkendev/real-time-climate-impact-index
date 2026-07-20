# Persistent data stack (ADR-0005 layer 1).
#
# Holds only durable, near-free resources plus the IAM roles and the billing
# tripwire: the two S3 buckets, the DynamoDB serving table, the Glue catalog
# database, least-privilege IAM, and the AWS Budgets ceiling. Nothing here bills
# by the hour, so this stack is applied once and rarely destroyed; every
# hourly-billing resource lives in the ephemeral stack instead. Proven with an
# offline, credential-free terraform validate and plan (init -backend=false).

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Remote state in the bootstrap bucket. Native S3 state locking (use_lockfile,
  # Terraform 1.10+) needs no DynamoDB lock table. The bucket and region are
  # supplied via -backend-config at the real init (P2-T3); the offline validate
  # and plan use init -backend=false and never touch this backend.
  backend "s3" {
    key          = "persistent/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

# The skip flags plus passing the account id as a variable (never
# aws_caller_identity) let validate and plan run credential-free with no AWS
# contact. default_tags stamps every taggable resource with the project tag,
# which the AT-11 teardown audit and cost allocation rely on.
provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true

  default_tags {
    tags = {
      Project = var.project_tag
    }
  }
}
