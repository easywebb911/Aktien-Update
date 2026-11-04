#!/usr/bin/env python3
"""EINMALIGE Bestandskorrektur der Backtest-Renditen aus FINALEN Schlusskursen
(Schritt 2/3, Easy-Entscheid 03.11.2026; Mechanik-Fix #647, Befund Probe #645,
siehe SESSION_HANDOVER „§4-Protokolleintrag 03.11.2026").

Rechnet die schon gefüllten Felder ``return_3d/5d/10d`` (+ ``_net``,
``_vs_spy``), ``entry_price_t1`` und ``return_Nd_t1`` in
``backtest_history.json`` UND ``matured_backtest_export.jsonl`` neu — mit
exakt der Logik von ``ki_agent.update_backtest_returns`` nach #647 (nur
Tageszeilen mit Datum ≤ ``trading_date.last_final_close_date(jetzt)``,
Close.dropna, Index über Handelstage mit Kurs, ``auto_adjust=True``). Die
Gleichheit belegt ``scripts/mock_test_fix_returns_oneoff.py`` (gleiche
Eingabe → gleiche Werte wie ``update_backtest_returns``).

Regeln:
  * Nur Felder, die heute einen Wert haben, werden angefasst (leere Felder
    füllt weiterhin der KI-Agent; Felder, die es im Record nicht gibt,
    werden nie angelegt).
  * Nicht korrigierbar (Ticker ohne Kursdaten, Einstiegstag fehlt, Zieltag
    fehlt/nicht final, SPY fehlt) → ``null``. Nie den alten Wert behalten,
    nie 0.
  * Bootstrap-Zeilen (``source == "bootstrap"``) bleiben unberührt (eigener
    Folgeschritt).
  * Reihenfolge, Zeilenzahl und alle anderen Felder bleiben byte-gleich
    (wird vor dem Schreiben geprüft; sonst Abbruch).
  * Archiv ``return_corrections_archive_2026-11.jsonl`` (append-only): je
    geändertem Feld ``{datei, date, ticker, feld, alt, neu_oder_null,
    grund}``. Wird NICHT geloggt.

BLINDUNG: Das Log enthält nur Zählungen und Abweichungs-Beträge
|alt − neu| (Median, p90, max, Anzahl > 0,5/1/2/5 pp) — keine Renditewerte,
keine Gruppierung nach Score/Bucket/Haltedauer/Regime.

Modi:
  --mode dry_run   (Default) rechnet und berichtet, schreibt NICHTS
  --mode apply     schreibt beide Dateien + Archiv (atomar, .tmp + os.replace)
  --mode restore   spielt das Archiv zurück (alt-Wert dort, wo heute noch
                   der im Archiv stehende neue Wert steht)
  --mode verify    read-only Nachprüfung nach apply (wie dry_run, ohne Schreiben)
  --now ISO        fester Zeitpunkt (Determinismus/Tests); Default jetzt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

BT_FILE = "backtest_history.json"
EXPORT_FILE = "matured_backtest_export.jsonl"
ARCHIVE_FILE = "return_corrections_archive_2026-11.jsonl"
WINDOWS = (3, 5, 10)

# Sicherheits-Grenze gegen einen gestörten Kursabruf: fehlen für mehr
# Ticker die Kursdaten (bekannt im Probe-Lauf #645: 4), bricht apply ab,
# statt reihenweise gültige Werte auf null zu setzen.
MAX_TICKERS_OHNE_DATEN = 10

FIELDS_RET = tuple(f"return_{w}d" for w in WINDOWS)
TARGET_FIELDS = (
    "entry_price_t1",
    *FIELDS_RET,
    *(f"return_{w}d_net" for w in WINDOWS),
    *(f"return_{w}d_vs_spy" for w in WINDOWS),
    *(f"return_{w}d_t1" for w in WINDOWS),
)


# ── Hilfen ───────────────────────────────────────────────────────────────────
def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _dmy(s) -> date | None:
    try:
        return datetime.strptime(s or "", "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _haircut(v):
    from backtest_history import apply_round_trip_haircut
    return apply_round_trip_haircut(v)


# ── Kern: Neuberechnung (identisch zu ki_agent.update_backtest_returns) ─────
def recompute(entry: dict, closes, spy, final_cut: date) -> dict[str, tuple]:
    """Neue Werte für ALLE Ziel-Felder eines Records.

    ``closes`` / ``spy``: Liste ``[(datum, close), …]`` (bereits ohne NaN,
    aufsteigend) oder ``None`` (keine Kursdaten). Returnt
    ``{feld: (neuer_wert_oder_None, grund)}``. ``grund`` ist ``"neu"``, wenn
    ein Wert berechnet wurde, sonst der Grund für ``null``.
    """
    out: dict[str, tuple] = {}
    if not closes:
        return {f: (None, "ticker_ohne_kursdaten") for f in TARGET_FIELDS}
    entry_dt = _dmy(entry.get("date"))
    idx = [d for d, _ in closes]
    ei = idx.index(entry_dt) if entry_dt in idx else -1
    if ei < 0:
        return {f: (None, "einstiegstag_fehlt") for f in TARGET_FIELDS}

    def _close_at(off: int):
        pos = ei + off
        if 0 <= pos < len(closes) and idx[pos] <= final_cut:
            return float(closes[pos][1])
        return None

    spy_idx = [d for d, _ in spy] if spy else []

    def _spy_at(off: int):
        if not spy_idx or entry_dt not in spy_idx:
            return None
        pos = spy_idx.index(entry_dt) + off
        if 0 <= pos < len(spy) and spy_idx[pos] <= final_cut:
            return float(spy[pos][1])
        return None

    entry_basis = _close_at(0) or 0.0
    close_t1 = _close_at(1)
    out["entry_price_t1"] = ((round(close_t1, 4), "neu") if close_t1 is not None
                             else (None, "zieltag_fehlt_oder_nicht_final"))
    for w in WINDOWS:
        k0 = f"return_{w}d"
        if entry_basis > 0:
            c = _close_at(w)
            if c is not None:
                r = round((c / entry_basis - 1) * 100, 2)
                out[k0] = (r, "neu")
                out[f"{k0}_net"] = (_haircut(r), "neu")
                s0, sn = _spy_at(0), _spy_at(w)
                if s0 is not None and s0 > 0 and sn is not None:
                    out[f"{k0}_vs_spy"] = (round(r - (sn / s0 - 1) * 100, 2), "neu")
                else:
                    out[f"{k0}_vs_spy"] = (None, "spy_fehlt_oder_nicht_final")
            else:
                for f in (k0, f"{k0}_net", f"{k0}_vs_spy"):
                    out[f] = (None, "zieltag_fehlt_oder_nicht_final")
        else:
            for f in (k0, f"{k0}_net", f"{k0}_vs_spy"):
                out[f] = (None, "einstieg_nicht_final_oder_ungueltig")
        k1 = f"return_{w}d_t1"
        if close_t1 is not None and close_t1 > 0:
            c = _close_at(1 + w)
            out[k1] = ((round((c / close_t1 - 1) * 100, 2), "neu") if c is not None
                       else (None, "zieltag_fehlt_oder_nicht_final"))
        else:
            out[k1] = (None, "t1_fehlt_oder_nicht_final")
    return out


def correct_record(entry: dict, closes, spy, final_cut: date):
    """Wendet ``recompute`` auf die heute gefüllten Ziel-Felder an.
    Returnt ``(neuer_record, änderungen)``; ``änderungen`` =
    ``[(feld, alt, neu_oder_None, grund)]``. Felder ohne Wert / ohne Key
    bleiben exakt wie sie sind."""
    new = dict(entry)
    changes = []
    vals = recompute(entry, closes, spy, final_cut)
    for f in TARGET_FIELDS:
        if f not in entry or entry[f] is None:
            continue
        nv, grund = vals[f]
        old = entry[f]
        if nv == old and type(nv) is type(old):
            continue
        new[f] = nv
        changes.append((f, old, nv, grund if nv is None else "neu_berechnet"))
    return new, changes


# ── Kursdaten ────────────────────────────────────────────────────────────────
def _series(df) -> list | None:
    try:
        s = df["Close"].dropna()
    except Exception:
        return None
    pairs = [(ts.date(), float(v)) for ts, v in zip(s.index, s.values)]
    return pairs or None


# yfinance-Fehler werden über Klassen-NAMEN eingestuft (Tests laufen ohne
# yfinance): „ausdrücklich keine Daten“ → null erlaubt; Rate-Limit, Timeouts,
# HTTP-/Verbindungsfehler, Yahoo-Sperrmeldungen → unvollständiger Abruf, darf
# NIE zu null führen (siehe classify_fetch_error).


# Yahoo-Fehlerbeschreibungen, die „Symbol/Daten gibt es nicht“ bedeuten.
_EMPTY_DESCRIPTIONS = ("not found", "no data found")


def classify_fetch_error(exc: BaseException) -> str:
    """``leer:<Typ>`` nur bei ausdrücklichem „keine Daten“, sonst ``fehler:<Typ>``.
    yfinance 1.4.1 fasst unter ``YFPricesMissingError`` auch Antworten mit
    HTTP-Statuscode und JEDE ``chart.error``-Beschreibung zusammen (z. B.
    „Invalid Crumb“/„Unauthorized“ bei Sperren) — deshalb wird die Meldung
    ausgewertet: ``(Yahoo status_code = …)`` → Fehler; ``(Yahoo error =
    "…")`` → leer nur bei „Not Found“/„No data found“; ohne Yahoo-Fehler
    (Antwort ohne Kurszeilen im Zeitraum) → leer. Guardian-Finding #653."""
    name = type(exc).__name__
    if name == "YFRateLimitError":
        return "fehler:rate_limit"
    if name == "YFTzMissingError":
        return f"leer:{name}"
    if name == "YFPricesMissingError":
        msg = str(exc)
        if "Yahoo status_code =" in msg:
            return f"fehler:{name}_status_code"
        marker = '(Yahoo error = "'
        if marker in msg:
            desc = msg.split(marker, 1)[1].split('")', 1)[0].lower()
            if any(k in desc for k in _EMPTY_DESCRIPTIONS):
                return f"leer:{name}"
            return f"fehler:{name}_yahoo_error"
        return f"leer:{name}"
    return f"fehler:{name}"


