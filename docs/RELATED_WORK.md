# Related work

This comparison uses upstream README snapshots inspected on 2026-10-26 and 2026-10-27. It covers documented interfaces and scope. The upstream systems were not run, and quality, speed, cost and finished-film performance remain unmeasured. The source/rights ledger records attribution and unresolved provenance.

| Project / primary source | Documented focus | Overlap and this project's emphasis | Evidence limit |
| --- | --- | --- | --- |
| [Hell Grind AIGC Skill](https://github.com/renmu2017/Hell-Grind-AIGC-Skill/blob/main/README.md) | Model-independent prompt work, explicit creative locks, production records and failure diagnosis, with references and local tools | This is an acknowledged base, so locks and traceable iteration are not claimed as original inventions here. AIGC Agent Studio emphasizes its implemented task/output/source-bound final-delivery interface across planning endpoints. | These are upstream README statements. No claim is made that the upstream lacks an equivalent gate. |
| [AIGC Film Studio](https://github.com/ifeihong/aigc-film-studio/blob/main/README.md) | A filmmaking workflow connecting briefs/scripts, assets, shots, prompts and consistency practices | The filmmaking scope overlaps. Here, the runnable demo explicitly separates engineering drafts, reviewed text/plans and separately authorized platform/media work. A review ends at the requested critique or revision. | The upstream's production/effect claims were not reproduced or adopted as our own results. |
| [screenwriting-skills](https://github.com/jtydhr88/screenwriting-skills/blob/main/README.md) | A collection of writing/dramaturgy craft skills with a natural-language, multilingual interface | Script craft remains part of this studio's scope. This repository also exposes structured production handoffs and a shared evidence boundary for prompt and text/planning artifacts. | Documentation-level scope comparison; no head-to-head creative assessment was conducted. |

## Handoffs and review

Creative locks are only useful if they survive the handoff. The [intent interface](../scripts/intent_handoff.py) distinguishes explicit values and proposals, while [independent constraint checking](../scripts/verify_delivery_semantics.py) inspects the actual supported output. A reviewer can inspect how supported constraints reach the output.

The [delivery entry](../scripts/compile_intent_delivery.py) and [shared review gate](../scripts/delivery_review.py) require current task/output/source evidence and an explicitly empty current unresolved list before formal delivery. They report missing evidence to the operator. Artistic quality requires review of the work.

The [catalog](../references/knowledge-catalog.json) makes the public tree discoverable; the Agent still considers relevance, direct dependencies and exceptions. Requiring every book on every shot would add context without establishing that the right craft choice was made. Selected-source bytes and short decisions make review possible, while comprehension remains an evaluation question.

These choices let a reviewer inspect the brief, the sources used and the resulting artifact in the same workflow.

## Choosing a workflow

For a writing-only task, start with the relevant script craft and stop at the requested critique or revision. For a prompt task, use the natural-language Agent intake and the offline handoff/compiler boundary. For full production, add separately approved platform execution and actual media review. These endpoints need different evidence; a software regression or text critique cannot stand in for playback.
