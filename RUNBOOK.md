# Runbook: deploy, verify, tear down (gate G2)

The operational runbook for the terminal cloud phase. Everything buildable offline
is proven green before any spend; the paid window is bounded and torn down
immediately (there is no auto-stop backstop, so teardown is non-negotiable).

## Resting state

Between demos the project sits at storage-only rest cost: data in S3 (Iceberg
aggregate-of-record and raw) and DynamoDB (serving), the Glue database, the ECR
repository, and the budget alarm. No compute runs. A re-demo is a single ephemeral
apply against this standing persistent layer.

## Offline gates (no spend, run first)

```
make lint type-check test        # all green
make smoke                       # writes the .smoke_ok marker
make container-smoke             # producer to dashboard through a live Kafka broker
make tf-fmt tf-validate tf-plan  # all three stacks validate and plan offline
make pre-deploy-gate             # AT-9: marker, single-sourced versions, terraform valid
```

Only on a green `pre-deploy-gate` may the paid sequence begin.

## Paid sequence (bounded; only after the gate is green)

Prerequisites (no spend): confirm current region pricing and free-tier eligibility;
fill the git-ignored `terraform.tfvars` in each stack; fetch the current arm64
AL2023 AMI id into `infra/ephemeral/terraform.tfvars`:

```
aws ssm get-parameters \
  --names /aws/service/ami-al2023-latest-arm64 \
  --region <region> --query 'Parameters[0].Value' --output text
```

Then, in order:

```
# 1. Bootstrap the remote-state bucket (one time, outside the main config).
terraform -chdir=infra/bootstrap init && terraform -chdir=infra/bootstrap apply

# 2. Init the two stacks on the real S3 backend.
terraform -chdir=infra/persistent init -backend-config=... 
terraform -chdir=infra/ephemeral  init -backend-config=...

# 3. Apply the persistent stack (buckets, DynamoDB, Glue, IAM, budget, ECR repo).
#    offline_plan=false lets the provider resolve the account id (needed for Glue).
TF_VAR_project_tag=$(.venv/bin/python -c 'from climate_index.config import get_settings; print(get_settings().project_tag)') \
  TF_VAR_offline_plan=false terraform -chdir=infra/persistent apply
#    Confirm the 12 dollar budget alarm is live in the console.

# 4. Build the arm64 image and push it to ECR (from the workstation, not the box).
export ECR_REPO=$(terraform -chdir=infra/persistent output -raw ecr_repository_url)
make image-build image-push          # buildx --platform linux/arm64, then push

# 5. Apply the ephemeral stack. The box pulls the image and runs the stack via
#    user_data (docker login by instance role, docker compose pull and up).
#    Pass ecr_repository_url and image_tag into the ephemeral tfvars first.
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral apply

# 6. Run the producer for a bounded batch (via SSM Session Manager on the box):
#    cd /opt/climate-index && docker compose run --rm producer
```

## Verify on AWS (exit gate G2)

```
CII_AGGREGATE_BACKEND=aws make verify-at5      # replay yields exactly one Iceberg row (real Glue)
CII_AGGREGATE_BACKEND=aws make verify-nfr-p3   # DynamoDB read p95 under one second
```

Also confirm the dashboard is reachable at the instance public address on the
dashboard port from the owner IP, showing the index, its verbal label, and its
confidence.

## Tear down immediately (manual, no backstop)

```
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral destroy
make teardown-audit                            # AT-11: no billable resource carries the project tag
```

Leave the persistent layer standing. Record the actual spend below.

## Re-demo (one command against the standing persistent layer)

```
export ECR_REPO=$(terraform -chdir=infra/persistent output -raw ecr_repository_url)
make image-push                                 # only if the image changed
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral apply
```

Tear down with the ephemeral destroy plus `make teardown-audit` as above.

## Recorded spend (paid run 2026-07-20, us-east-1)

- Instance: t4g.medium, up for roughly 40 minutes, then destroyed.
- Actual spend: under 0.05 US dollars (t4g.medium ~40 min about 0.025, public IPv4
  about 0.004, S3 and DynamoDB and Glue and ECR operations pennies). Cost Explorer
  showed 0 for the project tag at teardown time (billing data lags several hours).
  Far under the 50 dollar ceiling.
- AT-5 against the real Glue catalog: OK (replaying one window left exactly one
  Iceberg row for EUR).
- NFR-P3: OK (DynamoDB read p95 130 ms over 50 reads across 48 seeded windows,
  under the 1000 ms target; measured cross-internet, so faster in-region).
- Aggregates populated in both stores: DynamoDB and the S3 Iceberg or Glue table.
- Dashboard reachable at the instance public address on port 8501 from the owner
  IP, serving the index, verbal label, and confidence for all four regions.
- AT-11 post-teardown audit: clean (no billable resource carries the project tag).
- Persistent layer left standing at near-zero rest (state, warehouse, and raw
  buckets; DynamoDB; Glue database; ECR image; budget alarm).

## Notes learned on the run (folded into the code)

- Real applies pass `TF_VAR_offline_plan=false` so the provider resolves the
  account id (the offline default keeps validate and plan credential-free).
- The Glue database sets `catalog_id` explicitly, pyiceberg's Glue catalog needs
  `AWS_REGION` in the box environment, and the processor role needs
  `glue:CreateDatabase` (pyiceberg calls it idempotently on first table creation).
