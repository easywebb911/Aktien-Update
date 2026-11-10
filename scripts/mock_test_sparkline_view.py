"""Mock-Test: Score-Verlauf (Kurve) chronologisch + ISO, ohne KI-Score
(Anzeige-PR 09.11.2026; open_items sparkline-datum-textsortierung,
sparkline-ki-score-ueberschreibt-setup, watchlist-score-history-textsortierung).

Geprüft (ohne Netz, Golden-Harness-Stubs):
  1. Helfer: Monatswechsel (Okt → Nov) und Jahreswechsel (Dez → Jan) —
     Reihenfolge, Auswahl der 7 jüngsten Tage, ISO-Daten, Trend, Δ T-1.
  2. Determinismus: jede Reihenfolge der Einträge → gleiche Kurve.
  3. Unparsbare Daten / NaN-Score → nicht verwendet; < 2 Tage → None.
  4. Render-Prüfung des ERZEUGTEN HTML (generate_html_v1): data-dates
     chronologisch + ISO, data-today ISO, letzter Punkt = heutiger Rohwert,
     Δ-T-1-Tooltip mit Vortag; WL_HIST/WL_SCORES chronologisch.
  5. Seit 11.11.2026 EINE Quelle: ``apply_score_smoothing`` setzt
     ``s["sparkline_view"]`` über den Helfer; der text-sortierte Payload
     ``s["sparkline"]`` ist entfernt; der Backtest liest ``sparkline_view``.
  6. JS: kein KI-Agent-Score mehr in drawSparkline; Punktfarbe aus
     ``_TRI_SCORE_*`` (= ``_tri_score_color``), nicht aus ``KI_DOT_*``;
     Datums-Parser ohne String-Date-Parsing (Safari).
"""
from __future__ import annotations

import html as _html
import importlib.util
import itertools
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "golden_harness", ROOT / "scripts" / "mock_test_outer_page_golden.py")
golden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(golden)
gr = golden.gr

GR_SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")
_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def E(d, sc, drv=None):
    return {"date": d, "score": sc, "drivers": drv or []}


# ULCC-artig über den Monatswechsel (Text-Sortierung würde Oktober hinten sehen).
MONTH = [E("27.10.2026", 66.85), E("28.10.2026", 85.5), E("29.10.2026", 91.45),
         E("02.11.2026", 85.82), E("03.11.2026", 85.82), E("04.11.2026", 66.19),
         E("05.11.2026", 60.46), E("09.11.2026", 62.72, ["RVOL 2.1×"])]
YEAR = [E("28.12.2026", 40.0), E("29.12.2026", 45.0), E("30.12.2026", 50.0),
        E("31.12.2026", 55.0), E("04.01.2027", 60.0), E("05.01.2027", 58.0)]


def test_helper_month_year():
    v = gr._sparkline_view_from_entries(MONTH, "09.11.2026")
    check("Monat: 7 jüngste Tage chronologisch",
          v["dates"] == ["2026-10-28", "2026-10-29", "2026-11-02", "2026-11-03",
                         "2026-11-04", "2026-11-05", "2026-11-09"], v["dates"])
    check("Monat: Scores in Datumsreihenfolge",
          v["scores"] == [85.5, 91.5, 85.8, 85.8, 66.2, 60.5, 62.7], v["scores"])
    check("Monat: letzter Punkt = heutiger Rohwert", v["scores"][-1] == round(62.72, 1))
    check("Monat: Trend fallend (62,7 − 85,5)", v["trend"] == "↓ -22.8 Pkt" and v["col"] == "#ef4444",
          (v["trend"], v["col"]))
    check("Monat: Treiber am richtigen Tag", v["drivers"][-1] == ["RVOL 2.1×"] and v["drivers"][0] == [])
    check("Monat: today ISO", v["today"] == "2026-11-09")
    s = {"sparkline_view": v}
    d = gr._cockpit_delta_html(s)
    check("Δ T-1 = 62,7 − 60,5 = +2,2 (Vortag 05.11.2026)",
          "▲ +2.2" in d and "05.11.2026, raw 60.5 → 62.7" in d, d)
    y = gr._sparkline_view_from_entries(YEAR, "05.01.2027")
    check("Jahr: chronologisch über Silvester",
          y["dates"] == ["2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
                         "2027-01-04", "2027-01-05"], y["dates"])
    check("Jahr: letzter Punkt = 05.01.2027", y["scores"][-1] == 58.0)
    check("Jahr: Trend steigend (58 − 40)", y["trend"] == "↑ +18.0 Pkt", y["trend"])
    yd = gr._cockpit_delta_html({"sparkline_view": y})
    check("Jahr: Δ T-1 = −2,0 ggü. 04.01.2027 (grau)",
          "▼ -2.0" in yd and "cockpit-delta-mute" in yd and "04.01.2027" in yd, yd)


