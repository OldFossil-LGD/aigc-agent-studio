import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.grill_ledger import (
    FORMAT,
    QUESTION_BANK,
    build_patch,
    frontier,
    gate,
    validate_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
SCRIPT = ROOT / "scripts" / "grill_ledger.py"
SAMPLE = ROOT / "samples" / "grill_ledger_papercut_prompt.json"
COMPILER = ROOT / "scripts" / "compile_intent_delivery.py"
SAMPLE_INTENT = ROOT / "samples" / "papercut_empty_shot_intent.json"
PRODUCER = ROOT / "scripts" / "compile_production.py"
CONTROL_INTENT = ROOT / "tests" / "fixtures" / "control_matrix" / "control_matrix_intent.json"


def ledger(entries, kind="original"):
    return {"grill_format": FORMAT, "job": {"kind": kind, "request": "test"}, "entries": entries}


def answered(question_id, answer, basis="user_explicit", **extra):
    record = {"id": question_id, "status": "resolved", "basis": basis, "answer": answer,
              "locked": basis == "user_explicit"}
    record.update(extra)
    return record


def prompt_ledger(**overrides):
    """A complete prompt-stop ledger for a 15 秒 9:16 写实单镜."""

    entries = [
        answered("G01", "prompt_only"),
        answered("G03", overrides.get("duration", 15)),
        answered("G04", "9:16"),
        answered("G06", {"style_id": "纪实写实", "register": "photoreal"}),
        answered("G08", "ambience_only"),
        answered("G10", "他最后没有等到；不改成释然。"),
        answered("G02", ["不生成媒体", "不出资产"]),
    ]
    return ledger(entries)


def run(*args):
    proc = subprocess.run(
        [str(PYTHON), "-X", "utf8", "-B", str(SCRIPT), *args],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    return proc


class GrillLedgerModuleTests(unittest.TestCase):
    def test_bank_ids_are_unique_and_ordered_by_asking_priority(self):
        ids = [question["id"] for question in QUESTION_BANK]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 33)
        self.assertEqual(ids[0], "G01")   # delivery target decides which branches exist
        self.assertEqual(ids[1], "G17")   # reverse contract is asked first when it applies

    def test_empty_ledger_frontier_is_only_the_root(self):
        self.assertEqual([q["id"] for q in frontier(ledger([]))], ["G01"])

    def test_frontier_respects_dependency_order(self):
        root = ledger([answered("G01", "full_film")])
        ids = [q["id"] for q in frontier(root)]
        self.assertIn("G03", ids)
        self.assertNotIn("G05", ids)  # needs duration
        self.assertNotIn("G09", ids)  # needs sound mode
        self.assertNotIn("G13", ids)  # needs asset scope, which needs duration
        deeper = ledger([answered("G01", "full_film"), answered("G03", 60)])
        self.assertIn("G05", [q["id"] for q in frontier(deeper)])

    def test_prompt_only_hides_film_and_generation_branches(self):
        ids = [question["id"] for question in frontier(prompt_ledger())]
        for film_only in ("G05", "G07", "G09", "G11", "G12", "G13", "I04"):
            self.assertNotIn(film_only, ids)
        # Optional creative questions stay visible: they are worth asking when
        # their priority clears the mode's threshold.
        self.assertIn("I01", ids)
        self.assertIn("I02", ids)

    def test_an_unasked_optional_question_is_not_a_warning(self):
        entries = [entry for entry in prompt_ledger()["entries"] if entry["id"] != "G02"]
        result = gate(ledger(entries), "prompt")
        self.assertEqual(result["status"], "GRILL_PASS")
        self.assertEqual(result["warnings"], [])

    def test_a_conscious_deferral_stays_visible_as_a_warning(self):
        entries = [entry for entry in prompt_ledger()["entries"] if entry["id"] != "G02"]
        entries.append({"id": "G02", "status": "deferred", "reason": "用户没提范围外"})
        result = gate(ledger(entries), "prompt")
        self.assertEqual(result["status"], "GRILL_PASS_WITH_WARNINGS")
        self.assertEqual(result["warnings"], ["G02"])

    def test_single_shot_reaches_asset_and_ignition_branches(self):
        entries = [answered("G01", "single_shot"), answered("G03", 5), answered("G04", "16:9"),
                   answered("G06", {"style_id": "写实", "register": "photoreal"}),
                   answered("G08", "silent"), answered("G10", "只要压迫感，不落结局。")]
        ids = [q["id"] for q in frontier(ledger(entries))]
        self.assertIn("G12", ids)   # assets matter before generation
        self.assertIn("G14", ids)   # so does the channel
        self.assertIn("I02", ids)   # creative intent is still worth asking
        self.assertNotIn("G07", ids)  # film-stage anchor, not a single shot

    def test_gate_names_every_blocking_material_decision(self):
        result = gate(ledger([answered("G01", "prompt_only")]), "prompt")
        self.assertEqual(result["status"], "GRILL_BLOCKED")
        self.assertEqual(result["blocking"], ["G03", "G04", "G06", "G08", "G10"])

    def test_complete_prompt_ledger_passes(self):
        result = gate(prompt_ledger(), "prompt")
        self.assertEqual(result["status"], "GRILL_PASS")
        self.assertEqual(result["blocking"], [])

    def test_user_explicit_must_be_locked(self):
        entries = [{"id": "G01", "status": "resolved", "basis": "user_explicit",
                    "answer": "prompt_only", "locked": False}]
        self.assertTrue(any("must be locked" in error
                            for error in validate_ledger(ledger(entries))))

    def test_only_user_explicit_may_be_locked(self):
        entries = [answered("G01", "prompt_only", basis="agent_proposal", locked=True)]
        self.assertTrue(any("cannot be locked" in error
                            for error in validate_ledger(ledger(entries))))

    def test_verified_fact_needs_a_real_package_ref(self):
        missing = ledger([answered("G03", 15, basis="verified_fact", locked=False)])
        self.assertTrue(any("verified_fact" in error for error in validate_ledger(missing)))
        wrong = ledger([answered("G03", 15, basis="verified_fact", locked=False,
                                 evidence=[{"type": "platform", "ref": "references/nope.md"}])])
        self.assertTrue(any("does not exist" in error for error in validate_ledger(wrong)))
        good = ledger([answered("G03", 15, basis="verified_fact", locked=False,
                                evidence=[{"type": "library_rule",
                                           "ref": "references/run-sheet.md"}])])
        self.assertEqual(validate_ledger(good), [])

    def test_paid_ignition_refuses_an_agent_proposal(self):
        entries = [answered("G16", "批准一次", basis="agent_proposal", locked=False,
                            note="assumed the user would agree")]
        self.assertTrue(any("user-only" in error for error in validate_ledger(ledger(entries))))

    def test_unsettled_branch_cannot_carry_an_answer(self):
        entries = [{"id": "G03", "status": "open", "answer": 15, "reason": "还没问"}]
        self.assertTrue(any("GRILL_UNRESOLVED" in error
                            for error in validate_ledger(ledger(entries))))
        no_reason = [{"id": "G03", "status": "deferred"}]
        self.assertTrue(any("needs a reason" in error
                            for error in validate_ledger(ledger(no_reason))))

    def test_unknown_question_is_refused_instead_of_dropped(self):
        entries = [answered("G99", "随便")]
        self.assertTrue(any("GRILL_UNKNOWN_QUESTION" in error
                            for error in validate_ledger(ledger(entries))))

    def test_answer_shape_is_checked(self):
        bad_ratio = ledger([answered("G01", "prompt_only"), answered("G04", "wide")])
        self.assertTrue(any("W:H" in error for error in validate_ledger(bad_ratio)))
        for ratio in ("16:9", "9:16", "2.39:1", "1.85:1", "1:1"):
            accepted = ledger([answered("G01", "prompt_only"), answered("G04", ratio)])
            self.assertEqual(validate_ledger(accepted), [], ratio)
        bad_choice = ledger([answered("G01", "series")])
        self.assertTrue(any("not one of" in error for error in validate_ledger(bad_choice)))
        bad_object = ledger([answered("G01", "prompt_only"),
                             answered("G06", {"style_id": "写实", "register": "realistic"})])
        self.assertTrue(any("register" in error for error in validate_ledger(bad_object)))

    def test_reverse_job_needs_its_contract(self):
        first = frontier(ledger([answered("G01", "prompt_only")], kind="reverse"))
        self.assertEqual([question["id"] for question in first][:1], ["G17"])
        entries = prompt_ledger()["entries"]
        self.assertIn("G17", gate(ledger(entries, kind="reverse"), "prompt")["blocking"])
        entries = entries + [answered("G17", {"mode": "copy_reverse", "deliverable": "副本级提示词",
                                              "source_access": "copy_readback"})]
        self.assertEqual(gate(ledger(entries, kind="reverse"), "prompt")["status"], "GRILL_PASS")

    def test_patch_carries_material_decisions_and_never_authorizes(self):
        patch = build_patch(prompt_ledger(), "prompt")
        self.assertEqual(patch["patch_format"], "grill-intent-patch/v1")
        self.assertEqual(patch["task_type"], "prompt_only")
        self.assertEqual(patch["decisions"]["duration_sec"],
                         {"value": 15, "source": "user_explicit", "locked": True})
        self.assertEqual(patch["decisions"]["visual_style"]["value"],
                         {"text": "纪实写实", "register": "photoreal"})
        self.assertEqual(patch["sound"]["mode"], "ambience_only")
        self.assertFalse(patch["authority"]["generation_authorized"])
        self.assertEqual(patch["authority"]["creative_quality"], "NOT_VERIFIED")
        carried = {item["id"] for item in patch["carry_forward"]}
        self.assertIn("G10", carried)
        self.assertNotIn("G03", carried)  # mapped to decisions.duration_sec, not carried twice

    def test_patch_is_deterministic(self):
        self.assertEqual(build_patch(prompt_ledger(), "prompt"),
                         build_patch(prompt_ledger(), "prompt"))


class GrillLedgerCliTests(unittest.TestCase):
    def write(self, payload):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp, ensure_ascii=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_frontier_cli_asks_one_main_question_by_default(self):
        proc = run("--ledger", self.write(ledger([])), "--frontier")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("本轮 frontier 1 题", proc.stdout)
        self.assertIn("G01", proc.stdout)
        two = run("--ledger", self.write(ledger([answered("G01", "full_film")])), "--frontier")
        self.assertIn("本轮 frontier 1 题", two.stdout)

    def test_frontier_cli_full_mode(self):
        entries = [answered("G01", "full_film"), answered("G03", 60)]
        proc = run("--ledger", self.write(ledger(entries)), "--frontier", "--limit", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for question_id in ("G04", "G05", "G06", "G08"):
            self.assertIn(question_id, proc.stdout)

    def test_check_exit_codes(self):
        blocked = run("--ledger", self.write(ledger([answered("G01", "prompt_only")])), "--check")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("GRILL_BLOCKED", blocked.stdout)
        clean = run("--ledger", self.write(prompt_ledger()), "--check")
        self.assertEqual(clean.returncode, 0, clean.stdout)
        sample = run("--ledger", str(SAMPLE), "--check")
        self.assertEqual(sample.returncode, 4)
        self.assertIn("GRILL_PASS_WITH_WARNINGS", sample.stdout)

    def test_stop_cannot_be_inflated(self):
        path = self.write(ledger([answered("G01", "prompt_only")]))
        film = run("--ledger", path, "--check", "--stop", "film")
        self.assertEqual(film.returncode, 2)
        generation = run("--ledger", path, "--check", "--stop", "generation")
        self.assertEqual(generation.returncode, 2)

    def test_patch_cli_writes_the_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "patch.json"
            proc = run("--ledger", str(SAMPLE), "--check", "--patch", str(target))
            self.assertEqual(proc.returncode, 4, proc.stderr)
            patch = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(patch["patch_format"], "grill-intent-patch/v1")
            self.assertEqual(patch["open_items"][0]["id"], "G02")

    def test_invalid_ledger_exits_one_and_says_why(self):
        path = self.write({"grill_format": "grill-ledger/v0", "job": {"kind": "original"},
                           "entries": []})
        proc = run("--ledger", path, "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("GRILL_FORMAT", proc.stdout)

    def test_json_mode_is_machine_readable(self):
        proc = run("--ledger", str(SAMPLE), "--check", "--json")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["gate"]["status"], "GRILL_PASS_WITH_WARNINGS")
        self.assertEqual(payload["gate"]["warnings"], ["G02"])

    def test_self_test_passes(self):
        proc = run("--self-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 failed", proc.stdout)

    def test_bank_dump_exposes_stops(self):
        proc = run("--bank")
        payload = json.loads(proc.stdout)
        by_id = {question["id"]: question for question in payload["questions"]}
        self.assertEqual(by_id["G16"]["stops"], ["generation"])
        self.assertEqual(by_id["G01"]["stops"], ["prompt", "film", "generation"])


class CompilerIntegrationTests(unittest.TestCase):
    """Station 0 is not advisory: the prompt compiler refuses to finalize without it."""

    def compile(self, tmp, *args):
        out = Path(tmp) / "out"
        proc = subprocess.run(
            [str(PYTHON), "-X", "utf8", "-B", str(COMPILER), str(SAMPLE_INTENT),
             "--out", str(out), *args],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        )
        return proc, out

    def test_formal_final_needs_station_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self.compile(tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("GRILL_REQUIRED", proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["grill_status"], "GRILL_REQUIRED")
            self.assertFalse((out / "13_Final_Prompt.md").exists())
            self.assertTrue((out / "13_Draft_Prompt.md").is_file())

    def test_passing_ledger_moves_the_blocker_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self.compile(tmp, "--grill", str(SAMPLE))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("DRAFT_REVIEW_REQUIRED", proc.stderr)
            self.assertNotIn("GRILL_REQUIRED", proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["grill_status"], "GRILL_PASS_WITH_WARNINGS")

    def test_ledger_that_contradicts_the_intent_is_refused(self):
        ledger = json.loads(SAMPLE.read_text(encoding="utf-8"))
        for entry in ledger["entries"]:
            if entry["id"] == "G03":
                entry["answer"] = 15  # intent says 5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grill.json"
            path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
            proc, out = self.compile(tmp, "--grill", str(path))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("GRILL_MISMATCH", proc.stderr)
            self.assertFalse((out / "13_Final_Prompt.md").exists())


class ProductionCompilerGateTests(unittest.TestCase):
    """The full-film compiler is refused as well, not just the prompt compiler."""

    def test_film_compile_refuses_without_station_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [str(PYTHON), "-X", "utf8", "-B", str(PRODUCER), str(CONTROL_INTENT),
                 "--out", str(out)],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("GRILL_REQUIRED", proc.stderr)
            self.assertFalse((out / "01_production_contract.json").exists())


if __name__ == "__main__":
    unittest.main()
