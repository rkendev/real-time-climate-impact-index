# SETUP: clone to green

This is the deterministic clone-to-green checklist for Phase 1 Track A (NFR-M3,
AT-8). A clean bootstrap must reach green with no manual step. The time is
measured and recorded here, not asserted.

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
```

Stop the stopwatch when `make test` reports all tests passed. That elapsed time
is the clone-to-green figure.

`make bootstrap` is idempotent: re-running it reuses an existing `.venv`, asserts
the interpreter is Python 3.12, and re-runs the gate.

## Measured clone-to-green

Measured on the Phase 1 build host (Linux x86_64, Python 3.12.13):

| Scenario | Elapsed | What was cold |
| --- | --- | --- |
| First run (representative) | ~32 seconds | fresh `.venv`, fresh pre-commit hook cache (ruff and mypy hook environments cloned and built); pip wheel cache warm |
| Steady-state re-run | ~12 seconds | `.venv` and pre-commit hook cache reused (idempotent bootstrap) |

Notes on what these numbers include and exclude:

- Both figures cover `make bootstrap` plus `make lint`, `make type-check`, and
  `make test`.
- The ~32s first-run figure was taken with a warm pip wheel cache. A truly cold
  machine (no `~/.cache/pip`) additionally downloads the wheels, so its first run
  is somewhat slower; the dominant variable cost is building the pre-commit hook
  environments, which are cached after the first run.
- All four commands returned success (exit 0) in every recorded run.

## Environment note

If the environment sets a global `git core.hooksPath` (as some managed hosts do),
`pre-commit` refuses to install its git-hook shim. `make bootstrap` detects this,
prints a note, and skips only the shim; the hygiene gate
(`scripts/verify-precommit.sh`) still validates the config and runs every hook, so
no hook-install failure is ever swallowed (NFR-M2). To enable the on-commit shim
locally, unset the path (`git config --global --unset core.hooksPath`) and run
`make hooks`.
