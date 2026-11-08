# Reproduce the offline demo

This demo compiles a synthetic English brief into a prompt draft. Some compiler labels and boilerplate are still in Chinese. Creators normally give an Agent a natural-language brief. The structured sample lets you inspect the handoff directly.

## Setup and successful draft

Install the requirements in your Python environment, then run this from the project root.

~~~bash
python scripts/compile_intent_delivery.py samples/papercut_empty_shot_intent.en.json --out out/demo --draft
~~~

The [run receipt](evidence/demo.json) records a clean virtual environment and a relocated folder with spaces in its name. The R2 run used only the requirements dependencies, a system-only PATH and an absent LibTV binary. The [generated draft](evidence/13_Draft_Prompt.md) retains its original output text. Status values and exit codes are recorded with the run.

The run returned exit 0 with gate_status PASS, contract_status READY, verification_status PASS and delivery_readiness DRAFT_REVIEW_REQUIRED. File 13_Draft_Prompt.md exists; 13_Final_Prompt.md does not. The draft contains the five-second 9:16 setting, paper-cut style, fixed overhead view, upper-right negative space and rain-only instruction.

The output folder contains these files.

- 01_production_contract.json: values and source/lock provenance.
- 04_prompt_packages.jsonl: canonical prompt packages.
- 12_intent_delivery_package.json: current draft status and review evidence boundary.
- 13_Draft_Prompt.md: actual copyable draft, explicitly labelled as such.
- 14_delivery_verification.json: independent supported-constraint check.

The English source is [the sample](../samples/papercut_empty_shot_intent.en.json). The validator checks supported declared requirements. Review the resulting text for creative quality.

## Missing review is blocked

~~~bash
python scripts/compile_intent_delivery.py samples/papercut_empty_shot_intent.en.json --out out/review-required
~~~

This returns exit 1 and DRAFT_REVIEW_REQUIRED. It leaves a draft for review and writes no current Final. Valid formal review is documented in [delivery-review.md](../references/delivery-review.md). Unit tests use mechanical receipts to exercise the positive and tamper paths; those fixtures are not a filmmaker's approval.

## Invalid input is explained

For an invalid-input example, save this as out/invalid-intent.json.

~~~json
{"intent_format":"intent-handoff/v1","unexpected_camera_rule":"unhandled requirement"}
~~~

~~~bash
python scripts/compile_intent_delivery.py out/invalid-intent.json --out out/invalid-output --draft
~~~

This returns exit 2 with intent handoff invalid, unmapped task fields, and unexpected_camera_rule. Use declared decisions/constraints or keep the requirement unresolved. Neither a Draft nor a Final is delivered. Do not silently move unknown creative requirements into audit metadata: they belong in declared decisions/constraints or remain unresolved.

## What to review

Read the output against the brief, including its camera, sound and timing requirements. A deliberate camera, sound, duration or provenance mutation should fail the relevant regression. Review [EVALUATION.md](EVALUATION.md) for that automated scope and the separate, still-needed creative evaluation. No model request, LibTV write, media generation, ignition, upload or paid platform probe is part of these commands.
