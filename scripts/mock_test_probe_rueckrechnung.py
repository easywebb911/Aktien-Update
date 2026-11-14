#!/usr/bin/env python3
"""Mock-Tests für die Wegwerf-Probe Mehrjahres-Rückrechnung (stdlib-only, kein Netz).

Prüft die reinen Hilfsfunktionen (Stichprobe, Konfidenz, DTC-Hälften,
Veröffentlichungs-Verzug, Split-Klassen, Überschneidung, Proxy-Score-Teile),
die Blindheit (kein Ergebnisfeld, aus Backtest-Dateien nur ticker/date) und
den Workflow (nur Hand-Start, contents: read, keine Secrets, kein Push).
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_rueckrechnung as pr  # noqa: E402

SRC = (ROOT / "scripts" / "probe_rueckrechnung.py").read_text(encoding="utf-8")
WF = (ROOT / ".github" / "workflows" / "probe_rueckrechnung.yml").read_text(encoding="utf-8")
FAILS: list[str] = []


def check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main() -> int:
    check("01 Stichprobe n = 2401 (±2 pp, p = 0,5)", pr.SAMPLE_N == 2401)
    w = pr.wilson(50, 100)
    check("02 Wilson 50/100 ≈ [0,40; 0,60]", w["ki95"][0] < 0.41 and w["ki95"][1] > 0.59)
    check("03 Wilson n=0 → None", pr.wilson(0, 0) is None)
    pop = [f"S{i}" for i in range(5000)]
    a, b = pr.draw_sample(pop, 2021), pr.draw_sample(list(reversed(pop)), 2021)
    check("04 Stichprobe deterministisch (Seed, Reihenfolge egal)", a == b and len(a) == 2401)
    check("05 andere Jahre andere Stichprobe", pr.draw_sample(pop, 2022) != a)
    check("06 kleine Grundgesamtheit → Vollerhebung", pr.draw_sample(["B", "A"], 2021) == ["A", "B"])
    low, high, med = pr.split_halves({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": None})
    check("07 DTC-Hälften am Median, None außen vor", low == {"A", "B"} and high == {"C", "D"} and med == 2.5)
    check("08 DTC aus Feld", pr.dtc_value({"daysToCoverQuantity": 3.5}) == 3.5)
    check("09 DTC aus SI/ADV", pr.dtc_value({"currentShortPositionQuantity": 100, "averageDailyVolumeQuantity": 50}) == 2.0)
    check("10 DTC ohne Daten → None", pr.dtc_value({"currentShortPositionQuantity": 100}) is None)
    # Freitag 13.11.2026 + 7 Werktage = Dienstag 24.11.2026
    check("11 Werktage über Wochenende", pr.business_days_after(date(2026, 11, 13), 7) == date(2026, 11, 24))
    s = [date(2026, 10, 15), date(2026, 10, 30)]
    check("12 Stichtag erst nach Veröffentlichung nutzbar",
          pr.latest_usable_settlement(date(2026, 11, 6), s) == date(2026, 10, 15)
          and pr.latest_usable_settlement(date(2026, 11, 10), s) == date(2026, 10, 15)
          and pr.latest_usable_settlement(date(2026, 11, 11), s) == date(2026, 10, 30)
          and pr.latest_usable_settlement(date(2026, 10, 20), s) is None)
    check("13 Split roh + Vorperiode unbereinigt", pr.classify_split(1000, 100, 1000, 0.1) == ("folgt_split", "unbereinigt"))
    check("14 Split Vorperiode bereinigt", pr.classify_split(1000, 100, 100, 0.1) == ("folgt_split", "bereinigt"))
    check("15 Split unverändert", pr.classify_split(1000, 1000, 1000, 0.1)[0] == "unveraendert")
    check("16b Faktor 2: unverändert und folgt_split getrennt",
          pr.classify_split(1000, 1000, 1000, 2.0)[0] == "unveraendert"
          and pr.classify_split(1000, 2000, 1000, 2.0)[0] == "folgt_split")
    check("16c Verzug 8 Werktage (7 + Reserve)", pr.PUB_LAG_BUSINESS_DAYS == 8)
    check("16 kein echter Split → unklar", pr.classify_split(1000, 1000, 1000, 1.0) == ("unklar", "unklar"))
    o = pr.overlap_stats([({"A", "B"}, {"A", "C"}), ({"A"}, {"B"}), (set(), {"A"})])
    check("17 Überschneidung Mittel/Verteilung", o["tage"] == 2 and o["mittel"] == 0.5 and o["verteilung"]["1"] == 1)
    check("18 Gap kein Gap → 0", pr.gap_pts(101, 100, 102) == 0.0)
    check("19 Gap strong hold", pr.gap_pts(110, 100, 120) == 5.0)
    check("20 Gap fail", pr.gap_pts(110, 100, 99) == -3.0)
    check("21 RS-Punkte geklemmt", pr.rs_pts(50) == 3.0 and pr.rs_pts(-50) == -3.0 and pr.rs_pts(None) == 0.0)
    check("22 Proxy-Score Maximum ohne Gap/RS = 92 + Kombi",
          pr.proxy_score(60, 12, 5, 20, 0, 0, True) == 32 + 23 + 23 + 14 + 5)
    check("23 Symbol-Umsetzung für yfinance", pr.yf_symbol("BRK.B") == "BRK-B")
    check("24 Nicht-Stammaktien erkannt", not pr.is_common("XYZ ETF Trust") and pr.is_common("Acme Corp"))
    # Blindheit
    code = re.sub(r'"""(.|\n)*?"""', "", SRC)
    check("25 kein Ergebnisfeld im Code",
          not re.search(r"return_\d|max_gain|max_drawdown|outcome_path|forward_\d", code))
    keys = set(re.findall(r'\be\.get\("(\w+)"\)', SRC))
    check("26 aus Backtest-Dateien nur ticker/date/bootstrap", keys <= {"ticker", "date", "bootstrap"})
    check("27 SEC-User-Agent generisch .invalid", "@example.invalid" in pr.SEC_UA)
    # Workflow
    check("28 nur Hand-Start", "workflow_dispatch" in WF and "schedule" not in WF and "push:" not in WF)
    check("29 contents: read, keine Schreibrechte", "contents: read" in WF and "write" not in WF)
    check("30 keine Secrets, kein Push", "secrets." not in WF and "git push" not in WF)
    # no-op
    old = pr.PROBE_END
    pr.PROBE_END = date(2000, 1, 1)
    try:
        check("31 nach PROBE_END no-op (Exit 0, ohne Netz)", pr.main(["--out", "/nonexistent/x.json"]) == 0)
    finally:
        pr.PROBE_END = old
    if FAILS:
        print(f"{len(FAILS)} FAIL: {FAILS}")
        return 1
    print("Alle probe_rueckrechnung-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
