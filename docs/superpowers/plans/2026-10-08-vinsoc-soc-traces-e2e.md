# VinSOC SOC Traces E2E — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Theo chỉ thị người dùng: một người thực hiện trực tiếp trên `master`; không branch/PR/subagents.

**Goal:** Nhận cảnh báo/IOC, chạy điều tra bằng model và tools đọc corpus, xuất báo cáo đầy đủ có bằng chứng; so sánh S0/S1 trên 64 cảnh báo trước 16/10/2026.

**Architecture:** Dùng chính `InvestigationOrchestrator` với entrypoint/policy SOC riêng, hai tools truy vấn DuckDB read-only, EvidenceStore và final-report schema riêng. Agent chỉ nhận input/observations đã làm sạch; nhãn/reference reports ở evaluator. Release SOC có journal và budget riêng; JSON/HTML/Markdown đọc receipts bất biến.

**Tech Stack:** Python 3.11/3.12, DuckDB 1.5.5, OpenAI SDK 2.8.1, httpx 0.28.1, jsonschema, pytest và GitHub Actions. Không thêm framework hoặc dependency mới cho bản đầu.

**Spec:** [2026-10-08-vinsoc-soc-traces-e2e-design.md](../specs/2026-10-08-vinsoc-soc-traces-e2e-design.md), người dùng đã duyệt ngày 08/10/2026. Đọc cả spec và plan, không chỉ phần checklist.

## Global Constraints

- Tạm hoãn Text-to-SQL T0–T11/D1–D10; không sửa nguồn/khóa/gold/prompts/scorers/kết quả lịch sử để phục vụ SOC.
- Nguồn `alirezaaminzadeh/soc-agent-traces-100k`, revision `fe94a95dadbd188c2bf137a9785b82cb5f7865c2`, Apache-2.0; `data_origin=synthetic`. Không gọi đây là incident SOC thật hoặc family holdout.
- Test pool 5.031, validation 4.984 chỉ kiểm thiết kế offline; không dùng train hoặc dataset viewer chưa pin.
- Tập chính 64 = 32 malicious + 32 benign; hai conditions S0/S1, cùng IDs/input/model. Không success-filter hoặc chọn theo model output.
- Human audit nguồn ít nhất 12 = 6 mỗi label trước freeze; bốn demo IDs khóa trước output; review thật tách technical completion.
- Model `gpt-4.1-mini-2025-04-14`, temperature=0, max_completion_tokens=2000; SDK chính thức, max_retries=0, không fallback/retry.
- S0 tối đa một request/case; S1 tối đa 5 tool calls và 6 requests/case; suite tối đa 448 requests. Chưa có quyền/ngân sách API SOC.
- Max request 128.000 UTF-8 bytes, max messages 16, max tool payload 20.000 UTF-8 bytes, max 20 rows/tool; không parallel tools.
- Tools không nhận SQL/scenario_id do model chọn; trusted case scope do ứng dụng cấp. Thiếu/mơ hồ IOC mapping chặn trước SDK.
- Không MockProvider/mock-data hooks, canned report, scripted verdict/risk, tự duyệt, oracle metadata hoặc transcript replay trong nghiệm thu/demo.
- Không fake SDK/provider response để kiểm positive live workflow; tests parser/boundaries có thể dùng input nhỏ được ghi rõ là unit tests, không lưu thành experiment output.
- Không tính latency/confidence của bộ sinh làm số đo mới. Không claim prose correctness từ schema/citation-ID checks.
- Một người ghi `master`; mỗi mốc commit/push và CI đúng SHA trên 3.11/3.12. Raw parquet/DuckDB/private gates/journals/keys ngoài Git public.
- Mất usage/crash/timeout/unknown cost dừng release, giữ partial; không mở output/window/key khác để cứu lượt chạy.

## Review Focus

1. Native IDs lặp hoặc xung đột giữa cases: không cross-case join/overwrite; P0/P2 kiểm namespace và conflicts.
2. Unicode, null timestamp và giới hạn bytes: UTC half-open range, không đổi null thành thời gian giả hoặc cắt row; P2/P4 kiểm bytes thực.
3. IOC thiếu hoặc map nhiều scenarios: chặn trước provider, không tự chọn incident; P5 kiểm hai nhánh.
4. Crash sau reserve/response và hai tiến trình cùng claim: lưu exposure/raw output, không retry; P4 kiểm persistence liên process.
5. Receipt/review/HTML bị sửa hoặc chứa text HTML: hash binding, escape, trạng thái không nâng và nội dung không bị cắt; P7 kiểm tất cả.

## Điểm tiếp tục và cách kiểm

HEAD trước lập plan: `7f7349e94a2f338f456d801657780abe7a25abd3`, tracked tree sạch. CI `37754264616` success, 1.150 passed/2 skipped mỗi phiên bản; CI này chỉ là kiểm lịch sử, chưa nghiệm thu SOC mới.

