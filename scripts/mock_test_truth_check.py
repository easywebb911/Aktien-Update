"""Mock-Tests Wahrheits-Abgleich (scripts/truth_check.py) + Health-Check S16.

Kategorie A: deterministisch, OHNE Netz, ohne pandas/yfinance (künstliche
Kursreihen über eine injizierte Abruf-Funktion).

 a) korrekte Werte → 0 Abweichung
 b) ein manipuliertes return_5d → genau 1 Abweichung mit richtigem alt/neu
 c) Split im Fenster → Klasse neu_adjustiert
 d) Rate-Limit → unbekannt(rate_limit), KEIN Retry, Lauf endet sauber
 e) delisteter Ticker → nicht_pruefbar, kein Abruf
 f) Bootstrap-Zeile wird nicht geprüft
 + Erstlauf, Rotation deterministisch, SHA der drei Datendateien unverändert,
   Schreibziele nur Log/State (Quelltext-Grep), Formel-Spiegel = Produktion
   (nur wenn pandas da ist), S16-Stufen, Digest-Zeile im Byte-Budget.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import health_check as hc  # noqa: E402
import truth_check as tc  # noqa: E402

_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


# ── künstliche Kurswelt ──────────────────────────────────────────────────────
def _days(start: date, end: date):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in config.US_MARKET_HOLIDAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = _days(date(2026, 5, 1), date(2026, 10, 30))


def _series(base, step, wobble=0.0):
    rows = []
    for i, d in enumerate(DAYS):
        c = base + step * i + wobble * math.sin(i)
        rows.append({"d": d, "c": c, "h": c * 1.03, "l": c * 0.97, "div": 0.0, "split": 0.0})
    return rows


WORLD = {
    "SPY": _series(500.0, 0.6, 2.0),
    "^VIX": [{**r, "c": 15.0 + (i % 7) * 0.37} for i, r in enumerate(_series(1, 0))],
    "AAA": _series(10.0, 0.05, 0.4),
    "BBB": _series(20.0, -0.03, 0.5),
    "CCC": _series(5.0, 0.01, 0.2),
}
ENTRY = DAYS[100]           # genug SPY-Historie für das 50-Tage-Regime
NOW = datetime.combine(ENTRY + timedelta(days=40), datetime.min.time(),
                       tzinfo=timezone.utc).replace(hour=23, minute=30)


def _closes(t):
    return [(r["d"], r["c"]) for r in WORLD[t]]


def expected_row(t: str, d: date) -> dict:
    """Erwartete Werte unabhängig vom Prüfling (direkte Index-Arithmetik)."""
    cl = _closes(t)
    i = [x for x, _ in cl].index(d)
    c = [v for _, v in cl]
    sp = [v for _, v in _closes("SPY")]
    row = {"ticker": t, "date": d.strftime("%d.%m.%Y"), "entry_price": round(c[i] * 1.01, 2),
           "provenance": "forward"}
    for w in (3, 5, 10):
        r = round((c[i + w] / c[i] - 1) * 100, 2)
        row[f"return_{w}d"] = r
        h = abs(config.HAIRCUT_ROUND_TRIP_PCT) / 100 / 2
        row[f"return_{w}d_net"] = round(((1 + r / 100) * (1 - h) / (1 + h) - 1) * 100, 2)
        row[f"return_{w}d_vs_spy"] = round(r - (sp[i + w] / sp[i] - 1) * 100, 2)
        row[f"return_{w}d_t1"] = round((c[i + 1 + w] / c[i + 1] - 1) * 100, 2)
    rows = WORLD[t][i:i + 11]
    peak, dd = None, 0.0
    low, mg = None, 0.0
    dds, mgs = [], []
    for r in rows:
        peak = r["h"] if peak is None else max(peak, r["h"])
        low = r["l"] if low is None else min(low, r["l"])
        dds.append((r["l"] - peak) / peak * 100)
        mgs.append((r["h"] - low) / low * 100)
    row["max_drawdown_pct"] = round(min(dds), 2)
    row["max_gain_pct"] = round(max(mgs), 2)
    row["vix_level"] = round([v for dd_, v in _closes("^VIX") if dd_ == d][0], 2)
    dlt = (sp[i] - sp[i - 50]) / sp[i - 50] * 100
    row["market_regime"] = "bull" if dlt > 5 else ("bear" if dlt < -5 else "neutral")
    row["entry_past_return_5d"] = round((c[i] / c[i - 5] - 1) * 100, 2)
    return row


def shadow_row(t: str, d: date) -> dict:
    c = [v for _, v in _closes(t)]
    i = [x for x, _ in _closes(t)].index(d)
    out = {"schema_v": 1, "date": d.strftime("%d.%m.%Y"), "ticker": t, "signal_price": c[i]}
    for n in (3, 5, 10):
        out[f"forward_{n}d"] = round((c[i + n] - c[i]) / c[i] * 100, 2)
    return out


class Fetcher:
    def __init__(self, world=None, rate_limit_on=()):
        self.world = world or WORLD
        self.calls: list[str] = []
        self.rate_limit_on = set(rate_limit_on)

    def __call__(self, t, start, end):
        self.calls.append(t)
        if t in self.rate_limit_on:
            raise type("YFRateLimitError", (Exception,), {})("Too Many Requests")
        if t not in self.world:
            raise type("YFPricesMissingError", (Exception,), {})(
                '$X: possibly delisted (Yahoo error = "No data found, symbol may be delisted")')
        return [dict(r) for r in self.world[t] if start <= r["d"] < end]


def _setup(tmp: pathlib.Path, export_rows, shadow_rows, state=None):
    with open(tmp / config.MATURED_EXPORT_FILE, "w", encoding="utf-8") as fh:
        for r in export_rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    with open(tmp / "exit_shadow_log.jsonl", "w", encoding="utf-8") as fh:
        for r in shadow_rows:
            fh.write(json.dumps(r) + "\n")
    (tmp / "backtest_history.json").write_text(json.dumps([{"ticker": "AAA", "date": "x"}]))
    if state is not None:
        (tmp / config.TRUTH_CHECK_STATE_FILE).write_text(json.dumps(state))


FRESH_STATE = {"export_lines_seen": 0, "shadow_checked": [], "rotation_pos": 0}


def _run(export_rows, shadow_rows, fetcher, state=FRESH_STATE, rot_n=0, workers=2):
    orig = (config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS)
    config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS = rot_n, workers
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            _setup(tmp, export_rows, shadow_rows, state)
            line = tc.run(NOW, root=tmp, fetch_fn=fetcher)
            st = json.loads((tmp / config.TRUTH_CHECK_STATE_FILE).read_text())
            log = (tmp / config.TRUTH_CHECK_LOG_FILE).read_text().splitlines()
            return line, st, log
    finally:
        config.TRUTH_CHECK_ROTATION_N, config.TRUTH_CHECK_MAX_WORKERS = orig


# ── Tests ────────────────────────────────────────────────────────────────────
def test_a_correct():
    ex = [expected_row("AAA", ENTRY), expected_row("BBB", ENTRY)]
    sh = [shadow_row("AAA", DAYS[110])]
    line, st, log = _run(ex, sh, Fetcher())
    check("a: 3 Zeilen geprüft", line["n_zeilen"] == 3, line)
    check("a: 3 stimmt, 0 Abweichung", line["stimmt"] == 3 and line["abweichung"] == 0
          and line["neu_adjustiert"] == 0, line)
    check("a: alle Felder verglichen (2×17 + 3)", line["felder_verglichen"] == 2 * 17 + 3,
          line["felder_verglichen"])
    check("a: max |Δ| leer", line["max_abs_delta"] is None, line["max_abs_delta"])
    check("a: genau eine Log-Zeile", len(log) == 1)
    check("a: Abweichungs-Zeilen nicht erneut vorgemerkt", st["recheck"] == [])


def test_b_manipulated():
    good = expected_row("AAA", ENTRY)
    bad = dict(good, return_5d=round(good["return_5d"] + 1.5, 2))
    line, st, _ = _run([bad], [], Fetcher())
    devs = line["abweichungen"]
    check("b: genau 1 Abweichung", line["abweichung"] == 1 and len(devs) == 1, devs)
    if devs:
        d = devs[0]
        check("b: Feld return_5d", d["feld"] == "return_5d", d)
        check("b: alt = gespeicherter Wert", d["alt"] == bad["return_5d"], d)
        check("b: neu = Nachrechnung", d["neu"] == good["return_5d"], d)
        check("b: Klasse abweichung", d["klasse"] == "abweichung", d)
    check("b: max |Δ| = 1.5", abs((line["max_abs_delta"] or 0) - 1.5) < 1e-6, line["max_abs_delta"])
    check("b: Zeile für den nächsten Lauf vorgemerkt", len(st["recheck"]) == 1, st["recheck"])
    # Grenzfall: genau 0,02 Abstand ist noch keine Abweichung.
    edge = dict(good, return_3d=round(good["return_3d"] + 0.02, 2))
    line2, _, _ = _run([edge], [], Fetcher())
    check("b: Δ 0,02 liegt in der Toleranz", line2["abweichung"] == 0, line2["abweichungen"])


def test_c_split():
    world = copy.deepcopy(WORLD)
    i = [r["d"] for r in world["AAA"]].index(ENTRY)
    world["AAA"][i + 2]["split"] = 2.0
    good = expected_row("AAA", ENTRY)
    bad = dict(good, return_5d=round(good["return_5d"] - 3.0, 2))
    line, _, _ = _run([bad], [], Fetcher(world))
    devs = line["abweichungen"]
    check("c: Split im Fenster → neu_adjustiert", line["neu_adjustiert"] == 1
          and line["abweichung"] == 0 and devs and devs[0]["klasse"] == "neu_adjustiert", line)
    # Split AUSSERHALB des Fensters → bleibt echte Abweichung.
    world2 = copy.deepcopy(WORLD)
    world2["AAA"][i + 20]["split"] = 2.0
    line2, _, _ = _run([bad], [], Fetcher(world2))
    check("c: Split außerhalb → abweichung", line2["abweichung"] == 1, line2)


def test_d_rate_limit():
    ex = [expected_row("AAA", ENTRY), expected_row("BBB", ENTRY), expected_row("CCC", ENTRY)]
    f = Fetcher(rate_limit_on={"BBB"})
    line, st, _ = _run(ex, [], f, workers=1)
    check("d: BBB genau einmal abgefragt (kein Retry)", f.calls.count("BBB") == 1, f.calls)
    check("d: nach Rate-Limit kein weiterer Abruf", "CCC" not in f.calls, f.calls)
    check("d: 2 Zeilen unbekannt(rate_limit)", line["unbekannt"]["rate_limit"] == 2, line["unbekannt"])
    check("d: AAA trotzdem geprüft", line["stimmt"] == 1, line)
    check("d: Abbruch markiert", line["rate_limit_abbruch"] is True)
    check("d: Zeilen für Wiederholung vorgemerkt", len(st["retry"]) == 2, st["retry"])
    check("d: Ticker-Liste unbekannt", line["ticker_unbekannt"] == {"BBB": "rate_limit",
                                                                   "CCC": "rate_limit"}, line)
    # Yahoo-Fehler / ausdrücklich leer getrennt gezählt.
    f2 = Fetcher(world={k: v for k, v in WORLD.items() if k != "BBB"})
    line2, _, _ = _run([expected_row("BBB", ENTRY)], [], f2)
    check("d: 'No data found' → ausdruecklich_leer", line2["unbekannt"]["ausdruecklich_leer"] == 1,
          line2["unbekannt"])


def test_e_delisted():
    yy = dict(expected_row("AAA", ENTRY), ticker="YYGH")
    f = Fetcher()
    line, _, _ = _run([yy, expected_row("AAA", ENTRY)], [], f)
    check("e: delistet → nicht_pruefbar", line["nicht_pruefbar"] == 1, line)
    check("e: kein Abruf für YYGH", "YYGH" not in f.calls, f.calls)
    check("e: Liste in config", set(config.TRUTH_CHECK_DELISTED) ==
          {"BNRG", "PRA", "SNBR", "SNSE", "YYGH"})


def test_f_bootstrap():
    boot = dict(expected_row("CCC", ENTRY), source="bootstrap", return_5d=999.0)
    f = Fetcher()
    line, _, _ = _run([boot, expected_row("AAA", ENTRY)], [], f)
    check("f: Bootstrap-Zeile nicht im Umfang", line["n_zeilen"] == 1, line)
    check("f: kein Abruf für den Bootstrap-Ticker", "CCC" not in f.calls, f.calls)
    check("f: keine Abweichung", line["abweichung"] == 0, line)


def test_first_run_and_rotation():
    ex = [expected_row(t, ENTRY) for t in ("AAA", "BBB", "CCC")]
    f = Fetcher()
    line, st, _ = _run(ex, [], f, state=None, rot_n=2)
    check("Erstlauf: nichts gilt als frisch", line["n_frisch"] == 0, line)
    check("Erstlauf: Rotation AAA,BBB", line["rotation"] == ["AAA", "BBB"], line["rotation"])
    check("Erstlauf: export_lines_seen = Zeilenzahl", st["export_lines_seen"] == 3)
    _, _, n_fr, st2 = tc.plan_scope(ex, [], st, 2)
    _, rot3, _, _ = tc.plan_scope(ex, [], st2, 2)
    _, rot2, _, _ = tc.plan_scope(ex, [], st, 2)
    check("Rotation deterministisch + wrap", rot2 == ["CCC", "AAA"] and rot3 == ["BBB", "CCC"],
          (rot2, rot3))
    # Neue Exportzeile ist frisch.
    ex2 = ex + [expected_row("AAA", DAYS[101])]
    scope, _, n_fr, _ = tc.plan_scope(ex2, [], st, 0)
    check("frisch = Zeilen ab export_lines_seen", n_fr == 1 and len(scope) == 1, (n_fr, scope.keys()))


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_read_only():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        _setup(tmp, [expected_row("AAA", ENTRY)], [shadow_row("AAA", DAYS[110])], FRESH_STATE)
        files = [tmp / "backtest_history.json", tmp / config.MATURED_EXPORT_FILE,
                 tmp / "exit_shadow_log.jsonl"]
        before = [_sha(p) for p in files]
        tc.run(NOW, root=tmp, fetch_fn=Fetcher())
        after = [_sha(p) for p in files]
        check("SHA der drei Datendateien unverändert", before == after)
        written = sorted(p.name for p in tmp.iterdir())
        check("nur Log + State hinzugekommen", written == sorted(
            [p.name for p in files] + [config.TRUTH_CHECK_LOG_FILE, config.TRUTH_CHECK_STATE_FILE]),
            written)
    src = (ROOT / "scripts" / "truth_check.py").read_text(encoding="utf-8")
    opens = re.findall(r"open\(([^\n]*)\)", src)
    write_opens = [o for o in opens if re.search(r"""["'](w|a)["']""", o)]
    check("Schreib-open nur auf Log/State-tmp", len(write_opens) == 2 and all(
        "TRUTH_CHECK_LOG_FILE" in o or o.startswith("tmp") for o in write_opens), write_opens)
    check("kein Schreiben in Datendateien", not re.search(
        r"(write_text|json\.dump)\([^)]*(MATURED|exit_shadow|backtest_history)", src))


def test_mirror_vs_production():
    """Spiegel-Formeln == Produktion (nur wenn pandas verfügbar; im CI ohne
    pandas übersprungen — die erwarteten Werte oben sind unabhängig gerechnet)."""
    try:
        import pandas as pd
    except ImportError:
        print("  -- übersprungen (pandas fehlt)")
        return
    import types
    sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))
    try:
        import backtest_history as bh
    except Exception as exc:  # noqa: BLE001
        print(f"  -- übersprungen (backtest_history nicht importierbar: {exc!r})")
        return
    for g in (-80.0, -3.3, 0.0, 12.34, 950.0):
        check(f"Haircut-Spiegel {g}", tc._haircut(g) == bh.apply_round_trip_haircut(g))
    rows = [dict(r) for r in WORLD["BBB"][100:111]]
    rows[3]["h"] = float("nan")
    rows[6]["l"] = float("nan")
    df = pd.DataFrame({"High": [r["h"] for r in rows], "Low": [r["l"] for r in rows]},
                      index=pd.to_datetime([r["d"] for r in rows]))
    for k in (2, 5, 11):
        check(f"max_drawdown-Spiegel k={k}", tc._max_drawdown(rows[:k]) ==
              bh._compute_max_drawdown(df.iloc[:k]))
        check(f"max_gain-Spiegel k={k}", tc._max_gain(rows[:k]) ==
              bh._compute_max_gain_pct(df.iloc[:k]))
    c = [r["c"] for r in WORLD["AAA"]]
    check("EPR-Spiegel", round((c[100] / c[95] - 1) * 100, 2) ==
          bh._compute_entry_past_return_5d(c[100], c[95]))


