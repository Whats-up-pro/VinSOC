"""Read-only CTI provider adapters.

Providers normalize external intelligence into a common shape so CTISkill can
fuse multiple sources without treating any provider as ground truth.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import parse, request


@dataclass
class CTIFinding:
    source: str
    matched: bool
    reputation: str = "unknown"
    confidence: str = "low"
    malware: List[str] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)
    techniques: List[Dict[str, Any]] = field(default_factory=list)
    context: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "matched": self.matched,
            "reputation": self.reputation,
            "confidence": self.confidence,
            "malware": self.malware,
            "actors": self.actors,
            "techniques": self.techniques,
            "context": self.context,
            "references": self.references,
            "provenance": self.provenance,
        }


class CTIProvider(ABC):
    name = "cti"

    @abstractmethod
    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        raise NotImplementedError


def _post_json(url: str, payload: Dict[str, Any], auth_key: str, timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Auth-Key": auth_key, "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_form(url: str, payload: Dict[str, Any], auth_key: str, timeout: float) -> Dict[str, Any]:
    body = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Auth-Key": auth_key, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class ThreatFoxProvider(CTIProvider):
    """ThreatFox Community API IOC lookup."""

    name = "threatfox"
    endpoint = "https://threatfox-api.abuse.ch/api/v1/"

    def __init__(self, auth_key: str, timeout: float = 10.0):
        self.auth_key = auth_key
        self.timeout = timeout

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        try:
            response = _post_json(
                self.endpoint,
                {"query": "search_ioc", "search_term": indicator, "exact_match": True},
                self.auth_key,
                self.timeout,
            )
        except Exception as exc:
            return CTIFinding(
                source=self.name,
                matched=False,
                provenance={"status": "error", "error_type": type(exc).__name__},
            )

        rows = response.get("data") or []
        if response.get("query_status") != "ok" or not rows:
            return CTIFinding(
                source=self.name,
                matched=False,
                provenance={"query_status": response.get("query_status", "unknown")},
            )

        malware = sorted({
            str(row.get("malware_printable") or row.get("malware"))
            for row in rows
            if row.get("malware_printable") or row.get("malware")
        })
        context = [
            {
                "type": row.get("threat_type", "ioc_match"),
                "value": row.get("ioc", indicator),
                "context": row.get("threat_type_desc", "ThreatFox IOC match"),
            }
            for row in rows[:20]
        ]
        refs = [
            f"https://threatfox.abuse.ch/ioc/{row['id']}/"
            for row in rows[:20]
            if row.get("id")
        ]
        return CTIFinding(
            source=self.name,
            matched=True,
            reputation="malicious",
            confidence="high",
            malware=malware,
            context=context,
            references=refs,
            provenance={
                "query_status": response.get("query_status"),
                "record_count": len(rows),
                "provider": "abuse.ch ThreatFox",
            },
        )


class MalwareBazaarProvider(CTIProvider):
    """MalwareBazaar hash lookup; ignored for non-hash indicators."""

    name = "malwarebazaar"
    endpoint = "https://mb-api.abuse.ch/api/v1/"

    def __init__(self, auth_key: str, timeout: float = 10.0):
        self.auth_key = auth_key
        self.timeout = timeout

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        if indicator_type != "hash":
            return CTIFinding(source=self.name, matched=False, provenance={"status": "not_applicable"})

        try:
            response = _post_form(
                self.endpoint,
                {"query": "get_info", "hash": indicator},
                self.auth_key,
                self.timeout,
            )
        except Exception as exc:
            return CTIFinding(
                source=self.name,
                matched=False,
                provenance={"status": "error", "error_type": type(exc).__name__},
            )

        rows = response.get("data") or []
        if response.get("query_status") != "ok" or not rows:
            return CTIFinding(
                source=self.name,
                matched=False,
                provenance={"query_status": response.get("query_status", "unknown")},
            )

        malware = sorted({
            str(row.get("signature"))
            for row in rows
            if row.get("signature")
        })
        context = []
        for row in rows[:20]:
            context.append({
                "type": "malware_sample",
                "value": row.get("sha256_hash") or indicator,
                "context": (
                    f"signature={row.get('signature') or 'unknown'}; "
                    f"file_type={row.get('file_type') or 'unknown'}"
                ),
            })
        return CTIFinding(
            source=self.name,
            matched=True,
            reputation="malicious",
            confidence="high",
            malware=malware,
            context=context,
            references=["https://bazaar.abuse.ch/"],
            provenance={
                "query_status": response.get("query_status"),
                "record_count": len(rows),
                "provider": "abuse.ch MalwareBazaar",
            },
        )


class URLhausLocalProvider(CTIProvider):
    """Lookup against a locally downloaded URLhaus JSON/index export.

    The file can be either a dict keyed by URL/host or a list of URLhaus records.
    Keeping the export local makes investigations reproducible and avoids making
    every unit test or case replay depend on network availability.
    """

    name = "urlhaus"

    def __init__(self, path: str):
        self.path = Path(path)
        self.index: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            self.index = payload
            return
        for row in payload if isinstance(payload, list) else []:
            url = str(row.get("url") or "")
            host = str(row.get("host") or "")
            if url:
                self.index[url] = row
            if host:
                self.index.setdefault(host, row)

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        row = self.index.get(indicator)
        if not row:
            return CTIFinding(source=self.name, matched=False, provenance={"dataset": str(self.path)})
        malware = []
        for key in ("signature", "malware", "threat"):
            if row.get(key):
                malware.append(str(row[key]))
        return CTIFinding(
            source=self.name,
            matched=True,
            reputation="malicious",
            confidence="medium",
            malware=sorted(set(malware)),
            context=[{
                "type": "malware_distribution",
                "value": row.get("url", indicator),
                "context": row.get("url_status") or row.get("threat") or "URLhaus match",
            }],
            references=["https://urlhaus.abuse.ch/"],
            provenance={"dataset": str(self.path), "provider": "abuse.ch URLhaus"},
        )


class AttackSTIXProvider(CTIProvider):
    """Local ATT&CK STIX 2.1 knowledge mapper.

    ATT&CK is not an IOC reputation service. This adapter only enriches malware
    or technique names supplied by upstream CTI findings.
    """

    name = "mitre_attack"

    def __init__(self, path: str):
        self.path = Path(path)
        self.objects: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.objects = payload.get("objects", []) if isinstance(payload, dict) else []

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        # Direct IOC lookup is intentionally unsupported; ATT&CK is a knowledge
        # base, not an IOC reputation feed.
        return CTIFinding(source=self.name, matched=False, provenance={"status": "knowledge_only"})

    def map_software(self, software_names: List[str]) -> List[Dict[str, Any]]:
        wanted = {name.lower() for name in software_names if name}
        if not wanted:
            return []

        software_ids = {
            obj.get("id")
            for obj in self.objects
            if obj.get("type") in {"malware", "tool"}
            and str(obj.get("name", "")).lower() in wanted
        }
        relationships = [
            obj for obj in self.objects
            if obj.get("type") == "relationship"
            and obj.get("relationship_type") == "uses"
            and obj.get("source_ref") in software_ids
            and str(obj.get("target_ref", "")).startswith("attack-pattern--")
        ]
        technique_ids = {rel.get("target_ref") for rel in relationships}
        techniques = []
        for obj in self.objects:
            if obj.get("type") != "attack-pattern" or obj.get("id") not in technique_ids:
                continue
            external_id = None
            reference_url = None
            for ref in obj.get("external_references", []):
                if ref.get("source_name") == "mitre-attack":
                    external_id = ref.get("external_id")
                    reference_url = ref.get("url")
                    break
            techniques.append({
                "technique_id": external_id or obj.get("id"),
                "technique_name": obj.get("name", "unknown"),
                "tactics": [
                    phase.get("phase_name")
                    for phase in obj.get("kill_chain_phases", [])
                    if phase.get("phase_name")
                ],
                "reference": reference_url,
            })
        return techniques


def providers_from_environment() -> List[CTIProvider]:
    """Create live/local providers from environment without making a request."""
    providers: List[CTIProvider] = []
    auth_key = os.getenv("ABUSECH_AUTH_KEY")
    if auth_key:
        providers.extend([
            ThreatFoxProvider(auth_key=auth_key),
            MalwareBazaarProvider(auth_key=auth_key),
        ])

    urlhaus_path = os.getenv("URLHAUS_JSON_PATH")
    if urlhaus_path and Path(urlhaus_path).exists():
        providers.append(URLhausLocalProvider(urlhaus_path))

    attack_path = os.getenv("ATTACK_STIX_PATH")
    if attack_path and Path(attack_path).exists():
        providers.append(AttackSTIXProvider(attack_path))
    return providers
