"""Options-Sammlung in der Handelszeit (Easy-Entscheid 16.11.2026, open_item
``erkundungsfeld-plan`` Teil B).

REINE SAMMLUNG — keine Auswertung, keine Rendite, keine Anzeige, kein Score-/
Filter-/Push-Effekt. Getrennt von der Nachtsammlung ``options_chain_raw.jsonl``
(die bleibt unverändert).

Je Lauf (werktags in der US-Handelszeit, siehe ``.github/workflows/
options_intraday.yml``): für die Top-10 des letzten Postclose (jüngstes Datum D
der Nicht-Bootstrap-Einträge in ``backtest_history.json``) je Ticker die
Optionskette für
  (a) den ersten Verfall am oder nach Tag 10 des Einstiegs
      (``trading_date.nth_trading_day_after(D, 10)``) und
  (b) den darauf folgenden Verfall,
Basispreise ±``OPTIONS_CHAIN_RAW_MONEYNESS_RANGE`` (30 %) um den Kurs, Felder
wie in ``options_chain_raw.jsonl`` plus Aktienkurs aus DEMSELBEN Abruf
(``option_chain(...).underlying``) und Abrufzeit in UTC.

Unbekannt ist nicht 0: fehlende Werte bleiben ``None``. Fehlt eine Kette oder
ein Kurs → Zeile mit ``grund``, kein Abbruch. Rate-Limit → kein Retry, die
restlichen Ticker bekommen ``grund = "rate_limit"``. Zeitlimit für den ganzen
Lauf (``DEADLINE_S``).

Datei: ``options_chain_intraday.jsonl`` (nur angehängt). State:
``options_intraday_state.json`` (nur Zählungen, für den Digest).
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ROOT = pathlib.Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import trading_date  # noqa: E402
from config import OPTIONS_CHAIN_RAW_MONEYNESS_RANGE, US_MARKET_HOLIDAYS  # noqa: E402

DATA_FILE = "options_chain_intraday.jsonl"
STATE_FILE = "options_intraday_state.json"
BACKTEST_FILE = "backtest_history.json"
SCHEMA_V = 1
TOP_N = 10
DAY_OFFSET = 10                 # Tag 10 des Einstiegs
N_EXPIRIES = 2                  # (a) erster Verfall >= Tag 10, (b) der folgende
DEADLINE_S = 600                # Zeitlimit für den ganzen Lauf
PAUSE_S = 1.0                   # Pause zwischen Tickern
# Lauf-Fenster in US-Ostküstenzeit: frühestens 30 min nach Eröffnung, spätestens
# 30 min vor Schluss (Geld/Brief in der Handelszeit, nicht in Auktionen).
WINDOW_START_ET = (10, 0)
WINDOW_END_ET = (15, 30)
_NY = ZoneInfo("America/New_York")


# ── reine Helfer ────────────────────────────────────────────────────────────
def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _parse_dmy(s):
    try:
        return datetime.strptime(s, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def is_trading_day(d: date, holidays=US_MARKET_HOLIDAYS) -> bool:
    return d.weekday() < 5 and d.isoformat() not in holidays


def run_window_ok(now_utc: datetime, holidays=US_MARKET_HOLIDAYS) -> tuple[bool, str]:
    """(ok, grund). Nur an US-Handelstagen und im Fenster 10:00–15:30 ET."""
    et = now_utc.astimezone(_NY)
    if not is_trading_day(et.date(), holidays):
        return False, "kein_handelstag"
    t = (et.hour, et.minute)
    if t < WINDOW_START_ET:
        return False, "vor_fenster"
    if t >= WINDOW_END_ET:
        return False, "nach_fenster"
    return True, "ok"


def load_last_postclose_top10(backtest_path) -> tuple[date | None, list[str]]:
    """Jüngstes Datum D der Nicht-Bootstrap-Einträge (Postclose-Append) und die
    Ticker dieses Tages, nach pool_position sortiert (Gleichstand: Ticker)."""
    try:
        data = json.loads(pathlib.Path(backtest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, []
    by: dict = {}
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict) or e.get("source"):
            continue
        d = _parse_dmy(e.get("date"))
        t = e.get("ticker")
        if d is None or not isinstance(t, str) or not t:
            continue
        by.setdefault(d, {})[t] = e.get("pool_position")
    if not by:
        return None, []
    d = max(by)
    pos = by[d]
    tickers = sorted(pos, key=lambda t: (pos[t] if _finite(pos[t]) else 1e9, t))
    return d, tickers[:TOP_N]


def pick_expiries(expiry_strings, tag10: date, n: int = N_EXPIRIES) -> list[str]:
    """Erster Verfall am oder nach ``tag10`` und die ``n-1`` folgenden
    (aufsteigend, nur gültige ISO-Daten)."""
    ds = []
    for s in expiry_strings or []:
        try:
            ds.append(date.fromisoformat(str(s)))
        except ValueError:
            continue
    ds = sorted(set(ds))
    return [x.isoformat() for x in ds if x >= tag10][:n]


def extract_rows(df, spot) -> list[dict]:
    """Rohwerte je Strike innerhalb ±Moneyness (pandas-frei, Duck-Typing wie
    ``generate_report._extract_full_option_rows``). Fehlend/NaN → None."""
    rows: list = []
    if df is None or not _finite(spot) or spot <= 0:
        return rows
    cols = set(getattr(df, "columns", []))
    if "strike" not in cols:
        return rows
    strikes = list(df["strike"])
    n = len(strikes)

    def col(name):
        return list(df[name]) if name in cols else [None] * n

    bids, asks, lasts = col("bid"), col("ask"), col("lastPrice")
    vols, ois, ivs, ltds = col("volume"), col("openInterest"), col("impliedVolatility"), col("lastTradeDate")
    for i, sr in enumerate(strikes):
        k = _num(sr)
        if k is None or abs(k / spot - 1) > OPTIONS_CHAIN_RAW_MONEYNESS_RANGE:
            continue
        v, oi = _num(vols[i]), _num(ois[i])
        ltd = ltds[i]
        if hasattr(ltd, "isoformat"):
            try:
                ltd = ltd.isoformat()
            except Exception:  # noqa: BLE001
                ltd = None
        if not isinstance(ltd, str) or ltd in ("", "NaT"):
            ltd = None
        rows.append({"strike": k, "bid": _num(bids[i]), "ask": _num(asks[i]),
                     "lastPrice": _num(lasts[i]),
                     "volume": int(v) if v is not None else None,
                     "openInterest": int(oi) if oi is not None else None,
                     "impliedVolatility": _num(ivs[i]), "lastTradeDate": ltd})
    rows.sort(key=lambda r: r["strike"])
    return rows


def atm_pair_ok(expiry_entry: dict, spot) -> bool:
    """Vollständiges Paar Call/Put am gemeinsamen Strike nächst dem Kurs mit
    Geld- und Briefkurs > 0."""
    if not _finite(spot) or not expiry_entry or expiry_entry.get("grund"):
        return False
    cs = {r["strike"]: r for r in expiry_entry.get("calls") or []}
    ps = {r["strike"]: r for r in expiry_entry.get("puts") or []}
    common = [k for k in cs if k in ps]
    if not common:
        return False
    k = min(common, key=lambda x: (abs(x - spot), x))
    return all(_finite(r.get("bid")) and r["bid"] > 0 and _finite(r.get("ask")) and r["ask"] > 0
               for r in (cs[k], ps[k]))


def _is_rate_limit(exc) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "too many requests" in s or "rate limit" in s or "ratelimit" in s or "429" in s


def _underlying_spot(underlying) -> tuple[float | None, str | None]:
    if not isinstance(underlying, dict):
        return None, None
    p = _num(underlying.get("regularMarketPrice"))
    ts = underlying.get("regularMarketTime")
    iso = None
    tv = _num(ts)
    if tv is not None and tv > 0:
        iso = datetime.fromtimestamp(tv, tz=timezone.utc).isoformat()
    return (p if p is not None and p > 0 else None), iso


def collect_ticker(ticker: str, entry_d: date, tag10: date, *, now_utc: datetime,
                   ticker_factory) -> dict:
    """Eine Zeile für einen Ticker. ``ticker_factory(ticker)`` liefert ein
    Objekt mit ``.options`` und ``.option_chain(expiry)`` (yfinance-Ticker oder
    Test-Double). Wirft nur bei Rate-Limit (Aufrufer bricht dann ab)."""
    row = {"schema_v": SCHEMA_V, "date": now_utc.astimezone(_NY).date().isoformat(),
           "entry_date": entry_d.isoformat(), "tag10": tag10.isoformat(), "ticker": ticker,
           "fetch_ts_utc": now_utc.isoformat(), "spot": None, "spot_time_utc": None,
           "spot_source": "option_chain.underlying", "expiries": [], "grund": None}
    try:
        tk = ticker_factory(ticker)
        exps = pick_expiries(list(getattr(tk, "options", None) or []), tag10)
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit(exc):
            raise
        row["grund"] = "verfallsliste_fehlt"
        return row
    if not exps:
        row["grund"] = "kein_verfall_ab_tag10"
        return row
    for ex in exps:
        entry = {"expiry": ex,
                 "days_to_expiry": (date.fromisoformat(ex) - now_utc.astimezone(_NY).date()).days,
                 "calls": [], "puts": [], "grund": None}
        try:
            ch = tk.option_chain(ex)
        except Exception as exc:  # noqa: BLE001
            if _is_rate_limit(exc):
                raise
            entry["grund"] = "kette_fehlt"
            row["expiries"].append(entry)
            continue
        spot, spot_ts = _underlying_spot(getattr(ch, "underlying", None))
        if row["spot"] is None and spot is not None:
            row["spot"], row["spot_time_utc"] = spot, spot_ts
        use_spot = spot if spot is not None else row["spot"]
        if use_spot is None:
            entry["grund"] = "kurs_fehlt"
        else:
            entry["calls"] = extract_rows(getattr(ch, "calls", None), use_spot)
            entry["puts"] = extract_rows(getattr(ch, "puts", None), use_spot)
            if not entry["calls"] and not entry["puts"]:
                entry["grund"] = "kette_leer"
        row["expiries"].append(entry)
    if row["spot"] is None:
        row["grund"] = "kurs_fehlt"
    elif all(e.get("grund") for e in row["expiries"]):
        row["grund"] = "keine_kette"
    return row


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    with_chain = [r for r in rows if not r.get("grund")]
    pair = sum(1 for r in with_chain
               if r["expiries"] and atm_pair_ok(r["expiries"][0], r.get("spot")))
    return {"n_tickers": n, "n_with_chain": len(with_chain), "n_pair_ok": pair}


def prev_trading_day(d: date, holidays=US_MARKET_HOLIDAYS) -> date:
    x = d - timedelta(days=1)
    while not is_trading_day(x, holidays):
        x -= timedelta(days=1)
    return x


def already_done(state: dict, today_et: str) -> bool:
    """Ein Lauf je US-Handelstag: auch nach Rate-Limit oder Zeitlimit holt ein
    späterer Slot desselben Tages NICHT nach (kein Retry, Easy-Vorgabe)."""
    return isinstance(state, dict) and state.get("last_run_date") == today_et


def run(*, now_utc: datetime | None = None, root=_ROOT, ticker_factory=None,
        sleep=time.sleep, monotonic=time.monotonic, force: bool = False) -> dict:
    """Ein Lauf. Gibt den neuen State zurück (auch bei Skip). Ist ``now_utc``
    gesetzt (Tests), gilt es auch als Abrufzeit je Ticker; sonst echte Uhr."""
    clock = (lambda: now_utc) if now_utc is not None else (lambda: datetime.now(timezone.utc))
    now_utc = now_utc or datetime.now(timezone.utc)
    root = pathlib.Path(root)
    state_path = root / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    today_et = now_utc.astimezone(_NY).date().isoformat()
    ok, why = run_window_ok(now_utc)
    if not ok and not force:
        print(f"[options_intraday] übersprungen: {why} ({now_utc.isoformat()})")
        return state
    if already_done(state, today_et) and not force:
        print(f"[options_intraday] heute schon gesammelt ({today_et}) — übersprungen")
        return state
    entry_d, tickers = load_last_postclose_top10(root / BACKTEST_FILE)
    if entry_d is None or not tickers:
        print("[options_intraday] keine Postclose-Top-10 gefunden — nichts gesammelt")
        return state
    tag10 = trading_date.nth_trading_day_after(entry_d, DAY_OFFSET, US_MARKET_HOLIDAYS)
    # Kennzeichen statt stiller Annahme (Guardian 16.11.): fehlt der Postclose
    # des letzten Handelstags (Lauf ausgefallen, Vintage-Guard-Verwurf), wird die
    # ältere Top-10 trotzdem gesammelt, aber als veraltet markiert.
    erwartet = prev_trading_day(date.fromisoformat(today_et))
    top10_aktuell = entry_d == erwartet
    if not top10_aktuell:
        print(f"[options_intraday] WARNUNG: Top-10 vom {entry_d}, erwartet {erwartet} — als veraltet markiert")
    if ticker_factory is None:
        import yfinance as yf  # Netz nur im echten Lauf
        ticker_factory = yf.Ticker
    t0 = monotonic()
    rows: list[dict] = []
    stop_reason = None
    for i, t in enumerate(tickers):
        if stop_reason is None and monotonic() - t0 > DEADLINE_S:
            stop_reason = "zeitlimit"
        if stop_reason is not None:
            rows.append({"schema_v": SCHEMA_V, "date": today_et, "entry_date": entry_d.isoformat(),
                         "tag10": tag10.isoformat(), "ticker": t,
                         "fetch_ts_utc": now_utc.isoformat(), "spot": None, "spot_time_utc": None,
                         "spot_source": "option_chain.underlying", "expiries": [],
                         "grund": stop_reason})
            continue
        try:
            rows.append(collect_ticker(t, entry_d, tag10, now_utc=clock(),
                                       ticker_factory=ticker_factory))
        except Exception:  # Rate-Limit: kein Retry
            stop_reason = "rate_limit"
            rows.append({"schema_v": SCHEMA_V, "date": today_et, "entry_date": entry_d.isoformat(),
                         "tag10": tag10.isoformat(), "ticker": t,
                         "fetch_ts_utc": now_utc.isoformat(), "spot": None, "spot_time_utc": None,
                         "spot_source": "option_chain.underlying", "expiries": [],
                         "grund": "rate_limit"})
        if i + 1 < len(tickers) and stop_reason is None:
            sleep(PAUSE_S)
    with (root / DATA_FILE).open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    summ = summarize(rows)
    for r in rows:
        r["top10_aktuell"] = top10_aktuell
    new_state = {"last_run_date": today_et, "last_run_utc": now_utc.isoformat(),
                 "entry_date": entry_d.isoformat(), "tag10": tag10.isoformat(),
                 "top10_aktuell": top10_aktuell, "erwartet_entry_date": erwartet.isoformat(),
                 "status": "fertig" if stop_reason is None else stop_reason, **summ}
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(new_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, state_path)
    print(f"[options_intraday] {today_et}: Kette {summ['n_with_chain']}/{summ['n_tickers']}, "
          f"ATM-Paar {summ['n_pair_ok']}/{summ['n_with_chain']} (Einstieg {entry_d}, Tag 10 {tag10}, "
          f"Status {new_state['status']})")
    return new_state


def digest_line(state_path=STATE_FILE) -> str:
    """„🧾 Optionen Handelszeit (TT.MM.): Kette x/10 · ATM-Paar y/x“ (fail-soft)."""
    try:
        st = json.loads(pathlib.Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "🧾 Optionen Handelszeit: noch kein Lauf"
    try:
        d = datetime.strptime(st["last_run_date"], "%Y-%m-%d").strftime("%d.%m.")
        n, c, p = st["n_tickers"], st["n_with_chain"], st["n_pair_ok"]
        anteil = f"{round(100 * p / c)} %" if c else "—"
        extra = "" if st.get("status") == "fertig" else f" · Status {st.get('status')}"
        if st.get("top10_aktuell") is False:
            ed = datetime.strptime(st["entry_date"], "%Y-%m-%d").strftime("%d.%m.")
            extra += f" · Top-10 vom {ed} (veraltet)"
        if isinstance(n, int) and n < TOP_N:
            extra += f" · nur {n} Ticker"
        return f"🧾 Optionen Handelszeit ({d}): Kette {c}/{n} · ATM-Paar {p}/{c} ({anteil}){extra}"
    except Exception:  # noqa: BLE001
        return "🧾 Optionen Handelszeit: nicht ermittelbar"


if __name__ == "__main__":
    run(force="--force" in sys.argv)