def test_determinism():
    want = gr._sparkline_view_from_entries(MONTH, "09.11.2026")
    seen = set()
    for perm in itertools.islice(itertools.permutations(MONTH), 0, 40320, 97):
        seen.add(json.dumps(gr._sparkline_view_from_entries(list(perm), "09.11.2026"),
                            sort_keys=True, ensure_ascii=False))
    rnd = random.Random(11)
    for _ in range(60):
        sh = MONTH[:]
        rnd.shuffle(sh)
        seen.add(json.dumps(gr._sparkline_view_from_entries(sh, "09.11.2026"),
                            sort_keys=True, ensure_ascii=False))
    check("gleiche Historie, beliebige Reihenfolge → gleiche Kurve",
          seen == {json.dumps(want, sort_keys=True, ensure_ascii=False)}, len(seen))
    dup = MONTH + [E("09.11.2026", 50.0)]
    a = gr._sparkline_view_from_entries(dup, "09.11.2026")
    b = gr._sparkline_view_from_entries(list(reversed(dup)), "09.11.2026")
    check("doppelter Tag → ein Punkt, deterministisch", a == b and len(a["dates"]) == 7)


def test_bad_input():
    e = [E("03.11.2026", 50.0), E("kaputt", 70.0), E("31.02.2026", 70.0),
         E("04.11.2026", float("nan")), E("2026-11-05", 55.0)]
    v = gr._sparkline_view_from_entries(e, "05.11.2026")
    check("unparsbar/NaN nicht verwendet, ISO-Eingang akzeptiert",
          v["dates"] == ["2026-11-03", "2026-11-05"] and v["scores"] == [50.0, 55.0], v)
    check("< 2 Tage → None", gr._sparkline_view_from_entries([E("03.11.2026", 1.0)], "") is None)
    check("leeres today → ''", gr._sparkline_view_from_entries(MONTH, "")["today"] == "")
    check("jüngster Eintrag nach Datum (Watchlist-Score)",
          gr._spark_latest_entry(MONTH)["score"] == 62.72
          and gr._spark_latest_entry(list(reversed(MONTH)))["score"] == 62.72)


def _render(stocks, history):
    orig = {"dt": gr.datetime, "lbh": gr._load_backtest_history,
            "lsh": gr._load_score_history, "pl": gr.health_check.provider_liveness}
    try:
        gr.datetime = golden._FixedDateTime
        gr._load_backtest_history = golden._fixture_backtest_history
        gr._load_score_history = lambda: history
        gr.health_check.provider_liveness = golden._stub_provider_liveness
        return gr.generate_html_v1(stocks, "09.11.2026")
    finally:
        gr.datetime = orig["dt"]
        gr._load_backtest_history = orig["lbh"]
        gr._load_score_history = orig["lsh"]
        gr.health_check.provider_liveness = orig["pl"]


def test_render_generated_html():
    history = {"ULCC": [dict(e) for e in MONTH],
               "AAAA": [E("31.12.2026", 30.0), E("04.01.2027", 35.0)]}
    st = golden._fixture_stock("ULCC", score=62.2, price=8.0, change=11.0)
    # Wie apply_score_smoothing ihn setzt (gemeinsamer Helfer, volle History).
    st.pop("sparkline", None)
    st["sparkline_view"] = gr._sparkline_view_from_entries(history["ULCC"], "09.11.2026")
    out = _render([st], history)
    m = re.search(r'<article[^>]*data-ticker="ULCC"[\s\S]*?</article>', out)
    card = m.group(0) if m else out
    dd = re.search(r"data-dates='(\[[^']*\])'", card)
    ds = re.search(r"data-scores='(\[[^']*\])'", card)
    dt = re.search(r'data-today="([^"]*)"', card)
    dates = json.loads(dd.group(1)) if dd else []
    scores = json.loads(ds.group(1)) if ds else []
    check("HTML: Kurven-Daten ISO + chronologisch",
          dates == sorted(dates) and all(re.match(r"^\d{4}-\d{2}-\d{2}$", x) for x in dates)
          and dates[-1] == "2026-11-09", dates)
    check("HTML: letzter Punkt = heutiger Setup-Rohwert 62,7", scores[-1:] == [62.7], scores)
    check("HTML: data-today ISO", dt is not None and dt.group(1) == "2026-11-09")
    check("HTML: Trend ↓ −22,8", "↓ -22.8 Pkt" in card)
    check("HTML: Δ T-1 +2,2 ggü. 05.11.2026", "(05.11.2026, raw 60.5 → 62.7)" in card)
    wlh = re.search(r"const WL_HIST    = (\{.*?\});\n", out)
    wls = re.search(r"const WL_SCORES  = (\{.*?\});\n", out) or \
        re.search(r"const WL_SCORES\s*=\s*(\{.*?\});\n", out)
    hist = json.loads(wlh.group(1)) if wlh else {}
    check("WL_HIST chronologisch + ISO (Jahreswechsel)",
          hist.get("AAAA", {}).get("dates") == ["2026-12-31", "2027-01-04"], hist.get("AAAA"))
    check("WL_HIST ULCC endet am 09.11.", hist.get("ULCC", {}).get("dates", [""])[-1] == "2026-11-09")
    if wls:
        sc = json.loads(wls.group(1))
        check("WL_SCORES = jüngster Tag (nicht Text-Sortierung)",
              sc.get("AAAA") == 35.0 and sc.get("ULCC") == 62.72, sc)
    else:
        check("WL_SCORES gefunden", False)
    # v1 == v2 — mit fester Uhr wie im Golden/Paper-C-Test: ohne sie können
    # die eingebrannten Zeitstempel zwischen den zwei Renderings um eine
    # Sekunde springen (gleiche Länge, anderer Inhalt → Fehlalarm).
    orig = {"lsh": gr._load_score_history, "dt": gr.datetime,
            "lbh": gr._load_backtest_history, "pl": gr.health_check.provider_liveness}
    try:
        gr._load_score_history = lambda: history
        gr.datetime = golden._FixedDateTime
        gr._load_backtest_history = golden._fixture_backtest_history
        gr.health_check.provider_liveness = golden._stub_provider_liveness
        gr._render_test([st], "09.11.2026")
        check("v1 == v2 (_render_test)", True)
    except AssertionError as exc:
        check("v1 == v2 (_render_test)", False, str(exc)[:300])
    finally:
        gr._load_score_history = orig["lsh"]
        gr.datetime = orig["dt"]
        gr._load_backtest_history = orig["lbh"]
        gr.health_check.provider_liveness = orig["pl"]


