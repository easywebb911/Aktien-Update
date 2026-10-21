"""Mock-Tests für den News-Coverage-Watchdog (21.10.2026).

SCHRITT-0-Befund: ``get_yahoo_news``/``get_combined_news`` (generate_report.py)
lieferten ab 02.10.2026 02:16 UTC in JEDEM Lauf 0 Items für ALLE Karten
(Top-10 + Watchlist) — bestätigt per app_data.json-Commit-Historie (5/5 →
0/5 ab 29.09. 15:52, Recovery 30.09. 12:36, erneuter und bis mindestens
21.10.2026 anhaltender Totalausfall ab 02.10. 02:16). Es existierte KEIN
persistierter Zähler für diesen Pfad — ki_agent.py's EIGENE, unabhängige
News-Pipeline (5 RSS-Quellen, Tier-3-Provider ``news_rss``) lief unbemerkt
davon unverändert weiter, daher zeigte der KI-Block weiterhin News-Treffer
während die Karte "Keine Nachrichten verfügbar" zeigte. Siehe
SESSION_HANDOVER.md für die volle Diagnose.

Verriegelt die harten Invarianten:
  1  RAW/KEPT/DROPPED-ZÄHLER: ``get_yahoo_news`` zählt vor dem Altersfilter
     (raw), nach dem Altersfilter (kept) und wegen Alter verworfen
     (dropped_age) — pro Exception-Typ ein eigener Zähler.
  2  EXCEPTION-TYP-ZÄHLER: eine yf.Ticker-Exception landet im
     ``exception_counts``-Dict unter ihrem Typnamen.
  3  RSS-FALLBACK liefert, wenn yfinance ein LEERES Ergebnis liefert.
  4  RSS-FALLBACK liefert, wenn yfinance eine EXCEPTION wirft.
  5  BEIDE LEER → [] mit korrektem Zähler (kein Crash).
  6  ALTERSFILTER unverändert — gilt auch für RSS-Fallback-Items.
  7  ANFRAGEZAHL: RSS-Fallback wird NICHT aufgerufen, wenn yfinance liefert
     (Zero-New-Request-Beleg für den Normalfall).
  8  COVERAGE-PERSISTENZ: ``_persist_news_coverage`` schreibt eine Zeile
     mit den erwarteten Feldern (Top-10/Watchlist-Split, Quellenzähler).
  9  IDEMPOTENZ: derselbe (date, run_phase) erzeugt keine Duplikat-Zeile.
 10  FEATURE-FLAG: ``NEWS_COVERAGE_LOG_ENABLED = False`` → keine Datei.
 11  DIGEST-ZEILEN: absent/leer/ok (``news_coverage_liveness_line``) +
     Warnzeile bei 0-Abdeckung im Fenster, KEINE Warnzeile sonst
     (``news_coverage_warn_line``).
 12  SCORE-/TOP-10-GEGENPROBE: ``score()`` und Top-10-Sortierreihenfolge
     sind mit leeren und gefüllten News identisch (News beeinflusst nur
     den Anzeige-Teilwert Katalysator-Sub-Score, NICHT score()).
 13  format_digest_body-VERDRAHTUNG: neue Parameter erscheinen in allen
     drei Antwort-Klassen, bestehende Zeilen/Zähler unverändert.

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Import zieht _install_stubs() + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import gr  # noqa: E402

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _reset_acct():
    gr._news_coverage_acct_reset()


def _fresh_coverage_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "news_coverage_history.jsonl")
    gr.NEWS_COVERAGE_LOG_FILE = path
    return path


def _load_lines(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out


class _FakeTicker:
    """Double für yf.Ticker — ``.news`` liefert eine feste Liste oder wirft."""
    def __init__(self, items=None, raise_exc=None):
        self._items = items if items is not None else []
        self._raise_exc = raise_exc

    @property
    def news(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._items


def _yahoo_item(title, ts):
    return {
        "content": {"title": title, "pubDate": ts, "provider": {"displayName": "Yahoo Finance"}},
    }


# ===========================================================================
# 1-2: raw/kept/dropped + Exception-Typ-Zähler
# ===========================================================================

def test_raw_kept_dropped_counters():
    _reset_acct()
    now = 2_000_000_000.0
    orig_time = gr.time.time
    gr.time.time = lambda: now
    orig_ticker = gr.yf.Ticker
    try:
        # 1 frisches Item (heute) + 1 zu altes Item (> NEWS_MAX_AGE_DAYS_DISPLAY)
        old_ts = int(now - (gr.NEWS_MAX_AGE_DAYS_DISPLAY + 5) * 86400)
        fresh_ts = int(now - 3600)
        gr.yf.Ticker = lambda t: _FakeTicker([
            _yahoo_item("Fresh headline", fresh_ts),
            _yahoo_item("Old headline", old_ts),
        ])
        result = gr.get_yahoo_news("TEST")
        _check("raw=2 nach Lauf", gr._NEWS_COVERAGE_ACCT["yfinance_raw"] == 2)
        _check("kept=1 (nur frisches Item)", gr._NEWS_COVERAGE_ACCT["yfinance_kept"] == 1)
        _check("dropped_age=1 (altes Item verworfen)",
               gr._NEWS_COVERAGE_ACCT["yfinance_dropped_age"] == 1)
        _check("Rückgabe enthält nur das frische Item", len(result) == 1
               and result[0]["title_orig"] == "Fresh headline")
    finally:
        gr.yf.Ticker = orig_ticker
        gr.time.time = orig_time


def test_exception_type_counter():
    _reset_acct()
    orig_ticker = gr.yf.Ticker
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(raise_exc=ValueError("boom"))
        result = gr.get_yahoo_news("TEST")
        _check("Exception → leere Liste", result == [])
        _check("exception_counts zählt ValueError",
               gr._NEWS_COVERAGE_ACCT["exception_counts"].get("ValueError") == 1)
    finally:
        gr.yf.Ticker = orig_ticker


# ===========================================================================
# 3-5: RSS-Fallback-Logik
# ===========================================================================

def test_rss_fallback_on_empty_yfinance():
    _reset_acct()
    orig_ticker = gr.yf.Ticker
    orig_rss = gr._rss_news
    try:
        gr.yf.Ticker = lambda t: _FakeTicker([])  # yfinance leer
        calls = []

        def _fake_rss(ticker, url, source_label, timeout=3):
            calls.append((ticker, url, source_label))
            return [{
                "title": "RSS headline", "title_orig": "RSS headline",
                "summary_raw": "", "publisher": "Yahoo RSS", "source": "Yahoo RSS",
                "link": "#", "time": "21.10.2026 10:00", "ts": int(datetime.now(timezone.utc).timestamp()),
            }]
        gr._rss_news = _fake_rss
        result = gr.get_combined_news("TEST")
        _check("RSS-Fallback wurde aufgerufen", len(calls) == 1)
        _check("RSS-Fallback nutzt Yahoo-RSS-URL",
               calls[0][1] == "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TEST")
        _check("RSS-Fallback liefert Item zurück", len(result) == 1
               and result[0]["title_orig"] == "RSS headline")
        _check("rss_fallback_calls=1", gr._NEWS_COVERAGE_ACCT["rss_fallback_calls"] == 1)
        _check("rss_fallback_kept=1", gr._NEWS_COVERAGE_ACCT["rss_fallback_kept"] == 1)
    finally:
        gr.yf.Ticker = orig_ticker
        gr._rss_news = orig_rss


def test_rss_fallback_on_yfinance_exception():
    _reset_acct()
    orig_ticker = gr.yf.Ticker
    orig_rss = gr._rss_news
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(raise_exc=RuntimeError("down"))
        calls = []

        def _fake_rss(ticker, url, source_label, timeout=3):
            calls.append(ticker)
            return [{
                "title": "RSS after exc", "title_orig": "RSS after exc",
                "summary_raw": "", "publisher": "Yahoo RSS", "source": "Yahoo RSS",
                "link": "#", "time": "", "ts": int(datetime.now(timezone.utc).timestamp()),
            }]
        gr._rss_news = _fake_rss
        result = gr.get_combined_news("TEST")
        _check("RSS-Fallback greift auch nach Exception", len(calls) == 1)
        _check("Ergebnis trotz yfinance-Exception nicht leer", len(result) == 1)
    finally:
        gr.yf.Ticker = orig_ticker
        gr._rss_news = orig_rss


def test_both_sources_empty():
    _reset_acct()
    orig_ticker = gr.yf.Ticker
    orig_rss = gr._rss_news
    try:
        gr.yf.Ticker = lambda t: _FakeTicker([])
        gr._rss_news = lambda *a, **k: []
        result = gr.get_combined_news("TEST")
        _check("beide Quellen leer → []", result == [])
        _check("tickers_total erhöht trotz leerem Ergebnis",
               gr._NEWS_COVERAGE_ACCT["tickers_total"] == 1)
        _check("tickers_with_news NICHT erhöht",
               gr._NEWS_COVERAGE_ACCT["tickers_with_news"] == 0)
    finally:
        gr.yf.Ticker = orig_ticker
        gr._rss_news = orig_rss


# ===========================================================================
# 6: Altersfilter gilt auch für RSS-Fallback-Items
# ===========================================================================

def test_rss_fallback_age_filter():
    _reset_acct()
    now = 2_000_000_000.0
    orig_time = gr.time.time
    gr.time.time = lambda: now
    orig_ticker = gr.yf.Ticker
    orig_rss = gr._rss_news
    try:
        gr.yf.Ticker = lambda t: _FakeTicker([])
        old_ts = int(now - (gr.NEWS_MAX_AGE_DAYS_DISPLAY + 10) * 86400)
        fresh_ts = int(now - 7200)

        def _fake_rss(ticker, url, source_label, timeout=3):
            return [
                {"title": "old", "title_orig": "old", "summary_raw": "",
                 "publisher": "Yahoo RSS", "source": "Yahoo RSS", "link": "#",
                 "time": "", "ts": old_ts},
                {"title": "fresh", "title_orig": "fresh", "summary_raw": "",
                 "publisher": "Yahoo RSS", "source": "Yahoo RSS", "link": "#",
                 "time": "", "ts": fresh_ts},
            ]
        gr._rss_news = _fake_rss
        result = gr.get_combined_news("TEST")
        _check("Altes RSS-Item wird gefiltert", len(result) == 1)
        _check("Nur das frische RSS-Item bleibt übrig",
               result[0]["title_orig"] == "fresh")
    finally:
        gr.yf.Ticker = orig_ticker
        gr._rss_news = orig_rss
        gr.time.time = orig_time


# ===========================================================================
# 7: Anfragezahl — RSS-Fallback NICHT aufgerufen bei liefernder yfinance-Quelle
# ===========================================================================

def test_no_rss_fallback_when_yfinance_delivers():
    _reset_acct()
    orig_ticker = gr.yf.Ticker
    orig_rss = gr._rss_news
    try:
        fresh_ts = int(datetime.now(timezone.utc).timestamp()) - 60
        gr.yf.Ticker = lambda t: _FakeTicker([_yahoo_item("Yahoo headline", fresh_ts)])
        calls = []
        gr._rss_news = lambda *a, **k: calls.append(1) or []
        result = gr.get_combined_news("TEST")
        _check("RSS-Fallback NICHT aufgerufen (yfinance lieferte)", len(calls) == 0)
        _check("Yahoo-Item kommt unverändert durch", len(result) == 1
               and result[0]["title_orig"] == "Yahoo headline")
        _check("rss_fallback_calls bleibt 0", gr._NEWS_COVERAGE_ACCT["rss_fallback_calls"] == 0)
    finally:
        gr.yf.Ticker = orig_ticker
        gr._rss_news = orig_rss


# ===========================================================================
# 8-10: Coverage-Persistenz + Idempotenz + Feature-Flag
# ===========================================================================

def test_persist_news_coverage_writes_expected_fields():
    _reset_acct()
    path = _fresh_coverage_file()
    gr.NEWS_COVERAGE_LOG_ENABLED = True
    gr._NEWS_COVERAGE_ACCT["yfinance_raw"] = 10
    gr._NEWS_COVERAGE_ACCT["yfinance_kept"] = 7
    gr._NEWS_COVERAGE_ACCT["yfinance_dropped_age"] = 3
    gr._NEWS_COVERAGE_ACCT["rss_fallback_calls"] = 2
    gr._NEWS_COVERAGE_ACCT["rss_fallback_kept"] = 1
    top10 = [{"ticker": "AAA", "news": [{"title": "x"}]}, {"ticker": "BBB", "news": []}]
    enriched = top10 + [
        {"ticker": "CCC", "manual_personal": True, "news": [{"title": "y"}]},
        {"ticker": "DDD", "manual_personal": True, "news": []},
    ]
    n = gr._persist_news_coverage(top10, enriched, report_date_iso="2026-10-21",
                                  run_phase="postclose")
    _check("1 neue Zeile geschrieben", n == 1)
    lines = _load_lines(path)
    _check("genau 1 Zeile in der Datei", len(lines) == 1)
    row = lines[0]
    _check("date korrekt", row["date"] == "2026-10-21")
    _check("run_phase korrekt", row["run_phase"] == "postclose")
    _check("n_top10 == 2", row["n_top10"] == 2)
    _check("top10_mit_news == 1", row["top10_mit_news"] == 1)
    _check("n_wl == 2 (Watchlist-Outsider)", row["n_wl"] == 2)
    _check("wl_mit_news == 1", row["wl_mit_news"] == 1)
    _check("yfinance_raw == 10", row["yfinance_raw"] == 10)
    _check("yfinance_kept == 7", row["yfinance_kept"] == 7)
    _check("yfinance_dropped_age == 3", row["yfinance_dropped_age"] == 3)
    _check("rss_fallback_calls == 2", row["rss_fallback_calls"] == 2)
    _check("rss_fallback_kept == 1", row["rss_fallback_kept"] == 1)
    _check("exception_counts-Feld vorhanden", "exception_counts" in row)
    _check("kompakte JSON-Kodierung (kein Leerzeichen nach ':')",
           '"date":"2026-10-21"' in open(path, encoding="utf-8").readline())


def test_persist_idempotent():
    _reset_acct()
    path = _fresh_coverage_file()
    gr.NEWS_COVERAGE_LOG_ENABLED = True
    top10 = [{"ticker": "AAA", "news": []}]
    n1 = gr._persist_news_coverage(top10, top10, report_date_iso="2026-10-21",
                                   run_phase="premarket")
    n2 = gr._persist_news_coverage(top10, top10, report_date_iso="2026-10-21",
                                   run_phase="premarket")
    _check("erster Lauf schreibt 1 Zeile", n1 == 1)
    _check("zweiter Lauf (gleicher Tag/Phase) schreibt 0 Zeilen", n2 == 0)
    _check("Datei enthält weiterhin nur 1 Zeile", len(_load_lines(path)) == 1)
    n3 = gr._persist_news_coverage(top10, top10, report_date_iso="2026-10-21",
                                   run_phase="postclose")
    _check("andere Phase am selben Tag schreibt wieder 1 Zeile", n3 == 1)
    _check("Datei enthält jetzt 2 Zeilen", len(_load_lines(path)) == 2)


def test_flag_disabled_writes_nothing():
    _reset_acct()
    path = _fresh_coverage_file()
    gr.NEWS_COVERAGE_LOG_ENABLED = False
    try:
        top10 = [{"ticker": "AAA", "news": []}]
        n = gr._persist_news_coverage(top10, top10, report_date_iso="2026-10-21",
                                      run_phase="postclose")
        _check("Flag=False → 0 Zeilen", n == 0)
        _check("Flag=False → keine Datei angelegt", not os.path.exists(path))
    finally:
        gr.NEWS_COVERAGE_LOG_ENABLED = True


# ===========================================================================
# 11: Digest-Zeilen (echt + Fixture)
# ===========================================================================

def test_digest_liveness_line_states():
    d = tempfile.mkdtemp()
    missing = os.path.join(d, "absent.jsonl")
    line_absent = hc.news_coverage_liveness_line(missing)
    _check("absent → 'sammelt ab dem nächsten Lauf'", "sammelt ab dem nächsten Lauf" in line_absent)

    empty_path = os.path.join(d, "empty.jsonl")
    open(empty_path, "w").close()
    line_empty = hc.news_coverage_liveness_line(empty_path)
    _check("leere Datei → 'unlesbar/leer'", "unlesbar/leer" in line_empty)

    ok_path = os.path.join(d, "ok.jsonl")
    with open(ok_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "postclose",
            "ts_utc": "2026-10-21T21:30:00+00:00",
            "n_top10": 10, "top10_mit_news": 8, "n_wl": 5, "wl_mit_news": 3,
            "yfinance_kept": 9, "rss_fallback_kept": 2,
        }) + "\n")
    line_ok = hc.news_coverage_liveness_line(ok_path)
    _check("ok → enthält Top-10-Quote", "Top-10 8/10" in line_ok)
    _check("ok → enthält Watchlist-Quote", "Watchlist 3/5" in line_ok)
    _check("ok → enthält Quellenzähler", "yfinance 9" in line_ok and "RSS 2" in line_ok)
    print(f"    [Fixture-Digest-Zeile] {line_ok}")


def test_digest_warn_line():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 21, 22, 0, 0, tzinfo=timezone.utc)

    # Kein Fund bei fehlender/leerer Datei.
    missing = os.path.join(d, "absent.jsonl")
    _check("absent → keine Warnzeile", hc.news_coverage_warn_line(missing, now_ts=now) is None)

    # Alle Läufe im Fenster liefern 0 → Warnzeile.
    zero_path = os.path.join(d, "zero.jsonl")
    with open(zero_path, "w", encoding="utf-8") as fh:
        for h in (2, 8, 14):
            ts = (now.replace(hour=0) ).isoformat()
            fh.write(json.dumps({
                "date": "2026-10-21", "run_phase": "premarket",
                "ts_utc": f"2026-10-21T{h:02d}:00:00+00:00",
                "n_top10": 10, "top10_mit_news": 0, "n_wl": 5, "wl_mit_news": 0,
            }) + "\n")
    warn = hc.news_coverage_warn_line(zero_path, now_ts=now)
    _check("0 in allen Läufen im Fenster → Warnzeile", warn is not None
           and "News-Abdeckung 0" in warn)
    print(f"    [Fixture-Warnzeile] {warn}")

    # Mindestens ein Lauf mit News im Fenster → KEINE Warnzeile.
    mixed_path = os.path.join(d, "mixed.jsonl")
    with open(mixed_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "premarket",
            "ts_utc": "2026-10-21T02:00:00+00:00",
            "n_top10": 10, "top10_mit_news": 0, "n_wl": 5, "wl_mit_news": 0,
        }) + "\n")
        fh.write(json.dumps({
            "date": "2026-10-21", "run_phase": "postclose",
            "ts_utc": "2026-10-21T21:00:00+00:00",
            "n_top10": 10, "top10_mit_news": 4, "n_wl": 5, "wl_mit_news": 0,
        }) + "\n")
    _check("ein Lauf mit News im Fenster → keine Warnzeile",
           hc.news_coverage_warn_line(mixed_path, now_ts=now) is None)

    # Läufe außerhalb des Fensters zählen nicht mit (kein Fund → None).
    outside_path = os.path.join(d, "outside.jsonl")
    with open(outside_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-10", "run_phase": "postclose",
            "ts_utc": "2026-10-10T21:00:00+00:00",
            "n_top10": 10, "top10_mit_news": 0, "n_wl": 5, "wl_mit_news": 0,
        }) + "\n")
    _check("nur Läufe außerhalb des Fensters → kein Fund (None)",
           hc.news_coverage_warn_line(outside_path, now_ts=now) is None)


# ===========================================================================
# 13: format_digest_body-Verdrahtung (alle 3 Klassen + Backward-Compat)
# ===========================================================================

def test_format_digest_body_wiring():
    body_empty, *_ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-10-21",
        news_coverage_line="📰 News-Abdeckung: X", news_coverage_warn="⚠️ News-Abdeckung 0 …")
    _check("📭-Klasse enthält news_coverage_line", "📰 News-Abdeckung: X" in body_empty)
    _check("📭-Klasse enthält news_coverage_warn", "⚠️ News-Abdeckung 0" in body_empty)

    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21",
        news_coverage_line="📰 News-Abdeckung: Y")
    _check("✅-Klasse enthält news_coverage_line", "📰 News-Abdeckung: Y" in body_ok)

    body_warn, *_ = hc.format_digest_body(
        [{"id": "s1", "severity": "crit", "detail": "x", "recovered": False}], [],
        n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21",
        news_coverage_line="📰 News-Abdeckung: Z")
    _check("⚠️-Klasse enthält news_coverage_line", "📰 News-Abdeckung: Z" in body_warn)

    # Backward-Compat: ohne die neuen Parameter unverändertes Verhalten.
    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-21T21:00:00Z", digest_date="2026-10-21")
    _check("Backward-Compat: kein Crash ohne neue Parameter", isinstance(body_compat, str))


# ===========================================================================
# 12: Score-/Top-10-Gegenprobe — News beeinflusst NICHT score()/Reihenfolge
# ===========================================================================

def test_score_and_top10_order_unaffected_by_news():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "float_shares": 5_000_000, "price": 4.0, "change": 3.0},
        {"ticker": "BBB", "short_float": 10, "short_ratio": 4, "rel_volume": 1.2,
         "float_shares": 40_000_000, "price": 12.0, "change": 1.0},
        {"ticker": "CCC", "short_float": 30, "short_ratio": 12, "rel_volume": 4.0,
         "float_shares": 2_000_000, "price": 2.5, "change": 6.0},
    ]
    import copy
    no_news = copy.deepcopy(base)
    with_news = copy.deepcopy(base)
    for s in with_news:
        s["news"] = [{"title": f"{s['ticker']} headline", "ts": 1_700_000_000}]

    scores_no_news = [round(gr.score(s), 6) for s in no_news]
    scores_with_news = [round(gr.score(s), 6) for s in with_news]
    _check("score() identisch mit/ohne news", scores_no_news == scores_with_news)

    order_no_news = sorted(no_news, key=lambda x: x.get("score") or gr.score(x), reverse=True)
    rank_no_news = [s["ticker"] for s in
                   sorted(no_news, key=lambda x: gr.score(x), reverse=True)]
    rank_with_news = [s["ticker"] for s in
                      sorted(with_news, key=lambda x: gr.score(x), reverse=True)]
    _check("Top-10-Sortierreihenfolge identisch mit/ohne news",
           rank_no_news == rank_with_news)


def run_all():
    tests = [
        test_raw_kept_dropped_counters,
        test_exception_type_counter,
        test_rss_fallback_on_empty_yfinance,
        test_rss_fallback_on_yfinance_exception,
        test_both_sources_empty,
        test_rss_fallback_age_filter,
        test_no_rss_fallback_when_yfinance_delivers,
        test_persist_news_coverage_writes_expected_fields,
        test_persist_idempotent,
        test_flag_disabled_writes_nothing,
        test_digest_liveness_line_states,
        test_digest_warn_line,
        test_format_digest_body_wiring,
        test_score_and_top10_order_unaffected_by_news,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} News-Coverage-Watchdog-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle News-Coverage-Watchdog-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
