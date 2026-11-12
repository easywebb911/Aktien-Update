"""Mock-Test: Einmal-Korrektur abgeschnittener Rolling-Fenster im Export
(scripts/maxgain_export_correction.py, Easy-Entscheid 12.11.2026 Variante A).

Kein Netz: Kurse kommen aus einer Fake-Abruffunktion. Geprüft:
  1. Kandidaten = genau die abgeschnittenen Felder (S17-Regel), sonst nichts.
  2. Korrektur nur, wenn die Neuberechnung zur outcome_path-Gegenprobe passt
     (Toleranz 0,02 pp); Abweichung / unvollständiges Fenster / Abruffehler /
     Tag 10 noch nicht final → nicht geschrieben, gezählt.
  3. Unveränderte Zeilen byte-gleich, Zeilenzahl gleich; in korrigierten Zeilen
     nur die abgeschnittenen Felder (+ max_gain_pct_net abgeleitet,
     rolling_window_n = 11 falls vorhanden).
  4. Idempotent: zweiter Lauf ändert nichts.
  5. Blindheit: Replikationsfenster nur gezählt, Treffer-Wechsel nur Paper-C-Fenster.
  6. Formel identisch zu backtest_history (falls pandas verfügbar).
"""
from __future__ import annotations

import importlib
import io
import json
import os
import pathlib
import sys
import tempfile
import types
from contextlib import redirect_stdout
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)
for _m in ("yfinance", "bs4", "deep_translator"):
    try:
        importlib.import_module(_m)
    except ImportError:
        sys.modules[_m] = types.ModuleType(_m)

import config  # noqa: E402
import maxgain_export_correction as mc  # noqa: E402
import trading_date as td  # noqa: E402

_fails: list[str] = []
H = config.US_MARKET_HOLIDAYS


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


def days(edate, n=11):
    return [edate] + [td.nth_trading_day_after(edate, k, H) for k in range(1, n)]


HIGHS = [10, 10.4, 10.7, 10.3, 10.3, 10.3, 10.7, 11.0, 10.9, 12.9, 13.3]


def bars(edate, highs=HIGHS, low=9.0):
    return [{"d": x, "o": 9.5, "h": float(h), "l": low, "c": 9.5} for x, h in zip(days(edate), highs)]


def jbars(edate, **kw):
    return [dict(b, d=str(b["d"])) for b in bars(edate, **kw)]


FULL_MG = round((13.3 / 9 - 1) * 100, 2)
CUT7_MG = round((11.0 / 9 - 1) * 100, 2)
DD = round((9 / 10 - 1) * 100, 2)


def row(t, d, mg, dd=DD, **extra):
    r = {"ticker": t, "date": d.strftime("%d.%m.%Y"), "max_gain_pct": mg, "max_drawdown_pct": dd,
         "max_gain_pct_net": 1.0, "return_10d": 5.0, "provenance": "forward", "zz_other": "x"}
    r.update(extra)
    return json.dumps(r, sort_keys=True, ensure_ascii=False)


def setup(tmp):
    d_pc = date(2026, 10, 1)      # Paper-C-Fenster
    d_rep = date(2026, 10, 26)    # Replikationsfenster
    ex = [
        row("AAA", d_pc, CUT7_MG),                      # abgeschnitten → korrigieren, Treffer-Wechsel (22 → 47)
        row("BBB", d_pc, FULL_MG),                      # korrekt → unverändert
        row("CCC", d_rep, CUT7_MG, rolling_window_n=8), # Replikation, abgeschnitten → korrigieren (blind)
        row("DDD", d_pc, CUT7_MG),                      # Gegenprobe weicht ab → nicht schreiben
        row("EEE", d_pc, CUT7_MG),                      # Abruffehler → nicht schreiben
        row("FFF", date(2026, 6, 1), 5.0),              # ohne outcome_path → nie angefasst
    ]
    op = [{"ticker": t, "date": d.strftime("%d.%m.%Y"), "bars": jbars(d)}
          for t, d in (("AAA", d_pc), ("BBB", d_pc), ("CCC", d_rep), ("DDD", d_pc), ("EEE", d_pc))]
    exp = os.path.join(tmp, "ex.jsonl")
    opp = os.path.join(tmp, "op.jsonl")
    open(exp, "w").write("\n".join(ex) + "\n")
    open(opp, "w").write("\n".join(json.dumps(o) for o in op) + "\n")
    fetched = {"AAA": bars(d_pc), "CCC": bars(d_rep), "DDD": bars(d_pc, highs=HIGHS[:-1] + [14.0]),
               "EEE": None}
    return exp, opp, fetched


