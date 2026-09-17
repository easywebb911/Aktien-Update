"""Mock-Tests für den News-Anzeige-Max-Age-Cutoff in ``get_yahoo_news()``
(Diagnose: ein 5 Monate alter, themenfremder Artikel — "Top Midday
Decliners" vom 13.04.2026 — tauchte bei PLCE im September weiterhin in
den Top-3-News auf, weil Yahoos ``.news``-Feed für den Ticker aktuell
nichts Frischeres lieferte).

BEFUND: ``NEWS_DECAY_WEIGHTS`` (config.py) gewichtet Items älter als die
höchste Stufe (3 Tage) nur beim Score-Bonus auf 0 herunter — entfernt sie
aber NICHT aus der zurückgegebenen Anzeige-Liste. Es gab keinen Max-Age-
Cutoff für die ANZEIGE.

FIX (generate_report.py:get_yahoo_news(), ~Z. 1480-1489): ein Item mit
bekanntem Alter über ``NEWS_MAX_AGE_DAYS_DISPLAY`` (30 Tage, config.py)
wird komplett übersprungen (nicht mehr in die Liste aufgenommen). Items
mit fehlendem/unparsebarem ``ts`` (pub_ts=0) werden NICHT verworfen —
unbekanntes Alter ist nicht dasselbe wie "alt" (analog zum bestehenden
NEWS_DECAY_FALLBACK-Mittelweg im Score-Pfad).

UNVERÄNDERT: ``NEWS_DECAY_WEIGHTS``/``_news_age_weight`` (Score-Bonus-
Gewichtung in ``_compute_sub_scores()``) — dieser Fix betrifft nur, welche
Items überhaupt in die Liste kommen, nicht wie sie gewichtet werden.

Test-Standard: treibt die ECHTE ``generate_report.get_yahoo_news()`` über
einen gemockten ``yf.Ticker.news``-Response — kein Logik-Replikat. Feste,
deterministische Zeitstempel relativ zu einem FESTEN Anker (``time.time``
gemonkeypatcht auf eine feste Sekunde), nicht "heute minus X Tage" ohne
Ankerpunkt.

Tests:
  1. Ein frischer Artikel (2 Tage vor Anker) + ein alter Artikel (150 Tage
     vor Anker) im Mock-Response → nur der frische landet in der
     zurückgegebenen Liste, der alte wird komplett entfernt.
  2. Alle Items sind alt (150 + 200 Tage) → leere Liste als Ergebnis, kein
     Fehler/keine Exception.
  3. Ein Item mit fehlendem ``providerPublishTime`` (ts nicht ermittelbar)
     bleibt erhalten, obwohl es "irgendwie alt sein könnte" — unbekanntes
     Alter wird nicht als "alt" behandelt (Grenzfall-Bestätigung der
     bewussten Design-Entscheidung).
  4. Ein Item GENAU an der Schwelle (30 Tage minus 1 Sekunde, also noch
     NICHT über der Schwelle) bleibt erhalten — Boundary-Test für das
     ``>``-statt-``>=``-Verhalten.

Ausführung: ``python scripts/mock_test_news_max_age_cutoff.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


# ── Heavy-Dependency-Stubs (identisch zu mock_test_marketcap_price_nan_filter.py
#    / mock_test_atm_iv_zero_guard.py — get_yahoo_news() braucht KEIN pandas,
#    dieser Test läuft daher auf stdlib+Stubs, ALLOWLIST-fähig). ──────────────
def _install_stubs() -> None:
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
        dt = types.ModuleType("deep_translator")
        # Identity-Translate — deterministisch, kein Netzwerk.
        dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()
import generate_report as gr  # noqa: E402

# Fester Anker (beliebiger, aber FIXER Unix-Timestamp) — keine Abhängigkeit
# von der echten Wall-Clock. Alle Item-Zeitstempel werden relativ dazu
# konstruiert.
_ANCHOR_TS = 1_800_000_000
_DAY = 86400


class _FakeTicker:
    def __init__(self, news_items: list[dict]):
        self.news = news_items


def _news_item(title: str, provider_publish_time) -> dict:
    """Flaches (Nicht-'content'-genestetes) yfinance-News-Item — deckt den
    ``content = item.get('content', item)``-Fallback-Zweig ab."""
    return {
        "title": title,
        "providerPublishTime": provider_publish_time,
        "publisher": "Yahoo Finance",
        "link": "https://example.invalid/" + title.replace(" ", "-"),
    }


def _run_with_fake_news(news_items: list[dict]) -> list[dict]:
    fake = _FakeTicker(news_items)
    orig_ticker = gr.yf.Ticker
    orig_time = gr.time.time
    gr.yf.Ticker = lambda ticker: fake
    gr.time.time = lambda: float(_ANCHOR_TS)
    try:
        return gr.get_yahoo_news("TESTTICK", n=5)
    finally:
        gr.yf.Ticker = orig_ticker
        gr.time.time = orig_time


def test_fresh_kept_old_dropped():
    """(1) Frisch (2 Tage) bleibt, alt (150 Tage) wird komplett entfernt."""
    items = [
        _news_item("Fresh Article", _ANCHOR_TS - 2 * _DAY),
        _news_item("Top Midday Decliners", _ANCHOR_TS - 150 * _DAY),
    ]
    result = _run_with_fake_news(items)
    titles = [n["title_orig"] for n in result]
    _check("nur der frische Artikel bleibt in der Liste",
           titles == ["Fresh Article"],
           detail=f"titles={titles!r}")


def test_all_old_yields_empty_list_no_error():
    """(2) Alle Items alt -> leere Liste, kein Fehler."""
    items = [
        _news_item("Very Old A", _ANCHOR_TS - 150 * _DAY),
        _news_item("Very Old B", _ANCHOR_TS - 200 * _DAY),
    ]
    result = _run_with_fake_news(items)
    _check("alle-alt: leere Liste (kein Fehler, kein Ersatz-Fallback)",
           result == [],
           detail=f"result={result!r}")


def test_unknown_age_is_kept_not_dropped():
    """(3) Fehlendes providerPublishTime (ts=0, Alter unbekannt) bleibt erhalten."""
    items = [_news_item("No Timestamp Article", None)]
    result = _run_with_fake_news(items)
    titles = [n["title_orig"] for n in result]
    _check("Item mit unbekanntem Alter wird NICHT verworfen",
           titles == ["No Timestamp Article"],
           detail=f"titles={titles!r}")


def test_boundary_just_under_threshold_is_kept():
    """(4) Genau 1 Sekunde unter der 30-Tage-Schwelle -> bleibt erhalten."""
    just_under = _ANCHOR_TS - (30 * _DAY - 1)
    items = [_news_item("Boundary Article", just_under)]
    result = _run_with_fake_news(items)
    titles = [n["title_orig"] for n in result]
    _check("Item knapp UNTER der Schwelle bleibt erhalten",
           titles == ["Boundary Article"],
           detail=f"titles={titles!r}")


def main() -> int:
    print("── News-Anzeige-Max-Age-Cutoff (get_yahoo_news) ────────────────")
    test_fresh_kept_old_dropped()
    test_all_old_yields_empty_list_no_error()
    test_unknown_age_is_kept_not_dropped()
    test_boundary_just_under_threshold_is_kept()
    print()
    if _fails:
        print(f"{len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("Alle Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
