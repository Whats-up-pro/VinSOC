"""Independent kernel observations; diagnostic programs are not model predictions."""
import json
import os
import sys
import time
from pathlib import Path

import pytest


def test_group_limit_is_required_before_any_worker(tmp_path):
    from vinsoc_text2sql.process_group import ProcessGroup, GroupError
    with pytest.raises(GroupError, match='CGROUP_V2_REQUIRED'):
        ProcessGroup(root=tmp_path)
    assert list(tmp_path.iterdir()) == []


required = pytest.mark.skipif(os.environ.get('VINSOC_QUERY_REAL_DATA_REQUIRED') != '1',
                              reason='Required Linux real-data job observes kernel boundaries')


@required
def test_worker_observed_boundaries(tmp_path):
    from vinsoc_text2sql.executor import SqlExecutor
    from vinsoc_text2sql.process_group import ProcessGroup
    from evaluation.r2_cross_domain_v1.data import DatabaseContext
    context = DatabaseContext.from_manifest(Path('evaluation/r2_cross_domain_v1/runtime_registry.json'), 'ctu_dev')
    os.environ['VINSOC_BOUNDARY_SECRET_SENTINEL'] = 'must-never-enter-worker'
    observations = {}
    with ProcessGroup() as group:
        process = group.spawn(SqlExecutor()._command(context.snapshot_path), timeout_seconds=2)
        deadline = time.monotonic() + 5
        worker = None
        while time.monotonic() < deadline:
            for pid in group.path.joinpath('cgroup.procs').read_text().split():
                proc = Path('/proc')/pid
                try:
                    if b'/worker.py' in (proc/'cmdline').read_bytes() and (proc/'comm').read_text().strip().startswith('python'):
                        worker = proc
                        break
                except FileNotFoundError:
                    pass
            if worker:
                break
            time.sleep(.01)
        assert worker is not None, 'ISOLATED_WORKER_NOT_OBSERVED'
        assert os.readlink(worker/'ns/net') != os.readlink('/proc/self/ns/net')
        environment = (worker/'environ').read_bytes().split(b'\0')
        assert all(e.split(b'=')[0] in (b'', b'LC_CTYPE') for e in environment)
        assert b'must-never-enter-worker' not in b'\0'.join(environment)
        mounts = (worker/'mountinfo').read_text().splitlines()
        snapshot_mounts = [m.split() for m in mounts if m.split()[4].startswith('/snapshot/')]
        assert len(snapshot_mounts) == 1
        assert snapshot_mounts[0][4] == '/snapshot/db.duckdb'
        assert 'ro' in snapshot_mounts[0][5].split(',')
        assert not any('/.vinsoc/' in m or '/.env' in m for m in mounts)
        assert group.path.joinpath('memory.max').read_text().strip() == '536870912'
        assert group.path.joinpath('memory.swap.max').read_text().strip() == '0'
        assert group.path.joinpath('cpu.max').read_text().strip() == '100000 100000'
        assert len(os.sched_getaffinity(int(worker.name))) == 1
        limits = (worker/'limits').read_text()
        assert 'Max cpu time' in limits
        report = json.loads(Path('results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json').read_text())
        sql = next(r['final_sql'] for r in report['case_results'] if r['case_id'] == 'ctu_sql_001')
        stdout, stderr = process.communicate(json.dumps({'sql': sql, 'parameters': [], 'row_cap': 10000, 'timeout_seconds': 2}), timeout=5)
        assert process.returncode == 0, stderr
        assert json.loads(stdout.splitlines()[-1])['status'] == 'OK'
        observations = {'network_namespace_distinct': True, 'environment_allowlist_only': True,
                        'only_required_snapshot_read_only': True, 'memory_max_bytes': 536870912,
                        'swap_max_bytes': 0, 'cpu_max': '100000 100000', 'affinity_cpus': 1,
                        'proof': 'external /proc and cgroup filesystem, not executor isolation fields',
                        'model_calls': 0}
    receipt_dir = os.environ.get('VINSOC_QUERY_OBSERVATION_DIR')
    if receipt_dir:
        Path(receipt_dir).mkdir(parents=True, exist_ok=True)
        (Path(receipt_dir)/'worker_observed_boundaries.json').write_text(json.dumps(observations, indent=2))


@required
def test_memory_is_shared_by_all_descendants_and_timeout_kills_group():
    from vinsoc_text2sql.process_group import ProcessGroup
    # Two independent allocations exceed the aggregate cap, while each stays below it.
    program = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(300*1024*1024); time.sleep(30)']); x=bytearray(300*1024*1024); time.sleep(30)"
    with ProcessGroup() as group:
        process = group.spawn([sys.executable, '-c', program], timeout_seconds=2)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            events = dict(line.split() for line in (group.path/'memory.events').read_text().splitlines())
            if int(events['oom_kill']) > 0:
                break
            time.sleep(.02)
        assert int(events['oom_kill']) > 0, 'AGGREGATE_MEMORY_LIMIT_NOT_ENFORCED'
        group.kill()
        process.communicate(timeout=3)
        assert not (group.path/'cgroup.procs').read_text().strip()
    with ProcessGroup() as group:
        process = group.spawn([sys.executable, '-c', 'while True: pass'], timeout_seconds=1)
        process.communicate(timeout=5)
        assert process.returncode != 0, 'CPU_TIME_LIMIT_NOT_ENFORCED'
    with ProcessGroup() as group:
        process = group.spawn([sys.executable, '-c', 'import time; time.sleep(30)'], timeout_seconds=1)
        with pytest.raises(Exception) as failure:
            group.communicate(process, '', timeout_seconds=.1)
        assert str(failure.value) == 'GROUP_TIMEOUT'
        assert not (group.path/'cgroup.procs').read_text().strip()
