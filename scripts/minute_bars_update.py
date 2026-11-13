"""Minutenkurse Tag 1 je Top-10-Einstieg — Sammler + Backfill (Weg A, Schritt 2).

Easy-Auftrag 13.11.2026 nach der Probe (Lauf 43520272302: brauchbar, beide
Einschränkungen akzeptiert; open_item ``handelskosten-messung``):

* Je Forward-Einstieg (``ticker``, ``D`` = ET-Handelstag, Top-10 aus
  ``backtest_history.json``/Export, ohne Bootstrap) EINE Zeile mit den
  1-Minuten-Balken von **Tag 1** (= nächster US-Handelstag nach D).
* Vor- und nachbörsliche Balken werden mitgespeichert, jeder Balken trägt die
  Sitzung (``vor`` / ``reg`` / ``nach``). Minuten ohne Handel bleiben LEER
  (kein Auffüllen, kein Vortragen).
* Einstiegs- und Schlusskurs kommen weiter aus der **Tageszeile**: die Zeile
  speichert dazu die Tageszeilen von D und Tag 1 (``tageszeile_d`` /
  ``tageszeile_tag1``). Der letzte Minutenkurs ist NICHT der offizielle
  Schluss (Schlussauktion fehlt in den Minuten, Probe: 0–0,74 %).
* Prüf-Kennzeichen je Zeile (KEIN Ausschluss): Hoch/Tief der regulären
  Minuten gegen die Tageszeile von Tag 1, Toleranz
  ``config.MINUTE_BARS_HL_TOL_PCT`` (0,5 %).
* Abruf erst, wenn der Close von Tag 1 endgültig ist
  (``trading_date.last_settled_close_date``), solange Yahoo die Minuten noch
  liefert (~30 Tage). Ein Tag, den Yahoo nicht mehr liefert, wird als
  ``null`` mit Grund ``ausserhalb_yahoo_fenster`` notiert. Unbekannt ≠ 0.
* Erster Lauf = Backfill aller noch abrufbaren Tage ab
  ``config.MINUTE_BARS_START_DATE``.

Kurse: yfinance ``interval=1m``, ``prepost=True``, ``auto_adjust=False``;
Tageszeilen ``interval=1d``, ``auto_adjust=False`` — Stand zum Abrufzeitpunkt.

**BLINDHEIT / keine Auswertung:** Das Skript SCHREIBT nur. Log und State
enthalten nur Zählungen, keine Kurse, keine Kennzahl. Einstiege ≥ 24.10.2026
werden nur gespeichert (open_item ``blindes-fenster-keine-weiteren-tests``).
Kein Score-/Ranking-/Push-/Anzeige-Effekt.

Dateien: ``minute_bars/<Tag1 ISO>.jsonl.gz`` — append-only: neue Zeilen werden
als weiteres gzip-Glied angehängt (bestehende Bytes bleiben unverändert,
``gzip`` liest mehrgliedrige Dateien), kein Prune, atomar (tmp + replace),
deterministisch (gzip ``mtime=0``). Dazu ``minute_bars_state.json``
(Heartbeat, nur Zählungen). Liest ``backtest_history.json`` und
``matured_backtest_export.jsonl`` nur.

Aufruf (Workflow ``minute_bars.yml``)::

    python scripts/minute_bars_update.py --run
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import trading_date  # noqa: E402
from outcome_path_update import (  # noqa: E402  (nur Lesen der Kandidaten)
    BACKTEST_FILE, EXPORT_FILE, is_trading_day, load_candidates, parse_de,
)

SCHEMA_V = 1
ET = ZoneInfo("America/New_York")
OUT_DIR = ROOT / config.MINUTE_BARS_DIR
STATE_FILE = ROOT / config.MINUTE_BARS_STATE_FILE
START_DATE = config.MINUTE_BARS_START_DATE
RETRY_DAYS = config.MINUTE_BARS_RETRY_DAYS
HL_TOL = float(config.MINUTE_BARS_HL_TOL_PCT)
MAX_WORKERS = 2
CHUNK_DAYS = 7          # Yahoo: max. 8 Kalendertage je 1-Min-Abruf
OPEN, CLOSE = time(9, 30), time(16, 0)
REG_MINUTES = 390
SOURCE_LABEL = ("yfinance 1m prepost=True auto_adjust=False; Tageszeile 1d "
                "auto_adjust=False; Stand zum Abrufzeitpunkt")

GRUND_FENSTER = "ausserhalb_yahoo_fenster"
GRUND_KEINE_MINUTEN = "keine_minutendaten"


# ── Kalender ──────────────────────────────────────────────────────────────────
def next_trading_day(d: date) -> date:
    x = d + timedelta(days=1)
    while not is_trading_day(x):
        x += timedelta(days=1)
    return x


def _finite(x) -> bool:
    if x is None or isinstance(x, bool):
        return False
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _p(x):
    return round(float(x), 6) if _finite(x) else None


def _v(x):
    return int(round(float(x))) if _finite(x) else None


def session_of(t: datetime) -> str:
    tt = t.time()
    if tt < OPEN:
        return "vor"
    if tt >= CLOSE:
        return "nach"
    return "reg"


def _daily_row(rows, d: date):
    for r in rows or []:
        rd = r.get("d")
        if isinstance(rd, datetime):
            rd = rd.date()
        if rd == d:
            return {"o": _p(r.get("o")), "h": _p(r.get("h")), "l": _p(r.get("l")),
                    "c": _p(r.get("c")), "v": _v(r.get("v"))}
    return None


def _pct(a, b):
    if not _finite(a) or not _finite(b) or float(b) == 0:
        return None
    return round(abs(float(a) / float(b) - 1.0) * 100.0, 4)


# ── Kern: eine Zeile (pure, deterministisch) ──────────────────────────────────
def build_record(ticker: str, edate: date, bars: list | None, exchange,
                 daily_rows: list | None, *, fetched_utc: str,
                 grund: str | None = None) -> dict:
    """Pure. ``bars`` = 1-Min-Balken (``{t: datetime ET, o,h,l,c,v}``) des
    Abrufs; nur Balken von Tag 1 werden übernommen. ``grund`` erzwingt eine
    null-Zeile (z. B. ``ausserhalb_yahoo_fenster``)."""
    day1 = next_trading_day(edate)
    rec = {
        "schema_v": SCHEMA_V,
        "ticker": ticker,
        "date": edate.strftime("%d.%m.%Y"),
        "tag1": day1.isoformat(),
        "boerse": exchange,
        "tageszeile_d": _daily_row(daily_rows, edate),
        "tageszeile_tag1": _daily_row(daily_rows, day1),
        "minuten_felder": ["hh:mm ET", "sitzung", "o", "h", "l", "c", "v"],
        "minuten": [],
        "anzahl": {"vor": 0, "reg": 0, "nach": 0, "reg_ohne_handel": None},
        "pruefung": {"toleranz_pct": HL_TOL, "hoch_abw_pct": None,
                     "tief_abw_pct": None, "ok": None, "grund": None},
        "grund": grund,
        "kurse": SOURCE_LABEL,
        "abgerufen_utc": fetched_utc,
    }
    if grund is not None:
        rec["pruefung"]["grund"] = grund
        return rec
    own = []
    for b in bars or []:
        t = b.get("t")
        if not isinstance(t, datetime):
            continue
        t = t.astimezone(ET) if t.tzinfo else t.replace(tzinfo=ET)
        if t.date() != day1:
            continue
        vals = [b.get(k) for k in ("o", "h", "l", "c")]
        if not all(_finite(x) for x in vals):
            continue                       # Halbbalken: nicht erfinden, weglassen
        own.append((t, b))
    # Gleiche Minute doppelt → letzte gewinnt (Abruf-Reihenfolge), dann sortiert.
    by_min = {}
    for t, b in own:
        by_min[(t.hour, t.minute)] = (t, b)
    rows, regs = [], []
    for key in sorted(by_min):
        t, b = by_min[key]
        s = session_of(t)
        rows.append([t.strftime("%H:%M"), s, _p(b["o"]), _p(b["h"]), _p(b["l"]),
                     _p(b["c"]), _v(b.get("v"))])
        rec["anzahl"][s] += 1
        if s == "reg":
            regs.append(rows[-1])
    rec["minuten"] = rows
    if not rows:
        rec["grund"] = GRUND_KEINE_MINUTEN
        rec["pruefung"]["grund"] = GRUND_KEINE_MINUTEN
        return rec
    rec["anzahl"]["reg_ohne_handel"] = REG_MINUTES - len(regs)
    day = rec["tageszeile_tag1"]
    if not regs:
        rec["pruefung"]["grund"] = "keine_regulaeren_minuten"
    elif day is None:
        rec["pruefung"]["grund"] = "keine_tageszeile"
    else:
        hi = _pct(max(r[3] for r in regs), day.get("h"))
        lo = _pct(min(r[4] for r in regs), day.get("l"))
        rec["pruefung"].update(hoch_abw_pct=hi, tief_abw_pct=lo)
        if hi is None or lo is None:
            rec["pruefung"]["grund"] = "tageszeile_unvollstaendig"
        else:
            rec["pruefung"]["ok"] = hi <= HL_TOL and lo <= HL_TOL
    return rec


# ── Bestand (gz, mehrgliedrig) ────────────────────────────────────────────────
class StoreBroken(Exception):
    pass


def file_for(day1: date, out_dir=OUT_DIR) -> pathlib.Path:
    return pathlib.Path(out_dir) / f"{day1.isoformat()}.jsonl.gz"


def existing_keys(out_dir=OUT_DIR) -> set:
    """(ticker, D-DE) aller gespeicherten Zeilen. Unlesbare Datei → StoreBroken
    (dann schreibt der Lauf nichts)."""
    keys = set()
    d = pathlib.Path(out_dir)
    if not d.exists():
        return keys
    for f in sorted(d.glob("*.jsonl.gz")):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    keys.add((obj.get("ticker"), obj.get("date")))
        except (OSError, EOFError, ValueError, UnicodeDecodeError) as exc:
            raise StoreBroken(f"{f.name}: {type(exc).__name__}") from exc
    return keys


def append_records(records: list[dict], out_dir=OUT_DIR) -> int:
    """Hängt je Tag-1-Datei EIN gzip-Glied an. Bestehende Bytes bleiben
    unverändert (tmp + replace). Deterministisch (sortiert, mtime=0)."""
    if not records:
        return 0
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_file: dict = {}
    for r in sorted(records, key=lambda r: (r["tag1"], r["ticker"], r["date"])):
        by_file.setdefault(r["tag1"], []).append(r)
    for day1, recs in sorted(by_file.items()):
        path = file_for(date.fromisoformat(day1), out_dir)
        try:
            old = path.read_bytes()
        except FileNotFoundError:
            old = b""
        text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) + "\n" for r in recs)
        member = gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(old + member)
        os.replace(tmp, path)
    return len(records)


def write_state(state: dict, path=STATE_FILE) -> None:
    path = pathlib.Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


# ── Plan (pure) ───────────────────────────────────────────────────────────────
def plan(candidates, done: set, settled: date) -> dict:
    reif, nicht_reif = [], 0
    for t, d in candidates:
        if d < START_DATE or (t, d.strftime("%d.%m.%Y")) in done:
            continue
        if next_trading_day(d) > settled:
            nicht_reif += 1
            continue
        reif.append((t, d))
    return {"reif": reif, "nicht_reif": nicht_reif}


def chunks(days: list[date]) -> list[list[date]]:
    """Tag-1-Daten je Ticker in Abruf-Fenster ≤ CHUNK_DAYS Kalendertage."""
    out, cur = [], []
    for d in sorted(set(days)):
        if cur and (d - cur[0]).days >= CHUNK_DAYS:
            out.append(cur)
            cur = []
        cur.append(d)
    if cur:
        out.append(cur)
    return out


# ── Abruf (injizierbar) ───────────────────────────────────────────────────────
def classify_fetch_error(exc: BaseException) -> str:
    name, msg = type(exc).__name__, str(exc)
    if name == "YFRateLimitError" or "RateLimit" in name or "Too Many Requests" in msg:
        return "rate_limit"
    if "data not available for startTime" in msg or "must be within the last" in msg:
        return "ausserhalb_fenster"
    if name in ("YFTzMissingError", "LookupError"):
        return "leer"
    if name == "YFPricesMissingError":
        return "leer" if "Yahoo status_code =" not in msg else "yahoo_fehler"
    return "yahoo_fehler"


def _yf():
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    return yf


def yahoo_minutes(ticker: str, start: date, end_excl: date):
    yf = _yf()
    tk = yf.Ticker(ticker)
    df = tk.history(start=start.isoformat(), end=end_excl.isoformat(), interval="1m",
                    prepost=True, auto_adjust=False, actions=False)
    meta = getattr(tk, "history_metadata", {}) or {}
    bars = []
    if df is not None and not getattr(df, "empty", True):
        for ts, r in df.iterrows():
            t = ts.tz_convert(ET).to_pydatetime() if ts.tzinfo else ts.to_pydatetime()
            bars.append({"t": t, "o": r.get("Open"), "h": r.get("High"), "l": r.get("Low"),
                         "c": r.get("Close"), "v": r.get("Volume")})
    return bars, meta.get("exchangeName")


def yahoo_daily(ticker: str, start: date, end_excl: date) -> list[dict]:
    yf = _yf()
    df = yf.Ticker(ticker).history(start=start.isoformat(), end=end_excl.isoformat(),
                                   interval="1d", auto_adjust=False, actions=False)
    rows = []
    if df is not None and not getattr(df, "empty", True):
        for ts, r in df.iterrows():
            rows.append({"d": ts.date(), "o": r.get("Open"), "h": r.get("High"),
                         "l": r.get("Low"), "c": r.get("Close"), "v": r.get("Volume")})
    return rows


def fetch_all(by_ticker: dict, minute_fn, daily_fn, *, workers: int = MAX_WORKERS):
    """Je Ticker: eine Tageszeilen-Abfrage + 1-Min-Abfragen je Fenster.
    Fenster außerhalb der Yahoo-Reichweite → je Tag neu versucht, sonst
    ``ausserhalb``. Rate-Limit → KEIN Retry; alle noch nicht begonnenen
    Ticker entfallen (Zeilen bleiben offen). Ein Ticker mit Abruf-Fehler
    liefert gar nichts (keine halben Zeilen)."""
    stop = threading.Event()
    data, errors = {}, {}
    lock = threading.Lock()

    def _minutes(t, days):
        try:
            return minute_fn(t, days[0], days[-1] + timedelta(days=1)), None
        except Exception as exc:  # noqa: BLE001
            return None, classify_fetch_error(exc)

    def _one(t):
        if stop.is_set():
            with lock:
                errors[t] = "rate_limit"
            return
        entries = by_ticker[t]                       # [(D, day1)]
        d_min = min(d for d, _ in entries)
        d1_max = max(d1 for _, d1 in entries)
        try:
            daily = daily_fn(t, d_min, d1_max + timedelta(days=1))
        except Exception as exc:  # noqa: BLE001
            reason = classify_fetch_error(exc)
            if reason == "rate_limit":
                stop.set()
                with lock:
                    errors[t] = reason
                return
            if reason not in ("leer", "ausserhalb_fenster"):
                with lock:
                    errors[t] = reason
                return
            daily = []
        bars, exch, ausserhalb = [], None, set()
        for ch in chunks([d1 for _, d1 in entries]):
            res, reason = _minutes(t, ch)
            if reason == "ausserhalb_fenster" and len(ch) > 1:
                parts = [(_minutes(t, [d]), d) for d in ch]
            else:
                parts = [((res, reason), None)]
            for (r, why), single in parts:
                if why == "rate_limit":
                    stop.set()
                    with lock:
                        errors[t] = why
                    return
                if why == "ausserhalb_fenster":
                    ausserhalb.update([single] if single else ch)
                    continue
                if why == "leer":
                    continue
                if why is not None:
                    with lock:
                        errors[t] = why
                    return
                b, ex = r
                bars.extend(b or [])
                exch = exch or ex
        with lock:
            data[t] = {"bars": bars, "exchange": exch, "daily": daily or [],
                       "ausserhalb": ausserhalb}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(_one, sorted(by_ticker)))
    return data, errors


# ── Lauf ──────────────────────────────────────────────────────────────────────
def run(*, now_utc: datetime | None = None, minute_fn=yahoo_minutes, daily_fn=yahoo_daily,
        out_dir=OUT_DIR, state_path=STATE_FILE, backtest_path=BACKTEST_FILE,
        export_path=EXPORT_FILE, log=print) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    fetched_utc = now_utc.replace(microsecond=0).isoformat()
    try:
        done = existing_keys(out_dir)
    except StoreBroken as exc:
        state = {"schema_v": SCHEMA_V, "last_run_utc": fetched_utc, "geschrieben": 0,
                 "datei_kaputt": str(exc), "rate_limit_abbruch": False}
        write_state(state, state_path)
        log(f"[minute_bars] {json.dumps(state, ensure_ascii=False, sort_keys=True)}")
        return state
    # Close von Tag 1 endgültig erst am Folgetag ab 07:00 ET (#681).
    settled = trading_date.last_settled_close_date(now_utc)
    cands = load_candidates(backtest_path, export_path)
    p = plan(cands, done, settled)
    by_ticker: dict = {}
    for t, d in p["reif"]:
        by_ticker.setdefault(t, []).append((d, next_trading_day(d)))
    data, errors = fetch_all(by_ticker, minute_fn, daily_fn)
    today = now_utc.astimezone(ET).date()
    records, grund_count, retry_later, pruef_abw, pruef_offen = [], {}, 0, 0, 0
    for t, d in p["reif"]:
        if t in errors:
            continue                               # Abruf-Fehler → nächster Lauf
        got = data.get(t) or {}
        day1 = next_trading_day(d)
        if day1 in got.get("ausserhalb", set()):
            rec = build_record(t, d, None, got.get("exchange"), got.get("daily"),
                               fetched_utc=fetched_utc, grund=GRUND_FENSTER)
        else:
            rec = build_record(t, d, got.get("bars"), got.get("exchange"), got.get("daily"),
                               fetched_utc=fetched_utc)
            incomplete = rec["grund"] is not None or rec["tageszeile_tag1"] is None
            if incomplete and (today - day1).days < RETRY_DAYS:
                retry_later += 1
                continue
        if rec["grund"] is not None:
            grund_count[rec["grund"]] = grund_count.get(rec["grund"], 0) + 1
        elif rec["pruefung"]["ok"] is False:
            pruef_abw += 1
        elif rec["pruefung"]["ok"] is None:
            pruef_offen += 1
        records.append(rec)
    written = append_records(records, out_dir)
    err_count: dict = {}
    for r in errors.values():
        err_count[r] = err_count.get(r, 0) + 1
    state = {
        "schema_v": SCHEMA_V,
        "last_run_utc": fetched_utc,
        "geschrieben": written,
        "davon_null_nach_grund": dict(sorted(grund_count.items())),
        "pruefung_hoch_tief_abweichend": pruef_abw,
        "pruefung_nicht_moeglich": pruef_offen,
        "nicht_reif": p["nicht_reif"],
        "erneut_versuchen": retry_later,
        "abruf_fehler_ticker": dict(sorted(err_count.items())),
        "rate_limit_abbruch": "rate_limit" in err_count,
        "zeilen_gesamt": len(done) + written,
    }
    write_state(state, state_path)
    # NUR Zählungen loggen — keine Kurse, keine Kennzahl (keine Auswertung).
    log(f"[minute_bars] {json.dumps(state, ensure_ascii=False, sort_keys=True)}")
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
