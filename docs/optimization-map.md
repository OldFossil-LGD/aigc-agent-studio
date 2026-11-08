# Skill Corpus Optimization Map (2026-10-17)

## Inventory at the recorded date
- Registers (references/*.md, top level): 241
- Scripts (scripts/*.py): 55 (51 referenced somewhere in *.md; 4 unreferenced: __init__.py, layout_build_plan.py, make_fidelity_fixtures.py, shot_strips.py)
- Gate status at map time: lib_health exit=0; lib_doctor exit=0; audit_prompt index/claims exit=0; 11 validators exit=0.

## Near-limit registers (>=290 lines)
style-library-cinema-part3.md(299)
segmented-shot.md(299)
run-sheet.md(299)
quality-layer.md(299)
libtv-official-qa.md(299)
libtv-official-qa-part7.md(299)
libtv-model-params.md(299)
key-decisions.md(299)
governance-law-part2.md(299)
writing-methods.md(298)
updream-workflow.md(298)
platform-matrix.md(298)
pitfalls.md(298)
libtv-web-api-shapes.md(298)
libtv-node-topology.md(298)
libtv-canvas-nodes.md(298)
camera-movement-library.md(298)
skin-light-physics.md(297)
shot-linkage.md(297)
shot-craft.md(297)
script-format.md(297)
governance-law.md(297)
storyboard-frame.md(296)
libtv-realtime-and-fe-tools.md(296)
feasibility.md(296)
block-playbook-asset.md(296)
blind-reverse-runbook.md(296)
style-sources-a.md(294)
libtv-cli-env-binding.md(294)
style-library-genre.md(292)
production-ledger.md(292)
run-sheet-part2.md(291)
shot-orchestration.md(290)
color-science.md(290)

## Planned maintenance
1. Split the 6 registers at 299 lines into part2 files, preserving mount points.
2. Merge duplicate source-data rows only after lib_health confirms zero rule repeats.
3. Archive the 4 unreferenced scripts only after a manual reference check.
4. Keep all changes gated by lib_health/lib_doctor/audit_prompt/validators.

## Operating rule
At the time of this map, the next planned step was to split the 6 registers at 299 lines and verify library health before further feature work.
