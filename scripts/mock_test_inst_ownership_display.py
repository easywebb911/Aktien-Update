"""Mock-Tests für den Institutional-Ownership-Key-Fix (07.08.2026).

Probe #510 belegte: die verdrahteten .info-Keys
(institutionHeldPercentOutstanding / institutionsPercentHeld) existieren im
yfinance-.info-Dict NICHT (<KEY-FEHLT> bei 33/33 Tickern) → die Karten-Zeile
war seit jeher stumm (Render unterdrückt None). Fix: beide Lese-Stellen lesen
den Standard-Key heldPercentInstitutions (ein BRUCH, z.B. 0.659 = 65,9 %).

Diese Tests verfolgen einen bekannten Wert durch den ECHTEN Render-Pfad bis
zum Anzeige-String (Skalierungs-Falle Punkt 2) und sichern:
  1  0.659 → "65.9%" (Server-Karte ×100, keine ×100-/×10000-Fehler).
  2  >100 % (1.18 → "118.7%") wird NICHT gedeckelt, Layout/Farbe brechen nicht.
  3  None → Zeile bleibt stumm (unverändertes Verhalten).
  4  Read-Sites: heldPercentInstitutions, KEINE toten Keys als Fallback.
  5  JS-Watchlist-Drawer: ×100 + null-Guard (fmtPct erwartet Prozent-Skala,
     analog ATM IV) — sonst zeigte der Drawer "0.7%" statt "65.9%".

Reuse der validierten Golden-Test-Fixture + Stubs (kein Duplikat).
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Import zieht _install_stubs() + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import _fixture_stock, gr  # noqa: E402

GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

# _card liest ein paar Modul-Globals; defensiv setzen (analog Golden-Test).
gr._SCORE_CONFIDENCE = getattr(gr, "_SCORE_CONFIDENCE", {}) or {}
gr._FX_USD_EUR = getattr(gr, "_FX_USD_EUR", 0.92) or 0.92


def _card_html(inst, *, sec_13f: str = "") -> str:
    """Rendert eine echte Karte mit gesetztem inst_ownership über den
    Produktions-Renderer gr._card — der ganze Pfad bis zum HTML-String."""
    s = _fixture_stock("TSTX", score=80.0, price=5.0, change=2.0)
    s["inst_ownership"] = inst
    s["sec_13f_note"] = sec_13f      # leer → saubere None-Unterdrückung testbar
    return gr._card(0, s)


# ── 1. Skala end-to-end: 0.659 → "65.9%" ──────────────────────────────────────

def test_01_fraction_to_display_string() -> None:
    html = _card_html(0.659)
    assert "65.9%" in html, "0.659 muss als '65.9%' erscheinen (×100 im Server-Render)"
    # Gegenproben gegen die zwei ×100-Fehler-Richtungen:
    assert "0.7%" not in html, "×100 FEHLT (0.659 roh als '0.7%') — Skalierungs-Falle!"
    assert "6590" not in html, "doppeltes ×100 (0.659 → 6590%) — Skalierungs-Falle!"
    assert "Institutioneller Anteil" in html, "Zeile muss jetzt erscheinen (war stumm)"


# ── 2. >100 % nicht deckeln ────────────────────────────────────────────────────

def test_02_over_100_not_clamped() -> None:
    html = _card_html(1.187)   # HTZ 118,7 % — real bei stark geshorteten Titeln
    assert "118.7%" in html, "1.187 muss roh als '118.7%' erscheinen (kein Clamp)"
    assert "100.0%" not in html, "Wert wurde auf 100 % gedeckelt — verboten"
    assert "#22c55e" in html, "≥60 % → grün (#22c55e); Farb-Logik bricht bei >100 % nicht"


def test_02b_color_thresholds() -> None:
    # 60/30-Schwellen (NUR geprüft, nicht geändert — Farb-Semantik-Meldung im PR)
    assert "#22c55e" in _card_html(0.72),  "72 % → grün (≥60)"
    assert "#f59e0b" in _card_html(0.45),  "45 % → gelb (≥30, <60)"
    assert "#ef4444" in _card_html(0.12),  "12 % → rot (<30)"


# ── 3. None bleibt stumm ───────────────────────────────────────────────────────

def test_03_none_suppressed() -> None:
    html = _card_html(None, sec_13f="")   # ohne 13F-Note → Zeile ganz weg
    assert "Institutioneller Anteil" not in html, \
        "None ohne 13F-Note → Zeile muss unterdrückt bleiben (unverändert)"


# ── 4. Read-Sites: richtiger Key, keine toten Fallbacks ───────────────────────

def test_04_read_sites_use_standard_key() -> None:
    # beide Lese-Stellen lesen heldPercentInstitutions
    assert GR_SRC.count('info.get("heldPercentInstitutions")') >= 2, \
        "beide Read-Sites müssen heldPercentInstitutions lesen"
    # die toten Keys dürfen NICHT mehr als .info-Read auftauchen (Kommentar ok)
    assert 'info.get("institutionHeldPercentOutstanding")' not in GR_SRC, \
        "toter Key institutionHeldPercentOutstanding noch als Read vorhanden"
    assert 'info.get("institutionsPercentHeld")' not in GR_SRC, \
        "toter Key institutionsPercentHeld noch als Read vorhanden"


# ── 5. JS-Drawer: ×100 + null-Guard (Skalierungs-Falle im Client-Pfad) ────────

def test_05_js_drawer_scales_and_guards() -> None:
    # Die Watchlist-Drawer-Zeile muss d.inst_ownership * 100 (fmtPct erwartet
    # Prozent-Skala, analog ATM IV) UND einen null-Guard tragen.
    needle = "Inst. Beteiligung"
    idx = GR_SRC.find(needle)
    assert idx != -1, "Drawer-Zeile nicht gefunden"
    frag = GR_SRC[idx:idx + 160]
    assert "d.inst_ownership * 100" in frag, \
        "JS-Drawer OHNE ×100 → zeigte '0.7%' statt '65.9%' (Skalierungs-Falle)"
    assert "d.inst_ownership != null" in frag, \
        "JS-Drawer OHNE null-Guard → 'null*100'=0 → '0.0%' statt '—'"


def main() -> int:
    tests = [
        ("01 Skala 0.659 → '65.9%'",            test_01_fraction_to_display_string),
        ("02 >100 % nicht gedeckelt",           test_02_over_100_not_clamped),
        ("02b Farb-Schwellen 60/30",            test_02b_color_thresholds),
        ("03 None bleibt stumm",                test_03_none_suppressed),
        ("04 Read-Sites: Standard-Key",         test_04_read_sites_use_standard_key),
        ("05 JS-Drawer ×100 + null-Guard",      test_05_js_drawer_scales_and_guards),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
