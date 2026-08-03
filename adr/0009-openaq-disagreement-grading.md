# ADR-0009: OpenAQ disagreement grading (reopen under owner self-override)

Status: decided (reopen accepted; the contract is frozen in `PREREGISTRATION.md` at commit b81f1c9)
Date: 2026-08-02
Related: `PREREGISTRATION.md` (the frozen contract, commit b81f1c9, which is the authority on the threshold, the frozen rules, the claims and the floors), `adr/0007-data-source-adapter.md` (this takes the OpenAQ upgrade path that ADR recorded, and the falsifiable trigger it wrote), `adr/0008-continuous-integration.md` (the zero-secret CI property this must not break), `adr/0004-nonfunctional-invariants.md` (INV-1, INV-6, unamended by this record), `20_spec.md` E-3, E-5, UC-3, UC-5, `30_plan.md` AT-13, NFR-DQ2

## Context

This ADR exists because the project was closed and is being reopened. It records
why, what was declined along the way, and in what order things became known. It
does **not** restate the contract. Every number that could move the threshold,
every claim, every floor and every stated limit lives in `PREREGISTRATION.md` and
nowhere else, deliberately, so that there is exactly one authority and no second
document to drift against it.

### Why this project exists at all

The Real-Time Climate Impact Index reached its terminal gate G2 and was closed.
There is no Phase 3. Reopening therefore needs a reason that is not "there is
more that could be built", because there always is.

The reopen runs under **CII reopen trigger 3, owner self-override**. That trigger
requires no named person and no job description, on the condition that a
pre-registration carrying scope, pass and fail criteria and a cost cap is
committed before any code exists. It substitutes pre-registration discipline for
demand-pull discipline. It is not a bypass, and the condition was met literally:
the contract is commit b81f1c9, it contains one file, and it precedes every line
of implementation.

The candidate that survived is not the one that looked biggest. At the council of
2026-07-28 three extensions were put through the same extension test, which asks
what a candidate would prove that the portfolio has not already proved.
Continuous Kafka did not survive it: the transactional and exactly-once
properties it would demonstrate are the ones ProofBench already measures
directly, and a second demonstration of a measured property is decoration.
Further AWS runs did not survive it either: G2 already proved the cloud path
end to end against real Glue, within budget, with a clean teardown audit, and
repeating a passed gate produces spend rather than evidence.

Disagreement grading survived on merits. The confidence grader in
`src/climate_index/core/confidence.py` reads **absence** and only absence: it
receives two integers, a weather count and a satellite count, and it grades on
composition and sparsity. The dead-host run proved that mechanism is genuine
rather than arranged. But absence is the easy half of provenance. Two sources
that are both present and disagree is the case the grader has never seen, no
other project in the portfolio reads it, and it is the case where the honest
answer is to report both values rather than to pick a winner. That is a property
the portfolio does not yet have, which is what the extension test asks for.

ADR-0007 anticipated the shape of this change and wrote the trigger that fires
here: "If the provenance claim ever needs to be stronger for the pollution stream
specifically, OpenAQ is the upgrade path and it is an adapter change, not a core
change." The first half holds. The second half turns out to be wrong, and section
2 of the contract records why: the model side of a like-for-like comparison does
not exist in the pipeline today, so a new field on `SatelliteEvent` is required
and the change reaches the store schemas and the dashboard. That is a schema
change, not only an adapter change, and it is recorded as in scope rather than
discovered during implementation.

## Decision

Accept the reopen under trigger 3, on the terms frozen in `PREREGISTRATION.md`
at commit b81f1c9.

This ADR adds no invariant and amends none. INV-1 and INV-6 apply unchanged: the
OpenAQ key reaches the process through the environment and never enters the
repository, no endpoint literal enters `src/`, and both adapters sit behind the
existing `EventSource` Protocol with no network client in the core. ADR-0008's
zero-secret CI property is likewise untouched, because the suite runs on recorded
fixtures and CI is never asked to hold a credential.

The specification edits and the first implementation task follow this record, in
that order, each as its own commit. Specification leads code, as it has
throughout.

