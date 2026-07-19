# 20 Specification (Source of Truth)

Version: 0.2.0
Status: this document is the source of truth. Code, tests, infrastructure, and prose documentation are downstream artifacts generated from it. A change to behavior is an edit here first, then a cascade downstream. This follows the AI Unified Process described in the spec-driven-development source (`Research/New_Spec Driven Development Info/Spec-Driven Development How AI Is Flipping the Script on Software Engineering.txt`).

The specification has two halves the source calls out explicitly: an entity model (the nouns, the data) and system use cases (the verbs, the behavior). Everything downstream traces to an ID in one of these halves.

## Part A. Entity model

### E-1 RegionCode

An enumeration of region identifiers. Phase 1 default set: EUR, NAM, AFR, ASI. Adding a member is a configuration change, not a code change (NFR-S1).

### E-2 WeatherEvent

Fields:

- ts: timestamp, UTC, required.
- region: RegionCode, required.
- temperature_c: float, plausible range for a synthetic feed, required.
- rainfall_mm: float, greater than or equal to zero, required.
- wind_speed_ms: float, greater than or equal to zero, required.

### E-3 SatelliteEvent

Fields:

- ts: timestamp, UTC, required.
- region: RegionCode, required.
- cloud_cover_pct: float, zero to one hundred, required.
- vegetation_index: float, minus one to one, required.
- aerosol_index: float, required.

### E-4 EventEnvelope

The single message shape on the transport (FR-2).

- event_type: one of weather, satellite. Required.
- payload: the WeatherEvent or SatelliteEvent body matching event_type.
- key: the region code, used as the transport partition key (NFR-S2).

### E-5 ClimateIndexRecord

The aggregate row, one per region per closed window (FR-6).

- window_start: timestamp, UTC.
- window_end: timestamp, UTC.
- region: RegionCode.
- impact_index: float, normalized range zero to one hundred.
- temperature_anomaly: float, component metric.
- dryness_index: float, component metric.
- pollution_index: float, component metric.
- confidence: one of MEASURED, INFERRED, AMBIGUOUS (NFR-DQ2).
- Natural key: (region, window_start, window_end). Writes are idempotent on this key (FR-6, NFR-R1): locally via INSERT OR REPLACE, on AWS via an Apache Iceberg MERGE. The key is reproducible across replays because window boundaries are derived from event time by truncation, not from arrival time (see UC-3 and ADR-0002).

### E-6 QuarantineRecord

An event that failed validation (FR-3).

- ts_received: timestamp.
- event_type: the claimed type.
- reason_code: a short code naming why it failed (schema, range, parse).
- raw: the offending payload, retained for audit, never fed downstream.

### E-7 Derived feature definitions

These define the computation referenced by FR-4 and FR-5. Concrete constants live in the spec so the downstream code has one authority.

- temperature_anomaly(region, window): the mean temperature_c in the window minus a per-region normal baseline constant. Baselines are declared per region in configuration.
- dryness_index(region, window): a bounded function increasing with low rainfall and low vegetation_index. Higher means drier.
- pollution_index(region, window): a bounded function increasing with aerosol_index and cloud_cover_pct.
- impact_index(region, window): a weighted, normalized combination of the three component metrics mapped to zero to one hundred. Weights are declared constants in configuration and documented here when set.
- verbal_label(impact_index): low for the lower band, medium for the middle band, high for the upper band, by fixed thresholds (FR-9).

## Part B. System use cases

Each use case has an ID, actors, a trigger, a main flow, and the requirements and invariants it satisfies. Acceptance tests (AT-*) in `30_plan.md` reference these IDs.

### UC-1 Emit simulated events

- Actors: Producer.
- Trigger: the operator runs the producer command.
- Main flow: for each tick and each region, generate one WeatherEvent and one SatelliteEvent, wrap each in an EventEnvelope with the region as key, and publish to the transport.
- Satisfies: FR-1, FR-2, NFR-P1, NFR-S2.

### UC-2 Validate and quarantine

- Actors: Stream processor.
- Trigger: an EventEnvelope is consumed.
- Main flow: parse the envelope, validate the payload against the schema for its event_type through the deterministic gate. On pass, forward to windowing. On fail, write a QuarantineRecord with a reason_code and increment the quarantine counter. Never forward or persist an invalid event as data.
- Satisfies: FR-3, NFR-DQ1, NFR-T1, NFR-O1.

### UC-3 Window and compute the index

- Actors: Stream processor.
- Trigger: events accumulate; an event-time tumbling window closes. Window membership is decided by truncating each event timestamp to the window size, so boundaries are a deterministic function of the data (ADR-0002). Watermarks and late-data handling are deferred; a late event lands in its bucket if still open, otherwise it is counted as late and excluded.
- Main flow: group validated events by region for the window, compute temperature_anomaly, dryness_index, pollution_index, then impact_index and verbal_label, and assign a confidence grade from the window input composition. Produce one ClimateIndexRecord per region.
- Satisfies: FR-4, FR-5, FR-9, NFR-R1, NFR-R4, NFR-DQ2.

### UC-4 Persist aggregates and raw

- Actors: Stream processor, Store.
- Trigger: a ClimateIndexRecord is produced, or a validated raw event is ready to persist.
- Main flow: write the ClimateIndexRecord idempotently on its natural key, and append the validated raw event to the raw store. On replay, the aggregate write does not duplicate rows.
- Satisfies: FR-6, FR-7, NFR-R1, NFR-R2.

### UC-5 View the index

- Actors: Viewer, Store.
- Trigger: the viewer opens the dashboard and selects a region.
- Main flow: the dashboard reads aggregate rows for the region through a read-only connection, plots the impact_index time series, shows the current value, the verbal label, and the confidence grade. The dashboard performs no computation and no writes.
- Satisfies: FR-8, FR-9, NFR-P3, NFR-SEC3, NFR-DQ2.

### UC-6 Operate through canonical commands

- Actors: Operator.
- Trigger: the operator runs a command from the fixed set.
- Main flow: bootstrap the environment, bring infrastructure up, run the producer, run the processor, run the smoke check, open the dashboard. The smoke check sends a small batch and asserts the aggregate store is non-empty and duplicate-free.
- Satisfies: FR-10, NFR-M2, NFR-M3, NFR-R2.

### UC-7 Promote to cloud behind a deterministic gate

- Actors: Operator.
- Trigger: the operator runs a cloud deploy command for a phase.
- Main flow: a cheap deterministic pre-deploy check confirms the local smoke marker exists, dependencies are single-sourced, and the AWS config is present and parses. Only on pass does the expensive provisioning proceed. On fail, the deploy refuses and reports the failed check.
- Satisfies: NFR-C1, NFR-M1, and the cost-asymmetric gate in `60_panjuta_application.md`.

## Part C. Change protocol

When a requirement changes, edit this specification first. Identify the affected E-*, UC-*, FR-*, NFR-*, and AT-* IDs, then regenerate or amend the downstream code, tests, and infrastructure to match. A downstream patch with no corresponding change here is a defect against NFR-M4.
