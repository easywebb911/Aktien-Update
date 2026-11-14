#!/usr/bin/env python3
"""Mock-Tests Gewinn-Felder (Easy-Entscheid 14.11.2026) — synthetische Fälle,
kein Netz.

Felder (forward-only, additiv, S10_OBSERVED, kein Score-/Filter-/Push-Effekt):
  • ``earnings_surprise_pit`` — Überraschung zum Laufzeitpunkt (Wert = Karten-
    Wert, Quelle, Quartalsende, Abrufzeit) + jüngstes 8-K Item 2.02.
  • ``material_8k_events_14d`` — zweites 8-K-Fenster mit 14 Kalendertagen;
    ``material_8k_events`` (5 Tage) bleibt byte-gleich.

Gruppen: A material_8k (pure + Sammler), B Überraschung (Karten-Wert gleich),
C Backtest-Eintrag Ende-zu-Ende + Determinismus, D Digest-Zeile, E Isolation
(Score/Freeze lesen die Felder nicht), F config/S10.
"""
from __future__ import annotations

import copy
import io
import json
import logging
import os
import pathlib
import re
import sys
import tempfile
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# pandas: echte Bibliothek, falls vorhanden; sonst Ersatz mit einem kleinen
# DataFrame-Nachbau (CI hat kein pandas).
try:
    import pandas as _real_pd  # noqa: F401
    HAVE_PD = True
except Exception:
    HAVE_PD = False

from mock_test_outer_page_golden import gr  # noqa: E402  (stubbt yfinance/requests/bs4)

for _m in ("yfinance", "bs4", "deep_translator", "lxml"):
    sys.modules.setdefault(_m, types.ModuleType(_m))
for _attr in ("download", "Ticker"):
    if not hasattr(sys.modules["yfinance"], _attr):
        setattr(sys.modules["yfinance"], _attr, lambda *a, **k: None)

import backtest_history as bh  # noqa: E402
import config  # noqa: E402
import health_check as hc  # noqa: E402
import material_8k as m8  # noqa: E402

ET = ZoneInfo("America/New_York")
FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ── synthetische Daten ───────────────────────────────────────────────────────
NOW = datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc)   # Mo 17:00 ET


def _subs():
    """submissions.recent mit 8-K in 2, 9, 20, 80 Tagen Alter + ein 10-Q +
    ein 8-K NACH dem Report-Zeitpunkt (darf nie zählen)."""
    rows = [
        ("8-K", "2.02,9.01", "2026-11-14T21:05:00.000Z", "0001-26-000010"),  # 2 T, 2.02
        ("8-K", "8.01", "2026-11-07T13:00:00.000Z", "0001-26-000009"),        # 9 T
        ("8-K", "5.02", "2026-10-27T13:00:00.000Z", "0001-26-000008"),        # 20 T
        ("10-Q", "", "2026-11-13T13:00:00.000Z", "0001-26-000007"),
        ("8-K", "2.02,9.01", "2026-08-28T20:10:00.000Z", "0001-26-000005"),  # 80 T, 2.02
        ("8-K", "2.02", "2026-11-17T21:00:00.000Z", "0001-26-000011"),       # Zukunft
        ("8-K", "9.01", "2026-11-12T13:00:00.000Z", "0001-26-000006"),       # kein Qualifier
    ]
    return {"filings": {"recent": {
        "form": [r[0] for r in rows], "items": [r[1] for r in rows],
        "acceptanceDateTime": [r[2] for r in rows],
        "accessionNumber": [r[3] for r in rows],
        "primaryDocument": ["d.htm"] * len(rows)}}}


CT = {"0": {"cik_str": 1234, "ticker": "TEST", "title": "Test Corp"}}


def _fake_get_json(url, ua, timeout):
    if "submissions" in url:
        return _subs()
    return {"directory": {"item": []}}


