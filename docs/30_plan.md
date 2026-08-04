# 30 Delivery Plan

Version: 0.5.0
Related: `20_spec.md` (IDs), `adr/` (decisions), `50_cloud_strategy.md` (cloud detail), `PREREGISTRATION.md` (the frozen contract for the disagreement-grading work, commit b81f1c9)

The plan is phased. Phase 1 proves the system on one machine. Phase 2 moves it to AWS, which is the only cloud target (the earlier GCP phase is dropped; see `adr/0003-cloud-topology.md`). Hugging Face is not used at any point (see `50_cloud_strategy.md` for why). Each phase closes on a named gate before the next begins, which enforces the local-first, cheap-before-expensive rule (NFR-C1).

## Invariants (the standing law)

These hold in every phase. They are stated in full in `adr/0004-nonfunctional-invariants.md` and summarized here.

- INV-1: No secrets or endpoints in code or logs; all from config populated by the environment.
- INV-2: The dashboard is strictly read-only; no compute, no writes.
- INV-3: Every record entering the aggregate store passed the deterministic validation gate; invalid input is quarantined, never silently dropped or written.
- INV-4: The core package imports no cloud-vendor SDK; vendor specifics live behind adapters.
- INV-5: One source of truth for dependency versions; a check fails the build on disagreement.
- INV-6: No network I/O in the core package; every external data source sits behind a source adapter selected by config (ADR-0007).

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
- AT-12 (UC-1, FR-1, ADR-0007): with `CII_SOURCE_BACKEND=real` and the network available, one producer tick emits at least one weather and one satellite envelope per configured region, all of which pass the unchanged validation gate, and the resulting window rows carry grades produced by the committed grader. A live check run by hand against the real provider, deliberately not a unit test: no network enters the suite, and the offline adapter tests drive `httpx.MockTransport` instead.
- AT-13 (UC-8, FR-12, FR-13, NFR-DQ3, NFR-DQ4, ADR-0009): station observations reconcile against the model analysis end to end. Over recorded fixtures, every closed region-window carries a PM2.5 disagreement state and a provenance tier; a window whose sources disagree beyond the frozen tolerance reports both values and names the cities that drove it, with neither value substituted, averaged or preferred; a window with no qualifying station coverage carries the unchecked tier; and pollution_index is byte-identical to the same run with reconciliation disabled, which is what proves the disagreement state did not leak into the index.

### Acceptance tests are not the only required guards

AT-13 is the system-level test for UC-8, and it is the only new acceptance test, as the contract's scope states. **The seeded violations that NFR-DQ3 and NFR-DQ4 require are separate guards and are not acceptance tests.** They are unit and integration tests placed where the violation is observable rather than at the system boundary, and they are required regardless of the acceptance-test count:

This list is a ledger, not a to-do. Each entry carries where its proof lives, because a requirement whose discharge is not recorded is a requirement that quietly does not happen, and a reader who cannot tell which entries are done has a list that stops being read.

- **DISCHARGED** (T3a, `3f5e773`). One seeded violation for NFR-DQ3, in which the pipeline is made to resolve a disagreement rather than report it, and which must turn its guard red. Proof: `tests/unit/test_seeded_dq3_resolution.py`. Three seeds rather than one, because resolution has three shapes that fail independently: substitution, averaging, and preference expressed by dropping one side. The guard and all three seeds go through `assert_reported_never_resolved`, so the red proof exercises the shipped guard rather than a bespoke assertion.
- **DISCHARGED** (T3a, `816a60c`). Two seeded violations for NFR-DQ4, seeded separately because the branches fail independently: one forcing a computed tier onto a window with no qualifying coverage, and one forcing a window to inherit a neighbouring or previous window's tier. Each must turn its guard red on its own. Proof: `tests/unit/test_seeded_dq4_fabrication.py`, through `assert_tier_earned_by_this_window`. The uncovered branch also seeds a forged coverage count, so a window claiming coverage it did not have is caught as well as one carrying a tier it did not earn. The inheritance branch is only visible over a fixture whose previous window and neighbouring region differ from the target, so `assert_fixture_can_expose_inheritance` states that requirement and is itself proven red against three fixtures each lacking one of its three properties.
- **DISCHARGED** (T2, `9daeb93`). One seeded violation for the widened validation gate (FR-3, INV-3, E-4), in which a malformed station payload and an envelope carrying an event type outside the declared set are each fed to the gate and must quarantine with a reason code rather than passing through. Proof: `tests/unit/test_station_boundary.py`, three seeds. The gate was written when the envelope had two members, and a gate that silently admits an unrecognised type is a gate that cannot fail on the case it was widened for. AT-2 covers the two original types; this extends the same proof to the third rather than assuming it generalised.

AT-13 is **DISCHARGED** (T3a, `3fd27e5`), at `tests/integration/test_at13_reconciliation.py`. Its fixture is part of the guard rather than scenery: "every window carries both states" is satisfied by a fixture where every window is NOT_COMPARED and UNCHECKED, so the fixture spans three outcomes and a companion test asserts that it does. Emptying it of station rows leaves three of nine assertions still passing, which is what that companion exists to prevent.

The no-fault control run is **NOT YET RUN**. It is the only item here that needs the network.

This distinction is written down because the hazard is procedural rather than technical: "one new acceptance test" is a scope rule, and a later reader could honour it by deleting a seeded proof. A scope rule may not eat a validity rule. This is the same discipline as AT-7, where a seeded broken configuration proves the hygiene gate can fail, and as the companion tests that prove the INV-4 and INV-6 AST walk actually detects a banned import: every rule that passes by absence is paired with a proof that its detector works.

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

## Reopen: disagreement grading

Not a phase and not a cloud phase. G2 remains the terminal cloud gate and there is still no Phase 3. This work runs entirely local and at zero spend, under the contract frozen in `PREREGISTRATION.md` at commit b81f1c9 and the reopen recorded in `adr/0009-openaq-disagreement-grading.md`. Its scope, its pass and fail criteria, its cost cap and its abort rule live in that contract and are not restated here.

Work, in order:

1. Entity and schema edits. E-3, E-5 and the new E-8 through E-11, propagated to the DuckDB column tuple, the Iceberg schema, the DynamoDB item shape and the dashboard display model.
2. Station observation adapter. UC-8's input side behind the existing source interface, selected through the settings object, with the key from the environment and no endpoint literal in source (INV-1, INV-6).
3. Model PM2.5 on the existing adapter. The second half of the comparison, which does not exist today.
4. Reconciliation. UC-8 proper, with the tolerance and every frozen rule read from the settings object rather than written into adapter code.
5. Guards. AT-13, plus the three seeded violations required above, plus the no-fault control run.
6. Presentation and honest limits. UC-5's rendering of the two new states, and the README limits the contract requires to sit above any number.

Exit: the claims in the contract are evaluated exactly once against the sealed holdout and ship against the contract unmodified, whichever way they fall.

## Risks and their triggers

- Stream processor too heavy locally. If the processor chosen in ADR-0002 cannot reach a green smoke test on a laptop within the recorded bootstrap budget, fall back to the lighter option named in that ADR.
- Portability leak. If any core module needs a cloud SDK import to work, INV-4 is violated; stop and move the dependency behind an adapter before proceeding.
- Cost surprise in cloud. If the AWS phase approaches its spend ceiling before G2, tear down and reduce scope (fewer regions, shorter retention) rather than raising the ceiling.
