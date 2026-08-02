# OpenAQ disagreement grading: pre-registration

Pre-registered 2026-08-02, before any adapter, any schema change and any
comparison. This document is the contract. The claims, floors and ship rules
below are fixed before the first measurement, and results ship against them
unmodified. It reopens the Real-Time Climate Impact Index under the owner
self-override, which substitutes pre-registration discipline for demand-pull
discipline and is not a bypass. The same rule applies as everywhere else: a
failed or uninformative result ships as the headline.

The pre-flight in section 3 ran before this document was frozen and contradicted
three of the draft's own premises. Those corrections are recorded in place rather
than quietly absorbed. This file is self-sufficient on everything that determines
the threshold: a reader of this commit can reconstruct T completely without
reading any later commit.

This file is this repository's analogue of `CLAIMS.md` in ProofBench,
<https://github.com/rkendev/proofbench>, which is public and which applies the
same discipline. That cross-reference is the point rather than a courtesy: the
discipline produced a failed floor there, and it may produce one here.

## 1. What this project is

Add OpenAQ ground-station observations alongside the existing Open-Meteo air
quality analysis, which is served from the CAMS product, and use the relationship
between them to grade confidence.

The claim is not "a second air quality source". It is this:

> When an independent ground observation and a model analysis of **surface PM2.5
> mass concentration, in micrograms per cubic metre**, disagree beyond a
> threshold for a region-window, the index reports reduced confidence and both
> values, rather than picking a winner. Region-windows with no qualifying station
> coverage carry a documented lower provenance tier rather than a fabricated
> grade.

The quantity is named because a pre-registered claim that is ambiguous about what
it asserts is not pre-registered.

Today the confidence grader reads absence. The dead-host run proved that much:
with the air quality endpoint pointed at an unreachable host, twelve counted
skips dropped every region to INFERRED with no hand on the scale. It has never
read disagreement, and nothing else in the portfolio does either.

**The strongest thing this project will output is already known, and it is not
the flag rate.** The pre-flight established that AFR has no reference-grade
station reporting PM2.5 across the capture window near any of its three
configured cities, at every radius tested, and that Jakarta and Madrid have none
either. ADR-0007 called station coverage "sparse in AFR in particular". At the
grade this threshold requires, it is not sparse, it is absent. One of the index's
four regions will therefore carry the lower provenance tier permanently, because
it cannot be independently checked at all. That result lands in D3, it goes in
the README above any number that looks good, and it does not depend on how the
rest of the project turns out.

## 2. Scope

**In.** One OpenAQ adapter behind the existing source Protocol, selected through
the settings object. An extension of the existing Open-Meteo adapter to fetch
`pm2_5` alongside `aerosol_optical_depth`, because the model side of the
comparison does not exist today. A new field on `SatelliteEvent` carrying the
model PM2.5 value: this is a schema change, it propagates to the DuckDB column
tuple, the Iceberg schema, the DynamoDB item shape and the dashboard, and it is
**in scope**, so that it is not relitigated at implementation time. A
station-to-city mapping and a temporal alignment rule. A reconciliation rule that
computes disagreement per city-window. A separately named, PM2.5-scoped
disagreement state and a provenance tier. One new acceptance test, AT-13. One
ADR, 0009, recording the decision context.

**Out, and not negotiable inside this project.** Changing how `pollution_index`
is computed. Cross-source federation or joins. Any AWS run. Backfilling the
shipped index. Any dashboard work beyond rendering the new state in the existing
confidence strip. Changing the index formula. If any of these start to look
necessary, that is a finding to record, not a scope change to make.

**The disagreement state does not grade `pollution_index`.** `pollution_index` is
computed from `aerosol_optical_depth`, a dimensionless column-integrated
quantity. Grading it by PM2.5 disagreement would assert an aerosol-optical-depth
to surface-PM2.5 relationship that this project does not test and that is known
to be weak, because it turns on boundary layer height, aerosol vertical profile
and humidity. The state is therefore a separate, explicitly PM2.5-scoped field.
Disclosing the inference would have been weaker than not making it.

## 3. The pre-flight, completed before this document was frozen

Documentation and metadata reading only. No comparison computed, no repository
change, no spend. Its answers are recorded here rather than referenced, because a
pre-flight that is only cited cannot be checked.