Môi trường hiện có `.venv/bin/python` không dùng được; site-packages còn DuckDB 1.5.5. Khi triển khai, tạo lại môi trường từ requirements hiện có, pin DuckDB 1.5.5 cho đường SOC, ghi actual versions; không gọi test PASS nếu môi trường chưa chạy được. Các lệnh dưới dùng `python` của môi trường đã xác minh.

Mỗi task theo chu kỳ RED → minimal implementation → GREEN → commit/push/exact-SHA CI. Nếu RED là lỗi setup/dependency, sửa setup trước; không coi đó là lỗi chức năng. Mỗi task stage đúng các files kê dưới và receipt mốc, không `git add .`; commit message dùng `feat(soc): ...` hoặc `test(soc): ...` phù hợp. CI pending/failed phải ghi rõ, không đánh dấu task hoàn tất.

Artifacts công khai mới: `results/evaluation_v1/soc_traces_v1/`; dữ liệu lớn/cache riêng: `data/soc_traces_v1/` ngoài Git. Private state: `~/.vinsoc/live-windows/soc-traces-20261008-v1/`; không tạo private approval/account flags để pass gate. Các paths này phải được preflight canonicalize.

## Bản đồ files và trách nhiệm

| File mới / file sửa | Trách nhiệm |
|---|---|
| `vinsoc_data/soc_corpus.py` | Import/sanitize, provenance, read-only repository và IOC index |
| `scripts/prepare_soc_traces.py` | Fetch pin/verify, import, xuất receipts và restore corpus, không API |
| `evaluation/soc_traces_v1/{__init__,dataset}.py` | Candidate/selection/audit/demo inventories, evaluator labels riêng |
| `skills/soc_corpus_skill.py` | `SocCorpusContext`, hai tools, limits và delivered rows |
| `agent/soc_investigation_policy.py` | Tool schemas, prompt, final-report/citation validation |
| `schemas/{soc_investigation_report,soc_investigation_case}.json` | Schema mới, không nới schema lịch sử |
| `evaluation/soc_traces_v1/{release,accounting}.py` | Release hash/gates, canonical ledger và guarded SDK transport |
| `agent/soc_provider.py` | `SocProvider`, LLMResponse adapter và request budgets S0/S1 |
| sửa `agent/orchestrator.py` | Public entrypoint và SOC lifecycle nhiều bước; giữ nhánh cũ |
| `evaluation/soc_traces_v1/runner.py`, `scripts/run_soc_traces.py` | Preflight/live suite và durable case checkpoints |
| `evaluation/soc_traces_v1/reporting.py` | Scores/coverage/paired status và report rendering offline |
| `scripts/{render_soc_report,review_soc_case}.py`, sửa `cli/main.py` | CLI đầu vào/viewer/render và review thật, không replay API |
| sửa `.github/workflows/ci.yml` | Restore corpus pinned + required offline checks không key |
| `docs/evaluation/2026-10-08-soc-traces-runbook.md` | Hướng dẫn nhập cảnh báo/IOC, chạy scope đã cấp, đọc artifacts |

## Task 0: P0 — Nhập corpus có provenance, không đáp án

**Files:** Tạo `vinsoc_data/soc_corpus.py`, `scripts/prepare_soc_traces.py`, `evaluation/soc_traces_v1/__init__.py`, `evaluation/soc_traces_v1/source_manifest.json`, `tests/test_soc_corpus.py`. Bàn giao D-SOC1.

**Interfaces:** `verify_sources(source_dir: Path, manifest: dict) -> dict`; `import_corpus(source_dir: Path, database: Path, *, manifest: dict) -> dict`; `SocCorpusRepository(database: Path, *, expected_sha256: str)`; `repository.input_for(scenario_id: str) -> dict`; `repository.records(scenario_id: str, resource: str) -> list[dict]`; `repository.resolve_ioc(value: str, indicator_type: str) -> list[str]`.

