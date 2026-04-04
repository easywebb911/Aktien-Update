#!/usr/bin/env python3
"""
update_watchlist.py — Automatically refresh watchlist.py from Yahoo Finance screeners.

Runs weekly (Sunday 08:00 MEZ) via GitHub Actions and can be triggered manually.
Does NOT touch generate_report.py or any other files.

Safety guard: aborts if the newly fetched list contains fewer than MIN_TOTAL_TICKERS
tickers across all regions, so a Yahoo Finance outage cannot wipe the watchlist.
"""

import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_MARKET_CAP    = 10_000_000_000   # $10 B — upper cap for watchlist candidates
MIN_PRICE         = 0.50             # USD — exclude micro-cap/penny
MAX_PER_REGION    = 50               # target tickers per region
MIN_PER_REGION    = 10               # warn (but don't abort) below this
MIN_TOTAL_TICKERS = 200              # safety guard: abort if total is below this

WATCHLIST_FILE    = "watchlist.py"

# Screener IDs to query per international region
_INTL_SCREENERS: dict[str, list[str]] = {
    "DE": ["most_shorted_stocks", "small_cap_gainers"],
    "GB": ["most_shorted_stocks", "small_cap_gainers"],
    "FR": ["most_shorted_stocks", "small_cap_gainers"],
    "NL": ["most_shorted_stocks", "small_cap_gainers"],
    "CA": ["most_shorted_stocks", "small_cap_gainers"],
    "JP": ["most_shorted_stocks", "small_cap_gainers"],
    "HK": ["most_shorted_stocks", "small_cap_gainers"],
    "KR": ["most_shorted_stocks", "small_cap_gainers"],
}

_YF_SCREENER_URL = (
    "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
)

# Region comments shown in the generated watchlist.py
_REGION_LABELS: dict[str, str] = {
    "DE": "XETRA / Frankfurt",
    "GB": "London Stock Exchange",
    "FR": "Euronext Paris",
    "NL": "Euronext Amsterdam",
    "CA": "Toronto / TSX",
    "JP": "Tokyo Stock Exchange",
    "HK": "Hong Kong Stock Exchange",
    "KR": "Korea Exchange",
}


# ---------------------------------------------------------------------------
# Yahoo Finance screener helpers
# ---------------------------------------------------------------------------

def _fetch_screener(screener_id: str, region: str, count: int = 100) -> list[dict]:
    """Fetch one predefined Yahoo Finance screener; returns raw quote dicts."""
    params = {
        "formatted": "false",
        "scrIds":    screener_id,
        "count":     str(count),
        "region":    region,
        "lang":      "en-US",
    }
    try:
        resp = requests.get(_YF_SCREENER_URL, params=params,
                            headers=HTTP_HEADERS, timeout=20)
        resp.raise_for_status()
        data    = resp.json()
        results = (data.get("finance") or {}).get("result") or []
        quotes  = results[0].get("quotes", []) if results else []
        log.info("  Screener [%s] '%s': %d quotes", region, screener_id, len(quotes))
        return quotes
    except Exception as exc:
        log.warning("  Screener [%s] '%s' failed: %s", region, screener_id, exc)
        return []


def _fetch_all_for_region(region: str) -> list[dict]:
    """Fetch all screeners for a region, deduplicate, apply basic filters."""
    seen:   set[str] = set()
    quotes: list[dict] = []
    for sid in _INTL_SCREENERS[region]:
        for q in _fetch_screener(sid, region):
            ticker = (q.get("symbol") or "").strip().upper()
            if not ticker or not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,14}$', ticker):
                continue
            if ticker in seen:
                continue
            price   = float(q.get("regularMarketPrice") or 0)
            mkt_cap = q.get("marketCap") or q.get("intradayMarketCap")
            if price < MIN_PRICE:
                continue
            if mkt_cap and float(mkt_cap) > MAX_MARKET_CAP:
                continue
            seen.add(ticker)
            quotes.append({
                "ticker":   ticker,
                "mkt_cap":  float(mkt_cap) if mkt_cap else None,
                "price":    price,
                "avg_vol":  float(q.get("averageDailyVolume3Month") or
                                  q.get("averageDailyVolume10Day") or 0),
            })
        time.sleep(0.4)  # polite rate-limit between screener calls
    return quotes


# ---------------------------------------------------------------------------
# 20-day average volume enrichment via yfinance (batched)
# ---------------------------------------------------------------------------