## The order in which things became known

A reader can reconstruct this from the history, but not cheaply, and the sequence
is the part most worth having written down.

**The pre-flight ran before the freeze, and overturned three of the draft's own
premises.** That is what a pre-flight is for, and it is the reason the freeze was
worth delaying.

First, the draft asserted that the project would compare the existing model
analysis against station observations of the same quantity. It would not have.
The pipeline's pollution stream carries `aerosol_optical_depth`, which is
dimensionless and column-integrated, and OpenAQ measures surface PM2.5 mass. The
abort rule was examined and correctly did not fire, because it turns on whether
the two **sources** measure a comparable quantity, and both serve surface PM2.5;
it was the field the pipeline happens to carry that was incomparable. Scope grew
accordingly and was written down before the freeze rather than after.

Second, the draft's threshold branches both failed. It pre-committed to a
combined stated uncertainty if either source published one, and to a fixed
physical value otherwise. Neither source publishes an uncertainty at any usable
granularity, which should have selected the fallback, but the fallback applies
one tolerance across a range spanning roughly two orders of magnitude and is
close to inert at the bottom of it. The published solution to precisely that
problem was found in a guidance document, and the branch structure was replaced
rather than satisfied on a technicality.

Third, the draft set the discrimination claim's unit at the region-window. That
unit is not comparable across regions, because a region flags by union over a
varying number of covered cities, so identical underlying disagreement would
produce different rates purely from how many cities a region happens to have.
The unit moved to the city-window before any comparison existed.

**Two corrections were made after their cost was visible.** Both are disclosed in
the frozen file itself rather than only here, because a correction whose sequence
is hidden is indistinguishable from motivated reasoning.

The first concerns the measurement uncertainty constant for PM2.5, and recording
it correctly needs three labels rather than two. **The owner** decides. **The
advisor** reviews and reports. **The build session** is the working session that
reads sources and drafts, and until now it had no label at all, because the house
rule against tool brand names leaves it unnameable and the obvious workaround is
to fold its actions into one of the other two. That is exactly what happened, and
it is the root cause of the misattribution corrected below. The three labels are
used consistently from here on.

The sequence was:

1. The build session extracted the constant from the guidance published as
   JRC120649. The reading was correct **for that document**. That document is the
   superseded version, so the error was the version and not the reading.
2. The advisor reported that same value as the current version's value, from a
   summarised fetch, and described it as independent verification. **That was
   wrong.**
3. The build session extracted the current version directly, read the parameter
   table, and caught the error, finding that the constant had changed between
   versions while the surrounding prose had not.
4. The advisor re-verified by extracting the PDF text and confirmed the corrected
   value, which the owner relayed.

The prose in the current version now contradicts its own table on the same
printed page. The table binds, the discrepancy is quoted in the contract, and the
sensitivity of the threshold to the two candidate values had already been
computed when the constant was ratified. That ordering is disclosed in the
contract. The sensitivity table is analytic rather than observational, so no
observation preceded the pre-registration, but the sequence is stated rather than
left for a reader to reconstruct.

**The contract's attribution of step 4 is wrong, and the contract is deliberately
not amended.** Section 4.5 at b81f1c9 credits the confirming extraction to the
owner. It was the advisor's second extraction, which the owner relayed. The
contract's value rests on the freeze commit being untouched and its timestamp
provably preceding any measurement, and a second version would force every reader
to first establish which one was frozen. The slip concerns who performed a
verification, not a predicate, a constant or a floor, so it is disclosed here and
corrected here rather than by editing a frozen file.

The licence rule was the second. As first written by the owner it excluded
stations with unstated licence terms from admission entirely. Applied, it deleted
an entire national network and reduced one region to a single city. It was
corrected because the reasoning was defective and not because of what it cost:
using publicly served data in a measurement is not redistribution, whereas
committing raw values as fixtures is, and the original rule conflated the two.
The corrected rule constrains fixtures and leaves admission alone. Both the
defect and the cost are recorded in the contract, in that order.