- [x] Viết RED `test_pin_and_digest_required`, `test_no_oracle_fields`, `test_cross_case_native_id`, `test_conflicting_native_id_quarantined`. Assertions: sai digest → ValueError trước import; DB không có ground_truth/success/decision/verdict/confidence/archetype/decisive; cùng EV ID hai scenarios → hai source IDs; conflicting key → quarantine, không overwrite.
- [x] Chạy `python -m pytest tests/test_soc_corpus.py -q`; xác nhận FAIL do interfaces chưa có.
- [x] Implement importer chỉ bốn payload: events/tree/asset/related alerts, allowlist đầu vào như spec. Field profile được kiểm toàn 10.015 rows; whitelist events là mọi keys sau, trừ `decisive`: `access_mask, account, action, app, auth_package, binary_path, bytes_in, bytes_out, channel, cmdline, dst_domain, dst_ip, dst_port, duration_min, encryption, event_id, extension, file_path, forward_to, host, ip, label_length, location, logon_type, message, package, parent_process, path, process, query_type, registry_key, renamed_files, rule_name, sender, service, service_name, share, signed, source, src_host, src_ip, target_process, task_name, timestamp, url, user, user_agent, value`. Tree: cmdline/hash_sha256/image/parent_image/path/pid/signed/user. Asset: criticality/edr_installed/hostname/internet_exposed/ip/last_patch_days/os/owner/role/vlan. Related alerts: alert_id/host/severity/status/timestamp/title/user. Scalar/list types theo profile; nested/unexpected object phải reject/quarantine với source pointer, không truyền nguyên object.
- [x] Lưu bảng `case_inputs`, `observations`, `source_availability`, `ioc_index`, `corpus_metadata`; không bảng gold. Source record gồm scenario/resource/native key + revision/pointer/hash; provenance synthetic. IOC index chỉ literal IPv4/domain/hash/URL từ allowlisted fields, không ground truth. Process host chỉ từ payload container; missing timestamp null. Store dedupe logical keys và conflict receipts.
- [x] Manifest pin test digest `9ef309da7ad04f173d89a5f8da238f20db4051b92514531667b30c042da7bd1a`, validation `94cd7987fe3064cd0933d8fabed75d517e955f8faa8723ac07c9b01446cdfcf7`; source URLs là `https://huggingface.co/datasets/alirezaaminzadeh/soc-agent-traces-100k/resolve/fe94a95dadbd188c2bf137a9785b82cb5f7865c2/data/test-00000-of-00001.parquet` và cùng prefix + `validation-00000-of-00001.parquet`. Reuse raw cache khi digest match. CLI `prepare_soc_traces.py --source-dir <dir> --output-dir <dir>` xuất corpus, digest/logical hash, import/quarantine receipt và license attribution; không execute builder.
- [x] Chạy GREEN tests trên pinned parquet thực; kiểm 5.031/4.984 input records hoặc exclusions đầy đủ, query read-only, source pointers resolve, không oracle fields. Ghi `corpus_receipt.json`; commit/push/CI.

## Task 1: P1 — Chọn 64 cases, audit nguồn và khóa bốn demo

**Files:** Tạo `evaluation/soc_traces_v1/dataset.py`, `tests/test_soc_dataset.py`; dùng artifacts P0. Bàn giao D-SOC2; thiếu review không chặn P2–P7 offline.

**Interfaces:** `build_candidates(source_dir: Path, repository: SocCorpusRepository) -> list[dict]` ở evaluator; `select_inventory(candidates: list[dict], *, exclusions: list[dict]) -> dict`; `select_audit(inventory: dict) -> list[str]`; `select_demo(inventory: dict, repository: SocCorpusRepository) -> list[str]`; `validate_source_reviews(reviews: list[dict], *, inventory: dict) -> dict`.

- [x] RED `test_selection_is_balanced_and_deterministic`, `test_no_success_filter`, `test_insufficient_quota_blocks`, `test_demo_is_subset_and_missing_context_is_natural`. Assertions: 64 IDs unique/32 mỗi label; shuffle candidate order không đổi IDs; success flip không đổi selection; thiếu quota → BLOCKED_DATASET_COVERAGE; demo4 distinct là subset, không mutate corpus.
- [x] Chạy `python -m pytest tests/test_soc_dataset.py -q` và đọc FAIL chức năng.
- [x] Implement test-only eligible pool dựa observations/provenance/schema đã import. Round-robin lexical family trong từng label, sort SHA-256(`20261008|scenario_id`) rồi scenario_id; exact/near-duplicate normalized payload hashes được báo và không chọn exact duplicates. Public agreement gold ở evaluator file riêng; không agent-facing input. Không dùng reference report/decision/success để xếp hạng.
- [x] Chọn audit6/label bằng thứ tự selected candidates cố định; demo lần lượt hai malicious khác family, một benign, một case distinct có context tự nhiên unavailable, theo selected order. Xuất `inventory.json`, evaluator `gold.json`, `source_audit_queue.json`, `demo_selection.json`, `selection_receipt.json`; receipt chưa review ghi pending, không tự ký.
- [ ] Người thật nhập analyst/UTC/scenario/source hash/label supportability/decision/rationale cho ít nhất12. Ambiguous exclusions phải có phiếu thật; reselect cùng thuật toán trước model output, audit final inventory đủ quota. Agent chỉ validate/read reviews; không đánh dấu approved hộ người dùng.
- [ ] GREEN deterministic tests và receipt đầy đủ; commit/push/CI. Selection chỉ frozen khi source reviews PASS; pending không PASS.


## Task 2: P2 — Hai tools truy vấn corpus và scope

**Files:** Tạo `skills/soc_corpus_skill.py`, `tests/test_soc_corpus_tools.py`; mở rộng repository P0 cho typed filtering. Bàn giao phần tool D-SOC3.

