# ADR-0001: Record architecture decisions

Status: accepted
Date: 2026-07-16

## Context

This is a spec-driven, greenfield rebuild. Decisions need a durable home so that a future reader knows not just what was chosen but why, and what would reopen the choice. The portfolio already uses architecture decision records with a falsifiable reopen trigger on each significant decision.

## Decision

Every significant decision is recorded as a numbered ADR in this folder. Each ADR states context, the decision, the alternatives considered, the consequences, and a falsifiable trigger that would reopen it. ADRs are part of the source-of-truth set: a decision changes here first, then cascades downstream.

## Consequences

The two decisions deliberately left open at the start of this project (the Phase 1 stream processor and the cloud topology) have their own ADRs, 0002 and 0003, and are marked proposed until the owner locks them. The non-functional invariants have their own ADR, 0004, because they are the standing law the whole system is tested against.

## Reopen trigger

If the project adopts a decision-tracking mechanism that supersedes flat ADR files, migrate the existing records rather than abandoning them.
