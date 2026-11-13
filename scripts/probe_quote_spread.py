#!/usr/bin/env python3
"""WEGWERF-PROBE: Geld/Brief der Top-10 kurz nach der Eröffnung (open_item
``handelskosten-messung``).

Frage: Was liefert yfinance (``Ticker.info``) während der US-Sitzung für die
Top-10-Ticker wirklich — Geld (``bid``), Brief (``ask``), Größen, letzter Kurs,
Tagesvolumen, Zeitstempel und die Verzögerungsangabe der Börse
(``exchangeDataDelayedBy``)? Sind die Werte bei Small Caps belastbar (vorhanden,
Brief > Geld, letzter Kurs zwischen Geld und Brief, Zeitstempel frisch)?

Read-only. Schreibt NICHTS ins Repo — nur stdout (Job-Log, Zeilen
``[quote_probe_meta]`` / ``[quote_probe]``) und eine JSON-Datei unter
``$RUNNER_TEMP/quote_probe/`` (Artifact). Kein Produktionscode, keine Daten-
Datei wird verändert. Wird nach der Auswertung per Cleanup-PR gelöscht
(zusammen mit ``.github/workflows/probe_quote_spread.yml`` und
``scripts/mock_test_probe_quote_spread.py``). Ab ``PROBE_END_ET`` no-op.

Ticker: Top-10 des Postclose-Berichts von D (D = letzter US-Handelstag strikt
vor dem ET-Tag der Messung; fehlt D, der jüngste Tag davor) aus
``backtest_history.json`` (ohne Bootstrap) + SPY + drei bewusst illiquide Titel.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ET = ZoneInfo("America/New_York")
EXTRA = ("SPY", "SDHC", "CURV", "TTEC")   # Referenz + illiquide (wie Nacht-Probe)
OPEN_ET = (9, 30)
PROBE_END_ET = date(2026, 12, 5)          # danach no-op (Sicherheitsnetz bis Cleanup)
INFO_KEYS = ("bid", "ask", "bidSize", "askSize", "regularMarketPrice", "regularMarketTime",
             "regularMarketOpen", "regularMarketVolume", "regularMarketDayHigh",
             "regularMarketDayLow", "marketState", "exchangeDataDelayedBy", "exchange",
             "fullExchangeName", "quoteSourceName", "currency", "preMarketPrice", "postMarketPrice")


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in config.US_MARKET_HOLIDAYS


def last_trading_day_before(d: date) -> date:
    x = d - timedelta(days=1)
    for _ in range(15):
        if is_trading_day(x):
            return x
        x -= timedelta(days=1)
    return x


def ticker_set(bh: list, D: date) -> tuple[list, str]:
    rows = [e for e in bh if isinstance(e, dict) and e.get("source") != "bootstrap"]
    dates = set()
    for e in rows:
        try:
            dates.add(datetime.strptime(str(e.get("date")), "%d.%m.%Y").date())
        except ValueError:
            continue
    src = D if D in dates else max((x for x in dates if x < D), default=None)
    top = sorted({e["ticker"] for e in rows if src and e.get("date") == src.strftime("%d.%m.%Y")})
    return top + [t for t in EXTRA if t not in top], (src.isoformat() if src else "keine")


def num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def assess(info: dict, now_utc: datetime) -> dict:
    """Pure: Kennzahlen + Gründe aus einem .info-Ausschnitt. Unbekannt ≠ 0."""
    bid, ask, last = num(info.get("bid")), num(info.get("ask")), num(info.get("regularMarketPrice"))
    out = {"spread_pct": None, "mid": None, "last_in_quote": None, "quote_age_s": None, "grund": None}
    if bid is None or ask is None:
        out["grund"] = "geld_oder_brief_fehlt"
    elif bid <= 0 or ask <= 0:
        out["grund"] = "geld_oder_brief_null"
    elif ask <= bid:
        out["grund"] = "brief_nicht_ueber_geld"
    else:
        mid = (bid + ask) / 2
        out["mid"] = mid
        out["spread_pct"] = (ask - bid) / mid * 100
        if last is not None:
            out["last_in_quote"] = bid <= last <= ask
    ts = num(info.get("regularMarketTime"))
    if ts is not None:
        out["quote_age_s"] = round(now_utc.timestamp() - ts, 1)
    return out


def fetch_info(t: str) -> dict:
    import yfinance as yf  # lazy: Tests ohne yfinance
    return yf.Ticker(t).info or {}


def measure(now_utc: datetime, *, fetch=fetch_info, bh=None) -> dict:
    now_et = now_utc.astimezone(ET)
    D = last_trading_day_before(now_et.date())
    if bh is None:
        try:
            bh = json.load(open(ROOT / config.BACKTEST_FILE, encoding="utf-8"))
        except (OSError, ValueError):
            bh = []
    tickers, src = ticker_set(bh if isinstance(bh, list) else [], D)
    open_dt = now_et.replace(hour=OPEN_ET[0], minute=OPEN_ET[1], second=0, microsecond=0)
    meta = {"run_utc": now_utc.isoformat(timespec="seconds"), "run_et": now_et.isoformat(timespec="seconds"),
            "handelstag_et": is_trading_day(now_et.date()),
            "min_nach_eroeffnung": round((now_et - open_dt).total_seconds() / 60, 1),
            # Nur Messungen in der regulären US-Sitzung (Handelstag, 09:30 ≤ ET < 16:00)
            # zählen als Befund; alles andere wird geloggt, aber nicht gewertet.
            "in_handelszeit": bool(is_trading_day(now_et.date())
                                   and (9, 30) <= (now_et.hour, now_et.minute) < (16, 0)),
            "D": D.isoformat(), "top10_quelle": src, "tickers": tickers,
            "github_run_id": os.environ.get("GITHUB_RUN_ID")}
    recs = []
    for t in tickers:
        try:
            info = fetch(t)
            sub = {k: info.get(k) for k in INFO_KEYS}
            err = None
        except Exception as exc:  # noqa: BLE001 — Probe, fail-soft je Ticker
            sub, err = {}, f"{type(exc).__name__}: {str(exc)[:160]}"
        recs.append({"ticker": t, "info": sub, "fehler": err, **assess(sub, now_utc)})
    return {"meta": meta, "records": recs}


def summary(m: dict) -> dict:
    r = m["records"]
    ok = [x for x in r if x["spread_pct"] is not None]
    sp = sorted(x["spread_pct"] for x in ok)
    return {"n": len(r), "mit_spanne": len(ok),
            "gruende": {g: sum(1 for x in r if x["grund"] == g) for g in {x["grund"] for x in r if x["grund"]}},
            "fehler": sum(1 for x in r if x["fehler"]),
            "letzter_im_quote": sum(1 for x in ok if x["last_in_quote"]),
            "spanne_median_pct": (sp[len(sp) // 2] if sp else None),
            "delay_werte": sorted({str(x["info"].get("exchangeDataDelayedBy")) for x in r})}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Wegwerf-Probe Geld/Brief (read-only)")
    ap.add_argument("--out", default=os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "quote_probe"))
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if now.astimezone(ET).date() > PROBE_END_ET:
        print("[quote_probe_meta] no-op: Probe-Ende überschritten")
        return 0
    m = measure(now)
    m["summary"] = summary(m)
    print("[quote_probe_meta] " + json.dumps({**m["meta"], "summary": m["summary"]}, ensure_ascii=False), flush=True)
    for r in m["records"]:
        print("[quote_probe] " + json.dumps(r, ensure_ascii=False, default=str), flush=True)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"quote_probe_{m['meta']['run_utc'].replace(':', '')}.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
