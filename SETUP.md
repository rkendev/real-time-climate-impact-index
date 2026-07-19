# SETUP: clone to green

This is the deterministic clone-to-green checklist for Phase 1 (NFR-M3, AT-8). A
clean bootstrap must reach green with no manual step. The time is measured and
recorded here, not asserted. Reaching a green `make smoke` from a clean checkout
with no manual step is exit gate G1, which ends Phase 1 and unlocks Phase 2.

## Prerequisites

- Python 3.12 available on PATH as `python3.12` (override with `make PYTHON=...`).
- `git` and network access (the first hygiene-gate run clones the pre-commit
  hook repositories; after that they are cached).

## Stopwatch checklist

Start the stopwatch, then run:

```
git clone <this-repo> && cd climate-impact-index   # or: cd into your checkout
make bootstrap        # create .venv (Python 3.12), install pinned deps, run the hygiene gate
make lint             # ruff check + ruff format --check
make type-check       # mypy --strict on src
make test             # pytest
make smoke            # end-to-end in-memory pipeline; writes the .smoke_ok marker
```

Stop the stopwatch when `make smoke` reports `smoke_ok`. That elapsed time is the
clone-to-green figure and the gate G1 measurement. A green `make smoke` writes
the local `.smoke_ok` marker; `scripts/pre_deploy_gate.sh` then passes, which is
what unlocks the Phase 2 (cloud) work (NFR-C1, AT-9).

`make bootstrap` is idempotent: re-running it reuses an existing `.venv`, asserts
the interpreter is Python 3.12, and re-runs the gate.

## Measured clone-to-green (gate G1)

Measured on the Phase 1 build host (Linux x86_64, Python 3.12.13):

| Scenario | Elapsed | What was cold |
| --- | --- | --- |
| First run (representative) | ~55 seconds | fresh `.venv`, fresh pre-commit hook cache (ruff and mypy hook environments cloned and built); pip wheel cache warm |
| Steady-state re-run | ~26 seconds | `.venv` and pre-commit hook cache reused (idempotent bootstrap) |

Notes on what these numbers include and exclude:

- Both figures cover `make bootstrap` plus `make lint`, `make type-check`,
  `make test`, and `make smoke`. This is the gate G1 measurement: a clean
  bootstrap to a green smoke with no manual step.
- The ~55s first-run figure was taken with a warm pip wheel cache. A truly cold
  machine (no `~/.cache/pip`) additionally downloads the wheels (the runtime set
  now includes streamlit and its dependencies), so its first run is somewhat
  slower; the dominant variable cost is building the pre-commit hook
  environments, which are cached after the first run.
- `make test` reported 113 passed, 2 skipped (the two live-broker Kafka tests,
  deferred until Phase 2 infra). All five commands returned success (exit 0) in
  every recorded run, and `make smoke` wrote the `.smoke_ok` marker.

## Environment note

If the environment sets a global `git core.hooksPath` (as some managed hosts do),
`pre-commit` refuses to install its git-hook shim. `make bootstrap` detects this,
prints a note, and skips only the shim; the hygiene gate
(`scripts/verify-precommit.sh`) still validates the config and runs every hook, so
no hook-install failure is ever swallowed (NFR-M2). To enable the on-commit shim
locally, unset the path (`git config --global --unset core.hooksPath`) and run
`make hooks`.
