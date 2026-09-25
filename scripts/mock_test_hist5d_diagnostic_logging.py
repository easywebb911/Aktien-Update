"""Mock-Tests für das Diagnostik-Logging in ``_extract_hist_5d`` (25.09.2026).

Hintergrund: Diagnose 2026-09-25 (S10-crit) fand, dass die MUSS-Felder
``vol_stability_5d``/``rvol_buildup_5d``/``coiled_spring_score`` in
``backtest_history.json`` seit 23.09.2026 zu ~90 % null sind. Alle drei
hängen letztlich an ``s["hist_5d"]`` (``_extract_hist_5d`` in
``generate_report.py``, Zeile ~1132) — einer NESTED Closure innerhalb
``get_yfinance_batch``, die bei einer nicht-endlichen Zelle (Volume/High/
Low/Close) den GESAMTEN Trading-Tag verwirft (All-or-Nothing-Guard) und bei
< 5 gültigen Tagen eine leere Liste liefert. Bis zu diesem PR gab es dafür
KEINE Log-Zeile — die „batch-weites yfinance-Datenloch"-Hypothese aus der
Diagnose war deshalb nicht empirisch nachprüfbar.

Dieser PR fügt AUSSCHLIESSLICH Logging hinzu (WARNING pro verworfenem Tag/
Zelle(n) + WARNING falls am Ende < 5 Tage übrig bleiben) — die Guard-
Entscheidung selbst (welcher Tag verworfen wird, ob das Endergebnis leer
ist) ist BYTE-FÜR-BYTE unverändert. Jeder Test unten beweist das explizit:
dieselben Eingaben liefern dasselbe ``hist_5d``-Ergebnis wie vor dem PR
(siehe ``scripts/mock_test_backtest_history_writepath.py``, dessen
Replik-Tests für exakt dieselben Fälle weiterhin grün bleiben).

## Extraktions-Technik: ECHTE Funktion, nicht Replik

``_extract_hist_5d`` ist eine nested Closure (kein Top-Level-``def``) —
``mock_test_backtest_history_writepath.py`` löst das bisher über eine von
Hand nachgebaute Replik + „Quelltext-Deckung"-Assertions (prüft NUR, dass
bestimmte Substrings im echten Code vorkommen). Für DIESEN PR reicht das
nicht: die Aufgabenstellung verlangt einen Test gegen die ECHTE Funktion.

Da ``_extract_hist_5d`` keine Closure-Variablen aus ``get_yfinance_batch``
selbst referenziert (nur die Modul-Konstante ``EARLINESS_TREND_LOG_WINDOW_
DAYS`` und die Modul-Funktion ``_finite``), lässt sie sich per Regex aus dem
echten Quelltext ausschneiden, dedenten und in einem isolierten Namespace
``exec``en — das ausgeführte Bytecode ist zeichengenau identisch mit dem
Produktionscode (kein Hand-Abtippen, keine Drift-Gefahr), OHNE den kompletten
``generate_report``-Modul-Import zu brauchen (der yfinance/requests zieht,
im Minimal-CI nicht installiert — siehe ``pr-checks.yml``-Kommentar). Die
echte ``_finite``-Funktion (Top-Level, kein Nesting) wird auf demselben Weg
mitgezogen, damit auch DIESE Abhängigkeit nicht hand-nachgebaut werden muss.

Pflicht-Szenarien laut Aufgabenstellung:
  - mind. 1 Tag mit nicht-endlicher Zelle → Log-Zeile mit korrekten Details
    (Ticker, Datum, betroffene Zelle) — Tests B/C
  - vollständig saubere Daten → KEINE Warn-Log-Zeile (kein False-Positive) —
    Test A

Zusätzlich (Robustheit):
  D. < 5 Roh-Tage → eigene Log-Zeile + leere Liste
  E. kein ``ticker``-Argument (Default None) → identisches Ergebnis, aber
     KEIN Log (Rückwärtskompatibilität für einen hypothetischen künftigen
     Aufrufer ohne Ticker-Kontext)
  F. Ergebnis-Gleichheit exakt wie vor dem PR für "alle valide" und "eine
     NaN-Zelle" (Regressionsschutz auf die Guard-Entscheidung selbst)
  G. Exception im try-Block (z.B. ``.tail()`` wirft) → debug-Log statt
     Crash, leere Liste (bestehender äußerer try/except unverändert)

Kategorie A: reine stdlib (re/textwrap/pathlib/sys), keine Drittlibs.
"""
from __future__ import annotations

import math
import pathlib
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


# ── Echte Quelltext-Extraktion (kein generate_report-Import) ────────────────

_GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _extract_block(src: str, start_marker: str, end_marker: str) -> str:
    start = src.find(start_marker)
    if start == -1:
        raise AssertionError(
            f"Start-Marker nicht gefunden: {start_marker!r} — "
            f"generate_report.py-Struktur verändert?"
        )
    end = src.find(end_marker, start)
    if end == -1:
        raise AssertionError(
            f"End-Marker nicht gefunden: {end_marker!r} (ab Start-Marker) — "
            f"generate_report.py-Struktur verändert?"
        )
    return src[start:end]


