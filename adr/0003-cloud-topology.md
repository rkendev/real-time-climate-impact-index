# ADR-0003: Cloud topology (AWS only, cost-minimizing shape)

Status: decided (cost-constrained; owner chose the cheapest AWS option)
Date: 2026-07-16 (revised)
Related: `50_cloud_strategy.md`, `adr/0002-stream-processor.md`, NFR-PT1, NFR-PT2, NFR-PT3, NFR-P3, NFR-R1, NFR-SEC4, NFR-C1, NFR-C2, INV-4

## Context

AWS is the only cloud target. The owner has chosen the cheapest AWS option given a limited budget. Kafka is fixed as the transport protocol, not as a specific managed product. Two facts drive the decision: the aggregate volume is tiny (a handful of regions times roughly forty-eight windows a day, so kilobytes), and the system runs intermittently for demos rather than continuously. For an intermittent workload, idle cost is the dominant lever, so the cheapest design keeps durable state in services that are near-free at rest and provisions compute only while a demo is running.

## Decision

Ruled out on cost:

- EKS: the control plane bills roughly 0.10 US dollars per hour (about 73 per month) before any worker node, a constant idle cost for no benefit here.
- MSK provisioned and MSK Serverless: both carry a broker-hour or cluster-hour baseline that dwarfs a single small container at this volume.
- Amazon Managed Service for Apache Flink: a running KPU baseline, and unnecessary because ADR-0002 selected the Python consumer.

The cheapest shape:

- Compute and transport: run the same containers used locally (single-node Apache Kafka in KRaft mode, the Python consumer, and the Streamlit dashboard) on one small ARM compute instance (a t4g-class EC2 running docker compose is the cheapest and simplest; ECS Fargate tasks are the slightly more cloud-native alternative at similar cost). Provisioned by infrastructure-as-code and torn down between demos.
- Aggregate-of-record and raw store: Amazon S3 with Apache Iceberg. Near-zero at rest, and the Iceberg MERGE gives idempotent writes on the natural key (FR-6, NFR-R1, the H4 fix).
- Serving store: Amazon DynamoDB, on-demand billing, with partition key region and sort key window_start. This models the dashboard read exactly, gives a native idempotent upsert on the natural key, meets the sub-second target (NFR-P3), and is near-free at idle and within the free tier at this volume.
- Ad-hoc and backfill queries: Athena over the S3 Iceberg tables, pay-per-query, negligible at this data size, and not on the latency-bound path.

## Cost strategy (NFR-C1, NFR-C2)

Idle cost is minimized by keeping all persistent state in S3 and DynamoDB, which cost only cents at rest for this volume, and by provisioning the compute instance only during a demo. The deterministic pre-deploy gate (UC-7) is paired with a teardown command, so the normal resting state of the project is: data in S3 and DynamoDB, no compute running, near-zero spend.

Budget: the monthly spend ceiling is 50 US dollars. This is generous for this shape, where a small ARM instance left running all month is roughly 10 dollars and storage is cents. A billing alarm is set at 10 to 15 dollars as an early-warning tripwire: at this scale anything above that almost certainly means a costly resource was left running (most likely a NAT gateway, a lingering public IPv4 address, or the instance itself) rather than legitimate usage. The three known cost traps are avoided by design: no NAT gateway (the instance sits in a public subnet with a tight security group), awareness that a public IPv4 address bills by the hour, and codified teardown so nothing is forgotten. The teardown mechanism and its verification are specified in ADR-0005. Confirm current pricing and free-tier eligibility for the chosen region before Phase 2.

## Trade-off accepted

This is a cost-minimizing lift-and-shift of the local container stack, not a managed-services showcase. The owner runs single-node Kafka (the same container as local, so operational load is low, but there is no high availability and no managed patching). The managed-Kafka resume signal is deferred. If budget later allows and that signal is wanted, the upgrade path changes only the transport and processor: MSK Serverless for transport and ECS Fargate or Managed Service for Apache Flink for the processor, leaving S3 and DynamoDB unchanged. That upgrade is an adapter and infrastructure change, not a core change (INV-4).

## Consequences

- Only one cloud adapter pair (transport, store) is built. The core stays SDK-free (INV-4, AT-10).
- The store adapter is two-part: an S3 Iceberg aggregate-of-record for durability and idempotency, and a DynamoDB serving store for the dashboard. The processor writes both; the dashboard reads only DynamoDB.
- The compute host runs the Kafka, consumer, and dashboard containers; it is ephemeral and recreated per demo from infrastructure-as-code.
- The least-privilege matrix in `50_cloud_strategy.md` is implemented as IAM roles scoped to these services.

## Falsifiable triggers

- If the demo must stay up continuously rather than being torn down, re-evaluate MSK Serverless versus self-managed Kafka at that duty cycle, since the idle-cost advantage of self-managed shrinks the longer it runs.
- If the DynamoDB key model cannot serve a query the dashboard later needs, switch the serving store to Aurora Serverless v2 (which now scales to zero with auto-pause), keeping S3 as the system of record.
- If a core module needs a cloud SDK import to work (violating INV-4, AT-10), stop and move the dependency behind the adapter.
