"""Real CTU query results translated into existing EvidenceStore contracts."""
from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from evaluation.r2_cross_domain_v1.data import DatabaseContext
from skills.base import SkillContract, SkillResult
from vinsoc_text2sql.service import QueryRequest, TextToSQLService


@dataclass(frozen=True)
class QueryContext:
    database_id: str
    snapshot_path: Path
    snapshot_logical_sha256: str
    allowed_tables: tuple[str, ...]
    scope_id: str


class NetworkQuerySkill:
    skill_name = 'network_query'
    skill_version = '1.0.0'

    def __init__(self, *, context: DatabaseContext, query_context: QueryContext,
                 condition, transport, service=None, telemetry_sink=None):
        if (query_context.database_id != 'ctu_dev' or context.database_id != query_context.database_id
            or Path(context.snapshot_path).resolve() != Path(query_context.snapshot_path).resolve()
            or query_context.snapshot_logical_sha256 != context.identity['logical_sha256']
            or query_context.allowed_tables != ('network_flows',) or not query_context.scope_id
            or condition not in ('E0', 'E3')):
            raise ValueError('QUERY_SCOPE_MISMATCH')
        if not Path(context.snapshot_path).is_file():
            raise ValueError('REAL_DATA_REQUIRED')
        if hashlib.sha256(Path(context.snapshot_path).read_bytes()).hexdigest() != context.identity['duckdb_binary_sha256']:
            raise ValueError('SNAPSHOT_CHECKSUM_MISMATCH')
        # Scope down the catalog; dataset_provenance remains application-owned.
        identity = deepcopy(context.identity)
        identity['schema'] = [t for t in identity['schema'] if t['name'] == 'network_flows']
        identity['primary_keys'] = {'network_flows': identity['primary_keys']['network_flows']}
        identity['relationships'] = []
        self.context = DatabaseContext(context.database_id, context.snapshot_path, identity)
        self.query_context = query_context
        self.condition, self.transport = condition, transport
        self.service = service or TextToSQLService()
        self.telemetry_sink = telemetry_sink or (lambda record: None)
        self.last_generation = self.last_execution = None

    def get_contract(self):
        return SkillContract(self.skill_name, self.skill_version, ['question'], 'QueryExecutionReceipt')

    def execute(self, *, question):
        request = QueryRequest('query_'+uuid.uuid4().hex, self.context.database_id, question)
        generation = self.service.generate(request, condition=self.condition, context=self.context,
                                          transport=self.transport, telemetry_sink=self.telemetry_sink)
        self.last_generation = generation
        if generation['error_category'] != 'OK':
            return SkillResult(False, error=generation['error_category'])
        try:
            result = self.service.execute(generation, context=self.context)
        except ValueError as error:
            return SkillResult(False, error=str(error))
        self.last_execution = result
        self.telemetry_sink({**generation, 'execution':deepcopy(result)})
        if result['truncated']:
            return SkillResult(False, data={'execution': result}, error='QUERY_RESULT_TRUNCATED')
        provenance = {k: result[k] for k in ('database_id', 'snapshot_binary_sha256',
                     'snapshot_logical_sha256', 'sql_sha256', 'result_sha256', 'executor_version')}
        provenance.update(scope_id=self.query_context.scope_id, tables=['network_flows'],
                          lineage_mode='snapshot_query')
        names = [c['name'] for c in result['columns']]
        pairs = []
        if 'source_dataset' in names and 'source_row_id' in names:
            indexes = names.index('source_dataset'), names.index('source_row_id')
            pairs = sorted({(row[indexes[0]], row[indexes[1]]) for row in result['rows']})
            if pairs:
                # Constants/expressions in a projection are not trusted source IDs.
                placeholders = ','.join('(?,?)' for _ in pairs)
                check = self.service.executor.query(self.context,
                    'SELECT COUNT(*) FROM network_flows WHERE (source_dataset,source_row_id) IN ('+placeholders+')',
                    tuple(v for pair in pairs for v in pair), row_cap=1, timeout_seconds=10)
                if check['rows'] != [[len(pairs)]]:
                    return SkillResult(False, error='SOURCE_PAIR_NOT_FOUND')
            provenance.update(source_pairs=[list(pair) for pair in pairs])
        # Aggregate results are derived from a real observed query execution.
        items = [
            {'local_key': 'execution', 'evidence_class': 'OBSERVED', 'type': 'query_execution',
             'source_name': 'CTU-13 S5/S7 verified snapshot', 'provenance': provenance,
             'data': {**provenance, 'question': question, 'sql': result['sql'], 'isolation': result['isolation']}},
            {'local_key': 'result', 'evidence_class': 'DERIVED', 'type': 'query_result',
             'source_name': 'CTU-13 SQL result', 'related_local_keys': ['execution'],
             'provenance': provenance, 'data': {k: result[k] for k in
                 ('columns', 'rows', 'row_count', 'truncated', 'result_sha256')}}]
        return SkillResult(True, data={'question': question, 'execution': result,
                          'generation': generation, 'evidence_items': items})
