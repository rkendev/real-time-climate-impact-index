# 10 Product Requirements Document

Version: 0.4.0
Owner: Roy
Related: `20_spec.md` (use cases and entities), `adr/` (decisions), `30_plan.md` (delivery)

This document states what the system must do (functional requirements) and, with more weight, how well it must do it (non-functional requirements). Non-functional requirements are the emphasis of this project. Each requirement has a stable ID and a verification method so that it is testable rather than aspirational.

## 1. Actors

- Producer: a simulated source that emits weather and satellite events for the configured regions.
- Stream processor: the component that validates, windows, and computes the index.
- Store: the persistence layer holding raw events and per-region-per-window aggregates.
- Viewer: a human reading the read-only dashboard.
- Operator: the person running the canonical commands and reading logs and metrics.

## 2. Functional requirements

FR-1 Event generation. The producer generates weather events (temperature, rainfall, wind) and satellite events (cloud cover, vegetation index, aerosol index), each stamped with a UTC timestamp and a region code, for the configured region set. Verify: unit test on the generator output shape and value ranges.

FR-2 Single transport topic. All events are published to one stream transport, each message wrapped in an envelope carrying an event type field (weather or satellite) and the payload. Verify: contract test on the envelope shape.

FR-3 Schema validation at ingest. The processor validates every consumed event against the schema for its type before it is used. Invalid events are quarantined and counted, never silently dropped and never written to the aggregate store. Verify: unit test feeding malformed events and asserting the quarantine count and the absence of a bad aggregate.

FR-4 Feature computation. Per region, the processor computes a temperature anomaly, a dryness index, and a pollution index from the validated events in the current window. Verify: unit tests with fixed inputs and known expected outputs.

FR-5 Index computation. The processor combines the component features into a single Climate Impact Index over an event-time tumbling window (default thirty minutes, configurable), normalized to a fixed range, for each region. Verify: unit test asserting the index formula and range on fixed inputs.

FR-6 Aggregate persistence. For each region and closed window, the store receives one row: window start, window end, region, impact index, and the component metrics. Writes are idempotent on the natural key (region, window start, window end). Verify: smoke test asserting one row per region per window and no duplicates on replay.

FR-7 Raw persistence. Raw validated events are persisted for audit and replay. Verify: smoke test asserting raw counts match produced counts minus quarantined counts.

FR-8 Read-only dashboard. The dashboard shows, per selected region, a time series of the impact index, the current value, and a verbal label (low, medium, high). It performs no computation of the index and issues no writes. Verify: a test asserting the dashboard module imports no writer and no compute function, plus manual view.

FR-9 Verbal label mapping. The index range maps to low, medium, or high by fixed, documented thresholds. Verify: unit test on the threshold function.

FR-10 Canonical commands. The operator drives the system through a fixed command set (bootstrap, infra up, run producer, submit or run the processor, smoke, dashboard). Verify: each command exists and the smoke command returns non-zero on a broken pipeline.

## 3. Non-functional requirements (emphasis)

Each NFR states a target, a rationale, and a verification method. Targets are first drafts to be confirmed against the first local measurement, following the portfolio rule that a target is a hypothesis until a run produces a real number.

### 3.1 Performance and latency

NFR-P1 Ingest throughput. A single producer instance sustains at least 200 events per second for the configured regions on a developer laptop without loss. Verify: load the producer for sixty seconds and compare sent versus consumed counts.

NFR-P2 End-to-end freshness. The median delay from a window closing to its aggregate row being queryable in the store is under 5 seconds locally. Verify: stamp window-close time in logs, stamp write time, compare.

NFR-P3 Dashboard query latency. The dashboard returns a region time series in under 1 second at the p95 over a store holding at least twenty-four hours of windows. In the cloud phase this target is met by serving the dashboard from Amazon DynamoDB, not from Athena over S3, which is seconds-latency; see `adr/0003-cloud-topology.md`. Verify: seed the store, time the query at p95, on both the local store and the DynamoDB serving store.

### 3.2 Scalability