def _enrich_avg_vol(candidates: list[dict]) -> None:
    """Fill in avg_vol_20d from yfinance history for tickers that lack it.
    Updates candidates in-place. Uses yf.download for batching efficiency.
    """
    need = [c for c in candidates if c.get("avg_vol", 0) == 0]
    if not need:
        return
    tickers = [c["ticker"] for c in need]
    try:
        hist = yf.download(
            tickers, period="25d", auto_adjust=True,
            progress=False, threads=True, group_by="ticker",
        )
        vol_map: dict[str, float] = {}
        if len(tickers) == 1:
            t = tickers[0]
            series = hist.get("Volume")
            if series is not None:
                vol_map[t] = float(series.tail(20).mean())
        else:
            for t in tickers:
                try:
                    series = hist[t]["Volume"]
                    vol_map[t] = float(series.tail(20).mean())
                except Exception:
                    pass
        for c in need:
            c["avg_vol"] = vol_map.get(c["ticker"], 0.0)
    except Exception as exc:
        log.warning("yfinance batch volume enrichment failed: %s", exc)


# ---------------------------------------------------------------------------
# Per-region selection
# ---------------------------------------------------------------------------

def select_top_tickers(region: str, candidates: list[dict]) -> list[str]:
    """Sort by avg volume descending, return up to MAX_PER_REGION tickers."""
    candidates.sort(key=lambda c: c.get("avg_vol", 0), reverse=True)
    selected = [c["ticker"] for c in candidates[:MAX_PER_REGION]]
    n = len(selected)
    if n < MIN_PER_REGION:
        log.warning(
            "Region %s: only %d tickers found (minimum %d) — using all available",
            region, n, MIN_PER_REGION,
        )
    return selected


# ---------------------------------------------------------------------------
# watchlist.py writer
# ---------------------------------------------------------------------------

def _format_watchlist_py(watchlist: dict[str, list[str]], timestamp: str) -> str:
    """Render the watchlist as valid Python source (same format as original)."""
    lines: list[str] = [
        f'# Automatisch aktualisiert: {timestamp}',
        '"""',
        'Auto-generated watchlist of liquid small/mid-cap tickers per market.',
        'Updated weekly by update_watchlist.py — do not edit manually.',
        '',
        'Selection criteria: liquid small/mid-cap stocks (market cap < $10 B,',
        'price > $0.50 USD), sorted by average daily volume descending.',
        '"""',
        '',
        'WATCHLIST: dict[str, list[str]] = {',
    ]
    for region, tickers in watchlist.items():
        label = _REGION_LABELS.get(region, region)
        lines.append(f'    "{region}": [  # {label}')
        for t in tickers:
            lines.append(f'        "{t}",')
        lines.append('    ],')
    lines.append('}')
    lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    log.info("=== update_watchlist.py started at %s ===", timestamp)

    new_watchlist: dict[str, list[str]] = {}

    # Fetch all regions in parallel (one thread per region to keep screener
    # calls grouped, avoids interleaved rate-limit sleeps)
    with ThreadPoolExecutor(max_workers=4) as ex:
        future_map = {ex.submit(_fetch_all_for_region, region): region
                      for region in _INTL_SCREENERS}
        raw_by_region: dict[str, list[dict]] = {}
        for fut in as_completed(future_map):
            region = future_map[fut]
            try:
                raw_by_region[region] = fut.result()
                log.info("Region %s: %d raw candidates", region, len(raw_by_region[region]))
            except Exception as exc:
                log.error("Region %s fetch failed: %s", region, exc)
                raw_by_region[region] = []

    # Volume enrichment and selection per region
    for region in _INTL_SCREENERS:
        candidates = raw_by_region.get(region, [])
        if candidates:
            _enrich_avg_vol(candidates)
        new_watchlist[region] = select_top_tickers(region, candidates)

    # Safety guard
    total = sum(len(v) for v in new_watchlist.values())
    if total < MIN_TOTAL_TICKERS:
        print(
            f"Watchlist-Update abgebrochen: nur {total} Ticker gefunden, "
            f"Mindest {MIN_TOTAL_TICKERS} nicht erreicht",
            flush=True,
        )
        log.error(
            "Aborting: %d tickers is below safety threshold %d. watchlist.py unchanged.",
            total, MIN_TOTAL_TICKERS,
        )
        sys.exit(1)

    # Write new watchlist.py
    content = _format_watchlist_py(new_watchlist, timestamp)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as fh:
        fh.write(content)

    per_region = {r: len(v) for r, v in new_watchlist.items()}
    print(
        f"Watchlist aktualisiert: {per_region}, Gesamt: {total}",
        flush=True,
    )
    for region, n in per_region.items():
        log.info("  %s: %d Ticker", region, n)
    log.info("watchlist.py written (%d total tickers)", total)


if __name__ == "__main__":
    main()
