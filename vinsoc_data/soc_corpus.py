"""Pinned synthetic SOC observations; labels and reference reports never enter this store."""

from __future__ import annotations
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import urllib.request

import duckdb

REVISION = "fe94a95dadbd188c2bf137a9785b82cb5f7865c2"
SOURCE_MANIFEST = {
    "revision": REVISION,
    "license": "Apache-2.0",
    "files": {
        "test.parquet": "9ef309da7ad04f173d89a5f8da238f20db4051b92514531667b30c042da7bd1a",
        "validation.parquet": "94cd7987fe3064cd0933d8fabed75d517e955f8faa8723ac07c9b01446cdfcf7",
    },
}
ALERT_FIELDS = set("alert_id title severity source host user timestamp description".split())
FIELDS = {
    "events": set(
        "access_mask account action app auth_package binary_path bytes_in bytes_out channel cmdline dst_domain dst_ip dst_port duration_min encryption event_id extension file_path forward_to host ip label_length location logon_type message package parent_process path process query_type registry_key renamed_files rule_name sender service service_name share signed source src_host src_ip target_process task_name timestamp url user user_agent value".split()
    ),
    "process_tree": set("cmdline hash_sha256 image parent_image path pid signed user".split()),
    "asset": set(
        "criticality edr_installed hostname internet_exposed ip last_patch_days os owner role vlan".split()
    ),
    "related_alerts": set("alert_id host severity status timestamp title user".split()),
}
PAYLOADS = {
    "get_surrounding_events": ("events", "events"),
    "get_process_tree": ("process_tree", "tree"),
    "get_asset_context": ("asset", "asset"),
    "get_related_alerts": ("related_alerts", "alerts"),
}


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sources(source_dir: Path, manifest: dict) -> dict:
    if manifest != SOURCE_MANIFEST:
        raise ValueError("UNPINNED_SOC_SOURCE")
    actual = {}
    for name, expected in manifest["files"].items():
        path = Path(source_dir) / name
        if not path.is_file() or file_digest(path) != expected:
            raise ValueError("SOC_SOURCE_DIGEST_MISMATCH:" + name)
        actual[name] = expected
    return actual


def fetch_sources(source_dir: Path) -> dict:
    root = Path(source_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, expected in SOURCE_MANIFEST["files"].items():
        p = root / name
        if p.exists():
            if file_digest(p) != expected:
                raise ValueError("SOC_SOURCE_CACHE_MISMATCH")
            continue
        relative = "data/" + name.replace(".parquet", "-00000-of-00001.parquet")
        url = f"https://huggingface.co/datasets/alirezaaminzadeh/soc-agent-traces-100k/resolve/{REVISION}/{relative}"
        temporary = p.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=90) as response:
            temporary.write_bytes(response.read())
        if file_digest(temporary) != expected:
            raise ValueError("SOC_DOWNLOAD_DIGEST_MISMATCH")
        temporary.replace(p)
    return verify_sources(root, SOURCE_MANIFEST)


def _sanitize(data, allowed):
    if not isinstance(data, dict):
        raise ValueError("NON_OBJECT_OBSERVATION")
    clean = {}
    for key, value in data.items():
        if key == "decisive":
            continue
        if key not in allowed or isinstance(value, (dict, list)):
            raise ValueError("UNSUPPORTED_FIELD:" + key)
        if value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("UNSUPPORTED_TYPE")
        clean[key] = value
    canonical(clean)
    return clean


