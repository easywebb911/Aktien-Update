#!/usr/bin/env python3
"""WEGWERF-PROBE (read-only): 1-Minuten-Kurse aus yfinance für die Top-10
(open_item ``handelskosten-messung``, Weg A, Easy-Auftrag 13.11.2026).

Fragen:
  1  Liefert yfinance 1-Minuten-Balken (OHLCV) für die Top-10 des letzten
     US-Handelstags D vollständig (reguläre Handelszeit 09:30–15:59 ET = 390
     Minuten)? Wie viele Minuten fehlen (kein Handel)? Nasdaq vs. NYSE?
  2  Stimmen Hoch/Tief/Schluss aus den Minuten mit der Tageszeile überein?
  3  Gibt es vor-/nachbörsliche Balken (prepost=True)?
  4  Wie viele Tage zurück sind 1-Minuten-Balken abrufbar (SPY + 2 Ticker,
     Fenster je 7 Kalendertage rückwärts bis 42 Tage)?

Read-only. Schreibt NUR stdout (Zeilen ``[minute_probe_meta]`` /
``[minute_probe]`` / ``[minute_probe_depth]``) und ``--out`` (Artifact).
Rate-Limit → Abbruch (Exit 3), keine Ergebnisdatei, kein Teilbefund.
Ab ``PROBE_END_ET`` no-op. Wird nach der Auswertung per Cleanup-PR gelöscht.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ET = ZoneInfo("America/New_York")
EXTRA = ("SPY", "SDHC", "CURV")
DEPTH_TICKERS = ("SPY",)          # + zwei Top-10-Ticker (erster Nasdaq, erster NYSE)
DEPTH_MAX_DAYS = 42
PROBE_END_ET = date(2026, 12, 5)
OPEN, CLOSE = time(9, 30), time(16, 0)
REG_MINUTES = 390


class RateLimited(Exception):
    pass


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in config.US_MARKET_HOLIDAYS


def last_trading_day_before(d: date) -> date:
    x = d - timedelta(days=1)
    while not is_trading_day(x):
        x -= timedelta(days=1)
    return x


def top10_of(bh: list, D: date) -> tuple[list, str]:
    rows = [e for e in bh if isinstance(e, dict) and e.get("source") != "bootstrap"]
    ds = D.strftime("%d.%m.%Y")
    top = sorted({e["ticker"] for e in rows if e.get("date") == ds and e.get("ticker")})
    return top, (D.isoformat() if top else "keine")


def num(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def summarize_bars(bars: list, D: date) -> dict:
    """Pure. ``bars``: [{t: datetime(ET), o, h, l, c, v}]. Zählt reguläre,
    vor-/nachbörsliche Balken, fehlende Minuten, leere Felder."""
    reg = [b for b in bars if b["t"].date() == D and OPEN <= b["t"].time() < CLOSE]
    pre = [b for b in bars if b["t"].date() == D and b["t"].time() < OPEN]
    post = [b for b in bars if b["t"].date() == D and b["t"].time() >= CLOSE]
    complete = [b for b in reg if all(num(b[k]) is not None for k in ("o", "h", "l", "c"))]
    vol_none = sum(1 for b in reg if num(b["v"]) is None)
    vol_zero = sum(1 for b in reg if num(b["v"]) == 0)
    minutes = {(b["t"].hour, b["t"].minute) for b in reg}
    out = {"reg_bars": len(reg), "reg_complete": len(complete),
           "missing_minutes": REG_MINUTES - len(minutes), "vol_none": vol_none, "vol_zero": vol_zero,
           "pre_bars": len(pre), "post_bars": len(post),
           "first": min((b["t"] for b in reg), default=None),
           "last": max((b["t"] for b in reg), default=None)}
    if complete:
        out["m_high"] = max(num(b["h"]) for b in complete)
        out["m_low"] = min(num(b["l"]) for b in complete)
        out["m_close"] = num(sorted(complete, key=lambda b: b["t"])[-1]["c"])
        out["m_open"] = num(sorted(complete, key=lambda b: b["t"])[0]["o"])
        out["m_vol"] = sum(num(b["v"]) or 0 for b in reg)
    return out


def compare_daily(s: dict, day: dict | None) -> dict:
    """Pure. Abweichung Minuten vs. Tageszeile in % (|m/d − 1|·100)."""
    if not day or "m_high" not in s:
        return {}
    def pct(a, b):
        a, b = num(a), num(b)
        return None if a is None or b is None or b == 0 else round(abs(a / b - 1) * 100, 4)
    return {"d_high": pct(s["m_high"], day.get("h")), "d_low": pct(s["m_low"], day.get("l")),
            "d_close": pct(s["m_close"], day.get("c")), "d_open": pct(s["m_open"], day.get("o")),
            "vol_ratio": (round(s["m_vol"] / day["v"], 4) if num(day.get("v")) else None)}


def _rate(exc: BaseException) -> bool:
    n = type(exc).__name__
    return "RateLimit" in n or "Too Many Requests" in str(exc)


def fetch_minutes(t: str, start: date, end: date, prepost: bool):
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    tk = yf.Ticker(t)
    df = tk.history(start=start.isoformat(), end=end.isoformat(), interval="1m",
                    prepost=prepost, auto_adjust=False, actions=False)
    meta = getattr(tk, "history_metadata", {}) or {}
    bars = []
    if df is not None and not df.empty:
        for ts, r in df.iterrows():
            bars.append({"t": ts.tz_convert(ET).to_pydatetime() if ts.tzinfo else ts.to_pydatetime(),
                         "o": r.get("Open"), "h": r.get("High"), "l": r.get("Low"),
                         "c": r.get("Close"), "v": r.get("Volume")})
    return bars, meta.get("exchangeName")


def fetch_daily(t: str, D: date):
    import yfinance as yf
    df = yf.Ticker(t).history(start=(D - timedelta(days=5)).isoformat(),
                              end=(D + timedelta(days=1)).isoformat(),
                              interval="1d", auto_adjust=False, actions=False)
    for ts, r in (df.iterrows() if df is not None else []):
        if ts.date() == D:
            return {"o": r.get("Open"), "h": r.get("High"), "l": r.get("Low"),
                    "c": r.get("Close"), "v": r.get("Volume")}
    return None


def depth(t: str, today: date) -> dict:
    """Ältester abrufbarer Tag mit 1-Min-Balken: Fenster je 7 Kalendertage rückwärts."""
    oldest, fehler = None, []
    for back in range(7, DEPTH_MAX_DAYS + 1, 7):
        s, e = today - timedelta(days=back), today - timedelta(days=back - 7)
        try:
            bars, _ = fetch_minutes(t, s, e, False)
        except Exception as exc:  # noqa: BLE001
            if _rate(exc):
                raise RateLimited(str(exc)) from exc
            fehler.append({"fenster": [s.isoformat(), e.isoformat()], "fehler": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        days = sorted({b["t"].date() for b in bars})
        if days:
            oldest = days[0] if oldest is None else min(oldest, days[0])
        else:
            fehler.append({"fenster": [s.isoformat(), e.isoformat()], "fehler": "leer"})
    return {"ticker": t, "aeltester_tag": oldest.isoformat() if oldest else None,
            "handelstage_zurueck": (sum(1 for k in range((today - oldest).days)
                                        if is_trading_day(oldest + timedelta(days=k)))
                                    if oldest else None),
            "fenster_ohne_daten": fehler}


def run(now_utc: datetime) -> dict:
    today = now_utc.astimezone(ET).date()
    D = last_trading_day_before(today)
    try:
        with open(ROOT / config.BACKTEST_FILE, encoding="utf-8") as fh:
            bh = json.load(fh)
    except (OSError, ValueError):
        bh = []
    top, src = top10_of(bh if isinstance(bh, list) else [], D)
    tickers = top + [t for t in EXTRA if t not in top]
    recs = []
    for t in tickers:
        try:
            bars, exch = fetch_minutes(t, D, D + timedelta(days=1), True)
            day = fetch_daily(t, D)
        except Exception as exc:  # noqa: BLE001
            if _rate(exc):
                raise RateLimited(str(exc)) from exc
            recs.append({"ticker": t, "fehler": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        s = summarize_bars(bars, D)
        recs.append({"ticker": t, "top10": t in top, "boerse": exch, **s, **compare_daily(s, day),
                     "tageszeile": day is not None})
    nasdaq = next((r["ticker"] for r in recs if r.get("top10") and r.get("boerse") in ("NMS", "NGM", "NCM")), None)
    nyse = next((r["ticker"] for r in recs if r.get("top10") and r.get("boerse") in ("NYQ", "NYSE")), None)
    dep = [depth(t, today) for t in DEPTH_TICKERS + tuple(x for x in (nasdaq, nyse) if x)]
    meta = {"run_utc": now_utc.isoformat(timespec="seconds"),
            "run_et": now_utc.astimezone(ET).isoformat(timespec="seconds"),
            "D": D.isoformat(), "top10_quelle": src, "tickers": tickers}
    return {"meta": meta, "records": recs, "depth": dep}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Wegwerf-Probe 1-Minuten-Kurse (read-only)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if now.astimezone(ET).date() > PROBE_END_ET:
        print("[minute_probe_meta] no-op: Probe-Ende überschritten")
        return 0
    try:
        res = run(now)
    except RateLimited as exc:
        print(f"[minute_probe_meta] ABBRUCH: Rate-Limit — kein Retry, kein Ergebnis ({str(exc)[:120]})", flush=True)
        return 3
    print("[minute_probe_meta] " + json.dumps(res["meta"], ensure_ascii=False, default=str), flush=True)
    for r in res["records"]:
        print("[minute_probe] " + json.dumps(r, ensure_ascii=False, default=str), flush=True)
    for d in res["depth"]:
        print("[minute_probe_depth] " + json.dumps(d, ensure_ascii=False, default=str), flush=True)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
