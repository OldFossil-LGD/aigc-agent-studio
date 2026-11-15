import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.grill_bank import MODES, QUESTION_INDEX, priority_score
from scripts.grill_ledger import gate
from scripts.grill_session import (
    GrillSessionError,
    answer,
    compile_contract,
    default_rest,
    export_ledger,
    finish,
    frontier,
    load_session,
    new_session,
    record_facts,
    revise,
    save_session,
    select,
    skip,
    status,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
SESSION_CLI = ROOT / "scripts" / "grill_session.py"
COMPILER = ROOT / "scripts" / "compile_intent_delivery.py"
SAMPLE_INTENT = ROOT / "samples" / "papercut_empty_shot_intent.json"
SCHEMA = ROOT / "schemas" / "creative_intent_contract.schema.json"


def papercut_facts():
    return {
        "G01": "prompt_only",
        "G03": 5,
        "G04": "9:16",
        "G06": {"style_id": "剪纸风格：色块平涂、剪裁边缘干净、纸纤维哑光",
                "register": "stylized"},
        "G08": "ambience_only",
        "G10": "空镜按「时间在走、画面无人」处理。",
        "I01": "short_film",
        "I02": "gentle_healing",
        "I03": {"theme": "时间从不等人", "core_conflict": "人与时间"},
        "I11": {"must_have": ["雨声"], "must_never": ["人声", "配乐"]},
        "I17": "none",
    }


def papercut_session(mode="auto"):
    session = new_session("5 秒 9:16 剪纸空镜，只要雨声，只要提示词", mode=mode)
    record_facts(session, papercut_facts())
    return session


class SessionFlowTests(unittest.TestCase):
    def test_empty_round_asks_exactly_the_root_question(self):
        session = new_session("一句话需求")
        choice = select(session)
        self.assertEqual(choice["status"], "QUESTION")
        self.assertEqual(choice["question"]["id"], "G01")

    def test_complete_brief_ends_with_zero_questions(self):
        session = papercut_session()
        choice = select(session)
        self.assertEqual(choice["status"], "READY_TO_FINISH")
        self.assertEqual(choice["mode_effective"], "L0")
        result = finish(session)
        self.assertEqual(result["status"], "READY_FOR_PLANNING")
        self.assertEqual(result["contract"]["grill_policy"]["questions_asked"], 0)

    def test_vague_brief_asks_one_creative_question_not_a_parameter_list(self):
        session = new_session("出租车司机深夜遇到神秘乘客的悬疑短剧")
        record_facts(session, {"G01": "full_film"})
        choice = select(session)
        self.assertEqual(choice["status"], "QUESTION")
        self.assertEqual(choice["question"]["id"], "I02")
        self.assertEqual(choice["mode_effective"], "L1")

    def test_next_question_changes_with_the_emotional_answer(self):
        twist = new_session("x")
        record_facts(twist, {"G01": "full_film", "I02": "emotional_twist"})
        ids = [question["id"] for question in frontier(twist)]
        self.assertIn("I06", ids)
        self.assertNotIn("I07", ids)

        mystery = new_session("y")
        record_facts(mystery, {"G01": "full_film", "I02": "intellectual_mystery"})
        ids = [question["id"] for question in frontier(mystery)]
        self.assertIn("I07", ids)
        self.assertNotIn("I06", ids)

    def test_every_bank_default_passes_its_own_validation(self):
        from scripts.grill_bank import QUESTION_BANK, answer_errors

        for question in QUESTION_BANK:
            if "default" not in question:
                continue
            self.assertEqual(answer_errors(question, question["default"]), [],
                             "%s default fails its own validator" % question["id"])

    def test_content_type_changes_priority(self):
        ad = priority_score(QUESTION_INDEX["I11"], "ad")
        concept = priority_score(QUESTION_INDEX["I11"], "concept_piece")
        self.assertEqual(ad - concept, 6)  # constraints bias: ad +6, concept 0
        story_ad = priority_score(QUESTION_INDEX["I02"], "ad")
        story_film = priority_score(QUESTION_INDEX["I02"], "short_film")
        self.assertEqual(story_film - story_ad, 6)

    def test_skip_uses_a_traceable_preset(self):
        session = new_session("z")
        record_facts(session, {"G01": "prompt_only"})
        result = skip(session, "G05")
        self.assertEqual(result["status"], "DEFAULTED")
        entry = session["entries"]["G05"]
        self.assertEqual(entry["source_type"], "project_preset")
        self.assertEqual(entry["decision_status"], "defaulted")
        self.assertFalse(entry["locked"])

    def test_skip_without_default_requires_an_explicit_proposal(self):
        session = new_session("z")
        record_facts(session, {"G01": "full_film"})
        with self.assertRaises(GrillSessionError) as caught:
            skip(session, "I02")
        self.assertEqual(caught.exception.code, "GRILL_NO_SAFE_DEFAULT")
        result = skip(session, "I02", "emotional_twist")
        self.assertEqual(result["source_type"], "agent_proposed")
        self.assertEqual(session["entries"]["I02"]["decision_status"], "proposed")

    def test_paid_ignition_cannot_be_settled_by_the_agent(self):
        session = papercut_facts()
        session = new_session("generate")
        record_facts(session, {"G01": "single_shot"})
        with self.assertRaises(GrillSessionError) as caught:
            skip(session, "G16")
        self.assertEqual(caught.exception.code, "GRILL_USER_ONLY")

    def test_revision_creates_a_new_revision_and_keeps_history(self):
        session = new_session("rev")
        record_facts(session, {"G01": "prompt_only", "G03": 15})
        before = session["revision"]
        revise(session, "G03", 10)
        self.assertEqual(session["revision"], before + 1)
        self.assertEqual(session["history"][-1]["previous"], 15)
        contract = compile_contract(session)
        self.assertEqual(contract["revision"], before + 1)
        self.assertEqual(contract["production_constraints"]["duration_seconds"], 10)
        self.assertEqual(contract["revision_history"][-1]["previous"], 15)

    def test_duplicate_idempotency_key_is_a_noop(self):
        session = new_session("idem")
        record_facts(session, {"G01": "prompt_only"})
        answer(session, "G03", 15, key="k-1")
        turns = len(session["turns"])
        again = answer(session, "G03", 15, key="k-1")
        self.assertEqual(again["status"], "DUPLICATE")
        self.assertEqual(len(session["turns"]), turns)

    def test_stale_revision_is_rejected(self):
        session = new_session("stale")
        record_facts(session, {"G01": "prompt_only"})
        with self.assertRaises(GrillSessionError) as caught:
            answer(session, "G03", 15, revision=session["revision"] + 5)
        self.assertEqual(caught.exception.code, "GRILL_STALE_SESSION")

    def test_invalid_answers_are_named(self):
        session = new_session("bad")
        record_facts(session, {"G01": "prompt_only"})
        with self.assertRaises(GrillSessionError) as caught:
            answer(session, "G01", "series")
        self.assertEqual(caught.exception.code, "GRILL_INVALID_ANSWER")
        with self.assertRaises(GrillSessionError):
            answer(session, "I03", {"theme": "", "core_conflict": "x"})

    def test_resume_keeps_the_same_next_question(self):
        session = new_session("resume")
        record_facts(session, {"G01": "full_film", "G03": 60})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            save_session(path, session)
            loaded = load_session(path)
        self.assertEqual(status(loaded), status(session))


class ContractTests(unittest.TestCase):
    def test_contract_matches_the_published_schema(self):
        import jsonschema

        session = papercut_session()
        contract = finish(session)["contract"]
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(contract, schema)
        self.assertEqual(contract["status"], "ready_for_planning")
        self.assertEqual(contract["creative_intent"]["deliverable"], "prompt_only")

    def test_contract_and_ledger_views_both_pass_the_same_gate(self):
        session = papercut_session()
        contract = finish(session)["contract"]
        ledger = export_ledger(session)
        self.assertEqual(gate(ledger, "prompt")["status"], "GRILL_PASS")
        self.assertEqual(gate(contract, "prompt")["status"], "GRILL_PASS")

    def test_music_preset_against_a_ban_is_blocked(self):
        session = new_session("only water sound")
        record_facts(session, {
            "G01": "prompt_only", "G03": 15, "G04": "16:9",
            "G06": {"style_id": "写实", "register": "photoreal"},
            "G08": "ambience_only", "G10": "他走了。",
            "I11": {"must_have": ["雨声"], "must_never": ["配乐"]},
            "I17": "score",
        })
        result = finish(session)
        self.assertEqual(result["status"], "BLOCKED_CONFLICT")
        codes = [conflict["code"] for conflict in result["contract"]["blocking_conflicts"]]
        self.assertIn("CONFLICT_MUSIC_FORBIDDEN", codes)
        self.assertEqual(gate(result["contract"], "prompt")["status"], "GRILL_CONFLICT")

    def test_no_people_with_character_invariants_conflicts(self):
        session = new_session("empty shot")
        record_facts(session, {
            "G01": "full_film", "G03": 5, "G04": "9:16",
            "G06": {"style_id": "剪纸", "register": "stylized"},
            "G08": "silent", "G10": "无人。",
            "I11": {"must_have": ["空房间"], "must_never": ["不出现人物"]},
            "I09": ["左眼窄一线", "右手插兜", "清嗓后才说话"],
        })
        result = finish(session)
        codes = [conflict["code"] for conflict in result["contract"]["blocking_conflicts"]]
        self.assertIn("CONFLICT_PEOPLE_AND_INVARIANTS", codes)

    def test_defaults_are_never_reported_as_user_original(self):
        session = new_session("defaults")
        record_facts(session, {"G01": "prompt_only", "G03": 15, "G04": "16:9",
                               "G06": {"style_id": "写实", "register": "photoreal"},
                               "G08": "silent", "G10": "他走了。"})
        default_rest(session)
        result = finish(session)
        self.assertEqual(result["status"], "READY_FOR_PLANNING")
        for decision in result["contract"]["decisions"]:
            if decision["decision_status"] == "defaulted":
                self.assertEqual(decision["source_type"], "project_preset")
                self.assertFalse(decision["locked"])

    def test_authority_confirm_each_node_conflicts_with_defaults(self):
        session = new_session("confirm everything")
        record_facts(session, {"G01": "prompt_only", "G03": 15, "G04": "16:9",
                               "G06": {"style_id": "写实", "register": "photoreal"},
                               "G08": "silent", "G10": "他走了。",
                               "I14": "confirm_each_node"})
        answer(session, "I17", "none")  # answered, not defaulted
        default_rest(session)
        result = finish(session)
        codes = [conflict["code"] for conflict in result["contract"]["blocking_conflicts"]]
        self.assertIn("CONFLICT_DEFAULT_FORBIDDEN", codes)


class InheritanceTests(unittest.TestCase):
    def test_contract_declares_no_generation_authority(self):
        contract = finish(papercut_session())["contract"]
        self.assertFalse(contract["authorization"]["generation_authorized"])

    def test_inherited_contract_seeds_a_new_session(self):
        from scripts.grill_session import inherit_contract, load_session

        published = finish(papercut_session())["contract"]
        session = new_session("续作：同一条剪纸空镜的 v2")
        inherited = inherit_contract(session, published)
        self.assertIn("G03", inherited)
        self.assertEqual(session["entries"]["G03"]["source_type"], "inherited_project")
        self.assertTrue(session["entries"]["G03"]["locked"])
        self.assertEqual(gate(export_ledger(session), "prompt")["status"], "GRILL_PASS")


class MetricsAndImmutabilityTests(unittest.TestCase):
    def test_metrics_reports_skips_and_defaults(self):
        from scripts.grill_session import metrics, skip

        session = new_session("metrics")
        record_facts(session, {"G01": "prompt_only"})
        answer(session, "G03", 15)
        skip(session, "G05")
        default_rest(session)
        data = metrics(session)
        self.assertEqual(data["answered"], 1)
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(data["questions_asked"], 2)
        self.assertGreaterEqual(data["defaulted_fields"], 1)

    def test_published_contract_revision_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "s.json"
            contract_path = Path(tmp) / "cic.json"
            session = papercut_session()
            save_session(session_path, session)
            first = subprocess.run(
                [str(PYTHON), "-X", "utf8", "-B", str(SESSION_CLI), "finish",
                 "--session", str(session_path), "--contract", str(contract_path)],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(first.returncode, 0, first.stderr)
            before = contract_path.read_text(encoding="utf-8")

            revise(session, "G03", 8)
            save_session(session_path, session)
            second = subprocess.run(
                [str(PYTHON), "-X", "utf8", "-B", str(SESSION_CLI), "finish",
                 "--session", str(session_path), "--contract", str(contract_path)],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(contract_path.read_text(encoding="utf-8"), before)
            revised_path = Path(tmp) / ("cic.r%s.json" % session["revision"])
            self.assertTrue(revised_path.is_file())


class ExampleWalkthroughTests(unittest.TestCase):
    def test_offline_example_runs_end_to_end(self):
        proc = subprocess.run(
            [str(PYTHON), "-X", "utf8", "-B", str(ROOT / "examples" / "grillme_walkthrough.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("READY_FOR_PLANNING", proc.stdout)


class CompilerIntegrationTests(unittest.TestCase):
    def compile(self, tmp, grill_path):
        out = Path(tmp) / "out"
        proc = subprocess.run(
            [str(PYTHON), "-X", "utf8", "-B", str(COMPILER), str(SAMPLE_INTENT),
             "--out", str(out), "--grill", str(grill_path)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        )
        return proc, out

    def test_a_ready_contract_clears_the_station_zero_block(self):
        session = papercut_session()
        contract = finish(session)["contract"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cic.json"
            path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
            proc, out = self.compile(tmp, path)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("DRAFT_REVIEW_REQUIRED", proc.stderr)
            self.assertNotIn("GRILL_REQUIRED", proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["grill_status"], "GRILL_PASS")

    def test_a_blocked_contract_is_refused_with_its_own_code(self):
        session = new_session("only water sound")
        record_facts(session, {
            "G01": "prompt_only", "G03": 5, "G04": "9:16",
            "G06": {"style_id": "剪纸", "register": "stylized"},
            "G08": "ambience_only", "G10": "他走了。",
            "I11": {"must_have": ["雨声"], "must_never": ["配乐"]},
            "I17": "score",
        })
        contract = finish(session)["contract"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cic.json"
            path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
            proc, out = self.compile(tmp, path)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("GRILL_CONFLICT", proc.stderr)
            self.assertFalse((out / "13_Final_Prompt.md").exists())


class SessionCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([str(PYTHON), "-X", "utf8", "-B", str(SESSION_CLI), *args],
                              cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")

    def test_cli_roundtrip_writes_contract_and_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "session.json"
            contract_path = Path(tmp) / "cic.json"
            ledger_path = Path(tmp) / "ledger.json"
            start = self.run_cli("start", "--out", str(session_path),
                                 "--request", "5 秒剪纸空镜，只要雨声")
            self.assertEqual(start.returncode, 0, start.stderr)
            sets = []
            for qid, value in papercut_facts().items():
                sets += ["--set", "%s=%s" % (qid, json.dumps(value, ensure_ascii=False))]
            record = self.run_cli("record", "--session", str(session_path), *sets)
            self.assertEqual(record.returncode, 0, record.stderr)
            nxt = self.run_cli("next", "--session", str(session_path))
            self.assertEqual(nxt.returncode, 0, nxt.stderr)
            self.assertIn("READY_TO_FINISH", nxt.stdout)
            done = self.run_cli("finish", "--session", str(session_path),
                                "--contract", str(contract_path), "--ledger", str(ledger_path))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(contract_path.is_file())
            self.assertTrue(ledger_path.is_file())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["status"], "ready_for_planning")


if __name__ == "__main__":
    unittest.main()
