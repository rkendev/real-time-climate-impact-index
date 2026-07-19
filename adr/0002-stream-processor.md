# ADR-0002: Phase 1 stream processor

Status: decided (Python consumer; cost-constrained)
Date: 2026-07-16 (revised)
Related: FR-4, FR-5, UC-3, NFR-P2, NFR-R1, NFR-M3, NFR-C1, `adr/0003-cloud-topology.md`

## Context

Kafka is fixed as the Phase 1 transport by the owner's decision. What consumes Kafka and computes the windowed index is open. Two options are on the table. The earlier build used Apache Flink through PyFlink and hit friction (a Kafka client import chain that broke test collection, and general local heaviness) before the code was lost. That history is evidence, not a verdict.

## Options

Option A: Apache Flink (PyFlink). A real stream processor with windowing, state, and a clear path to a managed equivalent on AWS (Amazon Managed Service for Apache Flink, the current name for the former Kinesis Data Analytics). Cost: it is the heaviest local dependency, the local submit-and-run loop is slower, and the earlier build showed it can be fragile to set up. Strong streaming-skill story.

Option B: a plain Python consumer that windows in process. A single consumer reads Kafka, keeps per-region windows in memory keyed by event-time bucket (see the windowing note below), computes the index on window close, and writes aggregates. Cost: it is not a distributed stream processor, so very high throughput and stateful recovery are weaker, and the cloud phase would introduce a managed processor as a later upgrade. Benefit: it reaches a green smoke test on a laptop fast and reliably, which serves the local-first rule and the recorded clone-to-green target (NFR-M3).

## Decision

Option B, the Python consumer, is chosen, behind the transport and processor interfaces (INV-4, NFR-PT2). Flink is deferred as an ADR-gated upgrade for if the cloud phase ever needs managed, stateful, horizontally-scaled processing. Rationale: the fixed anchor is Kafka, not Flink; the Phase 1 goal is a correct, green, portable local slice, and Option B reaches it with the least risk given the earlier Flink friction; and Option B is the cheapest cloud option (NFR-C1), since the same consumer container runs on a small ephemeral compute instance rather than on a Managed Flink application that bills a running KPU baseline. Per ADR-0003, the cloud host for this consumer is the same container image running on a small ARM EC2 or ECS Fargate, provisioned only during a demo. Because the core depends on the processor interface, a later swap to Flink does not touch the models, the validation gate, or the index computation.

## Windowing note: event-time buckets, watermarks deferred (revision)

The earlier framing used processing-time windows to avoid watermark complexity. Processing-time windows break the idempotency guarantee the rest of the spec makes: the natural key is (region, window_start, window_end), but a processing-time window assigns boundaries from wall-clock arrival, so replaying the same events at a different time produces different boundaries, a different key, and a new row rather than a deduplicated one.

The fix keeps Phase 1 simple. Windows are event-time tumbling buckets computed by truncating each event timestamp to the window size (for example floor of ts to the nearest thirty minutes). This makes the window boundaries a deterministic function of the data, so the natural key is reproducible and idempotent writes actually deduplicate on replay. The hard part of event-time processing, watermarks and late-data handling, stays deferred: a late event either lands in its bucket if that bucket is still open, or is counted as late and excluded, and that policy is recorded rather than solved with watermarks in Phase 1.

## Offset-commit rule (revision, the crux of correctness)

At-least-once plus idempotent writes only holds if Kafka offsets are committed after the aggregate for the window those events belong to is durably written. Auto-commit is disabled. The consumer commits offsets only up to the last event whose bucket has closed and whose aggregate write has succeeded. Without this, a timed auto-commit would advance past events in a still-open window, and a crash would drop their contribution with no reprocessing, which is a silent undercount rather than a recoverable duplicate.

## Recovery model (revision)

On crash and restart, the consumer resumes from the last committed offset (NFR-R2). Any window that was open at crash time had not been committed (by the offset rule above), so its events are reprocessed and the bucket re-forms deterministically (by the event-time rule above). The idempotent write on the natural key (FR-6, NFR-R1) makes any redo of an already-written window a no-op. This recovery model is correct only because the event-time bucketing and the commit-after-write rule are both adopted; it does not hold under processing-time windows or auto-commit.

## Consequences

- Phase 1 windowing is event-time tumbling by timestamp truncation and in-process; watermarks and late-data handling remain deferred, consistent with the scope boundary in `00_project_description.md`.
- Exactly-once is not attempted in Phase 1; at-least-once, the commit-after-write rule, and idempotent writes (NFR-R1, FR-6) together cover duplicate and undercount safety.
- The interface boundary must be honest from the first commit, or the later Flink swap will leak into the core.

## Falsifiable trigger to choose Option A now instead

If a Phase 1 acceptance run shows the in-process consumer cannot hold per-region windows within laptop memory at the NFR-P1 event rate, or cannot recover cleanly after a crash (NFR-R2), adopt Flink for Phase 1 rather than deferring it.
