# Least-privilege IAM per the docs/50_cloud_strategy.md action matrix. Policies
# are rendered locally with aws_iam_policy_document (no AWS call), and every ARN
# is built from var.account_id and var.aws_region rather than aws_caller_identity,
# so validate and plan stay fully offline.
#
# Matrix realized here: the processor may read+write both S3 stores, read+write
# the Glue Iceberg table and its database, and read+write the DynamoDB table; the
# dashboard may only read DynamoDB; the producer touches no AWS service (it writes
# only to the local Kafka container) and so has no role or policy.
#
# Single-box consequence (ADR-0003 EC2 shape): the ephemeral stack's instance
# profile carries the processor role because all containers share one box, so the
# dashboard's read-only property stays enforced at the application layer (INV-2),
# as in Phase 1. This dashboard role documents the matrix and is fully realized as
# a separate identity only on per-task compute.

locals {
  warehouse_arn     = "arn:aws:s3:::${var.iceberg_warehouse_bucket}"
  raw_arn           = "arn:aws:s3:::${var.raw_s3_bucket}"
  dynamo_arn        = "arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/${var.dynamo_table}"
  glue_catalog_arn  = "arn:aws:glue:${var.aws_region}:${var.account_id}:catalog"
  glue_database_arn = "arn:aws:glue:${var.aws_region}:${var.account_id}:database/${var.iceberg_namespace}"
  glue_table_arn    = "arn:aws:glue:${var.aws_region}:${var.account_id}:table/${var.iceberg_namespace}/${var.iceberg_table}"
  # The ECR repo lives in this same stack; reference the resource so the ARN needs
  # no manual account/region assembly and validate stays offline.
  ecr_repository_arn = aws_ecr_repository.app.arn
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "processor" {
  statement {
    sid       = "S3ObjectReadWrite"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.warehouse_arn}/*", "${local.raw_arn}/*"]
  }

  statement {
    sid       = "S3BucketList"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.warehouse_arn, local.raw_arn]
  }

  statement {
    sid = "GlueReadWrite"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
      "glue:BatchGetPartition",
    ]
    resources = [local.glue_catalog_arn, local.glue_database_arn, local.glue_table_arn]
  }

  statement {
    sid = "DynamoWriteRead"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable",
    ]
    resources = [local.dynamo_arn]
  }

  # Pull-only access to the one app image (ADR-0006). GetAuthorizationToken is not
  # resource-scoped by ECR, so it is a separate statement on "*"; the layer and
  # image reads are scoped to this project's repository. No push permission: the
  # image is pushed from the build host, never from the box.
  statement {
    sid       = "EcrAuthToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [local.ecr_repository_arn]
  }
}

resource "aws_iam_role" "processor" {
  name               = "${var.project_tag}-processor"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy" "processor" {
  name   = "processor-least-privilege"
  role   = aws_iam_role.processor.id
  policy = data.aws_iam_policy_document.processor.json
}

# Operator shell without an open SSH port: SSM Session Manager needs this managed
# policy on the instance role (the security group opens no port 22).
resource "aws_iam_role_policy_attachment" "processor_ssm" {
  role       = aws_iam_role.processor.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "dashboard" {
  statement {
    sid       = "DynamoReadOnly"
    actions   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:DescribeTable"]
    resources = [local.dynamo_arn]
  }
}

resource "aws_iam_role" "dashboard" {
  name               = "${var.project_tag}-dashboard"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy" "dashboard" {
  name   = "dashboard-read-only"
  role   = aws_iam_role.dashboard.id
  policy = data.aws_iam_policy_document.dashboard.json
}
