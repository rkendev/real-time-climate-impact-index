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