# ── A: material_8k ───────────────────────────────────────────────────────────
def test_a():
    last = m8.select_last_item_8k(_subs(), now_utc=NOW, item_code="2.02")
    check("A1 letztes 2.02 = jüngstes vor dem Report-Zeitpunkt (Zukunft ignoriert)",
          last == {"acceptance_datetime": "2026-11-14T21:05:00.000Z",
                   "accession": "0001-26-000010"}, str(last))
    check("A2 kein 2.02 → None",
          m8.select_last_item_8k({"filings": {"recent": {"form": ["8-K"], "items": ["8.01"],
                                  "acceptanceDateTime": ["2026-11-10T10:00:00Z"],
                                  "accessionNumber": ["x"]}}}, now_utc=NOW, item_code="2.02") is None)
    check("A3 leeres/kaputtes JSON → None",
          m8.select_last_item_8k(None, now_utc=NOW, item_code="2.02") is None)
    ex = m8._extras_from_submissions(_subs(), now_utc=NOW, cik="0000001234",
                                     lookback_days=14,
                                     qualifying_items=config.MATERIAL_8K_QUALIFYING_ITEMS,
                                     cap_n=16)
    accs = [e["accession"] for e in ex["window"]["events"]]
    check("A4 14-Tage-Fenster: 2 T + 9 T drin, 20 T/80 T/Zukunft/10-Q/9.01 draußen",
          accs == ["0001-26-000009", "0001-26-000010"], str(accs))
    check("A5 14-T-Events ohne matched_terms/_primary_document (nur Rohdaten)",
          all(set(e) == {"acceptance_datetime", "accession", "cik", "item_codes"}
              for e in ex["window"]["events"]))
    check("A6 14-T-Wrapper trägt lookback_days=14, collected=True",
          ex["window"]["lookback_days"] == 14 and ex["window"]["collected"] is True)
    capped = m8._extras_from_submissions(_subs(), now_utc=NOW, cik="c", lookback_days=14,
                                         qualifying_items=config.MATERIAL_8K_QUALIFYING_ITEMS,
                                         cap_n=1)
    check("A7 Cap → truncated=True, erste N nach acceptance",
          capped["window"]["truncated"] is True and len(capped["window"]["events"]) == 1
          and capped["window"]["events"][0]["accession"] == "0001-26-000009")
    kw = dict(now_utc=NOW, ua="t", get_json=_fake_get_json,
              get_text=lambda *a: "", company_tickers=CT, sleep_s=0, run_budget_s=0)
    base = m8.collect_material_8k_events(["TEST"], **kw)
    extras: dict = {}
    with_x = m8.collect_material_8k_events(["TEST"], extras_out=extras, **kw)
    check("A8 material_8k_events byte-gleich mit/ohne extras_out",
          json.dumps(base, sort_keys=True) == json.dumps(with_x, sort_keys=True))
    w5 = [e["accession"] for e in base["TEST"]["events"]]
    check("A9 5-Tage-Feld unverändert (nur 2 T)", w5 == ["0001-26-000010"], str(w5))
    check("A10 extras: 14-T + letztes 2.02 aus demselben Abruf",
          [e["accession"] for e in extras["TEST"]["window"]["events"]]
          == ["0001-26-000009", "0001-26-000010"]
          and extras["TEST"]["last_2_02"]["accession"] == "0001-26-000010")
    calls = []

    def _counting(url, ua, timeout):
        calls.append(url)
        return _fake_get_json(url, ua, timeout)
    m8.collect_material_8k_events(["TEST"], **{**kw, "get_json": _counting})
    n0 = len(calls)
    calls.clear()
    m8.collect_material_8k_events(["TEST"], extras_out={}, **{**kw, "get_json": _counting})
    check("A11 kein zusätzlicher EDGAR-Abruf durch extras", len(calls) == n0, f"{n0} vs {len(calls)}")
    ex2: dict = {}
    m8.collect_material_8k_events(["NOPE"], extras_out=ex2, **kw)
    check("A12 keine CIK → extras collected=False, Grund no_cik, last None",
          ex2["NOPE"]["window"]["collected"] is False and ex2["NOPE"]["reason"] == "no_cik"
          and ex2["NOPE"]["last_2_02"] is None)
    ex3: dict = {}
    m8.collect_material_8k_events(["TEST"], extras_out=ex3,
                                  **{**kw, "get_json": lambda *a: None})
    check("A13 Abruf fehlgeschlagen → Grund fetch_failed", ex3["TEST"]["reason"] == "fetch_failed")
    ex4: dict = {}
    m8.collect_material_8k_events(["TEST"], extras_out=ex4, **{**kw, "company_tickers": {}})
    check("A14 leerer CIK-Index → Grund fetch_failed", ex4["TEST"]["reason"] == "fetch_failed")


