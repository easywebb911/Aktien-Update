"""Mock-Tests für reg_sho_history.json (forward-only Reg-SHO-Sammlung, 11.08.2026).

Sammelt TÄGLICH je Universums-Ticker, ob er auf der Reg-SHO-Threshold-Liste SEINER
BÖRSE steht — eigene prune-immune Datei, börsen-aware. REINE Sammlung.

Verriegelt die harten Invarianten (das HÄRTESTE ist #1):
  1  DREI UNTERSCHEIDBARE FORMEN im Datensatz: false (geprüft, nicht drauf) /
     none-weil-nicht-abgedeckt (exchange_not_covered/_unknown) / none-weil-Quelle-
     tot (fetch_failed/source_empty). false und „nicht geprüft" sehen NIE gleich aus.
  2  none-NEVER-false: ein nicht-abgedeckter/ungeprüfter Ticker endet NIE als false.
     Die EINZIGE Bool-Zuweisung ist `tk in syms` im syms-is-not-None-Zweig.
  3  Börsen-Mapping (NMS→nasdaq, NYQ/ASE→nyse, BATS→not_covered, None→unknown).
  4  Zwei Daten: date (as-of) + source_date (Datum in der Liste).
  5  IDEMPOTENZ (ticker, date). 6 Fetch-Fail ≠ Leerbefund im State.
  7  postclose-only + Budget + Feature-Flag. 8 KEIN Prune/Cap + Cap-Vorführung.
  9  Look-Ahead-Isolation: reg_sho-Felder NICHT in Score-Pfaden.
  10 NYSE-API-Umstellung (21.08.2026, Diagnose-Probe-Nachschärfung): echte
     ``_resolve_nyse()`` gegen die reale Ziffern-Platzhalter-Zeile
     (``'20260817210500'``) — MUSS NICHT als Symbol landen.
  11 ``_last_workday_before`` liefert T-1/letzten Handelstag, NIE heute —
     gegen die diagnose-bestätigten Beispieldaten 17.08.→14.08. / 21.08.→20.08.
  12 Rand-/Feiertagsfall: NYSE-Endpunkt für den angefragten Handelstag
     unerwartet leer → bleibt UNBEKANNT (None + source_empty), NIE „nicht auf
     der Liste" (false).
  13 Fetch-Fehler-Detail (02.09.2026): ``_resolve_nyse()`` reichert
     ``fetch_failed`` um ein Detail-Suffix an (err/HTTP-Status/leerer Body,
     nie ein bare „None", Defensiv-Cap 200 Zeichen). Reine Logging-
     Anreicherung — restricted bleibt None, reason bleibt „fetch_failed".

Kategorie A: stdlib only, deterministisch, env-frei — KEIN echter Netzwerk-Call,
alle NYSE-/Nasdaq-Antworten sind injizierte Mocks.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timezone

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


# Fixer Laufzeit-Stempel für alle Tests dieser Datei — Dienstag 11.08.2026.
# _last_workday_before(2026-08-11) == 2026-08-10 (Montag, reiner Wochenend-
# Skip) — das ist der T-1-Wert, den JEDER _nyse_fn-Mock unten erwartet.
_NOW = datetime(2026, 8, 11, 21, 30, tzinfo=timezone.utc)
_NYSE_T1 = "2026-08-10"

# Reale Response-Body-Zeilen aus der Diagnose 17./21.08.2026 (Live-Belege,
# nicht erfunden) — Header + zwei echte NYSE-Threshold-Einträge.
_NYSE_REAL_BODY = (
    "Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Filler|Filler\n"
    "AMZE|Amaze Holdings, Inc.|NYSE American|Y||\n"
    "BMNZ|Defiance Daily Target 2X Short BMNR ETF|NYSE Arca|Y||\n"
)
# Die REALE Platzhalter-Zeile bei leeren Tagen (Diagnose 21.08.2026, wörtlich
# aus dem Live-Response-Body kopiert — Format YYYYMMDDHHMMSS).
_NYSE_PLACEHOLDER_BODY = (
    "Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Filler|Filler\n"
    "20260817210500\n"
)


def _nyse_fn(url):
    """Erwartet IMMER T-1 (``_NYSE_T1``), NIE das aktuelle Kalenderdatum von
    ``_NOW`` (2026-08-11) — bricht hart, falls ``collect_and_persist`` versehentlich
    heute statt T-1 anfragt (Leitplanke 1)."""
    assert f"selectedDate={_NYSE_T1}" in url, f"erwartet T-1={_NYSE_T1} in {url!r}"
    assert "selectedDate=2026-08-11" not in url, f"NIEMALS heute in {url!r}"
    assert "market=" in url
    return (200, _NYSE_REAL_BODY, None)


def _load(p):
    return json.load(open(p, encoding="utf-8"))


_UNI = [
    {"ticker": "TNXP", "exchange": "NMS"},    # Nasdaq, auf Liste → restricted TRUE
    {"ticker": "SOHU", "exchange": "NCM"},    # Nasdaq, nicht drauf → restricted FALSE
    {"ticker": "AMZE", "exchange": "NYQ"},    # NYSE, auf Liste (reale Diagnose-Daten) → restricted TRUE
    {"ticker": "HZO", "exchange": "NYQ"},     # NYSE, NICHT auf Liste → restricted FALSE
    {"ticker": "BATSX", "exchange": "BATS"},  # Cboe → none/exchange_not_covered
    {"ticker": "NOEX", "exchange": None},     # keine Börse → none/exchange_unknown
]


def main() -> int:
    rs.REG_SHO_HISTORY_ENABLED = True

    # ── 1 + 2 + 3 + 4: die drei Formen + none-never-false + Mapping + zwei Daten ─
    H, S = _paths()
    n = rs.collect_and_persist(_UNI, report_date_iso="2026-08-11", run_phase="postclose",
                               now_utc=_NOW,
                               get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                               hist_path=H, state_path=S)
    h = _load(H)
    _check("00 added == 6", n == 6)
    tnxp, sohu, amze, hzo, bat, noex = (h["TNXP"][0], h["SOHU"][0], h["AMZE"][0],
                                        h["HZO"][0], h["BATSX"][0], h["NOEX"][0])
    # FORM 1: TRUE (auf der Liste) — Nasdaq UND NYSE (seit API-Umstellung 21.08.2026)
    _check("01 TRUE-Form Nasdaq: restricted=True, reason=null, source=nasdaq",
           tnxp["restricted"] is True and tnxp["reason"] is None and tnxp["source"] == "nasdaq")
    _check("01 TRUE-Form NYSE: restricted=True, reason=null, source=nyse, source_date=T-1",
           amze["restricted"] is True and amze["reason"] is None and amze["source"] == "nyse"
           and amze["source_date"] == _NYSE_T1)
    # FORM 2: FALSE (geprüft, nicht drauf) — restricted IST False, reason null
    _check("01 FALSE-Form Nasdaq: restricted=False, reason=null (geprüft gegen echte Liste)",
           sohu["restricted"] is False and sohu["reason"] is None and sohu["source"] == "nasdaq")
    _check("01 FALSE-Form NYSE: restricted=False, reason=null, source=nyse, source_date=T-1",
           hzo["restricted"] is False and hzo["reason"] is None and hzo["source"] == "nyse"
           and hzo["source_date"] == _NYSE_T1)
    # FORM 3a: none-weil-nicht-abgedeckt (Cboe)
    _check("01 none-nicht-abgedeckt: restricted=None + reason=exchange_not_covered",
           bat["restricted"] is None and bat["reason"] == "exchange_not_covered")
    # FORM 3b: none-weil-Börse-unbekannt
    _check("01 none-Börse-unbekannt: restricted=None + reason=exchange_unknown",
           noex["restricted"] is None and noex["reason"] == "exchange_unknown")
    # Alle vier FALSE-/none-Formen sind im Datensatz VERSCHIEDEN — inkl. Source,
    # denn SOHU (Nasdaq) und HZO (NYSE) sind beide legitim (False, reason=None)
    # und nur über die konsultierte Quelle unterscheidbar (bewusst KEIN Bug:
    # zwei unabhängige Ticker dürfen dasselbe "geprüft, nicht drauf" teilen).
    forms = [(p["restricted"], p["reason"], p["source"]) for p in (sohu, hzo, bat, noex)]
    _check("01 vier Formen paarweise verschieden (false×2-Quellen ≠ jede none-Variante)",
           len(set(forms)) == 4)

    # ── 2: none-NEVER-false (Grep + Daten) ────────────────────────────────────
    for t, p in h.items():
        if p[0]["restricted"] is False:
            _check(f"02 {t}: restricted=False NUR mit konsultierter Liste (source gesetzt)",
                   p[0]["source"] in ("nasdaq", "nyse") and p[0]["reason"] is None)
    raw = open(H, encoding="utf-8").read()
    _check("02 echte none-Ticker (BATSX/NOEX) tragen restricted:null, "
           "NIE false — HZO/SOHU sind legitim false (echt gegen Liste geprüft)",
           '"restricted":false' in raw            # SOHU/HZO sind legitim false
           and h["BATSX"][0]["restricted"] is None
           and h["NOEX"][0]["restricted"] is None)
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
                                now_utc=_NOW,
                                get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                                hist_path=H, state_path=S)
    _check("05 Doppel-Lauf: added=0, keine Dublette",
           n2 == 0 and len(_load(H)["TNXP"]) == 1)
    # nächster Tag → Snapshot angehängt
    n3 = rs.collect_and_persist(_UNI, report_date_iso="2026-08-12", run_phase="postclose",
                                now_utc=_NOW,
                                get_nasdaq_text_fn=_nasdaq_fn, get_nyse_text_fn=_nyse_fn,
                                hist_path=H, state_path=S)
    _check("05 nächster Tag: neuer Punkt (dicht, ein Punkt/Ticker/Tag)",
           n3 == 6 and len(_load(H)["TNXP"]) == 2)

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
           nb == 6 and _load(Hb)["TNXP"][0]["restricted"] is None
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

    # ── 10: NYSE-API-Umstellung — ECHTE _resolve_nyse() gegen die reale
    # Ziffern-Platzhalter-Zeile (wörtlich aus dem Diagnose-Response-Body vom
    # 17./21.08.2026 kopiert, KEINE Erfindung) ────────────────────────────────
    _check("10 isalpha()-Guard: parse_nyse_threshold(Platzhalter) → 0 Symbole",
           rs.parse_nyse_threshold(_NYSE_PLACEHOLDER_BODY) == set())
    _check("10 die Platzhalter-Ziffernkette selbst besteht isalpha() NICHT "
           "(Beweis, warum der Guard wirkt)",
           "20260817210500".isalpha() is False)
    _check("10 echter Ticker besteht isalpha() (Gegenprobe, Guard verwirft "
           "nicht zu viel)",
           "AMZE".isalpha() is True)

    def _nyse_placeholder_fn(url):
        return (200, _NYSE_PLACEHOLDER_BODY, None)
    r10 = rs._resolve_nyse(_nyse_placeholder_fn, lambda: False, date_iso="2026-08-17")
    _check("10 ECHTE _resolve_nyse() gegen Platzhalter-Response: "
           "symbols=None, result='empty' (NICHT '20260817210500' als Ticker)",
           r10 == (None, "2026-08-17", "empty"))

    def _nyse_real_fn(url):
        return (200, _NYSE_REAL_BODY, None)
    r10b = rs._resolve_nyse(_nyse_real_fn, lambda: False, date_iso="2026-08-14")
    _check("10 ECHTE _resolve_nyse() gegen echten Response: {'AMZE','BMNZ'}, ok:2",
           r10b == ({"AMZE", "BMNZ"}, "2026-08-14", "ok:2"))

    # ── 11: _last_workday_before — T-1/letzter Handelstag, NIE heute ─────────
    # Gegen die diagnose-bestätigten Beispieldaten (Probe-Läufe 17./21.08.2026).
    _check("11 Montag 17.08. → Freitag 14.08. (Wochenend-Skip Sa+So)",
           rs._last_workday_before(date(2026, 8, 17)) == date(2026, 8, 14))
    _check("11 Freitag 21.08. → Donnerstag 20.08. (kein Wochenend-Skip nötig)",
           rs._last_workday_before(date(2026, 8, 21)) == date(2026, 8, 20))
    _check("11 Dienstag 18.08. → Montag 17.08.",
           rs._last_workday_before(date(2026, 8, 18)) == date(2026, 8, 17))
    _check("11 niemals das übergebene Datum selbst",
           all(rs._last_workday_before(date(2026, 8, d)) != date(2026, 8, d)
               for d in range(17, 22)))
    # Integrations-Nachweis: der _nyse_fn-Mock oben (Sektion 1/5) besteht NUR,
    # weil collect_and_persist() tatsächlich T-1 statt heute anfragt — die
    # Assertions IN _nyse_fn selbst (nicht nur hier) sind der scharfe Test.
    _check("11 Integrations-Nachweis: Sektion 1 lief durch → _nyse_fn's "
           "eigene assert('selectedDate=T-1' in url, 'nicht heute' not in url) "
           "wurden nicht verletzt", n == 6)

    # ── 12: Rand-/Feiertagsfall — Endpunkt für den angefragten Handelstag
    # unerwartet leer → bleibt UNBEKANNT, NIE stillschweigend „nicht auf der
    # Liste" ──────────────────────────────────────────────────────────────────
    H12, S12 = _paths()
    rs.collect_and_persist([{"ticker": "HZO", "exchange": "NYQ"}], run_phase="postclose",
                           now_utc=_NOW, get_nasdaq_text_fn=_nasdaq_fn,
                           get_nyse_text_fn=_nyse_placeholder_fn,
                           hist_path=H12, state_path=S12)
    h12 = _load(H12)
    _check("12 NYSE liefert nur die Platzhalter-Zeile → restricted=None + "
           "reason=source_empty (NIEMALS False/'nicht auf der Liste')",
           h12["HZO"][0]["restricted"] is None
           and h12["HZO"][0]["reason"] == "source_empty"
           and _load(S12)["nyse_result"] == "empty")

    H13, S13 = _paths()
    rs.collect_and_persist([{"ticker": "HZO", "exchange": "NYQ"}], run_phase="postclose",
                           now_utc=_NOW, get_nasdaq_text_fn=_nasdaq_fn,
                           get_nyse_text_fn=lambda u: (500, None, "HTTPError 500"),
                           hist_path=H13, state_path=S13)
    h13 = _load(H13)
    _check("12 NYSE-Endpunkt HTTP 500 (Rate-Limit/Ausfall) → restricted=None + "
           "reason=fetch_failed (NIEMALS False), State-Detail zeigt HTTP-Fehlerursache",
           h13["HZO"][0]["restricted"] is None
           and h13["HZO"][0]["reason"] == "fetch_failed"
           and _load(S13)["nyse_result"] == "fetch_failed:HTTPError 500")

    # ── 13: Fehler-Detail erreicht Log/State (02.09.2026, reine Logging-
    # Anreicherung — KEINE Verhaltensänderung). Konkreter, deterministischer
    # simulierter Timeout-Fehlertext, direkt über die ECHTE _resolve_nyse()
    # UND über den vollen collect_and_persist()-Pfad geprüft, damit sowohl die
    # Single-Source (result-String) als auch ihre Propagation ins State-JSON
    # bewiesen sind (die log.info(...)-Zeile liest denselben result-String —
    # kein separater Prüfpfad nötig, Quelle ist identisch). ──────────────────
    _TIMEOUT_MSG = "TimeoutError: simulated network timeout after 8s"
    r13c = rs._resolve_nyse(lambda u: (None, None, _TIMEOUT_MSG), lambda: False,
                            date_iso="2026-08-31")
    _check("13 ECHTE _resolve_nyse() mit simuliertem Timeout: symbols=None, "
           "result trägt die konkrete Fehlermeldung 1:1 (Single-Source für "
           "Log-Zeile 'nyse=%s' UND state['nyse_result'])",
           r13c[0] is None and r13c[1] is None
           and r13c[2] == f"fetch_failed:{_TIMEOUT_MSG}")

    H13d, S13d = _paths()
    rs.collect_and_persist([{"ticker": "HZO", "exchange": "NYQ"}], run_phase="postclose",
                           now_utc=_NOW, get_nasdaq_text_fn=_nasdaq_fn,
                           get_nyse_text_fn=lambda u: (None, None, _TIMEOUT_MSG),
                           hist_path=H13d, state_path=S13d)
    h13d = _load(H13d)
    _check("13 collect_and_persist()-Volldurchlauf mit simuliertem Timeout: "
           "restricted bleibt None + reason bleibt fetch_failed (Entscheidungslogik "
           "unverändert), state['nyse_result'] trägt das Detail",
           h13d["HZO"][0]["restricted"] is None
           and h13d["HZO"][0]["reason"] == "fetch_failed"
           and _load(S13d)["nyse_result"] == f"fetch_failed:{_TIMEOUT_MSG}")

    # ── 13b: drei disjunkte Detail-Herleitungen (err / HTTP-Status≠200 ohne err /
    # leerer Body bei HTTP 200) — nie ein bare "None" im result-String, und der
    # Defensiv-Cap (200 Zeichen) greift ohne Crash bei überlangem err-Text ────
    r_err = rs._resolve_nyse(lambda u: (None, None, "URLError: timed out"),
                             lambda: False, date_iso="2026-08-31")
    r_status = rs._resolve_nyse(lambda u: (503, None, None), lambda: False,
                                date_iso="2026-08-31")
    r_emptybody = rs._resolve_nyse(lambda u: (200, "", None), lambda: False,
                                   date_iso="2026-08-31")
    r_long = rs._resolve_nyse(lambda u: (None, None, "X" * 500), lambda: False,
                              date_iso="2026-08-31")
    _check("13b Drei disjunkte Detail-Fälle: err-Vorrang, HTTP-Status-Fallback, "
           "leerer-Body-Fallback — nie 'fetch_failed:None'",
           r_err[2] == "fetch_failed:URLError: timed out"
           and r_status[2] == "fetch_failed:HTTP 503"
           and r_emptybody[2] == "fetch_failed:leerer Response-Body (HTTP 200)"
           and "None" not in r_err[2] and "None" not in r_status[2]
           and "None" not in r_emptybody[2])
    _check("13b Defensiv-Cap: überlanger err-Text wird auf 200 Zeichen gekappt, "
           "kein Crash",
           len(r_long[2]) == len("fetch_failed:") + 200)

    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle reg_sho_history-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
