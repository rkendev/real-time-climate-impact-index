# ADR-0007: Data source adapter (real readings behind a config flag)

Status: decided (Open-Meteo for both streams; the simulator retained and default)
Date: 2026-07-22
Related: `adr/0003-cloud-topology.md` (the store-adapter shape this mirrors), `adr/0004-nonfunctional-invariants.md` (amended by addition, see INV-6 below), `20_spec.md` UC-1, E-2, E-3, E-7, `30_plan.md` AT-12, INV-1, INV-4, FR-1, FR-6, NFR-R1, NFR-DQ2

## Context

The producer emits events from the pure generators in
`src/climate_index/core/generators.py`. Everything downstream is real
engineering, but the input is invented, and that is the single biggest thing a
reader discounts. The confidence grade suffers most: NFR-DQ2 exists to say how
much clean evidence backed a window, yet with a synthetic feed the only way to
show a grade below the top tier was to arrange a thin window on purpose
(`demo_degraded_window_fraction`). A grade computed from manufactured sparsity
demonstrates the mechanism but proves nothing about the data.

With real sources the grade becomes genuine. A source that times out, returns an
error status, or omits a field produces a real gap, and the committed grader
turns that gap into a lower grade with no help from anyone.

The store is already a config-selected adapter (ADR-0003, `store_factory.py`).
The event source should be the same shape, for the same reasons.

## Decision

### The adapter shape

An `EventSource` Protocol in `interfaces/source.py` with a single method
returning one tick of typed events, and `source_factory.build_event_source`
selecting the implementation from `Settings.source_backend`, exactly mirroring
`store_factory.build_aggregate_store`. Interfaces are imported at module scope;
each concrete adapter is imported lazily inside its own branch, so importing the
factory pulls in no HTTP client.

Two adapters:

- `adapters/simulated/source.py` wraps the existing core generators. The
  generators stay in `core/`, pure and unchanged.
- `adapters/openmeteo/source.py` fetches live readings.

`simulated` is the **default**, so every existing test, the local quickstart, and
both smoke checks behave exactly as before with no environment set. `real` is
opt-in per environment.

### The provider

Open-Meteo for both streams:

- the weather stream reads the forecast API's `current` block
  (`temperature_2m`, `precipitation`, `wind_speed_10m`, `cloud_cover`, with
  `wind_speed_unit=ms` and `timezone=UTC`);
- the pollution stream, whose wire type is still named `satellite`, reads the air
  quality API's `current` block (`aerosol_optical_depth`), combined with the
  cloud cover value from the same city's forecast call.

Chosen over **OpenAQ**, the recorded alternative. OpenAQ serves genuine ground
station measurements, which is a stronger provenance claim than a model
analysis, but it needs an API key, its station coverage is uneven across the four
regions (sparse in AFR in particular), and station metadata handling would be a
second integration rather than a second endpoint on the same client. Open-Meteo
gives both streams from one provider with one client, no key, and uniform global
coverage. If the provenance claim ever needs to be stronger for the pollution
stream specifically, OpenAQ is the upgrade path and it is an adapter change, not
a core change.

Note what this provider is and is not. Open-Meteo weather and the CAMS ENSEMBLE
air quality product are **model analyses**, not station observations. The
dashboard and the documentation say "readings", never "observations", and never
claim a per-second live feed.

### Terms

Open-Meteo is free for non-commercial use and needs no API key. Attribution is
required and is rendered in the dashboard's about panel and stated in the README:
Open-Meteo for weather and air quality, and the CAMS ENSEMBLE data provider for
atmospheric composition. The demo cadence, one refresh every thirty minutes with
one request per city per endpoint across twelve cities, sits far below the free
tier's daily allowance.

### Region to coordinate mapping

Three representative cities per region, held in config as structural reference
data alongside the baselines: EUR Amsterdam, Berlin, Madrid; NAM New York,
Chicago, Los Angeles; AFR Lagos, Nairobi, Cairo; ASI Tokyo, Delhi, Jakarta.

Each tick fetches every city and emits, per city, one weather event and one
satellite-stream event, keyed by region. A window therefore normally holds
several events per region, so the sparsity threshold and the stream-composition
rule keep doing real work rather than being trivially satisfied.

**One GET per city per endpoint**, twenty four per tick at the default four
regions. Open-Meteo also accepts comma-separated coordinate lists and returns a
JSON array, which would cut this to two requests per tick, and that batching was
rejected deliberately: a batched call that fails erases a whole region's stream
for that tick, whereas an independent call per city means one city failing costs
one city. Independent failure domains are the entire point of the design, and the
request volume is trivial against the free tier either way.

### Temperature baseline

Per-region **monthly** normals in config replace the single scalar
`region_baselines`. One mechanism serves both modes: the anomaly for a window is
the window's mean temperature minus the normal for the window's month.

The constants are derived, not invented. They are the mean of the three cities'
monthly means of ERA5 daily mean temperature over **1991-2020**, taken from the
Open-Meteo archive endpoint (`/v1/archive`, `daily=temperature_2m_mean`,
`timezone=UTC`). Those parameters are recorded here and in spec E-7 so the
numbers are reproducible from the specification alone. `scripts/derive_climatology.py`
is a convenience for regenerating them and is operator tooling only: it is never
imported by `src/`, and never run by any test, gate, or make target.