NFR-S1 Region scaling. Adding a region changes configuration only, not code. The system runs correctly with the region count raised from four to sixteen. Verify: run with sixteen regions and assert one aggregate stream per region per window.

NFR-S2 Partitioning readiness. The transport topic is partitioned by region key so that horizontal consumer scaling is possible without reordering within a region. Verify: assert the producer sets the region as the message key.

### 3.3 Reliability and availability

NFR-R1 Delivery semantics. Phase 1 targets at-least-once delivery with idempotent aggregate writes (FR-6), so that a consumer restart does not create duplicate aggregate rows. Idempotency depends on deterministic window keys (event-time bucketing) and on committing offsets only after the window's aggregate write succeeds; both are specified in ADR-0002. Exactly-once is explicitly deferred. Verify: kill and restart the consumer mid-run and assert no duplicate aggregate rows and no undercount.

NFR-R2 Recovery. After a process crash and restart, the system resumes consuming from the last committed offset and the smoke test passes without manual repair. Any window open at crash time is reprocessed and re-formed deterministically, because its offsets were not yet committed; this recovery model is stated in ADR-0002 and holds only with event-time bucketing and commit-after-write. Verify: crash injection during the smoke run, asserting the reprocessed window matches the pre-crash expectation.

NFR-R3 Backpressure safety. If the store write path stalls, the consumer slows rather than dropping events or exhausting memory. Verify: throttle the writer and assert consumer lag grows while memory stays bounded.

NFR-R4 Graceful degradation of the index. When a window has events of only one type, the index is still computed from available components and its confidence is graded down rather than the record being dropped. See NFR-DQ2 and `60_panjuta_application.md`. Verify: unit test with single-type windows.

### 3.4 Observability

NFR-O1 Structured logging. Every component emits structured logs with, at minimum, component name, event counts, per-region counts where useful, and window boundaries in the processor. Verify: parse logs in the smoke test and assert the required fields exist.

NFR-O2 Health and liveness. Each long-running component exposes a health signal (a log heartbeat in Phase 1, a health endpoint in the cloud phases). Verify: assert a heartbeat within a bounded interval.

NFR-O3 Metrics-only telemetry. Any telemetry the system emits about its own operation contains counts, rates, and boundaries only, never raw event payloads or secrets. This is the metadata-only telemetry rule carried from the portfolio. Verify: a test that scans emitted telemetry for payload or secret patterns and fails on a match.

### 3.5 Portability (local to AWS; anti-lock-in hygiene)

AWS is the only cloud target. Portability is kept not as a multi-cloud claim but as anti-lock-in hygiene: it keeps cloud SDKs out of the core, keeps the core unit-testable without cloud credentials, and preserves an exit path.

NFR-PT1 Portable core. The core (event models, schema validation, feature and index computation, the store interface, and the dashboard read interface) imports no cloud-vendor SDK. All vendor specifics live behind adapter modules with a stable interface. This is invariant INV-4 in `adr/0004`. Verify: a test asserting no cloud SDK import appears under the core package.

NFR-PT2 Transport abstraction. The code depends on a transport interface, not on a concrete client, so that local Kafka in Docker and the same Kafka container on AWS (and, if budget later allows, a managed MSK) are adapter swaps. Kafka is the fixed transport everywhere (see ADR-0002 and ADR-0003). Verify: a test that the core references only the transport interface.

NFR-PT3 Store abstraction. The code depends on a store interface so that local DuckDB maps to the AWS store shape (S3 with Iceberg for the aggregate-of-record and raw data, plus DynamoDB as the serving store for the dashboard). Verify: a test that the core references only the store interface.

### 3.6 Security

NFR-SEC1 No secrets in code or logs. All connection details, endpoints, and credentials come from a config object populated from the environment. No secret or endpoint literal appears in source or logs. This is invariant INV-1. Verify: a grep test over source and a scan over logs.

NFR-SEC2 Credential isolation. Credentials are readable only by the connection or adapter layer, never by the compute or dashboard modules. Verify: a test asserting no credential name is importable into core or dashboard modules.

