from collections import Counter
from copy import deepcopy

import pytest


def inventory():
    rows=[]
    for split, dbs, n in [('calibration',4,4),('evaluation',8,8)]:
        for db in range(dbs):
            for i in range(n):
                rows.append({'case_id':f'{split}_{db}_{i}','database_id':f'{split}_db_{db}',
                    'question':f'q{i}','gold_sql':'SELECT 1','comparator':'scalar',
                    'difficulty':'basic' if i<2 else 'medium' if i<6 else 'advanced',
                    'features':['join','nested','distinct','group_having','order_limit'],
                    'family_id':f'f{i}','domain':f'domain_{db}', 'split':split,
                    'accepted_links':[{'annotations_complete':True}]})
    for split,n in [('calibration',8),('evaluation',32)]:
        for i in range(n):
            rows.append({'case_id':f'ctu_{split}_{i}','database_id':'ctu_dev','question':f'ctu {split} q{i}',
                'gold_sql':'SELECT 1','comparator':'scalar','difficulty':'medium' if split=='calibration' else 'basic' if i<8 else 'medium' if i<24 else 'advanced',
                'features':['distinct','group_having','order_limit'], 'family_id':f'ctu_f{i}',
                'domain':'network','split':split,'accepted_links':[{'annotations_complete':True}]})
    return rows


def test_benchmark_counts_quotas_domains_and_oracle_subset_are_verified():
    from evaluation.r2_cross_domain_v1.benchmark_lock import validate_inventory, select_oracle
    rows=inventory()
    receipt=validate_inventory(rows)
    assert receipt['counts']=={'calibration':24,'evaluation':96}
    assert receipt['difficulty']=={'basic':24,'medium':48,'advanced':24}
    selected=select_oracle(rows)
    lookup={row['case_id']:row for row in rows}
    assert len(selected)==len(set(selected))==12
    assert Counter(lookup[key]['database_id'] for key in selected)['ctu_dev']==4
    assert all(lookup[key]['split']=='evaluation' for key in selected)
    assert select_oracle(list(reversed(rows)))==selected


def test_duplicate_missing_annotation_or_cross_split_database_fails_closed():
    from evaluation.r2_cross_domain_v1.benchmark_lock import validate_inventory
    for transform in [lambda rows:rows.append(rows[0]),
                      lambda rows:rows[0].update(accepted_links=[]),
                      lambda rows:rows[0].update(database_id='evaluation_db_0')]:
        rows=inventory()
        transform(rows)
        with pytest.raises(ValueError):
            validate_inventory(rows)


def test_runtime_dto_rejects_gold_sentinel_and_inconsistent_question():
    from evaluation.r2_cross_domain_v1.benchmark_lock import verify_runtime
    ref=inventory()[0]
    runtime={key:ref[key] for key in ('case_id','database_id','question')}
    verify_runtime([ref],[runtime])
    with pytest.raises(ValueError, match='RUNTIME'):
        verify_runtime([ref],[{**runtime,'gold_sql':'SECRET'}])
    with pytest.raises(ValueError, match='RUNTIME'):
        verify_runtime([ref],[{**runtime,'question':'changed'}])


def test_locked_file_drift_is_rejected_without_provider(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark_lock import verify_file_identities, file_hash
    path=tmp_path/'x.json'
    path.write_text('{}')
    lock={'files':{'x.json':file_hash(path)},'source_files':{}}
    verify_file_identities(tmp_path,lock)
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='IDENTITY'):
        verify_file_identities(tmp_path,lock)
