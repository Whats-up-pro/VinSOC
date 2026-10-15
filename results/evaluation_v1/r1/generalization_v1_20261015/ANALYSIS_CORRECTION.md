# Đính chính diễn giải gen_096

Bản REPORT.md trong lần công bố `aea0b9b2` mô tả nhầm là “thay một ký tự”. Đối chiếu chuỗi gốc cho thấy **expected hash dài 64 ký tự; native prediction dài 66 ký tự, thêm hai ký tự `e`**. Kết quả vẫn119/120, critical coverage154/155; scorer và response gốc không đổi.

Đây là đính chính phần diễn giải do người soạn báo cáo, không sửa output mô hình, gold hoặc điểm. `native_io.zip` chứa `responses/096-gen_096.json`; gold nằm trong `evaluation/tool_calling/benchmarks/generalization_v1/gen_096.json`. Original publication manifest được giữ nguyên; hash của file đính chính này nằm trong delivery manifest cuối. Không gọi lại mô hình.
