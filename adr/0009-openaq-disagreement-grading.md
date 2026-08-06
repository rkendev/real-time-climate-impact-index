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

## The coverage re-verification, and how its result will be read

Written 2026-08-03, **before the re-verification runs**. The reading is fixed here
while the answer is still unknown, because an interpretation chosen after seeing
a number is not an interpretation, it is a rationalisation.

**Why a settled number is being checked twice.** The coverage figures in the
contract came from a probe that ran at roughly 150 requests per minute against a
published limit of 60. The documentation says exceeding the limit returns 429 and
that repeated exceeding "can lead to either a temporary or permanent ban". That
probe recorded failures which were read at the time as transient errors; they
were most likely throttling. The contract's own section 3 says an empty result is
not a negative result until the query is confirmed well formed, and that rule was
written by the pre-flight and may not have been satisfied by it. The zeros are
load-bearing, because AFR carrying the lower provenance tier permanently is the
project's stated strongest output, so they are re-run at a compliant pace over all
twelve cities rather than the seven that were admitted.

**The three outcomes, and what each means.**

1. **AFR returns zero again**, from a city query chain in which every response is
   200 and no 429 and no other non-200 appears anywhere: the contract's zero is
   **confirmed**. The confirmation and the throttling retrospective that caused it
   both stay in this record. A number checked twice for a stated reason is
   stronger than one never questioned.
2. **AFR returns non-zero**: the contract's zero was **wrong**, and the probable
   cause is the over-rate probe. The correction is published prominently, it
   changes what the project's strongest output is, and it is not softened, not
   explained away as a station that has since appeared, and not filed quietly in a
   findings list.
3. **Any 429 or other non-200 appears in a city's chain**: that city's result is
   **void** and is re-run. A zero from a run containing failures is not a zero,
   which is the contract's section 3 rule applied to this project's own
   measurement rather than only to its sources.

No outcome adjusts a frozen rule, and nothing is tuned to reproduce the
contract's figure of 202 stations across seven cities.

**What is reported.** The funnel per city, not the total: stations within the
radius, then fixed, then reference grade, then carrying a PM2.5 sensor, then
bracketing the capture window, plus the HTTP status distribution for that city's
calls. The funnel is what makes the headline precise, because "AFR has no
monitoring" and "AFR has monitoring that this threshold cannot use, because none
of it is reference grade" are different claims and the second is both stronger
and more interesting. The contract asserts the second; only the funnel shows
which is true.

Excluded cities stay distinguishable by reason and are never written up in one
sentence. Madrid is excluded because reference-grade fixed stations near its grid
point do not cover the capture window, which is a consequence of the frozen radius
and admission rules rather than an absence of monitoring. Lagos, Nairobi, Cairo
and Jakarta were zero at every radius up to the cap, which is a far stronger
statement about the network itself.

## The coverage re-verification: result

Run 2026-08-03, after the reading above was committed at 5668272 and the script at
959a132. Twelve cities, paced below the rate limit. **300 station calls, every one
of them 200, no 429 anywhere, no void city.** Twenty domain probes accompany them,
of which eight returned 400, which is the informative answer and not a failure;
see the apparatus defect below.

```
    city         dom    R km cap   inR  fixed  refgrade  pm25  admitted  statuses
EUR Amsterdam    EU      6.5  no    14     14        10     5         5  200x6
EUR Berlin       EU      6.5  no    17     17        11     9         7  200x10
EUR Madrid       EU      7.0  no    21     21        15     6         6  200x7
NAM New York     GL     25.0 yes    71     71        26    19        15  200x20
NAM Chicago      GL     25.0 yes   311    311        14    10         8  200x11
NAM Los Angeles  GL     25.0 yes   248    248        18    12         6  200x13
AFR Lagos        GL     25.0 yes    61     61         1     1         0  200x2
AFR Nairobi      GL     25.0 yes    16     16         9     9         0  200x10
AFR Cairo        EU      7.4  no     1      1         1     1         0  200x2
ASI Tokyo        GL     25.0 yes   148    148       145   128       119  200x129
ASI Delhi        GL     25.0 yes    98     98        83    81        42  200x82
ASI Jakarta      GL     25.0 yes    27     27         7     7         0  200x8

208 admitted stations across 8 cities
```

### Outcome 1 fired for AFR, and the funnel makes the claim sharper

AFR returned zero again, from chains that were entirely 200 with no 429, so under
the pre-committed reading **the contract's zero is confirmed**. Section 1 of the
contract says AFR has no reference-grade station reporting PM2.5 across the
capture window. That is exactly what the funnel shows, three cities over, and it
needs no softening and no correction.

What the funnel adds is the reason, which the contract could not state because it
did not have a funnel:

> AFR is monitored. Sixty-one fixed stations near Lagos, sixteen near Nairobi,
> twenty-seven near Jakarta. None of it is usable by this threshold, which rests
> on a measurement uncertainty derived for reference methods. Nairobi is the
> sharpest case: nine reference-grade PM2.5 stations, none covering the capture
> window. That is a currency problem rather than an absence, and it is a finding
> about the available data rather than about the continent.

"AFR has no monitoring" would have been false. "AFR has no monitoring this
threshold can use" is true and is the stronger statement. That difference is what
the re-verification bought for its 300 calls, and it is why the recheck was worth
running even though its headline outcome was confirmation.

### Two corrections to the contract's evidence, both attributable to the probe

**Madrid is admitted, with six stations.** The contract excluded it.

The attribution matters more than the number, so the reasoning is recorded rather
than only the conclusion. Seven cities reproduced **exactly**: Amsterdam 5, Berlin
7, New York 15, Chicago 8, Los Angeles 6, Tokyo 119, Delhi 42. Drift in a station
network scatters; it does not leave seven figures untouched while moving one city
from zero to six. And Madrid's admitted sensors report `datetimeFirst` in 2016 and
2023, so they were not newly installed. Two of them were queried directly, outside
the script, and both bracket the capture window. The earlier probe was wrong; the
world was not.

**Cairo's radius was wrong, in the permissive direction.** Cairo resolves to the
European model domain, giving 7.4 km, not the global domain at the 25 km cap. The
pre-flight assumed the domain from the region label instead of probing it. Cairo
returned zero under both radii, so the error made the test easier and Cairo failed
it anyway, which is stronger evidence than an uncharacterised error would be.

**The contract is not amended, and here the outcome-versus-input distinction is
load-bearing for the first time.** Its admitted-city block is labelled an outcome
of the frozen rules rather than an input to them. Correcting it therefore corrects
evidence and moves no predicate: no threshold, no radius rule, no admission rule
and no claim changes. Had that block been written as configuration, this would
have been an amendment to a frozen file and there would have been no clean way to
make it.

### An apparatus defect, and it was correlated with the measurement

The first run reported eight of twelve cities void. Every non-200 was the
Open-Meteo domain probe, which returns 400 for a point outside CAMS Europe. A 400
there has two meanings, "the request failed" and "the point is outside this
domain", and the criterion admitted only the first.

The defect was not random. It voided **exactly** the cities in the global domain
and none in the European one. Left uncaught it would have voided all of AFR and
all of ASI while EUR passed cleanly, which reads as "the global domain could not
be measured" and would have taken the headline with it. It is the same shape as
writing a two-way test over a space that has three regions: the discriminator is
sound on the cases its author pictured and silently wrong on the one they did not.

Scoped to the station chain at 6199998 and re-run. The re-run is what the
pre-committed reading required for a void city in any case.

### Carried forward, not acted on

- Eight admitted cities rather than seven, so D2's holdout ceiling moves from 1176
  to 1344 city-windows. The evaluability precondition still stands with margin, and
  the realised count, after per-window coverage is applied, remains unestablished.
- EUR now rests on three cities rather than two, so the split between the 11 km
  domain and the 45 km one is three against five. That changes the per-domain
  reporting, not the rate D2 binds on.

## The admission artifact, and two things the adapter work surfaced

### The admitted set is pinned, not cached

`docs/evidence/station-admission/2026-08-03.json` carries the sensor location ids
per city, the rule parameters that produced them, the radius per city, the capture
window, and the HTTP status distribution of the run. The adapter **reads** it. It
does not re-derive on startup, on a miss, or on a schedule.

The reason is the distinction that carried the Madrid correction: this set is an
outcome of the frozen rules rather than an input to them, and a published figure
rests on it. A set that silently refreshed could move that figure with nothing
recording that it had, and the drift would be invisible in the same way the
throttled probe's zeros were. Re-derivation is therefore an explicit command that
writes a **new** dated file beside the old one, never over it, with the diff
recorded here. `tests/unit/test_station_admission_artifact.py` pins the totals to
208 across 8 of 12 cities, checks that every city lists exactly as many ids as it
admits, checks that the funnel is monotonic, and checks that the producing run was
clean. Both a hand edit and a silent refresh were seeded and both turn it red.

Station and sensor identifiers are metadata rather than measured values, so the
frozen licence rule, which restricts committing raw station readings, does not
apply to them.

### A frozen validity condition has never been observed to fire

The provider quality flag `hasFlags` was false on every hour sampled, across every
network. The fixture exercising it is therefore labelled a construction rather than
a transcription, and the honest reading is broader than the fixture: **one of the
frozen validity conditions has never been seen to fire against the real
population.**

The rule does not move. What follows is a reporting obligation, pre-committed here
rather than discovered by a reader later: during the capture, the number of hours
across the admitted set carrying `hasFlags` true is counted and reported. If it is
zero, the finding is that the provider flag never fires for these networks over
this window, the filter removed nothing, and D2's denominator is unaffected by it.
That is the same discipline as asserting a witness set is non-empty, applied to a
frozen filter instead of to a test: a filter that has never been observed to
exclude anything may be inert, and saying so is worth more than assuming it is
doing work.

### observedCount is cross-checked, because its own block is wrong elsewhere

The coverage block on the EEA sensor reports `expectedInterval` of `24:00:00` for a
one-hour period and `percentCoverage` of `2400.0`. Both are nonsense, and the
adapter takes `observedCount` from that same block.

Two second routes were established against live responses rather than assumed:

- **Arithmetic within the block.** `percentComplete * expectedCount / 100`
  reproduced `observedCount` exactly on the fifteen-minute network across the
  hours sampled, at 4 of 4 for 100.0, 3 of 4 for 75.0 and 2 of 4 for 50.0, and on
  the provider-hourly network at 1 of 1 for 100.0.
- **The summary block**, which is a different block and therefore the more
  independent of the two: a single underlying sample cannot span a range, so
  `observedCount` of 1 with `min` below `max` is a contradiction.

Where the routes disagree the adapter **reports and drops the hour** under its own
reason code rather than preferring either number. The limit is stated rather than
papered over: the first route shares a block with the field it checks, so a
corrupted count would escape it if `percentComplete` were corrupted consistently.

That same probing also localised the defect: `expectedInterval` reads `01:00:00`
correctly on the fifteen-minute network, so the nonsense is a property of that one
sensor's coverage block rather than of the endpoint.

The cross-check earned its place immediately by failing a fixture of mine that had
`observedCount` of 4 while inheriting `expectedCount` of 1. An invented fixture was
internally impossible; the transcribed replacement is not.

## A licence breach, confirmed, remedied at HEAD, and not erased

Recorded 2026-08-04.

**What happened.** The frozen rule permits raw station values as fixtures only
from providers whose licence allows redistribution. Commit b05a40a transcribed a
real hour from sensor 12234702 at location 5404 into the test fixtures, carrying
its value, its minimum, its maximum and its standard deviation. Confirmed by
direct query before this was written rather than assumed from the aggregate
licence survey: location 5404 is "Pusa, Delhi - IMD", provider CPCB,
`licenses: null`. Unstated terms are not permissive. The values should not have
been committed.

**How the rule failed.** It was written as a rule about *the capture*, a step
that had not yet happened. The breach occurred during a hand transcription while
building adapter fixtures, which is the same act under a different name. A rule
attached to an activity cannot catch an instance of that activity under another
label. That is the lesson, and it is worth more than the fix it prompted.