**Q1. Does either source publish an uncertainty at usable granularity? No.**
OpenAQ exposes no uncertainty, detection limit, accuracy or instrument tolerance
field anywhere: not in `/v3/locations`, `/v3/sensors`, `/v3/instruments`,
`/v3/providers`, `/v3/owners` or the measurement resources. Open-Meteo publishes
no error bound and no ensemble spread. The CAMS regional product is the median of
eleven models and distributes no per-grid-cell uncertainty. Section 4 records
what was done instead.

**Q2. What is comparable?** Both sources serve surface PM2.5 mass concentration
in micrograms per cubic metre. Confirmed against live responses: OpenAQ parameter
id 2, name `pm25`, units micrograms per cubic metre; Open-Meteo `pm2_5`, same
unit, valid time Instant, close to surface. **The pipeline's current pollution
field is not that quantity.** It carries `aerosol_optical_depth`, which is
dimensionless and column-integrated. The abort rule in section 8 does not fire,
because it turns on whether the two sources measure a comparable quantity and
they do; it is the field the pipeline happens to carry that does not. Section 2
records the consequence.

**Q3. Station metadata surface.** Sufficient for the mapping rule, and richer
than expected in one respect and poorer in another. `/v3/locations` returns `id`,
`name`, `locality`, `timezone`, `country`, `owner`, `provider`, `isMobile`,
`isMonitor`, `instruments`, `sensors`, `coordinates`, `licenses`, `bounds`,
`distance`, `datetimeFirst`, `datetimeLast`, and the detail view adds nothing.
`isMonitor` is inherited from the instrument, which carries its own `isMonitor`
flag, so it does separate regulatory-grade monitors from low-cost sensors.
`/v3/sensors/{id}/hours` returns a half-open hour with `period.label` of `1hour`,
`flagInfo.hasFlags`, and `coverage.observedCount`, so the underlying sample count
is available. **No station classification exists anywhere in the API**, which
section 5 resolves.

**One finding that was not asked for and changes the spatial rule.** Only the
three EUR cities lie inside CAMS Europe, at 0.1 degrees, about 11 km. Requesting
`models=cams_europe` at any of the other nine returns "No data is available for
this location", so they are served by CAMS global at 0.4 degrees, about 45 km.
The returned coordinates snap to a 0.1 degree grid everywhere, which hides this.
The model's effective resolution is not uniform across the four regions.

## 4. The threshold, and why it is not a number picked blind

A threshold chosen blind can be wrong in two directions and neither is
recoverable after the fact. Too tight and every window flags, so the grade
carries no information. Too loose and nothing ever flags, so the feature is green
over an empty set and the test that guards it is vacuous. Moving the threshold
after seeing the data is an observation moving a pre-registration, which is
forbidden.

Deriving the threshold as a quantile of the observed disagreement is also
rejected. If T were the 90th percentile of the observed disagreement, then
roughly a tenth of the holdout would flag by construction, and D2 below would
become a gate that cannot go red. A gate satisfiable by construction is not a
gate.

The draft branched on whether either source publishes an uncertainty. Q1 answered
no, which would have sent this to a fixed physical value. Neither branch is
taken, because both get one end of the concentration range wrong. A flat relative
bar claims an uncertainty of 1 microgram per cubic metre at a station value of 4,
below what the instrument class resolves, and over-flags at low concentration. A
flat absolute bar applies the same tolerance at 4 and at 100, and barely flags at
the low end. The published answer to exactly that problem is a form that blends a
proportional and a non-proportional term anchored at a reference value.

### 4.1 The threshold

T is the Modelling Quality Objective, taken whole.

```
T(O) = beta * U(O)

U(O) = Ur(RV) * sqrt( (1 - a^2) * O^2 + a^2 * RV^2 )

  PM2.5:   Ur(RV) = 0.36     RV = 25 ug/m3     a = 0.50     beta = 2
```

`O` is the station value, following the guidance, in which `O_i` is the
measurement. `M` is the model value. A city-window is flagged when
`|O - M| > T(O)`.

The floor this produces is 9.0 ug/m3 as the station value approaches zero, and
about 11 at a station value of 10. At the reference value of 25 the tolerance is
18, and it widens with concentration from there.

### 4.2 The citation, pinned

