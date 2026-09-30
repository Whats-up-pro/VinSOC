"""Snapshot and source-metadata-grounded retrieval for the CTU v2 experiment."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.tools import (
    CTUDatabaseTools,
    MAX_RESPONSE_BYTES,
    _size,
)


TOOL_VERSION = "dualsql_lite_ctu_gpt5_tools_v3"
LOW_CARDINALITY_LIMIT = 50


def _normal(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


class V2DatabaseTools(CTUDatabaseTools):
    """Keep the v1 snapshot boundary while adding metadata-backed aliases."""

    def __init__(self, snapshot_path: str | Path, manifest_path: str | Path):
        super().__init__(snapshot_path)
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("Source metadata is missing")
        dataset_values = {item["value"] for item in self.catalog
                          if item["column"] == "source_dataset"}
        self.source_aliases: dict[str, list[str]] = {}
        for source in sources:
            dataset_id = source.get("dataset_id")
            source_name = source.get("source_name")
            if (not isinstance(dataset_id, str) or dataset_id not in dataset_values
                    or not isinstance(source_name, str) or not source_name.strip()
                    or dataset_id in self.source_aliases):
                raise ValueError("Source metadata does not match the snapshot")
            words = _normal(source_name).split()
            aliases = [_normal(dataset_id), _normal(source_name)]
            aliases.extend(" ".join(words[index:]) for index in range(len(words) - 1))
            self.source_aliases[dataset_id] = sorted(set(aliases), key=len, reverse=True)
        if set(self.source_aliases) != dataset_values:
            raise ValueError("Source metadata is incomplete for this snapshot")
        self.domains: dict[str, list[str]] = {}
        for column in self.schema["network_flows"]:
            values = [item["value"] for item in self.catalog
                      if item["column"] == column["name"]]
            if 0 < len(values) <= LOW_CARDINALITY_LIMIT:
                self.domains[column["name"]] = values
        encoded = json.dumps({"catalog": self.catalog, "source_aliases": self.source_aliases},
                             sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.catalog_sha256 = hashlib.sha256(encoded).hexdigest()
        self.observed_evidence: dict[str, dict[str, Any]] = {}

    def _remember(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("ok") and result.get("evidence_id"):
            self.observed_evidence[result["evidence_id"]] = deepcopy(result)
        return result

    def source_reference_error(self, question: str) -> str | None:
        normalized = f" {_normal(question)} "
        aliases: dict[str, set[str]] = {}
        for value, names in self.source_aliases.items():
            for alias in names:
                aliases.setdefault(alias, set()).add(value)
        for alias, values in aliases.items():
            if len(alias.split()) >= 2 and f" {alias} " in normalized and len(values) > 1:
                return "AMBIGUOUS_SOURCE_REFERENCE"
        # Derive numbered source-name patterns from metadata, never benchmark IDs.
        for alias in aliases:
            words = alias.split()
            if len(words) >= 2 and words[-1].isdigit():
                prefix = " ".join(words[:-1])
                for mention in re.findall(r"(?<!\w)" + re.escape(prefix) + r"\s+\d+(?!\w)", normalized):
                    if mention not in aliases:
                        return "UNKNOWN_SOURCE_REFERENCE"
        return None

    def source_references(self, question: str) -> list[dict[str, str]]:
        normalized = f" {_normal(question)} "
        found: list[dict[str, str]] = []
        for value, aliases in self.source_aliases.items():
            surface = next((alias for alias in aliases if len(alias.split()) >= 2
                            and f" {alias} " in normalized), None)
            if surface is not None:
                found.append({"surface": surface, "column": "source_dataset",
                              "value": value, "evidence_class": "source_metadata"})
        return found

    def database_profiler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = super().database_profiler(arguments)
        if not base.get("ok"):
            return base
        base["domains"] = {}
        base["truncated_domains"] = []
        for column, values in self.domains.items():
            entries = [{"value": value, "evidence_id": base["evidence_id"],
                        **({"source_name": next((source for source in
                            self.source_aliases.get(value, []) if " " in source), value)}
                           if column == "source_dataset" else {})}
                       for value in values]
            base["domains"][column] = entries
            if _size(base) > MAX_RESPONSE_BYTES:
                del base["domains"][column]
                base["truncated_domains"].append(column)
        return self._remember(base)

    def value_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = super().value_search(arguments)
        if not base.get("ok"):
            return base
        query = arguments["query"].strip()
        requested_column = arguments.get("column")
        evidence_id = base["evidence_id"]
        matches: list[dict[str, str]] = []
        normalized_query = _normal(query)
        if requested_column in (None, "source_dataset"):
            aliases = [(dataset_id, alias) for dataset_id, values in self.source_aliases.items()
                       for alias in values if alias == normalized_query]
            values = {dataset_id for dataset_id, _ in aliases}
            if len(values) == 1:
                dataset_id = next(iter(values))
                matches.append({"table": "network_flows", "column": "source_dataset",
                                "value": dataset_id, "evidence_id": evidence_id,
                                "match_basis": "source_metadata"})
        for item in base["matches"]:
            if (len(normalized_query) < 2
                    and item["column"] not in self.domains):
                continue
            if not any(match["column"] == item["column"] and
                       match["value"] == item["value"] for match in matches):
                matches.append({**item, "match_basis": "substring"})
        result: dict[str, Any] = {"ok": True, "evidence_id": evidence_id,
                                  "matches": matches, "resolution": "matched" if matches else "unresolved",
                                  "truncated": base["truncated"], "domain": []}
        if not matches and requested_column in self.domains:
            result["domain"] = [{"value": value, "evidence_id": evidence_id}
                                for value in self.domains[requested_column]]
        while _size(result) > MAX_RESPONSE_BYTES and result["matches"]:
            result["matches"].pop()
            result["truncated"] = True
        if _size(result) > MAX_RESPONSE_BYTES:
            result["domain"] = []
            result["truncated"] = True
        return self._remember(result)

    def sql_probe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._remember(super().sql_probe(arguments))
