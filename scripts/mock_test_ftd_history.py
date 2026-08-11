"""Mock-Tests für ftd_history.json (forward-only SEC-FTD-Sammlung, 11.08.2026).

Sammelt pro postclose die Fail-to-Deliver-Zeilen der Universums-Ticker aus dem
neuesten SEC-Halbmonats-File in eine eigene, prune-immune Datei — analog
options_oi_history. REINE Sammlung: KEIN Score/Filter/Push/Anzeige/Auswertung.

Verriegelt die harten Invarianten:
  1  LOOK-AHEAD (Punkt A): jeder Punkt trägt settlement_date (SEC-Datenstand,
     rückdatiert) UND first_available (unser Run-Tag) — sonst unbrauchbar für
     Vorabregistrierung. Beide vorhanden + korrekt.
  2  NONE-SEMANTIK: blanke Fails → null (NICHT 0); Fetch-Fail → GAR KEIN Punkt;
     Ticker fehlt im File → kein Punkt (dünn, NICHT „0 Fails"). Getrennt.
  3  Fetch-Fail ≠ Leerbefund (Übersicht tot vs. Übersicht ohne Link vs. ZIP tot).
  4  IDEMPOTENZ pro (ticker, settlement_date) — Doppel-Parse ohne Dublette.
  5  NEUES-FILE-GATE: bereits ingestes File → kein Re-Download.
  6  POSTCLOSE-ONLY + ZEITBUDGET + FEATURE-FLAG.
  7  Discovery wählt das NEUESTE Halbmonats-File (nicht geraten — aus href-Links).
  8  KEIN PRUNE/CAP (Lehre #519) + Cap-Vorführung + Source-Guard.
  9  LOOK-AHEAD-ISOLATION: ftd-Felder werden NICHT in Score-Pfaden gelesen.

Kategorie A: stdlib only (ftd_history importiert nur stdlib), deterministisch.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ftd_history as ftd  # noqa: E402

FTD_SRC = (ROOT / "ftd_history.py").read_text(encoding="utf-8")
GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")

_fails: list[str] = []


def _check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def _paths():
    d = tempfile.mkdtemp()
    return os.path.join(d, "ftd_history.json"), os.path.join(d, "ftd_history_state.json")


def _make_zip(rows, name="cnsfails.txt"):
    hdr = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE"
    body = "\n".join("|".join(map(str, r)) for r in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, hdr + "\n" + body + "\n")
    return buf.getvalue()


_OVERVIEW = (
    '<a href="https://www.sec.gov/files/data/fails-deliver-data/cnsfails202606b.zip">a</a>'
    '<a href="/files/data/fails-deliver-data/cnsfails202607a.zip">newest</a>'
    '<a href="cnsfails202605a.zip">old</a>'
)
_ZIP = _make_zip([
    ("20260701", "0", "TNXP", "123456", "TENAX", "1.23"),
    ("20260702", "0", "TNXP", "7000", "TENAX", "1.20"),
    ("20260701", "0", "AAPL", "500", "APPLE", "200.0"),   # nicht im Universum
    ("20260703", "0", "HZO", "", "MARINEMAX", "30.0"),    # blanke Fails → null
])
_UNI = ["TNXP", "HZO", "INHD"]   # INHD fehlt im File → kein Punkt (dünn)


def _ov_ok(url):
    return (200, _OVERVIEW, None)


def _bytes_ok(url):
    return (200, _ZIP, None)


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def main() -> int:
    ftd.FTD_HISTORY_ENABLED = True

    # ── 1 + 7: Discovery neuestes File + two-date Schema ──────────────────────
    H, S = _paths()
    seen_url = {}

    def _bytes_capture(url):
        seen_url["u"] = url
        return (200, _ZIP, None)

    n = ftd.collect_and_persist(_UNI, report_date_iso="2026-08-11", run_phase="postclose",
                                get_overview_fn=_ov_ok, get_bytes_fn=_bytes_capture,
                                hist_path=H, state_path=S)
    h = _load(H)
    _check("07 Discovery wählt NEUESTES File (202607a)",
           "cnsfails202607a.zip" in seen_url.get("u", ""))
    # Kurzschluss: erste Übersicht mit Links → zweite wird NICHT geholt.
    ov_calls = {"n": 0}
    def _ov_count(url):
        ov_calls["n"] += 1
        return (200, _OVERVIEW, None)
    ftd.discover_newest_ftd_file(_ov_count)
    _check("07 Discovery-Kurzschluss: nur EINE Übersicht geholt (nicht beide)",
           ov_calls["n"] == 1)
    # Budget greift AUCH in der Discovery (nicht erst vor Download).
    Hbd, Sbd = _paths()
    def _ov_must_not(url):
        raise AssertionError("Budget muss VOR dem ersten Übersichts-Fetch greifen")
    nbd = ftd.collect_and_persist(_UNI, run_phase="postclose", get_overview_fn=_ov_must_not,
                                  time_budget_s=-1.0, hist_path=Hbd, state_path=Sbd)
    _check("07 Budget während Discovery → budget_exceeded, kein Übersichts-Fetch",
           nbd == 0 and _load(Sbd)["last_result"] == "budget_exceeded")
    _check("01 added == 3", n == 3)
    pt = h["TNXP"][0]
    _check("01 Punkt-Struktur (5 Keys inkl. beide Daten)",
           set(pt) == {"settlement_date", "first_available", "fails", "price", "source_file"})
    _check("01 LOOK-AHEAD: settlement_date (SEC) ≠ first_available (Run-Tag)",
           pt["settlement_date"] == "2026-07-01" and pt["first_available"] == "2026-08-11")
    _check("01 Ziel-Mechanik: aus first_available ist ableitbar, was am Tag X BEKANNT war",
           pt["first_available"] > pt["settlement_date"])   # rückdatiert

    # ── 2: NONE-SEMANTIK ──────────────────────────────────────────────────────
    raw = open(H, encoding="utf-8").read()
    _check("02 blanke Fails → null (NICHT 0)", h["HZO"][0]["fails"] is None)
    _check("02 keine Phantom-0 in der Datei", '"fails":0' not in raw)
    _check("02 Ticker fehlt im File → KEIN Punkt (dünn, ≠ 0 Fails)", "INHD" not in h)
    _check("02 Nicht-Universum gefiltert (AAPL)", "AAPL" not in h)
    _check("02 _ftd_num(None)=None / (0)=0 / ('')=None / (' 12 ')=12",
           ftd._ftd_num(None) is None and ftd._ftd_num(0) == 0.0
           and ftd._ftd_num("") is None and ftd._ftd_num(" 12 ") == 12.0)

    # ── 3: Fetch-Fail ≠ Leerbefund ────────────────────────────────────────────
    H2, S2 = _paths()
    ftd.collect_and_persist(_UNI, run_phase="postclose",
                            get_overview_fn=lambda u: (None, None, "URLError: boom"),
                            hist_path=H2, state_path=S2)
    _check("03 Übersicht Fetch-Fail → last_result=fetch_failed:overview",
           _load(S2)["last_result"] == "fetch_failed:overview")
    H3, S3 = _paths()
    ftd.collect_and_persist(_UNI, run_phase="postclose",
                            get_overview_fn=lambda u: (200, "<html>keine links</html>", None),
                            hist_path=H3, state_path=S3)
    _check("03 Übersicht geladen, 0 Links → last_result=empty:no_link (≠ fetch-fail)",
           _load(S3)["last_result"] == "empty:no_link")
    H4, S4 = _paths()
    ftd.collect_and_persist(_UNI, run_phase="postclose", get_overview_fn=_ov_ok,
                            get_bytes_fn=lambda u: (None, None, "URLError: zipdown"),
                            hist_path=H4, state_path=S4)
    _check("03 ZIP Fetch-Fail → last_result=fetch_failed:zip",
           _load(S4)["last_result"] == "fetch_failed:zip")

    # ── 4: IDEMPOTENZ (Doppel-Parse, State-Reset erzwingt Re-Ingest) ──────────
    os.remove(S)
    n2 = ftd.collect_and_persist(_UNI, report_date_iso="2026-08-12", run_phase="postclose",
                                 get_overview_fn=_ov_ok, get_bytes_fn=_bytes_ok,
                                 hist_path=H, state_path=S)
    h = _load(H)
    _check("04 Re-Ingest desselben Files → keine Dubletten (ticker,settlement)",
           n2 == 0 and len(h["TNXP"]) == 2)

    # ── 5: NEUES-FILE-GATE (kein Re-Download bei gleichem File) ───────────────
    def _bytes_must_not(url):
        raise AssertionError("darf NICHT erneut downloaden")
    n3 = ftd.collect_and_persist(_UNI, report_date_iso="2026-08-13", run_phase="postclose",
                                 get_overview_fn=_ov_ok, get_bytes_fn=_bytes_must_not,
                                 hist_path=H, state_path=S)
    _check("05 bereits ingestes File → no_new_file, kein Re-Download",
           n3 == 0 and _load(S)["last_result"] == "no_new_file")

    # ── 6: postclose-only + Budget + Feature-Flag ─────────────────────────────
    Hp, Sp = _paths()
    npre = ftd.collect_and_persist(_UNI, run_phase="premarket", get_overview_fn=_ov_ok,
                                   get_bytes_fn=_bytes_ok, hist_path=Hp, state_path=Sp)
    _check("06 premarket → 0, keine Datei", npre == 0 and not os.path.exists(Hp))
    Hb, Sb = _paths()
    nb = ftd.collect_and_persist(_UNI, run_phase="postclose", get_overview_fn=_ov_ok,
                                 get_bytes_fn=_bytes_must_not, time_budget_s=-1.0,
                                 hist_path=Hb, state_path=Sb)
    _check("06 Budget überschritten → budget_exceeded, kein Download",
           nb == 0 and _load(Sb)["last_result"] == "budget_exceeded")
    Hf, Sf = _paths()
    ftd.FTD_HISTORY_ENABLED = False
    nf = ftd.collect_and_persist(_UNI, run_phase="postclose", get_overview_fn=_ov_ok,
                                 get_bytes_fn=_bytes_ok, hist_path=Hf, state_path=Sf)
    _check("06 ENABLED=False → 0, keine Datei", nf == 0 and not os.path.exists(Hf))
    ftd.FTD_HISTORY_ENABLED = True

    # ── 8: KEIN PRUNE/CAP + Cap-Vorführung + Source-Guard ─────────────────────
    Hl, _ = _paths()
    many = [{"settlement_date": f"{2021 + i // 12}-{(i % 12) + 1:02d}-01",
             "first_available": "2026-08-11", "fails": 100 + i,
             "price": None if i % 3 else 1.5, "source_file": "x.zip"}
            for i in range(60)]
    ftd._save_history({"LONG": list(many)}, Hl)
    hl = _load(Hl)
    _check("08 KEIN Anzahl-Cap: alle 60 Punkte überleben den Save", len(hl["LONG"]) == 60)
    _check("08 KEIN Alters-Cutoff: ältester Punkt (2021) überlebt",
           any(q["settlement_date"].startswith("2021") for q in hl["LONG"]))
    _check("08 Roh-Wert + null bleiben erhalten",
           hl["LONG"][0]["price"] == 1.5           # i=0 → 1.5
           and hl["LONG"][1]["price"] is None)     # i=1 → null
    # Cap-Vorführung
    Hc, _ = _paths()
    _orig = ftd._save_history

    def _capped(hist, path=None):
        _orig({t: pts[-32:] for t, pts in hist.items()}, path)
    try:
        ftd._save_history = _capped
        ftd._save_history({"LONG": list(many)}, Hc)
        caught = len(_load(Hc)["LONG"]) != 60
    finally:
        ftd._save_history = _orig
    _check("08 Vorführung: künstliches 32-Cap → No-Prune-Assertion bricht", caught)
    # Source-Guard (save-CODE, Docstring gestrippt)
    i = FTD_SRC.find("def _save_history(")
    j = FTD_SRC.find("\ndef ", i + 1)
    save_body = FTD_SRC[i:j]
    save_code = re.sub(r'""".*?"""', "", save_body, flags=re.DOTALL)
    _check("08 save-CODE ohne Cutoff/Cap/Slice-Prune",
           "timedelta" not in save_code and "cutoff" not in save_code
           and "MAX_POINTS" not in save_code
           and not re.search(r"\[-\s*\d+\s*:\]", save_code)
           and not re.search(r"\[:\s*\d+\s*\]", save_code))
    _check("08 keine Retention-Konstanten im Modul",
           "FTD_HISTORY_DAYS" not in FTD_SRC and "FTD_HISTORY_MAX_POINTS" not in FTD_SRC)

    # ── 9: Look-Ahead-Isolation (ftd-Felder nicht in Score-Pfaden) ────────────
    def _body(sig):
        k = GR_SRC.find(sig)
        if k < 0:
            return ""
        m = GR_SRC.find("\ndef ", k + 1)
        return GR_SRC[k:m if m > 0 else k + 8000]
    for sig in ("def score(", "def _compute_sub_scores(", "def score_bonus("):
        b = _body(sig)
        _check(f"09 {sig.strip()} liest kein ftd/settlement/first_available (Look-Ahead)",
               "settlement_date" not in b and "first_available" not in b
               and "ftd_history" not in b)
    _check("09 ftd_history nur im postclose-Hook aufgerufen (collect_and_persist)",
           GR_SRC.count("ftd_history.collect_and_persist(") == 1)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle ftd_history-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
