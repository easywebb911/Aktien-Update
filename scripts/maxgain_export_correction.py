"""Einmal-Korrektur abgeschnittener Rolling-Fenster im Export (Easy-Entscheid
12.11.2026, Variante A; open_item max-gain-rolling-fenster-abgeschnitten).

Bis #676 endete das Rolling-Update von ``max_gain_pct``/``max_drawdown_pct``
nach 14 Kalendertagen (UTC-Datum); der append-only-Export
``matured_backtest_export.jsonl`` hat abgeschnittene Fenster (vor Tag 10)
eingefroren. Dieses Skript ist die **einmalige, dokumentierte Ausnahme** von
der append-only-Garantie (CLAUDE.md, SESSION_HANDOVER-Protokolleinträge):

1. **Kandidaten** = Export-Zeilen, deren gespeicherter Wert laut Wächter S17
   abgeschnitten ist (``health_check._s17_is_truncated`` gegen die OHLC Tag 0–10
   aus ``outcome_path.jsonl``). Nur das jeweils abgeschnittene Feld ist
   Kandidat. Zeilen ohne ``outcome_path``-Zeile → keine Gegenprobe → nicht
   angefasst.
2. **Neuberechnung** aus derselben Kursquelle wie die Produktion (yfinance,
   ``auto_adjust=True``, ein Abruf je Ticker), Formel wie
   ``backtest_history._compute_max_gain_pct``/``_compute_max_drawdown``
   (laufendes Tief/Hoch ab D, gerundet auf 2 Stellen), Fenster D..Tag 10 aus
   dem Handelskalender. Nur wenn alle 11 Zeilen vollständig sind.
3. **Gegenprobe:** der neue Wert muss innerhalb ``TRUTH_CHECK_TOLERANCE_PP``
   (0,02 pp, Toleranz wie S16) zum vollen Fenster aus ``outcome_path.jsonl``
   passen — sonst wird die Zeile NICHT geschrieben, nur gezählt.
4. **Schreiben:** ersetzt werden nur die abgeschnittenen Felder, dazu
   ``max_gain_pct_net`` (abgeleitet, ``apply_round_trip_haircut``) wenn
   ``max_gain_pct`` ersetzt wird und das Feld existiert, und
   ``rolling_window_n`` = 11, wenn das Feld existiert. Alle anderen Zeilen
   bleiben byte-gleich (Prüfung per Zeilen-Hash), alle anderen Felder der
   korrigierten Zeilen unverändert. Format wie ``matured_export``
   (``json.dumps(sort_keys=True, ensure_ascii=False)``). Atomar.

BLINDHEIT: Für Einstiege ≥ 24.10.2026 (Replikationsfenster) werden nur Zahlen
ausgegeben — keine Werte, keine Treffer-Zählung. Für das erste Paper-C-Fenster
(21.07.–23.10.2026) zusätzlich die Zahl der Treffer-Wechsel (``max_gain_pct``
über/unter 30) — KEINE Neuauswertung.

Ablauf im Workflow ``maxgain_export_correction.yml`` (nur Hand-Start):
``--compute <datei>`` holt Kurse und schreibt die Korrekturen (Werte) in eine
Datei im Runner-Temp (nicht committet, nicht geloggt); ``--apply <datei>``
wendet sie auf den aktuellen Export an (idempotent: ein zweiter Lauf findet
keine Kandidaten mehr).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config  # noqa: E402
import health_check as hc  # noqa: E402
import trading_date  # noqa: E402

EXPORT_FILE = config.MATURED_EXPORT_FILE
OUTCOME_FILE = config.OUTCOME_PATH_FILE
TOL = float(config.TRUTH_CHECK_TOLERANCE_PP)
N_DAYS = int(config.ROLLING_WINDOW_TRADING_DAYS)
REPLICATION_FROM = config.OUTCOME_PATH_REPLICATION_FROM          # 24.10.2026
PAPER_C_FROM, PAPER_C_TO = date(2026, 7, 21), date(2026, 10, 23)
HIT = 30.0


def _parse(ds) -> date | None:
    try:
        return datetime.strptime(str(ds), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def window_metrics(bars: list) -> tuple[float, float] | None:
    """(max_gain, max_drawdown) in %, gerundet auf 2 Stellen — dieselbe Formel
    wie backtest_history._compute_max_gain_pct/_compute_max_drawdown
    (laufendes Tief bzw. Hoch inkl. der aktuellen Zeile)."""
    if len(bars) < 2:
        return None
    lo = hi = None
    mg = dd = None
    for b in bars:
        h, l = float(b["h"]), float(b["l"])
        lo = l if lo is None else min(lo, l)
        hi = h if hi is None else max(hi, h)
        g = (h - lo) / lo * 100.0
        d = (l - hi) / hi * 100.0
        mg = g if mg is None else max(mg, g)
        dd = d if dd is None else min(dd, d)
    return round(mg, 2), round(dd, 2)


def _load_outcome(path=None) -> dict:
    path = path or OUTCOME_FILE
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                bars = r.get("bars") if isinstance(r, dict) else None
                if (isinstance(bars, list) and len(bars) >= N_DAYS + 1
                        and all(isinstance(b, dict) and _finite(b.get("h")) and _finite(b.get("l"))
                                and float(b["l"]) > 0 for b in bars[:N_DAYS + 1])):
                    out[(r.get("ticker"), r.get("date"))] = bars[:N_DAYS + 1]
    except OSError:
        pass
    return out


def _read_lines(path=None) -> list[str]:
    path = path or EXPORT_FILE
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    # Nur an "\n" trennen (wie matured_export), nicht an \x85/\u2028 o. ä.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def find_candidates(lines: list[str], outcome: dict) -> list[dict]:
    """Je Export-Zeile mit abgeschnittenem Feld: {idx, key, felder, voll}.
    Erste Zeile je (ticker, date) gewinnt (wie überall im Export)."""
    seen, out = set(), []
    for i, ln in enumerate(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict):
            continue
        key = (r.get("ticker"), r.get("date"))
        if key in seen:
            continue
        seen.add(key)
        bars = outcome.get(key)
        if bars is None:
            continue
        full = hc._s17_prefix_metrics(bars, N_DAYS)
        pref = [hc._s17_prefix_metrics(bars, k) for k in range(1, N_DAYS)]
        felder = []
        if hc._s17_is_truncated(r.get("max_gain_pct"), full[0], [p[0] for p in pref if p], +1):
            felder.append("max_gain_pct")
        if hc._s17_is_truncated(r.get("max_drawdown_pct"), full[1], [p[1] for p in pref if p], -1):
            felder.append("max_drawdown_pct")
        if felder:
            out.append({"idx": i, "key": key, "felder": felder,
                        "voll": (round(full[0], 2), round(full[1], 2))})
    return out


def compute_corrections(cands: list[dict], fetch_rows, final_cut: date) -> tuple[list[dict], dict]:
    """Holt Kurse (``fetch_rows(ticker, start, end_excl) → list[{d,h,l,c}]``),
    rechnet das volle Fenster neu und prüft gegen outcome_path. Returnt
    (Korrekturen, Zählungen je Grund). Rate-Limit-/Fehlerbehandlung macht
    ``fetch_rows`` bzw. der Aufrufer (outcome_path_update.fetch_all)."""
    reasons = {"abruf_fehler": 0, "unvollstaendig": 0, "gegenprobe_abweichung": 0,
               "noch_nicht_final": 0}
    corr = []
    for c in cands:
        t, ds = c["key"]
        edate = _parse(ds)
        rows = fetch_rows(t)
        if rows is None:
            reasons["abruf_fehler"] += 1
            continue
        end = trading_date.nth_trading_day_after(edate, N_DAYS, config.US_MARKET_HOLIDAYS)
        if not final_cut > end:
            reasons["noch_nicht_final"] += 1
            continue
        win = [r for r in rows if edate <= r["d"] <= end]
        win.sort(key=lambda r: r["d"])
        exp_days = [edate] + [trading_date.nth_trading_day_after(edate, k, config.US_MARKET_HOLIDAYS)
                              for k in range(1, N_DAYS + 1)]
        if ([r["d"] for r in win] != exp_days
                or not all(_finite(r.get("h")) and _finite(r.get("l")) and _finite(r.get("c"))
                           and float(r["l"]) > 0 for r in win)):
            reasons["unvollstaendig"] += 1
            continue
        mg, dd = window_metrics(win)
        new = {}
        if "max_gain_pct" in c["felder"]:
            new["max_gain_pct"] = mg
        if "max_drawdown_pct" in c["felder"]:
            new["max_drawdown_pct"] = dd
        ok = all(abs(new[f] - c["voll"][0 if f == "max_gain_pct" else 1]) <= TOL + 1e-9 for f in new)
        if not ok:
            reasons["gegenprobe_abweichung"] += 1
            continue
        corr.append({"ticker": t, "date": ds, "neu": new})
    return corr, reasons


def apply_corrections(lines: list[str], corr: list[dict]) -> tuple[list[str], dict]:
    """Wendet Korrekturen an. Returnt (neue Zeilen, Zählungen). Unveränderte
    Zeilen bleiben identische Strings; geprüft per Zeilen-Hash."""
    from backtest_history import apply_round_trip_haircut  # lazy (yfinance-Import)
    by_key = {(c["ticker"], c["date"]): c["neu"] for c in corr}
    out, done = [], set()
    stats = {"korrigiert_vor_replikation": 0, "korrigiert_replikation": 0,
             "treffer_wechsel_paper_c": 0, "felder_max_gain": 0, "felder_max_drawdown": 0,
             "zeilen_unveraendert": 0}
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            r = None
        key = (r.get("ticker"), r.get("date")) if isinstance(r, dict) else None
        neu = by_key.get(key) if key else None
        if not neu or key in done:
            out.append(ln)
            stats["zeilen_unveraendert"] += 1
            continue
        done.add(key)
        d = _parse(key[1])
        old_mg = r.get("max_gain_pct")
        for f, v in neu.items():
            r[f] = v
            stats["felder_max_gain" if f == "max_gain_pct" else "felder_max_drawdown"] += 1
        if "max_gain_pct" in neu and "max_gain_pct_net" in r:
            r["max_gain_pct_net"] = apply_round_trip_haircut(neu["max_gain_pct"])
        if "rolling_window_n" in r:
            r["rolling_window_n"] = N_DAYS + 1
        out.append(json.dumps(r, sort_keys=True, ensure_ascii=False))
        if d is not None and d >= REPLICATION_FROM:
            stats["korrigiert_replikation"] += 1          # BLIND: nur zählen
        else:
            stats["korrigiert_vor_replikation"] += 1
            if (d is not None and PAPER_C_FROM <= d <= PAPER_C_TO and "max_gain_pct" in neu
                    and _finite(old_mg) and (old_mg >= HIT) != (neu["max_gain_pct"] >= HIT)):
                stats["treffer_wechsel_paper_c"] += 1
    # Byte-Gleichheit der unveränderten Zeilen (Zeilen-Hash).
    h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
    changed_keys = done
    same = 0
    for a, b in zip(lines, out):
        try:
            k = (lambda r: (r.get("ticker"), r.get("date")))(json.loads(a))
        except Exception:  # noqa: BLE001
            k = None
        if k not in changed_keys:
            assert h(a) == h(b), "unveränderte Zeile weicht ab"
            same += 1
    assert len(lines) == len(out), "Zeilenzahl geändert"
    stats["hash_gleich"] = same
    return out, stats


def _write_atomic(lines: list[str], path=None) -> None:
    path = path or EXPORT_FILE
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def _counts(cands: list[dict]) -> dict:
    rep = sum(1 for c in cands if (_parse(c["key"][1]) or date.min) >= REPLICATION_FROM)
    return {"kandidaten_vor_replikation": len(cands) - rep, "kandidaten_replikation": rep}


def compute(out_path: str, *, now_utc: datetime | None = None) -> int:
    import outcome_path_update as op  # Abruf-Helfer (auto_adjust=True, Rate-Limit → kein Retry)
    now = now_utc or datetime.now(timezone.utc)
    final_cut = trading_date.last_final_close_date(now)
    lines = _read_lines()
    cands = find_candidates(lines, _load_outcome())
    by_ticker: dict = {}
    for c in cands:
        by_ticker.setdefault(c["key"][0], []).append(_parse(c["key"][1]))
    data, errors = op.fetch_all(by_ticker, op.yahoo_fetch)
    rows_for = lambda t: (None if t in errors else data.get(t) or None)
    corr, reasons = compute_corrections(cands, rows_for, final_cut)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(corr, fh)
    err_count: dict = {}
    for r in errors.values():
        err_count[r] = err_count.get(r, 0) + 1
    print("[maxgain_correction] compute " + json.dumps(
        {**_counts(cands), "korrekturen": len(corr), "nicht_geschrieben": reasons,
         "abruf_fehler_nach_grund": err_count, "rate_limit_abbruch": "rate_limit" in err_count},
        ensure_ascii=False, sort_keys=True), flush=True)
    # Rate-Limit → Lauf als fehlgeschlagen markieren, damit nichts halb
    # angewendet wird (Workflow bricht vor dem Apply ab; neuer Hand-Start später).
    return 3 if "rate_limit" in err_count else 0


def apply(corr_path: str, *, dry_run: bool = False) -> int:
    with open(corr_path, "r", encoding="utf-8") as fh:
        corr = json.load(fh)
    lines = _read_lines()
    outcome = _load_outcome()
    before = hc.s17_rolling_window_counts(EXPORT_FILE, OUTCOME_FILE)
    # Nur Korrekturen für Zeilen, die JETZT noch abgeschnitten sind (Idempotenz).
    still = {c["key"] for c in find_candidates(lines, outcome)}
    corr = [c for c in corr if (c["ticker"], c["date"]) in still]
    new_lines, stats = apply_corrections(lines, corr)
    if not dry_run and corr:
        _write_atomic(new_lines)
    after = hc.s17_rolling_window_counts(EXPORT_FILE, OUTCOME_FILE) if not dry_run else None
    print("[maxgain_correction] apply " + json.dumps(
        {**stats, "dry_run": dry_run, "s17_vorher": before, "s17_nachher": after},
        ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--compute", metavar="DATEI")
    g.add_argument("--apply", metavar="DATEI")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.compute:
        return compute(a.compute)
    return apply(a.apply, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
