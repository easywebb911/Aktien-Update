#!/usr/bin/env python3
"""
Daily Stock Squeeze Report Generator
Identifies top 10 short squeeze candidates from global markets (US, DE, GB, CA).
Data sources: Yahoo Finance Screener (primary) + Finviz (fallback) + yfinance (enrichment).
News titles and summaries are translated to German.
"""

import math
import os
import re
import json
import time
import logging
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from watchlist import WATCHLIST

try:
    import pandas_ta as ta  # optional: RSI / MA computation
    _HAS_PANDAS_TA = True
except ImportError:
    ta = None  # type: ignore[assignment]
    _HAS_PANDAS_TA = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_SHORT_FLOAT = 15.0   # %
MIN_REL_VOLUME       = 1.5   # × 20-day avg — US stocks
MIN_REL_VOLUME_INTL  = 1.2   # × 20-day avg — international watchlist (lower bar)
MAX_MARKET_CAP  = 10e9   # $10 B
MIN_PRICE       = 1.0    # USD
MIN_SCORE       = 15.0   # pts — informational reference only; NOT a hard filter.
                         # Candidates below this value show a "schwächeres Signal"
                         # hint on their card but are still included in the Top 10.

# ── Metric tile colour thresholds ────────────────────────────────────────────
# Farblogik: Grün = starkes Squeeze-Signal, Orange = moderat, Rot = schwach — gilt einheitlich für alle vier Kategorien.
# Short Float
SF_GREEN  = 30.0   # %   ≥30    → green
SF_ORANGE = 15.0   # %   15–29  → orange, <15 → red
# Days to Cover
SR_GREEN  =  8.0   # days  ≥8    → green
SR_ORANGE =  3.0   # days  3–7   → orange, <3 → red
# Rel. Volume
RV_GREEN  =  3.0   # ×   ≥3     → green
RV_ORANGE =  1.5   # ×   1.5–2.9 → orange, <1.5 → red
# Kursmomentum
MOM_GREEN =  5.0   # %   ≥+5    → green
MOM_ORANGE= -5.0   # %   −5–+5  → orange, <−5 → red

# ── Supplementary data source bonus limits ───────────────────────────────────
FINRA_BONUS_MAX          = 5    # max bonus points for rising FINRA short interest
FINRA_ACCELERATION_BONUS = 7    # elevated bonus when SI velocity is accelerating
COMBO_BONUS              = 5    # synergy bonus when ≥ 3 of 4 squeeze factors are strong simultaneously
FTD_BONUS_MAX    = 0    # SEC EDGAR + Nasdaq Data Link blocked on GitHub Actions IPs
# ── FINRA short interest trend thresholds ────────────────────────────────────
SI_TREND_PERIODS        = 6     # FINRA publishes twice monthly; 6 = ~3 months
SI_TREND_MIN_DATAPOINTS = 2     # minimum history points required for trend calc
# ── Float-size score factor ───────────────────────────────────────────────────
FLOAT_WEIGHT          = 8          # max bonus points for small float
FLOAT_SATURATION_LOW  = 30_000_000  # ≤ 30 M shares → full 8 pts
FLOAT_SATURATION_HIGH = 50_000_000  # ≥ 50 M shares → 0 pts; linear between
SI_TREND_UP_THRESHOLD   =  0.10   # ≥+10 % over full period → steigend
SI_TREND_DOWN_THRESHOLD = -0.10   # ≤−10 % → fallend; between → seitwärts
# ── Score smoothing weights ──────────────────────────────────────────────────
SCORE_TODAY_WEIGHT   = 0.70   # weight for today's raw score
SCORE_HISTORY_WEIGHT = 0.30   # weight for average of last 3 historical runs
SCORE_TREND_BONUS    = 3      # +Pkt wenn Score SCORE_TREND_DAYS Tage in Folge gestiegen
SCORE_TREND_MALUS    = 3      # −Pkt wenn Score SCORE_TREND_DAYS Tage in Folge gefallen
SCORE_TREND_DAYS     = 3      # Anzahl aufeinanderfolgender Tage für Trend-Erkennung
USE_RELATIVE_MOMENTUM = True  # Momentum relativ zum S&P 500 berechnen (adjusted_chg = chg − spx_daily)
_SCORE_HISTORY_FILE  = "score_history.json"
_SCORE_HISTORY_DAYS  = 14     # prune entries older than this many days
# ── Dynamic enrichment pool sizing ───────────────────────────────────────────
POOL_MIN                  = 20    # always enrich at least this many candidates
POOL_MAX                  = 75    # hard upper limit to keep runtime reasonable
POOL_SHORT_FLOAT_THRESHOLD = 10.0 # SF ≥ this % → always included regardless of POOL_MAX
POOL_ENRICH_TIMEOUT       = 90    # seconds — skip remaining candidates if exceeded
# ── Implied Volatility colour thresholds (percentage points) ─────────────────
IV_LOW  = 50    # IV < IV_LOW  → rot   (niedrig, kein Squeeze-Signal)
IV_HIGH = 100   # IV > IV_HIGH → grün  (extrem, typisch vor Squeezes)
IV_MIN_DAYS_TO_EXPIRY = 7  # Verfallstermin muss mind. N Tage entfernt sein (verhindert Time-Decay-Verzerrung)


# ===========================================================================
# 1. FINVIZ SCREENER
# ===========================================================================

def _parse_market_cap(s: str):
    """'1.5B' → 1_500_000_000  |  '-' → None"""
    if not s or s == "-":
        return None
    s = s.strip()
    mult = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    if s[-1] in mult:
        try:
            return float(s[:-1]) * mult[s[-1]]
        except ValueError:
            return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _parse_pct(s: str) -> float:
    if not s or s == "-":
        return 0.0
    try:
        return float(s.replace("%", "").strip())
    except ValueError:
        return 0.0


def _parse_float(s: str) -> float:
    if not s or s == "-":
        return 0.0
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return 0.0


# ===========================================================================
# 1a. YAHOO FINANCE SCREENER  (primary — direct JSON API, no yf.Screener)
# ===========================================================================

# Markets to scan: region code → list of predefined screener IDs
_YF_SCREENERS: dict[str, list[str]] = {
    "US": ["most_shorted_stocks", "small_cap_gainers", "aggressive_small_caps"],
    "DE": ["most_shorted_stocks", "small_cap_gainers"],   # XETRA / Frankfurt
    "GB": ["most_shorted_stocks", "small_cap_gainers"],   # London Stock Exchange
    "FR": ["most_shorted_stocks", "small_cap_gainers"],   # Euronext Paris
    "NL": ["most_shorted_stocks", "small_cap_gainers"],   # Euronext Amsterdam
    "CA": ["most_shorted_stocks", "small_cap_gainers"],   # Toronto Stock Exchange
}

# Deterministic flag from ticker suffix (longest match wins)
_SUFFIX_FLAGS: list[tuple[str, str]] = [
    (".KS", "🇰🇷"),
    (".HK", "🇭🇰"),
    (".TO", "🇨🇦"),
    (".PA", "🇫🇷"),
    (".AS", "🇳🇱"),
    (".DE", "🇩🇪"),
    (".L",  "🇬🇧"),
    (".T",  "🇯🇵"),
]

def get_flag(ticker: str) -> str:
    """Return the country flag emoji for *ticker* based on its suffix.
    Longest-match first ensures e.g. '.KS' beats a hypothetical '.K'."""
    t = ticker.upper()
    for suffix, flag in _SUFFIX_FLAGS:
        if t.endswith(suffix.upper()):
            return flag
    return "🇺🇸"  # no suffix → US


def get_region(ticker: str) -> str:
    """Return the region code for *ticker* based on its suffix.
    Consistent with get_flag() — both derived from ticker suffix only."""
    t = ticker.upper()
    suffix_regions = [
        (".KS", "KR"), (".T", "JP"), (".HK", "HK"),
        (".DE", "DE"), (".L", "GB"), (".PA", "FR"),
        (".AS", "NL"), (".TO", "CA"),
    ]
    for suffix, region in suffix_regions:
        if t.endswith(suffix.upper()):
            return region
    return "US"


_YF_SCREENER_URL = (
    "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
)


def _translate(text: str) -> str:
    """Translate text to German via Google Translate (free, no key required)."""
    if not text or len(text.strip()) < 4:
        return text
    try:
        return GoogleTranslator(source="auto", target="de").translate(text[:4900])
    except Exception as exc:
        log.debug("Translation skipped: %s", exc)
        return text


def _fetch_yf_screener(screener_id: str, region: str = "US", count: int = 100) -> list[dict]:
    """Call one Yahoo Finance predefined screener via raw HTTP. No crumb needed."""
    params = {
        "formatted": "false",
        "scrIds": screener_id,
        "count": str(count),
        "region": region,
        "lang": "en-US",
    }
    try:
        resp = requests.get(
            _YF_SCREENER_URL, params=params, headers=HTTP_HEADERS, timeout=20
        )
        _req_counts["yahoo"] += 1
        resp.raise_for_status()
        data = resp.json()
        results = (data.get("finance") or {}).get("result") or []
        quotes  = results[0].get("quotes", []) if results else []
        log.info("  Yahoo screener [%s] '%s': %d quotes", region, screener_id, len(quotes))
        return quotes
    except Exception as exc:
        log.warning("  Yahoo screener [%s] '%s' failed: %s", region, screener_id, exc)
        return []


def get_yahoo_screener_candidates() -> list[dict]:
    """Fetch candidates from Yahoo Finance screeners across all regions in parallel
    (max 5 threads, respects Yahoo rate-limits). Results are deduplicated.
    """
    result: list[dict] = []
    seen:   set[str]   = set()

    def _add_quotes(quotes: list, region: str, screener_id: str) -> None:
        src_tag = "yahoo_most_shorted" if screener_id == "most_shorted_stocks" else "yahoo_screener"
        for q in quotes:
            t = q.get("symbol", "").strip().upper()
            if not t or not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,14}$', t) or t in seen:
                continue
            price   = float(q.get("regularMarketPrice") or 0)
            mkt_cap = q.get("marketCap") or q.get("intradayMarketCap")
            if price < MIN_PRICE:
                continue
            if mkt_cap and float(mkt_cap) > MAX_MARKET_CAP:
                continue
            seen.add(t)
            sf_raw = float(q.get("shortPercentOfFloat") or 0)
            result.append({
                "ticker":       t,
                "market":       region,
                "market_cap":   float(mkt_cap) if mkt_cap else None,
                "market_cap_s": fmt_cap(mkt_cap),
                "price":        price,
                "change":       float(q.get("regularMarketChangePercent") or 0),
                "change_5d":    None,
                "short_float":  sf_raw * 100 if sf_raw <= 1.0 else sf_raw,
                "short_ratio":  float(q.get("shortRatio") or 0),
                "rel_volume":   0.0,
                "company_name": q.get("shortName") or q.get("longName") or t,
                "sector":       q.get("sector") or "",
                "source":       src_tag,
            })

    tasks = [(region, sid)
             for region, sids in _YF_SCREENERS.items()
             for sid in sids]
    log.info("Querying %d Yahoo Finance screeners across %d regions (parallel, max 5 threads) …",
             len(tasks), len(_YF_SCREENERS))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        future_map = {ex.submit(_fetch_yf_screener, sid, region): (region, sid)
                      for region, sid in tasks}
        for fut in as_completed(future_map):
            region, sid = future_map[fut]
            try:
                _add_quotes(fut.result(), region, sid)
            except Exception as exc:
                log.warning("Screener future error: %s", exc)

    elapsed = time.time() - t0
    print(f"Yahoo Screener: {len(tasks)} Requests parallel in {elapsed:.1f}s abgeschlossen",
          flush=True)
    log.info("Yahoo screener pool: %d unique tickers", len(result))
    return result


def get_finviz_candidates(max_pages: int = 6) -> list[dict]:
    """
    Scrape Finviz Ownership screener (v=141) — fallback when Yahoo screener fails.
    Note: Finviz may block cloud-runner IPs; use Yahoo screener as primary.
    """
    candidates: list[dict] = []
    col_map: dict[str, int] | None = None

    for page in range(max_pages):
        row_start = page * 20 + 1
        url = (
            "https://finviz.com/screener.ashx"
            f"?v=141&f=sh_short_o{int(MIN_SHORT_FLOAT)},sh_price_o{int(MIN_PRICE)}"
            f"&o=-shortfloat&r={row_start}"
        )
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Finviz request failed: %s", exc)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Locate the data table by finding the one whose first row contains "Ticker"
        table = None
        for t in soup.find_all("table"):
            first_tr = t.find("tr")
            if first_tr and any("Ticker" in td.get_text() for td in first_tr.find_all("td")):
                table = t
                break

        if table is None:
            log.warning("Screener table not found on page %d – stopping.", page + 1)
            break

        all_rows = table.find_all("tr")
        if not all_rows:
            break

        # Build column map from header row (first time)
        if col_map is None:
            headers = [td.get_text(strip=True) for td in all_rows[0].find_all("td")]
            col_map = {h: i for i, h in enumerate(headers)}
            log.debug("Finviz columns: %s", headers)

        data_rows = all_rows[1:]
        if not data_rows:
            break

        page_added = 0
        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) < 10:
                continue

            def cell(name: str, default: str = "") -> str:
                idx = col_map.get(name, -1)
                return cells[idx].get_text(strip=True) if 0 <= idx < len(cells) else default

            ticker = cell("Ticker")
            if not ticker or not ticker.replace(".", "").isalnum():
                continue

            mkt_cap     = _parse_market_cap(cell("Market Cap"))
            short_float = _parse_pct(cell("Float Short"))
            short_ratio = _parse_float(cell("Short Ratio"))
            rel_vol     = _parse_float(cell("Rel Volume"))
            price       = _parse_float(cell("Price"))
            change      = _parse_pct(cell("Change"))

            # Hard filters
            if price < MIN_PRICE:
                continue
            if short_float < MIN_SHORT_FLOAT:
                continue
            if rel_vol < MIN_REL_VOLUME:
                continue
            if mkt_cap and mkt_cap > MAX_MARKET_CAP:
                continue

            candidates.append({
                "ticker":       ticker,
                "market_cap":   mkt_cap,
                "market_cap_s": cell("Market Cap"),
                "short_float":  short_float,
                "short_ratio":  short_ratio,
                "rel_volume":   rel_vol,
                "price":        price,
                "change":       change,
                "change_5d":    None,
            })
            page_added += 1

        log.info("Finviz page %d: +%d → %d total", page + 1, page_added, len(candidates))
        time.sleep(1.5)  # polite rate-limit

    return candidates


# ===========================================================================
# 2. YFINANCE ENRICHMENT
# ===========================================================================

def get_yfinance_data(ticker: str) -> dict:
    """Single-ticker yfinance fetch — used as fallback when batch data is missing."""
    _req_counts["yfinance"] += 1
    try:
        stk  = yf.Ticker(ticker)
        info = stk.info or {}
        hist = stk.history(period="1y")

        avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 5 else 0.0
        cur_vol    = float(hist["Volume"].iloc[-1])         if len(hist) >= 1 else 0.0
        vol_ratio  = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

        rsi14, ma50, ma200, perf_20d = None, None, None, None
        if not hist.empty:
            try:
                close = hist["Close"].dropna()
                if len(close) >= 21:
                    perf_20d = float(
                        (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100
                    )
                if _HAS_PANDAS_TA and len(close) >= 14:
                    rsi_s = ta.rsi(close, length=14)
                    rsi14 = float(rsi_s.iloc[-1]) if rsi_s is not None and not rsi_s.empty else None
                if len(close) >= 50:
                    ma50 = float(close.tail(50).mean())
                if len(close) >= 200:
                    ma200 = float(close.tail(200).mean())
            except Exception:
                pass

        return {
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "sector":       info.get("sector") or "",
            "industry":     info.get("industry") or "",
            "market_cap":   info.get("marketCap"),
            "short_ratio":  info.get("shortRatio") or 0.0,
            "short_float_yf": (info.get("shortPercentOfFloat") or 0.0) * 100,
            "52w_high":     info.get("fiftyTwoWeekHigh"),
            "52w_low":      info.get("fiftyTwoWeekLow"),
            "avg_vol_20d":  avg_vol_20,
            "cur_vol":      cur_vol,
            "vol_ratio":    vol_ratio,
            "float_shares":       info.get("floatShares") or 0,
            "inst_ownership":     info.get("institutionHeldPercentOutstanding")
                                  or info.get("institutionsPercentHeld"),
            "rsi14":        rsi14,
            "ma50":         ma50,
            "ma200":        ma200,
            "perf_20d":     perf_20d,
        }
    except Exception as exc:
        log.warning("yfinance error for %s: %s", ticker, exc)
        return {}


def get_yfinance_batch(tickers: list[str]) -> dict[str, dict]:
    """Batch-fetch yfinance data for all tickers at once.

    Opt 1 — Two-phase approach:
      Phase A: Single yf.download() for full OHLCV history (one HTTP round-trip
               regardless of pool size — the dominant time saving).
      Phase B: Parallel .info fetches via ThreadPoolExecutor(max_workers=5) for
               metadata fields (sector, short float, market cap, …) that are not
               available in the download payload.

    IMPORTANT fallback: if a ticker is absent or empty in the batch result the
    function transparently falls back to the individual get_yfinance_data() call
    so no data is silently lost.

    Returns {ticker: yfd_dict} with the same keys as get_yfinance_data().
    """
    if not tickers:
        return {}

    results: dict[str, dict] = {}

    # ── Phase A: Batch OHLCV history (single HTTP request for all tickers) ──
    hist_batch = None
    try:
        hist_batch = yf.download(
            tickers, period="1y", group_by="ticker",
            auto_adjust=True, threads=True, progress=False,
        )
        _req_counts["yfinance"] += 1
        log.info("Batch history download: %d tickers", len(tickers))
    except Exception as exc:
        log.warning("Batch history download failed (%s) — will use individual fallbacks", exc)

    def _compute_indicators(df) -> tuple:
        """Compute (rsi14, ma50, ma200, perf_20d) from a Close series."""
        rsi14, ma50, ma200, perf_20d = None, None, None, None
        if df is None or df.empty:
            return rsi14, ma50, ma200, perf_20d
        try:
            close = df["Close"].dropna()
            if len(close) >= 21:
                perf_20d = float(
                    (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100
                )
            if _HAS_PANDAS_TA and len(close) >= 14:
                rsi_series = ta.rsi(close, length=14)
                rsi14 = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else None
            if len(close) >= 50:
                ma50 = float(close.tail(50).mean())
            if len(close) >= 200:
                ma200 = float(close.tail(200).mean())
        except Exception:
            pass
        return rsi14, ma50, ma200, perf_20d

    def _hist_stats(ticker: str) -> tuple:
        """Extract (avg_vol_20, cur_vol, vol_ratio, hi52, lo52, rsi14, ma50, ma200, perf_20d) from batch or fallback."""
        try:
            if hist_batch is not None and not hist_batch.empty:
                # yf.download with one ticker returns a flat DataFrame;
                # with multiple tickers it returns a MultiLevel DataFrame.
                df = hist_batch if len(tickers) == 1 else hist_batch[ticker]
                if df is not None and not df.empty and len(df) >= 5:
                    avg_vol = float(df["Volume"].tail(20).mean())
                    cur_vol = float(df["Volume"].iloc[-1])
                    vol_r   = cur_vol / avg_vol if avg_vol > 0 else 0.0
                    hi52    = float(df["High"].max())
                    lo52    = float(df["Low"].min())
                    rsi14, ma50, ma200, perf_20d = _compute_indicators(df)
                    return avg_vol, cur_vol, vol_r, hi52, lo52, rsi14, ma50, ma200, perf_20d
        except Exception:
            pass
        # Fallback: individual history call for this ticker
        try:
            df2 = yf.Ticker(ticker).history(period="1y")
            _req_counts["yfinance"] += 1
            if not df2.empty and len(df2) >= 5:
                avg_vol = float(df2["Volume"].tail(20).mean())
                cur_vol = float(df2["Volume"].iloc[-1])
                vol_r   = cur_vol / avg_vol if avg_vol > 0 else 0.0
                rsi14, ma50, ma200, perf_20d = _compute_indicators(df2)
                return avg_vol, cur_vol, vol_r, float(df2["High"].max()), float(df2["Low"].min()), rsi14, ma50, ma200, perf_20d
        except Exception as exc2:
            log.debug("Fallback history failed for %s: %s", ticker, exc2)
        return 0.0, 0.0, 0.0, None, None, None, None, None, None

    # ── Phase B: Parallel .info fetches (metadata not in download payload) ──
    def _fetch_info(ticker: str) -> tuple[str, dict]:
        """Return (ticker, info_dict); empty dict on any error."""
        try:
            info = yf.Ticker(ticker).info or {}
            _req_counts["yfinance"] += 1
            return ticker, info
        except Exception as exc:
            log.debug("Info fetch failed for %s: %s", ticker, exc)
            return ticker, {}

    info_map: dict[str, dict] = {}
    # max_workers=5 mirrors the Yahoo screener thread limit to avoid rate-limiting
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch_info, t): t for t in tickers}
        for fut in as_completed(futures):
            t, info = fut.result()
            info_map[t] = info

    # ── Combine history + info; fallback to individual call if both are empty ──
    for ticker in tickers:
        avg_vol_20, cur_vol, vol_ratio, hi52, lo52, rsi14, ma50, ma200, perf_20d = _hist_stats(ticker)
        info = info_map.get(ticker, {})

        # If the batch produced nothing useful for this ticker, fall back entirely
        if not info and avg_vol_20 == 0.0:
            log.debug("Batch empty for %s — falling back to individual get_yfinance_data()", ticker)
            results[ticker] = get_yfinance_data(ticker)
            continue

        results[ticker] = {
            "company_name":   info.get("longName") or info.get("shortName") or ticker,
            "sector":         info.get("sector") or "",
            "industry":       info.get("industry") or "",
            "market_cap":     info.get("marketCap"),
            "short_ratio":    info.get("shortRatio") or 0.0,
            "short_float_yf": (info.get("shortPercentOfFloat") or 0.0) * 100,
            # Prefer info 52w values; use batch hi/lo as fallback
            "52w_high":       info.get("fiftyTwoWeekHigh") or hi52,
            "52w_low":        info.get("fiftyTwoWeekLow")  or lo52,
            "avg_vol_20d":    avg_vol_20,
            "cur_vol":        cur_vol,
            "vol_ratio":      vol_ratio,
            "float_shares":   info.get("floatShares") or 0,
            "inst_ownership": info.get("institutionHeldPercentOutstanding")
                              or info.get("institutionsPercentHeld"),
            "rsi14":          rsi14,
            "ma50":           ma50,
            "ma200":          ma200,
            "perf_20d":       perf_20d,
        }

        # change_5d aus Batch-History
        try:
            _df = hist_batch if len(tickers) == 1 else hist_batch[ticker]
            if _df is not None and len(_df) >= 6:
                results[ticker]["change_5d"] = round(
                    (float(_df["Close"].iloc[-1]) - float(_df["Close"].iloc[-6])) /
                    float(_df["Close"].iloc[-6]) * 100, 2
                )
        except Exception:
            pass

    return results


def get_yahoo_news(ticker: str, n: int = 5) -> list[dict]:
    try:
        stk  = yf.Ticker(ticker)
        raw  = (stk.news or [])[:n]
        news = []
        for item in raw:
            # yfinance ≥ 0.2.x nests content inside item["content"]
            content = item.get("content", item)
            pub_ts = (
                content.get("pubDate")
                or content.get("providerPublishTime")
                or item.get("providerPublishTime")
                or 0
            )
            if isinstance(pub_ts, str):
                try:
                    pub_ts = int(datetime.fromisoformat(pub_ts.rstrip("Z")).timestamp())
                except Exception:
                    pub_ts = 0
            pub_ts = int(pub_ts) if pub_ts else 0
            ts_str = (
                datetime.fromtimestamp(pub_ts).strftime("%d.%m.%Y %H:%M")
                if pub_ts else ""
            )
            title_orig = content.get("title") or item.get("title") or ""
            # Collect every candidate field that might carry article body text.
            # yfinance uses different field names across versions.
            raw_summary = (
                content.get("body")
                or content.get("summary")
                or content.get("description")
                or content.get("snippet")
                or item.get("body")
                or item.get("summary")
                or item.get("description")
                or item.get("snippet")
                or ""
            ).strip()
            # If the "summary" is just a copy of the title, discard it.
            if raw_summary and raw_summary.strip(".").strip() == title_orig.strip(".").strip():
                raw_summary = ""

            news.append({
                "title":       _translate(title_orig) if title_orig else "",
                "title_orig":  title_orig,
                "summary_raw": raw_summary,
                "publisher":   (content.get("provider", {}) or {}).get("displayName")
                                or content.get("publisher")
                                or item.get("publisher") or "Yahoo Finance",
                "source":      "Yahoo Finance",
                "link":        (content.get("canonicalUrl", {}) or {}).get("url")
                                or content.get("link")
                                or item.get("link") or "#",
                "time":        ts_str,
                "ts":          pub_ts,
            })
        return news
    except Exception as exc:
        log.warning("News error for %s: %s", ticker, exc)
        return []


def _rss_news(ticker: str, url: str, source_label: str) -> list[dict]:
    """Fetch and parse a generic RSS/Atom feed; return normalised news items."""
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=8)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        # Support both RSS (<channel><item>) and Atom (<entry>)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        result = []
        for item in items[:5]:
            title = (
                item.findtext("title")
                or item.findtext("atom:title", namespaces=ns)
                or ""
            ).strip()
            link = (
                item.findtext("link")
                or (item.find("atom:link", ns) or ET.Element("x")).get("href", "")
                or "#"
            ).strip()
            pub_str = (
                item.findtext("pubDate")
                or item.findtext("atom:published", namespaces=ns)
                or item.findtext("atom:updated", namespaces=ns)
                or ""
            ).strip()
            ts = 0
            if pub_str:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                            "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        ts = int(datetime.strptime(pub_str, fmt).timestamp())
                        break
                    except ValueError:
                        pass
                if not ts:
                    try:
                        ts = int(parsedate_to_datetime(pub_str).timestamp())
                    except Exception:
                        pass
            ts_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else ""
            if title:
                result.append({
                    "title":       _translate(title),
                    "title_orig":  title,
                    "summary_raw": "",
                    "publisher":   source_label,
                    "source":      source_label,
                    "link":        link,
                    "time":        ts_str,
                    "ts":          ts,
                })
        return result
    except Exception as exc:
        log.debug("%s RSS error for %s: %s", source_label, ticker, exc)
        return []


def get_combined_news(ticker: str, n: int = 3) -> list[dict]:
    """Merge Yahoo Finance, Seeking Alpha, and Finviz news; return top n by date."""
    base_upper = ticker.split(".")[0].upper()

    yahoo_items = get_yahoo_news(ticker, n=5)
    sa_items    = _rss_news(
        ticker,
        f"https://seekingalpha.com/api/sa/combined/{base_upper}.xml",
        "Seeking Alpha",
    )
    fv_items    = _rss_news(
        ticker,
        f"https://finviz.com/rss.ashx?t={base_upper}",
        "Finviz",
    )

    n_yahoo, n_sa, n_fv = len(yahoo_items), len(sa_items), len(fv_items)
    combined = yahoo_items + sa_items + fv_items
    combined.sort(key=lambda x: x.get("ts", 0), reverse=True)
    result = combined[:n]
    print(f"News {ticker}: {n_yahoo} Yahoo + {n_sa} SeekingAlpha + {n_fv} Finviz = {len(result)} Meldungen")
    return result


# ===========================================================================
# 2a-OPT. OPTIONS MARKET DATA (US-only, stable expiry ≥ IV_MIN_DAYS_TO_EXPIRY)
# ===========================================================================