def _log_line(ts, **kw):
    base = {"schema_v": 1, "run_ts": ts, "n_zeilen": 20, "n_frisch": 5, "stimmt": 20,
            "abweichung": 0, "neu_adjustiert": 0, "nicht_pruefbar": 0,
            "unbekannt": {"yahoo_fehler": 0, "ausdruecklich_leer": 0, "rate_limit": 0},
            "max_abs_delta": None, "abweichungen": [], "ticker_geprueft": ["AAA"],
            "ticker_unbekannt": {}}
    base.update(kw)
    return base


def _s16(lines, now):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "log.jsonl"
        if lines is not None:
            p.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return hc.evaluate_s16_truth_check(str(p), now_utc=now), hc.truth_check_digest_line(str(p))


def test_s16():
    now = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)      # Di
    ok_ts = "2026-11-09T23:10:00Z"                                  # Mo
    dev = {"datei": "export", "ticker": "AAA", "date": "01.10.2026", "feld": "return_5d",
           "alt": 1.0, "neu": 2.5, "klasse": "abweichung"}
    f, line = _s16([_log_line(ok_ts)], now)
    check("S16: sauberer Lauf → kein Fail", f == [], f)
    check("S16: Digest-Zeile Format", line == "🔍 Wahrheits-Abgleich: 20 Zeilen · 0 Abweichung · "
          "0 neu-adjustiert · 0 unbekannt (Yahoo 0, leer 0) · max |Δ| —", line)
    f, _ = _s16(None, now)
    check("S16: kein Log → warn läuft nicht", f and f[0]["severity"] == "warn"
          and "läuft nicht" in f[0]["detail"], f)
    f, _ = _s16([_log_line("2026-11-05T23:10:00Z")], now)      # Do → Fr,Mo,Di = 3
    check("S16: Log 3 Handelstage alt → warn", f and f[0]["severity"] == "warn"
          and "läuft nicht" in f[0]["detail"], f)
    f, _ = _s16([_log_line("2026-11-06T23:10:00Z")], now)      # Fr → Mo,Di = 2
    check("S16: Log 2 Handelstage alt → ok", f == [], f)
    f, line = _s16([_log_line(ok_ts, abweichung=1, max_abs_delta=1.5, abweichungen=[dev])], now)
    check("S16: 1 Abweichung → warn", f and f[0]["severity"] == "warn", f)
    check("S16: Digest max |Δ| deutsch", line.endswith("max |Δ| 1,50 pp"), line)
    f, _ = _s16([_log_line(ok_ts, abweichung=3, abweichungen=[dev] * 3)], now)
    check("S16: 3 Abweichungen → crit", f and f[0]["severity"] == "crit", f)
    f, _ = _s16([_log_line("2026-11-06T23:10:00Z", abweichung=1, abweichungen=[dev]),
                 _log_line(ok_ts, abweichung=1, abweichungen=[dev])], now)
    check("S16: gleiche Abweichung 2× in Folge → crit", f and f[0]["severity"] == "crit"
          and "2 Läufen" in f[0]["detail"], f)
    adj = dict(dev, klasse="neu_adjustiert")
    f, _ = _s16([_log_line(ok_ts, neu_adjustiert=1, abweichungen=[adj])], now)
    check("S16: neu_adjustiert allein → kein Fail", f == [], f)
    f, line = _s16([_log_line(ok_ts, unbekannt={"yahoo_fehler": 5, "ausdruecklich_leer": 2,
                                                "rate_limit": 0})], now)
    check("S16: 35 % unbekannt → warn", f and f[0]["severity"] == "warn" and "unbekannt" in
          f[0]["detail"], f)
    check("S16: Digest unbekannt (Yahoo 5, leer 2)", "7 unbekannt (Yahoo 5, leer 2)" in line, line)
    streak = [_log_line(f"2026-11-0{i}T23:10:00Z", ticker_geprueft=["ZZZ"],
                        ticker_unbekannt={"ZZZ": "yahoo_fehler"}) for i in range(2, 7)]
    streak.append(_log_line(ok_ts, ticker_geprueft=["AAA"]))       # ZZZ nicht dran
    streak.append(_log_line("2026-11-10T01:00:00Z", ticker_geprueft=["ZZZ"],
                            ticker_unbekannt={"ZZZ": "yahoo_fehler"}))
    f, _ = _s16(streak, now)
    check("S16: Ticker 6× geprüft-unbekannt in Folge → warn", f and "ZZZ (6×)" in f[0]["detail"], f)
    # evaluate_state_invariants: nur mit Pfad, nur Daily-Run.
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "log.jsonl"
        p.write_text(json.dumps(_log_line(ok_ts, abweichung=3, abweichungen=[dev] * 3)) + "\n")
        kw = dict(top10_tickers=["AAA"], today_iso=None, now_utc=now)
        ids = {x["id"] for x in hc.evaluate_state_invariants(**kw, truth_check_log_path=str(p))}
        check("S16 im Daily-Run-Pfad", "S16" in ids, ids)
        ids2 = {x["id"] for x in hc.evaluate_state_invariants(**kw)}
        check("ohne Pfad kein S16", "S16" not in ids2, ids2)
        ids3 = {x["id"] for x in hc.evaluate_state_invariants(
            **kw, ki_agent_only=True, truth_check_log_path=str(p))}
        check("ki_agent-Tick ohne S16", "S16" not in ids3, ids3)