# ── B: Überraschung ──────────────────────────────────────────────────────────
class _FakeFrame:
    """Minimaler DataFrame-Nachbau für die CI (kein pandas)."""
    def __init__(self, rows, index):
        self._rows, self.index = rows, index
        self.columns = list(rows[0].keys()) if rows else []
        self.empty = not rows

    def sort_index(self, ascending=True):
        pairs = sorted(zip(self.index, self._rows), key=lambda p: p[0], reverse=not ascending)
        return _FakeFrame([p[1] for p in pairs], [p[0] for p in pairs])

    def iterrows(self):
        return iter(zip(self.index, self._rows))


class _D:
    def __init__(self, y, m, d):
        self._d = datetime(y, m, d).date()

    def date(self):
        return self._d

    def __lt__(self, o):
        return self._d < o._d


def _frame(rows, dates):
    if HAVE_PD:
        import pandas as pd
        return pd.DataFrame(rows, index=pd.to_datetime(dates))
    sys.modules["pandas"].DataFrame = _FakeFrame
    return _FakeFrame(rows, [_D(*map(int, d.split("-"))) for d in dates])


if not HAVE_PD:
    _pd = types.ModuleType("pandas")
    _pd.DataFrame = _FakeFrame
    sys.modules["pandas"] = _pd


def _old_card(hist):
    """Der Karten-Wert nach der Logik VOR diesem PR (Referenz)."""
    lower = {c.lower().replace(" ", ""): c for c in hist.columns}
    ca = lower.get("epsactual") or lower.get("reportedeps") or lower.get("actual")
    ce = lower.get("epsestimate") or lower.get("estimate") or lower.get("estimateeps")
    for _, row in hist.sort_index(ascending=False).iterrows():
        a, e = row.get(ca), row.get(ce)
        if a is None or e is None:
            continue
        a, e = float(a), float(e)
        if e == 0:
            continue
        pct = (a - e) / abs(e) * 100
        return {"beat": a >= e, "pct": round(pct, 1)}
    return None


def test_b():
    rows = [{"epsEstimate": -0.20, "epsActual": -0.15, "methodology": "normalized"},
            {"epsEstimate": 0.10, "epsActual": 0.05, "methodology": "normalized"}]
    h = _frame(rows, ["2026-09-30", "2026-06-30"])
    karte, rec = gr._earnings_surprise_from_hist(h, "2026-11-16T22:00:01+00:00")
    check("B1 Karten-Wert = Logik vor diesem PR", karte == _old_card(h), f"{karte} vs {_old_card(h)}")
    check("B2 Record: Wert = Karten-Wert, Quartalsende, Quelle, Abrufzeit",
          rec["collected"] is True and rec["surprise_pct"] == karte["pct"] == 25.0
          and rec["beat"] is True and rec["quartalsende"] == "2026-09-30"
          and rec["neuestes_quartalsende"] == "2026-09-30"
          and rec["abgerufen_utc"] == "2026-11-16T22:00:01+00:00"
          and rec["quelle"].startswith("yfinance earnings_history")
          and rec["eps_actual"] == -0.15 and rec["eps_estimate"] == -0.20
          and rec["methodik"] == "normalized", str(rec))
    rows2 = [{"epsEstimate": 0.0, "epsActual": 0.02}, {"epsEstimate": 0.10, "epsActual": 0.12}]
    h2 = _frame(rows2, ["2026-09-30", "2026-06-30"])
    k2, r2 = gr._earnings_surprise_from_hist(h2, "t")
    check("B3 jüngste Zeile übersprungen (Schätzung 0) → sichtbar: Quartalsende ≠ neuestes",
          k2 == _old_card(h2) and r2["quartalsende"] == "2026-06-30"
          and r2["neuestes_quartalsende"] == "2026-09-30", str(r2))
    k3, r3 = gr._earnings_surprise_from_hist(None, "t")
    check("B4 keine Daten → Karte None, collected=False, Wert None (nicht 0)",
          k3 is None and r3["collected"] is False and r3["surprise_pct"] is None
          and r3["reason"] == "keine_daten")
    h4 = _frame([{"foo": 1}], ["2026-09-30"])
    k4, r4 = gr._earnings_surprise_from_hist(h4, "t")
    check("B5 Spalten fehlen → None, Grund keine_daten", k4 is None and r4["reason"] == "keine_daten")
    a, b = gr._earnings_surprise_from_hist(h, "x"), gr._earnings_surprise_from_hist(h, "x")
    check("B6 deterministisch", json.dumps(a, sort_keys=True, default=str)
          == json.dumps(b, sort_keys=True, default=str))
    orig = gr.yf.Ticker
    gr.yf.Ticker = lambda t: types.SimpleNamespace(earnings_history=h)
    try:
        c, r = gr.get_earnings_surprise_full(
            "T", now_fn=lambda: datetime(2026, 11, 16, 22, 0, 5, tzinfo=timezone.utc))
        check("B7 get_earnings_surprise == Karte aus get_earnings_surprise_full",
              gr.get_earnings_surprise("T") == c == _old_card(h))
        check("B8 Abrufzeit aus injizierter Uhr", r["abgerufen_utc"] == "2026-11-16T22:00:05+00:00")

        def _boom(t):
            raise RuntimeError("down")
        gr.yf.Ticker = _boom
        c9, r9 = gr.get_earnings_surprise_full("T")
        check("B9 Abruf-Fehler → Karte None, Grund fehler", c9 is None and r9["reason"] == "fehler")
    finally:
        gr.yf.Ticker = orig
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    check("B10 Main nutzt get_earnings_surprise_full und setzt beide Keys",
          "_es_ex.submit(get_earnings_surprise_full" in src
          and '["earnings_surprise_record"]) = _fut.result()' in src)


