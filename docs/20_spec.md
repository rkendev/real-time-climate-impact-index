# 20 Specification (Source of Truth)

Version: 0.4.0
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
- model_pm25_ugm3: float, greater than or equal to zero, required. The model analysis of surface PM2.5 mass concentration in micrograms per cubic metre for the same location and instant, carried so that a like-for-like comparison against a station observation (E-8) is possible. It is a model value, not an observation.

Provenance note. The field shapes above are fixed and do not vary by source. What fills them does. Under the simulated source every field is generated. Under the real source (UC-1, ADR-0007) this stream carries modeled atmospheric-composition data rather than satellite imagery: aerosol_index is an aerosol optical depth from the configured air quality provider, model_pm25_ugm3 is a surface PM2.5 mass concentration from the same provider and the same product, cloud_cover_pct is the observed cloud cover reported for the same location and instant by the weather provider, and vegetation_index is a per-region monthly reference value declared in configuration, not a measurement. The vegetation reference values are approximate published seasonal climatology, and neither the dashboard nor the documentation may present them as observed. The stream keeps the name satellite on the wire for continuity of E-4 and the store schema.

Scope note on model_pm25_ugm3. This field exists only to support the disagreement state (E-10). It is not an input to pollution_index (E-7), which continues to be computed from aerosol_index and cloud_cover_pct. Aerosol optical depth is a dimensionless column-integrated quantity and surface PM2.5 is a mass concentration; the relationship between them is weak and depends on boundary layer height, vertical profile and humidity, and this system does not test it. Nothing may grade pollution_index by PM2.5 disagreement.

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
- confidence: one of MEASURED, INFERRED, AMBIGUOUS (NFR-DQ2). Derived from input completeness only. It is not affected by the disagreement state below.
- pm25_disagreement: a PM2.5DisagreementState (E-10), required (NFR-DQ3).
- provenance_tier: a ProvenanceTier (E-11), required (NFR-DQ4).
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
- pm25_disagreement(city, window): the comparison of the station value (E-8) against the model value (E-3) for a city-window (E-9), evaluated against a tolerance that is a published function of the station value. The tolerance, its parameters, its citation and the rule for flagging are frozen in `PREREGISTRATION.md` at commit b81f1c9 and are deliberately not restated here. This specification states that the comparison exists, where it is evaluated and what it produces; the contract states with what numbers. Two documents carrying the same constant are two documents that can disagree, and only one of them is frozen.

### E-8 StationObservation

An independent ground-station measurement, used only for the comparison in E-10 and never as an input to the index.

- ts: timestamp, UTC, required. The start of the half-open hour the value covers.
- region: RegionCode, required.
- city: the configured sampling point the station is mapped to (E-7), required.
- station_id: the provider's stable station identifier, required.
- pm25_ugm3: float, the observed surface PM2.5 mass concentration in micrograms per cubic metre, required. Negative values are retained and are not clamped or discarded; validity is decided by the provider's own quality flag and by the presence of at least one underlying sample, per the rules frozen in the contract.
- sample_count: integer, the number of underlying measurements the hourly value was built from, required.
- construction: one of PROVIDER_HOURLY, COMPUTED_MEAN. Recorded because networks build an hourly value differently and the tolerance in E-10 was derived for the first kind. It is recorded, never gated on.

### E-9 CityWindow

The unit at which a station and a model value are physically comparable: one configured sampling point (E-7) for one closed event-time window. It is distinct from the region-window of E-5, which aggregates several cities. Both units are reported. The distinction is not cosmetic: a region flags by union over a varying number of covered cities, so a region rate has a denominator constructed differently from region to region, while a city rate is comparable across regions.

### E-10 PM2.5DisagreementState

The output state carried by E-5, scoped to surface PM2.5 and to nothing else.

- One of AGREED, DISAGREED, NOT_COMPARED.
- AGREED and DISAGREED apply only where both a station value and a model value are present for a covered city-window. NOT_COMPARED applies everywhere else and is not a judgement about either source.
- A region-window is DISAGREED when at least one of its covered cities is DISAGREED, and the record names which cities drove it.
- The state never resolves a disagreement. Both values are reported and neither is substituted for the other, averaged with it, or preferred (NFR-DQ3).
- The state does not modify confidence (NFR-DQ2) and does not modify pollution_index (E-3 scope note).

### E-11 ProvenanceTier

Whether a region-window could be independently checked at all.