def test_digest_budget():
    line = ("🔍 Wahrheits-Abgleich: 99999 Zeilen · 999 Abweichung · 999 neu-adjustiert · "
            "9999 unbekannt (Yahoo 999, leer 999, Rate-Limit 999) · max |Δ| 9999,99 pp")
    check("Digest-Zeile < 200 Byte (Worst Case)", len(line.encode()) < 200, len(line.encode()))
    crit = [{"id": "S16", "severity": "crit", "detail": "Wahrheits-Abgleich: 3 Zeilen weichen ab",
             "count": 1, "recovered": False}]
    body, title, _, _ = hc.format_digest_body(crit, [], n_runs=4, last_run_iso="x",
                                              digest_date="2026-11-10", truth_check_line=line)
    check("crit-Digest enthält Zeile", line in body)
    check("crit-Digest hat S16-Diagnose-Block", "[S16] Wahrheits-Abgleich" in body)
    check("crit-Body im Byte-Budget", len(body.encode()) <= hc.DIGEST_BODY_SAFE_BYTES,
          len(body.encode()))
    body2, _, _, _ = hc.format_digest_body([], [], n_runs=4, last_run_iso="x",
                                           digest_date="2026-11-10", truth_check_line=line)
    check("OK-Digest enthält Zeile", line in body2)
    body3, _, _, _ = hc.format_digest_body([], [], n_runs=0, last_run_iso=None,
                                           digest_date="2026-11-10", truth_check_line=line)
    check("Ohne-Daten-Digest enthält Zeile", line in body3)
    wf = (ROOT / ".github" / "workflows" / "truth_check.yml").read_text(encoding="utf-8")
    adds = re.findall(r"git add ([^\n]+)", wf)
    check("Workflow: git add nur Log + State",
          adds == ["truth_check_log.jsonl truth_check_state.json"], adds)
    check("Workflow: Cron werktags 23:07", "cron: '7 23 * * 1-5'" in wf)
    check("Workflow: kein healthchecks-Ping", "hc_ping" not in wf and "HC_PING" not in wf)