# ── C: Backtest-Eintrag ──────────────────────────────────────────────────────
def test_c():
    base = {"ticker": "T"}
    f = bh._build_earnings_fields(base, None, True)
    check("C1 nicht abgefragt + nicht gesammelt → Gründe, Werte None",
          f["earnings_surprise_pit"]["reason"] == "nicht_abgefragt"
          and f["earnings_surprise_pit"]["surprise_pct"] is None
          and f["earnings_surprise_pit"]["letzter_termin_8k_grund"] == "edgar_nicht_gesammelt"
          and f["material_8k_events_14d"] is None)
    f2 = bh._build_earnings_fields(base, None, False)
    check("C2 8-K aus → Grund edgar_aus", f2["earnings_surprise_pit"]["letzter_termin_8k_grund"] == "edgar_aus")
    ex = m8._extras_from_submissions(_subs(), now_utc=NOW, cik="c", lookback_days=14,
                                     qualifying_items=config.MATERIAL_8K_QUALIFYING_ITEMS, cap_n=16)
    rec = {"collected": True, "reason": None, "surprise_pct": 25.0}
    f3 = bh._build_earnings_fields({"earnings_surprise_record": rec}, ex, True)
    check("C3 voller Fall: Überraschung + letzter Termin + 14-T-Fenster",
          f3["earnings_surprise_pit"]["surprise_pct"] == 25.0
          and f3["earnings_surprise_pit"]["letzter_termin_8k"]["accession"] == "0001-26-000010"
          and f3["earnings_surprise_pit"]["letzter_termin_8k_grund"] is None
          and len(f3["material_8k_events_14d"]["events"]) == 2)
    check("C4 Record wird nicht mutiert (Kopie)", "letzter_termin_8k" not in rec)
    ex_none = dict(ex, last_2_02=None)
    f4 = bh._build_earnings_fields({}, ex_none, True)
    check("C5 kein 2.02 in recent → Grund kein_2_02_in_recent",
          f4["earnings_surprise_pit"]["letzter_termin_8k_grund"] == "kein_2_02_in_recent")

    # Ende-zu-Ende über den ECHTEN Schreibpfad (Sammler gefakt, kein Netz).
    now_et = datetime(2026, 11, 16, 17, 40, tzinfo=ET)
    rd = now_et.strftime("%d.%m.%Y")

    def _stock(t, with_rec):
        s = {"ticker": t, "score": 70.0, "price": 10.0, "short_float": 25.0,
             "short_ratio": 5.0, "rel_volume": 2.4, "float_shares": 1e8,
             "avg_vol_20d": 1e6, "hist_5d": [], "score_trend_bonus_pts": 0.0,
             "agent_boost_factor": 1.0, "finra_bonus_pts": 0.0,
             "short_float_source": "yfinance",
             "finra_data": {"trend": "no_data", "history": [], "si_trend_source": "finra"},
             "sparkline_view": None, "bar_date": now_et.strftime("%Y-%m-%d")}
        if with_rec:
            s["earnings_surprise_record"] = {"collected": True, "reason": None,
                                             "surprise_pct": 25.0, "abgerufen_utc": "x"}
        return s

    _real_collect = m8.collect_material_8k_events

    def _fake_collect(tickers, *, now_utc=None, extras_out=None, **kw):
        out = _real_collect(
            tickers, now_utc=NOW, ua="t", get_json=_fake_get_json, get_text=lambda *a: "",
            company_tickers=CT, sleep_s=0, run_budget_s=0, extras_out=extras_out)
        return out

    def _run():
        orig = bh.material_8k_module.collect_material_8k_events
        bh.material_8k_module.collect_material_8k_events = _fake_collect
        cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="mt_earnings_fields_")
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        bh.log.addHandler(h)
        bh.log.setLevel(logging.INFO)
        try:
            os.chdir(tmp)
            json.dump({"signals": {}}, open("agent_signals.json", "w"))
            json.dump([], open("backtest_history.json", "w"))
            bh._append_backtest_entries(
                [_stock("TEST", True), _stock("NOPE", False)], rd, pool_size=2,
                compute_sub_scores_fn=lambda s: {"struct": 0, "catalyst": 0, "timing": 0},
                safe_float_fn=gr._safe_float, now_et=now_et)
            return json.load(open("backtest_history.json")), buf.getvalue()
        finally:
            os.chdir(cwd)
            bh.log.removeHandler(h)
            bh.material_8k_module.collect_material_8k_events = orig
    rows, logtxt = _run()
    by = {r["ticker"]: r for r in rows}
    check("C6 beide Einträge geschrieben", set(by) == {"TEST", "NOPE"}, str(list(by)))
    t = by.get("TEST", {})
    check("C7 TEST: beide neuen Felder vorhanden und gefüllt",
          t.get("earnings_surprise_pit", {}).get("surprise_pct") == 25.0
          and t["earnings_surprise_pit"]["letzter_termin_8k"]["accession"] == "0001-26-000010"
          and t.get("material_8k_events_14d", {}).get("collected") is True)
    check("C8 TEST: material_8k_events (5 T) unverändert = Sammler ohne extras",
          [e["accession"] for e in (t.get("material_8k_events") or {}).get("events", [])]
          == ["0001-26-000010"])
    n = by.get("NOPE", {})
    check("C9 NOPE: Unbekannt ≠ 0 (nicht abgefragt / no_cik)",
          n.get("earnings_surprise_pit", {}).get("reason") == "nicht_abgefragt"
          and n["earnings_surprise_pit"]["surprise_pct"] is None
          and n["earnings_surprise_pit"]["letzter_termin_8k_grund"] == "no_cik"
          and n.get("material_8k_events_14d", {}).get("collected") is False)
    check("C10 Log-Beleg der Herkunft",
          "[earnings_fields] 2 neue Einträge: Überraschung 1/2" in logtxt
          and "letzter 8-K-2.02-Termin 1/2" in logtxt and "8-K-14T gesammelt 1/2" in logtxt,
          logtxt[-400:])
    rows2, _ = _run()
    k = ("earnings_surprise_pit", "material_8k_events_14d", "material_8k_events")
    check("C11 Determinismus: gleiche Eingabe → gleiche Felder",
          json.dumps([{x: r.get(x) for x in k} for r in rows], sort_keys=True)
          == json.dumps([{x: r.get(x) for x in k} for r in rows2], sort_keys=True))
    return t


