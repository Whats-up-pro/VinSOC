"""Single-case real SOC demonstration with its own immutable paid window."""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

from evaluation.finalization.cloud_window import GitHubAPI, REPOSITORY
from evaluation.soc_traces_v1.accounting import SocRunJournal, SocTerminalError, _exclusive_claim
from evaluation.soc_traces_v1.release import MODEL, read_bound_file, validate_identities
from vinsoc_data.soc_corpus import digest

DEMO_WINDOW = "soc-demo-20261009-v1"
DEMO_CASE_ID = "SCT-087094"
DEMO_CONDITION = "S1"
DEMO_REQUEST_LIMIT = 6
DEMO_BUDGET_USD = 1.0
DEMO_TAG = "vinsoc-window-" + DEMO_WINDOW
INPUT_USD_PER_MILLION = 0.4
OUTPUT_USD_PER_MILLION = 1.6
FRAMING_TOKEN_RESERVE = 8192
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"


def _artifact(value):
    return read_bound_file(value) if isinstance(value, dict) and set(value) == {"path", "sha256"} else value


def build_demo_release(
    *, identities, implementation_sha, api_key_sha256, operator, authorization_statement
):
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "window": DEMO_WINDOW,
        "model": MODEL,
        "identities": {**identities, "implementation_sha": implementation_sha},
        "case_ids": [row["scenario_id"] for row in _artifact(identities["inventory"])["cases"]],
        "caps": {
            "S0": 1,
            "S1": 6,
            "suite": 6,
            "tool_calls": 5,
            "output_tokens": 2000,
            "request_bytes": 128000,
            "messages": 16,
        },
        "demo": {
            "case_id": DEMO_CASE_ID,
            "condition": DEMO_CONDITION,
            "request_limit": DEMO_REQUEST_LIMIT,
            "budget_limit_usd": DEMO_BUDGET_USD,
            "source_review_status": "deferred_after_demo",
            "operator": operator,
            "approved_at": now,
            "authorization_statement": authorization_statement,
            "account_id": "repository_actions_openai_secret",
            "api_key_sha256": api_key_sha256,
            "pricing_checked_at": now,
            "pricing_source": PRICING_SOURCE,
            "input_usd_per_million": INPUT_USD_PER_MILLION,
            "output_usd_per_million": OUTPUT_USD_PER_MILLION,
            "framing_token_reserve": FRAMING_TOKEN_RESERVE,
        },
    }
    return {**body, "release_sha256": digest(body)}


