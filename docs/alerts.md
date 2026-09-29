# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: HighLatencyP95
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack
- SLI/SLO liên quan: `fast_successful_requests` — SLI `latency_ms <= 3000`
- Điều kiện và thời gian duy trì: `percentile(response_sent.latency_ms, 95) > 3000 ms` liên tục 5 phút
- Ảnh hưởng tới người dùng: phản hồi chậm, dễ timeout, trải nghiệm giảm
- Ba bước kiểm tra đầu tiên:
  1. Mở panel latency, xác nhận P95/P99 và TTFT tăng cùng khoảng thời gian.
  2. Lọc `data/logs.jsonl` các `response_sent` có `latency_ms` lớn, lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`, so sánh thời lượng span `retrieval` và `llm-generation`.
- Mitigation tạm thời: giảm concurrency, rollback prompt/model, tắt incident đang bật (`rag_slow`)
- Owner: llmops-oncall

## Alert 2

- Tên: ElevatedErrorRate
- Severity: critical
- Duration: 5m
- Kênh thông báo: Slack
- SLI/SLO liên quan: `fast_successful_requests` — guardrail `error_rate_pct_max: 2`
- Điều kiện và thời gian duy trì: `request_failed / request_received > 2%` liên tục 5 phút
- Ảnh hưởng tới người dùng: request trả lỗi 500, không có câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở panel errors: error rate, breakdown `error_type`, retrieval success.
  2. Lọc event `request_failed` lấy `correlation_id` và `error_type`.
  3. Mở trace cùng `correlation_id`, xác định span `retrieval`/`llm-generation` bị lỗi.
- Mitigation tạm thời: kiểm tra vector store, retry, trả fallback answer, tắt `tool_fail`
- Owner: llmops-oncall

## Alert 3

- Tên: CostBudgetBurn
- Severity: warning
- Duration: 15m
- Kênh thông báo: Slack
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: `sum(response_sent.cost_usd)` trong 1 giờ > 2.5 USD liên tục 15 phút
- Ảnh hưởng tới người dùng: vượt ngân sách, chi phí LLM tăng bất thường
- Ba bước kiểm tra đầu tiên:
  1. Mở panel cost và tokens, xác nhận `cost_usd`/`tokens_out` tăng đột biến.
  2. Lọc `response_sent` có `cost_usd` hoặc `tokens_out` cao, lấy `correlation_id`.
  3. Mở trace, kiểm tra `usage_details`/`cost_details` của span `llm-generation`.
- Mitigation tạm thời: giới hạn max output tokens, rollback prompt version, rate limit, tắt `cost_spike`
- Owner: llmops-oncall