NFR-SEC3 Read-only serving. The dashboard connects to the store with read-only access and holds no write capability. This is invariant INV-2. Verify: assert the dashboard uses a read-only connection or role.

NFR-SEC4 Least privilege in cloud. Each cloud role grants only the actions its component needs (producer writes to the stream, processor reads the stream and writes aggregates, dashboard reads aggregates). Verify: policy review against the action matrix in `50_cloud_strategy.md`.

### 3.7 Maintainability and reproducibility

NFR-M1 Single source of truth for dependencies. One runtime requirements file is installed by both the host environment and any container. Dev and tool dependencies are pinned in one place and a check fails the build if a pin disagrees across files. This follows the portfolio single-source-pinning rule. Verify: a version-consistency check across all dependency-declaring files.

NFR-M2 Build hygiene gate. The pre-commit configuration must parse and install on a clean checkout, and the check for this must fail red on a knowingly broken config. This directly addresses the earlier build where a pre-commit config never parsed and a silent bootstrap swallowed the failure. Verify: a CI step that validates the config and a seeded-broken fixture that must fail.

NFR-M3 Deterministic environment. A clean bootstrap produces a working environment with no manual steps. The clone-to-green time is measured and recorded, not asserted. Verify: time a clean bootstrap.

NFR-M4 Documentation in sync. The project description, PRD, spec, plan, and tasks stay consistent. A behavior change begins as a spec edit, per the spec-driven rule. Verify: review gate on pull requests touching behavior without a spec change.

### 3.8 Testability and data quality

NFR-T1 Schema contracts. Raw and aggregate data have declared schema contracts enforced at runtime and in tests. Verify: schema validation in the pipeline and in unit tests.

NFR-DQ1 Deterministic validation gate. Data acceptance is decided by a deterministic schema and threshold check, not by any model judgment. Anomalies are surfaced as flagged candidates and a deterministic gate decides accept or quarantine. This applies the Panjuta convergence pattern (see `60_panjuta_application.md`). Verify: unit test on the gate with valid, borderline, and invalid inputs.

NFR-DQ2 Provenance-graded confidence. Each aggregate row carries a confidence grade derived from input completeness: MEASURED when both stream types are present in the window, INFERRED when a component is imputed from a single type, AMBIGUOUS when input is sparse below a threshold. The dashboard shows the grade. This applies Graphify's provenance grading from the Panjuta harvest. Verify: unit test mapping window input composition to grade.

### 3.9 Cost

NFR-C1 Local first, cheap before expensive. No cloud resource is provisioned until the local smoke test is green. A cheap deterministic pre-deploy check gates the expensive cloud step. This applies the cost-asymmetric pre-spend gate from the Panjuta harvest. Verify: the deploy command refuses to run when the local smoke marker is absent.

NFR-C2 Spend ceiling and codified teardown. The AWS phase runs under a monthly spend ceiling of 50 US dollars, with a billing alarm at 10 to 15 dollars as an early-warning tripwire. Setup and teardown are done as code (Terraform, see ADR-0005), split into a persistent data layer and an ephemeral compute layer, so the costly resources exist only during a demo and are removed by one command afterward. Verify: the documented ceiling and alarm exist, and AT-11 confirms that after teardown no billable resource carrying the project tag remains.

## 4. Verification summary

Every FR and NFR above names a verification method. The plan in `30_plan.md` turns these into acceptance tests (AT-*) with owning phases. A requirement with no acceptance test is not considered delivered.

## 5. Decisions now locked (previously open)

- Stream processor: the Python consumer (ADR-0002). Kafka as the transport is fixed. Flink is a deferred, ADR-gated upgrade.
- Cloud: AWS only, cheapest shape (ADR-0003). Local containers on one small ephemeral compute instance, S3 with Iceberg as the aggregate-of-record, DynamoDB as the serving store, Athena for ad-hoc queries. EKS, MSK, and Managed Flink were ruled out on idle cost; the upgrade path if budget grows is recorded in ADR-0003.