def validate_demo_release(release, *, validate_runtime=True):
    demo = release.get("demo", {})
    identities = release.get("identities", {})
    inventory = _artifact(identities.get("inventory"))
    selection = _artifact(identities.get("demo_selection"))
    if release.get("window") != DEMO_WINDOW or release.get("model") != MODEL:
        raise ValueError("SOC_DEMO_SCOPE_INVALID")
    if not isinstance(inventory, dict) or not isinstance(selection, dict):
        raise ValueError("SOC_DEMO_IDENTITY_INVALID")
    ids = [row.get("scenario_id") for row in inventory.get("cases", [])]
    if len(ids) != 64 or len(set(ids)) != 64 or release.get("case_ids") != ids:
        raise ValueError("SOC_DEMO_INVENTORY_INVALID")
    if demo.get("case_id") not in selection.get("ids", []):
        raise ValueError("SOC_DEMO_CASE_NOT_PRESELECTED")
    if (
        demo.get("case_id") != DEMO_CASE_ID
        or demo.get("condition") != DEMO_CONDITION
        or demo.get("request_limit") != DEMO_REQUEST_LIMIT
        or demo.get("budget_limit_usd") != DEMO_BUDGET_USD
        or demo.get("source_review_status") != "deferred_after_demo"
        or release.get("caps")
        != {
            "S0": 1,
            "S1": 6,
            "suite": 6,
            "tool_calls": 5,
            "output_tokens": 2000,
            "request_bytes": 128000,
            "messages": 16,
        }
    ):
        raise ValueError("SOC_DEMO_CONTRACT_CHANGED")
    body = {key: value for key, value in release.items() if key != "release_sha256"}
    if release.get("release_sha256") != digest(body):
        raise ValueError("SOC_DEMO_RELEASE_HASH_INVALID")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", identities.get("implementation_sha", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", demo.get("api_key_sha256", ""))
        or not isinstance(demo.get("operator"), str)
        or not demo["operator"].strip()
        or not isinstance(demo.get("authorization_statement"), str)
        or not demo["authorization_statement"].strip()
        or demo.get("account_id") != "repository_actions_openai_secret"
        or demo.get("pricing_source") != PRICING_SOURCE
        or demo.get("input_usd_per_million") != INPUT_USD_PER_MILLION
        or demo.get("output_usd_per_million") != OUTPUT_USD_PER_MILLION
        or demo.get("framing_token_reserve") != FRAMING_TOKEN_RESERVE
    ):
        raise ValueError("SOC_DEMO_AUTHORITY_OR_PRICING_INVALID")
    try:
        approved = datetime.fromisoformat(demo["approved_at"].replace("Z", "+00:00"))
        checked = datetime.fromisoformat(demo["pricing_checked_at"].replace("Z", "+00:00"))
        today = datetime.now(timezone.utc).date()
        if approved.tzinfo is None or checked.tzinfo is None or approved.date() != today or checked.date() != today:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError("SOC_DEMO_FRESH_AUTHORITY_REQUIRED") from None
    maximum_request = (
        (128000 + FRAMING_TOKEN_RESERVE) * INPUT_USD_PER_MILLION
        + 2000 * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    if maximum_request * DEMO_REQUEST_LIMIT > DEMO_BUDGET_USD or not math.isfinite(maximum_request):
        raise ValueError("SOC_DEMO_BUDGET_INSUFFICIENT")
    if validate_runtime:
        validate_identities(release)
    evidence = {
        "account": {
            "api_key_sha256": demo["api_key_sha256"],
            "account_id": demo["account_id"],
            "operator": demo["operator"],
            "authorization_statement": demo["authorization_statement"],
        },
        "pricing": {
            "input_usd_per_million": INPUT_USD_PER_MILLION,
            "output_usd_per_million": OUTPUT_USD_PER_MILLION,
            "source": PRICING_SOURCE,
            "checked_at": demo["pricing_checked_at"],
        },
        "request_bound": {"framing_token_reserve": FRAMING_TOKEN_RESERVE},
        "budget": {"limit_usd": DEMO_BUDGET_USD},
    }
    return {
        "status": "pass",
        "case_id": DEMO_CASE_ID,
        "condition": DEMO_CONDITION,
        "request_limit": DEMO_REQUEST_LIMIT,
        "budget_limit_usd": DEMO_BUDGET_USD,
        "source_review_status": "deferred_after_demo",
        "maximum_request_usd": maximum_request,
        "maximum_suite_usd": maximum_request * DEMO_REQUEST_LIMIT,
        "evidence": evidence,
    }


class SocDemoCloudStore:
    """Create one immutable GitHub tag before the first demo request."""

    def __init__(self, api, implementation_sha, run_id):
        if (
            type(api) is not GitHubAPI
            or not re.fullmatch(r"[0-9a-f]{40}", implementation_sha)
            or not re.fullmatch(r"[0-9]{1,24}", run_id)
        ):
            raise ValueError("SOC_DEMO_CLOUD_IDENTITY_INVALID")
        self.api, self.sha, self.run_id = api, implementation_sha, run_id
        self.prefix = "/repos/" + REPOSITORY
        self.claimed = False

    def exists(self):
        return self.api.request("GET", self.prefix + "/git/ref/tags/" + DEMO_TAG) is not None

    def claim(self, release):
        if self.exists():
            raise ValueError("SOC_DEMO_SCOPE_ALREADY_CONSUMED")
        marker = {
            "window": DEMO_WINDOW,
            "release_sha256": release["release_sha256"],
            "implementation_sha": self.sha,
            "run_id": self.run_id,
            "consumed": True,
            "state": "claimed_no_resume_if_runner_lost",
        }
        tag = self.api.request(
            "POST",
            self.prefix + "/git/tags",
            {
                "tag": DEMO_TAG,
                "message": json.dumps(marker, sort_keys=True),
                "object": self.sha,
                "type": "commit",
                "tagger": {
                    "name": "VinSOC SOC demo runner",
                    "email": "noreply@github.com",
                    "date": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        if not isinstance(tag, dict) or not re.fullmatch(r"[0-9a-f]{40}", tag.get("sha", "")):
            raise ValueError("SOC_DEMO_CLOUD_CLAIM_RESPONSE_INVALID")
        self.api.request(
            "POST", self.prefix + "/git/refs", {"ref": "refs/tags/" + DEMO_TAG, "sha": tag["sha"]}
        )
        self.claimed = True


class SocDemoJournal(SocRunJournal):
    """Reuse native durable accounting while restricting scope to one S1 case."""

    @classmethod
    def claim(cls, release, *, ledger_path, remote_store):
        checked = validate_demo_release(release)
        path = Path(ledger_path)
        if path.is_symlink() or path.name != "ledger.json" or path.exists():
            raise SocTerminalError("SOC_DEMO_SCOPE_ALREADY_CONSUMED")
        if type(remote_store) is not SocDemoCloudStore:
            raise ValueError("SOC_DEMO_NATIVE_CLOUD_STORE_REQUIRED")
        remote_store.claim(release)
        state = {
            "window": DEMO_WINDOW,
            "release_sha256": release["release_sha256"],
            "status": "running",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "owner_pid": os.getpid(),
            "reservations": [],
            "estimated_cost_usd": 0.0,
            "unknown_cost": False,
            "maximum_suite_usd": checked["maximum_suite_usd"],
            "source_review_status": "deferred_after_demo",
        }
        try:
            _exclusive_claim(path, state)
        except FileExistsError:
            raise SocTerminalError("SOC_DEMO_SCOPE_ALREADY_CONSUMED") from None
        return cls(path, release, checked)

    def ensure_case_capacity(self, case_id, condition):
        demo = self.release["demo"]
        if (case_id, condition) != (demo["case_id"], demo["condition"]):
            raise ValueError("SOC_DEMO_SCOPE_MISMATCH")
        with self._state() as state:
            if state["status"] != "running" or state["unknown_cost"]:
                raise SocTerminalError("SOC_RELEASE_TERMINAL")
            records = state["reservations"]
            if any(row["status"] == "reserved" for row in records):
                raise SocTerminalError("SOC_UNRESOLVED_EXPOSURE")
            if len(records) >= demo["request_limit"]:
                raise ValueError("SOC_REQUEST_CAP_EXCEEDED")
