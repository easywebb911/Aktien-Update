#!/usr/bin/env python3
"""Mock-Tests Treffer-Score (unvalidiert) — SUW-Schatten-Wert (15.11.2026).

Kein Netz. (a) Auswahl, Scores und gespeicherte Reihenfolge der Top-10 lesen
das Feld nie; (b) die Ansicht sortiert danach. Dazu: Rechenkern-Wiederverwendung
(Hand-Beispiel), Rang/Gleichstand, „leer statt Abbruch“ bei FINRA-/Yahoo-
Ausfall und Zeitlimit, Zwischenspeicher, Anzeige/Rundung, Workflow-Einträge.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import treffer_score as T  # noqa: E402
import suw_eval as S  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


D = date(2026, 9, 15)
NOHOL: frozenset = frozenset()
W = S.window_days(D, holidays=NOHOL)


def finra_text(sv_by_sym: dict) -> str:
    return ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
            + "".join(f"x|{k}|{v}|0|1|Q\n" for k, v in sv_by_sym.items()))


def make_fetch(sv_fn, calls=None):
    def f(d, timeout):
        if calls is not None:
            calls.append(d)
        return finra_text(sv_fn(d)), "ok"
    return f


def stock(t, price, **kw):
    s = {"ticker": t, "price": price, "letzte_zeile": "vollstaendig", "bar_date": D.isoformat(),
         "score": 70.0}
    s.update(kw)
    return s


# 10 Tage sv=1 @ 10 $, 10 Tage sv=3 @ 20 $ → R = 17,5; c_D = 21 → +20 %
def closes_hand(tickers, start, end_excl):
    out = {}
    for t in tickers:
        out[t] = {d: (10.0 if i < 10 else 20.0) for i, d in enumerate(W)}
    return out


def sv_hand(d):
    i = W.index(d)
    return {"AA": 1 if i < 10 else 3, "BB": 1 if i < 10 else 3, "CC": 1}


# ── 1) Rechenkern + Hand-Beispiel ───────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    top = [stock("AA", 21.0), stock("BB", 17.5), stock("CC", 30.0, letzte_zeile="vortag_rueckfall")]
    before = copy.deepcopy(top)
    items, info = T.compute_for_top10(top, D, cache_dir=td, fetch_finra=make_fetch(sv_hand),
                                      fetch_closes=closes_hand, holidays=NOHOL)
    by = {it["ticker"]: it for it in items}
    check("01 Hand-Beispiel: R = 17,5, c_D 21 → +20,0000 %", by["AA"]["wert"] == 20.0
          and by["AA"]["r"] == 17.5 and by["AA"]["fehlende_tage"] == 0, str(by["AA"]))
    check("02 c_D = R → 0,0 %", by["BB"]["wert"] == 0.0)
    check("03 vortag_rueckfall → kein Wert, Grund „Tagesschluss fehlt“, kein Rang",
          by["CC"]["wert"] is None and by["CC"]["grund"] == "Tagesschluss fehlt" and by["CC"]["rang"] is None)
    check("04 Rang 1/2, N = Einträge mit Wert", by["AA"]["rang"] == 1 and by["BB"]["rang"] == 2
          and by["AA"]["n_mit_wert"] == 2 and by["CC"]["n_mit_wert"] == 2)
    check("05 Top-10-Dicts unverändert (reine Leseoperation)", top == before)
    check("06 Stand immer vorläufig, Datum = Berichtstag", all(it["stand"] == "vorläufig"
          and it["datum"] == D.isoformat() for it in items))
    alt = T.compute_for_top10([stock("AA", 21.0, bar_date="2026-09-14")], D, cache_dir=td,
                              fetch_finra=make_fetch(sv_hand), fetch_closes=closes_hand, holidays=NOHOL)[0]
    check("07 Bar-Datum ≠ Berichtstag → Tagesschluss fehlt", alt[0]["grund"] == "Tagesschluss fehlt")
    # Zwischenspeicher: zweiter Lauf ohne Abruf
    calls: list = []
    T.compute_for_top10([stock("AA", 21.0)], D, cache_dir=td, fetch_finra=make_fetch(sv_hand, calls),
                        fetch_closes=closes_hand, holidays=NOHOL)
    check("08 Zwischenspeicher: zweiter Lauf lädt keine FINRA-Datei", calls == [])
    for i in range(30):
        (pathlib.Path(td) / f"CNMSshvol2025{i:04d}.txt").write_text("x", encoding="utf-8")
    T.prune_cache(td, keep=25)
    check("09 Zwischenspeicher behält 25 Börsentage", len(list(pathlib.Path(td).glob("CNMSshvol*.txt"))) == 25)

# ── 2) Rang und Gleichstand ─────────────────────────────────────────────────
its = [{"ticker": "Z", "pool_position": 3, "wert": 5.0}, {"ticker": "Y", "pool_position": 1, "wert": 5.0},
       {"ticker": "X", "pool_position": 1, "wert": 5.0}, {"ticker": "W", "pool_position": 2, "wert": None},
       {"ticker": "V", "pool_position": 4, "wert": 9.0}]
T.assign_ranks(its)
r = {i["ticker"]: i["rang"] for i in its}
check("10 Gleichstand: pool_position, dann Ticker; ohne Wert kein Rang",
      r == {"V": 1, "X": 2, "Y": 3, "Z": 4, "W": None} and its[0]["n_mit_wert"] == 4, str(r))

# ── 3) Leer statt Abbruch ───────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    def boom_finra(d, timeout):
        raise RuntimeError("FINRA weg")

    def boom_yahoo(*a):
        raise RuntimeError("Yahoo weg")
    try:
        a, _ = T.compute_for_top10([stock("AA", 21.0)], D, cache_dir=td, fetch_finra=boom_finra,
                                   fetch_closes=closes_hand, holidays=NOHOL)
        ok = a[0]["wert"] is None and a[0]["grund"]
    except Exception as exc:  # noqa: BLE001
        ok = False
        a = str(exc)
    check("11 FINRA wirft → Feld leer, keine Exception", ok, str(a))
    b, info_b = T.compute_for_top10([stock("AA", 21.0)], D, cache_dir=td, fetch_finra=make_fetch(sv_hand),
                                    fetch_closes=boom_yahoo, holidays=NOHOL)
    check("12 Yahoo wirft → kein Wert (zu viele fehlende Tage), keine Exception",
          b[0]["wert"] is None and b[0]["grund"] == "zu_viele_fehlende_tage" and "yahoo_fehler" in info_b)
with tempfile.TemporaryDirectory() as td:
    t = [0.0]
    calls = []

    def slow_fetch(d, timeout):
        calls.append(d)
        t[0] += 7.0
        return finra_text(sv_hand(d)), "ok"
    c, info_c = T.compute_for_top10([stock("AA", 21.0)], D, cache_dir=td, fetch_finra=slow_fetch,
                                    fetch_closes=closes_hand, holidays=NOHOL, clock=lambda: t[0])
    check("13 Zeitlimit 60 s: Abrufe danach unterbleiben, Wert leer",
          len(calls) == 9 and c[0]["wert"] is None and len(info_c["finra"]["fehlend"]) == 11,
          f"{len(calls)} {info_c}")

# ── 4) Anwenden im Lauf (generate_report._apply_treffer_score) ──────────────
# generate_report über das Golden-Harness laden (stubbt yfinance/requests/bs4 —
# CI läuft auf stdlib + jinja2 + pyyaml).
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "golden_harness_ts", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr

def sv_wl(d):
    v = sv_hand(d)
    v["WL"] = v["AA"]
    return v


BERLIN_FIX = datetime(2026, 9, 15, 17, 42, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Berlin"))

with tempfile.TemporaryDirectory() as td:
    dp = pathlib.Path(td) / "suw_daily.jsonl"
    top = [stock("AA", 21.0, score=82.0, conviction={"score": 70}), stock("BB", 17.5, score=71.0)]
    wl = [stock("WL", 21.0)]
    before = copy.deepcopy(top)
    order_before = [s["ticker"] for s in top]

    def fake_compute(top10, rd, cache_dir=None, extra=(), intraday=False):
        return T.compute_for_top10(top10, rd, cache_dir=td, fetch_finra=make_fetch(sv_wl),
                                   fetch_closes=closes_hand, holidays=NOHOL,
                                   extra=extra, intraday=intraday)
    gr._apply_treffer_score(top, "postclose", D, compute=fake_compute, daily_path=dp, extra=wl)
    check("14 Postclose: nur Feld treffer_score neu, Reihenfolge + alle anderen Felder gleich",
          [s["ticker"] for s in top] == order_before
          and all({k: v for k, v in s.items() if k != "treffer_score"} == b for s, b in zip(top, before)))
    rows = [json.loads(x) for x in dp.read_text(encoding="utf-8").splitlines()]
    check("15 suw_daily.jsonl: nur die Top-10 (keine Watchlist), 4 Nachkommastellen",
          len(rows) == 2 and rows[0]["wert"] == 20.0 and rows[0]["stand"] == "vorläufig"
          and "WL" not in {r["ticker"] for r in rows}, rows)
    check("15b Postclose-Watchlist: Wert ohne Rang, als Watchlist markiert",
          wl[0]["treffer_score"]["wert"] == 20.0 and wl[0]["treffer_score"]["rang"] is None
          and wl[0]["treffer_score"]["watchlist"] is True
          and top[0]["treffer_score"]["rang"] == 1 and top[0]["treffer_score"]["n_mit_wert"] == 2)
    dp_bytes = dp.read_bytes()

    # Vorschau-Lauf: c_D = aktueller Kurs desselben Laufs
    pre = [stock("AA", 24.5, bar_date="2026-09-14"), stock("BB", 17.5, letzte_zeile="vortag_rueckfall")]
    pwl = [stock("WL", 35.0)]
    gr._apply_treffer_score(pre, "premarket", D, compute=fake_compute, daily_path=dp,
                            extra=pwl, now_berlin=BERLIN_FIX)
    ta, tb, tw = (x["treffer_score"] for x in (pre[0], pre[1], pwl[0]))
    check("16 Vorschau: Wert mit aktuellem Kurs (24,5 / R 17,5 → +40 %), Bar-Datum egal",
          ta["wert"] == 40.0 and tb["wert"] == 0.0, (ta, tb))
    check("16b Vorschau: Rang nur unter den Top-10 desselben Laufs, Watchlist ohne Rang",
          ta["rang"] == 1 and tb["rang"] == 2 and ta["n_mit_wert"] == 2
          and tw["rang"] is None and tw["watchlist"] is True and tw["wert"] == 100.0)
    check("16c Vorschau: „vorläufig HH:MM Uhr“ (Berlin wie Kopfzeile)",
          ta["zeit"] == "17:42 Uhr" and not ta.get("aus_postclose")
          and "vorläufig 17:42 Uhr" in gr._treffer_pillar_html(pre[0]))
    check("16d Vorschau schreibt suw_daily.jsonl NIE (Freeze-Trennung, byte-gleich)",
          dp.read_bytes() == dp_bytes)

    # Rückfall: Tagesberechnung ohne Wert → letzter Abendwert ≤ 3 Handelstage
    td_leer = tempfile.mkdtemp()   # leerer Zwischenspeicher → FINRA scheitert wirklich

    def fail_compute(top10, rd, cache_dir=None, extra=(), intraday=False):
        return T.compute_for_top10(top10, rd, cache_dir=td_leer,
                                   fetch_finra=lambda d, timeout: (None, "fehler"),
                                   fetch_closes=closes_hand, holidays=NOHOL,
                                   extra=extra, intraday=intraday)
    D3 = date(2026, 9, 18)   # Fr: 3 Handelstage nach Di 15.09.
    D4 = date(2026, 9, 21)   # Mo: 4 Handelstage nach Di 15.09.
    r3 = [stock("AA", 30.0), stock("NEU", 5.0)]
    gr._apply_treffer_score(r3, "premarket", D3, compute=fail_compute, daily_path=dp,
                            now_berlin=BERLIN_FIX)
    f3 = r3[0]["treffer_score"]
    check("17a Rückfall (3 Handelstage alt): Abendwert mit „Stand TT.MM.“, OHNE Rang",
          f3["wert"] == 20.0 and f3["aus_postclose"] and f3["rang"] is None
          and "Stand 15.09." in gr._treffer_pillar_html(r3[0])
          and "Rang " not in gr._treffer_pillar_html(r3[0]).split("title=")[0]
          and 'treffer-sub' not in gr._treffer_pillar_html(r3[0])
          and gr._treffer_data_attr(r3[0]) == "", f3)
    check("17b ohne Abendwert → „—“ mit Grund, nie 0",
          r3[1]["treffer_score"]["wert"] is None and r3[1]["treffer_score"]["grund"]
          and ">—<" in gr._treffer_pillar_html(r3[1])
          and ">0,0" not in gr._treffer_pillar_html(r3[1]))
    r4 = [stock("AA", 30.0)]
    gr._apply_treffer_score(r4, "premarket", D4, compute=fail_compute, daily_path=dp,
                            now_berlin=BERLIN_FIX)
    f4 = r4[0]["treffer_score"]
    check("17c Rückfall-Grenze: 4 Handelstage alt → „—“ mit Grund „älter als 3 Handelstage“",
          f4["wert"] is None and "älter als 3 Handelstage" in str(f4["grund"]), f4)
    check("17d Grenze 3 zählt, 4 nicht (Handelstage; Wochenende zählt nicht)",
          T.trading_days_since("2026-09-15", D3) == 3 and T.trading_days_since("2026-09-15", D4) == 4
          and T.RUECKFALL_MAX_HANDELSTAGE == 3)
    check("17e Rückfall-Läufe schreiben suw_daily.jsonl nicht", dp.read_bytes() == dp_bytes)

    # Vorschau vor 09:30 ET / an Nicht-Handelstag: keine Berechnung (Guardian 23.11.)
    calls = []

    def spy_compute(top10, rd, cache_dir=None, extra=(), intraday=False):
        calls.append((len(top10), len(extra), intraday))
        return fake_compute(top10, rd, cache_dir=cache_dir, extra=extra, intraday=intraday)
    ZB = __import__("zoneinfo").ZoneInfo("Europe/Berlin")
    pre_open = [stock("AA", 30.0)]
    gr._apply_treffer_score(pre_open, "premarket", D, compute=spy_compute, daily_path=dp,
                            now_berlin=datetime(2026, 9, 15, 15, 0, tzinfo=ZB))  # 09:00 ET
    fp = pre_open[0]["treffer_score"]
    check("16e vor 09:30 ET: keine Berechnung, Rückfall auf Abendwert ohne Rang",
          calls == [] and fp["aus_postclose"] and fp["rang"] is None
          and fp["grund_tagsueber"] == T.GRUND_VOR_OEFFNUNG, (calls, fp))
    sat = [stock("NEU", 5.0)]
    gr._apply_treffer_score(sat, "premarket", date(2026, 9, 19), compute=spy_compute,
                            daily_path=dp, now_berlin=datetime(2026, 9, 19, 17, 42, tzinfo=ZB))
    check("16f Nicht-Handelstag: keine Berechnung, „—“ mit Grund „kein Handelstag“",
          calls == [] and sat[0]["treffer_score"]["wert"] is None
          and T.GRUND_KEIN_HANDELSTAG in str(sat[0]["treffer_score"]["grund"]))
    check("16g Vorschau-Gate schreibt suw_daily.jsonl nicht", dp.read_bytes() == dp_bytes)

    # Postclose: Top-10-Abruf ohne Watchlist; Watchlist-Fehler trifft Top-10 nicht
    with tempfile.TemporaryDirectory() as td2:
        dp2 = pathlib.Path(td2) / "suw_daily.jsonl"
        calls2 = []

        def wl_fails(top10, rd, cache_dir=None, extra=(), intraday=False):
            calls2.append((len(top10), len(extra), intraday))
            if extra:
                raise RuntimeError("watchlist-abruf kaputt")
            return fake_compute(top10, rd, cache_dir=cache_dir, extra=extra, intraday=intraday)
        t2 = [stock("AA", 21.0), stock("BB", 17.5)]
        w2 = [stock("WL", 21.0)]
        gr._apply_treffer_score(t2, "postclose", D, compute=wl_fails, daily_path=dp2, extra=w2)
        rows2 = [json.loads(x) for x in dp2.read_text(encoding="utf-8").splitlines()]
        check("15c Postclose: Top-10-Abruf ohne Watchlist (getrennt), Watchlist-Fehler → "
              "Top-10-Werte + suw_daily.jsonl unberührt",
              calls2 == [(2, 0, False), (0, 1, False)] and len(rows2) == 2
              and t2[0]["treffer_score"]["wert"] == 20.0
              and w2[0]["treffer_score"]["wert"] is None
              and w2[0]["treffer_score"]["grund"] == "nicht_berechnet", (calls2, rows2))

    def raising(*a, **k):
        raise RuntimeError("kaputt")
    x = [stock("AA", 21.0)]
    try:
        gr._apply_treffer_score(x, "postclose", D, compute=raising, daily_path=dp)
        ok17 = x[0]["treffer_score"]["wert"] is None
    except Exception:  # noqa: BLE001
        ok17 = False
    check("17 Fehler im Treffer-Score bricht den Lauf nicht ab", ok17)

# ── 5) Anzeige: dritte Säule ────────────────────────────────────────────────
def pil(t):
    return gr._treffer_pillar_html({"treffer_score": t})


p1 = pil({"wert": 12.4312, "rang": 3, "n_mit_wert": 10, "zeit": "11:42 Uhr"})
check("18 Säule: „+12,4 %“, „Rang 3 von 10“, Schild, Label",
      "+12,4 %" in p1 and "Rang 3 von 10" in p1 and gr.TREFFER_SCHILD in p1
      and "UNVALIDIERT · TEST LÄUFT" in p1 and ">Treffer-Score<" in p1)
check("19 Rundung eine Stelle, Minus, Null", "−2,5 %" in pil({"wert": -2.46, "rang": 1, "n_mit_wert": 1})
      and "0,0 %" in pil({"wert": -0.04, "rang": 1, "n_mit_wert": 1}))
import re as _re  # noqa: E402
hi = pil({"wert": 85.0, "rang": 1, "n_mit_wert": 10})
lo = pil({"wert": -60.0, "rang": 10, "n_mit_wert": 10})
_strip = lambda h: _re.sub(r'class="treffer-value">[^<]*<', "", _re.sub(r"Rang \d+", "", h))  # noqa: E731
check("19b Farbe hängt NICHT vom Wert ab (gleiches Markup bis auf Zahl/Rang, kein style, kein Balken)",
      _strip(hi) == _strip(lo) and "style=" not in hi and "pillar-bar" not in hi
      and "#22c55e" not in hi and "#ef4444" not in hi and "#f59e0b" not in hi)
check("19c Säule ohne cockpit-pillar-value (S9 zählt genau 2 Säulen-Werte je Karte)",
      "cockpit-pillar-value" not in hi and "cockpit-pillar-value" not in lo)
r_none = pil({"wert": None, "grund": "zu_viele_fehlende_tage"})
check("20 ohne Wert „—“ mit Grund, nie 0",
      'treffer-value">—<' in r_none and "zu_viele_fehlende_tage" in r_none and "0,0" not in r_none)
check("21 Abendwert: „Stand TT.MM.“", "Stand 15.09." in pil({"wert": 1.0, "rang": 1, "n_mit_wert": 1,
                                                           "datum": "2026-09-15", "aus_postclose": True}))
check("21b Watchlist: „Watchlist“ statt Rang",
      "Watchlist" in pil({"wert": 3.0, "rang": None, "watchlist": True, "zeit": "11:42 Uhr"})
      and 'class="treffer-sub">Rang' not in pil({"wert": 3.0, "rang": None, "watchlist": True}))
check("22 ohne Feld → keine Säule, kein Satz, kein Attribut",
      gr._treffer_pillar_html({}) == "" and gr._treffer_detail_row_html({}) == ""
      and gr._treffer_data_attr({}) == "")
check("23 data-treffer nur mit Rang (4 Stellen); Rückfall/Watchlist ohne",
      gr._treffer_data_attr({"treffer_score": {"wert": 13.6512, "rang": 2}}) == ' data-treffer="13.6512"'
      and gr._treffer_data_attr({"treffer_score": {"wert": 13.6512, "rang": None}}) == "")
check("24 Detail-Satz mit Pflichttext (Gegenprobe, Kein Kaufsignal, neutrale Farbe)",
      all(x in gr.TREFFER_NOTE for x in ("Misst, ob die Leerverkäufer der letzten 20 Tage im Minus sitzen.",
                                         "In Prüfung, Ergebnis ca. Februar 2027.",
                                         "Kein Kaufsignal.", "aktuellen Kurs", "Stand TT.MM.",
                                         "Gegenprobe an 30 anderen Aktien (2025/26): nicht bestätigt, "
                                         "dort zeigte der Wert in die Gegenrichtung. Richtung offen bis "
                                         "zum Test.", "keine Ampel")))
cp = gr._card_cockpit_html(0, {"ticker": "AA", "price": 1.0, "score": 70.0, "ki_signal_score": 40,
                               "treffer_score": {"wert": 5.0, "rang": 1, "n_mit_wert": 1}})
check("24b Cockpit: Säule unter KI in der Säulen-Spalte (Reihenfolge Setup, KI, Treffer)",
      cp.index('data-sb="setup"') < cp.index('data-sb="ki"') < cp.index('data-sb="treffer"')
      < cp.index('cockpit-donut-wrap') and "cockpit-treffer\"" not in cp)
_panel_rows, _ = gr._score_confidence_rows_html({"setup": {"n": 5, "data_tier": "klein"}})
_suw_li = next((li for li in _panel_rows.split("<li>") if "Treffer-Score (SUW)" in li), "")
check("24b Panel-Zeile Treffer-Score (SUW) nennt die Gegenprobe (Halbsatz, ohne Zahl)",
      "Gegenprobe an anderen Aktien: nicht bestätigt, Richtung offen" in _suw_li)

# ── 6) (a) Auswahl/Scores/Reihenfolge lesen das Feld nie ────────────────────
src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")
tree = ast.parse(src_gr)
forbidden = {"score", "score_bonus", "_compute_sub_scores", "apply_conviction_scores",
             "compute_conviction_score", "apply_score_smoothing", "apply_late_runner_penalty",
             "apply_agent_boost", "apply_monster_score", "compute_earliness_pts", "_drivers_breakdown",
             "compute_exit_score", "process_exit_signals", "_wl_card_payload",
             "_build_chat_synthesis_ctx", "_write_app_data_json"}
hits = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in forbidden
        and "treffer" in ast.get_source_segment(src_gr, n).lower()]
check("25 Score-/Conviction-/Filter-/Export-Funktionen lesen treffer nie", hits == [], str(hits))
other = [f for f in ("backtest_history.py", "matured_export.py", "score_inflation_log.py", "ki_agent.py",
                     "scripts/suw_eval.py", "scripts/freeze_eval.py")
         if any(tok in (ROOT / f).read_text(encoding="utf-8")
                for tok in ("treffer_score", "suw_daily", "data-treffer"))]
check("26 Backtest/Export/KI-Agent/Freeze-Auswertung lesen Feld und Datei nie", other == [], str(other))
i_conv = src_gr.index("apply_conviction_scores(top10, _anomalies_today")
i_bt = src_gr.index("_n_backtest_appended = _append_backtest_entries(")
i_ts = src_gr.index("_apply_treffer_score(top10, run_phase, _report_day,\n                         extra=_wl_outsiders_for_pool)")
i_html = src_gr.index("html = generate_html(top10, report_date")
check("27 Aufruf nach Conviction und Backtest-Append, vor generate_html", i_conv < i_bt < i_ts < i_html)

# ── 7) (b) Ansichts-Sortierung ──────────────────────────────────────────────
js = src_gr[src_gr.index("const _SORT_KEY = 'squeeze_sort_mode';"):src_gr.index("// ── Dark Mode")]
check("28 Speicherbare Modi ohne treffer; treffer nur Ansicht",
      "const _SORT_VALID = ['setup', 'ki', 'conviction'];" in js and "const _SORT_VIEW_ONLY = ['treffer'];" in js)
sm = js[js.index("function setSortMode"):]
check("29 setSortMode('treffer') schreibt localStorage nie",
      sm.index("_SORT_VIEW_ONLY.indexOf(mode) >= 0") < sm.index("localStorage.setItem")
      and "return;" in sm[:sm.index("localStorage.setItem")])
check("30 Laden: unbekannter/treffer-Wert → setup", "if (_SORT_VALID.indexOf(cur) < 0) cur = 'setup';" in js)
check("31 Sortierung: data-treffer absteigend, ohne Wert ans Ende, Basis Server-Reihenfolge",
      "parseFloat(b.dataset.treffer) - parseFloat(a.dataset.treffer)" in js and "if (ah) return -1;" in js
      and "dataset.setupRank" in js[js.index("m === 'treffer'"):js.index("m === 'ki'")])
menu = src_gr[src_gr.index('id="menu-sort-submenu"'):src_gr.index('id="menu-sort-submenu"') + 1500]
check("32 Menü: vierter Eintrag unter Conviction, voller Wortlaut",
      menu.index("Conviction-Score") < menu.index("Treffer-Score (unvalidiert)")
      and 'id="menu-sort-check-treffer"' in menu)

# ── 8) Panel, Workflow, Datei, Digest ───────────────────────────────────────
rows_html, _ = gr._score_confidence_rows_html({"setup": {"n": 10, "data_tier": "klein"},
                                                "computed_at": "x"})
check("33 Panel-Zeile: Test läuft x von 60, Erkundung kein Beleg, grau",
      "Treffer-Score (SUW)" in rows_html and "von 60 Einstiegstagen" in rows_html
      and "Erkundung, kein Beleg" in rows_html and "conf-kind-heuristic" in rows_html[rows_html.index("Treffer-Score (SUW)"):])
wf = (ROOT / ".github/workflows/daily-squeeze-report.yml").read_text(encoding="utf-8")
check("34 Workflow: actions/cache finra_cache vor Generate, git add suw_daily.jsonl",
      "path: finra_cache" in wf and wf.index("path: finra_cache") < wf.index("name: Generate squeeze report")
      and "git add suw_daily.jsonl" in wf)
check("35 finra_cache/ nie im Repo", "finra_cache/" in (ROOT / ".gitignore").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "d.jsonl"
    T.append_daily([{"datum": "2026-09-15", "ticker": "AA", "wert": 1.0, "rang": 1, "n_mit_wert": 1,
                     "stand": "vorläufig"},
                    {"datum": "2026-09-15", "ticker": "BB", "wert": None, "rang": None, "n_mit_wert": 1,
                     "stand": "vorläufig"}], p)
    check("36 Digest-Zeile „Treffer-Score: x/N mit Wert“",
          T.digest_line(p) == "📐 Treffer-Score: 1/2 mit Wert (Stand 15.09., vorläufig)", T.digest_line(p))
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("37 Digest bindet die Zeile fail-soft ein", "treffer_score.digest_line(" in dg
      and "Treffer-Score-Digest unerwartet" in dg)
check("38 Rechenkern nur importiert (keine zweite SUW-Formel)",
      "suw_eval.suw_value(" in (ROOT / "treffer_score.py").read_text(encoding="utf-8")
      and "sv * c" not in (ROOT / "treffer_score.py").read_text(encoding="utf-8"))
# Feste Uhr wie mock_test_paper_c_marker/sparkline_view: der Render enthält einen
# sekundengenauen Zeitstempel (daily_run_ts_js); ohne feste Uhr wird v1 != v2,
# sobald ein Sekundenwechsel zwischen die beiden Renders fällt (CI-Flake 16.11.2026).
_orig_dt = gr.datetime
try:
    gr.datetime = golden._FixedDateTime
    gr._render_test(golden._fixture_stocks(), golden._FIXED_REPORT_DATE)
    ok39 = True
except Exception:  # noqa: BLE001
    ok39 = False
finally:
    gr.datetime = _orig_dt
check("39 v1 == v2 mit Treffer-Score-Fixture (_render_test)", ok39)

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle Tests grün.")