class AbrufUnvollstaendig(Exception):
    """Mindestens ein Ticker wurde nicht sauber abgerufen (Rate-Limit o. ä.)."""


RETRY_PAUSE_S = 5.0


def error_detail(exc: BaseException) -> str:
    """Kurzer Fehlertext für das Log: HTTP-Statuscode (falls vorhanden) und die
    erste Meldungszeile ohne URL-Parameter (keine Kurswerte, kein Crumb)."""
    code = None
    resp = getattr(exc, "response", None)
    for obj in (resp, exc):
        c = getattr(obj, "status_code", None) if obj is not None else None
        if isinstance(c, int):
            code = c
            break
    text = str(exc).splitlines()[0] if str(exc) else ""
    text = text.split("?", 1)[0].strip()[:100]
    return (f"HTTP {code}: " if code is not None else "") + (text or type(exc).__name__)


def fetch_frames(tickers: list[str], start: date, now: datetime, *, workers: int = 4,
                 retry_pause: float | None = None, sleep=None):
    """Einzel-Abruf je Ticker (``Ticker.history``, ``auto_adjust=True``) mit
    ``yf.config.debug.hide_exceptions = False``, damit yfinance Fehler als
    Exception-Typ meldet statt sie zu verschlucken. Liefert
    ``({ticker: df|None}, {ticker: status})`` mit Status ``ok``
    (auch ``ok:wiederholt`` / ``ok:sammelweg``), ``leer:<Typ>`` (ausdrücklich
    keine Daten → darf null werden) oder ``fehler:<Typ> (<Detail>)``
    (Rate-Limit/Netzwerk/unklar → Lauf nicht verwertbar).

    Wiederholung (04.11.2026): Ticker mit Abruf-Fehler (NICHT „leer“, NICHT
    Rate-Limit) werden nach dem parallelen Durchgang EINZELN noch einmal
    versucht — nach ``retry_pause`` Sekunden zuerst derselbe Einzel-Abruf,
    dann der Sammel-Abruf-Weg (``yf.download`` mit yfinance-Standard
    ``hide_exceptions=True``, so lief der Daily-Run und so bekam YYGH im
    Sammel-Lauf #4 Daten). Vom Sammel-Weg wird NUR eine nicht-leere Antwort
    übernommen; leer bleibt Fehler (nie null). ``sleep`` injizierbar (Tests)."""
    import time as _time
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    sleep = sleep or _time.sleep
    retry_pause = RETRY_PAUSE_S if retry_pause is None else retry_pause

    def _hide(flag: bool) -> None:
        try:
            yf.config.debug.hide_exceptions = flag
        except Exception:  # noqa: BLE001 — ältere/gestubbte yfinance
            pass

    _hide(False)
    end = (now.date() + timedelta(days=2)).isoformat()

    def _one(t):
        try:
            df = yf.Ticker(t).history(start=start.isoformat(), end=end, interval="1d",
                                      auto_adjust=True, actions=False)
        except Exception as exc:  # noqa: BLE001
            st = classify_fetch_error(exc)
            if st.startswith("fehler:"):
                st = f"{st} ({error_detail(exc)})"
            return t, None, st
        if df is None or getattr(df, "empty", True):
            return t, None, "fehler:leer_ohne_meldung"
        return t, df, "ok"

    def _sammelweg(t):
        _hide(True)
        try:
            hist = yf.download([t], start=start.isoformat(), end=end, auto_adjust=True,
                               progress=False, threads=False, group_by="ticker")
        except Exception:  # noqa: BLE001
            return None
        finally:
            _hide(False)
        if hist is None or getattr(hist, "empty", True):
            return None
        try:
            df = hist[t]
        except Exception:  # noqa: BLE001
            df = hist
        try:
            if df.dropna(how="all").empty:
                return None
            return df.dropna(how="all")
        except Exception:  # noqa: BLE001
            return None

    frames, status = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for t, df, st in ex.map(_one, sorted(set(tickers))):
            frames[t], status[t] = df, st

    retry = [t for t, st in sorted(status.items())
             if st.startswith("fehler:") and not st.startswith("fehler:rate_limit")]
    for t in retry:
        first = status[t]
        sleep(retry_pause)
        _t, df, st = _one(t)
        if st == "ok":
            frames[t], status[t] = df, "ok:wiederholt"
            continue
        if st.startswith("leer:") or st.startswith("fehler:rate_limit"):
            frames[t], status[t] = None, st
            continue
        df2 = _sammelweg(t)
        if df2 is not None:
            frames[t], status[t] = df2, "ok:sammelweg"
        else:
            status[t] = f"{first} · Wiederholung: {st} · Sammelweg: keine Daten"
    _hide(False)
    return frames, status