# ── D: Digest ───────────────────────────────────────────────────────────────
def test_d(sample):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "bh.json")
    json.dump([{"date": "13.11.2026", "ticker": "X"}], open(p, "w"))
    check("D1 noch kein Eintrag → 'sammelt ab dem nächsten Postclose'",
          "sammelt ab dem nächsten Postclose" in hc.earnings_fields_digest_line(p))
    a = dict(sample, date="16.11.2026", ticker="A")
    b = {"date": "16.11.2026", "ticker": "B",
         "earnings_surprise_pit": {"surprise_pct": None, "letzter_termin_8k": None},
         "material_8k_events_14d": None}
    old = dict(sample, date="13.11.2026", ticker="C")
    json.dump([old, a, b], open(p, "w"))
    line = hc.earnings_fields_digest_line(p)
    check("D2 Zählung über den jüngsten Berichtstag",
          line == "🧾 Gewinn-Felder (letzter Bericht 16.11.): Überraschung 1/2 · "
                  "letzter 8-K-Termin 1/2 · 8-K 14 Tage 1/2", line)
    check("D3 Datei fehlt / kaputt → kein Raise",
          "Datei fehlt" in hc.earnings_fields_digest_line(os.path.join(d, "x.json")))
    for state_fails in ([], [{"id": "S1", "severity": "crit", "detail": "x"}]):
        body, *_ = hc.format_digest_body(state_fails, [], n_runs=1, last_run_iso="x",
                                         digest_date="2026-11-17",
                                         earnings_fields_line="🧾 Gewinn-Felder TEST")
        check(f"D4 Zeile im Digest ({'crit' if state_fails else 'ok'})", "🧾 Gewinn-Felder TEST" in body)
    body, *_ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None, digest_date="2026-11-17",
                                     earnings_fields_line="🧾 Gewinn-Felder TEST")
    check("D5 Zeile im Digest (ohne Daten)", "🧾 Gewinn-Felder TEST" in body)
    dig = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
    check("D6 Digest-Skript verdrahtet die Zeile", "earnings_fields_line=earnings_fields_line" in dig)


