"""Mock-Tests für reg_sho_history.json (forward-only Reg-SHO-Sammlung, 11.08.2026).

Sammelt TÄGLICH je Universums-Ticker, ob er auf der Reg-SHO-Threshold-Liste SEINER
BÖRSE steht — eigene prune-immune Datei, börsen-aware. REINE Sammlung.

Verriegelt die harten Invarianten (das HÄRTESTE ist #1):
  1  DREI UNTERSCHEIDBARE FORMEN im Datensatz: false (geprüft, nicht drauf) /
     none-weil-nicht-abgedeckt (exchange_not_covered/_unknown) / none-weil-Quelle-
     tot (fetch_failed/source_empty/source_unresolved). false und „nicht geprüft"
     sehen NIE gleich aus.
  2  none-NEVER-false: ein nicht-abgedeckter/ungeprüfter Ticker endet NIE als false.
     Die EINZIGE Bool-Zuweisung ist `tk in syms` im syms-is-not-None-Zweig.
  3  Börsen-Mapping (NMS→nasdaq, NYQ/ASE→nyse, BATS→not_covered, None→unknown).
  4  Zwei Daten: date (as-of) + source_date (Datum in der Liste).
  5  IDEMPOTENZ (ticker, date). 6 Fetch-Fail ≠ Leerbefund im State.
  7  postclose-only + Budget + Feature-Flag. 8 KEIN Prune/Cap + Cap-Vorführung.
  9  Look-Ahead-Isolation: reg_sho-Felder NICHT in Score-Pfaden.

Kategorie A: stdlib only, deterministisch, env-frei.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import reg_sho_history as rs  # noqa: E402

RS_SRC = (ROOT / "reg_sho_history.py").read_text(encoding="utf-8")
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _paths():
    d = tempfile.mkdtemp()
    return os.path.join(d, "reg_sho_history.json"), os.path.join(d, "reg_sho_state.json")


_NASDAQ_OV = ('<a href="http://www.nasdaqtrader.com/dynamic/symdir/regsho/'
              'nasdaqth20260810.txt">list</a>')
_NASDAQ_FILE = ("Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Rule 3210|Filler\n"
                "TNXP|Tenax|Q|Y||\n"
                "INHD|Inno|Q|Y||\n"
                "File Creation Date: 20260810230017\n")


def _nasdaq_fn(url):
    if "Trader.aspx" in url:
        return (200, _NASDAQ_OV, None)
    if "nasdaqth20260810.txt" in url:
        return (200, _NASDAQ_FILE, None)
    return (404, None, "HTTPError 404")


def _nyse_fn(url):
    return (200, "<html>JS-rendered, kein Datei-Link</html>", None)   # Probe #522


def _load(p):
    return json.load(open(p, encoding="utf-8"))


_UNI = [
    {"ticker": "TNXP", "exchange": "NMS"},    # auf Nasdaq-Liste → restricted TRUE
    {"ticker": "SOHU", "exchange": "NCM"},    # Nasdaq, nicht drauf → restricted FALSE
    {"ticker": "HZO", "exchange": "NYQ"},     # NYSE, nicht auflösbar → none/source_unresolved
    {"ticker": "BATSX", "exchange": "BATS"},  # Cboe → none/exchange_not_covered
    {"ticker": "NOEX", "exchange": None},     # keine Börse → none/exchange_unknown
]


def main() -> int:
    rs.REG_SHO_HISTORY_ENABLED = True

    # ── 1 + 2 + 3 + 4: die drei Formen + none-never-false + Mapping + zwei Daten ─
    H, S = _paths()
    n = rs.collect_and_persist(_UNI, report_date_iso="2026-08-11", run_phase="postclose",
                               get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                               hist_path=H, state_path=S)
    h = _load(H)
    _check("00 added == 5", n == 5)
    tnxp, sohu, hzo, bat, noex = (h["TNXP"][0], h["SOHU"][0], h["HZO"][0],
                                  h["BATSX"][0], h["NOEX"][0])
    # FORM 1: TRUE (auf der Liste)
    _check("01 TRUE-Form: restricted=True, reason=null, source=nasdaq",
           tnxp["restricted"] is True and tnxp["reason"] is None and tnxp["source"] == "nasdaq")
    # FORM 2: FALSE (geprüft, nicht drauf) — restricted IST False, reason null
    _check("01 FALSE-Form: restricted=False, reason=null (geprüft gegen echte Liste)",
           sohu["restricted"] is False and sohu["reason"] is None and sohu["source"] == "nasdaq")
    # FORM 3a: none-weil-Quelle-tot (NYSE nicht auflösbar)
    _check("01 none-Quelle-tot: restricted=None + reason=source_unresolved",
           hzo["restricted"] is None and hzo["reason"] == "source_unresolved")
    # FORM 3b: none-weil-nicht-abgedeckt (Cboe)
    _check("01 none-nicht-abgedeckt: restricted=None + reason=exchange_not_covered",
           bat["restricted"] is None and bat["reason"] == "exchange_not_covered")
    # FORM 3c: none-weil-Börse-unbekannt
    _check("01 none-Börse-unbekannt: restricted=None + reason=exchange_unknown",
           noex["restricted"] is None and noex["reason"] == "exchange_unknown")
    # Alle vier none-/false-Formen sind im Datensatz VERSCHIEDEN:
    forms = [(p["restricted"], p["reason"]) for p in (sohu, hzo, bat, noex)]
    _check("01 vier Formen paarweise verschieden (false ≠ jede none-Variante)",
           len(set(forms)) == 4)

    # ── 2: none-NEVER-false (Grep + Daten) ────────────────────────────────────
    for t, p in h.items():
        if p[0]["restricted"] is False:
            _check(f"02 {t}: restricted=False NUR mit konsultierter Liste (source gesetzt)",
                   p[0]["source"] in ("nasdaq", "nyse") and p[0]["reason"] is None)
    raw = open(H, encoding="utf-8").read()
    _check("02 kein none-Ticker trägt restricted:false (HZO/BATSX/NOEX → null)",
           '"restricted":false' in raw            # SOHU ist legitim false
           and h["HZO"][0]["restricted"] is None
           and h["BATSX"][0]["restricted"] is None)
    # Source-Guard: die EINZIGE Bool-Zuweisung ist `tk in syms` im Evaluator.
    i = RS_SRC.find("def _evaluate_ticker(")
    j = RS_SRC.find("\ndef ", i + 1)
    ev = RS_SRC[i:j]
    bool_assigns = re.findall(r'point\["restricted"\]\s*=\s*(.+)', ev)
    _check("02 GENAU eine restricted-Bool-Zuweisung, und die ist 'ticker in syms'",
           len(bool_assigns) == 1 and "in syms" in bool_assigns[0])

    # ── 3: Mapping-Unit ───────────────────────────────────────────────────────
    _check("03 _source_for_exchange NMS→nasdaq / NYQ→nyse / BATS→not_covered / None→unknown",
           rs._source_for_exchange("NMS") == ("nasdaq", None)
           and rs._source_for_exchange("NYQ") == ("nyse", None)
           and rs._source_for_exchange("BATS") == (None, "exchange_not_covered")
           and rs._source_for_exchange(None) == (None, "exchange_unknown"))

    # ── 4: zwei Daten ─────────────────────────────────────────────────────────
    _check("04 date (as-of) + source_date (Liste) getrennt",
           tnxp["date"] == "2026-08-11" and tnxp["source_date"] == "2026-08-10")

    # ── 5: IDEMPOTENZ ─────────────────────────────────────────────────────────
    n2 = rs.collect_and_persist(_UNI, report_date_iso="2026-08-11", run_phase="postclose",
                                get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                                hist_path=H, state_path=S)
    _check("05 Doppel-Lauf: added=0, keine Dublette",
           n2 == 0 and len(_load(H)["TNXP"]) == 1)
    # nächster Tag → Snapshot angehängt
    n3 = rs.collect_and_persist(_UNI, report_date_iso="2026-08-12", run_phase="postclose",
                                get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                                hist_path=H, state_path=S)
    _check("05 nächster Tag: neuer Punkt (dicht, ein Punkt/Ticker/Tag)",
           n3 == 5 and len(_load(H)["TNXP"]) == 2)

    # ── 6: Fetch-Fail ≠ Leerbefund im State — und NIE false ───────────────────
    Hf, Sf = _paths()
    rs.collect_and_persist([{"ticker": "TNXP", "exchange": "NMS"}], run_phase="postclose",
                           get_nasdaq_text_fn=lambda u: (None, None, "URLError"),
                           hist_path=Hf, state_path=Sf)
    hf = _load(Hf)
    _check("06 Nasdaq Fetch-Fail → restricted None + reason fetch_failed (NIE false)",
           hf["TNXP"][0]["restricted"] is None and hf["TNXP"][0]["reason"] == "fetch_failed"
           and _load(Sf)["nasdaq_result"] == "fetch_failed")
    He, Se = _paths()
    _EMPTY = "Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Rule 3210|Filler\n"
    rs.collect_and_persist([{"ticker": "TNXP", "exchange": "NMS"}], run_phase="postclose",
                           get_nasdaq_text_fn=lambda u: (200, _NASDAQ_OV, None) if "Trader" in u
                           else (200, _EMPTY, None), hist_path=He, state_path=Se)
    _check("06 Nasdaq geladen, 0 Symbole → reason source_empty (≠ fetch_failed, ≠ false)",
           _load(He)["TNXP"][0]["restricted"] is None
           and _load(He)["TNXP"][0]["reason"] == "source_empty"
           and _load(Se)["nasdaq_result"] == "empty")

    # ── 7: postclose-only + Budget + Feature-Flag ─────────────────────────────
    Hp, Sp = _paths()
    _check("07 premarket → 0, keine Datei",
           rs.collect_and_persist(_UNI, run_phase="premarket", get_nasdaq_text_fn=_nasdaq_fn,
                                  hist_path=Hp, state_path=Sp) == 0 and not os.path.exists(Hp))
    Hb, Sb = _paths()

    def _must_not(url):
        raise AssertionError("Budget muss VOR dem Netz-Fetch greifen")
    nb = rs.collect_and_persist(_UNI, run_phase="postclose", get_nasdaq_text_fn=_must_not,
                                time_budget_s=-1.0, hist_path=Hb, state_path=Sb)
    # Budget → Nasdaq-Resolver bricht ab (result=budget), Ticker → none (nie false)
    _check("07 Budget → kein Netz-Fetch, Nasdaq-Ticker werden none (nie false)",
           nb == 5 and _load(Hb)["TNXP"][0]["restricted"] is None
           and _load(Sb)["nasdaq_result"] == "budget")
    Hfl, Sfl = _paths()
    rs.REG_SHO_HISTORY_ENABLED = False
    _check("07 ENABLED=False → 0, keine Datei",
           rs.collect_and_persist(_UNI, run_phase="postclose", get_nasdaq_text_fn=_nasdaq_fn,
                                  hist_path=Hfl, state_path=Sfl) == 0 and not os.path.exists(Hfl))
    rs.REG_SHO_HISTORY_ENABLED = True

    # ── 8: KEIN Prune/Cap + Cap-Vorführung + Source-Guard ─────────────────────
    Hl, _ = _paths()
    many = [{"date": f"{2021 + i // 12}-{(i % 12) + 1:02d}-01", "restricted": bool(i % 2),
             "reason": None, "exchange": "NMS", "source": "nasdaq", "source_date": "x"}
            for i in range(60)]
    rs._save_history({"LONG": list(many)}, Hl)
    hl = _load(Hl)
    _check("08 KEIN Cap: alle 60 Punkte überleben", len(hl["LONG"]) == 60)
    _check("08 KEIN Cutoff: ältester (2021) überlebt",
           any(q["date"].startswith("2021") for q in hl["LONG"]))
    Hc, _ = _paths()
    _orig = rs._save_history

    def _capped(hist, path=None):
        _orig({t: pts[-32:] for t, pts in hist.items()}, path)
    try:
        rs._save_history = _capped
        rs._save_history({"LONG": list(many)}, Hc)
        caught = len(_load(Hc)["LONG"]) != 60
    finally:
        rs._save_history = _orig
    _check("08 Cap-Vorführung: künstliches 32-Cap → No-Prune-Assertion bricht", caught)
    i = RS_SRC.find("def _save_history(")
    j = RS_SRC.find("\ndef ", i + 1)
    save_code = re.sub(r'""".*?"""', "", RS_SRC[i:j], flags=re.DOTALL)
    _check("08 save-CODE ohne Cutoff/Cap/Slice-Prune",
           "timedelta" not in save_code and "cutoff" not in save_code
           and "MAX_POINTS" not in save_code
           and not re.search(r"\[-\s*\d+\s*:\]", save_code)
           and not re.search(r"\[:\s*\d+\s*\]", save_code))
    _check("08 keine Retention-Konstanten im Modul",
           "REG_SHO_HISTORY_DAYS" not in RS_SRC and "REG_SHO_HISTORY_MAX_POINTS" not in RS_SRC)

    # ── 9: Look-Ahead-Isolation ───────────────────────────────────────────────
    def _body(sig):
        k = GR_SRC.find(sig)
        if k < 0:
            return ""
        m = GR_SRC.find("\ndef ", k + 1)
        return GR_SRC[k:m if m > 0 else k + 8000]
    for sig in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        b = _body(sig)
        _check(f"09 {sig.strip()} liest kein reg_sho/restricted (Look-Ahead)",
               "reg_sho" not in b and "restricted_t" not in b)
    _check("09 reg_sho_history nur im postclose-Hook aufgerufen",
           GR_SRC.count("reg_sho_history.collect_and_persist(") == 1)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle reg_sho_history-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
