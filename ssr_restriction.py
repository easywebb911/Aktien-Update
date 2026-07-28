"""SSR-Sammelfeld (Rule-201 Short-Sale-Restriction) — forward-only S10_OBSERVED.

Erhebt pro postclose-Top-10-Record den **Short-Sale-Restriction-Status** des
Tickers am Entry-Handelstag T aus dem **Cboe-Jahres-Kumulativ**
(``BatsCircuitBreakers<year>.csv``: Trigger/End/Rescinded Date+Time über alle
Börsen). Reine Analyse-/Outcome-Persistenz.

WARUM Cboe-kumulativ (nicht der Nasdaq-per-Tag-File): reicheres Schema
(explizite End/Rescinded-Spalten + Primary Listing Exchange = alle Börsen),
EINE stabile Jahres-URL, und in der Timing-Probe (#481, 28.07.) ebenso
**postclose-final** wie der Nasdaq-File. Robust auf SPALTEN geparst
(``csv.DictReader`` über die Header-Zeile), NIE auf Byte-Positionen — die
Probe zeigte konstante Zeilenzahl bei minimaler Byte-Schwankung.

DISZIPLIN (eingefroren, analog ``material_8k`` / ``entry_past_return_5d`` #402):
  • KEIN Score-/Filter-/Push-/Anzeige-Effekt. Nur ``backtest_history.json``.
    Das Feld darf NIEMALS als Score-Feature gelesen werden (Look-Ahead).
  • EINMAL zum Entry-Tag T aus dem postclose-finalen Stand eingefroren —
    KEIN Rolling-Update. ``rescinded_date`` wird NUR gefüllt, wenn es im
    T-Stand schon vermerkt ist; niemals T+1 nachgetragen (das wäre Look-Ahead).
  • Rule 201 spannt T-1→T: eine Restriktion gilt Trigger-Tag + nächster
    Handelstag. ``triggered_today`` (Trigger==T) und ``carry_over``
    (Trigger==voriger Handelstag) werden EXPLIZIT getrennt, damit ein
    gestriger Übertrag später NICHT als frischer Trigger zählt.
  • Fail-soft überall: Cboe unerreichbar / HTTP-Fehler / Parse-Fehler →
    ``collected=False`` + Grund-Code, GELOGGT, kein Crash, kein Retry-Sturm.
    Zustandsfelder dann ``None`` (= „unbekannt", NICHT ``False`` =
    „geprüft, nicht restricted").
  • Deterministisch: einzige Zeit-Inputs sind ``report_date`` (ET-Handelstag T)
    und ``now_utc`` (Abruf-Zeitpunkt). Kein ``datetime.now()`` im Wertepfad.

BELEGWERTE (Finalitäts-Tripwire, 28.07.2026): ``fetched_at`` (UTC-Abrufzeit)
und ``source_latest_trigger`` (jüngster Trigger-Zeitstempel, der IM File stand,
ET). Die Postclose-Finalität ist an EINEM ruhigen Handelstag gemessen — falls
an einem extremen Tag zu früh gelesen würde, macht der Vergleich beider Stempel
das später in den Daten SICHTBAR, statt es unsichtbar zu lassen.

ZEITZONEN (explizit): Cboe-Quelldaten (Trigger/End/Rescinded Date+Time) sind
**ET** (US-Markt) — ``trigger_date``/``end_date``/``rescinded_date`` sind
ET-Handelstag-Daten, ``trigger_time_et`` ist ET-Wall-Clock, ``report_date`` T
ist der ET-Handelstag. ``fetched_at`` ist ein **UTC**-Maschinen-Stempel
(State-Konvention). Kein ET/UTC-Mix in einem Vergleich: die Restriktions-Logik
vergleicht ausschließlich ET-Daten gegen T; ``fetched_at`` ist reiner Beleg.

ISOLIERTER RÜCKWEG: EIN benannter Top-Level-Key ``ssr_restriction`` pro Record, geschrieben
AUSSCHLIESSLICH hier. ``scripts/purge_ssr_restriction.py`` poppt exakt diesen Key —
benannter Key, keine Recompute-Kollision, kein Manifest nötig (wie material_8k).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

_SOURCE = "cboe_cumulative"
_CBOE_URL_TMPL = ("https://www-api.cboe.com/us/equities/market_statistics/"
                  "short_sale_circuit_breakers/downloads/"
                  "BatsCircuitBreakers{yr}.csv")

# Cboe-CSV-Header (Spalten-Namen, NICHT Positionen — robust gegen Umordnung).
_COL_SYMBOL     = "Symbol"
_COL_TRIG_DATE  = "Trigger Date"
_COL_TRIG_TIME  = "Trigger Time"
_COL_END_DATE   = "End Date"
_COL_RESC_DATE  = "Rescinded Date"


def _default_ua() -> str:
    import os
    return os.environ.get("EDGAR_USER_AGENT",
                          "Squeeze Report contact@example.com")


def _cfg(name, default):
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


# ── Default-I/O (lazy requests) ──────────────────────────────────────────────
def _http_get_text(url: str, ua: str, timeout: int):
    import requests
    r = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
    if r.status_code != 200:
        log.warning("ssr GET %s → HTTP %s", url, r.status_code)
        return None
    return r.text


# ── Pure Helfer ──────────────────────────────────────────────────────────────
def _parse_iso_date(s):
    """``YYYY-MM-DD`` (Cboe-Format) → ``date`` oder ``None``. Leer/kaputt → None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _norm_report_date(report_date):
    """T als ``date``. Akzeptiert ``date``, ISO ``YYYY-MM-DD`` oder ``DD.MM.YYYY``
    (Haus-Format der Backtest-``date``-Spalte). Unbrauchbar → ``None``."""
    if isinstance(report_date, date) and not isinstance(report_date, datetime):
        return report_date
    if isinstance(report_date, datetime):
        return report_date.date()
    s = str(report_date or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def _prev_trading_day(d, holidays):
    """Voriger US-Handelstag vor ``d`` (Wochenende + ``holidays`` überspringend).
    ``holidays`` = Set von ISO-Strings (config.US_MARKET_HOLIDAYS-Format)."""
    hol = holidays or frozenset()
    cur = d - timedelta(days=1)
    # Backstop: max 10 Kalendertage zurück (deckt jedes Feiertags-Wochenende).
    for _ in range(10):
        if cur.weekday() < 5 and cur.isoformat() not in hol:
            return cur
        cur -= timedelta(days=1)
    return cur


def parse_cboe_csv(text):
    """Pure: Cboe-CSV → ``(rows, source_latest_trigger)``.

    ``rows`` = Liste ``{symbol, trigger_date(date), trigger_time(str),
    end_date(date|None), rescinded_date(date|None)}`` (nur parsebare Zeilen mit
    Symbol + Trigger-Datum). ``source_latest_trigger`` = jüngster
    ``"YYYY-MM-DD HH:MM:SS"``-Stempel im File (ET) oder ``None``.
    Spalten über Header-Namen (``csv.DictReader``) — robust gegen Umordnung.
    """
    rows = []
    latest_key = None          # (date, time_str) für den jüngsten Trigger
    latest_str = None
    if not text:
        return rows, None
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        sym = (raw.get(_COL_SYMBOL) or "").strip().upper()
        td = _parse_iso_date(raw.get(_COL_TRIG_DATE))
        if not sym or td is None:
            continue
        ttime = (raw.get(_COL_TRIG_TIME) or "").strip()
        row = {
            "symbol":         sym,
            "trigger_date":   td,
            "trigger_time":   ttime,
            "end_date":       _parse_iso_date(raw.get(_COL_END_DATE)),
            "rescinded_date": _parse_iso_date(raw.get(_COL_RESC_DATE)),
        }
        rows.append(row)
        key = (td, ttime)
        if latest_key is None or key > latest_key:
            latest_key = key
            latest_str = f"{td.isoformat()} {ttime}".strip()
    return rows, latest_str


def build_symbol_index(rows):
    """``rows`` → ``{SYMBOL: [row, ...]}``. Pure."""
    idx = {}
    for r in rows:
        idx.setdefault(r["symbol"], []).append(r)
    return idx


def _empty_wrapper(reason, *, fetched_at=None, source_latest=None):
    """Fail-soft-Wrapper: Zustand UNBEKANNT (None), collected=False."""
    return {
        "collected": False, "reason": reason, "source": _SOURCE,
        "restricted_t": None, "triggered_today": None, "carry_over": None,
        "trigger_date": None, "trigger_time_et": None,
        "end_date": None, "rescinded_date": None,
        "fetched_at": fetched_at, "source_latest_trigger": source_latest,
    }


def flag_ticker(rows_for_symbol, report_date_t, *, prev_td,
                fetched_at=None, source_latest=None):
    """Pure: SSR-Wrapper für EINEN Ticker (dessen Cboe-Zeilen).

    Aktiv am Handelstag T (Rule 201): Trigger-Datum ∈ {T, voriger Handelstag}
    UND nicht vor T geendet/rescinded. ``governing`` = die aktive Zeile mit dem
    jüngsten Trigger; ihre Datums-Felder werden persistiert.
    ``triggered_today`` = governing-Trigger == T; ``carry_over`` = < T
    (schließen sich für die governing-Zeile gegenseitig aus → ein gestriger
    Übertrag zählt NIE als frischer Trigger).
    """
    base = {
        "collected": True, "reason": None, "source": _SOURCE,
        "restricted_t": False, "triggered_today": False, "carry_over": False,
        "trigger_date": None, "trigger_time_et": None,
        "end_date": None, "rescinded_date": None,
        "fetched_at": fetched_at, "source_latest_trigger": source_latest,
    }
    active = []
    for r in rows_for_symbol or []:
        td = r["trigger_date"]
        if td != report_date_t and td != prev_td:
            continue                                   # außerhalb Rule-201-Fenster
        rd = r["rescinded_date"]
        if rd is not None and rd < report_date_t:
            continue                                   # vor T aufgehoben
        ed = r["end_date"]
        if ed is not None and ed < report_date_t:
            continue                                   # vor T beendet
        active.append(r)
    if not active:
        return base
    gov = max(active, key=lambda r: (r["trigger_date"], r["trigger_time"]))
    base["restricted_t"]    = True
    base["triggered_today"] = gov["trigger_date"] == report_date_t
    base["carry_over"]      = gov["trigger_date"] < report_date_t
    base["trigger_date"]    = gov["trigger_date"].isoformat()
    base["trigger_time_et"] = gov["trigger_time"] or None
    base["end_date"]        = gov["end_date"].isoformat() if gov["end_date"] else None
    base["rescinded_date"]  = (gov["rescinded_date"].isoformat()
                               if gov["rescinded_date"] else None)
    return base


# ── Orchestrierung ───────────────────────────────────────────────────────────
def collect_ssr_restriction_flags(tickers, *, report_date, now_utc=None, ua=None,
                      timeout=None, year=None, holidays=None,
                      get_text=None, cboe_text=None):
    """Sammelt für ``tickers`` je den ``ssr_restriction``-Wrapper zum Entry-Tag T.

    Cboe-CSV wird EINMAL geholt (geteilt) — kumulativ für das Jahr von T.
    Fail-soft über den gesamten Pfad. Rückgabe ``{ticker: wrapper}``.

    ``cboe_text`` (Test-Injektion) überspringt den Fetch. ``report_date`` ist
    der ET-Handelstag T (``date`` / ISO / ``DD.MM.YYYY``). ``now_utc`` stempelt
    ``fetched_at`` (Abruf-Beleg).
    """
    result = {}
    if not tickers:
        return result

    t = _norm_report_date(report_date)
    fetched_at = None
    if now_utc is not None:
        _n = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
        fetched_at = _n.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if t is None:
        log.warning("ssr: unbrauchbares report_date %r → alle Ticker leer "
                    "(bad_report_date)", report_date)
        return {tk: _empty_wrapper("bad_report_date", fetched_at=fetched_at)
                for tk in tickers}

    ua = ua or _default_ua()
    timeout = timeout if timeout is not None else _cfg("SSR_RESTRICTION_HTTP_TIMEOUT", 15)
    get_text = get_text or _http_get_text
    hol = holidays if holidays is not None else _cfg("US_MARKET_HOLIDAYS",
                                                     frozenset())

    text = cboe_text
    if text is None:
        yr = year if year is not None else t.year
        url = _CBOE_URL_TMPL.format(yr=yr)
        try:
            text = get_text(url, ua, timeout)
        except Exception as exc:
            log.warning("ssr: Cboe-Fetch fehlgeschlagen (fail-soft): %s", exc)
            text = None
        if text is None:
            return {tk: _empty_wrapper("fetch_failed", fetched_at=fetched_at)
                    for tk in tickers}

    try:
        rows, source_latest = parse_cboe_csv(text)
    except Exception as exc:
        log.warning("ssr: Cboe-Parse fehlgeschlagen (fail-soft): %s", exc)
        return {tk: _empty_wrapper("parse_failed", fetched_at=fetched_at)
                for tk in tickers}
    if not rows:
        # Erfolgreich geladen, aber leer/kein Header-Match → als „unbekannt"
        # behandeln (nicht fälschlich „nicht restricted" für alle).
        log.warning("ssr: Cboe-CSV lieferte 0 Zeilen (empty_or_bad_header)")
        return {tk: _empty_wrapper("empty_or_bad_header", fetched_at=fetched_at,
                                   source_latest=source_latest)
                for tk in tickers}

    idx = build_symbol_index(rows)
    prev_td = _prev_trading_day(t, hol)
    for tk in tickers:
        try:
            result[tk] = flag_ticker(
                idx.get((tk or "").strip().upper()), t, prev_td=prev_td,
                fetched_at=fetched_at, source_latest=source_latest)
        except Exception as exc:
            log.warning("ssr %s: unerwarteter Fehler (fail-soft): %s", tk, exc)
            result[tk] = _empty_wrapper("error", fetched_at=fetched_at,
                                        source_latest=source_latest)
    return result


# ── Selbsttest (nur manuell) ─────────────────────────────────────────────────
def _selftest(argv) -> int:
    """``python -m ssr_restriction --ticker GME --asof 2026-07-27`` — echter Cboe-Call."""
    import argparse
    import json as _json
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", action="append", required=True)
    p.add_argument("--asof", required=True, help="ET-Handelstag T (YYYY-MM-DD)")
    a = p.parse_args(argv)
    res = collect_ssr_restriction_flags(a.ticker, report_date=a.asof,
                            now_utc=datetime.now(timezone.utc))
    print(_json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_selftest(sys.argv[1:]))