**The remedy, and its limit stated plainly.** The values are removed from HEAD
and replaced with invented numbers that preserve the observed *structure*, which
is knowledge about the API rather than a licensed measurement: the field layout,
`expectedInterval` reading `01:00:00` on that network, and the arithmetic
relating `percentComplete` to the counts. No permissively licensed substitute was
available to transcribe instead, because every EEA, AirNow and Japanese station
sampled reports `observedCount` of one, so the only observed multi-sample network
is the one whose terms are unstated.

**Removal at HEAD is the best available remedy and it is not full compliance.**
The values remain in the public history at b05a40a. History is not rewritten, and
the reason is worth stating rather than leaving as an omission: this repository
has been public since before the commit, so the scrub-before-publication move
available on the sibling project does not exist here, and rewriting public
history to remove three numbers published under unstated terms would do more
damage to the record than it repairs. The residue is disclosed, which is the
remedy this project uses everywhere else.

**The control that now exists.** `tests/hygiene/test_fixture_provenance.py` is
attached to the artifact rather than to any activity. It asserts that no fixture
file carries the key header with a value, and that every fixture carrying a
measured value declares its source station and a licence on an explicit permitted
list. Both were proven red separately: a planted dummy key fails the first, a
value declared against a non-permitted station fails the second. Adding a licence
to the permitted list requires checking its `redistributionAllowed` flag first;
only ODC-BY has been checked.

## Both frozen validity conditions may be inert, and together they are the rule

The frozen validity condition for a station hour is `hasFlags == false` **and**
`observedCount >= 1`. Neither half has been observed to fire.

`hasFlags` was false on every hour sampled, across every network. And an hour with
no samples appears not to be returned at all: absent hours are omitted from the
results list rather than present with a zero count or a null value, observed
directly where one Berlin sensor returned 18 hours across a 42 hour range rather
than 42 rows with 24 of them empty.

If neither half can fire, **validity admits every hour the API returns, and the
frozen gate is a no-op over this population.** Nothing moves and this is not a
defect. It changes what a reader should believe the filter is doing, which is why
it is recorded rather than left to be inferred.

Pre-committed reporting obligation, extending the one already recorded for
`hasFlags`: during the measurement, count and report together the number of hours
carrying `hasFlags` true, the number reported with `observedCount` below one, and
the number returned with a null value. If all three are zero, the finding is that
the frozen validity gate is inert over this data, and it belongs with the stated
limits rather than among the results.

The corollary for the code is worth labelling honestly. The adapter branches
handling a flagged hour, a zero-sample hour and a null value may be unreachable by
reality, and their tests prove the handling of shapes the API may never produce.
That is defensible, since a rule with no branch is a rule that cannot be honoured
if the shape ever appears, but it is coverage of a hypothetical and should not be
read as coverage of observed behaviour.

## The construction breakdown is fully confounded with city

Recorded before any rate exists, because a limit stated before the number is a
limit and the same words after it are an excuse.

The contract requires the flag rate broken down by how the hourly station value
was built, provider-validated against computed mean. That breakdown **cannot
separate construction from city**, because every EEA, AirNow and Japanese station
sampled reports `observedCount` of one and CPCB is the only multi-sample network
found. The computed-mean arm is therefore Delhi, and nothing else.

So a difference between the two arms is equally well explained by any of: how the
hourly value was built, Delhi's concentration range, its siting mix, the 45 km
model cell it is compared against, or CPCB's calibration practice. The design
separates none of them, and no amount of care in the analysis can separate them
afterwards, because the confound is in the population rather than in the method.

The output still ships, because the contract requires it. It ships with this
paragraph beside it. It may not be read as evidence that construction affects the
rate.

## T2 close-out

**What shipped.** `StationObservation` (E-8), `station` as the third
`EventEnvelope` member, the validation gate widened to carry it, the OpenAQ
adapter behind the unchanged source Protocol with a lazily imported client and no
endpoint or key literal in source, and a composite source that fans out over both
real sources. Station observations reach the transport and the raw store and
touch no index value.

**Guards, and which were proven red.** All of them, by seeding the defect and
watching the failure rather than by watching a pass:

- index invariance, station events changing no record field. Two shapes seeded.
  The crude one, letting station events into the satellite bucket, went red at
  once. **The realistic one, folding station coverage into the confidence grade
  while touching no field value, did not**, because the fixture's only window
  already graded MEASURED and a grade that cannot move cannot be seen to move.
  The fixture now spans all three grades and both shapes go red;
- the widened gate: a malformed station payload, an undeclared event type, and a
  declared type with no model, the last of which was a real crash rather than a
  rejection before the lookup was guarded;
- the negative-space exclusion control, seeded with a reconciliation-shaped
  function;
- the admission artifact pin, seeded with a hand edit and with a silent refresh;
- the fixture provenance control, seeded with a planted key and with a value
  declared against a non-permitted station;
- composite failure isolation, seeded by swallowing the failure and by letting it
  propagate.

**The licence incident.** Real readings from a CPCB station with unstated terms
were committed at b05a40a and removed at cdc7108. The remedy is partial and the
residue is disclosed above; history is not rewritten and the reason is recorded.
The control that would have caught it now exists and is attached to the artifact
rather than to an activity.

**The pinned admission artifact** is `docs/evidence/station-admission/2026-08-03.json`,
version `2026-08-03`, 208 admitted stations across 8 of 12 cities. The adapter
reads it and derives nothing. Re-derivation writes a new dated file and its diff
belongs here.

**Findings carried, not built.** The seven in the list below, unchanged in
substance by T2 except that finding 7, the mypy environment split, was added by
it.

**Two frozen validity conditions may be inert**, as recorded above, and a third
observation now sits beside them: the rule retaining negative readings protects
against a case that is real in one sensor's history but absent from 1710 recent
hours sampled from it.

**What T2 did not do, stated plainly.** No comparison exists. No station value has
been subtracted from, divided by, or otherwise combined with a model value
anywhere in this repository, in code, in a test, in a script or in a terminal. The
negative-space control in `tests/hygiene/test_no_reconciliation_yet.py` remains in
place and remains green, which is the dated evidence that the exclusion period has
not ended. It goes red when T3 legitimately begins, and it is deleted in the same
commit that introduces the tolerance, so its deletion is the record of when the
exclusion ended.

## T3a: a second schema change, and why it is in scope

Recorded 2026-08-04, at the start of T3a and before any comparison exists.

`SatelliteEvent` gains a `city`. The contract freezes the comparison at city
granularity in section 5, and a per-city comparison requires the model side to
carry a city. The field follows mechanically from a frozen rule, exactly as the
envelope's third member and the aggregate model PM2.5 field did, and it is in
scope for the same reason.

Recorded rather than assumed, because the contract's section 2 names the model
PM2.5 field as an in-scope schema change and does not name this one. A reader
comparing the scope list against the diff would otherwise find a field the scope
did not authorise, and section 2 says an apparent necessity outside scope is a
finding to record rather than a scope change to make. This is the record.

**What it was not.** The alternative of leaving the stream at region granularity
and passing city-keyed model values into an offline analysis was declined, and not
because a schema change is inconvenient. It would leave the live pipeline
computing no comparison while an offline analysis computed one, so the index would
not report reduced confidence as section 1 of the contract claims, and D2 would
measure something the shipped system does not do. That is the same failure the
contract already declined when it declined per-station model fetching, and it is
larger here. Reconciling upstream of aggregation was also declined: it contradicts
the trigger UC-8 fixed at `6046845`.

**No key moved, confirmed rather than assumed.** The raw path keys on
`<prefix>/<region>/<window>/<uuid>` in S3 and has no column for the field at all in
DuckDB, where the event body is a `payload JSON` column. The field is additive in
both. This was checked before the field was written, because a DynamoDB key change
is a table replacement rather than a migration, and the same check is owed to the
aggregate fields that arrive with the reconciliation.

**A composition change follows, and it is not cosmetic.** The simulated source
emitted one satellite event per region. A generated event may not be attributed to
a city it was not generated for, so the source now emits one per configured city,
which is the composition the real adapter has always produced. The alternative,
labelling one synthetic reading with the region's first city, is a fabrication of
exactly the kind ADR-0007's no-fabrication rule exists to prevent, and a default
city argument on the generator would have made it silent. `city` is therefore
positional on `generate_satellite_event` and has no default.

**A false green the change created, found and closed.** `test_satellite_event_rejects_out_of_range`
builds a valid E-3 keyword set, corrupts one field and asserts the model rejects
it. Adding a required `city` to the model without adding it to that keyword set
left every case raising for the absent field rather than for the bound under test,
so the whole parameterization passed while asserting only that a required field
was missing. It is now paired with a no-fault control: the base keyword set must
construct before the field is corrupted, which is what makes the rejection
attributable. The same class of error put a `city` into a `WeatherEvent` in the
naive-timestamp test, where it also passed, because that test expects a rejection
and does not care which one. Both were introduced by a mechanical edit across the
construction sites and neither was caught by the suite going green, which is the
argument for the control rather than for more care.

Two consequences, neither of which moves a grade. The confidence grader reads
counts and both stream counts stay above zero, so no window changes tier; the
demo's thin windows are arranged by omitting the satellite stream entirely and by
cutting slots, both of which still work. The simulated backfill publishes more
messages per window than it did, and the bounded default is now at most 384 rather
than 192. A region configured with no city is now refused at construction by both
sources, because an empty city list would have produced weather-only windows that
read as thinned coverage rather than as a misconfiguration.

## T3a: simulated index values moved, and the correction record

Recorded 2026-08-04, correcting a claim made in the commit message of `be6d1a0`.

That commit said no grade moves when the simulated source went from one satellite
event per region to one per city. That is true and it is narrower than a reader
will take it for. **Simulated `pollution_index` values do move, and by a
substantial amount.** The claim "no grade moves" was established; the claim "no
value moves" was not, and it is false.

**Measured, over 2000 seeded window computations of each shape.**

| | mean | sd | min | max |
| --- | --- | --- | --- | --- |
| `pollution_index`, one event per region | 0.6504 | 0.2040 | 0.0246 | 0.9992 |
| `pollution_index`, one event per city | 0.7143 | 0.1141 | 0.2121 | 0.9635 |
| `impact_index`, one event per region | 40.70 | 18.84 | | |
| `impact_index`, one event per city | 42.70 | 17.89 | | |

At the same seed the two agreed on `pollution_index` in 0 of 2000 windows. The
per-seed absolute difference averaged 0.143 with a maximum of 0.738 on a zero to
one scale, and 5.3 with a maximum of 22.6 on the zero to one hundred index. The
confidence grade was MEASURED under both, which is all the earlier claim covered.

**The mean moved, not only the variance, and the mechanism is the clamp.**
Averaging more samples would ordinarily leave the expectation alone and shrink
the spread. `pollution_index` clamps the aerosol term at the saturation constant
before averaging it with cloud cover, and a clamp is not linear. The generator
samples aerosol uniformly over zero to five against a saturation of two, so a
single draw saturates 59.9 percent of the time while a mean of three draws
concentrates near 2.5 and saturates 71.7 percent of the time. The mean aerosol
sub-term rises from 0.799 to 0.928, and that is where the shift comes from.

**Which shape was wrong.** E-7 has the real source sampling one reading per city,
and the real adapter has always emitted one satellite event per city per tick, so
a real-source window has always held three per region. The mean over the window
was therefore already a mean of three there. The simulated source was the one
that disagreed with E-7, and aligning it is a fidelity improvement rather than a
defect introduced. Nothing on the real path moved, because nothing on the real
path changed.

The consequence is confined to the simulated feed and the demo backfill that runs
on it, which the dashboard already declares as generated rather than collected.
No shipped real-source row is affected and none was recomputed.

**Recorded because the suite was green.** No test pinned a simulated
`pollution_index` value, so the whole shift passed unremarked. A green suite
established that nothing asserted these numbers, not that they were unchanged,
and those are different findings.

## T3a: the exclusion period ended, and what replaced the control

Recorded 2026-08-04. This is the dated record the negative-space control was
built to produce.

**The control went red before it was deleted, and this is what it said.** Both
its assertions fired, naming what had appeared:

```
reconciliation settings exist during T2: ['mqo_alpha', 'mqo_beta',
  'mqo_reference_value_ugm3', 'mqo_relative_uncertainty_at_reference']
reconciliation machinery exists during T2: ['core/models.py:81
  PM25DisagreementState', 'core/reconciliation.py:53 mqo_tolerance',
  'core/reconciliation.py:124 reconcile', 'core/reconciliation.py:160
  _reconcile_one']
```

Recorded verbatim because it is the evidence that the exclusion ended by intent
rather than by decay. A control that was quietly removed while still green would
leave no way to tell the two apart.

**The successor landed in the same commit.** `tests/hygiene/test_holdout_not_opened.py`
exists before `tests/hygiene/test_no_reconciliation_yet.py` is gone, in one
commit, because that commit is where the risk peaks: comparison becomes possible
for the first time and the only automated guard against it disappears in the same
breath. A retirement that leaves a gap is worse than no retirement.

It no longer forbids comparison. It forbids comparison over the holdout, in four
independent ways, and each was proven red by making the violation and watching
the failure rather than by watching a pass:

1. the entry point requires an explicit window and has no default;
2. the holdout is not nameable. The settings object holds one window and the
   entry point accepts only what it holds, and there is deliberately no
   `--window-start` or `--window-end`, so a holdout date is not expressible
   through the interface at all;
3. no holdout capture exists on disk, checked both by what the artifacts declare
   and by the observation timestamps they actually wrote;
4. no holdout date appears on the run surface.

The forbidden range is parsed out of the contract rather than restated, so the
rule lives in one place. The test also forbids itself from naming a holdout date,
and that assertion fired on its own documentation comment during development,
which is the smallest possible demonstration that it works.

**A defect in the first version of the successor, found by the red proof.** The
run-surface scan enumerated files with `git ls-files`, which lists tracked files
only. A reconciliation entry point is a new and therefore untracked file when it
first appears, so the scan was not reading it at all: a holdout date appended to
`scripts/reconcile.py` passed. The scan now uses `--cached --others
--exclude-standard`, which covers uncommitted files while still honouring
`.gitignore`, and it went from 0 to 116 files on the run surface.

Recorded because of what found it. The green was indistinguishable from a working
control, and running the violation was the only thing that told them apart. This
is the fourth time in this project that a guard passing by absence turned out to
be passing over nothing, after the AST walk, the fixture that could not move a
grade, and the parameterization that asserted only a missing field.

**The single authority, made enforceable.** Section 9 makes the settings object
the authority and forbids a constant in adapter code, so the numbers now live in
two places. `tests/hygiene/test_settings_match_contract.py` closes that by parsing
`PREREGISTRATION.md` out of the repository and asserting the settings match
sections 4.1 and 5. Parsing rather than restating inline was chosen because
restating copies the numbers into a third place, which is the problem the test
exists to solve. Three things keep the parse honest: structural assertions that
run before any value is read, an anti-vacuity test that runs the same parser over
a document with different values, and a freeze assertion that
`git log -- PREREGISTRATION.md` still returns exactly one commit and that it is
`b81f1c9`. That last one turns this ADR's prose claim about the freeze into a
mechanical one that runs on every test invocation, including after the control
rate has been seen.

**A second schema change, on the record.** `ClimateIndexRecord` gains five fields,
not two. The contract's union rule requires the flagged-city count to be recorded,
and D1 requires both values to be reported, which is per city because the
comparison is per city. So the record carries the state, the tier,
`flagged_city_count`, `covered_city_count`, and `city_comparisons`. The per-city
detail is one JSON column rather than a second table: a table would introduce a
second natural key and therefore a second idempotency proof, and the frozen scope
admits neither.

`covered_city_count` is redundant with the detail, deliberately. It is D2's
denominator and the figure the 200-city-window precondition is tested against, so
it is established by two derivations that must agree: the summed scalar, and a
count over the per-city detail that round-trips through JSON encoding in every
store. A single common-mode error cannot satisfy both. Without it that number
would have been produced by parsing a JSON blob with nothing checking the parse.

**No key moved, in any of the three stores.** The DynamoDB partition and sort keys
are unchanged and the new fields are plain attributes; the Iceberg identifier
fields stay `[1, 2, 3]` and the new fields take ids 10 to 14 as optional, reusing
and reordering nothing; the local store appends to `ADDED_COLUMNS` and migrates in
place. Confirmed before the fields were written rather than after, because a key
change in either cloud store is a table replacement and not a migration.

**The two states are required with no default.** A default would make "never
reconciled" and "reconciled and found not comparable" the same value on every row,
and telling those apart is exactly what the no-inherited-grade rule needs. Rows
written before the fields existed carry neither, and each store maps their absence
onto the two documented states once, at its read boundary, where the mapping is
visible. Requiring them also caught two call sites the suite did not: the AT-5 and
NFR-P3 verify scripts both construct records, and mypy named them immediately.

## T3a: AT-13, and the fixture that had to be able to fail

Recorded 2026-08-04. AT-13 closes over recorded fixtures, before the control run
and deliberately so: three control faults end the project, and a fault this test
would have caught spends a scarce budget on a known-avoidable failure.

**The weak claim, named.** "Every closed region-window carries a disagreement
state and a provenance tier" is satisfied completely by a fixture in which every
window is NOT_COMPARED and UNCHECKED. That is the T2 lesson in a new place: the
station-boundary guard once passed over a fixture whose only window already
graded MEASURED, and a grade that cannot move cannot be seen to move. A guard
over a state machine needs a fixture that reaches more than one state.

So the fixture reaches three, and a companion test asserts that it does. EUR is
covered and agreeing, ASI is covered and disagreeing well past the tolerance, AFR
has no qualifying station at all. NAM is present with coverage one short of the
frozen minimum, because having stations and still not being covered is a
different case from having none, and a fixture holding only the AFR case would
let a rule that ignored the minimum pass.

**Proven by making the fixture inert and watching what survived.** With every
station row removed, so that every window is NOT_COMPARED and UNCHECKED, six of
the nine tests went red and **three still passed**:

* `test_every_closed_region_window_carries_both_states`, which is the weak claim
  itself;
* `test_an_uncovered_window_carries_the_unchecked_tier`, because everything was
  uncovered;
* `test_pollution_index_is_byte_identical_with_reconciliation_not_called`,
  because nothing had been reconciled for the index to be invariant to.

Those three are exactly the shape of an AT-13 that establishes the apparatus ran
rather than that it discriminated. The companion is what closes the gap, and the
invariance claim is now paired with its own non-vacuity test asserting that
reconciliation changed something before its not changing the index means
anything.

**The index comparison is on `repr`, not `==`.** "Byte-identical" is the word the
plan used and a float differing below printing precision would satisfy equality.

**The fixture licence surface grew, so the licence control grew with it.**
`tests/hygiene/test_fixture_provenance.py` scanned one fixture module by a
hardcoded tuple, so a second fixture module would have been a hole in exactly the
way the untracked-file hole was. The AT-13 fixture is entirely synthetic and says
so in its own docstring, and it is listed in the scan anyway, because "we know it
is clean" is the claim that control exists to replace. The key-shaped and header
scans also gained an anti-vacuity check, since a clean tree and a broken regex
had until now looked the same.

## T3a: a control's scope is derived, never enumerated

Recorded 2026-08-04, as a standing rule for the rest of this project.

Three controls in this repository have now been green while looking at the wrong
set of files:

* the pre-commit hygiene gate read tracked files only;
* the holdout scan used `git ls-files`, which cannot see a brand-new entry point,
  so it read none of `scripts/reconcile.py` and passed a holdout date appended to
  it;
* the fixture provenance scan read a hardcoded tuple, which would have left the
  next fixture module outside the licence control entirely.

**The failure mode is a populated but stale scope, not an empty one.** In every
case the scan read real files and reported a real green. Asserting the scope is
non-empty would have caught none of the three, which is why non-emptiness is not
the check.

So every control from here on derives its scope by walking the tree or the
working set, asserts it is non-empty, and **proves coverage by adding a member
and requiring the control to notice**. The provenance scan now derives from
`tests/**/*fixtures*.py` and creates a probe file to prove the derivation is
live; the holdout scan does the same on the run surface. Reverting the provenance
scan to the tuple written one commit earlier turns its new proof red with "a new
fixture module was not picked up by the scan", which is what a stale scope looks
like when something is finally checking for it.

## T3a: the NFR-DQ3 seeded violation

Recorded 2026-08-04. Every guard below has its green path and its red path
through the same function, because a red proof written against a bespoke
assertion proves something about the bespoke assertion and nothing about the
shipped guard.

**The pipeline made to resolve.** The guard recomputes what each source
actually said from the raw streams and requires the record to carry exactly that,
rather than checking the record against itself, which would accept any consistent
lie. Three seeds, because resolution has three shapes that fail independently:
substitution writes one source's value into the other's place, averaging replaces
both with a number that is neither, and preference keeps one and drops the other.
Each is red on its own.

The fourth seeded violation the plan requires, for the widened validation gate
(FR-3, INV-3, E-4), was closed in T2 at `tests/unit/test_station_boundary.py` and
is not reopened here. Named so that the plan's list of four does not read as three
delivered and one forgotten.

## T3a: the NFR-DQ4 seeded violations, and the meta-test's own red proof

Recorded 2026-08-04.

**Both branches, seeded separately.** The guard recomputes each tier from
that record's own coverage. Branch one forces a computed tier onto an uncovered
window, and a second seed forges the coverage count so that a window claiming
coverage it did not have is caught as well as one carrying a tier it did not
earn. Branch two carries a previous window's tier forward, and separately copies a
neighbouring region's.

**The inheritance branch, and why its fixture is load-bearing.** AFR guarantees
the uncovered branch a witness whether anyone arranges one or not. Inheritance has
no such guarantee, and it is worse than that: inheritance is invisible whenever
the inherited tier equals the tier the window would have earned anyway. So the
guard can only see it over a fixture where the previous window and the
neighbouring region both differ from the target, and the fixture is therefore part
of the guard rather than scenery around it.

**The meta-test has its own red proof.** `assert_fixture_can_expose_inheritance`
states those three properties, and it is itself a guard that would otherwise only
ever have been seen passing. It is handed three inadequate fixtures, each lacking
exactly one property, and fails on each separately: one spanning a single tier,
one where each region is constant over time so no previous-window difference
exists, and one where every region agrees within each window so no neighbour
difference exists. A fourth case, the adequate shape, is asserted to pass, because
three reds mean nothing from a function that rejects everything.

Without that, the thing protecting the inheritance seed from being vacuous would
itself be unverified, which is the same recursion as a call-site gate that nothing
checks the call site of.

## T3a: the holdout opens regardless, written before the number exists

Recorded 2026-08-04, **before the control window has been captured and before any
comparison has been computed over any real hour**. That timing is the whole point
of the paragraph and it is why this sits here rather than in the disclosure that
follows the run.

> The holdout opens exactly once regardless of what the control window showed.
> The control rate is not admissible as a reason to skip, shorten or reframe the
> D2 evaluation.

**Why this needs writing at all.** Every quantity the control rate could move is
frozen and now mechanically pinned: T, beta, alpha, `Ur(RV)`, `RV`, the 1 to 33
band, the 200 city-window precondition, the minimum coverage of three, the median
rule and the union rule are all in the contract at `b81f1c9`, and
`tests/hygiene/test_settings_match_contract.py` fails if the settings drift from
them or if the contract itself is edited.

The **procedure** is not pinned by any of that, and it is the one lever left. If
the control window comes back at, say, 0.3 percent, the available inference is
that D2 will land below its band, be declared uninformative, and send everything
to report-only, so T3b is not worth running. That reasoning would be an
observation moving a procedure rather than a predicate. It is the same class of
move the freeze exists to prevent, it would be entirely defensible-sounding at the
time, and nothing in the mechanical apparatus would stop it.

**Why now rather than after.** Written before the rate exists, this is a
constraint. Written after, it is a defence, and a reader would be right to weigh
it as one. That is the same reason the construction confound was written into this
record in T2 before any rate existed, and the same reason the alpha ratification
sequence was disclosed rather than tidied.

