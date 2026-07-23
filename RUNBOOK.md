# Runbook: deploy, verify, tear down (gate G2)

The operational runbook for the terminal cloud phase. Everything buildable offline
is proven green before any spend; the paid window is bounded and torn down
immediately (there is no auto-stop backstop, so teardown is non-negotiable).

## Resting state

Between demos the project sits at storage-only rest cost: data in S3 (Iceberg
aggregate-of-record and raw) and DynamoDB (serving), the Glue database, the ECR
repository, and the budget alarm. No compute runs. A re-demo is a single ephemeral
apply against this standing persistent layer.

## Offline gates (no spend, run first)

```
make lint type-check test        # all green
make smoke                       # writes the .smoke_ok marker
make container-smoke             # producer to dashboard through a live Kafka broker
make tf-fmt tf-validate tf-plan  # all three stacks validate and plan offline
make pre-deploy-gate             # AT-9: marker, single-sourced versions, terraform valid
```

Only on a green `pre-deploy-gate` may the paid sequence begin.

Everything above except `make smoke`, `make pre-deploy-gate`, and the Terraform
targets already runs in CI on every push, every pull request, and weekly
(`.github/workflows/ci.yml`, ADR-0008), the container smoke as its own job. The
Terraform stacks are still covered there, through the offline gate tests inside
`make test`. So this list is the local mirror of an automated chain, and the
operator steps that remain hand-run are the ones that write a marker or spend
money.

## Paid sequence (bounded; only after the gate is green)

Prerequisites (no spend): confirm current region pricing and free-tier eligibility;
fill the git-ignored `terraform.tfvars` in each stack; fetch the current arm64
AL2023 AMI id into `infra/ephemeral/terraform.tfvars`:

```
aws ssm get-parameters \
  --names /aws/service/ami-al2023-latest-arm64 \
  --region <region> --query 'Parameters[0].Value' --output text
```

Then, in order:

```
# 1. Bootstrap the remote-state bucket (one time, outside the main config).
terraform -chdir=infra/bootstrap init && terraform -chdir=infra/bootstrap apply

# 2. Init the two stacks on the real S3 backend.
terraform -chdir=infra/persistent init -backend-config=... 
terraform -chdir=infra/ephemeral  init -backend-config=...

# 3. Apply the persistent stack (buckets, DynamoDB, Glue, IAM, budget, ECR repo).
#    offline_plan=false lets the provider resolve the account id (needed for Glue).
TF_VAR_project_tag=$(.venv/bin/python -c 'from climate_index.config import get_settings; print(get_settings().project_tag)') \
  TF_VAR_offline_plan=false terraform -chdir=infra/persistent apply
#    Confirm the 12 dollar budget alarm is live in the console.

# 4. Build the arm64 image and push it to ECR (from the workstation, not the box).
export ECR_REPO=$(terraform -chdir=infra/persistent output -raw ecr_repository_url)
make image-build image-push          # buildx --platform linux/arm64, then push

# 5. Apply the ephemeral stack. The box pulls the image and runs the stack via
#    user_data (docker login by instance role, docker compose pull and up).
#    Pass ecr_repository_url and image_tag into the ephemeral tfvars first.
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral apply

# 6. Run the producer for a bounded batch (via SSM Session Manager on the box):
#    cd /opt/climate-index && docker compose run --rm producer
```

## Verify on AWS (exit gate G2)

```
CII_AGGREGATE_BACKEND=aws make verify-at5      # replay yields exactly one Iceberg row (real Glue)
CII_AGGREGATE_BACKEND=aws make verify-nfr-p3   # DynamoDB read p95 under one second
```

Also confirm the dashboard is reachable at the instance public address on the
dashboard port from the owner IP, showing the index, its verbal label, and its
confidence.

## Tear down immediately (manual, no backstop)

```
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral destroy
make teardown-audit                            # AT-11: no billable resource carries the project tag
```

Leave the persistent layer standing. Record the actual spend below.

## Re-demo (one command against the standing persistent layer)

```
export ECR_REPO=$(terraform -chdir=infra/persistent output -raw ecr_repository_url)
make image-push                                 # only if the image changed
TF_VAR_project_tag=$... TF_VAR_offline_plan=false terraform -chdir=infra/ephemeral apply
```

Tear down with the ephemeral destroy plus `make teardown-audit` as above.

## Recorded spend (paid run 2026-07-20, us-east-1)

- Instance: t4g.medium, up for roughly 40 minutes, then destroyed.
- Actual spend: under 0.05 US dollars (t4g.medium ~40 min about 0.025, public IPv4
  about 0.004, S3 and DynamoDB and Glue and ECR operations pennies). Cost Explorer
  showed 0 for the project tag at teardown time (billing data lags several hours).
  Far under the 50 dollar ceiling.
