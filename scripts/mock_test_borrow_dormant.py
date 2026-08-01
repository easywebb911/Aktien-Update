"""Mock-Tests für den Dormant-Zustand der Borrow-Quelle (01.08.2026).

Hintergrund: iBorrowDesk tot seit 23.07.2026, Wegwerf-Probe 01.08. fand keine
freie Cost-to-Borrow-Quelle → Borrow bewusst dormant (Muster earningswhispers/
stocktwits): BEIDE Flags aus, Orchestrator bleibt als Einhängepunkt.

Verifiziert:
  1. config: beide Borrow-Flags False (dormant aktiv).
  2. _borrow_dormant() True bei beiden aus, False sobald eine an ist.
  3. dormant → Karten-CTB-Zeile zeigt „keine Daten — Quelle eingestellt".
  4. re-enable (Flag) → CTB-Wert wird wieder gerendert (Wert-/Alt-Record-Pfad
     intakt), _borrow_rate_row_html rendert Rate.
  5. dormant → kein stiller Null-Bonus: Score-Bonus guarded auf `is not None`
     (borrow_rate None → 0), Methodik-Boni-Zeile schaltet auf „inaktiv".
  6. Erosion-CTB-Driver: bei fehlendem aktuellen CTB exkludiert (ctb_av-Gate),
     NICHT als „geprüft und nichts gefunden" gezählt.
  7. Health: Orchestrator-Loop-Gate + Emit-Gate → kein „borrow"-Provider-Record
     wenn beide Flags aus (kein Dauer-10/10-Fail-Warn).
  8. Alt-Records: Backtest speichert cost_to_borrow unverändert (kein Dormant-
     Spezialfall → historische Messwerte bleiben).
"""
from __future__ import annotations

import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GR_TEXT = (ROOT / "generate_report.py").read_text(encoding="utf-8")
BT_TEXT = (ROOT / "backtest_history.py").read_text(encoding="utf-8")


def _extract(name: str) -> str:
    pat = re.compile(rf"^def {name}\(.*?(?=^def |\Z)", re.MULTILINE | re.DOTALL)
    m = pat.search(GR_TEXT)
    assert m, f"{name} nicht gefunden"
    return m.group(0)


def _load_helpers(ibkr: bool, stock: bool):
    """Lade die 3 Borrow-Display-Helper mit injizierten Flag-Werten."""
    ns = {
        "IBKR_BORROW_ENABLED": ibkr,
        "STOCKANALYSIS_BORROW_ENABLED": stock,
        "IBKR_BORROW_LOW": 10.0,
        "IBKR_BORROW_HIGH": 50.0,
    }
    code = (_extract("_borrow_dormant") + "\n"
            + _extract("_borrow_rate_row_html") + "\n"
            + _extract("_ctb_util_rows_html"))
    exec(code, ns)
    return ns


# ── 1. config-Flags ──────────────────────────────────────────────────────────

def test_01_config_flags_dormant() -> None:
    cfg = importlib.import_module("config")
    importlib.reload(cfg)
    assert cfg.IBKR_BORROW_ENABLED is False, "IBKR_BORROW_ENABLED muss False sein"
    assert cfg.STOCKANALYSIS_BORROW_ENABLED is False, \
        "STOCKANALYSIS_BORROW_ENABLED muss False sein"


# ── 2. _borrow_dormant ───────────────────────────────────────────────────────

def test_02_borrow_dormant_predicate() -> None:
    assert _load_helpers(False, False)["_borrow_dormant"]() is True
    assert _load_helpers(True, False)["_borrow_dormant"]() is False
    assert _load_helpers(False, True)["_borrow_dormant"]() is False
    assert _load_helpers(True, True)["_borrow_dormant"]() is False


# ── 3. dormant Anzeige ───────────────────────────────────────────────────────

def test_03_dormant_ctb_row_shows_hint() -> None:
    ns = _load_helpers(False, False)
    out = ns["_ctb_util_rows_html"]({"cost_to_borrow": None, "utilization": None})
    assert "keine Daten" in out and "Quelle" in out and "eingestellt" in out, \
        f"Dormant-Hinweis fehlt: {out!r}"
    assert "%/Jahr" not in out, f"darf keine Wert-Zeile zeigen: {out!r}"
    assert "Utilization" not in out, f"keine leere Utilization-Zeile: {out!r}"


def test_03b_dormant_hint_even_if_stale_value_present() -> None:
    # Selbst wenn (fixture-artig) ein Wert am Dict hängt: dormant zeigt KEINEN
    # potentiell veralteten CTB — die Quelle ist aus.
    ns = _load_helpers(False, False)
    out = ns["_ctb_util_rows_html"]({"cost_to_borrow": 12.0, "utilization": 5.0})
    assert "keine Daten" in out and "12.0" not in out


# ── 4. re-enable → Wert-/Alt-Record-Pfad intakt ──────────────────────────────