**Nothing in the sealed holdout was read to reach any of this.** Station
admission consults the first and last timestamps at which a sensor reported,
which are metadata spanning the holdout period, and no measured value was
retrieved. The contract states this next to the seal paragraph so that the
question does not have to be reopened later.

## Follow-up: a factual error in the contract, found at implementation

Recorded 2026-08-03, after the freeze.

Section 2 of `PREREGISTRATION.md` at b81f1c9 states that the new field on
`SatelliteEvent` "propagates to the DuckDB column tuple, the Iceberg schema, the
DynamoDB item shape and the dashboard". The four named surfaces are right. **The
carrier named is wrong.** All four carry `ClimateIndexRecord`, the aggregate row,
whereas `SatelliteEvent` reaches only the raw store, which stores a JSON payload
and needs no schema change at all. A field on the event does not reach those
surfaces by itself.

The consequence is not a scope expansion. A second field on the aggregate is what
the contract's own stated propagation actually requires, in the same way the third
`EventEnvelope` member followed from the frozen clause placing the station source
behind the existing source Protocol. It is declared in `20_spec.md` E-5, and the
reasoning is recorded in that document's change log as well as here.

**The contract is not amended.** It contains a factual error about the existing
code, discovered at implementation and corrected in the record. Its value rests on
the freeze commit being untouched and its timestamp provably preceding any
measurement, and the error concerns a description of the codebase rather than a
predicate, a constant or a floor. This is the second such disclosure, after the
attribution slip in section 4.5, and the handling is the same for the same reason.

The reusable lesson is the more useful half, and it is the advisor's miss. The
pre-flight verified the external citations and the API surfaces to the byte, down
to which table binds when a document contradicts itself, and it verified that the
pipeline carries an aerosol optical depth rather than a mass concentration. It then
asserted this propagation path without checking it. **A pre-registration that
describes an existing system has to verify its description of that system with the
same rigour it applies to a published document.** The sentence was added
specifically to stop scope being relitigated later, which made it load-bearing, and
it was the one sentence in the file nobody checked. Rigour was applied where the
sources were foreign and withheld where they were familiar.

## Follow-up: a model-side query covering the holdout window, disclosed

Recorded 2026-08-03, during the first implementation task.

Establishing that the model side of the comparison cannot deliver a negative or
absent value required probing the provider, and the probe covered the sealed
holdout window. Disclosed here in the same form the contract uses for the
station metadata it reads next to its seal paragraph, because an auditor reading
the history will see model values for the holdout period fetched during
implementation and should find the answer already written rather than have to
assemble it.

**What was read.** Hourly `pm2_5` from the Open-Meteo air quality endpoint for
the twelve configured sampling points, over the ninety-two days the endpoint
serves, which is 26496 values. That span contains the holdout window.

**What was computed from it.** Three numbers per city and three in total: the
count of nulls, the count of negative values, and the minimum. Nulls and
negatives were zero everywhere and the global minimum was exactly zero, which is
what fixed the schema bound at greater-than-or-equal rather than greater-than
and what makes the new range-rejection counter evidence rather than an
assumption.

**What was not done.** No station data was fetched. No station value and no model
value were ever brought together. No difference, no tolerance, no flag, no rate
and no distribution over any comparison was computed, because the station half of
the comparison did not exist at that point and still does not. The disagreement
statistic the holdout exists to protect cannot have been observed, since nothing
capable of producing it had been written.

**Why the seal is intact.** Not because reading one source cannot constrain a
two-source statistic. It can: one side's distribution does narrow the joint one,
and an earlier version of this paragraph claimed otherwise and overclaimed. The
argument is narrower, and it is about what was computed rather than what was read.

The three quantities taken out of the probe are a null count, a negative count
and a minimum. All three are functions of the model side's validity range alone.
None is a function of any station value, so none carries information about a
difference between the two sources, which is what the holdout protects. The
individual hourly values were not retained and were summarised in no other way.

Second, and independently: every rule that could have responded to such
information was already fixed and published at b81f1c9 before this query ran. The
tolerance and its constants, the spatial and temporal rules, the admission and
coverage rules and the split all sit in a commit that precedes the probe, so
there was no knob left for it to move even had it carried information. The
holdout still opens exactly once, when both halves exist.