The re-run cap is unaffected and stands as the contract sets it: at most two
control re-runs after a diagnosed apparatus repair, every fault diagnosed in
writing before any repair, a third fault shipping the project as "the measurement
could not be completed" with the three diagnoses. A fault is not a rate, and none
of this makes a blocked run into a finding.

## Follow-up: the fifth contract defect, and the first internal one

Recorded 2026-08-04, before the control window was captured.

Section 5 of `PREREGISTRATION.md` names the station source twice and the two do
not agree. Its capture paragraph says the capture is "drawn from the OpenAQ
archive". Its temporal alignment paragraph says the station side is "the
`/v3/sensors/{id}/hours` value for the half-open hour `[H, H+1)`". Those are
different inputs, not two descriptions of one.

**The resolution: the endpoint binds and the archive is not an admissible source
for a station value.** The archive carries raw irregular instants, so drawing from
it means computing every hourly value locally. That would make every station a
computed mean, which destroys the provider-hourly against computed-mean breakdown
the contract requires as a reported output and collapses the one axis on which the
CPCB construction confound is visible at all. It would also mean a frozen rule was
set aside because a keyless route was cheaper, which is the shape of decision this
project exists not to make. So the key is required and there is no keyless route to
a station value.

**The contract is not amended.** As with the four before it, the freeze commit
stays untouched; the reading is recorded here and in `30_plan.md`, before the
capture rather than during it.

**Why this one is different from the other four.** The earlier defects were the
contract being wrong about the world: a superseded constant, an attribution slip,
a propagation path through the wrong carrier, a description of the codebase that
was never checked. This one is the contract being inconsistent with itself, and
nothing outside the document was needed to find it.

**Why it went unnoticed.** The contract was reviewed hard for its external
citations, and later, after the fourth defect, for its claims about the codebase.
It was never once read end to end against itself. A document that says two
different things about the same input is a document nobody read that way, and the
review effort had been spent entirely on whether it agreed with things outside it.

The reusable lesson sits beside the fourth defect's rather than replacing it. That
one said a pre-registration describing an existing system must verify its
description of that system. This one says a pre-registration must also be read
against itself, because internal contradiction needs no external source to detect
and no amount of external verification will surface it.

## Capture attempt 1, voided: diagnosis

Written 2026-08-04T14:14Z, **before any repair was attempted**, per the contract's
rule that every apparatus fault is diagnosed in writing first.

**What happened.** The first station call of the first capture attempt returned
404 and the attempt was voided. Recorded in
`docs/evidence/capture/voided-control.json`: one station call, status 404, zero
model calls, nothing kept on disk.

**The fault.** The requested URL was
`https://api.openaq.org/v3/v3/sensors/80/hours`. The path segment `/v3` appears
twice. `CII_OPENAQ_BASE_URL` is `https://api.openaq.org/v3`, and
`scripts/capture_window.py` held its endpoint constant as
`/v3/sensors/{sensor_id}/hours`, so joining them duplicated the version segment.
The shipped adapter has always had this right, at
`src/climate_index/adapters/openaq/source.py:240`, which builds
`f"{self._base_url}/sensors/{sensor.sensor_id}/hours"` against the same setting.
The capture script restated the path instead of matching the one working example
in the repository.

**Repair.** Drop the `/v3` from the capture script's endpoint constant so it joins
the base the same way the adapter does.

**Why no test caught it.** The capture script's tests covered what the parsing
does with a payload, what the artifact records, what the void history does. Not
one of them constructed a URL. The whole module was tested from the response
inwards, and the one thing that decides whether a response arrives at all was
outside the tests. A test asserting the built URL is added with the repair.

**Whether this counts against the contract's re-run cap.** The contract permits
the control window to be re-run after a diagnosed apparatus repair at most twice,
and a third fault ships the project as "the measurement could not be completed".
My reading is that **this does not count against that cap**, and the reasoning is
stated so it can be overruled rather than assumed:

* the cap governs the control-window *run*, which is the reconciliation over
  captured data. This failure was in data acquisition, before it;
* no station value was retrieved, no model value was fetched, no comparison was
  computed, and no rate of any kind was observed. Nothing about the control
  window was seen;
* the cap exists to stop a measurement being re-run until it gives an agreeable
  answer. A 404 on the first call, from a doubled path segment, cannot have been
  influenced by and cannot have influenced any result.

The conservative reading is that any fault in the apparatus counts, in which case
one of two permitted re-runs is now spent. That reading is recorded here beside
mine so a later reader is choosing between two stated positions rather than
discovering only the convenient one. Under either reading the holdout still opens
exactly once.

## Capture attempt 2, succeeded, and what it showed about admission

Recorded 2026-08-04. The capture is `docs/evidence/capture/2026-08-04-control.json`.
No comparison has been computed over it; that is commit 7.

**The run.** 208 station calls, all 200. 12 model calls, all 200. No 429 and no
rate limiting: the provider reported 59 of 60 remaining at the first response and
53 at the last. Realized bounds `2026-07-17T00:00:00Z` to `2026-07-23T23:00:00Z`
on both sources, which is strictly inside the control window and strictly before
the holdout. The voided first attempt is carried in the artifact's history.

**The finding, and it is a large one. Of 208 admitted sensors, 27 returned data.**
The model side is complete: 12 cities times 168 hours is 2016 rows, all present.
The station side is 4031 rows from 27 distinct stations, and two of the eight
admitted cities returned nothing at all: Tokyo, which holds 119 of the 208
admitted sensors, and Los Angeles.

**Diagnosed rather than assumed.** Every call returned 200, so this is not a
transport failure. Sensors were probed over the control window and over a window
strictly after the sealed holdout, and the pattern is unambiguous: a sensor either
serves data in **both** windows or in **neither**. Tokyo 1214487 and 1214508, Los
Angeles 1948 and 7936, Amsterdam 80 and Delhi 17 all return `found=0` in both.
Amsterdam 95 and Delhi 50 return data in both. Nothing about the control window is
special, and nothing about the capture failed.

**What is actually wrong is a premise of the frozen admission rule.** A station is
admitted when its PM2.5 sensor's `datetimeFirst` and `datetimeLast` bracket the
capture window, and the contract states the purpose of that rule as ensuring the
sensor "covered the whole span being measured". It does not ensure that. Those two
fields are location-level metadata about when a sensor first and last reported
anything; they evidently do not imply that `/v3/sensors/{id}/hours` serves an
hourly rollup for the span between them. The rule was applied correctly and its
premise is false.

**This is recorded, not repaired.** The admission rule is frozen, the artifact is
pinned at version 2026-08-03, and the obvious move now visible, loosening
admission or re-deriving the admitted set so that more sensors carry data, is
exactly an observation moving a frozen rule. It is the same move the licence
correction had to be defended against, and it would be worse here because the
observation is of the measurement's own denominator. The rule does not move. What
moves is the record.

**The consequence, computed rather than guessed, and it corrects the guess.** The
paragraph that stood here predicted that the contract's NOT EVALUABLE provision
was "considerably more likely to fire than when it was written". That prediction
was made before the coverage arithmetic was done, and **it is wrong**. The
arithmetic is admissible now because coverage is not disagreement and this is the
control window, and it is recorded here with the prediction it overturns rather
than in place of it.

Coverage requires at least 3 qualifying stations in a city-window, so a city
contributing two stations produces no covered window at all however completely
those two serve. The distribution, not the average, is what decides D2's
evaluability:

| city | admitted | contributing | hours with 3 or more | ceiling if all 168 |
| --- | ---: | ---: | ---: | ---: |
| Tokyo | 119 | 0 | 0 | 0 |
| Delhi | 42 | 15 | 162 | 168 |
| New York | 15 | 4 | 168 | 168 |
| Chicago | 8 | 2 | 0 | 0 |
| Berlin | 7 | 2 | 0 | 0 |
| Madrid | 6 | 3 | 156 | 168 |
| Los Angeles | 6 | 0 | 0 | 0 |
| Amsterdam | 5 | 1 | 0 | 0 |
| **total** | **208** | **27** | **486** | **504** |

**486 covered city-windows in the control week, against a precondition of 200.**
Three cities of eight clear the minimum coverage rule; the other five contribute
nothing. The ceiling is 504 rather than the 1176 the contract's reasoning
supposed, so the margin is less than half what was assumed, but 200 is cleared
about two and a half times over. If the holdout week resembles the control week,
**D2 is likely to be evaluable**, and the earlier prediction to the contrary is
withdrawn.

Three things follow that are worth stating before the holdout is opened:

* **The margin is thin in a specific place.** Madrid contributes exactly 3
  stations, the minimum. One station absent for an hour takes that hour from
  covered to uncovered, and one station absent for the week takes Madrid from 156
  covered windows to zero, which alone would drop the total to 330. New York's 4
  is the next most fragile. The 486 is not a robust number and should not be
  quoted as though it were.
* **Berlin was the city the contract disclosed as sitting near this boundary**,
  with seven admitted stations and a completeness sample suggesting sensitivity.
  The disclosure named the right city and understated the effect: Berlin
  contributes two stations and therefore zero covered windows.
* **The per-domain breakdown the contract requires as an output is now lopsided.**
  Delhi and New York are CAMS global; Madrid is the only CAMS Europe city with any
  coverage at all. A per-domain rate for Europe would rest on one city, and the
  CPCB construction confound already recorded for Delhi now covers 162 of the 486
  covered windows, a third of the total.

None of this is a comparison. No station value has been subtracted from any model
value, and the flag rate remains unobserved.

**No apparatus fault.** The capture did what it was asked to do and recorded what
the provider served. A thin station side is a fact about the data, not a defect in
the instrument, and it is not grounds for a re-run.

## Follow-up: the sixth contract defect, a well-formed rule on a false premise

Recorded 2026-08-04, after the control capture and before any comparison.

**The defect.** Section 5's admission rule admits a station when its PM2.5
sensor's `datetimeFirst` and `datetimeLast` bracket the capture window, and states
the purpose as ensuring the sensor "covered the whole span being measured". Those
two fields record when a sensor first and last reported anything. They do not
imply that `/v3/sensors/{id}/hours` serves an hourly rollup across the span
between them, and for 181 of 208 admitted sensors it does not.

**What distinguishes it from the first five.** Defects one through four were the
document being wrong about the world: a superseded constant, an attribution slip,
a propagation path through the wrong carrier, a description of the codebase nobody
checked. Defect five was the document being inconsistent with itself. This one is
neither. **The rule is well formed, was applied correctly, and rests on a premise
that is false.** Nothing in the document contradicts anything else in it, and
nothing in it misdescribes an external fact. It infers a property of one endpoint
from a field served by another, and the inference does not hold.

**The lesson, in the form it generalises.** The pre-flight verified that
`/v3/sensors/{id}/hours` works, from one sensor per city, and recorded its shape
in detail: the half-open hour, `period.label` of `1hour`, `flagInfo.hasFlags`,
`coverage.observedCount`. Admission then admitted 208 sensors on `/v3/locations`
metadata alone. **A capability was measured and a coverage was assumed.**
Verifying that a field exists, and even that an endpoint works, is not verifying
what either implies about what a different endpoint will serve for a given
sensor over a given span. The only way to have caught this before the freeze was
to ask the hours endpoint about the actual capture window for more than one
sensor per city, which is a metadata-only query and would have cost nothing.

**A sharper version of the same miss, found while checking this.** The record was
searched for the completeness evidence behind the admitted population. There is
**no Tokyo completeness sample and no Los Angeles one**. The only completeness
evidence anywhere in the contract or this ADR is a single unnamed Berlin sensor
returning 18 hours across a 42 hour range, cited twice: once to disclose that
Berlin sits near the coverage boundary, and once to suggest the realised
city-window count could be materially lower than the ceiling.

So neither branch of the obvious question applies. It is not that a sampled Tokyo
sensor is outside the admitted set, and not that the population has shifted since
2026-08-03. **One sensor, in one city, was the entire completeness evidence for a
population of 208 sensors across eight cities**, and that city is Berlin, which
now contributes two stations and therefore no covered windows at all. The sample
was also not reproducible: the sensor was never named, so it cannot be re-queried
to distinguish a change from a misreading.