def extract_case(row: dict, *, split: str, file_sha256: str) -> dict:
    scenario = row["scenario_id"]
    observations = {}
    conflicts = set()
    quarantine = []
    alert = json.loads(row["alert"])
    input_data = {k: v for k, v in alert.items() if k in ALERT_FIELDS}
    input_data = _sanitize(input_data, ALERT_FIELDS)
    calls = {}
    available = set()
    for index, message in enumerate(json.loads(row["trace"])):
        for call in message.get("tool_calls", []):
            calls[call["id"]] = call["function"]["name"]
        tool = calls.get(message.get("tool_call_id"))
        if message.get("role") != "tool" or tool not in PAYLOADS:
            continue
        resource, field = PAYLOADS[tool]
        payload = json.loads(message["content"])
        items = payload.get(field)
        object_payload = isinstance(items, dict)
        if object_payload:
            items = [items]
        if not isinstance(items, list):
            continue
        available.add(resource)
        for item_index, item in enumerate(items):
            pointer = f"/trace/{index}/content/{field}" + (
                "" if object_payload else f"/{item_index}"
            )
            provenance = {
                "dataset_revision": REVISION,
                "file_sha256": file_sha256,
                "split": split,
                "scenario_id": scenario,
                "original_tool_call_id": message["tool_call_id"],
                "json_pointer": pointer,
                "raw_record_sha256": digest(item),
                "data_origin": "synthetic",
            }
            try:
                data = _sanitize(item, FIELDS[resource])
            except ValueError as exc:
                quarantine.append(
                    {"scenario_id": scenario, "reason": str(exc), "provenance": provenance}
                )
                continue
            native = str(
                data.get("event_id")
                or data.get("alert_id")
                or data.get("pid")
                or data.get("hostname")
                or digest(data)
            )
            key = f"{REVISION}:{scenario}:{resource}:{native}"
            host = data.get("host") or data.get("hostname") or payload.get("host")
            record = {
                "source_record_id": key,
                "resource": resource,
                "data": data,
                "host": host,
                "user": data.get("user"),
                "observed_at": data.get("timestamp"),
                "provenance": provenance,
            }
            if key in observations and observations[key]["data"] != data:
                conflicts.add(key)
                quarantine.append(
                    {
                        "scenario_id": scenario,
                        "reason": "CONFLICTING_NATIVE_KEY",
                        "provenance": provenance,
                    }
                )
            else:
                observations.setdefault(key, record)
    return {
        "scenario_id": scenario,
        "input": input_data,
        "input_provenance": {
            "dataset_revision": REVISION,
            "file_sha256": file_sha256,
            "split": split,
            "scenario_id": scenario,
            "json_pointer": "/alert",
            "raw_record_sha256": digest(alert),
            "data_origin": "synthetic",
        },
        "observations": [v for k, v in observations.items() if k not in conflicts],
        "available": sorted(available),
        "quarantine": quarantine,
    }


def _iocs(data):
    result = set()
    for field, value in data.items():
        if not isinstance(value, str):
            continue
        for literal in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", value):
            try:
                result.add(("ipv4", str(ipaddress.IPv4Address(literal))))
            except ValueError:
                pass
        if re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", value):
            result.add(("hash", value.lower()))
        if value.startswith(("http://", "https://")):
            result.add(("url", value))
        elif "domain" in field and re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}", value):
            result.add(("domain", value.lower()))
    return result


def _insert_rows(connection, table, rows):
    if rows:
        columns = list(zip(*rows))
        connection.execute(
            "INSERT INTO " + table + " SELECT " + ",".join("unnest(?)" for _ in columns),
            [list(x) for x in columns],
        )


def import_corpus(source_dir: Path, database: Path, *, manifest: dict) -> dict:
    hashes = verify_sources(source_dir, manifest)
    if duckdb.__version__ != "1.5.5":
        raise ValueError("SOC_DUCKDB_VERSION_MISMATCH")
    database = Path(database)
    if database.exists():
        raise ValueError("SOC_DATABASE_ALREADY_EXISTS")
    database.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    quarantine = []
    imported = 0
    logical = hashlib.sha256()
    with duckdb.connect(str(database)) as out:
        out.execute("BEGIN TRANSACTION")
        out.execute(
            "CREATE TABLE case_inputs(scenario_id VARCHAR PRIMARY KEY, split VARCHAR, input_json VARCHAR, provenance_json VARCHAR)"
        )
        out.execute(
            "CREATE TABLE observations(scenario_id VARCHAR, resource VARCHAR, source_record_id VARCHAR PRIMARY KEY, record_json VARCHAR)"
        )
        out.execute("CREATE TABLE source_availability(scenario_id VARCHAR, resource VARCHAR)")
        out.execute("CREATE TABLE ioc_index(kind VARCHAR, value VARCHAR, scenario_id VARCHAR)")
        out.execute("CREATE TABLE corpus_metadata(metadata_json VARCHAR)")
        for name, sha in hashes.items():
            split = name[:-8]
            cursor = out.execute("SELECT * FROM read_parquet(?)", [str(Path(source_dir) / name)])
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()
            counts[split] = len(rows)
            inputs = []
            observations = []
            availability = []
            iocs = set()
            for values in rows:
                case = extract_case(dict(zip(columns, values)), split=split, file_sha256=sha)
                scenario = case["scenario_id"]
                inputs.append(
                    (scenario, split, canonical(case["input"]), canonical(case["input_provenance"]))
                )
                quarantine.extend(case["quarantine"])
                logical.update(canonical(case).encode())
                availability.extend((scenario, r) for r in case["available"])
                for kind, value in _iocs(case["input"]):
                    iocs.add((kind, value, scenario))
                for record in case["observations"]:
                    observations.append(
                        (
                            scenario,
                            record["resource"],
                            record["source_record_id"],
                            canonical(record),
                        )
                    )
                    for kind, value in _iocs(record["data"]):
                        iocs.add((kind, value, scenario))
            _insert_rows(out, "case_inputs", inputs)
            _insert_rows(out, "observations", observations)
            _insert_rows(out, "source_availability", availability)
            _insert_rows(out, "ioc_index", sorted(iocs))
            imported += len(observations)
        metadata = {
            "source_revision": REVISION,
            "source_hashes": hashes,
            "logical_sha256": logical.hexdigest(),
            "data_origin": "synthetic",
            "import_protocol": "soc_corpus_v1",
            "importer_sha256": file_digest(__file__),
        }
        out.execute("INSERT INTO corpus_metadata VALUES (?)", [canonical(metadata)])
        out.execute("COMMIT")
    return {
        "status": "imported",
        **metadata,
        "database_sha256": file_digest(database),
        "cases": counts,
        "imported_records": imported,
        "quarantined_records": len(quarantine),
        "quarantine": quarantine,
    }