## Post-project findings, recorded and not built

Things worth fixing that this project will not fix. Section 2 of the contract
says an apparent necessity outside scope is a finding to record rather than a
scope change to make, and the frozen scope lists one new acceptance test and no
hygiene gate. Recorded here rather than in a working note so they outlive the
session that found them.

1. **No permanent identifier-resolution gate.** A one-off audit over `docs/`,
   `adr/` and the contract found ninety distinct identifiers with every reference
   resolving to exactly one definition, no duplicates and no dangling references.
   Nothing keeps it that way.
2. **NFR-O2 and NFR-R3 have no acceptance test**, against the PRD's own rule that
   a requirement without one is not considered delivered.
3. **`test_run_producer_main_is_a_safe_noop_without_a_broker` is not isolated
   from a local `.env`.** It strips the environment variable but cannot strip the
   file that `env_file` reads, so a developer copying `.env.example` to `.env`
   breaks it. Proven by moving the file aside: 40 minutes and a failure with it
   present, 0.37 seconds and a pass without.
4. **That same test's `subprocess.run` has no timeout.** It was 40 of the suite's
   42 minutes when it failed.
5. **The producer reports success when nothing reached a broker.** It logs
   `published: 8` and exits zero while `librdkafka` writes connection-refused for
   every attempt, so `make run_producer` looks like it worked. This is the only
   one of these with consequences outside the test suite.
6. **Fifteen test call sites read `Settings` without `_env_file=None`.** The
   convention is used at more than thirty other sites, so these are omissions
   rather than a missing practice. The failure mode is a **false green** rather
   than a red, which is why it wants a gate and not vigilance; two instances have
   already bitten this project, the `.env` in finding 3 and a gloss test that
   first passed against the developer's machine rather than the repository.

   **The cause is the committed default, not a local file.** `config.py` declares
   `raw_store_path: Path = Path("data/raw")` and
   `aggregate_store_path: Path = Path("data/aggregates.duckdb")`. A `Settings`
   built in a test without those fields therefore points at the repository's own
   data directory whether or not a `.env` exists, so deleting the local `.env`
   did not close this and nothing else will short of setting the fields or
   banning the bare constructor.

   Latent, not realised, verified against the tree as it now stands: after a full
   271-passed run on the `.env`-free tree, `data/aggregates.duckdb` and
   `data/raw/raw_events.duckdb` both still carry their 2026-07-19 19:24 mtimes and
   nothing under `data/` has been written today.

   Exposed sites, most severe first, the first four because they omit
   `raw_store_path`: `tests/aws/test_write_path_factory.py` lines 35, 68, 100 and
   123; `tests/aws/test_store_factory.py` lines 25, 35, 64 and 78;
   `tests/aws/test_teardown_audit.py` line 30; `tests/unit/test_atomic_publish.py`
   line 42; and four `get_settings()` calls, which always read `.env`, at
   `tests/unit/test_generators.py` lines 38 and 50, `tests/unit/test_producer.py`
   line 40, and `tests/integration/test_terraform_offline.py` line 31.

   A lint rule banning a bare `Settings(` and `get_settings()` under `tests/`
   closes the class.

## Alternatives considered

Each was live, each was declined, and the point at which each was declined
matters more than the fact of it. Where an option was declined **after** its
consequence was visible, that is said.

**A quantile-derived threshold.** Declined at drafting, before any data existed.
Setting the threshold at a percentile of observed disagreement makes the
discrimination claim satisfiable by construction: the flag rate would then be a
property of the definition rather than an empirical fact, and the gate could not
go red. A gate satisfiable by construction is not a gate.

**Branch A and branch B, as originally pre-committed by the owner.** Both
declined during the pre-flight, before the freeze. Branch A required a combined
stated uncertainty that neither source publishes and that the guidance does not
provide either. Branch B, a single fixed value in the compared unit, applies the
same absolute bar at every concentration, which is close to inert at the low end
and comparatively tight at the high end. Both got one end of the range wrong.
The replacement is a published criterion that blends a proportional and a
non-proportional term, which is the documented answer to exactly that failure
mode.

