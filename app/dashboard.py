from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_WINDOW_MINUTES = 60
DEFAULT_REFRESH_SECONDS = 30

THRESHOLDS = {
    "latency": "p95 <= 3000 ms",
    "traffic": "rate >= 1 req/min",
    "errors": "error_rate <= 2%",
    "cost": "total <= 2.5 USD",
    "tokens": "total <= 50000 tokens",
    "quality": "mean >= 0.75",
}


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_records(
    log_path: str | Path,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    now: datetime | None = None,
) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        timestamp = _parse_ts(record.get("ts"))
        if timestamp is not None and timestamp >= cutoff:
            records.append(record)
    return records


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    index = max(0, min(len(items) - 1, round((percentile / 100) * len(items) + 0.5) - 1))
    return round(float(items[index]), 2)


def _numbers(records: list[dict], key: str) -> list[float]:
    return [r[key] for r in records if isinstance(r.get(key), (int, float))]


def _per_minute(records: list[dict], value_key: str | None = None) -> list[tuple[str, float]]:
    buckets: dict[str, float] = {}
    for record in records:
        timestamp = _parse_ts(record.get("ts"))
        if timestamp is None:
            continue
        label = timestamp.strftime("%H:%M")
        if value_key is None:
            buckets[label] = buckets.get(label, 0) + 1
        else:
            value = record.get(value_key)
            if isinstance(value, (int, float)):
                buckets[label] = buckets.get(label, 0) + float(value)
    return [(label, round(value, 4)) for label, value in sorted(buckets.items())]


