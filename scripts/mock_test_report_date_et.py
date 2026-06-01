"""Mock-Test: report_date + _today_iso an US-Eastern-Handelstag gekoppelt.

Hintergrund (Diagnose/Fix 01.06.2026): ``report_date`` (= Dedup-Key +
``date``-Feld jedes backtest_history-Eintrags) war an die Berlin-Wallclock
gekoppelt. Ein postclose-Run, der durch GitHub-Actions-Drift nach Berlin-
Mitternacht läuft (z.B. 22-23 UTC = 00-01 Berlin), bekam den NÄCHSTEN
Berlin-Tag, obwohl er denselben US-Handelstag (16-17 ET) verarbeitet →
Fehl-Datierung + Dedup-Kollision (28.05.-Kohorte landete als 29.05.).

Fix: ``report_date`` UND ``_today_iso`` auf ``America/New_York``. Beide
müssen DERSELBEN Achse folgen, weil ``_today_iso`` S1 (score_history-
Vergleich, gestempelt mit report_date) und das S4-Wochenend-Gate speist.

Tests:
  1. Datums-Logik: ein 28.05. 22:30-UTC-Drift-Run liefert unter ET den
     korrekten US-Tag 28.05. (Berlin hätte fälschlich 29.05. geliefert).
  2. today_iso (ET) folgt derselben Achse → S1/S4 konsistent.
  3. Source-Inspektion: report_date-Zeile nutzt America/New_York, nicht
     Europe/Berlin.
  4. Source-Inspektion: _today_iso-Zeile nutzt America/New_York.
  5. Source-Inspektion: backtest_has_today vergleicht weiterhin gegen
     report_date (nicht today_iso) — bleibt damit automatisch achs-konsistent.

Ausführung: ``python scripts/mock_test_report_date_et.py``.
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# === 1-2 — Datums-Logik (Drift über Berlin-Mitternacht) ==================
def test_et_date_at_midnight_drift():
    drift = datetime(2026, 5, 28, 22, 30, tzinfo=timezone.utc)
    et = drift.astimezone(ZoneInfo("America/New_York")).strftime("%d.%m.%Y")
    berlin = drift.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y")
    assert et == "28.05.2026", f"ET-date={et} (erwartet 28.05.2026)"
    assert berlin == "29.05.2026", f"Berlin-date={berlin} (Beleg alte Bug-Achse)"


def test_today_iso_same_et_axis():
    drift = datetime(2026, 5, 28, 22, 30, tzinfo=timezone.utc)
    iso = drift.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    assert iso == "2026-05-28", f"today_iso(ET)={iso}"


# === 3-5 — Source-Inspektion ============================================
def test_report_date_uses_eastern():
    m = re.search(r'report_date\s*=\s*datetime\.now\(\s*ZoneInfo\(\s*"([^"]+)"\s*\)\s*\)'
                  r'\.strftime\("%d\.%m\.%Y"\)', GR)
    assert m is not None, "report_date-Zuweisung nicht im erwarteten Muster gefunden"
    assert m.group(1) == "America/New_York", \
        f"report_date nutzt {m.group(1)!r}, erwartet America/New_York"


def test_today_iso_uses_eastern():
    m = re.search(r'_today_iso\s*=\s*datetime\.now\(\s*ZoneInfo\(\s*"([^"]+)"\s*\)\s*\)'
                  r'\.strftime\("%Y-%m-%d"\)', GR)
    assert m is not None, "_today_iso-Zuweisung nicht im erwarteten Muster gefunden"
    assert m.group(1) == "America/New_York", \
        f"_today_iso nutzt {m.group(1)!r}, erwartet America/New_York"


def test_backtest_has_today_compares_report_date():
    # backtest_has_today muss gegen report_date prüfen (achs-konsistent),
    # nicht gegen today_iso. Suchstring aus der bestehenden Zeile.
    assert '.get("date") == report_date' in GR, \
        "backtest_has_today vergleicht nicht mehr gegen report_date"


# === Runner ==============================================================
def main():
    tests = [
        ("ET-date am Mitternachts-Drift korrekt (28.05)", test_et_date_at_midnight_drift),
        ("today_iso folgt ET-Achse",                      test_today_iso_same_et_axis),
        ("report_date nutzt America/New_York",            test_report_date_uses_eastern),
        ("_today_iso nutzt America/New_York",             test_today_iso_uses_eastern),
        ("backtest_has_today vs report_date (konsistent)", test_backtest_has_today_compares_report_date),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) FEHLGESCHLAGEN.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
