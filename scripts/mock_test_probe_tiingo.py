#!/usr/bin/env python3
"""Mock-Tests für die Wegwerf-Probe Tiingo (stdlib-only, kein Netz).

Schwerpunkt Schlüssel-Sicherheit: nie im Log, nie in einer URL, nur im Header,
maskiert im Workflow, fehlendes Secret → Exit 2 ohne Abruf. Dazu Budget
(≤ 500 Symbole, ≤ 45/h), vorab festgeschriebene Regeln, Blindheit, Workflow.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_tiingo as pt  # noqa: E402

SRC = (ROOT / "scripts" / "probe_tiingo.py").read_text(encoding="utf-8")
WF = (ROOT / ".github" / "workflows" / "probe_tiingo.yml").read_text(encoding="utf-8")
FAILS: list[str] = []


def check(name, cond):
    print(("  OK  " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


class _Resp:
    def __init__(self, code=200, data=None, text=""):
        self.status_code = code
        self._d = data
        self.text = text or json.dumps(data)

    def json(self):
        return self._d


def main() -> int:
    check("01 Budget ≤ 500 Symbole/Monat und ≤ 1000/Tag", pt.MAX_REQUESTS <= 500 and pt.MAX_REQUESTS <= 1000)
    check("02 Takt ≤ 45 Anfragen je Stunde", 3600 / pt.PACE_S <= 45)
    check("03 Regeln vorab: 90 % / Kontrolle 18 von 20, 0,5 %, 95 %",
          pt.DECISION_MIN == 0.90 and pt.CTRL_MIN_OK == 18 and pt.CTRL_TOL == 0.005 and pt.CTRL_DAY_FRAC == 0.95)
    check("04 Entscheidung", pt.decide(90, 100) == "bauen" and pt.decide(89, 100) != "bauen"
          and pt.decide(0, 0) == "unbestimmt")
    rows = [{"date": f"2021-07-{d:02d}T00:00:00.000Z", "close": 1.0} for d in (15, 16, 19, 20, 21, 22, 23, 26)]
    check("05 Abdeckung ≥ 80 % der ersten 10 Handelstage", pt.covered(rows, date(2021, 7, 15)))
    check("06 Abdeckung zu dünn → nein", not pt.covered(rows[:5], date(2021, 7, 15)))
    tr = [{"date": f"2026-10-{d:02d}T00:00:00.000Z", "close": 10.0} for d in range(1, 21)]
    check("07 Kontrolle: gleiche Kurse stimmen", pt.ctrl_match(tr, {r["date"][:10]: 10.02 for r in tr}))
    check("08 Kontrolle: 1 % daneben stimmt nicht", not pt.ctrl_match(tr, {r["date"][:10]: 10.2 for r in tr}))
    check("09 Ticker-Umsetzung", pt.tiingo_ticker("BRK.B") == "brk-b")
    # Schlüssel-Sicherheit
    pt.KEY["v"] = "geheimSCHLUESSEL123"
    buf = io.StringIO()
    with redirect_stdout(buf):
        pt.log("Fehler bei Token geheimSCHLUESSEL123 in Antwort")
    check("10 scrub entfernt den Schlüssel aus dem Log", "geheimSCHLUESSEL123" not in buf.getvalue())
    import types
    requests = types.ModuleType("requests")   # Ersatz: CI hat kein requests, kein Netz
    requests.get = None
    saved_mod = sys.modules.get("requests")
    sys.modules["requests"] = requests
    seen = {}

    def _get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return _Resp(200, [{"date": "2021-07-15T00:00:00.000Z", "close": 1.0}])
    orig_get, orig_sleep = requests.get, pt.time.sleep
    requests.get, pt.time.sleep = _get, (lambda *_: None)
    try:
        st, data = pt.tiingo_prices("ABC", date(2021, 7, 1), date(2021, 8, 1))
        check("11 Schlüssel nur im Header, nicht in URL/Parametern",
              st == "ok" and "geheim" not in seen["url"] and "geheim" not in json.dumps(seen["params"])
              and seen["headers"]["Authorization"] == "Token geheimSCHLUESSEL123")

        def _get429(url, params=None, headers=None, timeout=None):
            return _Resp(429, None, "Too many requests, geheimSCHLUESSEL123")
        requests.get = _get429
        try:
            pt.tiingo_prices("ABC", date(2021, 7, 1), date(2021, 8, 1))
            check("12 HTTP 429 → RateLimited", False)
        except pt.RateLimited as exc:
            check("12 HTTP 429 → RateLimited, Schlüssel nicht in Meldung", "geheim" not in str(exc))
    finally:
        requests.get, pt.time.sleep = orig_get, orig_sleep
        if saved_mod is not None:
            sys.modules["requests"] = saved_mod
        else:
            sys.modules.pop("requests", None)
        pt.KEY["v"] = ""
        pt.COUNT["anfragen"] = 0
    code = re.sub(r'"""(.|\n)*?"""', "", SRC)
    check("13 kein token=/apikey= in URLs, kein print des Schlüssels",
          not re.search(r"token=|apikey=|print\([^)]*KEY", code, re.I))
    old = os.environ.pop("TIINGO_API_KEY", None)
    try:
        outp = pathlib.Path(tempfile.mkdtemp()) / "t.json"
        check("14 fehlendes Secret → Exit 2, keine Datei", pt.main(["--out", str(outp)]) == 2 and not outp.exists())
    finally:
        if old is not None:
            os.environ["TIINGO_API_KEY"] = old
    check("15 kein Ergebnisfeld im Code",
          not re.search(r"return_\d|max_gain|max_drawdown|outcome_path|forward_\d|pct_change", code))
    check("16 Workflow: nur Hand-Start, contents: read, kein Push",
          "workflow_dispatch" in WF and "schedule" not in WF and "contents: read" in WF
          and "write" not in WF and "git push" not in WF)
    check("17 Workflow: nur Secret TIINGO_API_KEY, maskiert",
          set(re.findall(r"secrets\.(\w+)", WF)) == {"TIINGO_API_KEY"} and "::add-mask::" in WF)
    old_end = pt.PROBE_END
    pt.PROBE_END = date(2000, 1, 1)
    try:
        check("18 nach PROBE_END no-op", pt.main(["--out", "/nonexistent/x.json"]) == 0)
    finally:
        pt.PROBE_END = old_end
    if FAILS:
        print(f"{len(FAILS)} FAIL: {FAILS}")
        return 1
    print("Alle probe_tiingo-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
