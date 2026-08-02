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

The measurement uncertainty constant for PM2.5 was first verified wrongly, by the
advisor, from a summarised fetch of the superseded version of the guidance. The
owner then verified it independently and **also reported it wrongly**, confirming
the superseded value. The error was caught only when the current version's text
was extracted directly and the parameter table read, at which point the constant
was found to have changed between versions while the surrounding prose had not.
The prose in the current version now contradicts its own table on the same
printed page. The table binds, the discrepancy is quoted in the contract, and the
sensitivity of the threshold to the two candidate values had already been
computed when the constant was ratified. That ordering is disclosed in the
contract. The sensitivity table is analytic rather than observational, so no
observation preceded the pre-registration, but the sequence is stated rather than
left for a reader to reconstruct.

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

**A recency-based admission filter.** The advisor's, wrong, and replaced before
the freeze. It selected stations by how recently they had reported relative to
the moment of selection, which is the wrong clock: the comparison consumes hours
that are deliberately old, so a station that stopped reporting after the capture
window but covered all of it belongs in, and one that came online this morning
does not. Admission is decided by coverage of the capture window instead.

**Measuring the mapping radius from the configured city coordinate.** Also the
advisor's, also wrong, also replaced before the freeze. The configured coordinate
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