**Interfaces:** Frozen `SocCorpusContext(repository, scenario_id: str, condition: str, source_revision: str, corpus_sha256: str)`; `SocCorpusSkill(context: SocCorpusContext)`; `search_events(*, host=None, user=None, source=None, query=None, start=None, end=None, limit=20) -> dict`; `get_context(*, resource: str, host=None, user=None, limit=20) -> dict`. Kết quả chuẩn: rows/matched_count/returned_count/truncated/availability/limitations; row có source_record_id/data/provenance/observed_at.

- [x] RED `test_half_open_utc_and_null_times`, `test_filters_never_cross_scope`, `test_unavailable_differs_from_no_match`, `test_utf8_payload_limit`, `test_unsupported_filter_rejected`. Assertions: start được lấy/end loại, naive/invalid/reversed timestamps bị từ chối; scope leak → ValueError; unavailable != no_match; encoded payload <=20000 và <=20 rows; single oversized row → lỗi, không cắt string.
- [x] Chạy `python -m pytest tests/test_soc_corpus_tools.py -q`; xác minh RED.
- [x] Implement parameterized SQL cố định phía tool, không SQL model. Event filters equality host/user/source, substring literal query, UTC half-open; timestamps null không match time range. Sort timestamp rồi source ID. Limit integer1..20, bool không là int hợp lệ. Context resource enum process_tree/asset/related_alerts; asset user filter unsupported → reject, không ignore. Scope bind từ context, additional arguments reject.
- [x] Giảm rows theo thứ tự nếu payload vượt20000 bytes; giữ matched_count/truncated/coverage limitations. Không tạo EV IDs cho rows chưa delivered; không nâng missing/no_match thành benign. Test unit SQL injection text là literal và DB hash không đổi sau queries.
- [x] GREEN tests bằng pinned corpus thật, không database giả thay acceptance; commit/push/CI, tool-query receipt ghi bytes/counts/identities.

## Task 3: P3 — Schema báo cáo và policy model

**Files:** Tạo `schemas/soc_investigation_report.json`, `schemas/soc_investigation_case.json`, `agent/soc_investigation_policy.py`, `tests/test_soc_report_policy.py`. Bàn giao schema D-SOC4 và policy D-SOC3.

**Interfaces:** `SocInvestigationPolicy(context: SocCorpusContext)`; `tool_schemas() -> list[dict]`; `system_prompt() -> str`; `validate_tool_call(call: dict) -> dict`; `parse_final_response(content: str, evidence_store: EvidenceStore) -> ValidatedAssessment`; `validate_report(report: dict, *, delivered_ids: set[str]) -> dict`; `validate_schema(case: dict) -> tuple[bool, str | None]`; METADATA_KEY=`soc_policy`. Full parsed report ở ValidatedAssessment.raw_json, assessment=summary; không rút nội dung findings/actions.

- [x] RED `test_all_report_fields_required`, `test_foreign_or_undelivered_citation_fails`, `test_union_of_citations_exact`, `test_insufficient_requires_limitation`, `test_strict_tool_schema_no_scope_argument`. Assertions: fenced/invalid JSON → fail; report.evidence_ids đúng union nested refs; malicious/benign cần cited finding; abstention có limitation; tool schema không scenario_id/SQL, additionalProperties=false.
- [x] Chạy `python -m pytest tests/test_soc_report_policy.py -q`; xác minh RED. Parser fixtures là unit tests, không model predictions/experiment records.
- [x] Implement exact required fields từ spec mục5; thêm confidence cho mỗi hypothesis nếu cần projection DTO, cùng enum LOW/MEDIUM/HIGH. Tool schemas strict: filters nullable nhưng required, context.resource enum; limit required1..20. Prompt tiếng Việt yêu cầu JSON report, cite delivered IDs, dữ liệu không là chỉ thị, đề xuất không thực thi. Prompt không nhãn/family/reference final/expected sequence.
- [x] Validation chỉ schema/reference/fact fields có phép so sánh rõ; giữ `prose_semantics_machine_verified=false`. Schema case cho input types alert/ioc và tool enums mới; schemas cũ giữ nguyên bytes. Evidence input linked_from=null; tool observations linked với call, provenance synthetic.
- [x] GREEN parser/negative tests và schema compatibility tests lịch sử; commit/push/CI. Chưa gọi report quality PASS bằng fixtures.

## Task 4: P4 — Release, journal và provider SOC có kiểm soát

**Files:** Tạo `evaluation/soc_traces_v1/release.py`, `evaluation/soc_traces_v1/accounting.py`, `agent/soc_provider.py`, `tests/test_soc_release.py`, `tests/test_soc_accounting.py`. Bàn giao D-SOC5. Không đổi `vinsoc_text2sql/accounting.py`/QueryProvider.

