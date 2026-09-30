"""Synthetic tools and scripted responses for offline controller/report checks."""
import json
from types import SimpleNamespace as NS

import duckdb

from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import MODEL
from evaluation.text_to_sql import SQLBenchmarkCase


def make_tools(tmp_path):
    snapshot = tmp_path / "fixture.duckdb"
    with duckdb.connect(str(snapshot)) as conn:
        conn.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR, protocol VARCHAR, n INTEGER)")
        conn.executemany("INSERT INTO network_flows VALUES (?, ?, ?, ?)", [("alpha", "flow=Botnet-A", "TCP", 1), ("beta", "Normal", "UDP", 2), ("beta", "Normal", "UDP", 2)])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"dataset_id": "alpha", "source_name": "Capture Group 5"}, {"dataset_id": "beta", "source_name": "Capture Group 7"}]}))
    return V2DatabaseTools(snapshot, manifest), manifest


def response(content=None, calls=None, model=MODEL, tokens=True, finish="stop"):
    return NS(id="response-fixture", model=model, usage=NS(prompt_tokens=10, completion_tokens=20, total_tokens=30) if tokens else None,
              choices=[NS(finish_reason=finish, message=NS(content=content, tool_calls=calls or []))])


def call(name="value_search", arguments='{"query":"Group 5"}', id="call-fixture"):
    return NS(id=id, function=NS(name=name, arguments=arguments))


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.chat = NS(completions=self)

    def create(self, **request):
        self.requests.append(request)
        item = next(self.replies)
        if isinstance(item, Exception):
            raise item
        return item


def case(question="Return totals by source dataset", gold="SELECT count(*) FROM network_flows", comparator="scalar"):
    return SQLBenchmarkCase("synthetic", question, "synthetic", (gold,), "network", "basic", comparator)
