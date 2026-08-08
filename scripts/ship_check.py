#!/usr/bin/env python3
"""Refuse to tag a commit that continuous integration has not passed.

This exists because a checklist line cannot prevent what happened here. CI was
red for twenty-one consecutive runs, from 3 August through the v2.2.0 release,
and every one of those runs published its verdict on the front page of the
repository. Nobody read them. Human memory is precisely what failed, so the
control has to be mechanical and the checklist entry documents it rather than
standing in for it.

Four properties, each of which is a failure mode this repository has already hit:

**Keyed on the SHA, never the branch.** A green run on a different commit is the
right answer to the wrong question, which is the vacuous mode: a witness set that
does not contain the thing under test.

**Absence of a red is not a green.** No run for the SHA fails. A run still in
progress fails. A cancelled run fails, and this project produced two of those
from its own concurrency group. A check that can pass by finding nothing is the
gate that cannot go red.

**It names the run it read**, by number and conclusion, so a verdict can be
traced to the evidence behind it. A check whose reasoning is invisible is one
nobody can audit and, on this project's evidence, one nobody reads.

**It runs the same entrypoint CI runs.** The root cause here was invocation
drift: ``make test`` aborted during collection while ``python -m pytest``
collected 447, and only the second was ever run. A ship check that skips CI's own
entrypoint locally rebuilds the same hole one level up, so this shells out to
``make test`` by name and reports the target it used.

The Actions verdict is read from ``/repos/{owner}/{repo}/actions/runs?head_sha=``.
The combined commit status endpoint is deliberately not used: for a commit whose
CI has passed it returns ``state: "pending"`` with zero statuses, because Actions
results are check runs and never appear there. Verified live against this
repository before this file was written.

Usage: python scripts/ship_check.py [SHA]     (default: HEAD)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_NAME = "ci"
# Anything other than this is a refusal, including states that are not failures.
# "cancelled", "skipped", "stale", "timed_out" and a null conclusion on an
# in-progress run all mean the same thing here: CI did not say yes.
PASSING = "success"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def resolve_sha(ref: str) -> str:
    """The full forty-character SHA. The API matches on the full value."""
    result = _run(["git", "rev-parse", ref])
    if result.returncode != 0:
        raise SystemExit(f"ship-check: cannot resolve {ref!r}: {result.stderr.strip()}")
    return result.stdout.strip()


def repo_slug() -> str:
    result = _run(["git", "remote", "get-url", "origin"])
    if result.returncode != 0:
        raise SystemExit("ship-check: no origin remote, so CI cannot be consulted")
    url = result.stdout.strip().removesuffix(".git")
    if ":" in url and "//" not in url:
        return url.split(":", 1)[1]
    return "/".join(url.split("/")[-2:])


def workflow_runs(slug: str, sha: str) -> list[dict[str, Any]]:
    result = _run(["gh", "api", "-X", "GET", f"repos/{slug}/actions/runs", "-f", f"head_sha={sha}"])
    if result.returncode != 0:
        raise SystemExit(f"ship-check: could not query CI: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    runs: list[dict[str, Any]] = payload.get("workflow_runs") or []
    return [r for r in runs if r.get("name") == WORKFLOW_NAME]


def check_ci(sha: str, slug: str) -> tuple[bool, str]:
    """Whether CI concluded success for this exact commit, and why."""
    runs = workflow_runs(slug, sha)
    if not runs:
        return False, (
            f"no {WORKFLOW_NAME!r} run found for {sha[:7]}. Absence of a red is not a "
            "green: the commit may not be pushed, or CI may not have started."
        )
    latest = max(runs, key=lambda r: int(r.get("run_number", 0)))
    number = latest.get("run_number")
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if status != "completed":
        return False, f"run #{number} is {status}, not completed. Wait for it."
    if conclusion != PASSING:
        return False, f"run #{number} concluded {conclusion!r}, not {PASSING!r}."
    return True, f"run #{number} concluded {conclusion!r}."


def run_make_test() -> tuple[bool, str]:
    """CI's own entrypoint, by name, because invocation drift is the root cause."""
    result = _run(["make", "test"])
    tail = (result.stdout or result.stderr).strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    return result.returncode == 0, f"`make test` exited {result.returncode}: {summary}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", nargs="?", default="HEAD", help="commit to check (default HEAD)")
    parser.add_argument(
        "--skip-local", action="store_true", help="consult CI only, do not run make test"
    )
    args = parser.parse_args(argv)

    sha = resolve_sha(args.ref)
    slug = repo_slug()
    print(f"ship-check: {slug} at {sha[:7]} ({sha})")

    ci_ok, ci_why = check_ci(sha, slug)
    print(f"  CI      : {'PASS' if ci_ok else 'FAIL'}  {ci_why}")

    local_ok, local_why = (True, "skipped by request")
    if not args.skip_local:
        local_ok, local_why = run_make_test()
    print(f"  local   : {'PASS' if local_ok else 'FAIL'}  {local_why}")

    if ci_ok and local_ok:
        print("ship-check: OK to tag.")
        return 0
    print("ship-check: REFUSING. Do not tag this commit.")
    return 1


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
