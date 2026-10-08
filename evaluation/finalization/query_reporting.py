"""Explicit external64/CTU32 coverage; unavailable measurements stay unavailable."""
from collections import defaultdict


def build_query_report(records, inventory, *, conditions=('E0','E3')):
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
        databases=defaultdict(list);domains=defaultdict(list);features=defaultdict(list)
        for r in inventory:
            databases[r['database_id']].append(r);domains[r['domain']].append(r)
            for feature in r['features']:
                features[feature].append(r)
        result={key:summarize(rows,condition) for key,rows in groups.items()}
        for label,groups in [('databases',databases),('domains',domains),('features',features)]:
            result[label]={key:summarize(rows,condition) for key,rows in groups.items()}
            values=[r['execution_accuracy'] for r in result[label].values()]
            if label != 'features':
                result['macro_'+label]=sum(values)/len(values) if values and all(v is not None for v in values) else None
        report['conditions'][condition]=result
    return report
