#!/usr/bin/env python3
"""
Daily Stock Squeeze Report Generator
Identifies top 10 short squeeze candidates from global markets (US, DE, GB, CA).
Data sources: Yahoo Finance Screener (primary) + Finviz (fallback) + yfinance (enrichment).
News titles and summaries are translated to German.
"""

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
_FINRA_DATES_CACHE_TTL_S = 3600   # 1 Stunde in Sekunden


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

    # Write cache
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
def score(stock: dict) -> float:
    """Weighted squeeze score 0–100.
    When no short data is available (sf=0, sr=0) the score is capped at 50
    so these stocks can appear in the top 10 but never displace a stock with
    confirmed high short interest.
    """
    sf_val = stock.get("short_float", 0)
    sr_val = stock.get("short_ratio", 0)
    rv_raw = min((stock.get("rel_volume", 0) - 1.0) / 2.0, 1.0)  # sättigt bei 3× statt 5×

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
    _chg_raw = stock.get("change", 0)
    if USE_RELATIVE_MOMENTUM:
        _spx_d = stock.get("spx_daily_perf", 0.0) or 0.0
        adjusted_chg = _chg_raw - _spx_d   # z.B. +3% Aktie, −2% SPX → +5% rel.
    else:
        adjusted_chg = _chg_raw

    if sf_val == 0 and sr_val == 0:
        # Fall 2: keine Short-Daten → Volumen (max 30) + Momentum (max 20), Cap 50
        # Nur positive Tagesveränderungen zählen: fallende Kurse = kein Squeeze-Druck
        rv_component = rv_raw * 30
        chg = max(adjusted_chg, 0)
        momentum = min(chg /  8.0, 1.0) * 20  # sättigt bei +8% statt +15%
        return min(round(rv_component + momentum + _fs, 2), 50.0)

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

    return round(min(sf + sr + rv + mom + _fs + _pts, 100.0), 2)


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

    return f"""
<article class="card" id="c{i}" data-ticker="{s['ticker']}">
  <div class="card-top">
    <div class="card-left">
      <span class="rank">{i}</span>
      <div class="ticker-block">
        <div class="ticker-row">
          <span class="ticker">{s['ticker']}</span>
          <span class="market-tag">{flag} {get_region(s["ticker"])}</span>
          {finviz_badge}{sa_badge}
          <span class="price-tag">${s.get('price',0):.2f}</span>
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
    </div>
    <div class="hdr-icons">
      <button class="fs-btn print-btn" onclick="window.print()" aria-label="Seite drucken" title="Drucken">🖨</button>
      <button class="fs-btn" id="fs-down" onclick="changeFontSize(-1)" aria-label="Schrift kleiner">A−</button>
      <button class="fs-btn" id="fs-up"   onclick="changeFontSize(1)"  aria-label="Schrift größer">A+</button>
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
  <div id="amsg" class="amsg" style="display:none"></div>
  <div style="padding-bottom:4px">
    <a class="tok-link" onclick="resetToken();return false;" href="#">Token zurücksetzen</a>
  </div>
  <div id="non-trading-banner" style="display:none;width:100%;background:#f59e0b;color:#1c1102;
    font-size:.78rem;font-weight:500;padding:5px 16px;box-sizing:border-box;
    border-top:1px solid #d97706;line-height:1.45" aria-live="polite"></div>
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
      const tickerSpan = card.querySelector('.ticker');
      if (!tickerSpan) return;

      const dot = document.createElement('span');
      let dotClass;
      if (score >= 70)      dotClass = 'strong';   // grün, schnell (1s)
      else if (score >= 40) dotClass = 'moderate'; // orange, mittel (1.5s)
      else if (score >= 1)  dotClass = 'weak';     // rot, langsam (2s)
      else                  dotClass = 'none';     // grau, kein Pulsieren
      dot.className = 'agent-dot ' + dotClass;

      const tip = document.createElement('span');
      tip.className = 'agent-tooltip';
      tip.textContent = `KI-Agent: Score ${{score}}/100 \u2014 ${{(sig && sig.drivers) || '?'}}`;
      dot.appendChild(tip);

      // iPhone: Antippen zeigt Tooltip für 3s
      dot.addEventListener('click', function(e) {{
        e.stopPropagation();
        dot.classList.add('touch-visible');
        setTimeout(() => dot.classList.remove('touch-visible'), 3000);
      }});

      tickerSpan.parentNode.insertBefore(dot, tickerSpan.nextSibling);

      // KI-Signal-Block im Neuigkeiten-Dropdown
      const block = card.querySelector('.ki-signal-block');
      if (block && score > 0) {{
        const lastScan = updated
          ? updated.toLocaleTimeString('de-DE', {{hour:'2-digit', minute:'2-digit'}})
          : '?';
        const phase = info.market_phase || '';
        const body  = block.querySelector('.ki-signal-body');
        if (body) {{
          body.innerHTML =
            `<span class="ki-score">Score: ${{score}}/100</span>` +
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
    candidates.sort(key=lambda x: x["score"], reverse=True)

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
    batch_yfd = get_yfinance_batch(pool_tickers)
    print(f"Step 2b (yfinance batch) abgeschlossen in {time.time()-_t_batch:.1f}s", flush=True)

    # Relative Stärke vs. S&P 500 (20T) + heutige Tagesveränderung
    _spx_perf_20d:   float | None = None
    _spx_daily_perf: float        = 0.0   # heutige S&P 500 Tagesveränderung in %
    try:
        _spx_hist = yf.download("^GSPC", period="25d", auto_adjust=True,
                                 progress=False, threads=False)
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
        enriched.append(c)
        # No per-ticker sleep needed — data already fetched in batch above

    _enrich_elapsed = time.time() - _enrich_start
    print(
        f"Angereichert: {len(enriched)}/{len(pool)} Kandidaten in {_enrich_elapsed:.1f}s",
        flush=True,
    )
    print(f"Step 2 abgeschlossen in {time.time()-_t_batch:.1f}s", flush=True)
    enriched.sort(key=lambda x: x["score"], reverse=True)

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

    top10.sort(key=lambda x: x["score"], reverse=True)

    # --- Step 3a: Score smoothing (70 % today + 30 % avg last 3 runs) ---
    apply_score_smoothing(top10, report_date)
    top10.sort(key=lambda x: x["score"], reverse=True)

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
    _t_opts = time.time()
    us_top10 = [s for s in top10 if "." not in s["ticker"]]
    log.info("Step 3b – Fetching options data for %d US stocks (parallel, max 5 threads) …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _opts_ex:
        _opts_futures = {_opts_ex.submit(get_options_data, s["ticker"]): s for s in us_top10}
        for _fut in as_completed(_opts_futures):
            _opts_futures[_fut]["options"] = _fut.result() or {}
    _opts_elapsed = time.time() - _t_opts
    _n_ok = sum(1 for s in us_top10 if s.get("options"))
    _n_na = len(us_top10) - _n_ok
    print(f"Optionsdaten: {len(us_top10)} Ticker parallel in {_opts_elapsed:.1f}s abgerufen — {_n_ok} mit Daten, {_n_na} ohne", flush=True)

    # Parallel earnings date fetch (US-only, max 5 threads).
    _t_earn = time.time()
    log.info("Step 3c – Fetching earnings dates for %d US stocks …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _earn_ex:
        _earn_futures = {_earn_ex.submit(get_earnings_date, s["ticker"]): s for s in us_top10}
        for _fut in as_completed(_earn_futures):
            _days, _dstr = _fut.result()
            _earn_futures[_fut]["earnings_days"] = _days
            _earn_futures[_fut]["earnings_date_str"] = _dstr
    print(f"Earnings-Termine: {len(us_top10)} Ticker in {time.time()-_t_earn:.1f}s abgerufen", flush=True)

    # Parallel SEC 13F fetch (US-only, max 5 threads).
    _t_13f = time.time()
    log.info("Step 3d – Checking SEC 13F for %d US stocks …", len(us_top10))
    with ThreadPoolExecutor(max_workers=5) as _13f_ex:
        _13f_futures = {_13f_ex.submit(fetch_sec_13f, s["ticker"]): s for s in us_top10}
        for _fut in as_completed(_13f_futures):
            note = _fut.result()
            if note:
                _13f_futures[_fut]["sec_13f_note"] = note
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
