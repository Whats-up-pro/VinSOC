"""Synthetic fixture bytes only; no CTU cases, source files or model outputs."""
import json
import importlib.util
from datetime import datetime
from decimal import Decimal

import duckdb

from evaluation.r2_phase2.grounding import Phase2Tools


def semantic_snapshot(path):
    # Until implementation exists, exercise the actual prior boundary for RED proof.
    if importlib.util.find_spec('evaluation.r2_phase2.safety_v4') is None:
        from evaluation.r2_phase2.safety import Phase2Snapshot
        return Phase2Snapshot(path)
    from evaluation.r2_phase2.safety_v4 import Phase2V4Snapshot
    return Phase2V4Snapshot(path)


def fixture_manifest(tmp_path, values):
    path = tmp_path / 'synthetic_manifest.json'
    path.write_text(json.dumps({'sources': [
        {'dataset_id': value, 'source_name': f'Lab Run {number}'}
        for value, number in zip(values, (41, 83))]}), encoding='utf-8')
    return path


def typed_tools(tmp_path, column):
    path = tmp_path / 'typed_fixture.duckdb'
    assert column.isidentifier()  # Test-only generated identifier, not model SQL.
    with duckdb.connect(str(path)) as connection:
        connection.execute(f'CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR, '
            f'"{column}" INTEGER, volume BIGINT, weight DECIMAL(10,2), observed_at TIMESTAMP, enabled BOOLEAN)')
        rows = [('omega', f'Class-{value}', value, index + 1, Decimal('2.75'), datetime(2024, 2, 3), True)
                for value in range(1, 10) for index in range(value)]
        rows.append(('theta', 'Other-class', 22, 100, Decimal('9.25'), datetime(2024, 2, 4), False))
        connection.executemany('INSERT INTO network_flows VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    return Phase2Tools(path, fixture_manifest(tmp_path, ('omega', 'theta')))


def semantic_tools(tmp_path):
    path = tmp_path / 'semantic_fixture.duckdb'
    rows = [
        ('alpha', 'Family-A', 'TCP', 'repeat', '2024-02-03 04:05:06.000000', 9, 10),
        ('alpha', 'Family-B', 'TCP', 'repeat', '2024-02-03 04:05:06.000001', 2, 20),
        ('beta', 'Family-A', 'UDP', 'other', '2024-02-03 04:05:07.000000', 7, 30),
        ('beta', 'x-Family-A', 'TCP', 'z', '2024-02-03 04:05:07.000001', 7, 2),
        ('alpha', 'family-C', 'UDP', 'other', '2024-02-03 04:05:05.999999', 2, 4),
        ('alpha', 'rack%_-A', 'UDP', 'repeat', '2024-02-03 04:05:06.500000', 9, 5),
        ('alpha', 'rackXYZ-A', 'UDP', 'x', '2024-02-03 04:05:06.999999', 4, 2),
        ('alpha', 'x-rack%_-A', 'TCP', 'x', '2024-02-03 04:05:06.000000', 4, 3),
        ('alpha', 'RACK%_-B', 'UDP', 'o', '2024-02-03 04:05:06.500000', 4, 3),
        ('alpha', 'Family-A', 'UDP', 'new', '2024-02-03 04:05:07.000000', 9, 4),
    ]
    with duckdb.connect(str(path)) as connection:
        connection.execute('CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR, '
            'protocol VARCHAR, target VARCHAR, event_time TIMESTAMP, code INTEGER, amount BIGINT)')
        connection.executemany('INSERT INTO network_flows VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    return Phase2Tools(path, fixture_manifest(tmp_path, ('alpha', 'beta')))


def predicate_sql(predicate):
    """Test-only SQL constructed from the returned generic predicate, not runtime code."""
    quoted = lambda value: "'" + value.replace("'", "''") + "'"
    assert predicate['column'] == 'label'
    assert predicate['operator'] in {'LIKE', 'ILIKE'}
    return ('SELECT COUNT(*) FROM network_flows WHERE label ' + predicate['operator'] + ' '
            + quoted(predicate['pattern']) + ' ESCAPE ' + quoted(predicate['escape']))
