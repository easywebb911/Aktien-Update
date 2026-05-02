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
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import *   # zentrale Konstanten (Schwellen, Score-Gewichte, Timeouts, URLs)
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

# Konstanten (Schwellen, Score-Gewichte, Timeouts, Farben) kommen aus config.py
# — siehe ``from config import *`` oben. Anpassungen dort vornehmen.


def strip_surrogates(s):
    """Entfernt nicht-UTF-8-fähige Surrogate-Codepoints (U+D800–U+DFFF) aus
    Strings. Verhindert ``UnicodeEncodeError`` beim HTML-Write.

    yfinance/RSS-Feeds liefern in seltenen Fällen halbe Surrogate-Paare
    (z. B. wenn ein 4-Byte-Emoji in zwei UTF-16-Halften zerschnitten wurde),
    die zwar als Python-``str`` existieren dürfen, aber bei
    ``str.encode("utf-8")`` einen ``UnicodeEncodeError`` werfen.
    """
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", errors="replace").decode("utf-8")


def _test_strip_surrogates():
    """Selbsttest. Aufrufbar via ``python -c
    'import generate_report as g; g._test_strip_surrogates()'``."""
    bad = "Hallo \ud83d Welt"
    try:
        bad.encode("utf-8")
    except UnicodeEncodeError:
        pass  # erwartet
    else:
        raise AssertionError("Test-Setup defekt: Surrogate war encodbar")
    cleaned = strip_surrogates(bad)
    cleaned.encode("utf-8")  # darf nicht mehr crashen
    assert "\ud83d" not in cleaned, "Surrogate nicht entfernt"
    # Non-string Input darf nicht crashen
    assert strip_surrogates(None) is None
    assert strip_surrogates(42) == 42
    # Sauberer Input bleibt unverändert
    assert strip_surrogates("Hello 🚀 World") == "Hello 🚀 World"
    print("OK: strip_surrogates self-test passed")


def _test_fallback_chain():
    """Selbsttest für SF/SI-Trend-Fallback-Logik. Aufrufbar via
    ``python -c 'import generate_report as g; g._test_fallback_chain()'``.

    Mockt die Live-Fetcher (Finviz/Stockanalysis/yfinance), damit der Test
    offline reproduzierbar ist und keine HTTP-Calls macht.
    """
    import sys
    mod = sys.modules[__name__]

    # ── SF-Kette ────────────────────────────────────────────────────
    saved = {
        "fv":  mod._fetch_short_float_finviz,
        "sa":  mod._fetch_short_float_stockanalysis,
    }
    try:
        # Stub 1: alle Fallback-Quellen liefern None → bei untauglichem yf
        # muss Endergebnis (None, "none") sein.
        mod._fetch_short_float_finviz        = lambda t: None
        mod._fetch_short_float_stockanalysis = lambda t: None

        # yf valide → akzeptiert ohne Fallback
        v, s = get_short_float_with_fallback("X", 1.5)
        assert (v, s) == (1.5, "yfinance"), (v, s)

        # yf=None, screener-Cache valide → "finviz" (Cache-Hit)
        v, s = get_short_float_with_fallback("X", None, screener_value=22.4)
        assert (v, s) == (22.4, "finviz"), (v, s)

        # yf=0.0 (häufiger yfinance-Bug) → ebenfalls Fallback
        v, s = get_short_float_with_fallback("X", 0.0)
        assert s == "none" and v is None, (v, s)

        # Stub 2: Finviz liefert
        mod._fetch_short_float_finviz = lambda t: 18.4
        v, s = get_short_float_with_fallback("WOLF", None)
        assert (v, s) == (18.4, "finviz"), (v, s)

        # Stub 3: nur Stockanalysis liefert
        mod._fetch_short_float_finviz        = lambda t: None
        mod._fetch_short_float_stockanalysis = lambda t: 12.3
        v, s = get_short_float_with_fallback("X", None)
        assert (v, s) == (12.3, "stockanalysis"), (v, s)

        # Schwelle 0.5 %: yf=0.4 wird abgelehnt, fällt in screener-Cache
        mod._fetch_short_float_finviz        = lambda t: None
        mod._fetch_short_float_stockanalysis = lambda t: None
        v, s = get_short_float_with_fallback("X", 0.4, screener_value=20.0)
        assert (v, s) == (20.0, "finviz"), (v, s)
    finally:
        mod._fetch_short_float_finviz        = saved["fv"]
        mod._fetch_short_float_stockanalysis = saved["sa"]

    # ── SI-Trend yfinance-Berechnung ────────────────────────────────
    # Wir testen die Klassifikationslogik durch Stub des yf.Ticker-Calls.
    class _FakeTicker:
        def __init__(self, info): self.info = info
    saved_yf = mod.yf
    class _FakeYF:
        @staticmethod
        def Ticker(t): return _FakeTicker(_FakeYF._next)
    try:
        mod.yf = _FakeYF
        # +12 % → "up"
        _FakeYF._next = {"sharesShort": 1_120_000, "sharesShortPriorMonth": 1_000_000}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "up" and r["trend_pct"] == 12.0, r
        # −10 % → "down"
        _FakeYF._next = {"sharesShort": 900_000, "sharesShortPriorMonth": 1_000_000}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "down" and r["trend_pct"] == -10.0, r
        # +3 % → "sideways"
        _FakeYF._next = {"sharesShort": 1_030_000, "sharesShortPriorMonth": 1_000_000}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "sideways" and r["trend_pct"] == 3.0, r
        # priorMonth = 0 → "no_data"
        _FakeYF._next = {"sharesShort": 1_000_000, "sharesShortPriorMonth": 0}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "no_data", r
        # priorMonth fehlt → "no_data"
        _FakeYF._next = {"sharesShort": 1_000_000}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "no_data", r
        # Beide fehlen → "no_data"
        _FakeYF._next = {}
        r = _fetch_si_trend_from_yfinance("X")
        assert r["trend"] == "no_data", r
    finally:
        mod.yf = saved_yf
    print("OK: fallback-chain self-test passed")


def _test_extended_schema():
    """Selbsttest für die backtest_history.json Schema-Erweiterung (Bahn B).

    Aufrufbar via ``python -c
    'import generate_report as g; g._test_extended_schema()'``.

    Baut zwei synthetische Top-10-Stocks (volle Boni vs. keine Boni) und
    verifiziert dass alle 14 neuen Felder korrekt im Extension-Dict landen,
    inklusive Default-Werten.
    """
    # Stock 1: alle Boni aktiv
    full = {
        "ticker": "TEST", "score": 88.5, "score_raw": 76.3,
        "price": 5.10, "short_float": 35.0, "short_ratio": 6.0,
        "rel_volume": 2.5, "change": 3.0, "spx_daily_perf": 0.0,
        "float_shares": 50_000_000, "rsi14": 55, "ma50": 4.8,
        "rel_strength_20d": 8.0, "earnings_days": 5, "options": {"pc_ratio": 0.4},
        "borrow_rate": 60.0, "sec_13f_note": True,
        "finra_data": {"trend": "up", "trend_pct": 25.0,
                       "history": [{"short_interest": 600},
                                   {"short_interest": 700},
                                   {"short_interest": 800}],
                       "si_trend_source": "finra"},
        "agent_boost_pts": 5.0, "agent_boost_factor": 1.10,
        "score_trend_bonus_pts": 3.0, "finra_bonus_pts": 7.0,
        "short_float_source": "yfinance",
    }
    sigs_full = {"TEST": {"combo_mult": 1.20, "active_triggers": 3}}
    ext = _build_backtest_extension(full, pool_position=1, pool_size=78,
                                    agent_signals=sigs_full)
    expected_keys = {
        "score_struct","score_catalyst","score_timing","score_raw",
        "combo_bonus","score_trend_bonus","agent_boost_factor",
        "perfect_storm_mult","finra_bonus","pool_member","pool_position",
        "pool_size","short_float_source","si_trend_source",
    }
    assert set(ext.keys()) == expected_keys, set(ext.keys()) ^ expected_keys
    assert ext["score_raw"]          == 76.3, ext
    assert ext["combo_bonus"]        == float(COMBO_BONUS), ext  # 4/4 Bedingungen
    assert ext["score_trend_bonus"]  == 3.0, ext
    assert ext["agent_boost_factor"] == 1.10, ext
    assert ext["perfect_storm_mult"] == 1.20, ext
    assert ext["finra_bonus"]        == 7.0, ext
    assert ext["pool_member"]        is True, ext
    assert ext["pool_position"]      == 1, ext
    assert ext["pool_size"]          == 78, ext
    assert ext["short_float_source"] == "yfinance", ext
    assert ext["si_trend_source"]    == "finra", ext
    assert ext["score_struct"]   is not None, ext
    assert ext["score_catalyst"] is not None, ext
    assert ext["score_timing"]   is not None, ext

    # Stock 2: keine Boni, fehlende Source-Felder, kein Agent-Signal
    bare = {
        "ticker": "BARE", "score": 42.0, "price": 1.5,
        "short_float": 10.0, "short_ratio": 2.0, "rel_volume": 1.2,
        "change": 0.5, "float_shares": 200_000_000,
        "finra_data": {"trend": "no_data", "history": []},
    }
    ext2 = _build_backtest_extension(bare, pool_position=10, pool_size=42,
                                     agent_signals={})
    # Defaults für inaktive Boni
    assert ext2["combo_bonus"]        == 0.0, ext2
    assert ext2["score_trend_bonus"]  == 0.0, ext2
    assert ext2["agent_boost_factor"] == 1.0, ext2
    assert ext2["perfect_storm_mult"] == 1.0, ext2
    assert ext2["finra_bonus"]        == 0.0, ext2
    # Source-Defaults
    assert ext2["short_float_source"] == "unknown", ext2
    assert ext2["si_trend_source"]    == "unknown", ext2
    # Pool-Kontext bleibt korrekt
    assert ext2["pool_position"] == 10, ext2
    assert ext2["pool_size"]     == 42, ext2
    # score_raw default 0.0 wenn Stock kein score_raw mitführt (Edge-Case)
    assert ext2["score_raw"] == 0.0, ext2
    print("OK: extended-schema self-test passed")


# Module-level state: aktueller USD→EUR-Wechselkurs. Wird in main() einmal
# pro Daily-Run via yfinance „EURUSD=X" gesetzt (= EUR pro 1 USD, also der
# Multiplikator für die Anzeige „$4.47 (4,11 €)"). Default 0.92 als Notnagel
# bevor main() läuft. Read-only nach Initialisierung.
_FX_USD_EUR: float = 0.92


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

# Markets to scan: region code → list of predefined screener IDs.
# Die US-Liste hängt auch EXTRA_SCREENERS aus config.py an — erweitert den
# Kandidatenpool um zusätzliche Kategorien (z.B. undervalued_growth_stocks,
# day_gainers). Duplikate zwischen Screenern werden per seen-Set (siehe
# _add_quotes) deduped.
_YF_SCREENERS: dict[str, list[str]] = {
    "US": ["most_shorted_stocks", "small_cap_gainers", "aggressive_small_caps"]
          + list(EXTRA_SCREENERS or []),
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
                "company_name": strip_surrogates(q.get("shortName") or q.get("longName") or t),
                "sector":       strip_surrogates(q.get("sector") or ""),
                "source":       src_tag,
            })

    tasks = [(region, sid)
             for region, sids in _YF_SCREENERS.items()
             for sid in sids
             if INTL_SCREENING_ENABLED or region == "US"]
    n_regions = len({r for r, _ in tasks})
    log.info("Querying %d Yahoo Finance screeners across %d region(s) "
             "(INTL_SCREENING_ENABLED=%s, parallel, max 5 threads) …",
             len(tasks), n_regions, INTL_SCREENING_ENABLED)
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


def get_finviz_screener_v111(max_tickers: int | None = None) -> list[dict]:
    """Finviz Screener (view 111) — **zusätzliche** Quelle zum Yahoo-Pool.

    URL-Filter:  sh_short_o20 (SF>20%)  + sh_price_o1 (>$1)
               + sh_relvol_o1.5 (≥1.5×) + cap_smallover (Small+)
               sortiert nach Short Float absteigend.

    Extrahiert nur Ticker (keine Detail-Spalten) und liefert
    minimal-ausgestattete Candidate-Dicts; Enrichment füllt den Rest.

    Config: FINVIZ_SCREENER_ENABLED=True aktiviert den Aufruf,
            FINVIZ_MAX_TICKERS begrenzt die Ergebniszahl.
    Bei HTTP-Fehler oder Parser-Ausfall: stillschweigend [] zurück.
    """
    if not FINVIZ_SCREENER_ENABLED:
        return []
    limit = max_tickers or FINVIZ_MAX_TICKERS
    url = ("https://finviz.com/screener.ashx"
           "?v=111&f=sh_short_o20,sh_price_o1,sh_relvol_o1.5,cap_smallover"
           "&ft=4&o=-shortfloat")
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"Finviz Screener: HTTP {resp.status_code} — übersprungen", flush=True)
            return []
    except Exception as exc:
        print(f"Finviz Screener: Fehler {exc} — übersprungen", flush=True)
        return []

    # Ticker-Symbole aus Finviz-Quote-Links extrahieren; v=111 zeigt die
    # Tabelle mit quote.ashx?t=<TICKER>-Links. Regex ist robust gegen
    # Markup-Varianten und vermeidet einen harten BeautifulSoup-Pfad.
    tickers: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'quote\.ashx\?t=([A-Z0-9.\-]{1,12})(?:&|")', resp.text):
        t = m.group(1).upper()
        if t in seen:
            continue
        seen.add(t)
        tickers.append(t)
        if len(tickers) >= limit:
            break

    print(f"Finviz Screener: {len(tickers)} Ticker geladen", flush=True)
    # Minimal-Candidate-Dicts — Enrichment-Schleife füllt alle fehlenden Felder
    return [{
        "ticker":       t,
        "market":       "US",
        "source":       "finviz_screener_v111",
        "short_float":  0.0,
        "short_ratio":  0.0,
        "rel_volume":   0.0,
        "company_name": t,
    } for t in tickers]


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
        cur_open   = float(hist["Open"].iloc[-1])  if "Open"  in hist.columns and len(hist) >= 1 else None
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None

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
            "company_name": strip_surrogates(info.get("longName") or info.get("shortName") or ticker),
            "sector":       strip_surrogates(info.get("sector") or ""),
            "industry":     strip_surrogates(info.get("industry") or ""),
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
            "cur_open":     cur_open,
            "prev_close":   prev_close,
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
        """Extract (avg_vol_20, cur_vol, vol_ratio, hi52, lo52, rsi14, ma50, ma200, perf_20d, cur_open, prev_close) from batch or fallback."""
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
                    cur_open   = float(df["Open"].iloc[-1])  if "Open"  in df.columns and len(df) >= 1 else None
                    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else None
                    return avg_vol, cur_vol, vol_r, hi52, lo52, rsi14, ma50, ma200, perf_20d, cur_open, prev_close
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
                cur_open   = float(df2["Open"].iloc[-1])  if "Open"  in df2.columns and len(df2) >= 1 else None
                prev_close = float(df2["Close"].iloc[-2]) if len(df2) >= 2 else None
                return avg_vol, cur_vol, vol_r, float(df2["High"].max()), float(df2["Low"].min()), rsi14, ma50, ma200, perf_20d, cur_open, prev_close
        except Exception as exc2:
            log.debug("Fallback history failed for %s: %s", ticker, exc2)
        return 0.0, 0.0, 0.0, None, None, None, None, None, None, None, None

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

    def _detect_recent_squeeze(df) -> dict | None:
        """Feature 6 — Scan ~90 Tage rückwärts auf Kursanstieg ≥50 % in
        5 Handelstagen bei Volumen ≥3× des 20-Tage-Durchschnitts davor.
        Gibt den jüngsten Treffer als ``{"found", "days_ago", "gain_pct"}``
        zurück oder ``None`` wenn kein Squeeze detektiert wurde.
        """
        try:
            if df is None or df.empty:
                return None
            closes = df["Close"].dropna()
            vols   = df["Volume"].dropna()
            if len(closes) < 26 or len(vols) < 26:
                return None
            max_offset = min(SQUEEZE_DETECTION_DAYS, len(closes) - 6)
            for offset in range(0, max_offset):   # offset 0 = jüngster Tag
                end_i   = len(closes) - 1 - offset
                start_i = end_i - 5
                if start_i < 20:
                    break
                c0 = float(closes.iloc[start_i])
                c1 = float(closes.iloc[end_i])
                if c0 <= 0:
                    continue
                gain = (c1 - c0) / c0
                if gain < SQUEEZE_MIN_GAIN:
                    continue
                win_vol   = float(vols.iloc[start_i:end_i + 1].mean())
                prior_vol = float(vols.iloc[start_i - 20:start_i].mean())
                if prior_vol <= 0:
                    continue
                if win_vol < SQUEEZE_MIN_RVOL * prior_vol:
                    continue
                return {
                    "found":    True,
                    "days_ago": offset,
                    "gain_pct": round(gain * 100, 1),
                }
        except Exception as exc:
            log.debug("squeeze-detect error: %s", exc)
        return None

    def _df_for(ticker: str):
        """Extrahiere ticker-spezifisches DataFrame aus dem Batch."""
        try:
            if hist_batch is None or hist_batch.empty:
                return None
            return hist_batch if len(tickers) == 1 else hist_batch[ticker]
        except Exception:
            return None

    # ── Combine history + info; fallback to individual call if both are empty ──
    for ticker in tickers:
        avg_vol_20, cur_vol, vol_ratio, hi52, lo52, rsi14, ma50, ma200, perf_20d, cur_open, prev_close = _hist_stats(ticker)
        info = info_map.get(ticker, {})

        # If the batch produced nothing useful for this ticker, fall back entirely
        if not info and avg_vol_20 == 0.0:
            log.debug("Batch empty for %s — falling back to individual get_yfinance_data()", ticker)
            results[ticker] = get_yfinance_data(ticker)
            continue

        results[ticker] = {
            "company_name":   strip_surrogates(info.get("longName") or info.get("shortName") or ticker),
            "sector":         strip_surrogates(info.get("sector") or ""),
            "industry":       strip_surrogates(info.get("industry") or ""),
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
            "cur_open":       cur_open,
            "prev_close":     prev_close,
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

        # Feature 6 — Squeeze-History-Detektor über Batch-Daten
        results[ticker]["recent_squeeze"] = _detect_recent_squeeze(_df_for(ticker))

        # Feature 3 (P&D): rel_volume_yesterday = vol[-2] / avg_vol(last 20 excluding yesterday)
        try:
            _df2 = _df_for(ticker)
            if _df2 is not None and len(_df2) >= 22:
                _vols = _df2["Volume"].dropna()
                if len(_vols) >= 22:
                    _vol_y    = float(_vols.iloc[-2])
                    _avg20_y  = float(_vols.iloc[-22:-2].mean())
                    if _avg20_y > 0:
                        results[ticker]["rel_volume_yesterday"] = round(
                            _vol_y / _avg20_y, 3)
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
            title_orig = strip_surrogates(content.get("title") or item.get("title") or "")
            # Collect every candidate field that might carry article body text.
            # yfinance uses different field names across versions.
            raw_summary = strip_surrogates((
                content.get("body")
                or content.get("summary")
                or content.get("description")
                or content.get("snippet")
                or item.get("body")
                or item.get("summary")
                or item.get("description")
                or item.get("snippet")
                or ""
            ).strip())
            # If the "summary" is just a copy of the title, discard it.
            if raw_summary and raw_summary.strip(".").strip() == title_orig.strip(".").strip():
                raw_summary = ""

            news.append({
                "title":       _translate(title_orig) if title_orig else "",
                "title_orig":  title_orig,
                "summary_raw": raw_summary,
                "publisher":   strip_surrogates(
                                (content.get("provider", {}) or {}).get("displayName")
                                or content.get("publisher")
                                or item.get("publisher") or "Yahoo Finance"),
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


def _rss_news(ticker: str, url: str, source_label: str, timeout: int = 3) -> list[dict]:
    """Fetch and parse a generic RSS/Atom feed; return normalised news items."""
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        # Support both RSS (<channel><item>) and Atom (<entry>)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        result = []
        for item in items[:5]:
            title = strip_surrogates((
                item.findtext("title")
                or item.findtext("atom:title", namespaces=ns)
                or ""
            ).strip())
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
    """Merge Yahoo Finance + Finviz news; return top n by date.

    Seeking Alpha wurde aus der Quellenliste entfernt (2026-04): lieferte
    oft dieselben Meldungen wie Yahoo und war langsam. Yahoo (JSON) +
    Finviz (RSS) decken die wichtigsten Catalysts ab.
    """
    base_upper = ticker.split(".")[0].upper()

    yahoo_items = get_yahoo_news(ticker, n=5)
    fv_items    = _rss_news(
        ticker,
        f"https://finviz.com/rss.ashx?t={base_upper}",
        "Finviz",
    )

    n_yahoo, n_fv = len(yahoo_items), len(fv_items)
    combined = yahoo_items + fv_items
    combined.sort(key=lambda x: x.get("ts", 0), reverse=True)
    result = combined[:n]
    print(f"News {ticker}: {n_yahoo} Yahoo + {n_fv} Finviz = {len(result)} Meldungen")
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

        # Gamma Squeeze: summiere Call-OI im ATM-Bereich über die nächsten 2
        # kurzlaufenden Verfallstermine (≤ GAMMA_MAX_DAYS_TO_EXPIRY).
        gamma_call_oi = 0
        if GAMMA_SQUEEZE_ENABLED and cur_price is not None:
            gamma_max = _dt.today() + _td(days=GAMMA_MAX_DAYS_TO_EXPIRY)
            short_exp = [e for e in expiries
                         if _dt.strptime(e, "%Y-%m-%d") <= gamma_max]
            atm_low  = cur_price * (1 - GAMMA_ATM_RANGE)
            atm_high = cur_price * (1 + GAMMA_ATM_RANGE)
            for exp in short_exp[:GAMMA_NUM_EXPIRIES]:
                try:
                    exp_calls = calls if exp == chosen else stk.option_chain(exp).calls
                    atm_slice = exp_calls[
                        (exp_calls["strike"] >= atm_low) &
                        (exp_calls["strike"] <= atm_high)
                    ]
                    gamma_call_oi += int(atm_slice["openInterest"].fillna(0).sum())
                except Exception as exc:  # noqa: BLE001
                    log.debug("%s gamma-expiry %s failed: %s", ticker, exp, exc)

        return {"pc_ratio": pc_ratio, "atm_iv": atm_iv, "expiry": chosen,
                "gamma_call_oi": gamma_call_oi}
    except Exception as exc:
        log.debug("Options data failed for %s: %s", ticker, exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 2b. IBKR Stock Borrow Rates (public page, cached single-fetch per run)
# ─────────────────────────────────────────────────────────────────────────────

# Sentinel: None = noch nicht versucht; dict = Fetch erfolgreich (u.U. leer);
# {} = Fetch versucht, aber geblockt/fehlgeschlagen (negatives Caching).
_IBKR_BORROW_CACHE: dict[str, float] | None = None


def _ibkr_borrow_load() -> dict[str, float]:
    """Scraped die öffentliche IBKR Stock-Borrow-Rates-Tabelle genau einmal.

    Fällt bei Cloudflare-Block, Timeout oder leerer Antwort auf ein leeres
    Dict zurück — der Aufrufer unterscheidet das nicht von „Ticker nicht
    vorhanden". Wird nur einmal pro Run aufgerufen (Ergebnis wird im
    Modul-Cache ``_IBKR_BORROW_CACHE`` gehalten).
    """
    # timeout als Tupel: (connect, read) — beide hart ≤ IBKR_BORROW_TIMEOUT,
    # verhindert langsames Trickle-Streaming durch Cloudflare.
    # stream=False zwingt requests die Response komplett zu lesen bevor
    # zurückgegeben wird — Verbindung wird sofort beendet statt offen gehalten.
    _to = (IBKR_BORROW_TIMEOUT, IBKR_BORROW_TIMEOUT)
    try:
        resp = requests.get(
            IBKR_BORROW_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=_to,
            stream=False,
        )
    except requests.RequestException as exc:
        log.warning("IBKR borrow-rate fetch failed after %ds: %s",
                    IBKR_BORROW_TIMEOUT, exc)
        return {}
    if resp.status_code == 404:
        print("IBKR Borrow Rate: HTTP 404 — Seite nicht gefunden, Fallback auf None",
              flush=True)
        return {}
    if resp.status_code != 200 or not resp.text:
        log.warning("IBKR borrow-rate HTTP %d (%d bytes)",
                    resp.status_code, len(resp.text or ""))
        return {}

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:  # noqa: BLE001
        log.debug("IBKR borrow-rate parse failed: %s", exc)
        return {}

    rates: dict[str, float] = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}$")
    rate_re   = re.compile(r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*%?\s*$")
    # Generischer Row-Scan: akzeptiert jedes <tr> mit ≥ 2 Zellen, wo Spalte 0
    # ein Ticker-Symbol ist und irgendeine spätere Zelle einen numerischen
    # Wert enthält. Damit sind kleinere HTML-Änderungen verkraftbar.
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        tick = cells[0].get_text(strip=True).upper()
        if not ticker_re.match(tick):
            continue
        for c in cells[1:]:
            m = rate_re.match(c.get_text(strip=True).replace(",", "."))
            if m:
                try:
                    rates[tick] = float(m.group(1))
                    break
                except ValueError:
                    continue
    log.info("IBKR borrow-rate: %d Ticker geparsed", len(rates))
    return rates


def fetch_ibkr_borrow_rate(ticker: str) -> float | None:
    """Public Borrow-Rate (%/Jahr) für ``ticker`` oder ``None``.

    Erster Aufruf löst den eigentlichen HTTP-Fetch aus; weitere Aufrufe
    nutzen den Modul-Cache. Gibt None zurück bei deaktiviertem Feature,
    fehlgeschlagenem Scraping oder unbekanntem Ticker.
    """
    global _IBKR_BORROW_CACHE
    if not IBKR_BORROW_ENABLED or not ticker:
        return None
    if _IBKR_BORROW_CACHE is None:
        _IBKR_BORROW_CACHE = _ibkr_borrow_load()
    return _IBKR_BORROW_CACHE.get(ticker.upper())


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


def get_earnings_surprise(ticker: str) -> dict | None:
    """Feature 3 — Letzte gemeldete Earnings: Beat/Miss + %-Abweichung vom Konsens.

    Nutzt ``yfinance.Ticker.earnings_history`` (DataFrame mit Spalten
    ``epsActual`` und ``epsEstimate``). Gibt ``{"beat": bool, "pct": float}``
    zurück oder ``None`` falls keine Daten verfügbar.
    """
    try:
        hist = yf.Ticker(ticker).earnings_history
    except Exception as exc:
        log.debug("earnings_history failed for %s: %s", ticker, exc)
        return None
    if hist is None:
        return None
    try:
        import pandas as _pd
        if not isinstance(hist, _pd.DataFrame) or hist.empty:
            return None
        # Spaltennamen sind case-insensitive; sowohl "epsActual" als auch
        # "Reported EPS" kommen in freier Wildbahn vor
        lower = {c.lower().replace(" ", ""): c for c in hist.columns}
        col_act = lower.get("epsactual") or lower.get("reportedeps") or lower.get("actual")
        col_est = lower.get("epsestimate") or lower.get("estimate") or lower.get("estimateeps")
        if not col_act or not col_est:
            return None
        # jüngste Zeile — yfinance liefert chronologisch sortiert
        hist_sorted = hist.sort_index(ascending=False)
        for _, row in hist_sorted.iterrows():
            actual   = row.get(col_act)
            estimate = row.get(col_est)
            if actual is None or estimate is None:
                continue
            try:
                a, e = float(actual), float(estimate)
            except (TypeError, ValueError):
                continue
            if e == 0:
                continue
            pct = (a - e) / abs(e) * 100
            return {"beat": a >= e, "pct": round(pct, 1)}
    except Exception as exc:
        log.debug("earnings_surprise parse failed for %s: %s", ticker, exc)
    return None


def fetch_stockanalysis_borrow(ticker: str) -> dict:
    """Cost-to-Borrow + Utilization von stockanalysis.com Stock-Page.

    Beide Felder sind **display-only** — fließen nicht in den Score. Wird
    pro Top-10-Ticker einmal gefetcht (kein Cache, weil Werte täglich neu).

    Returns Dict ``{cost_to_borrow: float|None, utilization: float|None}``.
    Fail-soft: HTTP-Fehler / Parse-Fail / deaktiviertes Flag → beide None.
    Niemals raise.
    """
    out = {"cost_to_borrow": None, "utilization": None}
    if not STOCKANALYSIS_BORROW_ENABLED or not ticker or "." in ticker:
        return out
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/short-interest/"
    try:
        # Browser-User-Agent, Stockanalysis blockt sonst hin und wieder.
        headers = {
            **HTTP_HEADERS,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
        }
        resp = requests.get(url, headers=headers, timeout=STOCKANALYSIS_BORROW_TIMEOUT)
        if resp.status_code != 200:
            return out
        text = resp.text
    except Exception as exc:
        log.debug("stockanalysis borrow %s: %s", ticker, exc)
        return out

    # CTB-Parser: tolerant gegen verschiedene Label-Schreibweisen.
    # „Cost to Borrow", „Borrow Fee", „CTB Fee" — gefolgt von %-Wert.
    for pattern in (
        r'(?:Cost\s*to\s*Borrow|Borrow\s*Fee|CTB\s*Fee)[^<]*</t[dh]>\s*<t[dh][^>]*>\s*([\d.]+)\s*%',
        r'"costToBorrow"\s*:\s*([\d.]+)',
        r'"borrowFee"\s*:\s*([\d.]+)',
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                out["cost_to_borrow"] = round(float(m.group(1)), 2)
                break
            except ValueError:
                pass

    # Utilization-Parser
    for pattern in (
        r'(?:Utilization|Utilization\s*Rate|Borrow\s*Utilization)[^<]*</t[dh]>\s*<t[dh][^>]*>\s*([\d.]+)\s*%',
        r'"utilization(?:Rate)?"\s*:\s*([\d.]+)',
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                # JSON-Variante kann 0..1 als Anteil sein; auf Prozent normieren
                if val <= 1.0:
                    val *= 100
                out["utilization"] = round(val, 2)
                break
            except ValueError:
                pass

    return out


def fetch_borrow_metrics(ticker: str) -> dict:
    """Orchestriert CTB + Utilization mit Stockanalysis als Primärquelle.

    Bei fehlendem CTB von Stockanalysis → IBKR-Borrow-Rate-Tabelle als
    Fallback (gleiche Semantik: %/Jahr Leihgebühr). Utilization hat keinen
    IBKR-Fallback — nur Stockanalysis liefert das. Beide Felder können
    unabhängig voneinander None sein.
    """
    metrics = fetch_stockanalysis_borrow(ticker)
    if metrics["cost_to_borrow"] is None:
        ibkr = fetch_ibkr_borrow_rate(ticker)
        if ibkr is not None:
            metrics["cost_to_borrow"] = round(float(ibkr), 2)
    return metrics


def fetch_stockanalysis_si(ticker: str) -> float | None:
    """Fetch wöchentlichen Short-Interest-Prozentwert von stockanalysis.com.

    Nur für US-Ticker sinnvoll (stockanalysis indexiert keine .DE/.L/.HK).
    Parser ist defensiv: akzeptiert Zeilen wie „Short % of Float: X.XX%"
    oder Tabellenfelder gleicher Semantik. Rückgabe None bei HTTP-Fehler,
    ungültigem Parse oder deaktiviertem Flag.
    """
    if not STOCKANALYSIS_SI_ENABLED or "." in ticker:
        return None
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
    except Exception as exc:
        log.debug("stockanalysis %s: %s", ticker, exc)
        return None
    # Primärer Parser: Regex auf „Short % of Float"-Label gefolgt von Prozent-Zahl.
    # Stockanalysis rendert die Zahl in einem <td> direkt nach dem Label-<td>.
    m = re.search(
        r'Short\s*%\s*of\s*Float[^<]*</t[dh]>\s*<t[dh][^>]*>\s*([\d.]+)\s*%',
        resp.text, re.IGNORECASE,
    )
    if m:
        try:
            return round(float(m.group(1)), 2)
        except ValueError:
            return None
    # Fallback: JSON-LD / data-Attribute (manche Seiten encoden Zahlen so)
    m = re.search(r'"shortPercentOfFloat"\s*:\s*([\d.]+)', resp.text)
    if m:
        try:
            return round(float(m.group(1)) * (100 if float(m.group(1)) <= 1 else 1), 2)
        except ValueError:
            return None
    return None


# ── Short-Float / SI-Trend Fallback-Ketten ────────────────────────────────
# Verhindert dass Ticker still wegen fehlender yfinance-Daten ausgefiltert
# werden (Bug 2026-04-26: WOLF, MX, VLN etc. wurden mit short_float=0.0 %
# fälschlich verworfen, obwohl andere Quellen valide Werte hatten).
#
# SF-Kette:    yfinance → screener-Cache → finviz quote.ashx → stockanalysis → none
# Trend-Kette: FINRA    → yfinance sharesShort/PriorMonth-Delta              → none
#
# Source-Tracking pro Ticker via ``short_float_source`` und
# ``si_trend_source`` — beides geht in app_data.json/watchlist_cards ein.

# Akzeptanzschwelle für „brauchbarer" SF-Wert. < 0.5 % = praktisch nicht
# vorhanden, oft fehlerhaft 0.0 statt None. Konsequent in beiden Ketten.
_SF_MIN_VALID = 0.5

# Geteilte Session für die Fallback-Fetcher — Connection-Reuse verhindert
# TCP-Handshake-Overhead bei mehreren Tickern gegen denselben Host.
_FALLBACK_SESSION = requests.Session()
_FALLBACK_SESSION.headers.update(HTTP_HEADERS)


def _fetch_short_float_finviz(ticker: str) -> float | None:
    """Fetcht die Finviz-Quote-Seite und parst „Short Float" %-Wert.

    Nutzt ``screener.ashx``-Tabellen-Layout (Spalten enthalten Label →
    Wert). Defensives Parsing: Tolerant ggü. Whitespace- und
    HTML-Variationen. Skippt Punkt-Ticker (z. B. .DE) — Finviz indexiert
    diese nicht.
    """
    if "." in ticker:
        return None
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    try:
        resp = _FALLBACK_SESSION.get(url, timeout=5)
        if resp.status_code != 200:
            return None
    except requests.RequestException as exc:
        log.debug("finviz quote %s: %s", ticker, exc)
        return None
    text = strip_surrogates(resp.text)
    # Layout 2024+: <td …>Short Float</td><td …>X.XX%</td>
    m = re.search(
        r'>Short Float<[^<]*</td>\s*<td[^>]*>\s*([\d.]+)\s*%',
        text,
    )
    if m:
        try:
            return round(float(m.group(1)), 2)
        except ValueError:
            return None
    return None


def _fetch_short_float_stockanalysis(ticker: str) -> float | None:
    """Dünner Wrapper um ``fetch_stockanalysis_si`` — semantisch identisch,
    aber als Teil der SF-Fallback-Kette benannt. Kein zusätzlicher Call:
    falls der Caller schon im Step-3c3-Pool fetched hat, kann er stattdessen
    diesen Wert direkt übergeben (siehe Aufruf-Site)."""
    return fetch_stockanalysis_si(ticker)


def get_short_float_with_fallback(
    ticker: str,
    yf_value: float | None,
    screener_value: float | None = None,
) -> tuple[float | None, str]:
    """Liefert ``(short_float_pct, source)`` durch eine geordnete Kette.

    Akzeptanzkriterium pro Stufe: Wert ist ``not None`` und ``>= 0.5``.
    Werte unter 0.5 % gelten praktisch immer als „fehlend" (yfinance
    liefert oft 0.0 statt None bei Datenausfall).

    Reihenfolge:
      1. yfinance ``shortPercentOfFloat`` (Standardpfad)
      2. Screener-Cache (Finviz screener-Listing aus Step 1, falls
         der Ticker dort schon mit SF-Wert auftauchte)
      3. Finviz quote.ashx pro Ticker (Live-Fetch)
      4. Stockanalysis.com pro Ticker (Live-Fetch)
      5. ``"none"`` — Caller entscheidet, ob der Ticker geskippt wird.

    Source-Labels: ``"yfinance"``, ``"finviz"``, ``"stockanalysis"``,
    ``"none"``. Stufen 2 und 3 teilen sich „finviz" — beides stammt aus
    Finviz-Quellen und ist für Frontend-Tooltips ununterscheidbar.
    """
    if yf_value is not None and yf_value >= _SF_MIN_VALID:
        return (round(float(yf_value), 2), "yfinance")
    if screener_value is not None and screener_value >= _SF_MIN_VALID:
        return (round(float(screener_value), 2), "finviz")
    fv = _fetch_short_float_finviz(ticker)
    if fv is not None and fv >= _SF_MIN_VALID:
        return (fv, "finviz")
    sa = _fetch_short_float_stockanalysis(ticker)
    if sa is not None and sa >= _SF_MIN_VALID:
        return (sa, "stockanalysis")
    return (None, "none")


def _fetch_si_trend_from_yfinance(ticker: str) -> dict:
    """Berechnet einen groben SI-Trend aus yfinance ``sharesShort`` /
    ``sharesShortPriorMonth`` (1-Monats-Delta).

    Strukturkompatibel zur FINRA-Trend-Ausgabe: liefert ``trend`` ∈
    {"up","down","sideways","no_data"} und ``trend_pct`` (in Prozent).
    Schwellen: ±5 % (gleich der FINRA-Klassifikation).

    Bei fehlendem ``sharesShortPriorMonth`` (None oder 0) → ``no_data``.
    """
    out = {"trend": "no_data", "trend_pct": 0.0}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        log.debug("yfinance SI-Trend %s: %s", ticker, exc)
        return out
    cur   = info.get("sharesShort")
    prior = info.get("sharesShortPriorMonth")
    if not cur or not prior:
        return out
    try:
        cur_f, prior_f = float(cur), float(prior)
    except (TypeError, ValueError):
        return out
    if prior_f <= 0:
        return out
    trend_pct = (cur_f - prior_f) / prior_f * 100.0
    if trend_pct > 5.0:
        out["trend"] = "up"
    elif trend_pct < -5.0:
        out["trend"] = "down"
    else:
        out["trend"] = "sideways"
    out["trend_pct"] = round(trend_pct, 1)
    return out


def fetch_earningswhispers_rss() -> dict[str, dict]:
    """EarningsWhispers RSS — einmal pro Run, liefert {ticker → {date, eps_estimate}}.

    URL: https://www.earningswhispers.com/rss/earningscalendar.asp

    Der Feed enthält ~50 nächste US-Earnings-Termine. Titel-Format ist
    in der Regel „TICKER — DD.MM.YYYY (vor/nach Markt) — Exp. $X.XX".
    Parser ist tolerant gegenüber leichten Formatvarianten.

    Rückgabe: dict ticker → {"date": ISO-String, "eps_estimate": float|None}
    Bei HTTP-Fehler: leeres Dict (Fallback auf yfinance im Consumer).
    """
    if not EARNINGSWHISPERS_ENABLED:
        return {}
    url = "https://www.earningswhispers.com/rss/earningscalendar.asp"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"EarningsWhispers: HTTP {resp.status_code} — übersprungen", flush=True)
            return {}
    except Exception as exc:
        print(f"EarningsWhispers: Fehler {exc} — übersprungen", flush=True)
        return {}
    out: dict[str, dict] = {}
    try:
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = strip_surrogates((item.findtext("title") or "").strip())
            pub   = (item.findtext("pubDate") or "").strip()
            # Ticker: erstes Token bis nicht-Buchstaben
            mt = re.match(r'^([A-Z0-9.\-]{1,12})\b', title)
            if not mt:
                continue
            sym = mt.group(1)
            # EPS-Schätzung: "Exp. $X.XX"
            me = re.search(r'Exp\.\s*\$?\s*([\d.]+)', title)
            eps = float(me.group(1)) if me else None
            # Datum: aus pubDate via email.utils.parsedate_to_datetime (robust)
            date_iso = None
            if pub:
                try:
                    dt = parsedate_to_datetime(pub)
                    date_iso = dt.date().isoformat()
                except Exception:
                    pass
            out[sym] = {"date": date_iso, "eps_estimate": eps}
    except ET.ParseError as exc:
        print(f"EarningsWhispers: Parser-Fehler {exc}", flush=True)
        return {}
    print(f"EarningsWhispers: {len(out)} Termine geladen", flush=True)
    return out


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
# 2b. SUPPLEMENTARY DATA SOURCES (FINRA CSV)
# ===========================================================================

# Mutable counters updated by the API functions during each run
_finra_stats: dict = {"ok": 0, "empty": 0, "err": 0}

# HTTP-request counters for the runtime summary
_req_counts: dict = {"finra": 0, "yahoo": 0, "yfinance": 0}

# Module-level cache: {date_str → {ticker → {"sv": short_vol, "tv": total_vol}}}
# loaded once per run
_finra_csv_cache: dict[str, dict[str, dict[str, int]]] = {}


def _load_finra_csv(date_str: str) -> dict[str, dict[str, int]]:
    """Download and parse FINRA daily short-volume files from CDN.

    Opt 4 — The three exchange files (CNMS, FNSQ, FNQC) for a single date are
    fetched in parallel via ThreadPoolExecutor(max_workers=3) rather than
    sequentially.  Across dates the caller (Step 2a) also parallelises.

    Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
    Returns ``{ticker: {"sv": short_volume, "tv": total_volume}}`` aggregated
    across the three exchange files, or ``{}`` on failure.
    """
    urls = [
        f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNSQshvol{date_str}.txt",
        f"https://cdn.finra.org/equity/regsho/daily/FNQCshvol{date_str}.txt",
    ]

    def _fetch_one(url: str) -> dict[str, dict]:
        """Fetch + parse a single FINRA CDN file; returns partial {ticker: {sv, tv}}."""
        partial: dict[str, dict] = {}
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
            try:
                tv_idx = next(i for i, h in enumerate(header)
                              if "totalvol" in h.replace(" ", ""))
            except StopIteration:
                tv_idx = 4   # Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
            for line in lines[1:]:
                parts = line.split("|")
                if len(parts) <= max(sym_idx, sv_idx, tv_idx):
                    continue
                ticker = parts[sym_idx].strip().upper()
                try:
                    sv_val = int(parts[sv_idx].strip().replace(",", ""))
                except ValueError:
                    continue
                try:
                    tv_val = int(parts[tv_idx].strip().replace(",", ""))
                except ValueError:
                    tv_val = 0
                if ticker and sv_val > 0:
                    entry = partial.setdefault(ticker, {"sv": 0, "tv": 0})
                    entry["sv"] += sv_val
                    entry["tv"] += tv_val
            print(f"FINRA CDN {date_str}: {filename} — {len(partial)} Ticker geladen",
                  flush=True)
        except Exception as exc:
            print(f"FINRA CDN Fehler bei {filename}: {exc}", flush=True)
        return partial

    # Opt 4: fetch all three exchange files for this date in parallel
    merged: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for partial in ex.map(_fetch_one, urls):
            for t, entry in partial.items():
                m = merged.setdefault(t, {"sv": 0, "tv": 0})
                m["sv"] += entry["sv"]
                m["tv"] += entry["tv"]
    return merged


def _get_finra_csv_for_date(date_str: str) -> dict[str, dict]:
    """Return cached CSV data for date_str, loading it if needed.

    Each value is a dict ``{"sv": int, "tv": int}`` — short volume and total
    volume aggregated across all FINRA exchange files for that date.
    """
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
    # Seit 2026-04: SI_TREND_PERIODS=12 → Rückschau bis zu 25 Kalendertage,
    # damit bei 12 Handelstagen + Wochenenden + US-Feiertagen genug Probes
    # gefunden werden (loop bricht nach dem n-ten Treffer ab).
    for delta in range(1, 25):   # start from yesterday (delta=1)
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

        # Letzter Strohhalm: die letzten n Handelstage rechnerisch bestimmen
        # (Wochenenden übersprungen, Feiertage ignoriert). Die einzelnen
        # CSV-Downloads schlagen dann pro Datum fehl, aber der Report bricht
        # nicht mehr komplett ab — andere Kennzahlen werden trotzdem gerendert.
        synth: list[str] = []
        delta_fb = 1
        while len(synth) < n and delta_fb <= 40:
            day_fb = today - timedelta(days=delta_fb)
            if day_fb.weekday() < 5:   # nur Mo–Fr
                synth.append(day_fb.strftime("%Y%m%d"))
            delta_fb += 1
        if synth:
            print(f"FINRA Datumssuche: kein Cache verfügbar — nutze rechnerischen "
                  f"Fallback ({len(synth)} Handelstage ab {today.strftime('%Y-%m-%d')} "
                  f"rückwärts): {synth}", flush=True)
            return synth

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
    # Strenger seit 2026-04: Datenpunkte < 500 Aktien sind zu dünn für
    # einen belastbaren Trend — werden aus der Berechnung ausgeschlossen
    # (bleiben aber im history-Array für T-1/T-2/T-3-Anzeige).
    _TREND_MIN_VOL  = 500      # min short-vol for a meaningful trend data point

    history: list[dict] = []
    for date_str in dates:
        data   = _get_finra_csv_for_date(date_str)
        entry  = data.get(sym) or {}
        si_val = entry.get("sv", 0)
        tv_val = entry.get("tv", 0)
        hit    = sym in data
        print(f"FINRA Ticker-Suche: {sym} [{date_str}] → "
              f"{'Treffer' if hit else 'Kein Treffer'}: {si_val:,}", flush=True)
        if si_val >= _FINRA_MIN_VOL:
            sd = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            history.append({
                "short_interest":   si_val,
                "total_volume":     tv_val,
                "settlement_date":  sd,
            })

    if not history:
        _finra_stats["empty"] += 1
        return {}

    # Nur Datenpunkte ≥ _TREND_MIN_VOL (500) fließen in den Trend ein.
    # Gleitender 3er-Durchschnitt auf beiden Enden (seit 2026-04) —
    # ein einzelner Ausreißer-Tag verschiebt den Trend nicht mehr.
    # Output-Cap: [-90 %, +150 %]; alles darüber ist fast immer Datenfehler.
    # Mindestens SI_TREND_MIN_DATAPOINTS (6) signifikante Punkte nötig;
    # weniger → „no_data" statt instabiler 2-Punkte-Berechnung.
    trend, trend_pct = "no_data", 0.0
    significant = [p for p in history if p["short_interest"] >= _TREND_MIN_VOL]
    if len(significant) >= SI_TREND_MIN_DATAPOINTS:
        avg_new = sum(p["short_interest"] for p in significant[:3]) / 3
        avg_old = sum(p["short_interest"] for p in significant[-3:]) / 3
        raw_pct = (avg_new - avg_old) / avg_old if avg_old > 0 else 0.0
        if raw_pct >= SI_TREND_UP_THRESHOLD:
            trend = "up"
        elif raw_pct <= SI_TREND_DOWN_THRESHOLD:
            trend = "down"
        else:
            trend = "sideways"
        trend_pct = max(-0.90, min(1.50, raw_pct))
        if _finra_stats.get("ok", 0) < 5:
            print(f"{sym} FINRA trend (3-vs-3 avg, n={len(significant)}): "
                  f"avg_old={avg_old:,.0f}, avg_new={avg_new:,.0f}, "
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

    # Daily Short Sale Ratio aus dem jüngsten Datenpunkt (Feature 1)
    ssr_today: float | None = None
    if history:
        _tv = history[0].get("total_volume", 0)
        _sv = history[0]["short_interest"]
        if _tv > 0:
            ssr_today = round(_sv / _tv, 4)
            print(f"FINRA SSR {sym}: sv={_sv:,}  tv={_tv:,}  → {ssr_today*100:.1f}%",
                  flush=True)
        else:
            # Explizit loggen wenn Total-Volume fehlt — hilft bei Diagnose,
            # ob FINRA-CSV die TotalVolume-Spalte tatsächlich liefert.
            print(f"FINRA SSR {sym}: sv={_sv:,}  tv=0 → SSR nicht berechnet",
                  flush=True)

    _finra_stats["ok"] += 1
    log.info("%s FINRA history=%d Punkte, trend=%s, velocity=%.0f/day, accel=%s, ssr=%s",
             sym, len(history), trend, si_velocity, si_accelerating,
             f"{ssr_today*100:.1f}%" if ssr_today is not None else "—")
    return {
        "short_interest":      history[0]["short_interest"],
        "prev_short_interest": history[1]["short_interest"] if len(history) >= 2 else 0,
        "settlement_date":     history[0]["settlement_date"],
        "history":             history,
        "trend":               trend,
        "trend_pct":           round(trend_pct * 100, 1),
        "si_velocity":         round(si_velocity, 0),
        "si_accelerating":     si_accelerating,
        "ssr_today":           ssr_today,
    }


def score_bonus(stock: dict) -> float:
    """Optional bonus points (0 – FINRA_BONUS_MAX).
    FINRA: up to 5 pts if daily short volume rose.
    Condition: ≥ 2 of the 3 FINRA data points must be > 100 shares.
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


_WL_CARD_STRIP_RE = {
    "article_open":  re.compile(r'^\s*<article\b[^>]*>'),
    "article_close": re.compile(r'</article>\s*$'),
    "rank":          re.compile(r'<span class="rank(?:[^"]*)"[^>]*>[^<]*</span>'),
    "wl_add_btn":    re.compile(r'<button class="wl-add-btn"[^>]*>[^<]*</button>'),
    "stale_ids":     re.compile(
        r' id="(?:c|dd|db|da|dl|nb|nb-icon|np|ka-btn|ka-res)\d+"'
    ),
    "details_onclick": re.compile(r'onclick="toggleDetails\(\d+\)"'),
    "news_onclick":    re.compile(r'onclick="toggleNews\(\d+\)"'),
    "ki_onclick":      re.compile(r'onclick="runKiAnalyse\(\d+\)"'),
}


def _wl_full_card_html(s: dict) -> str:
    """Vorgerendertes TopTen-Karten-HTML für die Watchlist-Drawer-Open-Ansicht.

    Ruft ``_card(0, s)`` und entfernt:
    - ``<article>``-Wrapper (``.wl-card`` ist die Watchlist-Hülle)
    - Rank-Badge (im Watchlist-Kontext redundant)
    - ``wl-add-btn`` (Ticker ist per Definition in der Watchlist)

    ``.details-body`` und ``.news-panel`` bleiben **wie in der TopTen-
    Karte** zugeklappt (kein ``open``, ``hidden`` bleibt) — die Toggle-
    Buttons ``.details-btn`` und ``.news-btn`` bleiben sichtbar und
    werden auf ID-freie ``wlToggleDetails(this)`` / ``wlToggleNews(this)``
    umgeleitet (Selektor-relativ via ``closest('.wl-card')``). Verbleibende
    ``id="…N"``-Attribute werden gestrippt, damit Top-10-Handler keine
    Watchlist-Elemente per ``getElementById`` finden. Der KI-Analyse-Klick
    geht weiterhin auf ``wlOpenKiAnalyse(ticker)``.

    Bei Render-Fehler (z. B. fehlende Felder bei nicht-Top-10-Watchlist-
    Tickern) leerer String — JS fällt dann auf ``buildWlSparkOnly``.
    """
    try:
        raw = _card(0, s)
    except Exception:
        return ""
    raw = _WL_CARD_STRIP_RE["article_open"].sub("", raw, count=1)
    raw = _WL_CARD_STRIP_RE["article_close"].sub("", raw, count=1)
    raw = _WL_CARD_STRIP_RE["rank"].sub("", raw, count=1)
    raw = _WL_CARD_STRIP_RE["wl_add_btn"].sub("", raw, count=1)
    raw = _WL_CARD_STRIP_RE["stale_ids"].sub("", raw)
    raw = _WL_CARD_STRIP_RE["details_onclick"].sub(
        'onclick="wlToggleDetails(this)"', raw, count=1
    )
    raw = _WL_CARD_STRIP_RE["news_onclick"].sub(
        'onclick="wlToggleNews(this)"', raw, count=1
    )
    raw = _WL_CARD_STRIP_RE["ki_onclick"].sub(
        f'onclick="wlOpenKiAnalyse(\'{s["ticker"]}\')"', raw, count=1
    )
    return raw.strip()


def _wl_card_payload(_s: dict) -> dict:
    """Baut das Watchlist-Karten-Payload aus einem angereicherten Stock-Dict.

    Identisch zum in-page WL_TOP10-Format und zum app_data.watchlist_cards-
    Eintrag — eine Quelle für beide Konsumenten, damit Browser und Backend
    nicht auseinanderdriften.

    ``card_html`` ist das vorgerenderte TopTen-Layout für den Drawer-
    Open-State (siehe ``_wl_full_card_html``); die übrigen Felder bleiben
    für das kompakte WL-Tile + KI-Dot + Tooltips.
    """
    _fd   = _s.get("finra_data") or {}
    _hist = _fd.get("history", [])
    _opts = _s.get("options") or {}
    _spark = _s.get("sparkline") or None
    return {
        "score":         _s.get("score", 0),
        "monster_score": _s.get("monster_score"),
        "ki_signal_score":      _s.get("ki_signal_score"),
        "ki_signal_confidence": _s.get("ki_signal_confidence"),
        "ki_signal_drivers":    _s.get("ki_signal_drivers"),
        "company_name":  _s.get("company_name", ""),
        "sector":        _s.get("sector", ""),
        "flag":          get_flag(_s["ticker"]),
        "price":         _s.get("price", 0),
        "change":        _s.get("change", 0),
        "change_5d":     _s.get("change_5d"),
        "spx_daily_perf": _s.get("spx_daily_perf"),
        "short_float":         _s.get("short_float", 0),
        "short_float_source":  _s.get("short_float_source", "yfinance"),
        "short_ratio":   _s.get("short_ratio", 0),
        "rel_volume":    _s.get("rel_volume", 0),
        "rel_volume_yesterday": _s.get("rel_volume_yesterday"),
        "float_shares":  _s.get("float_shares") or 0,
        "si_trend":          _fd.get("trend", "no_data"),
        "si_trend_source":   _fd.get("si_trend_source", "finra"),
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
        "sec_13f_note":  _s.get("sec_13f_note"),
        "52w_high":      _s.get("52w_high") or 0,
        "52w_low":       _s.get("52w_low") or 0,
        "avg_vol_20d":   _s.get("avg_vol_20d", 0),
        "cur_vol":       _s.get("cur_vol", 0),
        "cur_open":      _s.get("cur_open"),
        "prev_close":    _s.get("prev_close"),
        "market_cap":    _s.get("yf_market_cap") or _s.get("market_cap") or 0,
        "earnings_days": _s.get("earnings_days"),
        "earnings_date_str": _s.get("earnings_date_str", ""),
        "pc_ratio":      _opts.get("pc_ratio"),
        "atm_iv":        _opts.get("atm_iv"),
        "options_expiry":         _opts.get("expiry"),
        "options_gamma_call_oi":  _opts.get("gamma_call_oi"),
        "rel_strength_20d": _s.get("rel_strength_20d"),
        "perf_20d":      _s.get("perf_20d"),
        "cost_to_borrow": _s.get("cost_to_borrow"),
        "utilization":    _s.get("utilization"),
        "borrow_rate":    _s.get("borrow_rate"),
        "sparkline":     ({
            "scores": _spark.get("scores", []),
            "dates":  _spark.get("dates", []),
            "trend":  _spark.get("trend", ""),
            "col":    _spark.get("col", "#94a3b8"),
            "today":  _spark.get("today", ""),
        } if _spark else None),
        "news": [
            {
                "title":  n.get("title", ""),
                "link":   n.get("link", "#"),
                "time":   n.get("time", ""),
                "source": n.get("source") or n.get("publisher", ""),
                "ts":     n.get("ts"),
            }
            for n in _s.get("news", [])[:3]
        ],
        # Vorgerendertes TopTen-Layout für den expandierten Drawer-State.
        # Siehe ``_wl_full_card_html`` — Outer-``<article>``, Rank, Add-Button
        # und Toggle-Buttons sind gestrippt; details-body + news-panel sind
        # vor-geöffnet; KI-Analyse-Onclick zeigt auf ``wlOpenKiAnalyse``.
        "card_html":     _wl_full_card_html(_s),
    }


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


def _news_age_weight(news_item: dict, now_ts: float | None = None) -> float:
    """Liefert das Alters-Gewicht für ein News-Item via NEWS_DECAY_WEIGHTS.

    Liest ``news_item.ts`` (Epoch-Sekunden, von ``_rss_news`` gesetzt) und
    rechnet in Tages-Alter um (``floor((now − ts) / 86400)``).

    - Tag im Mapping → entsprechendes Gewicht
    - Älter als max. Stufe → 0.0 (Item effektiv ignoriert)
    - ``ts`` fehlt / ≤ 0 / nicht parsebar → ``NEWS_DECAY_FALLBACK`` (0.5)
    - Negative Alter (Item aus der Zukunft, Clock-Drift) → 1.0
    """
    raw = news_item.get("ts") if isinstance(news_item, dict) else None
    try:
        ts = float(raw or 0)
    except (TypeError, ValueError):
        return NEWS_DECAY_FALLBACK
    if ts <= 0:
        return NEWS_DECAY_FALLBACK
    if now_ts is None:
        now_ts = time.time()
    age_days = int((now_ts - ts) // 86400)
    if age_days < 0:
        return 1.0
    if age_days in NEWS_DECAY_WEIGHTS:
        return NEWS_DECAY_WEIGHTS[age_days]
    max_age = max(NEWS_DECAY_WEIGHTS.keys())
    if age_days > max_age:
        return 0.0
    # age_days liegt im Bereich, aber nicht als Schlüssel definiert (z.B.
    # ein Mapping mit Lücken) → nächstkleinere Stufe verwenden.
    candidates = [d for d in NEWS_DECAY_WEIGHTS.keys() if d <= age_days]
    return NEWS_DECAY_WEIGHTS[max(candidates)] if candidates else NEWS_DECAY_FALLBACK


def _float_turnover_row_html(stock: dict) -> str:
    """Detail-Zeile „Float Turnover: X.XX× (+N Pkt)" für Volumen-Sektion.

    Leerer String wenn Float-Daten fehlen (kein Wert angezeigt). Farb-
    codierung der Punkte über den Standard-`color`-Wert.
    """
    ratio, pts = _float_turnover_pts(stock)
    if (stock.get("float_shares") or 0) <= 0 or (stock.get("cur_vol") or 0) <= 0:
        return ""
    if pts >= FLOAT_TURNOVER_PTS_HIGH:
        col = "#22c55e"
    elif pts >= FLOAT_TURNOVER_PTS_MID:
        col = "#f59e0b"
    elif pts >= FLOAT_TURNOVER_PTS_LOW:
        col = "#94a3b8"
    else:
        col = "var(--txt-dim)"
    pts_str = f"+{int(pts)} Pkt" if pts > 0 else "0 Pkt"
    return (
        f'<tr><td>Float Turnover</td>'
        f'<td><span style="color:{col}">{ratio:.2f}× '
        f'<span style="color:var(--txt-dim);font-size:.85em">({pts_str})</span>'
        f'</span></td></tr>'
    )


def _gap_hold_pts(stock: dict) -> tuple[float | None, str, float]:
    """Misst Gap-Up + EOD-Hold (Eröffnungs-Stärke und Tagesverlauf).

    Returns ``(gap_pct, state, pts)``:
      • ``state="strong_hold"`` (+GAP_PTS_STRONG_HOLD): close > open + GAP_HOLD_FACTOR × gap_size
      • ``state="weak_hold"``   (+GAP_PTS_WEAK_HOLD):   close zwischen yesterday_close und hold_threshold
      • ``state="fail"``        (GAP_PTS_FAIL):         close < yesterday_close (Bull-Trap)
      • ``state="no_gap"``      (0):                    gap_pct < GAP_THRESHOLD_PCT
      • ``state="unknown"``     (0):                    Daten fehlen (cur_open/prev_close/price)
    """
    cur_open   = stock.get("cur_open")
    prev_close = stock.get("prev_close")
    price      = stock.get("price")
    if cur_open is None or prev_close is None or price is None or prev_close <= 0:
        return None, "unknown", 0.0
    try:
        cur_open   = float(cur_open)
        prev_close = float(prev_close)
        price      = float(price)
    except (TypeError, ValueError):
        return None, "unknown", 0.0
    gap_size = cur_open - prev_close
    gap_pct  = gap_size / prev_close * 100.0
    if gap_pct < GAP_THRESHOLD_PCT:
        return gap_pct, "no_gap", 0.0
    hold_threshold = cur_open + GAP_HOLD_FACTOR * gap_size
    if price > hold_threshold:
        return gap_pct, "strong_hold", float(GAP_PTS_STRONG_HOLD)
    if price < prev_close:
        return gap_pct, "fail", float(GAP_PTS_FAIL)
    # zwischen prev_close und hold_threshold (inklusive grenznah über open)
    return gap_pct, "weak_hold", float(GAP_PTS_WEAK_HOLD)


def _rs_spy_pts(stock: dict) -> tuple[float | None, float]:
    """Lineare Relative-Stärke vs. SPY (basiert auf 20T-Differenz).

    Eingabe: ``stock["rel_strength_20d"]`` = stock_perf_20d − ^GSPC_perf_20d
    (in Prozentpunkten, bereits in Step 3 berechnet). Skaliert symmetrisch:

      pts = round(clamp(rs / RS_SPY_THRESHOLD_PCT, −1, +1) × RS_SPY_PTS_MAX)

    Returns ``(rs_pct, pts)``. Bei fehlendem Wert → ``(None, 0)``.
    """
    rs = stock.get("rel_strength_20d")
    if rs is None:
        return None, 0.0
    try:
        rs = float(rs)
    except (TypeError, ValueError):
        return None, 0.0
    clamped = max(-RS_SPY_THRESHOLD_PCT, min(RS_SPY_THRESHOLD_PCT, rs))
    pts = round(clamped / RS_SPY_THRESHOLD_PCT * RS_SPY_PTS_MAX)
    return rs, float(pts)


def _gap_hold_row_html(stock: dict) -> str:
    """Detail-Zeile „Gap & Hold: +X.X% Open, [State] (±N Pkt)"."""
    gap_pct, state, pts = _gap_hold_pts(stock)
    if state == "unknown":
        return ""
    label_map = {
        "strong_hold": ("Strong Hold",  "#22c55e"),
        "weak_hold":   ("Weak Hold",    "#f59e0b"),
        "fail":        ("Fail",         "#ef4444"),
        "no_gap":      ("kein Gap",     "var(--txt-dim)"),
    }
    label, col = label_map.get(state, ("—", "var(--txt-dim)"))
    if gap_pct is None:
        gap_str = "—"
    else:
        gap_str = f"{gap_pct:+.1f}%"
    pts_str = f"{int(pts):+d} Pkt" if pts != 0 else "0 Pkt"
    return (
        f'<tr><td>Gap &amp; Hold</td>'
        f'<td><span style="color:{col}">{gap_str} Open · {label} '
        f'<span style="color:var(--txt-dim);font-size:.85em">({pts_str})</span>'
        f'</span></td></tr>'
    )


def _rs_spy_row_html(stock: dict) -> str:
    """Detail-Zeile „RS vs. SPY: ±X.X% (+N Pkt)"."""
    rs_pct, pts = _rs_spy_pts(stock)
    if rs_pct is None:
        return ""
    if pts > 0:
        col = "#22c55e"
    elif pts < 0:
        col = "#ef4444"
    else:
        col = "var(--txt-dim)"
    pts_str = f"{int(pts):+d} Pkt" if pts != 0 else "0 Pkt"
    return (
        f'<tr><td>RS vs. SPY (20T)</td>'
        f'<td><span style="color:{col}">{rs_pct:+.1f}% '
        f'<span style="color:var(--txt-dim);font-size:.85em">({pts_str})</span>'
        f'</span></td></tr>'
    )


def _float_turnover_pts(stock: dict) -> tuple[float, float]:
    """Float-Turnover = today_volume / float_shares.

    Misst, welcher Bruchteil des Floats heute gehandelt wurde — komplementär
    zu RVOL. Punkte: 0 / 3 / 6 / 10 bei Schwellen 0.5 / 1.0 / 2.0.

    Returns ``(ratio, pts)``. Bei fehlendem Float oder Volumen → ``(0, 0)``
    (graceful Fallback, kein Score-Beitrag).
    """
    fl  = stock.get("float_shares") or 0
    vol = stock.get("cur_vol") or 0
    if fl <= 0 or vol <= 0:
        return 0.0, 0.0
    ratio = float(vol) / float(fl)
    if ratio >= FLOAT_TURNOVER_HIGH:
        return ratio, float(FLOAT_TURNOVER_PTS_HIGH)
    if ratio >= FLOAT_TURNOVER_MID:
        return ratio, float(FLOAT_TURNOVER_PTS_MID)
    if ratio >= FLOAT_TURNOVER_LOW:
        return ratio, float(FLOAT_TURNOVER_PTS_LOW)
    return ratio, 0.0


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

    # Float-Turnover (Vol/Float) — komplementäres Volumen-Signal zu RVOL.
    _, turnover_pts = _float_turnover_pts(stock)
    # Gap & Hold (EOD-Stärke des Eröffnungs-Gaps)
    _, _gap_state, gap_pts = _gap_hold_pts(stock)
    # Relative Stärke vs. SPY (ersetzt RS-vs-Sektor)
    _, rs_spy_pts = _rs_spy_pts(stock)

    if sf_val == 0 and sr_val == 0:
        # Fall 2: keine Short-Daten → Volumen (max 30) + Momentum (max 20)
        #   + Float Turnover (max 10) + Gap+Hold (-3..+5) + RS-vs-SPY (±3)
        #   + Float-Size, Cap 50.
        # Nur positive Tagesveränderungen zählen: fallende Kurse = kein Squeeze-Druck
        rv_component = rv_raw * 30
        chg = max(adjusted_chg, 0)
        momentum = min(chg /  8.0, 1.0) * 20  # sättigt bei +8% statt +15%
        result = min(round(
            rv_component + momentum + _fs + turnover_pts + gap_pts + rs_spy_pts, 2
        ), 50.0)
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

    # Historischer Squeeze-Malus: falls ein Squeeze in den letzten 30 / 90 Tagen
    # erkannt wurde, ist das verbleibende Potenzial eingeschränkt.
    _sq = stock.get("recent_squeeze") or {}
    _sq_malus = 0.0
    if _sq.get("found"):
        _days = _sq.get("days_ago", 999)
        if _days <= 30:
            _sq_malus = float(SQUEEZE_HIST_MALUS_30D)
        elif _days <= 90:
            _sq_malus = float(SQUEEZE_HIST_MALUS_90D)
        if _sq_malus > 0:
            print(f"{stock.get('ticker', '?')} Squeeze-Malus: -{_sq_malus:.0f} Pkt "
                  f"(Squeeze vor {_days} Tagen)", flush=True)

    result = round(max(0.0, min(
        sf + sr + rv + mom + _fs + _pts + turnover_pts + gap_pts + rs_spy_pts - _sq_malus,
        100.0
    )), 2)
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

    Entries older than SCORE_HISTORY_DAYS (14) are dropped on load so
    _save_score_history() only serialises what is still needed — no second pass.
    """
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=SCORE_HISTORY_DAYS)).strftime("%d.%m.%Y")
    try:
        with open(SCORE_HISTORY_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    # Kompatibel zu altem UND neuem (komprimierten) Format:
    #   alt:  [{"date": "...", "score": …}, ...]
    #   neu:  [["...", …], ...]              ← Tuple/List-Einträge, spart ~45 %
    # Normalisiert zurück zum internen Dict-Format (Rest des Codes erwartet dict).
    def _normalize(entry):
        if isinstance(entry, dict):
            return entry
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            return {"date": entry[0], "score": entry[1]}
        return None

    pruned: dict[str, list[dict]] = {}
    for ticker, entries in raw.items():
        normalised = [_normalize(e) for e in entries]
        kept = [e for e in normalised if e and e.get("date", "") >= cutoff]
        if kept:
            pruned[ticker] = kept
    return pruned


def _save_score_history(history: dict, _dirty: bool = True) -> None:
    """Komprimiertes Format auf Disk: {ticker: [[date, score], ...]}.

    Abwärtskompatibel via _load_score_history (akzeptiert beide Formate).
    Zusätzlich Cutoff-Pruning beim Schreiben (defense-in-depth neben der
    Load-Time-Prune), damit die Datei monoton klein bleibt.
    """
    if not _dirty:
        return
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=SCORE_HISTORY_DAYS)).strftime("%d.%m.%Y")
    compact: dict[str, list] = {}
    for ticker, entries in history.items():
        rows: list[list] = []
        for e in entries:
            if isinstance(e, dict):
                d, sc = e.get("date", ""), e.get("score")
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                d, sc = e[0], e[1]
            else:
                continue
            if d and sc is not None and d >= cutoff:
                rows.append([d, sc])
        if rows:
            compact[ticker] = rows
    with open(SCORE_HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(compact, fh, indent=2)


def apply_agent_boost(stocks: list[dict]) -> None:
    """Feature 2 — KI-Agent-Multiplikator auf den Tages-Score.

    Liest agent_signals.json, matcht per Ticker, wendet bei hinreichend
    aktuellem (≤ AGENT_BOOST_MAX_AGE_H Stunden) und ausreichendem
    (≥ 25) Agent-Score einen Multiplikator an:
        25-49 → ×1.05    50-74 → ×1.10    ≥75 → ×1.15
    Cap bei 100 bleibt. Setzt s["agent_boost_pts"] + s["agent_boost_score"]
    auf jedem Stock mit Boost für spätere Anzeige in der Detail-Tabelle.
    """
    if not AGENT_BOOST_ENABLED:
        return
    try:
        with open("agent_signals.json", "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    signals = data.get("signals") or {}
    if not signals:
        return

    # KI-Signal-Score für die Card-Anzeige auf jeden Stock mit Signal-Eintrag
    # exposen — unabhängig von Alter und Boost-Threshold. Anzeige selbst ist
    # fail-soft (Badge nur wenn Wert vorhanden).
    for s in stocks:
        sig = signals.get(s["ticker"])
        if not sig:
            continue
        try:
            s["ki_signal_score"] = float(sig.get("score", 0))
        except (TypeError, ValueError):
            pass

    updated = data.get("updated")
    if not updated:
        return
    try:
        upd_dt = datetime.fromisoformat(updated)
    except ValueError:
        return
    age_h = (datetime.now(upd_dt.tzinfo) - upd_dt).total_seconds() / 3600
    if age_h > AGENT_BOOST_MAX_AGE_H:
        log.info("Agent-Boost übersprungen: Signal %.1fh alt (> %dh)",
                 age_h, AGENT_BOOST_MAX_AGE_H)
        return
    for s in stocks:
        sig = signals.get(s["ticker"])
        if not sig:
            continue
        ag_score = _safe_float(sig.get("score", 0))
        if ag_score < 25:
            continue
        factor = 1.15 if ag_score >= 75 else 1.10 if ag_score >= 50 else 1.05
        base = _safe_float(s.get("score", 0))
        new  = min(round(base * factor, 2), 100.0)
        boost = round(new - base, 2)
        if boost <= 0:
            continue
        s["score"] = new
        s["agent_boost_pts"]    = boost
        s["agent_boost_score"]  = ag_score
        s["agent_boost_factor"] = factor
        log.info("  Agent-Boost %s: base=%.2f × %.2f → %.2f (+%.2f, KI-Score %.0f)",
                 s["ticker"], base, factor, new, boost, ag_score)


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
        # Pre-smoothing Wert für backtest_history.score_raw aufheben.
        s["score_raw"] = today_raw
        s["score_trend_bonus_pts"] = 0.0  # default; wird unten gesetzt falls aktiv

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
                s["score_trend_bonus_pts"] = float(SCORE_TREND_BONUS)
            elif all(_tscores[i] > _tscores[i + 1] for i in range(len(_tscores) - 1)):
                s["score"] = round(max(s["score"] - SCORE_TREND_MALUS, 0.0), 1)
                s["score_trend_bonus_pts"] = -float(SCORE_TREND_MALUS)

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
             f"saved to {SCORE_HISTORY_FILE}" if _dirty else "unchanged (skip write)")


def apply_monster_score(stocks: list[dict]) -> None:
    """Berechnet Monster-Score pro Stock = Setup-Score gewichtet mit KI-Signal.

    Voraussetzung: ``apply_agent_boost`` lief bereits (setzt
    ``s["ki_signal_score"]``). Logik:

      kein KI-Signal  → monster = setup (unverändert)
      KI ≥ 60         → monster = min(100, round(setup × 1.20))    (Boost)
      KI < 25         → monster = round(setup × 0.80)              (Malus)
      sonst (25-59)   → monster = setup                            (neutral)

    Setzt ``s["monster_score"]`` (float) auf jedem Stock.
    """
    for s in stocks:
        base = _safe_float(s.get("score", 0))
        ki   = s.get("ki_signal_score")
        if ki is None:
            monster = base
        elif ki >= 60:
            monster = min(100.0, float(round(base * 1.20)))
        elif ki < 25:
            monster = float(round(base * 0.80))
        else:
            monster = base
        s["monster_score"] = monster


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


# ═══════════════════════════════════════════════════════════════════════════
#  Shared HTML-Snippet-Helfer — werden von ``_card`` (v1) UND
#  ``_build_card_ctx`` (v2) aufgerufen, damit beide Pfade byte-identisch
#  bleiben (Phase-3d-Render-Test).
# ═══════════════════════════════════════════════════════════════════════════

def _ssr_tile_html(s: dict) -> str:
    """Daily-Short-Sale-Ratio-Kachel (Feature 1). Leer wenn abgeschaltet."""
    if not SHOW_DAILY_SSR:
        return ""
    ssr = (s.get("finra_data") or {}).get("ssr_today")
    if ssr is None:
        display, col = "—", "#94a3b8"
    else:
        pct = ssr * 100
        display = f"{pct:.0f}%"
        if ssr < SSR_RED_THRESHOLD:
            col = "#ef4444"
        elif ssr > SSR_GREEN_THRESHOLD:
            col = "#22c55e"
        else:
            col = "#f59e0b"
    return (
        f'<div class="metric-box" style="--mc:{col}">'
        f'<span class="m-val">{display}</span>'
        f'<span class="m-lbl">SSR Heute</span>'
        f'</div>'
    )


def _float_display(s: dict) -> tuple[str, str, str, bool]:
    """Feature 2 — Plausibilitäts-Check + MCap-basierte Schätzung für Float.

    Rückgabe: ``(tile_val, detail_str, color, is_estimated)``
    * tile_val   — kompakt (z.B. "25,0 Mio." oder "—")
    * detail_str — für die Detail-Tabelle (z.B. "25,0 Mio. Aktien (geschätzt)")
    * color      — Kacheln-Farbe
    * is_estimated — True wenn der Wert aus market_cap / price geschätzt wurde
    """
    raw = s.get("float_shares") or 0
    price = s.get("price") or 0
    cap   = s.get("yf_market_cap") or s.get("market_cap") or 0
    estimated = False
    if FLOAT_MIN_VALID <= raw <= FLOAT_MAX_VALID:
        shares = raw
    elif raw == 0 and cap and price and price > 0:
        shares = int(cap / price)
        if not (FLOAT_MIN_VALID <= shares <= FLOAT_MAX_VALID):
            shares = 0
        else:
            estimated = True
    else:
        shares = 0

    if shares <= 0:
        return "—", "", "#94a3b8", False
    mio = shares / 1_000_000
    tile = f"{mio:.1f} Mio.".replace(".", ",")
    if estimated:
        tile += " (gesch.)"
    if shares < FLOAT_SATURATION_LOW:
        col = "#22c55e"
    elif shares <= FLOAT_SATURATION_HIGH:
        col = "#f59e0b"
    else:
        col = "#ef4444"
    suffix = " (geschätzt)" if estimated else ""
    detail = f"{mio:.1f} Mio. Aktien{suffix}"
    return tile, detail, col, estimated


def _earnings_surprise_html(s: dict) -> str:
    """Feature 3 — Letztes Earnings Beat/Miss als Detail-Tabellenzeile."""
    if not SHOW_EARNINGS_SURPRISE:
        return ""
    sp = s.get("earnings_surprise")
    if sp is None:
        return ""
    pct = sp.get("pct")
    beat = sp.get("beat")
    if pct is None:
        return ""
    if beat:
        icon, col = "\u2705", "#22c55e"
        sign_txt = f"Beat +{pct:.0f}%" if pct >= 0 else f"Beat {pct:.0f}%"
    else:
        icon, col = "\u274C", "#ef4444"
        sign_txt = f"Miss {pct:+.0f}%"
    return (
        f'<tr><td>Letztes Earnings</td>'
        f'<td><span style="color:{col}">{icon} {sign_txt}</span></td></tr>'
    )


def _sector_rs_row(s: dict) -> str:
    """Feature 5 — RS vs. Sektor-ETF als Detail-Tabellenzeile."""
    if not USE_SECTOR_RS:
        return ""
    rs = s.get("rel_strength_sector")
    if rs is None:
        return ""
    etf = s.get("sector_etf") or SECTOR_ETF_DEFAULT
    col = "#22c55e" if rs >= 0 else "#ef4444"
    return (
        f'<tr><td>RS vs. Sektor ({etf})</td>'
        f'<td><span style="color:{col}">{rs:+.1f}%</span></td></tr>'
    )


def _squeeze_history_badge(s: dict) -> str:
    """Feature 6 — '⚠️ Squeeze vor X Tagen'-Badge auf der Karte."""
    sq = s.get("recent_squeeze")
    if not sq or not sq.get("found"):
        return ""
    days = sq.get("days_ago", 0)
    return (
        f'<span class="squeeze-hist-badge" '
        f'title="Kursanstieg ≥ {SQUEEZE_MIN_GAIN*100:.0f}% in 5 Tagen '
        f'bei Volumen ≥ {SQUEEZE_MIN_RVOL:.0f}× vor {days} Tagen">'
        f'\u26A0\ufe0f Squeeze vor {days} Tagen</span>'
    )


def _compute_sub_scores(s: dict) -> dict:
    """Feature 1 — drei Sub-Scores (Struktur / Katalysator / Timing).

    Rein informative Aufspaltung: ``score()`` bleibt autoritativ für den
    Gesamt-Score. Die drei Werte hier sind unabhängige Themen-Metriken
    für die Karten-Anzeige.
    """
    sf = _safe_float(s.get("short_float", 0))
    sr = _safe_float(s.get("short_ratio", 0))
    rv = _safe_float(s.get("rel_volume", 0))
    chg = _safe_float(s.get("change", 0))
    if USE_RELATIVE_MOMENTUM:
        chg -= _safe_float(s.get("spx_daily_perf", 0.0))
    chg = max(chg, 0)
    fl  = s.get("float_shares") or 0
    finra = s.get("finra_data") or {}
    si_trend = finra.get("trend", "no_data")

    # Struktur (max 40) = SF + DTC + SI-Trend + Float-Größe, normiert 68 -> 40
    sf_pts  = min(sf / 50.0, 1.0) * 32
    dtc_pts = min(sr / 10.0, 1.0) * 23
    if fl > 0:
        fs_pts = max(0.0, min(1.0,
            (FLOAT_SATURATION_HIGH - fl) / (FLOAT_SATURATION_HIGH - FLOAT_SATURATION_LOW)
        )) * 8
    else:
        fs_pts = 0.0
    si_pts = {"up": 5, "sideways": 2.5, "down": 0, "no_data": 0}.get(si_trend, 0)
    struct_pts = round((sf_pts + dtc_pts + fs_pts + si_pts) * (SUB_STRUCT_MAX / 68.0), 1)

    # Katalysator (max 35) = Earnings + Insider + News-Keywords
    earn_days = s.get("earnings_days")
    earn_pts = 15 if (earn_days is not None and earn_days <= 7) \
           else 8  if (earn_days is not None and earn_days <= 14) \
           else 0
    insider_pts = 10 if s.get("sec_13f_note") else 0
    # News-Score mit Alters-Gewichtung: ältere Headlines scoren weniger als
    # frische. Gewichte aus NEWS_DECAY_WEIGHTS (T+0=1.0, T+3=0.2, älter=0.0).
    # Ohne ``ts`` → NEWS_DECAY_FALLBACK (0.5). Cap 10 wie zuvor.
    news_pts = 0.0
    _kw = ("squeeze", "catalyst", "beat", "fda", "merger",
           "activist", "halt", "short covering")
    _now_ts = time.time()
    for n in (s.get("news") or [])[:5]:
        title = (n.get("title") or n.get("title_orig") or "").lower()
        if any(kw in title for kw in _kw):
            weight = _news_age_weight(n, now_ts=_now_ts)
            news_pts = min(news_pts + 5 * weight, 10.0)
    news_pts = round(news_pts, 1)
    pressure_pts = SHORT_PRESSURE_BONUS if _detect_short_pressure(s) else 0
    _gamma_lvl = _gamma_squeeze_level(s)
    gamma_pts  = (GAMMA_BONUS_LIKELY   if _gamma_lvl == "likely"
                  else GAMMA_BONUS_POSSIBLE if _gamma_lvl == "possible"
                  else 0)
    # IBKR-Borrow-Rate: > 100 %/Jahr → extremer Short-Druck; > 50 % → teuer
    _borrow = s.get("borrow_rate")
    borrow_pts = 0
    if _borrow is not None:
        if _borrow > 100:
            borrow_pts = IBKR_BORROW_BONUS_EXTREME
        elif _borrow > IBKR_BORROW_HIGH:
            borrow_pts = IBKR_BORROW_BONUS_HOT
    # Put/Call-Ratio: bullisches Options-Sentiment (< 0.5) → +Bonus;
    # bearisches (> 1.5) → -Malus. Nur wenn Options-Daten vorhanden.
    pc_pts = 0
    _pc = (s.get("options") or {}).get("pc_ratio")
    if _pc is not None:
        if _pc < PC_RATIO_BULL_THRESHOLD:
            pc_pts = PC_RATIO_BULL_BONUS
        elif _pc > PC_RATIO_BEAR_THRESHOLD:
            pc_pts = -PC_RATIO_BEAR_MALUS
    catalyst_pts = round(max(0.0, min(
        earn_pts + insider_pts + news_pts + pressure_pts + gamma_pts + borrow_pts + pc_pts,
        SUB_CATALYST_MAX,
    )), 1)

    # Timing (max SUB_TIMING_MAX = 35):
    #   RV-Pts + Mom-Pts (raw 0..37) → normalisiert auf 0..25 (unverändert)
    #   + RS vs. SPY (±3, linear bis ±RS_SPY_THRESHOLD_PCT)
    #   + Float Turnover (0/3/6/10 Pkt) — komplementär zu RVOL
    #   + Gap & Hold (-3..+5) — Eröffnungsstärke EOD-validiert
    #   Cap bei SUB_TIMING_MAX. RS-vs-Sektor ist ersetzt; siehe CLAUDE.md.
    rv_raw = min((rv - 1.0) / 2.0, 1.0) if rv > 0 else 0
    rv_pts = max(rv_raw, 0) * 23
    mom_pts = min(chg / 8.0, 1.0) * 14
    rs_spy_pct,    rs_spy_pts_v   = _rs_spy_pts(s)
    turnover_ratio, turnover_pts  = _float_turnover_pts(s)
    gap_pct, gap_state, gap_pts   = _gap_hold_pts(s)
    timing_pts = round(max(0.0, min(
        (rv_pts + mom_pts) * (25.0 / 37.0) + rs_spy_pts_v + turnover_pts + gap_pts,
        SUB_TIMING_MAX,
    )), 1)

    def _col(pts, mx):
        pct = (pts / mx) if mx > 0 else 0
        if pct > 0.75:  return "#22c55e"
        if pct >= 0.50: return "#f59e0b"
        return "#94a3b8"
    return {
        "struct":        struct_pts,
        "catalyst":      catalyst_pts,
        "timing":        timing_pts,
        "struct_max":    SUB_STRUCT_MAX,
        "catalyst_max":  SUB_CATALYST_MAX,
        "timing_max":    SUB_TIMING_MAX,
        "struct_col":    _col(struct_pts,   SUB_STRUCT_MAX),
        "catalyst_col":  _col(catalyst_pts, SUB_CATALYST_MAX),
        "timing_col":    _col(timing_pts,   SUB_TIMING_MAX),
        "turnover":      round(turnover_ratio, 2),
        "turnover_pts":  int(turnover_pts),
        "gap_pct":       (round(gap_pct, 2) if gap_pct is not None else None),
        "gap_hold_state": gap_state,
        "gap_pts":       int(gap_pts),
        "rs_spy_pct":    (round(rs_spy_pct, 2) if rs_spy_pct is not None else None),
        "rs_spy_pts":    int(rs_spy_pts_v),
    }


def _sub_scores_html(s: dict) -> str:
    """3-teilige Sub-Score-Anzeige unter dem Haupt-Score (oder leer).

    Wichtig: die drei Sub-Scores sind unabhängige Qualitätsindikatoren
    und ergeben NICHT den Gesamt-Score. Header + Hinweistext kommunizieren
    das auf der Karte klar.
    """
    if not SHOW_SUB_SCORES:
        return ""
    sub = _compute_sub_scores(s)
    _tt = ("Diese Werte sind unabhängige Qualitätsindikatoren "
           "und ergeben nicht den Gesamt-Score")
    return (
        f'<div class="sub-scores-wrap">'
        f'<div class="sub-scores-header">SETUP-ANALYSE</div>'
        f'<div class="sub-scores-hint">unabhängige Qualitätsindikatoren</div>'
        f'<div class="sub-scores">'
        f'<span class="sub-score" title="{_tt}">'
        f'<span class="sub-score-lbl">Struktur</span>'
        f'<span class="sub-score-val" style="color:{sub["struct_col"]}">{sub["struct"]:.0f}/{sub["struct_max"]}</span>'
        f'</span>'
        f'<span class="sub-score" title="{_tt}">'
        f'<span class="sub-score-lbl">Katalysator</span>'
        f'<span class="sub-score-val" style="color:{sub["catalyst_col"]}">{sub["catalyst"]:.0f}/{sub["catalyst_max"]}</span>'
        f'</span>'
        f'<span class="sub-score" title="{_tt}">'
        f'<span class="sub-score-lbl">Timing</span>'
        f'<span class="sub-score-val" style="color:{sub["timing_col"]}">{sub["timing"]:.0f}/{sub["timing_max"]}</span>'
        f'</span>'
        f'</div>'
        f'</div>'
    )


def _drivers_breakdown(s: dict) -> dict:
    """Kategorisierte Treiber-Liste (Stärken / Risiken) aus Score-Komponenten.

    Deterministisch — keine LLM-Calls. Liest dieselben Felder wie
    ``_compute_sub_scores()`` und ``score()`` und ordnet jedem aktiven
    Signal ein ``weight`` (Score-Beitrag in Punkten, gerundet) zu, damit
    Sortierung nach Wirkungsstärke möglich ist.

    Returns: ``{"strengths": [...], "risks": [...]}`` mit Items
    ``{"label": str, "weight": float}`` — sortiert nach ``weight`` desc.
    Single source of truth für die Drivers-Liste in der Detail-Ansicht
    UND die deterministische Synthese-Zeile darüber.
    """
    strengths: list[tuple[float, str]] = []
    risks:     list[tuple[float, str]] = []

    sf  = _safe_float(s.get("short_float", 0))
    sr  = _safe_float(s.get("short_ratio", 0))
    rv  = _safe_float(s.get("rel_volume",  0))
    chg = _safe_float(s.get("change",      0))
    fl  = s.get("float_shares") or 0
    rsi = s.get("rsi14")
    finra    = s.get("finra_data") or {}
    si_trend = finra.get("trend", "no_data")
    si_tpct  = _safe_float(finra.get("trend_pct", 0.0))

    if sf >= 15:
        strengths.append((min(sf / 50.0, 1.0) * 32, f"Short Float {sf:.1f}%"))
    if sr >= 5:
        strengths.append((min(sr / 10.0, 1.0) * 23, f"Days-to-Cover {sr:.1f}d"))
    if 0 < fl <= FLOAT_SATURATION_HIGH:
        fs_w = max(0.0, min(1.0,
            (FLOAT_SATURATION_HIGH - fl) / (FLOAT_SATURATION_HIGH - FLOAT_SATURATION_LOW)
        )) * 8
        if fs_w > 0:
            strengths.append((fs_w, f"Float klein ({fl/1e6:.1f} M)"))
    if si_trend == "up":
        strengths.append((5.0, f"SI-Trend ↑ +{abs(si_tpct):.0f}%"))
    elif si_trend == "down":
        risks.append((5.0, f"SI-Trend ↓ −{abs(si_tpct):.0f}%"))

    earn_days = s.get("earnings_days")
    if earn_days is not None and earn_days <= 7:
        strengths.append((15.0, f"Earnings in {earn_days}d"))
    elif earn_days is not None and earn_days <= 14:
        strengths.append((8.0, f"Earnings in {earn_days}d"))
    if s.get("sec_13f_note"):
        strengths.append((10.0, "Insider/13F-Signal"))
    if _detect_short_pressure(s):
        strengths.append((float(SHORT_PRESSURE_BONUS), "Short-Druck-Muster"))
    g = _gamma_squeeze_level(s)
    if g == "likely":
        strengths.append((float(GAMMA_BONUS_LIKELY), "Gamma-Squeeze wahrscheinlich"))
    elif g == "possible":
        strengths.append((float(GAMMA_BONUS_POSSIBLE), "Gamma-Setup möglich"))
    borrow = s.get("borrow_rate")
    if borrow is not None:
        if borrow > 100:
            strengths.append((float(IBKR_BORROW_BONUS_EXTREME),
                              f"Borrow {borrow:.0f}%/J extrem"))
        elif borrow > IBKR_BORROW_HIGH:
            strengths.append((float(IBKR_BORROW_BONUS_HOT),
                              f"Borrow {borrow:.0f}%/Jahr"))

    pc = (s.get("options") or {}).get("pc_ratio")
    if pc is not None:
        if pc < PC_RATIO_BULL_THRESHOLD:
            strengths.append((float(PC_RATIO_BULL_BONUS), f"PC {pc:.2f} bullisch"))
        elif pc > PC_RATIO_BEAR_THRESHOLD:
            risks.append((float(PC_RATIO_BEAR_MALUS), f"PC {pc:.2f} bärisch"))

    if rv >= 2.0:
        rv_w = min((rv - 1.0) / 2.0, 1.0) * 23
        strengths.append((rv_w, f"RVOL {rv:.1f}×"))
    chg_eff = chg - _safe_float(s.get("spx_daily_perf", 0.0)) if USE_RELATIVE_MOMENTUM else chg
    if chg_eff >= 5:
        strengths.append((min(chg_eff / 8.0, 1.0) * 14, f"Momentum +{chg_eff:.1f}%"))
    elif chg < -3:
        risks.append((min(abs(chg) / 5.0, 1.0) * 8, f"Tagesverlust {chg:.1f}%"))

    rs_pct, rs_pts = _rs_spy_pts(s)
    if rs_pct is not None:
        if rs_pts > 0.5:
            strengths.append((rs_pts, f"RS vs. SPY +{rs_pct:.1f}%"))
        elif rs_pts < -0.5:
            risks.append((abs(rs_pts), f"RS vs. SPY {rs_pct:.1f}%"))

    turnover_ratio, turnover_pts = _float_turnover_pts(s)
    if turnover_pts > 0:
        strengths.append((float(turnover_pts), f"Vol/Float {turnover_ratio:.1f}×"))

    gap_pct, gap_state, gap_pts = _gap_hold_pts(s)
    if gap_state == "strong_hold" and gap_pct is not None:
        strengths.append((float(gap_pts), f"Strong Hold +{gap_pct:.1f}%"))
    elif gap_state == "fail":
        risks.append((float(abs(gap_pts)), "Bull-Trap (Gap-Fail)"))

    if rsi is not None and rsi > 70:
        risks.append((min((rsi - 70) / 2.0, 10.0), f"RSI {rsi:.0f} überkauft"))

    ma50  = s.get("ma50")
    price = _safe_float(s.get("price", 0))
    if ma50 and price and ma50 > 0:
        vs = (price - ma50) / ma50 * 100
        if vs < -5:
            risks.append((min(abs(vs) / 2.0, 12.0), f"Unter MA50 ({vs:+.1f}%)"))

    strengths.sort(key=lambda x: -x[0])
    risks.sort(key=lambda x: -x[0])
    return {
        "strengths": [{"label": l, "weight": round(w, 1)} for w, l in strengths],
        "risks":     [{"label": l, "weight": round(w, 1)} for w, l in risks],
    }


def _drivers_synthesis_line(breakdown: dict) -> str:
    """Ein-Satz-Synthese aus den Top-2 Stärken + Top-2 Risiken.

    Liest die bereits sortierte ``_drivers_breakdown``-Ausgabe — zweite
    Sortierung entfällt. Liefert HTML mit ``<strong>``-Labels (sicher,
    da Driver-Labels intern erzeugt sind, kein User-Input).
    Leerer String, wenn weder Stärken noch Risiken aktiv sind.
    """
    strengths = breakdown.get("strengths") or []
    risks     = breakdown.get("risks")     or []
    parts: list[str] = []
    if strengths:
        top = ", ".join(d["label"] for d in strengths[:2])
        parts.append(f'<strong class="syn-pos">Stark:</strong> {top}')
    if risks:
        top = ", ".join(d["label"] for d in risks[:2])
        parts.append(f'<strong class="syn-neg">Schwach:</strong> {top}')
    if not parts:
        return ""
    return ". ".join(parts) + "."


def _drivers_block_html(s: dict) -> str:
    """Detail-Ansicht-Block: Synthese-Zeile + zwei kategorisierte Listen.

    Ersetzt die alte einzeilige ``.driver-row`` (Risiko-Badge + sit_txt).
    Risiko-Badge bleibt erhalten (visueller Anker), aber die freie
    ``short_situation``-Prosa weicht der strukturierten Driver-Aufteilung.
    Synthese-Zeile nur sichtbar, wenn mindestens eine Kategorie befüllt
    ist — sonst leerer String (kein leerer Wrapper im DOM).
    """
    bd = _drivers_breakdown(s)
    strengths = bd["strengths"][:5]
    risks     = bd["risks"][:5]
    if not strengths and not risks:
        return ""
    risk_lv, risk_col, _ = risk_assessment(s)
    synth = _drivers_synthesis_line({"strengths": strengths, "risks": risks})
    out = ['<div class="drivers-block">']
    out.append(
        f'<div class="drivers-header">'
        f'<span class="risk-badge" style="color:{risk_col};'
        f'border-color:{risk_col}55;background:{risk_col}22">Risiko: {risk_lv}</span>'
        f'</div>'
    )
    if synth:
        out.append(f'<p class="drivers-synthesis">{synth}</p>')
    out.append('<div class="drivers-cats">')
    if strengths:
        items = "".join(
            f'<li><span class="drv-w drv-w-pos">+{d["weight"]:.0f}</span>'
            f'<span class="drv-lbl">{d["label"]}</span></li>'
            for d in strengths
        )
        out.append(
            '<div class="drivers-cat drivers-strengths">'
            '<div class="drivers-cat-hdr">✓ Stärken</div>'
            f'<ul class="drivers-list">{items}</ul></div>'
        )
    if risks:
        items = "".join(
            f'<li><span class="drv-w drv-w-neg">−{d["weight"]:.0f}</span>'
            f'<span class="drv-lbl">{d["label"]}</span></li>'
            for d in risks
        )
        out.append(
            '<div class="drivers-cat drivers-risks">'
            '<div class="drivers-cat-hdr">⚠ Risiken</div>'
            f'<ul class="drivers-list">{items}</ul></div>'
        )
    out.append('</div></div>')
    return "".join(out)


def _pd_badges_html(s: dict) -> str:
    """Feature 3 — Pump-&-Dump Warnbadges (orange + rot)."""
    if not PD_FILTER_ENABLED:
        return ""
    out = []
    chg5 = s.get("change_5d")
    rsi  = s.get("rsi14")
    rvol_now  = _safe_float(s.get("rel_volume", 0))
    rvol_prev = _safe_float(s.get("rel_volume_yesterday", 0))
    if (chg5 is not None and chg5 >= PD_GAIN_5D_THRESHOLD * 100
            and rvol_prev > 0 and rvol_now < rvol_prev):
        out.append(
            f'<span class="pd-badge pd-badge-warn" '
            f'title="+{chg5:.1f}% in 5T bei Volumen-Rückgang ({rvol_now:.1f}x heute vs {rvol_prev:.1f}x gestern)">'
            f'⚠️ Möglicher P&amp;D — bereits +{chg5:.0f}% in 5T</span>'
        )
    if (rsi is not None and rsi > PD_RSI_THRESHOLD
            and chg5 is not None and chg5 >= PD_GAIN_5D_RSI_THRESHOLD * 100):
        out.append(
            f'<span class="pd-badge pd-badge-risk" '
            f'title="RSI {rsi:.0f} > {PD_RSI_THRESHOLD} bei +{chg5:.1f}% in 5T">'
            f'\U0001F534 RSI überkauft — Einstieg riskant</span>'
        )
    return "".join(out)


def _gamma_pressure(s: dict) -> float | None:
    """Gamma-Druck = atm_call_oi × Kurs / Ø-Volumen (20T).

    Rückgabe None wenn Daten fehlen (internationale Ticker, leere Options-
    Chain, fehlendes Volumen).
    """
    if not GAMMA_SQUEEZE_ENABLED:
        return None
    opts  = s.get("options") or {}
    oi    = opts.get("gamma_call_oi")
    price = _safe_float(s.get("price", 0))
    vol   = _safe_float(s.get("avg_vol_20d", 0))
    if oi is None or oi <= 0 or price <= 0 or vol <= 0:
        return None
    return oi * price / vol


def _gamma_squeeze_level(s: dict) -> str:
    """'none' / 'possible' / 'likely' — abhängig von Schwellenwerten."""
    gp = _gamma_pressure(s)
    if gp is None:
        return "none"
    if gp >= GAMMA_LIKELY_THRESHOLD:
        return "likely"
    if gp >= GAMMA_POSSIBLE_THRESHOLD:
        return "possible"
    return "none"


def _gamma_badge_html(s: dict) -> str:
    """Gelbes Badge „⚡ Gamma-Druck erkannt" wenn Schwelle überschritten."""
    lvl = _gamma_squeeze_level(s)
    if lvl == "none":
        return ""
    gp = _gamma_pressure(s) or 0
    label = "wahrscheinlich" if lvl == "likely" else "möglich"
    cls   = "pd-badge-gamma-strong" if lvl == "likely" else "pd-badge-gamma"
    return (
        f'<span class="pd-badge {cls}" '
        f'title="Gamma-Pressure {gp:.2f} (ATM-Call-OI × Kurs ÷ Ø-Vol20T) — {label}">'
        f'⚡ Gamma-Druck {label}</span>'
    )


def _market_tag_html(ticker: str) -> str:
    """Market-Tag (Flag + Region) für die Ticker-Zeile. Leer für US-Ticker,
    da der Report ohnehin US-only anzeigt — die Information wäre redundant."""
    region = get_region(ticker)
    if region == "US":
        return ""
    return f'<span class="market-tag">{get_flag(ticker)} {region}</span>'


def _score_hint_html(score: float) -> str:
    """Backtesting-kalibrierter Score-Hinweis unterhalb des Haupt-Scores.

    Drei Stufen entsprechend der Backtesting-Erkenntnis, dass Scores unter 40
    historisch keine positive Median-Rendite erzielt haben:
      score <15   → dezenter grauer Hinweis
      15 ≤ <40    → oranger Hinweis mit Backtesting-Referenz
      ≥40         → kein Hinweis
    """
    if score < 15:
        return (
            '<span class="score-below-min" style="max-width:150px;font-style:normal">'
            'Score zu niedrig für Squeeze-Signal</span>'
        )
    if score < 40:
        return (
            '<span class="score-below-min" style="max-width:180px;color:#f59e0b;'
            'font-style:normal">'
            'Schwaches Setup — Backtesting zeigt keine positive Rendite unter Score 40'
            '</span>'
        )
    return ""


def _tri_score_color(sc) -> str:
    """Einheitliche Farblogik für Setup-, Monster- und KI-Score.

    ≥60 grün · 30–59 orange · <30 rot · None grau.
    """
    if sc is None:
        return "#94a3b8"
    if sc >= 60:
        return "#22c55e"
    if sc >= 30:
        return "#f97316"
    return "#ef4444"


def _score_block_inner_html(s: dict, hint_html: str = "") -> str:
    """Erzeugt das komplette Innere des ``<div class="score-block">``.

    Drei Zeilen (Setup/Monster/KI) — Reihenfolge & Schriftgröße werden
    rein über CSS-Klassen ``.sort-setup`` / ``.sort-monster`` am Container
    gesteuert (siehe head.jinja). Monster/KI-Zeilen werden nur gerendert,
    wenn die zugehörigen Werte vorhanden sind.
    """
    setup_val = s.get("score") or 0.0
    setup_pct = max(0.0, min(100.0, float(setup_val)))
    setup_col = _tri_score_color(setup_val)

    rows = [(
        f'<div class="sb-row" data-sb="setup">'
        f'<span class="sb-num" style="color:{setup_col}" '
        f'onclick="showScoreExplain(this,event)" role="button" tabindex="0">'
        f'{setup_val:.1f}</span>'
        f'<span class="sb-lbl">Setup-Score</span>'
        f'<div class="sb-track"><div class="sb-fill" '
        f'style="width:{setup_pct:.0f}%;background:{setup_col}"></div></div>'
        f'</div>'
    )]

    ms = s.get("monster_score")
    if ms is not None:
        m_pct = max(0.0, min(100.0, float(ms)))
        m_col = _tri_score_color(ms)
        rows.append(
            f'<div class="sb-row" data-sb="monster">'
            f'<span class="sb-num" style="color:{m_col}">{ms:.0f}</span>'
            f'<span class="sb-lbl">Monster-Score</span>'
            f'<div class="sb-track"><div class="sb-fill" '
            f'style="width:{m_pct:.0f}%;background:{m_col}"></div></div>'
            f'</div>'
        )

    ki = s.get("ki_signal_score")
    if ki is not None:
        k_pct = max(0.0, min(100.0, float(ki)))
        k_col = _tri_score_color(ki)
        rows.append(
            f'<div class="sb-row" data-sb="ki">'
            f'<span class="sb-num" style="color:{k_col}">{ki:.0f}</span>'
            f'<span class="sb-lbl">KI-Score</span>'
            f'<div class="sb-track"><div class="sb-fill" '
            f'style="width:{k_pct:.0f}%;background:{k_col}"></div></div>'
            f'</div>'
        )

    return "".join(rows) + (hint_html or "")


def _detect_short_pressure(s: dict) -> bool:
    """Short Ladder Attack Detection.

    Alle vier Bedingungen müssen gleichzeitig erfüllt sein:
      SSR ≥ 60 % · Kurs −2 % bis −8 % · SF ≥ 25 % · RVOL ≥ 1,5×
    """
    ssr = (s.get("finra_data") or {}).get("ssr_today")
    if ssr is None or ssr < SHORT_PRESSURE_SSR_MIN:
        return False
    chg = s.get("change")
    if chg is None:
        return False
    if not (SHORT_PRESSURE_CHG_MIN * 100 <= chg <= SHORT_PRESSURE_CHG_MAX * 100):
        return False
    sf = _safe_float(s.get("short_float", 0))
    if sf < SHORT_PRESSURE_SF_MIN * 100:
        return False
    rvol = _safe_float(s.get("rel_volume", 0))
    if rvol < SHORT_PRESSURE_RVOL_MIN:
        return False
    return True


def _short_pressure_badge_html(s: dict) -> str:
    """Oranges Badge „📉 Short-Druck erkannt" wenn alle vier Bedingungen matchen."""
    if not _detect_short_pressure(s):
        return ""
    return (
        '<span class="pd-badge pd-badge-pressure" '
        'title="Hoher Short-Sale-Anteil bei fallendem Kurs und hohem Volumen — '
        'möglicher koordinierter Verkaufsdruck. Leerverkäufer müssen irgendwann eindecken.">'
        '\U0001F4C9 Short-Druck erkannt — Squeeze-Potenzial erhöht</span>'
    )


def _agent_boost_row_html(s: dict) -> str:
    """Feature 2 — „⚡ Agent-Boost: +X Pkt"-Zeile in der Detail-Tabelle."""
    boost = s.get("agent_boost_pts")
    if not boost or boost <= 0:
        return ""
    ag_score = s.get("agent_boost_score", 0)
    return (
        f'<tr><td>⚡ Agent-Boost</td>'
        f'<td><span style="color:#a78bfa">+{boost:.1f} Pkt</span>'
        f' <span style="color:var(--txt-dim);font-size:.8em">'
        f'(KI-Score {ag_score:.0f}/100)</span></td></tr>'
    )


def _borrow_rate_row_html(s: dict) -> str:
    """IBKR-Borrow-Rate-Zeile für die Detail-Tabelle. Leer wenn keine Daten."""
    rate = s.get("borrow_rate")
    if rate is None:
        return ""
    if rate > IBKR_BORROW_HIGH:
        col = "#ef4444"
    elif rate >= IBKR_BORROW_LOW:
        col = "#f59e0b"
    else:
        col = "#94a3b8"
    return (
        f'<tr><td>Borrow Rate (IBKR)</td>'
        f'<td><span style="color:{col};font-weight:700">'
        f'{rate:.1f} %/Jahr</span></td></tr>'
    )


def _ctb_util_rows_html(s: dict) -> str:
    """Cost-to-Borrow + Utilization als Display-Only-Detail-Zeilen.

    Beide werden auch dann gerendert, wenn der Wert ``None`` ist —
    Anzeige als „—" statt Zeile zu verbergen. Quelle: Stockanalysis
    (primär) → IBKR (Fallback nur für CTB).
    """
    ctb = s.get("cost_to_borrow")
    util = s.get("utilization")
    ctb_disp  = (f"{ctb:.1f} %/Jahr" if isinstance(ctb, (int, float))
                 else "—")
    util_disp = (f"{util:.1f} %"     if isinstance(util, (int, float))
                 else "—")
    return (
        f'<tr><td>Cost-to-Borrow</td><td>{ctb_disp}</td></tr>'
        f'<tr><td>Utilization</td><td>{util_disp}</td></tr>'
    )


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
            f'<div class="spark-title-wrap">'
            f'<span class="spark-title">\u26a1 KI-Signalverlauf</span>'
            f'<span class="spark-subtitle">(KI-Agent Score der letzten 7 Tage)</span>'
            f'</div>'
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
    below_min_score_html = _score_hint_html(s["score"])
    score_block_html = _score_block_inner_html(s, below_min_score_html)
    monster_score_val = s.get("monster_score")
    monster_data_attr = (f' data-monster="{monster_score_val:.1f}"'
                         if monster_score_val is not None else '')


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

    # Float tile (Feature 2 — Plausibilitäts-Check + MCap-basierte Schätzung)
    float_tile_val, float_detail_str, float_tile_col, float_estimated = _float_display(s)
    si_t1_disp = _fmt_si_record(si_hist[0]) if len(si_hist) >= 1 else "—"
    si_t2_disp = _fmt_si_record(si_hist[1]) if len(si_hist) >= 2 else "—"
    si_t3_disp = _fmt_si_record(si_hist[2]) if len(si_hist) >= 3 else "—"
    ctb_util_rows = _ctb_util_rows_html(s)

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
        _ma50_row2 = f'<tr><td>Kurs vs. MA50</td><td><span style="color:{_ma50_col}">{_ma50_pct}</span></td></tr>'
    else:
        _ma50_row2 = ""
    # Kombinierte MA-Zeile (Stammdaten-Block: ein einziger Eintrag statt zwei)
    if _ma50 is not None and _ma200 is not None:
        _ma_combined_row = (
            f"<tr><td>MA 50T / 200T</td>"
            f"<td>${_ma50:.2f} / ${_ma200:.2f}</td></tr>"
        )
    elif _ma50 is not None:
        _ma_combined_row = f"<tr><td>MA 50T</td><td>${_ma50:.2f}</td></tr>"
    elif _ma200 is not None:
        _ma_combined_row = f"<tr><td>MA 200T</td><td>${_ma200:.2f}</td></tr>"
    else:
        _ma_combined_row = ""
    if _rs20 is not None:
        _rs_col  = "#22c55e" if _rs20 >= 0 else "#ef4444"
        _p20_str = f" (Aktie {_p20:+.1f}%)" if _p20 is not None else ""
        _rs_cell = f'<span style="color:{_rs_col}">{_rs20:+.1f}% vs. S&amp;P 500{_p20_str}</span>'
        _rs_row  = f"<tr><td>Rel. Stärke (20T)</td><td>{_rs_cell}</td></tr>"
    else:
        _rs_row  = ""
    rs_spy_row    = _rs_spy_row_html(s)        # ersetzt RS-vs-Sektor
    gap_hold_row  = _gap_hold_row_html(s)
    earn_surp_row = _earnings_surprise_html(s) # Feature 3
    # Volumen & Momentum (RSI + kombinierte MA + Kurs-vs-MA50 + RS-20T + RS-SPY).
    # Earnings-Surprise wandert in den Katalysatoren-Block.
    momentum_rows = _rsi_row + _ma_combined_row + _ma50_row2 + _rs_row + rs_spy_row
    float_turnover_row = _float_turnover_row_html(s)

    # Options market data rows — Feature 4: <0.5 bullisch, 0.5–1.5 neutral, >1.5 bearisch
    _opts     = s.get("options") or {}
    _pc       = _opts.get("pc_ratio")
    _iv       = _opts.get("atm_iv")
    _exp      = _opts.get("expiry", "")
    _exp_note = f" <span style='color:var(--txt-dim);font-size:.8em'>({_exp})</span>" if _exp else ""
    if SHOW_PUT_CALL_RATIO and _pc is not None:
        _pc_col = ("#22c55e" if _pc < PC_BULLISH
                   else "#ef4444" if _pc > PC_BEARISH
                   else "#f59e0b")
        _pc_lbl = (" — bullisch"  if _pc < PC_BULLISH
                   else " — bärisch" if _pc > PC_BEARISH
                   else " — neutral")
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
    # Katalysatoren-Block: Earnings-Surprise + Optionsdaten zusammengefasst
    catalyst_rows = earn_surp_row + _pc_row + _iv_row
    options_rows  = _pc_row + _iv_row  # legacy v1 placeholder, unused

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

    # Float size row (Feature 2 — nutzt vorberechnete Detail-String aus _float_display)
    if float_detail_str:
        _float_row = f"<tr><td>Float (frei handelbar)</td><td>{float_detail_str}</td></tr>"
    else:
        _float_row = ""

    # SSR-Kachel und Squeeze-History-Badge (Features 1 & 6)
    ssr_tile_html      = _ssr_tile_html(s)
    squeeze_badge_html = _squeeze_history_badge(s)
    sub_scores_html    = _sub_scores_html(s)         # Feature 1
    drivers_block_html = _drivers_block_html(s)       # Synthese + kategorisierte Treiber
    pd_badges_html     = (                            # Feature 3 + Short-Druck
        _pd_badges_html(s) + _short_pressure_badge_html(s) + _gamma_badge_html(s)
    )
    agent_boost_row    = _agent_boost_row_html(s) + _borrow_rate_row_html(s)  # Feature 2 + IBKR
    if agent_boost_row:
        # Score-Modifikator visuell vom ersten Sub-Header (Stammdaten) absetzen.
        agent_boost_row += (
            '<tr aria-hidden="true"><td colspan="2" '
            'style="height:8px;padding:0;border:0"></td></tr>'
        )

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

    # Rank-Marker: Zahl für organische Top-10-Karten, 📌-Badge für Ticker,
    # die ausschließlich wegen der persönlichen Watchlist sichtbar sind.
    if s.get("manual_forced"):
        rank_html = ('<span class="rank rank-manual" '
                     'title="Manuell beobachtet — via persönliche Watchlist hinzugefügt">'
                     '\U0001F4CC</span>')
    else:
        rank_html = f'<span class="rank">{i}</span>'

    return f"""
<article class="card{' card-manual' if s.get('manual_personal') else ''}{' card-lazy' if (LAZY_CARDS_ENABLED and i > LAZY_CARDS_EAGER) else ''}" id="c{i}" data-ticker="{s['ticker']}" data-setup-rank="{i}"{monster_data_attr}
  data-score="{sc:.1f}" data-company="{s.get('company_name','')}"
  data-price="{_price:.2f}" data-sf="{sf:.1f}" data-sr="{sr:.1f}"
  data-rv="{rv:.2f}" data-chg="{chg:.2f}" data-si="{si_trend}"
  data-rsi="{_da_rsi}" data-iv="{_da_iv}" data-earn="{_da_earn}"
  data-earn-date="{_da_earn_date}" data-float="{_da_float}"
  data-cap="{_da_cap}" data-sector="{_sector}" data-news="{_da_news}">
  <div class="card-top">
    <div class="card-left">
      {rank_html}
      <div class="ticker-block">
        <div class="ticker-row">
          <span class="ticker">{s['ticker']}</span>
          {_market_tag_html(s['ticker'])}
          {sa_badge}
          <span class="price-tag">${s.get('price',0):.2f}</span>
          <button class="wl-add-btn" data-ticker="{s['ticker']}" onclick="wlToggle(this)" title="Zur Watchlist hinzufügen">＋</button>
        </div>
        <span class="company">{s.get('company_name','')}</span>
        {sector_tag_html}{earnings_tag_html}{squeeze_badge_html}{pd_badges_html}
      </div>
    </div>
    <div class="score-block sort-setup">{score_block_html}</div>
  </div>
  {sub_scores_html}
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
        {agent_boost_row}
        <tr class="detail-group-header"><td colspan="2">Stammdaten</td></tr>
        <tr><td>Marktkapitalisierung</td><td>{fmt_cap(cap_val)}</td></tr>
        {_float_row}
        {sector_detail_row}
        <tr><td>52W-Hoch / -Tief</td><td>${s.get('52w_high') or 0:.2f} / ${s.get('52w_low') or 0:.2f}</td></tr>
        {_inst_row}
        <tr class="detail-group-header"><td colspan="2">Short-Daten</td></tr>
        {edgar_row}
        <tr><td>SI-Trend (3M)</td><td>{trend_html}</td></tr>
        {si_velocity_row}
        <tr><td>Short-Vol. T-1 (FINRA)</td><td>{si_t1_disp}</td></tr>
        <tr><td>Short-Vol. T-2</td><td>{si_t2_disp}</td></tr>
        <tr><td>Short-Vol. T-3</td><td>{si_t3_disp}</td></tr>
        {ctb_util_rows}
        <tr class="detail-group-header"><td colspan="2">Volumen &amp; Momentum</td></tr>
        <tr><td>Ø Volumen 20T</td><td>{s.get('avg_vol_20d',0):,.0f}</td></tr>
        <tr><td>Heutiges Volumen</td><td>{s.get('cur_vol',0):,.0f}</td></tr>
        {float_turnover_row}
        {gap_hold_row}
        {momentum_rows}
        <tr class="detail-group-header"><td colspan="2">Katalysatoren</td></tr>
        {catalyst_rows}
        <tr><td>Risiko-Detail</td><td style="color:{risk_col}">{risk_txt}</td></tr>
      </table>
    </div>
    {no_data_html}
    {drivers_block_html}
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
    KI-Analyse
  </button>
  <div class="ki-analyse-result" id="ka-res{i}"></div>
</article>"""


# ═══════════════════════════════════════════════════════════════════════════
# JINJA2-INFRASTRUKTUR (Phase 0 — parallel zur f-String-Implementation)
# ═══════════════════════════════════════════════════════════════════════════
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    """Jinja2-Environment mit ``fmt``-Filter und Helfer-Funktionen als Globals.

    fmt-Filter:   {{ val | fmt('.2f') }}   → ``format(val, '.2f')``
    Helpers:      fmt_cap, get_region, get_flag,
                  _score_color, _metric_color, _fmt_si_record,
                  risk_assessment, short_situation, news_summary
    JSON:         ``{{ obj | tojson }}`` (built-in Jinja2 filter) ersetzt json.dumps
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    env.filters["fmt"]             = lambda val, spec="": format(val, spec)
    env.globals["fmt_cap"]         = fmt_cap
    env.globals["get_region"]      = get_region
    env.globals["get_flag"]        = get_flag
    env.globals["score_color"]     = _score_color
    env.globals["metric_color"]    = _metric_color
    env.globals["fmt_si_record"]   = _fmt_si_record
    env.globals["risk_assessment"] = risk_assessment
    env.globals["short_situation"] = short_situation
    env.globals["news_summary"]    = news_summary
    return env


def _build_card_ctx(i: int, s: dict) -> dict:
    """Pre-compute **every** color, label, format-spec and flag for one card.

    The returned flat dict is consumed by ``templates/card.jinja`` (v2-only),
    where the template contains only ``{{ variable }}`` interpolations and
    ``{% if flag %}`` guards — no ternaries, no arithmetic, no format-specs.

    v1 (``_card()`` + f-string) remains fully untouched.
    Covers all 40 format-specs identified in the pre-analysis.
    """
    risk_lv, risk_col, risk_txt = risk_assessment(s)
    sit_txt  = short_situation(s)
    news_sum = news_summary(s.get("news", []))

    # ── Core numeric values ──────────────────────────────────────────────
    ticker   = s["ticker"]
    company  = s.get("company_name", "")
    price    = s.get("price", 0) or 0
    sf       = s.get("short_float", 0) or 0
    sr       = s.get("short_ratio",  0) or 0
    rv       = s.get("rel_volume",   0) or 0
    chg      = s.get("change", 0) or 0
    cap_val  = s.get("yf_market_cap") or s.get("market_cap")

    # ── Score ────────────────────────────────────────────────────────────
    sc       = min(s["score"], 100.0)
    sc_col   = _score_color(sc)

    # ── Sparkline block (pre-render HTML) ─────────────────────────────────
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
            f'<div class="spark-title-wrap">'
            f'<span class="spark-title">\u26a1 KI-Signalverlauf</span>'
            f'<span class="spark-subtitle">(KI-Agent Score der letzten 7 Tage)</span>'
            f'</div>'
            f'<span class="spark-trend" style="color:{_spark["col"]}">{_spark["trend"]}</span>'
            f'</div>'
            f'<div class="spark-svg-wrap"></div>'
            f'<div class="spark-days"></div>'
            f'</div>'
        )
    else:
        sparkline_html = '<p class="spark-placeholder">Verlauf ab morgen verfügbar.</p>'

    # ── Sector / industry ────────────────────────────────────────────────
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

    # ── Earnings badge ───────────────────────────────────────────────────
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

    # ── Momentum ─────────────────────────────────────────────────────────
    chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    chg_col = _metric_color("mom", chg)
    chg_5d_html = (
        f'<br><span style="font-size:0.75em;color:var(--color-text-secondary)">'
        f'5T: {s["change_5d"]:+.1f}%</span>'
        if s.get("change_5d") is not None else ""
    )

    # ── Short float / days-to-cover ──────────────────────────────────────
    has_no_short_data = (sf == 0 and sr == 0)
    flag = get_flag(ticker)
    sf_display = "—" if has_no_short_data else f"{sf:.1f}%"
    sr_display = "—" if has_no_short_data else f"{sr:.1f}d"
    no_data_html = (
        '<p class="no-data-notice">ⓘ Short-Float &amp; Days to Cover für diesen Markt nicht verfügbar.</p>'
        if has_no_short_data else ""
    )
    sf_col = "#94a3b8" if has_no_short_data else _metric_color("sf", sf)
    sr_col = "#94a3b8" if has_no_short_data else _metric_color("sr", sr)
    rv_col = _metric_color("rv", rv)

    below_min_score_html = _score_hint_html(s["score"])
    score_block_html = _score_block_inner_html(s, below_min_score_html)
    monster_score_val = s.get("monster_score")
    monster_data_attr = (f' data-monster="{monster_score_val:.1f}"'
                         if monster_score_val is not None else '')

    # ── FINRA SI-Trend & velocity ────────────────────────────────────────
    finra_d     = s.get("finra_data") or {}
    si_trend    = finra_d.get("trend", "no_data")
    si_tpct     = finra_d.get("trend_pct", 0.0)
    si_hist     = finra_d.get("history", [])
    si_velocity = finra_d.get("si_velocity", 0.0)
    si_accel    = finra_d.get("si_accelerating", False)

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
        trend_html  = f'<span style="color:#22c55e">↑ Steigend +{abs(si_tpct):.1f} %</span>'
        si_tile_val = f"↑ +{abs(si_tpct):.0f} %"
        si_tile_col = "#22c55e"
    elif si_trend == "down":
        trend_html  = f'<span style="color:#ef4444">↓ Fallend −{abs(si_tpct):.1f} %</span>'
        si_tile_val = f"↓ −{abs(si_tpct):.0f} %"
        si_tile_col = "#ef4444"
    elif si_trend == "sideways":
        sign = "+" if si_tpct >= 0 else "−"
        trend_html  = f'<span style="color:#f59e0b">→ Seitwärts {sign}{abs(si_tpct):.1f} %</span>'
        si_tile_val = "→ stabil"
        si_tile_col = "#f59e0b"
    else:
        trend_html  = "Keine Daten"
        si_tile_val = "—"
        si_tile_col = "#94a3b8"

    # ── Float tile (Feature 2) ───────────────────────────────────────────
    float_tile_val, float_detail_str, float_tile_col, _float_estimated = _float_display(s)

    si_t1_disp = _fmt_si_record(si_hist[0]) if len(si_hist) >= 1 else "—"
    si_t2_disp = _fmt_si_record(si_hist[1]) if len(si_hist) >= 2 else "—"
    si_t3_disp = _fmt_si_record(si_hist[2]) if len(si_hist) >= 3 else "—"
    ctb_util_rows = _ctb_util_rows_html(s)

    # ── RSI / MA / Relative-Strength rows ────────────────────────────────
    _rsi   = s.get("rsi14")
    _ma50  = s.get("ma50")
    _ma200 = s.get("ma200")
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
        _vs_ma50  = ((price - _ma50) / _ma50 * 100) if _ma50 > 0 else None
        _ma50_col = "#22c55e" if (_vs_ma50 is not None and _vs_ma50 >= 0) else "#ef4444"
        _ma50_pct = f'({_vs_ma50:+.1f}%)' if _vs_ma50 is not None else ""
        _ma50_row2 = f'<tr><td>Kurs vs. MA50</td><td><span style="color:{_ma50_col}">{_ma50_pct}</span></td></tr>'
    else:
        _ma50_row2 = ""
    # Kombinierte MA-Zeile (Stammdaten-Block: ein einziger Eintrag statt zwei)
    if _ma50 is not None and _ma200 is not None:
        _ma_combined_row = (
            f"<tr><td>MA 50T / 200T</td>"
            f"<td>${_ma50:.2f} / ${_ma200:.2f}</td></tr>"
        )
    elif _ma50 is not None:
        _ma_combined_row = f"<tr><td>MA 50T</td><td>${_ma50:.2f}</td></tr>"
    elif _ma200 is not None:
        _ma_combined_row = f"<tr><td>MA 200T</td><td>${_ma200:.2f}</td></tr>"
    else:
        _ma_combined_row = ""
    if _rs20 is not None:
        _rs_col  = "#22c55e" if _rs20 >= 0 else "#ef4444"
        _p20_str = f" (Aktie {_p20:+.1f}%)" if _p20 is not None else ""
        _rs_cell = f'<span style="color:{_rs_col}">{_rs20:+.1f}% vs. S&amp;P 500{_p20_str}</span>'
        _rs_row  = f"<tr><td>Rel. Stärke (20T)</td><td>{_rs_cell}</td></tr>"
    else:
        _rs_row  = ""
    _rs_spy_row_    = _rs_spy_row_html(s)          # ersetzt RS-vs-Sektor
    gap_hold_row    = _gap_hold_row_html(s)
    _earn_surp_row_ = _earnings_surprise_html(s)   # Feature 3
    # Volumen & Momentum (RSI + kombinierte MA + Kurs-vs-MA50 + RS-20T + RS-SPY).
    # Earnings-Surprise wandert in den Katalysatoren-Block.
    momentum_rows = _rsi_row + _ma_combined_row + _ma50_row2 + _rs_row + _rs_spy_row_
    float_turnover_row = _float_turnover_row_html(s)

    # ── Options rows — Feature 4 (<0.5 bullisch, 0.5–1.5 neutral, >1.5 bearisch) ──
    _opts     = s.get("options") or {}
    _pc       = _opts.get("pc_ratio")
    _iv       = _opts.get("atm_iv")
    _exp      = _opts.get("expiry", "")
    _exp_note = f" <span style='color:var(--txt-dim);font-size:.8em'>({_exp})</span>" if _exp else ""
    if SHOW_PUT_CALL_RATIO and _pc is not None:
        _pc_col = ("#22c55e" if _pc < PC_BULLISH
                   else "#ef4444" if _pc > PC_BEARISH
                   else "#f59e0b")
        _pc_lbl = (" — bullisch"  if _pc < PC_BULLISH
                   else " — bärisch" if _pc > PC_BEARISH
                   else " — neutral")
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
    # Katalysatoren-Block: Earnings-Surprise + Optionsdaten zusammengefasst
    catalyst_rows = _earn_surp_row_ + _pc_row + _iv_row
    options_rows  = _pc_row + _iv_row  # legacy v1 placeholder, unused

    # ── Institutional ownership ──────────────────────────────────────────
    _inst      = s.get("inst_ownership")
    _13f_note  = s.get("sec_13f_note") or ""
    _13f_badge = (
        f' <span style="color:#22c55e;font-size:.8em">● {_13f_note}</span>'
        if _13f_note else ""
    )
    if _inst is not None:
        _inst_pct = float(_inst) * 100
        _inst_col = "#22c55e" if _inst_pct >= 60 else ("#f59e0b" if _inst_pct >= 30 else "#ef4444")
        inst_row = (
            f'<tr><td>Institutioneller Anteil</td>'
            f'<td><span style="color:{_inst_col}">{_inst_pct:.1f}%</span>{_13f_badge}</td></tr>'
        )
    elif _13f_note:
        inst_row = (
            f'<tr><td>Institutioneller Anteil</td>'
            f'<td>{_13f_badge.strip()}</td></tr>'
        )
    else:
        inst_row = ""

    # ── Float row (detail table) — Feature 2 nutzt float_detail_str aus Helper ──
    if float_detail_str:
        float_row = f"<tr><td>Float (frei handelbar)</td><td>{float_detail_str}</td></tr>"
    else:
        float_row = ""

    # ── Feature 1 (SSR-Kachel) + Feature 6 (Squeeze-History-Badge) ───────
    ssr_tile_html      = _ssr_tile_html(s)
    squeeze_badge_html = _squeeze_history_badge(s)
    sub_scores_html    = _sub_scores_html(s)         # NEU: Sub-Scores
    drivers_block_html = _drivers_block_html(s)       # Synthese + kategorisierte Treiber
    pd_badges_html     = (                            # P&D + Short-Druck
        _pd_badges_html(s) + _short_pressure_badge_html(s) + _gamma_badge_html(s)
    )
    agent_boost_row    = _agent_boost_row_html(s) + _borrow_rate_row_html(s)  # Agent-Boost + IBKR
    if agent_boost_row:
        # Score-Modifikator visuell vom ersten Sub-Header (Stammdaten) absetzen.
        agent_boost_row += (
            '<tr aria-hidden="true"><td colspan="2" '
            'style="height:8px;padding:0;border:0"></td></tr>'
        )

    # ── Chart / external links ───────────────────────────────────────────
    yf_chart_url = f"https://finance.yahoo.com/chart/{ticker}"
    is_intl      = "." in ticker
    edgar_row    = (
        ""
        if is_intl else
        f'<tr><td>SEC-Meldungen</td><td>'
        f'<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany'
        f'&amp;CIK={ticker}&amp;type=&amp;dateb=&amp;owner=include&amp;count=10&amp;search_text=" '
        f'target="_blank" rel="noopener noreferrer" class="edgar-link">EDGAR öffnen →</a>'
        f'</td></tr>'
    )
    sa_ticker    = ticker.split(".")[0].lower()
    fv_url       = f"https://finviz.com/quote.ashx?t={ticker.split('.')[0].upper()}"
    sa_url       = f"https://stockanalysis.com/stocks/{sa_ticker}/"
    yahoo_badge  = (
        f'<a class="chart-badge chart-badge-y" href="{yf_chart_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Yahoo Finance Chart">Y</a>'
    )
    finviz_badge = (
        '<span class="chart-badge chart-badge-f chart-badge-dis" '
        'title="Finviz unterstützt nur US-Aktien">F</span>'
        if is_intl else
        f'<a class="chart-badge chart-badge-f" href="{fv_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Finviz Chart &amp; Kennzahlen">F</a>'
    )
    sa_badge     = (
        '<span class="chart-badge chart-badge-s chart-badge-dis" '
        'title="Stockanalysis unterstützt nur US-Aktien">S</span>'
        if is_intl else
        f'<a class="chart-badge chart-badge-s" href="{sa_url}" '
        f'target="_blank" rel="noopener noreferrer" title="Stockanalysis Chart &amp; Short-Interest">S</a>'
    )

    # ── News items ───────────────────────────────────────────────────────
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

    # ── Data attributes ──────────────────────────────────────────────────
    da_rsi       = f'{_rsi:.1f}'     if _rsi is not None else ''
    da_iv        = f'{_iv*100:.1f}'  if _iv  is not None else ''
    da_earn      = str(_earn_days)   if _earn_days is not None else ''
    da_cap       = str(int(cap_val)) if cap_val else ''
    # da_float spiegelt die alte v1-Logik (roher float_shares ohne Validierung),
    # damit v1/v2 byte-identisch bleiben — die neue Plausibilität steckt im Tile/Detail.
    _raw_float   = s.get("float_shares") or 0
    da_float     = f'{_raw_float/1e6:.1f}M' if _raw_float else ''
    _news_titles = [n.get("title","")[:140] for n in (s.get("news") or [])[:3] if n.get("title")]
    da_news      = json.dumps(_news_titles, ensure_ascii=False).replace('"', '&quot;')
    da_earn_date = _earn_dstr

    # ── Detail table formatted fields ────────────────────────────────────
    cap_fmt       = fmt_cap(cap_val)
    hi_str        = f"{s.get('52w_high') or 0:.2f}"
    lo_str        = f"{s.get('52w_low')  or 0:.2f}"
    avg_vol_str   = f"{s.get('avg_vol_20d', 0):,.0f}"
    cur_vol_str   = f"{s.get('cur_vol',    0):,.0f}"

    # ── Rank-Marker & Card-Modifier ──────────────────────────────────────
    # Rank-Badge: nur für FORCED Bonus-Slots (📌 statt Rang-Nummer).
    # Grüner Kartenhintergrund: für ALLE Watchlist-Ticker, auch wenn sie
    # organisch ranken — damit die persönliche Beobachtungsliste überall
    # auf einen Blick erkennbar ist. Spiegelt _card() byte-identisch.
    if s.get("manual_forced"):
        rank_html = ('<span class="rank rank-manual" '
                     'title="Manuell beobachtet — via persönliche Watchlist hinzugefügt">'
                     '\U0001F4CC</span>')
    else:
        rank_html = f'<span class="rank">{i}</span>'
    card_manual_class = " card-manual" if s.get("manual_personal") else ""
    card_lazy_class   = " card-lazy" if (LAZY_CARDS_ENABLED and i > LAZY_CARDS_EAGER) else ""

    return {
        # Identity / rank
        "i":              i,
        "ticker":         ticker,
        "company":        company,
        "region":         get_region(ticker),
        "flag":           flag,
        "market_tag_html": _market_tag_html(ticker),

        # Scalar formatted numbers (40 format-specs all pre-applied)
        # v1 emittiert den Score an zwei Stellen mit unterschiedlicher Semantik:
        #   - data-score="{sc:.1f}"        → gekappt auf 100 (Zeile ~1799)
        #   - <span class="score-num">{s['score']:.1f}</span> → roh (Zeile ~1821)
        # In der Pipeline wird score stets ≤100 gekappt (1312/1320/4702), aber
        # um auch bei unerwarteten Eingaben byte-identisch zu v1 zu bleiben,
        # trennen wir die beiden Keys hier strikt.
        "score_raw_str":  f"{s['score']:.1f}",          # score-num (roh)
        "score_cap_1f":   f"{sc:.1f}",                  # data-score (gekappt)
        "score_pct_str":  f"{sc:.0f}",                  # score-fill width
        "price_str":      f"{price:.2f}",               # price tag + data-price
        "sf_1f":          f"{sf:.1f}",                  # data-sf
        "sr_1f":          f"{sr:.1f}",                  # data-sr
        "rv_2f":          f"{rv:.2f}",                  # data-rv
        "chg_2f":         f"{chg:.2f}",                 # data-chg
        "rv_str":         f"{rv:.1f}",                  # metric tile volumen

        # Colors
        "score_col":      sc_col,
        "sf_col":         sf_col,
        "sr_col":         sr_col,
        "rv_col":         rv_col,
        "chg_col":        chg_col,
        "float_tile_col": float_tile_col,
        "si_tile_col":    si_tile_col,
        "risk_col":       risk_col,

        # Displays / labels
        "sf_display":     sf_display,
        "sr_display":     sr_display,
        "chg_str":        chg_str,
        "si_tile_val":    si_tile_val,
        "float_tile_val": float_tile_val,
        "si_t1_disp":     si_t1_disp,
        "si_t2_disp":     si_t2_disp,
        "si_t3_disp":     si_t3_disp,
        "ctb_util_rows":  ctb_util_rows,
        "cap_fmt":        cap_fmt,
        "hi_str":         hi_str,
        "lo_str":         lo_str,
        "avg_vol_str":    avg_vol_str,
        "cur_vol_str":    cur_vol_str,
        "rank_html":           rank_html,
        "card_manual_class":   card_manual_class,
        "card_lazy_class":     card_lazy_class,

        # Raw values that appear verbatim in data-attrs
        "si_trend":       si_trend,
        "sector":         _sector,

        # Data attributes
        "da_rsi":         da_rsi,
        "da_iv":          da_iv,
        "da_earn":        da_earn,
        "da_earn_date":   da_earn_date,
        "da_float":       da_float,
        "da_cap":         da_cap,
        "da_news":        da_news,

        # Risk / narrative
        "risk_lv":        risk_lv,
        "risk_txt":       risk_txt,
        "sit_txt":        sit_txt,
        "news_sum":       news_sum,

        # Pre-rendered HTML sub-blocks (each resolves internal ternaries)
        "sparkline_html":       sparkline_html,
        "sector_tag_html":      sector_tag_html,
        "sector_detail_row":    sector_detail_row,
        "earnings_tag_html":    earnings_tag_html,
        "chg_5d_html":          chg_5d_html,
        "no_data_html":         no_data_html,
        "below_min_score_html": below_min_score_html,
        "score_block_html":     score_block_html,
        "monster_data_attr":    monster_data_attr,
        "setup_rank":           i,
        "si_velocity_row":      si_velocity_row,
        "trend_html":           trend_html,
        "momentum_rows":        momentum_rows,
        "float_turnover_row":   float_turnover_row,
        "gap_hold_row":         gap_hold_row,
        "catalyst_rows":        catalyst_rows,
        "inst_row":             inst_row,
        "ssr_tile_html":        ssr_tile_html,        # Feature 1
        "squeeze_badge_html":   squeeze_badge_html,   # Feature 6
        "sub_scores_html":      sub_scores_html,      # Sub-Scores
        "drivers_block_html":   drivers_block_html,   # Synthese + Stärken/Risiken
        "pd_badges_html":       pd_badges_html,       # P&D-Badges
        "agent_boost_row":      agent_boost_row,      # Agent-Boost-Zeile
        "float_row":            float_row,
        "edgar_row":            edgar_row,
        "yahoo_badge":          yahoo_badge,
        "finviz_badge":         finviz_badge,
        "sa_badge":             sa_badge,
        "news_html":            news_html,
    }


def _build_chat_synthesis_ctx(stocks: list[dict], score_history: dict) -> dict:
    """Erweiterter Chat-Kontext mit Tagesvergleich + Anomalien + Position.

    Liefert ein Dict mit:
      - ``today_top10``: pro Top-10-Ticker setup_today + setup_yesterday +
        setup_delta (sowie alle Roh-Kennzahlen).
      - ``anomalies_today``: erkennbare „was hat sich geändert"-Events
        (Score-Sprung ≥15, Top-10-Eintritte/-Austritte, frische Earnings,
        starke RVOL-Werte). KI-Agent-Anomalien (UOA/RVOL-Vortagsvergleich)
        sind nicht enthalten — die liegen erst im nächsten ki_agent-Tick vor.
      - ``topten_changes``: ``{new: [...], dropped: [...]}`` vs. Vortag.
      - ``positions``: positions.json + PnL gegen heutigen Spot (Top-10
        Cross-Match) — leer wenn `positions.json` fehlt.
      - ``yesterday_date``: deutscher Datums-String, auf den die Diffs
        sich beziehen.
    Keine Calls in Code-Pfade mit Side-Effects; pure-Funktion-Helper.
    """
    def _entry_date(e):
        return e.get("date") if isinstance(e, dict) else (
            e[0] if isinstance(e, (list, tuple)) and e else None)

    def _entry_score(e):
        return e.get("score") if isinstance(e, dict) else (
            e[1] if isinstance(e, (list, tuple)) and len(e) >= 2 else None)

    # Yesterday-Datum: zweitneuester Eintrag in score_history (alle Datums-
    # Strings einsammeln, sortieren). Heute ist der neueste, gestern der
    # zweitneueste — robust gegen Wochenenden/Feiertage.
    all_dates: set[str] = set()
    for entries in (score_history or {}).values():
        for e in (entries or []):
            d = _entry_date(e)
            if d:
                all_dates.add(d)

    def _parse_de(d):
        try:
            return datetime.strptime(d, "%d.%m.%Y")
        except (ValueError, TypeError):
            return datetime.min

    sorted_dates  = sorted(all_dates, key=_parse_de, reverse=True)
    today_str     = sorted_dates[0] if sorted_dates else ""
    yesterday_str = sorted_dates[1] if len(sorted_dates) >= 2 else ""

    today_set = {s["ticker"] for s in stocks}
    today_top10: list[dict] = []
    for s in stocks:
        ticker  = s["ticker"]
        entries = (score_history or {}).get(ticker) or []
        # Gestriger raw setup-Eintrag, wenn vorhanden.
        prev_score = None
        if yesterday_str:
            for e in reversed(entries):
                if _entry_date(e) == yesterday_str:
                    prev_score = _entry_score(e)
                    break

        setup_today  = round(_safe_float(s.get("score", 0)), 1)
        prev_score_f = (round(_safe_float(prev_score), 1)
                        if prev_score is not None else None)
        delta        = (round(setup_today - prev_score_f, 1)
                        if prev_score_f is not None else None)

        _fd   = s.get("finra_data") or {}
        _opts = s.get("options") or {}
        today_top10.append({
            "ticker":          ticker,
            "company":         s.get("company_name", ""),
            "setup_today":     setup_today,
            "setup_yesterday": prev_score_f,
            "setup_delta":     delta,
            "monster_today":   (round(_safe_float(s.get("monster_score", 0)), 1)
                                if s.get("monster_score") is not None else None),
            "ki_today":        s.get("ki_signal_score"),
            "price":           round(_safe_float(s.get("price", 0)), 2),
            "change":          round(_safe_float(s.get("change", 0)), 2),
            "short_float":     round(_safe_float(s.get("short_float", 0)), 1),
            "short_ratio":     round(_safe_float(s.get("short_ratio", 0)), 1),
            "rel_volume":      round(_safe_float(s.get("rel_volume", 0)), 2),
            "rsi14":           s.get("rsi14"),
            "atm_iv":          _opts.get("atm_iv"),
            "earnings_days":   s.get("earnings_days"),
            "sector":          s.get("sector", ""),
            "si_trend":        _fd.get("trend", "no_data"),
        })

    # Top-10-Eintritte/-Austritte vs. Vortag
    yesterday_top10_set: set[str] = set()
    if yesterday_str:
        for t, entries in (score_history or {}).items():
            for e in entries:
                if _entry_date(e) == yesterday_str:
                    yesterday_top10_set.add(t)
                    break

    new_in_top10  = sorted(today_set - yesterday_top10_set)
    dropped_top10 = sorted(yesterday_top10_set - today_set)

    # Anomalie-Liste — bewusst minimal, weil ki_agent-eigene Trigger
    # (UOA-Extreme, RVOL-Combo) erst im stündlichen Tick auflaufen. Hier:
    # gestern→heute Score-Sprung, Top-10-Bewegung, Earnings-Nähe, RVOL-Spike.
    anomalies: list[dict] = []
    for d in today_top10:
        if d["setup_delta"] is not None and d["setup_delta"] >= ANOMALY_SCORE_JUMP:
            anomalies.append({
                "ticker":  d["ticker"],
                "trigger": "score_jump",
                "detail":  (f"Setup {d['setup_today']:.0f} ↑ "
                            f"(gestern {d['setup_yesterday']:.0f}, +{d['setup_delta']:.0f})"),
            })
        if d["rel_volume"] >= ANOMALY_RVOL_TODAY:
            anomalies.append({
                "ticker":  d["ticker"],
                "trigger": "rvol_high",
                "detail":  f"RVOL {d['rel_volume']:.1f}× heute",
            })
        if d["earnings_days"] is not None and 0 <= d["earnings_days"] <= 2:
            anomalies.append({
                "ticker":  d["ticker"],
                "trigger": "earnings_imminent",
                "detail":  f"Earnings in {d['earnings_days']}d",
            })
    for t in new_in_top10:
        anomalies.append({
            "ticker":  t,
            "trigger": "topten_entry",
            "detail":  "Neu in Top-10",
        })
    for t in dropped_top10:
        anomalies.append({
            "ticker":  t,
            "trigger": "topten_exit",
            "detail":  "Aus Top-10 gefallen",
        })

    # Positions-Kontext: positions.json + PnL gegen heutigen Spot.
    # Exit-Score wird hier NICHT berechnet (würde yfinance-Fetches je
    # Position auslösen); compute_exit_score läuft separat in Step 5.
    by_ticker = {s["ticker"]: s for s in stocks}
    positions_out: list[dict] = []
    try:
        positions = _load_positions()
    except Exception:
        positions = {}
    for ticker, pos in (positions or {}).items():
        s = by_ticker.get(ticker)
        entry_price = pos.get("entry_price")
        cur_price   = s.get("price") if s else None
        pnl_pct = None
        try:
            if entry_price and cur_price:
                pnl_pct = round(
                    (float(cur_price) - float(entry_price)) / float(entry_price) * 100, 2
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pnl_pct = None
        positions_out.append({
            "ticker":         ticker,
            "entry_date":     pos.get("entry_date"),
            "entry_price":    entry_price,
            "current_price":  (round(_safe_float(cur_price), 2)
                               if cur_price is not None else None),
            "pnl_pct":        pnl_pct,
            "in_top10":       s is not None,
            "setup_today":    (round(_safe_float(s.get("score")), 1)
                               if s and s.get("score") is not None else None),
            "monster_today":  (round(_safe_float(s.get("monster_score")), 1)
                               if (s and s.get("monster_score") is not None) else None),
        })

    return {
        "today_top10":     today_top10,
        "anomalies_today": anomalies,
        "topten_changes":  {"new": new_in_top10, "dropped": dropped_top10},
        "positions":       positions_out,
        "yesterday_date":  yesterday_str,
        "today_date":      today_str,
        "fx_usd_eur":      _FX_USD_EUR,
    }


def _build_context(stocks: list[dict], report_date: str) -> dict:
    """Zentrale Context-Erstellung für Template-Rendering.

    Liefert ein Dict mit allen vorberechneten Aggregaten + JSON-Blobs,
    die sowohl ``generate_html_v1`` (f-String) als auch ``generate_html_v2``
    (Jinja2) benötigen. Einzige Stelle für Template-Variablen.

    ``card_ctxs`` (Liste vorberechneter Card-Context-Dicts) wird ausschließlich
    von v2 konsumiert — v1 nutzt weiterhin ``_card()``.
    """
    cards = "\n".join(_card(i + 1, s) for i, s in enumerate(stocks))
    card_ctxs = [_build_card_ctx(i + 1, s) for i, s in enumerate(stocks)]

    # Dynamische Datenpunkt-Zahl für die Backtesting-Status-Sektion. Liest
    # backtest_history.json (silently [] bei Fehlern) — ersetzt die früher
    # hardcodierte „1.046 Datenpunkte"-Marke.
    backtest_count = len(_load_backtest_history())
    backtest_count_str = f"{backtest_count:,}".replace(",", ".")

    n       = max(len(stocks), 1)
    avg_sf  = sum(s["short_float"] for s in stocks) / n
    avg_sr  = sum(s["short_ratio"]  for s in stocks) / n
    avg_rv  = sum(s["rel_volume"]   for s in stocks) / n
    mom_vals = [s["change"] for s in stocks if s.get("change") is not None and s.get("change") != 0.0]
    _avg_mom = sum(mom_vals) / len(mom_vals) if mom_vals else None
    avg_mom_str = f"{_avg_mom:+.1f}%" if _avg_mom is not None else "—"
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

    # Watchlist: embed last known score, sparkline history, and full top10 snapshot.
    # Nutzt _load_score_history() statt direktem JSON-Load, damit beide Disk-Formate
    # (alt dict-per-entry, neu Tuple-per-entry) transparent normalisiert werden.
    try:
        _wl_raw = _load_score_history()
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
        _wl_raw    = {}
        _wl_scores = {}
        _wl_hist   = {}
    wl_scores_json = json.dumps(_wl_scores)
    wl_hist_json   = json.dumps(_wl_hist)
    # GIST_ID-Injection: vom Workflow per Env-Variable zur Render-Zeit
    # gesetzt. Leer → JS-Position-Panel zeigt „Gist nicht konfiguriert"-
    # Hinweis statt Save-/Load-Versuch. Sanitize: nur a-z0-9 erlaubt.
    _gid_raw = os.environ.get("GIST_ID", "").strip()
    gist_id_js = re.sub(r"[^A-Za-z0-9]", "", _gid_raw)[:64]

    # Full snapshots für Watchlist-Detail-Karten (gemeinsamer Builder, damit
    # sowohl in-page WL_TOP10 als auch app_data.watchlist_cards identisch
    # befüllt sind).
    _wl_top10 = {_s["ticker"]: _wl_card_payload(_s) for _s in stocks}
    wl_top10_json = json.dumps(_wl_top10, default=str)

    # Compact top-10 snapshot for Claude chat system prompt — strukturiert mit
    # Tagesvergleich, Anomalie-Liste, Position-Kontext und Top-10-Diff.
    # Siehe _build_chat_synthesis_ctx-Docstring für Schema.
    _chat_ctx     = _build_chat_synthesis_ctx(stocks, _wl_raw)
    chat_ctx_json = json.dumps(_chat_ctx, default=str)

    # Pre-render Jinja2-Templates (Phase 2+: head/CSS, Phase 4a: Chat-Panel-HTML,
    # Phase 4b: Chat-Panel-JS-IIFE).
    # Autoescape ist global OFF via select_autoescape(enabled_extensions=(),
    # default=False) — kritisch für chat_script.jinja, das den raw JSON-String
    # `chat_ctx_json` direkt als JS-Literal einfügt.
    _env = _jinja_env()
    head_html        = _env.get_template("head.jinja").render(report_date=report_date)
    chat_panel_html  = _env.get_template("chat_panel.jinja").render()
    chat_script_html = _env.get_template("chat_script.jinja").render(
        chat_ctx_json=chat_ctx_json,
    )

    return {
        "report_date":    report_date,
        "timestamp":      timestamp,
        "cards":          cards,
        "card_ctxs":      card_ctxs,   # v2-only: pre-computed per-card ctx
        "avg_sf":         avg_sf,
        "avg_sr":         avg_sr,
        "avg_rv":         avg_rv,
        "avg_mom_str":    avg_mom_str,
        "avg_float_str":  avg_float_str,
        "avg_si_str":     avg_si_str,
        "wl_scores_json": wl_scores_json,
        "wl_hist_json":   wl_hist_json,
        "wl_top10_json":  wl_top10_json,
        "gist_id_js":     gist_id_js,
        "chat_ctx_json":  chat_ctx_json,
        "head_html":      head_html,
        "chat_panel_html": chat_panel_html,
        "chat_script_html": chat_script_html,
        "backtest_count_str": backtest_count_str,
    }


def generate_html_v1(stocks: list[dict], report_date: str, _ctx: dict | None = None) -> str:
    """Legacy f-String-Rendering — aktuell autoritativ.

    ``_ctx`` ist ein optionaler Context-Override, den ``generate_html_v2``
    nutzt, um seine Jinja-gerenderten Karten einzuschleusen. Dadurch
    vergleicht ``_render_test`` v1 gegen v2 in einer Konfiguration, in der
    einzig die Kartenquelle (f-String vs Jinja2) variiert.
    """
    ctx = _ctx if _ctx is not None else _build_context(stocks, report_date)
    # Unpack context for f-string access
    report_date    = ctx["report_date"]
    timestamp      = ctx["timestamp"]
    cards          = ctx["cards"]
    avg_sf         = ctx["avg_sf"]
    avg_sr         = ctx["avg_sr"]
    avg_rv         = ctx["avg_rv"]
    avg_mom_str    = ctx["avg_mom_str"]
    avg_float_str  = ctx["avg_float_str"]
    avg_si_str     = ctx["avg_si_str"]
    wl_scores_json = ctx["wl_scores_json"]
    wl_hist_json   = ctx["wl_hist_json"]
    wl_top10_json  = ctx["wl_top10_json"]
    gist_id_js     = ctx["gist_id_js"]
    chat_ctx_json    = ctx["chat_ctx_json"]
    head_html        = ctx["head_html"]
    chat_panel_html  = ctx["chat_panel_html"]
    chat_script_html = ctx["chat_script_html"]
    backtest_count_str = ctx["backtest_count_str"]

    return f"""{head_html}
<body>
<header class="app-hdr">
  <div class="hdr-main">
    <span class="app-title">Squeeze <span>Report</span></span>
    <span class="hdr-ts">{timestamp}<span id="hdr-nontrading" class="hdr-nontrading" hidden></span></span>
    <button class="hamburger-btn" id="hamburger-btn" aria-label="Menü" aria-expanded="false" onclick="toggleMenuDrawer()">
      <i data-lucide="menu" class="hamburger-icon"></i>
    </button>
  </div>

  <!-- Hamburger-Drawer (mobile + desktop) — wird per JS getoggelt.
       Score-Sortierung als Sub-Menü mit Häkchen, Default aus
       localStorage[squeeze_sort_mode]. Footer mit Utility-Buttons. -->
  <div class="menu-overlay" id="menu-overlay" onclick="toggleMenuDrawer(false)" aria-hidden="true"></div>
  <nav class="menu-drawer" id="menu-drawer" aria-hidden="true">
    <div class="menu-list" role="menu">
      <button class="menu-item menu-item-primary" role="menuitem" onclick="reloadPage();toggleMenuDrawer(false)">
        <span class="menu-icon-box menu-icon-box-primary"><i data-lucide="refresh-cw"></i></span>
        <span class="menu-label">Reload</span>
      </button>
      <button class="menu-item" role="menuitem" onclick="triggerWorkflow();toggleMenuDrawer(false)">
        <span class="menu-icon-box"><i data-lucide="calculator"></i></span>
        <span class="menu-label">Recalculate</span>
      </button>
      <button class="menu-item" role="menuitem" onclick="triggerKiAgent();toggleMenuDrawer(false)">
        <span class="menu-icon-box"><i data-lucide="zap"></i></span>
        <span class="menu-label">Agent Run</span>
      </button>
      <button class="menu-item" role="menuitem" onclick="scrollToBacktesting();toggleMenuDrawer(false)">
        <span class="menu-icon-box"><i data-lucide="bar-chart-3"></i></span>
        <span class="menu-label">Backtesting</span>
      </button>
      <button class="menu-item" role="menuitem" onclick="scrollToMethodology();toggleMenuDrawer(false)">
        <span class="menu-icon-box"><i data-lucide="book-open"></i></span>
        <span class="menu-label">Score-Methodik</span>
      </button>
      <button class="menu-item menu-item-toggle" id="menu-sort-toggle" role="menuitem" aria-expanded="false" onclick="toggleMenuSort()">
        <span class="menu-icon-box"><i data-lucide="arrow-up-down"></i></span>
        <span class="menu-label">Score-Sortierung: <span id="menu-sort-current">Setup</span></span>
        <i data-lucide="chevron-down" class="menu-chevron" id="menu-sort-chevron"></i>
      </button>
      <div class="menu-submenu" id="menu-sort-submenu" hidden>
        <button class="menu-subitem" data-sort="setup" role="menuitemradio" onclick="selectSortMode('setup')">
          <i data-lucide="check" class="menu-check" id="menu-sort-check-setup"></i>
          <span>Setup-Score</span>
        </button>
        <button class="menu-subitem" data-sort="monster" role="menuitemradio" onclick="selectSortMode('monster')">
          <i data-lucide="check" class="menu-check" id="menu-sort-check-monster"></i>
          <span>Monster-Score</span>
        </button>
      </div>
      <button class="menu-item" role="menuitem" onclick="toggleChat();toggleMenuDrawer(false)">
        <span class="menu-icon-box"><i data-lucide="message-circle"></i></span>
        <span class="menu-label">Chat</span>
      </button>
    </div>
    <div class="menu-footer">
      <button class="menu-foot-btn" id="fs-down" onclick="changeFontSize(-1)" aria-label="Schrift kleiner" title="Schrift kleiner">
        <i data-lucide="minus"></i>
      </button>
      <button class="menu-foot-btn" id="fs-up" onclick="changeFontSize(1)" aria-label="Schrift größer" title="Schrift größer">
        <i data-lucide="plus"></i>
      </button>
      <button class="menu-foot-btn" id="settings-btn" onclick="toggleSettings()" aria-label="Einstellungen" title="Einstellungen">
        <i data-lucide="settings"></i>
      </button>
      <button class="menu-foot-btn" id="theme-toggle-btn" onclick="toggleThemeMenu()" aria-label="Theme umschalten" title="Theme umschalten">
        <i data-lucide="moon" id="theme-icon"></i>
      </button>
    </div>
  </nav>
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
    <hr style="border:none;border-top:1px solid var(--brd);margin:12px 0 8px">
    <p class="tok-hint"><strong>GitHub Token</strong> — Benötigt für Watchlist-Persistenz und manuelle Workflow-Trigger. Wird ausschließlich lokal im Browser gespeichert.</p>
    <div class="tok-row">
      <input type="password" id="gh-inp" class="tok-inp" placeholder="ghp_…"
             autocomplete="off" spellcheck="false"
             onkeydown="if(event.key==='Enter')saveGhToken()">
      <button class="btn btn-anth" style="flex:0;padding:0 12px" onclick="testGhToken()">Testen</button>
      <button class="btn btn-b" style="flex:0;padding:0 12px" onclick="saveGhToken()">OK</button>
    </div>
    <div id="gh-status" class="anth-status"></div>
    <div style="padding-top:4px">
      <a class="tok-link" onclick="clearGhToken();return false;" href="#">Token löschen</a>
    </div>
  </div>
  <div id="amsg" class="amsg" style="display:none"></div>
{chat_panel_html}
</header>

<main class="wrap">
  <div class="disc">⚠ <strong>Disclaimer:</strong> Dieser Report dient ausschließlich Informationszwecken und stellt keine Anlageberatung dar. Keine Kauf- oder Verkaufsempfehlung.</div>
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

  <section class="info-panel" id="methodology-section" aria-label="Score-Methodik &amp; Filterkriterien" hidden>
    <div class="info-panel-head">
      <h2 class="info-panel-title">Score-Methodik &amp; Filterkriterien</h2>
      <button class="info-panel-close" type="button" onclick="hideMethodology()" aria-label="Schließen" title="Schließen">
        <i data-lucide="x"></i>
      </button>
    </div>
    <div class="info-inner">
      <div class="info-box">
        <h4>Filterkriterien</h4>
        <ul class="info-compact">
          <li>Marktkapitalisierung &lt; {MAX_MARKET_CAP_B:.0f} Mrd. USD — Small-Cap-Fokus</li>
          <li>Short Float &gt; {MIN_SHORT_FLOAT:.0f} % — nur US</li>
          <li>Kurs &gt; ${MIN_PRICE:.0f} USD · Relatives Volumen ≥ {MIN_REL_VOLUME:.1f}×</li>
          <li>Nur 🇺🇸 US-Screening — internationale Ticker via 📌 Watchlist</li>
          <li>Manuell hinzugefügte Ticker umgehen den Cap-Filter</li>
        </ul>
      </div>
      <div class="info-box info-box--full">
        <h4>Score-Formel — Hauptblöcke</h4>
        <div class="score-blocks">
          <div class="score-block-card">
            <div class="score-block-head">
              <span class="score-block-name">Struktur</span>
              <span class="score-block-badge">0–40</span>
            </div>
            <ul class="score-block-list">
              <li><span class="sb-lbl">Short Float</span><span class="sb-pts">32 Pkt</span></li>
              <li><span class="sb-lbl">Days to Cover</span><span class="sb-pts">23 Pkt</span></li>
              <li><span class="sb-lbl">Float-Größe</span><span class="sb-pts">8 Pkt</span></li>
              <li><span class="sb-lbl">SI-Trend</span><span class="sb-pts">5 Pkt</span></li>
            </ul>
            <p class="score-block-foot">Summe normiert auf 0–40</p>
          </div>
          <div class="score-block-card">
            <div class="score-block-head">
              <span class="score-block-name">Katalysator</span>
              <span class="score-block-badge">0–35</span>
            </div>
            <ul class="score-block-list">
              <li><span class="sb-lbl">Earnings</span></li>
              <li><span class="sb-lbl">News-KI mit Alters-Gewichtung (T+0: 100&nbsp;%, T+3: 20&nbsp;%)</span></li>
              <li><span class="sb-lbl">P/C-Ratio</span></li>
              <li><span class="sb-lbl">Short-Druck</span></li>
              <li><span class="sb-lbl">Gamma Squeeze</span></li>
              <li><span class="sb-lbl">Insider</span></li>
              <li><span class="sb-lbl">UOA</span></li>
            </ul>
          </div>
          <div class="score-block-card">
            <div class="score-block-head">
              <span class="score-block-name">Timing</span>
              <span class="score-block-badge">0–35</span>
            </div>
            <ul class="score-block-list">
              <li><span class="sb-lbl">Rel. Volumen</span><span class="sb-pts">23 Pkt</span></li>
              <li><span class="sb-lbl">Momentum</span><span class="sb-pts">14 Pkt</span></li>
              <li><span class="sb-lbl">RS vs. SPY</span><span class="sb-pts">3 Pkt</span></li>
              <li><span class="sb-lbl">Float Turnover</span><span class="sb-pts">10 Pkt</span></li>
              <li><span class="sb-lbl">Gap &amp; Hold</span><span class="sb-pts">−3 bis +5</span></li>
            </ul>
            <p class="score-block-foot">Summe normiert auf 0–35</p>
          </div>
        </div>
      </div>
      <div class="info-box info-box--full">
        <h4>Boni / Malus / Monster-Score</h4>
        <div class="score-modifiers">
          <div class="score-mod-card score-mod-bonus">
            <span class="score-mod-name">Kombinations-Bonus</span>
            <span class="score-mod-val">+5 Pkt</span>
          </div>
          <div class="score-mod-card score-mod-bonus">
            <span class="score-mod-name">Score-Trend</span>
            <span class="score-mod-val">±3 Pkt</span>
          </div>
          <div class="score-mod-card score-mod-bonus">
            <span class="score-mod-name">Agent-Boost</span>
            <span class="score-mod-val">×1.05</span>
          </div>
          <div class="score-mod-card score-mod-malus">
            <span class="score-mod-name">Historischer Squeeze (90 / 30 Tage)</span>
            <span class="score-mod-val">−3 / −5 Pkt</span>
          </div>
        </div>
        <p class="score-block-foot score-block-foot-strong">
          <strong>Monster-Score = Setup-Score × KI-Boost</strong> — KI ≥ 60: +20&nbsp;% · KI &lt; 25: −20&nbsp;% · sonst neutral · Cap 100
        </p>
        <p class="score-block-foot"><em>Sub-Scores sind unabhängige Qualitätsindikatoren — nicht die Zerlegung des Gesamt-Scores.</em></p>
      </div>
      <div class="info-box">
        <h4>Datenquellen</h4>
        <ul class="info-compact">
          <li>Yahoo Finance (5 US-Screener) · Finviz Screener · FINRA Short Interest ({SI_TREND_PERIODS} Handelstage, 3 CDN-Feeds)</li>
          <li>yfinance · Stockanalysis.com (wöchentl. SI) · EarningsWhispers RSS · Sektor-ETFs (QQQ/XBI/XLE/XLF/XRT/SPY)</li>
          <li>KI-Agent: Claude Haiku · News-Sentiment · Insider · FDA RSS · FINRA Daily SSR · StockTwits API · yfinance Options-Chains (UOA) · SEC EDGAR (13D/13G Filings) · ntfy.sh (Push-Notifications)</li>
        </ul>
      </div>
      <div class="info-box info-box--full">
        <h4>⚡ KI-Agent</h4>
        <p class="score-block-intro">Läuft stündlich · Analysiert News, Earnings, Insider, FINRA SSR, Gamma, Options-Flow</p>
        <div class="score-blocks ki-agent-blocks">
          <div class="score-block-card">
            <div class="score-block-head">
              <span class="score-block-name">Boni</span>
            </div>
            <ul class="score-block-list">
              <li><span class="sb-lbl">StockTwits-Sentiment</span><span class="sb-pts">+8 / +15 / −5</span></li>
              <li><span class="sb-lbl">RVOL High-Alert</span><span class="sb-pts">+10 (≥3×) / +15 (≥5×)</span></li>
              <li><span class="sb-lbl">RVOL Velocity</span><span class="sb-pts">+8 (≥1.5× Anstieg)</span></li>
              <li><span class="sb-lbl">UOA ATM Vol/OI</span><span class="sb-pts">+10 / +20</span></li>
              <li><span class="sb-lbl">UOA Call/Put-Bias</span><span class="sb-pts">+10</span></li>
              <li><span class="sb-lbl">Gamma Squeeze</span><span class="sb-pts">+8 / +15</span></li>
              <li><span class="sb-lbl">Perfect-Storm-Multiplikator</span><span class="sb-pts">×1.10 / ×1.20 / ×1.35 bei 2 / 3 / 4 Triggern</span></li>
            </ul>
          </div>
          <div class="score-block-card">
            <div class="score-block-head">
              <span class="score-block-name">Anomalie-Push-Trigger</span>
            </div>
            <ul class="score-block-list">
              <li><span class="sb-lbl">RVOL-Explosion</span><span class="sb-pts">≥5× heute &amp; ≥2× vs. Vortag</span></li>
              <li><span class="sb-lbl">UOA-Extreme</span><span class="sb-pts">Call-Vol/OI ≥10×</span></li>
              <li><span class="sb-lbl">Score-Sprung</span><span class="sb-pts">≥15 Pkt vs. Vortag</span></li>
              <li><span class="sb-lbl">Gap+Hold-Combo</span><span class="sb-pts">Gap ≥5 %, Strong Hold, RVOL ≥3×</span></li>
              <li><span class="sb-lbl">Perfect Storm</span><span class="sb-pts">4/4 Trigger</span></li>
              <li><span class="sb-lbl">Monster ≥90 (Backup)</span><span class="sb-pts">—</span></li>
              <li><span class="sb-lbl">📜 SEC 13D/13G Filings (Top-10)</span><span class="sb-pts">13D immer · 13G nur Aktivisten · 24 h Cooldown</span></li>
            </ul>
          </div>
        </div>
        <p class="score-block-foot score-block-foot-strong">
          <strong>Push-Logik:</strong> Standard-Cooldown 6 h pro (Ticker × Trigger-Typ) · Push pausiert bei VIX &gt; 35 (Krise) · Warnung bei VIX &gt; 25.
        </p>
      </div>
      <div class="info-box info-box--full">
        <h4>📊 Backtesting-Status</h4>
        <p style="font-size:.82rem;color:var(--txt-sub);margin:0;line-height:1.55">
          {backtest_count_str} Datenpunkte (bootstrap + daily) — Details im Backtesting-Panel.
          Bootstrap-Scores vereinfacht (SF + RVOL + Momentum) — nicht 1:1 mit Live-Scores vergleichbar.
          Belastbare Live-Statistiken ab Juli 2026 (60+ Tage Daily-Daten).
        </p>
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
            <p class="cl-desc">Grün bedeutet dass Leerverkäufer ihre Positionen in den letzten 2,5 Wochen ausgebaut haben — der Druck auf einen möglichen Squeeze wächst.</p>
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
  </section>

  <style>
    .bt-section{{background:var(--bg-card);border:1px solid var(--brd);border-radius:10px;
      padding:14px 16px;margin-bottom:14px;
      max-width:100%;overflow-x:hidden;box-sizing:border-box}}
    .bt-section *{{box-sizing:border-box}}
    .bt-hdr{{display:flex;align-items:center;gap:10px;margin-bottom:4px}}
    .bt-title{{font-size:1rem;font-weight:800;color:var(--txt)}}
    .bt-close{{margin-left:auto;background:none;border:none;color:var(--txt-dim);
      cursor:pointer;font-size:1.2rem;line-height:1}}
    .bt-meta{{font-size:.78rem;color:var(--txt-dim);margin:0 0 12px;line-height:1.5;
      overflow-wrap:break-word}}
    .bt-meta b{{color:var(--txt)}}
    .bt-mode{{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}}
    .bt-mode-btn{{flex:1;min-width:140px;padding:6px 10px;font-size:.78rem;
      font-weight:700;color:var(--txt-dim);background:var(--bg-met);
      border:1px solid var(--brd);border-radius:6px;cursor:pointer;
      transition:background .12s,color .12s}}
    .bt-mode-btn:hover{{color:var(--txt)}}
    .bt-mode-btn.active{{color:#fff;background:#6366f1;border-color:#4f46e5}}
    /* Mobile-first: 1 Spalte auf iPhone, 2 Spalten ab 768 px */
    .bt-grid{{display:grid;grid-template-columns:1fr;gap:12px}}
    @media (min-width:768px){{ .bt-grid{{grid-template-columns:1fr 1fr}} }}
    .bt-tile{{background:var(--bg-met);border:1px solid var(--brd);border-radius:8px;
      padding:10px 12px;min-width:0}}
    .bt-tile--wide{{grid-column:1 / -1}}
    .bt-tile-title{{font-size:.72rem;font-weight:700;color:var(--txt-dim);
      text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}}
    .bt-tile-empty{{font-size:.82rem;color:var(--txt-dim);font-style:italic;
      padding:14px 0;text-align:center}}
    /* SVG skaliert mit Containerbreite via viewBox-Aspect-Ratio (2:1) */
    .bt-chart{{width:100%;height:auto;display:block;max-height:180px}}
    .bt-chart-lbl{{font-size:.68rem;fill:var(--txt-dim)}}
    .bt-chart-val{{font-size:.7rem;font-weight:700;fill:var(--txt)}}
    .bt-bar-stack{{display:flex;flex-direction:column;gap:6px;margin-top:2px}}
    .bt-bar-row{{display:flex;align-items:center;gap:8px;font-size:.78rem}}
    .bt-bar-row--best{{font-size:.88rem}}
    .bt-bar-row--best .bt-bar-row-lbl{{color:var(--txt);font-weight:900}}
    .bt-bar-row--best .bt-bar-row-val{{font-weight:900;font-size:.95rem}}
    .bt-bar-row--best .bt-bar-row-bar{{height:14px}}
    .bt-bar-row--best .bt-bar-row-lbl::before{{content:'★ ';color:#f59e0b}}
    .bt-bar-row-lbl{{flex:0 0 62px;color:var(--txt-dim);font-weight:700}}
    .bt-bar-row-bar{{flex:1 1 auto;min-width:0;height:10px;background:var(--brd);
      border-radius:4px;position:relative;overflow:hidden}}
    .bt-bar-row-fill{{position:absolute;top:0;bottom:0;left:50%;border-radius:3px}}
    .bt-bar-row-val{{flex:0 0 70px;text-align:right;font-weight:800;font-variant-numeric:tabular-nums}}
    /* Enge iPhones: Label/Val-Spalten verschmälern, mehr Platz für den Balken */
    @media (max-width:480px){{
      .bt-bar-row{{gap:6px;font-size:.72rem}}
      .bt-bar-row-lbl{{flex:0 0 38px}}
      .bt-bar-row-val{{flex:0 0 58px}}
      .bt-bar-row--best{{font-size:.82rem}}
      .bt-bar-row--best .bt-bar-row-val{{font-size:.88rem}}
    }}
    .bt-si-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:2px}}
    .bt-si-cell{{background:var(--bg-card);border:1px solid var(--brd);border-radius:6px;
      padding:8px 6px;text-align:center}}
    .bt-si-cell-ttl{{font-size:.68rem;color:var(--txt-dim);text-transform:uppercase;
      letter-spacing:.3px;margin-bottom:4px}}
    .bt-si-cell-hr{{font-size:1.15rem;font-weight:800;line-height:1.1}}
    .bt-si-cell-med{{font-size:.78rem;font-weight:700;margin-top:2px}}
    .bt-si-cell-n{{font-size:.65rem;color:var(--txt-dim);margin-top:3px}}
    /* Tabelle: 8 Spalten sprengen iPhone-Breite → horizontal scrollbar */
    #bt-tbl-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;
      margin:0 -2px;padding:0 2px}}
    .bt-tbl{{width:100%;min-width:520px;border-collapse:collapse;font-size:.78rem;
      font-variant-numeric:tabular-nums;margin-top:2px}}
    .bt-tbl th,.bt-tbl td{{padding:5px 6px;border-bottom:1px solid var(--brd);
      text-align:right;white-space:nowrap}}
    .bt-tbl th:first-child,.bt-tbl td:first-child,
    .bt-tbl th:nth-child(2),.bt-tbl td:nth-child(2){{text-align:left}}
    .bt-tbl th{{font-size:.66rem;color:var(--txt-dim);font-weight:700;
      text-transform:uppercase;letter-spacing:.3px}}
    .bt-src-tag{{font-size:.62rem;padding:1px 5px;border-radius:3px;font-weight:700;
      text-transform:uppercase;letter-spacing:.2px}}
    .bt-src-bootstrap{{color:#94a3b8;background:#94a3b822}}
    .bt-src-daily{{color:#22c55e;background:#22c55e22}}
    .bt-hint{{display:block;margin-top:4px;font-size:.74rem;color:#f59e0b;font-style:italic}}
    .btn-bt{{background:#1e293b;color:#94a3b8;border:1px solid #334155}}
    .btn-bt:hover{{background:#334155;color:#e2e8f0}}
    .bt-reco{{margin-top:14px;padding:12px 14px;background:var(--bg-met);
      border:1px solid var(--brd);border-left:3px solid #6366f1;border-radius:6px;
      font-size:.84rem;line-height:1.55;color:var(--txt)}}
    .bt-reco-ttl{{font-weight:800;margin-bottom:4px;font-size:.9rem}}
    .bt-reco-strong{{font-weight:800}}
    .bt-reco-pos{{color:#22c55e;font-weight:800}}
    .bt-reco-neg{{color:#ef4444;font-weight:800}}
    .bt-reco-rec{{margin-top:6px;padding-top:6px;border-top:1px solid var(--brd);
      font-weight:700}}
  </style>
  <section class="bt-section" id="bt-section" hidden>
    <div class="bt-hdr">
      <span class="bt-title">Backtesting</span>
      <button class="bt-close" onclick="toggleBacktesting(false)" aria-label="Schließen">&times;</button>
    </div>
    <p class="bt-meta" id="bt-meta">Lade Daten …</p>
    <div class="bt-mode" role="tablist" aria-label="Entry-Tag">
      <button type="button" class="bt-mode-btn active" data-bt-mode="t0"
              onclick="_btSetMode('t0')">T+0 (Signal-Tag)</button>
      <button type="button" class="bt-mode-btn" data-bt-mode="t1"
              onclick="_btSetMode('t1')">T+1 (nächster Tag)</button>
    </div>
    <div class="bt-mode" role="tablist" aria-label="Datenquelle">
      <button type="button" class="bt-mode-btn active" data-bt-src="live"
              onclick="_btSetSource('live')">Nur Live (DAILY)</button>
      <button type="button" class="bt-mode-btn" data-bt-src="all"
              onclick="_btSetSource('all')">Alle (Bootstrap + Daily)</button>
    </div>
    <div class="bt-grid">
      <div class="bt-tile">
        <div class="bt-tile-title">Trefferquote je Score-Schwelle (5T +5 %)</div>
        <svg class="bt-chart" id="bt-chart-hit" viewBox="0 0 320 160"
             preserveAspectRatio="xMidYMid meet"
             aria-label="Trefferquote je Score-Schwelle"></svg>
      </div>
      <div class="bt-tile">
        <div class="bt-tile-title">Median-Rendite nach Zeithorizont</div>
        <div class="bt-bar-stack" id="bt-bars-median"></div>
      </div>
      <div class="bt-tile">
        <div class="bt-tile-title">SI-Trend Vergleich (5T-Rendite)</div>
        <div class="bt-si-grid" id="bt-si-grid"></div>
      </div>
      <div class="bt-tile bt-tile--wide">
        <div class="bt-tile-title">Letzte 20 Einträge</div>
        <div id="bt-tbl-wrap"><table class="bt-tbl" id="bt-tbl"></table></div>
      </div>
    </div>
    <div id="bt-reco" class="bt-reco" hidden></div>
  </section>

  <section class="wl-section" id="wl-section">
    <div class="wl-section-hdr">
      <span class="wl-section-title">Meine Watchlist</span>
      <span class="wl-count-badge" id="wl-count">0</span>
    </div>
    <div class="wl-add-row">
      <input type="text" id="wl-add-input" class="wl-add-input"
        placeholder="TICKER eingeben" maxlength="12"
        autocomplete="off" autocapitalize="characters" spellcheck="false"
        inputmode="latin" aria-label="Ticker zur Watchlist hinzuf&uuml;gen">
      <button type="button" id="wl-add-btn-manual" class="wl-add-btn-manual"
        onclick="wlAddManual()">+ Hinzuf&uuml;gen</button>
    </div>
    <div class="wl-add-err" id="wl-add-err" role="alert"></div>
    <p class="wl-add-hint">Manuell hinzugef&uuml;gte Ticker erscheinen beim n&auml;chsten Report-Run mit vollst&auml;ndigen Daten. Bis dahin wird der letzte bekannte Score angezeigt falls vorhanden.</p>
    <div class="wl-sync-warn" id="wl-sync-warn"></div>
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
// ── Sortierung Setup ↔ Monster ─────────────────────────────────────────────
const _SORT_KEY = 'squeeze_sort_mode';
function _applySortMode(mode){{
  const m = (mode === 'monster') ? 'monster' : 'setup';
  const grid = document.querySelector('.cards-grid');
  if (grid) {{
    const cards = Array.from(grid.querySelectorAll('article.card'));
    if (m === 'monster') {{
      cards.sort((a, b) => parseFloat(b.dataset.monster || '0') - parseFloat(a.dataset.monster || '0'));
    }} else {{
      cards.sort((a, b) => parseInt(a.dataset.setupRank || '0', 10) - parseInt(b.dataset.setupRank || '0', 10));
    }}
    cards.forEach(c => grid.appendChild(c));
  }}
  document.querySelectorAll('.score-block').forEach(sb => {{
    sb.classList.toggle('sort-monster', m === 'monster');
    sb.classList.toggle('sort-setup',   m !== 'monster');
  }});
  // Hamburger-Menü-Label + Häkchen aktualisieren
  const lbl = document.getElementById('menu-sort-current');
  if (lbl) lbl.textContent = (m === 'monster') ? 'Monster' : 'Setup';
  const cs = document.getElementById('menu-sort-check-setup');
  const cm = document.getElementById('menu-sort-check-monster');
  if (cs) cs.style.visibility = (m === 'setup')   ? 'visible' : 'hidden';
  if (cm) cm.style.visibility = (m === 'monster') ? 'visible' : 'hidden';
}}
function setSortMode(mode){{
  const m = (mode === 'monster') ? 'monster' : 'setup';
  localStorage.setItem(_SORT_KEY, m);
  _applySortMode(m);
}}
window.addEventListener('DOMContentLoaded', () => {{
  const cur = localStorage.getItem(_SORT_KEY) || 'setup';
  _applySortMode(cur);
}});
// ── Dark Mode ─────────────────────────────────────────────────────────────
(function(){{
  const saved = localStorage.getItem('theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', saved);
  window.addEventListener('DOMContentLoaded', () => {{
    const tb = document.getElementById('theme-btn');
    if (tb) tb.textContent = saved === 'dark' ? '☀️' : '🌙';
  }});
}})();
function toggleTheme(){{
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  const tb = document.getElementById('theme-btn');
  if (tb) tb.textContent = next === 'dark' ? '☀️' : '🌙';
}}
// Theme-Toggle aus dem Hamburger-Footer: ruft toggleTheme() und tauscht das
// Lucide-Icon (moon ↔ sun). Lucide ersetzt <i data-lucide> beim Mount durch
// <svg> mit gleicher id — outerHTML-Swap rebuildet das <i> für re-render.
function toggleThemeMenu(){{
  toggleTheme();
  const ic = document.getElementById('theme-icon');
  if (!ic) return;
  const cur = document.documentElement.getAttribute('data-theme');
  const next = (cur === 'dark') ? 'moon' : 'sun';
  ic.outerHTML = `<i data-lucide="${{next}}" id="theme-icon"></i>`;
  if (window.lucide) lucide.createIcons();
}}
// Initialer Icon-Stand passend zum aktuellen Theme (dark→moon, light→sun)
window.addEventListener('DOMContentLoaded', () => {{
  const ic = document.getElementById('theme-icon');
  if (!ic) return;
  const cur = document.documentElement.getAttribute('data-theme');
  const want = (cur === 'dark') ? 'moon' : 'sun';
  if (ic.getAttribute('data-lucide') !== want) {{
    ic.setAttribute('data-lucide', want);
    if (window.lucide) lucide.createIcons();
  }}
}});

// ── Hamburger-Menü ────────────────────────────────────────────────────────
function _setMenuOpen(open){{
  const drawer  = document.getElementById('menu-drawer');
  const overlay = document.getElementById('menu-overlay');
  const btn     = document.getElementById('hamburger-btn');
  if (!drawer || !overlay || !btn) return;
  drawer.classList.toggle('open', open);
  overlay.classList.toggle('open', open);
  drawer.setAttribute('aria-hidden', !open);
  overlay.setAttribute('aria-hidden', !open);
  btn.setAttribute('aria-expanded', open);
  // Hamburger-Icon zwischen menu / x wechseln
  const ic = btn.querySelector('[data-lucide]');
  if (ic) {{
    ic.setAttribute('data-lucide', open ? 'x' : 'menu');
    if (window.lucide) lucide.createIcons();
  }}
  document.body.style.overflow = open ? 'hidden' : '';
}}
function toggleMenuDrawer(force){{
  const drawer = document.getElementById('menu-drawer');
  if (!drawer) return;
  const open = (typeof force === 'boolean') ? force
             : !drawer.classList.contains('open');
  _setMenuOpen(open);
}}
function toggleMenuSort(){{
  const sub = document.getElementById('menu-sort-submenu');
  const tog = document.getElementById('menu-sort-toggle');
  const chev = document.getElementById('menu-sort-chevron');
  if (!sub || !tog) return;
  const open = sub.hasAttribute('hidden');
  if (open) sub.removeAttribute('hidden'); else sub.setAttribute('hidden', '');
  tog.setAttribute('aria-expanded', open);
  if (chev) chev.style.transform = open ? 'rotate(180deg)' : '';
}}
function selectSortMode(mode){{
  setSortMode(mode);
  // Submenu schließen, Drawer offen lassen — Auswahl ist Action im Sub-Menu.
  toggleMenuSort();
}}
function scrollToBacktesting(){{
  // Wenn Backtesting-Section kollabiert ist (hidden), zuerst öffnen.
  if (typeof toggleBacktesting === 'function') toggleBacktesting(true);
  const t = document.getElementById('bt-section');
  if (t) t.scrollIntoView({{behavior:'smooth', block:'start'}});
}}
function scrollToMethodology(){{
  // Methodik-Sektion ist standardmäßig hidden. Click im Hamburger-Menü
  // macht sie sichtbar, scrollt hin, fokussiert für a11y. Schließen via
  // hideMethodology()-Button oben rechts in der Sektion.
  const sec = document.getElementById('methodology-section');
  if (!sec) return;
  sec.removeAttribute('hidden');
  // requestAnimationFrame, damit Layout den Reveal kennt bevor wir scrollen.
  requestAnimationFrame(() => sec.scrollIntoView({{behavior:'smooth', block:'start'}}));
}}
function hideMethodology(){{
  const sec = document.getElementById('methodology-section');
  if (sec) sec.setAttribute('hidden', '');
}}
// ESC schließt Drawer
window.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') {{
    const drawer = document.getElementById('menu-drawer');
    if (drawer && drawer.classList.contains('open')) toggleMenuDrawer(false);
  }}
}});
// Sticky-Header Scroll-Schatten (>5 px)
window.addEventListener('scroll', () => {{
  const hdr = document.querySelector('.app-hdr');
  if (hdr) hdr.classList.toggle('scrolled', window.scrollY > 5);
}}, {{passive: true}});
// Lucide-Icons rendern, sobald Library + DOM bereit sind
window.addEventListener('DOMContentLoaded', () => {{
  if (window.lucide) lucide.createIcons();
}});
window.addEventListener('load', () => {{
  if (window.lucide) lucide.createIcons();
}});

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
// ── Score-Erklärung Popup ─────────────────────────────────────────────────
function _closeScorePopup(){{
  const pop = document.getElementById('score-popup');
  if (!pop) return;
  pop.classList.remove('open');
  pop._src = null;
  clearTimeout(pop._timer);
}}
function _outsideScorePopup(e){{
  const pop = document.getElementById('score-popup');
  if (!pop || !pop.classList.contains('open')) return;
  if (pop.contains(e.target)) return;
  _closeScorePopup();
}}
function showScoreExplain(el, ev){{
  if (ev) ev.stopPropagation();
  let pop = document.getElementById('score-popup');
  if (!pop){{
    pop = document.createElement('div');
    pop.id = 'score-popup';
    pop.className = 'score-popup';
    pop.addEventListener('click', (e) => e.stopPropagation());
    pop.addEventListener('mouseleave', () => {{
      if (!window.matchMedia('(pointer: coarse)').matches) _closeScorePopup();
    }});
    document.body.appendChild(pop);
  }}
  if (pop.classList.contains('open') && pop._src === el){{
    _closeScorePopup();
    return;
  }}
  const art = el.closest('article');
  if (!art) return;
  const sc = parseFloat(art.dataset.score || '0');
  const sf = parseFloat(art.dataset.sf || '0');
  const sr = parseFloat(art.dataset.sr || '0');
  const rv = parseFloat(art.dataset.rv || '0');
  const si = art.dataset.si || 'no_data';
  let rating = 'Kein relevantes Signal';
  if      (sc >= 80) rating = 'Sehr starkes Setup';
  else if (sc >= 60) rating = 'Starkes Setup';
  else if (sc >= 40) rating = 'Moderates Setup';
  else if (sc >= 15) rating = 'Schwaches Setup';
  let sfTxt = 'geringer Leerverkaufsanteil';
  if      (sf >= 30) sfTxt = 'sehr hoher Leerverkaufsanteil';
  else if (sf >= 20) sfTxt = 'hoher Leerverkaufsanteil';
  else if (sf >= 15) sfTxt = 'moderater Leerverkaufsanteil';
  let rvTxt = 'normale Aktivität heute';
  if      (rv >= 2.0) rvTxt = 'überdurchschnittliche Aktivität heute';
  else if (rv >= 1.5) rvTxt = 'leicht erhöhte Aktivität heute';
  const siMap = {{
    up:       '↑ steigend — Short Interest wächst',
    sideways: '→ seitwärts — Short Interest stabil',
    down:     '↓ fallend — Short Interest sinkt'
  }};
  const siRow = siMap[si];
  const srInt = Math.round(sr);
  let inner = '<div class="sp-head">Score ' + sc.toFixed(0) + ' — ' + rating + '</div>'
            + '<ul class="sp-list">'
            + '<li><b>Short Float ' + sf.toFixed(0) + '%</b> — ' + sfTxt + '</li>'
            + '<li><b>Days to Cover ' + srInt + 'd</b> — Leerverkäufer brauchen ' + srInt + ' Tage zum Eindecken</li>'
            + '<li><b>Volumen ' + rv.toFixed(1) + '×</b> — ' + rvTxt + '</li>';
  if (siRow) inner += '<li><b>SI-Trend</b> ' + siRow + '</li>';
  inner += '</ul><p class="sp-foot">Je höher der Score, desto größer der potenzielle Squeeze-Druck.</p>';
  pop.innerHTML = inner;
  pop._src = el;
  pop.classList.add('open');
  const r  = el.getBoundingClientRect();
  const pw = pop.offsetWidth;
  const ph = pop.offsetHeight;
  let left = r.left + r.width/2 - pw/2;
  left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
  let top  = r.bottom + 8;
  if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 8);
  pop.style.left = left + 'px';
  pop.style.top  = top  + 'px';
  clearTimeout(pop._timer);
  if (window.matchMedia('(pointer: coarse)').matches){{
    pop._timer = setTimeout(_closeScorePopup, 3000);
  }}
  setTimeout(() => document.addEventListener('click', _outsideScorePopup, {{once: true}}), 0);
}}
// ── Backtesting-Sektion ───────────────────────────────────────────────────
let _btLoaded = false;
let _btData   = null;
let _btMode   = 't0';   // 't0' (Signal-Tag) | 't1' (nächster Tag)
let _btSrc    = 'live'; // 'live' (nur daily/live) | 'all' (inkl. bootstrap)
const _BT_SRC_KEY = 'squeeze_bt_source';
function _btSetMode(mode){{
  if (mode !== 't0' && mode !== 't1') return;
  _btMode = mode;
  document.querySelectorAll('[data-bt-mode]').forEach(b => {{
    b.classList.toggle('active', b.dataset.btMode === mode);
  }});
  if (_btData) _btRender();
}}
function _btSetSource(src){{
  if (src !== 'live' && src !== 'all') return;
  _btSrc = src;
  localStorage.setItem(_BT_SRC_KEY, src);
  document.querySelectorAll('[data-bt-src]').forEach(b => {{
    b.classList.toggle('active', b.dataset.btSrc === src);
  }});
  if (_btData) _btRender();
}}
function _btFiltered(data){{
  // 'live' filtert Bootstrap-Einträge raus; 'all' liefert alle.
  return _btSrc === 'live' ? data.filter(e => e.source !== 'bootstrap') : data;
}}
function _btKeys(){{
  // Feldnamen je Modus: T+0 → return_3d / return_5d / return_10d
  //                    T+1 → return_3d_t1 / ...
  const suf = (_btMode === 't1') ? '_t1' : '';
  return {{r3: 'return_3d' + suf, r5: 'return_5d' + suf, r10: 'return_10d' + suf}};
}}
function toggleBacktesting(force){{
  const sec = document.getElementById('bt-section');
  if (!sec) return;
  const open = (force === undefined) ? sec.hasAttribute('hidden') : !!force;
  if (open){{
    sec.hidden = false;
    if (!_btLoaded){{ _btLoaded = true; _btLoad(); }}
    sec.scrollIntoView({{behavior:'smooth', block:'start'}});
  }} else {{
    sec.hidden = true;
  }}
}}
function _btLoad(){{
  const meta = document.getElementById('bt-meta');
  // Persistierte Filter-Wahl reaktivieren BEVOR der erste Render läuft.
  const stored = localStorage.getItem(_BT_SRC_KEY);
  if (stored === 'live' || stored === 'all') {{
    _btSrc = stored;
    document.querySelectorAll('[data-bt-src]').forEach(b => {{
      b.classList.toggle('active', b.dataset.btSrc === _btSrc);
    }});
  }}
  fetch('./backtest_history.json?_=' + Date.now())
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => {{
      _btData = Array.isArray(data) ? data : [];
      _btRender();
    }})
    .catch(err => {{
      meta.innerHTML = '<em>Konnte backtest_history.json nicht laden (' + err + ').</em>';
    }});
}}
function _btMedian(arr){{
  const v = arr.filter(x => x !== null && x !== undefined && !isNaN(x))
               .map(Number).sort((a,b) => a-b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m-1] + v[m]) / 2;
}}
function _btRender(){{
  const data = _btData || [];
  const meta = document.getElementById('bt-meta');
  if (!data.length){{
    meta.innerHTML = '<em>Keine Backtest-Daten verfügbar. Nach dem ersten Daily-Run oder '
      + 'einem Lauf von <code>backtest_bootstrap.py</code> erscheinen hier Statistiken.</em>';
    return;
  }}
  const nTot  = data.length;
  const nBoot = data.filter(e => e.source === 'bootstrap').length;
  const nDay  = nTot - nBoot;
  const filtered = _btFiltered(data);
  let metaHtml = '<b>' + nTot + ' Datenpunkte</b> — davon <b>' + nBoot
    + '</b> bootstrap (historisch geschätzt) + <b>' + nDay
    + '</b> daily (live gemessen). '
    + '<em>Bootstrap-Scores sind vereinfachte Schätzungen aus SF + RVOL + Momentum und '
    + 'daher nicht 1:1 mit Live-Scores vergleichbar.</em>';
  if (_btSrc === 'live' && nBoot > 0){{
    metaHtml += '<span class="bt-hint">Bootstrap-Daten ausgeblendet — '
              + 'vereinfachter Score nicht mit Live-Scores vergleichbar</span>';
  }}
  meta.innerHTML = metaHtml;

  _btRenderHitRates(filtered);
  _btRenderMedian(filtered);
  _btRenderSiTrend(filtered);
  _btRenderTable(data);    // Tabelle zeigt IMMER alle Einträge (mit Quellen-Badge).
  _btRenderRecommendation(filtered);
}}
function _btRenderHitRates(data){{
  const svg = document.getElementById('bt-chart-hit');
  const thresholds = [40, 50, 60, 70, 80];
  const rows = thresholds.map(th => {{
    const k = _btKeys();
    const slice = data.filter(e => (e.score || 0) >= th && e[k.r5] !== null && e[k.r5] !== undefined);
    const n   = slice.length;
    const hit = slice.filter(e => e[k.r5] >= 5.0).length;
    return {{th, n, rate: n ? hit / n : null}};
  }});
  const W = 320, H = 160, PAD_L = 28, PAD_R = 8, PAD_T = 10, PAD_B = 30;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const barW  = plotW / thresholds.length * 0.70;
  const gap   = plotW / thresholds.length * 0.30;
  let body = '';
  // Y-Gridlines at 25/50/75/100 %
  for (const gy of [0, 25, 50, 75, 100]){{
    const y = PAD_T + plotH * (1 - gy/100);
    body += '<line x1="' + PAD_L + '" x2="' + (W-PAD_R) + '" y1="' + y + '" y2="' + y
          + '" stroke="var(--brd)" stroke-width="0.5"/>';
    body += '<text class="bt-chart-lbl" x="' + (PAD_L-4) + '" y="' + (y+3) + '" '
          + 'text-anchor="end">' + gy + '</text>';
  }}
  rows.forEach((r, i) => {{
    const x = PAD_L + i * (plotW / thresholds.length) + gap/2;
    if (r.rate === null){{
      // Grauer Placeholder
      body += '<rect x="' + x + '" y="' + (PAD_T+plotH-4) + '" width="' + barW
            + '" height="4" fill="var(--brd)"/>';
    }} else {{
      const h  = plotH * r.rate;
      const y  = PAD_T + plotH - h;
      const pct = r.rate * 100;
      const col = pct > 65 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';
      body += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + h
            + '" fill="' + col + '" rx="2"/>';
      body += '<text class="bt-chart-val" x="' + (x+barW/2) + '" y="' + (y-3) + '" '
            + 'text-anchor="middle">' + pct.toFixed(0) + '%</text>';
    }}
    const lx = PAD_L + i * (plotW/thresholds.length) + (plotW/thresholds.length)/2;
    body += '<text class="bt-chart-lbl" x="' + lx + '" y="' + (H-PAD_B+14)
          + '" text-anchor="middle">≥' + r.th + '</text>';
    body += '<text class="bt-chart-lbl" x="' + lx + '" y="' + (H-PAD_B+26)
          + '" text-anchor="middle">n=' + r.n + '</text>';
  }});
  svg.innerHTML = body;
}}
function _btBucketStats(data){{
  // Score-Buckets × 3 Horizonte → medians + n für beide Kacheln + Empfehlung
  const buckets = [
    {{key:'<50',   pred: e => (e.score || 0) < 50}},
    {{key:'50–69', pred: e => (e.score || 0) >= 50 && (e.score || 0) < 70}},
    {{key:'≥70',   pred: e => (e.score || 0) >= 70}},
  ];
  const k = _btKeys();
  const horizons = [['3T', k.r3], ['5T', k.r5], ['10T', k.r10]];
  return buckets.map(b => {{
    const slice = data.filter(b.pred);
    const meds = horizons.map(([lbl, key]) => {{
      const vals = slice.map(e => e[key])
                        .filter(v => v !== null && v !== undefined);
      const med = _btMedian(vals);
      return {{lbl, key, med, n: vals.length}};
    }});
    // Best = höchster Median mit mind. 1 Datenpunkt; null/keine Daten zählen nicht
    let bestIdx = -1;
    let bestVal = -Infinity;
    meds.forEach((m, i) => {{
      if (m.med !== null && m.n > 0 && m.med > bestVal){{
        bestVal = m.med;
        bestIdx = i;
      }}
    }});
    return {{key: b.key, n: slice.length, meds, bestIdx}};
  }});
}}
function _btRenderMedian(data){{
  const stats = _btBucketStats(data);
  const container = document.getElementById('bt-bars-median');
  let html = '';
  stats.forEach(s => {{
    html += '<div style="font-size:.72rem;color:var(--txt-dim);font-weight:700;margin-top:4px">'
          + 'Score ' + s.key + ' <span style="font-weight:400">(n=' + s.n + ')</span></div>';
    s.meds.forEach((m, i) => {{
      const med = m.med;
      const pct = med === null ? 0 : Math.max(-30, Math.min(30, med));
      const fillW = Math.abs(pct) / 30 * 50;
      const col  = med === null ? 'var(--brd)' : (med >= 0 ? '#22c55e' : '#ef4444');
      const side = med === null || med >= 0 ? 'left:50%' : ('left:' + (50-fillW) + '%');
      const cls  = (i === s.bestIdx) ? ' bt-bar-row--best' : '';
      html += '<div class="bt-bar-row' + cls + '">'
            + '<span class="bt-bar-row-lbl">' + m.lbl + '</span>'
            + '<span class="bt-bar-row-bar">'
            + '<span class="bt-bar-row-fill" style="' + side
            + ';width:' + fillW + '%;background:' + col + '"></span>'
            + '</span>'
            + '<span class="bt-bar-row-val" style="color:' + col + '">'
            + (med === null ? '—' : (med >= 0 ? '+' : '') + med.toFixed(1) + '%')
            + '</span></div>';
    }});
  }});
  container.innerHTML = html;
}}
function _btRenderRecommendation(data){{
  const box = document.getElementById('bt-reco');
  if (!box) return;
  const stats = _btBucketStats(data);
  // Globaler Sieger: (bucket, horizon) mit höchster Median-Rendite, n ≥ 5
  let best = null;
  stats.forEach(s => {{
    s.meds.forEach(m => {{
      if (m.med !== null && m.n >= 5 && (!best || m.med > best.med)){{
        best = {{bucket: s.key, lbl: m.lbl, med: m.med, n: m.n,
                 bucketMeds: s.meds}};
      }}
    }});
  }});
  if (!best || best.med <= 0){{
    box.hidden = false;
    box.innerHTML = '<div class="bt-reco-ttl">Erste Erkenntnisse</div>'
      + '<p>Noch zu wenige Datenpunkte mit positiver Median-Rendite für '
      + 'eine belastbare Handlungsempfehlung (Mindest-n=5 pro Score-Bucket).</p>';
    return;
  }}
  // Vergleich: 10T-Median im selben Bucket
  const tenT = best.bucketMeds.find(m => m.lbl === '10T');
  const fmtPct = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  const posCls = v => v >= 0 ? 'bt-reco-pos' : 'bt-reco-neg';

  let comparison = '';
  if (tenT && tenT.med !== null && best.lbl !== '10T'){{
    if (tenT.med < best.med - 1){{
      comparison = ' Längere Haltedauer (10T) liegt bei '
                 + '<span class="' + posCls(tenT.med) + '">' + fmtPct(tenT.med)
                 + '</span> — Squeezes erschöpfen sich schnell.';
    }} else if (tenT.med > best.med){{
      comparison = ' Längere Haltedauer (10T) erhöht die Rendite weiter auf '
                 + '<span class="' + posCls(tenT.med) + '">' + fmtPct(tenT.med)
                 + '</span>.';
    }} else {{
      comparison = ' Längere Haltedauer (10T) bringt kaum Unterschied ('
                 + '<span class="' + posCls(tenT.med) + '">' + fmtPct(tenT.med)
                 + '</span>).';
    }}
  }}

  const rec = 'Empfehlung: Score ' + best.bucket
            + ' + maximale Haltedauer ' + best.lbl + '.';

  box.hidden = false;
  box.innerHTML =
    '<div class="bt-reco-ttl">Erste Erkenntnisse</div>'
    + '<p>Bei <span class="bt-reco-strong">Score ' + best.bucket
    + '</span> erzielte die <span class="bt-reco-strong">' + best.lbl
    + '-Haltestrategie</span> eine Median-Rendite von '
    + '<span class="' + posCls(best.med) + '">' + fmtPct(best.med) + '</span> '
    + '(n=' + best.n + ').' + comparison + '</p>'
    + '<p class="bt-reco-rec">' + rec + '</p>';
}}
function _btRenderSiTrend(data){{
  const trends = [['up','↑ steigend'], ['sideways','→ seitwärts'], ['down','↓ fallend']];
  const container = document.getElementById('bt-si-grid');
  container.innerHTML = trends.map(([key, lbl]) => {{
    const kk = _btKeys();
    const slice = data.filter(e => e.si_trend === key
                                && e[kk.r5] !== null && e[kk.r5] !== undefined);
    const n   = slice.length;
    const hit = slice.filter(e => e[kk.r5] >= 5.0).length;
    const rate = n ? hit / n * 100 : null;
    const med  = _btMedian(slice.map(e => e[kk.r5]));
    const rateCol = rate === null ? 'var(--txt-dim)'
                 : (rate > 65 ? '#22c55e' : rate >= 50 ? '#f59e0b' : '#ef4444');
    const medCol = med === null ? 'var(--txt-dim)' : (med >= 0 ? '#22c55e' : '#ef4444');
    return '<div class="bt-si-cell">'
         + '<div class="bt-si-cell-ttl">' + lbl + '</div>'
         + '<div class="bt-si-cell-hr" style="color:' + rateCol + '">'
         + (rate === null ? '—' : rate.toFixed(0) + '%') + '</div>'
         + '<div class="bt-si-cell-med" style="color:' + medCol + '">'
         + (med === null ? '—' : (med >= 0 ? '+' : '') + med.toFixed(1) + '% Median')
         + '</div>'
         + '<div class="bt-si-cell-n">n=' + n + '</div>'
         + '</div>';
  }}).join('');
}}
function _btRenderTable(data){{
  const k = _btKeys();
  // Sortiere nach Datum absteigend (DD.MM.YYYY parsen)
  const parsed = data.map(e => {{
    const m = (e.date || '').match(/^(\\d{{2}})\\.(\\d{{2}})\\.(\\d{{4}})$/);
    const sortKey = m ? (m[3] + m[2] + m[1]) : '';
    return {{...e, _sk: sortKey}};
  }}).sort((a,b) => b._sk.localeCompare(a._sk)).slice(0, 20);
  const tbl = document.getElementById('bt-tbl');
  const head = '<thead><tr>'
             + '<th>Ticker</th><th>Datum</th><th>Score</th><th>Entry</th>'
             + '<th>R 3T</th><th>R 5T</th><th>R 10T</th><th>Quelle</th>'
             + '</tr></thead>';
  const fmtR = v => {{
    if (v === null || v === undefined) return '<span style="color:var(--txt-dim)">—</span>';
    const col = v > 0 ? '#22c55e' : v < 0 ? '#ef4444' : 'var(--txt-dim)';
    const sign = v > 0 ? '+' : '';
    return '<span style="color:' + col + '">' + sign + v.toFixed(1) + '%</span>';
  }};
  const fmtSrc = s => {{
    const cls = s === 'bootstrap' ? 'bt-src-bootstrap' : 'bt-src-daily';
    const txt = s === 'bootstrap' ? 'bootstrap' : 'daily';
    return '<span class="bt-src-tag ' + cls + '">' + txt + '</span>';
  }};
  const rows = parsed.map(e =>
    '<tr>'
    + '<td><b>' + (e.ticker || '—') + '</b></td>'
    + '<td>' + (e.date || '—') + '</td>'
    + '<td>' + ((e.score ?? 0).toFixed(1)) + '</td>'
    + '<td>$' + ((e.entry_price ?? 0).toFixed(2)) + '</td>'
    + '<td>' + fmtR(e[k.r3]) + '</td>'
    + '<td>' + fmtR(e[k.r5]) + '</td>'
    + '<td>' + fmtR(e[k.r10]) + '</td>'
    + '<td>' + fmtSrc(e.source || 'daily') + '</td>'
    + '</tr>'
  ).join('');
  tbl.innerHTML = head + '<tbody>' + rows + '</tbody>';
}}
// ── GitHub Actions Config ─────────────────────────────────────────────────
const GH_OWNER    = 'easywebb911';
const GH_REPO     = 'Aktien-Update';
const GH_WORKFLOW    = 'daily-squeeze-report.yml';
const GH_WORKFLOW_KI = 'ki_agent.yml';
const GH_BRANCH   = 'main';
const TOK_KEY     = 'ghpat_squeeze';
// Gist-ID: vom Workflow zur Render-Zeit per env-Variable injiziert.
// Leerer String → kein Gist konfiguriert → JS-Position-Panel zeigt Hinweis.
const GIST_ID     = '{gist_id_js}';
const GIST_FILE   = 'squeeze_data.json';
// ─────────────────────────────────────────────────────────────────────────
function reloadPage(){{
  const btn = document.getElementById('btn-reload');
  if (btn) {{ btn.disabled = true; btn.textContent = 'Lädt…'; }}
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
  if (btn) {{ btn.disabled = true; btn.innerHTML = 'Startet…'; }}
  // _pollStart MUSS vor dem Dispatch gesetzt werden, damit der server-
  // seitige created_at des neuen Runs (entsteht *während* des fetch)
  // garantiert >= _pollStart-15000ms ist und vom find()-Predikat erfasst wird.
  _pollStart = Date.now(); _pollToken = token; _noRunPolls = 0;
  console.log(`[Recalculate] _pollStart=${{_pollStart}} (${{new Date(_pollStart).toISOString()}})`);
  try {{
    const r = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{GH_WORKFLOW}}/dispatches`,
      {{method:'POST',headers:{{'Authorization':`Bearer ${{token}}`,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}},
        body:JSON.stringify({{ref:GH_BRANCH}})}}
    );
    const _dispatchBody = await r.clone().text().catch(()=>'');
    console.log(`[Recalculate] Dispatch HTTP ${{r.status}} body:`, _dispatchBody || '(leer)');
    if (r.status === 204) {{
      _pollWorkflowId = GH_WORKFLOW; _pollRunningLabel = 'Neuberechnung';
      _pollEnableBtn = _enableRecalcBtn; _pollOnSuccess = _startSuccessCountdown;
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
  // _pollStart MUSS vor dem Dispatch gesetzt werden \u2014 siehe dispatchWorkflow.
  _pollStart = Date.now(); _pollToken = token; _noRunPolls = 0;
  console.log(`[KI-Agent] _pollStart=${{_pollStart}} (${{new Date(_pollStart).toISOString()}})`);
  try {{
    const r = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{GH_WORKFLOW_KI}}/dispatches`,
      {{method:'POST',headers:{{'Authorization':`Bearer ${{token}}`,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'}},
        body:JSON.stringify({{ref:GH_BRANCH}})}}
    );
    const _dispatchBody = await r.clone().text().catch(()=>'');
    console.log(`[KI-Agent] Dispatch HTTP ${{r.status}} body:`, _dispatchBody || '(leer)');
    if (r.status === 204) {{
      _pollWorkflowId = GH_WORKFLOW_KI; _pollRunningLabel = 'KI-Agent';
      _pollEnableBtn = _enableKiBtn; _pollOnSuccess = _kiAgentSuccess;
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
  // app_data.json statt agent_signals.json — ein Fetch liefert beide Datensätze
  fetch('./app_data.json?_=' + Date.now())
    .then(r => r.ok ? r.json() : {{}})
    .then(appData => {{
      const data = appData.agent_signals || appData;  // Backwards-compat
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
const NO_RUN_MAX = 20;
let _pollStart = null, _pollToken = null, _pollTimer = null;
let _timeInterval = null;
let _pendingDispatch = null;
let _pollWorkflowId = GH_WORKFLOW, _pollRunningLabel = 'Neuberechnung';
let _pollEnableBtn = null, _pollOnSuccess = null;
let _noRunPolls = 0;
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
  if (btn) {{ btn.disabled=false; btn.innerHTML='&#9881; Recalculate'; }}
}}
function _showPollStatus(state, msg){{
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
    el.innerHTML='<span class="poll-dot poll-dot-err"></span>';
    el.appendChild(document.createTextNode(msg || 'Workflow fehlgeschlagen — bitte GitHub Actions prüfen.'));
  }} else if (state==='timeout'){{
    _stopTimeInterval();
    el.className='amsg amsg-error';
    el.textContent = msg || 'Zeitüberschreitung — bitte Seite manuell neu laden.';
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
  const _elapsedS = Math.floor((Date.now()-_pollStart)/1000);
  if (Date.now()-_pollStart>TIMEOUT_MS) {{
    console.log(`[Poll] Timeout nach ${{_elapsedS}}s — workflow=${{_pollWorkflowId}}`);
    _showPollStatus('timeout'); if(_pollEnableBtn)_pollEnableBtn(); return;
  }}
  try {{
    const res = await fetch(
      `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/actions/workflows/${{_pollWorkflowId}}/runs?per_page=5&event=workflow_dispatch`,
      {{headers:{{'Authorization':`Bearer ${{_pollToken}}`,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}}}}
    );
    console.log(`[Poll] HTTP ${{res.status}} elapsed=${{_elapsedS}}s workflow=${{_pollWorkflowId}}`);
    if (res.status !== 200) {{
      const _errBody = await res.text().catch(()=>'');
      console.log(`[Poll] !ok body:`, _errBody.slice(0,200));
      const _hint = (res.status===401||res.status===403) ? ' (Token-Scope?)'
                  : (res.status===429) ? ' (Rate-Limit)'
                  : '';
      _showPollStatus('failure', `Polling-Fehler: HTTP ${{res.status}}${{_hint}}`);
      if(_pollEnableBtn)_pollEnableBtn();
      return;
    }}
    const data = await res.json();
    const _runs = data.workflow_runs||[];
    // Fenster: 3 min — GH-Runner starten oft 30–60s nach dem Dispatch.
    const _threshold = _pollStart - 180000;
    const _runDump = _runs.map(w => {{
      const _ts = new Date(w.created_at).getTime();
      return `id=${{w.id}} status=${{w.status}} conclusion=${{w.conclusion}} created_at=${{w.created_at}} delta=${{Math.round((_ts-_pollStart)/1000)}}s matches=${{_ts>=_threshold}}`;
    }});
    console.log(`[Poll] ${{_runs.length}} runs zurück (threshold=_pollStart-3min):`, _runDump);
    const run = _runs.find(w=>new Date(w.created_at).getTime()>=_threshold);
    console.log(`[Poll] find() →`, run ? `id=${{run.id}} status=${{run.status}} conclusion=${{run.conclusion}}` : '(keiner — Run noch nicht erschienen oder zu alt)');
    if (!run) {{
      _noRunPolls++;
      console.log(`[Poll] kein Run gefunden — Versuch ${{_noRunPolls}}/${{NO_RUN_MAX}}`);
      if (_noRunPolls >= NO_RUN_MAX) {{
        _showPollStatus('failure', `Kein Workflow-Run nach ${{_noRunPolls}} Versuchen gefunden`);
        if(_pollEnableBtn)_pollEnableBtn();
        return;
      }}
      _pollTimer=setTimeout(_doPoll,POLL_MS); return;
    }}
    if (run.status==='completed'){{
      console.log(`[Poll] Run ${{run.id}} completed — conclusion=${{run.conclusion}} → ${{run.conclusion==='success'?'success path':'failure path'}}`);
      if (run.conclusion==='success') {{ _stopTimeInterval(); if(_pollOnSuccess)_pollOnSuccess(); }}
      else {{
        _showPollStatus('failure', `Workflow fehlgeschlagen: ${{run.conclusion}}`);
        if(_pollEnableBtn)_pollEnableBtn();
      }}
    }} else {{
      _pollTimer=setTimeout(_doPoll,POLL_MS);
    }}
  }} catch(e) {{
    console.log(`[Poll] Exception (elapsed ${{_elapsedS}}s):`, e.message);
    _showPollStatus('failure', `Polling-Exception: ${{e.message}}`);
    if(_pollEnableBtn)_pollEnableBtn();
  }}
}}
function resetToken(){{
  // Defensiv: Bestätigung verhindert versehentlichen Token-Verlust falls
  // die Funktion künftig wieder von einem Button mit mehrdeutigem Icon
  // (z. B. Refresh-Pfeil) getriggert wird. Drawer-Footer-Button wurde
  // wegen Mistap-Risiko entfernt; Reset weiterhin via Settings-Panel
  // (clearGhToken-Link).
  if (!confirm('GitHub-Token wirklich löschen?')) return;
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

// ── Non-trading-day status (inline neben Zeitstempel) ────────────────────────
// Dezent in der Top-Bar statt prominentes orange Banner: kleines Icon +
// Kurzform „Mo 04.05. Handel". Vollständiges Datum im title-Tooltip.
(function(){{
  const today = new Date();
  today.setHours(0,0,0,0);
  if (!_isNonTradingDay(today)) return;
  const ntd = _nextTradingDay(today);
  const el  = document.getElementById('hdr-nontrading');
  if (!el) return;
  const wd  = ['So','Mo','Di','Mi','Do','Fr','Sa'][ntd.getDay()];
  const dd  = String(ntd.getDate()).padStart(2,'0');
  const mm  = String(ntd.getMonth()+1).padStart(2,'0');
  el.textContent = `\u26a0 ${{wd}} ${{dd}}.${{mm}}. Handel`;
  el.title = `N\xe4chster US-Handelstag: ${{_fmtGerman(ntd)}}`;
  el.hidden = false;
}})();
// ─────────────────────────────────────────────────────────────────────────────

// ── Sparkline renderer ────────────────────────────────────────────────────────
(function(){{
  const isMobile = ('ontouchstart' in window) || (window.matchMedia('(pointer:coarse)').matches);
  const DAYS_DE  = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  const H        = 60;
  const PAD_X    = 10;
  const PAD_Y    = 8;
  const PT_R     = isMobile ? 6 : 5;

  function parseIso(s) {{ return new Date(s + 'T12:00:00'); }}

  // Per-point color by score threshold — identical palette to ticker-dot
  // (.agent-dot strong/moderate/weak/none): grün / orange / rot / grau.
  // Schwellen aus config.py (KI_DOT_STRONG/MODERATE/WEAK), damit Endpunkt-
  // Farbe und pulsierender Dot immer im selben Score-Band liegen.
  function scoreColor(s) {{
    if (s == null || isNaN(+s)) return '#6b7280';
    if (s >= {KI_DOT_STRONG})    return '#22c55e';
    if (s >= {KI_DOT_MODERATE})  return '#f59e0b';
    if (s >= {KI_DOT_WEAK})      return '#ef4444';
    return '#6b7280';
  }}

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

    // Sync rightmost point mit aktuellem KI-Agent-Score (≤ 4 h alt) damit
    // pulsierender Punkt und Sparkline-Endpunkt dieselbe Farbe + Wert zeigen.
    // Bei Ghost-Pfad (heute > letztes History-Datum): neuen Punkt anhängen,
    // sonst rechtester History-Eintrag in-place überschreiben.
    // Ticker-Lookup robust: ``data-ticker`` ist sowohl auf TopTen-
    // ``<article>`` als auch auf Watchlist-``<div class="wl-card">``
    // gesetzt — ein einziger ``closest('[data-ticker]')`` deckt beide Pfade ab.
    const _agData = window._AGENT_SIGNALS;
    if (_agData && _agData.updated) {{
      const _ageMs = Date.now() - new Date(_agData.updated).getTime();
      if (_ageMs >= 0 && _ageMs <= 4 * 3600 * 1000) {{
        const _host   = wrap.closest('[data-ticker]');
        const _ticker = _host ? _host.dataset.ticker : null;
        const _sig = (_ticker && _agData.signals) ? _agData.signals[_ticker] : null;
        if (_sig && _sig.score != null && !isNaN(+_sig.score)) {{
          const _ag = +_sig.score;
          if (scores.length > 0 && todayS && todayS > dates[dates.length - 1]) {{
            // Ghost-Pfad: heute fehlt in History → neuen Datenpunkt anhängen
            scores.push(_ag);
            dates.push(todayS);
          }} else if (scores.length > 0) {{
            // Letzter History-Eintrag = heute (oder ≤ heute) → überschreiben
            scores[scores.length - 1] = _ag;
          }}
        }}
      }}
    }}

    const n       = scores.length;
    if (n < 2) return;

    const svgWrap  = wrap.querySelector('.spark-svg-wrap');
    const daysWrap = wrap.querySelector('.spark-days');
    if (!svgWrap) return;

    const W = wrap.clientWidth || 280;

    const dateParsed = dates.map(parseIso);

    // Ghost dot: show if today is strictly after the last recorded date
    const hasGhost  = todayS && todayS > dates[n - 1];
    const ghostDate = hasGhost ? parseIso(todayS) : null;

    // X = Index (evenly spread left→right, like a stock chart)
    const xDenom = hasGhost ? n : Math.max(n - 1, 1);
    function xOf(i) {{
      return (i / xDenom) * (W - 2 * PAD_X) + PAD_X;
    }}

    const minS  = Math.min(...scores);
    const maxS  = Math.max(...scores);
    const range = maxS - minS || 1;

    // Y = Score (high score = top, low score = bottom)
    function yOf(val) {{
      return H - PAD_Y - ((val - minS) / range) * (H - 2 * PAD_Y);
    }}

    // Build area fill (continuous, no gaps) and stroke path (with gaps)
    let areaD = '', lineD = '', newSeg = true;
    for (let i = 0; i < n; i++) {{
      const cx = xOf(i).toFixed(1);
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
    const x0 = xOf(0).toFixed(1);
    const xN = xOf(n - 1).toFixed(1);
    areaD += ` L${{xN}},${{(H - PAD_Y).toFixed(1)}} L${{x0}},${{(H - PAD_Y).toFixed(1)}} Z`;

    const svgId = 'sp' + Math.random().toString(36).slice(2, 7);

    // Real data circles — each point coloured by its own score value
    let circlesHtml = '';
    for (let i = 0; i < n; i++) {{
      const cx  = xOf(i).toFixed(1);
      const cy  = yOf(scores[i]).toFixed(1);
      const dow = DAYS_DE[dateParsed[i].getDay()];
      const dd  = dates[i].slice(8, 10) + '.' + dates[i].slice(5, 7);
      const ptCol = scoreColor(scores[i]);
      circlesHtml += `<circle class="sp-dot" cx="${{cx}}" cy="${{cy}}" r="${{PT_R}}" fill="${{ptCol}}" stroke="var(--bg-card)" stroke-width="1.5" data-score="${{scores[i]}}" data-label="${{dow}} ${{dd}} · ${{scores[i]}} Pkt"/>`;
    }}

    // Ghost dot — gray, no connecting line
    let ghostHtml = '';
    if (hasGhost) {{
      const cx = xOf(n).toFixed(1);
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
  <path d="${{lineD}}" fill="none" stroke="#6b7280" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  ${{circlesHtml}}${{ghostHtml}}
</svg>`;
    svgWrap.innerHTML = svg;

    // Day labels under each point
    if (daysWrap) {{
      daysWrap.innerHTML = '';
      for (let i = 0; i < n; i++) {{
        const pct = (xOf(i) / W * 100).toFixed(1);
        const lbl = document.createElement('span');
        lbl.className = 'spark-day-lbl';
        lbl.style.left = pct + '%';
        lbl.textContent = DAYS_DE[dateParsed[i].getDay()];
        daysWrap.appendChild(lbl);
      }}
      if (hasGhost) {{
        const pct = (xOf(n) / W * 100).toFixed(1);
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
    // Globale Referenz für drawSparkline — synchronisiert den rechtesten
    // Punkt mit dem aktuellen KI-Agent-Score (gleiche Farbe wie pulsierender Dot).
    window._AGENT_SIGNALS = data || {{}};
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
      // Active tickers, sortiert nach Score absteigend (höchster zuerst).
      // Aus signals-Dict; tickers ohne Score oder mit 0 filtern.
      const MAX_IN_BAR = 3;
      const colorDot = (sc) => sc >= 70 ? '🟢'
                             : sc >= 40 ? '🟠'
                             : sc >= 15 ? '🔴'
                             : '⚪';
      const topActive = Object.entries(signals)
        .map(([t, s]) => {{
          const r = (s && s.rvol != null) ? +s.rvol : 0;
          const rvolMarker = r >= 5 ? ` 🚀 ${{r.toFixed(1)}}×`
                           : r >= 3 ? ` ⚡ ${{r.toFixed(1)}}×`
                           : '';
          return {{
            t,
            score: (s && s.score != null) ? +s.score : 0,
            // Fix 3 — StockTwits-Marker: Bonus ≥ 8 → 📣 in Statuszeile
            stMarker: (s && s.stocktwits && s.stocktwits.pts >= 8) ? ' 📣 StockTwits bullisch' : '',
            rvolMarker,
            rvolEmoji: r >= 5 ? ' 🚀' : r >= 3 ? ' ⚡' : '',
          }};
        }})
        .filter(x => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, Math.max(nSignals, 0));
      let signalPart;
      if (nSignals === 0 || topActive.length === 0) {{
        signalPart = `${{nSignals}} Signale aktiv`;
      }} else if (nSignals === 1) {{
        const s = topActive[0];
        signalPart = `1 Signal aktiv: ${{s.t}} ${{colorDot(s.score)}} ${{Math.round(s.score)}}/100${{s.stMarker}}${{s.rvolMarker}}`;
      }} else {{
        const shown = topActive.slice(0, MAX_IN_BAR);
        const rest  = Math.max(0, nSignals - shown.length);
        const list  = shown.map(s => `${{s.t}} ${{Math.round(s.score)}}${{s.stMarker ? ' 📣' : ''}}${{s.rvolEmoji}}`).join(', ');
        signalPart = `${{nSignals}} Signale aktiv: ${{list}}`
                   + (rest > 0 ? ` +${{rest}} weitere` : '');
      }}
      if (ageMin > 45) {{
        if (statusEl) statusEl.textContent =
          `\u26a1 KI-Agent: Scan verz\u00f6gert \u2014 letzter Stand ${{lastScan}} Uhr`;
      }} else {{
        if (statusEl) statusEl.textContent =
          `\u26a1 KI-Agent: Letzter Scan ${{lastScan}} Uhr \u2014 ${{phase}} \u2014 ${{signalPart}}`;
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
      // Schwellen aus config.py (KI_DOT_STRONG/MODERATE/WEAK) — gekoppelt an
      // apply_monster_score-Semantik: KI ≥ {KI_DOT_STRONG} → Monster ×1.20.
      if (score >= {KI_DOT_STRONG})        dotClass = 'strong';   // grün, schnell (1s)
      else if (score >= {KI_DOT_MODERATE}) dotClass = 'moderate'; // orange, mittel (1.5s)
      else if (score >= {KI_DOT_WEAK})     dotClass = 'weak';     // rot, langsam (2s)
      else                                  dotClass = 'none';     // grau, kein Pulsieren
      dot.className = 'agent-dot ' + dotClass;

      const driver = (sig && sig.drivers) || '?';
      const phaseTip = info.market_phase || '?';
      const lastScanTip = updated
        ? updated.toLocaleTimeString('de-DE', {{hour:'2-digit', minute:'2-digit'}}) + ' Uhr'
        : '?';
      const tip = document.createElement('span');
      tip.className = 'agent-tooltip';
      // StockTwits-Suffix (Fix 1) \u2014 sichtbar nur wenn aussagekr\u00e4ftige Stichprobe
      let stTip = '';
      if (sig && sig.stocktwits && sig.stocktwits.bull_ratio != null) {{
        const stPct = Math.round(sig.stocktwits.bull_ratio * 100);
        const stMs  = sig.stocktwits.msg_per_h || 0;
        const stP   = sig.stocktwits.pts || 0;
        const stSign = stP > 0 ? '+' : '';
        stTip = ` \u2014 StockTwits: ${{stPct}}% bullisch \u00b7 ${{stMs}} Nachrichten/h`
              + (stP !== 0 ? ` \u00b7 ${{stSign}}${{stP}} Pkt` : '');
      }}
      // RVOL-Suffix \u2014 immer anzeigen falls Daten vorhanden, Marker nur \u2265 3\u00d7
      let rvTip = '';
      if (sig && sig.rvol != null && +sig.rvol > 0) {{
        const rv = +sig.rvol;
        const rvMark = rv >= 5 ? ' \u00b7 🚀 Massives Volumen'
                     : rv >= 3 ? ' \u00b7 \u26a1 Extremes Volumen'
                     : '';
        rvTip = ` \u2014 RVOL: ${{rv.toFixed(1)}}\u00d7${{rvMark}}`;
      }}
      tip.textContent = `KI-Agent Score: ${{score}}/100 \u2014 ${{driver}} \u2014 ${{phaseTip}} \u2014 ${{lastScanTip}}${{stTip}}${{rvTip}}`;
      dot.appendChild(tip);

      // position:fixed → Koordinaten via getBoundingClientRect berechnen,
      // damit der Tooltip nicht durch .card (overflow:hidden) abgeschnitten wird
      const positionTip = () => {{
        const rect = dot.getBoundingClientRect();
        tip.style.left = (rect.left + rect.width / 2) + 'px';
        tip.style.top  = (rect.top - 6) + 'px';
      }};
      dot.addEventListener('mouseenter', positionTip);

      // iPhone: Antippen zeigt Tooltip für 3s
      dot.addEventListener('click', function(e) {{
        e.stopPropagation();
        positionTip();
        dot.classList.add('touch-visible');
        setTimeout(() => dot.classList.remove('touch-visible'), 3000);
      }});

      tickerSpan.parentNode.insertBefore(dot, tickerSpan.nextSibling);

      // Watchlist-Kompaktkarte: dot synchronisieren
      const wlDot = document.getElementById('wlkd-' + ticker);
      if (wlDot) wlDot.className = 'wl-ki-dot agent-dot ' + dotClass;

      // Fix 2 — StockTwits-Zeile in Detail-Tabelle dynamisch ein-/ausblenden.
      // Server-Rendering kennt die Daten nicht (Async-Fetch nach Page-Load),
      // daher wird die Zeile nach Agent-Daten-Eingang in die bestehende Tabelle
      // injiziert (oder entfernt wenn keine Daten).
      const detailTbl = card.querySelector('.detail-table');
      if (detailTbl) {{
        let stRow = detailTbl.querySelector('.detail-st-row');
        const st = sig && sig.stocktwits;
        if (st && st.bull_ratio != null && st.n_total >= 3) {{
          const stPct = Math.round(st.bull_ratio * 100);
          const stCol = st.bull_ratio > 0.60 ? '#22c55e'
                      : st.bull_ratio < 0.40 ? '#ef4444'
                      : '#94a3b8';
          const stLabel = st.bull_ratio > 0.60 ? 'bullisch'
                        : st.bull_ratio < 0.40 ? 'bearisch'
                        : 'neutral';
          const cellHtml = '<td>StockTwits Sentiment</td>'
            + '<td style="color:' + stCol + ';font-weight:700">'
            + stPct + '% ' + stLabel
            + ' <span style="color:var(--txt-dim);font-weight:400">('
            + st.n_total + ' Nachrichten)</span></td>';
          if (stRow) {{
            stRow.innerHTML = cellHtml;
          }} else {{
            stRow = document.createElement('tr');
            stRow.className = 'detail-st-row';
            stRow.innerHTML = cellHtml;
            detailTbl.appendChild(stRow);
          }}
        }} else if (stRow) {{
          stRow.remove();   // Daten verschwunden → Zeile auch
        }}

        // RVOL-Zeile aus agent_signals.json — gleiches Inject-Muster wie StockTwits.
        let rvRow = detailTbl.querySelector('.detail-rvol-row');
        const rv  = (sig && sig.rvol != null) ? +sig.rvol : null;
        if (rv != null && rv > 0) {{
          const rvCol = rv >= 3   ? '#22c55e'
                      : rv >= 1.5 ? '#f59e0b'
                      :             '#94a3b8';
          const rvMark = rv >= 5 ? ' 🚀'
                       : rv >= 3 ? ' ⚡'
                       : '';
          const rvCell = '<td>Rel. Volumen (KI-Agent)</td>'
            + '<td style="color:' + rvCol + ';font-weight:700">'
            + rv.toFixed(1) + '×' + rvMark + '</td>';
          if (rvRow) {{
            rvRow.innerHTML = rvCell;
          }} else {{
            rvRow = document.createElement('tr');
            rvRow.className = 'detail-rvol-row';
            rvRow.innerHTML = rvCell;
            detailTbl.appendChild(rvRow);
          }}
        }} else if (rvRow) {{
          rvRow.remove();
        }}
      }}

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

    // Re-draw aller Sparklines, damit der rechteste Punkt mit dem aktuellen
    // KI-Agent-Score synchronisiert ist (gleiche Farbe wie pulsierender Dot).
    if (typeof drawSparkline === 'function') {{
      document.querySelectorAll('.spark-wrap').forEach(drawSparkline);
    }}
  }}

  // Commit 3: ein fetch auf app_data.json liefert score_history + agent_signals
  // + watchlist_cards (vollständige Watchlist-Daten für expandierte Karten).
  fetch('./app_data.json?_=' + Date.now())
    .then(r => r.ok ? r.json() : {{}})
    .then(appData => {{
      window._WL_CARDS = appData.watchlist_cards || {{}};
      renderAgentSignals(appData.agent_signals || appData);
    }})
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
    const localArr = JSON.parse(localStorage.getItem(WL_KEY) || '[]');
    if (token) {{
      try {{
        const r = await fetch(
          `https://api.github.com/repos/${{GH_OWNER}}/${{GH_REPO}}/contents/${{WL_GH_PATH}}?ref=${{GH_BRANCH}}`,
          {{headers: {{'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}}}}
        );
        if (r.status === 404) {{
          // Datei existiert nicht im Repo — localStorage bleibt autoritativ
          _wlGhSha = null;
          _wlCache = localArr.slice();
          return localArr.slice();
        }}
        if (r.ok) {{
          const j = await r.json();
          _wlGhSha = j.sha;
          const ghArr = JSON.parse(atob(j.content.replace(/\\n/g, '')));
          // Fix: GitHub-Leer-Stand DARF NICHT einen vorhandenen localStorage
          // überschreiben. Nur wenn GitHub tatsächlich Einträge liefert, gilt
          // GitHub als Quelle der Wahrheit. Sonst bleibt localStorage führend
          // (Szenario: wlSave hat seit Tagen still gegen 401/403 verloren).
          const merged = ghArr.length > 0 ? ghArr : localArr;
          localStorage.setItem(WL_KEY, JSON.stringify(merged));
          _wlCache = merged;
          return merged.slice();
        }}
        // Non-OK, kein 404 (z.B. 401/403/5xx) — sichtbar machen
        console.error('WL GitHub GET fehlgeschlagen:', r.status, r.statusText);
        _wlWarn(`\u26a0 GitHub-Lesefehler ${{r.status}} \u2014 Watchlist aus lokalem Cache`);
      }} catch(e) {{
        console.error('WL wlLoad Netzwerkfehler:', e);
        _wlWarn('\u26a0 GitHub unerreichbar \u2014 Watchlist aus lokalem Cache');
      }}
    }}
    _wlCache = localArr.slice();
    return localArr.slice();
  }}

  // ── Async save — localStorage always, GitHub when token available ──────────
  function _wlWarn(msg) {{
    const w = document.getElementById('wl-sync-warn');
    if (!w) return;
    w.textContent = msg;
    w.classList.add('visible');
    clearTimeout(w._hideT);
    w._hideT = setTimeout(() => w.classList.remove('visible'), 5000);
  }}

  async function wlSave(arr) {{
    arr = arr.slice(0, WL_MAX);
    _wlCache = arr;
    localStorage.setItem(WL_KEY, JSON.stringify(arr));
    const token = localStorage.getItem(TOK_KEY);
    if (!token) {{
      _wlWarn('\u26a0 Kein GitHub Token \u2014 Watchlist wird nur lokal gespeichert');
      return;
    }}
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
      console.error('WL GitHub PUT fehlgeschlagen:', r.status, r.statusText);
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
          if (r.ok) {{ _wlGhSha = (await r.json()).content?.sha || null; return; }}
          console.error('WL GitHub PUT Retry fehlgeschlagen:', r.status, r.statusText);
        }} else {{
          console.error('WL GitHub GET (SHA-Retry) fehlgeschlagen:', rf.status, rf.statusText);
        }}
      }}
      // Status-spezifische Warnung — 401/403 deutet auf Token-Problem hin
      if (r.status === 401 || r.status === 403) {{
        _wlWarn(`\u26a0\ufe0f GitHub Token abgelaufen oder ohne 'contents:write' (HTTP ${{r.status}}) \u2014 Watchlist nur lokal.`);
      }} else {{
        _wlWarn(`\u26a0 GitHub Sync-Fehler HTTP ${{r.status}} \u2014 Watchlist lokal gespeichert`);
      }}
    }} catch(e) {{
      console.error('WL wlSave Netzwerkfehler:', e);
      _wlWarn('\u26a0 GitHub Sync-Fehler (Netzwerk) \u2014 Watchlist lokal gespeichert');
    }}
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

  // Score-Farbe für die expandierte Kopfzeile — mirror von _score_color
  function wlScoreColor2(sc) {{
    if (sc == null || !isFinite(+sc)) return '#94a3b8';
    const s = +sc;
    return s >= 50 ? '#22c55e' : s >= 30 ? '#f59e0b' : '#ef4444';
  }}

  function buildWlDetails(ticker, d) {{
    // Variante A: Server-seitig vorgerendertes TopTen-Karten-HTML
    // (``_wl_full_card_html``). Layout, Sub-Scores, Drivers, Sparkline,
    // Metrics-Tiles, News + KI-Signal-Block sind identisch zur Top-10-
    // Karte. Wir setzen einen ``wl-close-btn-inline`` als Top-Bar
    // davor \u2014 dadurch bleibt der Drawer-State schlie\u00dfbar, auch wenn
    // die wl-card-header per CSS in expanded Mode versteckt ist.
    if (d && d.card_html) {{
      const closeBar = `<div class="wl-exp-close-bar">
        <button class="wl-close-btn-inline"
                onclick="wlExpand('${{ticker}}', document.getElementById('wlb-${{ticker}}'))"
                title="Einklappen">\u25b2 Schlie\xdfen</button>
      </div>`;
      const posPanel = buildPositionPanel(ticker, d.price);
      return closeBar + d.card_html + posPanel;
    }}
    try {{
      const sfCol  = metColor('sf',  d.short_float);
      const srCol  = metColor('sr',  d.short_ratio);
      const rvCol  = metColor('rv',  d.rel_volume);
      const chgCol = metColor('chg', d.change);
      const siCol  = d.si_trend === 'up' ? '#22c55e' : d.si_trend === 'down' ? '#ef4444' : '#94a3b8';
      const siArr  = d.si_trend === 'up' ? '\u2191' : d.si_trend === 'down' ? '\u2193' : '\u2192';
      const chgSign = (d.change != null && isFinite(+d.change) && +d.change >= 0) ? '+' : '';

      // Kopfzeile analog zur Main-Karte: Ticker + Preis + Score rechts + Schließen-Button
      const scNum      = d.score != null ? (+d.score).toFixed(1) : '—';
      const scCol      = wlScoreColor2(d.score);
      const priceTag   = d.price ? '$' + (+d.price).toFixed(2) : '';
      const flagStr    = d.flag ? `<span style="font-size:.85rem;margin-right:4px">${{d.flag}}</span>` : '';
      const companyStr = d.company_name || '';
      const sectorStr  = d.sector ? `<span class="sector-tag">${{d.sector}}</span>` : '';
      const topHdr = `<div class="card-top wl-exp-top">
        <div class="card-left" style="align-items:center">
          <button class="wl-close-btn-inline" onclick="wlExpand('${{ticker}}', document.getElementById('wlb-${{ticker}}'))"
                  title="Einklappen">▲ Schlie\xdfen</button>
          <div class="ticker-block">
            <div class="ticker-row">
              ${{flagStr}}<span class="ticker">${{ticker}}</span>
              ${{priceTag ? `<span class="price-tag">${{priceTag}}</span>` : ''}}
            </div>
            ${{companyStr ? `<span class="company">${{companyStr}}</span>` : ''}}
            ${{sectorStr}}
          </div>
        </div>
        <div class="score-block">
          <span class="score-num" style="color:${{scCol}}">${{scNum}}</span>
          <span class="score-lbl">Score</span>
        </div>
      </div>`;

      // Metrics — 6 gleich große Kacheln (3×2-Grid, keine SF-Header-Sonderbehandlung).
      const tiles = `<div class="metrics-row" style="padding:0 12px 12px">
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
        newsHtml = `<div class="news-items" style="padding:0 12px 10px">${{items}}</div>`;
      }}

      // KI-Analyse-Button — leitet bei Top-10-Tickern auf die Main-Karte
      // weiter (runKiAnalyse dort hat alle data-attrs). Bei History-only
      // Tickern deaktiviert mit Tooltip.
      const kiEnabled = !!WL_TOP10[ticker];
      const kiBtn = kiEnabled
        ? `<button class="ki-analyse-btn" onclick="wlOpenKiAnalyse('${{ticker}}')">KI-Analyse</button>`
        : `<button class="ki-analyse-btn" disabled
             title="Nur für Ticker in den aktuellen Top-10 verfügbar">KI-Analyse (nicht verfügbar)</button>`;

      // Close-Button am Ende — zweite Griff-Stelle für lange Karten
      const closeBottom = `<div style="padding:0 12px 14px;text-align:center">
        <button class="wl-close-btn-inline" style="width:100%"
                onclick="wlExpand('${{ticker}}', document.getElementById('wlb-${{ticker}}'))">
          ▲ Schlie\xdfen
        </button>
      </div>`;

      return topHdr + tiles + sparkHtml + tableHtml + newsHtml + kiBtn + closeBottom;
    }} catch(e) {{
      console.error('buildWlDetails Fehler:', e);
      return '<div class="wl-no-data">Fehler beim Laden der Details.</div>';
    }}
  }}

  function buildWlSparkOnly(ticker, h) {{
    // Mini-Kopfzeile + Schließen-Button auch im History-only-Fall, damit
    // der expandierte Zustand konsistent aussieht (und schließbar ist).
    const scNum  = (WL_SCORES[ticker] != null) ? (+WL_SCORES[ticker]).toFixed(1) : '—';
    const scCol  = wlScoreColor2(WL_SCORES[ticker]);
    const topHdr = `<div class="card-top wl-exp-top">
      <div class="card-left" style="align-items:center">
        <button class="wl-close-btn-inline" onclick="wlExpand('${{ticker}}', document.getElementById('wlb-${{ticker}}'))"
                title="Einklappen">▲ Schlie\xdfen</button>
        <div class="ticker-block">
          <div class="ticker-row">
            <span class="ticker">${{ticker}}</span>
          </div>
          <span class="company" style="color:var(--txt-dim);font-style:italic">Letzter bekannter Stand \u2014 nicht in aktueller Top-10</span>
        </div>
      </div>
      <div class="score-block">
        <span class="score-num" style="color:${{scCol}}">${{scNum}}</span>
        <span class="score-lbl">Score</span>
      </div>
    </div>`;
    try {{
      // 6 Kacheln mit \u201e\u2014"-Platzhaltern (gleiche Struktur wie Main-Karten),
      // damit der expandierte Zustand optisch konsistent bleibt.
      const ph = '<span class="m-val" style="color:var(--txt-dim)">\u2014</span>';
      const tiles = `<div class="metrics-row" style="padding:0 12px 12px">
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">Short Float</span></div>
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">Days to Cover</span></div>
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">Volumen</span></div>
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">Momentum</span></div>
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">Float</span></div>
        <div class="metric-box" style="--mc:#94a3b8">${{ph}}<span class="m-lbl">SI-Trend</span></div>
      </div>`;

      // Sparkline nur wenn mindestens 2 History-Punkte vorhanden
      let sparkHtml = '';
      if (h && h.scores && h.scores.length >= 2) {{
        const scoresE = JSON.stringify(h.scores).replace(/"/g, '&quot;');
        const datesE  = JSON.stringify(h.dates).replace(/"/g, '&quot;');
        sparkHtml = `<div class="spark-wrap wl-spark" style="padding:0 10px 10px"
          data-scores="${{scoresE}}" data-dates="${{datesE}}"
          data-col="${{h.col}}" data-today="">
          <div class="spark-header"><div class="spark-title-wrap">
            <span class="spark-title">\u26a1 KI-Signalverlauf</span>
            <span class="spark-subtitle">(Score der letzten Tage)</span>
          </div></div>
          <div class="spark-svg-wrap" style="height:56px"></div>
          <div class="spark-days"></div>
        </div>`;
      }}

      // Detail-Tabelle: letzter bekannter Score + Datum aus WL_HIST, Rest \u201e\u2014"
      const histDates = (h && h.dates) ? h.dates : [];
      const lastDate  = histDates.length ? histDates[histDates.length - 1] : '\u2014';
      const tableHtml = `<div class="detail-table-wrap" style="padding:0 10px 10px">
        <table class="detail-table">
          <tr><td>Letzter bekannter Score</td><td>${{scNum}}</td></tr>
          <tr><td>Letzter Datenstand</td><td>${{lastDate}}</td></tr>
          <tr><td>Kurs</td><td>\u2014</td></tr>
          <tr><td>Marktkapitalisierung</td><td>\u2014</td></tr>
          <tr><td>Sektor</td><td>\u2014</td></tr>
        </table>
      </div>
      <div class="wl-no-data" style="padding:6px 12px 10px;font-size:.78rem;color:var(--txt-dim);font-style:italic">
        Live-Daten erst verf\u00fcgbar wenn der Ticker wieder in den Top-10 erscheint.
      </div>`;

      // Position-Panel auch im History-only-Fall — User kann eine
      // Position auf einem nicht-Top-10-Watchlist-Ticker eröffnen.
      const posPanel = buildPositionPanel(ticker, null);
      return topHdr + tiles + sparkHtml + tableHtml + posPanel;
    }} catch(e) {{
      console.error('buildWlSparkOnly Fehler:', e);
      return topHdr + '<div class="wl-no-data">Fehler beim Laden der Details.</div>';
    }}
  }}

  // Klick auf „KI-Analyse" im expandierten Watchlist-Kontext →
  // Main-Karte sichtbar machen und deren KI-Analyse-Button auslösen.
  window.wlOpenKiAnalyse = function(ticker) {{
    try {{
      const mainBtn = document.querySelector(
        `article.card[data-ticker="${{ticker}}"] .ki-analyse-btn`);
      if (!mainBtn) return;
      const card = mainBtn.closest('article.card');
      if (card) card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      setTimeout(() => mainBtn.click(), 400);
    }} catch(e) {{
      console.error('wlOpenKiAnalyse Fehler:', e);
    }}
  }};

  async function wlRender() {{
    try {{
      const arr  = await wlLoad();
      const grid = document.getElementById('wl-cards');
      const cnt  = document.getElementById('wl-count');
      cnt.textContent = arr.length;
      if (!arr.length) {{ grid.innerHTML = ''; return; }}

      const top10Set = new Set(Object.keys(WL_TOP10));

      // Bug 2 — Sortierung nach Score absteigend. Quellen: Top-10-Ticker aus
      // WL_TOP10[t].score; sonst WL_SCORES[t] (Score-History).
      // Fehlt beides → 0 (landet ans Ende).
      const scoreOf = (t) => {{
        const v = top10Set.has(t)
          ? (WL_TOP10[t] && WL_TOP10[t].score)
          : WL_SCORES[t];
        return (v != null && isFinite(+v)) ? +v : 0;
      }};
      arr.sort((a, b) => scoreOf(b) - scoreOf(a));

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
        // Bug 1 — card-manual-Klasse für dunkelgrünen Hintergrund + hellgrünen Rand
        // (Specificity 0,2,0 via .wl-card.card-manual-Regel in head.jinja)
        return `<div class="wl-card card-manual" data-ticker="${{ticker}}">
          ${{inTop ? '<span class="wl-badge-star">\u2605</span>' : ''}}
          <div class="wl-card-header">
            <div style="display:flex;align-items:center;gap:4px;width:100%">
              <button class="wl-remove-btn" onclick="wlRemoveTicker('${{ticker}}')" title="Entfernen" aria-label="Aus Watchlist entfernen">\xd7</button>
              <span class="wl-card-ticker">${{ticker}}</span>
              ${{flag ? `<span class="wl-flag" style="font-size:.85rem">${{flag}}</span>` : ''}}
              <span class="wl-ki-dot agent-dot none" id="wlkd-${{ticker}}"></span>
            </div>
            <span class="wl-card-score" style="color:${{scoreCol}}">${{scoreStr}}</span>
            <div style="display:flex;align-items:center;gap:4px;width:100%;justify-content:space-between">
              <span style="font-size:.8rem;color:${{trendCol}};font-weight:700">${{trendArrow}}</span>
              <button class="wl-details-btn" id="wlb-${{ticker}}" onclick="wlExpand('${{ticker}}',this)" title="Details einblenden">\u25be</button>
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
      // Daten-Quellen-Reihenfolge: WL_TOP10 (in-page, nur heutige Top-10) →
      // window._WL_CARDS (aus app_data.json, alle Watchlist-Ticker) → Sparkline-
      // only Fallback. So sehen auch nicht-Top-10-Watchlist-Karten echte Werte.
      const d = WL_TOP10[ticker]
            || (window._WL_CARDS && window._WL_CARDS[ticker]);
      body.innerHTML = d ? buildWlDetails(ticker, d) : buildWlSparkOnly(ticker, WL_HIST[ticker]);
      body.dataset.loaded = '1';
      // Position-Panel nachladen, sobald Gist-Daten da sind (Lädt…-State).
      if (GIST_ID && localStorage.getItem(TOK_KEY)
          && body.querySelector('.position-panel-loading')) {{
        gistLoad().then(() => _refreshPositionPanel(ticker)).catch(() => {{}});
      }}
      body.querySelectorAll('.wl-spark').forEach(w => {{
        if (typeof window.drawSparkline === 'function') window.drawSparkline(w);
      }});
    }} catch(e) {{
      console.error('wlExpand Fehler:', e);
    }}
  }};

  // Freitext-Eingabe: beliebigen Ticker zur persönlichen Watchlist hinzufügen.
  // Validierung: 1–12 Zeichen, nur A–Z / 0–9 / Punkt (getrimmt & uppercased).
  const _WL_RE = /^[A-Z0-9.]{{1,12}}$/;

  function _wlSetErr(msg) {{
    const e = document.getElementById('wl-add-err');
    if (!e) return;
    if (msg) {{ e.textContent = msg; e.classList.add('visible'); }}
    else     {{ e.textContent = '';  e.classList.remove('visible'); }}
  }}

  window.wlAddManual = async function() {{
    const inp = document.getElementById('wl-add-input');
    if (!inp) return;
    const raw = (inp.value || '').trim().toUpperCase();
    if (!_WL_RE.test(raw)) {{
      _wlSetErr('Ung\xfcltiger Ticker \u2014 Beispiele: GME, SAP.DE, 0700.HK');
      return;
    }}
    const arr = await wlLoad();
    if (arr.includes(raw)) {{
      _wlSetErr('');
      inp.value = '';
      return;  // bereits drin — stillschweigend ok
    }}
    if (arr.length >= WL_MAX) {{
      _wlSetErr(`Watchlist voll (max ${{WL_MAX}} Ticker).`);
      return;
    }}
    arr.unshift(raw);
    _wlSetErr('');
    inp.value = '';
    await wlSave(arr);
    await wlRender();
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

  // Fix 3 — stiller GET /user beim Seitenstart: prüft ob der gespeicherte
  // Token noch gültig ist und die Berechtigung hat. 401/403 → sichtbare
  // Warnung, damit der User nicht ahnungslos weiter-speichert während
  // GitHub jeden PUT ablehnt.
  async function _wlValidateToken() {{
    const token = localStorage.getItem(TOK_KEY);
    if (!token) return;  // kein Token ist OK — Watchlist-Save zeigt eigene Meldung
    try {{
      const r = await fetch('https://api.github.com/user', {{
        headers: {{'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28'}},
      }});
      if (r.status === 401 || r.status === 403) {{
        console.error('WL Token-Validierung:', r.status, r.statusText);
        _wlWarn('\u26a0\ufe0f GitHub Token abgelaufen \u2014 Watchlist wird nur lokal gespeichert. '
                + 'Bitte Token im \u2699-Panel erneuern.');
      }} else if (!r.ok) {{
        console.error('WL Token-Validierung fehlgeschlagen:', r.status, r.statusText);
      }}
    }} catch(e) {{
      console.error('WL Token-Validierung Netzwerkfehler:', e);
      // Netzwerkfehler still behandeln — möglicherweise nur offline, nicht
      // zwingend ein Token-Problem. Eventuelle tatsächliche PUT-Fehler
      // werden bei der nächsten wlSave sichtbar.
    }}
  }}

  // ── Gist-Datenstore (Watchlist + Positionen, privater User-Gist) ─────────
  // Schema: {{ "watchlist": [...], "positions": {{ ticker: {{entry_date,
  //          entry_price, shares}} }} }}.
  // GIST_ID/GIST_FILE oben (Render-Zeit per env injiziert). Token aus
  // localStorage[TOK_KEY] (Scope ``gist``). Cache lokal, Schreiben per
  // PATCH /gists/:id.
  let _GIST_DATA = null;

  async function gistLoad() {{
    if (_GIST_DATA) return _GIST_DATA;
    if (!GIST_ID) return null;
    const token = localStorage.getItem(TOK_KEY);
    if (!token) return null;
    try {{
      const r = await fetch(`https://api.github.com/gists/${{GIST_ID}}`, {{
        headers: {{'Authorization': `Bearer ${{token}}`,
                  'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28'}},
      }});
      if (!r.ok) {{
        console.error('gistLoad fehlgeschlagen:', r.status, r.statusText);
        return null;
      }}
      const j   = await r.json();
      const f   = (j.files || {{}})[GIST_FILE];
      const raw = (f && f.content) || '{{}}';
      let data;
      try {{ data = JSON.parse(raw); }} catch(_) {{ data = {{}}; }}
      if (!data.watchlist) data.watchlist = [];
      if (!data.positions) data.positions = {{}};
      _GIST_DATA = data;
      return data;
    }} catch(e) {{
      console.error('gistLoad Netzwerkfehler:', e);
      return null;
    }}
  }}

  async function gistSave(data) {{
    if (!GIST_ID) return false;
    const token = localStorage.getItem(TOK_KEY);
    if (!token) {{
      _wlWarn('⚠ Kein GitHub Token — Position nur lokal sichtbar');
      return false;
    }}
    _GIST_DATA = data;   // Optimistic
    try {{
      const r = await fetch(`https://api.github.com/gists/${{GIST_ID}}`, {{
        method: 'PATCH',
        headers: {{'Authorization': `Bearer ${{token}}`,
                  'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28',
                  'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          files: {{ [GIST_FILE]: {{ content: JSON.stringify(data, null, 2) }} }}
        }}),
      }});
      if (!r.ok) {{
        console.error('gistSave fehlgeschlagen:', r.status, r.statusText);
        _wlWarn(`⚠ Gist-Sync HTTP ${{r.status}} — Eingabe nur lokal`);
        return false;
      }}
      return true;
    }} catch(e) {{
      console.error('gistSave Netzwerkfehler:', e);
      _wlWarn('⚠ Gist unerreichbar — Eingabe nur lokal');
      return false;
    }}
  }}

  // Öffentliche Helper für Position-Panel (inline-onclick aus card_html)
  window.gistLoad = gistLoad;
  window.gistSave = gistSave;

  // ── Selektor-relative Toggle-Handler für Watchlist-Drawer-Karten ─────────
  // Die Top-10-Karten-IDs (``dd0``, ``np0`` etc.) werden in
  // ``_wl_full_card_html`` gestrippt — die Onclick-Calls dort werden
  // statt ``toggleDetails(0)`` / ``toggleNews(0)`` auf diese Helper
  // umgeleitet. Lookup per ``closest('.wl-card')`` + ``querySelector``.
  window.wlToggleDetails = function(btn) {{
    const card = btn.closest('.wl-card');
    if (!card) return;
    const body = card.querySelector('.details-body');
    if (!body) return;
    const open = body.classList.toggle('open');
    const arrow = btn.querySelector('.details-arrow');
    if (arrow) arrow.style.transform = open ? 'rotate(180deg)' : '';
    const labels = btn.querySelectorAll('span');
    if (labels.length >= 2) {{
      labels[1].textContent = open ? ' Details ausblenden' : ' Details anzeigen';
    }}
    btn.setAttribute('aria-expanded', open);
  }};

  window.wlToggleNews = function(btn) {{
    const card = btn.closest('.wl-card');
    if (!card) return;
    const panel = card.querySelector('.news-panel');
    if (!panel) return;
    const open = panel.hidden;
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', open);
    btn.innerHTML = '';
    const icon = document.createElement('span');
    icon.textContent = open ? '▲' : '▼';
    btn.appendChild(icon);
    btn.append(' ' + (open ? 'Meldungen verbergen' : 'Aktuelle Meldungen'));
  }};

  // ── Position-Panel (in expandierter Watchlist-Karte) ─────────────────────
  // Pure Render-Funktion — wird aus ``buildWlDetails`` an den card_html-
  // Block angehängt und vor jedem State-Wechsel (open/close/edit) neu
  // erzeugt. Liest Cache ``_GIST_DATA``; wenn der noch leer ist, zeigt
  // sie ein „Lade…"-Placeholder, bis der Hintergrund-Load fertig ist.
  function buildPositionPanel(ticker, currentPrice) {{
    if (!GIST_ID) {{
      return `<div class="position-panel position-panel-disabled">
        <p class="pos-msg">Position-Tracking inaktiv — Gist nicht konfiguriert (Repo-Secret <code>GIST_ID</code> fehlt).</p>
      </div>`;
    }}
    const tok = localStorage.getItem(TOK_KEY);
    if (!tok) {{
      return `<div class="position-panel position-panel-disabled">
        <p class="pos-msg">GitHub-Token fehlt — Position-Tracking ben\xf6tigt einen PAT mit <code>gist</code>-Scope (⚙ Einstellungen).</p>
      </div>`;
    }}
    const removeBtn = `<button class="pos-btn pos-btn-remove" onclick="wlRemoveFromExpanded('${{ticker}}')">\xd7 Aus Watchlist entfernen</button>`;
    const data = _GIST_DATA;
    if (!data) {{
      return `<div class="position-panel position-panel-loading">
        <p class="pos-msg">L\xe4dt Gist-Daten …</p>
        <div class="pos-actions">${{removeBtn}}</div>
      </div>`;
    }}
    const pos = data.positions ? data.positions[ticker] : null;
    if (pos) {{
      const ep = +pos.entry_price || 0;
      const cp = currentPrice && isFinite(+currentPrice) ? +currentPrice : null;
      const pnl = (cp != null && ep > 0) ? ((cp - ep) / ep * 100) : null;
      const pnlStr = pnl != null ? (pnl >= 0 ? '+' : '') + pnl.toFixed(1) + '%' : '—';
      const pnlCol = pnl == null ? '#94a3b8' : pnl >= 0 ? '#22c55e' : '#ef4444';
      const sharesStr = pos.shares ? `${{pos.shares}} Stk` : '—';
      return `<div class="position-panel position-panel-active">
        <div class="pos-header">📍 Offene Position</div>
        <div class="pos-grid">
          <div><span class="pos-lbl">Entry-Datum</span><span class="pos-val">${{pos.entry_date || '—'}}</span></div>
          <div><span class="pos-lbl">Einstiegskurs</span><span class="pos-val">$${{ep.toFixed(2)}}</span></div>
          <div><span class="pos-lbl">St\xfcckzahl</span><span class="pos-val">${{sharesStr}}</span></div>
          <div><span class="pos-lbl">P&amp;L</span><span class="pos-val" style="color:${{pnlCol}};font-weight:700">${{pnlStr}}</span></div>
        </div>
        <div class="pos-actions">
          <button class="pos-btn pos-btn-close" onclick="wlClosePosition('${{ticker}}')">Position schlie\xdfen</button>
          ${{removeBtn}}
        </div>
      </div>`;
    }}
    const today = new Date().toISOString().slice(0, 10);
    const priceDef = currentPrice && isFinite(+currentPrice)
      ? (+currentPrice).toFixed(2) : '';
    return `<div class="position-panel position-panel-empty">
      <div class="pos-header">Keine offene Position</div>
      <div class="pos-form" id="pos-form-${{ticker}}" hidden>
        <label class="pos-lbl-form">Datum
          <input type="date" id="pos-d-${{ticker}}" value="${{today}}">
        </label>
        <label class="pos-lbl-form">Einstiegskurs ($)
          <input type="number" inputmode="decimal" step="0.01" min="0"
                 id="pos-p-${{ticker}}" value="${{priceDef}}" placeholder="0.00">
        </label>
        <label class="pos-lbl-form">St\xfcckzahl
          <input type="number" inputmode="numeric" step="1" min="1"
                 id="pos-s-${{ticker}}" placeholder="z. B. 35">
        </label>
        <div class="pos-form-btns">
          <button class="pos-btn pos-btn-cancel" onclick="wlCancelOpenForm('${{ticker}}')">Abbrechen</button>
          <button class="pos-btn pos-btn-save" onclick="wlSubmitPosition('${{ticker}}')">Speichern</button>
        </div>
      </div>
      <div class="pos-actions">
        <button class="pos-btn pos-btn-open" onclick="wlShowOpenForm('${{ticker}}')">Position er\xf6ffnen</button>
        ${{removeBtn}}
      </div>
    </div>`;
  }}

  // Pure DOM-Helper — Wrapping ``buildPositionPanel`` damit es sich selbst
  // refreshen kann (Inputs verschwinden / P&L-Zeile erscheint).
  function _refreshPositionPanel(ticker) {{
    const body = document.getElementById('wld-' + ticker);
    if (!body) return;
    const wrap = body.querySelector('.position-panel');
    const priceTag = body.querySelector('.price-tag');
    const cur = priceTag ? parseFloat((priceTag.textContent || '').replace(/[^\\d.]/g, '')) : null;
    if (wrap) wrap.outerHTML = buildPositionPanel(ticker, cur);
  }}

  window.wlShowOpenForm = function(ticker) {{
    const f = document.getElementById('pos-form-' + ticker);
    if (f) f.hidden = false;
  }};
  window.wlCancelOpenForm = function(ticker) {{
    const f = document.getElementById('pos-form-' + ticker);
    if (f) f.hidden = true;
  }};

  window.wlSubmitPosition = async function(ticker) {{
    const d = document.getElementById('pos-d-' + ticker);
    const p = document.getElementById('pos-p-' + ticker);
    const s = document.getElementById('pos-s-' + ticker);
    if (!d || !p || !s) return;
    const date   = d.value;
    const price  = parseFloat(p.value);
    const shares = parseInt(s.value, 10) || 0;
    if (!date || !isFinite(price) || price <= 0 || shares <= 0) {{
      alert('Datum, Einstiegskurs > 0 und St\xfcckzahl > 0 erforderlich.');
      return;
    }}
    const data = (await gistLoad()) || {{watchlist: [], positions: {{}}}};
    data.positions = data.positions || {{}};
    data.positions[ticker] = {{
      entry_date: date, entry_price: price, shares: shares,
    }};
    await gistSave(data);
    _refreshPositionPanel(ticker);
  }};

  window.wlClosePosition = async function(ticker) {{
    if (!confirm(`Position ${{ticker}} schlie\xdfen?`)) return;
    const data = (await gistLoad()) || {{watchlist: [], positions: {{}}}};
    if (data.positions) delete data.positions[ticker];
    await gistSave(data);
    _refreshPositionPanel(ticker);
  }};

  // Footer-Button im expandierten Card: entfernt Ticker aus Watchlist
  // (Repo-Datei via wlSave) UND aus Gist (Position + Watchlist-Spiegel).
  // Karte schließt sich automatisch durch wlRender.
  window.wlRemoveFromExpanded = async function(ticker) {{
    const msg = `${{ticker}} aus Watchlist entfernen?\nEine evtl. offene Position wird ebenfalls gel\xf6scht.`;
    if (!confirm(msg)) return;
    // Gist: Position + Watchlist-Spiegel synchronisieren
    if (GIST_ID && localStorage.getItem(TOK_KEY)) {{
      const data = (await gistLoad()) || {{watchlist: [], positions: {{}}}};
      data.watchlist = (data.watchlist || []).filter(t => t !== ticker);
      if (data.positions) delete data.positions[ticker];
      await gistSave(data);
    }}
    // Repo-Datei (Bestand): existierender wlSave-Pfad
    await window.wlRemoveTicker(ticker);
  }};

  document.addEventListener('DOMContentLoaded', () => {{
    wlRender();
    _wlValidateToken();
    // Eager-Preload des Gist-Caches, damit das Position-Panel beim ersten
    // Karten-Expand sofort den korrekten State zeigt (sonst kurzes „Lädt…").
    if (GIST_ID && localStorage.getItem(TOK_KEY)) {{
      gistLoad().catch(() => {{}});
    }}
    const inp = document.getElementById('wl-add-input');
    if (inp) {{
      inp.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter') {{ e.preventDefault(); window.wlAddManual(); }}
      }});
      inp.addEventListener('input', () => _wlSetErr(''));
    }}
  }});
}})();
// ── Claude / Anthropic API ────────────────────────────────────────────────────
const ANT_KEY_LS       = 'anthropic_api_key';
const ANT_WARN_LS      = 'chat_warn_ack_ts';
const ANT_WARN_TTL_MS  = 7 * 24 * 60 * 60 * 1000;
const ANT_ENDPOINT     = 'https://api.anthropic.com/v1/messages';
const ANT_MODEL        = 'claude-sonnet-4-6';
const ANT_KI_LABEL     = 'KI-Analyse';
const ANT_KI_LABEL_HIDE= '\u25b2 Analyse ausblenden';
const ANT_KI_LABEL_NEW = 'Neu analysieren';
const ANT_KI_LABEL_BUSY= 'Analysiere …';
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
    // GitHub Token — gespeicherten Wert vor-ausfüllen
    const ghInp = document.getElementById('gh-inp');
    const ghTok = localStorage.getItem(TOK_KEY) || '';
    if (ghInp && ghTok) ghInp.value = ghTok;
  }}
}}

// ── GitHub Token — speichern / testen / löschen ─────────────────────────────
function saveGhToken() {{
  const inp    = document.getElementById('gh-inp');
  const status = document.getElementById('gh-status');
  const tok    = (inp?.value || '').trim();
  if (!tok) {{
    localStorage.removeItem(TOK_KEY);
    if (status) {{ status.className = 'anth-status'; status.textContent = ''; }}
    return;
  }}
  localStorage.setItem(TOK_KEY, tok);
  if (status) {{
    status.className = 'anth-status ok';
    status.textContent = '✅ Gespeichert';
    clearTimeout(status._hideT);
    status._hideT = setTimeout(() => {{
      status.textContent = ''; status.className = 'anth-status';
    }}, 2500);
  }}
}}

async function testGhToken() {{
  const inp    = document.getElementById('gh-inp');
  const status = document.getElementById('gh-status');
  const tok    = (inp?.value || '').trim() || localStorage.getItem(TOK_KEY) || '';
  if (!tok) {{
    if (status) {{ status.className = 'anth-status err'; status.textContent = '❌ Kein Token eingegeben'; }}
    return;
  }}
  try {{
    const r = await fetch('https://api.github.com/user', {{
      headers: {{'Authorization': `Bearer ${{tok}}`, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'}},
    }});
    if (r.ok) {{
      const j = await r.json();
      if (status) {{
        status.className = 'anth-status ok';
        status.textContent = `✅ Gültig — eingeloggt als ${{j.login || '?'}}`;
      }}
    }} else {{
      console.error('GH Token Test fehlgeschlagen:', r.status, r.statusText);
      if (status) {{
        status.className = 'anth-status err';
        status.textContent = `❌ Ungültig — HTTP ${{r.status}} ${{r.statusText}}`;
      }}
    }}
  }} catch(e) {{
    console.error('GH Token Test Netzwerkfehler:', e);
    if (status) {{
      status.className = 'anth-status err';
      status.textContent = '❌ Netzwerkfehler — GitHub nicht erreichbar';
    }}
  }}
}}

function clearGhToken() {{
  const inp    = document.getElementById('gh-inp');
  const status = document.getElementById('gh-status');
  localStorage.removeItem(TOK_KEY);
  if (inp) inp.value = '';
  if (status) {{ status.className = 'anth-status'; status.textContent = ''; }}
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
    price:    d.price   || '?',
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
    // FX: USD→EUR-Multiplikator (EUR pro 1 USD). Wird vom Chat-Panel-IIFE
    // aus app_data.json.fx_usd_eur auf window gespiegelt.
    fxUsdEur: window._FX_USD_EUR || 0.92,
  }};

  const sysPrompt = 'Du bist ein erfahrener Squeeze-Analyst. Analysiere das folgende Squeeze-Setup und gib eine präzise Einschätzung auf Deutsch. Maximal 200 Wörter. '
    + 'Wichtiger Hinweis zu Backtesting-Daten: Die bisherigen Bootstrap-Daten basieren auf einer vereinfachten Score-Formel ohne DTC, FINRA SI-Trend und Kombinations-Bonus — sie sind nicht direkt mit Live-Scores vergleichbar. Belastbare Statistiken folgen nach 60+ Tagen Live-Daten. Der Score ist ein struktureller Filter: Kandidaten mit hohem Score haben objektiv mehr Squeeze-Potential als Kandidaten mit niedrigem Score. Für konkrete Handlungsempfehlungen sind Katalysator-Sub-Score, aktuelle Nachrichten und eigene Recherche unverzichtbar. Empfehle immer Stop-Loss -15% und maximale Haltedauer 5 Handelstage bei Squeeze-Setups. '
    + 'Falls RSI > 80 oder Kurs bereits stark gestiegen (> 20% in 5 Tagen): explizit auf Rückschlagsrisiko hinweisen. '
    + 'Gib nach der Analyse ZWINGEND folgendes Risk/Reward-Framework aus — jede Zeile beginnt mit dem Label + Doppelpunkt:\\n'
    + 'Möglicher Einstieg: $<Kurs> (<EUR-Wert> €) (aktuell)\\n'
    + 'Stop-Loss: $<Kurs -15%> (<EUR-Wert> €) — falls dieser Level bricht, ist das Setup gescheitert\\n'
    + 'Profit-Target 1: $<Kurs +20%> (<EUR-Wert> €) — erstes Ziel bei Short-Covering\\n'
    + 'Profit-Target 2: $<Kurs +50%> (<EUR-Wert> €) — Squeeze-Szenario\\n'
    + 'Risk/Reward: 1:1.3 (Stop -15% / Target +20%)\\n'
    + 'Berechne die konkreten Dollar-Beträge aus dem angegebenen aktuellen Kurs. '
    + 'WÄHRUNGS-FORMAT: Bei JEDER Kursnennung beide Währungen — USD zuerst, EUR in Klammern mit deutschem Komma. Format: "$4.47 (4,11 €)". '
    + 'Umrechnung: USD-Betrag × ' + ctx.fxUsdEur.toFixed(4) + ' = EUR-Betrag, auf 2 Nachkommastellen gerundet. '
    + 'Gilt für Einstieg, Stop-Loss, beide Profit-Targets und jede weitere Kursnennung. '
    + 'Schließe immer mit einem Haftungshinweis ab: Diese Analyse ist keine Anlageempfehlung. '
    + 'Beende jede Analyse zwingend mit "Fazit:" gefolgt von einer konkreten Einschätzung in einem Satz.';
  const userPrompt =
`Squeeze-Setup für ${{ctx.ticker}} (${{ctx.company}}):
- Squeeze-Score: ${{ctx.score}}/100
- Aktueller Kurs: $${{ctx.price}} (${{(parseFloat(ctx.price) * ctx.fxUsdEur).toFixed(2).replace('.', ',')}} €)
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
    '<span class="ka-label">Claude &middot; ' + ctx.ticker +
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
        // Während des Streamings den Container mitscrollen, damit das
        // aktuelle Token immer sichtbar bleibt (Fazit steht am Ende).
        if (res) res.scrollTop = res.scrollHeight;
      }},
      {{model: ANT_MODEL, max_tokens: 600}}
    );
    // Nach Stream-Ende: via requestAnimationFrame nachscrollen, damit
    // der letzte Layout-Pass wirklich drin ist bevor wir bottom-scrollen.
    if (res) {{
      requestAnimationFrame(() => {{ res.scrollTop = res.scrollHeight; }});
    }}
    btn.dataset.kaHasResult = '1';
    btn.textContent = ANT_KI_LABEL_HIDE;
  }} catch(e) {{
    res.innerHTML = '<span class="ka-label">Fehler</span>' + e.message;
    btn.textContent = ANT_KI_LABEL;   // kein has-result setzen → nächster Tap macht neuen Call
  }} finally {{
    btn.disabled = false;
  }}
}}

{chat_script_html}
// ── Service Worker Registration (PWA-Cache) ─────────────────────────────────
// Skip-Registration wenn Seite nicht über https/localhost geladen wird
// (lokales file:// kann SW nicht).
if ('serviceWorker' in navigator
    && (location.protocol === 'https:' || location.hostname === 'localhost')) {{
  navigator.serviceWorker.register('service_worker.js').catch((e) => {{
    console.warn('Service Worker Registration fehlgeschlagen:', e);
  }});
}}
</script>
</body>
</html>"""


def generate_html_v2(stocks: list[dict], report_date: str) -> str:
    """Jinja2-basiertes Rendering.

    Phase 3d: ``templates/card.jinja`` rendert alle Karten; das Ergebnis
    wird in den v1-Page-Context eingeschleust, sodass ``_render_test``
    die Karten-Quelle (f-String vs Jinja2) isoliert vergleichen kann.
    Äußere Seitenstruktur folgt in späteren Phasen; v1 bleibt Default.
    """
    ctx = _build_context(stocks, report_date)
    env = _jinja_env()
    card_tmpl = env.get_template("card.jinja")
    cards_v2 = "\n".join(
        card_tmpl.render(**c).rstrip("\n") for c in ctx["card_ctxs"]
    )
    ctx_v2 = {**ctx, "cards": cards_v2}
    return generate_html_v1(stocks, report_date, _ctx=ctx_v2)


def generate_html(stocks: list[dict], report_date: str) -> str:
    """Öffentlicher Einstiegspunkt — ab Phase 3e Jinja2-basiert (v2).

    Byte-Identität v1==v2 ist in Phase 3d per ``_render_test`` verifiziert.
    v1 bleibt als Fallback erreichbar über die Umgebungsvariable
    ``JINJA_USE_V1=1`` (Rollback-Pfad, falls v2 produktiv auffällt).
    """
    if os.environ.get("JINJA_USE_V1"):
        return generate_html_v1(stocks, report_date)
    return generate_html_v2(stocks, report_date)


def _render_test(stocks: list[dict], report_date: str) -> None:
    """Sanity-Check: v1 und v2 müssen byte-identischen Output liefern.

    In Phase 0 delegiert v2 an v1 → trivial identisch. Der Test bleibt bis
    zum Abschluss der Migration Pflicht und wird bei jeder Phase aktiv.
    Aktivierung via Umgebungsvariable ``JINJA_RENDER_TEST=1``.
    """
    out_v1 = generate_html_v1(stocks, report_date)
    out_v2 = generate_html_v2(stocks, report_date)
    if out_v1 != out_v2:
        raise AssertionError(
            f"Render-Test fehlgeschlagen: "
            f"v1 ({len(out_v1)} Bytes) != v2 ({len(out_v2)} Bytes)"
        )
    log.info("Render-Test OK: v1 == v2 (%d Bytes)", len(out_v1))


# ===========================================================================
# 4b. WATCHLIST VOLUME SCAN
# ===========================================================================

_WL_PERSONAL_FILE = "watchlist_personal.json"
_WL_PERSONAL_RE   = re.compile(r"^[A-Z0-9.]{1,12}$")


def _load_personal_watchlist() -> list[str]:
    """Liste der manuell beobachteten Ticker aus ``watchlist_personal.json``.

    Rückgabe ist eine dedupte Liste aus validen Tickern in Großbuchstaben.
    Silently ignoriert fehlende Datei, kaputtes JSON und invalide Einträge.
    """
    try:
        with open(_WL_PERSONAL_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    seen: set[str] = set()
    out:  list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, str):
            continue
        t = item.strip().upper()
        if t and t not in seen and _WL_PERSONAL_RE.match(t):
            seen.add(t)
            out.append(t)
    return out


_WL_FAILURES_FILE   = "watchlist_failures.json"
_WL_INACTIVE_FILE   = "watchlist_inactive.json"
_WL_INACTIVE_LEGACY = "watchlist_inactive.txt"   # alte Datei, einmalig migriert

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
    """Liest delisted/inaktive Watchlist-Ticker aus JSON, mit Legacy-TXT-Migration."""
    inactive: set[str] = set()
    # Neu: JSON-Format
    try:
        with open(_WL_INACTIVE_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            inactive.update(data.get("tickers", []))
        elif isinstance(data, list):
            inactive.update(data)
    except Exception:
        pass
    # Legacy: TXT-Format (einmalige Migration beim ersten Lauf)
    try:
        with open(_WL_INACTIVE_LEGACY) as f:
            inactive.update(ln.strip() for ln in f if ln.strip())
    except Exception:
        pass
    return inactive


def _wl_save_inactive(inactive: set[str]) -> None:
    """Schreibt die Blacklist nach JSON — von update_watchlist.py ausgelesen."""
    payload = {
        "updated":  datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
        "tickers":  sorted(inactive),
    }
    with open(_WL_INACTIVE_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def _wl_mark_inactive(ticker: str) -> None:
    inactive = _wl_load_inactive()
    inactive.add(ticker)
    _wl_save_inactive(inactive)
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

def _load_backtest_history() -> list[dict]:
    """Lädt backtest_history.json als Liste. Silently [] bei fehlend/corrupt."""
    try:
        with open(BACKTEST_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_backtest_history(entries: list[dict]) -> None:
    """Schreibt backtest_history.json, sortiert nach (Datum, Ticker) für
    deterministische Git-Diffs. Pruning auf BACKTEST_MAX_DAYS erfolgt bereits
    beim Aufruf — hier nur Serialisierung."""
    with open(BACKTEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)


def _prune_backtest_history(entries: list[dict], max_days: int = None) -> list[dict]:
    """Entfernt Einträge älter als max_days Kalendertage (default BACKTEST_MAX_DAYS).

    Date-Format in entries: "DD.MM.YYYY" (matching generate_report's report_date).
    Unparsable dates werden belassen (defensiv) — keine Datenverluste durch
    Format-Wechsel. Bootstrap-Einträge (source == "bootstrap") sind
    prune-immun, damit backtest_bootstrap.py eingepflegte 365-Tage-Historie
    nicht nach 90 Tagen wieder gelöscht wird.
    """
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=max_days or BACKTEST_MAX_DAYS)
    kept: list[dict] = []
    for e in entries:
        if e.get("source") == "bootstrap":
            kept.append(e)
            continue
        d_str = e.get("date", "")
        try:
            ed = datetime.strptime(d_str, "%d.%m.%Y").date()
            if ed >= cutoff:
                kept.append(e)
        except (ValueError, TypeError):
            kept.append(e)   # keep unparseable entries to avoid data loss
    return kept


def _market_regime_from_spy(spy_hist=None) -> str:
    """SPY 50-Trading-Day-Trend → ``bull`` / ``bear`` / ``neutral``.

    Schwelle: ±5 % über die letzten 50 Handelstage. yfinance ``period="3mo"``
    liefert ~63 Handelstage; ``Close.iloc[-51]`` ist genau 50 Handelstage
    vor dem letzten Schlusskurs. Bei Daten- oder Fetch-Fehler → "neutral".
    """
    try:
        if spy_hist is None:
            spy_hist = yf.download("SPY", period="3mo",
                                   progress=False, threads=False)
        if spy_hist is None or spy_hist.empty:
            return "neutral"
        close = spy_hist["Close"].squeeze().dropna()
        if len(close) < 51:
            return "neutral"
        cur = float(close.iloc[-1])
        ref = float(close.iloc[-51])
        if ref <= 0:
            return "neutral"
        delta_pct = (cur - ref) / ref * 100.0
        if delta_pct >  5.0: return "bull"
        if delta_pct < -5.0: return "bear"
        return "neutral"
    except Exception as exc:
        log.debug("SPY market-regime fetch failed: %s", exc)
        return "neutral"


def _vix_close() -> float | None:
    """Letzter VIX-Schlusskurs (yfinance ^VIX). None bei Fetch-Fehler."""
    try:
        h = yf.download("^VIX", period="5d", progress=False, threads=False)
        if h is not None and not h.empty:
            return round(float(h["Close"].squeeze().dropna().iloc[-1]), 2)
    except Exception as exc:
        log.debug("^VIX fetch failed: %s", exc)
    return None


def _compute_max_drawdown(df_window) -> float | None:
    """Max-Drawdown vom rolling-Peak (Cummax-High) zur Tagestief (Low) im Fenster.

    Args:
        df_window: DataFrame mit Spalten ``High``/``Low`` für die ersten ≤10
                   Handelstage seit Entry (inklusive Entry-Tag als Index 0).
    Returns negativster %-Drop oder ``0.0`` bei zu wenig Daten.
    """
    try:
        if df_window is None or df_window.empty or len(df_window) < 2:
            return 0.0
        roll_peak = df_window["High"].cummax()
        dd = (df_window["Low"] - roll_peak) / roll_peak * 100.0
        return round(float(dd.min()), 2)
    except Exception:
        return None


def _build_backtest_extension(s: dict, pool_position: int, pool_size: int,
                              agent_signals: dict) -> dict:
    """Liefert das Schema-Erweiterungs-Dict (Bahn B) für einen Top-10-Eintrag.

    Felder, die retroaktiv NICHT rekonstruierbar sind:
      • Score-Komponenten + roher Pre-Smoothing-Score
      • Boni-Breakdown (combo, score-trend, agent-boost, perfect-storm, finra)
      • Pool-Kontext (Position + Größe — pool_member ist immer True für Top-10)
      • Source-Tracking aus den Fallback-Ketten

    Defaults:
      • Boni nicht aktiv  → 0.0  (Faktoren default 1.0)
      • Komponente nicht berechenbar → None  (NICHT 0)
      • Source unbekannt → "unknown"
    """
    sub = _compute_sub_scores(s) if s.get("short_float") is not None else None
    # Combo-Bonus aus den Bedingungen in score() rekonstruieren — Recompute
    # statt Refactor des autoritativen score()-Pfads.
    sf_val = _safe_float(s.get("short_float", 0))
    sr_val = _safe_float(s.get("short_ratio", 0))
    rv_val = _safe_float(s.get("rel_volume", 0))
    fd     = s.get("finra_data") or {}
    n_combo = sum([
        sf_val >= 30,
        sr_val >= 5,
        rv_val >= 2.0,
        fd.get("trend") == "up",
    ])
    combo_bonus = float(COMBO_BONUS) if n_combo >= 3 else 0.0
    # Perfect-Storm-Multiplikator: aus agent_signals.json pro Ticker (vom
    # KI-Agent persistiert in Bahn B). Default 1.0 wenn kein Signal vorhanden.
    sig = (agent_signals or {}).get(s["ticker"]) or {}
    return {
        "score_struct":         sub["struct"]   if sub is not None else None,
        "score_catalyst":       sub["catalyst"] if sub is not None else None,
        "score_timing":         sub["timing"]   if sub is not None else None,
        "score_raw":            round(float(s.get("score_raw") or 0), 2),
        "combo_bonus":          combo_bonus,
        "score_trend_bonus":    float(s.get("score_trend_bonus_pts") or 0.0),
        "agent_boost_factor":   float(s.get("agent_boost_factor") or 1.0),
        "perfect_storm_mult":   float(sig.get("combo_mult") or 1.0),
        "finra_bonus":          float(s.get("finra_bonus_pts") or 0.0),
        "pool_member":          True,
        "pool_position":        int(pool_position),
        "pool_size":            int(pool_size),
        "short_float_source":   s.get("short_float_source") or "unknown",
        "si_trend_source":      fd.get("si_trend_source") or "unknown",
    }


def _append_backtest_entries(top10: list[dict], report_date: str,
                             pool_size: int = 0) -> None:
    """Fügt für jeden Top-10-Kandidaten einen neuen Backtest-Eintrag hinzu,
    dedupliziert nach (ticker, date), prunet auf 90 Tage und schreibt die Datei.
    Idempotent: wiederholter Aufruf am gleichen Tag ändert nichts.

    ``pool_size`` ist die Anzahl der enriched Kandidaten BEVOR der Top-10-Cut
    erfolgt — Kontext für spätere „Pool-Position vs. Return"-Auswertung.
    """
    if not BACKTEST_ENABLED:
        return
    history = _load_backtest_history()
    existing_keys = {(e.get("ticker"), e.get("date")) for e in history}
    # Agent-Signals einmalig laden (pro-Ticker-Lookup für perfect_storm_mult).
    try:
        with open("agent_signals.json", "r", encoding="utf-8") as fh:
            agent_signals = (json.load(fh) or {}).get("signals") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        agent_signals = {}

    # Bahn-A2-Stufe-1: Markt-Regime + VIX einmal pro Run abrufen. Werden auf
    # NEUE Einträge persistiert; die rolling Drawdown-Aktualisierung läuft
    # weiter unten für Einträge < 14 Kalendertage alt.
    _spy_hist = None
    try:
        _spy_hist = yf.download("SPY", period="3mo",
                                progress=False, threads=False)
    except Exception as _exc:
        log.debug("SPY pre-fetch for backtest schema failed: %s", _exc)
    market_regime = _market_regime_from_spy(_spy_hist)
    vix_level     = _vix_close()
    log.info("Backtest-Schema (Stufe 1): market_regime=%s, vix=%s",
             market_regime, vix_level)

    n_added = 0
    for pos, s in enumerate(top10, start=1):
        key = (s["ticker"], report_date)
        if key in existing_keys:
            continue
        fd = s.get("finra_data") or {}
        entry = {
            "date":          report_date,
            "ticker":        s["ticker"],
            "score":         round(float(s.get("score") or 0), 2),
            "entry_price":   round(float(s.get("price") or 0), 4),
            "entry_price_t1": None,   # wird am Tag T+1 von ki_agent gefüllt
            "short_float":   round(float(s.get("short_float") or 0), 2),
            "dtc":           round(float(s.get("short_ratio") or 0), 2),
            "rvol":          round(float(s.get("rel_volume") or 0), 3),
            "si_trend":      fd.get("trend", "no_data"),
            "return_3d":     None,
            "return_5d":     None,
            "return_10d":    None,
            "return_3d_t1":  None,
            "return_5d_t1":  None,
            "return_10d_t1": None,
            # Bahn A2 Stufe 1 — Schema-Erweiterung für spätere Auswertung.
            # max_drawdown_pct wird über 10 Handelstage rolling aktualisiert.
            "max_drawdown_pct": 0.0,
            "market_regime":    market_regime,
            "vix_level":        vix_level,
        }
        # Bahn B: Schema-Erweiterung (rückwärtskompatibel — alte Einträge
        # bleiben mit 16 Feldern unverändert; neue bekommen 14 zusätzliche).
        entry.update(_build_backtest_extension(
            s, pool_position=pos, pool_size=pool_size,
            agent_signals=agent_signals,
        ))
        history.append(entry)
        n_added += 1

    # Rolling Drawdown-Aktualisierung: pro Eintrag < 14 Kalendertage (≈10
    # Handelstage) alt die Ticker-History seit Entry holen und max_drawdown
    # neu berechnen. Ein Batch-Download für alle aktiven Ticker spart
    # Round-Trips; pro Entry wird die Datums-Slice ausgewertet.
    today_d = date.today()
    active_dd: list[tuple[dict, "datetime"]] = []
    for e in history:
        try:
            edate = datetime.strptime(e.get("date", ""), "%d.%m.%Y").date()
        except (TypeError, ValueError):
            continue
        # Nur Einträge mit dem neuen Feld aktualisieren — alte Einträge
        # ohne max_drawdown_pct bleiben unangetastet (Backwards-Compat).
        if "max_drawdown_pct" not in e:
            continue
        days_old = (today_d - edate).days
        if days_old <= 0 or days_old > 14:
            continue
        active_dd.append((e, edate))

    if active_dd:
        unique_tickers = sorted({e["ticker"] for e, _ in active_dd})
        try:
            dd_batch = yf.download(
                " ".join(unique_tickers), period="1mo",
                progress=False, threads=False,
                group_by="ticker" if len(unique_tickers) > 1 else "column",
            )
        except Exception as _exc:
            log.debug("Drawdown batch fetch failed: %s", _exc)
            dd_batch = None

        n_dd = 0
        for e, edate in active_dd:
            try:
                if dd_batch is None or dd_batch.empty:
                    continue
                df = (dd_batch[e["ticker"]] if len(unique_tickers) > 1
                      else dd_batch)
                if df is None or df.empty:
                    continue
                df_since = df[df.index.date >= edate].iloc[:11]
                dd = _compute_max_drawdown(df_since)
                if dd is not None:
                    e["max_drawdown_pct"] = dd
                    n_dd += 1
            except Exception:
                continue
        log.info("Backtest-Schema (Stufe 1): max_drawdown aktualisiert für %d/%d aktive Einträge",
                 n_dd, len(active_dd))

    history = _prune_backtest_history(history)
    # Stabil sortieren: neueste Einträge zuletzt → Git-Diff zeigt nur den Append
    def _sortkey(e):
        try:
            return (datetime.strptime(e.get("date",""), "%d.%m.%Y").date(),
                    e.get("ticker",""))
        except ValueError:
            return (datetime.min.date(), e.get("ticker",""))
    history.sort(key=_sortkey)
    _save_backtest_history(history)
    print(f"Backtest-History: +{n_added} neue Einträge, total {len(history)} "
          f"(Cut-off: {BACKTEST_MAX_DAYS} Tage)", flush=True)


def _write_app_data_json(watchlist_cards: dict | None = None,
                          monster_scores: dict | None = None,
                          setup_scores: dict | None = None,
                          gap_states: dict | None = None) -> None:
    """Schreibt kombinierte app_data.json = score_history + agent_signals + watchlist_cards.

    Beide Quelldateien (score_history.json + agent_signals.json) bleiben separat
    erhalten (Kompatibilität mit bestehenden Consumern). app_data.json dient
    dem Browser als Einzel-Fetch-Quelle — spart einen HTTP-Request.

    ``watchlist_cards`` enthält das vollständige Karten-Payload für ALLE
    persönlichen Watchlist-Ticker (Top-10 + manuelle Extras), damit der
    Browser auch nicht-Top-10-Watchlist-Karten im expandierten Zustand mit
    echten Werten statt „—"-Platzhaltern anzeigt.

    Tolerant gegen fehlende Quelldateien (Platzhalter {}).
    """
    if not GENERATE_APP_DATA_JSON:
        return
    try:
        with open(SCORE_HISTORY_FILE, "r", encoding="utf-8") as fh:
            score_history = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        score_history = {}
    try:
        with open("agent_signals.json", "r", encoding="utf-8") as fh:
            agent_signals = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        agent_signals = {}
    payload = {
        "score_history":   score_history,
        "agent_signals":   agent_signals,
        "watchlist_cards": watchlist_cards or {},
        "monster_scores":  monster_scores or {},
        "setup_scores":    setup_scores or {},
        "gap_states":      gap_states or {},
        "fx_usd_eur":      _FX_USD_EUR,
        "generated_at":    datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open("app_data.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), default=str)
    print(f"app_data.json: {len(score_history)} Ticker-History + "
          f"{len(agent_signals.get('signals', {}))} Signals + "
          f"{len(payload['watchlist_cards'])} Watchlist-Karten zusammengeführt",
          flush=True)


def _write_service_worker() -> None:
    """Schreibt service_worker.js ins Repo-Root mit frischem Cache-Namen.

    Strategie: Network-first mit Cache-Fallback für index.html,
    score_history.json, agent_signals.json, app_data.json. Bei jedem
    Report-Run erhält der Cache einen neuen Namen (Zeitstempel) — alte
    Caches werden im activate-Handler automatisch gelöscht.
    """
    cache_version = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%d-%H%M")
    sw_code = f"""// Auto-generiert von generate_report.py — Service Worker
// Cache-Version: {cache_version} (wird bei jedem Daily-Run aktualisiert)
const CACHE_NAME = 'squeeze-{cache_version}';
const URLS = [
  './',
  './index.html',
  './score_history.json',
  './agent_signals.json',
  './app_data.json',
];

self.addEventListener('install', (event) => {{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(URLS).catch(() => null)));
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', (event) => {{
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Nur Same-Origin und unsere 4 gecachten Pfade
  if (url.origin !== self.location.origin) return;
  const path = url.pathname.split('/').pop();
  if (!['index.html', '', 'score_history.json', 'agent_signals.json', 'app_data.json'].includes(path)) return;
  event.respondWith((async () => {{
    try {{
      const fresh = await fetch(req);
      if (fresh && fresh.status === 200) {{
        const cache = await caches.open(CACHE_NAME);
        cache.put(req, fresh.clone()).catch(() => null);
      }}
      return fresh;
    }} catch (err) {{
      const cached = await caches.match(req);
      if (cached) return cached;
      throw err;
    }}
  }})());
}});
"""
    with open("service_worker.js", "w", encoding="utf-8") as fh:
        fh.write(sw_code)
    print(f"Service Worker: service_worker.js geschrieben (cache {cache_version})", flush=True)


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


# ═══════════════════════════════════════════════════════════════════════════
# EXIT-SIGNALE FÜR OFFENE POSITIONEN (Phase 1, kein Frontend)
# ═══════════════════════════════════════════════════════════════════════════
# positions.json wird vom Workflow zur Laufzeit aus dem GitHub Secret
# POSITIONS_JSON erzeugt — niemals committen (siehe .gitignore + CLAUDE.md).
# Schema: { "TICKER": { "entry_date": "YYYY-MM-DD", "entry_price": float } }

def _load_positions() -> dict:
    """Lädt positions.json. Bei fehlender/korrupter Datei → leeres Dict."""
    try:
        path = Path("positions.json")
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _exit_load_state() -> dict:
    """Lädt agent_state.json (gemeinsam mit ki_agent). Bei Fehler leerer Dict.

    Cooldowns werden über Key-Prefixe ``exit_TICKER`` / ``profit_TICKER``
    von den ki_agent-Cooldowns (Plain-Ticker) getrennt gehalten.
    """
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _exit_save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("agent_state.json Schreibfehler: %s", exc)


def _exit_is_on_cooldown(key: str, state: dict) -> bool:
    ts = (state.get("cooldowns") or {}).get(key)
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return False
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    if last.tzinfo is None:
        last = last.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    return (now - last).total_seconds() < EXIT_COOLDOWN_HOURS * 3600


def _exit_set_cooldown(key: str, state: dict) -> None:
    state.setdefault("cooldowns", {})[key] = (
        datetime.now(ZoneInfo("Europe/Berlin")).isoformat()
    )


def _send_exit_ntfy(ticker: str, body: str) -> bool:
    """Single-shot ntfy.sh push (analog zu ki_agent.send_ntfy_alert).
    Fail-soft: returnt False bei jedem Fehler, blockiert den Daily-Run nie.
    """
    if not NTFY_ENABLED or not NTFY_TOPIC:
        return False
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={
                "Title": f"Exit Alert: {ticker}",
                "Priority": "high",
                "Tags": "chart_with_downwards_trend",
            },
            timeout=5,
        )
        return True
    except Exception as exc:
        log.warning("ntfy exit-push fehlgeschlagen für %s: %s", ticker, exc)
        return False


def _fetch_position_market_data(ticker: str, entry_date: date) -> dict | None:
    """Holt Tagesdaten ab (entry_date − 25 Handelstage) bis heute via yfinance.

    Wird benötigt für high_since_entry, RVOL (heute vs. Ø 20T) und
    Tagesperformance. Gibt None zurück bei jedem yfinance-Fehler.
    """
    try:
        start = (entry_date - timedelta(days=40)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, period=None, auto_adjust=False)
        if hist is None or hist.empty:
            return None
        # Filter ab Entry-Datum für high_since_entry
        try:
            since_entry = hist[hist.index.date >= entry_date]
        except Exception:
            since_entry = hist
        if since_entry.empty:
            since_entry = hist.tail(1)
        cur_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur_close
        chg_pct = ((cur_close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        avg_vol_20d = float(hist["Volume"].tail(20).mean() or 0.0)
        cur_vol = float(hist["Volume"].iloc[-1] or 0.0)
        rvol = (cur_vol / avg_vol_20d) if avg_vol_20d > 0 else 0.0
        return {
            "price":             cur_close,
            "rvol":              rvol,
            "change_pct":        chg_pct,
            "history_since":     since_entry,
        }
    except Exception as exc:
        log.warning("yfinance Position-Fetch %s: %s", ticker, exc)
        return None


def compute_exit_score(ticker: str, position: dict, current_data: dict,
                        history: dict) -> dict:
    """Bewertet eine offene Position auf Exit-Signal (0–100).

    Komponenten (jeweils 0–100, mit Gewicht aus config.py):
      • Trailing-Stop  (40 %): Drawdown vom high_since_entry, ≥ EXIT_TRAILING_STOP_PCT → 100, linear darunter.
      • Setup-Verfall  (25 %): Setup-Score am Entry-Tag (aus score_history) vs. heute. Drop ≥ EXIT_SETUP_DROP_THRESHOLD → 100.
      • Distribution   (20 %): heute RVOL ≥ EXIT_DISTRIBUTION_RVOL UND Tages-PnL < 0 → 100, sonst 0.
      • Time-Decay     (15 %): ab EXIT_TIME_DECAY_DAYS Tagen ohne Tagesbewegung ≥ EXIT_TIME_DECAY_MOVE_PCT linear bis Tag = 2× Threshold → 100.

    Returns dict: ``exit_score, drivers, pnl_pct, days_held, high_since_entry``.
    """
    entry_date_str = position.get("entry_date", "")
    entry_price    = float(position.get("entry_price") or 0.0)
    today          = date.today()
    try:
        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"exit_score": 0.0, "drivers": [], "pnl_pct": 0.0,
                "days_held": 0, "high_since_entry": 0.0}

    days_held = max(0, (today - entry_date).days)
    cur_price = float(current_data.get("price") or 0.0)
    pnl_pct   = (((cur_price - entry_price) / entry_price) * 100.0) if entry_price > 0 else 0.0

    hist_df = current_data.get("history_since")
    try:
        high_since_entry = float(hist_df["High"].max()) if hist_df is not None and not hist_df.empty else max(cur_price, entry_price)
    except Exception:
        high_since_entry = max(cur_price, entry_price)

    drivers: list[str] = []

    # 1) Trailing-Stop
    trailing_pct = 0.0
    if high_since_entry > 0:
        drawdown_pct = max(0.0, (high_since_entry - cur_price) / high_since_entry * 100.0)
        if drawdown_pct >= EXIT_TRAILING_STOP_PCT:
            trailing_pct = 100.0
        else:
            trailing_pct = (drawdown_pct / EXIT_TRAILING_STOP_PCT) * 100.0
        if trailing_pct >= 50:
            drivers.append(f"Trailing-Stop −{drawdown_pct:.1f}% vom Hoch")

    # 2) Setup-Verfall
    setup_pct = 0.0
    setup_today = float(current_data.get("setup_today") or 0.0)
    setup_at_entry: float | None = None
    target = entry_date.strftime("%d.%m.%Y")
    for e in (history.get(ticker) or []):
        d = e.get("date") if isinstance(e, dict) else None
        s = e.get("score") if isinstance(e, dict) else None
        if d == target and s is not None:
            try:
                setup_at_entry = float(s)
            except (TypeError, ValueError):
                setup_at_entry = None
            break
    if setup_at_entry is not None and setup_today > 0:
        drop = setup_at_entry - setup_today
        if drop >= EXIT_SETUP_DROP_THRESHOLD:
            setup_pct = 100.0
        elif drop > 0:
            setup_pct = (drop / EXIT_SETUP_DROP_THRESHOLD) * 100.0
        if setup_pct >= 50:
            drivers.append(f"Setup-Verfall −{drop:.0f} Pkt seit Entry")

    # 3) Distribution-Day
    dist_pct = 0.0
    rvol_today = float(current_data.get("rvol") or 0.0)
    chg_today  = float(current_data.get("change_pct") or 0.0)
    if rvol_today >= EXIT_DISTRIBUTION_RVOL and chg_today < 0:
        dist_pct = 100.0
        drivers.append(f"Distribution {rvol_today:.1f}× / {chg_today:+.1f}%")

    # 4) Time-Decay
    decay_pct = 0.0
    if days_held > EXIT_TIME_DECAY_DAYS and hist_df is not None and not hist_df.empty:
        try:
            recent_chg = (hist_df["Close"].pct_change().abs() * 100.0).fillna(0.0)
            big_moves = int((recent_chg >= EXIT_TIME_DECAY_MOVE_PCT).sum())
            if big_moves == 0:
                excess = days_held - EXIT_TIME_DECAY_DAYS
                decay_pct = min(100.0, (excess / EXIT_TIME_DECAY_DAYS) * 100.0)
                if decay_pct >= 50:
                    drivers.append(f"Time-Decay {days_held}d ohne ≥{EXIT_TIME_DECAY_MOVE_PCT:.0f}% Move")
        except Exception:
            pass

    exit_score = min(100.0, (
        trailing_pct * EXIT_WEIGHT_TRAILING +
        setup_pct    * EXIT_WEIGHT_SETUP +
        dist_pct     * EXIT_WEIGHT_DISTRIBUTION +
        decay_pct    * EXIT_WEIGHT_TIMEDECAY
    ))

    return {
        "exit_score":       round(exit_score, 1),
        "drivers":          drivers,
        "pnl_pct":          round(pnl_pct, 2),
        "days_held":        days_held,
        "high_since_entry": round(high_since_entry, 4),
    }


def process_exit_signals(stocks: list[dict] | None = None) -> int:
    """Lädt positions.json und sendet ntfy-Pushes für offene Positionen.

    • exit_score ≥ EXIT_ALERT_THRESHOLD → ``📉 Exit N | ±N% | top driver``
    • pnl_pct    ≥ EXIT_PROFIT_TAKE_PCT → ``💰 Profit-Take | +N% seit Entry | Halbe Position?``
    Cooldown ``EXIT_COOLDOWN_HOURS`` h pro (Ticker, Alert-Typ) via
    Key-Prefix ``exit_`` / ``profit_`` in agent_state.json.

    ``stocks`` (optional Top-10-Liste vom aktuellen Run) liefert für
    bereits enriched Ticker den geglätteten Setup-Score ohne yfinance-
    Refetch. Returns Anzahl gesendeter Pushes.
    """
    if not EXIT_ENABLED:
        return 0
    positions = _load_positions()
    if not positions:
        return 0

    history = _load_score_history()
    state   = _exit_load_state()
    n_sent = 0

    for ticker, pos in positions.items():
        try:
            entry_date = datetime.strptime(pos.get("entry_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            log.warning("Position %s: ungültiges entry_date %r", ticker, pos.get("entry_date"))
            continue
        market = _fetch_position_market_data(ticker, entry_date)
        if not market:
            continue
        # Heutiger Setup-Score aus score_history (raw, letzter Eintrag) — bewusst
        # NICHT aus setup_scores (smoothed), damit der Vergleich gegen
        # setup_at_entry symmetrisch raw vs. raw bleibt. Sonst erzeugen
        # Eintages-Spikes am Entry-Tag falsche „Setup-Verfall"-Drops, die
        # nur Glättungs-Artefakte sind.
        setup_today: float | None = None
        entries = history.get(ticker) or []
        if entries:
            last = entries[-1]
            last_score = last.get("score") if isinstance(last, dict) else None
            if last_score is not None:
                try:
                    setup_today = float(last_score)
                except (TypeError, ValueError):
                    setup_today = None
        market["setup_today"] = setup_today or 0.0

        result = compute_exit_score(ticker, pos, market, history)
        log.info("Exit %s: score=%.1f pnl=%.1f%% days=%d drivers=%s",
                 ticker, result["exit_score"], result["pnl_pct"],
                 result["days_held"], result["drivers"])

        top_driver = result["drivers"][0] if result["drivers"] else "—"

        if result["exit_score"] >= EXIT_ALERT_THRESHOLD:
            key = f"exit_{ticker}"
            if not _exit_is_on_cooldown(key, state):
                body = (f"{ticker} 📉 Exit {result['exit_score']:.0f} | "
                        f"{result['pnl_pct']:+.0f}% | {top_driver}")
                if _send_exit_ntfy(ticker, body):
                    _exit_set_cooldown(key, state)
                    n_sent += 1

        if result["pnl_pct"] >= EXIT_PROFIT_TAKE_PCT:
            key = f"profit_{ticker}"
            if not _exit_is_on_cooldown(key, state):
                body = (f"{ticker} 💰 Profit-Take | "
                        f"+{result['pnl_pct']:.0f}% seit Entry | Halbe Position?")
                if _send_exit_ntfy(ticker, body):
                    _exit_set_cooldown(key, state)
                    n_sent += 1

    if n_sent > 0:
        _exit_save_state(state)
    return n_sent


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
        # Fallback: Finviz v141 (may be blocked on cloud IPs, but worth trying)
        log.warning("Yahoo screener returned 0 results. Trying Finviz as fallback …")
        candidates = get_finviz_candidates(max_pages=6)

    # Zusätzliche Quelle: Finviz v=111 mit SF>20% + Rel-Vol≥1.5× + Small+-Cap.
    # Läuft parallel zur Yahoo-Primärquelle (nicht nur als Fallback) — erweitert
    # die Kandidaten-Vielfalt um hochspezifische Short-Kandidaten.
    if FINVIZ_SCREENER_ENABLED:
        fv_extra = get_finviz_screener_v111()
        seen_ids = {c["ticker"] for c in candidates}
        n_new = 0
        for fv in fv_extra:
            if fv["ticker"] not in seen_ids:
                candidates.append(fv)
                seen_ids.add(fv["ticker"])
                n_new += 1
        if fv_extra:
            log.info("Finviz v=111 supplement: %d Ticker gesamt, %d neu im Pool",
                     len(fv_extra), n_new)

    log.info("Candidate pool: %d tickers", len(candidates))

    if not candidates:
        log.error("Both screeners failed. Writing error page.")
        _write_error_page(report_date,
            "Screener-Verbindung fehlgeschlagen (Yahoo Finance &amp; Finviz). "
            "Bitte manuell neu starten.")
        return

    # EarningsWhispers-Cache einmal pro Run vorladen — wird später bei
    # Top-10-Enrichment (Step 3c) als Preference über yfinance.Calendar genutzt.
    ew_calendar = fetch_earningswhispers_rss() if EARNINGSWHISPERS_ENABLED else {}

    # Supplement with watchlist volume scan (JP, HK, KR + any that screener missed)
    # — nur wenn INTL_SCREENING_ENABLED; sonst komplett übersprungen.
    existing_tickers = {c["ticker"] for c in candidates}
    if INTL_SCREENING_ENABLED:
        log.info("Step 1b – Watchlist volume scan (batch per region) …")
        watchlist_cands = get_watchlist_candidates()
        for wc in watchlist_cands:
            if wc["ticker"] not in existing_tickers:
                candidates.append(wc)
                existing_tickers.add(wc["ticker"])
    else:
        log.info("Step 1b – Watchlist-Scan übersprungen (INTL_SCREENING_ENABLED=False)")

    # Persönliche Watchlist: manuell hinzugefügte Ticker werden immer einge-
    # pflegt — unabhängig vom Screener-Ergebnis — und als "manual_personal"
    # markiert. So überleben sie später jeden Rang-/Volumen-Filter.
    personal_tickers = _load_personal_watchlist()
    n_personal_added  = 0
    n_personal_marked = 0
    for pt in personal_tickers:
        # Robust: auch bei (theoretischen) Duplikaten in `candidates` jeden
        # Match flaggen — nicht nach erstem Treffer abbrechen.
        matched = False
        for c in candidates:
            if c["ticker"] == pt:
                c["manual_personal"] = True
                matched = True
                n_personal_marked += 1
        if not matched:
            candidates.append({
                "ticker":         pt,
                "company_name":   pt,
                "source":         "personal_watchlist",
                "manual_personal": True,
                # "market" aus Suffix ableiten — damit Intl-Ticker (z.B. SAP.DE)
                # den is_us=False-Pfad treffen: kein Short-Float-Filter, Score
                # gedeckelt bei 50 Pkt, Volumen-Rescue-Logik aktiv.
                "market":         get_region(pt),
                # Minimal-Defaults; Enrichment füllt den Rest.
                "short_float":    0,
                "short_ratio":    0,
                "rel_volume":     0,
            })
            existing_tickers.add(pt)
            n_personal_added += 1
    if personal_tickers:
        log.info("Persönliche Watchlist: %d Ticker — %d neu im Pool, "
                 "%d existierende mit manual_personal=True markiert",
                 len(personal_tickers), n_personal_added, n_personal_marked)

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

    # Persönliche Watchlist: garantiert im Pool — überlebt POOL_MAX-Cap und
    # alle Tier-Filter, identisch zum manual_personal-Bypass in Step 2.
    # Sonst werden Watchlist-Ticker mit niedrigem SF/Volumen still aus dem
    # Pool gekippt und tauchen nie als Karte auf.
    pool_ids = {id(c) for c in pool}
    n_manual_added = 0
    for c in candidates:
        if c.get("manual_personal") and id(c) not in pool_ids:
            pool.append(c)
            pool_ids.add(id(c))
            n_manual_added += 1
    if n_manual_added:
        log.info("Pool: +%d manual_personal-Ticker garantiert eingeschleust "
                 "(POOL_MAX-Cap umgangen)", n_manual_added)

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

    # USD/EUR-Wechselkurs für Chat- + KI-Analyse-Anzeige (alle Kursangaben
    # erscheinen in der Form „$X.XX (Y,YY €)"). Quelle: yfinance EURUSD=X
    # (= Anzahl USD pro 1 EUR). Daraus invertiert: EUR pro 1 USD.
    # Fail-soft: bei Fetch-Fehler letzten persistierten Wert aus app_data.json
    # weiterverwenden, sonst Notnagel 0.92.
    _fx_usd_eur: float = 0.92
    try:
        _fx_hist = yf.download("EURUSD=X", period="2d", auto_adjust=False,
                               progress=False, threads=False)
        if _fx_hist is not None and not _fx_hist.empty:
            _eur_usd = float(_fx_hist["Close"].squeeze().dropna().iloc[-1])
            if _eur_usd > 0:
                _fx_usd_eur = round(1.0 / _eur_usd, 4)
                log.info("USD/EUR Rate: 1 USD = %.4f EUR (EURUSD=%.4f)",
                         _fx_usd_eur, _eur_usd)
    except Exception as _fx_exc:
        log.warning("EURUSD=X fetch failed: %s", _fx_exc)
        try:
            with open("app_data.json", "r", encoding="utf-8") as _adfh:
                _prev = json.load(_adfh).get("fx_usd_eur")
            if isinstance(_prev, (int, float)) and _prev > 0:
                _fx_usd_eur = float(_prev)
                log.info("USD/EUR Rate: stale fallback aus app_data.json: %.4f", _fx_usd_eur)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
    # Modul-Variable setzen, damit _build_chat_synthesis_ctx() und
    # _write_app_data_json() denselben Wert sehen ohne Signatur-Plumbing.
    globals()["_FX_USD_EUR"] = _fx_usd_eur

    # Feature 5 — Sektor-ETF 20T-Performance parallel holen
    _sector_perf_20d: dict[str, float] = {}
    if USE_SECTOR_RS:
        _t_sector = time.time()
        _SECTOR_TIMEOUT = 15
        try:
            with ThreadPoolExecutor(max_workers=1) as _sec_ex:
                _sec_hist = _sec_ex.submit(
                    lambda: yf.download(list(SECTOR_ETFS_ALL), period="25d",
                                        group_by="ticker", auto_adjust=True,
                                        progress=False, threads=True)
                ).result(timeout=_SECTOR_TIMEOUT)
            import pandas as _pd  # local alias
            if _sec_hist is not None and not _sec_hist.empty:
                for _etf in SECTOR_ETFS_ALL:
                    try:
                        _df = _sec_hist[_etf] if isinstance(_sec_hist.columns, _pd.MultiIndex) else _sec_hist
                        _close = _df["Close"].dropna()
                        if len(_close) >= 21:
                            _sector_perf_20d[_etf] = float(
                                (_close.iloc[-1] - _close.iloc[-21]) / _close.iloc[-21] * 100
                            )
                    except Exception:
                        continue
                log.info("Sektor-ETF 20T-Perf: %s",
                         {k: f"{v:.1f}%" for k, v in _sector_perf_20d.items()})
            print(f"Sektor-ETFs ({len(_sector_perf_20d)}/{len(SECTOR_ETFS_ALL)}) "
                  f"in {time.time()-_t_sector:.1f}s abgerufen", flush=True)
        except TimeoutError:
            log.warning("Sektor-ETF yf.download timeout after %ds", _SECTOR_TIMEOUT)
        except Exception as _sec_exc:
            log.warning("Sektor-ETF fetch failed: %s", _sec_exc)

    # --- Step 2: Filter loop — uses pre-fetched batch data, no HTTP per ticker ---
    log.info("Step 2 – Filtering %d candidates with enriched data …", len(pool))
    enriched = []
    _enrich_start = time.time()
    # Source-Telemetrie für die beiden Fallback-Ketten (Summary am Loop-Ende).
    sf_source_counts: dict[str, int] = {"yfinance": 0, "finviz": 0,
                                         "stockanalysis": 0, "none": 0}
    si_source_counts: dict[str, int] = {"finra": 0, "yfinance": 0, "none": 0}
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
        # Feature 5 — Sektor-ETF mapping + RS-Berechnung
        _sector_name = yfd.get("sector") or c.get("sector") or ""
        _sector_etf  = SECTOR_ETF_MAP.get(_sector_name.strip(), SECTOR_ETF_DEFAULT) \
                       if USE_SECTOR_RS else None
        _etf_perf    = _sector_perf_20d.get(_sector_etf) if _sector_etf else None
        _rel_sector  = (
            (_stock_perf_20d - _etf_perf)
            if (_stock_perf_20d is not None and _etf_perf is not None)
            else None
        )
        c.update({
            "company_name":    yfd.get("company_name") or c.get("company_name", t),
            "sector":          _sector_name,
            "industry":        yfd.get("industry") or c.get("industry") or "",
            "yf_market_cap":   yfd.get("market_cap"),
            "52w_high":        yfd.get("52w_high"),
            "52w_low":         yfd.get("52w_low"),
            "avg_vol_20d":     yfd.get("avg_vol_20d", 0),
            "cur_vol":         yfd.get("cur_vol", 0),
            "rsi14":           yfd.get("rsi14"),
            "ma50":             yfd.get("ma50"),
            "ma200":            yfd.get("ma200"),
            "perf_20d":         _stock_perf_20d,
            "rel_strength_20d": _rel_strength,
            "rel_strength_sector": _rel_sector,        # Feature 5 (deprecated — RS-vs-Sektor entfernt)
            "sector_etf":          _sector_etf,        # Feature 5 (nur noch interne Spur)
            "cur_open":            yfd.get("cur_open"),
            "prev_close":          yfd.get("prev_close"),
            "inst_ownership":  yfd.get("inst_ownership"),
            "float_shares":    yfd.get("float_shares", 0),
            "change_5d":       yfd.get("change_5d"),
            "spx_daily_perf":  _spx_daily_perf,
            "recent_squeeze":  yfd.get("recent_squeeze"),   # Feature 6
            "rel_volume_yesterday": yfd.get("rel_volume_yesterday"),  # P&D Flag 1
        })
        if i < 3:
            print(f"{t} float_shares={c.get('float_shares')} change_5d={c.get('change_5d')}", flush=True)
        # Short-Float Fallback-Kette: yfinance → screener-Cache → finviz
        # → stockanalysis → none. Verhindert dass Ticker mit yf=0.0/None
        # fälschlich als „kein Short-Interest" gefiltert werden.
        yf_sf      = yfd.get("short_float_yf", None)
        cached_sf  = c.get("short_float") or None  # aus Screener-Stage
        sf_value, sf_source = get_short_float_with_fallback(t, yf_sf, cached_sf)
        sf_source_counts[sf_source] = sf_source_counts.get(sf_source, 0) + 1
        if sf_value is not None:
            c["short_float"] = sf_value
        # else: c["short_float"] bleibt was Screener gegeben hat (oft 0.0);
        # der Skip-Pfad fängt sf_source=="none" separat ab.
        c["short_float_source"] = sf_source
        if sf_source not in ("yfinance", "none") and sf_value is not None:
            log.info("  SF-Fallback %s: %s → %.1f%%", t, sf_source, sf_value)

        yf_sr = yfd.get("short_ratio", 0)
        if yf_sr > 0:
            c["short_ratio"] = yf_sr
        if yfd.get("vol_ratio", 0) > 0:
            c["rel_volume"] = yfd["vol_ratio"]

        # FINRA daily short-volume data (US only; local dict lookup — no HTTP).
        # SI-Trend Fallback: bei trend=="no_data" oder <5 history-Punkten fällt
        # die Berechnung auf yfinance sharesShort / sharesShortPriorMonth zurück.
        is_us_finra = c.get("market", "US") == "US"
        if is_us_finra:
            fd = get_finra_short_interest(t, finra_dates)
            hist_len = len(fd.get("history", []))
            if fd.get("trend", "no_data") == "no_data" or hist_len < 5:
                yf_trend = _fetch_si_trend_from_yfinance(t)
                if yf_trend["trend"] != "no_data":
                    fd["trend"]     = yf_trend["trend"]
                    fd["trend_pct"] = yf_trend["trend_pct"]
                    fd["si_trend_source"] = "yfinance"
                    log.info("  SI-Trend Fallback %s: yfinance → %+.1f%% (%s)",
                             t, yf_trend["trend_pct"], yf_trend["trend"])
                else:
                    fd["si_trend_source"] = "none"
            else:
                fd["si_trend_source"] = "finra"
            c["finra_data"] = fd
        else:
            c["finra_data"] = {"si_trend_source": "none"}
        si_source_counts[c["finra_data"].get("si_trend_source", "none")] = (
            si_source_counts.get(c["finra_data"].get("si_trend_source", "none"), 0) + 1
        )
        # Backwards-Compat: altes ``sf_source``-Feld bleibt mitgeführt, damit
        # eventuell unbekannte Consumer nicht plötzlich None lesen. Mappt auf
        # menschenlesbares Label ("Yahoo Finance", "Finviz", …).
        _SF_SRC_LABEL = {"yfinance": "Yahoo Finance", "finviz": "Finviz",
                         "stockanalysis": "Stockanalysis", "none": "—"}
        c["sf_source"] = _SF_SRC_LABEL.get(sf_source, "—")

        # Hard filters — manual_personal-Ticker (persönliche Watchlist) sind
        # vollständig befreit: kein Cap-Filter, kein Short-Float-Filter, kein
        # RVOL-Filter. Der User hat sie explizit angefordert und sie sollen
        # garantiert als Karte erscheinen, unabhängig von ihren Kennzahlen.
        if c.get("manual_personal"):
            log.info("    keep %s [manual_personal]: alle Filter umgangen", t)
        else:
            cap = c.get("yf_market_cap") or c.get("market_cap")
            if cap and cap > MAX_MARKET_CAP:
                log.info("    skip %s: cap %s > $10B", t, fmt_cap(cap))
                continue

            # Short-float filter: strict for US; relaxed for non-US (data rarely available)
            is_us = c.get("market", "US") == "US"
            has_sf_data = c["short_float"] > 0
            if is_us and c.get("short_float_source") == "none":
                log.info("    skip %s: short_float unknown (alle Quellen ausgefallen)", t)
                continue
            if is_us and c["short_float"] < MIN_SHORT_FLOAT:
                log.info("    skip %s: short_float %.1f%% < %.0f%% (Quelle: %s)",
                         t, c["short_float"], MIN_SHORT_FLOAT,
                         c.get("short_float_source", "?"))
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
    log.info(
        "SF-Quellen: %d× yfinance, %d× finviz, %d× stockanalysis, %d× none",
        sf_source_counts["yfinance"], sf_source_counts["finviz"],
        sf_source_counts["stockanalysis"], sf_source_counts["none"],
    )
    log.info(
        "SI-Quellen: %d× finra, %d× yfinance, %d× none",
        si_source_counts["finra"], si_source_counts["yfinance"],
        si_source_counts["none"],
    )
    print(f"Step 2 abgeschlossen in {time.time()-_t_batch:.1f}s", flush=True)

    # Feature 7 — Post-Enrichment Marktkapitalisierungs-Filter (jetzt 2 Mrd.)
    # Ausnahme: manuell zur persönlichen Watchlist hinzugefügte Ticker
    # ignorieren den Filter und bleiben immer sichtbar.
    _pre_cap = len(enriched)
    enriched = [
        c for c in enriched
        if c.get("manual_personal")
        or not (c.get("yf_market_cap") or c.get("market_cap"))
        or (c.get("yf_market_cap") or c.get("market_cap") or 0) <= MAX_MARKET_CAP
    ]
    if _pre_cap > len(enriched):
        print(
            f"Cap-Filter ({MAX_MARKET_CAP_B:.0f} Mrd. $): "
            f"{_pre_cap - len(enriched)} Ticker ausgeschlossen (persönliche Watchlist immun)",
            flush=True,
        )

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

    # Persönliche Watchlist: jeder markierte Ticker erscheint garantiert —
    # entweder organisch im Top-10 (dann mit normaler Rang-Nummer) oder als
    # "Bonus-Slot" angehängt (mit 📌 Manuell-beobachtet-Badge statt Rang).
    # Bonus-Slots nach Score absteigend sortiert; Score=0/None/NaN ans Ende
    # (via _safe_float → 0.0 bei reverse=True).
    _top10_ids = {id(c) for c in top10}
    manual_extras = sorted(
        [c for c in enriched
         if c.get("manual_personal") and id(c) not in _top10_ids],
        key=lambda c: _safe_float(c.get("score")),
        reverse=True,
    )
    if manual_extras:
        for c in manual_extras:
            c["manual_forced"] = True
        log.info("Manuelle Watchlist-Ticker außerhalb Top-10: +%d Bonus-Slot(s): %s",
                 len(manual_extras), [c["ticker"] for c in manual_extras])
        top10.extend(manual_extras)

    if not top10:
        log.error("No candidates survived all filters.")
        _write_error_page(report_date,
            "Keine Aktien erfüllen aktuell alle Filterkriterien "
            f"(Short Float &gt;15 %, Preis &gt;$1, Marktkapitalisierung &lt;{MAX_MARKET_CAP_B:.0f} Mrd. $).")
        return

    # --- Step 3b: FINRA-Trend-Bonus ---
    for s in top10:
        bonus = score_bonus(s)
        s["finra_bonus_pts"] = float(bonus)  # 0.0 wenn kein Bonus
        if bonus > 0:
            base = s["score"]
            s["score"] = round(min(base + bonus, 100.0), 2)
            log.info("  %s: base=%.2f + bonus=%.2f = %.2f",
                     s["ticker"], base, bonus, s["score"])

    # Sortierung: organische Top-10 und manual_forced-Bonus-Slots werden
    # getrennt sortiert und erst am Ende zusammengeführt — damit der
    # Watchlist-Block immer als Gruppe ganz hinten steht, nie nach Score
    # zwischen die organischen Karten eingemischt.
    def _sort_keeping_manual_last(stocks: list[dict]) -> list[dict]:
        organic = [c for c in stocks if not c.get("manual_forced")]
        manual  = [c for c in stocks if     c.get("manual_forced")]
        organic.sort(key=lambda x: x.get("score") or 0, reverse=True)
        manual.sort( key=lambda x: x.get("score") or 0, reverse=True)
        return organic + manual

    top10 = _sort_keeping_manual_last(top10)

    # --- Step 3a: Score smoothing (70 % today + 30 % avg last 3 runs) ---
    apply_score_smoothing(top10, report_date)

    # Feature 2 — Agent-Boost: KI-Agent-Score als Multiplikator on-top.
    # Kommt NACH dem Smoothing, damit die History den unboosted Base-Score
    # behält (sonst würde der Boost sich selbst verstärken).
    apply_agent_boost(top10)

    # Monster-Score: Setup × KI-Signal-Gewichtung. Erfordert apply_agent_boost
    # (für ki_signal_score). Schreibt s["monster_score"] (float).
    apply_monster_score(top10)

    # Borrow-Metriken (Display-Only): CTB + Utilization von Stockanalysis,
    # Fallback IBKR für CTB. Beide Felder fließen NICHT in den Score und
    # bleiben None bei Fetch-Fehler. Nur US-Ticker (Stockanalysis indexiert
    # keine .DE/.L/.HK; IBKR-Tabelle ebenfalls US-only).
    if IBKR_BORROW_ENABLED or STOCKANALYSIS_BORROW_ENABLED:
        for _s in top10:
            if "." in _s["ticker"]:
                continue
            _bm = fetch_borrow_metrics(_s["ticker"])
            _s["cost_to_borrow"] = _bm.get("cost_to_borrow")
            _s["utilization"]    = _bm.get("utilization")
            # Backwards-Compat: borrow_rate-Feld bleibt erhalten (nutzt
            # gleichen Wert; existing-Code in _agent_boost_row_html etc.
            # könnte es lesen).
            _s["borrow_rate"]    = _s["cost_to_borrow"]

    top10 = _sort_keeping_manual_last(top10)

    # Opt 3 — Parallel news fetching (all 10 tickers × 3 sources concurrently).
    _t_news = time.time()
    log.info("Step 3 – Fetching news for %d stocks (parallel, max 13 threads) …", len(top10))
    with ThreadPoolExecutor(max_workers=13) as _news_ex:
        _news_futures = {_news_ex.submit(get_combined_news, s["ticker"]): s for s in top10}
        for _fut in as_completed(_news_futures):
            _news_futures[_fut]["news"] = _fut.result() or []
    _news_elapsed = time.time() - _t_news
    print(f"News: {len(top10)} Ticker parallel in {_news_elapsed:.1f}s abgerufen", flush=True)

    # Parallel options data fetch (US-only, Top-5, max 5 threads).
    # Opt 4 (2026-04): nur erste 5 Ticker von us_top10 — restliche Karten
    # zeigen „—" bei IV und P/C. Spart pro fehlendem Ticker eine yfinance-
    # Options-Chain-Abfrage (teuerster Einzelcall im Step 3).
    # Fix 3: as_completed(timeout=30) — skip remaining futures after 30s total
    _POOL_STEP3_TIMEOUT = 30
    _OPTS_TOP_N = 5
    _t_opts = time.time()
    us_top10 = [s for s in top10 if "." not in s["ticker"]]
    us_for_opts = us_top10[:_OPTS_TOP_N]
    log.info("Step 3b – Fetching options data for Top-%d US stocks (parallel, max 5 threads) …",
             len(us_for_opts))
    with ThreadPoolExecutor(max_workers=5) as _opts_ex:
        _opts_futures = {_opts_ex.submit(get_options_data, s["ticker"]): s for s in us_for_opts}
        try:
            for _fut in as_completed(_opts_futures, timeout=_POOL_STEP3_TIMEOUT):
                _opts_futures[_fut]["options"] = _fut.result() or {}
        except TimeoutError:
            print(f"Optionsdaten: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                  flush=True)
            log.warning("options as_completed timeout — skipping remaining futures")
    _opts_elapsed = time.time() - _t_opts
    _n_ok = sum(1 for s in us_for_opts if s.get("options"))
    _n_na = len(us_for_opts) - _n_ok
    print(f"Optionsdaten: Top-{len(us_for_opts)} von {len(us_top10)} US-Tickern parallel in "
          f"{_opts_elapsed:.1f}s abgerufen — {_n_ok} mit Daten, {_n_na} ohne", flush=True)

    # Parallel earnings date fetch (US-only, max 5 threads).
    # EarningsWhispers-Override: falls der Ticker im RSS-Cache ist, nutzen wir
    # dessen präziseren Termin + EPS-Schätzung statt yfinance.calendar.
    _t_earn = time.time()
    log.info("Step 3c – Fetching earnings dates for %d US stocks …", len(us_top10))
    _today_et = datetime.now(EASTERN).date() if 'EASTERN' in globals() else datetime.now(ZoneInfo("America/New_York")).date()
    _ew_applied = 0
    _ew_tickers = [s for s in us_top10 if s["ticker"] in ew_calendar]
    for s in _ew_tickers:
        entry = ew_calendar.get(s["ticker"], {})
        iso = entry.get("date")
        if not iso:
            continue
        try:
            edate = datetime.strptime(iso, "%Y-%m-%d").date()
            days = (edate - _today_et).days
            if days >= 0:
                s["earnings_days"]     = days
                s["earnings_date_str"] = edate.strftime("%d.%m.")
                if entry.get("eps_estimate") is not None:
                    s["earnings_eps_estimate"] = entry["eps_estimate"]
                _ew_applied += 1
        except Exception:
            continue
    if _ew_applied:
        print(f"EarningsWhispers-Override angewendet: {_ew_applied} Ticker", flush=True)

    _remaining_for_yf = [s for s in us_top10 if s.get("earnings_days") is None]
    with ThreadPoolExecutor(max_workers=5) as _earn_ex:
        _earn_futures = {_earn_ex.submit(get_earnings_date, s["ticker"]): s
                         for s in _remaining_for_yf}
        try:
            for _fut in as_completed(_earn_futures, timeout=_POOL_STEP3_TIMEOUT):
                _days, _dstr = _fut.result()
                _earn_futures[_fut]["earnings_days"] = _days
                _earn_futures[_fut]["earnings_date_str"] = _dstr
        except TimeoutError:
            print(f"Earnings-Termine: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                  flush=True)
            log.warning("earnings as_completed timeout — skipping remaining futures")
    print(f"Earnings-Termine: {len(us_top10)} Ticker (yf: {len(_remaining_for_yf)}, EW: {_ew_applied}) in "
          f"{time.time()-_t_earn:.1f}s abgerufen", flush=True)

    # Stockanalysis.com Short-Interest-Override (US-Top-10, parallel).
    # Stockanalysis publiziert wöchentlich — jünger als yfinance-Snapshot.
    # Wert wird nur übernommen, wenn erfolgreich geparst; yfinance bleibt
    # sonst autoritativ.
    if STOCKANALYSIS_SI_ENABLED:
        _t_sa = time.time()
        log.info("Step 3c3 – Stockanalysis.com SI für %d US-Ticker …", len(us_top10))
        with ThreadPoolExecutor(max_workers=5) as _sa_ex:
            _sa_futures = {_sa_ex.submit(fetch_stockanalysis_si, s["ticker"]): s
                           for s in us_top10}
            try:
                for _fut in as_completed(_sa_futures, timeout=_POOL_STEP3_TIMEOUT):
                    sa_val = _fut.result()
                    if sa_val is None:
                        continue
                    st = _sa_futures[_fut]
                    yf_val = st.get("short_float", 0.0)
                    # Sanity: 0 < sa_val < 100; prefer stockanalysis
                    if 0 < sa_val < 100 and abs(sa_val - yf_val) > 0.1:
                        print(f"{st['ticker']} SI aktualisiert: yfinance={yf_val:.1f}% → "
                              f"stockanalysis={sa_val:.1f}%", flush=True)
                        st["short_float"]        = sa_val
                        st["short_float_source"] = "stockanalysis"
                        st["sf_source"]          = "Stockanalysis"  # legacy label
            except TimeoutError:
                log.warning("stockanalysis SI Pool-Timeout")
        print(f"Stockanalysis SI: abgeschlossen in {time.time()-_t_sa:.1f}s", flush=True)

    # Feature 3 — Parallel earnings-surprise fetch (US-only, max 5 threads).
    if SHOW_EARNINGS_SURPRISE:
        _t_es = time.time()
        log.info("Step 3c2 – Fetching earnings surprise for %d US stocks …", len(us_top10))
        with ThreadPoolExecutor(max_workers=5) as _es_ex:
            _es_futures = {_es_ex.submit(get_earnings_surprise, s["ticker"]): s for s in us_top10}
            try:
                for _fut in as_completed(_es_futures, timeout=_POOL_STEP3_TIMEOUT):
                    _es_futures[_fut]["earnings_surprise"] = _fut.result()
            except TimeoutError:
                print(f"Earnings-Surprise: Pool-Timeout nach {_POOL_STEP3_TIMEOUT}s — verbleibende Ticker übersprungen",
                      flush=True)
                log.warning("earnings-surprise as_completed timeout — skipping remaining futures")
        _n_es = sum(1 for s in us_top10 if s.get("earnings_surprise"))
        print(f"Earnings-Surprise: {_n_es}/{len(us_top10)} Treffer in {time.time()-_t_es:.1f}s",
              flush=True)

    # Parallel SEC 13F fetch (US-only, max 5 threads) — gated by SEC_13F_ENABLED.
    # Opt 5 (2026-04): standardmäßig deaktiviert — lieferte seit Monaten
    # ~0 Treffer bei ~0,5 s Kosten; Reaktivierung via config.SEC_13F_ENABLED=True.
    if SEC_13F_ENABLED:
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
    else:
        log.info("Step 3d – SEC 13F übersprungen (SEC_13F_ENABLED=False)")
    print(f"Step 3 abgeschlossen in {time.time() - _t_news:.1f}s", flush=True)

    # Backtest-History: pro Top-10-Ticker einen Eintrag anlegen (idempotent,
    # dedupliziert nach ticker+date). Returns werden später vom KI-Agent
    # aktualisiert, sobald 3/5/10 Handelstage vergangen sind.
    _append_backtest_entries(top10, report_date, pool_size=len(enriched))

    # --- Step 4: HTML ---
    _t4 = time.time()
    log.info("Step 4 – Generating HTML report …")
    html = generate_html(top10, report_date)
    if os.environ.get("JINJA_RENDER_TEST") == "1":
        _render_test(top10, report_date)

    # Defense-in-Depth: trotz Sanitizing am Ingestion-Point können Surrogates
    # auf neuen API-Pfaden auftauchen. Diagnose + Fallback verhindert den Crash.
    surrogates = [(i, hex(ord(c))) for i, c in enumerate(html)
                  if 0xD800 <= ord(c) <= 0xDFFF]
    if surrogates:
        log.warning("Surrogates im HTML gefunden (%d Stück): %s",
                    len(surrogates), surrogates[:5])
        pos = surrogates[0][0]
        log.warning("Kontext um erste Fundstelle: %r",
                    html[max(0, pos - 100):pos + 100])
        html = strip_surrogates(html)

    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)

    # Service-Worker mit frischem Cache-Version-String (pro Run ein neuer
    # Zeitstempel) — Browser invalidieren alten Cache beim nächsten Besuch.
    if SW_ENABLED:
        _write_service_worker()
    # Kombinierte app_data.json (PWA-Single-Fetch).
    # watchlist_cards: vollständige Karten-Daten für ALLE persönlichen
    # Watchlist-Ticker (auch nicht-Top-10), damit der Browser im expandierten
    # Watchlist-Zustand echte Werte statt „—"-Platzhalter zeigen kann.
    # Primär: alle in enriched markierten manual_personal-Einträge.
    # Fallback: Ticker aus watchlist_personal.json per Namen suchen — falls
    # das manual_personal-Flag durch Pool-Filter verloren ging, sind die Daten
    # trotzdem in enriched, wir matchen sie via Ticker-Symbol.
    _wl_card_data = {
        c["ticker"]: _wl_card_payload(c)
        for c in enriched
        if c.get("manual_personal")
    }
    _personal_tickers = set(_load_personal_watchlist())
    _fallback_added = 0
    for c in enriched:
        if c["ticker"] in _personal_tickers and c["ticker"] not in _wl_card_data:
            _wl_card_data[c["ticker"]] = _wl_card_payload(c)
            _fallback_added += 1
    if _fallback_added:
        log.info("Watchlist-Karten: %d Ticker per manual_personal-Flag, "
                 "%d zusätzlich per Namens-Fallback gefunden",
                 len(_wl_card_data) - _fallback_added, _fallback_added)
    _monster_scores = {
        s["ticker"]: round(s["monster_score"], 1)
        for s in top10
        if s.get("monster_score") is not None
    }
    # Geglätteter Setup-Score (post apply_score_smoothing) — exakt der Wert,
    # den die Kachel rendert. Wird vom KI-Agent für den Alert-Text gelesen,
    # damit Setup im Alert mit dem Frontend matcht (score_history enthält
    # nur den rohen pre-smoothing-Wert).
    _setup_scores = {
        s["ticker"]: round(float(s["score"]), 1)
        for s in top10
        if s.get("score") is not None
    }
    # Gap+Hold-State pro Top-10-Ticker — wird vom KI-Agent für die Anomalie-
    # Erkennung „Gap-Hold + RVOL Combo" gelesen. Schema:
    #   { ticker: { "pct": float, "state": "strong_hold"|"weak_hold"|"fail"|"no_gap"|"unknown" } }
    _gap_states = {}
    for s in top10:
        gp, st, _pts = _gap_hold_pts(s)
        if st == "unknown":
            continue
        _gap_states[s["ticker"]] = {
            "pct":   round(gp, 2) if gp is not None else None,
            "state": st,
        }
    _write_app_data_json(watchlist_cards=_wl_card_data,
                         monster_scores=_monster_scores,
                         setup_scores=_setup_scores,
                         gap_states=_gap_states)
    print(f"Step 4 abgeschlossen in {time.time()-_t4:.1f}s", flush=True)

    # Step 5 — Exit-Signale für offene Positionen (Phase 1, kein Frontend).
    # Liest positions.json (vom Workflow aus GitHub Secret POSITIONS_JSON
    # erzeugt) und feuert ntfy-Pushes bei Exit-Score ≥ EXIT_ALERT_THRESHOLD
    # bzw. PnL ≥ EXIT_PROFIT_TAKE_PCT — Cooldown EXIT_COOLDOWN_HOURS.
    try:
        _t5 = time.time()
        n_exit = process_exit_signals(top10)
        if n_exit > 0:
            log.info("Step 5 — %d Exit/Profit-Push(es) gesendet (%.1fs)",
                     n_exit, time.time() - _t5)
    except Exception as exc:
        log.warning("process_exit_signals fehlgeschlagen: %s", exc)

    log.info("Report written → index.html")
    log.info("Top 10: %s", [s["ticker"] for s in top10])
    log.info("Supplementary data summary: FINRA=%d/10", _finra_stats["ok"])
    print(
        f"[Datenabruf-Zusammenfassung] "
        f"FINRA: {_finra_stats['ok']} erfolgreich, "
        f"{_finra_stats['empty']} leer, "
        f"{_finra_stats['err']} Fehler",
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
