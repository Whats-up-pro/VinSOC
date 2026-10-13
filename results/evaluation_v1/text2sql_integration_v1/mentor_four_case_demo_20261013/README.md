# Demo mentor — bốn case đã có API thật

Mở `index.html`. Trang này có 4/4 record của bốn case đã chọn, không gọi API.
Hai case đạt kỹ thuật và chờ người duyệt; một case incomplete; một case failed.
Đây là bốn demo độc lập với producer riêng, không phải một lượt pipeline32 hoặc
evaluation cùng SHA. Original reports, SQL, usage và source identities giữ nguyên.

## Mở demo

```powershell
Set-Location D:\VINUNI_AI2026\Phase3_VinSOC
Start-Process 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/index.html'
```

## Kịch bản 10–15 phút

1. **Mở bảng bốn case:** chỉ rõ 4 record đã có; không còn missing trong bốn ID.
   Trạng thái case được lấy từ facts, provenance, integrated EX và human review.
2. **Show luồng end-to-end mới bằng case AVG `ctu_cross_bce6d3679ade4cd6`:** đọc
   nguyên văn câu hỏi; mở native routing; mở schema/value trajectory; mở SQL; DB
   trả `TCP`; mở observed/derived evidence và parent ID; mở assessment dẫn chứng;
   mở verification và EX; kết thúc tại human review pending.
3. **Giải thích dễ hiểu:** “Ta tính average bytes của từng protocol rồi so với
   average của toàn scenario 7. Chỉ TCP vượt mức chung. Kết quả không chứng minh
   TCP độc hại; vẫn thiếu CTI/endpoint context và cần analyst đọc nhận định.”
4. **Mở case đếm `459`:** đây là run trước đã thành công. Hai EXISTS tìm IP chung
   ở S5 và S7 sau hai strict time boundaries. Producer/version/run giữ riêng.
5. **Mở edge case NULL `ctu_cross_3f659571f998adb0`:** SQL WHERE trước GROUP BY
   loại hết các nhóm không có match. Gold contract yêu cầu mỗi protocol, kể cả
   count 0. SQL đã chạy nhưng EX false. Response assessment thật có observations
   rỗng và bị từ chối; không sửa thành một assessment hợp lệ.
6. **Mở edge case UDP `ctu_cross_66b8e92a76c3359b`:** SQL và worker đã trả 9.780
   hàng không truncated. Rows riêng khoảng 186.810 bytes, lớn hơn cap assessment
   32.768 bytes. Pipeline dừng trước call assessment và trước scorer. Giữ EX
   unscored, không dùng replay/SQL sửa tay để nâng thành pass. Preview HTML chỉ
   tám hàng để dễ đọc; full rows thật vẫn ở JSON gốc.
7. **Mở chi phí/request IDs:** 23/23 responses mới; $0.02040420 mới; cumulative
   allocation $0.08155920; còn $2.91844080 trong cap $3; unknown exposure false.
   Invalid assessment và partial UDP đều đã được tính tiền.
8. **Kết luận:** đã có hai trace end-to-end kỹ thuật và hai lỗi thật để giải thích.
   Human approvals vẫn 0; calibration 0/48, evaluation 0/192 và pipeline chính
   thức 32 câu chưa được chạy. Không ghi COMPLETE cho các suite đó.

## Review thật của case AVG

```powershell
py -m cli.main query-review 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/cloud_public/ctu_cross_bce6d3679ade4cd6/live/E3_ctu_cross_bce6d3679ade4cd6.json' --output 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/analyst-review-avg.json'
```

Người thật tự nhập identity, decision, rationale và UTC thực tế. Không tự approve.
Receipt review mới liên kết hash của case gốc; không sửa case để khớp review.
Sau khi review thành công, render một trang mới:

```powershell
py -m scripts.render_query_pipeline_report 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/cloud_public/ctu_cross_bce6d3679ade4cd6/live/report.json' --review 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/analyst-review-avg.json' --output 'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/avg-reviewed.html'
```

`index.html` là snapshot tĩnh; mở trang reviewed mới để trình bày quyết định thật.

## Nguồn và tái lập

- `cloud_public/` và `preflight_public/`: bản sao nguyên bytes public artifacts.
- `existing_count_demo/`: bản sao bytes đã commit của run thành công trước.
- `assessment_responses/`: responses assessment thật đã lưu trước parse; có cả
  response không hợp lệ. Không có private request/journal được đưa vào Git.
- `views/`: renderer hiện hành xem riêng từng producer với mẫu số inventory 32.
- `demo_summary.json`: trạng thái của bốn demo, tách khỏi điểm suite chính thức.
- `artifact_manifest.json`: hash các file, SHA code, CI và nguồn Actions artifacts.

Có thể tái lập từng viewer bằng `python -m scripts.render_query_pipeline_report
<source_report> --output <new_file.html>`. Validator/renderer chỉ đọc artifacts.
Không cộng cả cost_events nested và top-level: chỉ tính journal events một lần.
Không dùng các SQL lưu để tạo thêm model score hoặc demo run mới.

Live workflow: https://github.com/Whats-up-pro/VinSOC/actions/runs/38369416643.
Preflight: https://github.com/Whats-up-pro/VinSOC/actions/runs/38368861277.
Producer CI: https://github.com/Whats-up-pro/VinSOC/actions/runs/38368039406.