# ── E: Isolation ─────────────────────────────────────────────────────────────
def test_e():
    new = ("earnings_surprise_pit", "material_8k_events_14d", "earnings_surprise_record")
    for f in ("scripts/freeze_eval.py", "scripts/stats_helpers.py",
              "scripts/hypothesen_nov26_eval.py", "ki_agent.py", "scripts/truth_check.py"):
        txt = (ROOT / f).read_text(encoding="utf-8")
        check(f"E1 {f} liest die neuen Felder nicht", not any(k in txt for k in new))
    gsrc = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    check("E2 generate_report liest die Backtest-Felder nicht (kein String-Zugriff)",
          not re.search(r"[\"'](earnings_surprise_pit|material_8k_events_14d)[\"']", gsrc))
    reads = [m.start() for m in re.finditer(r"earnings_surprise_record", gsrc)]
    check("E3 earnings_surprise_record nur an der Fetch-Stelle (Schreiben)", len(reads) == 1, str(len(reads)))
    hand = (ROOT / "SESSION_HANDOVER.md").read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^#{2,4}\s*", hand)
    frozen = [b for b in blocks if re.match(r"(VORABREGISTRIERUNG|ERRATUM)\b", b)]
    check("E4 kein Freeze-Block nennt die neuen Felder",
          frozen and not any(k in b for b in frozen for k in new[:2]))


# ── F: config ────────────────────────────────────────────────────────────────
def test_f():
    check("F1 beide Felder in S10_OBSERVED_FIELDS",
          {"earnings_surprise_pit", "material_8k_events_14d"} <= set(config.S10_OBSERVED_FIELDS))
    check("F2 14-T-Konstanten", config.MATERIAL_8K_14D_LOOKBACK_DAYS == 14
          and config.MATERIAL_8K_14D_CAP_N == 16)
    check("F3 5-T-Definition unverändert", config.MATERIAL_8K_LOOKBACK_DAYS == 5
          and config.MATERIAL_8K_CAP_N == 8)


def main() -> int:
    test_a()
    test_b()
    sample = test_c()
    test_d(sample)
    test_e()
    test_f()
    if FAILS:
        print(f"{len(FAILS)} FAIL: {FAILS}")
        return 1
    print("Alle earnings_fields-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