def test_04_reenable_renders_value() -> None:
    ns = _load_helpers(True, True)   # eine reicht; hier beide an
    out = ns["_ctb_util_rows_html"]({"cost_to_borrow": 12.0, "utilization": 5.0})
    assert "Cost-to-Borrow" in out and "12.0 %/Jahr" in out, \
        f"Wert-Pfad kaputt: {out!r}"
    assert "keine Daten" not in out


def test_05_reenable_borrow_rate_row() -> None:
    ns = _load_helpers(True, False)
    # Rate vorhanden → Zeile rendert
    out = ns["_borrow_rate_row_html"]({"borrow_rate": 75.0})
    assert "Borrow Rate (IBKR)" in out and "75.0" in out
    # Rate None → leer (kein Doppel-Hinweis; CTB-Zeile trägt ihn)
    assert ns["_borrow_rate_row_html"]({"borrow_rate": None}) == ""


# ── 6. kein stiller Null-Bonus ───────────────────────────────────────────────

def test_06_score_bonus_guards_on_not_none() -> None:
    # Der Borrow-Score-Bonus feuert nur bei borrow_rate is not None → dormant
    # (None) trägt 0 bei, ohne dass eine Schwelle geändert wurde.
    seg = GR_TEXT[GR_TEXT.index('_borrow = s.get("borrow_rate")'):]
    seg = seg[:400]
    assert "if _borrow is not None" in seg, \
        "Borrow-Bonus muss auf `is not None` guarden (None → kein Bonus)"


def test_07_methodology_boni_switches_to_inactive() -> None:
    # Die Methodik-Boni-Zeile darf bei dormant nicht mehr aktive Punkte
    # behaupten, sondern „inaktiv … eingestellt" zeigen.
    assert "_borrow_dormant()" in GR_TEXT
    assert re.search(r"inaktiv[^\"]*Leihkosten-Quelle eingestellt", GR_TEXT), \
        "Methodik-Boni-Zeile schaltet nicht auf inaktiv"


# ── 8. Erosion-CTB-Driver exkludiert statt „nichts gefunden" ─────────────────

def test_08_erosion_ctb_excluded_when_unavailable() -> None:
    # Combo-/Reason-Zählung berücksichtigt ctb nur bei ctb_av (beide Endpunkte
    # vorhanden). Fehlt der aktuelle CTB (dormant) → ctb_av=False → exkludiert,
    # NICHT als 0-Stage „geprüft und nichts gefunden" mitgezählt.
    assert "ctb_stage >= 50 if ctb_av else False" in GR_TEXT
    assert "ctb_stage >= 100 if ctb_av else False" in GR_TEXT
    # _drop_and_stage liefert available=False bei nicht-finitem cur_v
    assert "return None, 0, False" in GR_TEXT


# ── 9. Health: kein borrow-Provider-Record bei dormant ───────────────────────

def test_09_provider_record_suppressed_when_dormant() -> None:
    # (a) Orchestrator-Loop wird komplett übersprungen, wenn BEIDE Flags aus.
    assert "if IBKR_BORROW_ENABLED or STOCKANALYSIS_BORROW_ENABLED:" in GR_TEXT
    # (b) Emit-Gate: borrow-Record nur wenn Calls > 0 (bei Skip = 0 → keine Zeile).
    assert '_b_acct["calls"] > 0' in GR_TEXT
    # zusammen: dormant → 0 Calls → kein Record → kein Dauer-10/10-Fail-Warn.


# ── 10. Alt-Records unverändert ──────────────────────────────────────────────

def test_10_backtest_ctb_unchanged() -> None:
    # Backtest speichert cost_to_borrow ohne Dormant-Spezialfall — historische
    # Records (echte Messwerte von damals) bleiben unangetastet.
    assert '"cost_to_borrow":         s.get("cost_to_borrow"),' in BT_TEXT


def main() -> int:
    tests = [
        ("01 config Flags dormant",            test_01_config_flags_dormant),
        ("02 _borrow_dormant Prädikat",        test_02_borrow_dormant_predicate),
        ("03 dormant CTB-Hinweis",             test_03_dormant_ctb_row_shows_hint),
        ("03b Hinweis trotz stale Wert",       test_03b_dormant_hint_even_if_stale_value_present),
        ("04 re-enable Wert-Pfad",             test_04_reenable_renders_value),
        ("05 re-enable Borrow-Rate-Zeile",     test_05_reenable_borrow_rate_row),
        ("06 Score-Bonus None-Guard",          test_06_score_bonus_guards_on_not_none),
        ("07 Methodik-Boni inaktiv",           test_07_methodology_boni_switches_to_inactive),
        ("08 Erosion-CTB exkludiert",          test_08_erosion_ctb_excluded_when_unavailable),
        ("09 Provider-Record unterdrückt",     test_09_provider_record_suppressed_when_dormant),
        ("10 Alt-Records unverändert",         test_10_backtest_ctb_unchanged),
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