def report_fetch(status: dict) -> list[str]:
    """Druckt den Abruf-Status (nur Ticker + Grund, keine Werte). Returnt die
    Ticker mit ``fehler:*``; bei Fehlern klare Meldung."""
    bad = sorted(t for t, st in status.items() if st.startswith("fehler:"))
    empty = sorted(t for t, st in status.items() if st.startswith("leer:"))
    redo = sorted(t for t, st in status.items() if st.startswith("ok:"))
    print(f"Abruf: {len(status)} Ticker · ok {len(status) - len(bad) - len(empty)} "
          f"(davon nach Wiederholung {len(redo)}) · ausdrücklich leer {len(empty)} · "
          f"fehlerhaft {len(bad)}")
    for t in redo + empty + bad:
        print(f"  {t}: {status[t]}")
    if bad:
        print("Abruf unvollständig — nicht verwertbar (Rate-Limit/Abruffehler). "
              "Nichts geschrieben; später erneut starten.")
    return bad


def fetch_prices(tickers: list[str], start: date, now: datetime):
    """Renditen-Pfad: Schlusskurse je Ticker + SPY über ``fetch_frames``.
    Wirft ``AbrufUnvollstaendig``, wenn ein Abruf nicht sauber war."""
    frames, status = fetch_frames(list(tickers) + ["SPY"], start, now)
    if report_fetch(status):
        raise AbrufUnvollstaendig()
    out = {t: (_series(frames[t]) if frames.get(t) is not None else None) for t in tickers}
    spy = _series(frames["SPY"]) if frames.get("SPY") is not None else None
    return out, spy, frames


