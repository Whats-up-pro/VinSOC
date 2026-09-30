"""Run the v2 retrieval gate without a model call or scorer change."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.ctu_network_public.contract import CASES, split_data, validate
from evaluation.dualsql_lite_ctu_gpt5_v2.agents import validate_link
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools


V1_REPORTS = (
    Path("results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662231091/E1.json"),
    Path("results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662683274/E2.json"),
    Path("results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662943266/E3.json"),
)


def evaluate_offline(tools: V2DatabaseTools, cases: list[dict[str, str]],
                     replay_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source aliases, absence of a source reference, and two negatives."""
    case_results = []
    no_reference_cases = []
    resolved = 0
    for case in cases:
        references = tools.source_references(case["question"])
        if not references:
            no_reference_cases.append(case["case_id"])
            linked = validate_link(case["question"],
                                   [{"table": "network_flows", "columns": ["source_dataset"]}],
                                   [], tools)
            passed = linked["error"] is None
        else:
            events = []
            for reference in references:
                answer = tools.value_search({"query": reference["surface"],
                                             "column": reference["column"]})
                events.append({"tool": "value_search",
                               "arguments": {"query": reference["surface"],
                                             "column": reference["column"]},
                               "result": answer})
            linked = validate_link(case["question"],
                                   [{"table": "network_flows", "columns": ["source_dataset"]}],
                                   events, tools)
            passed = linked["error"] is None and all(
                any(item["column"] == reference["column"] and
                    item["value"] == reference["value"]
                    for item in linked["grounded_values"]) for reference in references)
            resolved += int(passed)
        case_results.append({"case_id": case["case_id"], "references": references,
                             "passed": passed, "error": linked["error"]})
    wrong_row = tools.value_search({"query": "7", "column": "source_row_id"})
    absent_dataset = tools.value_search({"query": "unknown-source",
                                         "column": "source_dataset"})
    negatives = [not wrong_row["matches"],
                 not absent_dataset["matches"] and bool(absent_dataset["domain"])]
    replay = []
    for call in replay_calls:
        current = tools.value_search(call["arguments"])
        replay.append({"case_id": call["case_id"], "arguments": call["arguments"],
                       "resolution": current.get("resolution"),
                       "match_columns": sorted({item["column"] for item in current["matches"]}),
                       "match_values": [item["value"] for item in current["matches"]],
                       "domain_columns": ([call["arguments"]["column"]] if current["domain"]
                                          and call["arguments"].get("column") else [])})
    return {"gate_passed": (all(item["passed"] for item in case_results)
                            and all(negatives)),
            "referenced_cases_resolved": resolved,
            "no_reference_cases": no_reference_cases,
            "negative_controls_passed": sum(negatives),
            "case_results": case_results,
            "replay": replay}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path,
                        default=Path("evaluation/ctu_network_public/dataset_manifest.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Offline gate artifact already exists")
    dev = validate(args.snapshot)
    tools = V2DatabaseTools(args.snapshot, args.manifest)
    calls = []
    v1_hashes = {}
    for path in V1_REPORTS:
        raw = path.read_bytes()
        v1_hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        report = json.loads(raw)
        for case in report["case_results"]:
            calls.extend({"case_id": case["case_id"], "arguments": event["arguments"]}
                         for event in case["trajectory"] if event["tool"] == "value_search")
    cases = list(split_data(CASES).values())
    result = evaluate_offline(tools, cases, calls)
    result["snapshot_sha256"] = dev["logical_snapshot_sha256"]
    result["split_sha256"] = dev["split_sha256"]
    result["source_manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    result["catalog_sha256"] = tools.catalog_sha256
    result["v1_report_sha256"] = v1_hashes
    result["replayed_call_count"] = len(calls)
    result["gate_passed"] &= (len(cases) == 8 and result["referenced_cases_resolved"] == 7
                              and result["no_reference_cases"] == ["ctu_sql_008"]
                              and result["negative_controls_passed"] == 2
                              and len(calls) == 27)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, indent=2, sort_keys=True)
        destination.write("\n")
    print(json.dumps({"gate_passed": result["gate_passed"],
                      "referenced_cases_resolved": result["referenced_cases_resolved"],
                      "no_reference_cases": result["no_reference_cases"],
                      "negative_controls_passed": result["negative_controls_passed"],
                      "replayed_call_count": len(calls)}))
    return 0 if result["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