def get_options_data(ticker: str) -> dict:
    """Fetch Put/Call ratio (open interest) and ATM implied volatility.
    US-only — skipped for international tickers.

    Uses the first expiry at least IV_MIN_DAYS_TO_EXPIRY days away to avoid
    Time-Decay distortion of near-expiry options.  Falls back to expiries[0]
    if no qualifying expiry exists.

    Returns dict with keys:
      pc_ratio  (float | None)  — put OI / call OI for chosen expiry
      atm_iv    (float | None)  — implied volatility of the nearest-ATM strike (0–1 scale)
      expiry    (str | None)    — expiry date used (YYYY-MM-DD)

    Any error (no options data, API failure, etc.) returns {} so callers can
    treat missing data uniformly with s.get("options", {}).
    """
    if "." in ticker:  # international ticker — options data unreliable / unavailable
        return {}
    try:
        stk      = yf.Ticker(ticker)
        expiries = stk.options  # tuple of expiry date strings
        if not expiries:
            return {}

        # Choose the first expiry at least IV_MIN_DAYS_TO_EXPIRY days away
        from datetime import datetime as _dt, timedelta as _td
        min_date = _dt.today() + _td(days=IV_MIN_DAYS_TO_EXPIRY)
        valid    = [e for e in expiries if _dt.strptime(e, "%Y-%m-%d") >= min_date]
        chosen   = valid[0] if valid else expiries[0]

        chain    = stk.option_chain(chosen)
        calls    = chain.calls
        puts     = chain.puts
        if calls.empty or puts.empty:
            return {}

        # Put/Call ratio by open interest
        total_call_oi = calls["openInterest"].fillna(0).sum()
        total_put_oi  = puts["openInterest"].fillna(0).sum()
        pc_ratio = (total_put_oi / total_call_oi) if total_call_oi > 0 else None

        # ATM IV: find the call strike closest to current price
        cur_price = stk.fast_info.get("lastPrice") or stk.fast_info.get("regularMarketPrice")
        if cur_price is None:
            atm_iv = None
        else:
            calls_iv = calls[["strike", "impliedVolatility"]].dropna()
            if not calls_iv.empty:
                idx    = (calls_iv["strike"] - cur_price).abs().idxmin()
                atm_iv = float(calls_iv.loc[idx, "impliedVolatility"])
            else:
                atm_iv = None

        days_to_expiry = (_dt.strptime(chosen, "%Y-%m-%d") - _dt.today()).days
        if atm_iv is not None:
            print(f"{ticker} IV: Verfallstermin {chosen} ({days_to_expiry} Tage), "
                  f"ATM-IV={atm_iv * 100:.1f}%")

        return {"pc_ratio": pc_ratio, "atm_iv": atm_iv, "expiry": chosen}
    except Exception as exc:
        log.debug("Options data failed for %s: %s", ticker, exc)
        return {}


def get_earnings_date(ticker: str) -> tuple[int | None, str | None]:
    """Return (days_until_earnings, date_str_DE) from yfinance calendar.

    Returns (None, None) if no upcoming earnings found or yfinance errors.
    Only looks at future dates (days >= 0).
    """
    try:
        import pandas as _pd
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None, None
        dates: list = []
        if isinstance(cal, _pd.DataFrame) and not cal.empty:
            dates = list(cal.columns)
        elif isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("earningsDate") or []
            if not isinstance(raw, list):
                raw = [raw]
            dates = raw
        today = datetime.now(ZoneInfo("America/New_York")).date()
        for d in dates:
            try:
                edate = _pd.Timestamp(d).date()
                days  = (edate - today).days
                if days >= 0:
                    return days, edate.strftime("%d.%m.")
            except Exception:
                continue
    except Exception as exc:
        log.debug("Earnings date failed for %s: %s", ticker, exc)
    return None, None


_SEC_HEADERS = {"User-Agent": "SqueezeReport/1.0 github-actions@squeeze-report.com"}
_13F_KEYWORDS = {"increase", "added", "new position", "added to"}


def fetch_sec_13f(ticker: str) -> str | None:
    """Check SEC EDGAR for recent 13F filings (last 90 days) for the given ticker.

    Returns a short note string if a filing with "increase"/"added" keywords is
    found, otherwise None. Silently returns None on HTTP 403 or any error.
    US-only; international tickers are skipped immediately.
    """
    if "." in ticker:
        return None
    from datetime import timedelta, timezone as _tz

    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={ticker}&type=13F"
        "&dateb=&owner=include&count=3&output=atom"
    )
    cutoff = datetime.now(_tz.utc) - timedelta(days=90)
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=12)
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        text = re.sub(r' xmlns="[^"]+"', "", resp.text, count=1)
        root = ET.fromstring(text)
        for entry in root.findall("entry"):
            updated = (entry.findtext("updated") or "").strip()
            try:
                dt = datetime.fromisoformat(updated)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass  # date parse failed; still check title
            title = (entry.findtext("title") or "").lower()
            if any(kw in title for kw in _13F_KEYWORDS):
                return "Institutionelle Käufe gemeldet"
    except Exception as exc:
        log.debug("SEC 13F failed for %s: %s", ticker, exc)
    return None


# ===========================================================================
# 2b. SUPPLEMENTARY DATA SOURCES (FINRA CSV + SEC EDGAR FTD)
# ===========================================================================

# Mutable counters updated by the API functions during each run
_finra_stats: dict = {"ok": 0, "empty": 0, "err": 0}

# HTTP-request counters for the runtime summary
_req_counts: dict = {"finra": 0, "yahoo": 0, "yfinance": 0}

# Module-level cache: {date_str → {ticker → short_interest}} loaded once per run
_finra_csv_cache: dict[str, dict[str, int]] = {}


def _load_finra_csv(date_str: str) -> dict[str, int]:
    """Download and parse FINRA daily short-volume files from CDN.

    Opt 4 — The three exchange files (CNMS, FNSQ, FNQC) for a single date are
    fetched in parallel via ThreadPoolExecutor(max_workers=3) rather than
    sequentially.  Across dates the caller (Step 2a) also parallelises.

    Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
    Returns {ticker: short_volume} or {} on failure.
    """
    urls = [
        f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNSQshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNQCshvol{date_str}.txt",
    ]

    def _fetch_one(url: str) -> dict[str, int]:
        """Fetch + parse a single FINRA CDN file; returns partial {ticker: sv}."""
        partial: dict[str, int] = {}
        filename = url.split("/")[-1]
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
            _req_counts["finra"] += 1
            if r.status_code != 200:
                print(f"FINRA CDN nicht verfügbar: {filename} → HTTP {r.status_code}")
                return partial
            lines = r.text.splitlines()
            header = [h.strip().lower() for h in lines[0].split("|")]
            try:
                sym_idx = next(i for i, h in enumerate(header)
                               if "symbol" in h or "ticker" in h)
                sv_idx  = next(i for i, h in enumerate(header)
                               if "shortvol" in h.replace(" ", "") and "exempt" not in h)
            except StopIteration:
                sym_idx, sv_idx = 1, 2   # fixed CDN column order fallback
            for line in lines[1:]:
                parts = line.split("|")
                if len(parts) <= max(sym_idx, sv_idx):
                    continue
                ticker = parts[sym_idx].strip().upper()
                try:
                    sv_val = int(parts[sv_idx].strip().replace(",", ""))
                except ValueError:
                    continue
                if ticker and sv_val > 0:
                    partial[ticker] = partial.get(ticker, 0) + sv_val
            print(f"FINRA CDN {date_str}: {filename} — {len(partial)} Ticker geladen",
                  flush=True)
        except Exception as exc:
            print(f"FINRA CDN Fehler bei {filename}: {exc}", flush=True)
        return partial

    # Opt 4: fetch all three exchange files for this date in parallel
    merged: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for partial in ex.map(_fetch_one, urls):
            for t, v in partial.items():
                merged[t] = merged.get(t, 0) + v
    return merged


def _get_finra_csv_for_date(date_str: str) -> dict[str, int]:
    """Return cached CSV data for date_str, loading it if needed."""
    if date_str not in _finra_csv_cache:
        _finra_csv_cache[date_str] = _load_finra_csv(date_str)
    return _finra_csv_cache[date_str]


_FINRA_DATES_CACHE_FILE  = "finra_dates_cache.json"
_FINRA_DATES_CACHE_TTL_S = 7200   # 2 Stunden in Sekunden


def _latest_finra_dates(n: int = 3) -> list[str]:
    """Find the n most recent FINRA CDN daily-short-volume dates by probing
    backwards from yesterday (max 14 trading days). The CDN publishes one
    file per trading day (no weekends). Returns list of YYYYMMDD strings,
    newest first.

    Opt 8: Result cached in finra_dates_cache.json for _FINRA_DATES_CACHE_TTL_S
    seconds to avoid repeated HTTP HEAD requests on manual re-runs.
    """
    from datetime import date, timedelta

    # Try cache first
    try:
        with open(_FINRA_DATES_CACHE_FILE, "r", encoding="utf-8") as _cf:
            _cache = json.load(_cf)
        _age = time.time() - _cache.get("ts", 0)
        if _age < _FINRA_DATES_CACHE_TTL_S and _cache.get("dates"):
            log.info("FINRA Datumssuche: Cache-Hit (%.0f s alt)", _age)
            print(f"FINRA Datumssuche: gecacht ({_age:.0f}s alt): {_cache['dates']}", flush=True)
            return _cache["dates"][:n]
    except Exception:
        pass  # cache miss or corrupt — proceed with HTTP probe

    found: list[str] = []
    today = date.today()
    for delta in range(1, 20):   # start from yesterday (delta=1)
        if len(found) >= n:
            break
        day = today - timedelta(days=delta)
        if day.weekday() >= 5:   # skip weekends
            continue
        date_str = day.strftime("%Y%m%d")
        probe = (f"https://cdn.finra.org/equity/regsho/daily/"
                 f"CNMSshvol{date_str}.txt")
        try:
            r = requests.head(probe, headers=HTTP_HEADERS, timeout=10)
            if r.status_code == 200:
                found.append(date_str)
                continue
            # HEAD blocked on some CDNs → fall back to streaming GET
            if r.status_code in (403, 405, 404):
                rg = requests.get(probe, headers=HTTP_HEADERS,
                                  timeout=10, stream=True)
                rg.close()
                if rg.status_code == 200:
                    found.append(date_str)
        except Exception:
            continue

    if not found:
        # CDN probe completely failed — try stale cache as fallback (up to 24h old)
        print("FINRA Datumssuche: 0 Daten gefunden — CDN nicht erreichbar oder alle "
              "Probes fehlgeschlagen", flush=True)
        try:
            with open(_FINRA_DATES_CACHE_FILE, "r", encoding="utf-8") as _cf:
                _stale = json.load(_cf)
            _stale_dates = _stale.get("dates", [])
            _stale_age   = time.time() - _stale.get("ts", 0)
            if _stale_dates and _stale_age < 86400:
                print(f"FINRA Datumssuche: Verwende Stale-Cache ({_stale_age/3600:.1f}h alt): "
                      f"{_stale_dates}", flush=True)
                return _stale_dates[:n]
        except Exception:
            pass
        print("FINRA Datumssuche: Kein Fallback-Cache verfügbar — SI-Trend zeigt '—'",
              flush=True)
        return []

    # Write/update cache only when probe succeeded
    try:
        with open(_FINRA_DATES_CACHE_FILE, "w", encoding="utf-8") as _cf:
            json.dump({"ts": time.time(), "dates": found}, _cf)
    except Exception:
        pass

    print(f"FINRA Datumssuche: {len(found)} Daten gefunden: {found}", flush=True)
    return found


def get_finra_short_interest(ticker: str,
                             dates: list[str] | None = None) -> dict:
    """Lookup daily short volume for ticker from FINRA CDN files.
    `dates` should be pre-computed by _latest_finra_dates() once per run.
    Returns dict with short_interest (= short volume), history, trend,
    trend_pct or {}.
    """
    if dates is None:
        dates = []
    if not dates:
        _finra_stats["empty"] += 1
        return {}

    sym = ticker.strip().upper()
    _FINRA_MIN_VOL  = 1        # any non-zero value counts; CSV parser already drops sv=0
    _TREND_MIN_VOL  = 100      # min short-vol for a meaningful trend data point

    history: list[dict] = []
    for date_str in dates:
        data = _get_finra_csv_for_date(date_str)
        si_val = data.get(sym, 0)
        hit = sym in data
        print(f"FINRA Ticker-Suche: {sym} [{date_str}] → "
              f"{'Treffer' if hit else 'Kein Treffer'}: {si_val:,}", flush=True)
        if si_val >= _FINRA_MIN_VOL:
            sd = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            history.append({"short_interest": si_val, "settlement_date": sd})

    if not history:
        _finra_stats["empty"] += 1
        return {}

    # Only include data points ≥ _TREND_MIN_VOL (100) in trend calc
    # Cap output to [-95 %, +500 %] to suppress data artefacts
    # Classification uses raw (uncapped) value; only the stored pct is capped.
    trend, trend_pct = "no_data", 0.0
    significant = [p for p in history if p["short_interest"] >= _TREND_MIN_VOL]
    if len(significant) >= SI_TREND_MIN_DATAPOINTS:
        newest = significant[0]["short_interest"]
        oldest = significant[-1]["short_interest"]
        raw_pct = (newest - oldest) / oldest
        if raw_pct >= SI_TREND_UP_THRESHOLD:
            trend = "up"
        elif raw_pct <= SI_TREND_DOWN_THRESHOLD:
            trend = "down"
        else:
            trend = "sideways"
        trend_pct = max(-0.95, min(5.0, raw_pct))
        if _finra_stats.get("ok", 0) < 5:
            print(f"{sym} FINRA trend: oldest={oldest:,}, newest={newest:,}, "
                  f"trend_pct={trend_pct*100:.1f}%, trend={trend}", flush=True)

    # SI Velocity: average daily share change (newest − oldest) / n data points
    si_velocity   = 0.0
    si_accelerating = False
    if len(history) >= 2:
        newest_v = history[0]["short_interest"]
        oldest_v = history[-1]["short_interest"]
        si_velocity = (newest_v - oldest_v) / len(history)

    # Acceleration: each of the last 3 steps larger than the previous
    if len(history) >= 3:
        s0 = history[0]["short_interest"]
        s1 = history[1]["short_interest"]
        s2 = history[2]["short_interest"]
        d_old = s1 - s2   # older step
        d_new = s0 - s1   # newer step
        si_accelerating = d_old > 0 and d_new > 0 and d_new > d_old

    _finra_stats["ok"] += 1
    log.info("%s FINRA history=%d Punkte, trend=%s, velocity=%.0f/day, accel=%s",
             sym, len(history), trend, si_velocity, si_accelerating)
    return {
        "short_interest":      history[0]["short_interest"],
        "prev_short_interest": history[1]["short_interest"] if len(history) >= 2 else 0,
        "settlement_date":     history[0]["settlement_date"],
        "history":             history,
        "trend":               trend,
        "trend_pct":           round(trend_pct * 100, 1),
        "si_velocity":         round(si_velocity, 0),
        "si_accelerating":     si_accelerating,
    }


# ── SEC EDGAR FTD ─────────────────────────────────────────────────────────────
# Permanently disabled: SEC EDGAR ZIP endpoint and Nasdaq Data Link both return
# HTTP 403 from GitHub Actions IP ranges. FTD_BONUS_MAX = 0.

def get_sec_ftd(ticker: str, _cache: dict = {}) -> dict:
    """Disabled stub – SEC EDGAR and Nasdaq Data Link blocked on GitHub Actions."""
    return {}



def score_bonus(stock: dict) -> float:
    """Optional bonus points (0 – FINRA_BONUS_MAX).
    FINRA: up to 5 pts if daily short volume rose.
    Condition: ≥ 2 of the 3 FINRA data points must be > 100 shares.
    FTD bonus permanently disabled (IP-blocked on GitHub Actions).
    """
    ticker = stock.get("ticker", "?")
    finra  = stock.get("finra_data") or {}
    hist   = finra.get("history", [])

    # Extract the three raw values
    t1 = hist[0]["short_interest"] if len(hist) >= 1 else None
    t2 = hist[1]["short_interest"] if len(hist) >= 2 else None
    t3 = hist[2]["short_interest"] if len(hist) >= 3 else None

    # Korrektur 3: bonus only when ≥ 2 of [t1, t2, t3] are > 100
    if sum(1 for v in [t1, t2, t3] if v and v > 100) >= 2:
        trend       = finra.get("trend", "no_data")
        accelerating = finra.get("si_accelerating", False)
        if trend == "up":
            if accelerating:
                bonus = float(FINRA_ACCELERATION_BONUS)
                print(f"{ticker} FINRA-Bonus: +{bonus} Pkt (Trend=up + Beschleunigung)", flush=True)
            else:
                bonus = float(FINRA_BONUS_MAX)
        elif trend == "sideways":
            bonus = FINRA_BONUS_MAX / 2
        else:
            bonus = 0.0
    else:
        bonus = 0.0
        print(f"{ticker}: bonus=0.00 (unzureichende FINRA-Daten: "
              f"T1={t1}, T2={t2}, T3={t3})", flush=True)

    return round(min(bonus, float(FINRA_ACCELERATION_BONUS)), 2)


def _fmt_si_date(date_str: str) -> str:
    """Convert FINRA settlement date 'YYYY-MM-DD' to German 'DD.MM.YYYY'."""
    if date_str and len(date_str) >= 10:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            pass
    return date_str or "—"


def _fmt_si_record(rec: dict) -> str:
    """Format a FINRA daily short-volume record.
    ≥ 1 000 000 shares → 'X,X Mio.'  |  < 1 000 000 → 'X,XXX Aktien'
    """
    si = rec.get("short_interest", 0)
    if not si:
        return "—"
    date_s = _fmt_si_date(rec.get("settlement_date", ""))
    if si >= 1_000_000:
        return f"{si / 1_000_000:,.1f} Mio. ({date_s})"
    return f"{si:,} Aktien ({date_s})"


# ===========================================================================
# 3. SCORING & ANALYSIS
# ===========================================================================

# Score-Gewichtung Fall 1 (Short-Daten vorhanden):
# Short Float %        → max 32 Pkt  (Sättigung bei 100 %)
# Short Ratio (Days)   → max 23 Pkt  (Sättigung bei 20 Tagen)
# Rel. Volumen         → max 23 Pkt  (Sättigung bei 5× Durchschnitt)
# Kursmomentum (1T)    → max 14 Pkt  (nur positive Tagesveränderung, Sättigung bei +15 %)
# Float-Größe          → max  8 Pkt  (≤30 Mio. Aktien = voll, ≥50 Mio. = 0, linear)
# Gesamt               → max 100 Pkt
#
# Verifikation (Float=0 angenommen wo nicht angegeben):
# A: SF=30%, DTC=5d,  RVOL=2×, Mom=+3%, Float=60M  → Score  47.45
# B: SF=50%, DTC=8d,  RVOL=3×, Mom=+5%, Float=20M  → Score  90.15
# C: SF=80%, DTC=12d, RVOL=4×, Mom=+8%, Float=5M   → Score 100.00
def _safe_float(v, default: float = 0.0) -> float:
    """Convert v to float, returning default for None / NaN / Inf / non-numeric."""
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def score(stock: dict) -> float:
    """Weighted squeeze score 0–100.
    When no short data is available (sf=0, sr=0) the score is capped at 50
    so these stocks can appear in the top 10 but never displace a stock with
    confirmed high short interest.
    """
    sf_val = _safe_float(stock.get("short_float", 0))
    sr_val = _safe_float(stock.get("short_ratio", 0))
    rv_raw = min((_safe_float(stock.get("rel_volume", 0)) - 1.0) / 2.0, 1.0)  # sättigt bei 3× statt 5×

    # Float-size factor: small float amplifies squeeze pressure
    _float = stock.get("float_shares") or 0
    if _float > 0:
        _fs = max(0.0, min(1.0,
            (FLOAT_SATURATION_HIGH - _float) /
            (FLOAT_SATURATION_HIGH - FLOAT_SATURATION_LOW)
        )) * FLOAT_WEIGHT
    else:
        _fs = 0.0

    # Marktkontext: Momentum relativ zum S&P 500 anpassen
    _chg_raw = _safe_float(stock.get("change", 0))
    if USE_RELATIVE_MOMENTUM:
        _spx_d = _safe_float(stock.get("spx_daily_perf", 0.0))
        adjusted_chg = _chg_raw - _spx_d   # z.B. +3% Aktie, −2% SPX → +5% rel.
    else:
        adjusted_chg = _chg_raw

    if sf_val == 0 and sr_val == 0:
        # Fall 2: keine Short-Daten → Volumen (max 30) + Momentum (max 20), Cap 50
        # Nur positive Tagesveränderungen zählen: fallende Kurse = kein Squeeze-Druck
        rv_component = rv_raw * 30
        chg = max(adjusted_chg, 0)
        momentum = min(chg /  8.0, 1.0) * 20  # sättigt bei +8% statt +15%
        result = min(round(rv_component + momentum + _fs, 2), 50.0)
        return result if math.isfinite(result) else 0.0

    # Fall 1: Short-Daten vorhanden → fünf Faktoren, max 100 Pkt
    # Nur positive Tagesveränderungen zählen: fallende Kurse = kein Squeeze-Druck
    sf  = min(sf_val /  50.0, 1.0) * 32  # sättigt bei 50% statt 100%
    sr  = min(sr_val /  10.0, 1.0) * 23  # sättigt bei 10d statt 20d
    rv  = rv_raw * 23
    mom = min(max(adjusted_chg, 0) /  8.0, 1.0) * 14  # sättigt bei +8% statt +15%

    # Kombinationssignal-Bonus: ≥ 3 von 4 Faktoren gleichzeitig stark
    _combo_conditions = [
        sf_val >= 30,                                         # Short Float ≥ 30 %
        sr_val >= 5,                                          # Days to Cover ≥ 5d
        stock.get("rel_volume", 0) >= 2.0,                   # Rel. Volumen ≥ 2×
        (stock.get("finra_data") or {}).get("trend") == "up", # SI-Trend steigend
    ]
    _n_combo = sum(_combo_conditions)
    if _n_combo >= 3:
        _pts = float(COMBO_BONUS)
        print(f"{stock.get('ticker', '?')} Kombinations-Bonus: +{_pts} Pkt ({_n_combo}/4 Bedingungen)",
              flush=True)
    else:
        _pts = 0.0

    result = round(min(sf + sr + rv + mom + _fs + _pts, 100.0), 2)
    return result if math.isfinite(result) else 0.0


def fmt_cap(v) -> str:
    if not v:
        return "N/A"
    v = float(v)
    if v >= 1e9:
        return f"${v/1e9:.1f} B"
    if v >= 1e6:
        return f"${v/1e6:.0f} M"
    return f"${v:,.0f}"


# ===========================================================================
# SCORE HISTORY — smoothing across trading days
# ===========================================================================

