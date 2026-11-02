#!/usr/bin/env python3
"""Mock-Test: Earnings-Termin auf Watchlist-Karten außerhalb der Top-10
(Easy-Entscheid 02.11.2026, REIN ANZEIGE).

Quelle: bereits vorhandenes ``agent_signals.json`` (Feld ``earnings`` =
"in N Tagen (TT.MM.JJJJ)"). Übernommen wird nur das DATUM, die Tage werden
gegen ein festes "heute" neu berechnet. Deterministisch (festes today/now,
kein Netz, kein Real-State).

  01 Termin in der Zukunft → angezeigt, Tage aus dem DATUM (nicht aus "N")
  02 Termin vergangen → leer
  03 unbekannt (None / kein Signal / unparsebar / NaN) → leer
  04 Termin heute → 0
  05 Frische-Gate: updated fehlt / naiv / älter als Schwelle → leer
  06 Karten-Render: identisches Badge-Format wie Top-10
     ("Earnings in Nd (TT.MM.)"), ohne Termin kein Badge
  07 Verdrahtung in main(): nur Ticker außerhalb der Top-10, nur wenn noch
     kein Termin gesetzt, nur auf einer KOPIE (enriched unverändert)
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib
import re
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _install_stubs() -> None:
    """CI läuft auf stdlib + jinja2 + pyyaml (pr-checks.yml) — Drittlibs
    stubben, analog mock_test_atm_iv_zero_guard.py."""
    if "yfinance" not in sys.modules:
        yf = types.ModuleType("yfinance")
        yf.download = lambda *a, **k: None
        yf.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf
    if "requests" not in sys.modules:
        rq = types.ModuleType("requests")
        rq.Session = lambda *a, **k: types.SimpleNamespace(
            headers=types.SimpleNamespace(update=lambda *a, **k: None))
        rq.get = lambda *a, **k: None
        rq.exceptions = types.SimpleNamespace(RequestException=Exception)
        sys.modules["requests"] = rq
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *a, **k: None
        sys.modules["bs4"] = bs4
    if "deep_translator" not in sys.modules:
        dt_mod = types.ModuleType("deep_translator")
        dt_mod.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt_mod
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()

import generate_report as g  # noqa: E402

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


TODAY = dt.date(2026, 11, 2)
NOW = dt.datetime(2026, 11, 2, 13, 30, tzinfo=dt.timezone.utc)
FRESH = "2026-11-02T07:04:00.727373+01:00"


def _sigs(earn, updated=FRESH, ticker="WOLF"):
    return {"updated": updated, "signals": {ticker: {"earnings": earn}}}


def _f(sigs, ticker="WOLF"):
    return g._wl_earnings_from_agent_signals(ticker, sigs, today=TODAY, now_utc=NOW)


def test_01_future_shown_days_from_date():
    # Gespeicherte Zahl "9" ist absichtlich falsch — es zählt nur das Datum.
    r = _f(_sigs("in 9 Tagen (04.11.2026)"))
    _check("01 Zukunft → angezeigt", r == {"earnings_days": 2, "earnings_date_str": "04.11."}, repr(r))


def test_02_past_empty():
    r = _f(_sigs("in 3 Tagen (30.10.2026)"))
    _check("02 vergangen → leer", r == {}, repr(r))


def test_03_unknown_empty():
    for label, sigs in [
        ("None", _sigs(None)),
        ("NaN", _sigs(float("nan"))),
        ("unparsebar", _sigs("in 2 Tagen")),
        ("kein Signal", {"updated": FRESH, "signals": {}}),
        ("kein Dict", None),
        ("ungültiges Datum", _sigs("in 2 Tagen (31.02.2026)")),
    ]:
        r = _f(sigs)
        _check(f"03 unbekannt ({label}) → leer", r == {}, repr(r))


def test_04_today_zero():
    r = _f(_sigs("in 0 Tagen (02.11.2026)"))
    _check("04 heute → 0", r == {"earnings_days": 0, "earnings_date_str": "02.11."}, repr(r))


def test_05_freshness_gate():
    old = (NOW - dt.timedelta(hours=g.WL_EARNINGS_FALLBACK_MAX_AGE_HOURS + 1)).isoformat()
    ok = (NOW - dt.timedelta(hours=g.WL_EARNINGS_FALLBACK_MAX_AGE_HOURS - 1)).isoformat()
    _check("05 älter als Schwelle → leer", _f(_sigs("in 2 Tagen (04.11.2026)", updated=old)) == {})
    _check("05 knapp innerhalb → angezeigt",
           _f(_sigs("in 2 Tagen (04.11.2026)", updated=ok)).get("earnings_days") == 2)
    _check("05 updated fehlt → leer", _f(_sigs("in 2 Tagen (04.11.2026)", updated=None)) == {})
    _check("05 updated ohne Zeitzone → leer",
           _f(_sigs("in 2 Tagen (04.11.2026)", updated="2026-11-02T07:04:00")) == {})


def _card_stock(**extra):
    s = {
        "ticker": "WOLF", "company_name": "Wolfspeed", "score": 50.0,
        "price": 21.98, "change": 1.0, "short_float": 20.0, "short_ratio": 5.0,
        "rel_volume": 1.2, "ma50": 26.8, "ma200": 30.0, "rsi14": 45.0,
        "market_cap": 3.0e9, "float_shares": 1.5e8, "52w_high": 40.0, "52w_low": 10.0,
    }
    s.update(extra)
    return s


def test_06_card_badge_same_format_as_top10():
    try:
        base = g._card(0, _card_stock())
        with_e = g._card(0, _card_stock(**_f(_sigs("in 2 Tagen (04.11.2026)"))))
    except Exception as exc:  # noqa: BLE001
        _check("06 Karten-Render ohne Fehler", False, repr(exc))
        return
    m = re.search(r'<span class="earnings-tag"[^>]*>([^<]*)</span>', with_e)
    _check("06 Badge im Top-10-Format", bool(m) and m.group(1) == "Earnings in 2d (04.11.)",
           m.group(1) if m else "kein Badge")
    _check("06 ohne Termin kein Badge", 'class="earnings-tag"' not in base)


def test_07_main_wiring():
    src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    i = src.index("def _wl_payload_with_earnings(c: dict) -> dict:")
    block = src[i:i + 900]
    _check("07 Top-10-Ticker ausgenommen", 'c["ticker"] in _wl_top10_set' in block)
    _check("07 bestehender Termin bleibt", 'c.get("earnings_days") is not None' in block)
    _check("07 nur auf Kopie (enriched unverändert)", "_wl_card_payload({**c, **_extra})" in block)
    _check("07 kein Schreibzugriff auf c", not re.search(r'\bc\[["\']earnings', block))


def main() -> int:
    for t in (test_01_future_shown_days_from_date, test_02_past_empty,
              test_03_unknown_empty, test_04_today_zero, test_05_freshness_gate,
              test_06_card_badge_same_format_as_top10, test_07_main_wiring):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle wl_earnings_fallback-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
