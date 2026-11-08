"""Historical asset definitions through the actual offline delivery/rework chain."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.compile_intent_delivery import compile_intent_delivery
from scripts.production_records import register_local_output
from scripts.production_capability_gate import evaluate
from scripts.compile_production import compile_production
from scripts.intent_handoff import to_compiler_input
from tests.test_rework_application import intent


def three_shots():
    raw=intent();raw["decisions"]["duration_sec"]["value"]=15
    raw["entities"][0]["history"]=[]
    raw["shots"][1]["asset_refs"]=[dict(entity_id="coat",version=1)]
    raw["shots"].append(dict(id="s3",duration_sec=5,description="独立杯子镜头",asset_refs=[dict(entity_id="cup",version=1)]))
    return raw


class HistoricalAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.count=0
        self.file=self.root/"existing.fixture";self.file.write_bytes(b"existing non-media asset history fixture")

    def build(self,raw,previous=None):
        self.count+=1;out=self.root/str(self.count)
        result=compile_intent_delivery(raw,out,previous_graph=previous)
        self.assertEqual(result["gate"]["status"],"PASS",result["gate"])
        self.assertEqual(result["verification"]["status"],"PASS",result["verification"])
        result["asset_plan"]=json.loads((out/"02_asset_graph_plan.json").read_text(encoding="utf-8"))
        result["out"]=out
        return result

    def changed(self,raw,initial):
        raw=copy.deepcopy(raw)
        snapshot=next(a for a in initial["asset_plan"]["assets"] if a.get("base_entity_id")=="coat")["definition"]
        raw["entities"][0].update(version=2,state="wet",state_versions=2,history=[copy.deepcopy(snapshot)])
        raw["shots"][1]["asset_refs"][0]["version"]=2
        return raw

    def bind(self,graph,nid):
        r=graph["production_records"][nid]
        return register_local_output(graph,nid,str(self.file),version=r["version"],source_revision=r["source_revision"],evidence_class="offline_fixture")

    def test_stable_version_nodes_and_real_rework_only_change_the_actual_consumer(self):
        raw=three_shots();first=self.build(raw);g=first["graph"]
        for sid in ("s1","s2","s3"):g=self.bind(g,sid+"__video_candidate_A")
        old=copy.deepcopy(g);changed=self.changed(raw,first);second=self.build(changed,g);new=second["graph"]
        self.assertIn("coat__v1__asset_anchor",{n["id"] for n in g["nodes"]})
        self.assertIn("coat__v2__asset_refine_b",{n["id"] for n in new["nodes"]})
        for nid in ("coat__v1__asset_anchor","s1__video_candidate_A","s3__video_candidate_A"):
            self.assertEqual(new["production_records"][nid],g["production_records"][nid])
        self.assertGreater(new["production_records"]["s2__video_candidate_A"]["version"],g["production_records"]["s2__video_candidate_A"]["version"])
        incoming=lambda target:[e["source"] for e in new["edges"] if e["target"]==target and e["purpose"].startswith("asset_")]
        self.assertEqual(incoming("s1__candidate_image_A"),["coat__v1__asset_anchor"])
        self.assertEqual(incoming("s2__candidate_image_A"),["coat__v2__asset_refine_b"])
        self.assertEqual(g,old)
        self.assertIn("media_sha256",new["record_history"]["s2__video_candidate_A"][0])
        self.assertFalse((second["out"]/"05_platform_execution_plan.json").exists())

    def test_historical_prompt_and_ratio_do_not_inherit_the_current_definition(self):
        raw=three_shots();raw["entities"][0]["aspect_ratio"]="1:1"
        first=self.build(raw);changed=self.changed(raw,first)
        changed["entities"][0].update(description="blue torn coat",aspect_ratio="9:16",name="new coat")
        second=self.build(changed,first["graph"])
        old_pkg=next(p for p in first["prompts"] if p["node_id"]=="coat__v1__asset_anchor")
        preserved=next(p for p in second["prompts"] if p["node_id"]=="coat__v1__asset_anchor")
        self.assertEqual(preserved,old_pkg)
        old_node=next(n for n in second["graph"]["nodes"] if n["id"]=="coat__v1__asset_anchor")
        self.assertEqual(old_node["settings"]["ratio"],"1:1")
        new_pkg=next(p for p in second["prompts"] if p["node_id"]=="coat__v2__asset_anchor")
        self.assertIn("blue torn coat",new_pkg["blocks"]["entity"])
        self.assertNotIn("blue torn coat",preserved["blocks"]["entity"])

    def test_history_must_be_complete_unique_older_and_counted(self):
        raw=three_shots();first=self.build(raw);valid=self.changed(raw,first)
        for mutation in ("missing_description","duplicate","current_version","foreign_id","no_count","implicit_refs"):
            with self.subTest(mutation=mutation):
                bad=copy.deepcopy(valid);entity=bad["entities"][0]
                if mutation=="missing_description":entity["history"][0].pop("description")
                if mutation=="duplicate":entity["history"].append(copy.deepcopy(entity["history"][0]));entity["state_versions"]=3
                if mutation=="current_version":entity["history"][0]["version"]=2
                if mutation=="foreign_id":entity["history"][0]["id"]="cup"
                if mutation=="no_count":entity["state_versions"]=1
                if mutation=="implicit_refs":bad["shots"][0].pop("asset_refs")
                with self.assertRaises(ValueError):self.build(bad)

    def test_frozen_old_definition_cannot_be_rewritten_under_the_same_version(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first)
        changed["entities"][0]["history"][0]["description"]="silently rewritten old coat"
        with self.assertRaises(ValueError):self.build(changed,first["graph"])

    def test_version_namespace_collision_and_unknown_pin_are_rejected(self):
        raw=three_shots()
        collision=copy.deepcopy(raw);collision["entities"].append(dict(id="coat__v1",kind="prop",description="colliding asset"))
        with self.assertRaises(ValueError):self.build(collision)
        bad=copy.deepcopy(raw);bad["shots"][0]["asset_refs"][0]["version"]=99
        with self.assertRaises(ValueError):self.build(bad)

    def test_unreferenced_historical_version_is_preserved_without_forced_generation_nodes(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first)
        changed["shots"][0]["asset_refs"][0]["version"]=2
        second=self.build(changed,first["graph"])
        asset=next(a for a in second["asset_plan"]["assets"] if a["id"]=="coat__v1")
        self.assertFalse(asset["active"])
        self.assertNotIn("coat__v1__asset_anchor",{n["id"] for n in second["graph"]["nodes"]})
        self.assertIn("coat__v1__asset_anchor",second["graph"]["archived_records"])

    def test_gate_rejects_misrouted_historical_reference_without_trusting_active_metadata(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first)
        result=compile_production(to_compiler_input(changed),self.root/"native")
        g=copy.deepcopy(result["graph"])
        edge=next(e for e in g["edges"] if e["target"]=="s1__candidate_image_A" and e["purpose"].startswith("asset_"))
        edge["source"]="coat__v2__asset_refine_b"
        bad=evaluate(result["contract"],result["assets"],g,result["prompts"])
        self.assertEqual(bad["status"],"FAIL")
        self.assertIn("ASSET_VERSION_REFERENCE_MISMATCH",{f["code"] for f in bad["failures"]})
        assets=copy.deepcopy(result["assets"]);assets["assets"][0]["active"]=False
        forged=evaluate(result["contract"],assets,result["graph"],result["prompts"])
        self.assertEqual(forged["status"],"FAIL")
        self.assertIn("ASSET_VERSION_METADATA_MISMATCH",{f["code"] for f in forged["failures"]})

    def test_inactive_frozen_history_cannot_be_rewritten_without_touching_active_nodes(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first)
        changed["shots"][0]["asset_refs"][0]["version"]=2
        second=self.build(changed,first["graph"])
        changed["entities"][0]["history"][0]["state"]="rewritten unused past"
        with self.assertRaises(ValueError):self.build(changed,second["graph"])

    def test_frozen_reuse_iteration_and_explicit_exemption_keep_their_original_scope(self):
        for exemption in (False,True):
            with self.subTest(exemption=exemption):
                raw=three_shots();raw["entities"][0]["reuse_count"]=3
                if exemption:raw["entities"][0]["requires_iteration"]=False
                first=self.build(raw);changed=self.changed(raw,first);second=self.build(changed,first["graph"])
                old=next(a for a in second["asset_plan"]["assets"] if a["id"]=="coat__v1")
                self.assertEqual(old["requires_iteration"],not exemption)
                nid="coat__v1__asset_anchor"
                self.assertEqual(second["graph"]["production_records"][nid],first["graph"]["production_records"][nid])

    def test_third_version_archives_the_second_without_changing_first_consumer(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first)
        second=self.build(changed,first["graph"])
        v2=next(a for a in second["asset_plan"]["assets"] if a["id"]=="coat__v2")["definition"]
        changed["entities"][0]["history"].append(copy.deepcopy(v2))
        changed["entities"][0].update(version=3,state_versions=3,state="torn")
        changed["shots"][1]["asset_refs"][0]["version"]=3
        third=self.build(changed,second["graph"])
        self.assertEqual(third["graph"]["production_records"]["s1__video_candidate_A"],first["graph"]["production_records"]["s1__video_candidate_A"])
        self.assertEqual(third["graph"]["asset_definitions"]["coat__v2"],second["graph"]["asset_definitions"]["coat__v2"])
        self.assertIn("coat__v2__asset_anchor",third["graph"]["archived_records"])
        self.assertIn("coat__v3__asset_anchor",third["graph"]["production_records"])

    def test_full_film_compiles_historical_graph_without_execution_permission(self):
        raw=three_shots();first=self.build(raw);changed=self.changed(raw,first);changed["task_type"]="full_film"
        result=compile_production(to_compiler_input(changed),self.root/"full_film")
        self.assertEqual(result["gate"]["status"],"PASS",result["gate"])
        self.assertIn("coat__v1",result["graph"]["asset_definitions"])
        plan=json.loads((self.root/"full_film/05_platform_execution_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["execution_boundary"],dict(compile_only=True,run=False,ignition_allowed=False))

    def test_inactive_history_does_not_confuse_json_boolean_with_number(self):
        raw=three_shots();raw["entities"][0]["state"]={"present":True}
        first=self.build(raw);changed=self.changed(raw,first)
        changed["shots"][0]["asset_refs"][0]["version"]=2
        second=self.build(changed,first["graph"])
        changed["entities"][0]["history"][0]["state"]={"present":1}
        with self.assertRaises(ValueError):self.build(changed,second["graph"])


if __name__=="__main__":unittest.main()
