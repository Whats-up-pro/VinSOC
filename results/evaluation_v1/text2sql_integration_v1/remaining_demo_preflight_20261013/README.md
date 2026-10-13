# Ba demo còn thiếu — preflight và blocker

Gói này lưu **preflight thật**, không có prediction, model response hoặc review.
Mã nguồn trước thay đổi: `3725ec3cc50f92d5e2a27ee3ce4232f63a4efa81`,
CI [38359598774](https://github.com/Whats-up-pro/VinSOC/actions/runs/38359598774) success.
`preparation.json` ghi source/code/receipt hashes và phép tính ngân sách.

| Case ID | Trạng thái |
|---|---|
| `ctu_cross_66b8e92a76c3359b` | Preflight blocked, chưa có model output |
| `ctu_cross_3f659571f998adb0` | Preflight blocked, chưa có model output |
| `ctu_cross_bce6d3679ade4cd6` | Preflight blocked, chưa có model output |

Mỗi preflight dùng câu hỏi nguyên văn từ `demo_selection.json`, E3 và một ca.
Không cung cấp private account/pricing/authorization; do đó các gate canonical
reconciliation, runtime/data/CI/worker, account, pricing/token bound và paid
release chưa đạt. Chưa tạo provider; attempted/received/cost mới đều bằng 0.
Các blocker local này không phủ định CI Linux/real-data đã xanh ở commit nguồn.

## Những thay đổi đã làm

CLI public nhận `--scope demo` và chuyển vào runner chung. Demo vẫn cần đúng
case ID, câu gốc, E3 và release riêng. Grant trong canonical allocation ledger
phải khớp case/condition/execution; quyền ca đầu không tự mở ca khác. Scope,
condition và case của release cũng phải khớp lựa chọn CLI trước `run_live`.

TDD đã chứng minh CLI từ chối `demo` trước sửa rồi nhận đúng cả bốn ID;
wrong case/condition/execution trong grant và scope/condition/case của release
đã có test RED rồi GREEN. Nhóm query/cloud: **99 passed**. Preservation kiểm
**3640 protected files**, `protected_changed=[]`, hai ZIP pin giữ nguyên hash;
`git diff --check` đạt. Review độc lập phát hiện hai ràng buộc permission/release
ở trên; đã sửa trong một vòng TDD. Các fixture grant âm chỉ nằm trong test tmp,
`paid_authorized=false`, không tạo paid authorization hay model artifact.

Cloud workflow hiện tại vẫn chỉ nhận ca `ctu_cross_708b66575657429a` và các
profile lịch sử tới `full-e2e-10`; window đó đã dùng. Gói này không mở một cloud
profile hay batch release mới. Cần cloud adapter cho lựa chọn mới sau khi đã
xác định hợp đồng release và đối soát ngân sách.

## Ngân sách cần đối soát trước khi chạy

Allocation hiện có: `$3`; chi phí đã xác minh: `$0.061155`; còn `$2.938845`.
Theo **cận bảo thủ của preflight run10**, một ca E3 là `$1.6732608`; tổng cận
ba ca là `$5.0197824`, yêu cầu allocation tổng `$5.0809374` khi cộng prior cost.
Chênh lệch với cap cũ là `$2.0809374`.

Đây là phép tính planning từ pricing/protocol đã lưu, không phải chi phí thực tế
hay quote đã xác minh giá hiện tại. Giá/account mới vẫn phải qua gate. Không
dùng chi phí thực tế nhỏ của một ca để tuyên bố ngân sách đủ cho cả ba. Mỗi lần
chạy thêm cần đối soát actual/unknown exposure trước quyền tiếp theo; không dùng
lại cùng số prior cost cho các execution khác nhau.

## Lệnh preflight cho operator

Từ repo root, lấy nguyên văn câu hỏi trong selection. Ví dụ PowerShell:

```powershell
$selection = Get-Content -Raw 'results/evaluation_v1/text2sql_integration_v1/demo_selection.json' | ConvertFrom-Json
$case = $selection.cases | Where-Object { $_.case_id -eq 'ctu_cross_66b8e92a76c3359b' }
py -m cli.main query --scope demo --condition E3 --case-id $case.case_id --question $case.question --preflight-only --output 'results/preflight-remaining-case.json'
```

Receipt public thiếu private gate inputs nên không thể dùng làm live release.
Muốn chạy thật phải cung cấp account/project và đối soát canonical ledger có
hash, authorization cho đúng ca/E3/execution, giá/token bound hiện hành,
runtime/snapshot/worker pin và CI đúng implementation SHA. Cần bổ sung cap hoặc
versioned protocol có cận mới được chứng minh nếu tổng cận không nằm trong cap.

Ca đầu vẫn có trace thật `459`, đang chờ receipt analyst. Ba ca mới vẫn missing
trong viewer; các suite chính thức giữ `0/48`, `0/192`, `0/32`.
