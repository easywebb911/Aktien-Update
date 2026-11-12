#!/usr/bin/env python3
"""Messlauf (read-only): wie viele seit den Bestandskorrekturen gefüllte
Einmal-Felder stimmen mit dem ENDGÜLTIGEN Schlusskurs?

Easy-Entscheid 12.11.2026 (open_item rendite-forward-abendzeile-nicht-final):
Vorwärts-Fix + Messlauf im selben PR; Korrektur alter Werte erst nach der
Messung und nur auf Easys Entscheid. Dieses Skript KORRIGIERT NICHTS.

Umfang: ``return_{3,5,10}d`` / ``_t1`` / ``_net`` in ``backtest_history.json``
(ohne Bootstrap) und ``forward_{3,5,10}d`` in ``exit_shadow_log.jsonl``, deren
Wert zuletzt NACH der Bestandskorrektur geschrieben wurde (03.11.2026
21:19:49 UTC bzw. 04.11.2026 21:10:54 UTC), Einstieg ab 21.07.2026. Der
Füll-Zeitpunkt kommt aus der Git-Historie (Commit-Zeit, ET), eingeteilt in
Zieltag vor 16:20 / 16:20–21:00 / ab 21:00 ET / Folgetag oder später.

Nachrechnen exakt wie der Wahrheits-Abgleich (scripts/truth_check.py:
``recompute_backtest`` / ``recompute_shadow``, eigene Handelstage des Tickers,
``auto_adjust=True``, ``actions=True``), aber nur mit ENDGÜLTIGEN Zeilen
(``trading_date.last_settled_close_date``). Toleranz
``config.TRUTH_CHECK_TOLERANCE_PP`` (0,02 pp). Dividende/Split im Fenster →
``neu_adjustiert``, nicht ``abweichung``.

BLINDHEIT: Einstiege ≥ 24.10.2026 (Replikationsfenster, darin alle
Exit-B.1-Nachfolger-Zeilen ab 09.11.) → NUR Anzahlen, keine Werte, keine
Richtung. Einstiege < 24.10.: zusätzlich Verteilung |Δ| und Vorzeichen-Wechsel.

Abbruch (Exit 3, keine Ergebnisdatei) bei Rate-Limit. Schreibt NUR die
Ergebnisdatei (``--out``), nichts im Repo.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import trading_date  # noqa: E402
import truth_check as tc  # noqa: E402

START = date(2026, 7, 21)
REPL_FROM = date(2026, 10, 24)
EXIT_SUCC_FROM = date(2026, 11, 9)
BT_SINCE = "2026-11-03T21:19:50Z"   # nach Renditen-Bestandskorrektur 872ac43f
ES_SINCE = "2026-11-04T21:10:55Z"   # nach Forward-Bestandskorrektur 14d48873
BT_FILE = "backtest_history.json"
ES_FILE = "exit_shadow_log.jsonl"
WINDOWS = (3, 5, 10)
BT_FIELDS = tuple(f"return_{w}d{s}" for w in WINDOWS for s in ("", "_t1", "_net"))
ES_FIELDS = tuple(f"forward_{w}d" for w in WINDOWS)
BUCKETS = ("zieltag_vor_1620", "zieltag_1620_2100", "zieltag_ab_2100", "folgetag_oder_spaeter")
_NY = trading_date._NY


def group_of(field: str) -> str:
    if field.startswith("forward_"):
        return "forward"
    if field.endswith("_t1"):
        return "t1"
    if field.endswith("_net"):
        return "net"
    return "return"


def offset_of(field: str) -> int:
    w = int(field.split("_")[1][:-1])
    return w + (1 if field.endswith("_t1") else 0)


def window_of(edate: date) -> str:
    return "replikation" if edate >= REPL_FROM else "vor_replikation"


def bucket_of(fill_utc: datetime, target: date) -> str:
    et = fill_utc.astimezone(_NY)
    if et.date() < target:
        return "zieltag_vor_1620"          # vor dem Zieltag: hier nicht erwartet, zählt mit
    if et.date() == target:
        if et.time() < trading_date.US_CLOSE_FINAL_ET:
            return "zieltag_vor_1620"
        return "zieltag_1620_2100" if et.time() < time(21, 0) else "zieltag_ab_2100"
    return "folgetag_oder_spaeter"


# ── Git-Historie: wann wurde ein Feldwert zuletzt geschrieben? ──────────────
def _git(*a) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout


def _bt_rows(text: str) -> list:
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return []
    return [e for e in d if isinstance(e, dict) and "bootstrap" not in str(e.get("source", ""))]


def _es_rows(text: str) -> list:
    out = []
    for line in (text or "").split("\n"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def fill_times(path: str, since: str, fields: tuple, loader, ref: str = "HEAD") -> dict:
    """``{(ticker, date, feld): commit_utc}`` für Werte, die NACH ``since``
    zuletzt geschrieben/geändert wurden. Werte liegen nur im Speicher
    (Gleich/Ungleich), werden nie ausgegeben."""
    base = _git("rev-list", "-1", f"--before={since}", ref, "--", path).strip()
    commits = [l.split() for l in _git("log", "--reverse", "--format=%H %cI",
                                       f"--since={since}", ref, "--", path).split("\n") if l]
    last, when = {}, {}
    seq = ([(base, None)] if base else []) + [(h, ts) for h, ts in commits]
    for h, ts in seq:
        t = datetime.fromisoformat(ts) if ts else None
        for e in loader(_git("show", f"{h}:{path}")):
            for f in fields:
                v = e.get(f)
                if v is None:
                    continue
                k = (e.get("ticker"), e.get("date"), f)
                if last.get(k) != v:
                    last[k] = v
                    when[k] = t
    return {k: t for k, t in when.items() if t is not None}


# ── Auswertung (pure, testbar) ───────────────────────────────────────────────
def _new_cell():
    return {"geprueft": 0, "stimmt": 0, "weicht_ab": 0, "neu_adjustiert": 0, "nicht_pruefbar": 0}


def evaluate(items: list, series: dict, unknown: dict, final_cut: date, tol: float) -> dict:
    """``items``: Dicts ``{datei, row, feld, bucket}``. Returnt das
    Ergebnis-Dict (Zählungen; Werte-Statistik nur vor Replikation)."""
    delisted = set(getattr(config, "TRUTH_CHECK_DELISTED", ()))
    counts: dict = {}
    deltas_pre: dict = {}
    sign_pre: dict = {}
    rec_cache: dict = {}
    for it in items:
        row, f, datei = it["row"], it["feld"], it["datei"]
        edate = tc._dmy(row.get("date"))
        win = window_of(edate)
        key = (win, group_of(f), it["bucket"])
        cell = counts.setdefault(key, _new_cell())
        t = row.get("ticker")
        s = series.get(t)
        if t in delisted or t in unknown or s is None:
            cell["nicht_pruefbar"] += 1
            continue
        ck = (datei, t, row.get("date"))
        if ck not in rec_cache:
            rec_cache[ck] = (tc.recompute_shadow(row, s, final_cut) if datei == "exit_shadow"
                             else tc.recompute_backtest(row, s, None, None, final_cut, final_cut))
        rec = rec_cache[ck]
        alt = tc._num(row.get(f))
        if alt is None or f not in rec or rec[f][0] is None:
            cell["nicht_pruefbar"] += 1
            continue
        neu, span, _srcs = rec[f]
        cell["geprueft"] += 1
        d = abs(neu - alt)
        if d <= tol + 1e-9:
            cell["stimmt"] += 1
            continue
        if s.has_action(span[0], span[1]):
            cell["neu_adjustiert"] += 1
            continue
        cell["weicht_ab"] += 1
        if win == "vor_replikation":
            g = group_of(f)
            deltas_pre.setdefault(g, []).append(d)
            if (alt > 0 > neu) or (alt < 0 < neu):
                sign_pre[g] = sign_pre.get(g, 0) + 1
    return {"counts": counts, "deltas_pre": deltas_pre, "sign_pre": sign_pre}


def _quant(xs: list, q: float) -> float:
    ys = sorted(xs)
    if not ys:
        return None
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return round(ys[i], 2)


def summarize(ev: dict, extra: dict) -> dict:
    tab = []
    for (win, grp, b), c in sorted(ev["counts"].items()):
        tab.append({"fenster": win, "feldgruppe": grp, "fuellzeit": b, **c})
    dist = {}
    for g, xs in sorted(ev["deltas_pre"].items()):
        dist[g] = {"n": len(xs), "median": _quant(xs, 0.5), "p90": _quant(xs, 0.9),
                   "max": round(max(xs), 2),
                   "ueber_0_5pp": sum(x > 0.5 for x in xs),
                   "ueber_1pp": sum(x > 1.0 for x in xs),
                   "ueber_5pp": sum(x > 5.0 for x in xs),
                   "vorzeichen_wechsel": ev["sign_pre"].get(g, 0)}
    return {**extra, "tabelle": tab, "vor_replikation_abweichung_absdelta": dist}


def collect_items(ref: str = "HEAD") -> list:
    items = []
    bt_now = {(e.get("ticker"), e.get("date")): e
              for e in _bt_rows((ROOT / BT_FILE).read_text(encoding="utf-8"))}
    for (t, ds, f), ts in fill_times(BT_FILE, BT_SINCE, BT_FIELDS, _bt_rows, ref).items():
        ed = tc._dmy(ds)
        row = bt_now.get((t, ds))
        if ed is None or ed < START or row is None:
            continue
        tgt = trading_date.nth_trading_day_after(ed, offset_of(f), config.US_MARKET_HOLIDAYS)
        items.append({"datei": "backtest", "row": row, "feld": f, "bucket": bucket_of(ts, tgt)})
    es_now = {(r.get("ticker"), r.get("date")): r
              for r in _es_rows((ROOT / ES_FILE).read_text(encoding="utf-8"))}
    for (t, ds, f), ts in fill_times(ES_FILE, ES_SINCE, ES_FIELDS, _es_rows, ref).items():
        ed = tc._dmy(ds)
        row = es_now.get((t, ds))
        if ed is None or ed < START or row is None:
            continue
        tgt = trading_date.nth_trading_day_after(ed, offset_of(f), config.US_MARKET_HOLIDAYS)
        items.append({"datei": "exit_shadow", "row": row, "feld": f, "bucket": bucket_of(ts, tgt)})
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--now", default=None)
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now
           else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    final_cut = trading_date.last_settled_close_date(now)
    items = collect_items()
    need: dict = {}
    for it in items:
        d = tc._dmy(it["row"].get("date"))
        need[it["row"]["ticker"]] = min(need.get(it["row"]["ticker"], d), d)
    starts = {t: d - timedelta(days=15) for t, d in need.items()}
    end = now.astimezone(timezone.utc).date() + timedelta(days=2)
    series, unknown = tc.fetch_all(sorted(need), starts, end, tc.yahoo_fetch,
                                   workers=int(config.TRUTH_CHECK_MAX_WORKERS))
    if any(v == "rate_limit" for v in unknown.values()):
        print("[settled_measure] ABBRUCH: Rate-Limit — kein Retry, kein Ergebnis.", flush=True)
        return 3
    ev = evaluate(items, series, unknown, final_cut, float(config.TRUTH_CHECK_TOLERANCE_PP))
    n_exit_succ = sum(1 for it in items if tc._dmy(it["row"].get("date")) >= EXIT_SUCC_FROM)
    out = summarize(ev, {
        "run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endgueltig_bis": final_cut.isoformat(),
        "felder_gesamt": len(items),
        "davon_exit_nachfolger_einstieg_ab_0911": n_exit_succ,
        "ticker": len(need),
        "ticker_unbekannt": len(unknown),
        "toleranz_pp": float(config.TRUTH_CHECK_TOLERANCE_PP),
    })
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    print("[settled_measure] " + json.dumps(out, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
