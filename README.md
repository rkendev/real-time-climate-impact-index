# Real-Time Climate Impact Index

A streaming data pipeline that turns live weather and air quality readings into a per-region Climate Impact Index, with a confidence label attached to every number, and runs the exact same processing code on a laptop or on AWS by changing one config flag.

Live demo: https://climate-index.85-215-55-99.sslip.io

Github repo: github.com/rkendev/real-time-climate-impact-index

## What it is

Most streaming demos show a number moving on a chart and ask you to trust it. This project takes the opposite stance: every index value is paired with a confidence label that is computed from how much clean data actually backed that window, and readings that fail validation are quarantined rather than silently averaged in. If the evidence for a region is thin, the dashboard says so instead of pretending the number is solid.

The pipeline reads weather and air quality readings for representative cities in each region, publishes them to a single-node Kafka broker, runs a deterministic validation-and-quarantine gate, aggregates the survivors into event-time tumbling windows keyed by a natural identity so a replay produces the same row rather than a duplicate, computes the index and its confidence, and writes the result to a store that a read-only Streamlit dashboard reads back.

The source is itself a config-selected adapter, exactly like the storage backend. `real` fetches live readings from Open-Meteo; `simulated` runs the original generators and remains the default, so the test suite and the local quickstart stay offline and deterministic. That distinction is what makes the confidence grade mean something. On a generated feed nothing can fail to arrive, so a low grade had to be arranged deliberately. On the real feed a timed-out request or a null field produces a genuine gap, and the committed grader turns that gap into a lower grade on its own. Nothing anywhere sets a grade by hand, and a reading that fails to arrive is left out rather than filled in.

The distinctive engineering choice is portability. The core processing code has no cloud SDK in it at all. A single configuration flag selects the storage backend: locally the aggregates land in DuckDB and the raw feed in the local filesystem; on AWS the same aggregates land in an Apache Iceberg table cataloged in Glue on S3, the serving copy lands in DynamoDB, and the raw feed lands in plain S3. The processor does not know or care which one is active. That is enforced, not aspirational: a test invariant fails the build if any cloud SDK import appears under the core package.

## Architecture

```mermaid
flowchart TB
    W[Open-Meteo weather] --> SRC[Source adapter<br/>selected by one config flag]
    S[Open-Meteo air quality] --> SRC
    G[Simulated generators] --> SRC
    SRC --> P[Producer]
    P -->|events| K[Kafka broker<br/>single-node KRaft]
    K --> V{Validate and<br/>quarantine}
    V -->|invalid| Q[Quarantine]
    V -->|valid| WIN[Event-time<br/>tumbling windows]
    WIN --> C[Compute index<br/>and confidence grade]
    C --> A[Store adapter<br/>selected by one config flag]
    A -->|local| DD[DuckDB aggregates<br/>and local raw files]
    A -->|aws| ICE[S3 and Apache Iceberg via Glue<br/>aggregate of record]
    A -->|aws| DYN[DynamoDB<br/>serving store]
    A -->|aws| RAW[S3<br/>raw feed]
    DD --> DASH[Read-only Streamlit dashboard]
    DYN --> DASH
```

The configured source publishes to Kafka; a deterministic gate validates each event or quarantines it; the survivors are bucketed into event-time windows and reduced to an index with a confidence grade; and a single config flag routes the result to DuckDB locally or to S3 with Apache Iceberg via Glue plus DynamoDB on AWS, all behind the same interface, with the read-only dashboard reading the local aggregates or the AWS serving store.

## How it is built

The project is spec-driven. A single specification document is the source of truth, and code, tests, and infrastructure are downstream artifacts that trace back to it by stable IDs. Every functional requirement, non-functional requirement, use case, entity, invariant, and acceptance test carries an ID, and a change to behavior starts as an edit to the ID that owns it rather than as a direct code patch. The reading order and the traceability contract are documented below so the repo can be read the way it was built.

The build ran in two gated phases. Phase 1 stood the whole pipeline up locally on a single machine with DuckDB, provable end to end with no cloud account involved. Phase 2 added the AWS adapters behind the existing storage interfaces, wrote the infrastructure as two-layer Terraform, and then crossed a deliberate spend boundary exactly once to prove the cloud path on real services under a hard cost ceiling.

Correctness is checked offline before any money is spent. The AWS store adapters are tested against moto so the S3, Iceberg, DynamoDB, and Glue code paths are exercised with no live account and no charge. The suite runs 203 tests green with 2 skipped, under strict mypy on the whole source tree, with lint and a set of build-hygiene gates that check things like a single consistent set of dependency pins and the absence of secrets in tracked files. Terraform is formatted, validated, and planned entirely offline with no credentials.

## What the cloud gate caught

Offline tests with moto get the logic right but they cannot reproduce the real control planes. The point of gating a single paid run behind all the offline checks was to catch exactly the class of problem that only appears against real AWS. It caught four. The Glue database needed an explicit catalog id tied to the account. The Terraform provider had to stop skipping account resolution on a real apply, which drove a small offline_plan switch that keeps validate and plan credential-free while a real apply turns it off. The Iceberg Glue client needed the region present in the box environment. And the processor role needed one more Glue permission because the client creates its namespace idempotently. None of these were visible offline. All four are fixed and committed.

## The paid run, and what it proved

The single Phase 2 spend window ran in us-east-1 for about forty minutes and was torn down immediately afterward. Two properties that moto physically cannot exercise were proven on live services. Replaying one window against the real Glue-cataloged Iceberg table left exactly one row for that key, which is the catalog-plane merge that the offline suite can only approximate. DynamoDB read latency measured a p95 of 130 milliseconds over fifty reads across forty-eight seeded windows, comfortably under the one-second requirement, and that was measured across the public internet so it is faster in region. The dashboard served an HTTP 200 with index, label, and confidence for all four regions.