Janssen, S., Thunis, P., *FAIRMODE Guidance Document on Modelling Quality
Objectives and Benchmarking* (version 3.3), EUR 31068 EN, Publications Office of
the European Union, Luxembourg, 2022, ISBN 978-92-76-52425-0, doi:10.2760/41988,
JRC129254. The version history in the document dates 3.3 to 15/02/2022.

In version 3.3 specifically:

- the form is **equation (37)**, ANNEX 1 MEASUREMENT UNCERTAINTY, **printed page
  41**
- the constants are the PM2.5 row of **Table 7**, **printed page 42**, which
  reads `Ur(RV) 0.36 | RV 25 ug/m3 | a 0.50 | Np 20 | Nnp 1.5`
- the criterion is **equation (5)**, **printed page 10**,
  `MQI(i) = |Oi - Mi| / (beta * U(Oi))`, fulfilled when the indicator is at most 1
- beta is set on **printed page 17**: "The proportionality coefficient beta is
  arbitrarily set equal to 2, allowing thus deviation between modelled and
  measured concentrations as large as twice the measurement uncertainty."

Equation and table numbers shift between versions. In version 3.2 the same form
is equation (33) on printed page 42 and the same table is Table 6 on printed page
43. This document cites 3.3.

`Np` and `Nnp`, given in the same table as 20 and 1.5, enter only equation (39),
which is the annual-average expression. **This project compares hourly values
through equation (37), so neither constant is used.** Stated here so that neither
is carried into the implementation by mistake.

### 4.3 Why beta is 2

Neither `U(Oi)` nor `2 * U(Oi)` is a combined two-source uncertainty, and the
guidance publishes no such figure. A branch requiring the combined stated
uncertainty of the two sources cannot be satisfied by either. What is available
is a published criterion, and beta = 2 is that criterion taken whole, with the
document's own arbitrary constant left where its authors put it. Choosing beta =
1 means selecting a different number than the one published. That is a smaller
move than fitting a threshold to data, but it is still a move, and the point of
sourcing the threshold externally is that the number comes from outside.

Second reason: a flag at beta = 1 says only that the difference exceeds the
station instrument's tolerance, which will be true constantly and reads as
trivial. A flag at beta = 2 says the model fails the published quality objective
at that point, which is a claim with an external referent.

Disclosed, because an undisclosed convenience is what motivated reasoning looks
like from outside: beta = 2 is also the choice more likely to land inside D2's 1
to 33 percent band, and beta = 1 plausibly over-flags past 33 percent. That was
considered and it is not the reason.

The guidance also defines, on printed page 10, the weaker condition
`|Oi - Mi| <= U(Oi)`, used "to indicate when model-measurement differences are
within the measurement uncertainty". **The count under that condition is computed
and reported alongside the beta = 2 count, as evidence, with no floor attached to
it and no claim binding to it.** D1 and D2 bind to `T = 2 * U(Oi)` only.

### 4.4 The prose contradicts the table, and the table binds

Immediately above Table 7, on the same printed page 42, version 3.3 carries this
sentence verbatim:

> Note also that the value of α for PM2.5 referred to in the Pernigotti et al.
> (2014) working note has been arbitrarily modified from 0.13 to 0.30 to avoid
> larger uncertainties for PM10 than PM2.5 in the lowest range of concentrations.

The source characters in that quotation, including the Greek alpha and the right
single quote, are retained deliberately. A quotation altered to satisfy an
internal style rule is no longer a quotation, and the house-style gate bans em
dashes and brand tokens rather than non-ASCII text.

The sentence says 0.30. Table 7 on the same page says 0.50. The prose was carried
unchanged from version 3.2, where the table did say 0.30, and was not updated
when the table was.

**Table 7 binds.** Three reasons. The document binds the table to the equations
directly, saying "Table 7 presents the values for the parameters in equations
(38) and (39)", whereas the sentence is a change note about a prior working note.
The revision is deliberate rather than a typo: PM10 moved in the same table from
0.13 to 0.25, with `Np` and `Nnp` moving from 30 and 0.25 to 20 and 1.5, so both
particulate rows were revised together. And the sentence states its own purpose,
to avoid larger uncertainties for PM10 than PM2.5 at low concentration; with PM10
at 0.25 and PM2.5 at 0.50, Table 7 satisfies that intent and preserves the
two-to-one ratio the authors were protecting. The numeral went stale, the
reasoning did not.