**Not repaired, and the reason is the same as before.** The admission rule is
frozen and the artifact is pinned at 2026-08-03. Re-deriving the admitted set on
the strength of this observation would move a frozen rule, and it would move the
measurement's own denominator. What changes is the record.

**The figure to quote is 208 admitted and 27 contributing.** Every later summary
will be tempted to describe the scale as 208 admitted stations, because that is
the larger and more flattering number and it is the one the contract states. The
honest pair is both, and the sentence between them is the finding: **OpenAQ's
location metadata does not predict what its hourly endpoint serves.** That is a
second-order version of the AFR result and a more useful one, because AFR is data
that visibly does not exist while this is data that appears to.

## The per-domain breakdown is fully confounded with city, exactly as construction is

Recorded before any rate exists, because a limit stated before the number is a
limit and the same words after it are an excuse.

The contract requires the flag rate broken down by model domain, and gives the
reason: the coarser domain carries the larger representativeness term and would be
expected to flag more, so a pooled rate driven by the global-grid regions is to be
recorded rather than presented as uniform. That breakdown **cannot separate domain
from city**, because of the eight admitted cities only three clear the minimum
coverage rule, and of those three **Madrid is the only CAMS Europe city with any
coverage at all**. The 11 km arm is therefore Madrid, and nothing else.

So a difference between the two arms is equally well explained by any of: the
model cell size, Madrid's concentration range, its siting mix, its three
contributing stations against Delhi's fifteen and New York's four, or the
calibration practice of the one Spanish network involved. The design separates
none of them, and no amount of care in the analysis can separate them afterwards,
because the confound is in the population rather than in the method.

The output still ships, because the contract requires it. It ships with this
paragraph beside it. It may not be read as evidence that model resolution affects
the rate.

**Both of the contract's required breakdowns are now single-city contrasts.** The
construction breakdown is Delhi against not-Delhi and was recorded as such in T2.
The per-domain breakdown is Madrid against not-Madrid and is recorded as such
here. Two required outputs, each a city contrast wearing another name. That the
first was known before the capture and the second only became visible after it is
a fact about when each was detectable, not a difference in how either should be
read.

## 486 city-windows is three city-weeks, not 486 observations

Recorded before any rate exists, for the same reason.

The evaluability precondition exists to rule out a witness set too small to carry
a percentage, and 486 clears 200 comfortably. **D2 is evaluable on its own frozen
terms and nothing moves**: the precondition is met, the band does not change, and
the rate will be computed and reported as the contract requires.

The count is nonetheless not what a reader will take it for. It was written as
though city-windows were independent, and they are not. They are 168 consecutive
hours from each of three cities, and hourly surface PM2.5 persists strongly over
many hours: consecutive hours in one city are close to the same observation
repeated. **The effective number of independent clusters is three, not 486.**

This belongs in section 7's territory, which records what a pass does not
establish. A rate computed over this population is precise about three city-weeks,
one each in Madrid, Delhi and New York, over seven specific days in July 2026. It
carries almost no generalisation beyond them. It is not a rate for the eight
admitted cities, not a rate for the four regions, and not a property of either
data source in general. Any confidence interval computed as though n were 486
would be wrong by a large factor, and none is computed here.

Nothing about this moves a predicate. The precondition is a floor on the witness
set and 486 clears it; this paragraph is about what the resulting number means,
which the contract's section 7 already reserves for exactly this kind of statement.

## Madrid at exactly three: the single point of failure, and its pre-committed handling

Recorded before the holdout is opened, so that the response is chosen without
knowing whether it will be needed.

Madrid contributes exactly 3 stations, which is the minimum coverage rule's
threshold. One station absent for the holdout week takes the total from 486 to
330. The same single loss, because it is Madrid, **removes the entire CAMS Europe
domain from the comparison** and reduces the per-domain breakdown from two arms to
one, at which point that required output has nothing to contrast.

**If it happens, it is reported and not repaired.** Pre-committed here, in
advance:

* no substitution of a station, from a neighbouring city or anywhere else;
* no change to the radius rule, in either direction;
* no re-derivation of the admitted set, which is pinned at version 2026-08-03;
* no dropping the minimum coverage rule from three to two, which is the single
  most tempting move available and the one that would most obviously be an
  observation moving a frozen rule.

The pre-registered responses already exist and are sufficient. Below 200 covered
city-windows, D2 is NOT EVALUABLE and ships as such. Outside the 1 to 33 band, the
grade is declared uninformative and every result ships report-only. A per-domain
breakdown with one arm is reported as a breakdown with one arm, with the reason.
None of that needs a new rule and none of it may be improved on after the fact.

**The contract named the right city and was quantitatively optimistic.** Section 5
disclosed in advance that Berlin sits near this boundary, with seven admitted
stations and a completeness sample suggesting sensitivity, and said its
covered-window count would be unusually sensitive to the minimum coverage rule.
That was directionally correct: Berlin is indeed sensitive to the rule. It was
also optimistic by the whole quantity in question, because Berlin does not sit
near the boundary, it contributes two stations and therefore **zero** covered
windows. The disclosure identified the right risk and understated its size, and
Madrid, which the disclosure does not mention, is now the city actually sitting on
the threshold. Both halves of that are recorded because a caveat that was
directionally right is not the same as one that was right.

## The control-window run, and the rate it showed

Recorded 2026-08-04. **This is an apparatus check and not a result.** The control
window is not the holdout, so D2's 1 to 33 band and its 200 city-window
precondition apply to none of what follows. The run completed with no apparatus
fault, at the first attempt, so no re-run of the contract's two was needed.

**A choice made on principle before either number was seen.** The run used a
60 minute window. The frozen temporal alignment pairs both sources on the hour,
and the contract itself notes that at the local default of 30 every second window
holds no fresh observation. Running at 30 would have made half the city-windows
empty as an artifact of pipeline window size rather than of any frozen rule. That
follows from the contract and not from the outcome, and it was stated before the
run.

### The numbers

| | covered city-windows | flagged | rate |
| --- | ---: | ---: | ---: |
| **pooled** | **486** | **274** | **56.4%** |
| Delhi (CAMS global, 45 km) | 162 | 135 | 83.3% |
| New York (CAMS global, 45 km) | 168 | 139 | 82.7% |
| Madrid (CAMS Europe, 11 km) | 156 | 0 | 0.0% |

Region-windows: 672, of which 486 STATION_CHECKED and 186 UNCHECKED; by state, 274
DISAGREED, 212 AGREED, 186 NOT_COMPARED. The covered count of 486 was established
by both derivations independently and they agreed, which is what
`cross_check_covered_count` exists to require.

**The union rule never unioned anything.** No region has two cities clearing the
minimum coverage rule, so every covered region-window rests on exactly one city.
The identity between 486 covered city-windows and 486 STATION_CHECKED
region-windows is that fact, not a coincidence.

**The per-domain split is total, and it is the confound recorded in advance.**
CAMS global flags 274 of 330; CAMS Europe flags 0 of 156. That is as clean a split
as the arithmetic permits, and it is exactly the contrast the paragraph committed
before this run said may not be read as evidence that model resolution affects the
rate, because the 11 km arm is Madrid and nothing else. A reader looking at
83% against 0% will want to conclude something about grid resolution. The design
does not support it and no analysis after the fact can separate resolution from
Madrid.

**The weaker condition**, reported as evidence with no claim bound to it: of 486
covered city-windows, 146 satisfy `|Oi - Mi| <= U(Oi)` and 340 do not.

### Nothing moved, and here is the proof, run after the number

The freeze evidence is run and recorded **after** the rate was seen, not before.
Checked before, it proves something nobody doubted. Checked after, it proves the
thing that matters. Executed at `2026-08-04T14:52:48Z`, with the rate above
already on screen:

```
$ git log --format=%H -- PREREGISTRATION.md
b81f1c97ae1a7e69918d918d5636318f57aee791

$ git log --format='%h %ci' -1 -- PREREGISTRATION.md
b81f1c9 2026-08-02 20:25:16 +0000

$ pytest tests/hygiene/test_settings_match_contract.py
7 passed
```

One commit, dated two days before this run, and the settings still match sections
4.1 and 5 of the document at that commit. T, beta at 2, alpha at 0.50, `Ur(RV)` at
0.36, `RV` at 25, the minimum coverage of 3, the median rule, the union rule, the
1 to 33 band and the 200 precondition are all exactly as frozen. **No predicate
moved after the number was seen.**

And the paragraph committed at `97d59e8`, before the capture existed, stands
unchanged beneath it: the holdout opens exactly once regardless of what the
control window showed, and this rate is not admissible as a reason to skip,
shorten or reframe the D2 evaluation. A pooled 56.4% sits above the 1 to 33 band.
That is not a reason to do anything differently, and the control window is not the
holdout.

### The three pre-committed inert-condition counts, one answered and two lost

Section 5 pre-commits to counting, during the measurement, the hours carrying
`hasFlags` true, the hours with `observedCount` below one, and the hours returned
with a null value.

**Negative values, answered.** 24 of 4031 retained rows are negative, 0.60%.
Median -2.55, distributed as 7 in `[-1, 0)`, 14 in `[-5, -1)`, 1 in `[-10, -5)`
and 2 below -10. By city: New York 13, Delhi 9, Madrid 2.

**And the two below -10 are not measurements.** Both are `-998.0`, from Madrid
station 4331, at two separate hours. That is a sentinel, and it passed both frozen
validity conditions: `hasFlags` was false and `observedCount` was 1. The frozen
gate does not catch it, and the contract's decision to treat the provider's own
flag as the external authority on validity is precisely what lets it through.

**The median rule earned its stated purpose, in the one city that could least
afford it.** Madrid contributes exactly three stations. A mean over
`{-998, x, y}` would have driven Madrid's value to about -330 and flagged every
hour it touched. The median took the middle value and the two sentinel hours
passed through without distorting anything, which is why Madrid reads 0 flagged
rather than 2. The contract chose the median so that "one bad station does not
carry the window", and here that is not a hypothetical.

**The other two counts are unavailable for this window, and that is my defect.**
The capture filtered on `hasFlags` and on `observedCount` without counting what it
removed. A gate that filters without counting cannot report whether it ever fired,
which is the exact question the pre-commitment exists to answer. The capture
script now tallies rows returned, retained, and removed by each condition
separately, with a test requiring returned to equal retained plus every named
removal reason so an unnamed one cannot hide. The holdout capture will carry all
three figures. **For the control window, two of the three are lost and cannot be
recovered without re-running acquisition, which I am not doing after having seen a
rate.**

**What can still be said, and what cannot.** Every one of the 4031 retained rows
carries `observedCount == 1`. The contract's hypothesis was that the frozen
validity gate may be inert over this population, and this is consistent with it
but does not establish it, because the rows the gate removed were never counted.
The holdout will answer it.

### The construction breakdown has an empty arm, which supersedes the T2 confound

T2 recorded that the required provider-hourly against computed-mean breakdown was
fully confounded with city, because CPCB was the only multi-sample network found
and the computed-mean arm was therefore Delhi and nothing else.

That is now too generous. **All 4031 retained rows are `PROVIDER_HOURLY`, including
all 2037 Delhi rows.** Every CPCB hour in this window returned `observedCount` of
1. The computed-mean arm is not Delhi-only; it is **empty**. The required
breakdown cannot be produced at all over this window, and the finding is not that
one arm is a single city but that one arm has no members.

Whether the holdout week differs is not known and is not assumed. Recorded here
because it changes what the T2 paragraph should be read to mean, and because
discovering at the end that a required output has no second arm would be worse
than saying so now.

## What the 0 against 83 split actually is, diagnosed on the control window

Recorded 2026-08-04, before the holdout is opened. Diagnosis of the apparatus over
the control window, which is what a control window is for. It moves nothing.

Madrid at 0 of 156 is not a low rate, it is never. Delhi and New York above 82
percent are not high rates, they are almost always. Total separation is a
signature rather than a result, and it has now been diagnosed by reporting the
distribution of `|O - M|` against the distribution of `T(O)` for each city.