def _sparkline_js():
    a = GR_SRC.index("// ── Sparkline renderer")
    return GR_SRC[a:GR_SRC.index("window.drawSparkline = drawSparkline;", a)]


def test_js():
    js = _sparkline_js()
    check("kein KI-Agent-Score in drawSparkline",
          "_AGENT_SIGNALS" not in js and "_sig.score" not in js and "scores.push(" not in js)
    check("Punktfarbe aus _TRI_SCORE_* (nicht KI_DOT_*)",
          "{_TRI_SCORE_GREEN_MIN}" in js and "{_TRI_SCORE_ORANGE_MIN}" in js
          and "{KI_DOT_" not in js)
    check("_tri_score_color nutzt dieselben Konstanten",
          re.search(r"def _tri_score_color[\s\S]*?_TRI_SCORE_GREEN_MIN[\s\S]*?"
                    r"_TRI_SCORE_ORANGE_MIN", GR_SRC) is not None)
    check("Datum ohne String-Parsing (Safari): new Date(y, m-1, d, 12)",
          "new Date(+m[1], +m[2] - 1, +m[3], 12, 0, 0)" in js and "'T12:00:00'" not in js)
    check("Ghost-Vergleich auf ISO", "todayIso > datesIso[n - 1]" in js)
    out = _render([golden._fixture_stock("AAAA", score=82.0, price=5.1, change=6.3)],
                  golden._fixture_score_history())
    check("eingebrannte Schwellen 60/30 + Farben",
          "if (s >= 60)  return '#22c55e';" in out and "if (s >= 30) return '#f97316';" in out
          and "return '#ef4444';" in out)
    check("renderAgentSignals zeichnet die Kurven nicht mehr neu",
          "document.querySelectorAll('.spark-wrap').forEach(drawSparkline);\n    }}\n    // Re-Sort"
          not in GR_SRC)


def test_main_wiring():
    a = GR_SRC.index("def apply_score_smoothing(")
    body = GR_SRC[a:GR_SRC.index("\ndef ", a + 10)]
    check("apply_score_smoothing setzt sparkline_view über den Helfer",
          's["sparkline_view"] = _sparkline_view_from_entries(history[ticker], today)' in body)
    check("kein text-sortierter Payload mehr (s['sparkline'] entfernt)",
          's["sparkline"]' not in body.replace('``s["sparkline"]``', "")
          and 'key=lambda x: x.get("date", "")' not in body)
    check("apply_sparkline_view entfernt (eine Quelle)", "apply_sparkline_view" not in GR_SRC)
    bt = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    check("Backtest liest sparkline_view", '_spark = s.get("sparkline_view") or {}' in bt
          and 's.get("sparkline")' not in bt)
    check("kein Konsument von s['sparkline'] mehr",
          's.get("sparkline")' not in GR_SRC and '_s.get("sparkline")' not in GR_SRC
          and '["sparkline"]' not in GR_SRC.replace('``s["sparkline"]``', ""))


def run_all() -> int:
    for t in (test_helper_month_year, test_determinism, test_bad_input,
              test_render_generated_html, test_js, test_main_wiring):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Kurven-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Kurven-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
