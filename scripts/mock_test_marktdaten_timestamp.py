"""Mock-Tests für die monotone „Marktdaten:"-Header-Zeile (_marktdaten_timestamp).

Anlass (Deploy-Diagnose 28.07.2026): die Zeile mischte den ET-Handelstag
(report_date, %d.%m.%Y in America/New_York) mit der Berlin-Render-UHRZEIT ohne
Datum. Ein Postclose, der nach Berlin-Mitternacht rendert (22:28 UTC = 00:30
Berlin), trug den Vortags-Handelstag + 00:30 → las sich ÄLTER als der frühere
Premarket (18:01), obwohl chronologisch später. Das löste eine echte
Fehldiagnose aus. Fix: Datum+Uhrzeit aus DEMSELBEN Berlin-Wallclock; Handelstag
nur explizit bei Abweichung.

Netzwerkfrei — der Helper wird per Source-Extraktion aus generate_report.py
gezogen und in isoliertem Namespace exec'd (kein yfinance-Import).

Fälle:
  (A) Premarket (Render-Datum == Handelstag)          → knapp, byte-identisch
  (B) Postclose VOR Mitternacht (Render == Handelstag) → knapp
  (C) Postclose NACH Mitternacht (Render ≠ Handelstag) → divergent, beide sichtbar
  (D) Monotonie: aufeinanderfolgende Läufe nie rückwärts
  (E) „00:30"-Fall rendert nachweisbar ANDERS als die alte Formel
  (F) DST: Sommer (UTC+2) und Winter (UTC+1) korrekt
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_BERLIN = ZoneInfo("Europe/Berlin")

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


def _load_helper():
    """Extrahiere _marktdaten_timestamp (pure, nur strftime + f-Strings)."""
    m = re.search(r"^def _marktdaten_timestamp\(.*?(?=^def |^class )",
                  GR, re.MULTILINE | re.DOTALL)
    assert m, "_marktdaten_timestamp nicht gefunden"
    ns: dict = {}
    exec(m.group(0), ns)
    return ns["_marktdaten_timestamp"]


_ts = _load_helper()


def _berlin(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=_BERLIN)


def _old_formula(report_date, berlin_now):
    """Die ALTE Zeile: ET-Handelstag + Berlin-Uhrzeit ohne Datum (der Bug)."""
    return f"Marktdaten: {report_date}, {berlin_now.strftime('%H:%M Uhr')}"


def _primary_dt(line, year):
    """Parse die PRIMÄRE (Datum, Uhrzeit) aus der Zeile — vor '(Handelstag'."""
    core = line.split(" (Handelstag")[0]
    m = re.search(r"Marktdaten: (\d{2})\.(\d{2})\.(\d{4}), (\d{2}):(\d{2})", core)
    assert m, f"Format unerwartet: {line!r}"
    dd, mm, yy, hh, mi = map(int, m.groups())
    return datetime(yy, mm, dd, hh, mi)


# ── (A) Premarket: Render-Datum == Handelstag → knapp, byte-identisch ─────────
def test_premarket_knapp():
    bn = _berlin(2026, 7, 27, 8, 17)          # 08:17 Berlin
    rd = "27.07.2026"                          # ET-Handelstag == Berlin-Datum
    out = _ts(rd, bn)
    _check("A1 Premarket knappe Form", out == "Marktdaten: 27.07.2026, 08:17 Uhr", out)
    _check("A2 byte-identisch zur alten Formel (kein Abweichungsfall)",
           out == _old_formula(rd, bn))
    _check("A3 kein redundanter Handelstag-Zusatz", "(Handelstag" not in out)


# ── (B) Postclose VOR Mitternacht: 23:17 Berlin, gleicher Tag → knapp ─────────
def test_postclose_vor_mitternacht():
    bn = _berlin(2026, 7, 27, 23, 17)         # 21:17 UTC = 23:17 Berlin, Datum 27.
    rd = "27.07.2026"
    out = _ts(rd, bn)
    _check("B1 Postclose vor Mitternacht knapp", out == "Marktdaten: 27.07.2026, 23:17 Uhr", out)
    _check("B2 kein Handelstag-Zusatz", "(Handelstag" not in out)


# ── (C) Postclose NACH Mitternacht: 00:30 Berlin (28.), Handelstag 27. ────────
def test_postclose_nach_mitternacht():
    bn = _berlin(2026, 7, 28, 0, 30)          # 22:30 UTC = 00:30 Berlin (28.)
    rd = "27.07.2026"                          # ET noch Montag 27.
    out = _ts(rd, bn)
    _check("C1 Render-Datum primär = 28.07.", out.startswith("Marktdaten: 28.07.2026, 00:30 Uhr"), out)
    _check("C2 Handelstag explizit ausgewiesen", "(Handelstag 27.07.2026)" in out)
    _check("C3 beide Größen unterscheidbar",
           "28.07.2026" in out and "27.07.2026" in out)


# ── (D) Monotonie: Premarket → Postclose-nach-Mitternacht nie rückwärts ───────
def test_monotonie():
    seq = [
        ("27.07.2026", _berlin(2026, 7, 27, 8, 17)),    # Premarket
        ("27.07.2026", _berlin(2026, 7, 27, 18, 1)),    # Dispatch premarket
        ("27.07.2026", _berlin(2026, 7, 28, 0, 30)),    # Postclose NACH Mitternacht
        ("28.07.2026", _berlin(2026, 7, 28, 8, 17)),    # nächster Premarket
    ]
    prev = None
    ok = True
    for rd, bn in seq:
        p = _primary_dt(_ts(rd, bn), bn.year)
        if prev is not None and p < prev:
            ok = False
        prev = p
    _check("D1 angezeigte Primär-Zeit wächst nie rückwärts (neu)", ok)
    # Gegenprobe: die ALTE Formel LIEF rückwärts (00:30 < 18:01 bei gleichem Datum)
    old_seq = [_primary_dt(_old_formula(rd, bn), bn.year) for rd, bn in seq]
    _check("D2 alte Formel LIEF rückwärts (Bug reproduziert)",
           old_seq[2] < old_seq[1], (old_seq[1], old_seq[2]))


# ── (E) Der 00:30-Fall rendert nachweisbar ANDERS als vorher ──────────────────
def test_00_30_differs_from_old():
    bn = _berlin(2026, 7, 28, 0, 30)
    rd = "27.07.2026"
    _check("E1 neu ≠ alt im 00:30-Fall", _ts(rd, bn) != _old_formula(rd, bn))
    _check("E2 alte Formel zeigte irreführend '27.07.2026, 00:30'",
           _old_formula(rd, bn) == "Marktdaten: 27.07.2026, 00:30 Uhr")


# ── (F) DST: Sommer (UTC+2) und Winter (UTC+1) — via echte UTC→Berlin-Konvert. ─
def test_dst():
    # Sommer: 2026-07-27 22:30 UTC → 00:30 Berlin (+2)
    summer = datetime.fromtimestamp(
        datetime(2026, 7, 27, 22, 30, tzinfo=ZoneInfo("UTC")).timestamp(), _BERLIN)
    _check("F1 Sommer +2: 22:30 UTC → 00:30 Berlin (28.)",
           summer.strftime("%d.%m.%Y %H:%M") == "28.07.2026 00:30", summer)
    out_s = _ts("27.07.2026", summer)
    _check("F2 Sommer-Postclose divergent korrekt", "(Handelstag 27.07.2026)" in out_s)
    # Winter: 2026-01-05 23:15 UTC → 00:15 Berlin (+1)
    winter = datetime.fromtimestamp(
        datetime(2026, 1, 5, 23, 15, tzinfo=ZoneInfo("UTC")).timestamp(), _BERLIN)
    _check("F3 Winter +1: 23:15 UTC → 00:15 Berlin (06.)",
           winter.strftime("%d.%m.%Y %H:%M") == "06.01.2026 00:15", winter)
    out_w = _ts("05.01.2026", winter)
    _check("F4 Winter-Postclose divergent korrekt",
           out_w.startswith("Marktdaten: 06.01.2026, 00:15 Uhr")
           and "(Handelstag 05.01.2026)" in out_w, out_w)


def main():
    print("── (A) Premarket knapp ───────────────────────────────────────")
    test_premarket_knapp()
    print("── (B) Postclose vor Mitternacht ─────────────────────────────")
    test_postclose_vor_mitternacht()
    print("── (C) Postclose nach Mitternacht (heute Nacht) ──────────────")
    test_postclose_nach_mitternacht()
    print("── (D) Monotonie ─────────────────────────────────────────────")
    test_monotonie()
    print("── (E) 00:30 rendert anders als vorher ───────────────────────")
    test_00_30_differs_from_old()
    print("── (F) DST Sommer/Winter ─────────────────────────────────────")
    test_dst()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Marktdaten-Zeile: knapp/divergent, Monotonie, "
          "DST, 00:30-Fall nachweisbar geheilt).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
