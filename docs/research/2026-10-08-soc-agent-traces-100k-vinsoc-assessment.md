# SOC-Agent-Traces-100K có bổ sung gì cho VinSOC?

Ngày nghiên cứu: 08/10/2026. VinSOC được đối chiếu tại `ec96e09ba844bbbb587cd351baa27ad53a709d1f`. Đây là nghiên cứu nguồn bên ngoài, không mở paid scope, không thay benchmark/locks, không nhập synthetic traces vào runtime hoặc demo nghiệm thu.

**Kết luận:** Có ích cho thiết kế kiểm thử hành vi agent, định dạng trajectory và nghiên cứu huấn luyện sau này. Giá trị trực tiếp cho Text-to-SQL thấp. Không giải quyết blocker 13 exact DB/worker/CI/ngân sách và không thay thế nghiệm thu, demo dữ liệu thật trước 16/10. Chưa nên huấn luyện hoặc chấm điểm VinSOC bằng nguyên bộ này.

## 1. Bộ dữ liệu thực chất là gì?

Theo dataset card, 100.000 sessions gồm alert, environment, ground truth, messages/tool calls, evidence, decision/confidence và success. Có 32 archetypes, 9 tools mô phỏng, license Apache-2.0; các tổ chức/entities và evidence là synthetic. Chính sách tham chiếu dựng traces trên backend SOC mô phỏng, không phải log người phân tích hoặc output LLM được kiểm từ hệ thống thật.

Metadata `stats.json` ghi train 89.985, validation 4.984, test 5.031; malicious 89.652 và benign 10.348. Card nói khoảng 12% flawed, nhưng stats ghi 17.200/100.000 = **17,2%**. Cần theo revision/bytes và tính lại, không sao chép con số mô tả.

Các field `decision` close/monitor/escalate mô tả kết luận của trace tổng hợp; không là quyết định human review approved/rejected/escalated của VinSOC. `success` không là kết quả chạy model VinSOC. Không dùng confidence ở đây như bằng chứng model đã được calibration.

## 2. Phạm vi kiểm chứng đã làm

- Dataset revision: `fe94a95dadbd188c2bf137a9785b82cb5f7865c2`.
- Builder revision được đọc: `d6d3c71465a1bbfa1c8101ee25a647a01e5adb59`; đọc code, không execute code tải về. Chưa chứng minh revision builder này tái tạo byte-for-byte dataset đã pin.
- Tải và kiểm SHA-256 **toàn bộ test + validation: 10.015 rows**, 14 columns. Đọc thêm 100 train đầu từ viewer; mẫu này chưa pin, không đại diện toàn train.
- Kiểm JSON, native tool-call linkage, duplicate IDs trong case, n_tool_calls/n_messages, final report/flat fields, decisive marker, citations trong tool responses, time-window diagnostic và overlap signatures giữa splits.
- 0 model calls. Chỉ đọc parquet bằng DuckDB 1.5.5 và phân tích Python trong workspace nghiên cứu; không dùng đây làm real-DB SQL/model acceptance của VinSOC.
- [Receipt đầy đủ](../../results/research/soc_agent_traces_100k/audit_receipt.json) và [notebook kiểm tra](2026-10-08-soc-agent-traces-quality-audit.ipynb) chứa phạm vi, hashes, code và limitations.

## 3. Những phát hiện quan trọng

| Phát hiện | Bằng chứng | Ảnh hưởng / xử lý tối thiểu |
|---|---|---|
| Lộ marker đáp án trong tool data — High | Test 5.029/5.031, validation 4.984/4.984 có `decisive`; tổng 10.013/10.015 = 99,98% | Model có thể chọn evidence bằng marker. Xóa label-only fields khỏi input; giữ gold ở evaluator. Không mặc định việc xóa marker đã xử lý hết leakage |
| Kết luận dựng từ ground truth — High | `policy.py::_resolve_risk_args` lấy verdict/techniques từ `ground_truth`; final report cũng lấy ground truth, template summary/actions, decisive IDs; `success = not flawed` | Đây là dữ liệu do oracle/policy dựng, không phép đo reasoning. Không lấy `success=true` làm quality stamp hoặc làm điểm VinSOC |
| Prose và JSON mâu thuẫn — High cho raw SFT | 864 test + 838 validation: prose kết luận theo template close/escalate trong khi final decision khác; cả 1.702 negative traces có mismatch theo phép kiểm template | Có thể dùng nghiên cứu negative examples có nhãn, nhưng không học toàn trace làm câu trả lời đúng. Kiểm tính nhất quán nhiều biểu diễn |
| Citation chưa thấy trong tool responses — High nếu coi successful trace là gold sạch | 80 test + 65 validation = 145 records; **99 trong đó `success=true`** | Lọc success riêng chưa đủ. Kiểm reference/visibility và tạo review queue; chưa gọi toàn prose là hallucination chỉ từ phép kiểm ID |
| Time-window mô phỏng không tương đương query thật — Medium | 3.573 test + 3.532 validation có event ngoài ±window_minutes của alert; backend dùng random subsampling, không filter timestamp chính xác | Không dùng để chứng minh time-range correctness của VinSOC. Temporal metric cần semantics riêng và nguồn kiểm được |
| Nhiều IDs lặp giữa cases — High nếu nhập bằng global ID | Chỉ 12 chuỗi evidence ID khác nhau xuất hiện trong cited IDs ở mỗi split đã đọc, cho hàng nghìn cases | Namespace theo dataset/scenario/native ID; không join `EV-0001` giữa các scenarios |
| Cấu trúc dữ liệu khá nhất quán | 0 invalid JSON, count-field mismatch, native-link mismatch hoặc final JSON parse failures trong 10.015 rows | Hữu ích học định dạng và kiểm schema; không thay chứng minh tính đúng sự kiện/nhận định |