def _world_with(t: str, d: date, **vals):
    """Kopie von WORLD; Zeile ``d`` von ``t`` mit überschriebenen Werten."""
    w = {k: [dict(r) for r in v] for k, v in WORLD.items()}
    for r in w[t]:
        if r["d"] == d:
            r.update(vals)
    return w


def test_g_runtime_rule():
    """Fix 10.11.2026: vix_level / market_regime gegen die PRODUKTIONS-
    Definition (Wert zum Laufzeitpunkt) statt nur gegen den Tagesschluss."""
    i = DAYS.index(ENTRY)
    prev = DAYS[i - 1]
    w = _world_with("^VIX", ENTRY, c=20.0, h=21.0, l=19.0)
    w = {**w, "^VIX": [dict(r, c=17.5) if r["d"] == prev else r for r in w["^VIX"]]}
    good = expected_row("AAA", ENTRY)
    good["vix_level"] = 20.0

    def run_vix(v):
        line, st, _ = _run([dict(good, vix_level=v)], [], Fetcher(world=w))
        return line, st

    # Intraday-Lauf: Wert in der Tagesspanne, nicht der Schluss → stimmt.
    line, _ = run_vix(19.4)
    check("g: Wert in Spanne → stimmt", line["stimmt"] == 1 and line["abweichung"] == 0,
          line["abweichungen"])
    notes = [n for n in line.get("laufzeit_regel", []) if n["feld"] == "vix_level"]
    check("g: Bestätigung mit Spanne geloggt",
          len(notes) == 1 and notes[0]["regel"] == "spanne" and notes[0]["tief"] == 19.0
          and notes[0]["hoch"] == 21.0 and notes[0]["schluss"] == 20.0, notes)
    # Lauf vor Börsenöffnung: Vortagsschluss (außerhalb der Spanne) → stimmt.
    line, _ = run_vix(17.5)
    check("g: Vortagsschluss → stimmt", line["stimmt"] == 1, line["abweichungen"])
    check("g: Regel vortag geloggt",
          [n["regel"] for n in line["laufzeit_regel"]] == ["vortag"], line["laufzeit_regel"])
    # Exakter Schluss → stimmt, ohne Laufzeit-Notiz.
    line, _ = run_vix(20.0)
    check("g: Schluss → stimmt ohne Notiz",
          line["stimmt"] == 1 and line["laufzeit_regel"] == [], line)
    # Außerhalb Spanne und ≠ Vortag → bleibt Abweichung (kein Stummschalten).
    line, st = run_vix(22.5)
    devs = line["abweichungen"]
    check("g: außerhalb Spanne → abweichung",
          line["abweichung"] == 1 and len(devs) == 1 and devs[0]["feld"] == "vix_level"
          and devs[0]["neu"] == 20.0 and devs[0]["klasse"] == "abweichung", devs)
    check("g: Abweichung vorgemerkt", len(st["recheck"]) == 1, st["recheck"])
    # Ränder: Toleranz 0,02 an der Spanne.
    check("g: Tief − 0,02 stimmt", run_vix(18.98)[0]["abweichung"] == 0)
    check("g: Tief − 0,03 weicht ab", run_vix(18.97)[0]["abweichung"] == 1)
    check("g: Hoch + 0,02 stimmt", run_vix(21.02)[0]["abweichung"] == 0)
    check("g: Hoch + 0,03 weicht ab", run_vix(21.03)[0]["abweichung"] == 1)
    # Determinismus: gleiche Eingabe → gleiche Log-Zeile.
    a, _ = run_vix(19.4)
    b, _ = run_vix(19.4)
    check("g: deterministisch", a == b)
    # Pure Regel-Funktion.
    spec = {"schluss": 20.0, "tief": 19.0, "hoch": 21.0, "vortag": 17.5}
    check("g: vix_runtime_verdict",
          [tc.vix_runtime_verdict(v, spec, 0.02) for v in (20.0, 19.5, 17.5, 25.0)]
          == ["schluss", "spanne", "vortag", None])
    check("g: fehlende Spanne → nur Schluss/Vortag",
          tc.vix_runtime_verdict(19.5, dict(spec, tief=None), 0.02) is None)


