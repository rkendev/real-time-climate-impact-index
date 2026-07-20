# ADR-0006: Container image delivery via ECR

Status: decided (private ECR repository in the persistent layer; arm64 built on the host, pulled by instance role)
Date: 2026-07-20
Related: `adr/0003-cloud-topology.md`, `adr/0005-iac-and-teardown.md`, `50_cloud_strategy.md`, INV-1, and G2 in `30_plan.md`

## Context

ADR-0003 runs the same containers in the cloud as locally, on one small ARM (t4g, Graviton) instance. It says "the same container image" but does not say how that image reaches the box. Three constraints from ADR-0003, ADR-0005, and INV-1 settle the question:

- The box is secret-free: it authenticates by its IAM instance role only, with no static AWS key and no git token (INV-1). So it cannot `git clone` a private repository or hold registry credentials.
- The paid window must be short (no auto-stop backstop, ADR-0005). Building the image or running `pip install` on the box during the paid window wastes that window and risks a slow or failed boot.
- The build host is x86_64 while the box is arm64. An x86 image fails at boot on Graviton with an exec-format error, so the image must be built for `linux/arm64`.

## Decision

Deliver the one app image through a private Amazon ECR repository:

- The repository lives in the **persistent** Terraform layer (alongside S3, DynamoDB, and Glue), so it survives between demos at near-zero rest cost and a re-demo needs no rebuild. A lifecycle policy expires untagged and surplus images so storage stays near zero.
- The image is **built for `linux/arm64` on the build host** (`docker buildx --platform linux/arm64`) and pushed to ECR from the operator workstation, which already holds AWS credentials for Terraform. Nothing is built on the box.
- The box **pulls the image via its instance role**: the persistent stack grants the processor role `ecr:GetAuthorizationToken` (not resource-scoped by ECR, so on `*`) plus the pull actions scoped to the repository ARN. No push permission is granted to the box; the image is pushed only from the host. `user_data` runs `aws ecr get-login-password | docker login`, then `docker compose pull` and `up`, so no build and no `pip install` runs during the paid window.

The push happens only after the persistent stack applies (it holds the repository), and before the ephemeral stack applies (the box pulls at boot).

## Consequences

- The image is a build artifact delivered out of band from the source; the box carries no source tree and no build toolchain.
- One more persistent resource (the repository and its lifecycle policy) and one more instance-role permission set (ECR pull). Both are near-zero cost and fully torn-down-independent: the repository is persistent, the box that pulls from it is ephemeral.
- The compose project the box runs pulls `image: <repository-url>:<tag>` rather than building, so the local and cloud stacks share the same image contents while differing only in how the image is obtained.

## Falsifiable triggers

- If image size or pull time dominates the boot and stretches the paid window, slim the image (multi-stage build, fewer layers) or pre-bake an AMI; do not move the build onto the box.
- If a second architecture is ever targeted, publish a multi-arch manifest from the host rather than building per-box.
- If the secret-free constraint is ever relaxed (it should not be), this ADR is void and the delivery mechanism is reconsidered from scratch.
