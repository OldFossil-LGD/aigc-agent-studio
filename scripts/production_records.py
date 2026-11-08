"""Offline Production Record version/history application; never authorizes generation."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

try:
    from scripts.compile_graph_plan import ROLE_MAP, edge_kind
except ImportError:
    from compile_graph_plan import ROLE_MAP, edge_kind

LAYOUT = {"x", "y", "layout", "position"}
RUNTIME = {"version", "source_version", "source_record_id", "source_revision", "state", "status",
           "review_status", "media_sha256", "media_path", "media_evidence_class", "media_byte_count"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _version(value):
    if type(value) is not int or value < 1:
        raise ValueError("version must be a positive integer")
    return value


def authored(node):
    result = {k:copy.deepcopy(v) for k,v in node.items() if k not in LAYOUT | RUNTIME}
    result["version"] = _version(node.get("source_version", node.get("version", 1)))
    return result


def _prompt_content(package):
    keys = ["prompt_format", "node_id", "role", "node_type", "blocks", "model_route"]
    if package.get("node_type") in {"video", "audio", "video-clip"}:
        keys.append("duration")
    return {k:copy.deepcopy(package[k]) for k in keys if k in package}


def bind_prompt_content(graph, prompts):
    """Bind actual canonical bodies, not status/evidence/binding self-reports."""
    result=copy.deepcopy(graph)
    nodes={n["id"]:n for n in result["nodes"]}
    seen=set()
    for package in prompts:
        nid=package.get("node_id")
        if nid not in nodes or nid in seen:
            raise ValueError("unknown or duplicate canonical prompt: %s" % nid)
        seen.add(nid)
        nodes[nid]["prompt_content_sha256"]=digest(_prompt_content(package))
    return result


def _graph_index(graph):
    if not isinstance(graph,dict) or not isinstance(graph.get("nodes"),list) or not graph["nodes"]:
        raise ValueError("EMPTY_GRAPH")
    if "asset_definitions" in graph:
        if not isinstance(graph["asset_definitions"],dict):raise ValueError("INVALID_ASSET_DEFINITIONS")
        digest(graph["asset_definitions"])
    nodes={}
    for node in graph["nodes"]:
        nid=node.get("id") if isinstance(node,dict) else None
        if not isinstance(nid,str) or not nid.strip() or nid in nodes:
            raise ValueError("INVALID_NODE_ID")
        _version(node.get("version",1));authored(node)
        nodes[nid]=node
    incoming={nid:[] for nid in nodes};outgoing={nid:[] for nid in nodes};seen=set()
    for e in graph.get("edges",[]):
        s,t=e.get("source"),e.get("target")
        if s not in nodes or t not in nodes:
            raise ValueError("DANGLING_EDGE")
        key=(s,t,str(e.get("purpose") or ""))
        if key in seen:
            raise ValueError("DUPLICATE_EDGE")
        seen.add(key)
        kind=e.get("kind") or edge_kind(ROLE_MAP.get(nodes[s].get("role"),"source"),
                                       ROLE_MAP.get(nodes[t].get("role"),"source"))
        if kind not in {"reference","dependency","assembly","lineage"}:
            raise ValueError("INVALID_EDGE_KIND")
        incoming[t].append(dict(source=s,purpose=key[2],kind=kind))
        outgoing[s].append(t)
    # Preserve consumption order, while text planning dependency order is immaterial.
    for nid,rows in incoming.items():
        incoming[nid]=[r for r in rows if r["kind"] in {"reference","assembly"}]+sorted(
            (r for r in rows if r["kind"] not in {"reference","assembly"}),key=lambda r:(r["source"],r["purpose"],r["kind"]))
    degree={nid:len(rows) for nid,rows in incoming.items()}
    ready=sorted(nid for nid,n in degree.items() if n==0);order=[]
    while ready:
        nid=ready.pop(0);order.append(nid)
        for child in outgoing[nid]:
            degree[child]-=1
            if degree[child]==0:ready.append(child)
    if len(order)!=len(nodes):raise ValueError("GRAPH_CYCLE")
    _version(graph.get("version",1))
    return nodes,incoming,outgoing,order


def _references(incoming, records):
    return [dict(row,record_id=row["source"],version=records[row["source"]]["version"],
                 source_revision=records[row["source"]]["source_revision"]) for row in incoming]


def _revision(node, references):
    return digest(dict(authored_node=authored(node),references=references))


def validate_records(graph):
    nodes,incoming,outgoing,order=_graph_index(graph)
    records=graph.get("production_records")
    if not isinstance(records,dict) or set(records)!=set(nodes):
        raise ValueError("actual Production Records required; recompile the previous source first")
    for nid in order:
        node,record=nodes[nid],records[nid]
        if record.get("record_format")!="production-record/v1" or record.get("record_id")!=nid or node.get("source_record_id")!=nid:
            raise ValueError("RECORD_ID_MISMATCH")
        if record.get("version")!=node["version"] or type(record.get("version")) is not int:
            raise ValueError("RECORD_VERSION_MISMATCH")
        if record.get("source_version")!=authored(node)["version"] or record.get("authored_node")!=authored(node):
            raise ValueError("RECORD_SOURCE_MISMATCH")
        if "asset_definition_sha256" in node and digest((graph.get("asset_definitions") or {}).get(node.get("entity_id")))!=node["asset_definition_sha256"]:
            raise ValueError("RECORD_ASSET_DEFINITION_MISMATCH")
        refs=_references(incoming[nid],records)
        revision=_revision(node,refs)
        if record.get("references")!=refs or record.get("source_revision")!=revision or node.get("source_revision")!=revision:
            raise ValueError("RECORD_REVISION_MISMATCH")
        package=record.get("source_prompt_package")
        if "prompt_content_sha256" in node and (not isinstance(package,dict) or
                digest(_prompt_content(package))!=node["prompt_content_sha256"]):
            raise ValueError("RECORD_PROMPT_MISMATCH")
        if record.get("state") not in {"recovering","graph_plan_ready","generated"} or record.get("review_status")!="NOT_VERIFIED":
            raise ValueError("unverified offline records cannot claim reviewed or delivered")
        if record.get("state")=="generated" and (not record.get("media_sha256") or not record.get("media_path")):
            raise ValueError("generated record requires a bound local file")
        for key in ("state","review_status","media_sha256","media_path","media_evidence_class","media_byte_count"):
            if record.get(key)!=node.get(key):raise ValueError("NODE_RECORD_STATE_MISMATCH")
    return nodes,incoming,outgoing,order


def _reentry(node, edge_only=False):
    """Use the existing failure-layer/state table, without another state machine."""
    role=node.get("role")
    if edge_only:return "图计划","graph_plan_ready"
    if role in {"asset_anchor","asset_refine","scene_ref","identity_ref","composition_ref","state_ref"}:
        return "资产","assets_draft"
    if role=="storyboard":return "故事板/分镜","storyboard_ready"
    if role in {"prompt","candidate_image","refined_image","video_candidate","audio"}:
        return "提示词","shot_contract_ready"
    return "图计划","graph_plan_ready"


def rework_advice(previous, current):
    result=dict(status="PASS",failures=[],generation_authorized=False,affected_record_ids=[],
                review_record_ids=[],changes=[],invalidations=[])
    try:
        before,old_in,old_out,_=_graph_index(previous)
        after,new_in,new_out,_=_graph_index(current)
    except ValueError as exc:
        result.update(status="FAIL",failures=[dict(code=str(exc))]);return result
    changed={nid for nid in before.keys()|after.keys() if nid not in before or nid not in after or
             authored(before[nid])!=authored(after[nid]) or old_in[nid]!=new_in[nid]}
    review={nid for nid in before.keys()&after.keys() if
            {k:before[nid].get(k) for k in LAYOUT}!={k:after[nid].get(k) for k in LAYOUT}}
    if previous.get("groups")!=current.get("groups"):
        review.update(before.keys()&after.keys())
    affected=set()
    for source in sorted(changed):
        descendants=set();pending=[source]
        while pending:
            nid=pending.pop()
            if nid in descendants:continue
            descendants.add(nid);pending.extend(old_out.get(nid,[]));pending.extend(new_out.get(nid,[]))
        affected.update(descendants)
        edge_only=source in before and source in after and authored(before[source])==authored(after[source])
        layer,reentry=_reentry(after.get(source,before.get(source,{})),edge_only)
        result["changes"].append(dict(source_record_id=source,affected_record_ids=sorted(descendants),
            failure_layer=layer,reentry_state=reentry,
            reason="source content, canonical prompt, revision or dependency changed",
            evidence=dict(previous_version=before.get(source,{}).get("version"),current_version=after.get(source,{}).get("version")),
            next_action="从 %s（%s）重编并重跑原门禁；真实生成仍需显式批准" % (reentry,layer)))
    result["affected_record_ids"]=sorted(affected);result["review_record_ids"]=sorted(review-affected)
    result["reusable_record_ids"]=sorted(after.keys()-affected)
    result["invalidations"]=[dict(record_id=nid,level="archive" if nid not in after else
        "invalidate_output" if before.get(nid,{}).get("media_sha256") or after.get(nid,{}).get("media_sha256") else "invalidate_plan") for nid in sorted(affected)]
    result["invalidations"].extend(dict(record_id=nid,level="review") for nid in sorted(review-affected))
    def view(plan,nid):
        node=next((n for n in plan["nodes"] if n["id"]==nid),{})
        return dict(layout={k:node.get(k) for k in LAYOUT},
                    groups=[g for g in plan.get("groups",[]) if nid in g.get("node_ids",[])])
    for row in result["invalidations"]:
        nid,level=row["record_id"],row["level"]
        causes=[c for c in result["changes"] if nid in c["affected_record_ids"]]
        sources=[c["source_record_id"] for c in causes] or [nid]
        evidence=({"source_changes":[c["evidence"] for c in causes]} if causes else
                  {"previous_view":view(previous,nid),"current_view":view(current,nid)})
        action=("回读分组/布局，不重新生成" if level=="review" else
                "归档旧版并保留文件/历史，只重验仍存在的后继" if level=="archive" else
                "从原责任层重编并重验；已有媒体保留，新生成仍需显式批准")
        row.update(source_record_id=sources[0],source_record_ids=sources,affected_record_ids=[nid],
                   reason="分组或布局视图变化" if level=="review" else "来源、内容或消费依赖变化",
                   evidence=evidence,next_action=action)
    return result


def _new_record(node, references, package, version):
    source_version=authored(node)["version"]
    record=dict(record_format="production-record/v1",scope="offline_plan_and_artifact_binding",record_id=node["id"],
        version=version,source_version=source_version,authored_node=authored(node),references=references,
        source_revision=_revision(node,references),state="recovering",review_status="NOT_VERIFIED")
    if package is not None:record["source_prompt_package"]=copy.deepcopy(package)
    return record


def _sync_node(node, record):
    for key in RUNTIME-{"source_record_id"}:
        node.pop(key,None)
        if key in record:node[key]=copy.deepcopy(record[key])
    node["source_record_id"]=record["record_id"]


def initialize_records(graph, prompts):
    graph=bind_prompt_content(graph,prompts)
    nodes,incoming,_,order=_graph_index(graph)
    packages={p["node_id"]:p for p in prompts};records={}
    for nid in order:
        record=_new_record(nodes[nid],_references(incoming[nid],records),packages.get(nid),nodes[nid].get("version",1))
        records[nid]=record;_sync_node(nodes[nid],record)
    graph.update(production_records=records,record_history={},graph_history=[],archived_records={},
        version=graph.get("version",1),generation_authorized=False)
    validate_records(graph)
    return graph


def apply_rework(previous, current, current_prompts=None):
    """Write actual changed records/history into a fresh graph; leave both inputs intact."""
    before,_,_,_=validate_records(previous)
    if "production_records" in current:
        validate_records(current)
    result=bind_prompt_content(current,current_prompts) if current_prompts is not None else copy.deepcopy(current)
    after,incoming,_,order=_graph_index(result)
    for snapshot in [previous]+previous.get("graph_history",[]):
        for aid,definition in (result.get("asset_definitions") or {}).items():
            old_definition=(snapshot.get("asset_definitions") or {}).get(aid)
            if old_definition is not None and digest(old_definition)!=digest(definition):
                raise ValueError("ASSET_SOURCE_VERSION_REUSED: "+aid)
    source_definitions_changed=digest(previous.get("asset_definitions"))!=digest(result.get("asset_definitions"))
    advice=rework_advice(previous,result)
    if advice["status"]!="PASS":raise ValueError(str(advice["failures"]))
    changed=set(advice["affected_record_ids"])
    packages={p["node_id"]:p for p in (current_prompts or [])}
    old_records=previous["production_records"]
    history=copy.deepcopy(previous.get("record_history",{}))
    archived=copy.deepcopy(previous.get("archived_records",{}))
    for nid in set(before)&set(after):
        if after[nid].get("role")=="asset_anchor" and (
                any(before[nid].get(k)!=after[nid].get(k) for k in ("asset_state","asset_description","asset_definition_sha256")) or
                authored(after[nid])["version"]<authored(before[nid])["version"]) and (
                authored(after[nid])["version"]<=authored(before[nid])["version"]):
            raise ValueError("ASSET_SOURCE_VERSION_REUSED: "+nid)
    for nid in changed&set(before):
        history.setdefault(nid,[]).append(copy.deepcopy(old_records[nid]))
        if nid not in after:
            archived[nid]=dict(copy.deepcopy(old_records[nid]),state="archived",previous_state=old_records[nid]["state"])
    records={}
    for nid in order:
        if nid not in changed and nid in old_records:
            records[nid]=copy.deepcopy(old_records[nid])
        else:
            package=packages.get(nid)
            if package is None and "prompt_content_sha256" in after[nid]:
                package=old_records.get(nid,{}).get("source_prompt_package")
                if package is None or digest(_prompt_content(package))!=after[nid]["prompt_content_sha256"]:
                    raise ValueError("actual new canonical prompt required: "+nid)
            old_versions=[r["version"] for r in history.get(nid,[])]+([old_records[nid]["version"]] if nid in old_records else [])
            version=max(authored(after[nid])["version"],max(old_versions,default=0)+1)
            records[nid]=_new_record(after[nid],_references(incoming[nid],records),package,version)
            causes=[c for c in advice["changes"] if nid in c["affected_record_ids"]]
            records[nid]["recovery"]=dict(scope="offline_native_plan",status="awaiting_revalidation",
                source_record_ids=[c["source_record_id"] for c in causes],
                responsibility_layers=sorted({c["failure_layer"] for c in causes}),
                reentry_states=sorted({c["reentry_state"] for c in causes}),
                remaining_gates=["production_capability_gate.py","reverse_claim_lint.py"])
        _sync_node(after[nid],records[nid])
    for change in advice["changes"]:
        actual=records.get(change["source_record_id"],{})
        change["evidence"]["current_source_revision"]=actual.get("source_revision")
        change["evidence"]["current_version"]=actual.get("version")
    histories=copy.deepcopy(previous.get("graph_history",[]))
    if changed or advice["review_record_ids"] or source_definitions_changed:
        histories.append({k:copy.deepcopy(v) for k,v in previous.items() if k not in
            {"graph_history","record_history","archived_records","production_records","rework"}})
    result.update(production_records=records,record_history=history,archived_records=archived,graph_history=histories,
        version=max(previous.get("version",1)+(1 if changed or advice["review_record_ids"] or source_definitions_changed else 0),result.get("version",1)),
        rework=advice,generation_authorized=False)
    validate_records(result)
    return result


def bind_record_packages(graph, prompts):
    packages=copy.deepcopy(prompts)
    for package in packages:
        record=graph["production_records"][package["node_id"]]
        package["record_binding"]={k:record[k] for k in ("record_id","version","source_revision")}
    return packages


def register_local_output(graph, record_id, path, *, version, source_revision, evidence_class="local_file_only"):
    """Import existing bytes for this precise record revision, never review them."""
    validate_records(graph)
    result=copy.deepcopy(graph)
    record=result["production_records"].get(record_id)
    if record is None or type(version) is not int or version!=record["version"] or source_revision!=record["source_revision"]:
        raise ValueError("STALE_OUTPUT_BINDING")
    if record["state"] not in {"graph_plan_ready","generated"}:
        raise ValueError("plan has not passed the real compiler gates")
    if evidence_class not in {"local_file_only","offline_fixture"}:
        raise ValueError("local import is not platform readback")
    path=Path(path).resolve(strict=True);sha=hashlib.sha256();size=0
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):
            sha.update(block);size+=len(block)
    if not size:raise ValueError("empty local artifact")
    if record.get("media_sha256") and record["media_sha256"]!=sha.hexdigest():
        raise ValueError("same record version cannot replace different bytes")
    record.update(state="generated",review_status="NOT_VERIFIED",media_path=str(path),media_sha256=sha.hexdigest(),
                  media_byte_count=size,media_evidence_class=evidence_class)
    _sync_node(next(n for n in result["nodes"] if n["id"]==record_id),record)
    validate_records(result)
    return result
