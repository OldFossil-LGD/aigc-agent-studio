# Production compiler implementation plan

> This is an earlier implementation plan. Its tasks and expected test results describe the work planned at that time. Checkboxes (`- [ ]`) track the steps.

The goal was to turn `aigc-agent-studio` from a reference library into a production compiler that converts simple inputs into asset graphs, shot graphs, prompt packages, platform plans, and capability gates.

The proposed architecture keeps existing `references/` as lookup knowledge. Add schemas, compiler scripts, and gates under `scripts/` plus one router document. The compiler emits machine-readable artifacts; platform execution remains a separate adapter and never ignites without approval.

The proposed stack uses Python 3.12 standard library, JSON Schema, Markdown routing, existing LibTV CLI.

Design specification `<HOME>/Documents/Codex/2026-10-04/wo/outputs/放殃_成片逆推_20261008/05_skill生产化改造设计.md`

## Constraints

- Do not delete or rewrite existing validated `references/` content.
- Do not ignite, generate, upload, export, or modify source canvases.
- Node count is not an acceptance target; production-role coverage is.
- Every compiler output must be machine-readable JSON or JSONL.
- Unknown intent must become an explicit question or an explicit assumption, never silent invention.
- Regression must cover W1, W2, W3, and the 放殃 source-copy metrics.
- `source_replica` must run `scripts/source_fidelity_lint.py`.

## Review criteria

- A simple input that omits duration/style: compiler must either ask one question or record explicit defaults.
- A 2-minute multi-shot script: shot graph must contain production roles, not only storyboard/prompt/video.
- Reused character or scene: asset graph must require an iteration plan or record an exemption.
- No ignition: every generated plan must remain runnable-by-agent but not executed.
- Existing source canvas: source fidelity must not be inferred from node names alone.

---

### Task 1: Production Contract Schema And Compiler

**Files:**
- Create: `schemas/production_contract.schema.json`
- Create: `scripts/compile_production_contract.py`
- Create: `tests/test_compile_production_contract.py`

**Interfaces:**
- Consumes: JSON input containing `goal`, `duration_sec`, `aspect_ratio`, `shots`, `entities`, `delivery`.
- Produces: `compile_contract(data: dict) -> dict`, with keys `production_contract`, `assumptions`, `questions`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.compile_production_contract import compile_contract

