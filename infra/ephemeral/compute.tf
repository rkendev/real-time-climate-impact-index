# The compute box and its instance profile. On this single shared box all
# containers share the instance role, so the instance profile carries the
# processor role (from the persistent stack); the dashboard's read-only property
# stays enforced at the application layer (INV-2), as in Phase 1. Per-component
# IAM separation is fully realized only on per-task compute.

resource "aws_iam_instance_profile" "processor" {
  name_prefix = "${var.project_tag}-processor-"
  role        = var.processor_role_name
}

locals {
  # The registry host to docker login to, and the concrete image reference the box
  # pulls, both derived from the persistent stack's ECR output (ADR-0006).
  ecr_registry = split("/", var.ecr_repository_url)[0]
  app_image    = "${var.ecr_repository_url}:${var.image_tag}"
}

# The t4g (ARM) instance is the primary hourly-billing resource, together with its
# auto-assigned public IPv4. Destroying this stack removes both.
resource "aws_instance" "app" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.instance.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.processor.name

  user_data = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    aws_region               = var.aws_region
    iceberg_warehouse_bucket = var.iceberg_warehouse_bucket
    raw_s3_bucket            = var.raw_s3_bucket
    dynamo_table             = var.dynamo_table
    iceberg_namespace        = var.iceberg_namespace
    iceberg_table            = var.iceberg_table
    dashboard_port           = var.dashboard_port
    ecr_registry             = local.ecr_registry
    app_image                = local.app_image
    compose_plugin_version   = var.compose_plugin_version
  })

  # IMDSv2 only.
  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    encrypted = true
  }
}