### 4.5 The correction record

The first verification of this constant, by the advisor, was **wrong**. It
reported `a = 0.30` as unchanged in version 3.3, from a summarised fetch of the
version 3.2 document. The error was found by extracting the version 3.3 PDF text
directly and reading Table 7, which gives `a = 0.50`, and confirmed independently
by the owner extracting the same table. The correction is recorded here rather
than only in the ADR because it changes T, and anything that changes T belongs in
the frozen commit.

Two further disclosures, both mandatory.

**A wholesale revert to version 3.2 was available and is declined.** Version 3.2
is internally consistent at `a = 0.30`, prose and table agreeing, and it flags
more at low concentration. It is declined on version currency alone, never on
effect.

**The constant was ratified after the sensitivity table below had been
computed.** That table is analytic rather than data, so no observation preceded
the pre-registration and the ordering holds, but the sequence is disclosed rather
than left for a reader to reconstruct.

```
                T = 2 * U(O)
    O        a = 0.30       a = 0.50 (v3.3, binding)
    2          6.03            9.08
    4          6.06            9.34
   10          8.74           10.95
   25         18.00           18.00
   50         34.76           32.45
  100         68.90           63.00
```

The two forms cross exactly at `O = RV = 25`, where `U = Ur(RV) * RV = 9.00` for
any value of alpha.

Whichever way the results fall, T does not move. Neither beta nor alpha moves.

## 5. Everything else that changes the magnitude, frozen here

Anything that changes the size of a measured effect must be fixed before the
effect is visible, not only the pass and fail predicate.

**The capture window.** A contiguous historical span, frozen here as
`2026-07-17T00:00Z` to `2026-07-31T00:00Z`, fourteen days. The whole span is
already older than the lag rule below at the moment of freezing.

**Spatial mapping.** The comparison is station to city at the same point, and
only then aggregated to the region-window. A station-to-region mapping alone
would permit comparing a Berlin station against a model value fetched for
Amsterdam. The centre of the mapping is **the grid point Open-Meteo returns**,
not the configured city coordinate, because the city sits at an arbitrary
position inside its cell and a station within R of the city can be up to 2R from
the cell centre and in a different cell. The same grid point centres the OpenAQ
radius query. R is `min(half-diagonal of the serving cell, 25 km)`, the second
term being the API maximum. In EUR the half-diagonal binds, at 6.5 km for
Amsterdam and Berlin and 7.0 km for Madrid. **At all nine non-EUR cities the 25
km cap binds first**, against half-diagonals of 27.8 to 31.5 km, so the rule
applied outside Europe is the cap and not the half-diagonal.

Per-station model fetching was considered and declined. At the 30-minute cadence,
roughly 250 stations would breach the free tier, and the pipeline would then ship
a comparison different from the one D2 measured. The residual offset between a
station and the centre of the cell whose value is compared is disclosed in
section 7 instead.

**Station admission, by capture-window coverage.** A station is admitted when its
PM2.5 sensor's `datetimeFirst` and `datetimeLast` bracket the capture window, so
that it covered the whole span being measured. Admission is not decided by
recency relative to the moment of selection: a station that stopped reporting
after the window but covered all of it belongs in, and one that came online after
the window does not.

*The looser rule was available and is declined.* Bracketing excludes outright a
station that covered 90 percent of the window, even though the per-window
coverage rule below would have used the hours it did cover. A rule admitting
partial coverage was therefore available. It is declined on methodological
grounds: a fixed population means each city's median is computed over the same
stations every hour, so a change in the flag rate over time is not confounded by
a changing station set. That reasoning was settled before the consequence was
weighed. The consequence, weighed afterwards, is that the looser rule might have
admitted Madrid.

**Station inclusion, two further axes.**

*Reference grade.* Only `isMonitor == true` and `isMobile == false`. The
threshold rests on a measurement uncertainty derived from a JRC instrument
inter-comparison of reference methods, cited in the guidance annex, so applying
it to a low-cost sensor would be the wrong tolerance with no way to tell which
direction it errs.

*Siting.* No station classification exists anywhere in the API, and provider is
not a usable proxy: the reference-grade providers are the national regulatory
networks, which contain roadside and industrial sites by design, and the returned
population visibly mixes them, with a roadside site and two park sites among the
first Amsterdam results. The mixed population is therefore **accepted, explicitly
and in advance**, and section 7 records that siting mismatch inflates measured
disagreement without being model error.