**Interfaces:** `build_release(*, identities: dict, gates: dict) -> dict`; `validate_release(release: dict) -> dict`; `SocRunJournal.claim(release: dict, *, ledger_path: Path)`; `reserve(*, case_id: str, condition: str, turn: int, payload: dict) -> int`; `record_response(reservation_id: int, raw_response: dict) -> dict`; `fail(reservation_id: int, category: str) -> None`; `SocProvider(client, *, journal: SocRunJournal, context: SocCorpusContext)` implements LLMProvider; `ensure_case_capacity(case_id: str, condition: str) -> None`.

- [x] RED `test_missing_gate_before_client`, `test_old_scope_rejected`, `test_request_contract_and_bytes`, `test_claim_race_and_crash_consumed`, `test_response_persisted_before_validation`. Assertions: missing reviews/CI/pricing/account/budget → blocked/client_created=false; old release/window rejected; >128000 UTF8 bytes/>16 messages/wrong model/caps fail before SDK; two processes only one claim; crash reserve keeps unknown; invalid usage raw response vẫn durable, terminal.
- [x] Chạy `python -m pytest tests/test_soc_release.py tests/test_soc_accounting.py -q`; xác minh RED bằng pure metadata/persistence checks, không fake SDK để giả live pass.
- [x] Implement source/import/selection+reviews/schema/scorer/prompt/runtime identities và full closure hashes, exact-SHA CI binding. Canonical window `soc-traces-20261008-v1`, ledger path đầu plan; condition S0/S1 + 64 IDs + caps1/6/448. Release hash canonical; private account authorization phải có chứng cứ người dùng/operator thật, không bool tự khai. Không claim/instantiate SDK lúc offline preflight.
- [x] Claim bằng exclusive atomic file + fsync; reserve cả suite/case/request trước transmission. Worst-case input bound theo actual serialized UTF8 bytes + framing reserve được xác minh, output2000 và pricing hiện hành đã kiểm; missing bound → blocked. Không suy giá mới từ constants cũ. Lưu event IDs/case/condition/turn/request hash/reserve/response/usage/model/request ID/latency.
- [x] Provider chỉ official SDK OpenAI2.8.1, official base_url, max_retries=0, một model/temp/cap; dùng LLMResponse shape hiện có, preserve raw bytes trước JSON arguments parse. Missing usage/model mismatch/finish_reason không stop/tool_calls → terminal, unknown exposure không0. S0 một request không tools; S1 request6 không tools; hết capacity không gọi thêm.
- [x] GREEN boundary/persistence tests, code review inline guard paths và compile; commit/push/CI. Positive official transport còn pending P9.

## Task 5: P5 — Public entrypoint cảnh báo/IOC và điều tra nhiều bước

**Files:** Sửa `agent/orchestrator.py`; tạo `tests/test_soc_orchestrator.py`; dùng P0–P4. Bàn giao public runtime D-SOC3.

**Interfaces:** `InvestigationOrchestrator.investigate_alert(alert: dict, *, soc_context: SocCorpusContext) -> InvestigationCase`; intake dict=`{kind: 'alert', alert: <allowlisted source alert>}` hoặc `{kind: 'ioc', value: str, indicator_type: str}`. Provider/context/scenario/condition/source identities phải khớp release. JSON report đầy đủ nằm `case.metadata['soc_report']`; trace/report/technical errors lưu riêng, không thay phần raw.

- [x] RED `test_ioc_missing_or_ambiguous_blocks_without_calls`, `test_scope_provider_mismatch_rejected`, `test_soc_does_not_use_legacy_triage_or_analysis`, `test_only_delivered_evidence_registered`. Assertions: mapping0/>1 chặn trước provider; provider/context mismatch fail; mode SOC không gọi `_analyze_evidence`/benign auto-close/final fallback; source rows không delivered không vào EvidenceStore.
- [x] Chạy `python -m pytest tests/test_soc_orchestrator.py -q`; RED tests intake/capability checks không fake model final outputs. Positive workflow chỉ xác minh bằng authentic outputs P9.
- [x] Implement nhánh SOC riêng trong public orchestrator, không rewrite loop network/query cũ. Dùng cùng case/evidence/lifecycle primitives; input evidence ở cả conditions, state triage=scope validated không verdict. Scoped dispatch chỉ hai SocCorpusSkill tools; actual native tool_call_id ghi trong trace/provenance và assistant/tool messages, không bịa native ID thiếu.
- [x] SOC loop cho model dừng sớm/abstain; tối đa một tool/turn, năm tool/sáu requests. After fifth tool dùng final-only request; S0 final-only một request. Multiple tools, invalid args/report/no final → failed/partial giữ raw; no semantic fallback. Khi tool errors an toàn, lưu error/status và evidence visibility đúng; unknown paid exposure terminal toàn suite.
- [x] Dùng policy-specific schema thay schema legacy, projection hypotheses/risk/confidence chỉ từ validated model report; full report không cắt. Final valid → awaiting_human, ScriptedHumanReviewGate rejected. Human request-more-evidence không mở lượt API mới.
- [x] GREEN offline intake/visibility/state boundary tests; chạy `python -m pytest tests/test_soc_orchestrator.py tests/test_network_e2e_policy.py tests/test_network_query_policy.py tests/test_schema_contracts.py -q`; commit/push/CI. Ghi rõ live multi-turn chưa nghiệm thu.

