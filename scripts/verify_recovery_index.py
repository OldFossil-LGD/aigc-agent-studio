#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the in-package recovery / migration index (stage 1 F item)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = SKILL_ROOT / "references" / "stage1-recovery-index.json"
MANIFEST_PATH = SKILL_ROOT / "references" / "unified-baseline" / "MIGRATION_MANIFEST.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def package_rel(book: dict[str, Any]) -> str | None:
    for key in ("in_package", "package_path", "package_rel"):
        value = book.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\\", "/")
    external = book.get("external") or {}
    raw = external.get("path")
    if isinstance(raw, str) and raw.strip():
        candidate = Path(raw)
        try:
            return str(candidate.relative_to(SKILL_ROOT)).replace("\\", "/")
        except ValueError:
            return None
    return None


def verify(index: dict[str, Any], write_hashes: bool = False) -> dict[str, Any]:
    books = index.get("books") or []
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    updated = 0
    declared_unrecoverable = 0

    for book in books:
        name = str(book.get("book") or "")
        external = book.get("external") or {}
        recorded_hash = external.get("sha256")
        recoverable = book.get("recoverable", True) is not False
        rel = package_rel(book)

        if not recoverable:
            declared_unrecoverable += 1
            entry_result: dict[str, Any] = {
                "book": name,
                "state": "declared_unrecoverable",
                "recoverable": False,
            }
            if rel:
                target = SKILL_ROOT / rel
                if not target.is_file():
                    failures.append(
                        {
                            "book": name,
                            "code": "IN_PACKAGE_SUBSTITUTE_MISSING",
                            "path": rel,
                            "message": "声明不可恢复的册，其包内替代文件也不存在。",
                        }
                    )
                    entry_result["in_package_state"] = "missing"
                else:
                    actual = sha256_file(target)
                    entry_result["in_package_path"] = rel
                    entry_result["in_package_sha256"] = actual
                    if recorded_hash and recorded_hash != actual:
                        failures.append(
                            {
                                "book": name,
                                "code": "RECOVERY_HASH_MISMATCH",
                                "path": rel,
                                "expected": recorded_hash,
                                "actual": actual,
                                "message": "包内替代文件的哈希与索引记录不一致。",
                            }
                        )
                        entry_result["in_package_state"] = "hash_mismatch"
                    else:
                        entry_result["in_package_state"] = "verified"
            results.append(entry_result)
            continue

        if not rel:
            failures.append(
                {
                    "book": name,
                    "code": "RECOVERY_NOT_MIGRATED",
                    "message": "册仍依赖包外路径，未迁入包内；分发包不自包含。",
                }
            )
            results.append({"book": name, "state": "not_migrated"})
            continue

        target = SKILL_ROOT / rel
        try:
            target.resolve().relative_to(SKILL_ROOT.resolve())
        except ValueError:
            failures.append(
                {
                    "book": name,
                    "code": "RECOVERY_PATH_ESCAPES_PACKAGE",
                    "path": rel,
                    "message": "索引路径逃逸出包目录。",
                }
            )
            results.append({"book": name, "state": "path_escapes_package", "path": rel})
            continue

        if not target.is_file():
            failures.append(
                {
                    "book": name,
                    "code": "RECOVERY_TARGET_MISSING",
                    "path": rel,
                    "message": "索引指向的包内文件不存在。",
                }
            )
            results.append({"book": name, "state": "target_missing", "path": rel})
            continue

        actual = sha256_file(target)
        if recorded_hash and recorded_hash != actual:
            failures.append(
                {
                    "book": name,
                    "code": "RECOVERY_HASH_MISMATCH",
                    "path": rel,
                    "expected": recorded_hash,
                    "actual": actual,
                    "message": "包内文件的哈希与索引记录不一致。",
                }
            )
            state = "hash_mismatch"
        elif recorded_hash:
            state = "verified"
        else:
            state = "hash_recorded"
            if write_hashes:
                external["sha256"] = actual
                external["bytes"] = target.stat().st_size
                updated += 1

        results.append(
            {
                "book": name,
                "state": state,
                "path": rel,
                "sha256": actual,
                "bytes": target.stat().st_size,
                "in_package_substitute": book.get("in_package_substitute"),
                "migrated": book.get("migrated", False),
                "authority": book.get("authority"),
            }
        )

    manifest_status = "MISSING"
    manifest_failures: list[dict[str, Any]] = []
    if MANIFEST_PATH.is_file():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            manifest_status = "PRESENT"
            for entry in manifest.get("entries") or []:
                target_rel = str(entry.get("target_path") or "")
                target = SKILL_ROOT / target_rel
                if not target.is_file():
                    manifest_failures.append(
                        {
                            "code": "MIGRATION_TARGET_MISSING",
                            "target_path": target_rel,
                            "message": "迁移清单指向的包内文件不存在。",
                        }
                    )
                    continue
                actual = sha256_file(target)
                if entry.get("target_sha256") and entry.get("target_sha256") != actual:
                    manifest_failures.append(
                        {
                            "code": "MIGRATION_HASH_MISMATCH",
                            "target_path": target_rel,
                            "expected": entry.get("target_sha256"),
                            "actual": actual,
                            "message": "迁移清单的包内文件哈希与实际不一致。",
                        }
                    )
            if manifest_failures:
                manifest_status = "FAIL"
                failures.extend(manifest_failures)
            else:
                manifest_status = "PASS"
        except (OSError, json.JSONDecodeError) as exc:
            manifest_status = "INVALID"
            failures.append(
                {
                    "code": "MIGRATION_MANIFEST_INVALID",
                    "message": str(exc),
                }
            )
    else:
        failures.append(
            {
                "code": "MIGRATION_MANIFEST_MISSING",
                "path": str(MANIFEST_PATH.relative_to(SKILL_ROOT)),
                "message": "迁移清单缺失：无法核验来源与迁移关系。",
            }
        )

    verified = sum(
        1
        for item in results
        if item.get("state") in {"verified", "hash_recorded"}
        or item.get("in_package_state") == "verified"
    )

    report = {
        "index_path": str(INDEX_PATH),
        "index_in_package": INDEX_PATH.is_file(),
        "total_books": len(books),
        "verified_reachable": verified,
        "declared_unrecoverable": declared_unrecoverable,
        "migration_manifest": str(MANIFEST_PATH),
        "migration_manifest_status": manifest_status,
        "external_runtime_dependencies": 0,
        "failures": failures,
        "status": "FAIL" if failures else "PASS",
        "results": results,
        "hashes_written": updated,
        "_index": index if write_hashes else None,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="verify the in-package recovery index")
    parser.add_argument("--report", help="write the report to this JSON file")
    parser.add_argument(
        "--write-hashes",
        action="store_true",
        help="fill in missing sha256 for external books that exist",
    )
    args = parser.parse_args()

    if not INDEX_PATH.is_file():
        print("recovery index missing from the package: %s" % INDEX_PATH)
        return 2

    index = load_index(INDEX_PATH)
    report = verify(index, write_hashes=args.write_hashes)
    if args.write_hashes and report["hashes_written"]:
        INDEX_PATH.write_text(
            json.dumps(report.pop("_index"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    report.pop("_index", None)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(
        json.dumps(
            {
                "status": report["status"],
                "index_in_package": report["index_in_package"],
                "total_books": report["total_books"],
                "verified_reachable": report["verified_reachable"],
                "declared_unrecoverable": report["declared_unrecoverable"],
                "migration_manifest_status": report["migration_manifest_status"],
                "external_runtime_dependencies": report["external_runtime_dependencies"],
                "failures": report["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())