# ── Dateien lesen / schreiben ────────────────────────────────────────────────
def load_files(root: pathlib.Path):
    bt_raw = (root / BT_FILE).read_text(encoding="utf-8")
    bt = json.loads(bt_raw)
    if json.dumps(bt, indent=2, ensure_ascii=False) != bt_raw:
        raise SystemExit("ABBRUCH: backtest_history.json lässt sich nicht byte-gleich "
                         "neu schreiben — nichts geändert.")
    ex_raw = (root / EXPORT_FILE).read_text(encoding="utf-8")
    ex_lines = ex_raw.split("\n")
    if ex_lines and ex_lines[-1] == "":
        ex_lines = ex_lines[:-1]
        trailing = True
    else:
        trailing = False
    ex = []
    for ln in ex_lines:
        o = json.loads(ln)
        if json.dumps(o, sort_keys=True, ensure_ascii=False) != ln:
            raise SystemExit("ABBRUCH: Export-Zeile nicht byte-gleich neu schreibbar — "
                             "nichts geändert.")
        ex.append(o)
    return bt, bt_raw, ex, ex_lines, trailing


def _ser_bt(bt) -> str:
    return json.dumps(bt, indent=2, ensure_ascii=False)


def _ser_ex(lines: list[str], trailing: bool) -> str:
    return "\n".join(lines) + ("\n" if trailing else "")


