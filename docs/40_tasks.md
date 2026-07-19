# 40 Tasks (Phase 1 backlog)

Version: 0.2.0
Scope: Phase 1 only (local). Cloud tasks are opened after gate G1 and are sketched in `50_cloud_strategy.md`.

Each task names the spec IDs it satisfies and the acceptance test that closes it. Tasks are ordered so that a working, testable slice exists as early as possible. No task is done until its acceptance test passes.

## Track A: build hygiene and skeleton

- T-A1 Create the repo skeleton: `src/climate_index/` package, `tests/`, `app/`, `infra/`, `docs/`, single `requirements.txt`, and a config object with an environment example file. Satisfies FR-10, NFR-M1. No AT yet.
- T-A2 Write the Makefile with the canonical commands (bootstrap, infra_up, run_producer, run_processor, smoke, ui), recipe lines tab-indented. Satisfies FR-10.
- T-A3 Add the pre-commit config and a CI step that validates it on a clean checkout, plus a seeded-broken fixture that must fail red. Satisfies NFR-M2, closes AT-7.
- T-A4 Add the version-consistency check across all dependency-declaring files. Satisfies NFR-M1, INV-5.
- T-A5 Measure and record clone-to-green time from a clean bootstrap. Satisfies NFR-M3, contributes to AT-8.

## Track B: models and contracts

- T-B1 Implement E-1 RegionCode and configuration for the region set and per-region baselines. Satisfies E-1, NFR-S1.
- T-B2 Implement E-2 WeatherEvent, E-3 SatelliteEvent, E-4 EventEnvelope. Satisfies FR-2.
- T-B3 Implement the raw and aggregate schema contracts (E-5, E-6) and their runtime validators. Satisfies NFR-T1.

## Track C: producer

- T-C1 Implement the generators for weather and satellite events with documented value ranges. Satisfies FR-1.
- T-C2 Wrap events in envelopes with the region key and publish to Kafka. Satisfies FR-2, NFR-S2.
- T-C3 Add the pure generator test against the schemas, with no transport import in the test path. Closes AT-1. Note: keep any transport client import lazy inside the run path so tests never trigger the transport import chain. This is the specific failure that blocked the earlier build.

## Track D: validation gate

- T-D1 Implement UC-2: parse, validate through the deterministic gate, forward or quarantine with a reason code and counter. Satisfies FR-3, NFR-DQ1, INV-3.
- T-D2 Add tests feeding valid, borderline, and invalid events, asserting quarantine counts and no bad aggregate. Closes AT-2.

## Track E: windowing and index

- T-E1 Implement UC-3 feature computation: temperature_anomaly, dryness_index, pollution_index per region per event-time tumbling window (buckets by timestamp truncation, per ADR-0002). Satisfies FR-4.
- T-E2 Implement impact_index, normalization, and verbal_label. Satisfies FR-5, FR-9.
- T-E3 Implement the confidence grade from window input composition. Satisfies NFR-DQ2.
- T-E4 Unit tests on fixed inputs for components, index, range, and grade. Closes AT-3, AT-4.

## Track F: persistence

- T-F1 Implement UC-4: idempotent aggregate write on the natural key and the raw append. Satisfies FR-6, FR-7, NFR-R1.
- T-F2 Replay test asserting no duplicate aggregate rows. Closes AT-5.

## Track G: dashboard

- T-G1 Implement UC-5: read-only region time series, current value, verbal label, confidence grade. Satisfies FR-8, NFR-P3, NFR-SEC3, INV-2.
- T-G2 Test asserting the dashboard module imports no writer and no compute path. Closes AT-6.

## Track H: smoke and operations

- T-H1 Implement the end-to-end smoke command: send a small batch, run the pipeline, assert the aggregate store is non-empty and duplicate-free. Satisfies FR-10, NFR-R2.
- T-H2 Confirm structured logging fields (counts, per-region, window boundaries) and the metadata-only telemetry rule. Satisfies NFR-O1, NFR-O3.
- T-H3 Full clean-bootstrap-to-green-smoke run, recording the time. Closes AT-8. This run is gate G1.

## Track I: portability guardrails (kept honest from day one)

- T-I1 Define the transport interface and the store interface; make the core depend on the interfaces only. Satisfies NFR-PT1, NFR-PT2, NFR-PT3.
- T-I2 Add the test asserting no cloud-vendor SDK import under the core package. Closes AT-10. This test passes trivially in Phase 1 and guards the AWS phase (Phase 2).
- T-I3 Stub the deterministic pre-deploy gate command (UC-7) that checks for the local smoke marker; it has nothing to deploy yet but the check exists. Contributes to AT-9.

## Definition of done for Phase 1

All acceptance tests AT-1 through AT-8 and AT-10 pass, AT-9 is stubbed and passing on the marker check, the smoke test is green, and the clone-to-green time is recorded. That state is gate G1 and unlocks Phase 2.
