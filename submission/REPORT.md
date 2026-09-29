# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên: Nguyễn Anh Trí**
- **MSSV: 2A202602730**
- **Lớp:** K4-L3A
- **Repository URL:** <điền URL repo cá nhân>
- **Commit SHA cuối:** <điền SHA sau khi commit>
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `monitor_logging` (self-hosted, local container)

> **Ghi chú local deployment & đặt tên:** tôi tự host Langfuse bằng Docker Compose theo mục tùy chọn trong `docs/SETUP.md` (`LANGFUSE_BASE_URL=http://localhost:3000`) thay vì Langfuse Cloud. Đây là instance riêng nên chỉ mình tôi tạo trace/prompt. Instance local dùng project tên `monitor_logging`, khác quy ước gợi ý `day13-k4-l3a-<MSSV>`; tên này không ảnh hưởng tính "cá nhân" của dữ liệu và có thể đổi trong Settings nếu cần đúng quy ước.

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt promote | `evidence/10a-prompt-promote.png` |
| Prompt rollback | `evidence/10b-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | `30/100` (0 correlation ID, 20/21 thiếu enrichment, 0 PII leak) | `100/100` (20 correlation ID, 0 thiếu required/enrichment, 0 PII leak) | CP1: correlation ID + bind metadata + scrub trước khi ghi |
| `validate_dashboard.py` | `HỢP LỆ: 6/6 panel` | `HỢP LỆ: 6/6 panel` | Contract không đổi; chốt runtime ở CP2 |
| `pytest` | `22 passed` | `25 passed` | Thêm test dashboard snapshot + tracing children |
| Số traces hợp lệ | `0` | ~40 trace (≥10) | Tự chạy workload trong project Langfuse cá nhân |
| Số PII leak | `0` | `0` | Kiểm chứng với email/phone/CCCD/card, log chỉ còn token `[REDACTED_*]` |
| Latency P95 / TTFT P95 | `150.0 ms / 50.0 ms` | `165.0 ms / 50.0 ms` (bình thường); incident `2651 ms` | Đo từ `/metrics`; incident `rag_slow` làm P95 vọt lên |
| Retrieval success rate | `100%` (10/10, `error_breakdown` rỗng) | `100%` | Incident không gây lỗi retrieval, chỉ chậm |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (`app/middleware.py`) xóa contextvars, nhận `x-request-id` nếu đúng định dạng `req-<8-hex>`, nếu không thì sinh mới bằng `uuid4().hex[:8]`; bind vào structlog contextvars và trả lại qua header `x-request-id` + `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** Ở `app/main.py` bind `user_id_hash` (SHA-256 rút gọn), `session_id`, `feature`, `model`, `env` trước `request_received`; log có `ts`, `level`, `service`, `event`, `correlation_id`, cùng latency/tokens/cost/quality trên `response_sent`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` (đệ quy) được đăng ký ngay sau `TimeStamper` và trước `JsonlFileProcessor`/`JSONRenderer` trong `app/logging_config.py`, nên mọi string được redact trước khi serialize/ghi file. Pattern gồm email, điện thoại VN, CCCD 12 số và thẻ 16 số (`app/pii.py`).
- **Cách kiểm chứng kết quả:** Gửi request chứa PII giả, `grep` xác nhận không còn giá trị thô và chỉ còn token `[REDACTED_*]` (`evidence/05-pii-redaction.png`); `validate_logs.py` báo 0 PII leak, 100/100.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Tự chạy `scripts/load_test.py` (10–60 request) trong project Langfuse local; danh sách trace ở `evidence/06-trace-list.png`.
- **Cấu trúc root/retrieval/generation observations:** `LabAgent.run` là root (`agent`), thêm con `retrieval` (`retriever`) và `llm-generation` (`generation`) bằng `client.start_as_current_observation` qua adapter `start_observation` (`app/tracing.py`, `app/agent.py`); generation có `model`, prompt, `usage_details`, `cost_details`.
- **Cách nối trace với log:** cùng `correlation_id`; log top-level `correlation_id` và trace metadata `correlation_id` trùng nhau (lọc `metadata.correlation_id = req-...`).
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1 — labels `baseline`, `production`
- **Version/label candidate:** v2 — label `candidate`
- **Trace ID của mỗi version:** v1/`baseline`: `<điền trace ID>`; v2/`candidate`: `<điền trace ID>`; waterfall mẫu: `9ffb4c328ec05d824b75cb3f41e286c4`
- **Cách promote và rollback `production`:** chạy `python scripts/manage_prompts.py promote` để chuyển `production` sang v2 (`evidence/10a-prompt-promote.png`), rồi `python scripts/manage_prompts.py rollback` để đưa `production` về v1 (`evidence/10b-prompt-rollback.png`).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `app/dashboard.py` render offline 6 panel từ `data/logs.jsonl` (latency P50/P95/P99 + TTFT P95, traffic, errors + retrieval success, cost, tokens, quality) kèm đơn vị, time range 60m và threshold (`evidence/11-dashboard-overview.png`).
- **SLO và lý do chọn:** `fast_successful_requests`, window 28d, good = `response_sent and latency_ms <= 3000`, target 99.5%. Baseline P95 = 150ms nên ngưỡng 3000ms rộng rãi; target 99.5% để có headroom cho incident.
- **Cách tính error budget:** `(100 - 99.5)% = 0.5%` tổng request; ví dụ 10.000 request/28 ngày ⇒ 50 request được phép xấu; xem `config/slo.yaml`.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (warning, 5m), `ElevatedErrorRate` (critical, 5m), `CostBudgetBurn` (warning, 15m) — `config/alert_rules.yaml` và `docs/alerts.md`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 2026-09-29T10:05:16Z (enable `rag_slow`) → 10:06:00Z
- **Triệu chứng từ metrics:** P95/P99 tăng 150ms → 2651ms, TTFT không đổi (~50ms); vượt ngưỡng challenge 2000ms (`evidence/12-incident-metric.png`).
- **Log line và correlation ID liên quan:** `req-300164f2` (feature `monitoring`, `latency_ms=2651`, `tool_name=retrieval`, `tool_success=true`), cùng đợt `req-650f9098`, `req-03a73555`, `req-d5a0084d`, `req-9c0b2583` (`evidence/13-incident-log.png`).
- **Trace ID và span gây ảnh hưởng:** trace `881cbf57b6bb84dd6e0f596ff9c2a4a7`; span `retrieval` ≈ 2.50s trong khi `llm-generation` ≈ 0.15s (`evidence/14-incident-trace.png`).
- **Root cause:** incident `rag_slow` thêm 2.5s vào `retrieve()` (vector store/retrieval chậm), không phải do LLM.
- **Fix action:** disable incident (`inject_incident.py --disable`) để khôi phục; thêm timeout/retry và cache cho retrieval.
- **Preventive measure:** alert `HighLatencyP95`, guardrail latency/retrieval trong `slo.yaml`, load test định kỳ và test incident scenarios trong CI.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** dùng adapter `start_observation` bọc `start_as_current_observation` thay vì gọi trực tiếp — vừa dùng đúng API v4, vừa không phá vỡ test double (`RecordingLangfuseClient`) và vẫn tách được retrieval/generation.
- **Một lỗi/blocker đã gặp:** prompt luôn `local-fallback`/`LangfuseNotFoundError` do chưa tạo prompt `day13-chat` hoặc sai label.
- **Cách tìm nguyên nhân và xử lý:** so khớp log `prompt_source` với `.env`/prompt name/label, restart API sau khi đổi `.env`.
- **Cách hiểu luồng Metrics → Logs → Traces:** metric (dashboard) chỉ ra triệu chứng và thời điểm; log (`data/logs.jsonl`) cho `correlation_id` của request bất thường; trace (Langfuse) cùng `correlation_id` chỉ ra span chậm/lỗi → root cause.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback:** prompt version cho biết request dùng prompt nào và cho phép rollback an toàn; token/cost phát hiện lạm chi; SLO/error budget định lượng mức độ ảnh hưởng.
- **Điều quan trọng nhất đã học:** observability chỉ đủ mạnh khi metric, log và trace nối được với nhau bằng một định danh chung.
- **Hạn chế hoặc phần chưa hoàn thành:** dashboard đọc log file (không streaming realtime) và alert mô tả dạng rule, chưa tích hợp kênh Slack thật.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
