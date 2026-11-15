#!/usr/bin/env python3
"""Mock-Test: Entry-Shadow von der Karte entfernt (Easy-Entscheid 16.11.2026).

Kein Netz. Prüft: (1) Kartenzeile, Füll-Skript und CSS sind weg; (2) Methodik-
Panel trägt den neuen Satz; (3) die Sammlung bleibt — der Backtest-Eintrag
enthält entry_score / entry_components / entry_n_components unverändert
(Fixture-Werte gepinnt); (4) v1 == v2; (5) open_item-Entwurf vorhanden.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "golden_harness_es", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr
import backtest_history as bh  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
head = (ROOT / "templates" / "head.jinja").read_text(encoding="utf-8")

check("01 Platzhalter cockpit-entry-shadow nicht mehr in generate_report.py",
      "cockpit-entry-shadow" not in src)
check("02 Füll-Skript _fillEntryShadow / Preload entfernt",
      "_fillEntryShadow" not in src and "_preloadBtForEntryShadow" not in src
      and "_esDmyKey" not in src)
check("03 CSS .cockpit-entry-shadow entfernt", "cockpit-entry-shadow" not in head)
_flat = " ".join(src.split())
check("04 Methodik-Satz vorhanden",
      "<strong>Entry-Shadow:</strong> wird im Hintergrund weiter gesammelt, steht "
      "nicht mehr auf der Karte (Prüfung 16.11.2026: findet häufiger Sprünge, aber "
      "keine bessere Rendite).</li>" in _flat)
check("05 alter Methodik-Eintrag weg", "Entry-Shadow N · M/5 Komp." not in src)

html = golden._render_outer_page()
check("06 gerendertes HTML ohne Kartenzeile",
      "cockpit-entry-shadow" not in html and "data-es-ticker" not in html)
check("07 Backtest-Panel setzt _BT_DATA weiter (anderer Konsument unberührt)",
      "window._BT_DATA = _btData" in src)

s = golden._fixture_stocks()[0]
ext = bh._build_backtest_extension(
    s, pool_position=1, pool_size=10, agent_signals={},
    compute_sub_scores_fn=gr._compute_sub_scores, safe_float_fn=gr._safe_float,
    now_dt=datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc))
check("08 entry_score weiter gesammelt (Fixture-Wert unverändert)",
      ext.get("entry_score") == 100.0, repr(ext.get("entry_score")))
check("09 entry_components weiter gesammelt (unverändert)",
      ext.get("entry_components") == {
          "anomaly_freshness": None, "rvol_buildup_5d": None,
          "score_delta_t1": 100.0, "si_trend_5d": None, "uoa_atm_ratio": None},
      repr(ext.get("entry_components")))
check("10 entry_n_components weiter gesammelt (unverändert)",
      ext.get("entry_n_components") == 1, repr(ext.get("entry_n_components")))

try:
    gr._render_test(golden._fixture_stocks(), golden._FIXED_REPORT_DATE)
    ok = True
except Exception:  # noqa: BLE001
    ok = False
check("11 v1 == v2 (_render_test)", ok)

items = json.loads((ROOT / "open_items.json").read_text(encoding="utf-8"))["items"]
it = next((i for i in items if i.get("id") == "hypothese-entwurf-kombination"), None)
check("12 open_item hypothese-entwurf-kombination offen",
      it is not None and it.get("status") == "offen"
      and "Hoher Entry-Shadow (oder geringe institutionelle Beteiligung) UND "
          "Treffer-Score in der oberen Tageshälfte: mehr Sprünge bei positiver "
          "Richtung." in it.get("description", ""))

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle 12 Checks grün.")
