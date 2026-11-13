#!/usr/bin/env python3
"""WEGWERF-PROBE (read-only): Beleg für die S16-Abweichungen BJDX (13.11.2026,
open_item ``truth-check-nachadjustierung-ausserhalb-fenster``).

Frage: Zeigen die Yahoo-Aktionsdaten eine Kapitalmaßnahme (Split/Dividende)
zwischen den Rechenfenstern der drei BJDX-Zeilen (14.07./15.07./05.08.2026) und
heute — mit Datum und Faktor? Und welche Nachkommastellen / welches Kursniveau
haben die heute gelieferten bereinigten Kurse (Grundlage der Rundungsschranke)?

Zum Vergleich dieselben Angaben für AMCX und ARCT (übrige S16-Fälle).

Liest NUR die drei BJDX-Export-Zeilen (alle Einstiege < 24.10.2026, kein
Blind-Fenster) für das Nachrechnen wie ``scripts/truth_check.py``. Schreibt
nichts ins Repo — nur stdout (``[bjdx_probe]``) und ``--out`` (Artifact).
Rate-Limit → Abbruch (Exit 3), kein Teilbefund. Cleanup-PR löscht die Datei.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import trading_date  # noqa: E402
import truth_check as tc  # noqa: E402

TICKERS = ("BJDX", "AMCX", "ARCT")
BJDX_DATES = ("14.07.2026", "15.07.2026", "05.08.2026")
START = date(2026, 6, 15)
BLIND_FROM = date(2026, 10, 24)
PROBE_END_ET = date(2026, 12, 5)


def decimals(x) -> int | None:
    """Nachkommastellen nach Entfernen des Float-Rauschens (7 signifikante Stellen — Yahoo liefert float32-nahe Werte)."""
    v = tc._num(x)
    if v is None:
        return None
    s = f"{float(f'{v:.7g}'):.10f}".rstrip("0").rstrip(".")
    return len(s.split(".")[1]) if "." in s else 0


def fetch(t: str, end: date) -> dict:
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    tk = yf.Ticker(t)
    adj = tk.history(start=START.isoformat(), end=end.isoformat(), interval="1d",
                     auto_adjust=True, actions=True)
    raw = tk.history(start=START.isoformat(), end=end.isoformat(), interval="1d",
                     auto_adjust=False, actions=True)
    rows = []
    for ts, r in adj.iterrows():
        rr = raw.loc[ts] if ts in raw.index else {}
        rows.append({"d": ts.date(), "c": float(r["Close"]), "h": float(r["High"]),
                     "l": float(r["Low"]), "div": float(r.get("Dividends", 0.0)),
                     "split": float(r.get("Stock Splits", 0.0)),
                     "close_unadj_feld": float(rr["Close"]) if len(rr) else None,
                     "adj_close_feld": float(rr["Adj Close"]) if len(rr) and "Adj Close" in rr else None})
    acts = [{"datum": d.date().isoformat(), "split_faktor": float(v)}
            for d, v in tk.splits.items() if d.date() >= date(2026, 1, 1)]
    divs = [{"datum": d.date().isoformat(), "dividende": float(v)}
            for d, v in tk.dividends.items() if d.date() >= date(2026, 1, 1)]
    return {"rows": rows, "splits_2026": acts, "dividenden_2026": divs}


def bjdx_rows(root: pathlib.Path = ROOT) -> list:
    out = []
    for e in tc._read_jsonl(root / config.MATURED_EXPORT_FILE):
        if e.get("ticker") == "BJDX" and e.get("date") in BJDX_DATES:
            assert tc._dmy(e["date"]) < BLIND_FROM
            out.append(e)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BJDX-Aktionsbeleg (read-only)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    today = now.astimezone(trading_date._NY).date()
    if today > PROBE_END_ET:
        print("[bjdx_probe] no-op: Probe-Ende überschritten")
        return 0
    final_cut = trading_date.last_settled_close_date(now)
    res = {"run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "endgueltig_bis": final_cut.isoformat(),
           "ticker": {}}
    for t in TICKERS:
        try:
            f = fetch(t, today + timedelta(days=2))
        except Exception as exc:  # noqa: BLE001
            if tc.classify_fetch_error(exc) == "rate_limit":
                print("[bjdx_probe] ABBRUCH: Rate-Limit — kein Retry, kein Ergebnis.", flush=True)
                return 3
            res["ticker"][t] = {"fehler": f"{type(exc).__name__}: {str(exc)[:200]}"}
            continue
        rows = f["rows"]
        res["ticker"][t] = {
            "splits_2026": f["splits_2026"], "dividenden_2026": f["dividenden_2026"],
            "aktionen_in_reihe": [{"d": r["d"].isoformat(), "split": r["split"], "div": r["div"]}
                                  for r in rows if r["split"] or r["div"]],
            "kurse": [{"d": r["d"].isoformat(), "c": repr(r["c"]), "dez": decimals(r["c"]),
                       "close_feld": repr(r["close_unadj_feld"]), "adj_close_feld": repr(r["adj_close_feld"])}
                      for r in rows if r["d"] <= date(2026, 9, 15)],
        }
        if t == "BJDX":
            s = tc.Series(rows)
            vergleich = []
            for e in bjdx_rows():
                rec = tc.recompute_backtest(e, s, None, None, final_cut, today)
                n, devs, _ = tc.compare_row("export", e, rec, {t: s}, float(config.TRUTH_CHECK_TOLERANCE_PP))
                ei = s.cpos(tc._dmy(e["date"]))
                vergleich.append({"date": e["date"], "felder_verglichen": n, "abweichungen": devs,
                                  "entry_price_t1_gespeichert": e.get("entry_price_t1"),
                                  "close_t0_heute": repr(s.closes[ei][1]) if ei >= 0 else None,
                                  "close_t1_heute": repr(s.closes[ei + 1][1]) if 0 <= ei < len(s.closes) - 1 else None})
            res["ticker"][t]["vergleich_export"] = vergleich
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                   encoding="utf-8")
    print("[bjdx_probe] " + json.dumps(res, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
