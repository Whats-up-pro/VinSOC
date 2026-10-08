import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.soc_traces_v1.reporting import render_case,build_suite_report,render_suite
from evaluation.soc_traces_v1.accounting import atomic_json

def main(argv=None):
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--receipt',type=Path);mode.add_argument('--suite',type=Path)
    p.add_argument('--inventory',type=Path,default=Path('results/evaluation_v1/soc_traces_v1/inventory.json'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--review',type=Path)
    a=p.parse_args(argv)
    if a.receipt:result=render_case(a.receipt,a.output,review_path=a.review)
    else:
        inv=json.loads(a.inventory.read_text());records=[json.loads(x.read_text()) for x in sorted((a.suite/'cases').glob('*.json'))]
        reviews=[json.loads(x.read_text()) for x in sorted((a.suite/'reviews').glob('*.json'))]
        result=build_suite_report(inv,records,reviews)
        selection=json.loads((a.inventory.parent/'demo_selection.json').read_text())
        if selection['inventory_sha256']!=inv['inventory_sha256']:raise ValueError('SOC_DEMO_SELECTION_CHANGED')
        for record in records:render_case(a.suite/'cases'/f"{record['scenario_id']}_{record['condition']}.json",a.output)
        render_suite(result,demo_ids=selection['ids'],output_dir=a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
