#!/usr/bin/env python3
"""WEGWERF-PROBE: Rendite-Diagnose (02.11.2026) — Freeze-Auto-Lauf pausiert (#644).

Frage: Stammen return_3d/5d/10d aus dem LAUFENDEN Handelstag T+N?
(ki_agent._trading_days_elapsed zählt heute mit; update_backtest_returns
füllt, sobald der Bar T+N existiert, und überschreibt nie.)

BLINDUNG (verbindlich): Dieses Skript gibt KEINE Renditewerte aus und
gruppiert NICHT nach Score, Bucket, Regime oder Haltedauer-Vergleich. Es
zeigt nur (A) Füll-Zeitpunkte relativ zum US-Börsenschluss und (B) die
ABWEICHUNG |gespeichert − korrekt| in Prozentpunkten als Verteilung.
Es erzeugt KEINE Freeze-Auswertung und schreibt NICHTS (kein Datei-Write,
kein Commit).

  python scripts/probe_return_check.py            # Teil A (ohne Netz)
  python scripts/probe_return_check.py --online   # Teil A + B (yfinance)

Teil A braucht die volle Git-Historie von backtest_history.json
(im Workflow: actions/checkout mit fetch-depth: 0).
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ET = ZoneInfo("America/New_York")
WINDOWS = (3, 5, 10)
FIELDS = tuple(f"return_{w}d" for w in WINDOWS)
CLOSE_ET = time(16, 0)
GRACE_MIN = 20          # Füllung 16:00–16:20 ET gilt als „unklar“ (Bar evtl. noch nicht final)
BT_FILE = "backtest_history.json"
EXPORT_FILE = "matured_backtest_export.jsonl"


def _holidays() -> set[str]:
    try:
        import config
        return set(config.US_MARKET_HOLIDAYS)
    except Exception:
        return set()


HOL = _holidays()


def _is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in HOL


def _target_day(entry: date, n: int) -> date:
    """N-ter US-Handelstag NACH dem Entry-Tag (Wochenenden + Feiertage)."""
    d, k = entry, 0
    while k < n:
        d += timedelta(days=1)
        if _is_trading_day(d):
            k += 1
    return d


def _dmy(s) -> date | None:
    try:
        return datetime.strptime(str(s), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


# ── Datensätze ───────────────────────────────────────────────────────────────
def _load_records() -> dict[tuple, dict]:
    """Vereinigung aus Matured-Export und aktuellem backtest_history
    (Bootstrap-Zeilen ausgenommen). Schlüssel (ticker, date). Export hat
    Vorrang (dort steht ``provenance``); fehlt sie, gilt source!=bootstrap
    als ``forward``."""
    recs: dict[tuple, dict] = {}
    try:
        bt = json.loads((ROOT / BT_FILE).read_text(encoding="utf-8"))
    except Exception:
        bt = []
    for e in bt if isinstance(bt, list) else []:
        if not isinstance(e, dict) or e.get("source") == "bootstrap":
            continue
        r = dict(e)
        r.setdefault("provenance", "forward")
        r["_in_export"] = False
        recs[(e.get("ticker"), e.get("date"))] = r
    try:
        with open(ROOT / EXPORT_FILE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(o, dict):
                    continue
                k = (o.get("ticker"), o.get("date"))
                base = recs.get(k, {})
                merged = {**base, **o, "_in_export": True}
                recs[k] = merged
    except FileNotFoundError:
        pass
    return recs


def _populations(r: dict) -> list[str]:
    import health_check as hc
    out = []
    if hc._is_exit_b1_population_row(r):
        out.append("§4")
    if hc._is_freeze_population_row(r, hc._parse_dmy_date(hc._FREEZE_DATE_STR)):
        out.append("Setup-Edge")
    if hc._is_ki_score_population_row(r, hc._parse_dmy_date(hc._KI_SCORE_FREEZE_DATE_STR)):
        out.append("KI-Score")
    return out


# ── Teil A: Füll-Zeitpunkte aus der Git-Historie ─────────────────────────────
def _history() -> list[tuple[str, int]]:
    out = subprocess.run(
        ["git", "log", "--reverse", "--format=%H %at", "--", BT_FILE],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    return [(ln.split()[0], int(ln.split()[1])) for ln in out if ln.strip()]


def first_fill_times(keys: set[tuple]) -> tuple[dict, dict, dict, int, bool]:
    """Pro (ticker, date, feld): erste Commit-Zeit (Autor-Zeit, ≈ Laufzeit)
    mit gefülltem Wert; ob der Wert schon beim ersten Auftauchen des Records
    gefüllt war; ob er später je geändert wurde. Werte werden NICHT
    ausgegeben, nur zum Änderungs-Vergleich im Speicher gehalten."""
    first: dict = {}
    at_creation: dict = {}
    changed: dict = {}
    seen_rec: set = set()
    last_val: dict = {}
    hist = _history()
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip() == "true"
    for i, (sha, ts) in enumerate(hist):
        try:
            blob = subprocess.run(["git", "show", f"{sha}:{BT_FILE}"], cwd=ROOT,
                                  capture_output=True, text=True, check=True).stdout
            data = json.loads(blob)
        except Exception:
            continue
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict):
                continue
            k = (e.get("ticker"), e.get("date"))
            if k not in keys:
                continue
            new_rec = k not in seen_rec
            seen_rec.add(k)
            for f in FIELDS:
                v = _num(e.get(f))
                if v is None:
                    continue
                fk = (k, f)
                if fk not in first:
                    first[fk] = (ts, i)
                    at_creation[fk] = new_rec
                    last_val[fk] = v
                elif last_val[fk] != v:
                    changed[fk] = True
                    last_val[fk] = v
    return first, at_creation, changed, len(hist), shallow


def classify(entry: date, n: int, ts: int, first_commit_idx: int, at_creation: bool) -> str:
    if first_commit_idx == 0 and at_creation:
        return "unklar_vor_historie"
    if at_creation:
        return "bei_anlage_gefuellt"
    tgt = _target_day(entry, n)
    close_dt = datetime.combine(tgt, CLOSE_ET, tzinfo=ET)
    fill = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ET)
    if fill.date() < tgt:
        return "vor_zieltag"
    if fill < close_dt:
        return "intraday"
    if fill < close_dt + timedelta(minutes=GRACE_MIN):
        return "unklar_grenze"
    return "nach_schluss"


CLASSES = ("intraday", "nach_schluss", "unklar_grenze", "unklar_vor_historie",
           "bei_anlage_gefuellt", "vor_zieltag", "keine_fuellzeit")


def part_a(recs: dict) -> dict:
    keys = {k for k, r in recs.items() if any(_num(r.get(f)) is not None for f in FIELDS)}
    first, at_creation, changed, n_commits, shallow = first_fill_times(keys)
    cls: dict = {}
    for k in keys:
        r = recs[k]
        entry = _dmy(r.get("date"))
        for w, f in zip(WINDOWS, FIELDS):
            if _num(r.get(f)) is None or entry is None:
                continue
            fk = (k, f)
            if fk not in first:
                cls[fk] = "keine_fuellzeit"
                continue
            ts, idx = first[fk]
            cls[fk] = classify(entry, w, ts, idx, at_creation.get(fk, False))
    print(f"[A] Git-Historie {BT_FILE}: {n_commits} Commits, shallow={shallow}")
    print(f"[A] Records mit mind. einer Rendite: {len(keys)} · Felder: {len(cls)}")
    print(f"[A] Später geänderte Werte (Korrektur nach Erstfüllung): {len(changed)}")
    _print_counts("[A] alle Records", cls, None, recs)
    for pop in ("§4", "Setup-Edge", "KI-Score"):
        _print_counts(f"[A] Population {pop}", cls, pop, recs)
    return cls


def _print_counts(label: str, cls: dict, pop: str | None, recs: dict) -> None:
    sel = {fk: c for fk, c in cls.items() if pop is None or pop in _populations(recs[fk[0]])}
    tot = Counter(sel.values())
    print(f"{label}: {len(sel)} Felder · " + " · ".join(f"{c}={tot.get(c, 0)}" for c in CLASSES))
    for f in FIELDS:
        sub = Counter(c for fk, c in sel.items() if fk[1] == f)
        print(f"    {f}: " + " · ".join(f"{c}={sub.get(c, 0)}" for c in CLASSES if sub.get(c)))


# ── Teil B: Neuberechnung mit echten Schlusskursen (nur Abweichungen) ───────
def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def _dist(label: str, devs: list[float]) -> None:
    if not devs:
        print(f"{label}: n=0")
        return
    over = {t: sum(1 for d in devs if d > t) for t in (0.5, 1, 2, 5)}
    print(f"{label}: n={len(devs)} · median={_quantile(devs, .5):.3f} pp · "
          f"p90={_quantile(devs, .9):.3f} pp · "
          + (f"max={max(devs):.3f} pp · " if len(devs) >= 5 else "max=(n<5, ausgeblendet) · ")
          + " · ".join(f">{t} pp: {c}" for t, c in over.items()))


def part_b(recs: dict, cls: dict) -> None:
    import yfinance as yf
    todo = [(k, r) for k, r in recs.items()
            if any(_num(r.get(f)) is not None for f in FIELDS) and _dmy(r.get("date"))]
    tickers = sorted({k[0] for k, _ in todo if k[0]})
    start = min(_dmy(r["date"]) for _, r in todo) - timedelta(days=10)
    now_et = datetime.now(timezone.utc).astimezone(ET)
    print(f"[B] Download: {len(tickers)} Ticker ab {start} (ein Batch, auto_adjust=True)")
    hist = yf.download(tickers, start=start.isoformat(),
                       end=(now_et.date() + timedelta(days=1)).isoformat(),
                       auto_adjust=True, progress=False, threads=True, group_by="ticker")
    skip = Counter()
    devs: dict[str, list[float]] = {}
    # Nur Bars, die sicher final sind: Datum < heute (ET), oder heute nach 16:20 ET.
    final_cut = now_et.date() if now_et.time() < time(16, GRACE_MIN) else now_et.date() + timedelta(days=1)
    for (tk, ds), r in todo:
        try:
            df = hist if len(tickers) == 1 else hist[tk]
            closes = df["Close"].dropna()
        except Exception:
            skip["ticker_fehlt"] += 1
            continue
        idx = [ts.date() for ts in closes.index]
        entry = _dmy(ds)
        if entry not in idx:
            skip["entry_nicht_im_index"] += 1
            continue
        ei = idx.index(entry)
        base = float(closes.iloc[ei])
        for w, f in zip(WINDOWS, FIELDS):
            stored = _num(r.get(f))
            if stored is None:
                continue
            pos = ei + w
            if pos >= len(closes) or idx[pos] >= final_cut or base <= 0:
                skip["zielbar_fehlt_oder_nicht_final"] += 1
                continue
            correct = round((float(closes.iloc[pos]) / base - 1) * 100, 2)
            d = abs(stored - correct)
            c = cls.get(((tk, ds), f), "keine_fuellzeit")
            pops = _populations(r)
            for key in ("alle", f"klasse:{c}", *(f"pop:{p}" for p in pops),
                        *(f"pop:{p}|klasse:{c}" for p in pops)):
                devs.setdefault(key, []).append(d)
    print(f"[B] übersprungen: {dict(skip)}")
    for key in sorted(devs, key=lambda s: (s != "alle", s)):
        _dist(f"[B] |gespeichert − korrekt| {key}", devs[key])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Wegwerf-Probe Rendite-Diagnose (blind)")
    ap.add_argument("--online", action="store_true", help="Teil B mit yfinance")
    args = ap.parse_args(argv)
    recs = _load_records()
    cls = part_a(recs)
    if args.online:
        part_b(recs, cls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
