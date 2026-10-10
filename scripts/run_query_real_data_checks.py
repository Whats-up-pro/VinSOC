"""Enter a systemd-delegated subtree as the runner user, then run required tests."""
import os
import sys
from pathlib import Path


def main():
    if sys.platform != 'linux':
        raise ValueError('LINUX_DELEGATED_CGROUP_REQUIRED')
    groups = dict(line.split('::', 1) for line in Path('/proc/self/cgroup').read_text().splitlines())
    relative = groups.get('0', '')
    if not relative.endswith('/vinsoc-query-real-data.service'):
        raise ValueError('SYSTEMD_DELEGATION_REQUIRED')
    root = Path('/sys/fs/cgroup')/relative.lstrip('/')
    manager = root/'supervisor'
    manager.mkdir()
    (manager/'cgroup.procs').write_text(str(os.getpid()))
    (root/'cgroup.subtree_control').write_text('+memory +cpu +pids')
    os.environ['VINSOC_QUERY_CGROUP_ROOT'] = str(root)
    os.execv(sys.executable, [sys.executable, '-m', 'pytest', '-q',
             'tests/test_query_real_data.py', 'tests/test_query_bundle_restore.py',
             'tests/test_query_worker_boundaries.py',
             '--junitxml=.vinsoc/query-real-data-ci/required_checks.xml'])


if __name__ == '__main__':
    main()
