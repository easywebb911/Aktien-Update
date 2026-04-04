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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from watchlist import WATCHLIST

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
MIN_REL_VOLUME  = 1.5    # × 20-day avg
MAX_MARKET_CAP  = 10e9   # $10 B
MIN_PRICE       = 1.0    # USD

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
FINRA_BONUS_MAX  = 5    # max bonus points for rising FINRA short interest
FTD_BONUS_MAX    = 0    # SEC EDGAR + Nasdaq Data Link blocked on GitHub Actions IPs
# ── FINRA short interest trend thresholds ────────────────────────────────────
SI_TREND_UP_THRESHOLD   =  0.10   # ≥+10 % over 3 periods → steigend
SI_TREND_DOWN_THRESHOLD = -0.10   # ≤−10 % → fallend; between → seitwärts


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

# Flag emojis for market tags
_MARKET_FLAGS: dict[str, str] = {
    "US": "🇺🇸",
    "DE": "🇩🇪",
    "GB": "🇬🇧",
    "FR": "🇫🇷",
    "NL": "🇳🇱",
    "CA": "🇨🇦",
    "JP": "🇯🇵",
    "HK": "🇭🇰",
    "KR": "🇰🇷",
}

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

    def _add_quotes(quotes: list, region: str) -> None:
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
                "short_float":  sf_raw * 100 if sf_raw <= 1.0 else sf_raw,
                "short_ratio":  float(q.get("shortRatio") or 0),
                "rel_volume":   0.0,
                "company_name": q.get("shortName") or q.get("longName") or t,
                "sector":       q.get("sector") or "",
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
            region, _ = future_map[fut]
            try:
                _add_quotes(fut.result(), region)
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
            })
            page_added += 1

        log.info("Finviz page %d: +%d → %d total", page + 1, page_added, len(candidates))
        time.sleep(1.5)  # polite rate-limit

    return candidates


# ===========================================================================
# 2. YFINANCE ENRICHMENT
# ===========================================================================

def get_yfinance_data(ticker: str) -> dict:
    _req_counts["yfinance"] += 1
    try:
        stk  = yf.Ticker(ticker)
        info = stk.info or {}
        hist = stk.history(period="30d")

        avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 5 else 0.0
        cur_vol    = float(hist["Volume"].iloc[-1])         if len(hist) >= 1 else 0.0
        vol_ratio  = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

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
            "float_shares": info.get("floatShares") or 0,
        }
    except Exception as exc:
        log.warning("yfinance error for %s: %s", ticker, exc)
        return {}


def get_yahoo_news(ticker: str, n: int = 2) -> list[dict]:
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
            ts_str = (
                datetime.fromtimestamp(int(pub_ts)).strftime("%d.%m.%Y %H:%M")
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
                "summary_raw": raw_summary,         # original English summary
                "publisher":   (content.get("provider", {}) or {}).get("displayName")
                                or content.get("publisher")
                                or item.get("publisher") or "",
                "link":        (content.get("canonicalUrl", {}) or {}).get("url")
                                or content.get("link")
                                or item.get("link") or "#",
                "time":        ts_str,
            })
        return news
    except Exception as exc:
        log.warning("News error for %s: %s", ticker, exc)
        return []


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
    """Download and parse FINRA daily short-volume pipe-delimited files from CDN.
    Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
    Tries consolidated (CNMS), NASDAQ (FNSQ) and NASDAQ Cap (FNQC) endpoints.
    Returns {ticker: short_volume} or {} on failure.
    """
    urls = [
        f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNSQshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNQCshvol{date_str}.txt",
    ]
    merged: dict[str, int] = {}
    for url in urls:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
            _req_counts["finra"] += 1
            if r.status_code != 200:
                print(f"FINRA CDN nicht verfügbar: {url.split('/')[-1]} → HTTP {r.status_code}")
                continue
            lines = r.text.splitlines()
            filename = url.split("/")[-1]
            # Parse header: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
            header = [h.strip().lower() for h in lines[0].split("|")]
            try:
                sym_idx = next(i for i, h in enumerate(header)
                               if "symbol" in h or "ticker" in h)
                sv_idx  = next(i for i, h in enumerate(header)
                               if "shortvol" in h.replace(" ", "") and "exempt" not in h)
            except StopIteration:
                # Fallback: fixed columns for CDN format (Symbol=1, ShortVolume=2)
                sym_idx, sv_idx = 1, 2
            count_before = len(merged)
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
                    merged[ticker] = merged.get(ticker, 0) + sv_val
            added = len(merged) - count_before
            print(f"FINRA CDN {date_str}: {filename} — {added} Ticker geladen", flush=True)
        except Exception as exc:
            print(f"FINRA CDN Fehler bei {url.split('/')[-1]}: {exc}", flush=True)
    return merged


