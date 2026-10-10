# VinSOC — Khôi phục DB gốc ngày 10/10/2026

Hai ZIP do operator push ở `3a77ec7d2d83b31bd7722632884233f21710cff8` đã đủ dữ liệu để tiếp tục R1/T2. Không cần xuất hoặc dựng lại 12 DB Spider trên laptop.

| Đầu vào | SHA-256 | Kết quả |
|---|---|---|
| `VinSOC_Runtime_DB_20261010.zip` | `7cc72e34d50b5533ae44d23abcf1b68aa949a8fed972ccce73c932bd6c67114e` | Đủ 13 DB/manifest; từng binary đúng khóa gốc |
| `VinSOC_CTU_20261010.zip` | `2847ba055dee714195898251e686ad62f0856c721eda84af8782c77a33293dc4` | Cùng CTU `0b29765b…` trong runtime ZIP |

User chủ động lưu hai ZIP trong Git; bước khôi phục/CI sử dụng chính artifact đã pin này. DB được giải nén và nguồn vẫn ở ignored paths. Không xóa ZIP hoặc đổi registry/locks; bản recovery và receipts trước đó giữ nguyên làm lịch sử. Retention artifact CI mới là 90 ngày.

## Đã kiểm thực tế

- Khôi phục 13 exact binaries, kiểm checksum, không WAL, không ghi đè dữ liệu khác hash.
- Dùng lại Spider archive đã tải đúng `00636695…`, lấy đúng dev/tables/12 SQLite members; không tải lại hoặc chọn/dựng DB mới. Bản archive cũ bị thiếu bytes được giữ tại `data/r2_cross_domain_v1/sources/spider_data.unverified-preserved-20261010.zip` với hash trong receipt.
- Kiểm schema, PK/FK của nguồn, catalog, row counts, source/member/content/logical/binary identity; CTU S5/S7 và origin logical identity đạt.
- Chạy đủ **120 gold** trên DB gốc: **24 calibration + 96 evaluation**, external 80 và CTU 40; đối chiếu SQLite–DuckDB cho external. Đây là kiểm dữ liệu/SQL chuẩn, không phải điểm của mô hình.
- Kiểm lại toàn bộ **492 file dữ liệu lịch sử** trước và sau thao tác.

Validator lịch sử vẫn báo code-lock mismatch ở `evaluation/r2_cross_domain_v1/tools.py`, do adapter runtime đã thay trước lượt này. Không sửa khóa để biến trạng thái đó thành PASS. Validator mới kiểm toàn bộ data/scorer/primitives còn lại, ghi rõ ngoại lệ này và hash hiện hành của adapter; không cấp quyền paid hoặc tự chứng nhận worker.

## Lệnh tái lập

```bash
python -m scripts.restore_query_data_bundle --repo . --bundle VinSOC_Runtime_DB_20261010.zip
python -m scripts.validate_original_query_data --restore-sources --output .vinsoc/new-validation/real_data_validation.json
VINSOC_QUERY_REAL_DATA_REQUIRED=1 python -m pytest -q tests/test_query_real_data.py tests/test_query_bundle_restore.py
```

Nếu đã có Spider archive đúng hash, thêm `--archive <path>` để dùng lại. Output validator phải là tên mới; không ghi đè receipts. Thiếu DB/nguồn/worker ở job required sẽ FAIL, không skip. Không đặt `VINSOC_LOCAL_SNAPSHOT` của network v1 bằng CTU cross-domain để né gate.

## Gate tiếp theo

Host hiện tại không chạy được worker cách ly; minimal bubblewrap probe trả `Failed to create NETLINK_ROUTE socket: Operation not permitted`, saved live SQL chưa nhận được `worker_ready`. Không bỏ network isolation hoặc chuyển SQL mô hình vào process chính. Job `query-real-data` trên CI Linux kiểm DB/nguồn/120 gold, saved live SQL và 120 gold qua cùng `SqlExecutor`, cho cả Python 3.11/3.12, không có API key/model calls.

CI positive path chưa thay thế việc quan sát boundary và chứng minh tổng memory 512 MiB cho process group. R2 chưa hoàn tất nếu các kiểm đó thiếu. Tích hợp native/routing/assessment và calibration/evaluation/pipeline mới vẫn cần các gate R3–R8 trước lượt paid; không đánh đồng gold replay với nghiệm thu live.

Hai ZIP này **không** chứa network-v1 binary `91a13ab1…` hoặc canonical ledger/gates. A2/A3 cũ vẫn cần identity/state của protocol cũ; không tráo binary.

Receipts: `results/evaluation_v1/text2sql_integration_v1/original_data_20261010/{bundle_restore_receipt,real_data_validation,local_worker_probe}.json`. Kết quả local suite và exact-SHA CI được ghi sau khi lệnh/job thực hoàn tất.
