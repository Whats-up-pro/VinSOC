"""Validate the existing R1 frozen split offline, without model or tool execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent.tools import get_tool_schemas
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.models import ToolCallCase
from evaluation.tool_calling.provenance import canonical_sha256

FROZEN_DIR = Path("evaluation/tool_calling/benchmarks/frozen")
DEV_DIR = Path("evaluation/tool_calling/benchmarks/dev")
BASELINE = Path("results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json")


def _source_sha256(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _validate_case(data: Any, filename: str, schema_properties: dict[str, set[str]]) -> ToolCallCase:
    if not isinstance(data, dict):
        raise ValueError(f"{filename}: case must be a JSON object")
    for key in ("case_id", "category", "difficulty", "request", "expected_calls", "forbidden_tools"):
        if key not in data:
            raise ValueError(f"{filename}: missing {key}")
    if not isinstance(data["case_id"], str) or not data["case_id"]:
        raise ValueError(f"{filename}: invalid case_id")
    if not isinstance(data["request"], str) or not data["request"].strip():
        raise ValueError(f"{filename}: invalid request")
    if not isinstance(data["expected_calls"], list) or not isinstance(data["forbidden_tools"], list):
        raise ValueError(f"{filename}: invalid expected_calls or forbidden_tools")
    if data["case_id"] + ".json" != filename:
        raise ValueError(f"{filename}: case ID and filename mismatch")
    call_ids: set[str] = set()
    for call in data["expected_calls"]:
        if not isinstance(call, dict) or not isinstance(call.get("call_id"), str):
            raise ValueError(f"{filename}: malformed expected call")
        if call["call_id"] in call_ids:
            raise ValueError(f"{filename}: duplicate expected call ID")
        call_ids.add(call["call_id"])
        name = call.get("tool")
        if name not in schema_properties:
            raise ValueError(f"{filename}: unknown tool {name!r}")
        arguments = call.get("required_arguments")
        critical = call.get("critical_arguments")
        if (not isinstance(arguments, dict) or not isinstance(critical, list)
                or not set(arguments).issubset(schema_properties[name])
                or not set(critical).issubset(arguments)):
            raise ValueError(f"{filename}: expected arguments incompatible with production schema")
    if not all(isinstance(name, str) and name in schema_properties for name in data["forbidden_tools"]):
        raise ValueError(f"{filename}: unknown forbidden tool")
    if set(data["forbidden_tools"]).intersection(call["tool"] for call in data["expected_calls"]):
        raise ValueError(f"{filename}: tool both expected and forbidden")
    try:
        case = ToolCallCase.from_dict(data)
        compute_case_metrics(case, [])  # Prove the unchanged scorer can load and score it offline.
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{filename}: scorer cannot load case") from exc
    return case


def build_compatibility_lock(directory: Path = FROZEN_DIR) -> dict[str, Any]:
    """Build a deterministic structural lock; no provider is imported or created."""
    directory = Path(directory)
    paths = sorted(directory.glob("frozen_*.json"))
    if len(paths) != 8:
        raise ValueError("R1 frozen split must contain exactly eight cases")
    schemas = get_tool_schemas()
    schema_properties = {
        item["function"]["name"]: set(item["function"]["parameters"]["properties"])
        for item in schemas
    }
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    schema_hash = canonical_sha256(schemas)
    if schema_hash != baseline["provenance"]["production_schema_sha256"]:
        raise ValueError("R1 production schema changed since dev baseline")
    dev_lock = json.loads((DEV_DIR / "VERSION.lock").read_text(encoding="utf-8"))
    scorer_hashes = {name: _source_sha256(Path(name)) for name in dev_lock["scorer_files"]}
    if (scorer_hashes != dev_lock["scorer_file_sha256"]
            or canonical_sha256(scorer_hashes) != dev_lock["scorer_sha256"]):
        raise ValueError("R1 scorer changed since dev lock")
    contents: dict[str, Any] = {}
    case_ids: set[str] = set()
    dev_ids = {path.stem for path in DEV_DIR.glob("case_*.json")}
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path.name}: malformed JSON") from exc
        case = _validate_case(data, path.name, schema_properties)
        if case.case_id in case_ids:
            raise ValueError(f"{path.name}: duplicate case ID")
        case_ids.add(case.case_id)
        contents[path.name] = data
    if case_ids.intersection(dev_ids):
        raise ValueError("R1 frozen and dev case IDs overlap")
    case_hashes = {name: canonical_sha256(data) for name, data in contents.items()}
    return {
        "version": "r1_a1_frozen_compatibility_v1",
        "case_count": len(contents),
        "case_ids": sorted(case_ids),
        "split_sha256": canonical_sha256(contents),
        "case_files_sha256": case_hashes,
        "case_directory_sha256": canonical_sha256(case_hashes),
        "hash_canonicalization": "UTF-8 JSON with sorted object keys and compact separators; scorer source line endings normalized to LF",
        "production_schema_sha256": schema_hash,
        "production_tool_names": sorted(schema_properties),
        "scorer_sha256": dev_lock["scorer_sha256"],
        "scorer_file_sha256": scorer_hashes,
        "model_calls": 0,
        "validation": "case structure, production tool/argument names, dev separation, and offline scorer load",
    }


def verify_compatibility_lock(
    directory: Path = FROZEN_DIR, lock_path: Path | None = None
) -> dict[str, Any]:
    directory = Path(directory)
    lock_path = Path(lock_path) if lock_path is not None else directory / "COMPATIBILITY.lock"
    actual = build_compatibility_lock(directory)
    expected = json.loads(lock_path.read_text(encoding="utf-8"))
    if actual != expected:
        raise ValueError("R1 frozen compatibility lock mismatch")
    return actual


def main() -> int:
    result = verify_compatibility_lock()
    print(json.dumps({"version": result["version"], "case_count": result["case_count"],
                      "case_directory_sha256": result["case_directory_sha256"],
                      "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