**Licences do not affect admission, and do constrain fixtures.** Using publicly
served data in a measurement, and publishing an aggregate rate derived from it,
is not redistribution. Committing raw station values as test fixtures is. So:
station admission does not depend on licence; raw values from stations whose
licence does not permit redistribution, including those where `licenses` is null,
may not be committed as fixtures, and fixtures are drawn from permissively
licensed stations only or synthesised; and attribution is carried in the README
for every provider whose licence requires it, with CPCB's unstated terms named as
unstated rather than assumed permissive.

*Recorded, because the sequence matters:* an earlier version of this rule
excluded stations with a null licence from admission itself. That was found to
remove the entire CPCB network and reduce ASI to one city. **The rule was
corrected because the original reasoning conflated redistribution with use, not
because of what it cost.** The defect carries the change; the cost is disclosed
so that a reader can see the order in which the two became known.

**Hourly value construction is recorded, not gated on.** The networks build an
hourly station value in two different ways. EEA, AirNow and the Japanese Ministry
of the Environment supply a provider-validated hourly value, so
`coverage.observedCount` is 1 and the rollup is a mean of one. CPCB supplies
15-minute raw data, so `observedCount` runs to about 4 and the rollup is a
computed mean. `U(Oi)` was derived for the first kind. The construction is
therefore frozen as a **recorded per-station attribute**, and the flag rate broken
down by it is a required reported output. The computed-mean network is **not
excluded**: it is the only one that shows what sub-hourly variability looks like,
and excluding the odd one out after seeing it would be the same move the licence
rule above had to correct.

**Aggregation.** The city value is the median of qualifying station hourly values
for that hour. Median rather than mean, so one bad station does not carry the
window.

A region-window carries the disagreement state when **at least one** of its
covered cities is flagged, and the flagged-city count is recorded. The reason is
semantic rather than statistical: the region index is built from all of its
cities, so if any covered constituent disagrees, the region's number is partly
built on a value that disagrees, and confidence should propagate. Union over a
varying number of cities raises the region rate relative to a median-of-cities
rule, and that is a property of the frozen rule rather than a result.

**Minimum coverage, decided per window and not per city.** A city-window is
covered when at least 3 stations report that hour with `hasFlags == false` and
`observedCount >= 1`. Three is the smallest value that gives any robustness,
because a median of three tolerates one bad station and a median of two tolerates
none, which makes it a principled floor rather than a fitted one. A region-window
is covered when at least one of its cities is.

Disclosed in advance: **Berlin sits near this boundary.** It has seven admitted
stations, and the completeness sample found one of them reporting 18 hours out of
42. Its covered-window count is therefore unusually sensitive to this rule.
Stated now it is a caveat. Discovered afterwards it would look like a reason to
have chosen differently. The rule does not move either way.

**Negative values are retained.** Validity is gated on `hasFlags == false` and
`observedCount >= 1` only. Negative PM2.5 readings occur, and one admitted sensor
reports a lifetime minimum of -10.2. Discarding or clamping them would bias the
station value upward precisely in the concentration range where T's floor of 9.0
dominates, which would move measured disagreement for a reason that is not
disagreement. The provider's own flag is the external authority on validity, and
using it avoids inventing a cutoff that would be this project's rather than a
cited one. The count and the magnitude distribution of retained negative values
are reported as evidence. If they turn out to matter, that is reported, not
repaired.

**Temporal alignment, hourly, and forced rather than chosen.** Both sources
produce one value per hour, so at `window_minutes = 30` every second window
contains no fresh observation and the disagreement state is undefined for half of
them. The hosted demo already runs at 60 while the local default is 30. That
difference is named here rather than reconciled.

The station side is the `/v3/sensors/{id}/hours` value for the half-open hour
`[H, H+1)`. The model side is the Open-Meteo hourly value at `H`, whose valid
time is Instant. They are paired on `H`. An hour is admitted only once `H + 48
hours` has passed, so that at least one full 24-hour model update cycle has
completed after the hour. Once an hour is admitted it is not re-read, so late
observations do not change an admitted value.

