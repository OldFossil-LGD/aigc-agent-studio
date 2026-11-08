# Evaluation

## What is measured now

The automated suite checks software behavior, including structured intent validation, explicit supported constraint semantics, camera/style/sound/state propagation, graph contracts, source planning and read evidence, final-delivery gating, path resolution, and synthetic graph fidelity. The [verification receipt](evidence/verification.json) records the commands, environment and outcomes. The [demo receipt](evidence/demo.json) contains one successful engineering draft and two expected rejections.

New review-gate cases bind a task, canonical output, catalog, full current source captures and decisions. They reject missing or dismissed mandatory domains, generic rationale without task grounding, missing requirements, false source/output excerpts, partial captures, wrong sessions and changed tasks/outputs. A positive fixture reaches REVIEW_EVIDENCE_READY while keeping creative_quality_verified, media_quality_verified and generation_authorized false. These fixtures exercise the checks. Model reading comprehension needs separate evaluation.

The fidelity manifest uses synthetic nodes and edges to expose over/under-building, schema mismatch and missing lineage. Visual and narrative similarity require separate media review. The original project fixtures remain private.

## Baseline and iteration

The baseline entry could label a prompt Final with engineering PASS/READY and no current source/decision review. The missing-review regression now requires a draft and nonzero default CLI exit. The fidelity regression formerly stopped at a missing helper import; the standalone CLI now runs its manifest. Machine-specific path use was replaced with environment/PATH/home resolution and repository-relative test paths. Unknown creative fields now fail validation.

Private work records include red/green trials, unsuccessful Hermes attempts and an early full-suite failure. Targeted test counts overlap with the full suite. Logs retain the warnings, and remote CI remains unverified.

## Cross-mode text evaluation

[Fixed briefs](evidence/cross-mode/briefs.json), [original Hermes drafts](evidence/cross-mode/hermes_first.json), [rework outputs](evidence/cross-mode/hermes_rework.json), [explicitly Codex-reviewed revisions](evidence/cross-mode/codex_reviewed.json), [source versions](evidence/cross-mode/source_versions.json) and [independent audit](evidence/cross-mode/audit.json) are retained. The cases cover a stylized empty shot, silence versus no-dialogue, fixed two-person framing, active handover, physical state continuity, two-shot story/editing/sound, limited copy reversal and local self-take review.

The first outputs were generated without the later audit feedback. Codex supplied the routed source bundles in full. The evaluation therefore covers work with supplied sources. The errors included fragments being implicitly moved back to a table and a two-shot cut placed at shot2's end. Several source/output excerpts were paraphrases rather than literal evidence. Targeted Hermes rework improved the text but retained some evidence-format errors; one job returned empty text with exit1. The original failures remain in the records. Codex then made labelled independent revisions, including the two cases without usable rework output.

The [evidence-gate run](evidence/cross-mode/gate_results.json) accepted seven independently revised text records for evidence consistency. The limited-reverse case remained rejected because actual accessible copy data was missing. The eighth workflow was rejected at that check. Every result keeps creative_quality_verified, media_quality_verified and generation_authorized false. Source captures retain the bytes supplied in the recorded queries. They support consistency checks. Model attention and comprehension remain outside this evaluation. Archived catalog bindings are evaluation evidence, not approvals reusable after source/task/output changes.

A separate eight-case [local-review revision probe](evidence/cross-mode/local_review_revision.json) retains active handover versus self-take, already clear possession, sealed-glass impossibility, ambiguous envelope identity and unique-object boundaries. It evaluates synthetic text. Playback and audience testing remain separate.

## Empty-scene regressions

A static woodcut empty shot exposed template instructions for picture change and related empty-scene defaults. Four regression cases failed before repair. The moving-empty-scene preservation case already passed. All five then passed, and 81 affected cases passed with overlapping counts. Actual [red](evidence/empty-scene-regression/empty_scene_all_red.txt), [green](evidence/empty-scene-regression/empty_scene_green.txt) and [affected-suite](evidence/empty-scene-regression/targeted_after_fix.stderr.txt) logs are retained. The associated operator-assisted review history and its original catalog bindings are archived privately.

## Creator study protocol (not yet performed)

Use approved or synthetic briefs covering text-only storyboard review; character performance and active handover; a stylized empty shot with sound exclusions; a multi-shot state change; lighting/material choices; local rework; reverse analysis with limited access. For each brief:

1. Independently list explicit user locks, proposals, unresolved facts and the requested endpoint.
2. Have the Agent consider all domains, choose applicable full sources/dependencies/exceptions, and produce its task-bound decisions and actual artifact. Do not provide a fabricated review receipt.
3. A creator reviews whether every applicable requirement is preserved, sources actually support choices, irrelevant rules were dismissed for good reasons, and questions do not repeat known facts.
4. Deliberately mutate the task, source capture and final text; check that the relevant evidence/semantic gate catches inconsistency. Record misses as well as correct rejections.
5. Assess causal clarity, creative usefulness and unnecessary constraints separately from machine status. If media is absent, label motion/contact/sound effects unverified. Media evaluation requires separately approved generation and actual playback.

Record brief IDs, source versions, artifacts, independent annotations and unresolved disagreements. Sample counts, success rates, audience benefit, cost reduction and finished-film scores require data from that study. The workflow can detect missing records and several forms of inconsistency. Model reasoning remains a separate evaluation problem.

## Comparison boundary

The Agent skill adds context routing and craft workflow instructions to the engineering tools; a raw compiler invocation exercises only declared structured inputs. A source catalog improves discoverability, but selected metadata is not equivalent to full source reading. No head-to-head benchmark against another creative system, unassisted creator or film model was conducted. [Related work](RELATED_WORK.md) compares inspected upstream documentation with implemented local features. Its scope is the documented design. Competing systems were not run.
