"""Mock-Tests fuer News-Coverage-Erweiterung (Watchlist-Extras).

Diagnose 15.05.2026: get_combined_news lief nur ueber Top-10. CRMD
als Position (heute nicht in Top-10) zeigte „Keine Nachrichten
verfuegbar" im Watchlist-Drawer trotz frischer Earnings.

Fix: News-Pool erweitert um manual_personal-Tickers aus enriched.
Set-Dedup verhindert Doppel-Fetch. News werden via _news_by_ticker
ueber das enriched-Stream attached — Top-10-Stocks bekommen sie
direkt (Referenz-equal), Watchlist-Outsider via _wl_card_payload
ins watchlist_cards[ticker].news.

Tests:
  1. Source-Inspektion: News-Pool ist Set aus top10 ∪
     manual_personal
  2. Source-Inspektion: max_workers >= 15 (deckt 10 Top + 3-5
     Watchlist-Extras)
  3. Source-Inspektion: News werden via _news_by_ticker an
     enriched-Dicts attached
  4. Source-Inspektion: get_combined_news unveraendert
     (Vorsichts-Prinzip)
  5. Pythonische Replikation: Set-Dedup (Ticker in beiden Listen
     wird einmal gefetcht)
  6. Pythonische Replikation: News-Attachment-Pfad — Top-10-Stock
     + Watchlist-Outsider bekommen news
  7. Pythonische Replikation: enriched ohne manual_personal -> News-
     Pool = Top-10 (Regression auf alten Verhalten bei keinen
     persoenlichen Watchlist-Tickern)
  8. Fallback „Keine Nachrichten verfuegbar" bei echtem leeren
     Fetch-Result bleibt funktional
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "generate_report.py").read_text(encoding="utf-8")


def _news_block() -> str:
    """Extrahiert den News-Fetch-Block (zwischen 'Opt 3 — Parallel news'
    Comment und naechstem Comment-Block)."""
    start = SRC.find("# Opt 3 — Parallel news fetching")
    assert start > 0, "News-Fetch-Block nicht gefunden"
    # bis zum Print mit "News:" + Step 4 Comment
    end = SRC.find("# Parallel options data fetch", start)
    assert end > start
    return SRC[start:end]


# === 1 — Source-Inspektion: News-Pool ===================================


def test_news_pool_is_set_union():
    block = _news_block()
    # News-Pool als Set initialisiert
    assert "_news_pool = {s[\"ticker\"] for s in top10}" in block, (
        "News-Pool nicht als Set aus top10-Tickers definiert")
    # Manual-personal-Tickers werden via Set-Union dazu gemerged
    pat = re.compile(
        r"_news_pool\s*\|=\s*\{c\[\"ticker\"\]\s+for\s+c\s+in\s+enriched"
        r"\s+if\s+c\.get\(\"manual_personal\"\)\}",
    )
    assert pat.search(block), (
        "manual_personal-Tickers werden nicht in den News-Pool gemerged")


def test_news_pool_uses_set_dedup():
    """Set-Operation garantiert Dedup ohne explizite Logik."""
    block = _news_block()
    # Set-Comprehension UND |=-Operator
    assert "{s[\"ticker\"] for s in top10}" in block
    assert "|=" in block


def test_news_max_workers_increased():
    """max_workers=16 deckt erweiterten Pool ab (10 Top + bis zu 6
    Watchlist-Extras)."""
    block = _news_block()
    assert "max_workers=16" in block, (
        "max_workers nicht auf 16 erhoeht — Erweiterung des Pools "
        "wuerde den Thread-Pool eng machen")
    # Alter Wert 13 sollte weg sein
    assert "max_workers=13" not in block, (
        "Alter max_workers=13 noch in News-Block — Update unvollstaendig")


# === 2 — News-Attachment ueber enriched =================================


def test_news_attached_via_news_by_ticker_dict():
    block = _news_block()
    # Result-Dict-Pattern: _news_by_ticker
    assert "_news_by_ticker" in block, (
        "_news_by_ticker-Dict nicht im News-Block")
    pat = re.compile(
        r"_news_by_ticker\[_news_futures\[_fut\]\]\s*=\s*_fut\.result\(\)",
    )
    assert pat.search(block), (
        "_news_by_ticker wird nicht aus Futures-Resultaten befuellt")


def test_news_attached_to_enriched_dicts():
    """Loop ueber enriched: pro Stock-Dict news-Field setzen wenn
    Ticker in _news_by_ticker."""
    block = _news_block()
    pat = re.compile(
        r"for _c in enriched:.*?if _t in _news_by_ticker:.*?_c\[\"news\"\]\s*=",
        re.DOTALL,
    )
    assert pat.search(block), (
        "News-Attachment ueber enriched-Stream fehlt — Top-10 + "
        "Watchlist-Outsider bekommen news nicht")


# === 3 — Vorsichts-Prinzip ==============================================


def test_get_combined_news_unchanged():
    """Strikt: dieser PR aendert get_combined_news nicht."""
    pat = re.compile(
        r"def get_combined_news\(ticker: str, n: int = 3\) -> list\[dict\]:",
    )
    assert pat.search(SRC), (
        "get_combined_news-Signatur veraendert oder weg")
    # Yahoo + Finviz-Quellen unveraendert
    assert "get_yahoo_news(ticker, n=5)" in SRC
    assert "https://finviz.com/rss.ashx?t=" in SRC


def test_wl_card_payload_news_field_unchanged():
    """_wl_card_payload muss weiterhin news aus _s.get('news', []) ziehen —
    sonst kommt der Fix nicht im watchlist_cards-Dict an."""
    pat = re.compile(
        r"\"news\":\s*\[\s*\{[^}]*\"title\":\s*n\.get\(\"title\", \"\"\)",
        re.DOTALL,
    )
    assert pat.search(SRC), (
        "_wl_card_payload news-Build-Pattern hat sich veraendert — "
        "Watchlist-Karten wuerden die news nicht durchreichen")


# === 4 — Pythonische Replikation ========================================


def _build_news_pool(top10, enriched):
    """Replikat der News-Pool-Logik."""
    pool = {s["ticker"] for s in top10}
    pool |= {c["ticker"] for c in enriched if c.get("manual_personal")}
    return pool


def test_replicate_set_dedup_ticker_in_both_lists():
    """CRMD ist sowohl Top-10 als auch persoenliche Watchlist → einmal
    gefetcht."""
    top10 = [{"ticker": "AAA"}, {"ticker": "CRMD"}]
    enriched = [
        {"ticker": "AAA"},
        {"ticker": "CRMD", "manual_personal": True},
        {"ticker": "BBB", "manual_personal": True},
    ]
    pool = _build_news_pool(top10, enriched)
    assert pool == {"AAA", "CRMD", "BBB"}, (
        f"Erwartet {{AAA, CRMD, BBB}}, got {pool}")


def test_replicate_only_top10_when_no_personal_watchlist():
    """Backward-Compat: ohne manual_personal-Tickers ist der Pool
    identisch zu vor dem Fix (nur Top-10)."""
    top10 = [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}]
    enriched = list(top10)   # alle in Top-10, keiner manual_personal
    pool = _build_news_pool(top10, enriched)
    assert pool == {"AAA", "BBB", "CCC"}


def test_replicate_watchlist_only_ticker_added():
    """CRMD ist nicht in Top-10 aber in enriched mit manual_personal=True
    → muss in den Pool."""
    top10 = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    enriched = [
        {"ticker": "AAA"},
        {"ticker": "BBB"},
        {"ticker": "CRMD", "manual_personal": True},
    ]
    pool = _build_news_pool(top10, enriched)
    assert "CRMD" in pool
    assert pool == {"AAA", "BBB", "CRMD"}


def _attach_news(enriched, news_by_ticker):
    """Replikat der News-Attachment-Logik."""
    for c in enriched:
        t = c.get("ticker")
        if t in news_by_ticker:
            c["news"] = news_by_ticker[t]


def test_replicate_news_attached_to_top10_stock():
    enriched = [{"ticker": "AAA"}, {"ticker": "BBB"}]
    news_by_ticker = {"AAA": [{"title": "headline1"}], "BBB": [{"title": "h2"}]}
    _attach_news(enriched, news_by_ticker)
    assert enriched[0]["news"] == [{"title": "headline1"}]
    assert enriched[1]["news"] == [{"title": "h2"}]


def test_replicate_news_attached_to_watchlist_outsider():
    enriched = [
        {"ticker": "AAA"},
        {"ticker": "CRMD", "manual_personal": True},
    ]
    news_by_ticker = {"CRMD": [{"title": "Earnings beat"}]}
    _attach_news(enriched, news_by_ticker)
    assert enriched[1]["news"] == [{"title": "Earnings beat"}]


def test_replicate_no_news_no_attach():
    """Ticker mit leerem Fetch-Result (Fallback-Pfad) bekommt news=[],
    nicht None. _attach setzt das Field aber auch dann, denn
    news_by_ticker[t] kann [] sein."""
    enriched = [{"ticker": "AAA"}]
    news_by_ticker = {"AAA": []}   # Fetch lief, Result leer
    _attach_news(enriched, news_by_ticker)
    assert enriched[0]["news"] == []   # explizit leer, nicht None


def test_replicate_ticker_not_in_pool_keeps_no_news_field():
    """Ein Stock, der nicht im Pool ist, hat KEIN news-Field — bei
    Render fällt das auf .get('news', []) zurück."""
    enriched = [{"ticker": "AAA"}, {"ticker": "DDD"}]
    news_by_ticker = {"AAA": [{"title": "x"}]}
    _attach_news(enriched, news_by_ticker)
    assert "news" in enriched[0]
    assert "news" not in enriched[1]


# === 5 — Fallback bei echtem leeren Fetch bleibt funktional ============


def test_fallback_no_news_html_path_intact():
    """„Keine Nachrichten verfuegbar"-Fallback im _card-Renderer bleibt
    da — wird gerendert, wenn s.get('news', []) leer ist (z.B. yfinance
    Rate-Limit oder neuer Ticker ohne News)."""
    assert '<p class="no-news">Keine Nachrichten verfügbar.</p>' in SRC, (
        "No-news-Fallback-Markup im Renderer geaendert oder weg")


def test_news_count_log_includes_pool_size():
    """Log-Output dokumentiert Pool-Groesse (Top-10 + Watchlist-Extras
    aufgeschluesselt) — Workflow-Logs zeigen die Erweiterung."""
    block = _news_block()
    assert "Watchlist-Extras" in block, (
        "Log-Output zeigt Watchlist-Extras-Count nicht — Diagnose "
        "bei zukuenftigen Coverage-Bugs schwerer")


# === 6 — JS-Pflichtcheck ================================================


def test_no_unescaped_js_template_vars():
    hits = re.findall(r"\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}", SRC)
    assert not hits, f"Unescapte JS-Template-Vars: {hits[:5]}"


# === Runner =============================================================


def main() -> None:
    tests = [
        # Source-Inspektion
        ("News-Pool = Set-Union top10 ∪ manual_personal", test_news_pool_is_set_union),
        ("Set-Dedup via |=-Operator",                     test_news_pool_uses_set_dedup),
        ("max_workers von 13 → 16",                       test_news_max_workers_increased),
        ("Attachment via _news_by_ticker-Dict",           test_news_attached_via_news_by_ticker_dict),
        ("News attached an enriched-Dicts",               test_news_attached_to_enriched_dicts),
        # Vorsichts-Prinzip
        ("get_combined_news unveraendert",                test_get_combined_news_unchanged),
        ("_wl_card_payload news-Field-Pattern intakt",    test_wl_card_payload_news_field_unchanged),
        # Pythonische Replikation
        ("Set-Dedup: Ticker in beiden Listen → 1x",       test_replicate_set_dedup_ticker_in_both_lists),
        ("Backward-Compat: nur Top-10 ohne personal",     test_replicate_only_top10_when_no_personal_watchlist),
        ("Watchlist-Only-Ticker → Pool",                  test_replicate_watchlist_only_ticker_added),
        ("News attached an Top-10-Stocks",                test_replicate_news_attached_to_top10_stock),
        ("News attached an Watchlist-Outsider",           test_replicate_news_attached_to_watchlist_outsider),
        ("Leerer Fetch → news=[]",                         test_replicate_no_news_no_attach),
        ("Ticker nicht im Pool → kein news-Field",        test_replicate_ticker_not_in_pool_keeps_no_news_field),
        # Fallback
        ("'Keine Nachrichten'-Fallback-Markup intakt",    test_fallback_no_news_html_path_intact),
        ("Log-Output dokumentiert Watchlist-Extras",      test_news_count_log_includes_pool_size),
        # Pflichtcheck
        ("Keine unescapten ${...} im f-String",          test_no_unescaped_js_template_vars),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}\n      {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      Unexpected: {type(exc).__name__}: {exc}")
    print()
    if failed:
        print(f"{failed} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"{len(tests)} Tests bestanden.")
    sys.exit(0)


if __name__ == "__main__":
    main()
