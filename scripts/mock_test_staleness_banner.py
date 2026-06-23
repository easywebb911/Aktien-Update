"""Mock-Tests für den Frontend-Staleness-Banner (Daily-Run-Frische, 22.06.2026).

Zeigt im Header dezent, WIE ALT die angezeigten Daily-Run-Daten (Top-10) sind.
Drei Zustände, kalibriert gegen die belegte Cron-Verspätung (Diagnose 22.06.):
  < STALENESS_FRESH_MAX_HOURS (15 h) → FRISCH (versteckt, kein Clutter)
  15–24 h                            → VERSPÄTET (gelb, „neuer Run ausstehend")
  > STALENESS_STALE_MIN_HOURS (24 h) → STALE (rot, Datum + Alter)

KRITISCHER Anker (fragile-Annahme-Guard): der Banner liest ``_DAILY_RUN_TS``
(server-eingebrannter Render-Timestamp, NUR vom Daily-Run gesetzt), NICHT
``app_data.generated_at`` (das ki_agent STÜNDLICH überschreibt → würde Frische
vortäuschen). Dieser Test verriegelt genau diese Quelle.

Kategorie A: stdlib only, deterministisch, env-frei, CI-gate-bar. Die
Klassifikations-Logik ist ein Python-Spiegel der JS-Schwellen (drift-resistent:
liest die config-Konstanten zur Laufzeit). Browser-Zeit beeinflusst nur das
ALTER (now − anchor), nicht die Klassifikation → deterministisch.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import STALENESS_FRESH_MAX_HOURS, STALENESS_STALE_MIN_HOURS  # noqa: E402

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HEAD = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def classify(age_h: float, fresh: float, stale: float) -> str:
    """Python-Spiegel der JS-Logik in _renderStaleness (gleiche Grenzen):
    ``if ageH < FRESH → fresh; elif ageH < STALE → delayed; else stale``."""
    if age_h < fresh:
        return "fresh"
    if age_h < stale:
        return "delayed"
    return "stale"


def main() -> int:
    F, S = STALENESS_FRESH_MAX_HOURS, STALENESS_STALE_MIN_HOURS

    print("=== Schwellen-Kalibrierung (Option 1: 15 h / 24 h) ===")
    _check("00 FRESH-Schwelle = 15 (über dem ~13,5 h Werktags-Deploy-Abstand)", F == 15)
    _check("01 STALE-Schwelle = 24 (ein voller Handelstag-Zyklus)", S == 24)
    _check("02 FRESH < STALE (Bänder konsistent)", F < S)

    print("\n=== Drei Zustände — Verifikations-Zeitpunkte (now − N h) ===")
    _check("03 now−3h  → FRISCH",      classify(3,  F, S) == "fresh")
    _check("04 now−12h → FRISCH (NB: unter 8h-Vorschlag wäre das VERSPÄTET — "
           "15h-Kalibrierung verhindert Werktags-Dauer-Alarm)", classify(12, F, S) == "fresh")
    _check("05 now−18h → VERSPÄTET",   classify(18, F, S) == "delayed")
    _check("06 now−36h → STALE",       classify(36, F, S) == "stale")

    print("\n=== Grenzen (exakt auf der Schwelle) ===")
    _check("07 exakt 15h → VERSPÄTET (nicht < FRESH)", classify(15, F, S) == "delayed")
    _check("08 exakt 24h → STALE (nicht < STALE)",     classify(24, F, S) == "stale")
    _check("09 knapp unter 15h → FRISCH",              classify(14.99, F, S) == "fresh")
    _check("10 knapp unter 24h → VERSPÄTET",           classify(23.99, F, S) == "delayed")

    print("\n=== Monday-after-weekend-Szenario (belegter Anlass) ===")
    # Fr-Postclose ~00:30 Berlin → Mo 08:00 Berlin ≈ 56 h alt → muss STALE sein.
    _check("11 56h (Mo-Morgen, Fr-Daten) → STALE", classify(56, F, S) == "stale")
    # Normaler Di-Morgen: Mo-Postclose ~7,5 h alt → FRISCH (kein Dauer-Alarm).
    _check("12 7,5h (normaler Werktags-Morgen) → FRISCH", classify(7.5, F, S) == "fresh")

    print("\n=== Daten-Source-Anker (fragile-Annahme-Guard) ===")
    _check("13 JS-Const _DAILY_RUN_TS injiziert (server-Render-Anker)",
           "const _DAILY_RUN_TS" in SRC and "{daily_run_ts_js}" in SRC)
    _check("14 Anker aus datetime.now(UTC) im _build_context (Render-Zeit, "
           "NICHT generated_at)",
           bool(re.search(r"daily_run_ts_js\s*=\s*datetime\.now\(ZoneInfo\(\"UTC\"\)\)", SRC)))
    _check("15 _renderStaleness wird mit _DAILY_RUN_TS aufgerufen",
           "_renderStaleness(_DAILY_RUN_TS)" in SRC)
    _check("16 GUARD: _renderStaleness NICHT mit appData.generated_at gefüttert",
           "_renderStaleness(appData.generated_at)" not in SRC
           and "_renderStaleness(appData.generated" not in SRC)

    print("\n=== Wiring / Struktur ===")
    _check("17 _renderStaleness-Funktion existiert", "function _renderStaleness(" in SRC)
    _check("18 Header-Span #hdr-staleness vorhanden", 'id="hdr-staleness"' in SRC)
    _check("19 fetch-unabhängiger DOMContentLoaded-Listener (zeigt auch bei "
           "Fetch-Fail/Offline)",
           "DOMContentLoaded', function() {{ _renderStaleness(_DAILY_RUN_TS)" in SRC)
    _check("20 Schwellen aus config injiziert (kein Hardcode im JS)",
           "{staleness_fresh_h}" in SRC and "{staleness_stale_h}" in SRC)

    print("\n=== CSS (head.jinja) ===")
    _check("21 .hdr-staleness-delayed (gelb)", ".hdr-staleness-delayed" in HEAD)
    _check("22 .hdr-staleness-stale (rot)", ".hdr-staleness-stale" in HEAD)
    _check("23 .hdr-staleness[hidden] (FRISCH versteckt)", ".hdr-staleness[hidden]" in HEAD)

    print("\n=== Isolation: kein Score-/Conviction-/Backtest-Eingriff ===")
    # Der Banner-Code darf rein anzeigend sein. Heuristik: _renderStaleness
    # berührt keine Score-Felder; die Anker-Berechnung ist ein reiner Timestamp.
    _func = SRC[SRC.find("function _renderStaleness("):
                SRC.find("function _applyExitGlows(")]
    _check("24 _renderStaleness berührt keine Score/Conviction/Backtest-Felder",
           not any(k in _func for k in ("score", "conviction", "backtest",
                                        "monster", "setup_score")))

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Staleness-Banner-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
