# 60 Applying the Panjuta Harvest to This Project

Version: 0.1.0
Sources: `Research/Panjuta_Article/Panjuta_Article.txt` (the eight-repo list) and `Research/Panjuta_Article/Panjuta_Article_workflow.txt` (the council harvest that extracted reusable patterns). Several of these patterns are already ingested in the knowledge base under `agents.md` and `system_design.md`.

The Panjuta article is a list of eight open-source repositories around agentic and AI-assisted development (ECC, GStack, Matt Pocock Skills, Graphify, GBrain, SkillSpector, OpenMontage, DeerFlow). A prior council harvest read all eight and distilled a small number of patterns that generalize beyond their original repos. This project is a deterministic data-engineering pipeline with no model in the hot path, so most repo-specific content does not apply. Three patterns do apply directly, and one meta-lesson shapes the process.

## Pattern 1: an analyzer surfaces candidates, a deterministic gate decides

The strongest signal in the harvest was a convergence across several unrelated authors: prefer a deterministic structural check over a model judgment, and split the roles so that an analyzer surfaces candidates while a deterministic gate or a human operator makes the decision.

Application here. The data validation path (UC-2, FR-3, NFR-DQ1, INV-3) is built exactly this way. The schema and range checks surface anomalies as flagged candidates with a reason code. A deterministic gate, not any model, decides accept or quarantine. Nothing about acceptance is probabilistic or model-driven. This keeps the compute path deterministic and testable, which matches the existing knowledge-base entry "Deterministic Compute, LLM Writes: the Multi-Tool Analyst Pattern" (agents.md).

## Pattern 2: provenance-graded confidence

Graphify contributed provenance-graded edge confidence: label a derived fact by how it was obtained, on a scale such as EXTRACTED, INFERRED, AMBIGUOUS, so that a consumer can calibrate trust. This is in the knowledge base as "Provenance-Graded Edge Confidence" (system_design.md).

Application here. Each aggregate row carries a confidence grade (E-5, NFR-DQ2, UC-3). MEASURED when both stream types are present in the window, INFERRED when a component is imputed from a single type, AMBIGUOUS when input is sparse below a threshold. The dashboard shows the grade next to the value (UC-5), so a viewer never reads an under-supported index as if it were fully measured. This also gives graceful degradation (NFR-R4): a thin window yields a graded-down record rather than a dropped one.

## Pattern 3: a cheap deterministic check before expensive stochastic or irreversible spend

OpenMontage contributed a pre-generation gate: run a cheap deterministic check upstream of an expensive step and block before spending. The novelty the harvest noted is the cost and time inversion, putting the cheap check before the expensive action rather than validating after the fact.

Application here. The local-first rule and the deterministic pre-deploy gate (NFR-C1, UC-7, and `50_cloud_strategy.md`) are this pattern applied to cloud deployment. Provisioning cloud infrastructure is the expensive, slow, spend-incurring step. Before it runs, a cheap check confirms the local smoke marker exists, dependencies are single-sourced, and the target config parses. The expensive step is gated on the cheap one (AT-9). The harvest also flagged that such a gate's thresholds are only trustworthy once shown to predict the expensive failure, so the gate's checks are concrete and verifiable, not heuristic guesses.

## Meta-lesson: propose before you mutate, and keep the source of truth clean

The harvest workflow itself modeled a discipline worth carrying: it produced proposals and impact analyses first and wrote nothing to the knowledge base until approved, and it de-duplicated candidates against what already existed before adding anything. That read-only-until-approved posture is the same shape as this spec set, which produces the source-of-truth documents first and defers all code and all cloud spend to gated later phases.

## What does not apply

The video pipeline (OpenMontage), the skill-authoring prose (Matt Pocock Skills), the meeting and notes knowledge system (GBrain), the multi-agent coordination frameworks (DeerFlow, GStack, ECC), and the skill security scanner (SkillSpector) target agentic and content workflows. This project has no agent in its runtime and no model in its compute path, so those repos are noted and set aside rather than force-fit. One item is worth a later look independent of this project: SkillSpector's security scanning is relevant to the portfolio's tooling supply chain, not to this pipeline's runtime.

## Traceability

The applied patterns land on concrete IDs: NFR-DQ1 and INV-3 (Pattern 1), NFR-DQ2 and E-5 (Pattern 2), NFR-C1 and UC-7 (Pattern 3). Each is verifiable through the acceptance tests in `30_plan.md`, so the borrowed patterns are held to the same evidence bar as the rest of the system.
