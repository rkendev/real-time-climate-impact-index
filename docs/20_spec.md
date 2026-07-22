# 20 Specification (Source of Truth)

Version: 0.3.0
Status: this document is the source of truth. Code, tests, infrastructure, and prose documentation are downstream artifacts generated from it. A change to behavior is an edit here first, then a cascade downstream. This follows the AI Unified Process described in the spec-driven-development source (`Research/New_Spec Driven Development Info/Spec-Driven Development How AI Is Flipping the Script on Software Engineering.txt`).

The specification has two halves the source calls out explicitly: an entity model (the nouns, the data) and system use cases (the verbs, the behavior). Everything downstream traces to an ID in one of these halves.

## Part A. Entity model

### E-1 RegionCode

An enumeration of region identifiers. Phase 1 default set: EUR, NAM, AFR, ASI. Adding a member is a configuration change, not a code change (NFR-S1).

### E-2 WeatherEvent

Fields:

- ts: timestamp, UTC, required.
- region: RegionCode, required.
- temperature_c: float, plausible surface air temperature in degrees Celsius, required. The field shape is the same whichever source is configured (UC-1): the simulated source samples a plausible range, the real source carries a fetched reading.
- rainfall_mm: float, greater than or equal to zero, required.
- wind_speed_ms: float, greater than or equal to zero, required.

### E-3 SatelliteEvent

Fields:

- ts: timestamp, UTC, required.
- region: RegionCode, required.
- cloud_cover_pct: float, zero to one hundred, required.
- vegetation_index: float, minus one to one, required.
- aerosol_index: float, required.

Provenance note. The field shapes above are fixed and do not vary by source. What fills them does. Under the simulated source every field is generated. Under the real source (UC-1, ADR-0007) this stream carries modeled atmospheric-composition data rather than satellite imagery: aerosol_index is an aerosol optical depth from the configured air quality provider, cloud_cover_pct is the observed cloud cover reported for the same location and instant by the weather provider, and vegetation_index is a per-region monthly reference value declared in configuration, not a measurement. The vegetation reference values are approximate published seasonal climatology, and neither the dashboard nor the documentation may present them as observed. The stream keeps the name satellite on the wire for continuity of E-4 and the store schema.

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

- temperature_anomaly(region, window): the mean temperature_c in the window minus the per-region normal for the window's calendar month. Baselines are declared in configuration as twelve monthly values per region, replacing the earlier single annual scalar, so a July window in EUR is measured against a July normal rather than an annual average. The window's month is taken from its window_start. One mechanism serves both configured sources (UC-1).
  - Derivation of the declared normals, recorded so the constants are reproducible from this specification without running any script: for each region, the mean of its three configured representative cities, where a city's monthly value is the mean of ERA5 daily mean temperature (`daily=temperature_2m_mean`, `timezone=UTC`) over 1991-01-01 to 2020-12-31, retrieved from the Open-Meteo archive endpoint `/v1/archive`. The cities are EUR Amsterdam, Berlin, Madrid; NAM New York, Chicago, Los Angeles; AFR Lagos, Nairobi, Cairo; ASI Tokyo, Delhi, Jakarta.
  - The per-region monthly vegetation reference values used by the real source (E-3) are declared alongside these and are approximate published seasonal climatology, not derived from a dataset and not measurements.
- dryness_index(region, window): a bounded function increasing with low rainfall and low vegetation_index. Higher means drier.
- pollution_index(region, window): a bounded function increasing with aerosol_index and cloud_cover_pct.
- impact_index(region, window): a weighted, normalized combination of the three component metrics mapped to zero to one hundred. Weights are declared constants in configuration and documented here when set.
- verbal_label(impact_index): low for the lower band, medium for the middle band, high for the upper band, by fixed thresholds (FR-9).

## Part B. System use cases

Each use case has an ID, actors, a trigger, a main flow, and the requirements and invariants it satisfies. Acceptance tests (AT-*) in `30_plan.md` reference these IDs.

### UC-1 Emit events from the configured source

- Actors: Producer, Event source.
- Trigger: the operator runs the producer command.
- Main flow: the producer obtains one tick of typed events from the event source selected by configuration, wraps each in an EventEnvelope with the region as key, and publishes each to the transport. The producer itself performs no network access and knows only the source interface, so selecting a source is a configuration change, not a code change (the same composition-root shape the store already uses, ADR-0003, ADR-0007).
- Sources: the simulated source generates one WeatherEvent and one SatelliteEvent per region per tick, and is the default so that the local quickstart and the smoke checks stay offline and deterministic. The real source fetches readings for the configured representative cities of each region (E-7) and emits, per city, one WeatherEvent and one SatelliteEvent keyed by that city's region, so a window normally holds several events per region.
- No fabrication: under the real source, a failed fetch, a timeout, an unsuccessful response, or a missing or null required field means the affected event is not emitted for that location on that tick. It is logged and counted, never replaced with a substituted value and never retried in a loop. The resulting gap is genuine input sparsity, which UC-3 grades through the ordinary confidence rule (NFR-DQ2); nothing anywhere sets a grade directly.
- Wire shape: E-4 is unchanged, and no event field varies by source (E-2, E-3).
- Satisfies: FR-1, FR-2, NFR-P1, NFR-S2, NFR-DQ2.

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
- Presentation: the page also explains itself to a first-time viewer. It states in plain language what the index is with its scale and direction (E-5, E-7), states which source is active and what that source is (UC-1): under the simulated source, that the readings are generated rather than collected; under the real source, what is fetched, how often it is republished, that the vegetation term is a configured monthly reference rather than a measurement (E-3), and that a reading which fails to arrive is left out rather than filled in. The page carries the data provider attribution the source's terms require. It shows the newest window time and the refresh cadence, and carries two legends: the confidence tiers with what drives each (NFR-DQ2) and the verbal-label band cutoffs (FR-9). The time series is plotted against real window times with the index range on the value axis, and each point carries its stored confidence grade. The window axis is written on the server as a UTC clock label and the chart is pinned to that order, so the axis states the same instant as the freshness line rather than the viewer's local time, and a series that crosses midnight stays in order. The per-window confidence strip colours each grade from a configured tier mapping that reads the way a viewer expects before consulting the legend, strongest tier calm through weakest tier warm. An about panel gives a one-line description of the pipeline and a link to the source repository. Every one of these definitions is read from configuration, which holds them as the single authority; the page invents none of them, computes nothing, and still issues no writes.
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

### Change log

0.3.0 (2026-07-22). The event source becomes configurable: the simulated generators or a real fetched feed, selected by configuration at the composition root (ADR-0007).

- Affected use cases: UC-1 (rewritten around the configured source, with the no-fabrication rule), UC-5 (the page states which source is active and carries the provider attribution).
- Affected entities: E-2 (temperature_c wording is no longer specific to a synthetic feed), E-3 (provenance note added for the real source), E-7 (temperature_anomaly now uses twelve monthly normals per region in place of one annual scalar, with the derivation parameters recorded; monthly vegetation reference values added).
- Unchanged and deliberately so: E-4, E-5, E-6, UC-2, UC-3, UC-4, UC-6, UC-7. The wire shape, the validation gate, the windowing, the index and confidence computation, and the stores all behave exactly as before.
- New invariant: INV-6 (no network I/O in the core package), stated in ADR-0007 and summarized in `30_plan.md`.
- New acceptance test: AT-12 (real source end to end), in `30_plan.md`.
- Downstream consequence to expect: the month-aware baseline lookup changes the values the AT-3 fixed-input tests pin. That cascade is intended and follows from the E-7 edit above.