The 48-hour lag is a **mitigation and not a proof**. The documentation lists both
a CAMS European forecast, updating every 24 hours with a 4-day forecast, and a
CAMS European reanalysis, but states nothing about which serves `past_days`, and
the reanalysis is not selectable through this endpoint. The analysis label
therefore remains unverified end to end.

One post-freeze observation is pre-committed here and is **reported, never a
gate**: fetch the same past hour twice at different lags, for example at `H + 6`
and at `H + 48`, and report whether the served value changed. A change proves the
early value was a forecast later replaced. No change is evidence, not proof, that
the served value is stable. This observation may not move the 48-hour rule in
either direction.

**The split.** There is no calibration in this project, because nothing is
fitted. The capture is divided into a **control window** and a **sealed
holdout**, by a rule fixed here and applied before any comparison is computed:
the control window is `[2026-07-17T00:00Z, 2026-07-24T00:00Z)` and the holdout is
`[2026-07-24T00:00Z, 2026-07-31T00:00Z)`. Both are half-open, so no hour falls in
both. The control window runs the apparatus end to end with no fault injected,
which is the no-fault control that every red-gate proof in this portfolio is
paired with. If the control reports a fault, that is an apparatus defect that
blocks the run, never a finding.

**Void and re-run cap.** The control window may be re-run after an apparatus
repair **at most twice**. Every apparatus fault is diagnosed in writing before
any repair is attempted. A third fault ships the project as "the measurement
could not be completed", accompanied by the three diagnoses. No run is ever
re-executed to check whether a fault was a flake. The holdout opens exactly once
regardless of how many control runs happened.

The capture is **historical**, drawn from the OpenAQ archive and from Open-Meteo
`past_days`, which was verified to serve 2400 hours with no nulls at
`past_days=100`. Fourteen days of wall-clock accumulation would consume the
entire effort cap on waiting.

The seal is **procedural**. The split rule is fixed before any download, the
holdout is opened exactly once, and nothing physically prevents an early look.
Claiming a stronger seal than exists is the kind of overstatement this project is
about not making.

The station admission rule above reads `datetimeFirst` and `datetimeLast`, which
are metadata spanning the holdout period, so it is stated plainly here that the
seal is intact: those two fields carry the first and last timestamps at which a
sensor reported, no measured value was read, and nothing about disagreement
could leak through them.

**Admitted cities, an outcome of the rules above and not an input to them.**

```
  EUR  Amsterdam        5 stations    R =  6.5 km     EEA
  EUR  Berlin           7 stations    R =  6.5 km     EEA
  NAM  New York        15 stations    R = 25.0 km     AirNow
  NAM  Chicago          8 stations    R = 25.0 km     AirNow
  NAM  Los Angeles      6 stations    R = 25.0 km     AirNow
  ASI  Tokyo          119 stations    R = 25.0 km     Japan Ministry of the Environment
  ASI  Delhi           42 stations    R = 25.0 km     CPCB x41, AirNow x1

  202 admitted stations across 7 cities in 3 regions

  excluded: Madrid 0, Lagos 0, Nairobi 0, Cairo 0, Jakarta 0
```

Madrid has six reference-grade fixed stations within 7.0 km of its grid point and
none of them covers the capture window. EUR therefore rests on two cities, NAM on
three, ASI on two, and AFR on none.

Station counts are strikingly uneven across the admitted cities, from 5 at
Amsterdam to 119 at Tokyo, and that asymmetry affects the quality of each city's
median rather than the weight a city carries: D2 binds on city-windows, so Tokyo
and Los Angeles each contribute one window per hour, and the minimum-coverage
rule of 3 sets the floor on median quality.

## 6. Claims and floors

### D1: disagreement is reported, never resolved

For every region-window where both sources are present and disagree by more than
T, the index reports a reduced confidence state and both values, and never
substitutes one source for the other or averages them into a single number.

T flags city-windows, so the region-level statement is made explicit: **a
region-window is in disagreement when at least one of its covered cities is
flagged**, and D1's reporting requirement applies to that region-window and names
which cities drove it.

**Floor.** One window where the pipeline silently picks a winner, or where a
disagreement above T fails to produce a reduced state, ships FAILED as the
headline. This claim is proven by a seeded violation that must turn the guard
red, not by the guard being green, and the seeded run is paired with the no-fault
control window described in section 5.

