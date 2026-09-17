#!/usr/bin/env python3
"""Reconstruct the published index from daily, publicly available inputs.

This is a retrospective *approximation*, not a point-in-time trading record:
FRED historical observations can be revised and the index rules were defined
after much of this sample.  Publication lags below prevent the most obvious
look-ahead from observation dates, but they are not exact release timestamps.
"""
from __future__ import annotations

import bisect
import json
import math
import statistics
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from update_data import FRED_IDS, MACRO_IDS, SPEC_IDS, SYMBOLS, build, fetch_fred


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "backtest.json"
START = date(2021, 7, 1)  # HOOD begins trading in July 2021.
HORIZONS = (5, 10, 20)
NASDAQ = "https://api.nasdaq.com/api/quote/{symbol}/historical?{query}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; public-market-history/1.0)",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
}


def nasdaq_history(symbol: str, end: date) -> list[dict]:
    asset = "stocks" if symbol == "HOOD" else "etf"
    query = urllib.parse.urlencode({
        "assetclass": asset, "limit": 5000,
        "fromdate": START.isoformat(), "todate": end.isoformat(),
    })
    url = NASDAQ.format(symbol=urllib.parse.quote(symbol), query=query)
    try:
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read()
    except Exception:
        command = ["curl", "-fsSL", "--retry", "2", "--max-time", "45"]
        for name, value in HEADERS.items():
            command += ["-H", f"{name}: {value}"]
        payload = subprocess.run(command + [url], check=True, capture_output=True, timeout=60).stdout
    parsed = json.loads(payload)
    data = parsed.get("data") or {}
    rows = (data.get("tradesTable") or {}).get("rows") or []
    if parsed.get("status", {}).get("rCode") != 200 or len(rows) < 100:
        raise RuntimeError(f"Nasdaq history unavailable/incomplete for {symbol}")
    out = []
    for row in rows:
        raw = (row.get("close") or "").replace("$", "").replace(",", "")
        if raw:
            out.append({"date": datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat(), "c": float(raw)})
    out.sort(key=lambda item: item["date"])
    if len(out) < 100 or len({item["date"] for item in out}) != len(out):
        raise RuntimeError(f"Invalid Nasdaq history for {symbol}")
    return out


def asof_series(fred: dict[str, list[tuple[str, float]]]) -> dict[str, tuple[list[date], list[float]]]:
    """Availability proxies: daily series +1d, spot oil +3d, CPI +45d."""
    result = {}
    for key, sid in FRED_IDS.items():
        if key == "CORE_CPI":
            values = fred[sid]
            observations = [
                (date.fromisoformat(values[i][0]) + timedelta(days=45),
                 (values[i][1] / values[i - 12][1] - 1) * 100)
                for i in range(12, len(values))
            ]
            output_key = "CORE_CPI_YOY"
        else:
            delay = 3 if key in ("BRENT", "WTI") else 1
            observations = [(date.fromisoformat(day) + timedelta(days=delay), value)
                            for day, value in fred[sid]]
            output_key = key
        result[output_key] = ([item[0] for item in observations], [item[1] for item in observations])
    return result


def value_asof(series: tuple[list[date], list[float]], day: date) -> float | None:
    dates, values = series
    index = bisect.bisect_right(dates, day) - 1
    return values[index] if index >= 0 else None


def pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3 or len(a) != len(b):
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return numerator / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    result = [0.0] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and indexed[end][1] == indexed[start][1]:
            end += 1
        rank = (start + 1 + end) / 2
        for index, _ in indexed[start:end]:
            result[index] = rank
        start = end
    return result


def auc(scores: list[float], events: list[bool]) -> float | None:
    n_positive = sum(events)
    n_negative = len(events) - n_positive
    if not n_positive or not n_negative:
        return None
    ranked = ranks(scores)
    rank_sum = sum(rank for rank, event in zip(ranked, events) if event)
    return (rank_sum - n_positive * (n_positive + 1) / 2) / (n_positive * n_negative)


def rounded(value: float | None, places: int = 3) -> float | None:
    return round(value, places) if value is not None else None


