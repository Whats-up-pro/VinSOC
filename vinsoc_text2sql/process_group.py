"""Kernel-enforced limits shared by every descendant of an isolated worker."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


class GroupError(ValueError):
    pass


class ProcessGroup:
    MEMORY_BYTES = 512 * 1024 * 1024

    def __init__(self, *, root=None):
        candidate = root or os.environ.get('VINSOC_QUERY_CGROUP_ROOT', '')
        root = Path(candidate).resolve()
        if (sys.platform != 'linux' or not candidate
                or not root.is_relative_to(Path('/sys/fs/cgroup'))
                or not (root/'cgroup.controllers').is_file()
                or not {'memory', 'cpu', 'pids'}.issubset((root/'cgroup.subtree_control').read_text().split())):
            raise GroupError('CGROUP_V2_REQUIRED')
        self.path = root/('query-'+uuid.uuid4().hex)
        try:
            self.path.mkdir()
            if not (self.path/'cgroup.kill').exists():
                self.path.rmdir()
                raise GroupError('ATOMIC_GROUP_KILL_REQUIRED')
            for name, value in {'memory.max': str(self.MEMORY_BYTES), 'memory.swap.max': '0',
                                'cpu.max': '100000 100000', 'pids.max': '32'}.items():
                (self.path/name).write_text(value)
                if (self.path/name).read_text().strip() != value:
                    raise GroupError('GROUP_LIMIT_UNVERIFIED')
        except OSError:
            raise GroupError('CGROUP_V2_REQUIRED') from None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kill()
        self.path.rmdir()

    def spawn(self, command, *, timeout_seconds):
        def attach():
            import math
            import resource
            # The child enters the group before executing any worker code.
            (self.path/'cgroup.procs').write_text(str(os.getpid()))
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
            resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(timeout_seconds), math.ceil(timeout_seconds)+1))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env={},
                                start_new_session=True, preexec_fn=attach)

    def kill(self):
        import signal
        # cgroup.kill is atomic and includes descendants; kernels without it fail closed.
        kill_file = self.path/'cgroup.kill'
        if kill_file.exists():
            kill_file.write_text('1')
        else:
            # Never run a worker without an available atomic group kill operation.
            for pid in (self.path/'cgroup.procs').read_text().split():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        import time
        deadline = time.monotonic()+3
        while (self.path/'cgroup.procs').read_text().strip():
            if time.monotonic() >= deadline:
                raise GroupError('GROUP_TERMINATION_FAILED')
            time.sleep(.01)

    def communicate(self, process, payload, *, timeout_seconds):
        try:
            return process.communicate(payload, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self.kill()
            process.communicate()
            raise GroupError('GROUP_TIMEOUT') from None
