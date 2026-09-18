"""Mock-Tests für die SPY-Benchmark-Geschwisterfelder (18.09.2026).

Ergänzt ``return_3d/5d/10d`` in ``backtest_history.json`` um parallele
``_vs_spy``-Geschwisterfelder: ``return_Nd_vs_spy = return_Nd (BRUTTO) −
SPY-Rendite über dasselbe Entry-Datum-Fenster``. Bestehende Felder
(``return_Nd``, ``return_Nd_net``, ``return_Nd_t1``) bleiben UNVERÄNDERT —
reine additive Ergänzung, analog zum Haircut-Netto-Präzedenzfall
(12.09.2026, siehe ``mock_test_haircut_net_returns.py``).

KRITISCHER Sorgfaltspunkt aus der Diagnose: SPYs Entry-Index-Position MUSS
SEPARAT in SPYs EIGENER Datums-Index-Liste gesucht werden — NICHT der
Ticker-Offset (``ei``) wiederverwendet werden. Ein Ticker mit Datenlücke
(Handelsaussetzung, bei diesen Small-Caps nicht selten) hat eine andere
Index-Belegung als SPY; ein gemeinsamer Offset würde SPY und Ticker
gegeneinander verschieben und eine falsche SPY-Rendite liefern.

Zweistufiger Test (Muster identisch zu ``mock_test_haircut_net_returns.py``):
  (A) S10-Whitelist + Wiring + Source-Inspektion — nur ``config``-Import +
      Text-Read von ``ki_agent.py`` (KEIN Modul-Import — importiert
      yfinance top-level). Läuft im stdlib-only CI-Slot (Allowlist).
  (B) ECHTE ``ki_agent.update_backtest_returns()`` gegen ZWEI unter-
      schiedliche gemockte ``yf.download``-Zeitreihen (Ticker MIT
      Datenlücke, SPY OHNE Lücke) — braucht pandas + yfinance, wird
      übersprungen wenn nicht verfügbar (CI-Slot).

Verifiziert:
- (A) alle 3 neuen Felder in S10_OBSERVED_FIELDS, NICHT in MUSS/LAG
      (reine Transformation, analog return_Nd_net — per Rückfrage bestätigt,
      WEICHT von der ursprünglichen "S10_LAG_FIELDS"-Anweisung ab).
- (A) Wiring: SPY-Fetch hat eigenen try/except (fail-soft, unabhängig vom
      Ticker-Fetch); ``_spy_close_at`` referenziert NIRGENDS den Ticker-
      Offset ``ei`` (nur ``ei_spy``, eigene Suche); vs_spy wird gegen den
      BRUTTO-Wert ``e[k0]`` gerechnet, nicht gegen ``e[f"{k0}_net"]``; vs_spy
      steht INNERHALB des ``if e.get(k0) is None`` Guards (kein Backfill
      bereits gereifter Alt-Records).
- (B) return_Nd (Brutto) unverändert korrekt trotz SPY-Zusatzlogik.
- (B) return_Nd_vs_spy ≠ return_Nd (echte Differenzbildung, kein
      Kopierfehler) UND ≠ 0 bei unterschiedlichen Trends.
- (B) return_Nd_vs_spy exakt gegen eine unabhängig aus der UNGEDÄMPFTEN
      SPY-Serie vorgerechnete Erwartung (Kernnachweis: SPY-Wert kommt aus
      SPYs EIGENER Datums-Position, nicht aus dem ticker-verschobenen Offset).
- (B) Datenlücken-Fall: der Ticker hat einen fehlenden Handelstag zwischen
      Entry und T+10 — die SPY-Berechnung bleibt davon vollständig
      unbeeinflusst (identisches Ergebnis wie im lückenlosen Referenzfall).
- (B) SPY-Fetch-Fehler (Exception) → return_Nd_vs_spy bleibt None,
      return_Nd (Brutto) UNBERÜHRT (Fail-Soft-Isolation der beiden Fetches).

Ausführung: ``python scripts/mock_test_backtest_return_vs_spy.py``.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_s10_schema_and_wiring():
    """(A) — läuft ohne pandas/yfinance, stdlib-only. CI-Slot-Kompatibel."""
    print("── (A) S10-Klassifikation + Source-Wiring (stdlib-only) ──────")

    new_fields = ("return_3d_vs_spy", "return_5d_vs_spy", "return_10d_vs_spy")
    for f in new_fields:
        _check(f"A1 {f} in S10_OBSERVED_FIELDS",
               f in config.S10_OBSERVED_FIELDS,
               "sonst feuert _s10_check_unknown_fields WARN am 1. Record (Lehre #388)")
        _check(f"A2 {f} NICHT in S10_MUSS_FIELDS",
               f not in config.S10_MUSS_FIELDS)
        _check(f"A3 {f} NICHT in S10_LAG_FIELDS",
               f not in config.S10_LAG_FIELDS,
               "reine Transformation von return_Nd, analog return_Nd_net — "
               "kein sinnvoller eigener Lag-Zeitpunkt (Rückfrage bestätigt)")

    ka_src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")

    _check("A4 update_backtest_returns() vorhanden",
           "def update_backtest_returns()" in ka_src)
    _check("A5 SPY-Fetch vorhanden (yf.download(\"SPY\", ...))",
           'yf.download("SPY"' in ka_src)

    # Fail-Soft-Isolation: SPY-Fetch hat einen EIGENEN try/except-Block,
    # getrennt vom Ticker-Fetch (kein gemeinsamer Fehlerpfad).
    spy_try_idx = ka_src.find('spy_hist = yf.download("SPY"')
    _check("A6 SPY-Fetch-Aufruf gefunden", spy_try_idx != -1)
    surrounding = ka_src[max(0, spy_try_idx - 200):spy_try_idx + 550]
    _check("A7 SPY-Fetch in eigenem try/except (fail-soft, unabhängig vom Ticker-Fetch)",
           "except Exception as exc:" in surrounding
           and "spy_closes = None" in surrounding)

    # KRITISCH: _spy_close_at referenziert NIE den Ticker-Offset `ei` —
    # nur `ei_spy` (eigene, separate Suche in SPYs Index).
    fn_idx = ka_src.find("def _spy_close_at(")
    _check("A8 _spy_close_at() definiert", fn_idx != -1)
    fn_end = ka_src.find("\n\n", fn_idx)
    fn_body = ka_src[fn_idx:fn_end] if fn_idx != -1 else ""
    _check("A9 _spy_close_at nutzt eigene Variable ei_spy",
           "ei_spy" in fn_body)
    _check("A10 KRITISCH: _spy_close_at referenziert NICHT den Ticker-Offset "
           "'ei' (nur 'ei_spy') — sonst Verschiebungs-Bug bei Ticker-Datenlücke",
           # 'ei' darf nur als Teilstring von 'ei_spy' vorkommen, nie bare.
           not any(tok == "ei" for tok in
                   fn_body.replace("ei_spy", "").replace("entry_dt", "")
                          .replace("dropna", "").replace("closes.index", "")
                          .split()))

    # vs_spy wird gegen den BRUTTO-Wert gerechnet, nicht gegen _net.
    kvs_idx = ka_src.find('kvs = f"{k0}_vs_spy"')
    _check("A11 kvs-Zuweisung gefunden", kvs_idx != -1)
    kvs_block = ka_src[kvs_idx:kvs_idx + 500] if kvs_idx != -1 else ""
    _check("A12 vs_spy wird gegen BRUTTO e[k0] gerechnet (e[k0] - spy_ret)",
           'e[kvs] = round(e[k0] - spy_ret, 2)' in kvs_block)
    _check("A13 vs_spy wird NICHT gegen das Netto-Geschwisterfeld gerechnet",
           'e[f"{k0}_net"] - spy_ret' not in kvs_block
           and 'e[kvs] = round(e[f"{k0}_net"]' not in kvs_block)

    # Kein Backfill: vs_spy-Block muss INNERHALB desselben Guards stehen wie
    # die frische Brutto-Zuweisung (return_Xd is None and entry_basis > 0).
    guard_idx = ka_src.find("if e.get(k0) is None and entry_basis > 0:")
    _check("A14 return_Xd-Guard gefunden", guard_idx != -1)
    guard_end = ka_src.find("k1 = f\"return_{win}d_t1\"", guard_idx)
    guard_block = ka_src[guard_idx:guard_end] if guard_idx != -1 else ""
    _check("A15 vs_spy-Berechnung steht INNERHALB des Brutto-Guards "
           "(kein Backfill auf bereits gereifte Alt-Records)",
           'kvs = f"{k0}_vs_spy"' in guard_block
           and 'e[kvs] = round(e[k0] - spy_ret, 2)' in guard_block)
    _check("A16 Reihenfolge: Brutto-Zuweisung VOR vs_spy-Zuweisung",
           guard_block.find('e[k0] = round((c / entry_basis - 1) * 100, 2)')
           < guard_block.find('e[kvs] = round(e[k0] - spy_ret, 2)'))

    # Regression: bestehende Felder unverändert vorhanden.
    _check("A17 Regression — return_Xd_net-Zuweisung weiterhin vorhanden",
           'e[f"{k0}_net"] = apply_round_trip_haircut(e[k0])' in ka_src)


def _test_real_functions():
    """(B) — braucht pandas + yfinance (ki_agent importiert yfinance top-
    level). Testet die ECHTE Produktions-Funktion, kein Logik-Replikat."""
    try:
        import pandas as pd  # noqa: F401
        import yfinance  # noqa: F401
    except ImportError as exc:
        print(f"── (B) Integrations-Tests: ÜBERSPRUNGEN — {exc} nicht "
              "verfügbar (CI-Slot stdlib+jinja2+pyyaml). Läuft im "
              "Daily-Run-Environment mit pandas+yfinance vollständig.")
        return

    print("── (B) ECHTE ki_agent.update_backtest_returns() — SPY-Benchmark ──")
    import pandas as pd
    import ki_agent

    dates = pd.bdate_range("2026-01-05", periods=40)
    entry_idx = 5
    entry_date = dates[entry_idx]
    entry_date_str = entry_date.strftime("%d.%m.%Y")
    gap_idx = 8  # 3 Handelstage nach Entry — zwischen Entry und T+10.

    # ── Ticker-Serie MIT Datenlücke (simulierte Handelsaussetzung an gap_idx) ──
    ticker_closes_full = pd.Series([100.0 + i for i in range(40)], index=dates)
    ticker_dates_gapped = dates.delete(gap_idx)
    ticker_closes_gapped = ticker_closes_full.drop(ticker_closes_full.index[gap_idx])
    ticker_df = pd.DataFrame({
        "Open": ticker_closes_gapped, "High": ticker_closes_gapped + 0.5,
        "Low": ticker_closes_gapped - 0.5, "Close": ticker_closes_gapped,
        "Volume": 1000,
    }, index=ticker_dates_gapped)

    # ── SPY-Serie OHNE Lücke, ANDERER Trend (0.5/Tag statt 1.0/Tag) ──
    spy_closes_full = pd.Series([400.0 + 0.5 * i for i in range(40)], index=dates)
    spy_df = pd.DataFrame({
        "Open": spy_closes_full, "High": spy_closes_full + 0.2,
        "Low": spy_closes_full - 0.2, "Close": spy_closes_full,
        "Volume": 2000,
    }, index=dates)

    tmp_dir = tempfile.mkdtemp(prefix="mock_test_vs_spy_")
    bt_path = os.path.join(tmp_dir, "backtest_history.json")
    entry = {
        "date": entry_date_str, "ticker": "TESTX", "score": 80.0,
        "entry_price": None, "entry_price_t1": None,
        "return_3d": None, "return_5d": None, "return_10d": None,
        "return_3d_t1": None, "return_5d_t1": None, "return_10d_t1": None,
        "return_3d_net": None, "return_5d_net": None, "return_10d_net": None,
        "return_3d_vs_spy": None, "return_5d_vs_spy": None, "return_10d_vs_spy": None,
    }
    with open(bt_path, "w", encoding="utf-8") as fh:
        json.dump([entry], fh)

    orig_backtest_file = ki_agent.BACKTEST_FILE
    orig_download = ki_agent.yf.download
    orig_datetime = ki_agent.datetime

    class _FakeDateTime(orig_datetime):
        @classmethod
        def now(cls, tz=None):
            return orig_datetime(2026, 2, 10, tzinfo=tz)  # weit genug für T+10

    def _fake_download(tickers, **kw):
        # Ticker-Fetch übergibt eine Liste (siehe update_backtest_returns:
        # `tickers = sorted({...})`), SPY-Fetch übergibt den bloßen String.
        if tickers == "SPY":
            return spy_df
        return ticker_df

    try:
        ki_agent.BACKTEST_FILE = bt_path
        ki_agent.yf.download = _fake_download
        ki_agent.datetime = _FakeDateTime

        ki_agent.update_backtest_returns()

        with open(bt_path, encoding="utf-8") as fh:
            result = json.load(fh)
    finally:
        ki_agent.BACKTEST_FILE = orig_backtest_file
        ki_agent.yf.download = orig_download
        ki_agent.datetime = orig_datetime

    e = result[0]

    # ── Unabhängig vorgerechnete Erwartungswerte ────────────────────────
    # Ticker (GAPPED positional offset — bestehender Mechanismus, hier NUR
    # als Kontrollwert reproduziert, nicht Gegenstand dieser Änderung).
    entry_basis = float(ticker_closes_gapped.iloc[entry_idx])
    c3_gapped  = float(ticker_closes_gapped.iloc[entry_idx + 3])
    c10_gapped = float(ticker_closes_gapped.iloc[entry_idx + 10])
    expected_return_3d  = round((c3_gapped / entry_basis - 1) * 100, 2)
    expected_return_10d = round((c10_gapped / entry_basis - 1) * 100, 2)

    _check("B1 return_3d (Brutto) unverändert korrekt",
           e["return_3d"] == expected_return_3d,
           f"expected {expected_return_3d}, got {e['return_3d']}")
    _check("B2 return_10d (Brutto) unverändert korrekt",
           e["return_10d"] == expected_return_10d,
           f"expected {expected_return_10d}, got {e['return_10d']}")

    # SPY — aus der UNGEDÄMPFTEN, eigenen Datums-Position (kein Ticker-
    # Offset-Bezug!). entry_idx in SPYs Serie ist exakt 5, unabhängig vom
    # Ticker-Gap.
    spy_c0  = float(spy_closes_full.iloc[entry_idx])
    spy_c3  = float(spy_closes_full.iloc[entry_idx + 3])
    spy_c10 = float(spy_closes_full.iloc[entry_idx + 10])
    spy_ret_3  = (spy_c3 / spy_c0 - 1) * 100
    spy_ret_10 = (spy_c10 / spy_c0 - 1) * 100
    expected_vs_spy_3  = round(e["return_3d"] - spy_ret_3, 2)
    expected_vs_spy_10 = round(e["return_10d"] - spy_ret_10, 2)

    _check("B3 return_3d_vs_spy exakt gegen unabhängig vorgerechnete SPY-"
           "Erwartung (SPY-Wert aus SPYs EIGENER Datumsposition)",
           e["return_3d_vs_spy"] == expected_vs_spy_3,
           f"expected {expected_vs_spy_3}, got {e['return_3d_vs_spy']}")
    _check("B4 return_10d_vs_spy exakt gegen unabhängig vorgerechnete SPY-"
           "Erwartung — KERNNACHWEIS: Ticker-Datenlücke bei gap_idx=8 "
           "(zwischen Entry und T+10) beeinflusst die SPY-Berechnung NICHT",
           e["return_10d_vs_spy"] == expected_vs_spy_10,
           f"expected {expected_vs_spy_10}, got {e['return_10d_vs_spy']}")

    _check("B5 return_3d_vs_spy != return_3d (echte Differenzbildung, kein "
           "Kopierfehler — SPY-Trend 0.5/Tag vs. Ticker-Trend 1.0/Tag)",
           e["return_3d_vs_spy"] != e["return_3d"])
    _check("B6 return_10d_vs_spy != 0.0 (unterschiedliche Trends erzeugen "
           "eine echte, von Null verschiedene Überschussrendite)",
           e["return_10d_vs_spy"] != 0.0)

    # Regression: bestehende Netto-Felder unverändert korrekt (Diagnose-
    # Fix betrifft NICHT die _net-Berechnung).
    import backtest_history as bh
    _check("B7 Regression — return_10d_net weiterhin apply_round_trip_haircut(return_10d)",
           e["return_10d_net"] == bh.apply_round_trip_haircut(e["return_10d"]))
    _check("B8 Regression — score unverändert (80.0)", e["score"] == 80.0)

    print("── (B) SPY-Fetch-Fehler — Fail-Soft-Isolation ──────────────────")
    _test_spy_fetch_failure_isolation()


def _test_spy_fetch_failure_isolation():
    """Schlägt NUR der SPY-Fetch fehl (Exception) → return_Nd_vs_spy bleibt
    None, return_Nd (Brutto) bleibt UNBERÜHRT — die beiden try/except-
    Blöcke dürfen sich nicht gegenseitig beeinflussen."""
    import pandas as pd
    import ki_agent

    dates = pd.bdate_range("2026-03-02", periods=40)
    entry_idx = 5
    entry_date_str = dates[entry_idx].strftime("%d.%m.%Y")
    ticker_closes = pd.Series([50.0 + 0.3 * i for i in range(40)], index=dates)
    ticker_df = pd.DataFrame({
        "Open": ticker_closes, "High": ticker_closes + 0.2,
        "Low": ticker_closes - 0.2, "Close": ticker_closes, "Volume": 500,
    }, index=dates)

    tmp_dir = tempfile.mkdtemp(prefix="mock_test_vs_spy_fail_")
    bt_path = os.path.join(tmp_dir, "backtest_history.json")
    entry = {
        "date": entry_date_str, "ticker": "TESTY", "score": 55.0,
        "entry_price": None, "entry_price_t1": None,
        "return_3d": None, "return_5d": None, "return_10d": None,
        "return_3d_t1": None, "return_5d_t1": None, "return_10d_t1": None,
        "return_3d_net": None, "return_5d_net": None, "return_10d_net": None,
        "return_3d_vs_spy": None, "return_5d_vs_spy": None, "return_10d_vs_spy": None,
    }
    with open(bt_path, "w", encoding="utf-8") as fh:
        json.dump([entry], fh)

    orig_backtest_file = ki_agent.BACKTEST_FILE
    orig_download = ki_agent.yf.download
    orig_datetime = ki_agent.datetime

    class _FakeDateTime(orig_datetime):
        @classmethod
        def now(cls, tz=None):
            return orig_datetime(2026, 3, 20, tzinfo=tz)

    def _fake_download_spy_broken(tickers, **kw):
        if tickers == "SPY":
            raise RuntimeError("simulated SPY fetch outage")
        return ticker_df

    try:
        ki_agent.BACKTEST_FILE = bt_path
        ki_agent.yf.download = _fake_download_spy_broken
        ki_agent.datetime = _FakeDateTime

        ki_agent.update_backtest_returns()

        with open(bt_path, encoding="utf-8") as fh:
            result = json.load(fh)
    finally:
        ki_agent.BACKTEST_FILE = orig_backtest_file
        ki_agent.yf.download = orig_download
        ki_agent.datetime = orig_datetime

    e = result[0]
    entry_basis = float(ticker_closes.iloc[entry_idx])
    c10 = float(ticker_closes.iloc[entry_idx + 10])
    expected_return_10d = round((c10 / entry_basis - 1) * 100, 2)

    _check("C1 return_10d (Brutto) bleibt korrekt trotz SPY-Fetch-Exception",
           e["return_10d"] == expected_return_10d,
           f"expected {expected_return_10d}, got {e['return_10d']}")
    _check("C2 return_10d_vs_spy bleibt None (SPY-Fetch fehlgeschlagen, "
           "kein Platzhalter-/Ersatzwert erfunden)",
           e["return_10d_vs_spy"] is None)
    _check("C3 return_10d_net weiterhin korrekt (Netto-Pfad unbeeinflusst)",
           e["return_10d_net"] is not None)


def main():
    _test_s10_schema_and_wiring()
    _test_real_functions()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (SPY-Benchmark-Renditefelder: S10 + "
          "Wiring + echte Integration inkl. Datenlücken- und Fetch-Fail-Fall).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
