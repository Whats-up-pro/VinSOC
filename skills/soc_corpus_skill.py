"""Two read-only, case-scoped queries over pinned synthetic observations."""

from dataclasses import dataclass
from datetime import datetime, timezone
from vinsoc_data.soc_corpus import canonical, REVISION, SocCorpusRepository, file_digest


@dataclass(frozen=True)
class SocCorpusContext:
    repository: object
    scenario_id: str
    condition: str
    source_revision: str
    corpus_sha256: str

    def __post_init__(self):
        if type(self.repository) is not SocCorpusRepository:
            raise ValueError("NATIVE_SOC_REPOSITORY_REQUIRED")
        if file_digest(self.repository.database) != self.corpus_sha256:
            raise ValueError("SOC_CONTEXT_DATABASE_CHANGED")
        if (
            self.condition not in ("S0", "S1")
            or self.source_revision != REVISION
            or self.corpus_sha256 != self.repository.sha256
        ):
            raise ValueError("SOC_CONTEXT_IDENTITY_MISMATCH")
        if self.repository.metadata()["source_revision"] != self.source_revision:
            raise ValueError("SOC_SOURCE_IDENTITY_MISMATCH")
        self.repository.input_for(self.scenario_id)


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_SOC_TIME")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_SOC_TIME") from None
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("SOC_TIME_ZONE_REQUIRED")
    return t.astimezone(timezone.utc)


class SocCorpusSkill:
    def __init__(self, context):
        self.context = context

    def _bound(self, rows, *, available, limit=20):
        if type(limit) != int or not 1 <= limit <= 20:
            raise ValueError("SOC_LIMIT_REQUIRED_1_20")
        matched = len(rows)
        delivered = rows[:limit]

        def payload():
            return {
                "rows": delivered,
                "matched_count": matched,
                "returned_count": len(delivered),
                "truncated": len(delivered) < matched,
                "availability": (
                    "unavailable" if not available else ("available" if matched else "no_match")
                ),
                "limitations": [
                    "Synthetic recorded observations only; counts describe imported data."
                ]
                + (["Source resource unavailable."] if not available else [])
                + (["Result truncated by row/byte cap."] if len(delivered) < matched else []),
            }

        for row in delivered:
            if len(canonical({**payload(), "rows": [row]}).encode()) > 20000:
                raise ValueError("SOC_ROW_EXCEEDS_BYTE_LIMIT")
        while len(canonical(payload()).encode()) > 20000 and delivered:
            delivered = delivered[:-1]
        return payload()

    def _query(
        self, resource, *, host, user, source=None, query=None, start=None, end=None, limit=20
    ):
        if type(limit) != int or not 1 <= limit <= 20:
            raise ValueError("SOC_LIMIT_REQUIRED_1_20")
        for value in (host, user, source, query):
            if value is not None and (
                not isinstance(value, str) or not value or len(value.encode()) > 2000
            ):
                raise ValueError("INVALID_SOC_FILTER")
        if (start is None) != (end is None):
            raise ValueError("SOC_TIME_RANGE_REQUIRES_BOTH")
        low = high = None
        if start is not None:
            low, high = _utc(start), _utc(end)
            if low > high:
                raise ValueError("SOC_REVERSED_TIME_RANGE")
        r = self.context.repository
        s = self.context.scenario_id
        sql = """SELECT record_json FROM observations WHERE scenario_id=? AND resource=?
          AND (? IS NULL OR json_extract_string(record_json,'$.host')=?)
          AND (? IS NULL OR json_extract_string(record_json,'$.user')=?)
          AND (? IS NULL OR json_extract_string(record_json,'$.data.source')=?)
          AND (? IS NULL OR strpos(coalesce(json_extract_string(record_json,'$.data.message'),''),?)>0)
          AND (? IS NULL OR try_cast(json_extract_string(record_json,'$.observed_at') AS TIMESTAMPTZ)>=?)
          AND (? IS NULL OR try_cast(json_extract_string(record_json,'$.observed_at') AS TIMESTAMPTZ)<?)
          ORDER BY try_cast(json_extract_string(record_json,'$.observed_at') AS TIMESTAMPTZ) NULLS LAST,source_record_id"""
        import json

        rows = [
            json.loads(x[0])
            for x in r._query(
                sql,
                [
                    s,
                    resource,
                    host,
                    host,
                    user,
                    user,
                    source,
                    source,
                    query,
                    query,
                    low,
                    low,
                    high,
                    high,
                ],
            )
        ]
        if any(x["provenance"]["scenario_id"] != s for x in rows):
            raise ValueError("SOC_SCOPE_LEAK")
        return self._bound(rows, available=r.available(s, resource), limit=limit)

    def search_events(
        self, *, host=None, user=None, source=None, query=None, start=None, end=None, limit=20
    ):
        return self._query(
            "events",
            host=host,
            user=user,
            source=source,
            query=query,
            start=start,
            end=end,
            limit=limit,
        )

    def get_context(self, *, resource, host=None, user=None, limit=20):
        if resource not in ("asset", "process_tree", "related_alerts"):
            raise ValueError("UNSUPPORTED_SOC_RESOURCE")
        if resource == "asset" and user is not None:
            raise ValueError("UNSUPPORTED_ASSET_USER_FILTER")
        return self._query(resource, host=host, user=user, limit=limit)