| city | n | `\|O-M\|` q1 / med / q3 / max | `T` q1 / med / q3 / max | station med | model med | ratio med | ratio max |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| Delhi | 162 | 15.5 / 26.7 / 96.2 / 190.7 | 11.3 / 12.9 / 14.3 / 23.9 | 14.8 | 40.1 | 2.47 | 15.79 |
| New York | 168 | 9.8 / 15.9 / 27.7 / 98.3 | 9.0 / 9.0 / 9.0 / 9.0 | 0.0 | 15.9 | 1.77 | 10.92 |
| Madrid | 156 | 1.2 / 2.7 / 4.0 / 13.7 | 9.5 / 9.9 / 10.6 / 16.1 | 6.5 | 5.3 | 0.26 | 0.92 |

**Madrid: the cause is the tolerance, not the model.** Its largest observed
difference across the whole week reaches 0.92 of its own tolerance and never
crosses it. Madrid's concentrations are low, station median 6.5 and model median
5.3, so `T` sits essentially at its floor of about 9.9. A flag at Madrid would
require the two sources to differ by more than 1.5 times the entire measured
concentration. The 0 percent is not evidence that the 11 km model agrees with
Madrid. It is evidence that at Madrid's concentrations almost no disagreement is
expressible.

**Delhi: genuine and large divergence.** Station median 14.8 against model median
40.1, with `|O - M|` routinely two to seven times its own tolerance and a maximum
of 190.7. This is the one city of three where the flag rate is measuring what the
project set out to measure.

**New York: not disagreement at all, and this was not anticipated.** Its `T` is
exactly 9.0 at every one of 168 hours, which is the floor and means the city value
is at or near zero throughout. Three of its four contributing stations report
median values of 0.03, 0.02 and 0.04 micrograms per cubic metre across the full
week. Those are not plausible urban PM2.5 concentrations; they are below any real
detection limit. The fourth station, 971, reports a median of 9.70, which is
plausible. The median of four then lands at about 0.03, because three of the four
carry it.

So New York's 82.7 percent measures three stations reporting essentially zero
against a model reading about 16, and it is a station data quality finding wearing
a disagreement rate's clothing.

**The pooled 56.4 percent is therefore a composite of three unlike things:** one
city where the tolerance cannot fire, one city where implausible station values
force flags, and one city with real divergence. It should not be quoted as a
disagreement rate without all three beside it.

**And the median rule's limit is now visible from the other side.** In Madrid it
absorbed one bad station in three, exactly as the contract intended. In New York
it cannot, because three of four stations carry the fault, and a median follows
the majority. **The median tolerates a minority of bad stations and adopts a
majority of them.** The frozen rule is correct and its protection is bounded, and
the bound was reached in this run.

Nothing here moves a predicate. The tolerance, its constants, the median rule, the
minimum coverage and the band are all as frozen.

## Applying a European regulatory criterion unchanged across an order of magnitude

Recorded before the holdout, so it cannot look assembled afterwards.

The Modelling Quality Objective widens with concentration by design, and the
contract records why: a proportional bar over-flags at low concentration and a
flat absolute bar barely flags there, so the published form blends the two and
anchors at a reference value of 25. That reasoning is sound for the setting it was
derived in, which is European regulatory air quality assessment.

This project applies it unchanged to cities whose PM2.5 differs by an order of
magnitude. The consequence is now measured rather than argued: **the same frozen
threshold is simultaneously too loose at low concentrations and too tight at high
ones, in different cities, in the same run.** At Madrid it is so loose that
disagreement is not expressible, with the largest difference of the week at 0.92
of tolerance. At Delhi it is exceeded by a median factor of 2.47 and a maximum of
15.79, so nearly everything flags and the rate carries no information about which
hours disagreed worst.

**The pre-registered prediction named both pressures and did not anticipate both
being true at once.** It recorded a downward pressure, that `T`'s floor of 9.0
would exceed typical departures and drive the rate below 1 percent, and an upward
pressure from representativeness mismatch inflating measured differences. It then
said which dominates is not predicted. What has happened is neither: the downward
pressure dominates completely in one city and the upward pressure dominates
completely in another, and the pooled rate is an average of a floor effect and a
ceiling effect rather than a measurement of anything in between.

That is a finding about applying a European regulatory criterion unchanged to
Delhi and to Madrid, and it is more useful than any flag rate this project will
produce. It is also not a reason to change the criterion, which is frozen, and it
is recorded before the holdout precisely so that it cannot be read as an
explanation constructed after seeing which way the holdout fell.

## The construction breakdown, and the third sample-of-one generalisation

T2 recorded that the required provider-hourly against computed-mean breakdown was
fully confounded with city, because every EEA, AirNow and Japanese station sampled
reported `observedCount` of one and CPCB was the only multi-sample network found.
The computed-mean arm was therefore Delhi and nothing else.

**All 2037 Delhi rows across the full control week return `observedCount` of one.**
The computed-mean arm is not a single city; it has no members. The T2 confound is
therefore moot rather than mitigated: there is nothing to confound, because the
breakdown cannot be produced at all over this population. Both records are kept in
sequence, as with the per-domain confound, because when each became visible is
part of the evidence.

**Name the pattern, because it is now three.** Three separate properties of the
station population were each established from one sensor or one city, generalised
to the whole, and each turned out not to describe it:

* **completeness**, from one unnamed Berlin sensor at 18 hours of 42, generalised
  to 208 sensors across eight cities. Twenty-seven contribute;
* **endpoint capability**, from one sensor per city, generalised to mean that
  admitted sensors would serve the capture window. 181 of 208 serve nothing;
* **construction classification**, from a sample identifying CPCB as the only
  multi-sample network, generalised to a breakdown arm. That arm is empty.

The common form is not carelessness in any one case. It is that a property was
verified where it was cheap to verify and assumed where it was not, and the
pre-flight recorded the verification without recording the assumption beside it.
A single instance establishes that a thing can happen, never how often.

## The sentinel is a limit, not a repair

Two values of `-998.0` from Madrid station 4331, at two separate hours, passed both
frozen validity conditions: `hasFlags` false and `observedCount` one.

**The median absorbed them.** Madrid contributes exactly three stations, so a mean
would have driven the city value to about -330 for those hours and flagged both.
The median took the middle value and neither hour was distorted. The contract chose
the median so that one bad station does not carry the window, and that is now
demonstrated by an event rather than argued from a hypothetical.

**What it exposes, and nothing follows from it.** The frozen validity rule does not
detect a sentinel. It delegates validity to the provider's own quality flag, which
is a deliberate choice recorded in the contract and defended there on the grounds
that inventing a cutoff would substitute this project's judgement for a cited one.
That choice has a cost and the cost is now visible: a value no instrument could
produce is admitted as a measurement. A city with more stations and more sentinels
could move a median, since the median's protection is bounded by the fault being
in a minority, which New York's near-zero stations have already shown can fail.

**Nothing changes.** `hasFlags` and `observedCount` stay exactly as frozen. No
sentinel filter is added, no plausibility bound is introduced, and no value is
excluded. The sentinel is reported in the negatives count with its magnitude, which
is where the contract's pre-committed reporting obligation puts it. Adding a filter
now would be an observation moving a frozen rule, and it would be doing so on the
strength of two hours.

## APPARATUS FAULT: the instrument was reading the wrong sensors entirely

Written 2026-08-04, **before any repair**, per the contract's rule. This blocks the
control run. It is a defect and not a finding, and it voids the measurement.

**What was found.** A diagnostic on the four New York stations, demanded before the
holdout was opened, resolved each admitted location to its own sensor list:

