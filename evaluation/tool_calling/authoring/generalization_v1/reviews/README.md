# Duyệt mù `generalization_v1`

Hai file `reviewer_a.jsonl` và `reviewer_b.jsonl` là hai gói độc lập. Mỗi người duyệt chỉ nhận một file, không xem metadata soạn thảo, file của người còn lại hoặc output của model.

## Cách điền

Giữ nguyên bốn trường có sẵn trong từng dòng:

- `case_id`
- `request`
- `difficulty`
- `production_schema_reference`

Thêm ba trường sau vào đủ 120 dòng:

```json
{
  "reviewer_id": "định-danh-người-duyệt",
  "reviewer_signature": "chữ-ký-hoặc-mã-xác-nhận",
  "expected_calls": [
    {
      "tool": "network_investigation",
      "required_arguments": {"indicator": "198.51.100.10"},
      "critical_arguments": ["indicator"]
    }
  ]
}
```

Quy tắc:

- Ca không cần công cụ dùng `"expected_calls": []`.
- Chỉ dùng tool và argument có trong `agent.tools.get_tool_schemas()`.
- `critical_arguments` phải là tên đã có trong `required_arguments`.
- Một file phải dùng cùng một `reviewer_id`; hai file phải do hai người khác nhau thực hiện.
- Không trao đổi quyết định trước khi hoàn thành cả hai file.
- Không dùng `authoring_stratum`, nguồn gợi ý hoặc kết quả model để quyết định gold.

## Phân xử bất đồng

Chỉ tạo `adjudication.jsonl` cho các `case_id` mà hai file không khớp. Người phân xử phải khác cả hai người duyệt. Mỗi dòng có dạng:

```json
{
  "case_id": "gen_001",
  "adjudicator_id": "định-danh-người-thứ-ba",
  "adjudicator_signature": "chữ-ký-hoặc-mã-xác-nhận",
  "reason": "Lý do chọn quyết định cuối.",
  "expected_calls": []
}
```

## Kiểm gate

```bash
python -m evaluation.tool_calling.generalization review-gate \
  --candidates evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl \
  --reviews evaluation/tool_calling/authoring/generalization_v1/reviews
```

Chưa đủ hai lượt duyệt thì lệnh phải trả `status=pending_human_review`, mã thoát khác 0 và `provider_created=false`. Không được tạo split khóa hoặc gọi API trước khi gate trả `approved`.
