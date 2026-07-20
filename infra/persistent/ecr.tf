# Private ECR repository for the one app image (ADR-0006). The image is built for
# linux/arm64 on the build host and pushed here after this stack applies; the
# ephemeral box pulls it via its instance role (no static credential, INV-1). The
# repository lives in the persistent layer so it survives between demos at near-zero
# rest cost, and a re-demo needs no rebuild.

resource "aws_ecr_repository" "app" {
  name                 = "${var.project_tag}-app"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.force_destroy_buckets

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Hold rest cost near zero: keep only the few most recent images so old demo tags
# do not accumulate storage. Untagged layers expire quickly; tagged images are
# capped at a small count.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after one day."
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent tagged images."
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "demo", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 3
        }
        action = { type = "expire" }
      },
    ]
  })
}