_FINITE_SRC = _extract_block(
    _GR_SRC, "def _finite(v) -> bool:\n", "\ndef _finite_cell("
)
_HIST5D_SRC_RAW = _extract_block(
    _GR_SRC, "    def _extract_hist_5d(", "    def _hist_stats("
)
_HIST5D_SRC = textwrap.dedent(_HIST5D_SRC_RAW)

# Vorab-Sanity: die Extraktion muss die NEUE Signatur (ticker-Parameter)
# tatsächlich erwischt haben — sonst testen wir stillschweigend eine alte
# oder leere Fassung (Exzellenz-Block Punkt 3: Nachweis per Test, nicht
# Behauptung — dieser Guard ist Teil des Nachweises selbst).
if "ticker: str | None = None" not in _HIST5D_SRC:
    raise AssertionError(
        "Extrahierter _extract_hist_5d-Quelltext enthält nicht den "
        "erwarteten ticker-Parameter — Extraktions-Marker oder "
        "Funktionssignatur haben sich geändert."
    )


class _FakeLogger:
    """Erfasst .warning()/.debug()-Aufrufe als fertig formatierte Strings
    (analog dem _FakeLogger-Pattern in mock_test_backtest_history_writepath.py)."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.debugs: list[str] = []

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg % args if args else msg)

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(msg % args if args else msg)


def _make_namespace(fake_log: "_FakeLogger") -> dict:
    ns: dict = {
        "math": math,
        "EARLINESS_TREND_LOG_WINDOW_DAYS": 5,  # = config.EARLINESS_TREND_LOG_WINDOW_DAYS
        "log": fake_log,
    }
    exec(_FINITE_SRC, ns)   # echte _finite -> ns["_finite"]
    exec(_HIST5D_SRC, ns)   # echte _extract_hist_5d -> ns["_extract_hist_5d"]
    return ns


class _FakeRow(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeDF:
    """Minimal-Stand-in für ein pandas-tail()/iterrows()-Objekt — trägt
    zusätzlich eine parallele Datums-Liste, damit Tests die geloggte
    Zeilen-Identität (das "Datum") prüfen können."""

    def __init__(self, rows: list[dict], dates: list[str] | None = None):
        self._rows = rows
        self._dates = dates if dates is not None else [str(i) for i in range(len(rows))]

    def tail(self, n):
        return _FakeDF(self._rows[-n:], self._dates[-n:])

    def __len__(self):
        return len(self._rows)

    def iterrows(self):
        return iter(zip(self._dates, (_FakeRow(r) for r in self._rows)))


class _RaisingDF:
    """Simuliert einen kaputten df, dessen .tail() eine Exception wirft —
    für den äußeren try/except-Pfad (Szenario G)."""

    def tail(self, n):
        raise RuntimeError("boom")


_DATES = ["2026-09-19", "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23"]


def _make_valid_rows(n=5):
    return [
        {"Volume": 1_000_000 + i, "High": 10.5 + i, "Low": 9.5 + i, "Close": 10.0 + i}
        for i in range(n)
    ]


# ── A — vollständig saubere Daten -> KEIN Warn-Log ──────────────────────────

def test_a_all_valid_no_warning_logged():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    df = _FakeDF(_make_valid_rows(5), _DATES)
    result = ns["_extract_hist_5d"](df, "ABCD")
    _check("A Ergebnis: 5 Tage, keine Warnung",
           len(result) == 5 and fake_log.warnings == [] and fake_log.debugs == [],
           f"result_len={len(result)} warnings={fake_log.warnings!r}")
    _check("A erster Tag korrekt extrahiert",
           result[0] == {"volume": 1_000_000.0, "high": 10.5, "low": 9.5, "close": 10.0},
           repr(result[0]))


# ── B — eine nicht-endliche Zelle -> Log mit Ticker/Datum/Zelle ────────────

def test_b_single_nan_cell_logs_ticker_date_and_field():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    rows = _make_valid_rows(5)
    rows[2]["High"] = float("nan")  # Tag mit Datum _DATES[2] = 2026-09-21
    df = _FakeDF(rows, _DATES)
    result = ns["_extract_hist_5d"](df, "ABCD")
    _check("B Ergebnis weiterhin leer (Guard-Entscheidung unverändert)",
           result == [], repr(result))
    day_warnings = [w for w in fake_log.warnings if "verworfen" in w]
    _check("B genau 1 Tag-Warnung", len(day_warnings) == 1, repr(fake_log.warnings))
    if day_warnings:
        w = day_warnings[0]
        _check("B Warnung enthält Ticker 'ABCD'", "ABCD" in w, w)
        _check("B Warnung enthält Datum '2026-09-21'", "2026-09-21" in w, w)
        _check("B Warnung enthält betroffene Zelle 'High'", "High" in w, w)
    summary_warnings = [w for w in fake_log.warnings if "gültige Tage" in w]
    _check("B zusätzliche Zusammenfassungs-Warnung (4/5 gültige Tage)",
           len(summary_warnings) == 1 and "4/5" in summary_warnings[0],
           repr(summary_warnings))


# ── C — mehrere nicht-endliche Zellen am selben Tag -> beide gelistet ──────

def test_c_multiple_bad_cells_same_day_listed_together():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    rows = _make_valid_rows(5)
    rows[0]["Volume"] = float("inf")
    rows[0]["Close"] = float("nan")
    df = _FakeDF(rows, _DATES)
    result = ns["_extract_hist_5d"](df, "WOLF")
    _check("C Ergebnis leer", result == [], repr(result))
    day_warnings = [w for w in fake_log.warnings if "verworfen" in w]
    _check("C genau 1 Tag-Warnung für den kaputten Tag",
           len(day_warnings) == 1, repr(fake_log.warnings))
    if day_warnings:
        w = day_warnings[0]
        _check("C nennt Volume UND Close", "Volume" in w and "Close" in w, w)
        _check("C nennt NICHT High/Low (die waren valide)",
               "High" not in w.split("Zelle(n): ")[-1] and "Low" not in w.split("Zelle(n): ")[-1],
               w)


# ── D — < 5 Roh-Tage -> eigene Log-Zeile ────────────────────────────────────

def test_d_insufficient_raw_days_logs_and_returns_empty():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    df = _FakeDF(_make_valid_rows(3), _DATES[:3])
    result = ns["_extract_hist_5d"](df, "GRPN")
    _check("D Ergebnis leer", result == [], repr(result))
    _check("D genau 1 Warnung", len(fake_log.warnings) == 1, repr(fake_log.warnings))
    if fake_log.warnings:
        w = fake_log.warnings[0]
        _check("D nennt Ticker + Roh-Tage-Anzahl 3",
               "GRPN" in w and "3" in w, w)


# ── E — kein ticker-Argument -> identisches Ergebnis, aber kein Log ────────

def test_e_no_ticker_means_no_logging_but_same_result():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    rows = _make_valid_rows(5)
    rows[1]["Low"] = float("nan")
    df = _FakeDF(rows, _DATES)
    result = ns["_extract_hist_5d"](df)  # kein ticker -> Default None
    _check("E Ergebnis identisch zu mit-ticker-Fall (leer)",
           result == [], repr(result))
    _check("E keine Log-Zeile ohne ticker", fake_log.warnings == [] and fake_log.debugs == [],
           repr(fake_log.warnings))


# ── F — Regressionsschutz: Guard-Entscheidung exakt wie vor dem PR ─────────

def test_f_regression_all_valid_matches_pre_pr_shape():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    df = _FakeDF(_make_valid_rows(5), _DATES)
    result = ns["_extract_hist_5d"](df, "TEST")
    expected = [
        {"volume": 1_000_000.0 + i, "high": 10.5 + i, "low": 9.5 + i, "close": 10.0 + i}
        for i in range(5)
    ]
    _check("F 5 valide Tage -> exakt dieselbe Struktur wie vor dem PR",
           result == expected, repr(result))


def test_f2_regression_single_nan_matches_pre_pr_shape():
    ns = _make_namespace(_FakeLogger())
    rows = _make_valid_rows(5)
    rows[2]["Volume"] = float("nan")
    df = _FakeDF(rows, _DATES)
    result = ns["_extract_hist_5d"](df, "TEST")
    _check("F2 1 NaN-Zelle -> weiterhin leere Liste (All-or-Nothing unverändert)",
           result == [], repr(result))


# ── G — Exception im try-Block -> debug-Log statt Crash ────────────────────

def test_g_exception_in_tail_logs_debug_and_returns_empty():
    fake_log = _FakeLogger()
    ns = _make_namespace(fake_log)
    result = ns["_extract_hist_5d"](_RaisingDF(), "XPOF")
    _check("G Exception -> leere Liste, kein Crash", result == [], repr(result))
    _check("G Exception -> genau 1 debug-Log mit Ticker",
           len(fake_log.debugs) == 1 and "XPOF" in fake_log.debugs[0],
           repr(fake_log.debugs))
    _check("G Exception -> keine WARNING (debug, nicht warning)",
           fake_log.warnings == [], repr(fake_log.warnings))


def main() -> int:
    tests = [
        test_a_all_valid_no_warning_logged,
        test_b_single_nan_cell_logs_ticker_date_and_field,
        test_c_multiple_bad_cells_same_day_listed_together,
        test_d_insufficient_raw_days_logs_and_returns_empty,
        test_e_no_ticker_means_no_logging_but_same_result,
        test_f_regression_all_valid_matches_pre_pr_shape,
        test_f2_regression_single_nan_matches_pre_pr_shape,
        test_g_exception_in_tail_logs_debug_and_returns_empty,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — Test-Harness, nicht Prod
            _fails.append(f"{t.__name__}: unexpected {type(exc).__name__}: {exc}")
            print(f"  FAIL {t.__name__}: unexpected {type(exc).__name__}: {exc}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print("  -", f)
        return 1
    print(f"Alle {len(tests)} hist5d_diagnostic_logging-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
