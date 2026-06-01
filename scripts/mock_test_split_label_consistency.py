"""Mock-Test: split-konsistente Return-Label-Berechnung (Fix 01.06.2026).

Hintergrund (Diagnose 01.06.2026): ``update_backtest_returns`` rechnete die
T+0-Returns gegen den GESPEICHERTEN ``entry_price`` (am Entry-Tag persistierter
yfinance-Adjust-Stand). Liegt ein Split zwischen Entry und T+N, sind die später
frisch geladenen ``auto_adjust=True``-Closes in einer ANDEREN Adjust-Epoche →
Skalensprung → extremes Falsch-Return. Fix: Entry-Basis = ``Close[entry_index]``
aus DEMSELBEN Download (``_close_at(0)``), nicht der gespeicherte entry_price.

Tests:
  1. Split zwischen Entry und T+5 → Return korrekt (entry_price gespeichert in
     PRE-Split-Skala wird IGNORIERT, Basis kommt aus dem adjustierten Download).
  2. Kein Split → Return unverändert (keine Regression).
  3. Idempotenz: zweiter Aufruf füllt nichts neu, ändert die Datei nicht.
  4. Entry-Tag nicht im Index (Feiertag/Delisting) → Label bleibt None, kein Crash.

Die schweren Dependencies (pandas/yfinance/requests) werden vor dem Import von
``ki_agent`` gestubbt; ``yf.download`` wird durch ein Fake ersetzt, das das von
der Funktion genutzte pandas-Interface (``["Close"]``, ``.dropna()``,
``.index``, ``.iloc``, ``len``) minimal nachbildet.

Ausführung: ``python scripts/mock_test_split_label_consistency.py``.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Heavy-Dependency-Stubs (vor ki_agent-Import) ────────────────────────────
def _install_stubs():
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")
    if "yfinance" not in sys.modules:
        yf_stub = types.ModuleType("yfinance")
        yf_stub.download = lambda *a, **k: None
        yf_stub.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf_stub


_install_stubs()
import ki_agent  # noqa: E402


# ── Fake-pandas-Objekte (nur das genutzte Interface) ────────────────────────
class _FakeTS:
    def __init__(self, d: _dt.date):
        self._d = d
    def date(self) -> _dt.date:
        return self._d


class _FakeIloc:
    def __init__(self, vals):
        self._vals = vals
    def __getitem__(self, i):
        return self._vals[i]


class _FakeCloses:
    """Bildet ``closes`` nach: index (Liste von _FakeTS), iloc, len, dropna."""
    def __init__(self, dates, vals):
        self.index = [_FakeTS(d) for d in dates]
        self._vals = vals
    @property
    def iloc(self):
        return _FakeIloc(self._vals)
    def __len__(self):
        return len(self._vals)
    def dropna(self):
        return self


class _FakeDF:
    def __init__(self, dates, vals):
        self._closes = _FakeCloses(dates, vals)
    def __contains__(self, key):
        return key == "Close"
    def __getitem__(self, key):
        if key == "Close":
            return self._closes
        raise KeyError(key)


def _trading_days(start: _dt.date, n: int):
    """Erzeugt n aufeinanderfolgende Mo–Fr-Daten ab start (inkl.)."""
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def _make_hist(close_vals, start=_dt.date(2026, 5, 11)):
    """Single-Ticker-Fake-Download: yf.download(...) → _FakeDF (len(tickers)==1
    Pfad). Entry-Datum liegt auf dem ersten Trading-Day."""
    dates = _trading_days(start, len(close_vals))
    return _FakeDF(dates, close_vals)


# ── Test-Harness ────────────────────────────────────────────────────────────
def _run_with(entries, hist_for_ticker, *, today):
    """Patcht BACKTEST_FILE, yf.download, datetime-today und ruft die Funktion.
    Returnt die neu geladenen Einträge + ob die Datei geschrieben wurde."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(entries, tmp)
    tmp.close()

    orig_file = ki_agent.BACKTEST_FILE
    orig_yf = ki_agent.yf
    orig_enabled = ki_agent.BACKTEST_ENABLED

    class _FakeYf:
        def download(self, tickers, *a, **k):
            return hist_for_ticker
    # mtime vor dem Lauf
    before_mtime = pathlib.Path(tmp.name).stat().st_mtime_ns

    ki_agent.BACKTEST_FILE = tmp.name
    ki_agent.yf = _FakeYf()
    ki_agent.BACKTEST_ENABLED = True
    # today fixieren via _today-Ersatz: ki_agent nutzt datetime.now(timezone.utc)
    import datetime as _d
    _orig_dt = ki_agent.datetime

    class _FixedDateTime:
        @staticmethod
        def now(tz=None):
            return _d.datetime(today.year, today.month, today.day,
                               12, 0, tzinfo=_d.timezone.utc)
        @staticmethod
        def strptime(s, fmt):
            return _d.datetime.strptime(s, fmt)
    try:
        ki_agent.datetime = _FixedDateTime
        ki_agent.update_backtest_returns()
    finally:
        ki_agent.datetime = _orig_dt
        ki_agent.BACKTEST_FILE = orig_file
        ki_agent.yf = orig_yf
        ki_agent.BACKTEST_ENABLED = orig_enabled

    after_mtime = pathlib.Path(tmp.name).stat().st_mtime_ns
    out = json.loads(pathlib.Path(tmp.name).read_text(encoding="utf-8"))
    pathlib.Path(tmp.name).unlink()
    return out, (after_mtime != before_mtime)


