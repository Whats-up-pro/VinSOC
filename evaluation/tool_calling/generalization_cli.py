"""Guarded commands for the added split, using the unchanged historical runner."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluation.tool_calling.generalization import verify_generalization_lock
from evaluation.tool_calling.generalization_run import MODEL, SPLIT, cli_generalization


def run_benchmark(args):
    return cli_generalization(args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('list', 'lock', 'preflight', 'run'):
        command = commands.add_parser(name)
        command.add_argument('split', choices=['generalization_v1'])
        if name in ('preflight','run'):
            command.add_argument('--authorization', type=Path)
            command.add_argument('--budget-usd')
            command.add_argument('--model', default=MODEL)
            command.add_argument('--output', type=Path)
            command.add_argument('--output-dir', type=Path, default=Path('.vinsoc/r1-generalization/run'))
    args = parser.parse_args(argv)
    if args.command == 'list':
        from evaluation.tool_calling.__main__ import list_cases
        return list_cases(args)
    if args.command == 'lock':
        checked = verify_generalization_lock(SPLIT,SPLIT/'GENERALIZATION.lock')
        print(json.dumps(asdict(checked)))
        if not checked.passed:
            raise ValueError('GENERALIZATION_LOCK_INVALID')
        return checked
    return run_benchmark(args)


if __name__ == '__main__':
    main()
