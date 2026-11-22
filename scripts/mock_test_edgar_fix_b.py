#!/usr/bin/env python3
"""Mock-Test EDGAR Fix (b) (Easy-Entscheid 22.11.2026). Feste Uhr, kein Netz.

 1  Titel exakt im alten Atom-Wortlaut (aus den KI-Logs 25.10.–16.11.2026)
 2  kein Stichwort in irgendeinem neuen Titel (8-K-Relevanz, Form-4-Kauf)
 3  compute_signal: identische Punkte alt vs. neu an echten Beispielen
    (TNDM 8-K, JBGS/ABEO Form 4, 8-K/A, Form 425)
 4  Auswahl wie früher: Präfix (425 und 4/A zählen als „Form 4“), Fenster
    nach Annahmezeit, neueste zuerst, Annahmezeit UTC
 5  VEEA/MPT: vorher „unbekannt“ (browse-edgar löste sie nicht auf) → jetzt
    über die CIK gefunden; diese Scores dürfen sich ändern (gezählt)
 6  ein Abruf je Ticker für 8-K und Form 4, Tickerliste einmal je Lauf,
    Fehler der Tickerliste wird gemerkt (kein Retry)
 7  keine CIK → None mit lesbarem Grund
 8  Rohdaten: Felder der Quelle, null bleibt null, Dublette nicht doppelt,
    keine Positions-/Nutzerfelder, Schreibfehler bricht nichts ab
 9  kein Score-Leser der Rohdaten
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _m in ("pandas", "requests", "yfinance"):
    try:
        __import__(_m)
    except ImportError:
        _mod = types.ModuleType(_m)
        if _m == "requests":
            class _E(Exception):
                pass

            class _T(_E):
                pass
            _mod.get = _mod.post = lambda *a, **k: None
            _mod.RequestException, _mod.Timeout = _E, _T
            _mod.exceptions = types.SimpleNamespace(RequestException=_E, Timeout=_T)
        if _m == "yfinance":
            _mod.download = _mod.Ticker = lambda *a, **k: None
        sys.modules[_m] = _mod

import sec_meldungen as sm  # noqa: E402
import ki_agent as ka       # noqa: E402
from config import SEC_RELEVANT_KEYWORDS  # noqa: E402

FAILS: list[str] = []
NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


# 1 exakter Wortlaut (Log-Belege)
OLD = {
    "8-K":   "8-K  - Current report",
    "8-K/A": "8-K/A [Amend]  - Current report",
    "4":     "4  - Statement of changes in beneficial ownership of securities",
    "425":   "425  - Prospectuses and communications, business combinations",
}
for form, t in OLD.items():
    check(sm.title_for(form) == t, f"Titel {form!r} wie früher")

# 2 kein Stichwort in neuen Titeln
for form in ("8-K", "8-K/A", "8-K12B", "8-K15D5", "4", "4/A", "425", "424B5", "424B3", "40-F", "40-17G"):
    tl = sm.title_for(form).lower()
    ok = not any(k in tl for k in SEC_RELEVANT_KEYWORDS) and "purchase" not in tl and "acquisition" not in tl
    check(ok, f"kein Bonus-Stichwort im Titel {form!r}")

# 3 compute_signal identisch alt vs. neu
ka.claude_sentiment_score = lambda t, n: (None, "")


def _sig(**kw):
    with mock.patch("builtins.print"):
        return ka.compute_signal(kw.pop("t"), {}, [], {}, kw.pop("has_8k", False), kw.pop("sec_title", ""),
                                 None, None, has_form4=kw.pop("has_form4", False),
                                 form4_title=kw.pop("form4_title", ""))


cases = [
    ("TNDM 8-K", dict(t="TNDM", has_8k=True), "sec_title", "8-K"),
    ("8-K/A",    dict(t="X", has_8k=True), "sec_title", "8-K/A"),
    ("JBGS Form 4", dict(t="JBGS", has_form4=True), "form4_title", "4"),
    ("ABEO Form 4", dict(t="ABEO", has_form4=True), "form4_title", "4"),
    ("Form 425 als Form 4", dict(t="Y", has_form4=True), "form4_title", "425"),
]
for name, base, key, form in cases:
    old = _sig(**{**base, key: OLD[form]})
    new = _sig(**{**base, key: sm.title_for(form)})
    check(old == new, f"compute_signal identisch: {name} ({old[0]} Pkt)")

# 4 Auswahl
SUB = {"filings": {"recent": {
    "form":                ["4", "425", "8-K", "8-K/A", "10-Q", "4/A", "8-K"],
    "accessionNumber":     ["a1", "a2", "a3", "a4", "a5", "a6", "a7"],
    "filingDate":          ["2026-11-20", "2026-11-18", "2026-11-20", "2026-11-19", "2026-11-19", "2026-11-10", "2026-11-01"],
    "acceptanceDateTime":  ["2026-11-20T15:00:00.000Z", "2026-11-18T21:00:00.000Z", "2026-11-20T12:30:00.000Z",
                            "2026-11-19T19:00:00.000Z", "2026-11-19T20:00:00.000Z", "2026-11-10T10:00:00.000Z",
                            "2026-11-01T10:00:00.000Z"],
    "items":               ["", "", "2.02,9.01", "8.01", "", "", "7.01"],
    "primaryDocDescription": ["FORM 4", "", "8-K", None, "10-Q", "4/A", "8-K"],
    "primaryDocument":     ["x.xml", "y.htm", "z.htm", "w.htm", "q.htm", "v.xml", "u.htm"],
}}}
k8 = sm.filings_in_window(SUB, prefix="8-K", cutoff_utc=NOW - timedelta(hours=24))
check([f["accession"] for f in k8] == ["a3", "a4"], f"8-K-Fenster 24 h, neueste zuerst: {[f['accession'] for f in k8]}")
check(k8[0]["items"] == ["2.02", "9.01"] and k8[1]["beschreibung"] is None, "Items als Liste, fehlende Beschreibung = null")
f4 = sm.filings_in_window(SUB, prefix="4", cutoff_utc=NOW - timedelta(days=7))
check([f["form"] for f in f4] == ["4", "425"], f"Präfix „4“ wie früher (425 zählt, 4/A außerhalb 7 Tage): {[f['form'] for f in f4]}")
check(f4[0]["items"] is None, "Form 4 ohne Items (null)")
check(sm.parse_acceptance("2026-11-12T22:05:40.000Z").hour == 22, "Annahmezeit als UTC gelesen")

# 5/6/7 über ki_agent mit gemocktem Netz
TICKERS = {"0": {"cik_str": 1840317, "ticker": "VEEA"}, "1": {"cik_str": 1287865, "ticker": "MPT"},
           "2": {"cik_str": 1438133, "ticker": "TNDM"}, "3": {"cik_str": 1, "ticker": "DUP"},
           "4": {"cik_str": 2, "ticker": "DUP"}}


class _R:
    def __init__(self, status, js=None, text=""):
        self.status_code, self._js, self.text = status, js, text

    def json(self):
        return self._js


calls: list[str] = []


def _router(url, *a, **k):
    calls.append(url)
    if "company_tickers" in url:
        return _R(200, TICKERS)
    return _R(200, json.loads(json.dumps(SUB)))


class _FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


ka._reset_tier3_accumulators()
with mock.patch.object(ka.requests, "get", side_effect=_router), mock.patch.object(ka.time, "sleep"), \
     mock.patch.object(ka, "datetime", _FixedDT):
    found = {}
    for t in ("VEEA", "MPT", "TNDM"):
        found[t] = (ka.fetch_sec_8k(t), ka.fetch_sec_form4(t))
    r_dup = ka.fetch_sec_8k("DUP")
    r_none = ka.fetch_sec_8k("NIXDA")
n_sub = sum(1 for c in calls if "submissions" in c)
n_tl = sum(1 for c in calls if "company_tickers" in c)
check(n_tl == 1 and n_sub == 3, f"Tickerliste 1×, Meldungsliste 1× je Ticker ({n_tl}/{n_sub})")
neu = [t for t in ("VEEA", "MPT") if found[t][0] is not None and found[t][1] is not None]
check(neu == ["VEEA", "MPT"], f"VEEA/MPT jetzt gefunden (vorher unbekannt): {neu} — Zählung {len(neu)}")
check(found["TNDM"][0] == (True, OLD["8-K"], datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)),
      "8-K-Ergebnis mit altem Titel und UTC-Annahmezeit")
check(found["TNDM"][1] == (True, OLD["4"]), "Form-4-Ergebnis mit altem Titel")
check(r_dup is None and r_none is None, "keine eindeutige CIK → None")
_err = ka._EDGAR_8K_ACCT.get("last_error_repr") or ""
check(_err.startswith("keine eindeutige CIK") and "(erster Fehler: DUP)" in _err, f"lesbarer Grund: {_err!r}")

ka._reset_tier3_accumulators()
calls.clear()
with mock.patch.object(ka.requests, "get", return_value=_R(429, text="Too Many Requests")), \
     mock.patch.object(ka.time, "sleep"):
    a = ka.fetch_sec_8k("VEEA")
    b = ka.fetch_sec_form4("MPT")
check(a is None and b is None, "Rate-Limit → None (unbekannt, kein Wert erfunden)")
ka._reset_tier3_accumulators()
cnt = {"n": 0}


def _rl(url, *a, **k):
    cnt["n"] += 1
    return _R(429, text="Too Many Requests")


with mock.patch.object(ka.requests, "get", side_effect=_rl), mock.patch.object(ka.time, "sleep"):
    ka.fetch_sec_8k("VEEA"); ka.fetch_sec_form4("VEEA"); ka.fetch_sec_8k("MPT")
check(cnt["n"] == 1, f"Tickerliste nach Fehler nicht erneut abgerufen (kein Retry): {cnt['n']} Abruf")
check("Tickerliste: HTTP 429" in (ka._EDGAR_8K_ACCT.get("last_error_repr") or ""), "Grund Rate-Limit lesbar")

# 8 Rohdaten
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "sec_meldungen.jsonl")
    recs = sm.raw_records("TNDM", "0001438133", k8 + f4, now_utc=NOW)
    n1 = sm.append_raw(recs, p)
    n2 = sm.append_raw(recs, p)
    rows = [json.loads(x) for x in open(p, encoding="utf-8")]
    check(n1 == 4 and n2 == 0 and len(rows) == 4, f"Dubletten nicht doppelt ({n1}/{n2})")
    allowed = {"schema_v", "ticker", "cik", "accession", "form", "filing_date", "acceptance_utc", "items",
               "beschreibung", "primary_document", "erfasst_utc", "quelle"}
    check(all(set(r) == allowed for r in rows), "nur Felder der öffentlichen SEC-Quelle")
    r425 = [r for r in rows if r["form"] == "425"][0]
    check(r425["beschreibung"] is None and r425["items"] is None, "null bleibt null")
    blob = open(p, encoding="utf-8").read()
    check(not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob), "keine Adresse in den Rohdaten")
ka._reset_tier3_accumulators()
ka._SEC_STATE["raw"] = recs
with mock.patch.object(ka._secm, "append_raw", side_effect=OSError("voll")):
    check(ka._sec_flush_raw("egal.jsonl") == 0, "Schreibfehler → 0, keine Ausnahme")

# 9 kein Score-Leser
users = []
for f in ROOT.rglob("*.py"):
    if ".git" in f.parts or f.name in ("sec_meldungen.py", "ki_agent.py", "mock_test_edgar_fix_b.py",
                                       "run_ci_mock_tests.py"):
        continue
    if "sec_meldungen" in f.read_text(encoding="utf-8", errors="ignore"):
        users.append(str(f.relative_to(ROOT)))
check(users == [], f"kein anderer Leser der Rohdaten: {users}")
ki = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
cs = ki[ki.index("def compute_signal("):ki.index("\ndef ", ki.index("def compute_signal(") + 10)]
check("_secm" not in cs and "sec_meldungen" not in cs, "compute_signal liest die Rohdaten nicht")

print()
if FAILS:
    print(f"{len(FAILS)} FEHLER")
    sys.exit(1)
print("OK — alle Checks grün")
