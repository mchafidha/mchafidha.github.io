#!/usr/bin/env python3
"""
update_data.py — refreshes data.json for the Turnaround Stock Monitor.
Run daily via GitHub Actions. Uses yfinance (delayed/EOD data — fine per strategy).

Quantitative fields (price, 52w range, drawdown, ratios) are refreshed automatically.
Qualitative fields (crash reason, catalyst, trading plan) are kept from the existing
data.json — those are analyst inputs, not screener outputs.

    pip install yfinance
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

DATA_FILE = Path(__file__).resolve().parent.parent / "data.json"

# Map dashboard tickers -> Yahoo Finance symbols
SYMBOLS = {
    "NASDAQ:CTSH": "CTSH",
    "NYSE:CRM": "CRM",
    "HKEX:1810": "1810.HK",
}


def safe(v, default=None):
    """Return None-safe float."""
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 2)
    except (TypeError, ValueError):
        return default


def refresh_stock(stock: dict) -> dict:
    yf_symbol = SYMBOLS.get(stock["ticker"])
    if not yf_symbol:
        return stock

    t = yf.Ticker(yf_symbol)
    info = t.info or {}
    hist = t.history(period="1y")

    price = safe(info.get("currentPrice")) or safe(hist["Close"].iloc[-1])
    hi52 = safe(info.get("fiftyTwoWeekHigh")) or safe(hist["High"].max())
    lo52 = safe(info.get("fiftyTwoWeekLow")) or safe(hist["Low"].min())

    if price and hi52:
        stock["crash"]["currentPrice"] = price
        stock["crash"]["high52w"] = hi52
        stock["crash"]["low52w"] = lo52
        stock["crash"]["dropPct"] = round((price / hi52 - 1) * 100, 1)

    # Fundamentals (yfinance provides these for most large caps; keep old value if missing)
    f = stock["fundamentals"]
    f["currentRatio"] = safe(info.get("currentRatio"), f.get("currentRatio"))
    de = safe(info.get("debtToEquity"))
    if de is not None:  # yfinance reports D/E in percent
        f["debtEquity"] = round(de / 100, 2) if de > 5 else de
    f["pb"] = safe(info.get("priceToBook"), f.get("pb"))
    fcf = info.get("freeCashflow")
    if fcf:
        sign = "+" if fcf > 0 else "−"
        f["fcfTTM"] = f"{sign}${abs(fcf) / 1e9:.2f}B" if not yf_symbol.endswith(".HK") else f"{sign}{abs(fcf) / 1e9:.1f}B (local)"

    # Screen flags — log a warning if a pick no longer passes the filters
    fails = []
    if stock["crash"]["dropPct"] > -30:
        fails.append("drawdown < 30%")
    if (f.get("currentRatio") or 0) < 1.2:
        fails.append("current ratio < 1.2")
    if (f.get("debtEquity") or 0) > 1.0:
        fails.append("D/E > 1.0")
    if (f.get("zScore") or 0) < 2.99:
        fails.append("Z-score < 2.99")
    stock["screenWarnings"] = fails

    print(f"  {stock['ticker']}: {price} ({stock['crash']['dropPct']}%)"
          + (f"  ⚠ {fails}" if fails else "  ✓ all filters pass"))
    return stock


def main():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print("Refreshing watchlist…")
    data["stocks"] = [refresh_stock(s) for s in data["stocks"]]
    data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC (EOD/T+1)")
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {DATA_FILE}")


if __name__ == "__main__":
    main()
