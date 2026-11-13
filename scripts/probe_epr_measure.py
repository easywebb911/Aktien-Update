#!/usr/bin/env python3
"""WEGWERF-MESSLAUF (read-only): ``entry_past_return_5d`` gegen die Rechnung
auf den EIGENEN Handelstagen des Tickers (open_item
``epr-gemeinsamer-index-vs-eigene-handelstage``; Easy-Auftrag 13.11.2026).

Produktion (``generate_report._hist_stats`` + ``backtest_history.
_compute_entry_past_return_5d``): Zähler ``s["price"]`` (Kurs zum Laufzeitpunkt),
Nenner ``df["Close"].iloc[-6]`` aus dem Mehr-Ticker-Download (gemeinsamer Index
aller Ticker, ohne ``dropna``). Prüfrechnung (wie ``scripts/truth_check.py``):
Close am Einstiegstag / Close 5 eigene Handelstage davor − 1, in %, auf 2
Stellen gerundet, ``auto_adjust=True``, nur endgültige Schlusskurse.

Umfang: ALLE forward-Zeilen = Export ``provenance == forward`` ∪
``backtest_history.json`` ohne Bootstrap ab 21.07.2026 (Schlüssel Ticker+Datum;
steht der Wert in beiden, gilt der Export-Wert, Unterschiede werden gezählt).

BLINDHEIT: Es wird AUSSCHLIESSLICH ``ticker``, ``date``, ``provenance``,
``source``, ``entry_price`` (Kurs-Snapshot, kein Ergebnis — nur für die
Ursachen-Zuordnung „Zähler = Laufzeitkurs“) und ``entry_past_return_5d``
gelesen — die Projektion passiert direkt beim Einlesen, kein Ergebnisfeld wird
übernommen oder gezählt. Einstiege ≥ 24.10.2026: nur Anzahlen und Größen der
Prädiktor-Abweichungen, keine Ticker/Daten im Log.

Ursachen (nur für Abweichungen, Reihenfolge fest):
``aktion_seit_nenner`` (Split/Dividende zwischen Nenner-Tag und heute),
``luecke_index`` (eigener Nenner-Tag ≠ 5. US-Handelstag vor Einstieg →
Handelsaussetzung bzw. Lücke im gemeinsamen Index), ``zaehler_laufzeitkurs``
(gespeicherter Wert = entry_price / eigener Nenner), ``sonstiges``.

Rate-Limit → Abbruch (Exit 3), KEIN Teilbefund, keine Ergebnisdatei. Schreibt
NUR ``--out``. Wird nach der Auswertung per Cleanup-PR gelöscht.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import trading_date  # noqa: E402
import truth_check as tc  # noqa: E402

FORWARD_FROM = date(2026, 7, 21)
BLIND_FROM = date(2026, 10, 24)
PROBE_END_ET = date(2026, 12, 5)            # danach no-op (Sicherheitsnetz bis Cleanup)
FIELD = "entry_past_return_5d"
KEEP = ("ticker", "date", "provenance", "source", "entry_price", FIELD)   # BLINDHEIT
CAUSES = ("aktion_seit_nenner", "luecke_index", "zaehler_laufzeitkurs", "sonstiges")
RANK_STEPS = (2, 5, 10)


def _project(e: dict) -> dict:
    return {k: e.get(k) for k in KEEP}


def load_rows(root: pathlib.Path = ROOT) -> tuple[dict, int]:
    """``({(ticker, date): {"wert", "entry_price", "quelle"}}, n_export_ungleich_bh)``."""
    exp, bh = {}, {}
    for e in tc._read_jsonl(root / config.MATURED_EXPORT_FILE):
        p = _project(e)
        if p["provenance"] == "forward" and p["ticker"] and p["date"]:
            exp[(p["ticker"], p["date"])] = p
    try:
        raw = json.load(open(root / config.BACKTEST_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        raw = []
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        p = _project(e)
        d = tc._dmy(p["date"])
        if p["source"] == "bootstrap" or d is None or d < FORWARD_FROM or not p["ticker"]:
            continue
        bh[(p["ticker"], p["date"])] = p
    rows, diff = {}, 0
    for k in sorted(set(exp) | set(bh)):
        e, b = exp.get(k), bh.get(k)
        if e and b and tc._num(e[FIELD]) is not None and tc._num(b[FIELD]) is not None \
                and abs(tc._num(e[FIELD]) - tc._num(b[FIELD])) > 1e-9:
            diff += 1
        src = e if (e and tc._num(e[FIELD]) is not None) else (b or e)
        rows[k] = {"wert": tc._num(src[FIELD]), "entry_price": tc._num(src["entry_price"]),
                   "quelle": "export" if src is e else "backtest_history"}
    return rows, diff


def nth_trading_day_before(d: date, n: int) -> date:
    x, k = d, 0
    while k < n:
        x -= timedelta(days=1)
        if x.weekday() < 5 and x.isoformat() not in config.US_MARKET_HOLIDAYS:
            k += 1
    return x


def evaluate_one(alt, entry_price, s, edate: date, final_cut: date, today: date, tol: float) -> dict:
    """Pure. Returnt ``{"status": stimmt|abweichung|unbekannt, ...}``."""
    if alt is None:
        return {"status": "unbekannt", "grund": "kein_gespeicherter_wert"}
    if s is None:
        return {"status": "unbekannt", "grund": "keine_kursreihe"}
    if edate > final_cut:
        return {"status": "unbekannt", "grund": "nicht_endgueltig"}
    ei = s.cpos(edate)
    if ei < 0:
        return {"status": "unbekannt", "grund": "einstiegstag_fehlt"}
    if ei < 5:
        return {"status": "unbekannt", "grund": "zu_wenig_tage_davor"}
    num, den, dden = s.closes[ei][1], s.closes[ei - 5][1], s.cidx[ei - 5]
    if not den or den <= 0:
        return {"status": "unbekannt", "grund": "nenner_ungueltig"}
    neu = round((num / den - 1.0) * 100.0, 2)
    delta = abs(neu - alt)
    out = {"status": "stimmt" if delta <= tol + 1e-9 else "abweichung", "neu": neu,
           "delta": delta, "vorzeichen_wechsel": (alt > 0 > neu) or (alt < 0 < neu)}
    if out["status"] == "abweichung":
        cal = nth_trading_day_before(edate, 5)
        if s.has_action(dden, today):
            cause = "aktion_seit_nenner"
        elif dden != cal:
            cause = "luecke_index"
        elif entry_price and entry_price > 0 and abs(round((entry_price / den - 1) * 100, 2) - alt) <= tol + 1e-9:
            cause = "zaehler_laufzeitkurs"
        else:
            cause = "sonstiges"
        out["ursache"] = cause
        ci = s.cpos(cal)
        if ci >= 0 and s.closes[ci][1] > 0:   # Produktions-Nenner (gemeinsamer Index)
            out["kalender_wert_passt"] = abs(round((num / s.closes[ci][1] - 1) * 100, 2) - alt) <= tol + 1e-9
        out["nenner_eigen"] = dden.isoformat()
        out["nenner_kalender"] = cal.isoformat()
    return out


def _quant(xs: list, q: float):
    ys = sorted(xs)
    if not ys:
        return None
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return round(ys[i], 4)


def _ranks(vals: list) -> list:
    order = sorted(range(len(vals)), key=lambda i: (vals[i], i))
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def rank_summary(pairs: list) -> dict:
    """``pairs`` = [(alt, neu)]. Spearman (Pearson der Ränge) + Rang-Wanderung."""
    n = len(pairs)
    if n < 3:
        return {"n": n}
    ra, rn = _ranks([a for a, _ in pairs]), _ranks([b for _, b in pairs])
    ma, mn = sum(ra) / n, sum(rn) / n
    cov = sum((x - ma) * (y - mn) for x, y in zip(ra, rn))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vn = math.sqrt(sum((y - mn) ** 2 for y in rn))
    moves = [abs(x - y) for x, y in zip(ra, rn)]
    return {"n": n, "spearman": round(cov / (va * vn), 6) if va and vn else None,
            **{f"rang_wandert_ueber_{k}": sum(m > k for m in moves) for k in RANK_STEPS},
            "rang_wanderung_max": max(moves)}


def summarize(results: list, blind: bool) -> dict:
    cmp = [r for r in results if r["status"] in ("stimmt", "abweichung")]
    dev = [r for r in cmp if r["status"] == "abweichung"]
    deltas = [r["delta"] for r in cmp]
    out = {"geprueft": len(cmp), "stimmt": len(cmp) - len(dev), "weicht_ab": len(dev),
           "unbekannt": {}, "absdelta_alle": {"median": _quant(deltas, 0.5),
                                              "p90": _quant(deltas, 0.9),
                                              "max": round(max(deltas), 4) if deltas else None},
           "absdelta_abweichungen": {"median": _quant([r["delta"] for r in dev], 0.5),
                                     "p90": _quant([r["delta"] for r in dev], 0.9),
                                     "max": round(max(r["delta"] for r in dev), 4) if dev else None},
           "vorzeichen_wechsel": sum(r["vorzeichen_wechsel"] for r in cmp),
           "ueber_1pp": sum(r["delta"] > 1.0 for r in cmp),
           "ursachen": {c: sum(r.get("ursache") == c for r in dev) for c in CAUSES},
           "abweichung_mit_kalender_nenner_erklaert": sum(r.get("kalender_wert_passt") is True for r in dev),
           "rang": rank_summary([(r["alt"], r["neu"]) for r in cmp])}
    for r in results:
        if r["status"] == "unbekannt":
            out["unbekannt"][r["grund"]] = out["unbekannt"].get(r["grund"], 0) + 1
    top = sorted(dev, key=lambda r: -r["delta"])[:15]
    if blind:
        out["groesste"] = [{"delta": round(r["delta"], 4), "ursache": r["ursache"]} for r in top]
    else:
        out["groesste"] = [{k: r.get(k) for k in ("ticker", "date", "alt", "neu", "ursache",
                                                  "nenner_eigen", "nenner_kalender",
                                                  "kalender_wert_passt")}
                           | {"delta": round(r["delta"], 4)} for r in top]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Messlauf entry_past_return_5d (read-only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--now", default=None)
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now
           else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = now.astimezone(trading_date._NY).date()
    if today > PROBE_END_ET:
        print("[epr_measure] no-op: Probe-Ende überschritten")
        return 0
    final_cut = trading_date.last_settled_close_date(now)
    tol = float(config.TRUTH_CHECK_TOLERANCE_PP)
    rows, n_diff = load_rows()
    need: dict = {}
    for (t, ds) in rows:
        d = tc._dmy(ds)
        need[t] = min(need.get(t, d), d)
    starts = {t: d - timedelta(days=20) for t, d in need.items()}
    series, unknown = tc.fetch_all(sorted(need), starts, today + timedelta(days=2), tc.yahoo_fetch,
                                   workers=int(config.TRUTH_CHECK_MAX_WORKERS))
    if any(v == "rate_limit" for v in unknown.values()):
        print("[epr_measure] ABBRUCH: Rate-Limit — kein Retry, kein Ergebnis.", flush=True)
        return 3
    pre, blind = [], []
    for (t, ds), v in sorted(rows.items()):
        ed = tc._dmy(ds)
        r = evaluate_one(v["wert"], v["entry_price"], series.get(t), ed, final_cut, today, tol)
        if t in unknown and r.get("grund") == "keine_kursreihe":
            r["grund"] = f"yahoo:{unknown[t]}"
        r.update({"ticker": t, "date": ds, "alt": v["wert"]})
        (blind if ed >= BLIND_FROM else pre).append(r)
    out = {"run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "endgueltig_bis": final_cut.isoformat(),
           "toleranz_pp": tol, "zeilen": len(rows), "ticker": len(need),
           "ticker_ohne_kursreihe": len(unknown), "export_ungleich_backtest_history": n_diff,
           "vor_2410": summarize(pre, blind=False),
           "ab_2410_nur_praediktor": summarize(blind, blind=True)}
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    print("[epr_measure] " + json.dumps(out, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
