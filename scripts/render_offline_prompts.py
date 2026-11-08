#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_offline_prompts —— 从 Prompt Package JSONL 生成可审阅 Markdown。

用途：消除“JSON 包”和“手写 Markdown”双份维护造成的漂移。

用法：
  python3 scripts/render_offline_prompts.py <package_dir>
  python3 scripts/render_offline_prompts.py --self-test

会生成：
  <package_dir>/04_Asset_Prompts.md
  <package_dir>/05_Storyboard_Prompts.md
  <package_dir>/06_Video_Prompts.md
  <package_dir>/07_Audio_Composite_Prompts.md
  <package_dir>/prompt_render_manifest.json

输入格式：
  权威来源是主编译器产出的 Prompt Package（`prompt-package/v1`）。旧版
  `03_Prompt_Packages.jsonl` 布局（带 prompt_id / target_type 的扁平行）通过
  **单向适配** 读入；未知格式必须报错，不得静默生成 0 份文档后返回成功。

不联网、不点火、不写平台画布。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile


# The canonical package format produced by scripts/compile_prompt_packages.py.
PROMPT_PACKAGE_FORMAT = "prompt-package/v1"

# The legacy offline layout. Supported through a one-way adapter only; the
# adapter never writes back into the canonical format.
LEGACY_FORMAT_MARKERS = ("prompt_id", "target_type")


class UnsupportedPackageFormat(RuntimeError):
    """Raised when the input is neither the canonical nor the legacy format."""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def detect_format(packages):
    """Return 'canonical', 'legacy' or raise for an unsupported input."""
    if not isinstance(packages, list) or not packages:
        raise UnsupportedPackageFormat(
            "Prompt Package 输入为空：既不是 %s，也不是旧版布局；不生成任何文档。"
            % PROMPT_PACKAGE_FORMAT
        )
    formats = set()
    for item in packages:
        if not isinstance(item, dict):
            raise UnsupportedPackageFormat("Prompt Package 行必须是 JSON 对象")
        declared = item.get("prompt_format")
        if declared:
            formats.add(str(declared))
        elif all(marker in item for marker in LEGACY_FORMAT_MARKERS):
            formats.add("legacy")
        else:
            raise UnsupportedPackageFormat(
                "无法识别的 Prompt Package 行格式（缺少 prompt_format，且不是旧版 "
                "prompt_id/target_type 布局）：%r" % (sorted(item.keys())[:8],)
            )
    if len(formats) > 1:
        raise UnsupportedPackageFormat(
            "Prompt Package 混用了多种格式：%s；必须单一格式。" % ", ".join(sorted(formats))
        )
    only = formats.pop()
    if only != PROMPT_PACKAGE_FORMAT and only != "legacy":
        raise UnsupportedPackageFormat(
            "不支持的 Prompt Package 格式 %r；本渲染器只接受 %s 或旧版布局。"
            % (only, PROMPT_PACKAGE_FORMAT)
        )
    return only


def adapt_legacy_package(item):
    """One-way adapter: legacy flat row -> canonical package shape."""

    blocks = item.get("blocks")
    if isinstance(blocks, dict):
        adapted_blocks = dict(blocks)
    else:
        adapted_blocks = {}
        for block in item.get("blocks") or []:
            if isinstance(block, dict) and block.get("name"):
                adapted_blocks[str(block["name"])] = block.get("text") or ""
    duration = item.get("duration") if isinstance(item.get("duration"), dict) else {}
    route = item.get("model_route") if isinstance(item.get("model_route"), dict) else {}
    target = item.get("target_type")
    node_type = {"video": "video", "audio": "audio", "image": "image", "asset": "image"}.get(
        str(target), "text"
    )
    return {
        "prompt_format": PROMPT_PACKAGE_FORMAT,
        "node_id": item.get("node_id") or item.get("prompt_id") or "unnamed",
        "prompt_id": item.get("prompt_id"),
        "shot_id": item.get("shot_id"),
        "role": item.get("role") or target or "text",
        "node_type": node_type,
        "target_type": target,
        "blocks": adapted_blocks,
        "unresolved": list(item.get("unresolved") or []),
        "missing_blocks": list(item.get("missing_blocks") or []),
        "status": item.get("status") or "READY",
        "duration": {
            "seconds": duration.get("seconds"),
            "mode": duration.get("mode") or "single_shot",
        },
        "model_route": {"model": route.get("model"), "mode": route.get("mode")},
        "source_record_id": item.get("source_record_id"),
        "constraint_evidence": list(item.get("constraint_evidence") or []),
    }



