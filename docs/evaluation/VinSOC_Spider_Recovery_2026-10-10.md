# Khôi phục Spider — quyết định và cách tiếp tục ngày 10/10/2026

Người dùng đã duyệt khôi phục riêng 12 DB Spider từ đúng archive đã ghim,
kiểm schema/nội dung và replay bộ câu hỏi hiện có. Đây là bổ sung cho T2 trong
`docs/superpowers/plans/2026-10-08-vinsoc-text2sql-integration-and-final-demo.md`.
Không đổi lựa chọn DB, 120 câu, gold, comparator, scorer, kết quả hoặc khóa lịch sử.

## Vì sao cần bản khôi phục

Exporter lịch sử báo 12 Spider binary thiếu trên laptop; CTU đúng hash đã qua
kiểm tra. ZIP Spider nguồn cũng chưa có trên laptop. Không dùng các DB khác
trong `data/` thay thế. Lỗi quyền của `source_probes/pytest-*` không liên quan.
Không cần sửa ACL hoặc tạo lại đường dẫn checkout cũ.

Raw hash của hai lần dựng cùng nội dung có thể khác nhau. Vì vậy bản khôi phục
có `runtime_registry.json`, `recovery.lock.json`, receipt và bundle riêng trong
`.vinsoc/`. Exporter `export_vinsoc_db_bundle.py` vẫn kiểm đúng 13 binary cũ;
không đổi script đó thành chấp nhận DB dựng lại.

Nguồn: Spider 1.0 dev, CC BY-SA 4.0, theo source manifest hiện có.
Archive SHA-256:
`00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`.
Mỗi member phải khớp receipt nguồn gốc. Mỗi DB dựng lại phải khớp source hash,
logical hash, content hash, schema, PK/FK và row counts gốc; chỉ raw binary hash
được ghi mới. Không chấp nhận WAL hoặc snapshot đổi bytes sau truy vấn.

## Chạy trên checkout hiện tại

Nếu cần tự khôi phục, dùng Python của `.venv` đã cài dependencies trong repo,
DuckDB đúng 1.5.5:

```powershell
git pull --ff-only origin master
python -m scripts.recover_vinsoc_spider_bundle --repo .
```

Script tải đúng archive nếu chưa cấp `--archive`, không tạo SDK/model client.
Đầu ra mặc định: `.vinsoc/spider-recovery-v1/`. Thư mục đã tồn tại thì bị chặn;
không xóa hoặc chạy đè để che failure. `--output` khác chỉ dùng cho lần dựng dữ
liệu offline có lý do và lưu receipt; không cấp quyền mở lượt paid mới.

Có archive đúng hash thì dùng:

```powershell
python -m scripts.recover_vinsoc_spider_bundle --repo . --archive .\spider_data.zip
```

`--check-only --archive <file>` chỉ kiểm prerequisites/source, không tải, dựng
hoặc tạo output. Không trỏ `--output` vào thư mục lịch sử.

Nếu thiếu CTU, `SPIDER_RECOVERED_CTU_PENDING` là thành công của phần khôi phục
12 Spider, **chưa đạt toàn bộ gate dữ liệu**: replay 80 câu ngoài SOC, còn 40
CTU (8 calibration + 32 evaluation). Nếu có CTU exact trên cùng checkout,
script kiểm identity gốc, copy bytes vào bundle riêng và replay đủ 120.
Không rebuild CTU hoặc dùng snapshot network demo thay cho nó.

## Phần duy nhất cần chuyển từ laptop lúc này

Cloud đã tải được archive Spider, nên không bắt operator tải/dựng Spider lại.
Tại `Phase3_VinSOC`, đóng gói CTU đang có rồi gửi ZIP:

```powershell
Compress-Archive -LiteralPath .\data\ctu_network_public\snapshots\ctu_dev.duckdb -DestinationPath ..\VinSOC_CTU_20261010.zip
```

File bên trong phải có SHA-256
`0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9`.
Trước khi nhận: không gọi model, không đổi registry lịch sử để hợp thức thiếu CTU.

## CI và bàn giao

Workflow `recover-spider-data.yml` dựng đúng nguồn thật và replay 80 câu trên
Python 3.11/3.12. Mỗi job có raw hashes/lock riêng; không giả định binary giữa
hai lần dựng phải giống nhau. Artifact `spider-recovery-<SHA>-py<version>` giữ
90 ngày, gồm bundle có archive nguồn, selected SQLite members, 12 DB và locks.
Sau khi chọn artifact để vận hành, phải pin run/artifact identity và digest,
restore đúng bytes đó; không rebuild khi đổi host.

Workflow này chưa đóng worker/integration gate và chưa thay việc restore toàn
bộ 13 DB trong CI nghiệm thu. Receipt `paid_authorized=false`, model calls=0;
gold replay là kiểm dữ liệu, không là điểm Text-to-SQL hoặc E2E.

Một adapter runtime (`tools.py`) hiện đã đổi so với khóa code lịch sử; receipt
ghi rõ `historical_code_lock_pass=false`. 492 file dữ liệu/benchmark lịch sử
vẫn phải giữ đúng hash. Protocol paid mới phải bind runtime/source/worker/CI
hiện hành và bản recovery đã chọn trước transmission.

## Nhật ký quyết định

- Quyết định đã duyệt: dùng identity khôi phục riêng thay vì sửa raw hash cũ.
  Nếu nội dung không khớp, giữ failure và không dùng làm dữ liệu nghiệm thu.
- Các probe dựng/replay ở thư mục tạm đều đạt; dựng trực tiếp trong checkout
  có đồng bộ file làm WAL đã xóa xuất hiện lại. Các output/failure được giữ
  lại, không đóng gói thành công. Dựng trong thư mục tạm, chỉ copy binary đã
  đóng/kiểm hash vào cây bàn giao; kiểm lại WAL và bytes sau replay. Không sửa
  primitive hoặc lịch sử để bỏ qua lỗi.
- Master và inline đã được người dùng chỉ định; không branch/PR/subagent.
  Tự rà mã phục vụ kiểm kỹ thuật, không thay người thật duyệt kết quả/demo.

Tiếp theo: nhận CTU exact → replay đủ 120 → pin bundle đầy đủ → kiểm worker
thực → tiếp T3–T7 còn thiếu. Calibration/evaluation/pipeline vẫn chưa chạy;
quyền paid/ngân sách mới vẫn là gate riêng.