## Task 6: P6 — Runner/preflight và checkpoint cả 128 records

**Files:** Tạo `evaluation/soc_traces_v1/runner.py`, `scripts/run_soc_traces.py`, `tests/test_soc_runner.py`. Bàn giao D-SOC5/D-SOC6 contract, chưa predictions.

**Interfaces:** `preflight(*, source_dir: Path, corpus: Path, inventory: Path, reviews: Path, private_dir: Path) -> dict`; `run_live(*, release_path: Path, output_dir: Path, private_dir: Path) -> dict`; `checkpoint_case(*, case_id: str, condition: str, receipt: dict, output_dir: Path) -> Path`. CLI `--preflight` hoặc `--live --release <path>` mutually exclusive, không default live.

- [x] RED `test_preflight_zero_calls`, `test_inventory_or_source_mutation_blocks`, `test_records_preserve_planned_ids`, `test_partial_after_failure_persists`, `test_output_change_cannot_reopen_scope`. Assertions: gate thiếu attempts=responses=0/client=false; identity mismatch fail trước claim; status inventory đủ128 planned records, missing không biến completed; failure giữ checkpoints; output path không identity paid scope.
- [x] Chạy `python -m pytest tests/test_soc_runner.py -q`; xác minh RED. Không tạo128 fake predictions để test reporting.
- [x] Implement preflight mọi gate P4, serializer leakage scan trên input/tool-visible corpus, runtime hashes và no MockProvider/hooks. Kiểm serialized gold/reference object/sentinel, không chặn từ verdict/benign/malicious hợp lệ trong schema prompt hoặc alert text. Không truyền evaluator gold/family vào public context/prompt. Freeze execution order theo inventory, mỗi case S0 rồi S1; không chọn order bằng model output.
- [x] Live reserve toàn suite, gọi đúng public `investigate_alert` cho cả conditions; private raw SDK journal, sanitized public receipt allowlist. Atomic/fsync checkpoint sau mỗi response và case/terminal; summary planned/completed/failed/not_run/received/unknowncost. Copy key/private gate/journal ra public bị chặn.
- [x] Parse/input failure ghi case failed không retry; transport/unknowncost/budget/crash terminal toàn suite; output path mới không bypass consumed ledger. CLI nonzero khi blocked/failed/partial, không ghi completed dù process chạy xong.
- [x] GREEN negative/preflight/checkpoint tests và preservation receipt; commit/push/CI. D-SOC6 live còn pending P9.

## Task 7: P7 — Phép đo, báo cáo đầy đủ, CLI và review thật

**Files:** Tạo `evaluation/soc_traces_v1/reporting.py`, `scripts/render_soc_report.py`, `scripts/review_soc_case.py`, `docs/evaluation/2026-10-08-soc-traces-runbook.md`, `tests/test_soc_reporting.py`; sửa `cli/main.py` thêm subcommands SOC, giữ output legacy. Bàn giao D-SOC4/D-SOC7/D-SOC8 tooling.

**Interfaces:** `score_record(receipt: dict, gold: dict) -> dict`; `build_suite_report(inventory: dict, records: list[dict], reviews: list[dict]) -> dict`; `render_case(receipt_path: Path, output_dir: Path, *, review_path: Path | None = None) -> dict`; `validate_review(review: dict, *, receipt: dict) -> dict`. CLI `soc --input <json> --case-id <locked-id> --condition S0|S1 --release <path>` chỉ lựa chọn/kiểm input cho suite đã cấp, không mở case paid riêng; `soc-report --receipt <path> --output <dir>` offline.

- [x] RED `test_missing_failed_abstained_remain_denominator`, `test_review_hash_binding`, `test_render_full_unicode_and_escape`, `test_no_output_no_success_report`, `test_input_only_citations_separate`. Assertions: planned64/condition luôn giữ; missing/failed/insufficient không correct; foreign/changed receipt review rejected; >2000-character assessment không cắt; HTML escaped; pending không approved; S0 tool citation metric NA.
- [x] Chạy `python -m pytest tests/test_soc_reporting.py -q`; RED parsing/escaping tests dùng unit strings rõ nguồn, không receipts giả thành experiment output.
- [x] Implement agreement với synthetic labels, confusion predictions3classes, malicious/benign precision/recall/F1 với abstentions là FN, macro families/case coverage và paired64 wins/loss/tie/incomplete. Input/tool citations tách riêng; S1 technical completion khác correct/approved; no citations NA; unknown cost giữ null/flag. Không interval mặc định khi sample/paired coverage chưa đủ.
- [x] Renderer JSON/HTML/Markdown từ cùng receipt, full report mọi fields spec5; trace/bằng chứng/source pointer/duration/model/tokens/cost/status/review hiển thị. Escape text/HTML, Markdown content không thực thi HTML nguồn. Missing final chỉ status + input/errors; không content điền sẵn. Missing/failed demo IDs vẫn hiện đủ bốn rows.
- [x] Review CLI yêu cầu người thật nhập analyst/decision/rationale/UTC, ghi receipt hash; không auto-input, không script approve, base receipt bất biến. Ghi technical-invalid không thành approved completion. Runbook có cách nhận input alert/IOC, scope mapping, suite run, xem bốn demos và hạn chế synthetic/public/template/pretraining.
- [x] GREEN offline negative/aggregation tests; full positive rendering/scoring trên authentic outputs còn pending P9, không gắn fixtures như bằng chứng; commit/push/CI.

