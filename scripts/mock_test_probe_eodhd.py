#!/usr/bin/env python3
"""Mock-Tests Wegwerf-Probe EODHD (stdlib-only, kein Netz).

Schwerpunkte: Schlüssel nie in Log/Meldung/Datei (nur Query-Parameter der
Anfrage), /api/user nur Whitelist-Felder, Kürzel-Schreibweise, Stufe-1-Gate,
Kontingent-Sperre vor Stufe 2, vorab festgelegte 90-%-Regel, Vergleich je
Aktie, Blindheit, Workflow.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import tempfile
import types
from contextlib import redirect_stdout
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_eodhd as pe  # noqa: E402

SRC = (ROOT / "scripts" / "probe_eodhd.py").read_text(encoding="utf-8")
WF = (ROOT / ".github" / "workflows" / "probe_eodhd.yml").read_text(encoding="utf-8")
KEYV = "geheimEODHD987"
FAILS: list[str] = []


def check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


class _Resp:
    def __init__(self, code=200, data=None):
        self.status_code = code
        self._d = data
        self.text = json.dumps(data)

    def json(self):
        if self._d is None:
            raise ValueError("kein json")
        return self._d


CALLS: list = []


def _bars(start_iso, n=12):
    d0 = date.fromisoformat(start_iso)
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append({"date": d.isoformat(), "open": 1, "high": 1, "low": 1, "close": 1.0,
                        "adjusted_close": 1.0, "volume": 1000})
        d = date.fromordinal(d.toordinal() + 1)
    return out


def _router(url, params=None, timeout=None, **kw):
    CALLS.append((url, dict(params or {})))
    if url.endswith("/user"):
        return _Resp(200, {"name": "Geheim Name", "email": "x@y.invalid", "subscriptionType": "free",
                           "dailyRateLimit": 20, "apiRequests": 3, "apiRequestsDate": "2026-11-15"})
    if "exchange-symbol-list" in url:
        return _Resp(200, [{"Code": "AAA", "Name": "Alpha Corp", "Type": "Common Stock", "Exchange": "NASDAQ"},
                           {"Code": "BB-B", "Name": "Beta Holdings Inc", "Type": "Common Stock", "Exchange": "NYSE"}])
    if "/eod/" in url:
        return _Resp(200, _bars(params["from"]))
    return _Resp(404, None)


def _install_requests(fn):
    mod = types.ModuleType("requests")
    mod.get = fn
    sys.modules["requests"] = mod


def main() -> int:
    saved_req = sys.modules.get("requests")
    pe.time.sleep = lambda *_: None
    pe.pt.time.sleep = lambda *_: None
    check("01 Kürzel-Schreibweise", pe.norm("BRK.B") == "BRK-B" and pe.norm("brk/b") == "BRK-B"
          and pe.norm("ABC.US") == "ABC" and pe.eod_symbol("BRK.B") == "BRK-B.US")
    check("02 Regel vorab 90 % (= Tiingo), Gate 90 %", pe.DECISION_MIN == 0.90 and pe.LIST_GATE_MIN == 0.90)
    check("03 Entscheidung: 126/140 bauen möglich, 125/140 nicht, Kontrolle ungültig",
          pe.decide_label(126, 140, True) == "bauen möglich" and pe.decide_label(125, 140, True) == "nicht bauen"
          and pe.decide_label(140, 140, False) == "ungültig")
    pe.KEY["v"] = KEYV
    _install_requests(_router)
    try:
        u = pe.user_info()
        check("04 /api/user nur Whitelist-Felder (kein Name/E-Mail)",
              "name" not in u and "email" not in u and u["dailyRateLimit"] == 20)
        check("05 Schlüssel als Query-Parameter api_token, nicht im Pfad",
              CALLS[-1][1].get("api_token") == KEYV and KEYV not in CALLS[-1][0])

        def _boom(url, params=None, **kw):
            raise ConnectionError(f"failed for {url}?api_token={params['api_token']}")
        _install_requests(_boom)
        buf = io.StringIO()
        with redirect_stdout(buf):
            st, _ = pe.eodhd_get("user", {})
            pe.log(f"status {st}")
        check("06 Netzfehler: nur Typ, kein Schlüssel/URL im Log",
              st == "netz:ConnectionError" and KEYV not in buf.getvalue())

        _install_requests(lambda url, params=None, **kw: _Resp(429, {"m": KEYV}))
        try:
            pe.eodhd_get("user", {})
            check("07 HTTP 429 → RateLimited", False)
        except pe.RateLimited as exc:
            check("07 HTTP 429 → RateLimited, Schlüssel nicht in Meldung", KEYV not in str(exc))
        buf = io.StringIO()
        with redirect_stdout(buf):
            pe.log(f"zufällig {KEYV}")
        check("08 scrub entfernt den Schlüssel", KEYV not in buf.getvalue())

        # Stufe 1 Ende-zu-Ende (FINRA gefakt)
        _install_requests(_router)
        CALLS.clear()
        pe.COUNT.update(eodhd=0, limit=pe.STUFE1_MAX_CALLS)
        base = date(2018, 7, 13)
        lists = {2018: {"base": base, "later": date(2019, 7, 15),
                        "verschwunden": ["AAA", "BB.B", "CCC", "DDD"],
                        "stichprobe_v": ["AAA", "BB.B"], "stichprobe_n": [], "adv": {}}}
        orig_gf = pe.pr.get_file
        pe.pr.get_file = lambda d: {"AAA": {"name": "Alpha Corp"}, "BB.B": {"name": "Other Name"},
                                    "CCC": {"name": "C"}, "DDD": {"name": "D"}}
        try:
            res = {}
            pe.stufe1(res, lists)
        finally:
            pe.pr.get_file = orig_gf
        y = res["E1"]["je_jahr"]["2018"]
        check("09 Abgleich alle: 2/4 Kürzel, 1/4 Kürzel+Name",
              y["alle"]["kuerzel"]["k"] == 2 and y["alle"]["kuerzel_und_name"]["k"] == 1)
        check("10 Stichprobe 2/2 → Gate weiter (Kurse 2018 vorhanden)",
              res["stufe1_gate"]["weiter_zu_stufe_2"] is True and res["stufe1_gate"]["kurse_verschwunden_2018"])
        check("11 Stufe 1 ≤ 6 EODHD-Abrufe", pe.COUNT["eodhd"] <= 6 and len(CALLS) <= 6)
        check("12 Felder/Typen der Liste erfasst", "Code" in res["E1"]["felder"]
              and res["E1"]["typen"].get("Common Stock") == 2)
        lists[2018]["stichprobe_v"] = ["AAA", "CCC"]
        pe.COUNT.update(eodhd=0, limit=pe.STUFE1_MAX_CALLS)
        pe.pr.get_file = lambda d: {}
        try:
            res2 = {}
            pe.stufe1(res2, lists)
        finally:
            pe.pr.get_file = orig_gf
        check("13 Listen-Quote 50 % → MINI-STOPP", res2["stufe1_gate"]["weiter_zu_stufe_2"] is False)

        # Stufe 2: Kontingent reicht nicht → Abbruch ohne Kurs-Abruf
        CALLS.clear()
        pe.COUNT.update(eodhd=0, limit=pe.STUFE1_MAX_CALLS)
        try:
            pe.stufe2({}, lists, [base])
            check("14 Kontingent zu klein → Abbruch", False)
        except pe.RateLimited as exc:
            check("14 Kontingent zu klein → Abbruch ohne Kurs-Abruf",
                  "Kontingent" in str(exc) and not any("/eod/" in c[0] for c in CALLS))
        # Stufe 2: Tiingo-Abbruch beendet die EODHD-Auswertung nicht (Guardian F1)
        def _router_big(url, params=None, **kw):
            if url.endswith("/user"):
                return _Resp(200, {"dailyRateLimit": 100000, "apiRequests": 0})
            return _router(url, params, **kw)
        _install_requests(_router_big)
        pe.COUNT.update(eodhd=0, limit=pe.STUFE1_MAX_CALLS)
        saved = (pe.pr.get_file, pe.pr.yf_download, pe.pt.tiingo_prices)
        pe.pr.get_file = lambda d: {}
        pe.pr.yf_download = lambda *a, **k: {}

        def _t_boom(*a, **k):
            raise pe.pt.RateLimited("tiingo 429")
        pe.pt.tiingo_prices = _t_boom
        os.environ["TIINGO_API_KEY"] = "tiingoX"
        lists[2018]["stichprobe_v"] = ["AAA", "BB.B"]
        res3 = {}
        try:
            with redirect_stdout(io.StringIO()):
                pe.stufe2(res3, lists, [date(2026, 11, 13)])
        finally:
            pe.pr.get_file, pe.pr.yf_download, pe.pt.tiingo_prices = saved
            os.environ.pop("TIINGO_API_KEY", None)
            pe.pt.KEY["v"] = ""
            pe.TIINGO_STOP["v"] = ""
        g = res3.get("T1", {}).get("gesamt", {})
        check("23 Tiingo-Abbruch: EODHD läuft weiter, Entscheidung berechnet",
              g.get("abdeckung", {}).get("k") == 2 and g.get("entscheidung") == "ungültig"
              and res3["vergleich"]["tiingo_abgebrochen"] == "RateLimited")
    finally:
        if saved_req is not None:
            sys.modules["requests"] = saved_req
        else:
            sys.modules.pop("requests", None)
        pe.KEY["v"] = ""
    per = [{"symbol": "A", "eodhd": True, "tiingo": True, "in_liste": True},
           {"symbol": "B", "eodhd": True, "tiingo": False, "in_liste": True},
           {"symbol": "C", "eodhd": False, "tiingo": True, "in_liste": True},
           {"symbol": "D", "eodhd": False, "tiingo": False, "in_liste": False}]
    v = pe.vergleich(per)
    check("15 Vergleich je Aktie + Vereinigung + Widersprüche",
          (v["beide"], v["nur_eodhd"], v["nur_tiingo"], v["keiner"]) == (1, 1, 1, 1)
          and v["vereinigung"]["k"] == 3 and v["widerspruch_liste_ja_kurse_nein"] == 1
          and v["tiingo_fehlt"] == 2 and v["davon_eodhd_liefert"] == 1)
    old = os.environ.pop("EODHD_API_KEY", None)
    try:
        outp = pathlib.Path(tempfile.mkdtemp()) / "e.json"
        with redirect_stdout(io.StringIO()):
            rc = pe.main(["--stufe", "1", "--out", str(outp)])
        check("16 fehlendes Secret → Exit 2, keine Datei", rc == 2 and not outp.exists())
    finally:
        if old is not None:
            os.environ["EODHD_API_KEY"] = old
    code = re.sub(r'"""(.|\n)*?"""', "", SRC)
    check("17 kein Ergebnisfeld/keine Rendite im Code",
          not re.search(r"return_\d|max_gain|max_drawdown|outcome_path|forward_\d|pct_change", code))
    check("18 kein print/log mit URL oder Schlüssel-Variable",
          not re.search(r"log\([^)]*(api_token|KEY\[|url)", code) and "print(url" not in code)
    check("19 Workflow: nur Hand-Start, contents: read, kein Push",
          "workflow_dispatch" in WF and "schedule" not in WF and "contents: read" in WF
          and "write" not in WF and "git push" not in WF)
    check("20 Workflow: nur EODHD/Tiingo-Secrets, beide maskiert, 30 Tage",
          set(re.findall(r"secrets\.(\w+)", WF)) == {"EODHD_API_KEY", "TIINGO_API_KEY"}
          and WF.count("::add-mask::") == 2 and "retention-days: 30" in WF)
    old_end = pe.PROBE_END
    pe.PROBE_END = date(2000, 1, 1)
    try:
        with redirect_stdout(io.StringIO()):
            rc21 = pe.main(["--stufe", "1", "--out", "/nonexistent/x.json"])
        check("21 nach PROBE_END no-op", rc21 == 0)
    finally:
        pe.PROBE_END = old_end
    check("22 gleiche Stichprobe wie Tiingo (finra_lists aus probe_tiingo)",
          "pt.finra_lists()" in SRC and "pt.covered(" in SRC)
    if FAILS:
        print(f"{len(FAILS)} FAIL: {FAILS}")
        return 1
    print("Alle probe_eodhd-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
