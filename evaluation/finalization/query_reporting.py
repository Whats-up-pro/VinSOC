"""Explicit external64/CTU32 coverage; unavailable measurements stay unavailable."""
from collections import defaultdict


def build_query_report(records, inventory, *, conditions=('E0','E3'), identities=None, journal=None):
    from evaluation.finalization.query_record_normalization import normalize_query_records, inventory_metadata
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    inventory = inventory_metadata(inventory)
    normalized = normalize_query_records(records, inventory, identities=identities or {}, journal=journal or {})
    records = [{**r, 'score':{'execution_accurate':r['execution_accurate']}} for r in normalized if r['present']]
    ids={r['case_id'] for r in inventory}
    indexed={}
    for record in records:
        key=record['condition'],record['case_id']
        if key in indexed or key[0] not in conditions or key[1] not in ids:
            raise ValueError('DUPLICATE_OR_FOREIGN_CASE_RECORD')
        indexed[key]=record
    def summarize(rows,condition):
        present=[indexed[(condition,r['case_id'])] for r in rows if (condition,r['case_id']) in indexed]
        complete=len(present)==len(rows) and bool(rows)
        scores=[r.get('score',{}) for r in present]
        scored=[s for s in scores if type(s.get('execution_accurate')) is bool]
        valid=complete and len(scored)==len(rows)
        return {'planned':len(rows),'completed':len(present),'scored':len(scored),
                'correct_completed':sum(s['execution_accurate'] for s in scored),
                'execution_accuracy':sum(s['execution_accurate'] for s in scored)/len(rows) if valid else None,
                'status':'complete' if valid else 'incomplete',
                'missing_ids':[r['case_id'] for r in rows if (condition,r['case_id']) not in indexed]}
    report={'scope':'new_query_runtime_metrics','official_eligible':False,'conditions':{}}
    for condition in conditions:
        groups={'total':inventory,'ctu':[r for r in inventory if r['database_id']=='ctu_dev'],
                'external':[r for r in inventory if r['database_id']!='ctu_dev']}
        databases=defaultdict(list);domains=defaultdict(list);features=defaultdict(list);difficulty=defaultdict(list)
        for r in inventory:
            databases[r['database_id']].append(r);domains[r['domain']].append(r)
            difficulty[r['difficulty']].append(r)
            for feature in r['features']:
                features[feature].append(r)
        result={key:summarize(rows,condition) for key,rows in groups.items()}
        for label,groups in [('databases',databases),('domains',domains),('features',features),('difficulty',difficulty)]:
            result[label]={key:summarize(rows,condition) for key,rows in groups.items()}
            values=[r['execution_accuracy'] for r in result[label].values()]
            if label in ('databases','domains'):
                result['macro_'+label]=sum(values)/len(values) if values and all(v is not None for v in values) else None
        report['conditions'][condition]=result
    selected = [r for r in normalized if r['condition'] in conditions]
    report['modules'] = build_evaluation_report([r for r in selected if r['present']], {'cases':inventory, 'conditions':list(conditions)})
    report['statistics'] = summarize_statistics(selected, seed=20261007, bootstrap_replicates=10000)
    if any(not r['scoring_valid'] for r in selected):
        paired = report['statistics']['paired']
        paired.update(complete=False, wins=None, losses=None, ties=None, delta=None, cluster_intervals=None)
        paired['reasons'] = list(dict.fromkeys(paired['reasons']+['INCOMPLETE_SCORING_OR_IDENTITY']))
    for condition in conditions:
        complete = all(r['scoring_valid'] for r in selected if r['condition'] == condition)
        if not complete:
            metrics = report['modules']['conditions'][condition]
            for name in ('execution_accuracy','syntax_validity','execution_success','semantic_test_accuracy'):
                metrics[name]['rate'] = None
            statistical = report['statistics']['conditions'][condition]
            statistical['micro']['rate'] = None
            statistical['wilson_case_diagnostic']['interval'] = None
            statistical['macro_database'] = statistical['macro_domain'] = None
            for interval in statistical['cluster_intervals'].values():
                interval.update(interval=None, reason='INCOMPLETE_SCORING_OR_IDENTITY')
            for label in ('database','domain','difficulty','features'):
                for row in statistical[label].values():
                    row['rate'] = None
    report['normalized_records'] = normalized
    report['positive_new_run_validation'] = 'pending_authentic_calibration_evaluation_records'
    return report