### Vegetation

No free live per-coordinate vegetation index exists at this integration cost, so
in real mode `vegetation_index` is a per-region **monthly reference value from
config**, the same mechanism the temperature normals use. Unlike the temperature
normals these values are approximate published seasonal references, not derived,
and they are documented as approximate in spec E-3, here, and in the dashboard
notice. The dashboard and the README must not claim live vegetation.

The aerosol optical depth the air quality API returns sits well below the
existing `pollution_aerosol_saturation` of 2.0 (probed range across the twelve
cities: roughly 0.18 to 0.99). That constant already lives in config, so tuning
it later is a configuration change, not a code change.

### The no-fabrication rule

A failed fetch, a timeout, a non-success HTTP status, an error body, or a missing
or null field means the affected event is **simply not emitted** for that city
this tick. It is logged with a structured counter and never substituted with a
made-up value, and there is no retry loop. The satellite-stream event for a city
is formed only when both of that city's fetches succeeded and every required
field is present and non-null, because its cloud cover comes from the forecast
call and its aerosol value from the air quality call. A payload that fails model
validation counts as a missing event for that city and is never published half
formed.

The rule applies **per hourly slot** in the historical fetch as well: a null in
an hourly array means no event for that slot and that city, logged and counted,
never interpolated from its neighbours.

The gap is not a defect to paper over. It is the honest signal the confidence
grader exists to read, and nothing anywhere hand-sets a grade.

### Historical fetch, and why the demo replays

The live demo rebuilds a bounded, self-contained snapshot on every refresh, so it
needs a series of windows rather than a single instant. Both Open-Meteo endpoints
serve `hourly` arrays with `past_days`, so in real mode the demo feeder
republishes the **past day of genuine hourly readings** at their true timestamps
through the same transport, the same envelopes, and the same unchanged consumer.
The demo's degraded-fraction logic is not applied in real mode: nothing
artificially degrades or upgrades anything, and whatever gaps the provider
actually had are what the grader sees.

This makes the live demo a **continuous replay by design**. Each refresh
republishes hours it has already published. Because window boundaries are derived
from event time by truncation and the aggregate write is idempotent on the
natural key `(region, window_start, window_end)`, a re-published hour lands on the
**same row** rather than creating a duplicate. That is exactly the property
FR-6, NFR-R1, and AT-5 exist to prove, now exercised continuously by the public
demo instead of only inside a test.

The historical fetch is deliberately **not** on the `EventSource` Protocol, which
stays single-method and describes one tick. It is an extra capability of the
Open-Meteo adapter that the demo feeder, itself operator tooling under
`deploy/vps/`, reaches for by concrete type.

### INV-6, a new invariant

> **INV-6**: No network I/O in the core package. Every external data source sits
> behind a source adapter selected by config. Enforced by a test asserting that
> no `httpx`, `requests`, `urllib.request`, `aiohttp`, or `socket` import appears
> under `src/climate_index/core/`, by the same AST walk that enforces INV-4.

INV-4 already keeps cloud SDKs out of the core. It does not keep an HTTP client
out, and now that the project has a real reason to make network calls that gap is
worth closing explicitly rather than by habit.

**ADR-0004's reopen trigger is honored.** That ADR requires an invariant to be
amended only through an ADR that updates the affected tests in the same change.
This ADR amends the standing law **by addition**: no existing invariant is
removed, weakened, or reworded, and the test that enforces INV-6 lands in the
same change as this record.

## Consequences

- Exactly one new runtime dependency, `httpx`, pinned in `requirements.txt` only
  (INV-5 unaffected: the version-consistency check compares `requirements-dev.txt`
  against `.pre-commit-config.yaml`). It ships type information, so strict mypy
  needs no stub and no override entry.
- The HTTP client is imported lazily inside the adapter's run path, so test
  collection neither dials nor imports it, matching the Kafka and cloud adapters.
- No endpoint literal enters source: both Open-Meteo URLs are `None` by default
  in `Settings` and populated from the environment like
  `transport_bootstrap_servers`, with example values in `.env.example` and the
  git-ignored demo environment only (INV-1).
- `demo_degraded_window_fraction` becomes a documented **simulated-mode demo knob
  only**.
- The month-aware baseline lookup changes the values the AT-3 fixed-input tests
  pin. That is a downstream consequence of the E-7 specification change, cascaded
  deliberately, not a test adjusted to fit code.
- `smoke.py` and the container smoke stay on the simulated source, so both remain
  offline and deterministic.

## Falsifiable triggers

- If Open-Meteo introduces a key requirement, a cost, or terms incompatible with
  this use, move to OpenAQ for pollution and a keyed weather provider; both are
  adapter changes behind the same Protocol.
- If the provider's uptime makes real mode produce so many gaps that the demo
  reads as broken rather than as honest, do not soften the no-fabrication rule.
  Reduce the cadence or widen the window instead, and if neither helps, record
  the provider as unfit and change providers.
- If a genuinely free live per-coordinate vegetation index becomes available,
  replace the monthly reference with it and delete the approximation note from
  E-3 and from the dashboard.
- If any core module needs a network client to work, INV-6 is violated: stop and
  move the dependency behind the source adapter.