- One of STATION_CHECKED, UNCHECKED.
- UNCHECKED applies where no qualifying station coverage exists for the window, or where coverage falls below the frozen minimum.
- A tier is never computed from data the window does not have, never inherited from a neighbouring region, and never inherited from a previous window (NFR-DQ4).
- The tier is a documented output state, not an error. Whole regions may carry UNCHECKED permanently, and the system is required to show that rather than to hide it.

## Part B. System use cases

Each use case has an ID, actors, a trigger, a main flow, and the requirements and invariants it satisfies. Acceptance tests (AT-*) in `30_plan.md` reference these IDs.

### UC-1 Emit events from the configured source

- Actors: Producer, Event source.
- Trigger: the operator runs the producer command.
- Main flow: the producer obtains one tick of typed events from the event source selected by configuration, wraps each in an EventEnvelope with the region as key, and publishes each to the transport. The producer itself performs no network access and knows only the source interface, so selecting a source is a configuration change, not a code change (the same composition-root shape the store already uses, ADR-0003, ADR-0007).
- Sources: the simulated source generates one WeatherEvent and one SatelliteEvent per region per tick, and is the default so that the local quickstart and the smoke checks stay offline and deterministic. The real source fetches readings for the configured representative cities of each region (E-7) and emits, per city, one WeatherEvent and one SatelliteEvent keyed by that city's region, so a window normally holds several events per region.
- No fabrication: under the real source, a failed fetch, a timeout, an unsuccessful response, or a missing or null required field means the affected event is not emitted for that location on that tick. It is logged and counted, never replaced with a substituted value and never retried in a loop. The resulting gap is genuine input sparsity, which UC-3 grades through the ordinary confidence rule (NFR-DQ2); nothing anywhere sets a grade directly.
- Station observations: a second real source fetches StationObservation records (E-8) for the sampling points of each region, behind the same source interface and selected the same way. It is independent of the weather and satellite streams and its absence degrades the provenance tier (E-11) rather than the index. The no-fabrication rule above applies to it unchanged (FR-11).
- Wire shape: E-4 is unchanged, and no event field varies by source (E-2, E-3).
- Satisfies: FR-1, FR-2, FR-11, NFR-P1, NFR-S2, NFR-DQ2.

### UC-2 Validate and quarantine

- Actors: Stream processor.
- Trigger: an EventEnvelope is consumed.
- Main flow: parse the envelope, validate the payload against the schema for its event_type through the deterministic gate. On pass, forward to windowing. On fail, write a QuarantineRecord with a reason_code and increment the quarantine counter. Never forward or persist an invalid event as data.
- Satisfies: FR-3, NFR-DQ1, NFR-T1, NFR-O1.

### UC-3 Window and compute the index

- Actors: Stream processor.
- Trigger: events accumulate; an event-time tumbling window closes. Window membership is decided by truncating each event timestamp to the window size, so boundaries are a deterministic function of the data (ADR-0002). Watermarks and late-data handling are deferred; a late event lands in its bucket if still open, otherwise it is counted as late and excluded.
- Main flow: group validated events by region for the window, compute temperature_anomaly, dryness_index, pollution_index, then impact_index and verbal_label, and assign a confidence grade from the window input composition. Produce one ClimateIndexRecord per region. The reconciliation of UC-8 then sets that record's pm25_disagreement and provenance_tier; it runs after the index is computed and changes none of the values above.
- Satisfies: FR-4, FR-5, FR-9, NFR-R1, NFR-R4, NFR-DQ2.

### UC-8 Reconcile station observations against the model analysis

- Actors: Stream processor.
- Trigger: a window closes and its ClimateIndexRecord has been computed (UC-3).
- Main flow: for each configured sampling point in the region, gather the qualifying StationObservations (E-8) for that city-window (E-9) and combine them into one city value; take the model value from the SatelliteEvents for the same city-window; and compare the two against the frozen tolerance. Assign the city-window a PM2.5DisagreementState (E-10), then set the region-window's state by the union rule in E-10 and record which cities drove it. Independently, set the region-window's ProvenanceTier (E-11) from whether qualifying coverage existed at all.
- Reported, never resolved: where the two disagree, both values are carried and neither is chosen, averaged away, or corrected by the other. Where they cannot be compared, that fact is stated rather than approximated (FR-12, FR-13).
- Deferral: the spatial mapping, the station admission and inclusion rules, the aggregation, the minimum coverage, the temporal alignment and the tolerance are all frozen in `PREREGISTRATION.md` at commit b81f1c9. This use case does not restate them and must not be read as an independent statement of them.
- Satisfies: FR-12, FR-13, NFR-DQ3, NFR-DQ4.

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
- Disagreement and provenance: the existing confidence strip also carries the PM2.5 disagreement state (E-10) and the provenance tier (E-11) for each window, from a configured mapping in the same way as the confidence tiers. Where a window is DISAGREED the page shows both the station value and the model value and never a single reconciled number, and it names the cities that drove the state. Where a window is UNCHECKED the page says that it could not be independently checked, which is a statement about coverage and not about the index. The page states that the disagreement state applies to PM2.5 only and does not grade pollution_index. The station data provider attributions required by their terms are carried alongside the existing ones.
- Satisfies: FR-8, FR-9, FR-12, FR-13, NFR-P3, NFR-SEC3, NFR-DQ2, NFR-DQ3, NFR-DQ4.

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

