"""Isolated worker; stdin is a trusted, AST-validated executor request."""
import hashlib
import json
import math
import os
import resource
import sys

sys.path.insert(0, '/packages')


def main():
    request = json.load(sys.stdin)
    resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(request['timeout_seconds']),
                                         math.ceil(request['timeout_seconds'])+1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    import duckdb
    connection = duckdb.connect('/snapshot/db.duckdb', read_only=True, config={
        'enable_external_access': False, 'autoload_known_extensions': False,
        'autoinstall_known_extensions': False, 'threads': 1, 'memory_limit': '256MB',
        'temp_directory': '/tmp'})
    print(json.dumps({'status': 'worker_ready'}), flush=True)
    try:
        cursor = connection.execute(request['sql'], request['parameters'])
        columns = [{'name': item[0], 'type': str(item[1])} for item in cursor.description]
        raw = cursor.fetchmany(request['row_cap']+1)
        def encode(v):
            if v is None or type(v) in (str, int, bool):
                return v
            if type(v) is float:
                if not math.isfinite(v):
                    raise ValueError('NONFINITE_RESULT')
                return v
            if isinstance(v, bytes):
                return {'bytes_hex': v.hex()}
            return v.isoformat() if hasattr(v, 'isoformat') else str(v)
        rows = [[encode(v) for v in row] for row in raw[:request['row_cap']]]
        identity = {'columns': columns, 'rows': rows, 'truncated': len(raw)>request['row_cap']}
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(encoded.encode()) > 8*1024*1024:
            raise ValueError('RESULT_PAYLOAD_LIMIT')
        return {'status': 'OK', **identity, 'row_count': len(rows),
                'result_sha256': hashlib.sha256(encoded.encode()).hexdigest()}
    finally:
        connection.close()


try:
    result = main()
except Exception:
    result = {'status': 'failed', 'error_category': 'SQL_EXECUTION_FAILED'}
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
