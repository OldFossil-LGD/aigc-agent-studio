# Creative consideration and delivery evidence

Use this interface before a final prompt, text review, asset plan, reverse analysis or rework delivery. It is not a model-thinking certificate or generation approval.

## Scope and discovery

1. Use knowledge_catalog.py to inspect the current domain inventory and candidate sources. It includes active references, mixed/history/example sources, code/schema and publication support. Metadata classification is a discovery hint, not authority or proof that every file was read.
2. Form the task intent from the complete user brief. Consider every catalog domain as applicable, not applicable (with a task-specific reason), or unresolved. Creative requirements belong in declared decisions/constraints/craft fields; audit/metadata fields are not prompt instructions. Unknown creative fields must not be silently discarded.
3. Select applicable original sources and their actual dependencies and exceptions. Use knowledge_routes.plan_context with all applicable features together and extra_refs for additional relevant material. Check related books and direct exceptions while reading; do not replace this with keyword matching or a catalog count.
4. Read selected original text fully. Keep same-session full captures with the existing read-receipt interface. Hashes and copied bytes demonstrate source consistency, not comprehension.
5. Record short, task-grounded decision reasons and where they appear in the real output. Keep proposed design separate from locked user facts. Review the actual output against constraints and artistic intent; do not treat the engineering checker as an artistic judge.

The catalog is static between deliberate maintenance reviews. A new, removed or changed source invalidates it. Never automatically rebuild it during a creative task merely to get a green result. Maintainers can inspect classifications and run:

    python scripts/knowledge_catalog.py --build

All catalog domains must be considered; this does not mean every task reads every book. Unrelated material stays available for another task. Historical observations and examples do not become universal craft defaults. The user never has to fill in JSON.

## Draft first, final only with current evidence

A reproducible offline draft requires no model API key or LibTV installation:

    python scripts/compile_intent_delivery.py samples/papercut_empty_shot_intent.en.json --out out/demo --draft

It creates 13_Draft_Prompt.md and reports DRAFT_REVIEW_REQUIRED. The same command without --draft or a valid review returns nonzero and creates no current Final. Engine PASS and contract READY refer to declared engineering constraints only.

For a formal prompt delivery, the Agent supplies its current creative-review/v1 record:

    python scripts/compile_intent_delivery.py intent.json --out out/reviewed --review review.json --capture-root .context_reads --session current-session

The review contains:

- review_format: creative-review/v1.
- unresolved: an explicit empty list for formal delivery. Missing or nonempty current-task facts/decisions block delivery. Later design and unverified media effects stay separate; a text-only conclusion does not require media effects to be verified. Local storyboard review categories follow `direction-reasoning.md` section 9.
- task_sha256: task_fingerprint(intent), using scripts.delivery_review.
- artifact_sha256: artifact_fingerprint of a map whose prompt_packages value is canonical JSON for the actual compiled packages (ensure_ascii=False, sort_keys=True, separators comma/colon, no extra spaces).
- catalog_sha256: the current catalog fingerprint.
- context_plan and read_receipt: the real existing source plan and same-session full capture evidence, bound to the complete current intent.
- consideration: one domain/status/reason record per catalog domain. Applicable intent features cannot be dismissed as not applicable; unresolved consideration is not ready.
- decisions: requirement_ids from context_plan.coverage; rationale that cites concrete task_evidence; source_evidence with selected path and exact original quote; applied_to with artifact name and text actually present in that artifact.

Source quotes and applied output fragments must be literal contiguous excerpts, including their original punctuation. A reconstructed summary is not an excerpt; put paraphrases in the rationale. The actual artifact must preserve causal/state constraints, not just mention requirement words.

The gate rejects changed tasks or outputs, stale catalogs/plans, truncated captures, missing requirements/domains, generic approval text without task grounding, fabricated quotes and missing output mappings. Its result REVIEW_EVIDENCE_VALID means consistency of these evidence records. Artistic judgement and media quality remain unverified by the machine. Tests using mechanical receipts are explicitly test fixtures, not evidence that an agent understood a film.

Independent constraint verification must also pass before Final is written. A previous recognised generated Final is archived on an unreviewed rerun; an unrecognised user file is not silently overwritten. Legacy test/recovery files named Final are historical or mechanical fixtures, not current reviewed delivery evidence.

## Text-only review and other planning endpoints

Pure screenplay/storyboard critique does not require producing media or running the production compiler. Form a task object with goal, a supported context profile (for example rework for local review), and requirements records with id/text; obtain an appropriate source plan with extra_refs as needed. Bind the real text artifact and use:

    python scripts/delivery_review.py --task task.json --artifact review.md --review evidence.json --capture-root .context_reads --session current-session

Here the artifact map uses the actual basename review.md as its key. The same current-task/source/decision evidence rules apply. An unsupported endpoint remains unsupported; do not silently convert it into a full film. Lower-level compilers and renderers remain engineering tools and cannot be presented by the Agent as evidence-reviewed creative delivery on their own.

## Non-negotiable boundaries

Source-evidence readiness does not establish private model reasoning, artistic correctness, full natural-language understanding or actual media effects. Cross-domain behavioural review is still necessary. No state in this protocol authorises platform writes, paid generation, ignition or re-ignition. Use current platform readbacks for platform facts; preserve user locks and unresolved matters.