def verify_untouched(old: list[dict], new: list[dict], fields=TARGET_FIELDS) -> None:
    """Belegt: gleiche Länge, Reihenfolge, Schlüssel; Nicht-Ziel-Felder gleich."""
    if len(old) != len(new):
        raise SystemExit("ABBRUCH: Zeilenzahl geändert.")
    for o, n in zip(old, new):
        if list(o.keys()) != list(n.keys()):
            raise SystemExit("ABBRUCH: Feld-Reihenfolge/-Menge geändert.")
        for k in o:
            if k not in fields and o[k] != n[k]:
                raise SystemExit(f"ABBRUCH: Nicht-Ziel-Feld {k} geändert.")
            if k in fields and o[k] is None and n[k] is not None:
                raise SystemExit("ABBRUCH: leeres Feld wurde gefüllt.")


def _atomic_write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _check_unique(files: dict) -> None:
    """Archiv und restore adressieren über (ticker, date) — das muss je Datei
    eindeutig sein (Bootstrap-Zeilen ausgenommen, die werden nie angefasst)."""
    for name, lst in files.items():
        keys = [(r.get("ticker"), r.get("date")) for r in lst
                if isinstance(r, dict) and r.get("source") != "bootstrap"]
        if len(keys) != len(set(keys)):
            raise SystemExit(f"ABBRUCH: doppelte (ticker, date) in {name} — nichts geändert.")


# ── Populationen (für die Kennzahlen) ────────────────────────────────────────
def _pops(r: dict) -> list[str]:
    import health_check as hc
    rr = dict(r)
    rr.setdefault("provenance", "forward")
    out = []
    try:
        if hc._is_exit_b1_population_row(rr):
            out.append("§4")
        if hc._is_freeze_population_row(rr, hc._parse_dmy_date(hc._FREEZE_DATE_STR)):
            out.append("Setup-Edge")
        if hc._is_ki_score_population_row(rr, hc._parse_dmy_date(hc._KI_SCORE_FREEZE_DATE_STR)):
            out.append("KI-Score")
    except Exception:
        pass
    return out


