# Durable stores: two S3 buckets (Iceberg warehouse and raw), the DynamoDB
# serving table, and the Glue catalog database. All near-free at rest.

# Iceberg aggregate-of-record warehouse (ADR-0003). force_destroy defaults false
# so a bucket still holding objects blocks destroy until deliberately emptied
# (ADR-0005); set var.force_destroy_buckets true only for an intentional teardown.
resource "aws_s3_bucket" "iceberg_warehouse" {
  bucket        = var.iceberg_warehouse_bucket
  force_destroy = var.force_destroy_buckets
}

resource "aws_s3_bucket_versioning" "iceberg_warehouse" {
  bucket = aws_s3_bucket.iceberg_warehouse.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "iceberg_warehouse" {
  bucket = aws_s3_bucket.iceberg_warehouse.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "iceberg_warehouse" {
  bucket = aws_s3_bucket.iceberg_warehouse.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Append-only raw store (FR-7): a separate S3 target from the aggregate-of-record,
# carrying no Iceberg table and no MERGE.
resource "aws_s3_bucket" "raw" {
  bucket        = var.raw_s3_bucket
  force_destroy = var.force_destroy_buckets
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# DynamoDB serving store (ADR-0003), on-demand billing, keyed exactly as the
# P2-T1 adapter expects: partition key region, sort key window_start.
resource "aws_dynamodb_table" "serving" {
  name         = var.dynamo_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "region"
  range_key    = "window_start"

  attribute {
    name = "region"
    type = "S"
  }

  attribute {
    name = "window_start"
    type = "S"
  }
}

# Glue catalog database that holds the Iceberg table: the production catalog the
# P2-T1 Iceberg adapter targets on AWS. catalog_id is set explicitly from
# var.account_id because the provider runs with skip_requesting_account_id (so
# validate and plan stay offline), which otherwise leaves the CatalogId empty on
# apply and the CreateDatabase call fails.
resource "aws_glue_catalog_database" "iceberg" {
  name       = var.iceberg_namespace
  catalog_id = var.account_id
}