def test_all():
    with tempfile.TemporaryDirectory() as tmp:
        exp, opp, fetched = setup(tmp)
        mc.EXPORT_FILE, mc.OUTCOME_FILE = exp, opp
        lines = mc._read_lines(exp)
        cands = mc.find_candidates(lines, mc._load_outcome(opp))
        keys = sorted(c["key"][0] for c in cands)
        check("Kandidaten = AAA, CCC, DDD, EEE (nur abgeschnittene)", keys == ["AAA", "CCC", "DDD", "EEE"], keys)
        check("nur das abgeschnittene Feld (max_gain_pct)", all(c["felder"] == ["max_gain_pct"] for c in cands))
        final_cut = date(2026, 12, 1)
        corr, reasons = mc.compute_corrections(cands, lambda t: fetched.get(t), final_cut)
        check("Korrekturen nur AAA und CCC", sorted(c["ticker"] for c in corr) == ["AAA", "CCC"], corr)
        check("Gegenprobe-Abweichung gezählt (DDD)", reasons["gegenprobe_abweichung"] == 1, reasons)
        check("Abruffehler gezählt (EEE)", reasons["abruf_fehler"] == 1, reasons)
        # Tag 10 noch nicht final → nichts.
        c2, r2 = mc.compute_corrections(cands, lambda t: fetched.get(t), date(2026, 10, 2))
        check("Tag 10 nicht final → keine Korrektur", c2 == [] and r2["noch_nicht_final"] >= 1, r2)
        # Unvollständiges Fenster (fehlender Tag).
        gap = [b for i, b in enumerate(bars(date(2026, 10, 1))) if i != 5]
        c3, r3 = mc.compute_corrections([c for c in cands if c["key"][0] == "AAA"], lambda t: gap, final_cut)
        check("fehlender Tag → unvollständig, keine Korrektur", c3 == [] and r3["unvollstaendig"] == 1, r3)
        corr_path = os.path.join(tmp, "corr.json")
        json.dump(corr, open(corr_path, "w"))
        before = open(exp).read().splitlines()
        buf = io.StringIO()
        with redirect_stdout(buf):
            mc.apply(corr_path)
        after = open(exp).read().splitlines()
        check("Zeilenzahl gleich", len(before) == len(after))
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        check("nur Zeilen AAA (0) und CCC (2) geändert", changed == [0, 2], changed)
        for i in changed:
            a, b = json.loads(before[i]), json.loads(after[i])
            diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            allowed = {"max_gain_pct", "max_gain_pct_net", "rolling_window_n"}
            check(f"Zeile {i}: nur erlaubte Felder geändert", set(diff) <= allowed, diff)
            check(f"Zeile {i}: max_gain_pct = volles Fenster", b["max_gain_pct"] == FULL_MG, b["max_gain_pct"])
        check("max_gain_pct_net abgeleitet", json.loads(after[0])["max_gain_pct_net"] != 1.0)
        check("rolling_window_n = 11 nur wo vorhanden",
              json.loads(after[2])["rolling_window_n"] == 11 and "rolling_window_n" not in json.loads(after[0]))
        out = buf.getvalue()
        stats = json.loads(out.split("[maxgain_correction] apply ", 1)[1])
        check("Zählung vor/ab Replikation", stats["korrigiert_vor_replikation"] == 1
              and stats["korrigiert_replikation"] == 1, stats)
        check("Treffer-Wechsel nur Paper-C (AAA 22→47)", stats["treffer_wechsel_paper_c"] == 1, stats)
        check("Hash-Gleichheit der 4 unveränderten Zeilen", stats["hash_gleich"] == 4, stats)
        check("Blindheit: Ausgabe ohne Werte", str(FULL_MG) not in out and str(CUT7_MG) not in out, out)
        check("S17 nachher: kein Altbestand mehr außer DDD/EEE",
              stats["s17_nachher"]["alt"] == 2, stats["s17_nachher"])
        # Idempotenz.
        snap = open(exp).read()
        with redirect_stdout(io.StringIO()):
            mc.apply(corr_path)
        check("zweiter Lauf ändert nichts (idempotent)", open(exp).read() == snap)
        lines2 = mc._read_lines(exp)
        c_after = mc.find_candidates(lines2, mc._load_outcome(opp))
        check("nach Korrektur nur noch DDD/EEE Kandidaten", sorted(c["key"][0] for c in c_after) == ["DDD", "EEE"])
        # Dry-Run schreibt nicht.
        exp2, opp2, _ = setup(tmp)
        mc.EXPORT_FILE, mc.OUTCOME_FILE = exp2, opp2
        snap2 = open(exp2).read()
        with redirect_stdout(io.StringIO()):
            mc.apply(corr_path, dry_run=True)
        check("--dry-run schreibt nicht", open(exp2).read() == snap2)


def test_formula_equals_production():
    try:
        import pandas as pd
    except ImportError:
        print("  (übersprungen: pandas nicht verfügbar — CI-Slot)")
        return
    import backtest_history as bh
    b = bars(date(2026, 10, 1))
    df = pd.DataFrame({"High": [x["h"] for x in b], "Low": [x["l"] for x in b]})
    check("Formel = backtest_history (max_gain, max_drawdown)",
          mc.window_metrics(b) == (bh._compute_max_gain_pct(df), bh._compute_max_drawdown(df)),
          (mc.window_metrics(b), bh._compute_max_gain_pct(df), bh._compute_max_drawdown(df)))


def test_workflow_guards():
    wf = (ROOT / ".github" / "workflows" / "maxgain_export_correction.yml").read_text(encoding="utf-8")
    check("Workflow: nur Hand-Start, kein Cron", "workflow_dispatch" in wf and "schedule" not in wf)
    check("Workflow: kein upload-artifact (Korrekturdatei mit Werten bleibt lokal)",
          "upload-artifact" not in wf)
    check("Workflow: Abbruch bei laufendem Daily-Run", "daily-squeeze-report.yml" in wf)
    src = (ROOT / "scripts" / "maxgain_export_correction.py").read_text(encoding="utf-8")
    check("Rate-Limit → Exit 3 (kein halbes Apply)", 'return 3 if "rate_limit" in err_count' in src)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "x.jsonl")
        open(p, "w", encoding="utf-8").write('{"a": "x\u2028y"}\n{"b": 1}\n')
        check("Zeilen nur an \\n getrennt", mc._read_lines(p) == ['{"a": "x\u2028y"}', '{"b": 1}'])


def run_all() -> int:
    for t in (test_all, test_formula_equals_production, test_workflow_guards):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Export-Korrektur-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
