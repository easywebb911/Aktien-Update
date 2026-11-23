"""Treffer-Score (unvalidiert) — täglicher SUW-Schatten-Wert für die Top-10.

Easy-Entscheid 15.11.2026: Der SUW-Wert („Leerverkäufer unter Wasser“, von
Beschwitz/Massa) erscheint auf der Hauptkarte unter dem Namen
„Treffer-Score (unvalidiert)“ und als vierter Eintrag im Sortier-Menü.

SCHATTEN-WERT: kein Einfluss auf Setup-Score, KI-Score, Conviction, Filter,
Auswahl oder gespeicherte Reihenfolge der Top-10. Berechnet wird er in
``generate_report.main()`` erst, wenn die Top-10 fest steht; er landet NUR im
Feld ``treffer_score`` und in ``suw_daily.jsonl``.

FREEZE-TRENNUNG (bindend): Der eingefrorene Test „VORABREGISTRIERUNG — SUW“
liest dieses Tagesfeld und ``suw_daily.jsonl`` NIE. Er rechnet selbst aus
endgültigen Daten (``scripts/suw_eval.py``, Betriebsart test). Das Tagesfeld
ist immer vorläufig: der Schlusskurs des Einstiegstags kommt aus dem
Postclose-Lauf und gilt erst am Folgetag ab 07:00 ET als endgültig.

Rechenkern: ``scripts/suw_eval.py`` (``window_days``, ``parse_finra``,
``suw_value``; Lesarten L1–L9) — keine zweite Formel. Neu hier sind nur
Abruf (Zwischenspeicher ``finra_cache/``, Zeitlimit), Rang und Speicherung.

Fail-soft: jeder Fehler (FINRA, Yahoo, Zeitlimit, Datei) lässt das Feld leer;
der Daily-Lauf läuft normal weiter. Unbekannt ist nicht 0: ohne Wert kein Rang.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

_ROOT = pathlib.Path(__file__).resolve().parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suw_eval  # noqa: E402  — Rechenkern (eingefroren, Lesarten L1–L9)

DAILY_FILE = "suw_daily.jsonl"
CACHE_DIR = "finra_cache"
CACHE_KEEP_DAYS = 25            # Easy-Entscheid: 25 Börsentage im Zwischenspeicher
FINRA_TIMEOUT_S = 10            # je Datei
TOTAL_BUDGET_S = 60             # FINRA gesamt
YAHOO_TIMEOUT_S = 20
STAND_VORLAEUFIG = "vorläufig"
GRUND_TAGESSCHLUSS_FEHLT = "Tagesschluss fehlt"
GRUND_KURS_FEHLT = "Kurs fehlt"
RUECKFALL_MAX_HANDELSTAGE = 3   # Easy-Entscheid 23.11.2026: 3 zählt, 4 nicht
SCHEMA_V = 1


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ── Abruf FINRA mit Zwischenspeicher und Zeitlimit ───────────────────────────
def _fetch_finra_http(d: date, timeout: float) -> tuple[str | None, str]:
    import requests
    try:
        r = requests.get(suw_eval.FINRA_URL.format(d=d.strftime("%Y%m%d")), timeout=timeout,
                         headers={"User-Agent": "squeeze-report-treffer-score"})
    except Exception as exc:  # noqa: BLE001
        return None, f"fehler:{type(exc).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    return r.text, "ok"


def load_finra(dates: Sequence[date], *, cache_dir, fetch=_fetch_finra_http,
               budget_s: float = TOTAL_BUDGET_S, clock: Callable[[], float] = time.monotonic
               ) -> tuple[dict, dict]:
    """{date: Dateitext} für die gefragten Tage. Erst Zwischenspeicher, dann
    Abruf (Zeitlimit je Datei + Gesamtbudget). Liefert (texte, status)."""
    cdir = pathlib.Path(cache_dir)
    try:
        cdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    texts, status = {}, {}
    start = clock()
    for d in sorted(set(dates)):
        f = cdir / f"CNMSshvol{d.strftime('%Y%m%d')}.txt"
        try:
            if f.is_file():
                texts[d] = f.read_text(encoding="utf-8")
                status[d.isoformat()] = "cache"
                continue
        except OSError:
            pass
        rest = budget_s - (clock() - start)
        if rest <= 0:
            status[d.isoformat()] = "zeitlimit"
            continue
        text, why = fetch(d, min(FINRA_TIMEOUT_S, rest))
        status[d.isoformat()] = why
        if text is None:
            continue
        texts[d] = text
        try:
            f.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return texts, status


def prune_cache(cache_dir, keep: int = CACHE_KEEP_DAYS) -> int:
    """Behält die jüngsten ``keep`` Dateien (Börsentage) im Zwischenspeicher."""
    cdir = pathlib.Path(cache_dir)
    try:
        files = sorted(cdir.glob("CNMSshvol*.txt"))
    except OSError:
        return 0
    n = 0
    for f in files[:-keep] if keep > 0 else files:
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


# ── Abruf Yahoo (ohne Dividenden-Bereinigung) ────────────────────────────────
def _fetch_closes_yf(tickers: Sequence[str], start: date, end_excl: date) -> dict:
    """{ticker: {date: Close}} — yfinance auto_adjust=False, Spalte Close."""
    import yfinance as yf
    out: dict = {}
    df = yf.download(list(tickers), start=start.isoformat(), end=end_excl.isoformat(),
                     interval="1d", auto_adjust=False, group_by="ticker", threads=True,
                     progress=False, timeout=YAHOO_TIMEOUT_S)
    if df is None or getattr(df, "empty", True):
        return out
    for t in tickers:
        try:
            sub = df[t] if len(tickers) > 1 else df
            col = sub["Close"]
        except Exception:  # noqa: BLE001
            continue
        vals = {}
        for idx, c in col.items():
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            if math.isfinite(c) and c > 0:
                vals[idx.date()] = c
        if vals:
            out[t] = vals
    return out


# ── Rang (Gleichstand wie im Freeze-Block: pool_position, dann Ticker) ───────
def assign_ranks(items: Sequence[dict]) -> None:
    """Setzt ``rang`` (1 = höchster Wert) und ``n_mit_wert`` für Einträge mit
    endlichem ``wert``; ohne Wert: rang None. Gleichstand: kleinere
    pool_position, dann Ticker alphabetisch (L8)."""
    with_val = [it for it in items if _finite(it.get("wert"))]

    def pos(it):
        p = it.get("pool_position")
        return p if _finite(p) else float("inf")

    ordered = sorted(with_val, key=lambda it: (-it["wert"], pos(it), str(it["ticker"])))
    n = len(ordered)
    for i, it in enumerate(ordered, start=1):
        it["rang"] = i
        it["n_mit_wert"] = n
    for it in items:
        if not _finite(it.get("wert")):
            it["rang"] = None
            it["n_mit_wert"] = n


# ── Hauptfunktion ───────────────────────────────────────────────────────────
def compute_for_top10(top10: Sequence[dict], report_day: date, *, cache_dir=CACHE_DIR,
                      fetch_finra=_fetch_finra_http, fetch_closes=_fetch_closes_yf,
                      clock: Callable[[], float] = time.monotonic, holidays=None,
                      budget_s: float = TOTAL_BUDGET_S, extra: Sequence[dict] = (),
                      intraday: bool = False) -> tuple[list[dict], dict]:
    """Berechnet je Top-10-Eintrag den Treffer-Score. Reine Leseoperation auf
    ``top10`` (kein Schreiben ins Stock-Dict). Liefert (items, info). Wirft
    nie: jeder Fehler → Einträge ohne Wert mit Grund.

    ``extra`` (23.11.2026): weitere angezeigte Aktien (Watchlist außerhalb der
    Top-10) im SELBEN Abruf — Wert ohne Rang (``top10`` = False). ``intraday``:
    Vorschau-Lauf, c_D = aktueller Kurs des Laufs (``s["price"]``) statt
    Tagesschluss; Fenster, Gewichtung und Fehl-Regel unverändert (derselbe
    Kern ``suw_eval.suw_value``)."""
    items: list[dict] = []
    info: dict = {}
    for i, s in enumerate(top10, start=1):
        items.append({"ticker": s.get("ticker"), "pool_position": i, "wert": None,
                      "grund": None, "c_d": None, "r": None, "fehlende_tage": None,
                      "top10": True})
    for s in extra or ():
        items.append({"ticker": s.get("ticker"), "pool_position": None, "wert": None,
                      "grund": None, "c_d": None, "r": None, "fehlende_tage": None,
                      "top10": False})
    stocks = list(top10) + list(extra or ())
    try:
        wdays = suw_eval.window_days(report_day, holidays=holidays)
        texts, fstatus = load_finra(wdays, cache_dir=cache_dir, fetch=fetch_finra,
                                    budget_s=budget_s, clock=clock)
        info["finra"] = {"benoetigt": len(wdays),
                         "aus_cache": sum(1 for v in fstatus.values() if v == "cache"),
                         "fehlend": sorted(k for k, v in fstatus.items() if v not in ("ok", "cache"))}
        tickers = [it["ticker"] for it in items if it["ticker"]]
        sv_by_t: dict = {}
        for d, txt in texts.items():
            for sym, v in suw_eval.parse_finra(txt, set(tickers)).items():
                sv_by_t.setdefault(sym, {})[d] = v
        try:
            closes = fetch_closes(tickers, min(wdays) - timedelta(days=5), report_day)
        except Exception as exc:  # noqa: BLE001
            closes = {}
            info["yahoo_fehler"] = type(exc).__name__
        for it, s in zip(items, stocks):
            t = it["ticker"]
            c_d = s.get("price")
            if intraday:
                if not (_finite(c_d) and c_d > 0):
                    it["grund"] = GRUND_KURS_FEHLT
                    continue
            else:
                bar_ok = (s.get("letzte_zeile") != "vortag_rueckfall"
                          and (s.get("bar_date") in (None, report_day.isoformat())))
                if not (bar_ok and _finite(c_d) and c_d > 0):
                    it["grund"] = GRUND_TAGESSCHLUSS_FEHLT
                    continue
            # nur Tage VOR D aus dem Abruf (D selbst kommt aus der reparierten
            # letzten Tageszeile des Daily-Laufs)
            cl = {k: v for k, v in (closes.get(t) or {}).items() if k < report_day}
            cl[report_day] = float(c_d)
            v, why, miss = suw_eval.suw_value(report_day, wdays, sv_by_t.get(t, {}), cl)
            it["fehlende_tage"] = miss
            it["c_d"] = round(float(c_d), 4)
            if v is None:
                it["grund"] = why
                continue
            # R nur für die Log-Zeile, aus dem Kern-Ergebnis zurückgerechnet
            # (SUW = c_D / R − 1) — keine zweite Formel.
            it["r"] = round(float(c_d) / (1 + v / 100.0), 4)
            it["wert"] = round(v, 4)
    except Exception as exc:  # noqa: BLE001 — leer statt Abbruch
        info["fehler"] = type(exc).__name__
        for it in items:
            if it["wert"] is None and it["grund"] is None:
                it["grund"] = "nicht_berechnet"
    # Rang nur unter den Top-10 des Laufs; Watchlist-Werte ohne Rang.
    assign_ranks([it for it in items if it["top10"]])
    for it in items:
        if not it["top10"]:
            it["rang"] = None
            it["n_mit_wert"] = None
    datum = report_day.isoformat()
    for it in items:
        it["datum"] = datum
        it["stand"] = STAND_VORLAEUFIG
    return items, info


def field_from_item(it: dict) -> dict:
    """Feld ``treffer_score`` für das Stock-Dict."""
    return {"wert": it.get("wert"), "rang": it.get("rang"), "n_mit_wert": it.get("n_mit_wert"),
            "datum": it.get("datum"), "stand": it.get("stand"), "grund": it.get("grund")}


def append_daily(items: Sequence[dict], path=DAILY_FILE, *, now: datetime | None = None) -> int:
    """Hängt je Eintrag eine Zeile an ``suw_daily.jsonl`` (nur anhängen)."""
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    lines = []
    for it in items:
        row = {"schema_v": SCHEMA_V, "datum": it.get("datum"), "ticker": it.get("ticker"),
               "pool_position": it.get("pool_position"), "wert": it.get("wert"),
               "rang": it.get("rang"), "n_mit_wert": it.get("n_mit_wert"),
               "stand": it.get("stand"), "grund": it.get("grund"), "c_d": it.get("c_d"),
               "r": it.get("r"), "fehlende_tage": it.get("fehlende_tage"), "berechnet_utc": ts}
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    with open(path, "a", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(ln + "\n")
    return len(lines)


def load_last_postclose(path=DAILY_FILE) -> tuple[str | None, dict]:
    """Letzter Postclose-Tag in ``suw_daily.jsonl``: (Datum ISO, {ticker: Zeile}).
    Fehlende/kaputte Datei → (None, {})."""
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obj, dict) and obj.get("datum") and obj.get("ticker"):
                    rows.append(obj)
    except OSError:
        return None, {}
    if not rows:
        return None, {}
    last = max(r["datum"] for r in rows)
    out = {}
    for r in rows:
        if r["datum"] == last:
            out[r["ticker"]] = r     # spätere Zeile desselben Tages gewinnt
    return last, out


def load_last_value_per_ticker(path=DAILY_FILE) -> dict:
    """{ticker: jüngste Postclose-Zeile mit endlichem Wert} aus
    ``suw_daily.jsonl`` (für den Rückfall im Vorschau-Lauf). Fail-soft."""
    out: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not (isinstance(obj, dict) and obj.get("ticker") and obj.get("datum")
                        and _finite(obj.get("wert"))):
                    continue
                cur = out.get(obj["ticker"])
                if cur is None or str(obj["datum"]) >= str(cur["datum"]):
                    out[obj["ticker"]] = obj
    except OSError:
        return {}
    return out


def trading_days_since(datum_iso: str, report_day: date, holidays=None) -> int | None:
    """US-Handelstage NACH ``datum_iso`` bis einschließlich ``report_day``
    (Wochenenden/Feiertage zählen nicht). None bei unlesbarem Datum."""
    try:
        d0 = date.fromisoformat(str(datum_iso))
    except (TypeError, ValueError):
        return None
    n = 0
    x = d0 + timedelta(days=1)
    while x <= report_day:
        if suw_eval.is_trading_day(x, holidays):
            n += 1
        x += timedelta(days=1)
    return n


def log_line(items: Sequence[dict]) -> str | None:
    """Eine Zeile für die Hand-Nachrechnung: erster Eintrag mit Wert."""
    for it in items:
        if _finite(it.get("wert")):
            return (f"[treffer_score] {it['ticker']} D={it['datum']} c_D={it['c_d']} "
                    f"R={it['r']} fehlende_tage={it['fehlende_tage']} wert={it['wert']}")
    return None


def digest_line(path=DAILY_FILE) -> str:
    """„Treffer-Score: x/10 mit Wert“ für den letzten Postclose-Tag (fail-soft)."""
    try:
        d, rows = load_last_postclose(path)
        if not rows:
            return "📐 Treffer-Score: noch kein Postclose-Wert"
        n_val = sum(1 for r in rows.values() if _finite(r.get("wert")))
        dd = datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.")
        return f"📐 Treffer-Score: {n_val}/{len(rows)} mit Wert (Stand {dd}, vorläufig)"
    except Exception:  # noqa: BLE001
        return "📐 Treffer-Score: nicht ermittelbar"
