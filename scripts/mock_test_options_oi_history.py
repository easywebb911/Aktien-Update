"""Mock-Tests für options_oi_history.json (forward-only Options-OI-Sammlung, 11.08.2026).

Sammelt pro postclose je Top-10-Ticker den NÄCHSTEN Verfall (Calls+Puts, nur
oi>0-Strikes, roh je strike/oi/iv) plus Spot + shares_outstanding (Nenner) als
forward-only Zeitreihe in einer SEPARATEN Datei — analog inst_ownership_history.
REINE Sammlung: KEIN Score/Filter/Push/Anzeige, KEIN Delta/Gamma.

Verriegelt die harten Invarianten:
  1  ZIEL-MECHANIK: ein Fetch-Ergebnis wandert durch _persist_options_oi_history in
     die Datei; Punkt-Struktur {date, expiry, spot, shares_outstanding, calls, puts},
     je Kontrakt {strike, oi, iv}. Alle Netto-Delta-Größen vorhanden.
  2  NONE-SEMANTIK (kritisch): keine Kette → expiry/calls/puts = null (NICHT oi 0);
     Fetch-Fail → GAR KEIN Punkt (getrennt von „keine Kette"). Grep: keine 0.
  3  oi>0-Filter + iv-NaN→null + Roh-Werte (kein Deckeln/Runden).
  4  IDEMPOTENZ: derselbe Ticker am selben Datum nie zweimal (Doppel-Lauf).
  5  FORWARD-ONLY: kein Backfill; nächster postclose-Tag hängt einen Snapshot an.
  6  POSTCLOSE-ONLY: premarket sammelt nichts.
  7  ZEITBUDGET: Überschreitung bricht ab + Daily-Run läuft weiter.
  8  FAIL-SOFT: ein kaputter Ticker / ein Fetch-Fail bricht die Sammlung nicht ab.
  9  FEATURE-FLAG: ENABLED=False → keine Sammlung.
 10  ISOLATION: options_oi/shares_outstanding NICHT als Score-/Filter-Feature gelesen.
 11  KEIN PRUNE/CAP (Lehre #519): keine Alters-/Anzahl-/Größen-Begrenzung; künstliches
     Cap bricht den Test (Regress-Nachweis); Retention-Konstanten repo-weit abwesend.

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
    gr.OPTIONS_OI_HISTORY_FILE = os.path.join(d, "options_oi_history.json")
    return gr.OPTIONS_OI_HISTORY_FILE


class _FDF:
    """Minimales DataFrame-Double für _extract_oi_rows — .columns + [col]-Listen."""
    def __init__(self, data):
        self._d = data
        self.columns = list(data)

    def __getitem__(self, k):
        return self._d[k]


def _stock(t, price=4.0, shares=10_000_000):
    return {"ticker": t, "price": price, "shares_outstanding": shares}


def _load(path):
    return json.load(open(path, encoding="utf-8"))


# ── Fetch-Doubles (kein yfinance) ─────────────────────────────────────────────
def _fetch_ok(_t):
    calls = gr._extract_oi_rows(_FDF({
        "strike": [5.0, 6.0, 7.0],
        "openInterest": [60, 0, 12],                 # 6.0 hat oi 0 → raus
        "impliedVolatility": [0.85, 0.9, float("nan")],  # 7.0 iv NaN → null
    }))
    puts = gr._extract_oi_rows(_FDF({
        "strike": [4.0], "openInterest": [30], "impliedVolatility": [0.7]}))
    return ("ok", "2026-08-15", calls, puts)


def _fetch_nochain(_t):
    return ("no_chain", None, None, None)


def _fetch_fail(_t):
    raise RuntimeError("boom-network")


def main() -> int:
    gr.OPTIONS_OI_HISTORY_ENABLED = True

    # ── 01 + 03: Ziel-Mechanik + Schema + oi>0-Filter + iv-NaN→null ───────────
    p = _fresh_file()
    top = [_stock("TNXP", price=4.47, shares=12_000_000)]
    n = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose", fetch_fn=_fetch_ok)
    h = _load(p)
    pt = h["TNXP"][0]
    _check("01 added == 1", n == 1)
    _check("01 Punkt-Struktur vollständig",
           set(pt) == {"date", "expiry", "spot", "shares_outstanding", "calls", "puts"})
    _check("01 Netto-Delta-Größen da: strike/oi/iv + spot + shares + expiry",
           pt["expiry"] == "2026-08-15" and pt["spot"] == 4.47
           and pt["shares_outstanding"] == 12000000.0
           and set(pt["calls"][0]) == {"strike", "oi", "iv"})
    _check("03 oi>0-Filter: Strike mit oi 0 fällt raus",
           [c["strike"] for c in pt["calls"]] == [5.0, 7.0])
    _check("03 iv-NaN → null (nicht 0)", pt["calls"][1]["iv"] is None)
    _check("03 Roh-Werte (kein Runden/Deckeln)",
           pt["calls"][0]["oi"] == 60 and pt["calls"][0]["iv"] == 0.85
           and pt["puts"][0]["strike"] == 4.0)

    # ── 02: NONE-SEMANTIK — keine Kette ≠ oi 0; Fetch-Fail = kein Punkt ────────
    p = _fresh_file()

    def _route(t):
        return {"AAA": _fetch_ok, "NOCHAIN": _fetch_nochain,
                "FAILT": _fetch_fail}[t](t)

    top = [_stock("AAA"), _stock("NOCHAIN"), _stock("FAILT")]
    gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose", fetch_fn=_route)
    h = _load(p)
    raw = open(p, encoding="utf-8").read()
    _check("02 keine Kette → expiry null", h["NOCHAIN"][0]["expiry"] is None)
    _check("02 keine Kette → calls/puts null (NICHT [] , NICHT oi 0)",
           h["NOCHAIN"][0]["calls"] is None and h["NOCHAIN"][0]["puts"] is None)
    _check('02 Datei enthält "calls":null (keine Kette)', '"calls":null' in raw)
    _check("02 keine-Kette wird NIRGENDS zu oi 0 (kein '\"oi\":0')",
           '"oi":0' not in raw)
    _check("02 Fetch-Fail schreibt GAR KEINEN Punkt (≠ keine Kette)",
           "FAILT" not in h)

    # Unit: _opt_num 0-vs-null-Grenze
    _check("02 _opt_num(None)=None", gr._opt_num(None) is None)
    _check("02 _opt_num(True)=None (bool-Guard)", gr._opt_num(True) is None)
    _check("02 _opt_num(NaN)=None", gr._opt_num(float("nan")) is None)
    _check("02 _opt_num(0.0)=0.0 (echtes 0 bleibt)", gr._opt_num(0.0) == 0.0)

    # Chain vorhanden aber kein oi>0-Strike → [] (beobachtet leer, ≠ null)
    def _fetch_empty_chain(_t):
        return ("ok", "2026-08-15", [], [])
    p = _fresh_file()
    gr._persist_options_oi_history(
        [_stock("EMP")], report_date_iso="2026-08-11", run_phase="postclose",
        fetch_fn=_fetch_empty_chain)
    h = _load(p)
    _check("02 Kette da, kein oi>0 → calls == [] (NICHT null)",
           h["EMP"][0]["calls"] == [] and h["EMP"][0]["expiry"] == "2026-08-15")

    # ── 04: IDEMPOTENZ (Doppel-Lauf) ─────────────────────────────────────────
    p = _fresh_file()
    top = [_stock("TNXP")]
    n1 = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose", fetch_fn=_fetch_ok)
    n2 = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose", fetch_fn=_fetch_ok)
    h = _load(p)
    _check("04 Doppel-Lauf: added=0 + kein Duplikat",
           n1 == 1 and n2 == 0 and len(h["TNXP"]) == 1)

    # ── 05: FORWARD-ONLY — nächster Tag hängt an, kein Backfill ────────────────
    n3 = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-12", run_phase="postclose", fetch_fn=_fetch_ok)
    h = _load(p)
    _check("05 nächster postclose-Tag: neuer Snapshot angehängt",
           n3 == 1 and len(h["TNXP"]) == 2)
    _check("05 Daten nur an tatsächlich gelaufenen Tagen (kein Backfill)",
           [q["date"] for q in h["TNXP"]] == ["2026-08-11", "2026-08-12"])

    # ── 06: POSTCLOSE-ONLY-GATE ───────────────────────────────────────────────
    p = _fresh_file()
    nf = gr._persist_options_oi_history(
        [_stock("TNXP")], report_date_iso="2026-08-11", run_phase="premarket",
        fetch_fn=_fetch_ok)
    _check("06 premarket → added=0, keine Datei",
           nf == 0 and not os.path.exists(p))

    # ── 07: ZEITBUDGET — Abbruch, Daily-Run läuft weiter ──────────────────────
    p = _fresh_file()

    class _Clock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            v = self.t
            self.t += 100.0        # jeder Aufruf +100 s
            return v

    top = [_stock("A"), _stock("B"), _stock("C")]
    nb = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose",
        fetch_fn=_fetch_ok, now_fn=_Clock(), time_budget_s=50.0)
    _check("07 Zeitbudget überschritten → Abbruch (weniger als alle Ticker)",
           nb < len(top))

    # ── 08: FAIL-SOFT — kaputter Ticker + Fetch-Fail brechen nichts ab ────────
    p = _fresh_file()

    def _route2(t):
        return {"OK1": _fetch_ok, "OK2": _fetch_ok, "BAD": _fetch_fail}[t](t)

    top = [_stock("OK1"), "NICHT-EIN-DICT", {"noticker": 1},
           _stock("BAD"), _stock("OK2")]
    added = gr._persist_options_oi_history(
        top, report_date_iso="2026-08-11", run_phase="postclose", fetch_fn=_route2)
    h = _load(p)
    _check("08 fail-soft: gute Ticker gesammelt trotz Müll + Fetch-Fail",
           "OK1" in h and "OK2" in h and added == 2)

    # ── 09: FEATURE-FLAG ──────────────────────────────────────────────────────
    p = _fresh_file()
    gr.OPTIONS_OI_HISTORY_ENABLED = False
    nfl = gr._persist_options_oi_history(
        [_stock("TNXP")], report_date_iso="2026-08-11", run_phase="postclose",
        fetch_fn=_fetch_ok)
    _check("09 ENABLED=False → added=0, keine Datei",
           nfl == 0 and not os.path.exists(p))
    gr.OPTIONS_OI_HISTORY_ENABLED = True

    # ── 10: Look-Ahead-Isolation — kein Score-/Filter-Read ────────────────────
    def _body(fn_sig):
        i = GR_SRC.find(fn_sig)
        if i < 0:
            return ""
        j = GR_SRC.find("\ndef ", i + 1)
        return GR_SRC[i:j if j > 0 else i + 8000]
    for sig in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        b = _body(sig)
        _check(f"10 {sig.strip()} liest kein options_oi/shares_outstanding (Look-Ahead)",
               "options_oi" not in b and "shares_outstanding" not in b)
    _check("10 Read-Site: sharesOutstanding aus .info (kein Extra-Fetch, ≥2×)",
           GR_SRC.count('info.get("sharesOutstanding")') >= 2)

    # ── 11: KEIN PRUNE/CAP — No-Retention-Invariante (Lehre #519) ─────────────
    p = _fresh_file()
    # 60 postclose-Snapshots über ~5 Jahre (weit über jedem denkbaren Cap):
    many = [{"date": f"{2021 + i // 12}-{(i % 12) + 1:02d}-01",
             "expiry": "2026-01-01", "spot": 1.0 + i, "shares_outstanding": 10_000_000,
             "calls": [{"strike": 5.0, "oi": 10 + i, "iv": None if i % 3 else 0.5}],
             "puts": []}
            for i in range(60)]
    gr._save_options_oi_history({"LONG": list(many)})
    h = _load(p)
    _check("11 KEIN Anzahl-Cap: alle 60 Snapshots überleben den Save",
           len(h["LONG"]) == 60)
    _check("11 KEIN Alters-Cutoff: ältester Punkt (2021, >400 Tage) überlebt",
           any(q["date"].startswith("2021") for q in h["LONG"]))
    _check("11 Roh-Wert + null bleiben erhalten (kein Umbau)",
           h["LONG"][0]["calls"][0]["iv"] == 0.5          # i=0 → 0.5
           and h["LONG"][1]["calls"][0]["iv"] is None)    # i=1 → null

    # Vorführung (Selbstprüfung 3): künstliches 32-Cap → No-Prune-Assertion bricht.
    p = _fresh_file()
    _orig_save = gr._save_options_oi_history

    def _capped_save(hist):
        capped = {t: pts[-32:] for t, pts in hist.items()}   # künstliches Cap
        _orig_save(capped)
    try:
        gr._save_options_oi_history = _capped_save
        gr._save_options_oi_history({"LONG": list(many)})
        h_cap = _load(p)
        caught = len(h_cap["LONG"]) != 60
    finally:
        gr._save_options_oi_history = _orig_save
    _check("11 Vorführung: künstliches 32-Cap → No-Prune-Assertion bricht (Regress erkannt)",
           caught)

    # Source-Guard: save-CODE (Docstring gestrippt — der erklärt bewusst „kein
    # timedelta/cutoff") ohne Cutoff/Cap/Slice-Prune; keine Retention-Konstanten.
    _save_body = _body("def _save_options_oi_history(")
    _save_code = re.sub(r'""".*?"""', "", _save_body, flags=re.DOTALL)
    _check("11 save-CODE ohne Alters-Cutoff (kein timedelta/cutoff)",
           "timedelta" not in _save_code and "cutoff" not in _save_code)
    _check("11 save-CODE ohne Anzahl-Cap (kein MAX_POINTS / [-N:]-Slice-Prune)",
           "MAX_POINTS" not in _save_code
           and not re.search(r"\[-\s*\d+\s*:\]", _save_code)
           and not re.search(r"\[:\s*\d+\s*\]", _save_code))
    _check("11 Retention-Konstanten repo-weit abwesend",
           "OPTIONS_OI_HISTORY_DAYS" not in GR_SRC
           and "OPTIONS_OI_HISTORY_MAX_POINTS" not in GR_SRC)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle options_oi_history-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
