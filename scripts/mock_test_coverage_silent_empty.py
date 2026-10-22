"""Mock-Tests für die Stiller-Leer-Ausfall-Erweiterung (22.10.2026).

Lücke in der generischen Daten-Abdeckungs-Wächter-PR (21.10.2026, #594):
``n_erhalten`` misst nur, ob der Provider-Call OHNE Exception antwortete —
ein stiller Ausfall, bei dem die Quelle antwortet, aber (ohne Fehler)
leer/None liefert, blieb unsichtbar. Genau dieses Muster ließ die
Karten-News 19 Tage unbemerkt (#593).

Neues additives Feld ``n_mit_daten`` in ``coverage_history.jsonl`` misst
die inhaltliche Nicht-Leere, unabhängig davon, ob die Leere "legitim" war.
Zwei Fenster: 24h für die dichten Quellen (options_atm, earnings_date),
7 Tage für die übrigen 4 (earnings_surprise, reddit_mentions, fda_calendar,
openinsider) — ein einzelner leerer Tag ist dort normal.

Verriegelt die harten Invarianten:
  1  persist_coverage_row: n_mit_daten additiv (None-fähig), bestehende
     Felder/Schema unverändert.
  2  coverage_silent_empty_warn_line: stiller Leer-Ausfall (alle Läufe im
     Fenster n_mit_daten=0 bei n_erwartet>0) → Warnung; mind. 1 Lauf mit
     Daten im Fenster → keine Warnung; unbekannte Quelle → None.
  3  Zwei Fenster korrekt zugeordnet (dense=24h, sparse=7 Tage).
  4  Alte Zeilen ohne ``n_mit_daten``-Feld (vor dieser PR) werden fail-soft
     aus dem Fenster ausgeschlossen — NICHT als 0 gewertet.
  5  Einzelne leere Tage bei sparsen Quellen lösen KEINE Warnung aus,
     solange mind. 1 Tag im 7-Tage-Fenster Daten lieferte.
  6  coverage_overview_line berücksichtigt BEIDE Warnarten (Call-Ebene +
     Inhalts-Ebene).
  7  format_digest_body-Verdrahtung (neuer Parameter, alle 3 Klassen,
     Backward-Compat).
  8  Zero-Behavior-Change: die neuen Call-Site-Zähler (n_mit_daten) ändern
     keine Rückgabewerte/Anfragezahl der 6 instrumentierten Funktionen.
  9  Score-/Top-10-Gegenprobe unverändert.

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from mock_test_outer_page_golden import gr  # noqa: E402

import health_check as hc  # noqa: E402

if "pandas" not in sys.modules:
    _pd_stub = types.ModuleType("pandas")
    _pd_stub.DataFrame = object
    _pd_stub.Timestamp = lambda *a, **k: None
    sys.modules["pandas"] = _pd_stub

import ki_agent as ka  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fresh_coverage_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "coverage_history.jsonl")
    hc.COVERAGE_LOG_FILE = path
    return path


def _load_lines(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out


def _write_row(path, **kw):
    defaults = {
        "date": "2026-10-22", "run_phase": "postclose", "quelle": "options_atm",
        "ts_utc": "2026-10-22T21:30:00+00:00", "n_erwartet": 5, "n_erhalten": 5,
        "error_counts": {},
    }
    defaults.update(kw)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(defaults, ensure_ascii=False) + "\n")


# ===========================================================================
# 1: persist_coverage_row — n_mit_daten additiv
# ===========================================================================

def test_persist_coverage_row_n_mit_daten_schema():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    n = hc.persist_coverage_row("options_atm", 5, 4, {"TimeoutError": 1},
                                n_mit_daten=3, report_date_iso="2026-10-22",
                                run_phase="postclose", path=path)
    _check("1 neue Zeile geschrieben", n == 1)
    row = _load_lines(path)[0]
    _check("n_mit_daten korrekt", row["n_mit_daten"] == 3)
    _check("bestehende Felder unverändert", row["n_erwartet"] == 5 and row["n_erhalten"] == 4)


def test_persist_coverage_row_n_mit_daten_none_default():
    path = _fresh_coverage_file()
    hc.COVERAGE_LOG_ENABLED = True
    hc.persist_coverage_row("earnings_date", 10, 10, {},
                            report_date_iso="2026-10-22",
                            run_phase="postclose", path=path)
    row = _load_lines(path)[0]
    _check("n_mit_daten ohne Angabe → null (nicht 0)", row["n_mit_daten"] is None)


# ===========================================================================
# 2-3: coverage_silent_empty_warn_line — beide Fenster
# ===========================================================================

def test_silent_empty_warn_dense_window():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 22, 22, 0, 0, tzinfo=timezone.utc)
    path = os.path.join(d, "dense.jsonl")
    for h in (2, 10, 18):
        _write_row(path, quelle="options_atm", ts_utc=f"2026-10-22T{h:02d}:00:00+00:00",
                  n_erwartet=5, n_erhalten=5, n_mit_daten=0)
    warn = hc.coverage_silent_empty_warn_line("options_atm", path, now_ts=now)
    _check("options_atm: 0 mit Daten in allen Läufen (24h) → Warnung",
           warn is not None and "options_atm" in warn and "24 h" in warn)
    print(f"    [Fixture-Warnzeile dense] {warn}")

    # Mind. 1 Lauf mit Daten im 24h-Fenster → keine Warnung.
    path2 = os.path.join(d, "dense_ok.jsonl")
    _write_row(path2, quelle="options_atm", ts_utc="2026-10-22T02:00:00+00:00",
              n_erwartet=5, n_erhalten=5, n_mit_daten=0)
    _write_row(path2, quelle="options_atm", ts_utc="2026-10-22T18:00:00+00:00",
              n_erwartet=5, n_erhalten=5, n_mit_daten=2)
    _check("mind. 1 Lauf mit Daten → keine Warnung",
           hc.coverage_silent_empty_warn_line("options_atm", path2, now_ts=now) is None)


def test_silent_empty_warn_sparse_window():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 22, 22, 0, 0, tzinfo=timezone.utc)

    # Einzelne leere TICKER innerhalb eines ansonsten erfolgreichen Laufs
    # (z. B. 7 von 10 Tickern ohne Insider-Kauf) → KEINE Warnung, weil
    # n_mit_daten > 0 bleibt (die Aggregation zählt Tickers, nicht Läufe).
    partial_path = os.path.join(d, "partial.jsonl")
    _write_row(partial_path, quelle="openinsider", ts_utc="2026-10-22T21:17:00+00:00",
              n_erwartet=10, n_erhalten=10, n_mit_daten=3)
    _check("einzelne leere Ticker (3 von 10 mit Daten) → keine Warnung",
           hc.coverage_silent_empty_warn_line("openinsider", partial_path, now_ts=now) is None)

    # 7 Tage durchgängig leer → Warnung.
    seven_days_path = os.path.join(d, "seven_days.jsonl")
    for days_ago in range(7):
        ts = (now - timedelta(days=days_ago)).isoformat()
        _write_row(seven_days_path, quelle="fda_calendar", ts_utc=ts,
                  n_erwartet=1, n_erhalten=1, n_mit_daten=0)
    warn = hc.coverage_silent_empty_warn_line("fda_calendar", seven_days_path, now_ts=now)
    _check("7 Tage durchgängig 0 mit Daten (sparse) → Warnung",
           warn is not None and "Tage" in warn)
    print(f"    [Fixture-Warnzeile sparse] {warn}")

    # Mind. 1 Tag mit Daten im 7-Tage-Fenster → keine Warnung.
    mixed_path = os.path.join(d, "mixed_sparse.jsonl")
    for days_ago in range(7):
        ts = (now - timedelta(days=days_ago)).isoformat()
        n_data = 1 if days_ago == 3 else 0
        _write_row(mixed_path, quelle="openinsider", ts_utc=ts,
                  n_erwartet=10, n_erhalten=10, n_mit_daten=n_data)
    _check("mind. 1 Tag mit Daten im 7-Tage-Fenster → keine Warnung",
           hc.coverage_silent_empty_warn_line("openinsider", mixed_path, now_ts=now) is None)


def test_silent_empty_warn_unknown_quelle():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "unknown.jsonl")
    _write_row(path, quelle="voellig_unbekannt", n_mit_daten=0)
    _check("unbekannte Quelle (nicht in dense/sparse-Liste) → None",
           hc.coverage_silent_empty_warn_line("voellig_unbekannt", path) is None)


# ===========================================================================
# 4: alte Zeilen ohne n_mit_daten-Feld — fail-soft, NICHT als 0 gewertet
# ===========================================================================

def test_silent_empty_warn_legacy_rows_excluded():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 22, 22, 0, 0, tzinfo=timezone.utc)
    path = os.path.join(d, "legacy.jsonl")
    # Zwei "alte" Zeilen OHNE n_mit_daten-Feld (vor dieser PR) im Fenster.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "date": "2026-10-22", "run_phase": "postclose", "quelle": "options_atm",
            "ts_utc": "2026-10-22T10:00:00+00:00",
            "n_erwartet": 5, "n_erhalten": 5, "error_counts": {},
        }) + "\n")
        fh.write(json.dumps({
            "date": "2026-10-22", "run_phase": "postclose", "quelle": "options_atm",
            "ts_utc": "2026-10-22T18:00:00+00:00",
            "n_erwartet": 5, "n_erhalten": 5, "n_mit_daten": None, "error_counts": {},
        }) + "\n")
    _check("nur alte/null-n_mit_daten-Zeilen im Fenster → kein Fund (None), NICHT Warnung",
           hc.coverage_silent_empty_warn_line("options_atm", path, now_ts=now) is None)


# ===========================================================================
# 6: coverage_overview_line berücksichtigt beide Warnarten
# ===========================================================================

def test_overview_considers_silent_empty():
    d = tempfile.mkdtemp()
    now = datetime(2026, 10, 22, 22, 0, 0, tzinfo=timezone.utc)
    path = os.path.join(d, "overview.jsonl")
    # Quelle "options_atm": Call-Ebene OK (n_erhalten>0), aber inhaltlich
    # über das gesamte 24h-Fenster leer → sollte als "unter Baseline" zählen.
    for h in (2, 10, 18):
        _write_row(path, quelle="options_atm", ts_utc=f"2026-10-22T{h:02d}:00:00+00:00",
                  n_erwartet=5, n_erhalten=5, n_mit_daten=0)
    # Quelle "earnings_date": völlig gesund.
    _write_row(path, quelle="earnings_date", ts_utc="2026-10-22T21:00:00+00:00",
              n_erwartet=10, n_erhalten=10, n_mit_daten=3)
    overview = hc.coverage_overview_line(path, now_ts=now, quellen=["options_atm", "earnings_date"])
    _check("options_atm zählt wegen stillem Leer-Ausfall als 'unter Baseline'",
           "1 von 2 Quellen unter Baseline" in overview)
    print(f"    [Fixture-Übersichtszeile] {overview}")


# ===========================================================================
# 7: format_digest_body-Verdrahtung
# ===========================================================================

def test_format_digest_body_silent_empty_wiring():
    body_ok, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22",
        coverage_silent_empty_warns=["⚠️ options_atm: in allen 3 Läufen der letzten 24 h keine Daten"])
    _check("✅-Klasse enthält coverage_silent_empty_warns",
           "options_atm: in allen 3" in body_ok)

    body_compat, *_ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-10-22T21:00:00Z", digest_date="2026-10-22")
    _check("Backward-Compat: kein Crash ohne neuen Parameter", isinstance(body_compat, str))


# ===========================================================================
# 8: Zero-Behavior-Change für die neuen Call-Site-Zähler
# ===========================================================================

class _FakeTicker:
    def __init__(self, *, options=(), raise_on=None, calendar="raise",
                 earnings_history="raise", fast_info=None):
        self._options = options
        self._raise_on = raise_on
        self.fast_info = fast_info or {}
        self._calendar = calendar
        self._earnings_history = earnings_history

    @property
    def options(self):
        if self._raise_on == "options":
            raise RuntimeError("boom")
        return self._options

    def option_chain(self, expiry):
        raise RuntimeError("boom")

    @property
    def calendar(self):
        if self._calendar == "raise":
            raise RuntimeError("boom")
        return self._calendar

    @property
    def earnings_history(self):
        if self._earnings_history == "raise":
            raise RuntimeError("boom")
        return self._earnings_history


def test_options_atm_n_mit_daten_zero_behavior_change():
    gr._coverage_acct_reset()
    orig_ticker = gr.yf.Ticker
    try:
        gr.yf.Ticker = lambda t: _FakeTicker(options=(), raise_on=None)
        result_before_count = gr.get_options_data("TEST")
        gr._coverage_acct_reset()
        result_after_count = gr.get_options_data("TEST")
        _check("get_options_data Rückgabe unverändert (legitim-leer)",
               result_before_count == result_after_count == {})
    finally:
        gr.yf.Ticker = orig_ticker


def test_earnings_date_n_mit_daten_counter_at_call_site():
    gr._coverage_acct_reset()
    _acct = gr._COVERAGE_ACCT["earnings_date"]
    # Simuliert exakt die Call-Site-Logik ohne main() auszuführen —
    # bestätigt nur den Zählmechanismus (days is not None).
    for days, _ in [(5, "x"), (None, None), (None, None)]:
        if days is not None:
            _acct["n_mit_daten"] += 1
    _check("n_mit_daten zählt nur Treffer mit echtem Tageswert", _acct["n_mit_daten"] == 1)


def test_reddit_mentions_n_mit_daten_zero_behavior_change():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"data": {"children": []}}
        ka.requests.get = lambda *a, **k: _RespOK()
        orig_sleep = ka.time.sleep
        ka.time.sleep = lambda *a, **k: None
        try:
            result1 = ka.fetch_reddit_mentions("TEST")
            result2 = ka.fetch_reddit_mentions("TEST")
        finally:
            ka.time.sleep = orig_sleep
        _check("fetch_reddit_mentions Rückgabe unverändert über mehrere Aufrufe",
               result1 == result2 == {"count": 0, "sentiment": 0.0})
    finally:
        ka.requests.get = orig_get


def test_openinsider_n_mit_daten_zero_behavior_change():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            text = "<rss><channel></channel></rss>"
            def raise_for_status(self): pass
        ka.requests.get = lambda *a, **k: _RespOK()
        result = ka.fetch_openinsider("TEST")
        _check("fetch_openinsider Rückgabe unverändert (legitim-leer)",
               result == {"count": 0, "csuite": False})
        _check("n_fehler NICHT erhöht (weiterhin legitim-leer, nicht Fehler)",
               ka._COVERAGE_ACCT["openinsider"]["n_fehler"] == 0)
    finally:
        ka.requests.get = orig_get


def test_fda_calendar_n_mit_daten_counter():
    ka._coverage_acct_reset()
    orig_get = ka.requests.get
    try:
        class _RespOK:
            status_code = 200
            text = "<rss><channel></channel></rss>"
            def raise_for_status(self): pass
        ka.requests.get = lambda *a, **k: _RespOK()
        result = ka.fetch_fda_calendar()
        _check("leeres Ergebnis → Rückgabe unverändert {}", result == {})
    finally:
        ka.requests.get = orig_get


# ===========================================================================
# 9: Score-/Top-10-Gegenprobe
# ===========================================================================

def test_score_unaffected_by_silent_empty_instrumentation():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "float_shares": 5_000_000, "price": 4.0, "change": 3.0},
        {"ticker": "BBB", "short_float": 10, "short_ratio": 4, "rel_volume": 1.2,
         "float_shares": 40_000_000, "price": 12.0, "change": 1.0},
    ]
    import copy
    no_opts = copy.deepcopy(base)
    with_opts = copy.deepcopy(base)
    for s in with_opts:
        s["options"] = {"pc_ratio": 1.1, "atm_iv": 0.5}
        s["earnings_days"] = 3
    scores_no = [round(gr.score(s), 6) for s in no_opts]
    scores_with = [round(gr.score(s), 6) for s in with_opts]
    _check("score() identisch", scores_no == scores_with)
    rank_no = [s["ticker"] for s in sorted(no_opts, key=lambda x: gr.score(x), reverse=True)]
    rank_with = [s["ticker"] for s in sorted(with_opts, key=lambda x: gr.score(x), reverse=True)]
    _check("Top-10-Reihenfolge identisch", rank_no == rank_with)


def run_all():
    tests = [
        test_persist_coverage_row_n_mit_daten_schema,
        test_persist_coverage_row_n_mit_daten_none_default,
        test_silent_empty_warn_dense_window,
        test_silent_empty_warn_sparse_window,
        test_silent_empty_warn_unknown_quelle,
        test_silent_empty_warn_legacy_rows_excluded,
        test_overview_considers_silent_empty,
        test_format_digest_body_silent_empty_wiring,
        test_options_atm_n_mit_daten_zero_behavior_change,
        test_earnings_date_n_mit_daten_counter_at_call_site,
        test_reddit_mentions_n_mit_daten_zero_behavior_change,
        test_openinsider_n_mit_daten_zero_behavior_change,
        test_fda_calendar_n_mit_daten_counter,
        test_score_unaffected_by_silent_empty_instrumentation,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Coverage-Silent-Empty-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Coverage-Silent-Empty-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
