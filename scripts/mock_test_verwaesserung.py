#!/usr/bin/env python3
"""Mock-Test Verwässerung (Sammlung, Easy-Entscheid 22.11.2026). Feste Uhr,
kein Netz, stabile Reihenfolge.

Prüft: Fenster-Grenzen (D−179 zählt, D−180 nicht, ET-Datum, Annahme nach dem
Report-Zeitpunkt nicht), Präfix-Regel eng/breit, Rohliste 365 Tage, null-Fälle
je Grund (nie False), „recent unvollständig“, bestehende Zusatzwerte
unverändert (Grund ``fetch_failed`` bleibt), HTTP-Status im Grund, gemerkter
CIK-Index, Pool-Schatten-CIK, Digest/Warnzeile, Lauf bricht nicht ab, kein
Score-Leser.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import material_8k as m8k  # noqa: E402
import verwaesserung as vw  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


D = "23.11.2026"                       # Berichtstag (Mo)
NOW = datetime(2026, 11, 23, 21, 50, tzinfo=timezone.utc)   # Report-Zeitpunkt 16:50 ET


def sub(rows, files=None):
    """submissions-JSON: rows = [(form, acceptanceDateTime, accession)]."""
    return {"filings": {"recent": {
        "form": [r[0] for r in rows],
        "acceptanceDateTime": [r[1] for r in rows],
        "accessionNumber": [r[2] for r in rows],
        "items": ["" for _ in rows],
        "primaryDocument": ["d.htm" for _ in rows],
        "filingDate": ["" for _ in rows]},
        "files": files or []}}


# D−179 = 2026-05-28, D−180 = 2026-05-27 (ET-Datum).
ROWS = [
    ("424B5", "2026-05-28T13:00:00.000Z", "a-179"),         # D−179 → zählt
    ("424B5", "2026-05-27T15:00:00.000Z", "a-180"),         # D−180 → nicht
    ("424B5", "2026-05-28T03:30:00.000Z", "a-et"),          # UTC 28.05., ET 27.05. 23:30 → nicht
    ("424B3", "2026-10-01T12:00:00.000Z", "b-3"),           # nur breit
    ("S-3", "2026-09-01T12:00:00.000Z", "s-3"),             # nur Rohliste
    ("4", "2026-11-20T12:00:00.000Z", "f-4"),               # nicht in Rohliste
    ("424B5", "2026-11-23T22:30:00.000Z", "a-future"),      # nach Report-Zeitpunkt → nie
    ("S-1", "2025-11-20T12:00:00.000Z", "s-1-old"),         # > 365 Tage → nicht in Rohliste
    ("8-K", "2025-06-01T12:00:00.000Z", "old-8k"),          # älteste Meldung in recent
]

src = m8k.verw_source_from_submissions(sub(ROWS), now_utc=NOW, cik="0000000123")
check("01 Quelle ok, älteste recent-Annahme, files=False",
      src["ok"] and src["recent_aelteste_utc"] == "2025-06-01T12:00:00Z"
      and src["recent_files_vorhanden"] is False, src)
forms = [(r["form"], r["accession"]) for r in src["rows"]]
check("02 Quelle: nur Präfixe 424B/S-3/S-1/F-3/F-1, keine Annahme nach Report-Zeitpunkt, sortiert",
      ("4", "f-4") not in forms and ("424B5", "a-future") not in forms
      and [r["acceptance_utc"] for r in src["rows"]] == sorted(r["acceptance_utc"] for r in src["rows"]),
      forms)

b = vw.build({"verw_quelle": src, "reason": None}, D)
check("03 D−179 zählt, D−180 nicht, ET-Datum entscheidet (UTC-Folgetag zählt nicht)",
      b["anzahl_424b5_180d"] == 1 and b["juengste_424b5_annahme_utc"] == "2026-05-28T13:00:00Z", b)
check("04 breit (424B) zählt 424B3 mit, eng nicht",
      b["verw_424b_180d"] is True and b["anzahl_424b_180d"] == 2
      and b["juengste_424b_annahme_utc"] == "2026-10-01T12:00:00Z")
check("05 Annahme nach dem Report-Zeitpunkt zählt nie",
      all(r["accession"] != "a-future" for r in b["rohliste"]))
check("06 Rohliste 365 Tage: S-3 drin, S-1 von vor > 365 Tagen und Form 4 nicht",
      [r["accession"] for r in b["rohliste"]] == ["a-180", "a-et", "a-179", "s-3", "b-3"],
      [r["accession"] for r in b["rohliste"]])
check("07 geprueft, Schema, Quelle, vollständig",
      b["geprueft"] is True and b["schema_v"] == 1 and b["grund"] is None
      and b["rohliste_vollstaendig"] is True and b["cik"] == "0000000123")

# keine Treffer → False (nicht None), weil vollständig geprüft
b0 = vw.build({"verw_quelle": m8k.verw_source_from_submissions(
    sub([("8-K", "2026-11-01T12:00:00Z", "x")]), now_utc=NOW, cik="1")}, D)
check("08 geprüft ohne Meldung → False / 0", b0["verw_424b5_180d"] is False
      and b0["anzahl_424b5_180d"] == 0 and b0["verw_424b_180d"] is False)

# null-Fälle je Grund — nie False
cases = {
    "edgar_aus": vw.build(None, D, material_8k_enabled=False),
    "edgar_nicht_gesammelt": vw.build(None, D),
    "keine eindeutige CIK": vw.build(m8k._empty_extras("no_cik"), D),
    "http_403": vw.build(m8k._empty_extras("fetch_failed", "9", verw_grund="http_403"), D),
    "Zeitbudget erschöpft": vw.build(m8k._empty_extras("budget_skip"), D),
    "filings.recent fehlt": vw.build({"verw_quelle": m8k.verw_source_from_submissions(
        {"filings": {}}, now_utc=NOW, cik="9")}, D),
}
for g, blk in cases.items():
    check(f"09 null mit Grund „{g}“, nie False",
          blk["geprueft"] is False and blk["grund"] == g
          and blk["verw_424b5_180d"] is None and blk["verw_424b_180d"] is None, blk)

# recent unvollständig: Zusatzdateien vorhanden, älteste recent-Annahme im Fenster
inc = vw.build({"verw_quelle": m8k.verw_source_from_submissions(
    sub([("424B5", "2026-10-01T12:00:00Z", "z"), ("4", "2026-07-01T12:00:00Z", "y")],
        files=[{"name": "CIK-submissions-001.json"}]), now_utc=NOW, cik="9")}, D)
check("10 recent unvollständig → null mit Grund, Rohliste trotzdem da, nicht vollständig",
      inc["geprueft"] is False and inc["grund"] == "recent unvollständig"
      and inc["verw_424b5_180d"] is None and inc["rohliste_vollstaendig"] is False
      and len(inc["rohliste"]) == 1, inc)
ok_files = vw.build({"verw_quelle": m8k.verw_source_from_submissions(
    sub([("424B5", "2026-10-01T12:00:00Z", "z"), ("4", "2026-04-01T12:00:00Z", "y")],
        files=[{"name": "x"}]), now_utc=NOW, cik="9")}, D)
check("11 Zusatzdateien, aber recent reicht vor das Fenster → geprüft",
      ok_files["geprueft"] is True and ok_files["verw_424b5_180d"] is True
      and ok_files["rohliste_vollstaendig"] is False)

check("12 deterministisch: gleiche Eingabe → gleiches Ergebnis",
      json.dumps(vw.build({"verw_quelle": src}, D), sort_keys=True)
      == json.dumps(vw.build({"verw_quelle": src}, D), sort_keys=True))
check("13 kaputte Eingaben brechen nicht ab",
      vw.build({"verw_quelle": {"ok": True, "rows": [{"acceptance_utc": "kaputt"}]}}, D)["geprueft"] is True
      and vw.build({"verw_quelle": src}, "kein Datum")["grund"] == "berichtstag_unlesbar")

# ── material_8k: bestehende Werte unverändert, HTTP-Status, CIK-Index ────────
CT = {"0": {"cik_str": 123, "ticker": "AAA", "title": "A"},
      "1": {"cik_str": 456, "ticker": "BBB", "title": "B"}}


def gj_factory(fail_for=None, status=403):
    def gj(url, ua, timeout):
        if "company_tickers" in url:
            return CT
        if fail_for and fail_for in url:
            raise m8k.HttpStatusError(status)
        return sub(ROWS)
    return gj


extras: dict = {}
res = m8k.collect_material_8k_events(["AAA", "BBB", "ZZZ"], now_utc=NOW, ua="t",
                                     get_json=gj_factory(fail_for="CIK0000000456"),
                                     get_text=lambda *a: "", extras_out=extras,
                                     run_budget_s=0, sleep_s=0)
check("14 HTTP 403: material_8k_events-Grund bleibt fetch_failed, Zusatzwerte-Grund bleibt fetch_failed",
      res["BBB"]["reason"] == "fetch_failed" and extras["BBB"]["reason"] == "fetch_failed"
      and extras["BBB"]["window"]["reason"] == "fetch_failed")
check("15 … aber der Verwässerungs-Grund nennt den Status (http_403)",
      vw.build(extras["BBB"], D)["grund"] == "http_403")
check("16 keine CIK → „keine eindeutige CIK“",
      vw.build(extras["ZZZ"], D)["grund"] == "keine eindeutige CIK")
ex = extras["AAA"]
ref = m8k._extras_from_submissions(sub(ROWS), now_utc=NOW, cik="0000000123",
                                   lookback_days=14, qualifying_items=("2.02",), cap_n=16)
check("17 bestehende Zusatzwerte (window, last_2_02, reason) haben dieselbe Form wie vorher",
      set(ex) == {"window", "last_2_02", "reason", "verw_quelle"}
      and set(ref["window"]) == {"collected", "reason", "cik", "truncated", "lookback_days", "events"})
idx, g = m8k.last_cik_index()
check("18 CIK-Index gemerkt, ohne weiteren Abruf auflösbar",
      g is None and m8k.resolve_cik("AAA", idx) == "0000000123")
m8k.collect_material_8k_events(["AAA"], now_utc=NOW, ua="t",
                               get_json=lambda u, a, t: (_ for _ in ()).throw(m8k.HttpStatusError(500)),
                               get_text=lambda *a: "", extras_out={}, run_budget_s=0, sleep_s=0)
idx2, g2 = m8k.last_cik_index()
check("19 Tickerliste gescheitert → Index leer mit Grund", idx2 is None
      and g2 == "tickerliste_fehlgeschlagen")

# ── Pool-Schatten: CIK je Zeile aus dem gemerkten Index ─────────────────────
import pool_schatten as ps  # noqa: E402
m8k._LAST_CIK_INDEX.update({"index": m8k.build_cik_index(CT), "grund": None})
fn = ps._default_cik_fn()
check("20 Pool-Schatten-CIK: bekannt → CIK, unbekannt → null + Grund",
      fn("AAA") == ("0000000123", None) and fn("QQQ") == (None, "keine eindeutige CIK"))
m8k._LAST_CIK_INDEX.update({"index": None, "grund": "tickerliste_fehlgeschlagen"})
check("21 ohne Index → null mit Grund des Index", ps._default_cik_fn()("AAA")
      == (None, "tickerliste_fehlgeschlagen"))

# ── Digest / Warnzeile / Log ────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    bp = pathlib.Path(td) / "bh.json"
    good = vw.build({"verw_quelle": src}, D)
    bp.write_text(json.dumps([
        {"date": "20.11.2026", "ticker": "OLD", vw.FIELD: good},
        {"date": D, "ticker": "A", vw.FIELD: good},
        {"date": D, "ticker": "B", vw.FIELD: b0},
        {"date": D, "ticker": "C", vw.FIELD: cases["http_403"]}]))
    line = vw.digest_line(bp)
    check("22 Digest-Zeile: Zählung jüngster Tag mit Gründen",
          line == "🧾 Verwässerung (23.11.): 1 von 3 mit 424B5 · 1 mit 424B · 1 unbekannt (http_403 1)",
          line)
    check("23 nicht alle unbekannt → keine Warnzeile", vw.warn_line(bp) is None)
    bp.write_text(json.dumps([{"date": D, "ticker": "A", vw.FIELD: cases["http_403"]},
                              {"date": D, "ticker": "B", vw.FIELD: cases["keine eindeutige CIK"]}]))
    w = vw.warn_line(bp)
    check("24 alle unbekannt → Warnzeile mit Gründen",
          w is not None and w.startswith("🟡") and "alle 2 unbekannt" in w, w)
    check("25 Datei fehlt → keine Warnung; kaputt → Warnung",
          vw.warn_line(pathlib.Path(td) / "x.json") is None
          and (bp.write_text("{kaputt") or True) and (vw.warn_line(bp) or "").startswith("🟡"))
    check("26 Digest-Zeile unter 200 Bytes", len(line.encode()) < 200)
check("27 Log-Zeile zählt", vw.log_line([{vw.FIELD: good}, {vw.FIELD: cases["http_403"]}])
      == "[verwaesserung] 2 neue Einträge: geprüft 1 · 424B5 1 · 424B 1 · unbekannt 1 (http_403 1)")

# ── Verdrahtung / kein Score-Leser ──────────────────────────────────────────
bh = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
check("28 Backtest-Eintrag: Feld aus build(m8k_extras, report_date)",
      "entry[verwaesserung_module.FIELD] = verwaesserung_module.build(" in bh
      and "m8k_extras_by_ticker.get(s[\"ticker\"]), report_date" in bh)
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("29 Digest verdrahtet (Zeile + Warnzeile)",
      "verwaesserung.digest_line(" in dg and "[_vw_warn]" in dg)
import config  # noqa: E402
check("30 S10_OBSERVED enthält verwaesserung", "verwaesserung" in config.S10_OBSERVED_FIELDS)
for f in ("generate_report.py", "ki_agent.py", "health_check.py", "templates/card.jinja",
          "templates/head.jinja"):
    t = (ROOT / f).read_text(encoding="utf-8")
    check(f"31 kein Leser in {f}", "verwaesserung" not in t)

# ── Nachtrag 22.11.2026: raise-frei, interner Fehler sichtbar ───────────────
bad = vw.build({"verw_quelle": {"ok": True, "cik": "0000000005", "rows": [1, "x", None]}}, D)
check("32 Nicht-Dict-Zeilen → null-Block „interner_fehler: <Typ>“, keine Ausnahme",
      bad["geprueft"] is False and bad["grund"].startswith("interner_fehler: ")
      and bad["verw_424b5_180d"] is None and bad["verw_424b_180d"] is None
      and bad["cik"] == "0000000005", bad)
bad2 = vw.build({"verw_quelle": {"ok": True, "rows": [{"acceptance_utc": object(), "form": 5}],
                                 "recent_aelteste_utc": 7, "recent_files_vorhanden": "ja"}}, D)
check("33 kaputte Zeitstempel-/Form-Typen → kein Wurf, Block mit Grund",
      bad2["geprueft"] is False and bad2["grund"] and bad2["verw_424b5_180d"] is None, bad2)
check("34 log_line wirft nie", vw.log_line([1, None, "x"]).startswith("[verwaesserung]")
      and vw.log_line(None).startswith("[verwaesserung]"))
with tempfile.TemporaryDirectory() as td:
    bp = pathlib.Path(td) / "bh.json"
    bp.write_text(json.dumps([{"date": D, "ticker": "A", vw.FIELD: good},
                              {"date": D, "ticker": "B", vw.FIELD: bad}]))
    dl = vw.digest_line(bp)
    check("35 Digest: interner_fehler zählt als unbekannt mit Grund",
          "1 unbekannt (interner_fehler: AttributeError 1)" in dl, dl)
    wl = vw.warn_line(bp) or ""
    check("36 interner_fehler → Warnzeile, auch wenn nicht alle unbekannt",
          wl.startswith("🟡") and "interner Fehler bei 1 von 2" in wl, wl)


def _append_level_test():
    """Ende-zu-Ende über den ECHTEN Schreibpfad: wirft der Kern von build(),
    werden die Tages-Einträge trotzdem geschrieben (kein Netz, Sammler gefakt)."""
    import io
    import logging
    import os
    import types
    from zoneinfo import ZoneInfo
    sys.path.insert(0, str(ROOT / "scripts"))
    from mock_test_outer_page_golden import gr  # noqa: F401  (stubbt yfinance/requests/bs4)
    for _m in ("yfinance", "bs4", "deep_translator", "lxml"):
        sys.modules.setdefault(_m, types.ModuleType(_m))
    for _attr in ("download", "Ticker"):
        if not hasattr(sys.modules["yfinance"], _attr):
            setattr(sys.modules["yfinance"], _attr, lambda *a, **k: None)
    import backtest_history as bh
    et = ZoneInfo("America/New_York")
    now_et = datetime(2026, 11, 23, 17, 40, tzinfo=et)
    rd = now_et.strftime("%d.%m.%Y")

    def _stock(t):
        return {"ticker": t, "score": 70.0, "price": 10.0, "short_float": 25.0,
                "short_ratio": 5.0, "rel_volume": 2.4, "float_shares": 1e8,
                "avg_vol_20d": 1e6, "hist_5d": [], "score_trend_bonus_pts": 0.0,
                "agent_boost_factor": 1.0, "finra_bonus_pts": 0.0,
                "short_float_source": "yfinance",
                "finra_data": {"trend": "no_data", "history": [], "si_trend_source": "finra"},
                "sparkline_view": None, "bar_date": now_et.strftime("%Y-%m-%d")}

    real_collect = m8k.collect_material_8k_events

    def fake_collect(tickers, *, now_utc=None, extras_out=None, **kw):
        return real_collect(tickers, now_utc=NOW, ua="t", get_json=gj_factory(),
                            get_text=lambda *a: "", company_tickers=CT, sleep_s=0,
                            run_budget_s=0, extras_out=extras_out)

    def boom(*a, **k):
        raise RuntimeError("absichtlich")

    orig_c = bh.material_8k_module.collect_material_8k_events
    orig_b = bh.verwaesserung_module._build
    bh.material_8k_module.collect_material_8k_events = fake_collect
    bh.verwaesserung_module._build = boom
    cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="mt_verw_")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    logging.getLogger("verwaesserung").addHandler(h)
    try:
        os.chdir(tmp)
        json.dump({"signals": {}}, open("agent_signals.json", "w"))
        json.dump([], open("backtest_history.json", "w"))
        n = bh._append_backtest_entries(
            [_stock("AAA"), _stock("BBB")], rd, pool_size=2,
            compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
            safe_float_fn=gr._safe_float, now_et=now_et)
        rows = json.load(open("backtest_history.json"))
    finally:
        os.chdir(cwd)
        logging.getLogger("verwaesserung").removeHandler(h)
        bh.material_8k_module.collect_material_8k_events = orig_c
        bh.verwaesserung_module._build = orig_b
    by = {r["ticker"]: r for r in rows}
    check("37 _append_backtest_entries: Ausnahme im Kern → beide Einträge trotzdem geschrieben",
          n == 2 and set(by) == {"AAA", "BBB"}, (n, list(by)))
    check("38 … mit null-Block „interner_fehler: RuntimeError“ und Log-Warnung",
          all(by[t][vw.FIELD]["grund"] == "interner_fehler: RuntimeError"
              and by[t][vw.FIELD]["verw_424b5_180d"] is None for t in by)
          and "interner Fehler" in buf.getvalue())
    check("39 bestehende Felder unberührt (material_8k_events gesammelt)",
          all((by[t].get("material_8k_events") or {}).get("collected") is True for t in by))


_append_level_test()

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle Checks grün.")