| our "station" | location name | its actual PM2.5 sensor | what `/sensors/{that id}` really is |
| --- | --- | ---: | --- |
| 857 | Fort Lee Near Road | 1534 | **`o3`, ppm** |
| 928 | Jersey City FH | 5077566 | **`o3`, ppm** |
| 971 | Elizabeth Trailer | 1758 | `pm25`, µg/m³ (a different station's) |

**Three of the four New York stations were reading ozone in parts per million and
recording it as PM2.5 in micrograms per cubic metre.** Urban ozone runs about 0.02
to 0.05 ppm, which is exactly the 0.03, 0.02 and 0.04 "implausible PM2.5 medians"
diagnosed an hour ago as a station data quality finding. They were not implausible
PM2.5. They were entirely plausible ozone.

**The root cause.** The admission artifact correctly stores **location** ids, under
a key correctly named `sensor_location_ids`. `admitted_sensors()` at
`src/climate_index/adapters/openaq/admission.py:74` assigns that location id to a
field named `sensor_id`, with a docstring stating that the sensor identifier "is
resolved by the adapter at fetch time". **Nothing resolves it.** The shipped
adapter uses it directly at `src/climate_index/adapters/openaq/source.py:240`, and
`scripts/capture_window.py` copied that. Location ids and sensor ids are different
id spaces that overlap numerically, so a location id used as a sensor id either
404s or silently returns a completely unrelated sensor, of any parameter, at any
site.

This is not a capture-script bug. **It is a defect in code shipped in T2**, and the
docstring describing the resolution step is a description of something that was
never written.

**Every quantitative claim made from this capture is void.** Retracted in full, and
struck rather than deleted:

* the control-window rate of 56.4 percent, and the per-city rates of 83.3, 82.7 and
  0.0 percent;
* the 486 covered city-windows and the 274 flagged, and every count derived from
  them, including the weaker-condition 146 of 486;
* **contract defect six**, that admission's `datetimeFirst`/`datetimeLast` premise
  is false. The 181 of 208 sensors "serving nothing" were location ids that are not
  sensor ids. The contract's premise has not been tested and that defect is
  withdrawn;
* the 27-of-208 contributing figure and the whole "208 admitted, 27 contributing"
  framing;
* the per-domain confound as measured, the three-city-weeks independence limit as
  measured, and the Madrid single-point-of-failure arithmetic, all of which rested
  on which cities appeared covered;
* the empty construction arm, since `observedCount` of 1 was read off the wrong
  sensors;
* the New York near-zero station finding, which was ozone;
* the `-998.0` Madrid sentinel finding and the median-absorbed-it demonstration.
  Whatever sensor 4331 is, it is not the PM2.5 sensor of that location.

**What survives.** The freeze, which the pin still proves. The guards, the seeded
violations, AT-13, and the successor control, none of which depend on these values.
The capture and reconciliation apparatus, which did faithfully what it was told to
do with the identifiers it was given. And the seal: **the holdout was not opened,
which is the entire reason this was recoverable.**

**Why the pattern paragraph now reads differently.** Three sample-of-one
generalisations were recorded as a pattern. Two of the three, endpoint capability
and construction classification, were themselves artifacts of this fault. The
Berlin completeness one may stand. The pattern as stated is withdrawn along with
its instances, and what replaces it is narrower and worse: **a field named
`sensor_id` held a location id for the whole of T2, was documented as being
resolved elsewhere, was never resolved, and no test compared an identifier against
the entity it was supposed to name.**

**The repair, not yet made.** Resolve each admitted location to its PM2.5 sensor id
through `/v3/locations/{id}`, selecting the sensor whose `parameter.name` is
`pm25`, and assert the parameter and units of every sensor actually queried. The
assertion matters more than the lookup: this fault produced values that were
individually plausible and only became visible when someone asked what the numbers
were of.

**Re-run accounting.** Under the contract's rule this is an apparatus fault
requiring a diagnosed repair and a re-run of the control window. **One of the two
permitted re-runs is spent by this.** The counter is recorded here and in the
committed evidence, and the holdout still opens exactly once.

## What spends a re-run attempt, defined before the next one

Written 2026-08-04, **before the repair**, with one attempt remaining and before
knowing whether the repair will work. With two remaining this was academic. With
one it decides whether the project can complete, which is exactly why it is being
settled now rather than later in whichever direction suits the state.

**The counter counts reconciliation runs over a captured window.** A reconciliation
run is an execution of `scripts/reconcile.py` that produces a rate. Captures,
metadata probes and verification fetches are **inputs** to a run and do not
increment it.

The reasoning, and it is the owner's, offered before the outcome was known: this
reading is the one that makes a small verification fetch possible, and it was
stated in advance of knowing whether that verification would pass. The alternative
reading, where any contact with the provider spends an attempt, would make it
rational to skip verification and spend the last attempt on hope, which is the
opposite of what the cap exists to encourage.

What the cap protects against is re-running a **measurement** until it gives an
agreeable answer. A capture retrieves data without computing a rate; a metadata
probe reads no measurement at all. Neither can produce a number to be disagreeable
about, so neither is what the cap is for.

**Spent: 1. Remaining: 1.** Recorded in
`docs/evidence/control-window/rerun-counter.json`. The holdout still opens exactly
once.

## The identifier sweep, and the defect class no gate here was pointed at

An identifier's name is a claim about what it identifies. **No test in this
repository has ever checked a claim of that kind**, and the fault above is what
that costs: a value that is type-correct, range-plausible and semantically wrong.
Ozone at 0.03 ppm passes every check this project owns except the one nobody
wrote, which is "is this a PM2.5 measurement".

Every field whose name asserts an entity type was checked:

| field | holds | verdict |
| --- | --- | --- |
| `AdmittedSensor.sensor_id` | an OpenAQ **location** id | **the fault**, repaired below |
| `AdmittedSensor.station_id` | an OpenAQ location id | **correct**, see below |
| `StationObservation.station_id` | the same location id | **correct** |
| `KafkaTransport.group_id` | a consumer group name | correct, not an entity reference |

The sweep found one instance and no others. `station_id` is correct for a
non-obvious reason worth writing down: in the OpenAQ model a **location is the
monitoring station**, so a location id is the right value for a field named
`station_id`. The same integer is correct in one field and wrong in the other,
which is precisely why reading the code did not reveal it and why only asking the
provider what the entity was could.

**The general form, for the record.** Type checking proves a value is an `int`.
Range checking proves it is plausible. Neither proves it names the thing its field
says it names, and a system that resolves identifiers against a remote API can be
wholly type-correct and still be reading another entity entirely. The check that
catches this is semantic and has to be made against the source of truth: ask what
the identifier resolves to, and assert the answer.

## What 208 counts, stated precisely rather than voided

The admission artifact is **not wrong**. It stores location ids under a key
correctly named `sensor_location_ids`, and its funnel counts are counts of
locations.

So, exactly: **208 is the number of monitoring locations meeting the frozen
admission criteria** across eight cities. That figure stands and is untouched by
this fault.

**How many of those 208 resolve to a PM2.5 sensor that serves the capture window
is unknown and untested.** It was never measured, because what was measured was
whatever entity happened to share each location's integer. That is also why
contract defect six is **withdrawn rather than inverted**: the claim that
`datetimeFirst` and `datetimeLast` fail to predict hourly coverage may be true or
false, and this project has produced no evidence either way.

**Which sample-of-one generalisation survives.** Of the three recorded:

* **completeness**, from one unnamed Berlin sensor at 18 hours of 42, generalised
  to the whole population. **This one survives.** It is drawn from the pre-flight,
  not from the faulty capture, and it remains a single unnamed sensor standing in
  for 208 locations. It is also still not reproducible, because the sensor was
  never named.
* **endpoint capability**, that admitted sensors would serve the window.
  **Withdrawn**: an artifact of this fault.
* **construction classification**, the empty computed-mean arm. **Withdrawn**:
  `observedCount` was read off the wrong sensors.

One of three survives, and the pattern is not a pattern on one instance. What
replaces it is the identifier claim above, which is a different and sharper thing.

## The repair, and the small verification that precedes the last attempt

Recorded 2026-08-04. No reconciliation run was spent on any of this, per the
definition pinned above: captures and metadata probes are inputs.

**The repair.** `admitted_sensors` becomes `admitted_locations` and returns an
`AdmittedLocation` carrying `location_id`, `station_id` and a `pm25_sensor_id`
that is `None` until resolved. `resolve_pm25_sensor` reads
`/v3/locations/{id}`, selects the sensor whose `parameter.name` is `pm25`, and
`check_pm25_sensor` asserts both the parameter name and the units before returning
its id. A location offering no PM2.5 sensor is refused by name rather than having
its first sensor returned. The hours query refuses outright when
`pm25_sensor_id` is `None`, so skipping resolution is impossible rather than
merely wrong.

**The assertion is the repair; the lookup is plumbing.** `tests/unit/test_sensor_identity.py`
seeds the violation with the two real sensors the diagnostic found: location 857
resolves to 1534 and never to 857, and pointed at what `/sensors/857` actually
serves the resolver refuses with "location 857 has no pm25 sensor; it offers
['o3']". A pm25 sensor reporting ppm is refused too, which is the same class of
fault one level down.

**The small verification, two locations per city, before any full capture.**

| city | location | resolved sensor | parameter | hours | median |
| --- | ---: | ---: | --- | ---: | ---: |
| New York | 384 | 673 | pm25/µg/m³ | 165 | 10.40 |
| New York | 625 | 1097 | pm25/µg/m³ | 166 | 6.05 |
| Delhi | 17 | 35 | pm25/µg/m³ | 0 | no hours |
| Delhi | 50 | 396 | pm25/µg/m³ | 0 | no hours |
| Madrid | 4274 | 10378 | pm25/µg/m³ | 68 | 9.00 |
| Madrid | 4275 | 10382 | pm25/µg/m³ | 67 | 11.00 |
| Tokyo | 1214487 | 6518561 | pm25/µg/m³ | 153 | 12.00 |
| Tokyo | 1214508 | 6516165 | pm25/µg/m³ | 147 | 10.00 |
| Berlin | 2993 | 1300115 | pm25/µg/m³ | 138 | 6.79 |
| Berlin | 3019 | 1300119 | pm25/µg/m³ | 138 | 6.90 |
| Los Angeles | 1948 | 25551 | pm25/µg/m³ | 168 | 10.45 |
| Los Angeles | 7936 | 25196 | pm25/µg/m³ | 69 | 8.70 |

Every location resolved, every resolved sensor is `pm25` in µg/m³, and every
median is a plausible urban PM2.5 concentration. New York reads 10.40 and 6.05
where the faulty apparatus read 0.03 and 0.02, which was ozone.

**And Tokyo and Los Angeles serve.** Both were reported as returning nothing at
all, and that observation was the whole basis of the withdrawn contract defect
six. Tokyo location 1214487 serves 153 hours of the control window and Los Angeles
1948 serves 168. The withdrawal was correct and is now positively confirmed rather
than merely prudent: the contract's admission premise was never tested, and the
first evidence about it points the other way.

Delhi's two sampled locations serve no hours, which is now a real observation
about those two locations rather than an artifact. What it means for Delhi overall
is not inferred from two.

The instrument is verified. The last permitted reconciliation run will be made
over a capture taken with it.

## Capture attempt 3, voided: periods anchored off the hour

Diagnosed 2026-08-04, before repair. The repaired instrument ran to completion and
then refused at the window assertion: 21 rows fell outside
`[2026-07-17T00:00Z, 2026-07-24T00:00Z)`, the first at `2026-07-16T23:30:00Z`.
Nothing was kept.

**That is a half-hour boundary.** Three known-good sensors were checked directly,
Berlin 1300115, New York 673 and Tokyo 6518561, and all three return
`label='1hour'`, `interval='01:00:00'`, `from=…T00:00:00Z to=…T01:00:00Z`, with
zero off-hour rows. A minority of sensors report hourly rollups anchored at `:30`,
and the provider returns one when its period overlaps the requested start.

### Why rejecting them applies the frozen rule rather than extending it

This distinction carries the whole decision, and without it the change reads
exactly like a validity rule added after seeing the data.

`hasFlags == false` and `observedCount >= 1` are **admissibility** filters. They
select among rows that **are** hours. The frozen temporal alignment is a different
kind of statement: it quantifies over the half-open hour `[H, H+1)` and pairs the
two sources **on H**. A period of `[23:30, 00:30)` is not `[H, H+1)` for any
integer `H`. It is not the thing the rule quantifies over, and there is no `H` to
pair it with, because the model side has values only on the hour. **The rule
defines no comparison for such a period.** Rejecting it is applying the rule. It
is not a new gate.

**The alternative, and why it is refused.** A row anchored at `:30` could be
assigned to the nearest `H`. That would invent an alignment convention the
contract does not contain, after seeing the data, and in the direction that
**retains rows** and therefore helps D2's evaluability. That direction is the
whole reason it cannot be taken. The contract's alignment is explicit and it is
not this project's to extend when extending it would be convenient.

### The end boundary is what actually matters here

The first offending row was `2026-07-16T23:30:00Z`, before the window start, which
looks like a tidiness problem. **The same anchoring at the other end produces a
period `[2026-07-23T23:30Z, 2026-07-24T00:30Z)`, which contains thirty minutes of
holdout time.**

Had off-hour periods been kept, a control capture would have imported holdout
minutes through a rounding convention nobody wrote down, and no declaration
anywhere would have said so. **Rejecting non-hour-aligned periods is therefore
part of what keeps the seal intact at the boundary**, not housekeeping.

It is worth being plain about how narrowly this was caught. The realized-bounds
assertion is what refused, and it exists only because it was added when the
capture artifact was designed. The declared-window check alone would have passed:
the run asked for the control window and was labelled the control window. Only
comparing what actually landed against the window caught it.

### The exclusion is reported per sensor and per city

Sensors so a reader can re-query them, and cities because the
confound-in-the-population risk has now bitten twice. If the `:30`-anchored
sensors sit mostly in one city, the exclusion changes that city's coverage and
could remove it from the comparison entirely, which is a fact about the population
and not about the rule. The capture artifact now carries
`period_not_hour_aligned` with total rows, a per-station breakdown and a per-city
fold, and the per-city coverage figures are reported before and after the
exclusion.

### A stopping condition for capture voids, stated as mine and not the contract's

The contract caps **reconciliation runs**, not captures, and the definition pinned
above makes captures inputs. Nothing in the contract therefore stops a
re-capture-until-it-works pattern, and an uncapped loop is worth closing before it
becomes one.

**This is operational discipline I am adopting, not a contract provision.** Every
capture void carries a diagnosed cause written before its repair, which is what
distinguishes the two so far: attempt 1 was a doubled version segment, attempt 2
was periods anchored off the hour. **At a third void I stop and reassess rather
than re-capture**, and reassessing means reporting the three diagnoses and asking
whether the instrument can be trusted at all, not adjusting one more thing and
trying again.

Spent so far: 0 reconciliation runs of the 1 remaining. Capture voids: 2, both
diagnosed.

## Capture attempt 4: the clean capture, and everything re-derived from it

Recorded 2026-08-06. Nothing in this section is carried across the void boundary;
every figure is re-derived from the capture at
`docs/evidence/capture/2026-08-06-control.json`. No comparison has been computed.

**Resolution.** 208 locations admitted, 208 resolved to a PM2.5 sensor, 0 refused.
The prediction that the new bracket rule would refuse some locations was wrong:
once dead sensors are excluded, each location has exactly one PM2.5 sensor
covering the window, so neither `none_covering_window` nor
`ambiguous_multiple_covering` fired.

**Gate.** 30868 rows returned, 24409 retained, 6459 rejected as
`period_not_hour_aligned`, and the per-city fold is `{"Delhi": 6459}`. The
exclusion is not spread across cities: **every excluded row is Delhi and no other
city loses one**. `hasFlags` and `observedCount` removed nothing, so the
contract's pre-committed question about whether the frozen validity gate is inert
over this population is answered by count rather than by inference: it never
fired.

**Uniqueness.** 24409 station-hours, 0 duplicated. **Bounds.** Both sources
`2026-07-17T00:00:00Z` to `2026-07-23T23:00:00Z`, an hour clear of the boundary.

| city | stations | rows | hours | median | min | max | qualifying |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Amsterdam | 5 | 749 | 156 | 5.60 | 0.3 | 173.0 | 156 |
| Berlin | 7 | 965 | 138 | 8.03 | 2.3 | 24.9 | 138 |
| Chicago | 8 | 1342 | 168 | 16.45 | 1.8 | 538.0 | 168 |
| Los Angeles | 6 | 904 | 168 | 11.10 | -1.0 | 31.0 | 168 |
| Madrid | 6 | 401 | 69 | 11.00 | -1.0 | 37.0 | 68 |
| New York | 15 | 2430 | 168 | 8.90 | -9.1 | 177.0 | 168 |
| Tokyo | 119 | 17618 | 154 | 11.00 | 0.0 | 253.0 | 154 |
| **total** | | | | | | | **1020** |

Every median is a plausible urban PM2.5 concentration. Nothing reads like ozone.

## A national monitoring network the frozen alignment cannot express

Recorded before the reconciliation run, as a finding rather than as attrition.

Delhi is excluded from the measurement. Its 42 admitted locations resolve to live
PM2.5 sensors that serve the control week and a recent week through
`/v3/sensors/{id}/hours`, the endpoint the contract names. Their hourly periods
are anchored at `:30`.

**The mechanism, plainly.** `[23:30, 00:30)` is not `[H, H+1)` for any integer
`H`. The model side has values only on the hour. There is therefore nothing to
pair a `:30`-anchored station hour with, and the frozen alignment defines no
comparison for it.

**This is not a defect in CPCB and not a defect in the rule.** It is a mismatch
between two conventions, and it is visible only because one of them was frozen in
advance and applied without adjustment. A European regulatory alignment convention
cannot express an entire national monitoring network's hourly data. That is a
stronger and more transferable result than any flag rate this project will
produce, and it is the temporal sibling of the tolerance behaving differently at
Delhi's concentrations than at Madrid's: the same frozen document meeting the same
country and failing to fit it, once on the value axis and once on the time axis.

**Recorded at city level, because the state machine cannot hold the distinction.**
Delhi and Lagos both end UNCHECKED and they are not the same fact. Lagos has no
reference-grade PM2.5 station. Delhi has forty-two locations serving data whose
periods the contract cannot express. The capture artifact now carries
`city_exclusion_reasons` distinguishing the two, because a reader who sees only
UNCHECKED learns the wrong thing about Delhi.

**The exclusion improves a required breakdown, and that is a consequence and not a
reason.** Removing Delhi leaves the per-domain breakdown as CAMS Europe with three
cities and 362 qualifying city-windows against CAMS global with four cities and
658. The confound recorded before the void run, when the faulty capture left
Madrid as the only European city, was total: the 11 km arm was one city. It is now
a real if uneven comparison, and the paragraph recording it as total confounding
is superseded rather than restated. **Stated in these words because an improvement
that arrives unremarked is what an auditor looks for**, and it is the same
disclosure the contract made about beta = 2 also being the choice more likely to
land inside the band. Delhi is excluded because the alignment rule says so. That
the exclusion happens to strengthen a required output is a fact about the
consequence, not a reason for the decision, and the decision was taken and
recorded before this breakdown was computed.

## Defect seven: admission is stricter than the rule it implements

Recorded 2026-08-06.

**What was checked, and what it was not.** The question asked was whether
admission bracketed on the location or on the sensor. It bracketed on the
**sensor**, as the contract requires:
`scripts/recompute_station_admission.py` queries `/v3/locations/{id}/sensors` and
reads each sensor's own `datetimeFirst` and `datetimeLast`. **There is no defect
of the kind that was hypothesised**, and the conditional is recorded as not firing
rather than quietly dropped.

**The defect that is there.** The loop examines the **first** PM2.5 sensor at each
location and then `break`s unconditionally. A location whose first-listed PM2.5
sensor does not bracket the window is rejected even when a second one does. The
frozen rule admits a station when its PM2.5 sensor brackets the window; the code
admits it when its *first-listed* PM2.5 sensor does. **The code is stricter than
the frozen rule**, and it is the first defect found in code implementing a frozen
rule rather than in the contract itself.

**Ordering is not stable over time.** Location 50 carries two PM2.5 sensors, one
dead since 2018. On 2026-08-04 a probe listed the dead one first; on 2026-08-06
six consecutive calls list the live one first. Claimed narrowly: variation
observed on `/v3/locations/{id}` between two probes two days apart, and nothing
established either way about `/v3/locations/{id}/sensors`. It is enough to make
"take the first match" unsafe, which is why the repaired resolver refuses to
choose rather than picking.

**The repair is required in principle and is not available.** By the
validity-repair principle a change moving **code** toward what was **frozen** is
required, and a change moving the **declaration** toward a wanted result is
forbidden. This is the first kind. That fixing it would **enlarge** the population
and help D2's precondition is not a reason either way; that is what "never on
effect" means, and it is the identical reasoning applied to the resolver
tightening, which **reduced** the population and made the precondition **harder**
to clear. If the direction of the effect could argue for one repair it could argue
against the other.

It is unavailable because one reconciliation run remains, and a corrected admitted
set requires a new artifact, a new capture and a new run. **The budget is the
reason the defect is unfixed. It is not the reason the defect is acceptable.** The
measurement is taken over a population that under-counts the frozen rule's
admissible set.

**The shortfall is measured, not carried as an unknown.** All 80 non-admitted
locations with a PM2.5 sensor were queried: those with a second PM2.5 sensor whose
own dates bracket the window while the first does not. Metadata only, no
comparison.

| city | candidates examined | recovered by a later sensor |
| --- | ---: | ---: |
| Delhi | 39 | **6** |
| Tokyo | 9 | 0 |
| Nairobi | 9 | 0 |
| Jakarta | 7 | 0 |
| Los Angeles | 6 | 0 |
| New York | 4 | 0 |
| Berlin, Chicago | 2 each | 0 |
| Lagos, Cairo | 1 each | 0 |
| Amsterdam, Madrid | 0 | 0 |
| **total** | **80** | **6** |

**Six locations, all of them in Delhi.** The under-count is bounded at six, and
because Delhi is excluded from the measurement by the alignment rule regardless,
those six would have contributed nothing. **The defect is real, measured, and
inert for this measurement.** That is a materially different statement from "an
under-count by an unknown amount", and it is the fourth exclusion in this project
to turn out concentrated in a single city rather than spread.

**Two dated artifacts that disagree, with the reason written.** The pinned
admission artifact stays exactly as it is, the dated record of what admission
produced on 2026-08-03. The capture artifact records what resolved under the
frozen rule. Neither is corrected into agreement with the other, because a
quietly reconciled pair of records is worth less than a disagreeing pair whose
reason is written down.

## Before the last control run: two things settled while they are uncontested

Written 2026-08-06, **before the run**, for the same reason the definition of what
spends an attempt was written before the repair: settling a question afterwards,
in whichever direction the state you are in requires, is not settling it.

### If this run faults, the project ships "the measurement could not be completed"

That is the contract's pre-registered outcome and it is **acceptable**. Said out
loud now, before the run, so that if it happens nobody starts looking for a fourth
attempt or for a reason this fault is different from the others.

The two diagnosed capture voids and the diagnosed apparatus fault ship with it, and
that is a **complete and honest result**, not a failure to produce one. A project
that reports what its instrument could and could not do, with each fault diagnosed
in writing before its repair, has produced evidence. A project that keeps adjusting
until a number appears has produced a number.

### The counter does not constrain the holdout run, and the holdout has none

The contract caps re-runs of **the control window**. The holdout is governed by a
different clause entirely: it opens **exactly once, regardless**.

So the re-run allowance does not transfer. **The holdout run carries no re-run
allowance at all. Not two, not one. Zero.** One attempt, and an apparatus fault
there is not recoverable by re-running, because re-running is precisely what "opens
exactly once" forbids.

Two consequences worth stating now rather than discovering later. Whatever remains
of the control-window allowance after this run is **spent or unspent, and either
way irrelevant to the holdout**; a leftover attempt is not a credit. And the
verification discipline built for this run matters more there than here, because
here a fault could be diagnosed and repaired, and there it cannot. Everything that
can be checked about the holdout capture must be checked before the holdout
reconciliation is executed, since there is no second execution to fall back on.

## The control-window run: the rate, and the freeze proved after it

Recorded 2026-08-06. **An apparatus check and not a result.** The control window is
not the holdout, so D2's 1 to 33 band and its 200 city-window precondition apply to
none of what follows.

**The run completed with no apparatus fault.** The last permitted control-window
reconciliation was executed once and returned exit 0.

### The numbers

| | covered city-windows | flagged | rate |
| --- | ---: | ---: | ---: |
| **pooled** | **1020** | **109** | **10.7%** |
| Tokyo (global) | 154 | 58 | 37.7% |
| New York (global) | 168 | 29 | 17.3% |
| Los Angeles (global) | 168 | 11 | 6.5% |
| Chicago (global) | 168 | 9 | 5.4% |
| Madrid (Europe) | 68 | 2 | 2.9% |
| Berlin (Europe) | 138 | 0 | 0.0% |
| Amsterdam (Europe) | 156 | 0 | 0.0% |

Region-windows: 672, of which 484 STATION_CHECKED and 188 UNCHECKED; by state, 377
AGREED, 107 DISAGREED, 188 NOT_COMPARED. The covered count of 1020 agreed across
both derivations.

**The union rule now unions.** 109 flagged city-windows produce 107 DISAGREED
region-windows, so two region-windows carry two flagged cities each. In the voided
run no region had more than one covered city and the union rule was inert; it is
not inert here.

**Per domain:** CAMS Europe, three cities, **2 of 362, 0.55%**. CAMS global, four
cities, **107 of 658, 16.26%**. The contrast survives the repair and is no longer
total: the voided run showed 0 against 83 with one European city, and this shows
0.55 against 16.26 across three against four. The confound recorded before that
run is weakened but not gone, and no reading of these two arms separates grid
resolution from which cities sit in each.

**The weaker condition**, reported as evidence with no claim bound to it: of 1020
covered city-windows, 633 satisfy `|Oi - Mi| <= U(Oi)` and 387 do not.

### Nothing moved, and the proof is run after the number

Executed at `2026-08-06T17:47:06Z`, with the rate above already on screen:

```
$ git log --format=%H -- PREREGISTRATION.md
b81f1c97ae1a7e69918d918d5636318f57aee791

$ git log --format='%h %ci' -1 -- PREREGISTRATION.md
b81f1c9 2026-08-02 20:25:16 +0000

$ pytest tests/hygiene/test_settings_match_contract.py
7 passed
```

One commit, dated four days before this run, and the settings still match sections
4.1 and 5 of the document at that commit. T, beta at 2, alpha at 0.50, `Ur(RV)` at
0.36, `RV` at 25, the minimum coverage of 3, the median rule, the union rule, the 1
to 33 band and the 200 precondition are all exactly as frozen. **No predicate moved
after the number was seen.**

The paragraph committed at `97d59e8`, before any capture existed, stands unchanged:
the holdout opens exactly once regardless of what the control window showed, and
this rate is not admissible as a reason to skip, shorten or reframe the D2
evaluation. A pooled 10.7 percent happens to sit inside the 1 to 33 band. **That is
not a reason to expect anything of the holdout and not a reason to do anything
differently**, and the fact that it is a more comfortable number than the voided
run's 56.4 percent is precisely why the paragraph was written before either existed.

### What this run does and does not establish

It establishes that the apparatus completes: it resolves sensors and asserts what
they measure, applies the frozen alignment, coverage, median and union rules, and
produces per-city and per-domain figures with its denominator checked twice.

It establishes nothing about D2, which binds on the holdout alone.

The limits recorded before the run stand and are not restated here as though the
number changed them. The clustering limit now reads over seven city-weeks rather
than three, which is a larger effective sample than the voided run had and still far
short of 1020 independent observations.

**Reconciliation runs: 1 of 1 spent. None remain.** Capture voids: 2, both
diagnosed. The holdout is unopened and carries no re-run allowance of its own.

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
7. **Two mypy configurations disagree, and only one of them runs in CI's gate.**
   `make type-check` runs mypy in the project virtual environment, where `httpx`
   ships type information. The pre-commit hook runs it in an isolated environment
   carrying only pydantic, where `httpx` is untyped. A `ModuleType` annotation on
   the lazy import passed the first and failed the second with a
   `no-any-return`. The resolution taken is to match the Open-Meteo adapter's
   `Any` annotation rather than to widen the hook's dependencies, since the hook's
   isolation is the property that makes it cheap. Recorded because it is the same
   family as finding 6: a check whose result depends on which environment ran it,
   where the two can disagree silently until one of them happens to be the one
   that fails.

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
