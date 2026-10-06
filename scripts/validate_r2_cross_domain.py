"""Validate locked cross-domain data/gold identities offline; never create a client."""
import argparse
import json
from pathlib import Path

from evaluation.r2_cross_domain_v1.benchmark_lock import validate_benchmark


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--benchmarks',type=Path,required=True)
    parser.add_argument('--lock',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=validate_benchmark(args.registry,args.benchmarks,args.lock)
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as handle:
            handle.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
