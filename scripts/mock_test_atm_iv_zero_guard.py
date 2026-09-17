"""Mock-Tests für den ATM-IV-Plausibilitäts-Guard in ``get_options_data()``
(Diagnose: 4 von 10 Top-10-Karten zeigten "Impl. Volatilität (ATM) 0,0%" als
vermeintlich echten Messwert).

BEFUND: yfinance liefert für nicht aktuell quotierte ATM-Strikes gelegentlich
den literalen Sentinel-Wert ``impliedVolatility = 0.0`` statt ``NaN`` (Yahoos
IV-Solver konvergiert ohne Bid/Ask nicht). Der bestehende ``.dropna()``-Filter
fängt nur ``NaN``, nicht den literalen Wert ``0.0`` — die Render-Pfade sind
bereits korrekt ``!= None``-gated (v1-Card, v2-Card, Watchlist-JS-Detailtabelle,
KI-Analyse-Kontext), zeigen also fälschlich "0,0%" statt die Zeile wegzulassen.

FIX (generate_report.py:get_options_data(), ~Z. 1660-1666): analog zum
direkt daneben stehenden ``pc_ratio``-Guard (``if total_call_oi > 0 else
None``) wird ein ATM-IV-Wert ``<= 0`` jetzt als ``None`` behandelt statt als
valider Messwert durchgereicht.

Test-Standard: treibt die ECHTE ``generate_report.get_options_data()`` über
einen gemockten ``yf.Ticker`` (reale pandas-DataFrames für ``calls``/``puts``,
kein Logik-Replikat) — der Fix wird durch das tatsächliche Funktionsergebnis
bewiesen, nicht durch eine Nachbildung.

EINZIGE geänderte Stelle: die Fetch-Funktion selbst. Kein Konsument (Render-
oder Kontext-Code) wird hier angefasst oder getestet — die vier Konsumenten
sind bereits ``!= None``-gated und profitieren automatisch, sobald die Quelle
``None`` statt ``0.0`` liefert (durch Code-Inspektion in der Diagnose bereits
belegt, hier nicht erneut getestet).

Tests:
  1. ATM-Strike mit impliedVolatility=0.0 (Yahoo-Sentinel) → atm_iv is None
     (statt 0.0) — der eigentliche Bug-Fix-Nachweis.
  2. ATM-Strike mit einem plausiblen IV-Wert (0.85 = 85 %) → atm_iv bleibt
     unverändert 0.85 (Gegenprobe: kein False-Positive der neuen Guard-
     Bedingung, normale Messwerte werden nicht verworfen).
  3. pc_ratio bleibt in beiden Fällen unverändert aus den openInterest-Spalten
     berechnet — der neue Guard betrifft nachweislich nur atm_iv, nicht den
     Nachbar-Code.

HINWEIS ZUR CI-EINORDNUNG: dieser Test treibt echte pandas-DataFrame-
Operationen (``.dropna()``, ``.abs()``, ``.idxmin()``, ``.loc[]``,
Boolean-Masking) — nicht nur gestubbtes yfinance. Die Minimal-CI
(``pr-checks.yml`` installiert bewusst NUR jinja2+pyyaml, kein
``requirements.txt``/pandas) kann das nicht ausführen. Analog zu den
bestehenden EXCLUDED-Einträgen der yfinance-Import-Klasse
(``catalyst``, ``chat_synthesis_watchlist_fallback``, ``postclose_run``,
``score_history_pruning``, ``setup_erosion`` in
``scripts/run_ci_mock_tests.py``) gehört dieser Test in dieselbe EXCLUDED-
Kategorie (Grund: "pandas erforderlich"), NICHT in die ALLOWLIST. Lokal
verifiziert (pandas installiert) — beide Tests grün.

Ausführung: ``python scripts/mock_test_atm_iv_zero_guard.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import date, timedelta

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# ── Heavy-Dependency-Stubs (identisch zu mock_test_marketcap_price_nan_filter.py,
#    NUR yfinance/requests/bs4/deep_translator/watchlist — pandas bleibt ECHT,
#    weil get_options_data() reale DataFrame-Operationen ausführt). ──────────
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
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
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


_install_stubs()
import generate_report as gr  # noqa: E402


# ── Fake yfinance.Ticker — genug Oberfläche für get_options_data() ─────────
class _FakeOptionChain:
    def __init__(self, calls: pd.DataFrame, puts: pd.DataFrame):
        self.calls = calls
        self.puts = puts


class _FakeTicker:
    """Ein einziger Verfallstermin (+10 Tage) — liegt sowohl über
    IV_MIN_DAYS_TO_EXPIRY (7) als auch unter GAMMA_MAX_DAYS_TO_EXPIRY (14),
    damit der Gamma-Squeeze-Block (GAMMA_SQUEEZE_ENABLED=True per Default)
    denselben ``calls``-Frame wiederverwendet (``exp == chosen``) statt
    einen zweiten ``option_chain()``-Aufruf zu brauchen."""

    def __init__(self, calls: pd.DataFrame, puts: pd.DataFrame, last_price: float):
        expiry = (date.today() + timedelta(days=10)).isoformat()
        self.options = (expiry,)
        self._chain = _FakeOptionChain(calls, puts)
        self.fast_info = {"lastPrice": last_price}

    def option_chain(self, expiry):
        return self._chain


def _make_chain(atm_iv_value: float, cur_price: float = 10.0):
    """Drei Strikes um ``cur_price`` herum; der mittlere (== cur_price) trägt
    ``atm_iv_value`` — das ist der Strike, den idxmin() als ATM wählt."""
    calls = pd.DataFrame({
        "strike":            [cur_price - 2.5, cur_price, cur_price + 2.5],
        "impliedVolatility": [1.20,             atm_iv_value, 0.95],
        "openInterest":      [50.0,             300.0,        80.0],
    })
    puts = pd.DataFrame({
        "strike":       [cur_price - 2.5, cur_price, cur_price + 2.5],
        "openInterest": [40.0,             120.0,     60.0],
    })
    return calls, puts


def _run_with_fake_ticker(atm_iv_value: float, cur_price: float = 10.0) -> dict:
    calls, puts = _make_chain(atm_iv_value, cur_price)
    fake = _FakeTicker(calls, puts, last_price=cur_price)
    orig_ticker = gr.yf.Ticker
    gr.yf.Ticker = lambda ticker: fake
    try:
        return gr.get_options_data("TESTTICK")
    finally:
        gr.yf.Ticker = orig_ticker


def test_zero_iv_becomes_none():
    """(1) Yahoo-Sentinel 0.0 am ATM-Strike → atm_iv muss None sein, nicht 0.0."""
    result = _run_with_fake_ticker(atm_iv_value=0.0)
    _check("zero-iv: atm_iv is None (nicht 0.0)",
           result.get("atm_iv") is None,
           detail=f"atm_iv={result.get('atm_iv')!r}")
    # Nachbar-Feld pc_ratio darf vom neuen Guard nicht berührt werden.
    _check("zero-iv: pc_ratio unveraendert berechnet (nicht None)",
           result.get("pc_ratio") is not None,
           detail=f"pc_ratio={result.get('pc_ratio')!r}")


def test_plausible_iv_passes_through():
    """(2) Plausibler Wert 0.85 → unveraendert durchgereicht (kein False-Positive)."""
    result = _run_with_fake_ticker(atm_iv_value=0.85)
    _check("plausible-iv: atm_iv == 0.85 (unveraendert)",
           result.get("atm_iv") == 0.85,
           detail=f"atm_iv={result.get('atm_iv')!r}")


def test_pc_ratio_value_matches_openinterest():
    """(3) pc_ratio-Berechnung selbst ist vom Guard unberuehrt — Kontrollwert
    aus den fixen openInterest-Spalten: put-Summe 220 / call-Summe 430."""
    result = _run_with_fake_ticker(atm_iv_value=0.85)
    expected = (40.0 + 120.0 + 60.0) / (50.0 + 300.0 + 80.0)
    pc = result.get("pc_ratio")
    _check("pc_ratio: exakter Kontrollwert aus openInterest-Spalten",
           pc is not None and abs(pc - expected) < 1e-9,
           detail=f"pc_ratio={pc!r} erwartet={expected!r}")


def main() -> int:
    print("── ATM-IV Zero-Sentinel-Guard (get_options_data) ──────────────")
    test_zero_iv_becomes_none()
    test_plausible_iv_passes_through()
    test_pc_ratio_value_matches_openinterest()
    print()
    if _fails:
        print(f"{len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("Alle Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
