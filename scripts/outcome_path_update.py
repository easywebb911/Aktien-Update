"""Kursverlauf ab Einstieg (outcome_path.jsonl) — Sammler + Backfill.

Easy-Auftrag 12.11.2026 (nach dem Gipfel-Bericht 11.11.2026): je Forward-
Einstieg (``date`` = ET-Handelstag D, Einstieg = Schlusskurs D) die täglichen
OHLC von Tag 0 (= D) bis Tag 10 speichern — nur finale Tageszeilen, gleiche
Regel wie ``backtest_history._final_window`` — und daraus ableiten:

* ``max_gain_from_entry_pct``     = max(High Tag 1–10) / Close D − 1 (× 100).
  Tag D zählt NICHT. Ein Gap über das Ziel steckt im Hoch des Gap-Tags.
* ``max_gain_from_entry_pct_net`` = derselbe Wert nach Round-Trip-Haircut
  (``backtest_history.apply_round_trip_haircut``) — nachrangig, nur Einordnung.
* ``max_drawdown_from_entry_pct`` = min(Low Tag 1–10) / Close D − 1 (× 100).

Zielfeld der Vorabregistrierung „Paper C handelbar“ (SESSION_HANDOVER.md,
eingefroren 12.11.2026). Easy-Entscheide (Mini-Stopp 12.11.2026):

1. **Kurse angepasst, ein Abruf:** ``auto_adjust=True`` wie die Produktion; alle
   Tage einer Zeile stammen aus EINEM Abruf (``Ticker.history`` je Ticker),
   alle Kennzahlen werden innerhalb dieses Abrufs gerechnet. Split/Dividende im
   Fenster werden nur gekennzeichnet (wie S16). Eine Zeile wird EINMAL
   geschrieben, wenn Tag 10 final ist — danach nie neu.
2. **Unbekannt ≠ 0:** fehlt ein Handelstag (US-Kalender) oder hat er kein
   endliches OHLC (Halbzeile), bleiben die Kennzahlen ``null`` mit Grund.
   Vorher wird bis ``RETRY_DAYS`` Kalendertage nach Tag 10 erneut abgerufen.

**BLINDHEIT (hart):** Das Skript SCHREIBT Werte, es wertet sie nie aus. Logs
und State enthalten nur Zählungen (geschrieben / nicht reif / Grund / Abruf-
Fehler), keine Kennzahl, keine Verteilung. Zeilen mit Einstieg ≥ 24.10.2026
werden nur geschrieben, wenn der Freeze-Block „Paper C handelbar“ im Handover
steht (Reihenfolge-Sicherung: Freeze vor Befüllung).

Schreibt AUSSCHLIESSLICH ``outcome_path.jsonl`` (append-only, kein Prune,
atomar) und ``outcome_path_state.json`` (Heartbeat für den Digest). Liest
``backtest_history.json`` und ``matured_backtest_export.jsonl`` nur.

Aufruf (Workflow ``outcome_path.yml``)::

    python scripts/outcome_path_update.py --run
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import trading_date  # noqa: E402

SCHEMA_V = 1
OUT_FILE = ROOT / config.OUTCOME_PATH_FILE
STATE_FILE = ROOT / config.OUTCOME_PATH_STATE_FILE
BACKTEST_FILE = ROOT / "backtest_history.json"
EXPORT_FILE = ROOT / "matured_backtest_export.jsonl"
HANDOVER_FILE = ROOT / "SESSION_HANDOVER.md"

WINDOW_DAYS = config.OUTCOME_PATH_WINDOW_DAYS            # Tag 1..10 nach D
START_DATE = config.OUTCOME_PATH_START_DATE              # erster Forward-Einstieg
RETRY_DAYS = config.OUTCOME_PATH_RETRY_DAYS              # Kalendertage nach Tag 10
REPLICATION_FROM = config.OUTCOME_PATH_REPLICATION_FROM  # Fenster Replikation/handelbar
FREEZE_HEADING = config.OUTCOME_PATH_FREEZE_HEADING
MAX_WORKERS = 2
SOURCE_LABEL = "yfinance auto_adjust=True, ein Abruf je Ticker"

GRUND_FEHLENDER_TAG = "fehlender_tag"
GRUND_HALBZEILE = "halbzeile"
GRUND_KALENDER = "kalender_abweichung"
GRUND_LEER = "ticker_ohne_kursdaten"


# ── Datum / Kalender ──────────────────────────────────────────────────────────
def parse_de(s) -> date | None:
    try:
        return datetime.strptime(str(s).strip(), "%d.%m.%Y").date()
    except (ValueError, TypeError):
        return None


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in config.US_MARKET_HOLIDAYS


def expected_window(edate: date, n: int = WINDOW_DAYS) -> list[date]:
    """Tag 0 (= D) plus die nächsten ``n`` US-Handelstage (Kalender wie S4/S15)."""
    out = [edate]
    d = edate
    while len(out) < n + 1:
        d += timedelta(days=1)
        if is_trading_day(d):
            out.append(d)
    return out


def _finite(x) -> bool:
    if x is None or isinstance(x, bool):
        return False
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _r(x, nd):
    return round(float(x), nd)


def _haircut(gross):
    # Einzige Quelle der Netto-Formel (Produktion); Import erst hier, damit
    # das Modul ohne yfinance importierbar bleibt (Tests stubben yfinance).
    from backtest_history import apply_round_trip_haircut
    return apply_round_trip_haircut(gross)


# ── Kern: eine Zeile aus einem Abruf (pure, deterministisch) ──────────────────
def build_record(ticker: str, edate: date, rows: list[dict] | None, *,
                 fetched_utc: str) -> dict:
    """Pure. ``rows`` = Tageszeilen EINES Abrufs (``{d, o, h, l, c, div,
    split}``, ``d`` = ``date``). Returnt den Datensatz; ``grund`` ist ``None``
    bei vollständigem Fenster. Keine Reife-Prüfung hier (macht der Aufrufer)."""
    window = expected_window(edate)
    rec = {
        "schema_v": SCHEMA_V,
        "ticker": ticker,
        "date": edate.strftime("%d.%m.%Y"),
        "fenster": [d.isoformat() for d in window],
        "bars": [],
        "close_d": None,
        "max_gain_from_entry_pct": None,
        "max_gain_from_entry_pct_net": None,
        "max_drawdown_from_entry_pct": None,
        "grund": None,
        "grund_tag": None,
        "split_im_fenster": False,
        "dividende_im_fenster": False,
        "kurse": SOURCE_LABEL,
        "abgerufen_utc": fetched_utc,
    }
    if not rows:
        rec["grund"] = GRUND_LEER
        return rec
    by_day: dict = {}
    for r in rows:
        d = r.get("d")
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            by_day[d] = r            # gleiche Tag doppelt → letzte gewinnt (Abruf-Reihenfolge)
    # Handelstage in den Daten, die der Kalender nicht kennt → ehrlich null.
    extra = sorted(d for d in by_day if window[0] < d < window[-1] and d not in window)
    bars = []
    for d in window:
        r = by_day.get(d)
        if r is None:
            bars.append({"d": d.isoformat(), "fehlt": True})
            if rec["grund"] is None:
                rec["grund"], rec["grund_tag"] = GRUND_FEHLENDER_TAG, d.isoformat()
            continue
        vals = [r.get(k) for k in ("o", "h", "l", "c")]
        if not all(_finite(v) for v in vals):
            bars.append({"d": d.isoformat(), "halb": True})
            if rec["grund"] is None:
                rec["grund"], rec["grund_tag"] = GRUND_HALBZEILE, d.isoformat()
            continue
        o, h, l, c = (float(v) for v in vals)
        bars.append({"d": d.isoformat(), "o": _r(o, 6), "h": _r(h, 6),
                     "l": _r(l, 6), "c": _r(c, 6)})
        if _finite(r.get("split")) and float(r.get("split")) not in (0.0, 1.0):
            rec["split_im_fenster"] = True
        if _finite(r.get("div")) and float(r.get("div")) != 0.0:
            rec["dividende_im_fenster"] = True
    rec["bars"] = bars
    if rec["grund"] is None and extra:
        rec["grund"], rec["grund_tag"] = GRUND_KALENDER, extra[0].isoformat()
    if rec["grund"] is not None:
        return rec
    close_d = bars[0]["c"]
    if not close_d > 0:
        rec["grund"], rec["grund_tag"] = GRUND_HALBZEILE, bars[0]["d"]
        return rec
    rec["close_d"] = close_d
    highs = [b["h"] for b in bars[1:]]
    lows = [b["l"] for b in bars[1:]]
    mg = _r((max(highs) / close_d - 1.0) * 100.0, 2)
    rec["max_gain_from_entry_pct"] = mg
    net = _haircut(mg)
    rec["max_gain_from_entry_pct_net"] = None if net is None else _r(net, 2)
    rec["max_drawdown_from_entry_pct"] = _r((min(lows) / close_d - 1.0) * 100.0, 2)
    return rec


# ── Kandidaten (nur lesen) ────────────────────────────────────────────────────
def _read_jsonl(path) -> list[dict]:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except FileNotFoundError:
        pass
    return out


def load_candidates(backtest_path=BACKTEST_FILE, export_path=EXPORT_FILE) -> list[tuple]:
    """Forward-Einstiege ab ``START_DATE``: Export (``provenance == forward``)
    ∪ ``backtest_history.json`` (ohne Bootstrap; dort steht der jüngste Teil,
    der noch nicht im Export ist). Schlüssel (ticker, D), sortiert."""
    keys = set()
    for r in _read_jsonl(export_path):
        d = parse_de(r.get("date"))
        if r.get("provenance") == "forward" and d and d >= START_DATE and r.get("ticker"):
            keys.add((str(r["ticker"]), d))
    try:
        with open(backtest_path, "r", encoding="utf-8") as fh:
            bh = json.load(fh)
        bh = bh.get("entries", bh) if isinstance(bh, dict) else bh
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        bh = []
    for r in bh if isinstance(bh, list) else []:
        if not isinstance(r, dict) or r.get("bootstrap"):
            continue
        d = parse_de(r.get("date"))
        if d and d >= START_DATE and r.get("ticker"):
            keys.add((str(r["ticker"]), d))
    return sorted(keys, key=lambda k: (k[1], k[0]))


def existing_keys(path=OUT_FILE) -> set:
    return {(r.get("ticker"), r.get("date")) for r in _read_jsonl(path)}


def freeze_present(handover_path=HANDOVER_FILE) -> bool:
    try:
        text = pathlib.Path(handover_path).read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.strip() == FREEZE_HEADING for line in text.splitlines())


def plan(candidates, done: set, final_cut: date, *, freeze_ok: bool) -> dict:
    """Pure. Teilt Kandidaten in ``reif`` (Tag 10 final, noch nicht geschrieben),
    ``nicht_reif`` und ``gesperrt`` (≥ Replikationsfenster ohne Freeze)."""
    reif, nicht_reif, gesperrt = [], 0, 0
    for t, d in candidates:
        if (t, d.strftime("%d.%m.%Y")) in done:
            continue
        if expected_window(d)[-1] > final_cut:
            nicht_reif += 1
            continue
        if d >= REPLICATION_FROM and not freeze_ok:
            gesperrt += 1
            continue
        reif.append((t, d))
    return {"reif": reif, "nicht_reif": nicht_reif, "gesperrt": gesperrt}


# ── Abruf (injizierbar) ───────────────────────────────────────────────────────
def classify_fetch_error(exc: BaseException) -> str:
    name = type(exc).__name__
    if name == "YFRateLimitError" or "RateLimit" in name:
        return "rate_limit"
    if name in ("YFTzMissingError", "LookupError"):
        return "leer"
    if name == "YFPricesMissingError":
        return "leer" if "Yahoo status_code =" not in str(exc) else "yahoo_fehler"
    return "yahoo_fehler"


def yahoo_fetch(ticker: str, start: date, end_excl: date) -> list[dict]:
    """``Ticker.history(auto_adjust=True, actions=True)`` — EIN Abruf je Ticker."""
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    df = yf.Ticker(ticker).history(start=start.isoformat(), end=end_excl.isoformat(),
                                   interval="1d", auto_adjust=True, actions=True)
    if df is None or getattr(df, "empty", True):
        raise LookupError("leer_ohne_meldung")
    rows = []
    for ts, rec in df.iterrows():
        rows.append({"d": ts.date(), "o": rec.get("Open"), "h": rec.get("High"),
                     "l": rec.get("Low"), "c": rec.get("Close"),
                     "div": rec.get("Dividends", 0.0), "split": rec.get("Stock Splits", 0.0)})
    return rows


def fetch_all(by_ticker: dict, fetch_fn, *, workers: int = MAX_WORKERS):
    """Feste Reihenfolge, max. ``workers`` parallel. Rate-Limit → KEIN Retry;
    alle noch nicht begonnenen Abrufe entfallen (Zeilen bleiben offen)."""
    stop = threading.Event()
    data, errors = {}, {}
    lock = threading.Lock()

    def _one(t):
        if stop.is_set():
            with lock:
                errors[t] = "rate_limit"
            return
        days = by_ticker[t]
        start = min(days)
        end_excl = max(expected_window(d)[-1] for d in days) + timedelta(days=1)
        try:
            rows = fetch_fn(t, start, end_excl)
        except Exception as exc:  # noqa: BLE001
            reason = classify_fetch_error(exc)
            if reason == "rate_limit":
                stop.set()
            with lock:
                if reason == "leer":
                    data[t] = []
                else:
                    errors[t] = reason
            return
        with lock:
            data[t] = rows or []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(_one, sorted(by_ticker)))
    return data, errors


# ── Schreiben (append-only, atomar) ──────────────────────────────────────────
def append_records(records: list[dict], path=OUT_FILE) -> int:
    """Hängt Zeilen an; bestehende Bytes bleiben unverändert (tmp + replace)."""
    if not records:
        return 0
    path = pathlib.Path(path)
    try:
        old = path.read_bytes()
    except FileNotFoundError:
        old = b""
    if old and not old.endswith(b"\n"):
        old += b"\n"
    new = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(old + new.encode("utf-8"))
    os.replace(tmp, path)
    return len(records)


def write_state(state: dict, path=STATE_FILE) -> None:
    path = pathlib.Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


# ── Lauf ──────────────────────────────────────────────────────────────────────
def run(*, now_utc: datetime | None = None, fetch_fn=yahoo_fetch,
        out_path=OUT_FILE, state_path=STATE_FILE, backtest_path=BACKTEST_FILE,
        export_path=EXPORT_FILE, handover_path=HANDOVER_FILE, log=print) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    final_cut = trading_date.last_final_close_date(now_utc)
    cands = load_candidates(backtest_path, export_path)
    done = existing_keys(out_path)
    freeze_ok = freeze_present(handover_path)
    p = plan(cands, done, final_cut, freeze_ok=freeze_ok)
    by_ticker: dict = {}
    for t, d in p["reif"]:
        by_ticker.setdefault(t, []).append(d)
    data, errors = fetch_all(by_ticker, fetch_fn)
    fetched_utc = now_utc.replace(microsecond=0).isoformat()
    records, grund_count, retry_later = [], {}, 0
    today = now_utc.date()
    for t, d in p["reif"]:
        if t in errors:
            continue                                   # Abruf-Fehler → nächster Lauf
        rec = build_record(t, d, data.get(t), fetched_utc=fetched_utc)
        if rec["grund"] is not None:
            day10 = expected_window(d)[-1]
            if (today - day10).days < RETRY_DAYS:
                retry_later += 1                       # noch einmal versuchen
                continue
            grund_count[rec["grund"]] = grund_count.get(rec["grund"], 0) + 1
        records.append(rec)
    written = append_records(records, out_path)
    err_count: dict = {}
    for r in errors.values():
        err_count[r] = err_count.get(r, 0) + 1
    state = {
        "schema_v": SCHEMA_V,
        "last_run_utc": fetched_utc,
        "geschrieben": written,
        "davon_null_nach_grund": dict(sorted(grund_count.items())),
        "nicht_reif": p["nicht_reif"],
        "gesperrt_ohne_freeze": p["gesperrt"],
        "erneut_versuchen": retry_later,
        "abruf_fehler_ticker": dict(sorted(err_count.items())),
        "rate_limit_abbruch": "rate_limit" in err_count,
        "zeilen_gesamt": len(done) + written,
    }
    write_state(state, state_path)
    # NUR Zählungen loggen — keine Kennzahl, keine Verteilung (Blindheit).
    log(f"[outcome_path] {json.dumps(state, ensure_ascii=False, sort_keys=True)}")
    return state


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--run", action="store_true", help="Sammeln und schreiben")
    a = ap.parse_args(argv)
    if not a.run:
        print("Nichts getan (nur mit --run).")
        return 2
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