def _q(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def _dist(label: str, devs: list[float]) -> None:
    if not devs:
        print(f"{label}: n=0")
        return
    over = {t: sum(1 for d in devs if d > t) for t in (0.5, 1, 2, 5)}
    mx = f"max={max(devs):.3f} pp · " if len(devs) >= 5 else "max=(n<5, ausgeblendet) · "
    print(f"{label}: n={len(devs)} · median={_q(devs, .5):.3f} pp · "
          f"p90={_q(devs, .9):.3f} pp · " + mx
          + " · ".join(f">{t} pp: {c}" for t, c in over.items()))


def _counters(export_path: str):
    """Freeze-Zähler (nur n, kein Ergebnis) für eine Export-Datei."""
    try:
        import health_check as hc
        return (hc.retest_counter_value(export_path),
                hc._count_setup_edge_freeze_population(export_path),
                hc._count_ki_score_freeze_population(export_path))
    except Exception as exc:  # noqa: BLE001
        return ("nicht lesbar", type(exc).__name__)


def _print_counters(root: pathlib.Path) -> None:
    c = _counters(str(root / EXPORT_FILE))
    print(f"Zähler: §4 / Setup-Edge / KI-Score = {c}")


# ── Lauf ─────────────────────────────────────────────────────────────────────
_SKIP_RE = __import__("re").compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


def parse_skip(raw: str | None) -> frozenset:
    """Easy-Entscheid-Liste übersprungener Ticker (Komma/Leerzeichen getrennt).
    Ungültiger Eintrag → ``ValueError`` (Lauf bricht ab, nichts geschrieben)."""
    items = [x.strip().upper() for x in (raw or "").replace(",", " ").split() if x.strip()]
    bad = [x for x in items if not _SKIP_RE.match(x)]
    if bad:
        raise ValueError(f"ungültige Ticker in der Überspringen-Liste: {bad}")
    return frozenset(items)


def print_skip(skip: frozenset) -> None:
    if skip:
        print(f"Übersprungen (Easy-Entscheid, Felder bleiben UNVERÄNDERT, kein Archiv): "
              f"{sorted(skip)}")


def run(mode: str, now: datetime, root: pathlib.Path = ROOT, prices=None,
        max_null: int | None = None, skip: frozenset = frozenset()) -> int:
    import trading_date
    final_cut = trading_date.last_final_close_date(now)
    bt, bt_raw, ex, ex_lines, trailing = load_files(root)
    _check_unique({BT_FILE: bt, EXPORT_FILE: ex})
    sha_bt, sha_ex = _sha(root / BT_FILE), _sha(root / EXPORT_FILE)

    def _todo(r):
        return (isinstance(r, dict) and r.get("source") != "bootstrap"
                and r.get("ticker") not in skip
                and any(f in r and r[f] is not None for f in TARGET_FIELDS)
                and _dmy(r.get("date")) is not None)

    print_skip(skip)
    recs = [r for r in bt if _todo(r)] + [r for r in ex if _todo(r)]
    tickers = sorted({r["ticker"] for r in recs if r.get("ticker")})
    if not tickers:
        print("Nichts zu tun.")
        return 0
    start = min(_dmy(r["date"]) for r in recs) - timedelta(days=10)
    frames = None
    if prices is None:
        try:
            closes_by, spy, frames = fetch_prices(tickers, start, now)
        except AbrufUnvollstaendig:
            return 2
    else:
        closes_by, spy = prices
    ohne = sorted(t for t in tickers if not closes_by.get(t))
    _print_counters(root)
    print(f"Stand: final_cut={final_cut.isoformat()} · Ticker {len(tickers)} · "
          f"ohne Kursdaten {len(ohne)}: {ohne} · SPY {'ok' if spy else 'FEHLT'}")

    archive: list[dict] = []
    stats = Counter()
    devs: dict[str, list[float]] = {}
    seen_keys = set()

    def _process(lst, datei):
        new_lst = []
        for r in lst:
            if not _todo(r):
                new_lst.append(r)
                continue
            new, ch = correct_record(r, closes_by.get(r["ticker"]), spy, final_cut)
            new_lst.append(new)
            n_target = sum(1 for f in TARGET_FIELDS if f in r and r[f] is not None)
            stats[f"{datei}:felder"] += n_target
            stats[f"{datei}:unveraendert"] += n_target - len(ch)
            for f, old, nv, grund in ch:
                stats[f"{datei}:geaendert" if nv is not None else f"{datei}:null:{grund}"] += 1
                archive.append({"datei": datei, "date": r.get("date"), "ticker": r.get("ticker"),
                                "feld": f, "alt": old, "neu_oder_null": nv, "grund": grund})
            # Abweichungs-Kennzahlen (nur return_Nd, wie #645), je Schlüssel einmal
            key_base = (r.get("ticker"), r.get("date"))
            pops = _pops(r)
            for f in FIELDS_RET:
                ov, nv = _num(r.get(f)), _num(new.get(f))
                if ov is None or nv is None or (key_base, f) in seen_keys:
                    continue
                seen_keys.add((key_base, f))
                d = abs(ov - nv)
                for k in ("alle", *(f"pop:{p}" for p in pops)):
                    devs.setdefault(k, []).append(d)
        return new_lst

    # Export zuerst (dort stehen die Freeze-Populationen), dann backtest_history
    new_ex = _process(ex, EXPORT_FILE)
    new_bt = _process(bt, BT_FILE)
    verify_untouched(ex, new_ex)
    verify_untouched(bt, new_bt)

    for datei in (EXPORT_FILE, BT_FILE):
        nulls = {k.split(":", 2)[2]: v for k, v in stats.items() if k.startswith(f"{datei}:null:")}
        print(f"[{datei}] Felder {stats[f'{datei}:felder']} · unverändert "
              f"{stats[f'{datei}:unveraendert']} · geändert {stats[f'{datei}:geaendert']} · "
              f"auf null {sum(nulls.values())} {dict(sorted(nulls.items()))}")
    n_null = sum(v for k, v in stats.items() if ":null:" in k)
    print(f"Auf null gesetzt gesamt (beide Dateien): {n_null}")
    print("Abweichung |alt − neu| (nur return_3d/5d/10d, je Ticker/Datum/Feld einmal):")
    for k in ("alle", "pop:§4", "pop:Setup-Edge", "pop:KI-Score"):
        _dist(f"  {k}", devs.get(k, []))

    # Freeze-Populationen verlangen gefüllte Renditen — ein auf null gesetztes
    # Feld könnte eine Zeile aus einer Population fallen lassen. Zähler auf dem
    # BERECHNETEN Export prüfen; ändern sie sich, schreibt apply nicht (Easy
    # entscheidet über den Umgang mit diesen Zeilen).
    import tempfile
    with tempfile.TemporaryDirectory() as _td:
        _tp = pathlib.Path(_td) / EXPORT_FILE
        _tp.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                               for r in new_ex), encoding="utf-8")
        c_before = _counters(str(root / EXPORT_FILE))
        c_after = _counters(str(_tp))
    print(f"Zähler nach Korrektur (berechnet): {c_after} · "
          f"{'unverändert' if c_after == c_before else 'GEÄNDERT'}")

    if mode in ("dry_run", "verify"):
        if frames is not None and mode == "dry_run":
            measure_max_gain(ex, now, final_cut, frames)
        print(f"Modus {mode}: nichts geschrieben.")
        return 0

    # apply: Sicherheits-Grenzen
    # Schutz gegen Massen-Nullung durch einen gestörten Kursabruf (abgeschnittene
    # Historien, NaN-Tage): apply verlangt die Obergrenze aus dem dry_run.
    if max_null is None:
        print("ABBRUCH: --max-null fehlt (Zahl „Auf null gesetzt gesamt“ aus dem dry_run "
              "angeben). Nichts geschrieben.")
        return 2
    if n_null > max_null:
        print(f"ABBRUCH: {n_null} Felder würden auf null gesetzt (> {max_null} aus dem dry_run) — "
              "Kursabruf vermutlich anders/gestört. Nichts geschrieben.")
        return 2
    if len(ohne) > MAX_TICKERS_OHNE_DATEN:
        print(f"ABBRUCH: {len(ohne)} Ticker ohne Kursdaten (> {MAX_TICKERS_OHNE_DATEN}) — "
              "Kursabruf vermutlich gestört. Nichts geschrieben.")
        return 2
    if not spy and any(r.get(f"return_{w}d_vs_spy") is not None for r in recs for w in WINDOWS):
        print("ABBRUCH: SPY-Kurse fehlen. Nichts geschrieben.")
        return 2
    if c_after != c_before:
        print("ABBRUCH: die Korrektur würde Freeze-Zähler ändern (Zeilen fielen aus einer "
              "Population). Nichts geschrieben — Easy entscheidet.")
        return 2
    if _sha(root / BT_FILE) != sha_bt or _sha(root / EXPORT_FILE) != sha_ex:
        print("ABBRUCH: Dateien seit dem Lesen geändert. Nichts geschrieben.")
        return 2

    changed_ex = {i for i, (o, n) in enumerate(zip(ex, new_ex)) if o != n}
    new_ex_lines = [json.dumps(new_ex[i], sort_keys=True, ensure_ascii=False)
                    if i in changed_ex else ln for i, ln in enumerate(ex_lines)]
    bt_text = _ser_bt(new_bt)
    ex_text = _ser_ex(new_ex_lines, trailing)
    # Gegenprobe vor dem Schreiben: neu geparst = berechnet
    verify_untouched(bt, json.loads(bt_text))
    verify_untouched(ex, [json.loads(ln) for ln in ex_text.split("\n") if ln])
    if not archive:
        print("Modus apply: keine Änderung nötig, nichts geschrieben.")
        return 0
    arch_path = root / ARCHIVE_FILE
    prev = arch_path.read_text(encoding="utf-8") if arch_path.exists() else ""
    arch_text = prev + "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in archive)
    _atomic_write(arch_path, arch_text)
    _atomic_write(root / EXPORT_FILE, ex_text)
    _atomic_write(root / BT_FILE, bt_text)
    print(f"Modus apply: geschrieben — {len(archive)} Felder, Archiv {ARCHIVE_FILE}.")
    return 0