def summarize(rows: list[dict], horizon: int) -> dict:
    usable = rows[:-horizon]
    scores = [row["score"] for row in usable]
    closes = [row["spy_close"] for row in rows]
    future_returns = [(closes[i + horizon] / closes[i] - 1) * 100 for i in range(len(usable))]
    future_drops = [max(0.0, (1 - min(closes[i + 1:i + horizon + 1]) / closes[i]) * 100)
                    for i in range(len(usable))]
    events = [drop >= 5 for drop in future_drops]
    high7 = [event for score, event in zip(scores, events) if score >= 7]
    high93 = [event for score, event in zip(scores, events) if score >= 9.3]
    return {
        "n": len(usable),
        "score_vs_future_return_pearson": rounded(pearson(scores, future_returns)),
        "score_vs_future_drop_spearman": rounded(pearson(ranks(scores), ranks(future_drops))),
        "drawdown_5pct_auc": rounded(auc(scores, events)),
        "base_5pct_rate": rounded(sum(events) / len(events), 4),
        "risk7_days": len(high7),
        "risk7_5pct_rate": rounded(sum(high7) / len(high7), 4) if high7 else None,
        "risk93_days": len(high93),
        "risk93_5pct_rate": rounded(sum(high93) / len(high93), 4) if high93 else None,
    }


def main() -> None:
    today = datetime.now(timezone.utc).date()
    equity = {symbol: nasdaq_history(symbol, today) for symbol in SYMBOLS}
    fred = fetch_fred()
    macro_history = asof_series(fred)
    by_date = {symbol: {bar["date"]: i for i, bar in enumerate(bars)}
               for symbol, bars in equity.items()}
    rows = []
    for spy_bar in equity["SPY"]:
        day_text = spy_bar["date"]
        day = date.fromisoformat(day_text)
        positions = {symbol: by_date[symbol].get(day_text) for symbol in SYMBOLS}
        if any(index is None or index < 5 for index in positions.values()):
            continue
        macro = {key: value_asof(series, day) for key, series in macro_history.items()}
        if any(value is None for value in macro.values()):
            continue
        windows = {symbol: equity[symbol][index - 5:index + 1]
                   for symbol, index in positions.items()}
        signals = build(windows, macro, {})  # Never apply today's manual overrides to history.
        total = sum(item["score"] * item["weight"] for item in signals) / 100
        subset = lambda ids: sum(item["score"] * item["weight"] for item in signals if item["id"] in ids) / sum(item["weight"] for item in signals if item["id"] in ids)
        rows.append({
            "date": day_text,
            "score": round(total, 2),
            "macro_score": round(subset(MACRO_IDS), 2),
            "spec_score": round(subset(SPEC_IDS), 2),
            "spy_close": round(spy_bar["c"], 4),
            "factor_scores": {item["id"]: item["score"] for item in signals},
        })
    if len(rows) < 500 or rows[-1]["date"] < (today - timedelta(days=10)).isoformat():
        raise RuntimeError("Historical series too short or stale; keeping the last published backtest")
    result = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "benchmark": "SPY daily close (price-only, not total return)",
        "method": "Existing 11-factor index, recomputed at each daily close; no manual overrides. FRED daily inputs lagged 1 calendar day, oil 3 days, core CPI 45 days. Future drop = largest close-to-close decline from signal-day close over the next N trading days.",
        "limitations": "Retrospective/in-sample approximation. Historical FRED values can be revised; exact original release timestamps are not reconstructed; current weights/thresholds were set after much of this period; forward windows overlap. Correlation is not proof of predictive power.",
        "sources": {
            "equities": "https://www.nasdaq.com/market-activity/etf/spy/historical",
            "macro": "https://fred.stlouisfed.org/",
            "factor_model": "scripts/update_data.py",
        },
        "metrics": {str(horizon): summarize(rows, horizon) for horizon in HORIZONS},
        "days": rows,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"days": len(rows), "start": rows[0]["date"], "end": rows[-1]["date"], "metrics": result["metrics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
