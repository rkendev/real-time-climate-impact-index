# 50 Cloud Strategy

Version: 0.4.0 (budget + IaC teardown)
Related: `adr/0003-cloud-topology.md` (the decision record), `30_plan.md` (phase gates)

## Principle: local first, then AWS, no intermediate hop

The system is proven on one machine before any cloud resource is provisioned (NFR-C1). The sequence is local, then AWS, and it stops there. There is no Hugging Face step: this is a streaming data-engineering pipeline (Kafka, a stream processor, an aggregate store, a dashboard) rather than a single request-response inference app, so a Spaces container is a poor fit and would add a throwaway hop. The owner has direct AWS access, so the pipeline goes straight to a real cloud.

## Why AWS, and why one cloud

The owner has decided AWS is the only cloud target. The earlier draft planned a second move to GCP as a portability proof, and that second phase is dropped. Dropping it also removes two problems the review flagged: GCP Pub/Sub is not Kafka-API-compatible, and GCP has no managed Apache Flink, so a cross-cloud story would have strained the fixed-Kafka anchor and the processor abstraction. With one cloud and the cheapest-shape decision (ADR-0003), the transport stays literally Kafka but runs as the same single-node container as local rather than a managed MSK cluster, and the processor is the Python consumer, not Managed Flink.

## The portable core and the single cloud adapter

The core (models, validation, feature and index computation, and the two interfaces for transport and store) never imports a cloud SDK. AWS is one adapter pair behind those interfaces:

- Transport adapter: publishes and consumes envelopes against Kafka. Locally this is Kafka in Docker; on AWS it is the same single-node Kafka container running on a small ephemeral compute instance (the cheapest option chosen in ADR-0003), not a managed MSK cluster.
- Store adapter: writes the aggregate-of-record and raw records to Amazon S3 with Apache Iceberg, and serves read-only dashboard queries from Amazon DynamoDB.

The adapter boundary is kept even with one cloud. It is no longer a multi-cloud claim; it is anti-lock-in hygiene that keeps cloud SDKs out of the core (INV-4, NFR-PT1), keeps the core unit-testable without cloud credentials, and preserves an exit path.

## The AWS shape (decided in ADR-0003: the cheapest option)

The owner chose the cheapest AWS shape given budget. Compute and transport are the same containers as local (single-node Kafka in KRaft mode, the Python consumer, and the Streamlit dashboard) running on one small ARM compute instance (a t4g-class EC2 running docker compose, or ECS Fargate tasks), provisioned by infrastructure-as-code and torn down between demos. The aggregate-of-record and raw data live in S3 as Iceberg tables, which gives the MERGE needed for idempotent writes on the natural key (FR-6, NFR-R1). The dashboard is served from Amazon DynamoDB (partition key region, sort key window_start), which meets the sub-second target (NFR-P3), upserts idempotently on the natural key, and is near-free at idle. Athena over S3 serves ad-hoc and backfill queries, off the latency-bound path. EKS, MSK, and Managed Flink were ruled out on idle cost; see ADR-0003 for the reasoning and the upgrade path if budget later allows.

## Least-privilege action matrix (NFR-SEC4)

Every AWS role grants only what its component needs.

| Component | Transport (Kafka) | Aggregate store (S3 Iceberg) | Serving store (DynamoDB) | Raw store (S3) |
|-----------|-------------------|------------------------------|--------------------------|----------------|
| Producer | write | none | none | none |
| Processor | read | write | write | write |
| Dashboard | none | none | read | none |

No component holds a capability outside its row. The dashboard reads only DynamoDB and has no transport, aggregate-of-record, or raw access (INV-2, NFR-SEC3).

## The deterministic pre-deploy gate (NFR-C1, UC-7)

Before any AWS provisioning, a cheap deterministic check runs: the local smoke marker from gate G1 must exist, dependency versions must be single-sourced and consistent, and the AWS config must be present and parse. Only on pass does the expensive provisioning proceed. This is the cost-asymmetric gate from the Panjuta harvest applied to deployment: a cheap check upstream of an expensive irreversible-spend step (see `60_panjuta_application.md`). The deploy command refuses and names the failed check otherwise (AT-9).

## Cost controls (NFR-C2)

Idle cost is the dominant lever for an intermittently-run project, so the design keeps all persistent state in S3 and DynamoDB, which cost only cents at rest for this volume and sit within the free tier, and provisions the compute instance only during a demo. The resting state is data-at-rest with no compute running and near-zero spend.

The monthly spend ceiling is 50 US dollars, with a billing alarm at 10 to 15 dollars as an early-warning tripwire. That ceiling is generous: a small ARM instance left on all month is roughly 10 dollars and storage is cents, so exceeding the alarm at this scale almost always means a costly resource was left running. The three cost traps are handled by design: no NAT gateway (the instance sits in a public subnet with a tight security group), the public IPv4 hourly charge is accounted for, and teardown is codified rather than manual. Setup and teardown are done with Terraform in a two-layer split (a persistent data layer for S3 and DynamoDB, an ephemeral compute layer torn down after each demo), with a tag-based audit that verifies no billable resource survives a teardown; this is specified in ADR-0005 and checked by AT-11. If spend approaches the ceiling before the exit gate, the response is to tear down and reduce scope (fewer regions, shorter retention), not to raise the ceiling. Confirm current pricing and free-tier eligibility for the chosen region before provisioning.

## Secrets and configuration (NFR-SEC1, NFR-SEC2, INV-1)

Endpoints and credentials come from the AWS secret backend into the config object at the adapter layer only. No secret or endpoint literal appears in source or logs. The compute and dashboard modules cannot import credential names. This is identical discipline to the local phase, differing only in which secret backend the adapter reads.
