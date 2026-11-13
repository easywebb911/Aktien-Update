#!/usr/bin/env python3
"""Tests Klasse „bekannt (geprüft)“ im Wahrheits-Abgleich (Easy-Auftrag 13.11.2026).

Ohne Netz, ohne pandas/yfinance (künstliche Kursreihen aus mock_test_truth_check).

 1  Liste: echte Datei truth_check_known.json — jeder Eintrag hat alle Pflichtfelder
    (Grund, Verweis, Entscheid-Datum, Werte); Fail-safe: fehlende/kaputte Datei oder
    unvollständiger Eintrag greift nicht.
 2  apply_known: bekannter Fall → bekannt; verschobener gespeicherter ODER neu
    berechneter Wert → abweichung; neuer Fall → abweichung; neu_adjustiert bleibt.
 3  Die echten 8 Abweichungen aus dem Log vom 13.11.2026 (03:20 UTC): Gruppe (1)
    → bekannt, die übrigen 5 bleiben abweichung; S16 meldet weiter crit, aber ohne
    Gruppe (1); nur Gruppe (1) → kein S16-Fail; Digest-Zeile zeigt „bekannt (geprüft)“.
 4  End-to-end über truth_check.run: Eintrag passt → Zähler bekannt, nicht abweichung;
    Eintrag passt nicht mehr → abweichung. Determinismus (zweimal gleich).
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import health_check as hc  # noqa: E402
import truth_check as tc  # noqa: E402
import mock_test_truth_check as mt  # noqa: E402

_fails: list[str] = []
TOL = float(config.TRUTH_CHECK_TOLERANCE_PP)


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


# Die echten 8 Abweichungen, Log-Zeile 2026-11-13T03:20:51Z (wörtlich).
REAL_8 = [
    {"datei": "export", "ticker": "GRPN", "date": "26.10.2026", "feld": "return_10d_t1", "alt": -24.3, "neu": -24.27, "klasse": "abweichung"},
    {"datei": "export", "ticker": "FRGT", "date": "27.10.2026", "feld": "return_5d_t1", "alt": -1.47, "neu": -1.5, "klasse": "abweichung"},
    {"datei": "exit_shadow", "ticker": "GRPN", "date": "27.10.2026", "feld": "forward_10d", "alt": -24.3, "neu": -24.27, "klasse": "abweichung"},
    {"datei": "export", "ticker": "AMCX", "date": "15.07.2026", "feld": "entry_past_return_5d", "alt": 5.11, "neu": 5.16, "klasse": "abweichung"},
    {"datei": "export", "ticker": "ARCT", "date": "01.09.2026", "feld": "entry_past_return_5d", "alt": 5.08, "neu": 5.12, "klasse": "abweichung"},
    {"datei": "export", "ticker": "BJDX", "date": "14.07.2026", "feld": "return_10d_t1", "alt": -34.92, "neu": -34.89, "klasse": "abweichung"},
    {"datei": "export", "ticker": "BJDX", "date": "15.07.2026", "feld": "return_10d", "alt": -34.92, "neu": -34.89, "klasse": "abweichung"},
    {"datei": "export", "ticker": "BJDX", "date": "05.08.2026", "feld": "return_10d_t1", "alt": -18.32, "neu": -18.35, "klasse": "abweichung"},
]
GROUP1 = {("export", "GRPN", "26.10.2026"), ("export", "FRGT", "27.10.2026"), ("exit_shadow", "GRPN", "27.10.2026")}


def _known():
    return tc.load_known(ROOT / tc.KNOWN_FILE)


def test_list():
    print("1 Liste")
    raw = json.loads((ROOT / tc.KNOWN_FILE).read_text(encoding="utf-8"))
    items = raw.get("eintraege") or []
    check("Datei hat Einträge", len(items) == 3, len(items))
    for e in items:
        miss = [k for k in tc.KNOWN_REQUIRED if e.get(k) in (None, "")]
        check(f"Eintrag {e.get('ticker')} {e.get('date')} {e.get('feld')}: Pflichtfelder", not miss, miss)
        check(f"  Verweis + Grund nicht leer, Datum ISO",
              len(str(e.get("grund"))) > 20 and str(e.get("verweis")).strip() != ""
              and len(str(e.get("entscheid_datum"))) == 10 and str(e.get("entscheid_datum"))[4] == "-")
    check("alle Einträge werden geladen", len(_known()) == len(items))
    with tempfile.TemporaryDirectory() as t:
        p = pathlib.Path(t) / "k.json"
        check("fehlende Datei → leer (alles alarmiert)", tc.load_known(p) == [])
        p.write_text("{kaputt")
        check("kaputte Datei → leer", tc.load_known(p) == [])
        p.write_text(json.dumps({"eintraege": [dict(items[0], grund="")]}))
        check("Eintrag ohne Grund greift nicht", tc.load_known(p) == [])
        p.write_text(json.dumps({"eintraege": [dict(items[0], vergleich=None)]}))
        check("Eintrag ohne Vergleichswert greift nicht", tc.load_known(p) == [])


def test_apply():
    print("2 apply_known")
    k = _known()
    d0 = dict(REAL_8[0])
    check("bekannter Fall → bekannt + Verweis", tc.apply_known([d0], k, TOL)[0]["klasse"] == "bekannt"
          and "rendite-forward" in tc.apply_known([d0], k, TOL)[0]["verweis"])
    check("gespeicherter Wert verschoben (+0,03) → abweichung",
          tc.apply_known([dict(d0, alt=-24.27)], k, TOL)[0]["klasse"] == "abweichung")
    check("neu berechneter Wert verschoben (−0,05) → abweichung",
          tc.apply_known([dict(d0, neu=-24.32)], k, TOL)[0]["klasse"] == "abweichung")
    check("innerhalb Toleranz (+0,02) → bekannt",
          tc.apply_known([dict(d0, neu=-24.25)], k, TOL)[0]["klasse"] == "bekannt")
    check("neuer Fall → abweichung", tc.apply_known([dict(d0, ticker="XYZ")], k, TOL)[0]["klasse"] == "abweichung")
    check("anderes Feld → abweichung", tc.apply_known([dict(d0, feld="return_10d")], k, TOL)[0]["klasse"] == "abweichung")
    check("neu_adjustiert bleibt", tc.apply_known([dict(d0, klasse="neu_adjustiert")], k, TOL)[0]["klasse"] == "neu_adjustiert")
    check("leere Liste → alles abweichung", all(d["klasse"] == "abweichung" for d in tc.apply_known(REAL_8, [], TOL)))
    check("Eingabe unverändert (pure)", d0["klasse"] == "abweichung")


def _line(ts, devs, prev=False):
    rows = {}
    for d in devs:
        key = (d["datei"], d["ticker"], d["date"])
        rows.setdefault(key, []).append(d["klasse"])
    n_ab = sum(1 for v in rows.values() if "abweichung" in v)
    n_be = sum(1 for v in rows.values() if "abweichung" not in v and "bekannt" in v)
    return {"schema_v": 1, "run_ts": ts, "n_zeilen": 36, "stimmt": 36 - len(rows), "abweichung": n_ab,
            "bekannt": n_be, "neu_adjustiert": 0, "nicht_pruefbar": 0,
            "unbekannt": {"yahoo_fehler": 0, "ausdruecklich_leer": 0, "rate_limit": 0},
            "max_abs_delta": 0.05, "abweichungen": devs, "ticker_geprueft": [], "ticker_unbekannt": {}}


def _s16(lines):
    with tempfile.TemporaryDirectory() as t:
        p = pathlib.Path(t) / "log.jsonl"
        p.write_text("".join(json.dumps(x) + "\n" for x in lines))
        res = hc.evaluate_s16_truth_check(str(p), now_utc=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc))
        dl = hc.truth_check_digest_line(str(p))
    return res, dl


def test_real_8():
    print("3 Die echten 8 Fälle vom 13.11.2026")
    k = _known()
    cls = tc.apply_known(REAL_8, k, TOL)
    bek = {(d["datei"], d["ticker"], d["date"]) for d in cls if d["klasse"] == "bekannt"}
    check("genau Gruppe (1) → bekannt", bek == GROUP1, bek)
    check("übrige 5 bleiben abweichung", sum(d["klasse"] == "abweichung" for d in cls) == 5)
    prev_old = _line("2026-11-12T03:42:53Z", [dict(d) for d in REAL_8[:5]])   # alter Lauf ohne Klasse bekannt
    last = _line("2026-11-13T03:20:51Z", cls)
    res, dl = _s16([prev_old, last])
    det = res[0]["detail"] if res else ""
    check("S16 weiter crit (Gruppe 2 + BJDX ungeprüft)", res and res[0]["severity"] == "crit", res)
    check("S16-Text nennt Gruppe (1) nicht", "GRPN" not in det and "FRGT" not in det, det)
    check("S16: 5 Zeilen weichen ab", "5 Zeilen weichen ab" in det, det)
    only1 = tc.apply_known(REAL_8[:3], k, TOL)
    res2, dl2 = _s16([_line("2026-11-12T03:42:53Z", [dict(d) for d in REAL_8[:3]]),
                      _line("2026-11-13T03:20:51Z", only1)])
    check("nur Gruppe (1) → kein S16-Fail (auch nicht „2 Läufe“)", res2 == [], res2)
    check("Digest-Zeile: 3 bekannt (geprüft)", "3 bekannt (geprüft)" in dl2 and "0 Abweichung" in dl2, dl2)
    print("    Beispiel-Digest-Zeile:", dl)


def test_end_to_end():
    print("4 End-to-end truth_check.run")
    good = mt.expected_row("AAA", mt.ENTRY)
    bad = dict(good, return_5d=round(good["return_5d"] + 0.05, 2))

    def run_with(entries):
        orig = (config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS)
        config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS = 0, 2
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = pathlib.Path(td)
                mt._setup(tmp, [bad], [], mt.FRESH_STATE)
                if entries is not None:
                    (tmp / tc.KNOWN_FILE).write_text(json.dumps({"eintraege": entries}))
                return tc.run(mt.NOW, root=tmp, fetch_fn=mt.Fetcher())
        finally:
            config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS = orig
    base = run_with(None)
    check("ohne Liste: 1 abweichung", base["abweichung"] == 1 and base["bekannt"] == 0, base)
    e = {"datei": "export", "ticker": "AAA", "date": bad["date"], "feld": "return_5d", "alt": bad["return_5d"],
         "vergleich": good["return_5d"], "grund": "Testfall synthetisch, bekannt und geprüft",
         "verweis": "Test", "entscheid_datum": "2026-11-13"}
    l1 = run_with([e])
    check("passender Eintrag: bekannt statt abweichung", l1["abweichung"] == 0 and l1["bekannt"] == 1, l1)
    check("Log-Eintrag klasse bekannt + Verweis", l1["abweichungen"][0]["klasse"] == "bekannt"
          and l1["abweichungen"][0]["verweis"] == "Test", l1["abweichungen"])
    l2 = run_with([dict(e, vergleich=good["return_5d"] + 0.1)])
    check("Eintrag passt nicht mehr: abweichung", l2["abweichung"] == 1 and l2["bekannt"] == 0, l2)
    l3 = run_with([e])
    strip = lambda x: {k: v for k, v in x.items() if k != "run_ts"}  # noqa: E731
    check("deterministisch (gleiche Eingabe → gleiche Klassierung)", strip(l1) == strip(l3))


def main() -> int:
    for fn in (test_list, test_apply, test_real_8, test_end_to_end):
        fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAIL: {_fails}")
        return 1
    print("Alle truth_check_known-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
