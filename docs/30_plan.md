# 30 Delivery Plan

Version: 0.4.0
Related: `20_spec.md` (IDs), `adr/` (decisions), `50_cloud_strategy.md` (cloud detail)

The plan is phased. Phase 1 proves the system on one machine. Phase 2 moves it to AWS, which is the only cloud target (the earlier GCP phase is dropped; see `adr/0003-cloud-topology.md`). Hugging Face is not used at any point (see `50_cloud_strategy.md` for why). Each phase closes on a named gate before the next begins, which enforces the local-first, cheap-before-expensive rule (NFR-C1).

## Invariants (the standing law)

These hold in every phase. They are stated in full in `adr/0004-nonfunctional-invariants.md` and summarized here.

- INV-1: No secrets or endpoints in code or logs; all from config populated by the environment.
- INV-2: The dashboard is strictly read-only; no compute, no writes.
- INV-3: Every record entering the aggregate store passed the deterministic validation gate; invalid input is quarantined, never silently dropped or written.
- INV-4: The core package imports no cloud-vendor SDK; vendor specifics live behind adapters.
- INV-5: One source of truth for dependency versions; a check fails the build on disagreement.

## Acceptance tests

Acceptance tests map to use cases and requirements. A phase is done when its acceptance tests pass.

- AT-1 (UC-1, FR-1): the generator produces weather and satellite events that pass their schemas across a sample of runs.
- AT-2 (UC-2, FR-3, INV-3): malformed events are quarantined with a reason code and never reach an aggregate.
- AT-3 (UC-3, FR-4, FR-5): fixed inputs produce the documented component metrics and index within range.
- AT-4 (UC-3, NFR-DQ2): window input composition maps to the correct confidence grade.
- AT-5 (UC-4, FR-6, NFR-R1): replaying the same window does not create duplicate aggregate rows. Run against both adapters: locally via INSERT OR REPLACE, and on AWS via an Apache Iceberg MERGE on the natural key.
- AT-6 (UC-5, FR-8, INV-2): the dashboard module imports no writer and no compute path.
- AT-7 (UC-6, NFR-M2): a seeded broken pre-commit config makes the hygiene gate fail red.
- AT-8 (UC-6, NFR-M3): a clean bootstrap reaches a green smoke test with no manual step, and the time is recorded.
- AT-9 (UC-7, NFR-C1): the cloud deploy command refuses when the local smoke marker is absent.
- AT-10 (NFR-PT1, INV-4): no cloud-vendor SDK import appears under the core package. With one cloud, this guards anti-lock-in hygiene and keeps the core unit-testable without cloud credentials, rather than proving a second-cloud move.
- AT-11 (NFR-C2, ADR-0005): after tearing down the ephemeral compute layer, a tag-based audit finds no billable resource (running instance, NAT gateway, attached or unattached public IPv4 address, load balancer) still carrying the project tag.

## Phase 1: local, single machine

Goal: from simulated events to a correct, non-empty, duplicate-free chart, proven by a green smoke test.

Entry criteria: this spec set reviewed. ADR-0002 (stream processor: Python consumer) and ADR-0003 (cheapest AWS shape) are both decided.

Work, in order:

1. Repo skeleton and build hygiene. Package layout, single requirements file, config object plus environment example, Makefile with the canonical commands, and the pre-commit-parses gate (AT-7). Record clone-to-green time (AT-8).
2. Entity models and schemas. Implement E-1 through E-7 and the raw and aggregate schema contracts (NFR-T1).
3. Producer. UC-1 with the region key and envelope (AT-1).
4. Validation gate. UC-2 with quarantine and counters (AT-2).
5. Windowing and index. UC-3 including confidence grading (AT-3, AT-4).
6. Persistence. UC-4 with idempotent aggregate writes (AT-5).
7. Dashboard. UC-5, read-only (AT-6).
8. Smoke and operations. UC-6 end to end (AT-8).

Exit gate G1: all Phase 1 acceptance tests pass, the smoke test is green, and the local run is recorded. G1 is the marker that unlocks Phase 2 (AT-9, NFR-C1).

## Phase 2: AWS

Goal: the same core code runs behind the cheapest AWS shape decided in ADR-0003: the local containers (single-node Kafka, the Python consumer, the Streamlit dashboard) on one small ephemeral compute instance, the aggregate-of-record and raw data in S3 as Iceberg tables, and the dashboard served from DynamoDB. AWS is the terminal cloud phase.

Work, in order:

1. Infrastructure-as-code. Write the two Terraform layers per ADR-0005: a persistent data layer (S3 Iceberg tables, DynamoDB table) and an ephemeral compute layer (the instance, security group, public IP, IAM roles from the action matrix in `50_cloud_strategy.md`), plus the tag-based teardown audit (AT-11).
2. Adapters. Implement the Kafka transport adapter (against the same container image) and the two-part store adapter (S3 Iceberg aggregate-of-record plus DynamoDB serving store) behind the existing interfaces (INV-4). No change to the core.
3. Idempotency on the cloud store. Implement the Iceberg MERGE and the DynamoDB upsert on the natural key, and extend AT-5 to run against the AWS adapters.
4. Deterministic pre-deploy gate. UC-7 wired for AWS (AT-9).
5. Deploy, run, verify, tear down. Provision, run the producer, confirm aggregates populate, confirm the dashboard reads DynamoDB within NFR-P3, then tear down.
6. Cost controls. Set the spend ceiling and confirm the teardown returns the project to storage-only resting cost (NFR-C2).

Exit gate G2: the AWS pipeline passes the same acceptance tests as Phase 1 through the adapters, including AT-5 against the Iceberg store and NFR-P3 against the serving store, within the 50 dollar ceiling, and AT-11 confirms a clean teardown leaves no billable resource running. G2 is the terminal cloud gate; there is no Phase 3.

## Risks and their triggers

- Stream processor too heavy locally. If the processor chosen in ADR-0002 cannot reach a green smoke test on a laptop within the recorded bootstrap budget, fall back to the lighter option named in that ADR.
- Portability leak. If any core module needs a cloud SDK import to work, INV-4 is violated; stop and move the dependency behind an adapter before proceeding.
- Cost surprise in cloud. If the AWS phase approaches its spend ceiling before G2, tear down and reduce scope (fewer regions, shorter retention) rather than raising the ceiling.