**beta = 1**, the weaker of the two conditions the guidance defines on the same
uncertainty. Declined at ratification, before any comparison. Taking it would
mean selecting a different number than the one the guidance publishes, and a
flag under it says only that the difference exceeds the station instrument's
tolerance, which is a statement with no external referent. The count under that
weaker condition is nonetheless computed and reported as evidence, with no floor
attached to it and no claim binding to it. It was also disclosed in the contract
that the chosen criterion is the one more likely to land inside the
discrimination band, that this was considered, and that it is not the reason.

**A wholesale revert to the superseded version of the guidance.** Declined after
its consequence was visible, and that is why the ground is stated narrowly. The
superseded version is internally consistent, prose and table agreeing, and it
flags more at low concentration. It is declined on version currency alone, never
on effect. Citing a superseded document because its arithmetic is more convenient
is the move this project exists to not make.

**Per-station model fetching.** Declined at rule-freezing time. Fetching a model
value at each station's own coordinates would remove the residual offset between
a station and the centre of the cell it is compared against. At the shipped
cadence roughly 250 stations would breach the provider's free tier, and the
pipeline would then have to ship a comparison different from the one the claim
was measured on. The offset is disclosed as a limit instead.

**The licence rule that excluded null-licence stations from admission.** The
owner's, wrong, and corrected after its cost was visible, as narrated above. The
defect carries the change.

**The looser, partial-coverage admission rule.** Declined at rule-freezing time,
on methodological grounds settled before the consequence was weighed. Admitting
a station that covered most but not all of the capture window would have used
more data, but it would let the station population vary hour to hour, so a change
in the flag rate over time could not be separated from a change in which stations
were contributing. A fixed population keeps each city's median computed over the
same stations every hour. Weighed afterwards, the looser rule might have admitted
one additional city, and the contract records that consequence in that order.

**A recency-based admission filter.** The build session's, wrong, and replaced before
the freeze. It selected stations by how recently they had reported relative to
the moment of selection, which is the wrong clock: the comparison consumes hours
that are deliberately old, so a station that stopped reporting after the capture
window but covered all of it belongs in, and one that came online this morning
does not. Admission is decided by coverage of the capture window instead.

**Measuring the mapping radius from the configured city coordinate.** Also the
build session's, also wrong, also replaced before the freeze. The configured coordinate
sits at an arbitrary position inside its model cell, so a station near the city
can fall in a neighbouring cell and be compared against a value that does not
describe it. The radius is measured from the grid point the provider returns.

## Consequences

- One new source adapter and one extension to the existing Open-Meteo adapter,
  both behind the unchanged `EventSource` Protocol and selected through the
  settings object.
- A schema change reaching `SatelliteEvent`, the DuckDB column tuple, the Iceberg
  schema, the DynamoDB item shape and the dashboard. ADR-0007's expectation that
  the OpenAQ upgrade would be an adapter change and not a core change does not
  survive contact, and the contract records the correction rather than preserving
  the expectation.
- The first secret name in `.env.example`, landing with the implementation and
  not with this record. CI stays secret-free.
- One new acceptance test, AT-13, and the specification edits that precede it.
- A permanent, visible consequence in the product: one of the four regions cannot
  be independently checked at all, and will carry the lower provenance tier for
  as long as that remains true. The contract treats this as the strongest output
  of the project rather than as a shortfall in it.

## Falsifiable triggers

- If any predicate in `PREREGISTRATION.md` is changed after commit b81f1c9 by
  anything other than a proof, this reopen has failed on its own terms and the
  trigger 3 condition was not met. An observation may never move it.
- If this ADR is ever edited to state a threshold constant, a claim or a floor,
  the single-authority property is broken. Those belong in the contract, and a
  second copy is a second thing to drift.
- If the implementation cannot satisfy the frozen rules without changing one of
  them, that is a finding to publish, not a rule to adjust.
- If the effort cap is reached with work outstanding, the project ships what
  exists with the unevaluable claims marked unevaluable. A cap that moves is not
  a cap.
