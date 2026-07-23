# ADR-0008: Continuous integration on GitHub Actions

Status: decided (two jobs on hosted runners; zero secrets, zero spend, no deploy path)
Date: 2026-07-23
Related: `adr/0004-nonfunctional-invariants.md` (INV-5, and the gate-protects-the-gate clause), `10_prd.md` NFR-M1, NFR-M2, `30_plan.md` AT-7, AT-8, `40_tasks.md` T-A3, `RUNBOOK.md` offline gates

## Context

### The decision this closes was never written down

The specification asked for CI from the start, in three places:

- `10_prd.md` NFR-M2: "Verify: a CI step that validates the config and a seeded-broken fixture that must fail."
- `40_tasks.md` T-A3: "Add the pre-commit config and a CI step that validates it on a clean checkout."
- `adr/0004-nonfunctional-invariants.md`: "if the pre-commit or CI config does not parse, the invariants are not actually enforced."

What Track A actually built was a local script, `scripts/verify-precommit.sh`, run from
`make bootstrap`. That script does the work the requirement describes: it validates the
configuration, refuses to swallow a hook-install failure, and runs every hook over the
whole tree, with `tests/hygiene/test_precommit_gate.py` proving a broken configuration
fails red (AT-7). It just never ran anywhere except on an operator's machine.

So there is no recorded decision to go without CI, and this ADR is not a reversal of one.
It closes an unrecorded substitution: a local gate stood in for a specified CI step, and
the substitution was never argued, dated, or written down. The honest reading is that the
requirement was satisfied in substance and left open in mechanism for the length of the
build.

### Why now

Three things that were not true earlier are true now, and together they make a hosted
runner cheap and worth having:

- The repository is public. A reader can now see whether the checks pass without being
  asked to take a claim on trust, and a green run on every commit is a stronger statement
  than a number quoted in a README.
- The suite is order-independent and offline-deterministic. Two defects fixed that: the
  session-scoped fake AWS credentials that leaked out of the AWS package into a
  Terraform-running subprocess, and a hygiene scan that walked the working directory
  instead of the tracked tree, so it reported on files no commit could carry. Before
  those, a hosted run would have been a source of false red.
- The whole check chain runs with zero secrets and zero spend. Nothing in it needs an AWS
  credential, a registry token, or a paid resource. That is precisely the shape a hosted
  runner rewards, and it is why this costs nothing to adopt.

## Decision

Add `.github/workflows/ci.yml` with two jobs, both required to pass.

**`checks`** runs the full offline chain on `ubuntu-24.04`: `make bootstrap` (pinned
installs plus the hygiene gate), `make lint`, `make type-check` (strict mypy), `make
verify-versions` (INV-5), `make hygiene` (NFR-M2, the whole tree), and `make test` (the
complete suite, including the moto-backed AWS adapter tests and the Terraform-dependent
gate tests). Each gate is its own named step so a failure has its own line on the run
page rather than being buried inside a composite command.

**`container-smoke`** runs `make container-smoke`: the app image built, single-node Kafka
started in KRaft mode, and producer to consumer to store to dashboard over a live broker.
It is a separate job on purpose. It is the only job that needs a container runtime and a
broker, it is the slowest, and its failure modes (image build, broker health, drain
timing) have nothing to do with the offline chain. Isolating it makes a failure legible
and attributable at a glance.

Every step invokes a repository `make` target. The workflow reimplements no command body,
so the thing CI runs and the thing an operator runs cannot drift apart.

### Triggers

Push to `main`, `pull_request`, a weekly schedule at 06:17 UTC on Mondays, and
`workflow_dispatch`.

The weekly run is the deliberate one. A finished repository gets no pushes, and a
dormant repository is exactly where toolchain and dependency drift accumulates unseen.
This project has already been bitten by that class of defect once: a Terraform release
changed credential validation under a configuration that had not changed, and it was
found by a hand-run, not by a check. A weekly run turns that from a discovery into a
notification. The cron is deliberately off the hour, because scheduled jobs queued at the
top of the hour wait behind everyone else's.

`workflow_dispatch` is there for the failure mode described below, and because a
zero-cost manual trigger is worth having on a repository whose whole point is that anyone
can reproduce the checks.

### What is pinned, and why

- **Terraform 1.14.8**, the version proven on the box during the G2 run. The gate tests
  shell out to `terraform`, so the version is part of what is under test. An upgrade
  becomes a deliberate commit rather than something that arrives on its own.