0.4.0 (2026-08-02). Station observations are reconciled against the model analysis, and the outcome becomes two first-class output states. The reopen is recorded in `adr/0009-openaq-disagreement-grading.md`; the contract it runs under is `PREREGISTRATION.md`, frozen at commit b81f1c9, which is the sole authority on every constant, rule, claim and floor. This specification states structure and behaviour and defers every number to that file.

- New entities: E-8 StationObservation, E-9 CityWindow, E-10 PM2.5DisagreementState, E-11 ProvenanceTier.
- Affected entities: E-3 (model_pm25_ugm3 added, with the scope note that it feeds the disagreement state and never pollution_index), E-5 (pm25_disagreement and provenance_tier added), E-7 (the pm25_disagreement definition added, deferring its constants to the contract).
- New use case: UC-8 (reconcile station observations against the model analysis).
- Affected use cases: UC-1 (a station-observation source behind the same interface), UC-3 (reconciliation runs after the index is computed and changes none of its values), UC-5 (the confidence strip also carries the two new states, both values are shown where they disagree, and unchecked windows say so).
- New requirements: FR-11 (station observation ingestion), FR-12 (disagreement reconciliation), FR-13 (provenance tier assignment), NFR-DQ3 (disagreement is reported and never resolved), NFR-DQ4 (no fabricated or inherited provenance tier).
- New acceptance test: AT-13, in `30_plan.md`. The seeded violations that NFR-DQ3 and NFR-DQ4 require are guards, not acceptance tests, and `30_plan.md` states that distinction so that the count of acceptance tests cannot be used to drop one of them.
- New settings keys, declared here as the single authority for tunables and named without values, which arrive at implementation: `openaq_base_url`, `openaq_api_key`, `station_source_backend`, `station_radius_cap_m`, `station_min_per_city_window`, `model_analysis_lag_hours`, `mqo_relative_uncertainty_at_reference`, `mqo_reference_value_ugm3`, `mqo_alpha`, `mqo_beta`, `disagreement_state_glosses`, `disagreement_state_colors`, `provenance_tier_glosses`, `provenance_tier_colors`. No constant may appear in adapter code.
- Downstream consequence to expect: E-3 gains a required field, so the fixed-input fixtures that AT-1 and AT-3 pin change, and the field propagates to the DuckDB column tuple, the Iceberg schema (a new field id, existing ids unchanged), the DynamoDB item shape and the dashboard. E-5 gains two required fields and propagates to the same four places. That cascade follows from the entity edits above and is intended.
- Unchanged and deliberately so: E-1, E-2, E-4, E-6, UC-2, UC-4, UC-6, UC-7. The wire shape, the validation gate, the windowing, the index formula, the confidence rule and the idempotent write behave exactly as before.

0.3.0 (2026-07-22). The event source becomes configurable: the simulated generators or a real fetched feed, selected by configuration at the composition root (ADR-0007).

- Affected use cases: UC-1 (rewritten around the configured source, with the no-fabrication rule), UC-5 (the page states which source is active and carries the provider attribution).
- Affected entities: E-2 (temperature_c wording is no longer specific to a synthetic feed), E-3 (provenance note added for the real source), E-7 (temperature_anomaly now uses twelve monthly normals per region in place of one annual scalar, with the derivation parameters recorded; monthly vegetation reference values added).
- Unchanged and deliberately so: E-4, E-5, E-6, UC-2, UC-3, UC-4, UC-6, UC-7. The wire shape, the validation gate, the windowing, the index and confidence computation, and the stores all behave exactly as before.
- New invariant: INV-6 (no network I/O in the core package), stated in ADR-0007 and summarized in `30_plan.md`.
- New acceptance test: AT-12 (real source end to end), in `30_plan.md`.
- Downstream consequence to expect: the month-aware baseline lookup changes the values the AT-3 fixed-input tests pin. That cascade is intended and follows from the E-7 edit above.