def render(package):
    src = os.path.join(package, "03_Prompt_Packages.jsonl")
    if not os.path.isfile(src):
        raise RuntimeError("缺 Prompt Package：%s" % src)
    raw_packages = load_jsonl(src)
    source_format = detect_format(raw_packages)
    packages = [
        item if source_format == PROMPT_PACKAGE_FORMAT else adapt_legacy_package(item)
        for item in raw_packages
    ]
    legacy_dir = os.path.join(package, "generated")
    if os.path.isdir(legacy_dir):
        shutil.rmtree(legacy_dir)
    target_files = {
        "asset": "04_Asset_Prompts.md",
        "storyboard": "05_Storyboard_Prompts.md",
        "video": "06_Video_Prompts.md",
        "audio": "07_Audio_Composite_Prompts.md",
        "composite": "07_Audio_Composite_Prompts.md",
    }
    grouped = {}
    for item in packages:
        key = target_files.get(item.get("target_type"))
        if not key:
            continue
        grouped.setdefault(key, []).append(item)
    if not grouped:
        raise UnsupportedPackageFormat(
            "Prompt Package 中没有任何可渲染的 target_type（已知：%s）；"
            "不生成 0 份文档后返回成功。"
            % ", ".join(sorted(target_files))
        )

    source_map_path = os.path.join(package, "04_Source_Node_Map.json")
    source_map = {}
    if os.path.isfile(source_map_path):
        source_map = json.load(io.open(source_map_path, encoding="utf-8"))

    generated = {}
    for name, items in grouped.items():
        lines = [
            "# %s" % name.replace(".md", ""),
            "",
            "> 本文件由 `%s` 生成；禁止手改。" % os.path.basename(src),
            "> 正本格式：%s（输入格式：%s）。" % (PROMPT_PACKAGE_FORMAT, source_format),
            "",
        ]
        if name.startswith("04_") and source_map:
            lines += ["## 观测节点映射", "", "| 计划节点 | W2 观测节点 | 用途 |", "|---|---|---|"]
            for observed, meta in sorted((source_map.get("observed_w2_nodes") or {}).items()):
                lines.append("| `%s` | `%s` | %s |" % (
                    meta.get("plan_node", ""), observed, meta.get("role", "")))
            lines.append("")
        for item in items:
            pid = item.get("prompt_id") or item.get("node_id") or "unnamed"
            duration = item.get("duration") or {}
            route = item.get("model_route") or {}
            lines += [
                "## %s · %s" % (pid, item.get("target_type") or ""),
                "",
                "```text",
                "prompt_id: %s" % pid,
                "source_record_id: %s" % (item.get("source_record_id") or ""),
                "duration_seconds: %s" % (duration.get("seconds", "")),
                "duration_mode: %s" % (duration.get("mode", "")),
                "model: %s" % (route.get("model", "")),
                "mode: %s" % (route.get("mode", "")),
                "",
            ]
            blocks = item.get("blocks") or {}
            if isinstance(blocks, dict):
                block_items = list(blocks.items())
            else:
                block_items = [
                    (block.get("name") or "未命名", block.get("text") or "")
                    for block in blocks or []
                    if isinstance(block, dict)
                ]
            for key, value in block_items:
                lines += [
                    "【%s】" % key,
                    value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
                    "",
                ]
            lines.append("```")
            lines.append("")
        path = os.path.join(package, name)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines).rstrip() + "\n")
        generated[os.path.relpath(path, package).replace("\\", "/")] = sha256(path)
    audit_hashes = {}
    for name in ("06A_Video_Prompt_A_audit.md", "06B_Video_Prompt_B_audit.md"):
        path = os.path.join(package, name)
        if os.path.isfile(path):
            audit_hashes[name] = sha256(path)
    manifest = {
        "schema": "offline-prompt-render/v2",
        "source": "03_Prompt_Packages.jsonl",
        "source_sha256": sha256(src),
        "source_format": source_format,
        "canonical_format": PROMPT_PACKAGE_FORMAT,
        "generated": generated,
        "audit_sources": audit_hashes,
    }
    manifest_path = os.path.join(package, "prompt_render_manifest.json")
    with io.open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return manifest_path, generated



def self_test():
    root = tempfile.mkdtemp(prefix="offline_render_")
    try:
        # legacy layout still renders (one-way adapter)
        with io.open(os.path.join(root, "03_Prompt_Packages.jsonl"), "w",
                     encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({
                "prompt_id": "p1",
                "target_type": "video",
                "source_record_id": "r1",
                "blocks": [{"name": "时间线", "text": "已经启动"}],
                "duration": {"seconds": 5, "mode": "single_shot"},
                "model_route": {"model": "M", "mode": "mixed2video"},
            }, ensure_ascii=False) + "\n")
        manifest_path, generated = render(root)
        if len(generated) != 1 or not os.path.isfile(manifest_path):
            return 1
        with io.open(os.path.join(root, "03_Prompt_Packages.jsonl"), "w",
                     encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({
                "prompt_format": PROMPT_PACKAGE_FORMAT,
                "node_id": "n1",
                "target_type": "video",
                "role": "video_candidate",
                "blocks": {"action": "镜头运动"},
                "duration": {"seconds": 5, "mode": "single_shot"},
                "model_route": {"model": "M", "mode": "mixed2video"},
            }, ensure_ascii=False) + "\n")
        manifest_path, generated = render(root)
        if len(generated) != 1 or not os.path.isfile(manifest_path):
            return 1
        # unknown format must raise, not succeed with 0 documents
        with io.open(os.path.join(root, "03_Prompt_Packages.jsonl"), "w",
                     encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"unexpected": "shape"}, ensure_ascii=False) + "\n")
        try:
            render(root)
        except UnsupportedPackageFormat:
            pass
        else:
            return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("self-test 通过")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["--self-test"], ["-t"]):
        return self_test()
    parser = argparse.ArgumentParser(description="Prompt Package -> Markdown renderer")
    parser.add_argument("package", nargs="?", help="离线生成包目录")
    args = parser.parse_args(argv)
    if not args.package:
        parser.print_help()
        return 2
    try:
        manifest, generated = render(os.path.abspath(args.package))
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    print("已生成 %d 个 Markdown" % len(generated))
    print("manifest=%s" % manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