## Task 8: P8 — CI corpus, kiểm ngoại tuyến và freeze trước API

**Files:** Sửa `.github/workflows/ci.yml`; tạo `tests/test_soc_corpus_acceptance.py`; dùng prepare CLI P0, preflight P6. Bàn giao D-SOC1–D-SOC5 readiness.

**Interfaces:** CLI P0 thêm `--fetch` tải hai nguồn pin, `--verify-only`; test acceptance nhận `VINSOC_SOC_SOURCE_DIR`, `VINSOC_SOC_CORPUS_PATH`, `VINSOC_SOC_REQUIRED=1`. Không API key cho corpus jobs.

- [x] RED `test_required_corpus_absence_fails`, `test_source_pointer_and_digest_acceptance`, `test_real_scoped_tool_queries`: required=1 thiếu data fail, không skip; nguồn pointer/hash resolve; thực queries P2 trên imported corpus, cross-case/time/bytes checks PASS.
- [x] Chạy RED bằng required flag và source path chưa có trong thư mục test riêng; không xóa dữ liệu đã tải.
- [x] CI matrix3.11/3.12 install requirements rồi pin DuckDB1.5.5; fetch/import public pinned corpus trước full suite, download/hash failure fail job. Không reuse artifact không digest. Source cache nếu có phải identity key revision+digests; output artifact receipts theo exact implementation SHA, không keys/labels truyền vào runtime.
- [x] Chạy GREEN required corpus tests/full suite/compile/diff/preservation. Restore script sản sinh DB theo import protocol mới và ghi binary/logical hashes; đây là corpus mới, không thay13 exact DB lịch sử. SDK positive path vẫn pending P9.
- [ ] Sau P0–P7 tests, source-human reviews và demo selection PASS, freeze importer/tool/schema/prompt/policy/provider/accounting/runner/report/CLI/scorer/source/selection/environment closure. Runtime source không tự bind SHA của receipt chứa chính digest để gây vòng; locks ở evaluator/private release, exact CI run bind implementation commit SHA.
- [ ] Commit/push/CI đúng final implementation SHA; preflight trước SDK attempts=0. Pending account/pricing/budget phải hiện BLOCKED, không ghi ready-to-live chỉ vì CI green.


## Task 9: P9 — Release được cấp, chạy một lượt và bàn giao thật

**Files/đầu ra:** Không sửa code sau freeze. Artifacts mới trong `results/evaluation_v1/soc_traces_v1/`; raw/private ngoài Git. Bàn giao D-SOC5–D-SOC8 thực.

**Consumes:** Release P4/P8, `run_live` P6, inventory/gold/demo locks P1, renderer/scorer P7. **Produces:** Model outputs/receipts128 planned slots, report so sánh, bốn demo JSON/HTML/Markdown, review receipts thật hoặc awaiting_human và final handoff.

- [ ] Operator/người dùng đối soát account/prior exposure/canonical window và cấp ngân sách SOC riêng. Xác minh pricing/availability chính thức cho model pin, reserve cả448 worst-case requests theo contract; không gọi model để thử khi chưa release. Budget thiếu chỉ blocked, không tự giảm64/đổi model/cap.
- [ ] `python scripts/run_soc_traces.py --preflight --source-dir <source> --corpus <corpus> --inventory <inventory> --reviews <reviews> --private-dir <private>`: tất cả gate PASS, attempts=responses=0/client=false; gate thiếu thì lưu receipt và tiếp tục phần offline/review còn làm được.
- [ ] `python scripts/run_soc_traces.py --live --release <approved-release> --output <output> --private-dir <private>` đúng một lần. Đọc checkpoint/ledger thực trước mọi resume; consumed không rerun. Live chặn khi full case/suite capacity thiếu. Không đổi input/ID/output để cứu lỗi.
- [ ] Chấm offline trên records thật + gold evaluator, đủ planned128 slots/status; kiểm actual model/usage/native IDs/tool queries/input hashes/citations. Parse/final failures không sửa output để pass; no-final không có report thành công. Paired64 output hợp lệ thì báo metrics, incomplete giữ incomplete.
- [ ] Render cả suite và bốn demo IDs khóa trước output; người thật rà ngữ nghĩa/approve/reject/escalate. Thiếu review bàn giao awaiting_human, không tự xử lý hộ. Arbitrary IOC ngoài scope chưa hỗ trợ phải hiện blocked/unsupported trước API.
- [ ] Commit/push sanitized receipts/report/runbook updates, CI đúng SHA. Handoff ghi implementation SHA/CI identity và artifact commit SHA riêng; không sửa runtime frozen. Nêu phần đạt/lỗi/chạy dở/chờ duyệt/blocked, cost known/unknown và synthetic limits. Chỉ claim nghiệm thu tương ứng bằng evidence thực.

