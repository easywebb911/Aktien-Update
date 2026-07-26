"""Mock-Tests für den Stale-Preis-Marker der Positions-Karte (Anzeige-Folge #483).

Reine Anzeige-Logik: der persistierte Daily-Run-current_price wird bei einem
Fetch-Fehler PRESERVED (price_asof bleibt alt). Die Karte markiert dann den
gezeigten Preis gedimmt + „Kurs vom <Datum>" (Berlin). Frisch/null → kein
Marker (null optischer Unterschied).

(A) Source-Inspektion: Helper + Wiring + CSS vorhanden, price_asof nur GELESEN.
(B) Logik-Replik von `_positionStaleAsof(ticker, shownPrice)`:
    - frisch (asof ≈ runTs)           → kein Marker
    - preserved (asof << runTs)        → Marker mit asof
    - null/fehlend (Alt-State)         → kein Marker (null-tolerant)
    - Live-Overlay (shownPrice≠stored) → kein Marker (kein Fehlalarm)
    - Grenzfall gleicher Tag/Run       → kein Marker
    - Zeitzone: Vergleich UTC, Anzeige Berlin
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
HEAD = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


# ── (A) Source-Inspektion ────────────────────────────────────────────────────

def test_source_wiring():
    _check("A1 Helper _positionStaleAsof definiert",
           "function _positionStaleAsof(ticker, shownPrice)" in GR)
    _check("A2 Helper _fmtStaleDate definiert (Berlin)",
           "function _fmtStaleDate(iso)" in GR and "Europe/Berlin" in GR)
    _check("A3 Toleranz-Konstante vorhanden",
           "_POS_PRICE_STALE_TOL_MS" in GR)
    _check("A4 P&L-Span bekommt Stale-Klasse konditional",
           "pos-pnl-live${{_pnlStaleCls}}" in GR)
    _check("A5 Caption-Zeile bei stale gerendert",
           'class="pos-stale-note"' in GR and "Kurs vom" in GR)
    _check("A6 Live-Patch entfernt Stale-Marker (kein Fresh-Dimming)",
           "el.classList.remove('pos-pnl-stale')" in GR
           and ".pos-stale-note').forEach(el => el.remove())" in GR)
    _check("A7 CSS-Klassen in head.jinja",
           ".pos-pnl-stale{" in HEAD and ".pos-stale-note{" in HEAD)
    # price_asof wird NUR gelesen (ph2.price_asof), nie geschrieben im JS.
    _check("A8 price_asof nur gelesen, nie geschrieben (JS)",
           "ph2.price_asof" in GR
           and not re.search(r"price_asof\s*=", GR.split("function buildPositionPanel")[0][-4000:]))
    # Vergleich in UTC (Date.parse auf …Z-Strings), Anzeige Berlin.
    _check("A9 Vergleich UTC (Date.parse), Anzeige Berlin (timeZone)",
           "Date.parse(ph2.price_asof)" in GR and "timeZone: 'Europe/Berlin'" in GR)


# ── (B) Logik-Replik von _positionStaleAsof ──────────────────────────────────

_TOL_MS = 2 * 3600 * 1000


def _stale_asof(price_asof, run_ts, stored, shown):
    """1:1-Replik der JS-Entscheidung: gibt price_asof (stale) oder None."""
    if not price_asof or not run_ts:
        return None
    try:
        asof_ms = datetime.fromisoformat(price_asof.replace("Z", "+00:00")).timestamp() * 1000
        run_ms = datetime.fromisoformat(run_ts.replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return None
    if run_ms - asof_ms <= _TOL_MS:
        return None
    if stored is not None and shown is not None and abs(float(shown) - stored) > 0.005:
        return None
    return price_asof


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_RUN = datetime(2026, 7, 25, 10, 43, 49, tzinfo=timezone.utc)   # Samstag-Run (Diagnose)
_FRI = datetime(2026, 7, 24, 22, 30, 0, tzinfo=timezone.utc)    # letzter guter Fetch (Fr postclose)


def test_fresh_no_marker():
    # asof 1s vor dem Run (gleicher Run) → frisch → kein Marker
    asof = _iso(_RUN - timedelta(seconds=1))
    _check("B1 frisch (asof≈runTs) → kein Marker",
           _stale_asof(asof, _iso(_RUN), 3.45, 3.45) is None)


def test_preserved_marker():
    # Sa-Klobber-Fall: Fr-Preis preserved, Run ist Sa → Marker
    asof = _iso(_FRI)
    got = _stale_asof(asof, _iso(_RUN), 3.45, 3.45)
    _check("B2 preserved (Fr-asof, Sa-run) → Marker mit asof", got == asof, got)


def test_null_price_asof_no_marker():
    _check("B3 price_asof None (Alt-State) → kein Marker",
           _stale_asof(None, _iso(_RUN), 3.45, 3.45) is None)
    _check("B4 run_ts None → kein Marker (null-tolerant)",
           _stale_asof(_iso(_FRI), None, 3.45, 3.45) is None)


def test_live_overlay_guard():
    # gezeigter Preis ≠ stored (Live-Quote-Overlay) → KEIN Marker (kein Fehlalarm)
    asof = _iso(_FRI)
    _check("B5 Live-Overlay (shown≠stored) → kein Marker",
           _stale_asof(asof, _iso(_RUN), 3.45, 3.90) is None)
    # shown == stored (innerhalb Epsilon) → Marker bleibt
    _check("B6 shown≈stored (Epsilon) → Marker",
           _stale_asof(asof, _iso(_RUN), 3.45, 3.451) == asof)


def test_grenzfall_same_run():
    # asof leicht NACH runTs (Positions-Fetch später im Run) → delta negativ → frisch
    asof = _iso(_RUN + timedelta(minutes=3))
    _check("B7 Grenzfall asof>runTs (später im Run) → kein Marker",
           _stale_asof(asof, _iso(_RUN), 3.45, 3.45) is None)
    # exakt an der Toleranz-Grenze (2h) → noch kein Marker (<=)
    asof_edge = _iso(_RUN - timedelta(hours=2))
    _check("B8 exakt 2h alt (Toleranzgrenze) → kein Marker",
           _stale_asof(asof_edge, _iso(_RUN), 3.45, 3.45) is None)
    # knapp über 2h → Marker
    asof_over = _iso(_RUN - timedelta(hours=2, minutes=1))
    _check("B9 2h1min alt → Marker",
           _stale_asof(asof_over, _iso(_RUN), 3.45, 3.45) == asof_over)


def test_same_day_preserve():
    # premarket-Fetch (06:17), postclose preserved (21:17) — gleicher Tag, 15h delta
    pm = datetime(2026, 7, 24, 6, 17, 0, tzinfo=timezone.utc)
    pc = datetime(2026, 7, 24, 21, 17, 0, tzinfo=timezone.utc)
    _check("B10 Same-Day-Preserve (15h delta) → Marker (Datum-Vergleich reichte nicht)",
           _stale_asof(_iso(pm), _iso(pc), 3.45, 3.45) == _iso(pm))


def test_timezone_display():
    # Anzeige Berlin: 24.07. 22:30 UTC = 25.07. 00:30 Berlin (Sommerzeit +2).
    # Der Vergleich läuft in UTC (beide Z); nur die Anzeige ist Berlin.
    import zoneinfo
    berlin = datetime(2026, 7, 24, 22, 30, tzinfo=timezone.utc).astimezone(
        zoneinfo.ZoneInfo("Europe/Berlin"))
    _check("B11 Berlin-Anzeige: 22:30 UTC → 25.07. 00:30 (Sommerzeit)",
           berlin.strftime("%d.%m. %H:%M") == "25.07. 00:30", berlin)


def main():
    print("── (A) Source-Wiring ─────────────────────────────────────────")
    test_source_wiring()
    print("── (B) Logik-Replik _positionStaleAsof ───────────────────────")
    test_fresh_no_marker()
    test_preserved_marker()
    test_null_price_asof_no_marker()
    test_live_overlay_guard()
    test_grenzfall_same_run()
    test_same_day_preserve()
    test_timezone_display()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (Stale-Preis-Marker: frisch/preserved/null, "
          "Live-Overlay-Guard, Grenzfall, UTC-vs-Berlin).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
