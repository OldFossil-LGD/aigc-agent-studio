"""Offline GrillMe walkthrough — no agent, no API key, no network.

Run from the repository root:

    python examples/grillme_walkthrough.py

It shows the whole loop: record what the brief already says, ask the single
next question the engine selects, answer it, fill safe library presets, then
compile and validate the Creative Intent Contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.grill_session import (  # noqa: E402
    answer,
    default_rest,
    finish,
    new_session,
    record_facts,
    select,
)

BRIEF = "5 秒、9:16 竖屏剪纸空镜，蓝色墙面，只要雨声；固定俯拍，只要提示词，不生成。"

FACTS = {
    "G01": "prompt_only",
    "G03": 5,
    "G04": "9:16",
    "G06": {"style_id": "剪纸风格：色块平涂、剪裁边缘干净、纸纤维哑光",
            "register": "stylized"},
    "G08": "ambience_only",
    "I11": {"must_have": ["雨声", "蓝色墙面"], "must_never": ["人物", "配乐"]},
    "I17": "none",
}


def main() -> int:
    session = new_session(BRIEF)
    record_facts(session, FACTS)
    print("brief:", BRIEF)
    print("facts recorded from the brief:", ", ".join(FACTS))

    choice = select(session)
    if choice["status"] != "QUESTION":
        print("nothing left to ask:", choice["status"])
        return 1
    question = choice["question"]
    print("\nnext question (%s, score %s): %s"
          % (question["id"], choice["score"], question["title"]))
    print("  " + question["question"])
    print("  recommendation: " + question["recommendation"])

    answer(session, question["id"], "空镜按「时间在走、画面无人」处理；影子推进即时间推进。")
    print("\nanswered:", question["id"])

    filled = default_rest(session)
    print("library defaults applied:", ", ".join(filled) or "none")

    result = finish(session)
    contract = result["contract"]
    print("\nfinish:", result["status"])
    print("contract:", contract["contract_id"], contract["status"],
          "| revision", contract["revision"])
    print("decisions:", len(contract["decisions"]),
          "| unresolved:", len(contract["unresolved"]),
          "| conflicts:", len(contract["blocking_conflicts"]))
    print("generation_authorized:", contract["authorization"]["generation_authorized"])

    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    path = out / "grillme-example.contract.json"
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written:", path.relative_to(ROOT))
    return 0 if result["status"] == "READY_FOR_PLANNING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
