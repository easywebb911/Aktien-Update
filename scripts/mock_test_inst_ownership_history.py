"""Mock-Tests für inst_ownership_history.json (forward-only Sammlung, 10.08.2026).

Sammelt den aktuellen 13F-Institutional-Ownership (heldPercentInstitutions) +
Insider-Ownership (heldPercentInsiders) pro US-Ticker als forward-only Zeitreihe
in einer SEPARATEN Datei — analog si_position_history. REINE Sammlung: KEIN
Score/Filter/Push/Anzeige/Auswertung.

Verriegelt die harten Invarianten:
  1  ZIEL-MECHANIK: ein echter Wert wandert durch _persist_inst_ownership_history
     in die Datei (Punkt-Struktur {date, inst_ownership, insider_ownership}).
  2  NONE-SEMANTIK (kritisch): fehlender Wert → JSON null, NIEMALS 0. Ein echtes
     gemessenes 0.0 bleibt 0.0 (0 ≠ null). Grep über die geschriebene Datei:
     kein missing-Wert wird 0.
  3  WERTE ROH: 1.187 (118,7 %) landet ungedeckelt/ungerundet.
  4  FORWARD-ONLY: kein Backfill; unveränderter Wert am Folgetag → kein Punkt.
  5  IDEMPOTENZ: derselbe Ticker am selben Datum nie zweimal (Doppel-Lauf).
  6  Zweite Achse insider_ownership wird mitgeschrieben (kein Extra-Fetch:
     Read-Site liest heldPercentInsiders aus demselben .info-Dict).
  7  FAIL-SOFT: ein kaputter Stock bricht die Sammlung nicht ab.
  8  FEATURE-FLAG: ENABLED=False → keine Sammlung.
  9  US-only-Filter.
 10  ISOLATION: inst_ownership/insider_ownership werden NICHT als Score-/Filter-/
     Push-Feature gelesen (Look-Ahead-Guard, Grep über die Berechnungs-Pfade).

Kategorie A: stdlib + jinja2 (Golden-Stub-Reuse), deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Import zieht _install_stubs() + `import generate_report as gr` (Modul-Ebene).
from mock_test_outer_page_golden import gr  # noqa: E402

GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fresh_file():
    d = tempfile.mkdtemp()
    gr.INST_OWNERSHIP_HISTORY_FILE = os.path.join(d, "inst_ownership_history.json")
    return gr.INST_OWNERSHIP_HISTORY_FILE


def _stock(t, inst, insider, market="US"):
    return {"ticker": t, "inst_ownership": inst,
            "insider_ownership": insider, "market": market}


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def main() -> int:
    gr.INST_OWNERSHIP_HISTORY_ENABLED = True

    # ── 1 + 3 + 6: Ziel-Mechanik, Roh-Wert, zweite Achse ──────────────────────
    p = _fresh_file()
    n = gr._persist_inst_ownership_history(
        [_stock("HTZ", 1.187, 0.05), _stock("FTK", 0.42, 0.607)],
        report_date_iso="2026-08-10")
    h = _load(p)
    _check("01 Ziel-Mechanik: Punkte geschrieben (2 Ticker)",
           n == 2 and set(h) == {"HTZ", "FTK"})
    _check("01 Punkt-Struktur {date, inst_ownership, insider_ownership}",
           set(h["HTZ"][0]) == {"date", "inst_ownership", "insider_ownership"}
           and h["HTZ"][0]["date"] == "2026-08-10")
    _check("03 Roh >100 % (1.187) NICHT gedeckelt/gerundet",
           h["HTZ"][0]["inst_ownership"] == 1.187)
    _check("06 zweite Achse insider_ownership mitgeschrieben",
           h["FTK"][0]["insider_ownership"] == 0.607)

    # ── 2: none → null, NIEMALS 0; echtes 0.0 bleibt 0.0 ──────────────────────
    p = _fresh_file()
    gr._persist_inst_ownership_history(
        [_stock("AAA", None, 0.10),    # inst missing → null
         _stock("BBB", 0.30, None),    # insider missing → null
         _stock("CCC", None, None),    # beide missing → null-Punkt
         _stock("DDD", 0.0, 0.0)],     # ECHTES 0.0 → bleibt 0.0
        report_date_iso="2026-08-10")
    h = _load(p)
    _check("02 inst missing → null (nicht 0)", h["AAA"][0]["inst_ownership"] is None)
    _check("02 insider missing → null (nicht 0)", h["BBB"][0]["insider_ownership"] is None)
    _check("02 beide missing → beide null", h["CCC"][0]["inst_ownership"] is None
           and h["CCC"][0]["insider_ownership"] is None)
    _check("02 echtes 0.0 bleibt 0.0 (≠ null)",
           h["DDD"][0]["inst_ownership"] == 0.0
           and h["DDD"][0]["inst_ownership"] is not None)
    # Grep über die GESCHRIEBENE Datei: kein missing-Wert wurde 0
    raw = open(p, encoding="utf-8").read()
    _check("02 geschriebene Datei nutzt JSON null (nicht 0) für missing",
           '"inst_ownership": null' in raw and '"insider_ownership": null' in raw)
    # AAA/BBB/CCC dürfen NIRGENDS ein 0 für den missing-Slot tragen
    aaa = json.dumps(h["AAA"][0])
    _check("02 AAA-Punkt: inst als null, KEIN 0", '"inst_ownership": null' in aaa
           and '"inst_ownership": 0' not in aaa)
    # Value-Normalizer-Einheit
    _check("02 _inst_own_value(None)=None", gr._inst_own_value(None) is None)
    _check("02 _inst_own_value(True)=None (bool-Guard)", gr._inst_own_value(True) is None)
    _check("02 _inst_own_value(NaN)=None", gr._inst_own_value(float("nan")) is None)
    _check("02 _inst_own_value(0.0)=0.0 (echtes 0 bleibt)", gr._inst_own_value(0.0) == 0.0)
    _check("03 _inst_own_value(1.187)=1.187 (roh)", gr._inst_own_value(1.187) == 1.187)

    # ── 5: Idempotenz (Doppel-Lauf gleiches Datum) ────────────────────────────
    p = _fresh_file()
    day = [_stock("HTZ", 1.187, 0.05)]
    gr._persist_inst_ownership_history(day, report_date_iso="2026-08-10")
    n2 = gr._persist_inst_ownership_history(day, report_date_iso="2026-08-10")
    h = _load(p)
    _check("05 Doppel-Lauf gleiches Datum → keine Dublette",
           n2 == 0 and len(h["HTZ"]) == 1)

    # ── 4: forward-only — unverändert am Folgetag → kein Punkt; kein Backfill ──
    n3 = gr._persist_inst_ownership_history(day, report_date_iso="2026-08-11")
    h = _load(p)
    _check("04 unveränderter Wert am Folgetag → kein neuer Punkt",
           n3 == 0 and len(h["HTZ"]) == 1)
    # Wertänderung → genau ein neuer Punkt (forward)
    n4 = gr._persist_inst_ownership_history(
        [_stock("HTZ", 1.25, 0.05)], report_date_iso="2026-08-12")
    h = _load(p)
    _check("04 Wertänderung → ein neuer forward-Punkt (Serie wächst)",
           n4 == 1 and [q["inst_ownership"] for q in h["HTZ"]] == [1.187, 1.25])
    _check("04 kein Backfill: nur die tatsächlich gelaufenen Daten",
           [q["date"] for q in h["HTZ"]] == ["2026-08-10", "2026-08-12"])

    # ── 7: fail-soft — kaputter Stock bricht nicht ab ─────────────────────────
    p = _fresh_file()
    bad = [{"ticker": "OK1", "inst_ownership": 0.5, "insider_ownership": 0.1,
            "market": "US"},
           "NICHT-EIN-DICT",                       # .get würde werfen → gefangen
           {"ticker": "OK2", "inst_ownership": 0.6, "insider_ownership": 0.2,
            "market": "US"}]
    try:
        nb = gr._persist_inst_ownership_history(bad, report_date_iso="2026-08-10")
        crashed = False
    except Exception:
        crashed = True
    h = _load(p) if os.path.exists(p) else {}
    _check("07 kaputter Stock → kein Crash, gute Ticker gesammelt",
           not crashed and "OK1" in h and "OK2" in h)

    # ── 8: Feature-Flag ───────────────────────────────────────────────────────
    p = _fresh_file()
    gr.INST_OWNERSHIP_HISTORY_ENABLED = False
    nf = gr._persist_inst_ownership_history([_stock("ZZZ", 0.5, 0.1)],
                                            report_date_iso="2026-08-10")
    _check("08 Flag OFF → keine Sammlung, keine Datei geschrieben",
           nf == 0 and not os.path.exists(p))
    gr.INST_OWNERSHIP_HISTORY_ENABLED = True

    # ── 9: US-only ────────────────────────────────────────────────────────────
    p = _fresh_file()
    gr._persist_inst_ownership_history(
        [_stock("USX", 0.4, 0.1, market="US"),
         _stock("UKX", 0.9, 0.2, market="UK")], report_date_iso="2026-08-10")
    h = _load(p)
    _check("09 US-only: non-US-Ticker übersprungen", "USX" in h and "UKX" not in h)

    # ── 10: Look-Ahead-Isolation — kein Score-/Filter-Read ────────────────────
    # inst_ownership/insider_ownership dürfen NICHT in den Score-Berechnungs-
    # Funktionen auftauchen. Prüfe die Rümpfe von score()/_compute_sub_scores/
    # score_bonus auf einen Read dieser Felder.
    def _body(fn_sig):
        i = GR_SRC.find(fn_sig)
        if i < 0:
            return ""
        j = GR_SRC.find("\ndef ", i + 1)
        return GR_SRC[i:j if j > 0 else i + 8000]
    for sig in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        b = _body(sig)
        _check(f"10 {sig.strip()} liest kein inst_/insider_ownership (Look-Ahead-Guard)",
               "inst_ownership" not in b and "insider_ownership" not in b)
    # Read-Site liest heldPercentInsiders aus demselben .info-Dict (kein Extra-Fetch)
    _check("06 Read-Site: heldPercentInsiders aus .info (kein Extra-Fetch)",
           GR_SRC.count('info.get("heldPercentInsiders")') >= 2)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle inst_ownership_history-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