def _get_finra_csv_for_date(date_str: str) -> dict[str, int]:
    """Return cached CSV data for date_str, loading it if needed."""
    if date_str not in _finra_csv_cache:
        _finra_csv_cache[date_str] = _load_finra_csv(date_str)
    return _finra_csv_cache[date_str]


def _latest_finra_dates(n: int = 3) -> list[str]:
    """Find the n most recent FINRA CDN daily-short-volume dates by probing
    backwards from yesterday (max 14 trading days). The CDN publishes one
    file per trading day (no weekends). Returns list of YYYYMMDD strings,
    newest first.
    """
    from datetime import date, timedelta
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
    _FINRA_MIN_VOL  = 10    # include all real data points (≥ 10 shares)
    _TREND_MIN_VOL  = 100   # trend % only computed when oldest ≥ 100 (avoids ÷ tiny)

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

    # Korrektur 2 debug: confirm T1/T2/T3 after threshold fix
    t1 = history[0]["short_interest"] if len(history) >= 1 else None
    t2 = history[1]["short_interest"] if len(history) >= 2 else None
    t3 = history[2]["short_interest"] if len(history) >= 3 else None
    print(f"{ticker} FINRA-Werte nach Fix: T1={t1}, T2={t2}, T3={t3}", flush=True)

    # Trend only when oldest ≥ 100 to prevent absurd percentages from tiny values
    trend, trend_pct = "no_data", 0.0
    if len(history) >= 2:
        newest = history[0]["short_interest"]
        oldest = history[-1]["short_interest"]
        if oldest >= _TREND_MIN_VOL:
            trend_pct = (newest - oldest) / oldest
            if trend_pct >= SI_TREND_UP_THRESHOLD:
                trend = "up"
            elif trend_pct <= SI_TREND_DOWN_THRESHOLD:
                trend = "down"
            else:
                trend = "sideways"

    _finra_stats["ok"] += 1
    return {
        "short_interest":      history[0]["short_interest"],
        "prev_short_interest": history[1]["short_interest"] if len(history) >= 2 else 0,
        "settlement_date":     history[0]["settlement_date"],
        "history":             history,
        "trend":               trend,
        "trend_pct":           round(trend_pct * 100, 1),
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
        trend = finra.get("trend", "no_data")
        if trend == "up":
            bonus = float(FINRA_BONUS_MAX)
        elif trend == "sideways":
            bonus = FINRA_BONUS_MAX / 2
        else:
            bonus = 0.0
    else:
        bonus = 0.0
        print(f"{ticker}: bonus=0.00 (unzureichende FINRA-Daten: "
              f"T1={t1}, T2={t2}, T3={t3})", flush=True)

    return round(min(bonus, float(FINRA_BONUS_MAX)), 2)


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
# Short Float %        → max 35 Pkt  (Sättigung bei 100 %)
# Short Ratio (Days)   → max 25 Pkt  (Sättigung bei 20 Tagen)
# Rel. Volumen         → max 25 Pkt  (Sättigung bei 5× Durchschnitt)
# Kursmomentum 5d      → max 15 Pkt  (Sättigung bei 15 %)
# Gesamt               → max 100 Pkt
#
# Verifikation (nicht ändern ohne explizite Anweisung):
# A: SF=30%, SR=10d, RV=3×, Mom=+8%   → Score 43.5
# B: SF=50%, SR=5d,  RV=5×, Mom=+15%  → Score 63.75
# C: SF=15%, SR=3d,  RV=1.5×, Mom=+3% → Score 15.12
def score(stock: dict) -> float:
    """Weighted squeeze score 0–100.
    When no short data is available (sf=0, sr=0) the score is capped at 50
    so these stocks can appear in the top 10 but never displace a stock with
    confirmed high short interest.
    """
    sf_val = stock.get("short_float", 0)
    sr_val = stock.get("short_ratio", 0)
    rv_raw = min((stock.get("rel_volume", 0) - 1.0) / 4.0, 1.0)

    if sf_val == 0 and sr_val == 0:
        # Fall 2: keine Short-Daten → Volumen (max 30) + Momentum (max 20), Cap 50
        rv_component = rv_raw * 30
        chg = abs(stock.get("change", 0))
        momentum = min(chg / 15.0, 1.0) * 20
        return min(round(rv_component + momentum, 2), 50.0)

    # Fall 1: Short-Daten vorhanden → vier Faktoren, max 100 Pkt
    sf  = min(sf_val / 100.0, 1.0) * 35
    sr  = min(sr_val /  20.0, 1.0) * 25
    rv  = rv_raw * 25
    mom = min(abs(stock.get("change", 0)) / 15.0, 1.0) * 15
    return round(sf + sr + rv + mom, 2)


def fmt_cap(v) -> str:
    if not v:
        return "N/A"
    v = float(v)
    if v >= 1e9:
        return f"${v/1e9:.1f} B"
    if v >= 1e6:
        return f"${v/1e6:.0f} M"
    return f"${v:,.0f}"


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

    sc      = min(s["score"], 100.0)
    sc_col  = _score_color(sc)
    sf      = s.get("short_float", 0)
    sr      = s.get("short_ratio", 0)
    rv      = s.get("rel_volume", 0)
    cap_val = s.get("yf_market_cap") or s.get("market_cap")
    chg     = s.get("change", 0)
    chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    chg_col = _metric_color("mom", chg)

    has_no_short_data = sf == 0 and sr == 0
    flag    = _MARKET_FLAGS.get(s.get("market", "US"), "")
    sf_display = "—" if has_no_short_data else f"{sf:.1f}%"
    sr_display = "—" if has_no_short_data else f"{sr:.1f}d"
    no_data_html = (
        '<p class="no-data-notice">ⓘ Short-Float &amp; Days to Cover für diesen Markt nicht verfügbar.</p>'
        if has_no_short_data else ""
    )

    sf_col = "#94a3b8" if has_no_short_data else _metric_color("sf", sf)
    sr_col = "#94a3b8" if has_no_short_data else _metric_color("sr", sr)
    rv_col = _metric_color("rv", rv)


    # SI trend badge + history
    finra_d  = s.get("finra_data") or {}
    si_trend = finra_d.get("trend", "no_data")
    si_tpct  = finra_d.get("trend_pct", 0.0)
    si_hist  = finra_d.get("history", [])
    if si_trend == "up":
        si_badge_html = '<span class="si-badge si-badge-up">↑</span>'
        trend_html    = f'<span style="color:#22c55e">↑ Steigend +{abs(si_tpct):.1f} %</span>'
    elif si_trend == "down":
        si_badge_html = '<span class="si-badge si-badge-down">↓</span>'
        trend_html    = f'<span style="color:#ef4444">↓ Fallend −{abs(si_tpct):.1f} %</span>'
    elif si_trend == "sideways":
        si_badge_html = '<span class="si-badge si-badge-side">→</span>'
        sign = "+" if si_tpct >= 0 else "−"
        trend_html    = f'<span style="color:#f59e0b">→ Seitwärts {sign}{abs(si_tpct):.1f} %</span>'
    else:
        si_badge_html = ""
        trend_html    = "Keine Daten"
    si_cur_disp = _fmt_si_record(si_hist[0]) if len(si_hist) >= 1 else "—"
    si_4w_disp  = _fmt_si_record(si_hist[1]) if len(si_hist) >= 2 else "—"
    si_8w_disp  = _fmt_si_record(si_hist[2]) if len(si_hist) >= 3 else "—"

    # Chart links
    yf_chart_url  = f"https://finance.yahoo.com/chart/{s['ticker']}"
    is_intl       = "." in s["ticker"]
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

    news_html = ""
    for n in s.get("news", [])[:2]:
        news_html += (
            f'<div class="ni">'
            f'<a href="{n.get("link","#")}" target="_blank" rel="noopener noreferrer">'
            f'{n.get("title","")}</a>'
            f'<span class="ni-meta">{n.get("publisher","")} · {n.get("time","")}</span>'
            f'</div>'
        )
    if not news_html:
        news_html = '<p class="no-news">Keine Nachrichten verfügbar.</p>'

    return f"""
<article class="card" id="c{i}">
  <div class="card-top">
    <div class="card-left">
      <span class="rank">{i}</span>
      <div class="ticker-block">
        <div class="ticker-row">
          <a class="ticker ticker-link" href="{yf_chart_url}" target="_blank" rel="noopener noreferrer">{s['ticker']}</a>
          <span class="market-tag">{flag} {s.get('market','US')}</span>
          {yahoo_badge}{finviz_badge}{sa_badge}
          <span class="price-tag">${s.get('price',0):.2f}</span>
        </div>
        <span class="company">{s.get('company_name','')}</span>
        {sector_tag_html}
      </div>
    </div>
    <div class="score-block">
      <span class="score-num" style="color:{sc_col}">{s['score']:.0f}</span>
      <span class="score-lbl">Score</span>
      <div class="score-track"><div class="score-fill" style="width:{sc:.0f}%;background:{sc_col}"></div></div>
    </div>
  </div>
  <div class="metrics-row">
    <div class="metric-box" style="--mc:{sf_col}">
      {si_badge_html}
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
      <span class="m-val">{chg_str}</span>
      <span class="m-lbl">Momentum</span>
    </div>
  </div>
  <button class="details-btn" onclick="toggleDetails({i})" id="db{i}" aria-expanded="false">
    <span class="details-arrow" id="da{i}">▾</span><span id="dl{i}"> Details anzeigen</span>
  </button>
  <div class="details-body" id="dd{i}">
    <div class="detail-table-wrap">
      <table class="detail-table">
        <tr><td>Marktkapitalisierung</td><td>{fmt_cap(cap_val)}</td></tr>
        {sector_detail_row}
        <tr><td>52W-Hoch / -Tief</td><td>${s.get('52w_high') or 0:.2f} / ${s.get('52w_low') or 0:.2f}</td></tr>
        <tr><td>Ø Volumen 20T</td><td>{s.get('avg_vol_20d',0):,.0f}</td></tr>
        <tr><td>Heutiges Volumen</td><td>{s.get('cur_vol',0):,.0f}</td></tr>
        <tr><td>Short Interest Quelle</td><td>{s.get('sf_source','Yahoo Finance')}</td></tr>
        <tr><td>Short-Vol.-Trend (3T)</td><td>{trend_html}</td></tr>
        <tr><td>Short-Vol. T-1 (FINRA)</td><td>{si_cur_disp}</td></tr>
        <tr><td>Short-Vol. T-2</td><td>{si_4w_disp}</td></tr>
        <tr><td>Short-Vol. T-3</td><td>{si_8w_disp}</td></tr>

        <tr><td>Risiko-Detail</td><td style="color:{risk_col}">{risk_txt}</td></tr>
      </table>
    </div>
    {no_data_html}
    <div class="driver-row">
      <span class="risk-badge" style="color:{risk_col};border-color:{risk_col}55;background:{risk_col}22">Risiko: {risk_lv}</span>
      <p class="driver-text">{sit_txt}</p>
    </div>
    <button class="news-btn" onclick="toggleNews({i})" id="nb{i}" aria-expanded="false">
      <span id="nb-icon{i}">▼</span> Nachrichten anzeigen
    </button>
    <div class="news-panel" id="np{i}" hidden>
      <div class="news-items">{news_html}</div>
      <div class="news-summary-box">
        <span class="summary-label">Zusammenfassung</span>
        <p class="summary-text">{news_sum}</p>
      </div>
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
.hdr-btns{{display:flex;gap:8px;width:100%;order:4}}
.btn{{display:inline-flex;align-items:center;justify-content:center;
  gap:6px;min-height:44px;padding:0 16px;border:none;border-radius:10px;
  font-size:.9rem;font-weight:700;cursor:pointer;flex:1;
  transition:opacity .15s,transform .1s;white-space:nowrap}}
.btn:active{{transform:scale(.96)}}
.btn:disabled{{opacity:.45;cursor:not-allowed;transform:none}}
.btn-g{{background:#16a34a;color:#fff}}.btn-g:hover:not(:disabled){{background:#15803d}}
.btn-b{{background:#2563eb;color:#fff}}.btn-b:hover:not(:disabled){{background:#1d4ed8}}
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
.stats-bar{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:14px}}
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
.ticker-link{{color:inherit;text-decoration:none}}
.ticker-link:hover{{text-decoration:underline;text-underline-offset:3px}}
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
.score-block{{display:flex;flex-direction:column;align-items:flex-end;min-width:64px}}
.score-num{{font-size:1.7rem;font-weight:900;line-height:1}}
.score-lbl{{font-size:.62rem;color:var(--txt-dim);text-transform:uppercase;
  letter-spacing:.4px;margin-bottom:5px}}
.score-track{{width:60px;height:5px;background:var(--brd);border-radius:3px}}
.score-fill{{height:100%;border-radius:3px;transition:width .3s}}
/* ── Metrics ── */
.metrics-row{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:0 12px 12px}}
.metric-box{{background:var(--bg-met);border:1px solid var(--brd);border-radius:10px;
  padding:10px 6px;text-align:center;border-top:3px solid var(--mc,#94a3b8);position:relative}}
.m-val{{display:block;font-size:1.1rem;font-weight:800;color:var(--mc,#94a3b8)}}
.m-lbl{{display:block;font-size:.62rem;color:var(--txt-dim);text-transform:uppercase;
  letter-spacing:.3px;margin-top:2px}}
.si-badge{{position:absolute;top:4px;right:5px;font-size:9px;font-weight:700;line-height:1}}
.si-badge-up{{color:#22c55e}}
.si-badge-down{{color:#ef4444}}
.si-badge-side{{color:#f59e0b}}
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
  border-top:1px solid var(--brd);color:var(--accent);font-size:.82rem;
  font-weight:700;cursor:pointer;padding:0 14px;text-align:left;display:flex;
  align-items:center;gap:6px}}
.news-btn:hover{{background:var(--brd)}}
/* ── News panel ── */
.news-panel{{border-top:1px solid var(--brd);padding:12px 14px}}
.news-items{{margin-bottom:12px}}
.ni{{margin-bottom:10px;font-size:.93rem;line-height:1.5}}
.ni a{{color:var(--accent);display:block;margin-bottom:2px}}
.ni a:hover{{text-decoration:underline}}
.ni-meta{{font-size:.7rem;color:var(--txt-dim)}}
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
  .metrics-row{{grid-template-columns:repeat(4,1fr)}}
  .stats-bar{{grid-template-columns:repeat(4,1fr)}}
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
</style>
</head>
<body>
<header class="app-hdr">
  <div class="hdr-main">
    <span class="app-title">Squeeze <span>Report</span></span>
    <span class="hdr-ts">{timestamp}</span>
    <div class="hdr-btns">
      <button id="btn-reload" class="btn btn-g" onclick="reloadPage()">&#8635; Neu laden</button>
      <button id="btn-recalc" class="btn btn-b" onclick="triggerWorkflow()">&#9881; Neu berechnen</button>
    </div>
    <div class="hdr-icons">
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
  <div class="stats-bar">
    <div class="stat-title">TopTen Squeezer</div>
    <div class="stat-box"><span class="stat-val">{avg_sf:.1f}%</span><span class="stat-lbl">Ø Short Float</span></div>
    <div class="stat-box"><span class="stat-val">{avg_sr:.1f}d</span><span class="stat-lbl">Ø Days to Cover</span></div>
    <div class="stat-box"><span class="stat-val">{avg_rv:.1f}×</span><span class="stat-lbl">Ø Volumen</span></div>
    <div class="stat-box"><span class="stat-val">{avg_mom_str}</span><span class="stat-lbl">Ø Kursmomentum</span></div>
  </div>

  <details class="info-panel">
    <summary>Score-Methodik &amp; Filterkriterien</summary>
    <div class="info-inner">
      <div class="info-box">
        <h4>Score (0–100)</h4>
        <ul>
          <li><strong>35 % Short Float</strong> – Anteil leerverkaufter Aktien; je höher, desto stärker der Squeeze-Druck</li>
          <li><strong>25 % Days to Cover</strong> – Tage zum vollständigen Eindecken; hohe Werte erhöhen Kapitulationsrisiko</li>
          <li><strong>25 % Rel. Volumen</strong> – Heutiges vs. 20-Tage-Durchschnitt; Spitzen signalisieren Kaufinteresse</li>
          <li><strong>15 % Kursmomentum</strong> – Kursveränderung (5 Tage); steigende Kurse erhöhen den Squeeze-Druck</li>
          <li><strong>+ bis 5 Pkt FINRA SI-Trend Bonus</strong> – steigender Short Interest ≥ +10 % → 5 Pkt · Seitwärts → 2,5 Pkt · Fallend oder keine Daten → 0 Pkt</li>
        </ul>
      </div>
      <div class="info-box">
        <h4>Filterkriterien</h4>
        <ul>
          <li><strong>Short Float &gt; 15 %</strong> – Mindest-Leerverkaufsquote</li>
          <li><strong>Kurs &gt; $1</strong> – Ausschluss von Penny Stocks</li>
          <li><strong>Marktkapitalisierung &lt; $10 Mrd.</strong> – Small- &amp; Mid-Caps</li>
          <li><strong>Märkte:</strong> 🇺🇸 US · 🇩🇪 DE · 🇬🇧 GB · 🇫🇷 FR · 🇳🇱 NL · 🇨🇦 CA · 🇯🇵 JP · 🇭🇰 HK · 🇰🇷 KR</li>
          <li><strong>Internationale Aktien:</strong> kein Short-Float-Filter, Score gedeckelt bei 50 Pkt (nur Volumen + Momentum)</li>
        </ul>
      </div>
      <div class="info-box">
        <h4>Datenquellen</h4>
        <ul>
          <li><strong>Yahoo Finance Screener</strong> – Most Shorted, Small Cap Gainers, Aggressive Small Caps</li>
          <li><strong>Märkte:</strong> 🇺🇸 US · 🇩🇪 DE · 🇬🇧 GB · 🇫🇷 FR · 🇳🇱 NL · 🇨🇦 CA · 🇯🇵 JP · 🇭🇰 HK · 🇰🇷 KR</li>
          <li><strong>Anreicherung:</strong> yfinance (Short Float, Days to Cover, Volumen, Kurs) + FINRA (offizielles Short Interest, SI-Trend aus 3 Meldezeiträumen)</li>

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
              <div class="cb-seg" style="background:#ef4444">&lt;−5 %</div>
              <div class="cb-seg" style="background:#f59e0b">−5 bis +5 %</div>
              <div class="cb-seg" style="background:#22c55e">≥ +5 %</div>
            </div>
            <p class="cl-desc">Grün bedeutet, dass der Kurs bereits steigt — Leerverkäufer geraten damit unter Druck, ihre Positionen schnell zu schließen.</p>
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
  btn.append(' ' + (open ? 'Nachrichten verbergen' : 'Nachrichten anzeigen'));
}}
// ── GitHub Actions Config ─────────────────────────────────────────────────
const GH_OWNER    = 'easywebb911';
const GH_REPO     = 'Aktien-update';
const GH_WORKFLOW = 'daily-squeeze-report.yml';
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
  if (!token) {{ showTokenInput(); return; }}
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
  await dispatchWorkflow(token);
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
// ── Workflow polling ──────────────────────────────────────────────────────
const POLL_MS    = 10000;
const TIMEOUT_MS = 600000;
let _pollStart = null, _pollToken = null, _pollTimer = null;
let _timeInterval = null;
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
  btn.disabled=false; btn.innerHTML='&#9881; Neu berechnen';
}}
function _showPollStatus(state){{
  const el = document.getElementById('amsg');
  el.style.display='block';
  if (state==='running'){{
    el.className='amsg amsg-poll-running';
    el.innerHTML='<span class="poll-dot poll-dot-run"></span>Neuberechnung läuft … <span id="poll-elapsed"></span>';
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
  if (Date.now()-_pollStart>TIMEOUT_MS) {{ _showPollStatus('timeout'); _enableRecalcBtn(); return; }}
  try {{
    const res = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/runs?workflow_id=${{GH_WORKFLOW}}&per_page=5&event=workflow_dispatch`,
      {{headers:{{'Authorization':`Bearer ${{_pollToken}}`,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}}}}
    );
    if (!res.ok) {{ _pollTimer=setTimeout(_doPoll,POLL_MS); return; }}
    const data = await res.json();
    const run = (data.workflow_runs||[]).find(w=>new Date(w.created_at).getTime()>=_pollStart-15000);
    if (!run) {{ _pollTimer=setTimeout(_doPoll,POLL_MS); return; }}
    if (run.status==='completed'){{
      if (run.conclusion==='success') {{ _stopTimeInterval(); _startSuccessCountdown(); }}
      else {{ _showPollStatus('failure'); _enableRecalcBtn(); }}
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

// ── Non-trading-day banner ────────────────────────────────────────────────────
// US federal holidays — update this array each year (format: "YYYY-MM-DD").
// Observed dates (Monday if Sunday, Friday if Saturday) should be listed.
(function(){{
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

  function toIso(d) {{
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const day = String(d.getDate()).padStart(2,'0');
    return `${{y}}-${{m}}-${{day}}`;
  }}

  function isHoliday(d) {{
    return US_HOLIDAYS.includes(toIso(d));
  }}

  function isNonTradingDay(d) {{
    const dow = d.getDay(); // 0=Sun, 6=Sat
    return dow === 0 || dow === 6 || isHoliday(d);
  }}

  function nextTradingDay(d) {{
    const next = new Date(d);
    next.setDate(next.getDate() + 1);
    while (isNonTradingDay(next)) {{
      next.setDate(next.getDate() + 1);
    }}
    return next;
  }}

  function fmtGerman(d) {{
    const weekdays = ['Sonntag','Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag'];
    const months = ['Januar','Februar','März','April','Mai','Juni',
                    'Juli','August','September','Oktober','November','Dezember'];
    return `${{weekdays[d.getDay()]}}, ${{d.getDate()}}. ${{months[d.getMonth()]}} ${{d.getFullYear()}}`;
  }}

  const today = new Date();
  today.setHours(0,0,0,0);

  if (isNonTradingDay(today)) {{
    const ntd = nextTradingDay(today);
    const dow = today.getDay();
    let reason;
    if (dow === 6 || dow === 0) {{
      reason = 'Wochenende';
    }} else {{
      reason = 'US-Feiertag';
    }}
    const banner = document.getElementById('non-trading-banner');
    banner.textContent =
      `\u26a0\ufe0f Kein Handelstag (${{reason}}) \u2014 ` +
      `Nächster US-Handelstag: ${{fmtGerman(ntd)}}. ` +
      `Die angezeigten Daten stammen vom letzten Handelstag.`;
    banner.style.display = 'block';
  }}
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
_WL_MAX_FAILURES  = 3   # consecutive 404/empty responses before auto-deactivation


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


def get_watchlist_candidates() -> list[dict]:
    """Quick volume scan of the static watchlist (only .history, no .info).
    Returns stocks whose current-day volume is ≥1.5× the 20-day average.
    Tickers with ≥3 consecutive empty/404 responses are auto-moved to
    watchlist_inactive.txt and skipped in future runs.
    """
    failures = _wl_load_failures()
    inactive = _wl_load_inactive()
    newly_inactive: list[str] = []

    results: list[dict] = []
    for market, tickers in WATCHLIST.items():
        active = [t for t in tickers if t not in inactive]
        log.info("Watchlist scan: %s (%d active / %d total)",
                 market, len(active), len(tickers))
        for ticker in active:
            try:
                hist = yf.Ticker(ticker).history(period="21d")
                if hist.empty or len(hist) < 5:
                    # Count consecutive failure
                    failures[ticker] = failures.get(ticker, 0) + 1
                    if failures[ticker] >= _WL_MAX_FAILURES:
                        _wl_mark_inactive(ticker)
                        newly_inactive.append(ticker)
                        failures.pop(ticker, None)
                    time.sleep(0.15)
                    continue
                # Success → reset failure count
                failures.pop(ticker, None)

                avg_vol = float(hist["Volume"].iloc[:-1].mean())
                cur_vol = float(hist["Volume"].iloc[-1])
                if avg_vol < 1000:
                    time.sleep(0.15)
                    continue
                rel_vol = cur_vol / avg_vol if avg_vol > 0 else 0.0
                if rel_vol < MIN_REL_VOLUME:
                    time.sleep(0.15)
                    continue
                price = float(hist["Close"].iloc[-1])
                if price < MIN_PRICE:
                    time.sleep(0.15)
                    continue
                prev_close = float(hist["Close"].iloc[-2])
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
            time.sleep(0.2)

    _wl_save_failures(failures)
    if newly_inactive:
        print(f"Watchlist: {len(newly_inactive)} Ticker als inaktiv markiert: "
              f"{newly_inactive}", flush=True)
    log.info("Watchlist candidates: %d (inactive skipped: %d)", len(results), len(inactive))
    return results


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
    log.info("Step 1b – Watchlist volume scan …")
    watchlist_cands = get_watchlist_candidates()
    existing_tickers = {c["ticker"] for c in candidates}
    for wc in watchlist_cands:
        if wc["ticker"] not in existing_tickers:
            candidates.append(wc)
            existing_tickers.add(wc["ticker"])
    log.info("Combined candidate pool after watchlist: %d tickers", len(candidates))

    # Pre-sort by whatever data we have so we enrich the most promising first
    for c in candidates:
        c["score"] = score(c)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Build enrichment pool: guarantee representation from all markets.
    # US stocks are sorted by score; international regions get up to 6 slots each
    # regardless of initial score (short-float data is rarely in screener response).
    us_pool   = [c for c in candidates if c.get("market") == "US"][:28]
    intl_pool = []
    for region in ("DE", "GB", "FR", "NL", "CA", "JP", "HK", "KR"):
        region_stocks = [c for c in candidates if c.get("market") == region][:6]
        intl_pool.extend(region_stocks)
    pool = us_pool + intl_pool

    # Pre-compute FINRA publication dates once
    finra_dates = _latest_finra_dates(3)

    # Opt 1: Pre-load all FINRA CSV files into cache before the per-ticker loop.
    # This triggers exactly 3×3 = 9 HTTP requests upfront instead of lazily
    # re-entering _load_finra_csv for every candidate.
    log.info("Step 2a – Pre-loading FINRA CDN data for %d dates …", len(finra_dates))
    for _d in finra_dates:
        _get_finra_csv_for_date(_d)
    _total_finra_entries = sum(len(v) for v in _finra_csv_cache.values())
    print(f"FINRA Cache aufgebaut: {len(_finra_csv_cache)} Dateien, "
          f"{_total_finra_entries} Ticker-Einträge gesamt", flush=True)

    # --- Step 2: yfinance enrichment (all real filtering happens here) ---
    log.info("Step 2 – Enriching %d candidates with yfinance …", len(pool))
    enriched = []
    for i, c in enumerate(pool):
        t = c["ticker"]
        log.info("  [%d/%d] %s", i + 1, len(pool), t)
        yfd = get_yfinance_data(t)

        # Overwrite with accurate yfinance values
        c.update({
            "company_name":  yfd.get("company_name") or c.get("company_name", t),
            "sector":        yfd.get("sector") or c.get("sector") or "",
            "industry":      yfd.get("industry") or c.get("industry") or "",
            "yf_market_cap": yfd.get("market_cap"),
            "52w_high":      yfd.get("52w_high"),
            "52w_low":       yfd.get("52w_low"),
            "avg_vol_20d":   yfd.get("avg_vol_20d", 0),
            "cur_vol":       yfd.get("cur_vol", 0),
        })
        yf_sf = yfd.get("short_float_yf", 0)
        if yf_sf > 0:
            c["short_float"] = yf_sf
        yf_sr = yfd.get("short_ratio", 0)
        if yf_sr > 0:
            c["short_ratio"] = yf_sr
        if yfd.get("vol_ratio", 0) > 0:
            c["rel_volume"] = yfd["vol_ratio"]

        # FINRA daily short-volume data (US stocks only; used for trend badge/bonus only,
        # NOT for short-float override since CDN files contain daily volume, not total SI)
        is_us_finra = c.get("market", "US") == "US"
        if is_us_finra:
            finra = get_finra_short_interest(t, finra_dates)
            c["finra_data"] = finra
            time.sleep(0.2)
        else:
            c["finra_data"] = {}
        c["sf_source"] = "Yahoo Finance"

        # Hard filters (now with accurate data)
        cap = c.get("yf_market_cap") or c.get("market_cap")
        if cap and cap > MAX_MARKET_CAP:
            log.info("    skip %s: cap %s > $10B", t, fmt_cap(cap))
            time.sleep(0.25)
            continue

        # Short-float filter: apply strictly for US; relax for non-US markets
        # where short-interest data is rarely available via yfinance.
        is_us = c.get("market", "US") == "US"
        has_sf_data = c["short_float"] > 0
        if is_us and c["short_float"] < MIN_SHORT_FLOAT:
            log.info("    skip %s: short_float %.1f%% < %.0f%%",
                     t, c["short_float"], MIN_SHORT_FLOAT)
            time.sleep(0.25)
            continue
        if not is_us and not has_sf_data:
            # No short data available – keep if relative volume signals activity
            if c.get("rel_volume", 0) < 1.0:
                log.info("    skip %s [%s]: no short data + low volume (%.1f×)",
                         t, c.get("market"), c.get("rel_volume", 0))
                time.sleep(0.25)
                continue
            log.info("    keep %s [%s]: no short data but vol=%.1f× (intl)",
                     t, c.get("market"), c.get("rel_volume", 0))

        c["score"] = score(c)
        enriched.append(c)
        time.sleep(0.4)

    enriched.sort(key=lambda x: x["score"], reverse=True)

    # Apply volume filter; relax automatically if too few results
    top10 = [c for c in enriched if c.get("rel_volume", 0) >= MIN_REL_VOLUME][:10]
    if len(top10) < 5:
        log.warning(
            "Only %d pass rel_volume ≥ %.1f×. Relaxing to 1.0× …",
            len(top10), MIN_REL_VOLUME,
        )
        top10 = enriched[:10]

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

    # --- Step 3: News ---
    log.info("Step 3 – Fetching news for %d stocks …", len(top10))
    for s in top10:
        s["news"] = get_yahoo_news(s["ticker"])
        time.sleep(0.3)

    # --- Step 4: HTML ---
    log.info("Step 4 – Generating HTML report …")
    html = generate_html(top10, report_date)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)

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
        f"Laufzeit: {_elapsed:.1f}s | "
        f"HTTP-Requests: FINRA={_req_counts['finra']}, "
        f"Yahoo={_req_counts['yahoo']}, "
        f"Sonstige(yfinance)={_req_counts['yfinance']} | "
        f"Kandidaten: {len(pool)}→{len(top10)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