**D1 cannot pass vacuously.** The claim quantifies over flagged windows, so it is
trivially satisfied when no window flags at all. **D1's pass therefore requires
at least one flagged window in the holdout.** With zero flagged windows D1 is NOT
EVALUABLE and ships as such, never as PASSED. A gate that reads green because its
witness set was empty is the third way a gate lies, alongside a gate that cannot
go red and a gate satisfiable by construction.

### D2: the grade discriminates, and is not inert

On the sealed holdout, the disagreement state fires on more than 1 percent and
fewer than 33 percent of **city-windows** that have station coverage.

**The unit is the city-window, not the region-window.** A region-window flags by
union over a varying number of covered cities, two for EUR, three for NAM, two
for ASI, so the same underlying disagreement would produce different region rates
purely from how many cities a region has. A rate whose denominator is constructed
differently across the thing being measured is not one number. The city-window is
where a station and a model cell are physically comparable and where the rate is
comparable across regions. D1 and D3 stay at region level, because that is where
the index output lives, and region-window rates are reported alongside.

**The pooled rate is not one number either, and the per-domain rates are a
required output.** EUR is compared against an 11 km product and NAM and ASI
against a 45 km one. D2 binds on the pooled rate, and the per-domain rates ship
beside it. The flag rate broken down by hourly value construction, provider-
validated against computed mean, is also a required output.

**Reasoning for the band, recorded before any data exists.** Below 1 percent the
state cannot be distinguished from a detector that never fires, so it carries no
information and its guard is vacuous. Above a third, either the threshold sits
below the sources' real combined uncertainty or the two sources are not measuring
a comparable quantity, and in both cases the output is reporting a modelling
error rather than disagreement. The band was **re-examined when the unit changed**
from region-windows to city-windows, rather than carried by inertia, and its
reasoning is unit-agnostic, so it carries unchanged.

**Floor.** Outside that band, the disagreement grade is declared uninformative
and every result in the project ships report-only, exactly as a missed
sensitivity floor did on ProofBench, <https://github.com/rkendev/proofbench>,
where C2 observed 7 losses of 20 against a floor of 16 and every result there
ships report-only as a result.

**Evaluability precondition, stated in advance.** The holdout must contain at
least 200 city-windows with station coverage. Below that, D2 is NOT EVALUABLE and
ships as such rather than as a pass or a fail. A percentage over a witness set
too small to carry it is not a result.

Seven admitted cities at hourly grain give 168 city-windows per day, so the
seven-day holdout has a **ceiling of 1176, which is what the count would be if
every city-hour were covered**. The realised count is an outcome and is not yet
established: the minimum-coverage rule of 3 reporting stations has not been
applied to any hour, and Berlin's completeness sample suggests the realised
figure could be materially lower. The margin appears large. The precondition
stands at 200 either way.

### D3: no fabricated grades

Every region-window with no qualifying station coverage, or with coverage below
the frozen minimum, carries a documented lower provenance tier. No window ever
receives a grade computed from data it does not have, and no window inherits a
grade from a neighbour or from a previous window.

**Floor.** One fabricated or inherited grade ships FAILED. Like D1, this claim is
proven by a seeded violation that must turn the guard red, not by the guard being
green. **The two branches are seeded separately, because they can fail
independently.** One run forces a computed grade onto an uncovered window. A
second forces a window to inherit a neighbour's grade or a previous window's
grade. Each must turn the guard red on its own. AFR guarantees the uncovered
branch a non-empty witness set; the inheritance branch has no such guarantee,
which is precisely why it needs the seeded proof most.

This is the objection ADR-0007 raised about sparse station coverage, turned into
an output, and the pre-flight has already made it sharper than the objection was:
AFR carries the lower tier permanently and in full, because it has no
reference-grade PM2.5 station covering the capture window near any of its three
cities at any radius tested.

### The pre-registered prediction

Two pressures act on D2's flag rate in opposite directions, and both are recorded
before any comparison exists.

**Downward.** At beta = 2 with alpha = 0.50, T has a floor of 9.0 micrograms per
cubic metre at low concentration and is about 11 at a station value of 10, while
typical CAMS regional hourly departures from ground stations are frequently
smaller. This may drive the flag rate below 1 percent, making D2 uninformative
and sending every result to report-only.

