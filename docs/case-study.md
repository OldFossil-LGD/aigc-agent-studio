# Case study

## Problem and intended users

A filmmaker may request a five-second vertical paper-cut shot with a fixed overhead camera and rain only. A handoff can preserve the duration but lose the camera, style, silence requirements or requested endpoint. Storyboard review also needs to distinguish a receiver taking an object from a giver initiating a handover. The skill supports those creative tasks as well as planning for production.

The intended users are independent filmmakers and creative agent operators. Interviews, creator studies and production-effect measurements have yet to be carried out.

## Requirements and workflow

The creator uses natural language. The Agent forms an internal task record, distinguishes user facts from proposals and chooses the appropriate endpoint: script/review, assets, storyboard, prompts, reverse analysis or separately authorized production. Python interfaces make the internal handoff reproducible.

The Agent considers each library domain, then reads the relevant sources and exceptions in full. It records the choices needed for the task and checks them against the output. Work with unresolved requirements stays a draft.

## Implementation changes

| Observed problem | Change | Check and remaining limit |
| --- | --- | --- |
| Baseline compilation could create a Final with engineering PASS/READY without current reading/review evidence | Actual delivery entry now creates Draft by default; a current review record is required for Final | Missing-review CLI and task/output/source/session tampering regressions; consistency is not proof of comprehension |
| New creative keys could disappear from the internal handoff | Unknown creative fields now raise a validation error | Dedicated unknown-field tests; Agent extraction of a natural-language brief still needs review |
| LibTV and a digest test used one machine's paths | Resolve explicit environment/PATH/home executable and repository-relative test path | Mocked adapter/resume cases and real relocated offline demo; live LibTV was not executed |
| Fidelity regression imported a helper that was absent | Added narrowly scoped graph mutations and replaced private fixtures with labelled synthetic graphs | Regression evaluates the manifest's scale/schema/lineage failures; no film reconstruction claim |
| Publication material mixed private paths, historical evidence and uncertain licensing | Normalised public paths, kept original private hashes, added rights ledger and notices | Recovery-index hash verification and local publication scan; owner clearance remains necessary |

The first diagnostic full-suite attempt failed because existing tests still expected an unconditional Final and default CLI success. Those rendering/constraint tests were migrated to explicit drafts without removing their semantic assertions. Separate tests now enforce the final-delivery boundary. Failed runs remain in the private work records. The public verification receipt identifies the runtime and reference sources covered by its checks.

## A stationary scarf

A natural-language request for a still, silent woodcut empty shot exposed overly broad prompt defaults. The template requested picture change, could exclude the scarf as clothing or reject explicitly allowed offscreen speech, and could request undeclared human voice. The [regression logs](evidence/empty-scene-regression/) record the failures and repair. Minimal empty-scene wording repairs preserve declared objects, action and sound boundaries. Five focused regressions cover static and moving scenes, props and offscreen/unspecified voices; four failed before repair and all five passed after it.

The source review also failed. A reply marked ready quoted text absent from the source. The formal CLI rejected it without writing Final. After the source excerpts and their scope were corrected, the text passed the evidence review. The run records identify operator assistance and the evaluated source version. Source selection and finished media still require separate evaluation. [Related work](RELATED_WORK.md) describes the overlap with other projects.

## Architecture and trade-offs

The Agent interprets the natural-language brief. Structured validation checks supported values and their sources, while a reviewer checks the completeness of that interpretation. A static source catalog makes unregistered/changed files visible, while applicability and dependency reading require Agent judgement. A review record binds the task, source captures, choices and output. Artistic quality is reviewed separately.

The offline prompt compiler demonstrates one part of the filmmaking workflow. Platform execution, media review and finishing require their own authorization and evidence. A text critique need not become a film-generation job.

## Evaluation and next step

See [DEMO.md](DEMO.md), [EVALUATION.md](EVALUATION.md) and the [verification receipt](evidence/verification.json). Automated regressions cover software behavior. The synthetic cross-mode evaluation in EVALUATION.md includes failed first drafts and labelled independent revisions. Autonomous creative reliability still needs evaluation. A future creator review should test whether the workflow preserves all requirements without unnecessary questions, and whether selected craft choices improve an actual artifact. That study has not been performed.

## Contributions

The project was independently developed using AI-assisted coding. The [contribution notes](CONTRIBUTIONS.md) describe project decisions, implementation assistance and upstream work.
