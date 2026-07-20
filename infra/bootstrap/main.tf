# Remote-state bootstrap (ADR-0005), run once by the owner.
#
# Chicken-and-egg: the persistent and ephemeral stacks keep their state in an S3
# bucket, but that bucket must exist before those stacks can init. This minimal
# config uses a local backend to create the versioned, encrypted, access-blocked
# state bucket a single time, then is left untouched. It is applied as a P2-T3
# setup step; nothing here is applied in P2-T2. Validated offline like the other
# stacks (terraform validate needs no credentials and makes no AWS call).

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# The skip flags let validate and a credential-free plan run with no AWS contact
# and no account lookup. They are harmless on the real apply, which still uses
# the owner credentials from the environment.
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

# The remote-state bucket itself. Versioned so a corrupt state can be rolled
# back, fully private, and encrypted at rest. Native S3 state locking
# (use_lockfile) in the consuming stacks needs no separate DynamoDB lock table.
resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

output "state_bucket" {
  description = "Name of the remote-state bucket the other stacks configure as their S3 backend."
  value       = aws_s3_bucket.state.id
}