Then everything billable was destroyed. A tag-based teardown audit confirmed that no billable resource still carried the project tag, backed up by a region-wide sweep for stray instances, NAT gateways, elastic IPs, and load balancers. The persistent layer, which costs effectively nothing at rest, was left standing so the demo can be reproduced with a single command. Total spend for the run was under five cents against a fifty-dollar ceiling with a twelve-dollar budget alarm wired in and confirmed live before any compute started.

## Run it locally

The local path needs no cloud account. It brings up a single-node Kafka broker, runs the producer and processor, and serves the dashboard, all against DuckDB.

```bash
make bootstrap        # create the virtualenv and install pinned deps
make hooks            # install the pre-commit hygiene gates
make run_processor    # start the validation, windowing, and index compute
make run_producer     # feed readings from the configured source (simulated by default)
make ui               # open the read-only Streamlit dashboard
```

To exercise the full pipeline inside containers over a live broker in one shot:

```bash
make container-smoke
```

The quality gates that run in the build are available directly:

```bash
make lint
make type-check       # strict mypy over the source tree
make test             # 203 passed, 2 skipped
```

## Live demo

A hosted instance of the local pipeline runs continuously at [climate-index.85-215-55-99.sslip.io](https://climate-index.85-215-55-99.sslip.io). It serves the read-only dashboard and refreshes its data every thirty minutes, so the numbers advance on their own. The AWS path is run on demand rather than left standing, which keeps it at near-zero cost.

![Dashboard overview](docs/img/dashboard-overview.png)

*The dashboard: a region's current index, its label, and its confidence grade, above the index plotted over recent thirty-minute windows on a UTC axis.*

![Confidence strip](docs/img/confidence-strip.png)

*The confidence strip: every thirty-minute window is colored by the grade the pipeline computed from that window's own data (teal measured, amber inferred, red ambiguous), so a thin window is flagged rather than hidden.*

## Run it on AWS

The AWS path is the same processing code with the storage backend flag flipped. Infrastructure is two-layer Terraform: a persistent layer that rests at near-zero cost (buckets, DynamoDB, Glue database, IAM, the budget alarm, and an ECR repository) and an ephemeral layer (the VPC, security group, and a single Graviton instance) that exists only for a demo. The image is delivered through ECR and the box pulls it with its instance role, so no secret, credential, or token ever lands on the instance or in any tracked file.

Because the persistent layer is left standing, reproducing the whole cloud demo is a single ephemeral apply, and the runbook records the exact one-command sequence along with the recorded spend. The pre-deploy gate refuses to proceed unless the offline checks are green first.

## Reading the repo

The specification set is meant to be read in order.

- `docs/00_project_description.md`: the concept, the story, and the scope boundary.
- `docs/10_prd.md`: product requirements, with a deliberately heavy non-functional section, which is the emphasis of the project.
- `docs/20_spec.md`: the source-of-truth specification. System use cases and the entity model. Everything downstream traces to an ID here.
- `docs/30_plan.md`: the phased delivery plan (local, then AWS), the invariants, and the acceptance tests mapped to use cases.
- `docs/40_tasks.md`: the ordered task backlog for the local phase.
- `docs/50_cloud_strategy.md`: the local-first-then-AWS path and why AWS is the only cloud target.
- `docs/60_panjuta_application.md`: how the reusable patterns harvested from earlier work apply to this pipeline.
- `adr/`: the architecture decision records. ADR-0002 selects the Python consumer, ADR-0003 selects the cheapest viable AWS shape under a fifty-dollar ceiling, ADR-0004 is the non-functional invariant law, ADR-0005 records the Terraform setup-and-teardown design that keeps costly resources from lingering, ADR-0006 records ECR as the image-delivery mechanism, and ADR-0007 records the event-source adapter, the choice of data provider, and the rule that a missing reading is never fabricated.
- `RUNBOOK.md`: the one-command cloud re-demo and the recorded spend.
- `SETUP.md`: local setup and the recorded G1 timing.

## Traceability contract

Every functional requirement (FR-), non-functional requirement (NFR-), use case (UC-), entity (E-), invariant (INV-), and acceptance test (AT-) has a stable ID. Downstream code, tests, and infrastructure reference these IDs. A change to behavior starts as an edit to the ID that owns it, not as a code patch. The repository name is brand-neutral and the Python package is `climate_index`, consistent with the project's clean-commit-trail rule.

## Data sources and attribution

In real mode the readings come from [Open-Meteo](https://open-meteo.com/): the forecast API for temperature, precipitation, wind speed, and cloud cover, and the air quality API for aerosol optical depth. Both are free for non-commercial use and need no API key, and the demo's request volume sits far below the free tier.

Weather and air quality data by Open-Meteo. Atmospheric composition from the CAMS ENSEMBLE data provider.

Two honest caveats, stated on the dashboard as well as here. These products are model analyses rather than station observations, so the page says "readings" and never "observations". And there is no free live per-coordinate vegetation index at this integration cost, so the vegetation term is a per-region monthly reference value held in configuration; it is not a measurement and is never presented as one. The per-region temperature normals are derived from ERA5 daily means over 1991-2020 for the same cities, and the derivation parameters are recorded in the specification so the constants are reproducible.

## Tech

Python 3.12, Apache Kafka (single-node KRaft), DuckDB, Apache Iceberg via pyiceberg, AWS S3, DynamoDB, and Glue, Terraform, Docker and Docker Compose, ECR with arm64 images on Graviton (t4g), Streamlit, moto for offline AWS testing, pytest, mypy (strict), and pre-commit build-hygiene gates.