- **Actions by full commit SHA**, with the release tag in a trailing comment. A tag can be
  moved to point at new code; a commit SHA cannot. On a project whose claim is a
  secret-free supply chain, pinning the mutable thing is not enough.
- **The runner image** as `ubuntu-24.04` rather than `ubuntu-latest`, for the same reason
  the Python interpreter and every dependency are pinned: a floating label is an
  undeclared input.
- **Python as the 3.12 series, with the patch floating.** This is the one place the
  pin-everything rule is deliberately relaxed, and the reason matters. No file in this
  repository declares a patch version: the Makefile asks for `python3.12`, ruff targets
  `py312`, mypy sets `python_version = "3.12"`, and the image is `python:3.12-slim`. A
  patch pin in the workflow would have no counterpart anywhere and would be a rival
  declaration of the kind INV-5 exists to prevent. It would also blind the weekly run to
  a bad new patch release, which is one of the two drift classes the schedule exists to
  catch. Pinning the series and letting the patch float states what the project actually
  requires and leaves the drift detector working.

### What CI deliberately does not do

No deploy, no `terraform apply`, no AWS API call, no spend, no image push, no release
automation, and no `make pre-deploy-gate` run. The paid sequence stays a hand-run
operator procedure behind the gate documented in `RUNBOOK.md`, because the value of that
gate is that a person decides to cross it.

This is enforced structurally rather than by convention: the workflow declares
`permissions: contents: read`, no repository secret is configured, and no AWS variable
appears anywhere in the file. The only token in play is the default read-only
`GITHUB_TOKEN`. There is nothing for a compromised step to spend or to publish with.

## Consequences

### The hygiene gate now covers the CI configuration

`tests/hygiene/test_house_style.py` scans every file `git ls-files` reports, so
`.github/workflows/ci.yml` falls under it automatically: no em-dash, no attribution
token, no brand token in the workflow, checked on every run including CI's own. That
makes good on the clause in ADR-0004 that the build-hygiene gate protects the mechanism
that runs the checks. Until now the CI half of that sentence described nothing.

### Honest limits

**The suite is not network-free.** Under an isolated network namespace, two tests fail
and six more skip: `tests/integration/test_terraform_offline.py` and
`tests/unit/test_pre_deploy_gate.py` shell out to `terraform init`, which fetches the AWS
provider from the public registry. No Python test dials out, and INV-6 (no network client
under core) is unaffected. What the offline claim means precisely is: no credential, no
paid service, no project-specific endpoint. It does not mean no egress.

**A scheduled workflow is disabled after about 60 days without repository activity.**
GitHub stops the schedule on a repository nobody has touched, which is the exact state
the weekly run exists to cover. The mitigation is `workflow_dispatch`: a quiet workflow
is re-run and re-enabled by hand from the Actions page or with `gh workflow run`, at no
cost and with no secret. It is worth stating plainly that the drift detector has a
dormancy limit of its own, rather than assuming a schedule set once runs forever.

**Two Terraform cache optimizations were considered and rejected**, because neither
works here. Setting `TF_PLUGIN_CACHE_DIR` at job level is inert: the offline Terraform
test module sets its own temp cache and then removes the variable from the environment
entirely, and it runs before the gate test that would otherwise benefit. Caching on
`.terraform.lock.hcl` has no key, because the lock files are git-ignored and a fresh
clone has none. The measured cost of doing nothing is one provider download of a few
seconds per stack, already inside the recorded suite time.

### Cost and timing

Free-tier minutes only, on public-repository runners. The timeouts (20 minutes for
`checks`, 25 for `container-smoke`) come from a measured fresh-clone chain of about six
to seven minutes, doubled for runner variance: pinned installs 55 seconds, pre-commit
hook environments 12 seconds, cold mypy 69 seconds, and the full suite 253 passed and 2
skipped in 147 seconds including the Terraform provider downloads. An explicit timeout
means a hung broker or a stuck moto server dies in minutes instead of burning against the
platform default. A concurrency group cancels superseded runs on the same ref for the
same reason.

## Falsifiable triggers

- If the weekly run turns into noise rather than signal (repeated red for reasons outside
  the repository), keep it and quarantine the flaky check; do not delete the schedule,
  because a dormant repository with no scheduled run is the state this was written to fix.
- If the Terraform provider downloads come to dominate the run, pin the provider version
  and commit the lock files rather than adding a cache whose key would hide the drift the
  weekly run is looking for.
- If CI is ever asked to hold a secret, that request is out of scope for this ADR and
  needs a new one. The zero-secret property is the reason this workflow is safe to run on
  every pull request from anyone.
