"""SOC commands default to offline; live is explicit and single-use."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.soc_traces_v1.runner import preflight,run_live
from evaluation.soc_traces_v1.release import private_directory
from evaluation.soc_traces_v1.accounting import atomic_json

def main(argv=None):
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true');mode.add_argument('--live',action='store_true')
    p.add_argument('--source-dir',type=Path);p.add_argument('--corpus',type=Path)
    p.add_argument('--inventory',type=Path,default=Path('results/evaluation_v1/soc_traces_v1/inventory.json'))
    p.add_argument('--reviews',type=Path,default=private_directory()/'source_reviews.json')
    p.add_argument('--private-dir',type=Path,default=private_directory());p.add_argument('--release',type=Path)
    p.add_argument('--output-dir',type=Path);p.add_argument('--write-release',type=Path)
    a=p.parse_args(argv)
    try:
        if a.preflight:
            if not a.source_dir or not a.corpus:p.error('--source-dir and --corpus required')
            result=preflight(source_dir=a.source_dir,corpus=a.corpus,inventory=a.inventory,reviews=a.reviews,private_dir=a.private_dir)
            if a.write_release:
                if result['status']!='ready_to_live':raise ValueError('SOC_RELEASE_GATE_BLOCKED')
                if a.write_release.resolve()!=private_directory()/'release.json':raise ValueError('SOC_CANONICAL_RELEASE_REQUIRED')
                atomic_json(a.write_release,result['release'])
            result.pop('release',None)
        else:
            if not a.release or not a.output_dir:p.error('--release and --output-dir required')
            result=run_live(release_path=a.release,output_dir=a.output_dir,private_dir=a.private_dir)
    except (ValueError,RuntimeError,OSError,KeyError):
        ledger=private_directory()/'ledger.json'
        state=json.loads(ledger.read_text()) if ledger.is_file() else {}
        result={'status':'blocked','error':'SOC_GATE_OR_SCOPE_INVALID','client_created':state.get('client_created',False),
            'scope_attempted_calls':len(state.get('reservations',[])),'scope_cost_unknown':state.get('unknown_cost',False),'attempted_calls_this_invocation':None if state else 0}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status'] in ('ready_to_live','completed') else 2
if __name__=='__main__':raise SystemExit(main())
