"""Mock-Tests für die Reddit-Aufmerksamkeits-Schattensammlung (ApeWisdom,
23.10.2026, Easy-Entscheid).

Easy-Entscheid 23.10.2026: Ersatz für die seit mind. 27.07.2026 toten
ki_agent.py-Quellen reddit_mentions/openinsider/fda_calendar NICHT in den
ki_signal_score zurückfließen lassen, bevor die laufende KI-Score-Freeze-
Auswertung (PR #597/#598) abgeschlossen ist. Diese Sammlung ist eine
SEPARATE, rein additive Zeitreihe (apewisdom_attention_history.jsonl) —
KEIN Ersatz für ki_agent.fetch_reddit_mentions (die alte, tote Quelle bleibt
unverändert im Code stehen, siehe PR #599-Bericht + open_items.json
"openinsider-fda-tot").

Verriegelt die harten Invarianten:
  1  _fetch_apewisdom_attention: Mock-Antwort → Dict mit Feldern; Fehler auf
     irgendeiner Seite → {} (fail-soft), nie Exception nach außen.
  2  _persist_apewisdom_attention: Flag=False → keine Datei, keine
     _COVERAGE_ACCT-Buchung. Flag=True + Fetch-Erfolg → eine Zeile je Ticker
     im Pool, found=True/False korrekt, _COVERAGE_ACCT["apewisdom_shadow"]
     n_erwartet/n_mit_daten korrekt. Fetch-Fehler ({}) → n_fehler = Pool-
     Größe (nicht 1 — EIN Bulk-Call bedient den ganzen Pool).
  3  Idempotenz über (date, ticker) — zweiter Lauf am selben Tag erzeugt
     KEINE Duplikat-Zeile pro Ticker (Lehre aus #599 beachtet: diese Quelle
     läuft NUR über generate_report.py, nie über den stündlichen
     ki_agent-Tick — der Befund-B-Idempotenz-Kollaps greift hier
     strukturell nicht, siehe Docstring in generate_report.py).
  4  apewisdom_shadow ist in config.COVERAGE_QUELLEN +
     COVERAGE_SILENT_EMPTY_SPARSE_QUELLEN eingetragen — automatisch von
     coverage_liveness_line/coverage_overview_line erfasst (generischer
     Daten-Abdeckungs-Wächter, kein Sonderfall).
  5  apewisdom_attention_digest_line: absent/leer/ok (+Fixture), Format
     "🗣 Reddit-Schatten (ApeWisdom): läuft · x Ticker · y Punkte".
  6  format_digest_body-Verdrahtung: apewisdom_line erscheint in allen 3
     Klassen (ok/warn/leer).
  7  Grep-Beleg: KEIN Score-/Push-/Top-10-Pfad liest apewisdom-Felder
     (score(), _compute_sub_scores, apply_agent_boost, compute_signal).
  8  Score-/Top-10-Gegenprobe: score() unverändert mit/ohne
     apewisdom-Fetch/-Persist aktiv.
  9  Golden byte-identisch (separater Lauf, siehe scripts/
     mock_test_outer_page_golden.py — hier nur als Kommentar-Beleg, kein
     Doppel-Test).

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

# Import zieht _install_stubs() (yfinance/requests/bs4/deep_translator/
# watchlist) + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import gr  # noqa: E402

import health_check as hc  # noqa: E402
import config  # noqa: E402

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fresh_attention_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "apewisdom_attention_history.jsonl")
    gr.APEWISDOM_ATTENTION_LOG_FILE = path
    hc.APEWISDOM_ATTENTION_LOG_FILE = path
    return path


def _load_lines(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s:
                out.append(json.loads(s))
    return out


class _RespOK:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# ===========================================================================
# 1: _fetch_apewisdom_attention
# ===========================================================================

def test_fetch_attention_parses_mock_response():
    orig_get = gr.requests.get
    try:
        gr.requests.get = lambda *a, **k: _RespOK({
            "results": [
                {"ticker": "GME", "mentions": 42, "mentions_24h_ago": 30,
                 "rank": 1, "rank_24h_ago": 2, "upvotes": 999},
                {"ticker": "amc", "mentions": 7, "mentions_24h_ago": 5,
                 "rank": 15, "rank_24h_ago": 20, "upvotes": 50},
            ]
        })
        out = gr._fetch_apewisdom_attention(pages=1, timeout=5)
        _check("GME geparst", out.get("GME", {}).get("mentions") == 42)
        _check("Ticker wird groß normalisiert (amc -> AMC)", "AMC" in out)
        _check("genau 2 Einträge", len(out) == 2)
    finally:
        gr.requests.get = orig_get


def test_fetch_attention_multi_page_merges():
    orig_get = gr.requests.get
    calls = []
    try:
        def _fake_get(url, **kw):
            calls.append(url)
            if "/page/1" in url:
                return _RespOK({"results": [{"ticker": "AAA", "mentions": 1}]})
            return _RespOK({"results": [{"ticker": "BBB", "mentions": 2}]})
        gr.requests.get = _fake_get
        out = gr._fetch_apewisdom_attention(pages=2, timeout=5)
        _check("2 Requests (eine Gesamtliste pro Seite, kein Pro-Ticker-Call)",
               len(calls) == 2)
        _check("beide Seiten gemerged", set(out.keys()) == {"AAA", "BBB"})
    finally:
        gr.requests.get = orig_get


def test_fetch_attention_error_returns_empty_fail_soft():
    orig_get = gr.requests.get
    try:
        def _raise(*a, **k):
            raise ConnectionError("down")
        gr.requests.get = _raise
        out = gr._fetch_apewisdom_attention(pages=2, timeout=5)
        _check("Fetch-Fehler -> {} (fail-soft, keine Exception nach außen)",
               out == {})
    finally:
        gr.requests.get = orig_get


def test_fetch_attention_malformed_entry_skipped():
    orig_get = gr.requests.get
    try:
        gr.requests.get = lambda *a, **k: _RespOK({
            "results": [{"mentions": 5}, {"ticker": "", "mentions": 9},
                        {"ticker": "OK", "mentions": 3}]
        })
        out = gr._fetch_apewisdom_attention(pages=1, timeout=5)
        _check("Einträge ohne/leeren Ticker übersprungen, kein Crash",
               out == {"OK": {"mentions": 3, "mentions_24h_ago": None,
                               "rank": None, "rank_24h_ago": None,
                               "upvotes": None}})
    finally:
        gr.requests.get = orig_get


# ===========================================================================
# 2: _persist_apewisdom_attention — Flag, Schema, Coverage-Buchung
# ===========================================================================

def test_persist_flag_disabled_no_file_no_booking():
    path = _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = False
        n = gr._persist_apewisdom_attention(
            {"AAA", "BBB"}, {"AAA": {"mentions": 5}},
            report_date_iso="2026-10-23")
        _check("Flag=False -> return 0", n == 0)
        _check("Flag=False -> keine Datei angelegt", not os.path.exists(path))
        _check("Flag=False -> _COVERAGE_ACCT NICHT gebucht",
               gr._COVERAGE_ACCT["apewisdom_shadow"]["n_erwartet"] == 0)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


def test_persist_success_one_row_per_ticker_found_flag_correct():
    path = _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = True
        attention = {"AAA": {"mentions": 12, "mentions_24h_ago": 8,
                              "rank": 3, "rank_24h_ago": 5, "upvotes": 100}}
        n = gr._persist_apewisdom_attention(
            {"AAA", "BBB"}, attention, report_date_iso="2026-10-23",
            now_fn=lambda: datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc))
        _check("2 Zeilen geschrieben (ganzer Pool, auch ohne Treffer)", n == 2)
        rows = _load_lines(path)
        _check("2 Zeilen in der Datei", len(rows) == 2)
        by_ticker = {r["ticker"]: r for r in rows}
        _check("AAA found=True mit Feldern", by_ticker["AAA"]["found"] is True
               and by_ticker["AAA"]["mentions"] == 12)
        _check("BBB found=False, mentions=None (legitim leer)",
               by_ticker["BBB"]["found"] is False
               and by_ticker["BBB"]["mentions"] is None)
        _check("quelle-Feld gesetzt", rows[0]["quelle"] == "apewisdom")
        acct = gr._COVERAGE_ACCT["apewisdom_shadow"]
        _check("n_erwartet = Pool-Größe", acct["n_erwartet"] == 2)
        _check("n_mit_daten = Treffer-Anzahl", acct["n_mit_daten"] == 1)
        _check("n_fehler NICHT erhöht bei Erfolg", acct["n_fehler"] == 0)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


def test_persist_bulk_fetch_failure_counts_as_fehler_for_whole_pool():
    _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = True
        n = gr._persist_apewisdom_attention(
            {"AAA", "BBB", "CCC"}, {}, report_date_iso="2026-10-23")
        acct = gr._COVERAGE_ACCT["apewisdom_shadow"]
        _check("n_fehler = Pool-Größe (EIN Bulk-Call fehlgeschlagen, "
               "nicht nur 1 Ticker)", acct["n_fehler"] == 3)
        _check("error_counts trägt FetchFailed",
               acct["error_counts"].get("FetchFailed") == 3)
        _check("trotzdem 3 Zeilen geschrieben (found=False für alle)", n == 3)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


def test_persist_empty_pool_no_booking():
    _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = True
        n = gr._persist_apewisdom_attention(set(), {}, report_date_iso="2026-10-23")
        _check("leerer Pool -> 0 Zeilen", n == 0)
        _check("leerer Pool -> keine Buchung",
               gr._COVERAGE_ACCT["apewisdom_shadow"]["n_erwartet"] == 0)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


# ===========================================================================
# 3: Idempotenz über (date, ticker)
# ===========================================================================

def test_persist_idempotent_same_day_no_duplicate_rows():
    path = _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = True
        attention = {"AAA": {"mentions": 1}}
        n1 = gr._persist_apewisdom_attention(
            {"AAA"}, attention, report_date_iso="2026-10-23")
        n2 = gr._persist_apewisdom_attention(
            {"AAA"}, attention, report_date_iso="2026-10-23")
        _check("erster Lauf schreibt 1 Zeile", n1 == 1)
        _check("zweiter Lauf am selben Tag schreibt 0 (idempotent)", n2 == 0)
        rows = _load_lines(path)
        _check("Datei hat nur 1 Zeile für AAA/2026-10-23", len(rows) == 1)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


def test_persist_different_day_writes_new_row():
    path = _fresh_attention_file()
    orig_flag = gr.APEWISDOM_SHADOW_ENABLED
    gr._coverage_acct_reset()
    try:
        gr.APEWISDOM_SHADOW_ENABLED = True
        attention = {"AAA": {"mentions": 1}}
        gr._persist_apewisdom_attention({"AAA"}, attention, report_date_iso="2026-10-23")
        n2 = gr._persist_apewisdom_attention({"AAA"}, attention, report_date_iso="2026-10-24")
        _check("neuer Tag -> neue Zeile", n2 == 1)
        rows = _load_lines(path)
        _check("2 Zeilen gesamt (forward-only, ein Tag je Zeile)", len(rows) == 2)
    finally:
        gr.APEWISDOM_SHADOW_ENABLED = orig_flag


# ===========================================================================
# 4: config.COVERAGE_QUELLEN-Eintragung
# ===========================================================================

def test_apewisdom_shadow_registered_in_coverage_quellen():
    _check("apewisdom_shadow in COVERAGE_QUELLEN",
           "apewisdom_shadow" in config.COVERAGE_QUELLEN)
    _check("apewisdom_shadow in COVERAGE_SILENT_EMPTY_SPARSE_QUELLEN "
           "(Small-Cap-Abdeckung ist sparse, nicht dense)",
           "apewisdom_shadow" in config.COVERAGE_SILENT_EMPTY_SPARSE_QUELLEN)
    _check("apewisdom_shadow NICHT in COVERAGE_SILENT_EMPTY_DENSE_QUELLEN",
           "apewisdom_shadow" not in config.COVERAGE_SILENT_EMPTY_DENSE_QUELLEN)
    _check("apewisdom_shadow in generate_report._COVERAGE_ACCT",
           "apewisdom_shadow" in gr._COVERAGE_ACCT)


# ===========================================================================
# 5: apewisdom_attention_digest_line
# ===========================================================================

def test_digest_line_absent():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "nope.jsonl")
    line = hc.apewisdom_attention_digest_line(path)
    _check("absent -> 'sammelt ab dem nächsten Lauf'", "nächsten Lauf" in line)
    _check("Emoji-Präfix korrekt", line.startswith("🗣 Reddit-Schatten (ApeWisdom)"))


def test_digest_line_empty_file():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "empty.jsonl")
    pathlib.Path(path).write_text("", encoding="utf-8")
    line = hc.apewisdom_attention_digest_line(path)
    _check("leere Datei -> 'unlesbar/leer'", "unlesbar/leer" in line)


def test_digest_line_ok_counts_last_day_only():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "att.jsonl")
    rows = [
        {"date": "2026-10-22", "ticker": "OLD", "found": True, "mentions": 999},
        {"date": "2026-10-23", "ticker": "AAA", "found": True, "mentions": 10},
        {"date": "2026-10-23", "ticker": "BBB", "found": True, "mentions": 5},
        {"date": "2026-10-23", "ticker": "CCC", "found": False, "mentions": None},
    ]
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    line = hc.apewisdom_attention_digest_line(path)
    _check("Format exakt: läuft · 2 Ticker · 15 Punkte",
           line == "🗣 Reddit-Schatten (ApeWisdom): läuft · 2 Ticker · 15 Punkte")
    _check("Vortag (OLD) NICHT mitgezählt", "999" not in line and "3 Ticker" not in line)


def test_digest_line_never_raises_on_garbage():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "garbage.jsonl")
    pathlib.Path(path).write_text("{not json\n", encoding="utf-8")
    try:
        line = hc.apewisdom_attention_digest_line(path)
        _check("Garbage -> String zurück, keine Exception", isinstance(line, str))
    except Exception as exc:
        _check(f"Garbage löste Exception aus: {exc}", False)


# ===========================================================================
# 6: format_digest_body-Verdrahtung (3 Klassen)
# ===========================================================================

def test_format_digest_body_apewisdom_line_in_all_classes():
    marker = "🗣 Reddit-Schatten (ApeWisdom): läuft · 3 Ticker · 20 Punkte"

    body_ok, _, _, _ = hc.format_digest_body(
        [], [], n_runs=2, last_run_iso="2026-10-23T09:00:00Z",
        digest_date="2026-10-23", apewisdom_line=marker)
    _check("OK-Klasse enthält apewisdom_line", marker in body_ok)

    body_warn, _, _, _ = hc.format_digest_body(
        [{"id": "S1", "severity": "warn", "detail": "x"}] * 3, [],
        n_runs=5, last_run_iso="2026-10-23T09:00:00Z",
        digest_date="2026-10-23", apewisdom_line=marker)
    _check("Warn-Klasse enthält apewisdom_line", marker in body_warn)

    body_empty, _, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None,
        digest_date="2026-10-23", apewisdom_line=marker)
    _check("Leer-Klasse (n_runs=0) enthält apewisdom_line", marker in body_empty)

    body_none, _, _, _ = hc.format_digest_body(
        [], [], n_runs=2, last_run_iso="2026-10-23T09:00:00Z",
        digest_date="2026-10-23", apewisdom_line=None)
    _check("apewisdom_line=None -> kein Crash, kein Reddit-Text im Body",
           "Reddit-Schatten" not in body_none)


# ===========================================================================
# 7: Grep-Beleg — kein Score-/Push-/Top-10-Pfad liest apewisdom
# ===========================================================================

def test_no_score_path_reads_apewisdom_fields():
    import inspect
    for fn in (gr.score, gr._compute_sub_scores, gr.apply_agent_boost):
        src = inspect.getsource(fn)
        _check(f"{fn.__name__} liest kein 'apewisdom'", "apewisdom" not in src.lower())


def test_no_ki_agent_score_path_reads_apewisdom():
    import inspect
    sys_path_added = str(ROOT) not in sys.path
    if sys_path_added:
        sys.path.insert(0, str(ROOT))
    if "pandas" not in sys.modules:
        _pd_stub = types.ModuleType("pandas")
        _pd_stub.DataFrame = object
        _pd_stub.Timestamp = lambda *a, **k: None
        sys.modules["pandas"] = _pd_stub
    import ki_agent as ka
    src = inspect.getsource(ka.compute_signal)
    _check("ki_agent.compute_signal liest kein 'apewisdom'",
           "apewisdom" not in src.lower())


# ===========================================================================
# 8: Score-/Top-10-Gegenprobe
# ===========================================================================

def test_score_unaffected_by_apewisdom_shadow_collection():
    base = [
        {"ticker": "AAA", "short_float": 20, "short_ratio": 8, "rel_volume": 2.5,
         "price": 5.0, "change": 3.0, "market_cap": 100e6},
        {"ticker": "BBB", "short_float": 15, "short_ratio": 4, "rel_volume": 1.8,
         "price": 10.0, "change": -1.0, "market_cap": 200e6},
    ]
    import copy
    no_shadow = copy.deepcopy(base)
    with_shadow_metadata = copy.deepcopy(base)
    # Simuliert, dass ein Stock-Dict versehentlich mit apewisdom-Feldern
    # "verschmutzt" würde (defensive Gegenprobe — der echte Code tut das
    # nirgends, siehe Grep-Tests oben) — score() darf es trotzdem ignorieren.
    for s in with_shadow_metadata:
        s["apewisdom_mentions"] = 999
        s["apewisdom_rank"] = 1

    scores_no = [round(gr.score(s), 6) for s in no_shadow]
    scores_with = [round(gr.score(s), 6) for s in with_shadow_metadata]
    _check("score() identisch mit/ohne apewisdom-Metadaten auf dem Stock-Dict",
           scores_no == scores_with)

    rank_no = [s["ticker"] for s in sorted(no_shadow, key=lambda x: gr.score(x), reverse=True)]
    rank_with = [s["ticker"] for s in sorted(with_shadow_metadata, key=lambda x: gr.score(x), reverse=True)]
    _check("Top-10-Sortierreihenfolge identisch mit/ohne apewisdom-Metadaten",
           rank_no == rank_with)


def run_all():
    tests = [
        test_fetch_attention_parses_mock_response,
        test_fetch_attention_multi_page_merges,
        test_fetch_attention_error_returns_empty_fail_soft,
        test_fetch_attention_malformed_entry_skipped,
        test_persist_flag_disabled_no_file_no_booking,
        test_persist_success_one_row_per_ticker_found_flag_correct,
        test_persist_bulk_fetch_failure_counts_as_fehler_for_whole_pool,
        test_persist_empty_pool_no_booking,
        test_persist_idempotent_same_day_no_duplicate_rows,
        test_persist_different_day_writes_new_row,
        test_apewisdom_shadow_registered_in_coverage_quellen,
        test_digest_line_absent,
        test_digest_line_empty_file,
        test_digest_line_ok_counts_last_day_only,
        test_digest_line_never_raises_on_garbage,
        test_format_digest_body_apewisdom_line_in_all_classes,
        test_no_score_path_reads_apewisdom_fields,
        test_no_ki_agent_score_path_reads_apewisdom,
        test_score_unaffected_by_apewisdom_shadow_collection,
    ]
    for t in tests:
        t()
    print()
    if _fails:
        print(f"{len(_fails)} ApeWisdom-Shadow-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle ApeWisdom-Shadow-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
