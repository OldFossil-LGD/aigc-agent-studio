"""Real compiler/rework/byte-binding fixtures, not media-effect claims."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_intent_delivery import compile_intent_delivery
from scripts.compile_graph_plan import convert
from scripts import compile_shot_graph as shot_graph
from scripts import film_qc_gate as qc


def intent():
    values = dict(duration_sec=10, aspect_ratio="16:9", visual_style=dict(text="写实", register="photoreal"))
    return dict(intent_format="intent-handoff/v1", goal="两镜服装与杯子，离线返工", task_type="prompt_only",
        decisions={k:dict(value=v,source="user_explicit",locked=True) for k,v in values.items()},
        entities=[dict(id="coat",kind="prop",description="red coat",state="dry",version=1),
                  dict(id="cup",kind="prop",description="white cup",state="intact",version=1)],
        shots=[dict(id="s1",version=1,duration_sec=5,description="衣服镜头",asset_refs=[dict(entity_id="coat",version=1)]),
               dict(id="s2",version=1,duration_sec=5,description="杯子镜头",asset_refs=[dict(entity_id="cup",version=1)])])


class ReworkApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.count=0
        self.old_file=self.root/"old.fixture";self.old_file.write_bytes(b"existing old offline fixture, not a video")
        self.new_file=self.root/"new.fixture";self.new_file.write_bytes(b"existing new offline fixture, not a video")

    def build(self, raw=None, previous=None):
        self.count+=1
        out=self.root/("run%d"%self.count)
        kwargs={} if previous is None else dict(previous_graph=previous)
        result=compile_intent_delivery(raw or intent(),out,**kwargs)
        self.assertEqual(result["verification"]["status"],"PASS",result["verification"])
        return result

    def record(self, graph, nid):
        self.assertIsInstance(graph.get("production_records"),dict,"actual records missing from compiled graph")
        return graph["production_records"][nid]

    def register(self, graph, nid, path=None, version=None, source=None):
        from scripts.production_records import register_local_output
        record=self.record(graph,nid)
        return register_local_output(graph,nid,str(path or self.old_file),
            version=record["version"] if version is None else version,
            source_revision=record["source_revision"] if source is None else source,
            evidence_class="offline_fixture")

    def test_main_compiler_creates_real_record_and_prompt_bindings(self):
        result=self.build();g=result["graph"]
        self.assertEqual(set(g["production_records"]),{n["id"] for n in g["nodes"]})
        rec=self.record(g,"s1__video_candidate_A")
        self.assertEqual(rec["state"],"graph_plan_ready")
        self.assertEqual(rec["review_status"],"NOT_VERIFIED")
        pkg=next(p for p in result["prompts"] if p["node_id"]==rec["record_id"])
        self.assertEqual(pkg["record_binding"],{k:rec[k] for k in ("record_id","version","source_revision")})
        plan=convert(g,"rework-fixture","generic")
        mapped=next(n for n in plan["nodes"] if n["node_id"]==rec["record_id"])
        self.assertEqual((mapped["source_record_id"],mapped["version"]),(rec["record_id"],rec["version"]))

    def test_change_writes_versions_history_and_preserves_unrelated_media(self):
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        before=self.register(before,"s2__video_candidate_A",self.new_file)
        saved=copy.deepcopy(before)
        raw=intent();raw["entities"][0].update(state="wet",version=2);raw["shots"][0]["asset_refs"][0]["version"]=2
        after=self.build(raw,before)["graph"]
        one=self.record(before,"s1__video_candidate_A");new=self.record(after,"s1__video_candidate_A")
        self.assertGreater(new["version"],one["version"])
        self.assertGreater(after["version"],before["version"])
        self.assertEqual(new["state"],"graph_plan_ready")
        self.assertNotIn("media_sha256",new)
        self.assertEqual(self.record(after,"s2__video_candidate_A"),self.record(before,"s2__video_candidate_A"))
        history=after["record_history"][one["record_id"]]
        self.assertTrue(any(h["version"]==one["version"] and h.get("media_sha256")==one["media_sha256"] for h in history))
        self.assertTrue(after["graph_history"])
        self.assertEqual(before,saved)
        self.assertEqual(self.old_file.read_bytes(),b"existing old offline fixture, not a video")
        self.assertFalse(after["generation_authorized"])

    def test_prompt_only_craft_change_is_not_missed_when_node_description_stays_same(self):
        before=self.build()["graph"]
        raw=intent();raw["shots"][0]["performance"]="先看向门，再缓慢收回右手"
        after=self.build(raw,before)["graph"]
        self.assertGreater(self.record(after,"s1__video_candidate_A")["version"],self.record(before,"s1__video_candidate_A")["version"])
        self.assertEqual(self.record(after,"s2__video_candidate_A"),self.record(before,"s2__video_candidate_A"))

    def test_no_change_is_idempotent_and_does_not_reset_derived_versions(self):
        before=self.build()["graph"]
        raw=intent();raw["shots"][0]["performance"]="抬起右手"
        changed=self.build(raw,before)["graph"]
        again=self.build(raw,changed)["graph"]
        self.assertEqual(again["version"],changed["version"])
        self.assertEqual(again["production_records"],changed["production_records"])
        self.assertEqual(again["record_history"],changed["record_history"])

    def test_layout_only_requires_review_without_invalidating_output(self):
        from scripts.production_records import apply_rework
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        moved=copy.deepcopy(before);moved["nodes"][0]["x"]=250;moved["groups"][0]["name"]="UI label"
        after=apply_rework(before,moved)
        self.assertFalse(after["rework"]["affected_record_ids"])
        self.assertTrue(after["rework"]["review_record_ids"])
        for invalidation in after["rework"]["invalidations"]:
            self.assertTrue({"source_record_id","affected_record_ids","reason","evidence","next_action"}.issubset(invalidation))
            self.assertTrue(invalidation["evidence"])
        old=self.record(before,"s1__video_candidate_A");new=self.record(after,"s1__video_candidate_A")
        self.assertEqual((new["version"],new["media_sha256"]),(old["version"],old["media_sha256"]))

    def test_cycle_broken_graph_and_forged_review_flags_are_rejected(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"]
        for mutation in ("cycle","dangling","forged_review","record_version"):
            with self.subTest(mutation=mutation):
                bad=copy.deepcopy(before)
                if mutation=="cycle":bad["edges"].append(dict(source="s1__video_candidate_A",target="s1__prompt",purpose="dependency"))
                if mutation=="dangling":bad["edges"].append(dict(source="missing",target="s1__prompt",purpose="reference"))
                if mutation=="forged_review":bad["production_records"]["s1__video_candidate_A"].update(state="reviewed",review_status="PASS")
                if mutation=="record_version":bad["production_records"]["s1__video_candidate_A"]["version"]+=1
                with self.assertRaises(ValueError):apply_rework(bad,before)

    def test_same_asset_source_version_cannot_mean_two_different_states(self):
        before=self.build()["graph"]
        raw=intent();raw["entities"][0]["state"]="wet"
        with self.assertRaises(ValueError):self.build(raw,before)

    def test_late_or_replaced_local_output_is_rejected_and_not_reviewed(self):
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        raw=intent();raw["shots"][0]["performance"]="向后退一步"
        changed=self.build(raw,before)["graph"]
        old=self.record(before,"s1__video_candidate_A")
        with self.assertRaises(ValueError):self.register(changed,"s1__video_candidate_A",self.new_file,old["version"],old["source_revision"])
        with self.assertRaises(ValueError):self.register(before,"s1__video_candidate_A",self.new_file)
        current=self.register(changed,"s1__video_candidate_A",self.new_file)
        rec=self.record(current,"s1__video_candidate_A")
        self.assertEqual(rec["state"],"generated")
        self.assertEqual(rec["review_status"],"NOT_VERIFIED")
        self.assertEqual(rec["media_sha256"],hashlib.sha256(self.new_file.read_bytes()).hexdigest())

    def test_old_or_wrong_source_receipt_cannot_approve_current_revision(self):
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        old=self.record(before,"s1__video_candidate_A")
        raw=intent();raw["shots"][0]["performance"]="向后退一步"
        current=self.register(self.build(raw,before)["graph"],"s1__video_candidate_A",self.new_file)
        rec=self.record(current,"s1__video_candidate_A")
        receipt={k:rec[k] for k in ("record_id","version","source_revision","media_sha256")}
        receipt["layers"]={name:dict(status="PASS",evidence="offline fixture only",decision="retain") for name in ("structure","instruction","technical","creative")}
        receipt["layers"]["creative"]["passes"]=[dict(pass_id=n,status="PASS",evidence="fixture",decision="retain",**{"pass":n}) for n in range(1,7)]
        good=qc.verify_review_binding(str(self.new_file),rec,receipt)
        self.assertEqual((good["status"],good["review_status"]),("PASS","NOT_VERIFIED"))
        receipt["source_revision"]=old["source_revision"]
        bad=qc.verify_review_binding(str(self.new_file),rec,receipt)
        self.assertEqual(bad["status"],"FAIL")
        self.assertIn("REVIEW_SOURCE_REVISION_MISMATCH",{f["code"] for f in bad["failures"]})

    def test_deleted_shot_is_archived_and_resurrection_uses_a_new_record_version(self):
        before=self.register(self.build()["graph"],"s2__video_candidate_A")
        raw=intent();raw["shots"].pop();raw["entities"].pop();raw["decisions"]["duration_sec"]["value"]=5
        removed=self.build(raw,before)["graph"]
        nid="s2__video_candidate_A"
        self.assertNotIn(nid,removed["production_records"])
        self.assertEqual(removed["archived_records"][nid]["media_sha256"],self.record(before,nid)["media_sha256"])
        self.assertEqual(removed["archived_records"][nid]["state"],"archived")
        self.assertEqual(removed["archived_records"][nid]["previous_state"],self.record(before,nid)["state"])
        restored=self.build(intent(),removed)["graph"]
        self.assertGreater(self.record(restored,nid)["version"],self.record(before,nid)["version"])
        self.assertNotIn("media_sha256",self.record(restored,nid))
        self.assertEqual(self.old_file.read_bytes(),b"existing old offline fixture, not a video")

    def test_removed_reference_invalidates_old_consumer_and_preserves_other_shot(self):
        from scripts.production_records import apply_rework
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        current=copy.deepcopy(before)
        current["edges"]=[e for e in current["edges"] if not (e["source"]=="coat__asset_anchor" and e["target"]=="s1__candidate_image_A")]
        # This raw edit deliberately has no records; the application must recompute them.
        current.pop("production_records")
        after=apply_rework(before,current)
        self.assertIn("s1__video_candidate_A",after["rework"]["affected_record_ids"])
        self.assertEqual(self.record(after,"s1__video_candidate_A")["state"],"recovering")
        self.assertEqual(self.record(after,"s2__video_candidate_A"),self.record(before,"s2__video_candidate_A"))
        self.assertTrue(any(row["record_id"]=="s1__video_candidate_A" and row["level"]=="invalidate_output"
                            for row in after["rework"]["invalidations"]))

    def test_changed_reference_order_is_not_lost_by_converting_edges_to_a_set(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"];current=copy.deepcopy(before)
        inds=[i for i,e in enumerate(current["edges"]) if e["target"]=="s1__candidate_image_A"]
        self.assertGreaterEqual(len(inds),2)
        a,b=inds[:2];current["edges"][a],current["edges"][b]=current["edges"][b],current["edges"][a]
        current.pop("production_records")
        after=apply_rework(before,current)
        self.assertIn("s1__video_candidate_A",after["rework"]["affected_record_ids"])
        self.assertEqual(self.record(after,"s2__video_candidate_A"),self.record(before,"s2__video_candidate_A"))

    def test_forged_current_records_are_not_silently_discarded(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"];current=copy.deepcopy(before)
        current["production_records"]["s1__video_candidate_A"]["review_status"]="PASS"
        with self.assertRaises(ValueError):apply_rework(before,current)

    def test_prompt_snapshot_tamper_and_missing_previous_records_are_rejected(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"]
        for missing in (True,False):
            bad=copy.deepcopy(before)
            if missing:bad.pop("production_records")
            else:bad["production_records"]["s1__video_candidate_A"]["source_prompt_package"]["blocks"]["visual"]="forged"
            with self.assertRaises(ValueError):apply_rework(bad,before)

    def test_local_import_requires_actual_pass_and_nonempty_bytes(self):
        from scripts.production_records import initialize_records, register_local_output
        result=self.build();g=initialize_records(result["graph"],result["prompts"])
        rec=self.record(g,"s1__video_candidate_A")
        with self.assertRaises(ValueError):self.register(g,rec["record_id"])
        empty=self.root/"empty.fixture";empty.write_bytes(b"")
        with self.assertRaises(ValueError):self.register(result["graph"],rec["record_id"],empty)
        with self.assertRaises(ValueError):register_local_output(result["graph"],rec["record_id"],str(self.old_file),
            version=rec["version"],source_revision=rec["source_revision"],evidence_class="platform_readback")

    def test_failed_delivery_cannot_be_registered_as_a_ready_plan(self):
        raw=intent()
        raw["constraints"]=[dict(id="camera_required",kind="camera",text="相机保持固定。",delivery="prompt",
            source="user_explicit",locked=True,semantics=dict(required_any=["ABSENT_CAMERA_REQUIREMENT"]))]
        result=compile_intent_delivery(raw,self.root/"failed_delivery")
        self.assertEqual(result["verification"]["status"],"FAIL")
        self.assertEqual(self.record(result["graph"],"s1__video_candidate_A")["state"],"recovering")
        with self.assertRaises(ValueError):self.register(result["graph"],"s1__video_candidate_A")

    def test_deleting_an_independent_branch_with_same_body_preserves_other_record(self):
        from scripts.production_records import apply_rework
        before=self.register(self.build()["graph"],"s1__video_candidate_A")
        current=copy.deepcopy(before)
        gone={n["id"] for n in current["nodes"] if n.get("shot_id")=="s2"}
        current["nodes"]=[n for n in current["nodes"] if n["id"] not in gone]
        current["edges"]=[e for e in current["edges"] if e["source"] not in gone and e["target"] not in gone]
        for group in current["groups"]:group["node_ids"]=[nid for nid in group["node_ids"] if nid not in gone]
        current["shots"]=[s for s in current["shots"] if s["id"]!="s2"]
        current.pop("production_records")
        after=apply_rework(before,current)
        self.assertEqual(self.record(after,"s1__video_candidate_A"),self.record(before,"s1__video_candidate_A"))
        self.assertIn("s2__video_candidate_A",after["archived_records"])

    def test_node_source_record_link_cannot_point_at_another_shot(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"];bad=copy.deepcopy(before)
        next(n for n in bad["nodes"] if n["id"]=="s1__video_candidate_A")["source_record_id"]="s2__video_candidate_A"
        for previous,current in ((bad,before),(before,bad)):
            with self.assertRaisesRegex(ValueError,"RECORD_ID_MISMATCH"):apply_rework(previous,current)

    def test_rework_identifies_the_responsible_layer_and_the_actual_reentry_gates(self):
        from scripts.production_records import apply_rework
        before=self.build()["graph"];raw=intent();raw["shots"][0]["performance"]="轻轻放下手中物件"
        result=self.build(raw,before);after=result["graph"]
        recovery=self.record(after,"s1__video_candidate_A")["recovery"]
        self.assertIn("提示词",recovery["responsibility_layers"])
        self.assertIn("shot_contract_ready",recovery["reentry_states"])
        self.assertEqual(recovery["remaining_gates"],[])
        self.assertEqual(recovery["status"],"plan_revalidated")
        self.assertIn("s2__video_candidate_A",after["rework"]["reusable_record_ids"])
        edge_edit=copy.deepcopy(before);edge_edit.pop("production_records")
        edge_edit["edges"]=[e for e in edge_edit["edges"] if not (e["source"]=="coat__asset_anchor" and e["target"]=="s1__candidate_image_A")]
        pending=apply_rework(before,edge_edit)
        recovery=self.record(pending,"s1__video_candidate_A")["recovery"]
        self.assertIn("图计划",recovery["responsibility_layers"])
        self.assertIn("graph_plan_ready",recovery["reentry_states"])
        self.assertTrue(recovery["remaining_gates"])
        self.assertEqual(self.record(pending,"s1__video_candidate_A")["state"],"recovering")


if __name__=="__main__":unittest.main()