def _entry(ticker="TICK", date="11.05.2026", entry_price=100.0):
    return {
        "date": date, "ticker": ticker, "score": 80.0,
        "entry_price": round(entry_price, 4), "entry_price_t1": None,
        "return_3d": None, "return_5d": None, "return_10d": None,
        "return_3d_t1": None, "return_5d_t1": None, "return_10d_t1": None,
    }


# === 1 — Split zwischen Entry und T+5 ====================================
def test_split_uses_adjusted_basis():
    """Entry am 11.05. zu Roh-Kurs 100 (gespeichert). Danach 1:10-Reverse-
    Split: die FRISCHEN auto_adjust-Closes stehen alle in Post-Split-Skala
    (~10/Bar, flach). Korrektes Return ≈ 0 %. Der ALTE Code (gegen
    entry_price=100) hätte ~ −90 % gerechnet (Skalensprung)."""
    # Adjustierte Closes: alle ~10.0 (flacher Kurs, nur Skala verschoben)
    closes = [10.0] * 12   # entry-index 0 .. genug für return_10d
    hist = _make_hist(closes)
    out, _ = _run_with([_entry(entry_price=100.0)], hist,
                       today=_dt.date(2026, 5, 30))
    e = out[0]
    # Basis = Close[entry]=10.0, c(T+5)=10.0 → 0 %. NICHT (10/100-1)=-90 %.
    assert e["return_5d"] == 0.0, f"return_5d={e['return_5d']} (erwartet 0.0)"
    assert e["return_3d"] == 0.0, e["return_3d"]
    assert e["return_10d"] == 0.0, e["return_10d"]
    # entry_price-Feld bleibt unverändert erhalten (nur nicht als Basis genutzt)
    assert e["entry_price"] == 100.0, e["entry_price"]


# === 2 — Kein Split: Return unverändert / korrekt ========================
def test_no_split_return_correct():
    """Echter +20 %-Move über 5 Bars, keine Skalen-Diskrepanz. entry_price
    gespeichert == Close[entry] == 50.0."""
    closes = [50.0, 52.0, 54.0, 55.0, 58.0, 60.0, 61.0, 62.0,
              63.0, 64.0, 66.0, 70.0]
    hist = _make_hist(closes)
    out, _ = _run_with([_entry(entry_price=50.0)], hist,
                       today=_dt.date(2026, 5, 30))
    e = out[0]
    # return_5d = closes[5]/closes[0]-1 = 60/50-1 = 20 %
    assert e["return_5d"] == 20.0, f"return_5d={e['return_5d']}"
    # return_3d = 55/50-1 = 10 %
    assert e["return_3d"] == 10.0, e["return_3d"]
    # return_10d = 66/50-1 = 32 %
    assert e["return_10d"] == 32.0, e["return_10d"]


# === 3 — Idempotenz ======================================================
def test_idempotent_second_call_no_write():
    closes = [50.0, 52.0, 54.0, 55.0, 58.0, 60.0, 61.0, 62.0,
              63.0, 64.0, 66.0, 70.0]
    hist = _make_hist(closes)
    # 1. Lauf füllt alles
    out1, wrote1 = _run_with([_entry(entry_price=50.0)], hist,
                             today=_dt.date(2026, 5, 30))
    assert wrote1 is True
    # 2. Lauf auf bereits gefüllten Einträgen → kein Write
    out2, wrote2 = _run_with(out1, hist, today=_dt.date(2026, 5, 30))
    assert wrote2 is False, "Idempotenz verletzt — zweiter Lauf schrieb erneut"
    assert out2 == out1


# === 4 — Entry-Tag nicht im Index → None, kein Crash =====================
def test_entry_date_not_in_index_stays_none():
    closes = [50.0, 52.0, 54.0, 55.0, 58.0, 60.0]
    # Download-Index startet am 18.05., Entry ist 11.05. → ei<0
    hist = _make_hist(closes, start=_dt.date(2026, 5, 18))
    out, _ = _run_with([_entry(date="11.05.2026", entry_price=50.0)], hist,
                       today=_dt.date(2026, 5, 30))
    e = out[0]
    assert e["return_3d"] is None and e["return_5d"] is None, e


# === Runner ==============================================================
def main():
    tests = [
        ("Split → adjustierte Basis (kein Faktor-Sprung)", test_split_uses_adjusted_basis),
        ("Kein Split → Return korrekt (keine Regression)", test_no_split_return_correct),
        ("Idempotenz: 2. Lauf kein Write",                 test_idempotent_second_call_no_write),
        ("Entry-Tag fehlt im Index → None, kein Crash",    test_entry_date_not_in_index_stays_none),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"  ✗ {name}: UNERWARTET {exc!r}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} Test(s) FEHLGESCHLAGEN.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
