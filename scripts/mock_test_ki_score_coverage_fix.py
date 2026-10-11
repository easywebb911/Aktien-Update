"""Mock-Tests — KI-Score-Coverage-Fix (11.10.2026).

Hintergrund (Diagnose 10.10.2026): ``ki_signal_score`` im Backtest stammte
vom letzten COMMITTETEN ``ki_agent``-Tick — wegen Cron-Kollision
(``daily-squeeze-report.yml`` postclose ``17 21 * * 1-5`` vs. ``ki_agent.yml``
``17 * * * *``, dieselbe Minute) + komplettem Überschreiben von
``agent_signals.json`` pro Tick (nur der zur Tick-Zeit aktuelle Top-10/
Watchlist/Positions-Pool) oft Stunden alt oder ganz fehlend — nur 30 %
Coverage über 472 gereifte Forward-Zeilen (0 % an 4 Tagen).

Fix: ``generate_report._compute_fresh_ki_signals_for_backtest(top10)``
berechnet synchron, GENAU für die finalen Top-10-Ticker des postclose-
Laufs, direkt vor dem Backtest-Append, einen frischen Wert (Reuse von
``ki_agent._process_ticker``, lazy importiert). Das Ergebnis fließt
AUSSCHLIESSLICH über den neuen ``fresh_ki_signals``-Parameter in
``_append_backtest_entries``/``_build_backtest_extension`` — NIE zurück
in ``score()``, Ranking, Push oder Conviction.

Verifiziert (fixture-/source-only, CI-minimal-safe — Heavy-Dependency-
Stubs identisch zu ``mock_test_outer_page_golden.py``):
- (A) Score-Unabhängigkeit: Call-Order-Beleg im Source (Top-10-Cut VOR
  apply_agent_boost; Fresh-Compute-Aufruf NACH apply_conviction_scores,
  NICHT vor); die neue Funktion schreibt nirgends auf ``s[...]``.
- (B) ``_compute_fresh_ki_signals_for_backtest`` End-to-End (gepatchter
  ``ki_agent._process_ticker``): 10-Ticker-Fixture mit Erfolgs- UND
  Fehlerfall — alle 10 haben ``ts``, Erfolgsfall hat ``score``+
  ``sentiment_source``, Fehlerfall hat ``score=None`` (kein Crash, kein
  leeres Überschreiben, Pipeline läuft weiter).
- (C) ``FRESH_KI_SIGNAL_ENABLED=False`` → sofortiger None-Pfad, kein
  ki_agent-Import-Versuch.
- (D) ``_build_backtest_extension``: ``fresh_ki`` hat Vorrang vor
  ``s.get("ki_signal_score")``; ``fresh_ki=None`` → byte-identisch zum
  alten Verhalten (Regression); ``ki_signal_ts`` wird exakt dann gesetzt,
  wenn ``fresh_ki`` übergeben wurde (auch bei ``score=None``).
- (E) Schema/S10: ``ki_signal_ts`` in ``S10_OBSERVED_FIELDS``, NICHT in
  MUSS/LAG, Schema bleibt v4 (kein Bump).
- (F) ``claude_sentiment_score``-Fehlerart-Sichtbarkeit: Zähler-Dict
  existiert, wird bei Timeout/HTTP/Parse/Rate-Limit erhöht, Verhalten
  (Rückgabe ``None, ""``) bleibt unverändert.

Ausführung: ``python3 scripts/mock_test_ki_score_coverage_fix.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_BH_SRC = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
_KI_SRC = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


# ── Heavy-Dependency-Stubs (identisch zu mock_test_outer_page_golden.py /
#    mock_test_exit_p2_score_at_nback_fix.py) — keine Netzwerkaufrufe. ──────
def _install_stubs() -> None:
    if "yfinance" not in sys.modules:
        yf = types.ModuleType("yfinance")
        yf.download = lambda *a, **k: None
        yf.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.post = lambda *a, **k: None

        class _Timeout(Exception):
            pass

        class _RequestException(Exception):
            pass

        rq.Timeout = _Timeout
        rq.RequestException = _RequestException
        rq.exceptions = types.SimpleNamespace(RequestException=_RequestException)
        sys.modules["requests"] = rq
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *a, **k: None
        sys.modules["bs4"] = bs4
    if "deep_translator" not in sys.modules:
        dt = types.ModuleType("deep_translator")
        dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl
    if "pandas" not in sys.modules:
        pd_mod = types.ModuleType("pandas")
        pd_mod.DataFrame = lambda *a, **k: None
        sys.modules["pandas"] = pd_mod
    if "lxml" not in sys.modules:
        sys.modules["lxml"] = types.ModuleType("lxml")


_install_stubs()
import generate_report as gr          # noqa: E402
import ki_agent as ka                 # noqa: E402
import backtest_history as bh         # noqa: E402
import config                         # noqa: E402


# ── (A) Score-Unabhängigkeit — Call-Order-Beleg im Source ──────────────────

def test_a1_top10_cut_before_agent_boost():
    """Top-10-MEMBERSHIP wird VOR apply_agent_boost fixiert — ein frischer
    KI-Wert kann also keinen Ticker nachträglich in/aus der Top-10 holen."""
    i_cut = _GR_SRC.find("top10 = top10_vol[:10]")
    i_boost = _GR_SRC.find("apply_agent_boost(top10)")
    assert i_cut > 0, "Top-10-Cut-Zeile nicht gefunden"
    assert i_boost > 0, "apply_agent_boost(top10)-Aufruf nicht gefunden"
    assert i_cut < i_boost, "Top-10-Cut muss VOR apply_agent_boost stehen"


def test_a2_fresh_compute_after_conviction_before_append():
    """Die neue Fresh-Compute-Funktion wird NACH apply_conviction_scores
    UND NACH dem zweiten Re-Sort aufgerufen, NICHT davor — sonst könnte sie
    (über einen künftigen Refactor-Fehler) versehentlich vor Boost/Monster/
    Conviction landen."""
    i_boost = _GR_SRC.find("apply_agent_boost(top10)")
    i_monster = _GR_SRC.find("apply_monster_score(top10)")
    i_conviction = _GR_SRC.find("apply_conviction_scores(top10, _anomalies_today")
    # Der LETZTE Fund von "_compute_fresh_ki_signals_for_backtest(top10)" ist
    # der tatsächliche Call in main() (der erste Fund weiter oben ist die
    # Funktionsdefinition selbst) — ebenso sucht _append_backtest_entries(
    # NACH dem Fresh-Call, um den Import-Statement-Fund (Top of File) zu
    # überspringen.
    i_fresh = _GR_SRC.rfind("_compute_fresh_ki_signals_for_backtest(top10)")
    i_append = _GR_SRC.find("_append_backtest_entries(", i_fresh)
    assert i_boost > 0 and i_monster > 0 and i_conviction > 0, \
        "Boost/Monster/Conviction-Aufrufe nicht gefunden"
    assert i_fresh > 0, "Fresh-Compute-Aufruf nicht gefunden"
    assert i_append > i_fresh, "_append_backtest_entries-Aufruf (nach Fresh-Call) nicht gefunden"
    assert i_boost < i_monster < i_conviction < i_fresh < i_append, (
        "Reihenfolge verletzt: Boost < Monster < Conviction < Fresh-Compute "
        "< Append muss gelten")


def test_a3_fresh_compute_never_writes_to_stock_dict():
    """Die Fresh-Compute-Funktion darf NIE auf s["score"]/s["ki_signal_
    score"]/s["monster_score"]/s["conviction"] schreiben (Grep über den
    Funktionskörper: keine Zuweisung der Form s[...] = ...)."""
    start = _GR_SRC.find("def _compute_fresh_ki_signals_for_backtest(")
    assert start > 0, "Funktion nicht gefunden"
    end = _GR_SRC.find("\ndef ", start + 10)
    assert end > start
    body = _GR_SRC[start:end]
    import re as _re
    forbidden = _re.findall(r's\["[a-z_]+"\]\s*=', body)
    assert not forbidden, f"Schreibzugriff auf Stock-Dict gefunden: {forbidden}"


def test_a4_result_only_consumed_by_append_call():
    """Der Rückgabewert wird ausschließlich als fresh_ki_signals= an
    _append_backtest_entries durchgereicht — kein zweiter Konsument."""
    assert "fresh_ki_signals=_fresh_ki_signals" in _GR_SRC
    # Nur EIN Zuweisungs-Ort für die Variable im gesamten File.
    assert _GR_SRC.count("_fresh_ki_signals = _compute_fresh_ki_signals_for_backtest") == 1


# ── (B) _compute_fresh_ki_signals_for_backtest End-to-End ──────────────────

def _fake_process_ticker(ticker: str, shared: dict) -> dict:
    if ticker == "FAIL":
        raise RuntimeError("simulierter Netzwerkfehler")
    return {
        "ticker": ticker,
        "signal": {
            "score": 42.0 if ticker == "AAA" else 17.0,
            "ki_sentiment_source": "llm" if ticker == "AAA" else "keyword",
        },
    }


def test_b1_all_tickers_get_entry_with_ts():
    tickers = ["AAA", "BBB", "FAIL"] + [f"T{i}" for i in range(7)]
    top10 = [{"ticker": t} for t in tickers]

    orig_process = ka._process_ticker
    orig_yf = ka.fetch_yfinance
    orig_fda = ka.fetch_fda_calendar
    orig_finra = ka.fetch_finra_ssr
    ka._process_ticker = _fake_process_ticker
    ka.fetch_yfinance = lambda ts: {}
    ka.fetch_fda_calendar = lambda: {}
    ka.fetch_finra_ssr = lambda ts: {}
    try:
        result = gr._compute_fresh_ki_signals_for_backtest(top10)
    finally:
        ka._process_ticker = orig_process
        ka.fetch_yfinance = orig_yf
        ka.fetch_fda_calendar = orig_fda
        ka.fetch_finra_ssr = orig_finra

    assert len(result) == len(tickers), \
        f"Erwarte {len(tickers)} Einträge, bekam {len(result)}"
    for t in tickers:
        assert t in result, f"{t} fehlt im Ergebnis"
        assert result[t]["ts"] is not None, f"{t}: ts fehlt"
    assert result["AAA"]["score"] == 42.0
    assert result["AAA"]["sentiment_source"] == "llm"
    assert result["BBB"]["score"] == 17.0
    assert result["BBB"]["sentiment_source"] == "keyword"
    # Fehlerfall: score None, aber ts gesetzt (ehrliches "versucht, aber None")
    assert result["FAIL"]["score"] is None, "FAIL-Ticker sollte score=None haben"
    assert result["FAIL"]["sentiment_source"] is None


def test_b2_empty_top10_returns_empty_dict():
    assert gr._compute_fresh_ki_signals_for_backtest([]) == {}
    assert gr._compute_fresh_ki_signals_for_backtest([{"ticker": None}]) == {}


def test_b3_ki_agent_import_failure_is_fail_soft():
    """Simuliert einen kompletten ki_agent-Import-Fehler (z.B. kaputtes
    Deploy) — alle Ticker bekommen score=None+ts, kein Crash."""
    import builtins
    top10 = [{"ticker": "XXX"}]
    orig_import = builtins.__import__

    def _raising_import(name, *a, **kw):
        if name == "ki_agent":
            raise ImportError("simulierter Import-Fehler")
        return orig_import(name, *a, **kw)

    builtins.__import__ = _raising_import
    try:
        result = gr._compute_fresh_ki_signals_for_backtest(top10)
    finally:
        builtins.__import__ = orig_import
    assert result["XXX"]["score"] is None
    assert result["XXX"]["ts"] is not None, "ts sollte trotz Import-Fehler gesetzt sein"


# ── (C) FRESH_KI_SIGNAL_ENABLED=False — sofortiger None-Pfad ───────────────

def test_c1_disabled_flag_short_circuits():
    top10 = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    orig = config.FRESH_KI_SIGNAL_ENABLED
    gr.FRESH_KI_SIGNAL_ENABLED = False
    try:
        result = gr._compute_fresh_ki_signals_for_backtest(top10)
    finally:
        gr.FRESH_KI_SIGNAL_ENABLED = orig
    assert result["AAA"] == {"score": None, "ts": None, "sentiment_source": None}
    assert result["BBB"] == {"score": None, "ts": None, "sentiment_source": None}


# ── (D) _build_backtest_extension: fresh_ki-Priorität + Regression ─────────

def _baseline_stock(ticker="TEST"):
    return {
        "ticker": ticker, "score": 70.0, "score_raw": 68.0, "price": 10.0,
        "short_float": 25.0, "short_ratio": 5.0, "rel_volume": 2.4,
        "rel_volume_yesterday": 1.5, "change": 2.5, "float_shares": 1e8,
        "avg_vol_20d": 1e6, "hist_5d": [],
        "score_trend_bonus_pts": 0.0, "agent_boost_factor": 1.0,
        "finra_bonus_pts": 0.0, "short_float_source": "yfinance",
        "finra_data": {"trend": "no_data", "history": [],
                       "si_trend_source": "finra"},
        "sparkline": None,
    }


def _build(stock, fresh_ki=None):
    return bh._build_backtest_extension(
        stock, pool_position=1, pool_size=20, agent_signals={},
        compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
        safe_float_fn=lambda v, d=0.0: float(v) if v not in (None, "") else d,
        latest_push_ts_by_ticker=None,
        now_dt=None,
        fresh_ki=fresh_ki,
    )


def test_d1_fresh_ki_overrides_stale_stock_value():
    st = _baseline_stock()
    st["ki_signal_score"] = 12.0          # "stale" Wert vom apply_agent_boost
    st["ki_sentiment_source"] = "keyword"  # stale
    ext = _build(st, fresh_ki={"score": 88.0, "ts": "2026-10-11T21:30:00Z",
                               "sentiment_source": "llm"})
    assert ext["ki_signal_score"] == 88.0, "Fresh-Wert muss Vorrang haben"
    assert ext["ki_sentiment_source"] == "llm"
    assert ext["ki_signal_ts"] == "2026-10-11T21:30:00Z"


def test_d2_fresh_ki_none_score_is_honest_none_not_fallback():
    """score=None im Fresh-Dict (Berechnung versucht, fehlgeschlagen) darf
    NICHT auf den stale Stock-Wert zurückfallen — sonst wäre ki_signal_ts
    irreführend (suggeriert einen zum ts-Zeitpunkt berechneten Score)."""
    st = _baseline_stock()
    st["ki_signal_score"] = 12.0
    ext = _build(st, fresh_ki={"score": None, "ts": "2026-10-11T21:30:00Z",
                               "sentiment_source": None})
    assert ext["ki_signal_score"] is None, \
        "score=None darf NICHT auf den stale Wert zurückfallen"
    assert ext["ki_signal_ts"] == "2026-10-11T21:30:00Z", \
        "ts muss trotzdem gesetzt sein (Fresh-Versuch fand statt)"


def test_d3_no_fresh_ki_is_byte_identical_regression():
    """fresh_ki=None (Default, alter Aufrufer/Test) → exakt altes Verhalten."""
    st = _baseline_stock()
    st["ki_signal_score"] = 55.0
    st["ki_sentiment_source"] = "keyword"
    ext = _build(st)  # kein fresh_ki übergeben
    assert ext["ki_signal_score"] == 55.0
    assert ext["ki_sentiment_source"] == "keyword"
    assert ext["ki_signal_ts"] is None, \
        "ohne fresh_ki darf ki_signal_ts nicht gesetzt werden"


def test_d4_no_fresh_ki_no_stale_score_stays_none():
    st = _baseline_stock()  # kein ki_signal_score gesetzt
    ext = _build(st)
    assert ext["ki_signal_score"] is None
    assert ext["ki_signal_ts"] is None


# ── (E) Schema / S10 ────────────────────────────────────────────────────────

def test_e1_in_observed_not_muss_not_lag():
    assert "ki_signal_ts" in config.S10_OBSERVED_FIELDS
    assert "ki_signal_ts" not in config.S10_MUSS_FIELDS
    assert "ki_signal_ts" not in config.S10_LAG_FIELDS


def test_e2_schema_stays_v4():
    assert '"backtest_schema_version": 4,' in _BH_SRC
    assert '"backtest_schema_version": 5' not in _BH_SRC


# ── (F) claude_sentiment_score Fehlerart-Sichtbarkeit ──────────────────────

def test_f1_error_counter_exists_and_resets():
    assert hasattr(ka, "_KI_SENTIMENT_ERROR_COUNTS")
    for k in ("timeout", "rate_limit", "http_other", "parse_error",
              "request_error", "no_api_key", "no_headlines"):
        assert k in ka._KI_SENTIMENT_ERROR_COUNTS, f"Zähler {k!r} fehlt"
    ka._KI_SENTIMENT_ERROR_COUNTS["timeout"] = 5
    ka._reset_tier3_accumulators()
    assert ka._KI_SENTIMENT_ERROR_COUNTS["timeout"] == 0, \
        "_reset_tier3_accumulators muss den KI-Sentiment-Zähler mit zurücksetzen"


def test_f2_timeout_counted_and_warned_behavior_unchanged(monkeypatch=None):
    import logging
    warnings = []

    class _Handler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warnings.append(record.getMessage())

    ka._KI_SENTIMENT_ERROR_COUNTS["timeout"] = 0
    import os as _os
    import requests as _rq

    def _raise_timeout(*a, **k):
        raise _rq.Timeout("simuliert")

    orig_post = _rq.post
    orig_env = _os.environ.get("ANTHROPIC_API_KEY")
    _rq.post = _raise_timeout
    _os.environ["ANTHROPIC_API_KEY"] = "test-key-fixture"
    handler = _Handler()
    ka.log.addHandler(handler)
    try:
        score, reason = ka.claude_sentiment_score("XXX", ["eine Schlagzeile"])
    finally:
        _rq.post = orig_post
        ka.log.removeHandler(handler)
        if orig_env is None:
            _os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            _os.environ["ANTHROPIC_API_KEY"] = orig_env

    assert score is None and reason == "", \
        "Verhalten (Fallback) darf sich nicht ändern"
    assert ka._KI_SENTIMENT_ERROR_COUNTS["timeout"] == 1
    assert any("Timeout" in w for w in warnings), \
        "Timeout muss jetzt log.warning erzeugen (vorher nur log.debug)"


def test_f3_source_distinguishes_rate_limit_from_other_http():
    start = _KI_SRC.find("def claude_sentiment_score(")
    end = _KI_SRC.find("\ndef ", start + 10)
    body = _KI_SRC[start:end]
    assert '"rate_limit"' in body
    assert "429" in body
    assert '"parse_error"' in body
    assert '"request_error"' in body


def main() -> None:
    tests = [
        ("A1 Top-10-Cut vor apply_agent_boost", test_a1_top10_cut_before_agent_boost),
        ("A2 Fresh-Compute nach Boost/Monster/Conviction, vor Append",
         test_a2_fresh_compute_after_conviction_before_append),
        ("A3 Fresh-Compute schreibt nie auf Stock-Dict",
         test_a3_fresh_compute_never_writes_to_stock_dict),
        ("A4 Ergebnis nur von _append_backtest_entries konsumiert",
         test_a4_result_only_consumed_by_append_call),
        ("B1 alle Ticker bekommen Eintrag + ts, Fehlerfall score=None",
         test_b1_all_tickers_get_entry_with_ts),
        ("B2 leere Top-10 -> leeres Dict", test_b2_empty_top10_returns_empty_dict),
        ("B3 ki_agent-Import-Fehler ist fail-soft",
         test_b3_ki_agent_import_failure_is_fail_soft),
        ("C1 FRESH_KI_SIGNAL_ENABLED=False kurzschliesst",
         test_c1_disabled_flag_short_circuits),
        ("D1 fresh_ki überschreibt stale Stock-Wert",
         test_d1_fresh_ki_overrides_stale_stock_value),
        ("D2 fresh_ki score=None ist ehrliches None (kein Fallback)",
         test_d2_fresh_ki_none_score_is_honest_none_not_fallback),
        ("D3 fresh_ki=None ist byte-identische Regression",
         test_d3_no_fresh_ki_is_byte_identical_regression),
        ("D4 ohne fresh_ki + ohne stale Score bleibt None",
         test_d4_no_fresh_ki_no_stale_score_stays_none),
        ("E1 S10: OBSERVED, nicht MUSS/LAG", test_e1_in_observed_not_muss_not_lag),
        ("E2 Schema bleibt v4", test_e2_schema_stays_v4),
        ("F1 Fehlerzähler existiert + wird zurückgesetzt",
         test_f1_error_counter_exists_and_resets),
        ("F2 Timeout gezählt + gewarnt, Verhalten unverändert",
         test_f2_timeout_counted_and_warned_behavior_unchanged),
        ("F3 Source unterscheidet rate_limit/parse_error/request_error",
         test_f3_source_distinguishes_rate_limit_from_other_http),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # pragma: no cover
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    print()
    if failed:
        print(f"{failed} von {len(tests)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
