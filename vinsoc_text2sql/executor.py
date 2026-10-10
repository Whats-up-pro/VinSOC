"""Fail-closed Linux namespace executor for model-authored read-only SQL."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic

from evaluation.r2_cross_domain_v1.safety import validate_sql
from vinsoc_text2sql.process_group import ProcessGroup, GroupError


class ExecutorError(ValueError):
    pass


class SqlExecutor:
    VERSION = 'text2sql_namespace_cgroup_executor_v2'
    FINAL_ROW_CAP = 10000
    MEMORY_BYTES = 512 * 1024 * 1024

    def _command(self, snapshot):
        backend = shutil.which('bwrap')
        if not backend or sys.platform != 'linux':
            raise ExecutorError('WORKER_ISOLATION_REQUIRED')
        base = Path(sys.base_prefix).resolve()
        executable = Path(sys.executable).resolve()
        packages = Path(__import__('duckdb').__file__).parent.parent.resolve()
        worker = Path(__file__).with_name('_worker.py').resolve()
        command = [backend, '--unshare-all', '--die-with-parent', '--new-session',
                   '--cap-drop', 'ALL', '--clearenv', '--ro-bind', str(base), str(base)]
        for directory in ('/lib', '/lib64', '/usr/lib'):
            if Path(directory).exists():
                command += ['--ro-bind', directory, directory]
        command += ['--ro-bind', str(packages), '/packages', '--ro-bind', str(worker), '/worker.py',
                    '--dir', '/snapshot', '--ro-bind', str(snapshot), '/snapshot/db.duckdb',
                    '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--chdir', '/tmp',
                    str(executable), '-I', '/worker.py']
        return command

    @staticmethod
    def timeout_category(stdout):
        return 'SQL_TIMEOUT' if '"status": "worker_ready"' in (stdout or '') else 'WORKER_ISOLATION_OR_STARTUP_FAILED'

    def query(self, context, sql, parameters=(), *, row_cap, timeout_seconds):
        validate_sql(sql, context)  # No process is started for unsafe SQL.
        if (type(row_cap) is not int or not 1 <= row_cap <= self.FINAL_ROW_CAP
                or type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 10):
            raise ExecutorError('INVALID_EXECUTION_CAP')
        snapshot = Path(context.snapshot_path).resolve()
        if not snapshot.is_file():
            raise ExecutorError('REAL_DATA_REQUIRED')
        before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if before != context.identity.get('duckdb_binary_sha256'):
            raise ExecutorError('SNAPSHOT_CHECKSUM_MISMATCH')
        payload = json.dumps({'sql': sql, 'parameters': parameters, 'row_cap': row_cap,
                              'timeout_seconds': timeout_seconds}, ensure_ascii=False)
        started = monotonic()
        try:
            command = self._command(snapshot)
            with ProcessGroup() as group:
                process = group.spawn(command, timeout_seconds=timeout_seconds)
                stdout, _stderr = group.communicate(process, payload, timeout_seconds=timeout_seconds)
        except GroupError as error:
            raise ExecutorError('SQL_TIMEOUT' if str(error) == 'GROUP_TIMEOUT' else str(error)) from None
        if process.returncode != 0:
            # Do not leak worker stderr, mount paths or SQL error bodies.
            raise ExecutorError('WORKER_ISOLATION_OR_STARTUP_FAILED')
        try:
            lines = stdout.splitlines()
            if not lines or json.loads(lines[0]).get('status') != 'worker_ready':
                raise ExecutorError('WORKER_ISOLATION_OR_STARTUP_FAILED')
            result = json.loads(lines[-1])
        except (ValueError, TypeError):
            raise ExecutorError('INVALID_WORKER_RECEIPT') from None
        if result.get('status') != 'OK':
            raise ExecutorError(result.get('error_category', 'SQL_EXECUTION_FAILED'))
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != before:
            raise ExecutorError('SNAPSHOT_CHANGED')
        result.update(database_id=context.database_id, snapshot_binary_sha256=before,
                      snapshot_logical_sha256=context.identity['logical_sha256'],
                      sql=sql, sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                      executor_version=self.VERSION, wall_seconds=monotonic()-started,
                      isolation={'backend': 'bubblewrap', 'network': 'unshared', 'secrets': 'absent',
                                 'snapshot_mount': 'read_only', 'memory_bytes': self.MEMORY_BYTES,
                                 'cpu_count': 1, 'timeout_seconds': timeout_seconds})
        return result
