#!/usr/bin/env python3
"""Mock-Test Anzeige-PR Teil B (Easy-Auftrag 13.11.2026) — rein Anzeige.

1  Institutioneller Anteil: Wert neutral (keine Farbe, keine 60/30-Schwellen),
   Hinweis-Text darunter, v1 und v2 über denselben Helfer, kein Marker im
   Kartenkopf.
2  SCORE_STATUS_LABELS: H-I BLAU mit Easys Text; H-G/H-K „Unklar“ (grau),
   Zahlen im Panel aus eval_results.jsonl (nicht aus Konstanten).
3  Panel-Kopfzeile: Zahl der Tests/Belege aus eval_results.jsonl gezählt
   (Gegenprobe mit eigener Datei), keine feste „4“ mehr.
4  K1-Zeile: explorativ + 1 Fenster gekennzeichnet, kein Status-Punkt.
5  GRÜN bleibt unvergeben (Konfiguration und gerendertes Panel).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "golden_harness", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr
import config  # noqa: E402

SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {str(detail)[:400]}"))
    if not cond:
        _fails.append(name)


def _panel() -> str:
    rows, _ = gr._score_confidence_rows_html({"setup": {"n": 5, "data_tier": "klein"}})
    return rows


def test_inst():
    print("1 Institutioneller Anteil")
    for pct in (0.05, 0.45, 0.95):
        row = gr._inst_row_html({"inst_ownership": pct})
        val = re.search(r"<td><span([^>]*)>[\d.]+%</span>", row)
        check(f"{pct:.0%}: Wert ohne Farbe", val is not None and val.group(1) == "", row)
        check(f"{pct:.0%}: Hinweis-Text", config.INST_OWNERSHIP_HINT in row)
        check(f"{pct:.0%}: keine Ampelfarbe", not any(c in row for c in ("#ef4444", "#f59e0b")), row)
    check("keine 60/30-Schwellen mehr im Quelltext",
          "_inst_pct >= 60" not in SRC and "_inst_pct >= 30" not in SRC)
    check("v1 + v2 nutzen denselben Helfer",
          "_inst_row = _inst_row_html(s)" in SRC and "inst_row = _inst_row_html(s)" in SRC)
    check("ohne Wert → keine Zeile, NaN → keine Zeile",
          gr._inst_row_html({}) == "" and gr._inst_row_html({"inst_ownership": float("nan")}) == "")
    check("Hinweis wörtlich (Easy-Auftrag)",
          config.INST_OWNERSHIP_HINT == "Niedrigere Beteiligung: häufiger +30 % im Hoch (Beleg, "
          "1 Zeitfenster). Rendite im selben Zeitraum nicht besser als null — kein Kaufsignal.")
    stock = dict(golden._fixture_stocks()[0])
    stock["inst_ownership"] = 0.9
    head = gr._card_cockpit_html(0, stock)
    check("kein Inst-Marker im Kartenkopf (gerendert)",
          "Institution" not in head and "inst-hint" not in head and "90.0%" not in head)
    full = gr._card(0, stock)
    check("Wert + Hinweis im Detailbereich der Karte",
          "Institutioneller Anteil</td><td><span>90.0%</span>" in full
          and config.INST_OWNERSHIP_HINT in full)


def test_labels_and_panel():
    print("2–5 Status, Panel, K1, GRÜN")
    L = config.SCORE_STATUS_LABELS
    check("H-I blau + Easys Text",
          L["h_i"]["status_kind"] == "pending"
          and L["h_i"]["status"] == "Beleg (Gipfel), 1 Fenster — Rendite-Test läuft")
    check("H-G/H-K „Unklar“, nicht grün/rot",
          all(L[k]["status"].startswith("Unklar") and L[k]["status_kind"] == "heuristic"
              for k in ("h_g", "h_k")))
    check("eval_ref auf die Stufe-1-Zeilen",
          [L[k]["eval_ref"]["test_id"] for k in ("h_i", "h_g", "h_k")] == ["hi_s1", "hg_s1", "hk_s1"])
    ev = gr._eval_results_index()
    rows = _panel()
    for key, tid in (("H-I", "hi_s1"), ("H-G", "hg_s1"), ("H-K", "hk_s1")):
        num = gr._eval_numbers_text(ev.get(tid))
        check(f"{key}: Zahlen aus eval_results im Panel", num and num.replace("<", "&lt;") in rows, num)
    check("H-I-Zahl stimmt mit eval_results (AUC 0,33, n = 508)",
          "AUC 0,33 [0,25; 0,41]" in rows and "n = 508 (54 Treffer)" in rows)
    n_t = len(ev)
    n_b = sum(1 for r in ev.values() if r.get("verdict") == "Beleg")
    check("Kopfzeile zählt aus eval_results",
          f"{n_t} Bestätigungstests ausgewertet, {n_b} formale Belege" in rows, (n_t, n_b))
    check("keine feste „4 Bestätigungstests“", "4 Bestätigungstests" not in rows or n_t == 4)
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "ev.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in (
            {"test_id": "a", "verdict": "Beleg", "evaluated_at": "2026-12-01T00:00:00Z"},
            {"test_id": "b", "verdict": "Unklar", "evaluated_at": "2026-11-01T00:00:00Z"},
            {"test_id": "c", "verdict": "Unklar"})) + "\n", encoding="utf-8")
        txt = gr._validation_summary_html(gr._eval_results_index(p))
        check("Gegenprobe eigene Datei: 3 Tests, 1 Beleg, Stand 01.12.2026",
              txt.startswith("Stand 01.12.2026: 3 Bestätigungstests ausgewertet, 1 formaler Beleg"), txt)
        check("fehlende Datei → keine Kopfzeile (fail-soft)",
              gr._validation_summary_html(gr._eval_results_index(pathlib.Path(td) / "nix")) == "")
    check("Kopfzeile verspricht keine Rendite", "kein Beleg für eine Rendite" in rows)
    k1 = re.search(r'<li class="sb-explorativ">(.*?)</li>', rows)
    check("K1-Zeile vorhanden, explorativ + 1 Fenster, ohne Status-Punkt",
          k1 is not None and "explorativ, 1 Fenster" in k1.group(1)
          and "conf-status-dot" not in k1.group(1) and "(K1)" in k1.group(1), rows[-600:])
    check("GRÜN unvergeben (Konfiguration)",
          all(v.get("status_kind") != "validated" for v in L.values()))
    check("GRÜN unvergeben (Panel)", "conf-kind-validated" not in rows)
    check("H-I-Zeile blau im Panel",
          re.search(r"Inst-Beteiligung \(H-I\).*?conf-kind-pending", rows) is not None)


def main() -> int:
    for fn in (test_inst, test_labels_and_panel):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle Teil-B-Anzeige-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