Các tỷ lệ trên thuộc test+validation ở revision đã pin, không là kết luận đo trực tiếp toàn 100k. Kiểm citation thu thập các explicit event/evidence IDs và chuỗi `EV-*` trong tool payloads; không chấm toàn bộ ý nghĩa prose. Time diagnostic dùng ±minutes, không tự gọi đó là lỗi của một API thời gian chưa quy định như VinSOC.

Ví dụ kiểm được trong receipt: test `SCT-065533` có prose close nhưng JSON monitor; `SCT-023221` cite `EV-0009` chưa thấy ở tool responses. Đây là case tổng hợp được audit, không incident/model result VinSOC.

### Độ độc lập của splits

Không có scenario_id trùng giữa test và validation đã đọc, nhưng có 31 archetypes chung và 335 signatures chung kiểu `(archetype, ordered tool sequence)`. Builder chia ngẫu nhiên trong nhóm `(verdict, archetype)`, không giữ riêng scenario family/template cho holdout. Signature overlap không chứng minh records trùng hoặc train/test leakage hoàn toàn; nó cho thấy phép đo chủ yếu là nội suy trong cách sinh chung.

Không nên gọi test split này là độc lập khỏi templates, model pretraining hoặc incident sources. Muốn claim tổng quát hơn cần family/template/entity split được thiết kế trước, rà near-duplicates và kiểm trên nguồn thật riêng. Chưa audit toàn train nên chưa kết luận tỷ lệ overlap train/test của 100k.

### Latency, confidence và knowledge

Backend thêm `rng.randint(40, 220)` vào duration thực của lookup; confidence được lấy ngẫu nhiên từ khoảng của scenario. Không dùng các số đó làm latency/cost/calibration của VinSOC. ATT&CK/Sigma/CVE trong trace là lookup ở knowledge base tổng hợp; cần kiểm version/source/coverage trước dùng như CTI đáng tin.

## 4. Đối chiếu với hệ thống hiện tại

| Phần VinSOC | Có thể bổ sung | Không thể suy ra / thay thế |
|---|---|---|
| R1 Tool Calling | Ý tưởng scenario, lựa chọn tool theo evidence, dead-end lookup, thiếu bước và lỗi argument/ordering | 9 tools khác 3 tools R1; không ánh xạ tên 1:1 để kế thừa 22/24 hoặc tạo gold production tự động |
| R2 Text-to-SQL | Có thể dùng sau này để thiết kế câu hỏi SOC synthetic/phụ lục parser/schema diagnostics có nhãn rõ | Không có benchmark NL↔gold SQL↔schema/snapshot/result tương đương. Không bổ sung trực tiếp external64/CTU32/96; không thay 13 locked DB |
| Public orchestrator | Định dạng assistant/tool messages, link native call IDs, trajectory/dead-end/stop/error coverage | Replay trace cũ không chứng minh model VinSOC tự chọn tool/SQL hay thực thi tool/DB thật |
| EvidenceStore / verification | Namespace IDs, missing citation, evidence chưa delivered, mâu thuẫn prose–JSON, phân biệt absence với failed retrieval | `decisive` và synthetic sources không được nâng thành observed incident provenance thật; không tự sinh parent/source rows để khớp schema |
| Assessment / triage | Ví dụ false positives như backup/vulnerability scanner/maintenance; protocol đo citations/root cause/uncertainty | Verdict/calculate_risk policy không thay nhận định model thực; decision của trace không thay human review |
| SFT / model riêng | Pilot sau deadline, dữ liệu chuẩn hóa hợp schema, quality-filtered và audited | Không copy nguyên trace vào prompt đánh giá, không fine-tune rồi đánh giá trên templates gần nhau để claim holdout |

Ánh xạ cụ thể cần adapter có semantic contract: `get_process_tree` chỉ gợi ý một phần endpoint investigation; `get_surrounding_events` không chứa đầy đủ flow schema/count/bytes/protocol/source identity của CTU; `get_asset_context` là khả năng mới ngoài network query hiện tại. Không thêm cả chín tools chỉ vì dataset có chúng: mỗi tool phải có backend thật, scope, nguồn và phép đo riêng.

## 5. Có nên dùng trước báo cáo cuối khóa?

