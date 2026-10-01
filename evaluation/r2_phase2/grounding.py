"""Four-layer controller provenance; reuse recovered metadata adapter."""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path

from evaluation.dualsql_lite_ctu_gpt5_v2.source_tools import V2DatabaseTools
from evaluation.dualsql_lite_ctu_gpt5.tools import MAX_RESPONSE_BYTES, _size
from evaluation.r2_phase2.safety import Phase2Snapshot, parse_select, validate_sql
from vinsoc_data.duckdb_store import QuerySafetyError

CONTRACT_IDENTITY = 'r2_generalized_controller_provenance_v2'
TEXT_TYPES = {'VARCHAR', 'TEXT'}


def _pattern(query):
    return '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


class Phase2Tools(V2DatabaseTools):
    def __init__(self, snapshot_path, manifest_path):
        super().__init__(snapshot_path, manifest_path)
        self.column_types = {c['name']: c['type'].upper() for c in self.schema['network_flows']}
        # A sampled/length-filtered catalog cannot prove a domain is complete.
        with self._connect() as connection:
            self.distinct_counts = {column: connection.execute(
                f'SELECT count(DISTINCT "{column}") FROM network_flows').fetchone()[0]
                for column, dtype in self.column_types.items() if dtype in TEXT_TYPES}
        self.complete_domains = {col for col, vals in self.domains.items()
                                 if self.distinct_counts[col] == len(vals)}

    def question_literals(self, question):
        literals = [{'surface': m.group(2), 'kind': 'text_literal'}
                    for m in re.finditer(r"(['\"])(.*?)\1", question)]
        times = list(re.finditer(r'\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\b', question))
        literals.extend({'surface': m.group(), 'kind': 'timestamp_constraint'} for m in times)
        literals.extend({'surface': m.group(), 'kind': 'numeric_constraint'}
                        for m in re.finditer(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])', question)
                        if not any(t.start() <= m.start() < t.end() for t in times))
        return literals

    def schema_context(self, tables=None):
        metadata = [{'table': 'network_flows', 'column': 'source_dataset', 'value': value,
                     'aliases': aliases, 'evidence_class': 'source_metadata'}
                    for value, aliases in sorted(self.source_aliases.items())]
        return super().schema_context(tables) + '\n' + json.dumps({
            'controller_contract': CONTRACT_IDENTITY, 'source_metadata': metadata,
            'numeric_and_timestamp_constraints_require_catalog_search': False,
            'truncated_catalog_results_are_closed_domains': False,
            'grouping_predicates': 'operator, pattern, escape and catalog witness are returned by value_search',
        }, sort_keys=True)

    def database_profiler(self, args):
        result = super().database_profiler(args)
        if result.get('ok'):
            result['domain_completeness'] = {col: col in self.complete_domains for col in result['domains']}
            while _size(result) > MAX_RESPONSE_BYTES and result['domains']:
                col = next(reversed(result['domains']))
                del result['domains'][col]
                del result['domain_completeness'][col]
                result['truncated_domains'].append(col)
        return self._remember(result)

    def value_search(self, args):
        if (isinstance(args,dict) and args.get('column') is None and isinstance(args.get('query'),str)
                and re.fullmatch(r'-?\d+(?:\.\d+)?|\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?', args['query'].strip())):
            if set(args)-{'query','table','column'} or args.get('table','network_flows')!='network_flows':
                return {'ok':False,'error_type':'INVALID_ARGUMENTS'}
            return self._remember({'ok':True,'evidence_id':self._evidence_id(),'matches':[],
                                  'resolution':'typed_constraint_not_catalog_value','domain_complete':False,
                                  'grouping_predicates':[]})
        if isinstance(args, dict) and self.column_types.get(args.get('column')) not in TEXT_TYPES | {None}:
            if not isinstance(args.get('query'), str) or set(args) - {'query','table','column'} or args.get('table','network_flows') != 'network_flows':
                return {'ok': False, 'error_type': 'INVALID_ARGUMENTS'}
            return self._remember({'ok': True, 'evidence_id': self._evidence_id(), 'matches': [],
                                  'resolution': 'typed_constraint_not_catalog_value',
                                  'domain_complete': False, 'grouping_predicates': [],
                                  'constraint_column': {'table':'network_flows','column':args['column'],
                                                        'type':self.column_types[args['column']]}})
        result = super().value_search(args)
        if not result.get('ok'):
            return result
        result['domain_complete'] = False  # search samples are never a closed domain
        result['grouping_predicates'] = []
        query = args['query'].strip()
        for match in result['matches']:
            if (match.get('match_basis') == 'substring' and len(query) >= 2
                    and query.casefold() in match['value'].casefold()
                    and match['value'].casefold() != query.casefold()):
                if any(p['column'] == match['column'] for p in result['grouping_predicates']):
                    continue
                result['grouping_predicates'].append({
                    'table':'network_flows','column':match['column'], 'operator':'ILIKE',
                    'pattern':_pattern(query), 'escape':'\\', 'case_insensitive': True,
                    'surface': query, 'witness': match, 'evidence_id': result['evidence_id'],
                    'domain_complete':False})
        # Bounded output prioritizes the pattern witness over enumerating samples.
        while _size(result) > MAX_RESPONSE_BYTES and len(result['matches']) > 1:
            result['matches'].pop()
            result['truncated'] = True
        if _size(result) > MAX_RESPONSE_BYTES:
            return {'ok':False,'error_type':'OUTPUT_LIMIT'}
        return self._remember(result)

    def sql_probe(self, args):
        if not isinstance(args, dict) or set(args) != {'sql'} or not isinstance(args['sql'], str) or len(args['sql']) > 4000:
            return {'ok':False,'error_type':'INVALID_ARGUMENTS'}
        try:
            sql = validate_sql(args['sql'])
            node = parse_select(sql)['statements'][0]['node']
            result = Phase2Snapshot(self.snapshot_path, row_limit=20).query(sql)
            lineage = {}
            relation = node.get('from_table', {})
            # Derived relations, joins, CTEs and expressions have no inferred lineage.
            if (relation.get('type') == 'BASE_TABLE' and relation.get('table_name','').casefold() == 'network_flows'
                    and not node.get('cte_map', {}).get('map')):
                projected_names = Counter((expr.get('alias') or
                    (expr.get('column_names', [''])[-1] if expr.get('class')=='COLUMN_REF' else '')).casefold()
                    for expr in node.get('select_list',[]))
                for expr in node.get('select_list', []):
                    if expr.get('class') == 'COLUMN_REF':
                        names = expr['column_names']
                        column = names[-1]
                        if (column in self.column_types and (len(names) == 1 or
                                (len(names) == 2 and names[0] in {'network_flows', relation.get('alias')}))):
                            output = expr.get('alias') or column
                            if projected_names[output.casefold()] != 1:
                                continue
                            lineage[output] = {
                                'table':'network_flows','column':column,'type':self.column_types[column]}
            evidence = self._evidence_id()
            matches = []
            for output, origin in lineage.items():
                if origin['type'] not in TEXT_TYPES:
                    continue
                for row in result.rows:
                    value = row.get(output)
                    if isinstance(value,str) and any(v['column']==origin['column'] and v['value']==value for v in self.catalog):
                        entry = {'table':origin['table'],'column':origin['column'],'value':value,'evidence_id':evidence}
                        if entry not in matches:
                            matches.append(entry)
            payload = {'ok':True,'evidence_id':evidence,'columns':list(result.columns),
                       'rows':result.rows,'truncated':result.truncated,'column_provenance':lineage,
                       'matches':matches,'domain_complete':False}
            if _size(payload) > MAX_RESPONSE_BYTES:
                return {'ok':False,'error_type':'OUTPUT_LIMIT'}
            return self._remember(payload)
        except QuerySafetyError:
            return {'ok':False,'error_type':'SAFETY_REJECTION'}
        except RuntimeError:
            return {'ok':False,'error_type':'SQL_EXECUTION_ERROR'}