**Upward.** The comparison pairs a station hourly mean against a model value
whose valid time is Instant, and a point station against an 11 km or 45 km grid
cell. Both mismatches inflate the measured difference by amounts contained in
neither source's stated uncertainty and neither of which is model error. The
coarser domain carries the larger representativeness term and would be expected
to flag more, so if the pooled rate lands in band driven by the global-grid
regions, that is recorded rather than presented as a uniform result.

Which pressure dominates is not predicted. If the flag rate lands inside the
band, this document does not permit claiming the band was reached by real
disagreement rather than by representativeness, and section 7 says so. Under no
outcome does beta or alpha move.

## 7. What a pass does not establish

A disagreement grade says the two sources differ. It does not say which one is
wrong, and it is not an accuracy claim about either. Anyone reading a flagged
window as "the model is wrong" is reading something this project does not
measure.

Station coverage is uneven, so the flag rate is a property of the covered cities
and does not generalise to the uncovered ones. D2's rate describes EUR, NAM and
ASI only, and within those it describes seven cities. The provenance tier exists
precisely so that this limit is visible in the output rather than only in the
documentation.

The pooled rate mixes two model resolutions, 11 km in EUR and 45 km in NAM and
ASI, which is why the per-domain rates are reported beside it.

Four further limits, all of them things **this project does not separate from
model error**:

1. **Scope.** The disagreement state applies to PM2.5 only. It does not grade
   `pollution_index`, which is computed from `aerosol_optical_depth`. What
   remains ungraded is the pollution component the index is actually built from.
2. **Temporal representativeness.** A station hourly mean is compared against a
   model value whose valid time is Instant.
3. **Spatial representativeness**, in two parts: a point station is compared
   against an 11 km or 45 km cell mean, and there is a residual offset between
   the station and the centre of the cell whose value is compared.
4. **Siting.** The station population mixes roadside, urban background and park
   sites, with no machine-readable classification anywhere in the API. Siting
   mismatch inflates measured disagreement without being model error, and a
   kerbside station cannot be represented by a cell mean at either resolution.

The MQO tolerance widens with concentration, which is a designed property of the
criterion and not a defect, but it means a flag at 4 micrograms per cubic metre
and a flag at 100 are not equally hard to earn.

All of these go in the README, above any number that looks good.

## 8. Cost cap and abort rule

**Money. Zero.** OpenAQ and Open-Meteo are free at this volume, no cloud resource
is created, and no model API is called. If any step would cost money, that step is
out of scope and the project stops rather than expanding the cap. A cap that moves
is not a cap.

**Effort. Four working sessions.** If the work is not complete at the end of the
fourth, the project ships what exists, with the claims that were evaluable marked
as such and the rest marked not evaluable.

**Abort.** A pre-flight showing the two sources do not measure a comparable
quantity would have ended the project with a written record and no code. It did
not fire, and section 3 records why.

## 9. Invariants carried over, not renegotiated

The API key reaches the process through the environment. It is never committed,
and CI stays secret-free, which is a stated property of ADR-0008. Tests run on
recorded fixtures, subject to the licence constraint in section 5. A proposal to
add a repository secret is the wrong branch. The tracked placeholder in
`.env.example` lands during implementation, after this freeze, and it will be the
first secret name in that file.

No HTTP client in the core, per INV-6. Both adapters sit behind the existing
Protocol and are selected through the settings object.

Thresholds and tunables live in the settings object as the single authority. A
constant does not appear in adapter code. This includes `Ur(RV)`, `RV`, `alpha`
and `beta`.

Specification leads code. ADR-0009 and the specification edits land before any
implementation task exists. ADR-0009 records decision context and may reference
this file; it is not the only home for anything in section 4.

No em-dashes and no tool brand names in anything tracked. The repository enforces
both mechanically at stage time.

## 10. Freeze procedure

1. Run the pre-flight. Done, and its answers are recorded in section 3.
2. Record the answers, fix the threshold, and fill the frozen rules of section 5.
   Done, including the changes the pre-flight forced: the compared quantity, the
   threshold form and its constants, D2's unit, the licence rule, the admission
   rule, and the admitted-city list.
3. Commit this file alone, unchanged thereafter.
4. Then ADR-0009, then the specification edits, then the first implementation
   task.

After step 3, only a proof may move a predicate in this document. Never an
observation.
