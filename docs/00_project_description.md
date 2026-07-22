# 00 Project Description

## One-line summary

A real-time streaming pipeline that computes a Climate Impact Index per geographic region over recent time windows from two data streams (weather metrics and atmospheric-composition summaries), persists the results, and shows them in a read-only dashboard. The stream source is selected by configuration: real readings fetched from a live provider, or the simulated generators the project was first built against (ADR-0007).

## The story

Two kinds of events arrive continuously for a small set of regions. Weather events carry temperature, rainfall, and wind. Satellite-style events carry cloud cover, a vegetation or dryness score, and an aerosol or pollution score. Either stream can be produced by the simulated generators or fetched from the real provider, chosen by one configuration flag. The simulated source remains the default, so the project still needs no API key and no paid data feed to run, and the real source needs no key either.

A stream processor consumes these events, validates them against a fixed schema, computes per-region climate features (a temperature anomaly, a dryness index, a pollution index), and combines them into a single Climate Impact Index over a sliding time window, for example the last thirty minutes. The index and its component metrics are written to a store, one row per region per window. A dashboard reads that store and shows the index over time per region, the current value, and a short verbal label (low, medium, high).

The point of the project is not climate science accuracy. It is a clean, observable, testable, and portable streaming data-engineering system that starts on one laptop and moves to the cloud (AWS) without a rewrite of its core.

## Why this project

It exercises the full streaming path (ingest, validate, window, aggregate, serve) end to end, it produces a visible result a non-technical viewer understands in one glance, and it has a clear portability story from local to AWS. The compute is deterministic, so correctness is testable rather than a matter of opinion.

## Scope boundary for Phase 1 (local)

In scope:

- Three or four regions with simple codes, for example EUR, NAM, AFR, ASI.
- One combined event stream carrying a type field (weather or satellite) on each message.
- One stream-processing job using event-time tumbling windows computed by truncating the event timestamp to the window size. This keeps window keys deterministic and replayable while deferring the harder parts of event-time processing. See ADR-0002.
- One aggregate table holding, per region per window: window start, window end, region, impact index, and the component metrics.
- One read-only dashboard page: a region selector, a time-series plot of the impact index, the current value, and a verbal label.

Out of scope for Phase 1:

- Geospatial maps.
- Real external weather or satellite APIs.
- Watermarks and late-data handling (deferred as a later, ADR-gated upgrade; Phase 1 uses event-time tumbling buckets by truncation, so a late event lands in its bucket only if that bucket is still open).
- Any write path from the dashboard. The dashboard never computes and never writes.
- Authentication and multi-tenant concerns (revisited only if a public cloud demo needs them).

## Fixed anchors carried from the earlier attempt

The earlier build recorded several lessons that this spec bakes in from the start rather than rediscovering:

- A single runtime requirements file that both the host virtual environment and any container install from, so a green local run and a green container run are claims about the same dependency set.
- All connection details and paths live in a config object and an environment example file. No bootstrap servers or file paths are scattered as literals through the code.
- A small canonical command set through a Makefile (for example bootstrap, infra up, run producer, submit job, smoke), with the known tab-not-spaces rule for recipe lines treated as a hard build-hygiene requirement.
- Structured logging in every component, emitting counts, per-region breakdowns, and window boundaries.
- Schema validation on both raw and aggregate data, unit tests for the index computation, and an end-to-end smoke check that sends a small batch and asserts the aggregate store is non-empty.
- Requirements, plan, and tasks kept in sync, which this spec-driven set enforces by making the spec the source of truth.

## Success in one sentence

From events, simulated or real, to a correct, non-empty chart of the Climate Impact Index per region, proven locally by a green smoke test, with the same core code ready to run behind managed services on AWS.
