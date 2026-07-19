# ADR-0004: Non-functional invariants (the standing law)

Status: accepted
Date: 2026-07-16
Related: the whole NFR section of `10_prd.md`, enforced across all phases in `30_plan.md`

## Context

The emphasis of this project is its non-functional quality. A subset of the non-functional requirements are not targets to tune but invariants to hold at every commit and in every phase. They are stated once here as the standing law, given short INV IDs, and each names how it is enforced. This mirrors the portfolio invariant discipline, where an invariant is a property tested on every change rather than a goal.

## The invariants

INV-1: No secrets or endpoints in code or logs. All connection details and credentials come from a config object populated by the environment. Enforced by a grep test over source and a scan over logs (NFR-SEC1). Rationale: the earlier build scattered configuration and this rule removes that class of error.

INV-2: The dashboard is strictly read-only. It performs no index computation and issues no writes; it connects to the store with read-only access. Enforced by a test that the dashboard module imports no writer and no compute path, and by a read-only connection or role (NFR-SEC3, FR-8, AT-6).

INV-3: Every record entering the aggregate store passed the deterministic validation gate. Invalid input is quarantined with a reason code and counted, never silently dropped and never written as data. Enforced by tests feeding malformed events and asserting quarantine and the absence of a bad aggregate (NFR-DQ1, FR-3, AT-2).

INV-4: The core package imports no cloud-vendor SDK. All vendor specifics live behind the transport and store adapters. Enforced by a test asserting no cloud SDK import appears under the core package (NFR-PT1, AT-10). Rationale: this keeps the core free of vendor SDKs and unit-testable without cloud credentials, and makes the local-to-AWS move an adapter swap. AWS is the only cloud target; the invariant is anti-lock-in hygiene, not a multi-cloud claim.

INV-5: One source of truth for dependency versions. A pin declared in one file and disagreeing in another fails the build. Enforced by a version-consistency check across all dependency-declaring files (NFR-M1). Rationale: the earlier build had rival dependency declarations, so a green check in one toolchain was not a green check in another.

## Consequences

- These five invariants are wired as tests from the first commit, several of them failing until the code that satisfies them exists, so the scaffold is red until the invariants hold.
- A change that breaks any invariant is a defect regardless of whether functional tests pass.
- The build-hygiene gate (NFR-M2, AT-7) protects the mechanism that runs these checks: if the pre-commit or CI config does not parse, the invariants are not actually enforced, so the gate must fail red on a broken config.

## Reopen trigger

An invariant is removed or amended only through an ADR that supersedes this one and updates the affected tests in the same change. Silently dropping an invariant test is itself a defect.
