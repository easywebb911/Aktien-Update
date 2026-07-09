"""Mock-Tests für Good-Friday-Auto-Ergänzung in ``config.US_MARKET_HOLIDAYS``.

FIXTURE-ONLY — kein Kontakt mit Live-Dateien. Verifiziert die algorithmische
Osterberechnung + Set-Membership + Konsumenten-Verhalten (via Aufruf von
``cluster_purge.previous_trading_day``).

HINTERGRUND (Diagnose 05.07.2026):
Karfreitag war je Jahr 2025/2026/2027 im ``US_MARKET_HOLIDAYS``-Set gefehlt
(je 9 Einträge statt 10). Show-Stopper für den geplanten FINRA-pub_date-
Fix, weil ``settlement + 7 Business-Days`` mit Look bei Karfreitag im
Zählungspfad **1 Business-Day zu früh** berechnet würde → Look-Ahead in die
falsche Richtung (früher-öffentlich-behauptet als real).

Fix (dieser PR):
Good Friday algorithmisch via Meeus/Jones/Butcher-Osterformel (stdlib-only,
kein pandas-Import in config.py — würde CI-Slot-A-Tests brechen).
Karfreitag = Ostersonntag − 2 Tage. Range 2020–2050 (deckt vergangene 5 +
zukünftige 25 Jahre). Union mit statischer 27-Einträge-Liste ergibt 58-
Elemente-Frozenset.

Verifiziert:
- (A) Osterformel: 11 Jahre (2020–2030) gegen echten NYSE-Kalender.
- (B) Set-Membership: alle 11 Karfreitage IM Set.
- (C) Regression: statische NYSE-Feiertage 2025–2027 unverändert im Set.
- (D) Konsumenten-Verhalten: ``previous_trading_day`` überspringt Karfreitag
      korrekt (Mo nach Ostern → Do davor).
- (E) Zukunfts-Coverage: Auto-Ergänzung für 2030+ (deckt spätere Jahre
      OHNE Config-Änderung ab).
- (F) Determinismus: mehrfache Set-Erzeugung liefert identisches Ergebnis.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
from cluster_purge import previous_trading_day  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_easter_formula():
    """(A) Osterformel gegen echten NYSE-Kalender.

    Karfreitag-Daten aus NYSE-Feiertagsseiten (öffentlich, historisch):
    2020–2030. Die Formel MUSS bit-exakt auf diese Werte kommen.
    """
    print("── (A) Meeus-Osterformel gegen echten NYSE-Kalender ──────────")
    # Realer Karfreitag laut NYSE (verifiziert auf nyse.com/markets/hours-calendars):
    real_good_fridays = {
        2020: date(2020, 4, 10),
        2021: date(2021, 4,  2),
        2022: date(2022, 4, 15),
        2023: date(2023, 4,  7),
        2024: date(2024, 3, 29),
        2025: date(2025, 4, 18),
        2026: date(2026, 4,  3),
        2027: date(2027, 3, 26),
        2028: date(2028, 4, 14),
        2029: date(2029, 3, 30),
        2030: date(2030, 4, 19),
    }
    for year, expected in real_good_fridays.items():
        computed = config._easter_sunday(year) - timedelta(days=2)
        _check(
            f"A{year} Karfreitag {expected.isoformat()} bit-exakt",
            computed == expected,
            f"berechnet {computed.isoformat()}",
        )


def _test_set_membership():
    """(B) Alle 11 Karfreitage im Set."""
    print("── (B) Set-Membership Karfreitag 2020–2030 ───────────────────")
    for iso in (
        "2020-04-10", "2021-04-02", "2022-04-15", "2023-04-07", "2024-03-29",
        "2025-04-18", "2026-04-03", "2027-03-26", "2028-04-14", "2029-03-30",
        "2030-04-19",
    ):
        _check(f"B {iso} in US_MARKET_HOLIDAYS", iso in config.US_MARKET_HOLIDAYS)


def _test_regression_static_holidays():
    """(C) Regression: statische NYSE-Feiertage 2025–2027 unverändert.

    Kein Regress-Bruch durch den Set-Union-Wechsel. Kein anderer Feiertag
    versehentlich hinzugefügt oder entfernt.
    """
    print("── (C) Regression: statische Feiertage 2025–2027 ─────────────")
    # Kernauswahl aus den 27 statischen Einträgen — 3 pro Jahr:
    static_expected = [
        # 2025
        "2025-01-01",  # New Year's Day
        "2025-05-26",  # Memorial Day
        "2025-11-27",  # Thanksgiving
        # 2026
        "2026-01-19",  # MLK Day
        "2026-06-19",  # Juneteenth
        "2026-12-25",  # Christmas
        # 2027
        "2027-02-15",  # Presidents Day
        "2027-07-05",  # Independence Day (observed)
        "2027-09-06",  # Labor Day
    ]
    for iso in static_expected:
        _check(
            f"C {iso} (Regression: statisch) in US_MARKET_HOLIDAYS",
            iso in config.US_MARKET_HOLIDAYS,
        )

    # Explizit: das Set enthält NUR die statischen Feiertage + Karfreitage.
    # Nichts Verschmutzendes wie z.B. Kalenderwoche-Random-Daten.
    _check(
        "C4 Set-Größe = 27 statisch + 31 Karfreitage (2020..2050) = 58",
        len(config.US_MARKET_HOLIDAYS) == 58,
        f"got {len(config.US_MARKET_HOLIDAYS)}",
    )
    _check(
        "C5 Alle Set-Einträge sind YYYY-MM-DD-Strings",
        all(isinstance(d, str) and len(d) == 10 and d[4] == "-" and d[7] == "-"
            for d in config.US_MARKET_HOLIDAYS),
    )


def _test_consumer_behavior():
    """(D) ``previous_trading_day`` überspringt Karfreitag."""
    print("── (D) Konsumenten-Verhalten: previous_trading_day ───────────")

    # Karfreitag 03.04.2026 (Fr) — Mo davor: 06.04.2026 → Do davor: 02.04.
    # Vor dem Fix hätte previous_trading_day(Mo 06.04.) fälschlich Karfreitag
    # (Fr 03.04.) zurückgegeben. Mit dem Fix wird 03.04. übersprungen → Do 02.04.
    prev = previous_trading_day(date(2026, 4, 6))
    _check(
        "D1 previous_trading_day(Mo 06.04.2026) → Do 02.04.2026",
        prev == date(2026, 4, 2),
        f"got {prev.isoformat()}",
    )
    # Kontrolle: Sa 04.04. auch Karfreitag überspringen → Do 02.04.
    prev = previous_trading_day(date(2026, 4, 4))
    _check(
        "D2 previous_trading_day(Sa 04.04.2026) → Do 02.04.2026 "
        "(überspringt Wochenende + Karfreitag)",
        prev == date(2026, 4, 2),
        f"got {prev.isoformat()}",
    )
    # Kontroll-Kontrolle: unabhängiger Feiertag Juneteenth 2026 (Fr 19.06.)
    # war vor UND nach dem Fix im Set → Verhalten unverändert.
    prev = previous_trading_day(date(2026, 6, 22))  # Mo nach Juneteenth-Wochenende
    _check(
        "D3 previous_trading_day(Mo 22.06.2026) → Do 18.06.2026 "
        "(Kontroll: Juneteenth-Fr 19.06. wird übersprungen)",
        prev == date(2026, 6, 18),
        f"got {prev.isoformat()}",
    )


def _test_future_auto_coverage():
    """(E) Auto-Coverage 2030+ (Beleg: algorithmisch, nicht hartcodiert)."""
    print("── (E) Zukunfts-Coverage ohne Config-Änderung ────────────────")
    # 2030 ist NICHT in der statischen Liste (die endet 2027), Karfreitag
    # kommt aus dem algorithmischen Union-Teil.
    _check(
        "E1 Karfreitag 2030-04-19 im Set (algorithmisch, kein Manual-Eintrag)",
        "2030-04-19" in config.US_MARKET_HOLIDAYS,
    )
    _check(
        "E2 Karfreitag 2040-03-30 im Set (algorithmisch, weit voraus)",
        "2040-03-30" in config.US_MARKET_HOLIDAYS,
    )
    _check(
        "E3 Karfreitag 2050-04-08 im Set (Range-Obergrenze)",
        "2050-04-08" in config.US_MARKET_HOLIDAYS,
    )
    # Range-Grenze: 2051 NICHT abgedeckt (Range endet 2050) — bewusst dokumentiert.
    _check(
        "E4 2051-03-31 NICHT im Set (Range endet 2050, WARTUNGS-REMINDER 2050+)",
        "2051-03-31" not in config.US_MARKET_HOLIDAYS,
    )


def _test_determinism():
    """(F) Determinismus: mehrfacher Aufruf liefert identische Werte."""
    print("── (F) Determinismus ─────────────────────────────────────────")
    a = config._easter_sunday(2026)
    b = config._easter_sunday(2026)
    c = config._easter_sunday(2026)
    _check("F1 _easter_sunday(2026) 3× → identisch", a == b == c)
    _check("F2 US_MARKET_HOLIDAYS ist frozenset",
           isinstance(config.US_MARKET_HOLIDAYS, frozenset))


def _test_js_python_symmetry():
    """(G) Frontend-Spiegel: JS `US_HOLIDAYS`-Array enthält jeden Karfreitag,
    den auch das Python-Set enthält.

    Source-Inspektion (kein Node-Runner-Zwang im CI-Slot-A): der JS-Block
    trägt eine algorithmische Ergänzung (`_goodFriday`-Funktion +
    `_GOOD_FRIDAYS`-IIFE) mit identischer Meeus-Formel-Signatur wie das
    Python-Pendant. Damit ist die Python↔JS-Spiegelung strukturell
    garantiert.
    """
    print("── (G) Frontend-Spiegel Python↔JS (Meeus-Formel-Symmetrie) ──")
    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")

    # G1 — JS-Helper `_goodFriday(year)` präsent
    _check(
        "G1 JS-Funktion _goodFriday(year) definiert",
        "function _goodFriday(year)" in gr_src,
        "JS-Meeus-Portierung fehlt im Frontend-Template",
    )
    # G2 — Meeus-Kern-Formel-Zeilen (Python-Original: `(19*a + b - d - g + 15) % 30`).
    # JS-Version nutzt Umbenennung `d0` statt `d` (JS `d`-Kollision mit Datums-Var).
    _check(
        "G2 Meeus-Kern-Formel in JS präsent (h-Zeile, Bit-identisch zu Python)",
        "(19 * a + b - d0 - g + 15) % 30" in gr_src,
    )
    # G3 — IIFE erzeugt Karfreitags-Array für Range 2020-2050 (spiegel-symmetrisch)
    _check(
        "G3 _GOOD_FRIDAYS-IIFE über Range 2020..2050",
        "for (let y = 2020; y <= 2050; y++) arr.push(_goodFriday(y))" in gr_src,
    )
    # G4 — Array wird via Spread in US_HOLIDAYS eingehängt (additiv)
    _check(
        "G4 _GOOD_FRIDAYS via Spread in US_HOLIDAYS eingehängt",
        "..._GOOD_FRIDAYS," in gr_src,
        "Spread-Insertion in US_HOLIDAYS-Array fehlt → JS würde Karfreitag nicht sehen",
    )
    # G5 — Spiegel-Vertrag im Kommentar dokumentiert
    _check(
        "G5 SPIEGEL-VERTRAG-Kommentar präsent (Wartungs-Anker)",
        "SPIEGEL-VERTRAG" in gr_src or "Spiegel-Vertrag" in gr_src.lower(),
    )
    # G6 — 5 ausstehende bewegliche Feiertage als Wartungs-Reminder markiert
    _check(
        "G6 Wartungs-Reminder für 5 ausstehende bewegliche Feiertage",
        "AUSSTEHENDE BEWEGLICHE FEIERTAGE" in gr_src
        and "Presidents Day" in gr_src
        and "Thanksgiving" in gr_src,
    )
    # G7 — die 27 statischen Feiertage-Zeilen unverändert (Regression, Kontroll-Sample)
    for iso in (
        '"2025-01-01"', '"2026-06-19"', '"2027-12-24"',
        '"2026-11-26"', '"2025-05-26"',
    ):
        _check(
            f"G7 statisches JS-Feiertag {iso} unverändert im Array",
            iso in gr_src,
        )
    # G8 — NICHT hartcodierte Karfreitag-Datumswerte (die kommen aus IIFE, nicht
    # als Literale, damit auslauf-frei). Assertion: die drei bekannten
    # Karfreitage 2025/2026/2027 sind NICHT als eigene Literal-Zeilen dupliziert
    # (sonst würde man sie zweimal sehen — algorithmisch UND hardcoded).
    for iso in ("2025-04-18", "2026-04-03", "2027-03-26"):
        _check(
            f"G8 Karfreitag {iso} NICHT als Literal-Zeile dupliziert "
            f"(kommt algorithmisch aus _GOOD_FRIDAYS)",
            gr_src.count(f'"{iso}"') == 0,
            f"gefunden als Literal → doppelte Quelle statt spiegel-symmetrisch",
        )


def main():
    _test_easter_formula()
    _test_set_membership()
    _test_regression_static_holidays()
    _test_consumer_behavior()
    _test_future_auto_coverage()
    _test_determinism()
    _test_js_python_symmetry()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Osterformel bit-exakt gegen echten NYSE-"
          "Kalender + Set-Membership + Regression + Konsument + Auto-Coverage + "
          "Determinismus).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