- AT-5 against the real Glue catalog: OK (replaying one window left exactly one
  Iceberg row for EUR).
- NFR-P3: OK (DynamoDB read p95 130 ms over 50 reads across 48 seeded windows,
  under the 1000 ms target; measured cross-internet, so faster in-region).
- Aggregates populated in both stores: DynamoDB and the S3 Iceberg or Glue table.
- Dashboard reachable at the instance public address on port 8501 from the owner
  IP, serving the index, verbal label, and confidence for all four regions.
- AT-11 post-teardown audit: clean (no billable resource carries the project tag).
- Persistent layer left standing at near-zero rest (state, warehouse, and raw
  buckets; DynamoDB; Glue database; ECR image; budget alarm).

## Local live demo (the always-on link)

A separate thing from everything above: the public demo runs the **local** backend
only (`CII_AGGREGATE_BACKEND=duckdb`), on a box already fronted by Caddy. It reads
no cloud credential, makes no cloud call, and costs nothing. The AWS full-stack run
stays on demand and is the recorded gate G2 above.

Shape: an always-on read-only dashboard over a local DuckDB, plus a timer that
refreshes the snapshot. Between refreshes only the dashboard is resident, roughly a
quarter of a gigabyte; Kafka, the feeder, and the consumer exist for the minute or
two a refresh takes and are torn down with it.

```
make vps-demo-up         # idempotent standup: units, first refresh, timer, Caddy site
make vps-demo-status     # what is resident, next firing, snapshot freshness
make vps-demo-refresh    # run one refresh now
make vps-demo-down       # remove units and site block (ARGS=--purge drops the snapshot)
```

Standup writes `deploy/vps/demo.env` from the tracked placeholder, derives the
public IPv4, and records `climate-index.<the address with dashes>.sslip.io` there.
That file is git-ignored; only the `*.example` and the templates are tracked
(INV-1). Caddy issues and renews the certificate for that name itself.

**Cadence.** One value, `CII_DEMO_REFRESH_INTERVAL` in `deploy/vps/demo.env`
(default `30min`). Change it and re-run `make vps-demo-up`; the timer is re-rendered
and re-armed. The page states this same cadence, because the dashboard unit reads
that environment file. `CII_DEMO_WINDOWS` and `CII_DEMO_EVENTS_PER_WINDOW` size each
snapshot (default twelve windows, so six hours of series at the 30 minute window).

**Uneven coverage on purpose.** `CII_DEMO_DEGRADED_WINDOW_FRACTION` (default `0.25`)
is the share of each backfill's windows given thinner input: those carry weather
readings only, and the oldest of them carries a single reading. The newest window is
never thinned. The committed confidence computation grades those windows down by
itself, so a snapshot reads roughly nine MEASURED, two INFERRED, and one AMBIGUOUS
window per region and the page shows the provenance signal working rather than one
flat tier. The tiers displayed are computed from that input by the pipeline; neither
the feeder nor the dashboard sets a grade, and every event published stays
well-formed, so nothing is quarantined to achieve it.

**What a refresh does.** Wipes the staging directory, brings single-node Kafka up on
its own compose project, publishes a bounded backfill across the last N event-time
windows, drains it with the committed consumer into a staging DuckDB, publishes that
snapshot, then brings every streaming component down. Bounded input plus a wiped
staging area means each snapshot is self-contained and the disk footprint stays flat.

**Atomic publish.** `deploy/vps/publish_snapshot.py` verifies the staging snapshot
through the same read-only factory the dashboard reads with (every region present,
natural keys unique, no write-ahead log), then renames it over the served path. The
writer only ever holds the staging file, so the reader never contends for the DuckDB
lock; the rename is atomic, so a render sees a whole snapshot or the whole previous
one. A refresh that fails anywhere before that step publishes nothing and the last
good snapshot keeps serving. `tests/unit/test_atomic_publish.py` holds that line.

**Caddy.** The site block is appended between managed markers, validated, and
reloaded; the existing configuration is never replaced and the other sites are
untouched. A backup is left at `/etc/caddy/Caddyfile.bak.climate-index`, and
`make vps-demo-down` removes the block the same way.

**Recovery.** The dashboard unit is `Restart=always` and enabled, so it returns
after a crash and after a reboot with no human. The timer is enabled too, and fires
two minutes after boot.

## AT-12: the real source, verified live (2026-07-22)

The acceptance test for the real event source (`30_plan.md` AT-12, ADR-0007) is a
hand-run check against the live provider, deliberately not part of the suite: no
network enters the test run, and the adapter's offline tests drive
`httpx.MockTransport` instead. Recorded here so the result is auditable without
rerunning it.