def test_compile_contract_fills_required_production_fields():
    result = compile_contract({"goal": "两分钟苗族风筝短片", "duration_sec": 120})
    contract = result["production_contract"]
    assert contract["duration_sec"] == 120
    assert contract["production_mode"] in {"film_reverse", "production_build", "source_replica"}
    assert contract["delivery"]["ignition_allowed"] is False
    assert result["assumptions"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compile_production_contract.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `compile_contract`**

Create the schema and compiler. The compiler fills duration defaults only when absent, records every default in `assumptions`, and emits `questions` for conflicting mode/style/delivery requests.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compile_production_contract.py -v`  
Expected: PASS.

---

### Task 2: Asset Graph Compiler

**Files:**
- Create: `schemas/asset_graph_plan.schema.json`
- Create: `scripts/compile_asset_graph.py`
- Create: `tests/test_compile_asset_graph.py`

**Interfaces:**
- Consumes: `production_contract`.
- Produces: `compile_asset_graph(contract: dict) -> dict`, with `assets`, `iteration_chains`, `exemptions`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.compile_asset_graph import compile_asset_graph

def test_reused_character_requires_iteration_chain():
    contract = {
        "entities": [{"id": "char_01", "kind": "character", "reuse_count": 3}],
        "shots": [{"id": "shot_01"}],
    }
    plan = compile_asset_graph(contract)
    assert plan["iteration_chains"]
    assert plan["assets"][0]["requires_iteration"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compile_asset_graph.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `compile_asset_graph`**

Create anchors for every entity, add state versions for non-default states, and add `anchor -> refine_a -> refine_b` chains when reuse/state/precision triggers are present.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compile_asset_graph.py -v`  
Expected: PASS.

---

### Task 3: Shot Graph Compiler

**Files:**
- Create: `schemas/shot_graph_plan.schema.json`
- Create: `scripts/compile_shot_graph.py`
- Create: `tests/test_compile_shot_graph.py`

**Interfaces:**
- Consumes: `production_contract`, `asset_graph_plan`.
- Produces: `compile_shot_graph(contract: dict, assets: dict) -> dict`, with `shots`, `nodes`, `edges`, `groups`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.compile_shot_graph import compile_shot_graph

def test_each_shot_has_required_production_roles():
    contract = {"shots": [{"id": "shot_01", "duration_sec": 5, "risk": "high"}]}
    assets = {"assets": []}
    graph = compile_shot_graph(contract, assets)
    roles = {node["role"] for node in graph["nodes"] if node["shot_id"] == "shot_01"}
    assert {"storyboard", "prompt", "scene_ref", "identity_ref", "composition_ref", "candidate_image", "refined_image", "video_candidate", "selection", "audio", "assembly"}.issubset(roles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compile_shot_graph.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `compile_shot_graph`**

For each shot, emit the required roles. High-risk shots get two image candidates and two video candidates; low-risk shots get one of each and record the reduced candidate reason.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compile_shot_graph.py -v`  
Expected: PASS.

---

### Task 4: Prompt Compiler

**Files:**
- Create: `schemas/prompt_package.schema.json`
- Create: `scripts/compile_prompt_packages.py`
- Create: `tests/test_compile_prompt_packages.py`

**Interfaces:**
- Consumes: `production_contract`, `asset_graph_plan`, `shot_graph_plan`.
- Produces: `compile_prompt_packages(contract: dict, assets: dict, graph: dict) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.compile_prompt_packages import compile_prompt_packages

def test_video_prompt_package_contains_required_blocks():
    contract = {"duration_sec": 120, "visual_style": "写实纪录片"}
    assets = {"assets": []}
    graph = {"nodes": [{"id": "shot_01_video_a", "role": "video_candidate", "shot_id": "shot_01"}]}
    packages = compile_prompt_packages(contract, assets, graph)
    package = next(p for p in packages if p["node_id"] == "shot_01_video_a")
    for block in ["material_roles", "continuity", "visual", "action", "sound", "negative", "duration"]:
        assert block in package["blocks"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compile_prompt_packages.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `compile_prompt_packages`**

Compile separate prompt types for assets, storyboard, image candidates, image refinement, video, sound, and assembly. Every package must include required blocks and unresolved-placeholder checks.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compile_prompt_packages.py -v`  
Expected: PASS.

---

### Task 5: Production Capability Gate

**Files:**
- Create: `scripts/production_capability_gate.py`
- Create: `tests/test_production_capability_gate.py`

**Interfaces:**
- Consumes: contract, asset plan, shot graph, prompt packages.
- Produces: `evaluate(contract: dict, assets: dict, graph: dict, prompts: list[dict]) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.production_capability_gate import evaluate

def test_missing_candidate_role_fails_gate():
    result = evaluate(
        {"production_mode": "production_build"},
        {"assets": []},
        {"shots": [{"id": "shot_01"}], "nodes": [{"shot_id": "shot_01", "role": "storyboard"}]},
        [],
    )
    assert result["status"] == "FAIL"
    assert any(item["code"] == "MISSING_SHOT_ROLE" for item in result["failures"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_production_capability_gate.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `evaluate`**

Gate production-role coverage, asset iteration exemptions, candidate policy, prompt completeness, placeholder/order alignment, no-ignition flags, and source fidelity when mode is `source_replica`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_production_capability_gate.py -v`  
Expected: PASS.

---

### Task 6: One-Command Production Compiler And Regression

**Files:**
- Create: `scripts/compile_production.py`
- Create: `scripts/production_regression.py`
- Create: `tests/test_compile_production_pipeline.py`
- Modify: `SKILL.md`
- Modify: `references/source-fidelity-mode.md`

**Interfaces:**
- Consumes: one simple JSON input.
- Produces: `01_production_contract.json`, `02_asset_graph_plan.json`, `03_shot_graph_plan.json`, `04_prompt_packages.jsonl`, `05_platform_execution_plan.json`, `06_gate_results.json`, `07_regression_ledger.json`.

- [ ] **Step 1: Write the failing test**

```python
import subprocess, json, tempfile, pathlib

def test_compile_production_pipeline_writes_all_artifacts(tmp_path):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps({"goal": "两分钟测试片", "duration_sec": 120, "shots": [{"id": "shot_01", "duration_sec": 4}]}), encoding="utf-8")
    out = tmp_path / "out"
    subprocess.run(["python", "scripts/compile_production.py", str(inp), "--out", str(out)], check=True)
    assert (out / "01_production_contract.json").exists()
    assert (out / "04_prompt_packages.jsonl").exists()
    assert (out / "06_gate_results.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compile_production_pipeline.py -v`  
Expected: FAIL because the pipeline entrypoint does not exist.

- [ ] **Step 3: Implement the one-command pipeline**

Wire Tasks 1 through 5 in order. Write all artifacts. Exit non-zero when gate status is FAIL. Update `SKILL.md` so the compiler is the primary entrypoint and existing references are lookup material.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compile_production_pipeline.py -v`  
Expected: PASS.

- [ ] **Step 5: Run full regression**

Run: `python scripts/production_regression.py`  
Expected: PASS for W1/W2/W3/source metrics and the two-minute no-source fixture; no ignition.

---

## Plan review

- Spec coverage: all five modules, schemas, gates, regression, and skill routing have tasks.
- Step scan: each task has fail → implement → pass.
- Type consistency: shared object names are consistent across tasks.
- Review focus: default handling, production roles, asset iteration, no-ignition, and source fidelity each have gate coverage.
- Proportion: plan describes interfaces and tests, not full bodies.
