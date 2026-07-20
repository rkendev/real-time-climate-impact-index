# Ephemeral compute stack (ADR-0005 layer 2).
#
# Holds everything that bills by the hour: the VPC and its public networking, the
# security group, the t4g instance, its instance profile, and the auto-assigned
# public IPv4. Because every hourly-billing resource lives here, terraform destroy
# of this stack returns the project to storage-only rest while the persistent data
# is untouched. Deliberately no NAT gateway (ADR-0003 cost trap). Proven with an
# offline, credential-free terraform validate and plan (init -backend=false).

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Separate state key in the same bootstrap bucket as the persistent stack;
  # native S3 locking, no DynamoDB lock table. Bucket and region come via
  # -backend-config at the real init (P2-T3); offline uses init -backend=false.
  backend "s3" {
    key          = "ephemeral/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = var.offline_plan
  skip_requesting_account_id  = var.offline_plan
  skip_metadata_api_check     = var.offline_plan

  default_tags {
    tags = {
      Project = var.project_tag
    }
  }
}
