# ADR-0005: Infrastructure-as-code and the ephemeral-teardown design

Status: decided (tool: Terraform; two-layer ephemeral split; S3 remote state)
Date: 2026-07-16 (revised)
Related: `adr/0003-cloud-topology.md`, `50_cloud_strategy.md`, NFR-C1, NFR-C2, UC-7, and AT-11 in `30_plan.md`

## Context

The cheapest AWS shape (ADR-0003) depends on one discipline above all others: the costly resources must never be left running between demos. The dominant cost driver is compute-while-running, and the classic budget leaks (a NAT gateway, an unattached or attached public IPv4 address, a forgotten instance) are all resources that should exist only during a demo. A manual "remember to delete things in the console" process is exactly how a $50 ceiling gets blown. The setup and teardown must therefore be codified, reproducible, and verifiable, not manual. This ADR records that design choice. The actual code is a Phase 2 build artifact; this spec set stays code-free.

## Decision: Terraform

Infrastructure is defined as code with Terraform. A single `terraform apply` stands the project up and a single `terraform destroy` tears it down, so provisioning and teardown are one reproducible command each rather than a console checklist. Every resource carries a project cost-allocation tag so spend and any stragglers are auditable.

Terraform is chosen over the alternatives for portfolio value (it is the most widely recognized IaC tool on data-engineering resumes), maturity, and the clean apply/destroy lifecycle that this project's ephemeral model needs. The alternatives considered: AWS CDK in Python (would unify the language with the consumer and is a strong second choice, but it is AWS-only and less universally recognized), CloudFormation or SAM (AWS-native with no extra tool, but more verbose and a weaker portfolio signal), and Pulumi (real languages, smaller ecosystem). Any of these could implement the same two-layer split below; the split matters more than the tool.

## The two-layer split (the mechanism that prevents leftovers)

Resources are divided into two Terraform stacks (separate state, applied and destroyed independently):

- Persistent data layer: the S3 bucket (with its Iceberg tables) and the DynamoDB table. These hold the aggregate-of-record and the serving data. They cost only cents at rest and are meant to survive between demos, so they are applied once and rarely destroyed. Their teardown is a deliberate, separate action.
- Ephemeral compute layer: the compute instance (EC2 or the Fargate service), its security group, any public IPv4 address, the IAM instance role, and anything else that bills while running. This layer is applied at the start of a demo and destroyed at the end. Nothing costly lives here longer than a demo.

The split is the guarantee. Because every resource that bills by the hour lives in the ephemeral layer, `terraform destroy` of that layer returns the project to storage-only resting cost, while the cheap durable data is untouched in the persistent layer. There is deliberately no NAT gateway in either layer: the compute instance sits in a public subnet with a tight security group, which removes the single largest silent cost.

## Teardown verification (AT-11)

Teardown is not trusted, it is verified. After `terraform destroy` of the ephemeral layer, a small audit script queries for any resource carrying the project tag that still bills by the hour (a running instance, a NAT gateway, an unattached or attached public IPv4 address, a load balancer) and fails if any remain. This is acceptance test AT-11 and it is what turns "we tear down after demos" from an intention into a checked property. The audit is also safe to run on a schedule as a backstop.

## Consequences

- Phase 2 ships two Terraform stacks plus the audit script and two commands (or Make targets): one to bring the ephemeral layer up, one to tear it down. The persistent layer has its own rarely-used apply and destroy.
- The deterministic pre-deploy gate (UC-7, AT-9) runs before the ephemeral apply, so the cheap local checks still gate the spend.
- Terraform state lives in the persistent S3 bucket, not locally. This is chosen because the whole cost-safety design depends on `terraform destroy` working reliably: local state on one machine can be lost or corrupted, which orphans running billable resources that Terraform can no longer destroy, the exact leftover-cost failure this ADR prevents. Remote state in the versioned bucket makes teardown recoverable from any machine and gives point-in-time rollback of the state itself. Details: bucket versioning is on; native S3 state locking is used (`use_lockfile = true`, Terraform 1.10 or later), so no separate DynamoDB lock table is needed; the two layers use separate state keys in the same bucket. The chicken-and-egg (the state bucket is itself Terraform-managed) is handled by a one-time bootstrap that creates the state bucket outside the main config (a short CLI step or a minimal local-state bootstrap module left untouched afterward), after which both layers use the S3 backend. State is never committed to git and never holds plaintext secrets. Local state is a defensible fallback only if Phase 2 is kept deliberately minimal and the AT-11 tag audit is accepted as the sole safety net, but it is not the choice for a project whose headline discipline is no leftover cost.
- An S3 bucket that still holds objects will block `terraform destroy` unless emptied first or created with force-destroy enabled; since the data bucket lives in the persistent layer that is rarely destroyed, this does not affect the routine demo teardown, but the persistent-layer destroy path must handle it.

## Falsifiable triggers

- If the audit (AT-11) ever finds a billable resource surviving a teardown, the split is wrong: move that resource into the ephemeral layer or fix its dependency so `terraform destroy` removes it.
- If managing two stacks proves more friction than value at this scale, collapse to one stack but keep the tag-based teardown audit, accepting that a full destroy then also removes the cheap data.
- If the team later adopts a different IaC tool as a portfolio standard, migrate these stacks rather than running two tools.