**Nên:** Ghi phần related work và rút yêu cầu kiểm chất lượng/citations/status cho runner/report đã lên kế hoạch. Bộ dữ liệu gợi ý kiểm “tool syntax → evidence → semantic correctness → workflow completion” thay một điểm cuối cùng; VinSOC đang có R1/EX/facts/human gates phù hợp để báo riêng từng tầng.

**Chưa nên:** Thêm 100k vào denominator; nhập nó làm nguồn CTU/incident thật; fine-tune model trong release hiện tại; đổi prompt/tools sau output; làm một simulator mới để thay demo cần DB thật. Những việc đó làm thay protocol và tạo scope/cost mới, không đóng blocker hiện có.

Nếu muốn tận dụng thực sự, lập track riêng **SOC_TRACE_AUX_V1** sau mốc hiện tại. Tên track là đề xuất; chưa tạo benchmark/run hoặc cấp quyền model trong lượt nghiên cứu này. Chỉ gọi nó là synthetic auxiliary diagnostics/training research, không nghiệm thu sản phẩm thật. Nếu một thử nghiệm simulator xung đột với yêu cầu cấm mock, nó cần scope được người dùng cho phép riêng.

## 6. Gói công việc đề xuất cho track riêng

| Thứ tự | Công việc | Đầu ra / gate |
|---|---|---|
| A0 | Pin revision, license/attribution/source hashes; kiểm lại toàn train nếu dùng training | Source manifest + full quality receipt; không dựa first100 để suy rộng |
| A1 | Chốt mục đích: training hoặc diagnostics; mapping capabilities tới VinSOC | Mapping schema/input/output, unsupported coverage; không rename tools thành tương đương |
| A2 | Loại oracle metadata khỏi agent input, namespace IDs, kiểm delivered citations/prose–JSON/time semantics | Sanitization/visibility/consistency report; success-filter không đủ; giữ raw immutable |
| A3 | Split theo family/template/entity; audit exact/near duplicates và coverage/class imbalance | Split lock trước output; rare families và benign coverage rõ; không claim nguồn thật |
| A4 | Human audit mẫu stratified trước chọn training/benchmark gold | Review receipt và exclusions; agent không tự phê duyệt gold/nhận định |
| A5 | Pilot nhỏ, model contracts/journal/budget riêng; compare cùng conditions | Authentic new model outputs + trace/coverage/cost report, synthetic environment được ghi rõ |
| A6 | Kiểm tác động trên benchmark VinSOC nguồn thật hợp lệ riêng trước deploy | Không rerun consumed/frozen để cứu pilot; không thay đổi release trước 16/10 khi chưa nghiệm thu |

Chỉ sau A0–A4 mới cân nhắc training. Lọc `success=true`, bỏ `decisive` và bỏ prose mâu thuẫn là bước đầu, chưa đủ biến oracle traces thành human-validated reasoning data. Nếu SFT, không gán phần prose theo template thành “chain of thought đúng”; ưu tiên hành động/observations có nguồn kiểm được và output schema.

## 7. Nguồn và tái lập

Nguồn tác giả:

- [Dataset card](https://huggingface.co/datasets/alirezaaminzadeh/soc-agent-traces-100k).
- [stats.json tại revision đã pin](https://huggingface.co/datasets/alirezaaminzadeh/soc-agent-traces-100k/blob/fe94a95dadbd188c2bf137a9785b82cb5f7865c2/stats.json).
- [Policy sinh trace](https://huggingface.co/spaces/alirezaaminzadeh/soc-agent-traces-builder/blob/d6d3c71465a1bbfa1c8101ee25a647a01e5adb59/soc_traces/policy.py): `_resolve_risk_args`, `synthesize_trace`.
- [Tool backend](https://huggingface.co/spaces/alirezaaminzadeh/soc-agent-traces-builder/blob/d6d3c71465a1bbfa1c8101ee25a647a01e5adb59/soc_traces/tools_backend.py): temporal sampling và duration.
- [Generator/split](https://huggingface.co/spaces/alirezaaminzadeh/soc-agent-traces-builder/blob/d6d3c71465a1bbfa1c8101ee25a647a01e5adb59/soc_traces/generator.py).

Đối chiếu VinSOC: `agent/tools.py`, `agent/orchestrator.py`, `agent/network_query_policy.py`, `skills/network_query_skill.py`, schemas InvestigationCase/query, `winner_lock.json`, kế hoạch tích hợp và bản remaining-work 08/10. Không sửa các files đó trong nghiên cứu này.

Notebook tải các files public cố định, kiểm digest rồi chạy audit; cần DuckDB 1.5.5. Train viewer sample không tải tự động vì chưa pin. Script audit và cell audit của notebook đã thực chạy trên bytes đã tải; kết quả test/validation trùng receipt. Notebook giữ source hashes; chưa chạy toàn notebook từ đầu trong môi trường sạch. Bộ này không cung cấp raw runtime binaries VinSOC hoặc gỡ gate paid.