Command (the two endpoints and the broker address come from the environment,
never from source, INV-1):

```bash
CII_SOURCE_BACKEND=real \
CII_OPEN_METEO_WEATHER_URL=https://api.open-meteo.com/v1/forecast \
CII_OPEN_METEO_AIR_QUALITY_URL=https://air-quality-api.open-meteo.com/v1/air-quality \
CII_TRANSPORT_BOOTSTRAP_SERVERS=localhost:9092 \
PYTHONPATH=src .venv/bin/python -m climate_index.producer   # one tick, then the processor pass
```

**Clean run.** Four regions, three cities each, two streams per city: 24 events,
six per region, nothing unavailable, nothing quarantined, four window rows graded
by the committed grader.

```
{"component":"at12","emitted":24,"event":"source_tick_complete","regions":4,"unavailable":0}
{"component":"at12","event":"heartbeat","published":24,"regions":4,"tick_events":24}
{"component":"at12","event":"producer_run_complete","published":24,"ticks":1}

per-region published counts (published=24): EUR 6, NAM 6, AFR 6, ASI 6

{"component":"at12","consumed":24,"event":"processor_run_complete","forwarded":24,"quarantined":0,"records":4}

EUR 2026-07-22 13:00 .. 13:30  index=44.99 anomaly= 2.97 dry=0.605 poll=0.499 confidence=MEASURED
NAM 2026-07-22 13:00 .. 13:30  index=31.37 anomaly=-3.13 dry=0.605 poll=0.441 confidence=MEASURED
AFR 2026-07-22 13:00 .. 13:30  index=56.87 anomaly= 7.07 dry=0.643 poll=0.311 confidence=MEASURED
ASI 2026-07-22 13:00 .. 13:30  index=37.82 anomaly= 1.90 dry=0.598 poll=0.410 confidence=MEASURED
```

**Induced-gap run.** The same command with the air quality endpoint pointed at a
dead host (`air-quality-api.open-meteo.invalid`) and a five second timeout. This
is the run that matters: it shows the confidence grade is genuine rather than
arranged. Twelve counted skips, one per city, half the events, and the committed
grader drops every region to INFERRED on its own. Nothing sets a grade, and no
missing reading is substituted or retried.

```
{"city":"Amsterdam","event":"source_reading_unavailable","reason":"transport_error","region":"EUR","stream":"satellite"}
{"city":"Berlin",   "event":"source_reading_unavailable","reason":"transport_error","region":"EUR","stream":"satellite"}
...one per city, twelve in all...
{"component":"at12","emitted":12,"event":"source_tick_complete","regions":4,"unavailable":12}
{"component":"at12","event":"producer_run_complete","published":12,"ticks":1}

per-region published counts (published=12): EUR 3, NAM 3, AFR 3, ASI 3

{"component":"at12","consumed":12,"event":"processor_run_complete","forwarded":12,"quarantined":0,"records":4}

EUR 2026-07-22 13:00 .. 13:30  index=41.87 anomaly= 2.97 dry=1.000 poll=0.000 confidence=INFERRED
NAM 2026-07-22 13:00 .. 13:30  index=30.00 anomaly=-3.13 dry=1.000 poll=0.000 confidence=INFERRED
AFR 2026-07-22 13:00 .. 13:30  index=57.97 anomaly= 7.07 dry=0.990 poll=0.000 confidence=INFERRED
ASI 2026-07-22 13:00 .. 13:30  index=37.60 anomaly= 1.90 dry=1.000 poll=0.000 confidence=INFERRED
```

Note the temperature anomaly is identical across both runs (EUR +2.97, NAM
-3.13): the weather stream was unaffected, only the pollution stream went dark.
That is the per-stream containment the one-request-per-city design buys.

**Demo replay check.** Two consecutive `make vps-demo-refresh` runs each fetched
and republished 912 events (4 regions x 3 cities x 2 streams x 38 hours) and the
published snapshot held **152 rows both times, not 304**. Re-publishing an hour
lands on the same natural key rather than duplicating it, so the live demo now
exercises FR-6 / NFR-R1 continuously instead of only inside AT-5.

## Notes learned on the run (folded into the code)

- Real applies pass `TF_VAR_offline_plan=false` so the provider resolves the
  account id (the offline default keeps validate and plan credential-free).
- The Glue database sets `catalog_id` explicitly, pyiceberg's Glue catalog needs
  `AWS_REGION` in the box environment, and the processor role needs
  `glue:CreateDatabase` (pyiceberg calls it idempotently on first table creation).
