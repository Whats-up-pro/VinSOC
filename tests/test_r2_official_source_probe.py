"""Credential-safe, complete-byte receipts for the three official R2 sources."""

from __future__ import annotations

import io
import json
import zipfile
from hashlib import sha256


class Response(io.BytesIO):
    def __init__(self, payload: bytes, declared_length: int | None = None):
        super().__init__(payload)
        self.headers = {"Content-Length": str(
            len(payload) if declared_length is None else declared_length
        )}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def zipped(name: str, payload: bytes) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)
    return target.getvalue()


def test_probe_hashes_transport_and_exact_ingest_bytes_without_serializing_key(tmp_path):
    from scripts.probe_r2_official_sources import probe

    secret = "SECRET_AUTH_KEY_SENTINEL"
    threatfox_csv = b"ioc_id,ioc_value\n1,1.2.3.4\n"
    threatfox_zip = zipped("full.csv", threatfox_csv)
    ctu = b"StartTime,SrcAddr,DstAddr\n2011/08/12 00:00:00,1.1.1.1,2.2.2.2\n"
    otrf_member = b'{"Hostname":"host","EventID":1}\n'
    otrf_zip = zipped("apt29_evals_day1_manual_2020-05-01225525.json", otrf_member)

    def opener(request, timeout):
        url = request.full_url
        if "threatfox-api" in url:
            assert secret in url
            return Response(threatfox_zip)
        if url.endswith("capture20110812.binetflow"):
            return Response(ctu)
        if url.endswith("apt29_evals_day1_manual.zip"):
            return Response(otrf_zip)
        raise AssertionError(url)

    result = probe(tmp_path, environ={"THREATFOX_AUTH_KEY": secret}, opener=opener,
                   retrieved_at="2026-09-26T00:00:00+00:00")
    assert result["status"] == "verified_bytes"
    receipts = {item["dataset_id"]: item for item in result["sources"]}
    assert receipts["threatfox_full"]["transport"]["sha256"] == sha256(threatfox_zip).hexdigest()
    assert receipts["threatfox_full"]["ingest"]["sha256"] == sha256(threatfox_csv).hexdigest()
    assert receipts["ctu13_s3"]["transport"] == {
        "bytes": len(ctu), "sha256": sha256(ctu).hexdigest()
    }
    assert receipts["otrf_apt29_day1"]["ingest"] == {
        "archive_member": "apt29_evals_day1_manual_2020-05-01225525.json",
        "bytes": len(otrf_member), "sha256": sha256(otrf_member).hexdigest(),
    }
    serialized = (tmp_path / "probe.json").read_text()
    assert secret not in serialized
    assert "threatfox-api.abuse.ch/v2/files/exports" not in serialized
    assert all("path" not in item for item in result["sources"])


def test_missing_threatfox_secret_fails_closed_without_opening_network(tmp_path):
    from scripts.probe_r2_official_sources import probe

    opened = []

    def opener(request, timeout):
        opened.append(request.full_url)
        return Response(b"unused")

    result = probe(tmp_path, environ={}, opener=opener,
                   retrieved_at="2026-09-26T00:00:00+00:00")
    threatfox = result["sources"][0]
    assert result["status"] == "partial"
    assert threatfox["status"] == "failed"
    assert threatfox["error"] == {"type": "MissingSecret", "message": "THREATFOX_AUTH_KEY unavailable"}
    assert not any("threatfox-api" in url for url in opened)


def test_declared_content_length_mismatch_is_not_verified(tmp_path):
    from scripts.probe_r2_official_sources import download_complete

    target = tmp_path / "source.bin"

    def opener(_request, timeout):
        return Response(b"partial", declared_length=100)

    try:
        download_complete("https://example.invalid/source", target, opener=opener)
    except ValueError as exc:
        assert "Content-Length" in str(exc)
    else:
        raise AssertionError("truncated response was accepted")
    assert not target.exists()
    assert not target.with_suffix(".bin.partial").exists()


def test_zip_with_unexpected_member_is_rejected(tmp_path):
    from scripts.probe_r2_official_sources import inspect_zip_member

    path = tmp_path / "bad.zip"
    path.write_bytes(zipped("wrong.csv", b"x"))
    try:
        inspect_zip_member(path, "full.csv")
    except ValueError as exc:
        assert "member" in str(exc).lower()
    else:
        raise AssertionError("unexpected archive layout was accepted")
