from __future__ import annotations

from datetime import datetime, timezone

from app.dashboard import build_snapshot, load_records


def _record(ts: str, event: str, **kwargs) -> dict:
    return {"ts": ts, "event": event, **kwargs}


def test_build_snapshot_aggregates_all_panels() -> None:
    records = [
        _record("2026-01-01T10:00:10Z", "request_received"),
        _record(
            "2026-01-01T10:00:20Z",
            "response_sent",
            latency_ms=100,
            ttft_ms=40,
            cost_usd=0.001,
            tokens_in=10,
            tokens_out=20,
            quality_score=0.8,
            tool_success=True,
        ),
        _record("2026-01-01T10:01:10Z", "request_received"),
        _record("2026-01-01T10:01:20Z", "request_failed", error_type="RuntimeError", tool_success=False),
    ]

    snapshot = build_snapshot(records)

    assert snapshot["traffic"]["count"] == 2
    assert snapshot["latency"]["p95"] == 100
    assert snapshot["errors"]["error_rate_pct"] == 50.0
    assert snapshot["errors"]["breakdown"] == {"RuntimeError": 1}
    assert snapshot["errors"]["retrieval_success_pct"] == 100.0
    assert snapshot["tokens"]["total"] == 30
    assert snapshot["quality"]["mean"] == 0.8
    assert snapshot["cost"]["total"] == 0.001


def test_load_records_filters_by_window_and_skips_bad_lines(tmp_path) -> None:
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text(
        '{"ts": "2026-01-01T09:00:00Z", "event": "request_received"}\n'
        '{"ts": "2026-01-01T10:00:00Z", "event": "request_received"}\n'
        "not-json\n",
        encoding="utf-8",
    )

    now = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    records = load_records(log_path, window_minutes=60, now=now)

    assert len(records) == 1
    assert records[0]["ts"].startswith("2026-01-01T10:00")
