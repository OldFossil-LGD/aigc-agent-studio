"""Question payloads must wait for an actual, identity-bound user response."""
import unittest

from scripts.grill_session import new_session, record_facts, select
from scripts.grill_ui import prepare_question, record_response
from tests.test_grill_session import papercut_session


def native_tool(async_shape=False):
    fields = {"title": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}}
    name = "functions.request_user_input_async"
    required = ["title"]
    if not async_shape:
        name = "functions.request_user_input"
        fields = {"id": {"type": "string"}, "header": {"type": "string"},
                  "question": {"type": "string"}, "options": {"type": "array", "minItems": 2, "maxItems": 3,
                  "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label", "description"]}}}
        required = ["id", "header", "question", "options"]
    return {"name": name, "available": True, "input_schema": {"type": "object", "properties": {
        "questions": {"type": "array", "items": {"type": "object", "properties": fields, "required": required}}}, "required": ["questions"]}}


def response(pending, value):
    return {"pending_id": pending["pending_id"], "revision": pending["revision"],
            "result": {"answers": {pending["question_id"]: {"answers": [value]}}}}


class NativeQuestionTests(unittest.TestCase):
    def test_native_question_explains_recommendation_and_reason(self):
        from scripts.grill_bank import QUESTION_INDEX
        for async_shape in (False, True):
            with self.subTest(async_shape=async_shape):
                prepared = prepare_question(new_session("x"), [native_tool(async_shape)])
                question = prepared["tool_call"]["arguments"]["questions"][0]
                text = question.get("title") if async_shape else question["question"]
                bank = QUESTION_INDEX[prepared["question_id"]]
                self.assertIn(bank["why"], text)
                self.assertIn(bank["recommendation"], text)

    def test_consent_based_text_reply_uses_the_same_answer_path(self):
        session = new_session("x")
        pending = prepare_question(session, [], text_consent="可以用文字选项")
        result = record_response(session, response(pending, "完整短片"))
        self.assertEqual(result["state"], "ANSWERED")
        self.assertEqual(session["entries"]["G01"]["answer"], "full_film")

    def test_prepare_does_not_answer_or_select_a_default(self):
        session = new_session("先确定交付")
        prepared = prepare_question(session, [native_tool()])
        self.assertEqual(prepared["state"], "WAITING_FOR_USER")
        self.assertEqual(prepared["tool_call"]["name"], "functions.request_user_input")
        question = prepared["tool_call"]["arguments"]["questions"][0]
        self.assertEqual(question["id"], "G01")
        self.assertEqual(len(question["options"]), 3)
        self.assertNotIn("default", question)
        self.assertEqual(session["entries"], {})
        self.assertEqual(session["turns"], [])
        self.assertEqual(prepare_question(session, [native_tool()]), prepared)

    def test_real_choice_is_mapped_to_original_locked_answer(self):
        session = new_session("选择交付")
        pending = prepare_question(session, [native_tool()])
        result = record_response(session, response(pending, "完整短片"))
        self.assertEqual(result["state"], "ANSWERED")
        self.assertEqual(session["entries"]["G01"]["answer"], "full_film")
        self.assertEqual(session["entries"]["G01"]["source_type"], "grillme_answer")
        self.assertEqual(session["ui_history"][0]["result"]["answers"]["G01"]["answers"], ["完整短片"])

    def test_empty_cancel_and_multi_answer_do_not_advance(self):
        for raw in (None, {}, {"cancelled": True}, {"answers": {"G01": {"answers": []}}},
                    {"answers": {"G01": {"answers": ["只要提示词", "完整短片"]}}}):
            with self.subTest(raw=raw):
                session = new_session("x")
                pending = prepare_question(session, [native_tool()])
                envelope = dict(response(pending, ""), result=raw)
                result = record_response(session, envelope)
                self.assertIn(result["state"], ("WAITING_FOR_USER", "NEEDS_INTERPRETATION"))
                self.assertEqual(session["entries"], {})
                self.assertEqual(session["turns"], [])

    def test_stale_or_wrong_identity_is_rejected(self):
        session = new_session("x")
        pending = prepare_question(session, [native_tool()])
        for key, value in (("pending_id", "foreign"), ("revision", 99)):
            envelope = response(pending, "完整短片")
            envelope[key] = value
            with self.assertRaises(ValueError):
                record_response(session, envelope)
        record_facts(session, {"G03": 5})
        with self.assertRaises(ValueError):
            record_response(session, response(pending, "完整短片"))

    def test_unavailable_tool_requires_consent_before_text_choices(self):
        session = new_session("x")
        tool = native_tool()
        tool["available"] = False
        waiting = prepare_question(session, [tool])
        self.assertEqual(waiting["state"], "TEXT_CONSENT_REQUIRED")
        self.assertNotIn("text_question", waiting)
        prepared = prepare_question(session, [], text_consent="用户同意改用文字选项")
        self.assertEqual(prepared["state"], "WAITING_FOR_USER")
        self.assertIn("text_question", prepared)
        self.assertEqual(session["ui_text_consent"], "用户同意改用文字选项")

    def test_complete_brief_needs_no_ui(self):
        session = papercut_session()
        result = prepare_question(session, [])
        self.assertEqual(result["state"], "READY_TO_FINISH")
        self.assertNotIn("ui_pending", session)

    def test_async_schema_keeps_all_bank_choices(self):
        session = new_session("悬疑短片")
        record_facts(session, {"G01": "full_film"})
        prepared = prepare_question(session, [native_tool(True)])
        question = prepared["tool_call"]["arguments"]["questions"][0]
        self.assertEqual(set(question), {"title", "options"})
        self.assertEqual(len(question["options"]), 6)

    def test_plan_tool_pages_without_answering(self):
        session = new_session("悬疑短片")
        record_facts(session, {"G01": "full_film"})
        pending = prepare_question(session, [native_tool()])
        more = pending["tool_call"]["arguments"]["questions"][0]["options"][-1]["label"]
        self.assertEqual(more, "更多选项")
        result = record_response(session, response(pending, more))
        self.assertEqual(result["state"], "QUESTION_PAGE_CHANGED")
        self.assertEqual(session["turns"], [])
        second = prepare_question(session, [native_tool()])
        self.assertNotEqual(second["pending_id"], pending["pending_id"])
        self.assertEqual(second["question_id"], "I02")

    def test_structured_free_text_requires_interpretation(self):
        session = new_session("x")
        record_facts(session, {"G01": "prompt_only", "G08": "silent", "G10": "离开"})
        pending = prepare_question(session, [native_tool(True)])
        self.assertEqual(pending["question_id"], "G06")
        result = record_response(session, response(pending, "水墨风格"))
        self.assertEqual(result["state"], "NEEDS_INTERPRETATION")
        self.assertNotIn("G06", session["entries"])

    def test_only_bank_delegation_choices_are_unlocked_proposals(self):
        session = new_session("x", mode="L2")
        record_facts(session, {"G01": "full_film", "I02": "emotional_twist", "I04": "final_reveal"})
        # Settle every higher priority question to reach I05 naturally.
        from scripts.grill_session import defer
        while select(session).get("question", {}).get("id") != "I05":
            qid = select(session)["question"]["id"]
            defer(session, qid, "本轮稍后处理")
        pending = prepare_question(session, [native_tool(True)])
        result = record_response(session, response(pending, "由 AI 决定"))
        self.assertEqual(result["state"], "DELEGATED")
        self.assertNotIn("I05", session["entries"])
        result = record_response(session, response(pending, "由 AI 决定"), proposal="relief")
        self.assertEqual(result["state"], "ANSWERED")
        self.assertEqual(session["entries"]["I05"]["decision_status"], "proposed")
        self.assertFalse(session["entries"]["I05"]["locked"])

    def test_unknown_tool_schema_is_not_claimed_as_native(self):
        result = prepare_question(new_session("x"), [{"name": "other", "available": True, "input_schema": {}}])
        self.assertEqual(result["state"], "TEXT_CONSENT_REQUIRED")

    def test_async_ack_is_not_an_answer_but_later_matching_reply_is(self):
        session = new_session("x")
        pending = prepare_question(session, [native_tool(True)])
        title = pending["tool_call"]["arguments"]["questions"][0]["title"]
        envelope = dict(response(pending, ""), result={"accepted": True})
        self.assertEqual(record_response(session, envelope)["state"], "WAITING_FOR_USER")
        self.assertEqual(session["entries"], {})
        reply = [{"questionItemId": '["request_user_input_async","call_example",0]',
                  "question": title, "answer": "完整短片"}]
        envelope["result"] = reply
        self.assertEqual(record_response(session, envelope)["state"], "ANSWERED")
        self.assertEqual(session["entries"]["G01"]["answer"], "full_film")

    def test_async_reply_for_other_question_stays_waiting(self):
        session = new_session("x")
        pending = prepare_question(session, [native_tool(True)])
        envelope = dict(response(pending, ""), result=[{"questionItemId": '["request_user_input_async","call_x",0]',
                                                      "question": "foreign question", "answer": "完整短片"}])
        self.assertEqual(record_response(session, envelope)["state"], "WAITING_FOR_USER")
        self.assertEqual(session["entries"], {})

    def test_interpretation_requires_a_real_result_and_keeps_raw_provenance(self):
        session = new_session("x")
        record_facts(session, {"G01": "prompt_only", "G08": "silent", "G10": "离开"})
        pending = prepare_question(session, [native_tool(True)])
        interpreted = {"style_id": "水墨", "register": "stylized"}
        empty = dict(response(pending, ""), result={"accepted": True})
        self.assertEqual(record_response(session, empty, interpreted_value=interpreted)["state"], "WAITING_FOR_USER")
        actual = response(pending, "水墨风格")
        self.assertEqual(record_response(session, actual, interpreted_value=interpreted)["state"], "ANSWERED")
        self.assertEqual(session["entries"]["G06"]["answer"], interpreted)
        self.assertEqual(session["ui_history"][-1]["interpreted_value"], interpreted)

    def test_paid_questions_never_treat_delegation_as_user_approval(self):
        from scripts.grill_session import defer
        session = new_session("生成单镜", mode="L2")
        record_facts(session, {"G01": "single_shot", "G14": "libtv"})
        while select(session).get("question", {}).get("id") != "G15":
            defer(session, select(session)["question"]["id"], "稍后")
        pending = prepare_question(session, [native_tool(True)])
        result = record_response(session, response(pending, "你定"), interpreted_value="批准100元")
        self.assertEqual(result["state"], "NEEDS_INTERPRETATION")
        self.assertNotIn("G15", session["entries"])


if __name__ == "__main__":
    unittest.main()
