# Real-Time Climate Impact Index: Greenfield Spec Set

Version: 0.4.0 (spec only, no code)
Date: 2026-07-16
Status: source-of-truth documents for a clean-slate rebuild

## What this is

This is the spec-driven starting point for rebuilding the Real-Time Climate Impact Index (CII) project end to end. The prior build was lost. This set treats the specification as the source of truth: code, tests, infrastructure, and documentation are downstream artifacts generated from these documents, and when a requirement changes you edit the spec first and let the change cascade. That inversion is the central idea in the spec-driven-development source (`Research/New_Spec Driven Development Info/Spec-Driven Development How AI Is Flipping the Script on Software Engineering.txt`, Martinelli's AI Unified Process).

No code is produced in this document set by design. The first build phase (local, single machine) and the cloud phase (AWS, the only cloud target) are planned here but executed later.

## Reading order

1. `docs/00_project_description.md` : the concept, the story, the scope boundary.
2. `docs/10_prd.md` : product requirements. Functional requirements, and a deliberately heavy non-functional-requirements section, which is the emphasis of this project.
3. `docs/20_spec.md` : the source-of-truth specification. System use cases and the entity model. Everything downstream traces to an ID here.
4. `docs/30_plan.md` : phased delivery plan (local, then AWS), invariants, and acceptance tests mapped to use cases.
5. `docs/40_tasks.md` : the ordered task backlog for Phase 1 (local).
6. `docs/50_cloud_strategy.md` : the local-first-then-AWS path, why Hugging Face is skipped, and why AWS is the only cloud.
7. `docs/60_panjuta_application.md` : how the reusable patterns from the Panjuta repo harvest apply to this pipeline.
8. `adr/` : the architecture decision records. Both open decisions are now locked: ADR-0002 selects the Python consumer, and ADR-0003 selects the cheapest AWS shape (ephemeral local containers, S3 with Iceberg, DynamoDB serving store) under a 50 dollar monthly ceiling. ADR-0004 is the non-functional invariant law; ADR-0005 records the Terraform setup-and-teardown design that keeps costly resources from lingering.

## Naming

Repo name: `climate-impact-index`. Python package: `climate_index`. These names are brand-neutral and carry no vendor tokens, consistent with the portfolio clean-commit-trail rule.

## Traceability contract

Every functional requirement (FR-*), non-functional requirement (NFR-*), use case (UC-*), entity (E-*), invariant (INV-*), and acceptance test (AT-*) has a stable ID. Downstream code, tests, and infrastructure reference these IDs. A change to behavior starts as an edit to the ID that owns it, not as a code patch.