## Kiểm phủ đặc tả và lịch mục tiêu

| Yêu cầu / đầu ra | Task sở hữu | Gate còn cần người thật/live |
|---|---|---|
| Nguồn sạch/provenance D-SOC1 | P0, P2, P8 | Pinned source và required CI |
| Tập64/demo/audit D-SOC2 | P1 | Audit12 nguồn và bốn IDs trước output |
| Public multi-turn/runtime D-SOC3 | P2–P5 | Positive official model/tool trace P9 |
| Báo cáo model đầy đủ D-SOC4 | P3, P5, P7 | Authentic final + full rendering P9 |
| Paid gates/journal D-SOC5 | P4, P6, P8 | Account/pricing/budget SOC riêng |
| Records thật D-SOC6 | P6, P9 | Một lượt đúng release, không retry |
| Phép đo D-SOC7 | P7, P9 | Outputs S0/S1 và coverage thực |
| Demo/review D-SOC8 | P1, P7, P9 | Bốn reports và người thật rà |

Mục tiêu lịch: 08–09/10 P0–P2; 10–11/10 P3–P6; 12–13/10 P7–P8 và human source audit; 14–15/10 P9 khi đủ gates. Đây là thứ tự mục tiêu, không cam kết vượt gate; nếu chậm, bàn giao rõ phần chưa chạy trước16/10. Không dùng lịch để mở thêm scope/rescue run.

## Execution cursor

- [x] Thiết kế trong hội thoại và đặc tả được người dùng duyệt.
- [x] Đối chiếu mã/CI/source audit; lập kế hoạch và tự rà coverage/interfaces/limits/preservation.
- [x] Người dùng duyệt kế hoạch và giao toàn quyền triển khai ngày 08/10/2026; phương thức đã chọn giữ nguyên: triển khai trực tiếp, một người trên master.
- [x] P0–P7 đã triển khai và CI đúng từng commit trên Python 3.11/3.12; xem bảng dưới. Các checkbox kỹ thuật không đồng nghĩa nghiệm thu live.
- [ ] P1 human audit nguồn: 0/12; inventory chưa frozen. Gói 12 hồ sơ đã có ở `results/evaluation_v1/soc_traces_v1/source_audit_pack.json`.
- [ ] P8: CI required corpus đã soạn; đang chốt full suite/CI final implementation. Freeze chưa được cấp.
- [ ] P9: chưa chạy; SDK client chưa tạo, inference calls/responses/cost mới = 0. Chưa có 128 outputs, bốn báo cáo model hoặc human review demo thật.

| Mốc kỹ thuật | Implementation commit | CI run / kết luận |
|---|---|---|
| P0 + pin môi trường | `de052bbecbc8350ef4beffbd568d81f17931a499` | 37758770922 / success |
| P1 selection ngoại tuyến | `1c66ee250a46eaf46f8c52796de5eab37c7e48fd` | 37758985847 / success |
| P2 tools | `1929687a6b7afdf5a20942a2dc3f65a9623de076` | 37759268310 / success |
| P3 policy/schema | `d1fc757b3062fdb777b4b3b2f23b729b70fa924f` | 37759636567 / success |
| P4 journal/provider | `3db85c3b8abc34bab5429cc77335425c072e7001` | 37760351694 / success |
| P5 public orchestrator | `ec9f082019e57a643e222e606be003ce83b9cb6f` | 37761075092 / success |
| P6 runner | `8efb3b5d38a408a15680c763823c9761104af314` | 37761867081 / success |
| P7 báo cáo/CLI | `e946b72eb93f3a89199ce55a75cfbe626c5f632f` | 37763702999 / success |

Thứ tự tiếp theo: hoàn tất CI P8 → người thật audit12 nguồn → operator đối soát account/pricing/budget/request-bound/CI ngày chạy → preflight tất cả gate PASS → một lượt S0/S1 qua public orchestrator → render/chấm từ outputs thật → người thật rà bốn demo. Text-to-SQL và network window cũ vẫn hoãn/blocked theo kế hoạch riêng; không mở lại hoặc sửa locks để dùng quyền cũ.