def restore(root: pathlib.Path = ROOT, apply: bool = False) -> int:
    """Spielt das Archiv zurück: setzt ``alt`` dort, wo heute noch
    ``neu_oder_null`` steht (später geänderte Werte bleiben unangetastet)."""
    rows = [json.loads(l) for l in (root / ARCHIVE_FILE).read_text(encoding="utf-8").splitlines() if l]
    bt, bt_raw, ex, ex_lines, trailing = load_files(root)
    files = {BT_FILE: bt, EXPORT_FILE: ex}
    _check_unique(files)
    idx = {name: {(r.get("ticker"), r.get("date")): r for r in lst
                  if isinstance(r, dict) and r.get("source") != "bootstrap"}
           for name, lst in files.items()}
    n_ok = n_skip = 0
    touched_ex = set()
    for a in reversed(rows):
        r = idx.get(a["datei"], {}).get((a["ticker"], a["date"]))
        if r is None or r.get(a["feld"]) != a["neu_oder_null"]:
            n_skip += 1
            continue
        r[a["feld"]] = a["alt"]
        n_ok += 1
        if a["datei"] == EXPORT_FILE:
            touched_ex.add((a["ticker"], a["date"]))
    print(f"restore: zurückgespielt {n_ok} · übersprungen {n_skip}")
    if not apply:
        print("restore (Probe): nichts geschrieben.")
        return 0
    new_lines = [json.dumps(o, sort_keys=True, ensure_ascii=False)
                 if (o.get("ticker"), o.get("date")) in touched_ex else ln
                 for o, ln in zip(ex, ex_lines)]
    _atomic_write(root / EXPORT_FILE, _ser_ex(new_lines, trailing))
    _atomic_write(root / BT_FILE, _ser_bt(bt))
    return 0


