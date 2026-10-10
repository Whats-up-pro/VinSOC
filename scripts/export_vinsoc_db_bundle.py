#!/usr/bin/env python3
"""Đóng gói 13 DB đúng binary đã khóa; chạy trên máy giữ DB gốc.

  python scripts/export_vinsoc_db_bundle.py --repo . --check-only
  python scripts/export_vinsoc_db_bundle.py --repo . --output ../VinSOC_Locked_Runtime_DB_20261008.zip

Chỉ đọc danh sách DB cố định; không gọi model, không rebuild, không lấy .env/API key.
Bundle này tách biệt VinSOC_Qualified_Network_Snapshot_20261007.zip.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

FILES = [{'database_id': 'student_transcripts_tracking', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/student_transcripts_tracking/build_1.duckdb', 'sha256': 'e24fe6dc3e1fc974d402867e61914dcc98edaf866a42ecf42c0f778b5c60bf8a'}, {'database_id': 'cre_Doc_Template_Mgt', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/cre_Doc_Template_Mgt/build_1.duckdb', 'sha256': '57f8fe36123efd57eb4064d9b878326570e6779485b9a2a5d0e382f800749646'}, {'database_id': 'world_1', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/world_1/build_1.duckdb', 'sha256': '5db49abba55e2fc5ad2602cf70c5a5eefb34026e916b54f38058fdc690aca242'}, {'database_id': 'voter_1', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/voter_1/build_1.duckdb', 'sha256': '95524b974bb0b562cb5261ab5e1b31e7092524fb8001c85eabe6b9da7415d78c'}, {'database_id': 'dog_kennels', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/dog_kennels/build_1.duckdb', 'sha256': 'e631dc777c2041d11a8f9dd0978c8e01e8a6253af2ff2bc66ab934fc38e19711'}, {'database_id': 'orchestra', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/orchestra/build_1.duckdb', 'sha256': 'f7867ab139501fd2c2b772d3ea6e4e8f7271d8ab7858278405bd77740162bc3a'}, {'database_id': 'concert_singer', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/concert_singer/build_1.duckdb', 'sha256': 'ec6a69a065840fe18b95fa383cd4e9da57a2acc4aec73c65c9675a95899e19f1'}, {'database_id': 'car_1', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/car_1/build_1.duckdb', 'sha256': 'b63545a40f1419c0dba60806434763eb2967c97c1a554c4b99aa3f6167e1e2a2'}, {'database_id': 'flight_2', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/flight_2/build_1.duckdb', 'sha256': 'e7a85f8d8765a6310e74970ae4a9a55ddfa3b78a99fc04f9030611e132b42192'}, {'database_id': 'course_teach', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/course_teach/build_1.duckdb', 'sha256': 'f54ec5ad018cc60d324b508761a8bd07da8bc58f2dcf787111e2e443a89420fb'}, {'database_id': 'poker_player', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/poker_player/build_1.duckdb', 'sha256': '56edebee2d6c0386cec69843ccd467371941ea630fe0cd2edb35b30c9994a323'}, {'database_id': 'tvshow', 'path': 'data/r2_cross_domain_v1/snapshots/20261006T014925Z_c66580fa/tvshow/build_1.duckdb', 'sha256': '954c9058717139e3c019e87ee59d7d8a73ba53d0c1b531f914da79de589f1187'}, {'database_id': 'ctu_dev', 'path': 'data/ctu_network_public/snapshots/ctu_dev.duckdb', 'sha256': '0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9'}]

SOURCES = {'spider': {'schema_version': 1, 'source_id': 'spider-1.0-dev', 'source_version': 'Spider 1.0', 'official_project_url': 'https://yale-lily.github.io/spider', 'official_repository_url': 'https://github.com/taoyds/spider', 'download_url': 'https://drive.usercontent.google.com/download?id=1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J&export=download&confirm=t', 'license': 'CC BY-SA 4.0', 'acquired_at_utc': '2026-10-05T10:33:25Z', 'archive_filename': 'spider_data.zip', 'archive_sha256': '00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b', 'archive_sha256_provenance': 'Computed from the acquired official download; the publisher does not provide a SHA-256 on the cited source page.', 'archive_root': 'spider_data', 'split_member': 'spider_data/dev.json', 'schema_member': 'spider_data/tables.json', 'sqlite_member_pattern': 'spider_data/database/{database_id}/{database_id}.sqlite'}, 'ctu': {'schema_version': '1', 'sources': [{'archive_member': None, 'dataset_id': 'ctu13_s5', 'file_sha256': 'ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c', 'format': 'ctu13_binetflow', 'license_note': 'CTU-13 Scenario 5; attribute Sebastian Garcia and the Malware Capture Facility Project.', 'path': 'data/ctu_network_public/sources/capture20110815-2.binetflow', 'retrieved_at': '2026-09-27T15:09:29Z', 'source_name': 'CTU-13 Scenario 5', 'source_url': 'https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-46/detailed-bidirectional-flow-labels/capture20110815-2.binetflow'}, {'archive_member': None, 'dataset_id': 'ctu13_s7', 'file_sha256': 'df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680', 'format': 'ctu13_binetflow', 'license_note': 'CTU-13 Scenario 7; attribute Sebastian Garcia and the Malware Capture Facility Project.', 'path': 'data/ctu_network_public/sources/capture20110816-2.binetflow', 'retrieved_at': '2026-09-27T15:09:35Z', 'source_name': 'CTU-13 Scenario 7', 'source_url': 'https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-48/detailed-bidirectional-flow-labels/capture20110816-2.binetflow'}]}}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('VinSOC_Locked_Runtime_DB_20261008.zip'))
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    root = args.repo.resolve(strict=True)
    errors = []
    for item in FILES:
        path = root / item['path']
        if not path.is_file():
            errors.append({'database_id': item['database_id'], 'status': 'MISSING', 'path': item['path'], 'expected_sha256': item['sha256']})
            continue
        if not path.resolve().is_relative_to(root):
            errors.append({'database_id': item['database_id'], 'status': 'OUTSIDE_REPO'})
            continue
        if Path(str(path) + '.wal').exists():
            errors.append({'database_id': item['database_id'], 'status': 'WAL_PRESENT_CLOSE_WRITER_FIRST'})
            continue
        actual = digest(path)
        if actual != item['sha256']:
            errors.append({'database_id': item['database_id'], 'status': 'HASH_MISMATCH', 'expected_sha256': item['sha256'], 'actual_sha256': actual})
    if errors:
        print(json.dumps({'status': 'BLOCKED', 'errors': errors, 'bundle_created': False}, ensure_ascii=False, indent=2))
        return 1
    if args.check_only:
        print(json.dumps({'status': 'ALL_13_EXACT_BINARIES_VERIFIED', 'bundle_created': False}))
        return 0
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.error('File đầu ra đã tồn tại; chọn tên mới, không ghi đè.')
    fd, tmp = tempfile.mkstemp(prefix='.vinsoc-db-', suffix='.zip', dir=output.parent)
    os.close(fd)
    temporary = Path(tmp)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for item in FILES:
                bundle.write(root / item['path'], arcname=item['path'])
            bundle.writestr('bundle_manifest.json', json.dumps({'schema_version': 1, 'scope': 'r2_cross_domain_v1_locked_runtime_13', 'lock_baseline_commit': '791184cbc0346c3c6331dab63b603facfeb4005a', 'files': FILES, 'source_attribution': SOURCES, 'model_calls': 0}, ensure_ascii=False, indent=2) + '\n')
        with zipfile.ZipFile(temporary) as bundle:
            for item in FILES:
                with bundle.open(item['path']) as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual != item['sha256']:
                    raise RuntimeError('DB thay đổi trong lúc đóng gói: ' + item['database_id'])
        bundle_hash = digest(temporary)
        # Không ghi đè ngay cả nếu một tiến trình khác tạo output sau lần kiểm tra trên.
        with temporary.open('rb') as source, output.open('xb') as target:
            import shutil
            shutil.copyfileobj(source, target)
        print(json.dumps({'status': 'BUNDLE_CREATED_AND_VERIFIED', 'path': str(output), 'sha256': bundle_hash, 'database_count': 13, 'size_bytes': output.stat().st_size, 'model_calls': 0}, ensure_ascii=False, indent=2))
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