def validate_link(question, selected, trajectory, tools, submitted_values=None):
    def rejected(category, unresolved=None):
        return {'error':category,'grounded_values':[],'unresolved_literals':unresolved or []}
    allowed = tools.column_types
    if (not isinstance(selected,list) or len(selected)!=1 or not isinstance(selected[0],dict)
            or set(selected[0]) != {'table','columns'} or selected[0]['table'] != 'network_flows'):
        return rejected('INVALID_LINKED_SCHEMA')
    columns = selected[0]['columns']
    if (not isinstance(columns,list) or not columns or any(not isinstance(c,str) or c not in allowed for c in columns)
            or len(columns)!=len(set(columns))):
        return rejected('INVALID_LINKED_SCHEMA')
    error = tools.source_reference_error(question)
    if error:
        return rejected(error)
    references = tools.source_references(question)
    if any(ref['column'] not in columns for ref in references):
        return rejected('WRONG_COLUMN_FOR_INTENT',[ref['surface'] for ref in references])
    values = [{**{k:ref[k] for k in ('column','value')}, 'table':'network_flows',
               'evidence_id':'controller-source-metadata', 'evidence_class':'source_metadata'} for ref in references]
    predicates = []
    for event in trajectory:
        result = event.get('result',{})
        if not result.get('ok'):
            continue
        if tools.observed_evidence.get(result.get('evidence_id')) != result:
            return rejected('INVALID_TOOL_PROVENANCE')
        observed = list(result.get('matches', []))
        column = event.get('arguments',{}).get('column')
        if column in columns:
            observed.extend({'table':'network_flows','column':column,**item} for item in result.get('domain',[]))
        for column, domain in result.get('domains',{}).items():
            observed.extend({'table':'network_flows','column':column,**item} for item in domain)
        for item in observed:
            column = item.get('column')
            if column not in columns or tools.column_types[column] not in TEXT_TYPES:
                continue
            if not any(v['column']==column and v['value']==item.get('value') for v in tools.catalog):
                return rejected('INVALID_TOOL_PROVENANCE')
            if column == 'source_dataset' and references and not any(ref['value']==item['value'] for ref in references):
                continue
            entry = {k:item[k] for k in ('table','column','value','evidence_id')}
            if entry not in values:
                values.append(entry)
        predicates.extend(p for p in result.get('grouping_predicates',[]) if p['column'] in columns)
    constraints = []
    for item in submitted_values or []:
        if not isinstance(item,dict) or set(item)-{'table','column','value','evidence_id'}:
            return rejected('INVALID_TOOL_PROVENANCE')
        column = item.get('column')
        if item.get('table')!='network_flows' or column not in columns:
            return rejected('INVALID_TOOL_PROVENANCE')
        if tools.column_types[column] not in TEXT_TYPES:
            # Model values cannot become provenance for typed constraints.
            constraints.append({'column':column,'type':tools.column_types[column],
                                'submitted_value':item.get('value'),'catalog_grounding_required':False})
            continue
        exact = any(all(item.get(k)==v[k] for k in ('table','column','value')) and
                    ('evidence_id' not in item or item['evidence_id']==v['evidence_id']) for v in values)
        pattern = any(item.get('value')==p['surface'] and column==p['column'] and
                      ('evidence_id' not in item or item['evidence_id']==p['evidence_id']) for p in predicates)
        if not exact and not pattern:
            return rejected('INVALID_TOOL_PROVENANCE')
    return {'error':None,'contract_identity':CONTRACT_IDENTITY,'tables':selected,
            'grounded_values':values[:20], 'source_metadata':references,
            'question_literals':tools.question_literals(question), 'typed_constraints':constraints,
            'grouping_predicates':predicates, 'unresolved_literals':[],
            'catalog_samples_are_closed_domains':False}