def _load_score_history() -> dict:
    """Opt 7 — Load history and immediately prune stale entries at read time.

    Entries older than _SCORE_HISTORY_DAYS (14) are dropped on load so
    _save_score_history() only serialises what is still needed — no second pass.
    """
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=_SCORE_HISTORY_DAYS)).strftime("%Y-%m-%d")
    try:
        with open(_SCORE_HISTORY_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    # Drop entries older than cutoff; drop tickers with no remaining entries
    pruned = {
        ticker: [e for e in entries if e.get("date", "") >= cutoff]
        for ticker, entries in raw.items()
    }
    return {k: v for k, v in pruned.items() if v}


def _save_score_history(history: dict, _dirty: bool = True) -> None:
    """Opt 7 — Write history to disk only when _dirty=True (changed since load).

    Pruning is done at load time; this function only serialises what remains.
    """
    if not _dirty:
        return
    with open(_SCORE_HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)


def apply_score_smoothing(stocks: list[dict], today: str) -> None:
    """Smooth each stock's score in-place using historical data and save history.

    Weighted formula: displayed_score = TODAY_WEIGHT * raw + HISTORY_WEIGHT * avg(last 3 runs)
    Sets s["score_label"] to "Ø 3T" when history contributed, else "Erster Run".
    """
    # Opt 5: load once (pruning happens at load time); track dirty state
    history = _load_score_history()
    _dirty  = False

    for s in stocks:
        ticker    = s["ticker"]
        today_raw = s["score"]

        # Past entries (exclude today to avoid double-counting)
        past = sorted(
            [e for e in history.get(ticker, []) if e.get("date", "") != today],
            key=lambda x: x.get("date", ""),
            reverse=True,
        )[:3]

        if len(past) >= 2:
            # Smoothing greift nur ab 2 Vorläufen — neue Ticker bekommen keinen Abzug
            hist_avg = sum(e["score"] for e in past) / len(past)
            smoothed = SCORE_TODAY_WEIGHT * today_raw + SCORE_HISTORY_WEIGHT * hist_avg
            s["score"] = round(min(smoothed, 100.0), 1)
        # else (0 or 1 past entry): keep raw score — no smoothing penalty for new tickers

        # Score-Trend-Bonus/-Malus: continous rise/fall over SCORE_TREND_DAYS
        if len(past) >= SCORE_TREND_DAYS:
            trend_entries = past[:SCORE_TREND_DAYS][::-1]  # ascending: oldest → newest
            _tscores = [e["score"] for e in trend_entries]
            if all(_tscores[i] < _tscores[i + 1] for i in range(len(_tscores) - 1)):
                s["score"] = round(min(s["score"] + SCORE_TREND_BONUS, 100.0), 1)
            elif all(_tscores[i] > _tscores[i + 1] for i in range(len(_tscores) - 1)):
                s["score"] = round(max(s["score"] - SCORE_TREND_MALUS, 0.0), 1)

        # Store today's raw score only if it differs from what's already there
        existing = [e for e in history.get(ticker, []) if e.get("date", "") == today]
        if not existing or existing[0]["score"] != today_raw:
            entries = [e for e in history.get(ticker, []) if e.get("date", "") != today]
            entries.append({"date": today, "score": today_raw})
            history[ticker] = entries
            _dirty = True   # mark that history was modified and needs saving

        # Sparkline data: last 7 calendar entries (oldest → newest) for this ticker
        all_entries = sorted(
            [e for e in history[ticker]],
            key=lambda x: x.get("date", ""),
        )[-7:]
        if len(all_entries) >= 2:
            spark_scores = [round(e["score"], 1) for e in all_entries]
            spark_dates  = [e["date"] for e in all_entries]   # ISO YYYY-MM-DD; JS parses weekday
            delta = spark_scores[-1] - spark_scores[0]
            if delta >= 3:
                spark_trend = f"↑ +{delta:.1f} Pkt"
                spark_col   = "#22c55e"
            elif delta <= -3:
                spark_trend = f"↓ {delta:.1f} Pkt"
                spark_col   = "#ef4444"
            else:
                spark_trend = "→ stabil"
                spark_col   = "#94a3b8"
            s["sparkline"] = {
                "scores": spark_scores,
                "dates":  spark_dates,
                "trend":  spark_trend,
                "col":    spark_col,
                "today":  today,
            }
        else:
            s["sparkline"] = None

    # Opt 5: write only when something actually changed (dirty flag)
    _save_score_history(history, _dirty)
    log.info("Score smoothing applied; history %s",
             f"saved to {_SCORE_HISTORY_FILE}" if _dirty else "unchanged (skip write)")


def risk_assessment(stock: dict) -> tuple[str, str, str]:
    """Returns (level_de, hex_color, reason)."""
    pts = 0
    reasons = []

    sf = stock.get("short_float", 0)
    if sf > 40:
        pts += 2
        reasons.append(
            f"Extrem hohes Short-Interesse ({sf:.1f} %) bedeutet massive Squeeze-Gefahr, "
            "aber auch starke Kursausschläge in beide Richtungen."
        )
    elif sf > 25:
        pts += 1
        reasons.append(f"Hohes Short-Interesse ({sf:.1f} %) erhöht die Volatilität deutlich.")

    cap = stock.get("market_cap") or stock.get("yf_market_cap")
    if cap:
        if cap < 300e6:
            pts += 2
            reasons.append(
                f"Micro-Cap ({fmt_cap(cap)}) – geringe Liquidität, Kursmanipulation möglich."
            )
        elif cap < 2e9:
            pts += 1
            reasons.append(f"Small-Cap ({fmt_cap(cap)}) mit eingeschränkter Liquidität.")

    rv = stock.get("rel_volume", 0)
    if rv > 5:
        pts += 1
        reasons.append(
            f"Extremer Volumenanstieg ({rv:.1f}×) kann auf koordiniertes Kaufinteresse hinweisen."
        )

    if pts >= 3:
        return "HOCH",   "#ef4444", " ".join(reasons[:2])
    if pts >= 1:
        return "MITTEL", "#f59e0b", " ".join(reasons[:2])
    return  "NIEDRIG", "#22c55e", "Moderates Risikoprofil für einen Squeeze-Kandidaten."


def short_situation(stock: dict) -> str:
    parts = []
    sf = stock.get("short_float", 0)
    sr = stock.get("short_ratio", 0)
    rv = stock.get("rel_volume", 0)
    chg = stock.get("change", 0)
    has_short_data = sf > 0 or sr > 0

    if has_short_data:
        if sf > 30:
            parts.append(f"Short Float {sf:.1f} % — sehr hohes Leerverkaufsinteresse, starkes Squeeze-Potenzial.")
        elif sf > 0:
            parts.append(f"Short Float {sf:.1f} % liegt deutlich über dem Marktdurchschnitt.")
        if sr > 5:
            parts.append(f"Short Ratio {sr:.1f} Tage — Eindeckungsdruck erhöht den Squeeze-Druck.")

    if rv >= 2.0:
        parts.append(f"Volumen bei {rv:.1f}× dem Durchschnitt — erhöhtes Kaufinteresse erkennbar.")
    if chg > 5:
        parts.append(f"+{chg:.1f} % heute — mögliche Margin Calls bei Leerverkäufern.")
    elif chg < -3:
        parts.append(f"{chg:.1f} % heute — Short-Interesse könnte kurzfristig steigen.")

    if not has_short_data and not parts:
        parts.append("Ungewöhnlicher Volumenanstieg ohne verfügbare Short-Daten.")

    return " ".join(parts[:2]) if parts else "Keine eindeutigen Trendsignale erkennbar."


def news_summary(news_list: list[dict]) -> str:
    """Return a complete German-language summary of the most important news item."""
    if not news_list:
        return "Keine aktuellen Nachrichten verfügbar."
    top = news_list[0]

    # 1. Best case: article has a real body/summary – translate and return it fully.
    raw = top.get("summary_raw", "").strip()
    if raw and len(raw) > 100:
        translated = _translate(raw[:2500])
        if translated and len(translated) > 60:
            return translated

    # 2. No article body available (common with yfinance).
    #    Build a meaningful German-language synthesis from all available titles
    #    plus publisher context so the reader gets genuine orientation.
    titles_orig = [
        (n.get("title_orig") or n.get("title", "")).rstrip(".")
        for n in news_list
        if n.get("title_orig") or n.get("title")
    ]
    if not titles_orig:
        return "Keine Nachrichteninhalte verfügbar."

    if len(titles_orig) == 1:
        to_translate = titles_orig[0]
    else:
        # Combine both headlines into one coherent sentence for the translator
        to_translate = f"{titles_orig[0]}. Weitere aktuelle Meldung: {titles_orig[1]}"

    translated = _translate(to_translate[:2500])
    result = translated if translated else to_translate

    # Append source/date so the user knows the freshness and origin.
    pub = top.get("publisher", "")
    ts  = top.get("time", "")
    if pub and ts:
        result += f"  –  Quelle: {pub} ({ts})"
    elif pub:
        result += f"  –  Quelle: {pub}"

    return result


# ===========================================================================
# 4. HTML REPORT
# ===========================================================================

def _metric_color(kind: str, val: float) -> str:
    """Return hex color for a metric tile based on defined squeeze thresholds."""
    G, O, R = "#22c55e", "#f59e0b", "#ef4444"
    if kind == "sf":   # Short Float — higher = stronger signal → green
        return G if val >= SF_GREEN else (O if val >= SF_ORANGE else R)
    if kind == "sr":   # Days to Cover — higher = stronger signal → green
        return G if val >= SR_GREEN else (O if val >= SR_ORANGE else R)
    if kind == "rv":   # Rel. Volume — higher = stronger signal → green
        return G if val >= RV_GREEN else (O if val >= RV_ORANGE else R)
    if kind == "mom":  # Kursmomentum — higher = stronger signal → green
        return G if val >= MOM_GREEN else (O if val >= MOM_ORANGE else R)
    return "#94a3b8"


def _score_color(sc: float) -> str:
    return "#22c55e" if sc >= 50 else ("#f59e0b" if sc >= 30 else "#ef4444")


def _card(i: int, s: dict) -> str:
    risk_lv, risk_col, risk_txt = risk_assessment(s)
    sit_txt  = short_situation(s)
    news_sum = news_summary(s.get("news", []))

    # Sparkline — embed history data as data-attributes; JS draws SVG at load
    _spark = s.get("sparkline")
    if _spark:
        _sc_json  = json.dumps(_spark["scores"])
        _dt_json  = json.dumps(_spark["dates"])
        sparkline_html = (
            f'<div class="spark-wrap" '
            f'data-scores=\'{_sc_json}\' '
            f'data-dates=\'{_dt_json}\' '
            f'data-col="{_spark["col"]}" '
            f'data-today="{_spark["today"]}">'
            f'<div class="spark-header">'
            f'<span class="spark-title">Score-Verlauf</span>'
            f'<span class="spark-trend" style="color:{_spark["col"]}">{_spark["trend"]}</span>'
            f'</div>'
            f'<div class="spark-svg-wrap"></div>'
            f'<div class="spark-days"></div>'
            f'</div>'
        )
    else:
        sparkline_html = '<p class="spark-placeholder">Verlauf ab morgen verfügbar.</p>'

    # Sector / industry display — omit entirely if not available
    _sector   = (s.get("sector") or "").strip()
    _industry = (s.get("industry") or "").strip()
    if _sector and _industry:
        sector_tag_html   = f'<span class="sector-tag">{_sector} · {_industry}</span>'
        sector_detail_row = f"<tr><td>Sektor</td><td>{_sector} · {_industry}</td></tr>"
    elif _sector:
        sector_tag_html   = f'<span class="sector-tag">{_sector}</span>'
        sector_detail_row = f"<tr><td>Sektor</td><td>{_sector}</td></tr>"
    else:
        sector_tag_html   = ""
        sector_detail_row = ""

    # Earnings-Termin-Badge
    _earn_days = s.get("earnings_days")
    _earn_dstr = s.get("earnings_date_str") or ""
    if _earn_days is not None and _earn_days <= 14:
        _earn_col = "#ef4444" if _earn_days <= 3 else "#f59e0b"
        earnings_tag_html = (
            f'<span class="earnings-tag" style="color:{_earn_col}">'
            f'Earnings in {_earn_days}d ({_earn_dstr})</span>'
        )
    else:
        earnings_tag_html = ""

    sc      = min(s["score"], 100.0)
    sc_col  = _score_color(sc)
    sf      = s.get("short_float", 0)
    sr      = s.get("short_ratio", 0)
    rv      = s.get("rel_volume", 0)
    cap_val = s.get("yf_market_cap") or s.get("market_cap")
    chg     = s.get("change", 0)
    chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    chg_col = _metric_color("mom", chg)
    chg_5d_html = (f'<br><span style="font-size:0.75em;color:var(--color-text-secondary)">5T: {s["change_5d"]:+.1f}%</span>'
                   if s.get("change_5d") is not None else "")

    has_no_short_data = sf == 0 and sr == 0
    flag    = get_flag(s["ticker"])
    sf_display = "—" if has_no_short_data else f"{sf:.1f}%"
    sr_display = "—" if has_no_short_data else f"{sr:.1f}d"
    no_data_html = (
        '<p class="no-data-notice">ⓘ Short-Float &amp; Days to Cover für diesen Markt nicht verfügbar.</p>'
        if has_no_short_data else ""
    )

    sf_col = "#94a3b8" if has_no_short_data else _metric_color("sf", sf)
    sr_col = "#94a3b8" if has_no_short_data else _metric_color("sr", sr)
    rv_col = _metric_color("rv", rv)

    # Informational hint for candidates below the MIN_SCORE reference value
    below_min_score_html = (
        f'<span class="score-below-min">Score unter Richtwert ({MIN_SCORE:.0f} Pkt) '
        f'— schwächeres Signal.</span>'
        if s["score"] < MIN_SCORE else ""
    )


    # SI trend history + velocity
    finra_d       = s.get("finra_data") or {}
    si_trend      = finra_d.get("trend", "no_data")
    si_tpct       = finra_d.get("trend_pct", 0.0)
    si_hist       = finra_d.get("history", [])
    si_velocity   = finra_d.get("si_velocity", 0.0)
    si_accel      = finra_d.get("si_accelerating", False)

    if si_velocity != 0.0:
        _vel_sign = "+" if si_velocity > 0 else ""
        _vel_col  = "#22c55e" if si_velocity > 0 else "#ef4444"
        _accel_note = " ⚡ Beschleunigung" if si_accel else ""
        _vel_str  = f"{_vel_sign}{si_velocity:,.0f}".replace(",", ".")
        si_velocity_row = (
            f'<tr><td>SI Velocity (tägl. Ø)</td>'
            f'<td><span style="color:{_vel_col}">{_vel_str} Aktien/Tag{_accel_note}</span></td></tr>'
        )
    else:
        si_velocity_row = ""

    if si_trend == "up":
        trend_html      = f'<span style="color:#22c55e">↑ Steigend +{abs(si_tpct):.1f} %</span>'
        si_tile_val     = f"↑ +{abs(si_tpct):.0f} %"
        si_tile_col     = "#22c55e"
    elif si_trend == "down":
        trend_html      = f'<span style="color:#ef4444">↓ Fallend −{abs(si_tpct):.1f} %</span>'
        si_tile_val     = f"↓ −{abs(si_tpct):.0f} %"
        si_tile_col     = "#ef4444"
    elif si_trend == "sideways":
        sign = "+" if si_tpct >= 0 else "−"
        trend_html      = f'<span style="color:#f59e0b">→ Seitwärts {sign}{abs(si_tpct):.1f} %</span>'
        si_tile_val     = "→ stabil"
        si_tile_col     = "#f59e0b"
    else:
        trend_html      = "Keine Daten"
        si_tile_val     = "—"
        si_tile_col     = "#94a3b8"

    # Float tile
    _float_shares = s.get("float_shares") or 0
    if _float_shares > 0:
        float_mio       = _float_shares / 1_000_000
        float_tile_val  = f"{float_mio:.1f} Mio.".replace(".", ",")
        if _float_shares < 30_000_000:
            float_tile_col = "#22c55e"
        elif _float_shares <= 50_000_000:
            float_tile_col = "#f59e0b"
        else:
            float_tile_col = "#ef4444"
    else:
        float_tile_val  = "—"
        float_tile_col  = "#94a3b8"
    si_t1_disp = _fmt_si_record(si_hist[0]) if len(si_hist) >= 1 else "—"
    si_t2_disp = _fmt_si_record(si_hist[1]) if len(si_hist) >= 2 else "—"
    si_t3_disp = _fmt_si_record(si_hist[2]) if len(si_hist) >= 3 else "—"

    # RSI / MA / Relative-Strength rows for detail table
    _rsi   = s.get("rsi14")
    _ma50  = s.get("ma50")
    _ma200 = s.get("ma200")
    _price = s.get("price", 0)
    _rs20  = s.get("rel_strength_20d")
    _p20   = s.get("perf_20d")
    if _rsi is not None:
        if _rsi < 30:
            _rsi_col, _rsi_lbl = "#22c55e", "überverkauft"
        elif _rsi > 70:
            _rsi_col, _rsi_lbl = "#ef4444", "überkauft"
        else:
            _rsi_col, _rsi_lbl = "var(--txt)", ""
        _rsi_cell = f'<span style="color:{_rsi_col}">{_rsi:.1f}{(" — " + _rsi_lbl) if _rsi_lbl else ""}</span>'
        _rsi_row  = f"<tr><td>RSI (14T)</td><td>{_rsi_cell}</td></tr>"
    else:
        _rsi_row  = ""
    if _ma50 is not None:
        _vs_ma50  = ((_price - _ma50) / _ma50 * 100) if _ma50 > 0 else None
        _ma50_col = "#22c55e" if (_vs_ma50 is not None and _vs_ma50 >= 0) else "#ef4444"
        _ma50_pct = f'({_vs_ma50:+.1f}%)' if _vs_ma50 is not None else ""
        _ma50_row1 = f"<tr><td>MA 50T</td><td>${_ma50:.2f}</td></tr>"
        _ma50_row2 = f'<tr><td>Kurs vs. MA50</td><td><span style="color:{_ma50_col}">{_ma50_pct}</span></td></tr>'
    else:
        _ma50_row1, _ma50_row2 = "", ""
    if _ma200 is not None:
        _ma200_row = f"<tr><td>MA 200T</td><td>${_ma200:.2f}</td></tr>"
    else:
        _ma200_row = ""
    if _rs20 is not None:
        _rs_col  = "#22c55e" if _rs20 >= 0 else "#ef4444"
        _p20_str = f" (Aktie {_p20:+.1f}%)" if _p20 is not None else ""
        _rs_cell = f'<span style="color:{_rs_col}">{_rs20:+.1f}% vs. S&amp;P 500{_p20_str}</span>'
        _rs_row  = f"<tr><td>Rel. Stärke (20T)</td><td>{_rs_cell}</td></tr>"
    else:
        _rs_row  = ""
    rsi_ma_rows = _rsi_row + _ma50_row1 + _ma200_row + _ma50_row2 + _rs_row

    # Options market data rows
    _opts     = s.get("options") or {}
    _pc       = _opts.get("pc_ratio")
    _iv       = _opts.get("atm_iv")
    _exp      = _opts.get("expiry", "")
    _exp_note = f" <span style='color:var(--txt-dim);font-size:.8em'>({_exp})</span>" if _exp else ""
    if _pc is not None:
        # Bearish if puts dominate (P/C > 1.0), bullish if calls dominate (P/C < 0.7)
        _pc_col = "#ef4444" if _pc > 1.0 else ("#22c55e" if _pc < 0.7 else "var(--txt)")
        _pc_lbl = " — bärisch" if _pc > 1.0 else (" — bullisch" if _pc < 0.7 else "")
        _pc_row = (
            f'<tr><td>Put/Call-Ratio{_exp_note}</td>'
            f'<td><span style="color:{_pc_col}">{_pc:.2f}{_pc_lbl}</span></td></tr>'
        )
    else:
        _pc_row = ""
    if _iv is not None:
        _iv_pct = _iv * 100
        _iv_col = ("#22c55e" if _iv_pct > IV_HIGH
                   else "#f59e0b" if _iv_pct >= IV_LOW
                   else "#ef4444")
        _iv_row = (
            f'<tr><td>Impl. Volatilität (ATM)</td>'
            f'<td><span style="color:{_iv_col}">{_iv_pct:.1f}%</span></td></tr>'
        )
    else:
        _iv_row = ""
    options_rows = _pc_row + _iv_row

    # Institutional ownership row (+ optional 13F note)
    _inst      = s.get("inst_ownership")
    _13f_note  = s.get("sec_13f_note") or ""
    _13f_badge = (
        f' <span style="color:#22c55e;font-size:.8em">● {_13f_note}</span>'
        if _13f_note else ""
    )
    if _inst is not None:
        _inst_pct = float(_inst) * 100
        _inst_col = "#22c55e" if _inst_pct >= 60 else ("#f59e0b" if _inst_pct >= 30 else "#ef4444")
        _inst_row = (
            f'<tr><td>Institutioneller Anteil</td>'
            f'<td><span style="color:{_inst_col}">{_inst_pct:.1f}%</span>{_13f_badge}</td></tr>'
        )
    elif _13f_note:
        _inst_row = (
            f'<tr><td>Institutioneller Anteil</td>'
            f'<td>{_13f_badge.strip()}</td></tr>'
        )
    else:
        _inst_row = ""

    # Float size row
    _float_sh = s.get("float_shares") or 0
    if _float_sh > 0:
        _float_mio = _float_sh / 1_000_000
        _float_row = f"<tr><td>Float (frei handelbar)</td><td>{_float_mio:.1f} Mio. Aktien</td></tr>"
    else:
        _float_row = ""

    # Chart links
    yf_chart_url  = f"https://finance.yahoo.com/chart/{s['ticker']}"
    is_intl       = "." in s["ticker"]
    edgar_row     = (
        ""
        if is_intl else
        f'<tr><td>SEC-Meldungen</td><td>'
        f'<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany'
        f'&amp;CIK={s["ticker"]}&amp;type=&amp;dateb=&amp;owner=include&amp;count=10&amp;search_text=" '
        f'target="_blank" rel="noopener noreferrer" class="edgar-link">EDGAR öffnen →</a>'
        f'</td></tr>'
    )
    sa_ticker     = s["ticker"].split(".")[0].lower()
    fv_url        = f"https://finviz.com/quote.ashx?t={s['ticker'].split('.')[0].upper()}"
    sa_url        = f"https://stockanalysis.com/stocks/{sa_ticker}/"
    yahoo_badge   = (
        f'<a class="chart-badge chart-badge-y" href="{yf_chart_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Yahoo Finance Chart">Y</a>'
    )
    finviz_badge  = (
        '<span class="chart-badge chart-badge-f chart-badge-dis" '
        'title="Finviz unterstützt nur US-Aktien">F</span>'
        if is_intl else
        f'<a class="chart-badge chart-badge-f" href="{fv_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Finviz Chart &amp; Kennzahlen">F</a>'
    )
    sa_badge      = (
        '<span class="chart-badge chart-badge-s chart-badge-dis" '
        'title="Stockanalysis unterstützt nur US-Aktien">S</span>'
        if is_intl else
        f'<a class="chart-badge chart-badge-s" href="{sa_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Stockanalysis Chart &amp; Short-Interest">S</a>'
    )

    _news_items = []
    for n in s.get("news", [])[:3]:
        src_label = n.get("source") or n.get("publisher") or ""
        src_html  = f' <span class="ni-src">({src_label})</span>' if src_label else ""
        _news_items.append(
            f'<div class="ni">'
            f'<a href="{n.get("link","#")}" target="_blank" rel="noopener noreferrer">'
            f'{n.get("title","")}</a>{src_html}'
            f'<span class="ni-meta">{n.get("time","")}</span>'
            f'</div>'
        )
    news_html = "".join(_news_items) if _news_items else '<p class="no-news">Keine Nachrichten verfügbar.</p>'

    _da_rsi   = f'{_rsi:.1f}'   if _rsi   is not None else ''
    _da_iv    = f'{_iv*100:.1f}' if _iv   is not None else ''
    _da_earn  = str(_earn_days)  if _earn_days is not None else ''
    _da_cap   = str(int(cap_val)) if cap_val else ''
    _da_float = f'{(s.get("float_shares") or 0)/1e6:.1f}M' if s.get("float_shares") else ''
    _news_titles = [n.get("title","")[:140] for n in (s.get("news") or [])[:3] if n.get("title")]
    _da_news  = json.dumps(_news_titles, ensure_ascii=False).replace('"','&quot;')
    _da_earn_date = _earn_dstr

    return f"""
<article class="card" id="c{i}" data-ticker="{s['ticker']}"
  data-score="{sc:.1f}" data-company="{s.get('company_name','')}"
  data-price="{_price:.2f}" data-sf="{sf:.1f}" data-sr="{sr:.1f}"
  data-rv="{rv:.2f}" data-chg="{chg:.2f}" data-si="{si_trend}"
  data-rsi="{_da_rsi}" data-iv="{_da_iv}" data-earn="{_da_earn}"
  data-earn-date="{_da_earn_date}" data-float="{_da_float}"
  data-cap="{_da_cap}" data-sector="{_sector}" data-news="{_da_news}">
  <div class="card-top">
    <div class="card-left">
      <span class="rank">{i}</span>
      <div class="ticker-block">
        <div class="ticker-row">
          <span class="ticker">{s['ticker']}</span>
          <span class="market-tag">{flag} {get_region(s["ticker"])}</span>
          {finviz_badge}{sa_badge}
          <span class="price-tag">${s.get('price',0):.2f}</span>
          <button class="wl-add-btn" data-ticker="{s['ticker']}" onclick="wlToggle(this)" title="Zur Watchlist hinzufügen">＋</button>
        </div>
        <span class="company">{s.get('company_name','')}</span>
        {sector_tag_html}{earnings_tag_html}
      </div>
    </div>
    <div class="score-block">
      <span class="score-num" style="color:{sc_col}">{s['score']:.1f}</span>
      <span class="score-lbl">Score</span>
      <div class="score-track"><div class="score-fill" style="width:{sc:.0f}%;background:{sc_col}"></div></div>
      {below_min_score_html}
    </div>
  </div>
  {sparkline_html}
  <div class="metrics-row">
    <div class="metric-box" style="--mc:{sf_col}">
      <span class="m-val">{sf_display}</span>
      <span class="m-lbl">Short Float</span>
    </div>
    <div class="metric-box" style="--mc:{sr_col}">
      <span class="m-val">{sr_display}</span>
      <span class="m-lbl">Days to Cover</span>
    </div>
    <div class="metric-box" style="--mc:{rv_col}">
      <span class="m-val">{rv:.1f}×</span>
      <span class="m-lbl">Volumen</span>
    </div>
    <div class="metric-box" style="--mc:{chg_col}">
      <span class="m-val">{chg_str}{chg_5d_html}</span>
      <span class="m-lbl">Momentum</span>
    </div>
    <div class="metric-box" style="--mc:{float_tile_col}">
      <span class="m-val">{float_tile_val}</span>
      <span class="m-lbl">Float</span>
    </div>
    <div class="metric-box" style="--mc:{si_tile_col}">
      <span class="m-val">{si_tile_val}</span>
      <span class="m-lbl">SI-Trend</span>
    </div>
  </div>
  <button class="details-btn" onclick="toggleDetails({i})" id="db{i}" aria-expanded="false">
    <span class="details-arrow" id="da{i}">▾</span><span id="dl{i}"> Details anzeigen</span>
  </button>
  <div class="details-body" id="dd{i}">
    <div class="detail-table-wrap">
      <table class="detail-table">
        <tr><td>Marktkapitalisierung</td><td>{fmt_cap(cap_val)}</td></tr>
        {_float_row}
        {sector_detail_row}
        <tr><td>52W-Hoch / -Tief</td><td>${s.get('52w_high') or 0:.2f} / ${s.get('52w_low') or 0:.2f}</td></tr>
        <tr><td>Ø Volumen 20T</td><td>{s.get('avg_vol_20d',0):,.0f}</td></tr>
        <tr><td>Heutiges Volumen</td><td>{s.get('cur_vol',0):,.0f}</td></tr>
        {edgar_row}
        <tr><td>SI-Trend (3M)</td><td>{trend_html}</td></tr>
        {si_velocity_row}
        <tr><td>Short-Vol. T-1 (FINRA)</td><td>{si_t1_disp}</td></tr>
        <tr><td>Short-Vol. T-2</td><td>{si_t2_disp}</td></tr>
        <tr><td>Short-Vol. T-3</td><td>{si_t3_disp}</td></tr>

        {rsi_ma_rows}
        {options_rows}
        {_inst_row}
        <tr><td>Risiko-Detail</td><td style="color:{risk_col}">{risk_txt}</td></tr>
      </table>
    </div>
    {no_data_html}
    <div class="driver-row">
      <span class="risk-badge" style="color:{risk_col};border-color:{risk_col}55;background:{risk_col}22">Risiko: {risk_lv}</span>
      <p class="driver-text">{sit_txt}</p>
    </div>
  </div>
  <button class="news-btn" onclick="toggleNews({i})" id="nb{i}" aria-expanded="false">
    <span id="nb-icon{i}">▼</span> Aktuelle Meldungen
  </button>
  <div class="news-panel" id="np{i}" hidden>
    <div class="ki-signal-block">
      <div class="ki-signal-header">&#9889; KI-Agent Signale</div>
      <div class="ki-signal-body"></div>
    </div>
    <div class="news-items">{news_html}</div>
    <div class="news-summary-box">
      <span class="summary-label">Zusammenfassung</span>
      <p class="summary-text">{news_sum}</p>
    </div>
  </div>
  <button class="ki-analyse-btn" id="ka-btn{i}" onclick="runKiAnalyse({i})">
    &#x1F916; KI-Analyse
  </button>
  <div class="ki-analyse-result" id="ka-res{i}"></div>
</article>"""


def generate_html(stocks: list[dict], report_date: str) -> str:
    cards = "\n".join(_card(i + 1, s) for i, s in enumerate(stocks))

    n       = max(len(stocks), 1)
    avg_sf  = sum(s["short_float"] for s in stocks) / n
    avg_sr  = sum(s["short_ratio"]  for s in stocks) / n
    avg_rv  = sum(s["rel_volume"]   for s in stocks) / n
    mom_vals = [s["change"] for s in stocks if s.get("change") is not None and s.get("change") != 0.0]
    _avg_mom = sum(mom_vals) / len(mom_vals) if mom_vals else None
    avg_mom_str = f"{_avg_mom:+.1f}%" if _avg_mom is not None else "—"
    avg_mom_col = ("#22c55e" if _avg_mom > 0 else "#ef4444") if _avg_mom is not None else "var(--accent)"
    # Ø Float (Mio.)
    float_vals = [s["float_shares"] / 1_000_000 for s in stocks if (s.get("float_shares") or 0) > 0]
    avg_float_str = f"{sum(float_vals)/len(float_vals):.1f} Mio.".replace(".", ",") if float_vals else "—"
    # Ø SI-Trend
    si_vals = [
        (s.get("finra_data") or {}).get("trend_pct")
        for s in stocks
        if (s.get("finra_data") or {}).get("trend", "no_data") != "no_data"
    ]
    si_vals = [v for v in si_vals if v is not None]
    if si_vals:
        _avg_si = sum(si_vals) / len(si_vals)
        avg_si_str = f"{_avg_si:+.1f} %".replace(".", ",")
    else:
        avg_si_str = "—"
    now_str = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%H:%M Uhr")
    timestamp = f"Stand: {report_date}, {now_str}"

    # Watchlist: embed last known score, sparkline history, and full top10 snapshot
    try:
        with open(_SCORE_HISTORY_FILE, "r", encoding="utf-8") as _wl_fh:
            _wl_raw = json.load(_wl_fh)
        _wl_scores = {
            t: sorted(entries, key=lambda e: e.get("date",""))[-1]["score"]
            for t, entries in _wl_raw.items() if entries
        }
        _wl_hist: dict = {}
        for _t, _entries in _wl_raw.items():
            _sorted = sorted(_entries, key=lambda e: e.get("date",""))[-7:]
            if len(_sorted) >= 2:
                _delta = _sorted[-1]["score"] - _sorted[0]["score"]
                _wl_hist[_t] = {
                    "scores": [e["score"] for e in _sorted],
                    "dates":  [e["date"]  for e in _sorted],
                    "col":    ("#22c55e" if _delta >= 3
                               else "#ef4444" if _delta <= -3
                               else "#94a3b8"),
                    "trend":  (f"↑ +{_delta:.1f}" if _delta >= 3
                               else f"↓ {_delta:.1f}" if _delta <= -3
                               else "→ stabil"),
                }
    except Exception:
        _wl_scores = {}
        _wl_hist   = {}
    wl_scores_json = json.dumps(_wl_scores)
    wl_hist_json   = json.dumps(_wl_hist)

    # Full top10 snapshots for watchlist detail cards (all metrics + news)
    _wl_top10: dict = {}
    for _s in stocks:
        _fd   = _s.get("finra_data") or {}
        _hist = _fd.get("history", [])
        _opts = _s.get("options") or {}
        _wl_top10[_s["ticker"]] = {
            "score":         _s.get("score", 0),
            "company_name":  _s.get("company_name", ""),
            "sector":        _s.get("sector", ""),
            "flag":          get_flag(_s["ticker"]),
            "price":         _s.get("price", 0),
            "change":        _s.get("change", 0),
            "change_5d":     _s.get("change_5d"),
            "short_float":   _s.get("short_float", 0),
            "short_ratio":   _s.get("short_ratio", 0),
            "rel_volume":    _s.get("rel_volume", 0),
            "float_shares":  _s.get("float_shares") or 0,
            "si_trend":      _fd.get("trend", "no_data"),
            "si_tpct":       _fd.get("trend_pct", 0.0),
            "si_velocity":   _fd.get("si_velocity", 0.0),
            "si_accel":      _fd.get("si_accelerating", False),
            "si_t1":         _fmt_si_record(_hist[0]) if len(_hist) >= 1 else "—",
            "si_t2":         _fmt_si_record(_hist[1]) if len(_hist) >= 2 else "—",
            "si_t3":         _fmt_si_record(_hist[2]) if len(_hist) >= 3 else "—",
            "rsi14":         _s.get("rsi14"),
            "ma50":          _s.get("ma50"),
            "ma200":         _s.get("ma200"),
            "inst_ownership": _s.get("inst_ownership"),
            "52w_high":      _s.get("52w_high") or 0,
            "52w_low":       _s.get("52w_low") or 0,
            "avg_vol_20d":   _s.get("avg_vol_20d", 0),
            "cur_vol":       _s.get("cur_vol", 0),
            "market_cap":    _s.get("yf_market_cap") or _s.get("market_cap") or 0,
            "earnings_days": _s.get("earnings_days"),
            "earnings_date_str": _s.get("earnings_date_str", ""),
            "pc_ratio":      _opts.get("pc_ratio"),
            "atm_iv":        _opts.get("atm_iv"),
            "rel_strength_20d": _s.get("rel_strength_20d"),
            "perf_20d":      _s.get("perf_20d"),
            "news": [
                {
                    "title":  n.get("title", ""),
                    "link":   n.get("link", "#"),
                    "time":   n.get("time", ""),
                    "source": n.get("source") or n.get("publisher", ""),
                }
                for n in _s.get("news", [])[:3]
            ],
        }
    wl_top10_json = json.dumps(_wl_top10, default=str)

    # Compact top-10 snapshot for Claude chat system prompt
    _chat_ctx = []
    for _s in stocks:
        _fd   = _s.get("finra_data") or {}
        _opts = _s.get("options") or {}
        _chat_ctx.append({
            "ticker":      _s["ticker"],
            "score":       round(_s.get("score", 0), 1),
            "company":     _s.get("company_name", ""),
            "price":       round(_s.get("price", 0), 2),
            "change":      round(_s.get("change", 0), 2),
            "short_float": round(_s.get("short_float", 0), 1),
            "short_ratio": round(_s.get("short_ratio", 0), 1),
            "rel_volume":  round(_s.get("rel_volume", 0), 2),
            "si_trend":    _fd.get("trend", "no_data"),
            "rsi14":       _s.get("rsi14"),
            "atm_iv":      _opts.get("atm_iv"),
            "earnings_days": _s.get("earnings_days"),
            "sector":      _s.get("sector", ""),
        })
    chat_ctx_json = json.dumps(_chat_ctx, default=str)

    return f"""<!DOCTYPE html>
<html lang="de" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Squeeze Report">
<meta name="theme-color" content="#0d1117">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<title>Squeeze Report – {report_date}</title>
<style>
:root{{
  --bg:#f1f5f9;--bg-card:#fff;--bg-hdr:#fff;--bg-met:#f8fafc;
  --txt:#1e293b;--txt-sub:#64748b;--txt-dim:#94a3b8;
  --brd:#e2e8f0;--shadow:0 2px 8px rgba(0,0,0,.07);
  --accent:#3b82f6;--radius:14px;
  --red:#ef4444;--ora:#f59e0b;--grn:#22c55e;
  --disc-col:#c2410c;
  --base-font-size:15px;
}}
html{{font-size:var(--base-font-size)}}
html[data-theme="dark"]{{
  --bg:#0a0c12;--bg-card:#141929;--bg-hdr:#0d1117;--bg-met:#1a2035;
  --txt:#e2e8f0;--txt-sub:#94a3b8;--txt-dim:#64748b;
  --brd:#1e2d4a;--shadow:0 2px 12px rgba(0,0,0,.35);
  --disc-col:#ca8a04;
}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--txt);min-height:100vh;font-size:1rem;overflow-x:hidden}}
a{{color:var(--accent);text-decoration:none}}
/* ── Sticky header – full width on all screens ── */
.app-hdr{{position:sticky;top:0;z-index:100;background:var(--bg-hdr);
  border-bottom:1px solid var(--brd);padding:0 16px;
  box-shadow:0 1px 4px rgba(0,0,0,.08);width:100%}}
/* Mobile-first: row1=title+theme-btn  row2=ts  row3=action-btns */
.hdr-main{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:10px 0}}
.app-title{{font-size:1.05rem;font-weight:800;color:var(--txt);flex:1;order:1;min-width:0}}
.app-title span{{color:var(--accent)}}
/* Font-size controls + theme btn grouped on right side of header */
.hdr-icons{{display:flex;gap:4px;flex-shrink:0;order:2;align-items:center}}
.fs-btn{{width:44px;height:44px;border:none;border-radius:10px;
  background:var(--bg-met);color:var(--txt);font-size:13px;font-weight:800;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  letter-spacing:-.5px;line-height:1}}
.fs-btn:disabled{{opacity:.35;cursor:not-allowed}}
.fs-btn:hover:not(:disabled){{background:var(--brd)}}
.theme-btn{{width:44px;height:44px;border:none;border-radius:10px;
  background:var(--bg-met);color:var(--txt);font-size:1.1rem;cursor:pointer;
  display:flex;align-items:center;justify-content:center}}
.hdr-ts{{font-size:.73rem;color:var(--txt-sub);width:100%;order:3}}
.hdr-btns{{display:flex;flex-wrap:wrap;gap:8px;width:100%;order:4}}
@media(max-width:479px){{
  .hdr-btns .btn{{font-size:13px!important;min-height:40px!important;padding:0 10px!important}}
  #btn-reload,#btn-recalc{{flex:1 1 calc(50% - 4px)}}
  #btn-ki{{flex:1 1 100%}}
}}
.btn{{display:inline-flex;align-items:center;justify-content:center;
  gap:6px;min-height:44px;padding:0 16px;border:none;border-radius:10px;
  font-size:.9rem;font-weight:700;cursor:pointer;flex:1;
  transition:opacity .15s,transform .1s;white-space:nowrap}}
.btn:active{{transform:scale(.96)}}
.btn:disabled{{opacity:.45;cursor:not-allowed;transform:none}}
.btn-g{{background:#16a34a;color:#fff}}.btn-g:hover:not(:disabled){{background:#15803d}}
.btn-b{{background:#2563eb;color:#fff}}.btn-b:hover:not(:disabled){{background:#1d4ed8}}
.btn-ki{{background:#1e3a5f;color:#93c5fd}}.btn-ki:hover:not(:disabled){{background:#1e40af;color:#fff}}
/* token panel */
.tok-panel{{padding:0 0 10px}}
.tok-hint{{font-size:.8rem;color:var(--txt-sub);margin-bottom:8px;line-height:1.5}}
.tok-row{{display:flex;gap:8px;flex-wrap:wrap}}
.tok-inp{{flex:1;min-width:180px;background:var(--bg-met);border:1px solid var(--brd);
  border-radius:8px;color:var(--txt);padding:0 12px;height:44px;
  font-size:.85rem;font-family:monospace}}
.tok-inp:focus{{outline:2px solid var(--accent);outline-offset:1px}}
.tok-link{{font-size:.75rem;color:var(--txt-dim);padding:4px 2px;cursor:pointer}}
.amsg{{margin-top:8px;padding:10px 13px;border-radius:8px;font-size:.8rem;line-height:1.5;display:flex;align-items:center}}
.amsg-success{{background:#052a14;border:1px solid #166534;color:#86efac}}
.amsg-error{{background:#2d0a0a;border:1px solid #991b1b;color:#fca5a5}}
.amsg-info{{background:#0c1a30;border:1px solid #1e3a5f;color:#93c5fd}}
@keyframes poll-pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.poll-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;
  margin-right:8px;flex-shrink:0}}
.poll-dot-run{{background:#f59e0b;animation:poll-pulse 1.2s ease-in-out infinite}}
.poll-dot-done{{background:#22c55e}}
.poll-dot-err{{background:#ef4444}}
.amsg-poll-running{{background:#1c1200;border:1px solid #92400e;color:#fcd34d}}
.amsg-poll-done{{background:#052a14;border:1px solid #166534;color:#86efac;align-items:flex-start}}
.amsg-cd-body{{flex:1;display:flex;flex-direction:column;gap:5px}}
.amsg-cd-title{{font-weight:700;font-size:.85rem}}
.amsg-cd-sub{{font-size:.75rem;opacity:.85;line-height:1.5}}
.amsg-cd-bar-wrap{{height:4px;background:rgba(255,255,255,.15);border-radius:2px;overflow:hidden;margin-top:2px}}
.amsg-cd-bar{{height:100%;background:#22c55e;border-radius:2px;transition:width 1s linear}}
.amsg-cd-btn{{margin-top:8px;align-self:flex-start;background:#22c55e;color:#052a14;border:none;
  border-radius:6px;padding:6px 14px;font-size:.78rem;font-weight:700;cursor:pointer;min-height:36px}}
/* ── Container – fluid, no max-width ── */
.wrap{{padding:16px 14px 32px}}
/* ── Stats bar ── */
.stats-bar{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}}
.stat-title{{grid-column:1 / -1;background:#042C53;border-radius:10px;
  padding:11px 8px;text-align:center;color:#E6F1FB;font-size:1.19rem;font-weight:500}}
.stat-box{{background:var(--bg-card);border:1px solid var(--brd);border-radius:10px;
  padding:10px 8px;text-align:center}}
.stat-val{{display:block;font-size:1.05rem;font-weight:800;color:var(--accent)}}
.stat-lbl{{display:block;font-size:.62rem;color:var(--txt-dim);text-transform:uppercase;
  letter-spacing:.4px;margin-top:2px}}
/* ── Info panel ── */
.info-panel{{background:var(--bg-card);border:1px solid var(--brd);border-radius:var(--radius);
  margin-bottom:12px;overflow:hidden}}
.info-panel summary{{display:flex;align-items:center;justify-content:space-between;
  padding:13px 16px;cursor:pointer;font-size:.83rem;font-weight:700;
  color:var(--txt-sub);list-style:none;min-height:44px}}
.info-panel summary::-webkit-details-marker{{display:none}}
.info-panel summary::after{{content:"▼";font-size:.7rem;transition:transform .2s}}
.info-panel[open] summary::after{{transform:rotate(180deg)}}
/* Mobile: single column; tablet+ overrides to 3 */
.info-inner{{display:grid;grid-template-columns:1fr;gap:10px;padding:0 12px 14px}}
.info-box{{background:var(--bg-met);border-radius:8px;padding:10px 12px}}
.info-box--full{{grid-column:1 / -1}}
.info-box h4{{font-size:.67rem;text-transform:uppercase;letter-spacing:.5px;
  color:var(--accent);margin-bottom:7px}}
.info-box ul{{list-style:none;display:flex;flex-direction:column;gap:4px}}
.info-box li{{font-size:.77rem;color:var(--txt-sub);line-height:1.5;
  padding-left:12px;position:relative}}
.info-box li::before{{content:"–";position:absolute;left:0;color:var(--accent)}}
/* ── Color legend ── */
.color-legend{{display:grid;grid-template-columns:1fr;gap:12px;margin-top:2px}}
.cl-name{{display:block;font-size:.67rem;text-transform:uppercase;letter-spacing:.5px;
  color:var(--accent);margin-bottom:5px;font-weight:700}}
.color-bar{{display:flex;border-radius:6px;overflow:hidden;height:22px;margin-bottom:6px}}
.cb-seg{{flex:1;display:flex;align-items:center;justify-content:center;
  font-size:.6rem;font-weight:700;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.45)}}
.cl-desc{{font-size:.77rem;color:var(--txt-sub);line-height:1.5;margin:0}}
.info-box li strong{{color:var(--txt)}}
/* ── Disclaimer ── */
.disc{{background:var(--bg-met);border:1px solid var(--brd);border-radius:8px;
  padding:10px 14px;margin-bottom:14px;font-size:.76rem;color:var(--disc-col);line-height:1.5}}
/* ── Card grid: mobile 1-col (8px gap); ≥768px auto-fill (16px gap) ── */
.cards-grid{{display:grid;grid-template-columns:1fr;gap:8px}}
/* ── Card ── */
.card{{background:var(--bg-card);border:1px solid var(--brd);border-radius:var(--radius);
  box-shadow:var(--shadow);overflow:hidden}}
.card-top{{display:flex;align-items:flex-start;justify-content:space-between;
  padding:14px 14px 10px;gap:10px}}
.card-left{{display:flex;align-items:flex-start;gap:10px;flex:1;min-width:0}}
.rank{{display:flex;align-items:center;justify-content:center;width:28px;height:28px;
  border-radius:50%;background:var(--accent);color:#fff;font-size:.75rem;
  font-weight:800;flex-shrink:0;margin-top:3px}}
.ticker-block{{flex:1;min-width:0}}
.ticker-row{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:3px}}
.ticker{{font-size:1.25rem;font-weight:800;font-family:'SF Mono','Courier New',monospace;color:var(--txt)}}
.market-tag{{font-size:.62rem;font-weight:700;background:var(--accent);color:#fff;
  padding:1px 6px;border-radius:4px;letter-spacing:.3px}}
.chart-badge{{display:inline-flex;align-items:center;justify-content:center;
  min-width:32px;min-height:32px;border-radius:6px;font-size:10px;font-weight:700;
  text-decoration:none;border:1.5px solid;padding:0 6px;line-height:1;box-sizing:border-box}}
.chart-badge-y{{background:#1d4ed8;color:#fff;border-color:#2563eb}}
.chart-badge-y:hover{{background:#1e40af}}
.chart-badge-f{{background:#4b5e7a;color:#fff;border-color:#5d7494}}
.chart-badge-f:hover{{background:#3b4d63}}
.chart-badge-s{{background:#7c3aed;color:#fff;border-color:#8b5cf6}}
.chart-badge-s:hover{{background:#6d28d9}}
.chart-badge-dis{{background:#334155;color:#94a3b8;border-color:#475569;
  cursor:default;pointer-events:none}}
.price-tag{{font-size:.82rem;font-weight:600}}
.company{{display:block;font-size:.78rem;color:var(--txt-sub);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}}
.sector-tag{{display:inline-block;font-size:.67rem;color:var(--txt-dim);margin-top:3px}}
.earnings-tag{{display:inline-block;font-size:.67rem;font-weight:600;margin-top:3px;margin-left:2px}}
.wl-add-btn{{background:none;border:none;color:var(--txt-dim);cursor:pointer;font-size:1rem;padding:0 3px;line-height:1;opacity:.55;transition:opacity .15s,color .15s}}
.wl-add-btn:hover{{color:#22c55e;opacity:1}}
.wl-add-btn.in-wl{{color:#22c55e;opacity:1}}
.wl-section{{display:none;margin-bottom:14px}}
.wl-section.has-items{{display:block}}
.wl-section-hdr{{display:flex;align-items:center;gap:8px;padding:0 4px;margin-bottom:8px}}
.wl-section-title{{font-size:.9rem;font-weight:700;color:var(--txt)}}
.wl-count-badge{{font-size:.68rem;color:var(--txt-dim);background:var(--brd);padding:1px 7px;border-radius:10px}}
.wl-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}}
.wl-card{{background:var(--bg-card);border:1px solid #3b82f644;border-radius:10px;position:relative}}
.wl-card--expanded{{grid-column:1/-1}}
.wl-card-header{{display:flex;flex-direction:column;align-items:flex-start;gap:4px;padding:8px}}
.wl-card-ticker{{font-size:.9rem;font-weight:800;color:var(--txt)}}
.wl-card-score{{font-size:20px;font-weight:800;line-height:1;align-self:center}}
.wl-badge-star{{position:absolute;top:4px;right:4px;font-size:.65rem;color:#3b82f6;opacity:.7;pointer-events:none}}
.wl-notop-badge{{font-size:.62rem;color:#6b7280;background:#6b728022;border:1px solid #6b728044;border-radius:4px;padding:1px 5px;width:fit-content}}
.wl-details-btn{{background:none;border:1px solid #3b82f644;color:#3b82f6;cursor:pointer;font-size:.75rem;padding:1px 6px;border-radius:6px}}
.wl-details-btn:hover{{background:#3b82f622}}
.wl-details-body{{border-top:1px solid var(--brd)}}
.wl-no-data{{padding:10px 14px;color:var(--txt-dim);font-size:.8rem;font-style:italic}}
.wl-remove-btn{{background:none;border:none;color:var(--txt-dim);cursor:pointer;font-size:.85rem;padding:0;opacity:.5}}
.wl-remove-btn:hover{{color:#ef4444;opacity:1}}
@media(max-width:479px){{.wl-cards{{grid-template-columns:repeat(2,1fr)}}}}
/* ── Anthropic / Claude API ── */
.anth-panel{{padding:0 0 10px}}
.anth-panel .tok-hint{{margin-bottom:6px}}
.anth-panel .tok-row{{flex-wrap:wrap;gap:6px}}
.anth-status{{font-size:.75rem;margin-top:6px;padding:6px 10px;border-radius:6px;display:none}}
.anth-status.ok{{background:#052a14;border:1px solid #166534;color:#86efac;display:block}}
.anth-status.err{{background:#2d0a0a;border:1px solid #991b1b;color:#fca5a5;display:block}}
.btn-anth{{background:#6d28d9;color:#fff;min-height:36px;padding:0 12px;font-size:.78rem}}
.btn-anth:hover:not(:disabled){{background:#5b21b6}}
/* KI-Analyse per card */
.ki-analyse-btn{{width:100%;min-height:44px;background:linear-gradient(90deg,#1e1040 0%,#2d1460 100%);
  border:none;border-top:1px solid #4c1d9522;color:#c4b5fd;font-size:.82rem;font-weight:600;
  cursor:pointer;padding:0 14px;text-align:left;display:flex;align-items:center;gap:6px;
  transition:background .15s}}
.ki-analyse-btn:hover:not(:disabled){{background:linear-gradient(90deg,#2d1460 0%,#3b1f6b 100%)}}
.ki-analyse-btn:disabled{{opacity:.5;cursor:not-allowed}}
.ki-analyse-result{{padding:10px 14px;border-top:1px solid #4c1d9522;display:none;
  font-size:.82rem;line-height:1.6;color:var(--txt-sub);background:#0d0920}}
.ki-analyse-result.visible{{display:block}}
.ki-analyse-result .ka-label{{font-size:.65rem;text-transform:uppercase;letter-spacing:.5px;
  color:#a78bfa;font-weight:700;margin-bottom:5px;display:flex;align-items:center;gap:8px}}
.ka-rerun-btn{{background:none;border:1px solid #4c1d95;color:#a78bfa;border-radius:6px;
  padding:1px 7px;font-size:.65rem;cursor:pointer;white-space:nowrap;flex-shrink:0}}
.ka-rerun-btn:hover{{background:#4c1d9533}}
/* Chat panel — mobile full-screen, desktop right panel (380px) */
.btn-chat{{background:#0e3a5e;color:#7dd3fc}}
.btn-chat:hover:not(:disabled){{background:#0c4a6e;color:#fff}}
.chat-panel{{position:fixed;left:0;right:0;bottom:0;top:auto;height:100vh;width:100vw;
  background:var(--bg-card);border:1px solid var(--brd);box-shadow:0 -4px 24px rgba(0,0,0,.35);
  display:flex;flex-direction:column;z-index:300;
  transform:translateY(100%);transition:transform .28s cubic-bezier(.4,0,.2,1)}}
.chat-panel.open{{transform:translateY(0)}}
@media(min-width:768px){{
  .chat-panel{{left:auto;top:0;width:380px;height:100vh;border-radius:0;
    transform:translateX(100%)}}
  .chat-panel.open{{transform:translateX(0)}}
}}
.chat-hdr{{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--brd);
  gap:10px;flex-shrink:0;background:var(--bg-hdr)}}
.chat-hdr-title{{flex:1;font-size:.95rem;font-weight:700;color:var(--txt)}}
.chat-close-btn{{background:none;border:none;color:var(--txt-dim);cursor:pointer;font-size:1.3rem;
  padding:0;line-height:1;width:44px;height:44px;display:flex;align-items:center;
  justify-content:center;border-radius:8px;flex-shrink:0}}
.chat-close-btn:hover{{color:var(--txt);background:var(--bg-met)}}
.chat-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:299;
  display:none;-webkit-tap-highlight-color:transparent}}
.chat-overlay.open{{display:block}}
.chat-warn-banner{{padding:10px 14px;background:#1c1200;border:1px solid #92400e;color:#fcd34d;
  font-size:.78rem;line-height:1.5;margin:10px 12px 0;border-radius:8px}}
.chat-warn-banner.hidden{{display:none}}
.chat-warn-banner .btn{{margin-top:8px;min-height:32px;padding:0 12px;font-size:.78rem;
  background:#f59e0b;color:#1c1102;flex:0 0 auto}}
.chat-msgs{{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}}
.chat-msg{{max-width:88%;padding:9px 13px;border-radius:10px;font-size:.85rem;line-height:1.55;
  word-wrap:break-word}}
.chat-msg--user{{align-self:flex-end;background:#1e3a5f;color:#bae6fd;border-radius:10px 10px 2px 10px}}
.chat-msg--ai{{align-self:flex-start;background:var(--bg-met);color:var(--txt);border-radius:10px 10px 10px 2px}}
.chat-msg--sys{{align-self:center;color:var(--txt-dim);font-size:.72rem;font-style:italic;text-align:center}}
.chat-msg--err{{align-self:center;background:#2d0a0a;border:1px solid #991b1b;color:#fca5a5;
  border-radius:8px;font-size:.78rem}}
.chat-msg.streaming::after{{content:'\u258B';color:var(--accent);animation:chatCaret 1s steps(2) infinite}}
@keyframes chatCaret{{50%{{opacity:0}}}}
.chat-chips{{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;border-top:1px solid var(--brd);flex-shrink:0}}
.chip{{background:var(--bg-met);border:1px solid var(--brd);border-radius:20px;
  padding:5px 11px;font-size:.72rem;cursor:pointer;color:var(--txt-sub);white-space:nowrap;
  text-align:left}}
.chip:hover{{background:var(--brd);color:var(--txt)}}
.chat-input-row{{display:flex;gap:6px;padding:10px 12px;border-top:1px solid var(--brd);flex-shrink:0;
  padding-bottom:max(10px,env(safe-area-inset-bottom))}}
.chat-inp{{flex:1;background:var(--bg-met);border:1px solid var(--brd);border-radius:8px;
  color:var(--txt);padding:0 12px;height:42px;font-size:.85rem;font-family:inherit}}
.chat-inp:focus{{outline:2px solid var(--accent);outline-offset:1px}}
.chat-send-btn{{background:#2563eb;color:#fff;border:none;border-radius:8px;
  padding:0 16px;height:42px;font-size:.95rem;font-weight:700;cursor:pointer;flex-shrink:0}}
.chat-send-btn:hover:not(:disabled){{background:#1d4ed8}}
.chat-send-btn:disabled{{opacity:.45;cursor:not-allowed}}
.score-block{{display:flex;flex-direction:column;align-items:flex-end;min-width:64px}}
.score-num{{font-size:1.7rem;font-weight:900;line-height:1}}
.score-lbl{{font-size:.62rem;color:var(--txt-dim);text-transform:uppercase;
  letter-spacing:.4px;margin-bottom:5px}}
.score-track{{width:60px;height:5px;background:var(--brd);border-radius:3px}}
.score-fill{{height:100%;border-radius:3px;transition:width .3s}}
.score-hist-lbl{{font-size:.58rem;color:var(--txt-dim);margin-top:2px;text-align:center}}
.score-below-min{{display:block;font-size:.58rem;color:var(--txt-dim);margin-top:3px;
  text-align:right;font-style:italic;line-height:1.3;max-width:68px}}
/* ── Sparkline ── */
.spark-wrap{{padding:8px 12px 4px;border-top:1px solid var(--brd)}}
.spark-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}}
.spark-title{{font-size:.65rem;color:var(--txt-dim);text-transform:uppercase;letter-spacing:.3px}}
.spark-trend{{font-size:13px;font-weight:700}}
.spark-svg-wrap{{width:100%;height:60px;position:relative}}
.spark-svg-wrap svg{{width:100%;height:60px;overflow:visible}}
.spark-days{{position:relative;height:14px;margin-top:2px}}
.spark-day-lbl{{position:absolute;font-size:.58rem;color:var(--txt-dim);
  transform:translateX(-50%);white-space:nowrap;line-height:1}}
.spark-day-lbl.ghost{{color:#6b7280}}
.spark-placeholder{{font-size:.7rem;color:var(--txt-dim);font-style:italic;
  padding:8px 12px 6px;border-top:1px solid var(--brd)}}
/* Sparkline tooltip */
.spark-tip{{position:absolute;background:var(--bg-card);border:1px solid var(--brd);
  border-radius:5px;padding:2px 6px;font-size:.68rem;color:var(--txt);
  pointer-events:none;white-space:nowrap;z-index:10;
  transform:translate(-50%,-130%);opacity:0;transition:opacity .15s}}
.spark-tip.visible{{opacity:1}}
/* ── Metrics ── */
.metrics-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;padding:0 12px 12px}}
.metric-box{{background:var(--bg-met);border:1px solid var(--brd);border-radius:10px;
  padding:10px 6px;text-align:center;border-top:3px solid var(--mc,#94a3b8);position:relative}}
.m-val{{display:block;font-size:1.1rem;font-weight:800;color:var(--mc,#94a3b8)}}
.m-lbl{{display:block;font-size:.62rem;color:var(--txt-dim);text-transform:uppercase;
  letter-spacing:.3px;margin-top:2px}}
.si-badge{{position:absolute;top:4px;right:5px;font-size:9px;font-weight:700;line-height:1}}
.si-badge-up{{color:#22c55e}}
.si-badge-down{{color:#ef4444}}
.si-badge-side{{color:#f59e0b}}
/* ── KI-Agent Status & Signal Dots ── */
.agent-status-bar{{font-size:.72rem;color:var(--txt-dim);padding:4px 14px 8px;
  letter-spacing:.1px}}
.agent-dot{{display:inline-block;border-radius:50%;
  margin-left:5px;vertical-align:middle;cursor:pointer;position:relative}}
.agent-dot.strong  {{width:12px;height:12px;--pc:#22c55e88;background:#22c55e;animation:pulse 1s   ease-out infinite}}
.agent-dot.moderate{{width:11px;height:11px;--pc:#f59e0b88;background:#f59e0b;animation:pulse 1.5s ease-out infinite}}
.agent-dot.weak    {{width:10px;height:10px;--pc:#ef444488;background:#ef4444;animation:pulse 2s   ease-out infinite}}
.agent-dot.none    {{width:8px; height:8px; background:#6b7280}}
@keyframes pulse{{
  0%  {{box-shadow:0 0 0 0   var(--pc)}}
  70% {{box-shadow:0 0 0 8px transparent}}
  100%{{box-shadow:0 0 0 0   transparent}}
}}
@media(max-width:480px){{
  .agent-dot.strong  {{width:14px;height:14px}}
  .agent-dot.moderate{{width:13px;height:13px}}
  .agent-dot.weak    {{width:12px;height:12px}}
  .agent-dot.none    {{width:10px;height:10px}}
}}
.agent-tooltip{{position:absolute;left:50%;transform:translateX(-50%);
  bottom:calc(100% + 6px);background:#1e293b;color:#f1f5f9;
  font-size:.68rem;white-space:nowrap;padding:4px 8px;border-radius:6px;
  pointer-events:none;opacity:0;transition:opacity .15s;z-index:50;
  border:1px solid #334155}}
.agent-dot:hover .agent-tooltip{{opacity:1}}
.agent-dot.touch-visible .agent-tooltip{{opacity:1}}
/* ── Detail table (top of details body) ── */
.detail-table-wrap{{padding:10px 12px 8px}}
/* ── Driver row ── */
.driver-row{{display:flex;align-items:flex-start;gap:10px;
  padding:10px 12px 10px;border-top:1px solid var(--brd)}}
.driver-text{{font-size:.93rem;color:var(--txt-sub);line-height:1.55;flex:1}}
.risk-badge{{flex-shrink:0;padding:4px 10px;border-radius:20px;font-size:.7rem;
  font-weight:700;letter-spacing:.4px;border:1px solid;white-space:nowrap;margin-top:2px}}
@media(max-width:359px){{.driver-row{{flex-direction:column}}}}
/* ── Details dropdown button ── */
.details-btn{{width:100%;min-height:44px;background:var(--bg-met);
  border:none;border-top:1px solid var(--brd);border-bottom:none;
  color:var(--txt-sub);font-size:.82rem;font-weight:600;cursor:pointer;
  padding:0 14px;text-align:left;display:flex;align-items:center;gap:6px}}
.details-btn:hover{{background:var(--brd)}}
.details-arrow{{display:inline-block;font-size:.75rem;transition:transform .2s ease;
  flex-shrink:0}}
/* ── Collapsible details body ── */
.details-body{{max-height:0;overflow:hidden;
  transition:max-height .25s ease}}
.details-body.open{{max-height:1200px}}
/* ── News toggle button ── */
.news-btn{{width:100%;min-height:44px;background:var(--bg-met);border:none;
  border-top:1px solid var(--brd);color:var(--txt-sub);font-size:.82rem;
  font-weight:600;cursor:pointer;padding:0 14px;text-align:left;display:flex;
  align-items:center;gap:6px}}
.news-btn:hover{{background:var(--brd)}}
/* ── News panel ── */
.news-panel{{border-top:1px solid var(--brd);padding:12px 14px}}
.ki-signal-block{{border-bottom:1px solid var(--brd);padding:0 0 10px;margin-bottom:10px;display:none}}
.ki-signal-header{{font-size:.72rem;font-weight:700;color:#f59e0b;letter-spacing:.4px;margin-bottom:5px}}
.ki-signal-body{{display:flex;flex-direction:column;gap:3px}}
.ki-score{{font-size:.82rem;font-weight:700;color:var(--txt)}}
.ki-confidence{{font-size:.75rem;color:#f59e0b;font-weight:600}}
.ki-drivers{{font-size:.78rem;color:var(--txt-sub)}}
.ki-meta{{font-size:.68rem;color:var(--txt-dim)}}
.news-items{{margin-bottom:12px}}
.ni{{margin-bottom:10px;font-size:.93rem;line-height:1.5}}
.ni a{{color:var(--accent);display:block;margin-bottom:2px}}
.ni a:hover{{text-decoration:underline}}
.ni-meta{{font-size:.7rem;color:var(--txt-dim)}}
.ni-src{{font-size:.72rem;color:var(--txt-dim);font-style:italic}}
.no-news{{font-size:.93rem;color:var(--txt-dim)}}
.no-data-notice{{font-size:.75rem;color:var(--txt-dim);font-style:italic;
  margin:4px 12px 10px;padding:6px 10px;background:var(--bg-met);border-radius:6px;
  border-left:3px solid var(--brd)}}
.news-summary-box{{background:var(--bg-met);border-radius:8px;padding:10px 12px;margin-bottom:12px}}
.summary-label{{display:block;font-size:.65rem;text-transform:uppercase;letter-spacing:.5px;
  color:var(--accent);margin-bottom:5px;font-weight:700}}
.summary-text{{font-size:.93rem;color:var(--txt-sub);line-height:1.6}}
.detail-table{{width:100%;font-size:.78rem;border-collapse:collapse}}
.detail-table td{{padding:4px 0;border-bottom:1px solid var(--brd)}}
.detail-table td:first-child{{color:var(--txt-dim);padding-right:10px}}
.detail-table td:last-child{{text-align:right;font-weight:600;color:var(--txt)}}
/* ── Footer – full width ── */
.footer{{padding:16px 14px 32px;
  border-top:1px solid var(--brd);text-align:center}}
.footer p{{font-size:.73rem;color:var(--txt-dim);line-height:1.6;margin-bottom:4px}}
/* ══ RESPONSIVE ═════════════════════════════════════════════════════════════
   ≥ 768 px  Tablet / kleiner Desktop
   ═════════════════════════════════════════════════════════════════════════ */
@media(min-width:768px){{
  /* Header: single row – title | ts (centered) | btns | theme-btn */
  .hdr-main{{flex-wrap:nowrap;padding:0;height:60px;gap:12px}}
  .app-title{{order:1;flex:0 0 auto}}
  .hdr-ts{{order:2;flex:1;width:auto;text-align:center}}
  .hdr-btns{{order:3;width:auto;flex:0 0 auto}}
  .hdr-btns .btn{{flex:0 0 auto;min-height:44px;padding:0 16px;font-size:.87rem}}
  .hdr-icons{{order:4}}
  /* Info panel: 3 columns */
  .info-inner{{grid-template-columns:repeat(3,1fr)}}
  .color-legend{{grid-template-columns:repeat(2,1fr)}}
  /* Cards: fluid auto-fill, min 340px per card, 16px gap, full width */
  .cards-grid{{grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}}
  .stats-bar{{grid-template-columns:repeat(6,1fr)}}
  .wrap{{padding:16px 16px 32px}}
  .footer{{padding:16px 16px 32px}}
  /* Slightly smaller body text */
  .driver-text{{font-size:.82rem}}
  .ni,.no-news,.summary-text{{font-size:.82rem}}
}}
/* ══ ≥ 1200 px  großer Desktop / Wide-Screen ════════════════════════════════ */
@media(min-width:1200px){{
  .app-hdr{{padding:0 24px}}
  .hdr-main{{height:52px;gap:10px}}
  .hdr-btns .btn{{min-height:36px;padding:0 14px;font-size:.82rem}}
  .theme-btn{{width:32px;height:32px;font-size:.9rem}}
  .fs-btn{{width:32px;height:32px;font-size:11px}}
  .wrap{{padding:24px 24px 40px}}
  .footer{{padding:24px 24px 40px}}
}}
.edgar-link{{color:var(--accent);text-decoration:none}}
.edgar-link:hover{{text-decoration:underline}}
/* ══ Druckansicht ════════════════════════════════════════════════════════════ */
@media print{{
  /* Reset colours to print-friendly light theme */
  :root{{
    --bg:#fff;--bg-card:#fff;--bg-hdr:#fff;--bg-met:#f5f5f5;
    --txt:#000;--txt-sub:#444;--txt-dim:#666;
    --brd:#ccc;--shadow:none;--accent:#1a56db;
  }}
  html[data-theme="dark"]{{
    --bg:#fff;--bg-card:#fff;--bg-hdr:#fff;--bg-met:#f5f5f5;
    --txt:#000;--txt-sub:#444;--txt-dim:#666;
    --brd:#ccc;--shadow:none;
  }}
  /* Hide interactive / non-content elements */
  .app-hdr,.hdr-btns,.hdr-icons,.tok-panel,#amsg,#non-trading-banner,
  .details-btn,.news-btn,.print-btn,.tok-link,
  [id^="tok-"],.info-panel summary::after{{display:none!important}}
  /* Show all collapsed sections */
  .details-body,.news-panel{{display:block!important;height:auto!important;
    overflow:visible!important;visibility:visible!important}}
  [hidden]{{display:block!important}}
  /* Page layout */
  body{{background:#fff;font-size:11pt;color:#000}}
  .wrap{{padding:8px 0}}
  .card{{break-inside:avoid;page-break-inside:avoid;
    border:1px solid #ccc;border-radius:0;box-shadow:none;
    margin-bottom:12pt;padding:10pt}}
  .stats-bar{{break-inside:avoid;page-break-inside:avoid}}
  .info-panel{{break-inside:avoid;page-break-inside:avoid}}
  /* Make sparkline section take less space */
  .spark-wrap{{max-height:90px;overflow:hidden}}
  /* Score track bar via background-color not CSS var */
  .score-fill{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
  /* Badges and colour indicators — keep colours in print */
  .metric-box,.score-num,.risk-badge,
  [style*="color:"]{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
  /* Print header with report title + date */
  .app-title{{display:block!important;font-size:14pt;font-weight:800;margin-bottom:4pt}}
  .hdr-ts{{display:block!important;font-size:9pt;color:#444}}
  /* Ensure links are visible in print */
  a[href]::after{{content:" (" attr(href) ")";font-size:7pt;color:#666;word-break:break-all}}
  a.chart-badge::after{{content:none}}
}}
</style>
</head>
<body>
<header class="app-hdr">
  <div class="hdr-main">
    <span class="app-title">Squeeze <span>Report</span></span>
    <span class="hdr-ts">{timestamp}</span>
    <div class="hdr-btns">
      <button id="btn-reload" class="btn btn-g" onclick="reloadPage()">&#8635; Reload</button>
      <button id="btn-recalc" class="btn btn-b" onclick="triggerWorkflow()">&#9881; Recalculate</button>
      <button id="btn-ki" class="btn btn-ki" onclick="triggerKiAgent()">&#9889; Agent Run</button>
      <button id="btn-chat" class="btn btn-chat" onclick="toggleChat()">&#x1F4AC; Chat</button>
    </div>
    <div class="hdr-icons">
      <button class="fs-btn print-btn" onclick="window.print()" aria-label="Seite drucken" title="Drucken">🖨</button>
      <button class="fs-btn" id="fs-down" onclick="changeFontSize(-1)" aria-label="Schrift kleiner">A−</button>
      <button class="fs-btn" id="fs-up"   onclick="changeFontSize(1)"  aria-label="Schrift größer">A+</button>
      <button class="fs-btn" onclick="toggleSettings()" id="settings-btn" aria-label="Einstellungen" title="Einstellungen">&#9881;</button>
      <button class="theme-btn" onclick="toggleTheme()" id="theme-btn" aria-label="Dark Mode umschalten">🌙</button>
    </div>
  </div>
  <div id="tok-sec" style="display:none" class="tok-panel">
    <p class="tok-hint">GitHub-Token eingeben (nur lokal gespeichert, nie weitergegeben):</p>
    <div class="tok-row">
      <input type="password" id="tok-inp" class="tok-inp" placeholder="ghp_xxxx…"
             onkeydown="if(event.key==='Enter')saveTokenAndDispatch()">
      <button class="btn btn-b" style="flex:0;padding:0 16px" onclick="saveTokenAndDispatch()">OK</button>
    </div>
  </div>
  <div id="anth-sec" style="display:none" class="anth-panel">
    <p class="tok-hint"><strong>Anthropic API-Key</strong> — Dein API-Key wird ausschließlich lokal im Browser gespeichert und nie an andere Server übertragen.</p>
    <div class="tok-row">
      <input type="password" id="anth-inp" class="tok-inp" placeholder="sk-ant-…"
             onkeydown="if(event.key==='Enter')saveAnthropicKey()">
      <button class="btn btn-anth" style="flex:0;padding:0 12px" onclick="testAnthropicKey()">Testen</button>
      <button class="btn btn-b" style="flex:0;padding:0 12px" onclick="saveAnthropicKey()">OK</button>
    </div>
    <div id="anth-status" class="anth-status"></div>
    <div style="padding-top:4px">
      <a class="tok-link" onclick="clearAnthropicKey();return false;" href="#">API-Key löschen</a>
    </div>
  </div>
  <div id="amsg" class="amsg" style="display:none"></div>
  <div style="padding-bottom:4px">
    <a class="tok-link" onclick="resetToken();return false;" href="#">Token zurücksetzen</a>
  </div>
  <div id="non-trading-banner" style="display:none;width:100%;background:#f59e0b;color:#1c1102;
    font-size:.78rem;font-weight:500;padding:5px 16px;box-sizing:border-box;
    border-top:1px solid #d97706;line-height:1.45" aria-live="polite"></div>
  <!-- Chat Overlay (tap outside to close) -->
  <div id="chat-overlay" class="chat-overlay" onclick="toggleChat()" aria-hidden="true"></div>
  <!-- Claude Chat Panel -->
  <div id="chat-panel" class="chat-panel" role="dialog" aria-label="KI-Assistent Chat">
    <div class="chat-hdr">
      <span style="font-size:1.1rem">&#x1F916;</span>
      <span class="chat-hdr-title">TopTen Squeezer &middot; KI-Assistent</span>
      <button class="chat-close-btn" onclick="toggleChat()" aria-label="Chat schließen">&#10005;</button>
    </div>
    <div id="chat-warn" class="chat-warn-banner hidden">
      &#9888;&#65039; Alle KI-Analysen sind rein informativ und stellen keine Anlageempfehlung dar. Short Squeezes sind hochspekulative Ereignisse mit erheblichem Verlustrisiko.
      <div><button class="btn" onclick="chatWarnAck()">Verstanden</button></div>
    </div>
    <div class="chat-msgs" id="chat-msgs"></div>
    <div class="chat-chips" id="chat-chips"></div>
    <div class="chat-input-row">
      <input class="chat-inp" id="chat-inp" type="text" placeholder="Frage zu den aktuellen Squeeze-Kandidaten …"
             onkeydown="if(event.key==='Enter'&&!event.shiftKey){{chatSend();event.preventDefault()}}">
      <button class="chat-send-btn" id="chat-send" onclick="chatSend()" aria-label="Senden">&#10148;</button>
    </div>
  </div>
</header>

<main class="wrap">
  <div class="agent-status-bar" id="agent-status">⚡ KI-Agent: Wird geladen …</div>
  <div class="stats-bar">
    <div class="stat-title">TopTen Squeezer</div>
    <div class="stat-box"><span class="stat-val">{avg_sf:.1f}%</span><span class="stat-lbl">Ø Short Float</span></div>
    <div class="stat-box"><span class="stat-val">{avg_sr:.1f}d</span><span class="stat-lbl">Ø Days to Cover</span></div>
    <div class="stat-box"><span class="stat-val">{avg_rv:.1f}×</span><span class="stat-lbl">Ø Volumen</span></div>
    <div class="stat-box"><span class="stat-val">{avg_mom_str}</span><span class="stat-lbl">Ø Kursmomentum</span></div>
    <div class="stat-box"><span class="stat-val">{avg_float_str}</span><span class="stat-lbl">Ø Float</span></div>
    <div class="stat-box"><span class="stat-val">{avg_si_str}</span><span class="stat-lbl">Ø SI-Trend</span></div>
  </div>

  <details class="info-panel">
    <summary>Score-Methodik &amp; Filterkriterien</summary>
    <div class="info-inner">
      <div class="info-box">
        <h4>Score (0–100)</h4>
        <ul>
          <li><strong>32 Pkt Short Float</strong> – Anteil leerverkaufter Aktien (Sättigung 50 %; ≥ 50 % = volle Punkte); je höher, desto stärker der Squeeze-Druck</li>
          <li><strong>23 Pkt Days to Cover</strong> – Tage zum vollständigen Eindecken (Sättigung 10 Tage; ≥ 10 d = volle Punkte); hohe Werte erhöhen Kapitulationsrisiko</li>
          <li><strong>23 Pkt Rel. Volumen</strong> – Heutiges vs. 20-Tage-Durchschnitt (Sättigung 3×; ≥ 3× = volle Punkte); Spitzen signalisieren Kaufinteresse</li>
          <li><strong>14 Pkt Kursmomentum</strong> – Kursveränderung relativ zum S&amp;P 500 (adjusted = Aktie − SPX; Sättigung +8 %; ≥ +8 % rel. Stärke = volle Punkte); nur positive Werte zählen</li>
          <li><strong>8 Pkt Float-Größe</strong> – kleiner Float verstärkt den Squeeze-Effekt; unter 30 Mio. Aktien = voll, über 50 Mio. = 0 Pkt</li>
          <li><strong>+ bis 7 Pkt FINRA SI-Trend Bonus</strong> – steigend ≥ +10 % → 5 Pkt · mit Beschleunigung → 7 Pkt · seitwärts → 2,5 Pkt · fallend → 0 Pkt</li>
          <li><strong>+ 5 Pkt Kombinationssignal-Bonus</strong> – wenn ≥ 3 von 4 Faktoren gleichzeitig stark: Short Float ≥ 30 %, DTC ≥ 5d, Rel. Volumen ≥ 2×, SI-Trend steigend</li>
          <li><strong>± 3 Pkt Score-Trend-Bonus/-Malus</strong> – +3 Pkt bei 3 Tagen kontinuierlichem Score-Anstieg; −3 Pkt bei 3 Tagen kontinuierlichem Rückgang (min 0)</li>
        </ul>
      </div>
      <div class="info-box">
        <h4>Filterkriterien</h4>
        <ul>
          <li><strong>Short Float &gt; 15 %</strong> – Mindest-Leerverkaufsquote (nur US)</li>
          <li><strong>Kurs &gt; 1 USD</strong> – Ausschluss von Penny Stocks</li>
          <li><strong>Marktkapitalisierung &lt; 10 Mrd. USD</strong> – Small- &amp; Mid-Caps</li>
          <li><strong>Relatives Volumen ≥ 1,5×</strong> – Mindestaktivität</li>
          <li><strong>Märkte:</strong> 🇺🇸 US · 🇩🇪 DE · 🇬🇧 GB · 🇫🇷 FR · 🇳🇱 NL · 🇨🇦 CA · 🇯🇵 JP · 🇭🇰 HK · 🇰🇷 KR</li>
          <li><strong>Internationale Aktien:</strong> kein Short-Float-Filter, Score gedeckelt bei 50 Pkt (nur Volumen + Momentum)</li>
        </ul>
      </div>
      <div class="info-box">
        <h4>Datenquellen</h4>
        <ul>
          <li><strong>Yahoo Finance Screener</strong> – Most Shorted, Small Cap Gainers, Aggressive Small Caps</li>
          <li><strong>FINRA</strong> – offizielles Short Interest; SI-Trend aus 6 Meldezeiträumen (≈ 3 Monate)</li>
          <li><strong>yfinance</strong> – Short Float, Days to Cover, Volumen, Kursdaten, RSI, MA50/200, Optionsdaten</li>
          <li><strong>Fails-to-Deliver:</strong> nicht verfügbar (IP-Beschränkung GitHub Actions)</li>
        </ul>
      </div>
      <div class="info-box">
        <h4>⚡ KI-Agent</h4>
        <p style="font-size:.82rem;color:var(--txt-sub);margin:0 0 8px">Der KI-Agent überwacht alle 30 Minuten die Top-10-Kandidaten auf Squeeze-Trigger.</p>
        <ul>
          <li><strong>Datenquellen:</strong> Yahoo Finance News, Google News, Seeking Alpha, MarketBeat, Unusual Whales, SEC EDGAR RSS, yfinance Intraday-Daten, Earnings-Kalender, FDA Press Release RSS</li>
          <li><strong>Signal-Schwellen:</strong> Kursanstieg ≥ 2 % · Volumen ≥ 1,5× · News-Keywords · Earnings ≤ 30 Tage</li>
          <li><strong>Alert-Schwelle:</strong> Score ≥ 25 Punkte</li>
        </ul>
      </div>
      <div class="info-box info-box--full">
        <h4>Farbcodierung der Kennzahlen</h4>
        <div class="color-legend">
          <div>
            <span class="cl-name">Short Float</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&lt;15 %</div>
              <div class="cb-seg" style="background:#f59e0b">15–29 %</div>
              <div class="cb-seg" style="background:#22c55e">≥ 30 %</div>
            </div>
            <p class="cl-desc">Grün bedeutet hohen Leerverkaufsdruck — je mehr Aktien leerverkauft sind, desto stärker der potenzielle Squeeze.</p>
          </div>
          <div>
            <span class="cl-name">Days to Cover</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&lt;3 d</div>
              <div class="cb-seg" style="background:#f59e0b">3–7 d</div>
              <div class="cb-seg" style="background:#22c55e">≥ 8 d</div>
            </div>
            <p class="cl-desc">Grün bedeutet, dass Leerverkäufer viele Tage brauchen würden, um ihre Positionen zu schließen — das erhöht den Druck bei steigendem Kurs.</p>
          </div>
          <div>
            <span class="cl-name">Rel. Volumen</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&lt;1,5×</div>
              <div class="cb-seg" style="background:#f59e0b">1,5–2,9×</div>
              <div class="cb-seg" style="background:#22c55e">≥ 3×</div>
            </div>
            <p class="cl-desc">Grün bedeutet ungewöhnlich hohes Handelsvolumen — ein Zeichen für aktiven Kaufdruck, der einen Squeeze auslösen kann.</p>
          </div>
          <div>
            <span class="cl-name">Kursmomentum</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&lt;0 %</div>
              <div class="cb-seg" style="background:#f59e0b">0–8 %</div>
              <div class="cb-seg" style="background:#22c55e">≥ +8 %</div>
            </div>
            <p class="cl-desc">Grün bedeutet, dass der Kurs bereits steigt — Leerverkäufer geraten damit unter Druck, ihre Positionen schnell zu schließen.</p>
          </div>
          <div>
            <span class="cl-name">Float-Größe</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&gt;50 Mio.</div>
              <div class="cb-seg" style="background:#f59e0b">30–50 Mio.</div>
              <div class="cb-seg" style="background:#22c55e">&lt;30 Mio.</div>
            </div>
            <p class="cl-desc">Grün bedeutet einen Streubesitz unter 30 Mio. Aktien — wenige handelbare Aktien verstärken den Squeeze-Effekt bei steigendem Kaufdruck erheblich.</p>
          </div>
          <div>
            <span class="cl-name">SI-Trend (3M)</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">Fallend ≤−10 %</div>
              <div class="cb-seg" style="background:#f59e0b">Seitwärts</div>
              <div class="cb-seg" style="background:#22c55e">Steigend ≥+10 %</div>
            </div>
            <p class="cl-desc">Grün bedeutet dass Leerverkäufer ihre Positionen in den letzten 3 Monaten ausgebaut haben — der Druck auf einen möglichen Squeeze wächst.</p>
          </div>
          <div>
            <span class="cl-name">Impl. Volatilität (IV)</span>
            <div class="color-bar">
              <div class="cb-seg" style="background:#ef4444">&lt;50 %</div>
              <div class="cb-seg" style="background:#f59e0b">50–100 %</div>
              <div class="cb-seg" style="background:#22c55e">&gt;100 %</div>
            </div>
            <p class="cl-desc">Hohe implizite Volatilität (IV &gt; 100 %) signalisiert dass der Markt eine extreme Kursbewegung erwartet — ein typisches Zeichen für erhöhtes Squeeze-Potential.</p>
          </div>
        </div>
      </div>
    </div>
  </details>

  <div class="disc">⚠ <strong>Disclaimer:</strong> Dieser Report dient ausschließlich Informationszwecken und stellt keine Anlageberatung dar. Keine Kauf- oder Verkaufsempfehlung.</div>

  <section class="wl-section" id="wl-section">
    <div class="wl-section-hdr">
      <span class="wl-section-title">Meine Watchlist</span>
      <span class="wl-count-badge" id="wl-count">0</span>
    </div>
    <div class="wl-cards" id="wl-cards"></div>
  </section>

  <div class="cards-grid">
  {cards}
  </div>
</main>

<footer class="footer">
  <p>Der Squeeze-Score ist ein rein rechnerischer Indikator und ersetzt keine individuelle Anlageberatung. Short-Squeeze-Kandidaten sind hochspekulative Investments mit erhöhtem Totalverlustrisiko. Nur mit kleinen Positionen und engem Stop-Loss handeln.</p>
  <p>Automatisch generiert am {report_date} · Quellen: Yahoo Finance (US/DE/GB/FR/NL/CA/JP/HK/KR), Finviz · Übersetzung: Google Translate</p>
</footer>

<script>
// ── Font Size ─────────────────────────────────────────────────────────────
const _FS_SIZES = [13, 15, 17, 19, 21];
const _FS_KEY   = 'squeeze_fs';
(function(){{
  const idx = Math.min(Math.max(parseInt(localStorage.getItem(_FS_KEY) ?? '1', 10), 0), _FS_SIZES.length - 1);
  document.documentElement.style.setProperty('--base-font-size', _FS_SIZES[idx] + 'px');
  window.addEventListener('DOMContentLoaded', () => _updateFsBtns(idx));
}})();
function _updateFsBtns(idx){{
  const d = document.getElementById('fs-down');
  const u = document.getElementById('fs-up');
  if (d) d.disabled = (idx === 0);
  if (u) u.disabled = (idx === _FS_SIZES.length - 1);
}}
function changeFontSize(dir){{
  const idx  = Math.min(Math.max(parseInt(localStorage.getItem(_FS_KEY) ?? '1', 10), 0), _FS_SIZES.length - 1);
  const next = Math.max(0, Math.min(_FS_SIZES.length - 1, idx + dir));
  document.documentElement.style.setProperty('--base-font-size', _FS_SIZES[next] + 'px');
  localStorage.setItem(_FS_KEY, String(next));
  _updateFsBtns(next);
}}
// ── Dark Mode ─────────────────────────────────────────────────────────────
(function(){{
  const saved = localStorage.getItem('theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', saved);
  window.addEventListener('DOMContentLoaded', () => {{
    document.getElementById('theme-btn').textContent = saved === 'dark' ? '☀️' : '🌙';
  }});
}})();
function toggleTheme(){{
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.getElementById('theme-btn').textContent = next === 'dark' ? '☀️' : '🌙';
}}
// ── Details dropdown ─────────────────────────────────────────────────────
function toggleDetails(id){{
  const body  = document.getElementById('dd' + id);
  const arrow = document.getElementById('da' + id);
  const label = document.getElementById('dl' + id);
  const btn   = document.getElementById('db' + id);
  const open  = body.classList.toggle('open');
  arrow.style.transform = open ? 'rotate(180deg)' : '';
  label.textContent = open ? ' Details ausblenden' : ' Details anzeigen';
  btn.setAttribute('aria-expanded', open);
}}
// ── News toggle ───────────────────────────────────────────────────────────
function toggleNews(id){{
  const panel = document.getElementById('np' + id);
  const btn   = document.getElementById('nb' + id);
  const icon  = document.getElementById('nb-icon' + id);
  const open  = panel.hidden;
  panel.hidden = !open;
  btn.setAttribute('aria-expanded', open);
  icon.textContent = open ? '▲' : '▼';
  btn.textContent  = '';
  btn.appendChild(icon);
  btn.append(' ' + (open ? 'Meldungen verbergen' : 'Aktuelle Meldungen'));
}}
// ── GitHub Actions Config ─────────────────────────────────────────────────
const GH_OWNER    = 'easywebb911';
const GH_REPO     = 'Aktien-update';
const GH_WORKFLOW    = 'daily-squeeze-report.yml';
const GH_WORKFLOW_KI = 'ki_agent.yml';
const GH_BRANCH   = 'main';
const TOK_KEY     = 'ghpat_squeeze';
// ─────────────────────────────────────────────────────────────────────────
function reloadPage(){{
  const btn = document.getElementById('btn-reload');
  btn.disabled = true; btn.textContent = 'Lädt…';
  window.location.reload();
}}
function triggerWorkflow(){{
  const token = localStorage.getItem(TOK_KEY);
  if (!token) {{ _pendingDispatch='recalc'; showTokenInput(); return; }}
  dispatchWorkflow(token);
}}
function showTokenInput(){{
  document.getElementById('tok-sec').style.display = 'block';
  document.getElementById('amsg').style.display = 'none';
  setTimeout(() => document.getElementById('tok-inp').focus(), 60);
}}
async function saveTokenAndDispatch(){{
  const token = document.getElementById('tok-inp').value.trim();
  if (!token) return;
  localStorage.setItem(TOK_KEY, token);
  document.getElementById('tok-sec').style.display = 'none';
  document.getElementById('tok-inp').value = '';
  if (_pendingDispatch === 'ki') {{ await dispatchKiWorkflow(token); }}
  else {{ await dispatchWorkflow(token); }}
  _pendingDispatch = null;
}}
async function dispatchWorkflow(token){{
  const btn = document.getElementById('btn-recalc');
  btn.disabled = true; btn.innerHTML = 'Startet…';
  try {{
    const r = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{GH_WORKFLOW}}/dispatches`,
      {{method:'POST',headers:{{'Authorization':`Bearer ${{token}}`,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}},
        body:JSON.stringify({{ref:GH_BRANCH}})}}
    );
    if (r.status === 204) {{
      _pollWorkflowId = GH_WORKFLOW; _pollRunningLabel = 'Neuberechnung';
      _pollEnableBtn = _enableRecalcBtn; _pollOnSuccess = _startSuccessCountdown;
      _pollStart = Date.now(); _pollToken = token;
      _showPollStatus('running');
      setTimeout(_doPoll, 5000);
    }} else if (r.status === 401 || r.status === 403) {{
      localStorage.removeItem(TOK_KEY);
      showMsg('error',`Token ungültig (HTTP ${{r.status}}). Bitte neu eingeben.`);
      _enableRecalcBtn();
    }} else {{
      const bd = await r.text().catch(()=>'');
      showMsg('error',`Fehler HTTP ${{r.status}}: ${{bd.slice(0,200)}}`);
      _enableRecalcBtn();
    }}
  }} catch(e) {{ showMsg('error',`Netzwerkfehler: ${{e.message}}`); _enableRecalcBtn(); }}
}}
// ── KI-Agent dispatch ─────────────────────────────────────────────────────
function _enableKiBtn(){{
  const btn = document.getElementById('btn-ki');
  if (btn) {{ btn.disabled=false; btn.innerHTML='&#9889; Agent Run'; }}
}}
function triggerKiAgent(){{
  const token = localStorage.getItem(TOK_KEY);
  if (!token) {{ _pendingDispatch='ki'; showTokenInput(); return; }}
  dispatchKiWorkflow(token);
}}
async function dispatchKiWorkflow(token){{
  const btn = document.getElementById('btn-ki');
  if (btn) {{ btn.disabled=true; btn.innerHTML='&#9889; L\u00e4uft\u2026'; }}
  try {{
    const r = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{GH_WORKFLOW_KI}}/dispatches`,
      {{method:'POST',headers:{{'Authorization':`Bearer ${{token}}`,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}},
        body:JSON.stringify({{ref:GH_BRANCH}})}}
    );
    if (r.status === 204) {{
      _pollWorkflowId = GH_WORKFLOW_KI; _pollRunningLabel = 'KI-Agent';
      _pollEnableBtn = _enableKiBtn; _pollOnSuccess = _kiAgentSuccess;
      _pollStart = Date.now(); _pollToken = token;
      _showPollStatus('running');
      setTimeout(_doPoll, 5000);
    }} else if (r.status === 401 || r.status === 403) {{
      localStorage.removeItem(TOK_KEY);
      showMsg('error',`Token ung\u00fcltig (HTTP ${{r.status}}). Bitte neu eingeben.`);
      _enableKiBtn();
    }} else {{
      const bd = await r.text().catch(()=>'');
      showMsg('error',`Fehler HTTP ${{r.status}}: ${{bd.slice(0,200)}}`);
      _enableKiBtn();
    }}
  }} catch(e) {{ showMsg('error',`Netzwerkfehler: ${{e.message}}`); _enableKiBtn(); }}
}}
function _kiAgentSuccess(){{
  _stopTimeInterval();
  const el = document.getElementById('amsg');
  el.style.display='block'; el.className='amsg amsg-poll-done';
  el.innerHTML='<span class="poll-dot poll-dot-done"></span>KI-Agent abgeschlossen \u2014 Signale werden aktualisiert\u2026';
  fetch('./agent_signals.json?_=' + Date.now())
    .then(r => r.ok ? r.json() : {{}})
    .then(data => {{
      if (typeof renderAgentSignals === 'function') renderAgentSignals(data);
      el.innerHTML='<span class="poll-dot poll-dot-done"></span>KI-Agent abgeschlossen \u2014 Signale aktualisiert.';
      setTimeout(()=>{{el.style.display='none';}}, 8000);
    }})
    .catch(()=>{{
      el.innerHTML='<span class="poll-dot poll-dot-err"></span>KI-Agent abgeschlossen \u2014 Seite neu laden.';
    }});
  _enableKiBtn();
}}
// ── Workflow polling ──────────────────────────────────────────────────────
const POLL_MS    = 10000;
const TIMEOUT_MS = 600000;
let _pollStart = null, _pollToken = null, _pollTimer = null;
let _timeInterval = null;
let _pendingDispatch = null;
let _pollWorkflowId = GH_WORKFLOW, _pollRunningLabel = 'Neuberechnung';
let _pollEnableBtn = null, _pollOnSuccess = null;
function _elapsedStr(){{
  const s = Math.floor((Date.now()-_pollStart)/1000);
  const m = Math.floor(s/60), r = s%60;
  return m>0 ? `${{m}}:${{String(r).padStart(2,'0')}} min` : `${{s}} s`;
}}
function _stopTimeInterval(){{
  if (_timeInterval){{ clearInterval(_timeInterval); _timeInterval=null; }}
}}
function _enableRecalcBtn(){{
  const btn = document.getElementById('btn-recalc');
  btn.disabled=false; btn.innerHTML='&#9881; Recalculate';
}}
function _showPollStatus(state){{
  const el = document.getElementById('amsg');
  el.style.display='block';
  if (state==='running'){{
    el.className='amsg amsg-poll-running';
    el.innerHTML='<span class="poll-dot poll-dot-run"></span>' + _pollRunningLabel + ' läuft \u2026 <span id="poll-elapsed"></span>';
    const span = document.getElementById('poll-elapsed');
    if (span) span.textContent = _elapsedStr();
    _stopTimeInterval();
    _timeInterval = setInterval(()=>{{
      const sp = document.getElementById('poll-elapsed');
      if (sp) sp.textContent = _elapsedStr();
    }}, 1000);
  }} else if (state==='failure'){{
    _stopTimeInterval();
    el.className='amsg amsg-error';
    el.innerHTML=`<span class="poll-dot poll-dot-err"></span>Workflow fehlgeschlagen — bitte GitHub Actions prüfen.`;
  }} else if (state==='timeout'){{
    _stopTimeInterval();
    el.className='amsg amsg-error';
    el.textContent='Zeitüberschreitung — bitte Seite manuell neu laden.';
  }}
}}
const CD_SECS = 30;
let _cdInterval = null;
function _startSuccessCountdown(){{
  let n = CD_SECS;
  const el = document.getElementById('amsg');
  el.style.display='block';
  el.className='amsg amsg-poll-done';
  el.innerHTML =
    '<span class="poll-dot poll-dot-done"></span>' +
    '<div class="amsg-cd-body">' +
      '<div class="amsg-cd-title">Neuberechnung abgeschlossen</div>' +
      '<div class="amsg-cd-sub">Seite wird in <span id="cd-secs">' + n + '</span> Sekunden automatisch neu geladen — oder jetzt manuell neu laden.</div>' +
      '<div class="amsg-cd-bar-wrap"><div class="amsg-cd-bar" id="cd-bar" style="width:100%"></div></div>' +
      '<button class="amsg-cd-btn" onclick="_manualReload()">Jetzt neu laden</button>' +
    '</div>';
  if (_cdInterval) clearInterval(_cdInterval);
  _cdInterval = setInterval(()=>{{
    n--;
    const secsEl = document.getElementById('cd-secs');
    const barEl  = document.getElementById('cd-bar');
    if (secsEl) secsEl.textContent = n;
    if (barEl)  barEl.style.width  = (n / CD_SECS * 100) + '%';
    if (n <= 0){{ clearInterval(_cdInterval); _cdInterval = null; window.location.reload(); }}
  }}, 1000);
}}
function _manualReload(){{
  if (_cdInterval){{ clearInterval(_cdInterval); _cdInterval = null; }}
  window.location.reload();
}}
window.addEventListener('beforeunload', ()=>{{
  if (_cdInterval){{ clearInterval(_cdInterval); _cdInterval = null; }}
  _stopTimeInterval();
}});
async function _doPoll(){{
  if (Date.now()-_pollStart>TIMEOUT_MS) {{ _showPollStatus('timeout'); if(_pollEnableBtn)_pollEnableBtn(); return; }}
  try {{
    const res = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/runs?workflow_id=${{_pollWorkflowId}}&per_page=5&event=workflow_dispatch`,
      {{headers:{{'Authorization':`Bearer ${{_pollToken}}`,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}}}}
    );
    if (!res.ok) {{ _pollTimer=setTimeout(_doPoll,POLL_MS); return; }}
    const data = await res.json();
    const run = (data.workflow_runs||[]).find(w=>new Date(w.created_at).getTime()>=_pollStart-15000);
    if (!run) {{ _pollTimer=setTimeout(_doPoll,POLL_MS); return; }}
    if (run.status==='completed'){{
      if (run.conclusion==='success') {{ _stopTimeInterval(); if(_pollOnSuccess)_pollOnSuccess(); }}
      else {{ _showPollStatus('failure'); if(_pollEnableBtn)_pollEnableBtn(); }}
    }} else {{
      _pollTimer=setTimeout(_doPoll,POLL_MS);
    }}
  }} catch(e) {{ _pollTimer=setTimeout(_doPoll,POLL_MS); }}
}}
function resetToken(){{
  localStorage.removeItem(TOK_KEY);
  document.getElementById('tok-sec').style.display='none';
  showMsg('info','Token zurückgesetzt.');
}}
function showMsg(type,text){{
  const el=document.getElementById('amsg');
  el.className=`amsg amsg-${{type}}`;
  el.textContent=text;
  el.style.display='block';
  if(type!=='error') setTimeout(()=>{{el.style.display='none';}},13000);
}}

// ── Gemeinsame Handelstag-Hilfsfunktionen (wird von Banner + KI-Agent genutzt) ──
// US federal holidays — update this array each year (format: "YYYY-MM-DD").
// Observed dates (Monday if Sunday, Friday if Saturday) should be listed.
const US_HOLIDAYS = [
  // 2025
  "2025-01-01", // New Year's Day
  "2025-01-20", // MLK Day
  "2025-02-17", // Presidents' Day
  "2025-05-26", // Memorial Day
  "2025-06-19", // Juneteenth
  "2025-07-04", // Independence Day
  "2025-09-01", // Labor Day
  "2025-11-27", // Thanksgiving
  "2025-12-25", // Christmas
  // 2026
  "2026-01-01", // New Year's Day
  "2026-01-19", // MLK Day
  "2026-02-16", // Presidents' Day
  "2026-05-25", // Memorial Day
  "2026-06-19", // Juneteenth
  "2026-07-03", // Independence Day (observed, 4th = Saturday)
  "2026-09-07", // Labor Day
  "2026-11-26", // Thanksgiving
  "2026-12-25", // Christmas
  // 2027
  "2027-01-01", // New Year's Day
  "2027-01-18", // MLK Day
  "2027-02-15", // Presidents' Day
  "2027-05-31", // Memorial Day
  "2027-06-18", // Juneteenth (observed, 19th = Saturday)
  "2027-07-05", // Independence Day (observed, 4th = Sunday)
  "2027-09-06", // Labor Day
  "2027-11-25", // Thanksgiving
  "2027-12-24", // Christmas (observed, 25th = Saturday)
];
function _toIso(d) {{
  const y = d.getFullYear();
  const m = String(d.getMonth()+1).padStart(2,'0');
  const day = String(d.getDate()).padStart(2,'0');
  return `${{y}}-${{m}}-${{day}}`;
}}
function _isHoliday(d)        {{ return US_HOLIDAYS.includes(_toIso(d)); }}
function _isNonTradingDay(d)  {{ const dow = d.getDay(); return dow === 0 || dow === 6 || _isHoliday(d); }}
function _nextTradingDay(d) {{
  const next = new Date(d);
  next.setDate(next.getDate() + 1);
  while (_isNonTradingDay(next)) next.setDate(next.getDate() + 1);
  return next;
}}
function _fmtGerman(d) {{
  const weekdays = ['Sonntag','Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag'];
  const months   = ['Januar','Februar','März','April','Mai','Juni',
                    'Juli','August','September','Oktober','November','Dezember'];
  return `${{weekdays[d.getDay()]}}, ${{d.getDate()}}. ${{months[d.getMonth()]}} ${{d.getFullYear()}}`;
}}

// ── Non-trading-day banner ────────────────────────────────────────────────────
(function(){{
  const today = new Date();
  today.setHours(0,0,0,0);
  if (_isNonTradingDay(today)) {{
    const ntd = _nextTradingDay(today);
    const dow = today.getDay();
    const reason = (dow === 6 || dow === 0) ? 'Wochenende' : 'US-Feiertag';
    const banner = document.getElementById('non-trading-banner');
    banner.textContent =
      `\u26a0\ufe0f Kein Handelstag (${{reason}}) \u2014 ` +
      `Nächster US-Handelstag: ${{_fmtGerman(ntd)}}. ` +
      `Die angezeigten Daten stammen vom letzten Handelstag.`;
    banner.style.display = 'block';
  }}
}})();
// ─────────────────────────────────────────────────────────────────────────────

// ── Sparkline renderer ────────────────────────────────────────────────────────
(function(){{
  const isMobile = ('ontouchstart' in window) || (window.matchMedia('(pointer:coarse)').matches);
  const DAYS_DE  = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  const PAD      = {{l:4, r:4, t:6, b:6}};
  const H        = 60;
  const PT_R     = isMobile ? 6 : 5;

  function parseIso(s) {{ return new Date(s + 'T12:00:00'); }}

  // Returns true if consecutive data points have a missing trading day between them
  function isGap(d1, d2) {{
    const diff = Math.round((d2 - d1) / 86400000);
    if (diff <= 1) return false;
    if (diff === 3 && d1.getDay() === 5) return false; // Fri→Mon = normal weekend
    return true;
  }}

  function drawSparkline(wrap) {{
    const scores  = JSON.parse(wrap.dataset.scores || '[]');
    const dates   = JSON.parse(wrap.dataset.dates  || '[]'); // ISO YYYY-MM-DD
    const col     = wrap.dataset.col   || '#94a3b8';
    const todayS  = wrap.dataset.today || '';
    const n       = scores.length;
    if (n < 2) return;

    const svgWrap  = wrap.querySelector('.spark-svg-wrap');
    const daysWrap = wrap.querySelector('.spark-days');
    if (!svgWrap) return;

    const W = svgWrap.clientWidth || 280;

    const dateParsed = dates.map(parseIso);
    const firstDate  = dateParsed[0];
    const lastDate   = dateParsed[n - 1];

    // Ghost dot: show if today is strictly after the last recorded date
    const hasGhost  = todayS && todayS > dates[n - 1];
    const ghostDate = hasGhost ? parseIso(todayS) : null;

    // X-axis spans from firstDate to max(lastDate, today)
    const spanEnd    = hasGhost ? ghostDate : lastDate;
    const totalMs    = spanEnd - firstDate || 1;

    function xOf(d) {{
      return PAD.l + ((d - firstDate) / totalMs) * (W - PAD.l - PAD.r);
    }}

    const minS  = Math.min(...scores);
    const maxS  = Math.max(...scores);
    const range = maxS - minS || 1;

    function yOf(val) {{
      return PAD.t + (1 - (val - minS) / range) * (H - PAD.t - PAD.b);
    }}

    // Build area fill (continuous, no gaps) and stroke path (with gaps)
    let areaD = '', lineD = '', newSeg = true;
    for (let i = 0; i < n; i++) {{
      const cx = xOf(dateParsed[i]).toFixed(1);
      const cy = yOf(scores[i]).toFixed(1);
      if (i === 0) {{
        areaD += `M${{cx}},${{cy}}`;
        lineD += `M${{cx}},${{cy}}`;
        newSeg = false;
      }} else {{
        areaD += `L${{cx}},${{cy}}`;
        lineD += (newSeg ? `M${{cx}},${{cy}}` : `L${{cx}},${{cy}}`);
        newSeg = false;
      }}
      if (i < n - 1 && isGap(dateParsed[i], dateParsed[i + 1])) newSeg = true;
    }}
    // Close area along bottom baseline
    const x0 = xOf(dateParsed[0]).toFixed(1);
    const xN = xOf(dateParsed[n-1]).toFixed(1);
    areaD += ` L${{xN}},${{(H - PAD.b).toFixed(1)}} L${{x0}},${{(H - PAD.b).toFixed(1)}} Z`;

    const svgId = 'sp' + Math.random().toString(36).slice(2, 7);

    // Real data circles
    let circlesHtml = '';
    for (let i = 0; i < n; i++) {{
      const cx = xOf(dateParsed[i]).toFixed(1);
      const cy = yOf(scores[i]).toFixed(1);
      const dow = DAYS_DE[dateParsed[i].getDay()];
      const dd  = dates[i].slice(8, 10) + '.' + dates[i].slice(5, 7);
      circlesHtml += `<circle class="sp-dot" cx="${{cx}}" cy="${{cy}}" r="${{PT_R}}" fill="${{col}}" stroke="var(--bg-card)" stroke-width="1.5" data-score="${{scores[i]}}" data-label="${{dow}} ${{dd}} · ${{scores[i]}} Pkt"/>`;
    }}

    // Ghost dot — gray, no connecting line
    let ghostHtml = '';
    if (hasGhost) {{
      const cx = xOf(ghostDate).toFixed(1);
      const cy = (H / 2).toFixed(1);
      ghostHtml = `<circle class="sp-dot sp-ghost" cx="${{cx}}" cy="${{cy}}" r="${{PT_R}}" fill="#6b7280" stroke="var(--bg-card)" stroke-width="1.5" data-score="" data-label="Heute nicht in Top 10"/>`;
    }}

    const svg = `<svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="sg${{svgId}}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${{col}}" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="${{col}}" stop-opacity="0.03"/>
    </linearGradient>
  </defs>
  <path d="${{areaD}}" fill="url(#sg${{svgId}})"/>
  <path d="${{lineD}}" fill="none" stroke="${{col}}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  ${{circlesHtml}}${{ghostHtml}}
</svg>`;
    svgWrap.innerHTML = svg;

    // Day labels under each point
    if (daysWrap) {{
      daysWrap.innerHTML = '';
      for (let i = 0; i < n; i++) {{
        const pct = (xOf(dateParsed[i]) / W * 100).toFixed(1);
        const lbl = document.createElement('span');
        lbl.className = 'spark-day-lbl';
        lbl.style.left = pct + '%';
        lbl.textContent = DAYS_DE[dateParsed[i].getDay()];
        daysWrap.appendChild(lbl);
      }}
      if (hasGhost) {{
        const pct = (xOf(ghostDate) / W * 100).toFixed(1);
        const lbl = document.createElement('span');
        lbl.className = 'spark-day-lbl ghost';
        lbl.style.left = pct + '%';
        lbl.textContent = '–';
        daysWrap.appendChild(lbl);
      }}
    }}

    // Tooltip
    const tip = document.createElement('div');
    tip.className = 'spark-tip';
    svgWrap.appendChild(tip);

    let hideTimer = null;
    const hideTip = () => {{ if (hideTimer) clearTimeout(hideTimer); tip.classList.remove('visible'); }};

    svgWrap.querySelectorAll('.sp-dot').forEach(dot => {{
      const show = () => {{
        if (hideTimer) clearTimeout(hideTimer);
        tip.textContent = dot.dataset.label;
        tip.style.left  = dot.getAttribute('cx') + 'px';
        tip.style.top   = dot.getAttribute('cy') + 'px';
        tip.classList.add('visible');
      }};
      if (isMobile) {{
        dot.addEventListener('touchstart', e => {{
          e.preventDefault(); show();
          hideTimer = setTimeout(() => tip.classList.remove('visible'), 2000);
        }}, {{passive: false}});
      }} else {{
        dot.addEventListener('mouseenter', show);
        dot.addEventListener('mouseleave', hideTip);
      }}
    }});
  }}

  function initAll() {{
    document.querySelectorAll('.spark-wrap').forEach(drawSparkline);
  }}

  window.drawSparkline = drawSparkline;

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initAll);
  }} else {{
    initAll();
  }}
}})();
// ─────────────────────────────────────────────────────────────────────────────
// ── KI-Agent Signal Indicators ───────────────────────────────────────────────
(function() {{
  function renderAgentSignals(data) {{
    const statusEl = document.getElementById('agent-status');
    const updated  = data.updated ? new Date(data.updated) : null;
    const signals  = data.signals || {{}};
    const info     = data.run_info || {{}};

    // Status-Bar — 24/7, vereinfacht
    if (!updated) {{
      if (statusEl) statusEl.textContent = '\u26a1 KI-Agent: Kein aktueller Scan verfügbar.';
    }} else {{
      const ageMin   = (Date.now() - updated.getTime()) / 60000;
      const phase    = info.market_phase || '';
      const lastScan = updated.toLocaleTimeString('de-DE', {{hour:'2-digit', minute:'2-digit'}});
      const nSignals = info.signals_active || 0;
      if (ageMin > 45) {{
        if (statusEl) statusEl.textContent =
          `\u26a1 KI-Agent: Scan verz\u00f6gert \u2014 letzter Stand ${{lastScan}} Uhr`;
      }} else {{
        if (statusEl) statusEl.textContent =
          `\u26a1 KI-Agent: Letzter Scan ${{lastScan}} Uhr \u2014 ${{phase}} \u2014 ${{nSignals}} Signale aktiv`;
      }}
    }}

    // Dots auf Karten (immer gerendert wenn Signaldaten vorhanden)
    document.querySelectorAll('.card[data-ticker]').forEach(card => {{
      const ticker = card.getAttribute('data-ticker');
      const sig    = signals[ticker];
      const score  = (sig && sig.score != null) ? sig.score : 0;
      // Expose for Claude KI-Analyse button
      card.dataset.kiScore = String(score);
      if (sig && sig.drivers)       card.dataset.kiDrivers = String(sig.drivers);
      if (sig && sig.confidence != null) card.dataset.kiConf = String(sig.confidence);
      const tickerSpan = card.querySelector('.ticker');
      if (!tickerSpan) return;

      const dot = document.createElement('span');
      let dotClass;
      if (score >= 70)      dotClass = 'strong';   // grün, schnell (1s)
      else if (score >= 40) dotClass = 'moderate'; // orange, mittel (1.5s)
      else if (score >= 15) dotClass = 'weak';     // rot, langsam (2s)
      else                  dotClass = 'none';     // grau, kein Pulsieren (Score 0–14)
      dot.className = 'agent-dot ' + dotClass;

      const confidence = (sig && sig.confidence != null) ? sig.confidence : null;
      const confStr = confidence != null ? ` \u2014 Konfidenz ${{confidence}}%` : '';
      const tip = document.createElement('span');
      tip.className = 'agent-tooltip';
      tip.textContent = `KI-Agent: Score ${{score}}/100${{confStr}} \u2014 ${{(sig && sig.drivers) || '?'}}`;
      dot.appendChild(tip);

      // iPhone: Antippen zeigt Tooltip für 3s
      dot.addEventListener('click', function(e) {{
        e.stopPropagation();
        dot.classList.add('touch-visible');
        setTimeout(() => dot.classList.remove('touch-visible'), 3000);
      }});

      tickerSpan.parentNode.insertBefore(dot, tickerSpan.nextSibling);

      // Watchlist-Kompaktkarte: dot synchronisieren
      const wlDot = document.getElementById('wlkd-' + ticker);
      if (wlDot) wlDot.className = 'wl-ki-dot agent-dot ' + dotClass;

      // KI-Signal-Block im Neuigkeiten-Dropdown
      const block = card.querySelector('.ki-signal-block');
      if (block && score > 0) {{
        const lastScan = updated
          ? updated.toLocaleTimeString('de-DE', {{hour:'2-digit', minute:'2-digit'}})
          : '?';
        const phase = info.market_phase || '';
        const body  = block.querySelector('.ki-signal-body');
        if (body) {{
          const confBlock = (sig && sig.confidence != null)
            ? `<span class="ki-confidence">Konfidenz: ${{sig.confidence}}% (${{sig.confidence >= 70 ? 'hoch' : sig.confidence >= 40 ? 'mittel' : 'gering'}})</span>`
            : '';
          body.innerHTML =
            `<span class="ki-score">Score: ${{score}}/100</span>` +
            confBlock +
            ((sig && sig.drivers)
              ? `<span class="ki-drivers">${{sig.drivers}}</span>`
              : '') +
            `<span class="ki-meta">Letzter Scan: ${{lastScan}} Uhr` +
            (phase ? ` \u2014 ${{phase}}` : '') + '</span>';
        }}
        block.style.display = 'block';
      }}
    }});
  }}

  fetch('./agent_signals.json?_=' + Date.now())
    .then(r => r.ok ? r.json() : {{}})
    .then(renderAgentSignals)
    .catch(() => {{
      const el = document.getElementById('agent-status');
      if (el) el.textContent = 'KI-Agent: Kein aktueller Scan verfügbar.';
    }});
}})();
// ── Persönliche Watchlist ─────────────────────────────────────────────────────
(function(){{
  const WL_KEY     = 'squeeze_watchlist';
  const WL_MAX     = 20;
  const WL_GH_PATH = 'watchlist_personal.json';
  const WL_SCORES  = {wl_scores_json};
  const WL_TOP10   = {wl_top10_json};
  const WL_HIST    = {wl_hist_json};

  let _wlGhSha = null;
  let _wlCache = null;

  // ── Async load — GitHub first (if token available), localStorage fallback ──
  async function wlLoad() {{
    if (_wlCache !== null) return _wlCache.slice();
    const token = localStorage.getItem(TOK_KEY);
    if (token) {{
      try {{
        const r = await fetch(
          `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/${{WL_GH_PATH}}?ref=${{GH_BRANCH}}`,
          {{headers: {{'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}}}}
        );
        if (r.status === 404) {{ _wlGhSha = null; _wlCache = []; return []; }}
        if (r.ok) {{
          const j = await r.json();
          _wlGhSha = j.sha;
          const arr = JSON.parse(atob(j.content.replace(/\\n/g, '')));
          localStorage.setItem(WL_KEY, JSON.stringify(arr));
          _wlCache = arr;
          return arr.slice();
        }}
      }} catch(_) {{}}  // network error — fall through to localStorage
    }}
    const arr = JSON.parse(localStorage.getItem(WL_KEY) || '[]');
    _wlCache = arr;
    return arr.slice();
  }}

  // ── Async save — localStorage always, GitHub when token available ──────────
  async function wlSave(arr) {{
    arr = arr.slice(0, WL_MAX);
    _wlCache = arr;
    localStorage.setItem(WL_KEY, JSON.stringify(arr));
    const token = localStorage.getItem(TOK_KEY);
    if (!token) return;
    try {{
      const _put = async (sha) => {{
        const body = {{message: 'Update watchlist_personal.json',
                      content: btoa(JSON.stringify(arr)), branch: GH_BRANCH}};
        if (sha) body.sha = sha;
        return fetch(
          `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/${{WL_GH_PATH}}`,
          {{method: 'PUT',
            headers: {{'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github+json',
                      'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'}},
            body: JSON.stringify(body)}});
      }};
      let r = await _put(_wlGhSha);
      if (r.ok) {{ _wlGhSha = (await r.json()).content?.sha || null; return; }}
      if (r.status === 409 || r.status === 422) {{
        // SHA conflict — re-fetch current SHA and retry once
        const rf = await fetch(
          `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/${{WL_GH_PATH}}?ref=${{GH_BRANCH}}`,
          {{headers: {{'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}}}}
        );
        if (rf.ok) {{
          _wlGhSha = (await rf.json()).sha;
          r = await _put(_wlGhSha);
          if (r.ok) {{ _wlGhSha = (await r.json()).content?.sha || null; }}
        }}
      }}
    }} catch(_) {{}}  // silent — localStorage already saved
  }}
  function wlScoreColor(v) {{
    if (v === null) return '#94a3b8';
    return v >= 50 ? '#22c55e' : v >= 30 ? '#f59e0b' : '#ef4444';
  }}
  function fmt(n, dec) {{ dec = dec == null ? 1 : dec; return n != null && isFinite(+n) ? (+n).toFixed(dec) : '\u2014'; }}
  function fmtPct(n)   {{ return n != null && isFinite(+n) ? (+n).toFixed(1) + '%' : '\u2014'; }}
  function fmtVol(n) {{
    if (!n) return '\u2014';
    const v = +n;
    return v > 1e6 ? (v/1e6).toFixed(1)+'M' : v > 1e3 ? (v/1e3).toFixed(0)+'K' : v.toFixed(0);
  }}
  function fmtCap(n) {{
    if (!n) return '\u2014';
    const v = +n;
    return v > 1e12 ? (v/1e12).toFixed(2)+'T' : v > 1e9 ? (v/1e9).toFixed(1)+'B' : v > 1e6 ? (v/1e6).toFixed(0)+'M' : '\u2014';
  }}
  function metColor(type, val) {{
    if (val == null || !isFinite(+val)) return '#94a3b8';
    const v = +val;
    if (type === 'sf')  return v >= 20 ? '#22c55e' : v >= 10 ? '#f59e0b' : '#94a3b8';
    if (type === 'sr')  return v >= 10 ? '#22c55e' : v >= 5  ? '#f59e0b' : '#94a3b8';
    if (type === 'rv')  return v >= 2  ? '#22c55e' : v >= 1.2? '#f59e0b' : '#94a3b8';
    if (type === 'chg') return v >= 3  ? '#22c55e' : v >= -3 ? '#f59e0b' : '#ef4444';
    return '#94a3b8';
  }}

  function buildWlDetails(ticker, d) {{
    try {{
      const sfCol  = metColor('sf',  d.short_float);
      const srCol  = metColor('sr',  d.short_ratio);
      const rvCol  = metColor('rv',  d.rel_volume);
      const chgCol = metColor('chg', d.change);
      const siCol  = d.si_trend === 'up' ? '#22c55e' : d.si_trend === 'down' ? '#ef4444' : '#94a3b8';
      const siArr  = d.si_trend === 'up' ? '\u2191' : d.si_trend === 'down' ? '\u2193' : '\u2192';
      const chgSign = (d.change != null && isFinite(+d.change) && +d.change >= 0) ? '+' : '';
      const tiles = `<div class="metrics-row" style="padding:10px 10px 8px">
        <div class="metric-box" style="--mc:${{sfCol}}">
          <span class="m-val">${{fmtPct(d.short_float)}}</span>
          <span class="m-lbl">Short Float</span>
        </div>
        <div class="metric-box" style="--mc:${{srCol}}">
          <span class="m-val">${{fmt(d.short_ratio)}}</span>
          <span class="m-lbl">Days to Cover</span>
        </div>
        <div class="metric-box" style="--mc:${{rvCol}}">
          <span class="m-val">${{d.rel_volume != null ? (+d.rel_volume).toFixed(1)+'\xd7' : '\u2014'}}</span>
          <span class="m-lbl">Volumen</span>
        </div>
        <div class="metric-box" style="--mc:${{chgCol}}">
          <span class="m-val">${{d.change != null ? chgSign+fmtPct(d.change) : '\u2014'}}</span>
          <span class="m-lbl">Momentum</span>
        </div>
        <div class="metric-box" style="--mc:#94a3b8">
          <span class="m-val">${{d.float_shares > 0 ? (d.float_shares/1e6).toFixed(1)+'M' : '\u2014'}}</span>
          <span class="m-lbl">Float</span>
        </div>
        <div class="metric-box" style="--mc:${{siCol}}">
          <span class="m-val">${{siArr}}</span>
          <span class="m-lbl">SI-Trend</span>
        </div>
      </div>`;

      const h = WL_HIST[ticker];
      let sparkHtml = '';
      if (h && h.scores && h.scores.length >= 2) {{
        const scoresE = JSON.stringify(h.scores).replace(/"/g, '&quot;');
        const datesE  = JSON.stringify(h.dates).replace(/"/g, '&quot;');
        sparkHtml = `<div class="spark-wrap wl-spark" style="padding:0 10px 10px"
          data-scores="${{scoresE}}" data-dates="${{datesE}}"
          data-col="${{h.col}}" data-today="">
          <div class="spark-svg-wrap" style="height:56px"></div>
          <div class="spark-days"></div>
        </div>`;
      }}

      const priceStr = d.price ? '$' + (+d.price).toFixed(2) : '\u2014';
      const hiStr    = d['52w_high'] ? '$' + (+d['52w_high']).toFixed(2) : '\u2014';
      const loStr    = d['52w_low']  ? '$' + (+d['52w_low']).toFixed(2)  : '\u2014';
      const siVelStr = d.si_velocity != null ? fmt(d.si_velocity, 2) + '%' + (d.si_accel ? ' \u2b06' : '') : '\u2014';
      const earStr   = d.earnings_days != null
        ? 'T+' + d.earnings_days + 'd (' + (d.earnings_date_str || '?') + ')'
        : '\u2014';
      const tableHtml = `<div class="detail-table-wrap" style="padding:0 10px 10px">
        <table class="detail-table">
          <tr><td>Preis</td><td>${{priceStr}}</td></tr>
          <tr><td>Marktkapitalisierung</td><td>${{fmtCap(d.market_cap)}}</td></tr>
          <tr><td>Sektor</td><td>${{d.sector || '\u2014'}}</td></tr>
          <tr><td>52W-Hoch / -Tief</td><td>${{hiStr}} / ${{loStr}}</td></tr>
          <tr><td>\xd8 Volumen 20T</td><td>${{fmtVol(d.avg_vol_20d)}}</td></tr>
          <tr><td>Heutiges Volumen</td><td>${{fmtVol(d.cur_vol)}}</td></tr>
          <tr><td>SI-Trend (3M)</td><td>${{d.si_trend || '\u2014'}}${{d.si_tpct ? ' ' + fmtPct(d.si_tpct) : ''}}</td></tr>
          <tr><td>SI-Velocity</td><td>${{siVelStr}}</td></tr>
          <tr><td>Short-Vol. T-1 (FINRA)</td><td>${{d.si_t1 || '\u2014'}}</td></tr>
          <tr><td>Short-Vol. T-2</td><td>${{d.si_t2 || '\u2014'}}</td></tr>
          <tr><td>Short-Vol. T-3</td><td>${{d.si_t3 || '\u2014'}}</td></tr>
          <tr><td>RSI 14</td><td>${{fmt(d.rsi14, 1)}}</td></tr>
          <tr><td>MA 50</td><td>${{d.ma50 != null ? '$' + (+d.ma50).toFixed(2) : '\u2014'}}</td></tr>
          <tr><td>MA 200</td><td>${{d.ma200 != null ? '$' + (+d.ma200).toFixed(2) : '\u2014'}}</td></tr>
          <tr><td>Put/Call-Ratio</td><td>${{fmt(d.pc_ratio, 2)}}</td></tr>
          <tr><td>ATM IV</td><td>${{d.atm_iv != null ? fmtPct(d.atm_iv * 100) : '\u2014'}}</td></tr>
          <tr><td>Inst. Beteiligung</td><td>${{fmtPct(d.inst_ownership)}}</td></tr>
          <tr><td>Rel. St\xe4rke 20T</td><td>${{fmt(d.rel_strength_20d, 2)}}</td></tr>
          <tr><td>Performance 20T</td><td>${{d.perf_20d != null ? (d.perf_20d>=0?'+':'')+fmtPct(d.perf_20d) : '\u2014'}}</td></tr>
          <tr><td>N\xe4chste Earnings</td><td>${{earStr}}</td></tr>
        </table>
      </div>`;

      let newsHtml = '';
      if (d.news && d.news.length) {{
        const items = d.news.map(n =>
          `<div class="ni"><a href="${{n.link}}" target="_blank" rel="noopener">${{n.title}}</a>` +
          (n.source ? ` <span class="ni-src">(${{n.source}})</span>` : '') +
          `<span class="ni-meta">${{n.time || ''}}</span></div>`
        ).join('');
        newsHtml = `<div class="news-items" style="padding:0 10px 10px">${{items}}</div>`;
      }}

      return tiles + sparkHtml + tableHtml + newsHtml;
    }} catch(e) {{
      console.error('buildWlDetails Fehler:', e);
      return '<div class="wl-no-data">Fehler beim Laden der Details.</div>';
    }}
  }}

  function buildWlSparkOnly(ticker, h) {{
    try {{
      if (!h || !h.scores || h.scores.length < 2) {{
        return '<div class="wl-no-data">Kein Score-Verlauf vorhanden.</div>';
      }}
      const scoresE = JSON.stringify(h.scores).replace(/"/g, '&quot;');
      const datesE  = JSON.stringify(h.dates).replace(/"/g, '&quot;');
      return `<div class="spark-wrap wl-spark" style="padding:10px 10px 4px"
        data-scores="${{scoresE}}" data-dates="${{datesE}}"
        data-col="${{h.col}}" data-today="">
        <div class="spark-svg-wrap" style="height:56px"></div>
        <div class="spark-days"></div>
      </div>
      <div class="wl-no-data">Nicht in aktueller Top-10 \u2014 keine Live-Daten.</div>`;
    }} catch(e) {{
      console.error('buildWlSparkOnly Fehler:', e);
      return '<div class="wl-no-data">Fehler beim Laden der Details.</div>';
    }}
  }}

  async function wlRender() {{
    try {{
      const arr  = await wlLoad();
      const sec  = document.getElementById('wl-section');
      const grid = document.getElementById('wl-cards');
      const cnt  = document.getElementById('wl-count');
      if (!arr.length) {{ sec.classList.remove('has-items'); return; }}
      sec.classList.add('has-items');
      cnt.textContent = arr.length;

      const top10Set = new Set(Object.keys(WL_TOP10));

      grid.innerHTML = arr.map(ticker => {{
        const inTop   = top10Set.has(ticker);
        const scoreVal = inTop
          ? (WL_TOP10[ticker].score ?? null)
          : (WL_SCORES[ticker] ?? null);
        const scoreStr = scoreVal !== null ? (+scoreVal).toFixed(1) : '\u2014';
        const scoreCol = wlScoreColor(scoreVal);
        const flag = (inTop && WL_TOP10[ticker].flag) ? WL_TOP10[ticker].flag : '';
        const h = WL_HIST[ticker];
        const trendArrow = h ? (h.col === '#22c55e' ? '\u2191' : h.col === '#ef4444' ? '\u2193' : '\u2192') : '';
        const trendCol   = h ? h.col : '#94a3b8';
        return `<div class="wl-card" data-ticker="${{ticker}}">
          ${{inTop ? '<span class="wl-badge-star">\u2605</span>' : ''}}
          <div class="wl-card-header">
            <div style="display:flex;align-items:center;gap:4px;width:100%">
              <span class="wl-card-ticker">${{ticker}}</span>
              ${{flag ? `<span style="font-size:.85rem">${{flag}}</span>` : ''}}
              <span class="wl-ki-dot agent-dot none" id="wlkd-${{ticker}}"></span>
            </div>
            <span class="wl-card-score" style="color:${{scoreCol}}">${{scoreStr}}</span>
            <div style="display:flex;align-items:center;gap:4px;width:100%;justify-content:space-between">
              <span style="font-size:.8rem;color:${{trendCol}};font-weight:700">${{trendArrow}}</span>
              <div style="display:flex;gap:3px">
                <button class="wl-remove-btn" onclick="wlRemoveTicker('${{ticker}}')" title="Entfernen">\xd7</button>
                <button class="wl-details-btn" id="wlb-${{ticker}}" onclick="wlExpand('${{ticker}}',this)" title="Details einblenden">\u25be</button>
              </div>
            </div>
          </div>
          <div class="wl-details-body" id="wld-${{ticker}}" hidden></div>
        </div>`;
      }}).join('');

      // Sync ＋ buttons on main cards
      document.querySelectorAll('.wl-add-btn').forEach(b => {{
        const t = b.dataset.ticker;
        const active = arr.includes(t);
        b.classList.toggle('in-wl', active);
        b.title = active ? 'Aus Watchlist entfernen' : 'Zur Watchlist hinzuf\xfcgen';
      }});
    }} catch(e) {{
      console.error('wlRender Fehler:', e);
    }}
  }}

  window.wlExpand = function(ticker, btn) {{
    try {{
      const body = document.getElementById('wld-' + ticker);
      if (!body) return;
      const card    = body.closest('.wl-card');
      const opening = body.hidden;
      body.hidden = !opening;
      btn.textContent = opening ? '\u25b4' : '\u25be';
      if (card) card.classList.toggle('wl-card--expanded', opening);
      if (!opening) return;
      if (body.dataset.loaded) {{
        body.querySelectorAll('.wl-spark').forEach(w => {{
          if (typeof window.drawSparkline === 'function') window.drawSparkline(w);
        }});
        return;
      }}
      const d = WL_TOP10[ticker];
      body.innerHTML = d ? buildWlDetails(ticker, d) : buildWlSparkOnly(ticker, WL_HIST[ticker]);
      body.dataset.loaded = '1';
      body.querySelectorAll('.wl-spark').forEach(w => {{
        if (typeof window.drawSparkline === 'function') window.drawSparkline(w);
      }});
    }} catch(e) {{
      console.error('wlExpand Fehler:', e);
    }}
  }};

  window.wlToggle = async function(btn) {{
    const ticker = btn.dataset.ticker;
    const arr    = await wlLoad();
    const idx    = arr.indexOf(ticker);
    if (idx >= 0) {{
      arr.splice(idx, 1);
    }} else if (arr.length < WL_MAX) {{
      arr.unshift(ticker);
    }}
    await wlSave(arr);
    await wlRender();
  }};

  window.wlRemoveTicker = async function(ticker) {{
    const arr = await wlLoad();
    await wlSave(arr.filter(t => t !== ticker));
    await wlRender();
  }};

  document.addEventListener('DOMContentLoaded', wlRender);
}})();
// ── Claude / Anthropic API ────────────────────────────────────────────────────
const ANT_KEY_LS       = 'anthropic_api_key';
const ANT_WARN_LS      = 'chat_warn_ack_ts';
const ANT_WARN_TTL_MS  = 7 * 24 * 60 * 60 * 1000;
const ANT_ENDPOINT     = 'https://api.anthropic.com/v1/messages';
const ANT_MODEL        = 'claude-sonnet-4-6';
const ANT_KI_LABEL     = '\U0001F916 KI-Analyse';
const ANT_KI_LABEL_HIDE= '\u25b2 Analyse ausblenden';
const ANT_KI_LABEL_NEW = '\U0001F504 Neu analysieren';
const ANT_KI_LABEL_BUSY= '\u23F3 Analysiere …';
const ANT_KI_LABEL_KEY = '\U0001F511 API-Key erforderlich';

function _mapAnthropicError(status, rawMsg) {{
  if (status === 401) return 'Ungültiger API-Key';
  if (status === 429) return 'Rate Limit erreicht — bitte kurz warten';
  if (status === 0)   return 'Keine Verbindung zur Claude API';
  return rawMsg || ('API-Fehler ' + status);
}}

/**
 * Streaming API-Call an Claude.
 * onDelta(text) wird für jedes text-delta Event aufgerufen.
 * Resolves mit vollem Antworttext bei message_stop.
 */
async function callAnthropicStream(messages, systemPrompt, onDelta, opts) {{
  opts = opts || {{}};
  const key = localStorage.getItem(ANT_KEY_LS);
  if (!key) throw new Error('Kein API-Key gespeichert.');
  const body = {{
    model:      opts.model      || ANT_MODEL,
    max_tokens: opts.max_tokens || 500,
    system:     systemPrompt || '',
    messages:   messages,
    stream:     true,
  }};
  let res;
  try {{
    res = await fetch(ANT_ENDPOINT, {{
      method:  'POST',
      headers: {{
        'Content-Type':                              'application/json',
        'x-api-key':                                 key,
        'anthropic-version':                         '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      }},
      body: JSON.stringify(body),
    }});
  }} catch(_netErr) {{
    throw new Error(_mapAnthropicError(0, ''));
  }}
  if (!res.ok) {{
    let raw = '';
    try {{ const e = await res.json(); raw = e?.error?.message || ''; }} catch(_) {{}}
    throw new Error(_mapAnthropicError(res.status, raw));
  }}
  if (!res.body || !res.body.getReader) {{
    // Fallback: no streaming support → parse as JSON
    const data = await res.json();
    const text = data?.content?.[0]?.text || '';
    if (onDelta && text) onDelta(text);
    return text;
  }}
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '', full = '';
  while (true) {{
    const {{ value, done }} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {{stream:true}});
    let idx;
    while ((idx = buf.indexOf('\\n\\n')) !== -1) {{
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = chunk.split('\\n');
      let ev = '', dataStr = '';
      for (const line of lines) {{
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
      }}
      if (!dataStr) continue;
      try {{
        const obj = JSON.parse(dataStr);
        if (obj.type === 'content_block_delta' && obj.delta && obj.delta.type === 'text_delta') {{
          const t = obj.delta.text || '';
          full += t;
          if (onDelta) onDelta(t);
        }} else if (obj.type === 'error') {{
          throw new Error(obj.error?.message || 'Stream-Fehler');
        }}
      }} catch(parseErr) {{
        if (parseErr instanceof Error && parseErr.message && !parseErr.message.startsWith('Unexpected')) throw parseErr;
      }}
    }}
  }}
  return full;
}}

async function testAnthropicKey() {{
  const inp = document.getElementById('anth-inp');
  const st  = document.getElementById('anth-status');
  const key = (inp?.value || '').trim() || localStorage.getItem(ANT_KEY_LS) || '';
  if (!key) {{ st.className = 'anth-status err'; st.textContent = '❌ Bitte API-Key eingeben.'; return; }}
  st.className = 'anth-status ok'; st.textContent = 'Wird geprüft …';
  const prev = localStorage.getItem(ANT_KEY_LS);
  localStorage.setItem(ANT_KEY_LS, key);
  try {{
    await callAnthropicStream(
      [{{role:'user', content:'ping'}}],
      '', null, {{max_tokens: 5}}
    );
    st.className = 'anth-status ok'; st.textContent = '✅ Verbunden';
  }} catch(e) {{
    if (prev) localStorage.setItem(ANT_KEY_LS, prev); else localStorage.removeItem(ANT_KEY_LS);
    st.className = 'anth-status err';
    st.textContent = (/Ungültiger/.test(e.message)) ? '❌ Ungültiger Key' : '❌ ' + e.message;
  }}
}}

function saveAnthropicKey() {{
  const inp = document.getElementById('anth-inp');
  const st  = document.getElementById('anth-status');
  const key = (inp?.value || '').trim();
  if (!key) {{ st.className='anth-status err'; st.textContent='❌ Bitte API-Key eingeben.'; return; }}
  localStorage.setItem(ANT_KEY_LS, key);
  st.className = 'anth-status ok'; st.textContent = '✓ Gespeichert.';
  // Analyse-Buttons aktualisieren
  document.querySelectorAll('.ki-analyse-btn').forEach(b => {{
    if (b.textContent.indexOf('API-Key') !== -1) b.textContent = ANT_KI_LABEL;
  }});
  setTimeout(() => {{ document.getElementById('anth-sec').style.display='none'; }}, 800);
}}

function clearAnthropicKey() {{
  localStorage.removeItem(ANT_KEY_LS);
  const inp = document.getElementById('anth-inp');
  const st  = document.getElementById('anth-status');
  if (inp) inp.value = '';
  if (st)  {{ st.className='anth-status ok'; st.textContent='API-Key gelöscht.'; }}
  document.querySelectorAll('.ki-analyse-btn').forEach(b => {{ b.textContent = ANT_KI_LABEL_KEY; }});
}}

function toggleSettings() {{
  const tok  = document.getElementById('tok-sec');
  const anth = document.getElementById('anth-sec');
  const show = anth.style.display === 'none' || anth.style.display === '';
  anth.style.display = show ? 'block' : 'none';
  if (show) {{
    if (tok) tok.style.display = 'none';
    const inp  = document.getElementById('anth-inp');
    const key  = localStorage.getItem(ANT_KEY_LS) || '';
    if (inp && key) inp.value = key;
  }}
}}

// Initialer Button-Text setzen (zeigt „🔑 API-Key erforderlich" wenn nichts gespeichert)
document.addEventListener('DOMContentLoaded', () => {{
  if (!localStorage.getItem(ANT_KEY_LS)) {{
    document.querySelectorAll('.ki-analyse-btn').forEach(b => {{ b.textContent = ANT_KI_LABEL_KEY; }});
  }}
}});

// Setzt das „Hat Ergebnis"-Flag zurück und startet einen neuen API-Call.
function kaRerun(cardIdx) {{
  const btn = document.getElementById('ka-btn' + cardIdx);
  if (btn) delete btn.dataset.kaHasResult;
  runKiAnalyse(cardIdx);
}}

async function runKiAnalyse(cardIdx) {{
  const article = document.getElementById('c' + cardIdx);
  const btn     = document.getElementById('ka-btn' + cardIdx);
  const res     = document.getElementById('ka-res' + cardIdx);
  if (!article || !btn || !res) return;

  if (!localStorage.getItem(ANT_KEY_LS)) {{
    btn.textContent = ANT_KI_LABEL_KEY;
    toggleSettings();
    return;
  }}

  // ── Bereits ein Ergebnis vorhanden → nur ein-/ausklappen ─────────────────
  if (btn.dataset.kaHasResult === '1') {{
    const nowVisible = res.classList.toggle('visible');
    btn.textContent  = nowVisible ? ANT_KI_LABEL_HIDE : ANT_KI_LABEL;
    return;
  }}

  // ── Neuer API-Call ────────────────────────────────────────────────────────
  const d = article.dataset;
  let newsArr = [];
  try {{ newsArr = JSON.parse(d.news || '[]'); }} catch(_) {{}}
  const ctx = {{
    ticker:   d.ticker  || '',
    company:  d.company || d.ticker || '',
    score:    d.score   || '?',
    sf:       d.sf      || '?',
    sr:       d.sr      || '?',
    rv:       d.rv      || '?',
    chg:      d.chg     || '?',
    floatM:   d.float   || 'n/a',
    si:       d.si      || 'no_data',
    rsi:      d.rsi     || 'n/a',
    iv:       d.iv      || 'n/a',
    earn:     d.earn    ? ('in ' + d.earn + 'd' + (d.earnDate ? ' (' + d.earnDate + ')' : '')) : 'keine in 14T',
    cap:      d.cap     ? (parseInt(d.cap)/1e9).toFixed(1) + 'B USD' : 'n/a',
    sector:   d.sector  || 'n/a',
    kiScore:  d.kiScore != null ? (d.kiScore + '/100') : 'nicht bewertet',
    kiConf:   d.kiConf  != null ? (d.kiConf  + '%')    : 'n/a',
    kiDrv:    d.kiDrivers || '',
    news:     newsArr,
  }};

  const sysPrompt = 'Du bist ein erfahrener Squeeze-Analyst. Analysiere das folgende Squeeze-Setup und gib eine präzise Einschätzung auf Deutsch. Maximal 150 Wörter. Schließe immer mit einem Haftungshinweis ab: Diese Analyse ist keine Anlageempfehlung.';
  const userPrompt =
`Squeeze-Setup für ${{ctx.ticker}} (${{ctx.company}}):
- Squeeze-Score: ${{ctx.score}}/100
- Short Float: ${{ctx.sf}}%
- Days to Cover: ${{ctx.sr}}d
- Rel. Volumen: ${{ctx.rv}}×
- Momentum (heute): ${{ctx.chg}}%
- Float: ${{ctx.floatM}}
- SI-Trend (FINRA, 3M): ${{ctx.si}}
- RSI 14: ${{ctx.rsi}}
- ATM Impl. Volatilität: ${{ctx.iv}}%
- Nächste Earnings: ${{ctx.earn}}
- KI-Agent-Score: ${{ctx.kiScore}} (Konfidenz ${{ctx.kiConf}})${{ctx.kiDrv ? ' — Treiber: ' + ctx.kiDrv : ''}}
- Marktkapitalisierung: ${{ctx.cap}} · Sektor: ${{ctx.sector}}
- Aktuelle Schlagzeilen:
${{ctx.news.length ? ctx.news.map((n,i) => '  ' + (i+1) + '. ' + n).join('\\n') : '  (keine)'}}

Gib eine knappe Einschätzung: Squeeze-Potenzial, wichtigste Treiber, kritische Risiken.`;

  btn.disabled = true;
  btn.textContent = ANT_KI_LABEL_BUSY;
  res.innerHTML =
    '<span class="ka-label">\U0001F916 Claude &middot; ' + ctx.ticker +
    '<button class="ka-rerun-btn" onclick="kaRerun(' + cardIdx + ')">' + ANT_KI_LABEL_NEW + '</button></span>' +
    '<span class="ka-stream"></span>';
  res.classList.add('visible');
  const streamSpan = res.querySelector('.ka-stream');

  try {{
    let acc = '';
    await callAnthropicStream(
      [{{role:'user', content: userPrompt}}],
      sysPrompt,
      (delta) => {{
        acc += delta;
        if (streamSpan) streamSpan.innerHTML = acc.replace(/\\n/g, '<br>');
      }},
      {{model: ANT_MODEL, max_tokens: 400}}
    );
    btn.dataset.kaHasResult = '1';
    btn.textContent = ANT_KI_LABEL_HIDE;
  }} catch(e) {{
    res.innerHTML = '<span class="ka-label">Fehler</span>' + e.message;
    btn.textContent = ANT_KI_LABEL;   // kein has-result setzen → nächster Tap macht neuen Call
  }} finally {{
    btn.disabled = false;
  }}
}}

// ── Claude Chat Panel ─────────────────────────────────────────────────────────
(function(){{
  const STOCKS_CTX = {chat_ctx_json};
  let _history = [];
  let _open    = false;

  function _buildSystem() {{
    return `Du bist ein erfahrener Squeeze-Analyst und kennst die aktuellen Top-10-Squeeze-Kandidaten mit allen Kennzahlen. Beantworte Fragen des Nutzers präzise auf Deutsch. Gib keine verbindlichen Anlageempfehlungen. Schreibe kompakt — maximal 200 Wörter pro Antwort. Der Squeeze-Score ist das primäre Ranking-Kriterium. Bei gleichen qualitativen Signalen bevorzuge immer den Kandidaten mit dem höheren Score. Erkläre explizit wenn du vom Score-Rang abweichst und begründe warum.

Aktuelle Top-10 (JSON):
${{JSON.stringify(STOCKS_CTX)}}`;
  }}

  function _renderChips() {{
    const chips = document.getElementById('chat-chips');
    if (!chips) return;
    const top1 = STOCKS_CTX[0]?.ticker || 'Top 1';
    const top2 = STOCKS_CTX[1]?.ticker || 'Top 2';
    const suggestions = [
      'Welcher Kandidat hat heute das beste Setup?',
      `Was spricht gegen einen Einstieg bei ${{top1}}?`,
      `Erkläre den SI-Trend von ${{top2}}`,
      'Welche Risiken sehe ich bei High-IV-Kandidaten?',
    ];
    chips.innerHTML = suggestions.map(s =>
      `<button class="chip" onclick="chatAsk(${{JSON.stringify(s).replace(/"/g,'&quot;')}})">${{s}}</button>`
    ).join('');
  }}

  function _maybeShowWarn() {{
    const banner = document.getElementById('chat-warn');
    if (!banner) return;
    const ts  = parseInt(localStorage.getItem(ANT_WARN_LS) || '0', 10);
    const ok  = ts && (Date.now() - ts) < ANT_WARN_TTL_MS;
    banner.classList.toggle('hidden', !!ok);
  }}

  window.chatWarnAck = function() {{
    localStorage.setItem(ANT_WARN_LS, String(Date.now()));
    const b = document.getElementById('chat-warn');
    if (b) b.classList.add('hidden');
  }};

  function _setChatOpen(open) {{
    const panel   = document.getElementById('chat-panel');
    const overlay = document.getElementById('chat-overlay');
    if (!panel) return;
    _open = open;
    panel.classList.toggle('open', open);
    if (overlay) overlay.classList.toggle('open', open);
    if (open) {{
      if (_history.length === 0) {{
        _addMsg('sys', 'Hallo! Ich kenne die heutigen Top-10-Squeeze-Kandidaten. Frag mich nach Setup, Risiken oder Vergleichen.');
      }}
      _maybeShowWarn();
      setTimeout(() => document.getElementById('chat-inp')?.focus(), 300);
    }}
  }}

  window.toggleChat = function() {{ _setChatOpen(!_open); }};

  // Swipe-down to close (mobile full-screen only, < 768 px)
  (function(){{
    const panel = document.getElementById('chat-panel');
    if (!panel) return;
    let _touchStartY = 0, _touchStartT = 0;
    panel.addEventListener('touchstart', function(e) {{
      _touchStartY = e.touches[0].clientY;
      _touchStartT = Date.now();
    }}, {{passive: true}});
    panel.addEventListener('touchend', function(e) {{
      if (window.innerWidth >= 768) return;          // desktop: kein Swipe-close
      const dy = e.changedTouches[0].clientY - _touchStartY;
      const dt = Date.now() - _touchStartT;
      if (dy > 60 && dt < 400) {{                    // ≥60px nach unten, <400ms
        const msgs = document.getElementById('chat-msgs');
        if (msgs && msgs.scrollTop > 0) return;      // nur wenn am Anfang des Scroll
        _setChatOpen(false);
      }}
    }}, {{passive: true}});
  }})();

  function _addMsg(role, text) {{
    const msgs = document.getElementById('chat-msgs');
    if (!msgs) return null;
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg--' + role;
    div.innerHTML = text.replace(/\\n/g, '<br>');
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }}

  window.chatAsk = function(text) {{
    const inp = document.getElementById('chat-inp');
    if (inp) inp.value = text;
    chatSend();
  }};

  window.chatSend = async function() {{
    const inp  = document.getElementById('chat-inp');
    const send = document.getElementById('chat-send');
    const text = (inp?.value || '').trim();
    if (!text) return;

    if (!localStorage.getItem(ANT_KEY_LS)) {{
      toggleSettings();
      _addMsg('err', '\u26A0 Bitte zuerst den Anthropic API-Key eingeben (\u2699 oben rechts).');
      return;
    }}

    inp.value = '';
    _addMsg('user', text);
    _history.push({{role:'user', content: text}});

    if (send) send.disabled = true;
    const aiDiv = _addMsg('ai', '');
    if (aiDiv) aiDiv.classList.add('streaming');

    try {{
      let acc = '';
      await callAnthropicStream(
        _history,
        _buildSystem(),
        (delta) => {{
          acc += delta;
          if (aiDiv) aiDiv.innerHTML = acc.replace(/\\n/g, '<br>');
          const msgs = document.getElementById('chat-msgs');
          if (msgs) msgs.scrollTop = msgs.scrollHeight;
        }},
        {{model: ANT_MODEL, max_tokens: 500}}
      );
      if (aiDiv) aiDiv.classList.remove('streaming');
      _history.push({{role:'assistant', content: acc}});
      if (_history.length > 20) _history = _history.slice(-20);
    }} catch(e) {{
      if (aiDiv && aiDiv.parentNode) aiDiv.parentNode.removeChild(aiDiv);
      _history.pop();
      _addMsg('err', '✗ ' + e.message);
    }} finally {{
      if (send) send.disabled = false;
      inp?.focus();
    }}
  }};

  document.addEventListener('DOMContentLoaded', _renderChips);
}})();
// ─────────────────────────────────────────────────────────────────────────────
</script>
</body>
</html>"""


# ===========================================================================
# 4b. WATCHLIST VOLUME SCAN
# ===========================================================================

_WL_FAILURES_FILE = "watchlist_failures.json"
_WL_INACTIVE_FILE = "watchlist_inactive.txt"

# Required ticker suffix per non-US region; US = no suffix from this dict
_WL_REGION_SUFFIX: dict[str, str] = {
    "DE": ".DE", "GB": ".L", "FR": ".PA", "NL": ".AS",
    "CA": ".TO", "JP": ".T", "HK": ".HK", "KR": ".KS",
}
_WL_ALL_SUFFIXES = tuple(v.upper() for v in _WL_REGION_SUFFIX.values())
_WL_MAX_FAILURES  = 3   # consecutive 404/empty responses before auto-deactivation
_WL_SCAN_TIMEOUT  = 30  # seconds — hard limit for the entire watchlist scan
_WL_DL_TIMEOUT    = 20  # seconds — per-region yf.download timeout


def _wl_load_failures() -> dict[str, int]:
    try:
        with open(_WL_FAILURES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _wl_save_failures(failures: dict[str, int]) -> None:
    try:
        with open(_WL_FAILURES_FILE, "w") as f:
            json.dump(failures, f, indent=2, sort_keys=True)
    except Exception:
        pass


def _wl_load_inactive() -> set[str]:
    try:
        with open(_WL_INACTIVE_FILE) as f:
            return {ln.strip() for ln in f if ln.strip()}
    except Exception:
        return set()


def _wl_mark_inactive(ticker: str) -> None:
    inactive = _wl_load_inactive()
    inactive.add(ticker)
    with open(_WL_INACTIVE_FILE, "w") as f:
        f.write("\n".join(sorted(inactive)) + "\n")
    log.warning("Watchlist: %s nach %d× Fehler als inaktiv markiert → %s",
                ticker, _WL_MAX_FAILURES, _WL_INACTIVE_FILE)


_WL_SCAN_TIMEOUT = 30  # seconds — abort entire watchlist scan if exceeded


def get_watchlist_candidates() -> list[dict]:
    """Volume scan of the static watchlist using per-region batch downloads.

    Runs inside a _WL_SCAN_TIMEOUT hard limit (Fix 1). Each region's yf.download
    is additionally wrapped with a _WL_DL_TIMEOUT per-region limit (Fix 2) so a
    single hanging exchange cannot consume the whole budget.
    """

    def _scan() -> list[dict]:
        failures = _wl_load_failures()
        inactive = _wl_load_inactive()
        newly_inactive: list[str] = []

        results: list[dict] = []
        for market, tickers in WATCHLIST.items():
            active = [t for t in tickers if t not in inactive]
            # Suffix guard: each region only processes tickers with the matching suffix.
            required_suffix = _WL_REGION_SUFFIX.get(market)
            if required_suffix:
                active = [t for t in active if t.upper().endswith(required_suffix.upper())]
            else:
                active = [t for t in active if not t.upper().endswith(_WL_ALL_SUFFIXES)]
            if not active:
                continue
            log.info("Watchlist scan: %s (%d active / %d total)",
                     market, len(active), len(tickers))

            # Fix 2: per-region yf.download with hard timeout
            def _dl(syms=active):
                return yf.download(
                    syms, period="21d", group_by="ticker",
                    auto_adjust=True, threads=True, progress=False,
                )
            try:
                with ThreadPoolExecutor(max_workers=1) as _dl_ex:
                    hist_batch = _dl_ex.submit(_dl).result(timeout=_WL_DL_TIMEOUT)
            except TimeoutError:
                print(f"yfinance Batch-Download Timeout nach {_WL_DL_TIMEOUT}s — Region {market} übersprungen", flush=True)
                log.warning("yf.download timeout for %s — skipping region", market)
                continue
            except Exception as exc:
                log.warning("Watchlist batch failed for %s: %s — skipping region", market, exc)
                continue

            for ticker in active:
                try:
                    if len(active) == 1:
                        df = hist_batch
                    else:
                        try:
                            df = hist_batch[ticker]
                        except KeyError:
                            df = None

                    if df is None or df.empty or len(df) < 5:
                        failures[ticker] = failures.get(ticker, 0) + 1
                        if failures[ticker] >= _WL_MAX_FAILURES:
                            _wl_mark_inactive(ticker)
                            newly_inactive.append(ticker)
                            failures.pop(ticker, None)
                        continue

                    failures.pop(ticker, None)

                    avg_vol = float(df["Volume"].iloc[:-1].mean())
                    cur_vol = float(df["Volume"].iloc[-1])
                    if avg_vol < 1000:
                        continue
                    rel_vol = cur_vol / avg_vol if avg_vol > 0 else 0.0
                    vol_threshold = MIN_REL_VOLUME_INTL if market != "US" else MIN_REL_VOLUME
                    if rel_vol < vol_threshold:
                        continue
                    price = float(df["Close"].iloc[-1])
                    if price < MIN_PRICE:
                        continue
                    prev_close = float(df["Close"].iloc[-2])
                    chg = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
                    results.append({
                        "ticker":       ticker,
                        "market":       market,
                        "price":        price,
                        "change":       round(chg, 2),
                        "rel_volume":   round(rel_vol, 2),
                        "short_float":  0.0,
                        "short_ratio":  0.0,
                        "company_name": ticker,
                        "sector":       "",
                        "source":       "watchlist",
                    })
                    log.info("  watchlist hit: %s [%s] vol=%.1f×", ticker, market, rel_vol)
                except Exception as exc:
                    log.debug("  watchlist skip %s: %s", ticker, exc)
                    failures[ticker] = failures.get(ticker, 0) + 1
                    if failures[ticker] >= _WL_MAX_FAILURES:
                        _wl_mark_inactive(ticker)
                        newly_inactive.append(ticker)
                        failures.pop(ticker, None)

        _wl_save_failures(failures)
        if newly_inactive:
            print(f"Watchlist: {len(newly_inactive)} Ticker als inaktiv markiert: "
                  f"{newly_inactive}", flush=True)
        log.info("Watchlist candidates: %d (inactive skipped: %d)", len(results), len(inactive))
        return results

    # Fix 1: hard outer timeout for the entire scan
    with ThreadPoolExecutor(max_workers=1) as _ex:
        _fut = _ex.submit(_scan)
        try:
            return _fut.result(timeout=_WL_SCAN_TIMEOUT)
        except TimeoutError:
            print(f"Watchlist-Scan Timeout nach {_WL_SCAN_TIMEOUT}s — 0 Kandidaten", flush=True)
            log.warning("Watchlist scan exceeded %ds timeout — returning []", _WL_SCAN_TIMEOUT)
            return []
        except Exception as exc:
            log.error("Watchlist scan error: %s", exc)
            return []


# ===========================================================================
# 5. ERROR PAGE HELPER
# ===========================================================================

def _write_error_page(report_date: str, message: str) -> None:
    """Write a minimal error page when no data could be retrieved."""
    html = f"""<!DOCTYPE html><html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Squeeze Report – {report_date}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:#07090f;color:#dde4f5;display:flex;align-items:center;
justify-content:center;min-height:100vh;margin:0}}
.box{{background:#111827;border:1px solid #1e2d4a;border-radius:12px;
padding:36px 44px;max-width:500px;text-align:center}}
.err{{color:#ef4444;font-size:1.15rem;font-weight:700;margin-bottom:12px}}
p{{color:#8899bb;font-size:.88rem;line-height:1.65}}
</style></head>
<body><div class="box">
<div class="err">&#9888; Datenabruf fehlgeschlagen</div>
<p>{message}<br><br>Datum: {report_date}</p>
</div></body></html>"""
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    log.info("Error page written to index.html")


# ===========================================================================
# 6. MAIN
# ===========================================================================

def main():
    t_run_start = time.time()
    berlin = ZoneInfo("Europe/Berlin")
    report_date = datetime.now(berlin).strftime("%d.%m.%Y")
    log.info("=== Squeeze Report %s ===", report_date)

    # --- Step 1: Get candidate pool ---
    # Primary: Yahoo Finance Screener (reliable from GitHub Actions runners)
    _t1 = time.time()
    log.info("Step 1 – Yahoo Finance Screener …")
    candidates = get_yahoo_screener_candidates()

    if not candidates:
        # Fallback: Finviz (may be blocked on cloud IPs, but worth trying)
        log.warning("Yahoo screener returned 0 results. Trying Finviz as fallback …")
        candidates = get_finviz_candidates(max_pages=6)

    log.info("Candidate pool: %d tickers", len(candidates))

    if not candidates:
        log.error("Both screeners failed. Writing error page.")
        _write_error_page(report_date,
            "Screener-Verbindung fehlgeschlagen (Yahoo Finance &amp; Finviz). "
            "Bitte manuell neu starten.")
        return

    # Supplement with watchlist volume scan (JP, HK, KR + any that screener missed)
    log.info("Step 1b – Watchlist volume scan (batch per region) …")
    watchlist_cands = get_watchlist_candidates()
    existing_tickers = {c["ticker"] for c in candidates}
    for wc in watchlist_cands:
        if wc["ticker"] not in existing_tickers:
            candidates.append(wc)
            existing_tickers.add(wc["ticker"])
    log.info("Combined candidate pool after watchlist: %d tickers", len(candidates))
    print(f"Step 1 abgeschlossen in {time.time()-_t1:.1f}s", flush=True)

    # Pre-sort by whatever data we have so we enrich the most promising first
    for c in candidates:
        c["score"] = score(c)
    candidates.sort(key=lambda x: x.get("score") or 0, reverse=True)

    # ── Dynamic pool construction ─────────────────────────────────────────────
    # Priority 1: SF ≥ POOL_SHORT_FLOAT_THRESHOLD (always included)
    tier1 = [c for c in candidates if c.get("short_float", 0) >= POOL_SHORT_FLOAT_THRESHOLD]
    # Priority 2: SF 5–10 % from most_shorted_stocks screener
    tier2 = [c for c in candidates
             if c not in tier1
             and 5.0 <= c.get("short_float", 0) < POOL_SHORT_FLOAT_THRESHOLD
             and c.get("source") == "yahoo_most_shorted"]
    # Priority 3: relative volume ≥ 2× (volume spike from any screener source)
    tier3 = [c for c in candidates
             if c not in tier1 and c not in tier2
             and c.get("rel_volume", 0) >= 2.0]
    # Priority 4: remainder sorted by volume descending
    used  = {id(c) for c in tier1 + tier2 + tier3}
    tier4 = sorted(
        [c for c in candidates if id(c) not in used],
        key=lambda c: c.get("rel_volume", 0),
        reverse=True,
    )

    # Assemble pool: tiers 1–3 always in, fill with tier4 up to POOL_MAX
    pool: list[dict] = list(tier1) + list(tier2) + list(tier3)
    remaining_slots  = max(POOL_MAX - len(pool), 0)
    pool.extend(tier4[:remaining_slots])

    # Enforce minimum
    if len(pool) < POOL_MIN:
        extras = [c for c in candidates if c not in pool]
        extras.sort(key=lambda c: c.get("rel_volume", 0), reverse=True)
        pool.extend(extras[:POOL_MIN - len(pool)])

    n_sf10 = len(tier1)
    n_sf5  = len(tier2)
    n_vol  = len(tier3)
    n_rest = len(pool) - n_sf10 - n_sf5 - n_vol
    print(
        f"Pool-Aufbau: {n_sf10}× SF≥{POOL_SHORT_FLOAT_THRESHOLD:.0f}% + "
        f"{n_sf5}× SF 5-10% + {n_vol}× Vol≥2× + {n_rest}× Rest = "
        f"{len(pool)} Kandidaten (Min={POOL_MIN}, Max={POOL_MAX})",
        flush=True,
    )
    # ─────────────────────────────────────────────────────────────────────────

    # Pre-compute FINRA publication dates once (6 = ~3 months, twice-monthly releases)
    finra_dates = _latest_finra_dates(SI_TREND_PERIODS)

    # Opt 4 — FINRA CSV parallel load (3 URLs per date × 6 dates in parallel).
    # The actual parallelism across URLs is inside _load_finra_csv(); here we
    # additionally parallelize across dates.
    _t_finra = time.time()
    log.info("Step 2a – Pre-loading FINRA CDN data for %d dates (parallel) …", len(finra_dates))
    with ThreadPoolExecutor(max_workers=6) as _finra_ex:
        list(_finra_ex.map(_get_finra_csv_for_date, finra_dates))
    _total_finra_entries = sum(len(v) for v in _finra_csv_cache.values())
    print(f"FINRA Cache aufgebaut: {len(_finra_csv_cache)} Dateien, "
          f"{_total_finra_entries} Ticker-Einträge gesamt — "
          f"{time.time()-_t_finra:.1f}s", flush=True)
    print(f"FINRA 3M-Trend: {len(_finra_csv_cache)} Datenpunkte je Ticker geladen", flush=True)
    print(f"Step 2a abgeschlossen in {time.time()-_t_finra:.1f}s", flush=True)

    # Opt 1 — yfinance Batch: pre-fetch all history + info for the entire pool
    # in two parallel shots before the filter loop.  No per-ticker sleeps needed.
    _t_batch = time.time()
    pool_tickers = [c["ticker"] for c in pool]
    log.info("Step 2b – Batch yfinance fetch for %d pool tickers …", len(pool_tickers))
    # Fix 1: hard 45s timeout — a hanging yf.download would otherwise block forever
    _YF_BATCH_TIMEOUT = 45
    try:
        with ThreadPoolExecutor(max_workers=1) as _yf_ex:
            batch_yfd = _yf_ex.submit(get_yfinance_batch, pool_tickers).result(
                timeout=_YF_BATCH_TIMEOUT
            )
    except TimeoutError:
        print(f"yfinance Batch-Download Timeout nach {_YF_BATCH_TIMEOUT}s — leeres Ergebnis",
              flush=True)
        log.warning("get_yfinance_batch timeout after %ds — using empty dict", _YF_BATCH_TIMEOUT)
        batch_yfd = {}
    print(f"Step 2b (yfinance batch) abgeschlossen in {time.time()-_t_batch:.1f}s", flush=True)

    # Relative Stärke vs. S&P 500 (20T) + heutige Tagesveränderung
    # Fix 2: hard 15s timeout so a hanging ^GSPC fetch cannot stall the pipeline
    _spx_perf_20d:   float | None = None
    _spx_daily_perf: float        = 0.0   # heutige S&P 500 Tagesveränderung in %
    _SPX_TIMEOUT = 15
    def _fetch_spx():
        return yf.download("^GSPC", period="25d", auto_adjust=True,
                           progress=False, threads=False)
    try:
        with ThreadPoolExecutor(max_workers=1) as _spx_ex:
            _spx_hist = _spx_ex.submit(_fetch_spx).result(timeout=_SPX_TIMEOUT)
        if _spx_hist is not None and not _spx_hist.empty and len(_spx_hist) >= 21:
            # squeeze() collapses a single-ticker MultiLevel column DataFrame to a Series
            _spx_close = _spx_hist["Close"].squeeze().dropna()
            _last  = float(_spx_close.iloc[-1])
            _first = float(_spx_close.iloc[-21])
            _spx_perf_20d = (_last - _first) / _first * 100
            log.info("S&P 500 20T-Perf: %.2f%%", _spx_perf_20d)
            print(f"S&P 500 20T Performance: {_spx_perf_20d:.1f}%", flush=True)
            # Daily perf for relative momentum
            if len(_spx_close) >= 2:
                _prev = float(_spx_close.iloc[-2])
                _spx_daily_perf = (_last - _prev) / _prev * 100 if _prev > 0 else 0.0
                log.info("S&P 500 Tages-Perf: %.2f%%", _spx_daily_perf)
    except TimeoutError:
        print("S&P 500 Fetch Timeout — Relative Stärke nicht verfügbar", flush=True)
        log.warning("S&P 500 yf.download timeout after %ds — skipping relative strength", _SPX_TIMEOUT)
    except Exception as _spx_exc:
        log.warning("S&P 500 fetch failed: %s", _spx_exc)

    # --- Step 2: Filter loop — uses pre-fetched batch data, no HTTP per ticker ---
    log.info("Step 2 – Filtering %d candidates with enriched data …", len(pool))
    enriched = []
    _enrich_start = time.time()
    for i, c in enumerate(pool):
        # Timeout guard: skip remaining candidates if wall-clock limit exceeded
        _elapsed_enrich = time.time() - _enrich_start
        if _elapsed_enrich > POOL_ENRICH_TIMEOUT:
            print(
                f"Pool-Anreicherung Zeitlimit erreicht: {i}/{len(pool)} Kandidaten angereichert",
                flush=True,
            )
            log.warning("Enrichment timeout after %.1fs — skipping remaining %d candidates",
                        _elapsed_enrich, len(pool) - i)
            break

        t = c["ticker"]
        log.info("  [%d/%d] %s", i + 1, len(pool), t)
        # Use pre-fetched batch data; fall back to individual call if missing
        yfd = batch_yfd.get(t) or get_yfinance_data(t)

        # Overwrite with accurate yfinance values
        _stock_perf_20d = yfd.get("perf_20d")
        _rel_strength   = (
            (_stock_perf_20d - _spx_perf_20d)
            if _stock_perf_20d is not None and _spx_perf_20d is not None
            else None
        )
        c.update({
            "company_name":    yfd.get("company_name") or c.get("company_name", t),
            "sector":          yfd.get("sector") or c.get("sector") or "",
            "industry":        yfd.get("industry") or c.get("industry") or "",
            "yf_market_cap":   yfd.get("market_cap"),
            "52w_high":        yfd.get("52w_high"),
            "52w_low":         yfd.get("52w_low"),
            "avg_vol_20d":     yfd.get("avg_vol_20d", 0),
            "cur_vol":         yfd.get("cur_vol", 0),
            "rsi14":           yfd.get("rsi14"),
            "ma50":            yfd.get("ma50"),
            "ma200":           yfd.get("ma200"),
            "perf_20d":        _stock_perf_20d,
            "rel_strength_20d": _rel_strength,
            "inst_ownership":  yfd.get("inst_ownership"),
            "float_shares":    yfd.get("float_shares", 0),
            "change_5d":       yfd.get("change_5d"),
            "spx_daily_perf":  _spx_daily_perf,
        })
        if i < 3:
            print(f"{t} float_shares={c.get('float_shares')} change_5d={c.get('change_5d')}", flush=True)
        yf_sf = yfd.get("short_float_yf", 0)
        if yf_sf > 0:
            c["short_float"] = yf_sf
        yf_sr = yfd.get("short_ratio", 0)
        if yf_sr > 0:
            c["short_ratio"] = yf_sr
        if yfd.get("vol_ratio", 0) > 0:
            c["rel_volume"] = yfd["vol_ratio"]

        # FINRA daily short-volume data (US only; local dict lookup — no HTTP)
        is_us_finra = c.get("market", "US") == "US"
        if is_us_finra:
            c["finra_data"] = get_finra_short_interest(t, finra_dates)
        else:
            c["finra_data"] = {}
        c["sf_source"] = "Yahoo Finance"

        # Hard filters (now with accurate data)
        cap = c.get("yf_market_cap") or c.get("market_cap")
        if cap and cap > MAX_MARKET_CAP:
            log.info("    skip %s: cap %s > $10B", t, fmt_cap(cap))
            continue

        # Short-float filter: strict for US; relaxed for non-US (data rarely available)
        is_us = c.get("market", "US") == "US"
        has_sf_data = c["short_float"] > 0
        if is_us and c["short_float"] < MIN_SHORT_FLOAT:
            log.info("    skip %s: short_float %.1f%% < %.0f%%",
                     t, c["short_float"], MIN_SHORT_FLOAT)
            continue
        if not is_us and not has_sf_data:
            # Keep intl stock if volume signals activity despite missing short data
            if c.get("rel_volume", 0) < 1.0:
                log.info("    skip %s [%s]: no short data + low volume (%.1f×)",
                         t, c.get("market"), c.get("rel_volume", 0))
                continue
            log.info("    keep %s [%s]: no short data but vol=%.1f× (intl)",
                     t, c.get("market"), c.get("rel_volume", 0))

        c["score"] = score(c)
        if not math.isfinite(c["score"]):
            log.warning("    skip %s: score is nan/inf after enrichment", t)
            continue
        enriched.append(c)
        # No per-ticker sleep needed — data already fetched in batch above

    _enrich_elapsed = time.time() - _enrich_start
    print(
        f"Angereichert: {len(enriched)}/{len(pool)} Kandidaten in {_enrich_elapsed:.1f}s",
        flush=True,
    )
    print(f"Step 2 abgeschlossen in {time.time()-_t_batch:.1f}s", flush=True)
    enriched.sort(key=lambda x: x.get("score") or 0, reverse=True)

    # Always pick the best 10 by score — MIN_SCORE is informational only, not a filter.
    # Prefer candidates with rel_volume ≥ MIN_REL_VOLUME; fall back to the full enriched
    # list if fewer than 10 pass that soft filter, so the report always shows 10.
    top10_vol = [c for c in enriched if c.get("rel_volume", 0) >= MIN_REL_VOLUME]
    top10 = top10_vol[:10] if len(top10_vol) >= 10 else enriched[:10]

    # Safety net for extreme market days: if fewer than 3 candidates exist at all
    if len(top10) < 3:
        log.warning(
            "Only %d qualified candidates found (very unusual). "
            "Using all available enriched results.",
            len(top10),
        )
        top10 = enriched  # show whatever survived

    if not top10:
        log.error("No candidates survived all filters.")
        _write_error_page(report_date,
            "Keine Aktien erfüllen aktuell alle Filterkriterien "
            "(Short Float &gt;15 %, Preis &gt;$1, Marktkapitalisierung &lt;$10 Mrd.).")
        return

    # --- Step 3b: Bonus scores (FTD permanently disabled – IP-blocked) ---
    for s in top10:
        s["ftd_data"] = {}

    for s in top10:
        s.setdefault("ftd_data", {})
        bonus = score_bonus(s)
        if bonus > 0:
            base = s["score"]
            s["score"] = round(min(base + bonus, 100.0), 2)
            log.info("  %s: base=%.2f + bonus=%.2f = %.2f",
                     s["ticker"], base, bonus, s["score"])

    top10.sort(key=lambda x: x.get("score") or 0, reverse=True)

    # --- Step 3a: Score smoothing (70 % today + 30 % avg last 3 runs) ---
    apply_score_smoothing(top10, report_date)
    top10.sort(key=lambda x: x.get("score") or 0, reverse=True)

    # Opt 3 — Parallel news fetching (all 10 tickers × 3 sources concurrently).
    _t_news = time.time()
    log.info("Step 3 – Fetching news for %d stocks (parallel, max 5 threads) …", len(top10))
    with ThreadPoolExecutor(max_workers=5) as _news_ex:
        _news_futures = {_news_ex.submit(get_combined_news, s["ticker"]): s for s in top10}
        for _fut in as_completed(_news_futures):
            _news_futures[_fut]["news"] = _fut.result() or []
    _news_elapsed = time.time() - _t_news
    print(f"News: {len(top10)} Ticker parallel in {_news_elapsed:.1f}s abgerufen", flush=True)

    # Parallel options data fetch (US-only top-10, max 5 threads).
    # Fix 3: as_completed(timeout=30) — skip remaining futures after 30s total
    _POOL_STEP3_TIMEOUT = 30
    _t_opts = time.time()
    us_top10 = [s for s in top10 if "." not in s["ticker"]]
    log.info("Step 3b – Fetching options data for %d US stocks (parallel, max 5 threads) …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _opts_ex:
        _opts_futures = {_opts_ex.submit(get_options_data, s["ticker"]): s for s in us_top10}
        try:
            for _fut in as_completed(_opts_futures, timeout=_POOL_STEP3_TIMEOUT):
                _opts_futures[_fut]["options"] = _fut.result() or {}
        except TimeoutError:
            print(f"Optionsdaten: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                  flush=True)
            log.warning("options as_completed timeout — skipping remaining futures")
    _opts_elapsed = time.time() - _t_opts
    _n_ok = sum(1 for s in us_top10 if s.get("options"))
    _n_na = len(us_top10) - _n_ok
    print(f"Optionsdaten: {len(us_top10)} Ticker parallel in {_opts_elapsed:.1f}s abgerufen — {_n_ok} mit Daten, {_n_na} ohne", flush=True)

    # Parallel earnings date fetch (US-only, max 5 threads).
    _t_earn = time.time()
    log.info("Step 3c – Fetching earnings dates for %d US stocks …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _earn_ex:
        _earn_futures = {_earn_ex.submit(get_earnings_date, s["ticker"]): s for s in us_top10}
        try:
            for _fut in as_completed(_earn_futures, timeout=_POOL_STEP3_TIMEOUT):
                _days, _dstr = _fut.result()
                _earn_futures[_fut]["earnings_days"] = _days
                _earn_futures[_fut]["earnings_date_str"] = _dstr
        except TimeoutError:
            print(f"Earnings-Termine: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                  flush=True)
            log.warning("earnings as_completed timeout — skipping remaining futures")
    print(f"Earnings-Termine: {len(us_top10)} Ticker in {time.time()-_t_earn:.1f}s abgerufen", flush=True)

    # Parallel SEC 13F fetch (US-only, max 5 threads).
    _t_13f = time.time()
    log.info("Step 3d – Checking SEC 13F for %d US stocks …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _13f_ex:
        _13f_futures = {_13f_ex.submit(fetch_sec_13f, s["ticker"]): s for s in us_top10}
        try:
            for _fut in as_completed(_13f_futures, timeout=_POOL_STEP3_TIMEOUT):
                note = _fut.result()
                if note:
                    _13f_futures[_fut]["sec_13f_note"] = note
        except TimeoutError:
            print(f"SEC 13F: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                  flush=True)
            log.warning("SEC 13F as_completed timeout — skipping remaining futures")
    _n_13f = sum(1 for s in us_top10 if s.get("sec_13f_note"))
    print(f"SEC 13F: {_n_13f} Treffer in {time.time()-_t_13f:.1f}s", flush=True)
    print(f"Step 3 abgeschlossen in {time.time() - _t_news:.1f}s", flush=True)

    # --- Step 4: HTML ---
    _t4 = time.time()
    log.info("Step 4 – Generating HTML report …")
    html = generate_html(top10, report_date)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Step 4 abgeschlossen in {time.time()-_t4:.1f}s", flush=True)

    log.info("Report written → index.html")
    log.info("Top 10: %s", [s["ticker"] for s in top10])
    log.info("Supplementary data summary: FINRA=%d/10", _finra_stats["ok"])
    print(
        f"[Datenabruf-Zusammenfassung] "
        f"FINRA: {_finra_stats['ok']} erfolgreich, "
        f"{_finra_stats['empty']} leer, "
        f"{_finra_stats['err']} Fehler | "
        f"FTD: deaktiviert (IP-Beschränkung)",
        flush=True,
    )
    _elapsed = time.time() - t_run_start
    print(
        f"Gesamtlaufzeit: {_elapsed:.1f}s | Ziel: unter 30s",
        flush=True,
    )
    print(
        f"HTTP-Requests: FINRA={_req_counts['finra']}, "
        f"Yahoo={_req_counts['yahoo']}, "
        f"yfinance={_req_counts['yfinance']} | "
        f"Kandidaten: {len(pool)}→{len(top10)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