# ── Nur messen: max_gain_pct / max_drawdown_pct im Export ───────────────────
def measure_max_gain(ex: list[dict], now: datetime, final_cut: date, frames: dict) -> None:
    """Gleiche Kennzahlen für max_gain_pct / max_drawdown_pct gegen finale
    Kurse (Fenster wie backtest_history: ab Entry, erste 11 Zeilen, nur wenn
    alle 11 Zeilen final sind). Ändert NICHTS."""
    try:
        from backtest_history import _compute_max_drawdown, _compute_max_gain_pct
    except Exception as exc:  # noqa: BLE001
        print(f"max_gain/max_drawdown-Messung übersprungen: {type(exc).__name__}")
        return
    recs = [r for r in ex if _dmy(r.get("date"))
            and (_num(r.get("max_gain_pct")) is not None or _num(r.get("max_drawdown_pct")) is not None)]
    if not recs:
        print("max_gain/max_drawdown: keine Werte im Export.")
        return
    devs: dict[str, list[float]] = {}
    skip = Counter()
    for r in recs:
        try:
            df = frames[r["ticker"]]
            df = df.dropna(subset=["High", "Low"])
        except Exception:
            skip["ticker_fehlt"] += 1
            continue
        ed = _dmy(r["date"])
        win = df[df.index.date >= ed].iloc[:11]
        if len(win) < 11 or win.index[-1].date() > final_cut or win.index[0].date() != ed:
            skip["fenster_unvollstaendig"] += 1
            continue
        pops = _pops(r)
        for f, fn in (("max_gain_pct", _compute_max_gain_pct),
                      ("max_drawdown_pct", _compute_max_drawdown)):
            ov, nv = _num(r.get(f)), _num(fn(win))
            if ov is None or nv is None:
                continue
            for k in ("alle", *(f"pop:{p}" for p in pops)):
                devs.setdefault(f"{f}|{k}", []).append(abs(ov - nv))
    print(f"max_gain/max_drawdown (NUR GEMESSEN, nichts geändert) · übersprungen {dict(skip)}")
    for f in ("max_gain_pct", "max_drawdown_pct"):
        for k in ("alle", "pop:§4", "pop:Setup-Edge", "pop:KI-Score"):
            _dist(f"  {f} {k}", devs.get(f"{f}|{k}", []))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("dry_run", "apply", "verify", "restore", "restore_probe"),
                    default="dry_run")
    ap.add_argument("--target", choices=("returns", "maxgain_shadow"), default="returns",
                    help="returns (Default, Pfad aus #648 unverändert) oder maxgain_shadow "
                         "(max_gain_pct/max_drawdown_pct + Exit-Shadow-Forwards)")
    ap.add_argument("--now", default=None)
    ap.add_argument("--skip-tickers", default="",
                    help="Easy-Entscheid: diese Ticker überspringen (Felder unverändert)")
    ap.add_argument("--max-null", type=int, default=None,
                    help="apply: höchstens so viele Felder dürfen auf null gesetzt werden "
                         "(Zahl aus dem dry_run)")
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        skip = parse_skip(a.skip_tickers)
    except ValueError as exc:
        print(f"ABBRUCH: {exc}. Nichts geschrieben.")
        return 2
    if a.target == "maxgain_shadow":
        import fix_maxgain_shadow as mgs
        if a.mode in ("restore", "restore_probe"):
            return mgs.restore(apply=(a.mode == "restore"))
        return mgs.run(a.mode, now, max_null=a.max_null, skip=skip)
    if a.mode in ("restore", "restore_probe"):
        return restore(apply=(a.mode == "restore"))
    return run(a.mode, now, max_null=a.max_null, skip=skip)


if __name__ == "__main__":
    sys.exit(main())