def test_h_regime_runtime():
    """market_regime: Regime aus einem SPY-Kurs in der Tagesspanne → stimmt;
    unerreichbares Regime → abweichung."""
    i = DAYS.index(ENTRY)
    sp = WORLD["SPY"]
    ref = sp[i - 50]["c"]
    # Schluss knapp unter +5 % (neutral), Tageshoch darüber (bull erreichbar),
    # Tief im neutralen Band; Vortag neutral.
    c, h, lo = ref * 1.049, ref * 1.06, ref * 1.03
    w = _world_with("SPY", ENTRY, c=c, h=h, l=lo)
    good = expected_row("AAA", ENTRY)

    def run_regime(rg):
        line, _, _ = _run([dict(good, market_regime=rg)], [], Fetcher(world=w))
        return line

    def regime_devs(line):
        return [d for d in line["abweichungen"] if d["feld"] == "market_regime"]

    line = run_regime("neutral")
    check("h: Schluss-Regime neutral → keine Regime-Abweichung", regime_devs(line) == [],
          line["abweichungen"])
    line = run_regime("bull")
    check("h: bull (Intraday erreichbar) → keine Regime-Abweichung",
          regime_devs(line) == [], line["abweichungen"])
    check("h: bull als Laufzeit-Regel geloggt",
          any(n["feld"] == "market_regime" and n["alt"] == "bull"
              for n in line["laufzeit_regel"]), line["laufzeit_regel"])
    line = run_regime("bear")
    rd = regime_devs(line)
    check("h: bear unerreichbar → abweichung",
          len(rd) == 1 and rd[0]["neu"] == "neutral", line["abweichungen"])
    check("h: _regimes_between",
          tc._regimes_between(3.0, 6.0) == {"neutral", "bull"}
          and tc._regimes_between(-7.0, -6.0) == {"bear"}
          and tc._regimes_between(-6.0, 6.0) == {"bear", "neutral", "bull"})


def run_all() -> int:
    for t in (test_a_correct, test_b_manipulated, test_c_split, test_d_rate_limit,
              test_e_delisted, test_f_bootstrap, test_first_run_and_rotation,
              test_read_only, test_mirror_vs_production, test_s16, test_digest_budget,
              test_g_runtime_rule, test_h_regime_runtime):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Wahrheits-Abgleich-Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle Wahrheits-Abgleich-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