class SocCorpusRepository:
    def __init__(self, database: Path, *, expected_sha256: str):
        self.database = Path(database)
        if not self.database.is_file() or file_digest(self.database) != expected_sha256:
            raise ValueError("SOC_CORPUS_IDENTITY_MISMATCH")
        self.sha256 = expected_sha256
        self._connection = duckdb.connect(str(self.database), read_only=True)

    def _query(self, sql, parameters=()):
        return self._connection.execute(sql, parameters).fetchall()

    def close(self):
        self._connection.close()

    def metadata(self):
        return json.loads(self._query("SELECT metadata_json FROM corpus_metadata")[0][0])

    def tables(self):
        return {x[0] for x in self._query("SHOW TABLES")}

    def scenario_ids(self, split=None):
        return [
            x[0]
            for x in self._query(
                "SELECT scenario_id FROM case_inputs WHERE (? IS NULL OR split=?) ORDER BY scenario_id",
                [split, split],
            )
        ]

    def input_for(self, scenario_id: str) -> dict:
        rows = self._query("SELECT input_json FROM case_inputs WHERE scenario_id=?", [scenario_id])
        if not rows:
            raise ValueError("UNKNOWN_SOC_SCENARIO")
        return json.loads(rows[0][0])

    def input_provenance_for(self, scenario_id):
        rows = self._query(
            "SELECT provenance_json FROM case_inputs WHERE scenario_id=?", [scenario_id]
        )
        if not rows:
            raise ValueError("UNKNOWN_SOC_SCENARIO")
        return json.loads(rows[0][0])

    def records(self, scenario_id: str, resource: str) -> list[dict]:
        self.input_for(scenario_id)
        if resource not in FIELDS:
            raise ValueError("UNSUPPORTED_SOC_RESOURCE")
        return [
            json.loads(x[0])
            for x in self._query(
                "SELECT record_json FROM observations WHERE scenario_id=? AND resource=? ORDER BY source_record_id",
                [scenario_id, resource],
            )
        ]

    def available(self, scenario_id: str, resource: str) -> bool:
        return bool(
            self._query(
                "SELECT 1 FROM source_availability WHERE scenario_id=? AND resource=? LIMIT 1",
                [scenario_id, resource],
            )
        )

    def resolve_ioc(self, value: str, indicator_type: str) -> list[str]:
        if indicator_type not in ("ipv4", "domain", "hash", "url"):
            raise ValueError("UNSUPPORTED_SOC_IOC")
        if indicator_type == "ipv4":
            value = str(ipaddress.IPv4Address(value))
        if indicator_type in ("domain", "hash"):
            value = value.lower()
        return [
            x[0]
            for x in self._query(
                "SELECT DISTINCT scenario_id FROM ioc_index WHERE kind=? AND value=? ORDER BY scenario_id",
                [indicator_type, value],
            )
        ]


def require_corpus_paths(source_dir, database, *, required):
    source_dir = Path(source_dir)
    database = Path(database)
    if not database.is_file() or any(
        not (source_dir / name).is_file() for name in SOURCE_MANIFEST["files"]
    ):
        if required:
            raise ValueError("SOC_REQUIRED_CORPUS_ABSENT")
        return None
    verify_sources(source_dir, SOURCE_MANIFEST)
    receipt_path = database.parent / "corpus_receipt.json"
    if not receipt_path.is_file():
        raise ValueError("SOC_REQUIRED_CORPUS_RECEIPT_ABSENT")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("importer_sha256") != file_digest(__file__) or receipt.get(
        "database_sha256"
    ) != file_digest(database):
        raise ValueError("SOC_REQUIRED_CORPUS_IDENTITY_CHANGED")
    return source_dir, database