def build_snapshot(records: list[dict], window_minutes: int = DEFAULT_WINDOW_MINUTES) -> dict:
    received = [r for r in records if r.get("event") == "request_received"]
    sent = [r for r in records if r.get("event") == "response_sent"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    latencies = _numbers(sent, "latency_ms")
    ttfts = _numbers(sent, "ttft_ms")
    costs = _numbers(sent, "cost_usd")
    qualities = _numbers(sent, "quality_score")
    tokens_in = int(sum(_numbers(sent, "tokens_in")))
    tokens_out = int(sum(_numbers(sent, "tokens_out")))

    total_received = len(received)
    error_rate = round(len(failed) / total_received * 100, 2) if total_received else 0.0

    tool_results = [r.get("tool_success") for r in sent if r.get("tool_success") is not None]
    retrieval_success = (
        round(sum(1 for result in tool_results if result) / len(tool_results) * 100, 2)
        if tool_results
        else 0.0
    )

    timestamps = [t for t in (_parse_ts(r.get("ts")) for r in records) if t is not None]
    time_range = {
        "start": min(timestamps).strftime("%Y-%m-%d %H:%M:%S UTC") if timestamps else "-",
        "end": max(timestamps).strftime("%Y-%m-%d %H:%M:%S UTC") if timestamps else "-",
    }

    return {
        "window_minutes": window_minutes,
        "time_range": time_range,
        "records": len(records),
        "traffic": {"count": total_received, "series": _per_minute(received)},
        "latency": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "ttft_p95": _percentile(ttfts, 95),
        },
        "errors": {
            "error_rate_pct": error_rate,
            "failed": len(failed),
            "retrieval_success_pct": retrieval_success,
            "breakdown": dict(Counter(r.get("error_type", "unknown") for r in failed)),
        },
        "cost": {"total": round(sum(costs), 4), "series": _per_minute(sent, "cost_usd")},
        "tokens": {"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out},
        "quality": {"mean": round(mean(qualities), 3) if qualities else 0.0, "count": len(qualities)},
        "thresholds": THRESHOLDS,
    }


def _stat(label: str, value: float, unit: str, threshold: float | None = None, higher_is_worse: bool = True) -> str:
    css = "stat"
    if threshold is not None:
        bad = value > threshold if higher_is_worse else value < threshold
        css += " bad" if bad else " good"
    return (
        f'<div class="{css}"><span class="val">{value:g} {html.escape(unit)}</span>'
        f'<span class="lbl">{html.escape(label)}</span></div>'
    )


def _bar_rows(
    pairs: list[tuple[str, float]],
    unit: str,
    threshold: float | None = None,
    higher_is_worse: bool = True,
) -> str:
    if not pairs:
        return '<p class="empty">No data in window.</p>'
    peak = max([value for _, value in pairs] + ([threshold] if threshold is not None else []) + [1e-9])
    rows = []
    for label, value in pairs:
        width = max(2.0, value / peak * 100) if peak else 0.0
        css = "bar"
        if threshold is not None:
            bad = value > threshold if higher_is_worse else value < threshold
            css += " bad" if bad else " good"
        rows.append(
            f'<div class="row"><span class="lbl">{html.escape(str(label))}</span>'
            f'<span class="track"><span class="{css}" style="width:{width:.1f}%"></span></span>'
            f'<span class="val">{value:g} {html.escape(unit)}</span></div>'
        )
    return "\n".join(rows)


def _panel(panel_id: str, title: str, unit: str, body: str, time_range: str, threshold: str) -> str:
    return f"""
    <section class="card" id="{panel_id}">
      <header>
        <h2>{html.escape(title)}</h2>
        <div class="meta">
          <span class="unit">{html.escape(unit)}</span>
          <span class="range">{html.escape(time_range)}</span>
          <span class="threshold">{html.escape(threshold)}</span>
        </div>
      </header>
      <div class="body">{body}</div>
    </section>"""


_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: #0f172a; color: #e2e8f0;
       font: 14px/1.4 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: #94a3b8; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
.card header h2 { font-size: 15px; margin: 0 0 6px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; font-size: 11px; }
.meta span { background: #0f172a; border: 1px solid #334155; border-radius: 999px; padding: 2px 8px; color: #cbd5e1; }
.threshold { border-color: #f59e0b !important; color: #fbbf24 !important; }
.row { display: grid; grid-template-columns: 96px 1fr 110px; align-items: center; gap: 8px; margin: 6px 0; }
.row .lbl { color: #94a3b8; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row .track { background: #0f172a; border-radius: 6px; height: 14px; overflow: hidden; }
.row .bar { display: block; height: 100%; background: #38bdf8; }
.row .bar.good { background: #22c55e; }
.row .bar.bad { background: #ef4444; }
.row .val { text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
.stat { display: flex; flex-direction: column; gap: 2px; margin-bottom: 12px; }
.stat .val { font-size: 26px; font-weight: 600; }
.stat .lbl { color: #94a3b8; font-size: 12px; }
.stat.good .val { color: #22c55e; }
.stat.bad .val { color: #ef4444; }
.empty { color: #64748b; font-style: italic; }
"""


def render_html(snapshot: dict) -> str:
    time_range = (
        f'{snapshot["time_range"]["start"]} → {snapshot["time_range"]["end"]} '
        f'({snapshot["window_minutes"]}m)'
    )
    latency = snapshot["latency"]
    errors = snapshot["errors"]
    tokens = snapshot["tokens"]
    quality = snapshot["quality"]
    cost = snapshot["cost"]
    thresholds = snapshot["thresholds"]

    latency_body = _bar_rows(
        [("P50", latency["p50"]), ("P95", latency["p95"]), ("P99", latency["p99"]), ("TTFT P95", latency["ttft_p95"])],
        "ms",
        threshold=3000,
    )
    traffic_body = _stat("requests", snapshot["traffic"]["count"], "req", threshold=1, higher_is_worse=False) + _bar_rows(
        snapshot["traffic"]["series"], "req"
    )
    breakdown = sorted(errors["breakdown"].items())
    errors_body = (
        _stat("error rate", errors["error_rate_pct"], "%", threshold=2)
        + _stat("retrieval success", errors["retrieval_success_pct"], "%", threshold=90, higher_is_worse=False)
        + _bar_rows([(name, value) for name, value in breakdown], "fails")
    )
    cost_body = _stat("total", cost["total"], "USD", threshold=2.5) + _bar_rows(cost["series"], "USD")
    tokens_body = _stat("total", tokens["total"], "tokens", threshold=50000) + _bar_rows(
        [("Input", tokens["input"]), ("Output", tokens["output"])], "tokens"
    )
    quality_body = _stat("mean", quality["mean"], "score", threshold=0.75, higher_is_worse=False) + _bar_rows(
        [("Mean quality", quality["mean"])], "score"
    )

    panels = "".join(
        [
            _panel("latency", "Latency percentiles and TTFT", "ms", latency_body, time_range, thresholds["latency"]),
            _panel("traffic", "Request traffic", "req/min", traffic_body, time_range, thresholds["traffic"]),
            _panel("errors", "Error rate and retrieval success", "%", errors_body, time_range, thresholds["errors"]),
            _panel("cost", "Cost over time", "USD", cost_body, time_range, thresholds["cost"]),
            _panel("tokens", "Input and output tokens", "tokens", tokens_body, time_range, thresholds["tokens"]),
            _panel("quality", "Quality proxy", "score_0_to_1", quality_body, time_range, thresholds["quality"]),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{DEFAULT_REFRESH_SECONDS}">
  <title>K4-L3A Day 13 Dashboard</title>
  <style>{_STYLE}</style>
</head>
<body>
  <h1>K4-L3A Day 13 Monitoring &amp; LLMOps</h1>
  <div class="sub">Source: data/logs.jsonl · {snapshot["records"]} records · refresh {DEFAULT_REFRESH_SECONDS}s</div>
  <div class="grid">{panels}</div>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    log_path: Path = DEFAULT_LOG_PATH
    window_minutes: int = DEFAULT_WINDOW_MINUTES

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/snapshot"):
            snapshot = build_snapshot(load_records(self.log_path, self.window_minutes), self.window_minutes)
            self._respond(200, "application/json", json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
        elif self.path in ("/", "/index.html"):
            snapshot = build_snapshot(load_records(self.log_path, self.window_minutes), self.window_minutes)
            self._respond(200, "text/html; charset=utf-8", render_html(snapshot).encode("utf-8"))
        else:
            self._respond(404, "text/plain; charset=utf-8", b"not found")

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:  # silence per-request logging
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline 6-panel dashboard from data/logs.jsonl")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    args = parser.parse_args()

    DashboardHandler.log_path = args.log
    DashboardHandler.window_minutes = args.window_minutes

    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Dashboard: http://127.0.0.1:{args.port} (source: {args.log}, window: {args.window_minutes}m)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
