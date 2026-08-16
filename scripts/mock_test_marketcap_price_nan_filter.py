"""Mock-Tests für den Preis-/Market-Cap-K.o.-Filter-Bypass (16.08.2026).

Hintergrund (analog #532/#534/#535): harte Aufnahme-/K.o.-Filter dürfen nie
durch ein NaN umgangen werden — "unbekannt (NaN) muss ausschließen, nicht
durchrutschen" (Reg-SHO/None-Semantik-Prinzip). Zwei konkrete Fundstellen:

  1. ``_add_quotes`` (nested Closure in ``get_yahoo_screener_candidates``,
     generate_report.py): ``price = float(q.get("regularMarketPrice") or 0)``
     ließ eine NaN durch ("or 0" ersetzt nur bei einem falsy Wert, NaN ist
     truthy) — der nachfolgende ``if price < MIN_PRICE: continue`` verliert
     dann JEDEN Vergleich (``nan < X`` ist immer False) und lässt den
     Kandidaten mit einer rohen NaN als Preis durch. ``mkt_cap = q.get(
     "marketCap") or q.get("intradayMarketCap")`` hatte dieselbe Falle: eine
     NaN in ``marketCap`` fällt NICHT auf ``intradayMarketCap`` zurück (NaN
     ist truthy, "or" gewinnt links) — ein legitim über der Cap liegender
     Intraday-Wert wurde dadurch nie geprüft.

  2. Post-Enrichment-Cap-Filter in ``main()`` (~Z. 17930, jetzt als
     eigenständige, testbare Funktion ``_cap_within_limit`` extrahiert):
     dieselbe "or"-Kette speiste ``<= MAX_MARKET_CAP``. Diagnose-Befund
     (Exzellenz-Block Punkt 2 des Auftrags, siehe PR-Body): dieser konkrete
     Vergleich war durch die *positive* Form ("keep if <= limit" statt
     "skip if > limit") zufällig bereits NaN-sicher — ``nan <= limit`` ist
     False, der Kandidat fiel also schon vorher korrekt raus. Trotzdem
     explizit auf ``_finite()`` umgestellt (kein Verlass auf Vergleichs-
     Zufall, Lehre aus der 27.07.2026-NaN-Dichtigkeit-Regel in CLAUDE.md).

  3. Zusätzlich entdeckter, ECHT verwundbarer Zwilling im selben
     main()-Enrichment-Loop (~Z. 17894, per-Kandidat-Schleife VOR dem
     Post-Enrichment-Filter): ``cap = c.get("yf_market_cap") or c.get(
     "market_cap")`` gefolgt von ``if cap and cap > MAX_MARKET_CAP:
     continue`` — negierte Form, also die ECHTE Bypass-Variante (NaN ist
     truthy UND verliert den ">"-Vergleich). War NICHT explizit im Auftrag
     benannt, aber im selben Enrichment-Loop entdeckt und mitgefixt. Dieser
     Block ist strukturell in main() eingebettet (kein Top-Level-def, keine
     einfache Extraktion ohne main()'s komplette Fixture-Kette) — hier daher
     NUR Quelltext-Deckung (kein Behaviour-Test), transparent so benannt.

Test-Standard (Lehre aus #535): NICHT nur Logik-Repliken. Test A treibt die
ECHTE ``get_yahoo_screener_candidates()`` (inkl. der darin verschachtelten
``_add_quotes``) über einen monkeygepatchten ``_fetch_yf_screener`` an — der
Bypass wird durch den tatsächlichen Kandidaten-Ausschluss bewiesen, nicht
durch eine Nachbildung. Test B ruft die echte, jetzt modul-globale
``_cap_within_limit()`` direkt auf (kein Extraktions-Hack nötig, da
Top-Level-Funktion).

Ausführung: ``python scripts/mock_test_marketcap_price_nan_filter.py``.
"""
from __future__ import annotations

import math
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")


# ── Heavy-Dependency-Stubs (identisch zu mock_test_outer_page_golden.py) ────
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
        dt.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
            translate=lambda s: s)
        sys.modules["deep_translator"] = dt
    if "watchlist" not in sys.modules:
        wl = types.ModuleType("watchlist")
        wl.WATCHLIST = []
        sys.modules["watchlist"] = wl


_install_stubs()
import generate_report as gr  # noqa: E402


# === A — _add_quotes (via echtem get_yahoo_screener_candidates) ============

FAKE_QUOTES = [
    # NaN-Preis: alte Falle liess ihn durch (NaN < MIN_PRICE ist False).
    {"symbol": "NANPRICE", "regularMarketPrice": float("nan"), "marketCap": 1e9,
     "regularMarketChangePercent": 2.0, "shortPercentOfFloat": 0.12,
     "shortRatio": 3.0, "shortName": "NaN Price Co", "sector": "Technology"},
    # NaN in marketCap, aber intradayMarketCap liegt klar über der Cap (2 Mrd.
    # $, config.MAX_MARKET_CAP) — alte "or"-Kette hat NIE auf den Fallback
    # geprüft, weil NaN truthy ist und links gewinnt.
    {"symbol": "NANCAPBYPASS", "regularMarketPrice": 5.0, "marketCap": float("nan"),
     "intradayMarketCap": 5_000_000_000.0,
     "regularMarketChangePercent": 1.5, "shortPercentOfFloat": 0.20,
     "shortRatio": 4.0, "shortName": "NaN Cap Bypass Co", "sector": "Industrials"},
    # Beide Cap-Felder NaN — echt unbekannt, keine der beiden Quellen nutzbar.
    # Bestehende Regel (unverändert durch diesen Fix): unbekannter Cap wird
    # HIER noch nicht abgelehnt (kein Fallback-Wert existiert), aber auch
    # nicht als NaN ins Kandidaten-Dict geschrieben.
    {"symbol": "NANCAPUNKNOWN", "regularMarketPrice": 5.0, "marketCap": float("nan"),
     "intradayMarketCap": float("nan"),
     "regularMarketChangePercent": 0.5, "shortPercentOfFloat": 0.18,
     "shortRatio": 2.5, "shortName": "NaN Cap Unknown Co", "sector": "Healthcare"},
    # Regressions-Kontrolle: vollstaendig valide Daten bleiben unveraendert.
    {"symbol": "VALIDOK", "regularMarketPrice": 3.5, "marketCap": 1_000_000_000.0,
     "regularMarketChangePercent": 4.0, "shortPercentOfFloat": 0.30,
     "shortRatio": 5.0, "shortName": "Valid Co", "sector": "Energy"},
]


def _run_real_screener_with_fake_quotes():
    """Ruft die ECHTE get_yahoo_screener_candidates() (inkl. der darin
    verschachtelten _add_quotes) auf; nur der Netzwerk-Fetch wird gestubbt."""
    orig_screeners = gr._YF_SCREENERS
    orig_fetch = gr._fetch_yf_screener
    gr._YF_SCREENERS = {"US": ["fake_screener"]}
    gr._fetch_yf_screener = lambda screener_id, region: FAKE_QUOTES
    try:
        return gr.get_yahoo_screener_candidates()
    finally:
        gr._YF_SCREENERS = orig_screeners
        gr._fetch_yf_screener = orig_fetch


def test_add_quotes_nan_price_excludes_candidate():
    candidates = _run_real_screener_with_fake_quotes()
    tickers = {c["ticker"] for c in candidates}
    assert "NANPRICE" not in tickers, (
        f"NaN-Preis muss den Preis-Filter NICHT umgehen — Kandidat war in "
        f"der Ergebnisliste: {sorted(tickers)}")


def test_add_quotes_nan_marketcap_falls_back_and_rejects_over_cap():
    candidates = _run_real_screener_with_fake_quotes()
    tickers = {c["ticker"] for c in candidates}
    assert "NANCAPBYPASS" not in tickers, (
        f"NaN in marketCap mit über-Cap-intradayMarketCap-Fallback muss "
        f"ausgeschlossen werden — Kandidat war in der Ergebnisliste: "
        f"{sorted(tickers)}")


def test_add_quotes_both_cap_fields_nan_is_unknown_not_rejected():
    """Bestehende Regel unverändert: ein Kandidat OHNE jede nutzbare
    Cap-Quelle wird hier nicht blockiert (Filter-Zuständigkeit liegt beim
    Post-Enrichment-Filter mit vollständigeren Daten)."""
    candidates = _run_real_screener_with_fake_quotes()
    by_ticker = {c["ticker"]: c for c in candidates}
    assert "NANCAPUNKNOWN" in by_ticker, (
        "Ein Kandidat mit komplett unbekanntem Cap darf hier nicht "
        "abgelehnt werden (bestehende Sonderregel)")


def test_add_quotes_no_silent_nan_or_fake_value_in_dict():
    """Gegenprobe: kein stiller Ersatzwert. market_cap wird bei unbekanntem
    Cap zu None, NIEMALS zu NaN oder einer erfundenen Zahl."""
    candidates = _run_real_screener_with_fake_quotes()
    by_ticker = {c["ticker"]: c for c in candidates}
    mc = by_ticker["NANCAPUNKNOWN"]["market_cap"]
    assert mc is None, f"Erwarte None (kein stiller Ersatzwert), bekam {mc!r}"


def test_add_quotes_valid_regression_unchanged():
    candidates = _run_real_screener_with_fake_quotes()
    by_ticker = {c["ticker"]: c for c in candidates}
    assert "VALIDOK" in by_ticker
    valid = by_ticker["VALIDOK"]
    assert valid["price"] == 3.5
    assert valid["market_cap"] == 1_000_000_000.0


def test_add_quotes_source_no_longer_has_or_zero_price_gotcha():
    """Quelltext-Deckung: die alte 'or 0'-Falle ist raus."""
    assert 'float(q.get("regularMarketPrice") or 0)' not in src_gr
    assert 'q.get("marketCap") or q.get("intradayMarketCap")' not in src_gr


def test_add_quotes_source_uses_finite_guard():
    seg = src_gr[src_gr.find("def _add_quotes("):
                  src_gr.find("tasks = [(region, sid)")]
    assert seg, "generate_report.py-Struktur verändert — Segment-Suche angepasst?"
    assert "_finite(_price_raw)" in seg
    assert "_finite(_mkt_cap_raw)" in seg


# === B — Post-Enrichment-Cap-Filter (_cap_within_limit, main() ~Z. 17930) ===

def test_cap_within_limit_nan_primary_falls_back_and_rejects_over_cap():
    c = {"yf_market_cap": float("nan"), "market_cap": 5e9}
    assert gr._cap_within_limit(c) is False, (
        "NaN in yf_market_cap muss auf market_cap zurückfallen; 5 Mrd. $ "
        "liegt über MAX_MARKET_CAP -> Kandidat muss ausgeschlossen werden")


def test_cap_within_limit_both_nan_is_unknown_not_rejected():
    c = {"yf_market_cap": float("nan"), "market_cap": float("nan")}
    assert gr._cap_within_limit(c) is True, (
        "Komplett unbekannter Cap ist bestehende Sonderregel — kein Reject")


def test_cap_within_limit_manual_personal_exempt_even_with_nan():
    c = {"yf_market_cap": float("nan"), "market_cap": 5e9, "manual_personal": True}
    assert gr._cap_within_limit(c) is True, (
        "manual_personal-Ausnahme muss auch bei NaN-Cap greifen")


def test_cap_within_limit_valid_under_cap_kept():
    assert gr._cap_within_limit({"yf_market_cap": 1e9}) is True


def test_cap_within_limit_valid_over_cap_rejected():
    assert gr._cap_within_limit({"yf_market_cap": 5e9}) is False


def test_cap_within_limit_end_to_end_list_filter():
    """Treibt exakt die Ziel-Mechanik aus main(): 'enriched = [c for c in
    enriched if _cap_within_limit(c)]' — echte Funktion, echte Liste."""
    enriched = [
        {"ticker": "NANOVER", "yf_market_cap": float("nan"), "market_cap": 5e9},
        {"ticker": "OK1",     "yf_market_cap": 1e9},
        {"ticker": "UNKNOWN", "yf_market_cap": float("nan"), "market_cap": float("nan")},
    ]
    filtered = [c for c in enriched if gr._cap_within_limit(c)]
    tickers = {c["ticker"] for c in filtered}
    assert tickers == {"OK1", "UNKNOWN"}, (
        f"NANOVER muss (via Fallback) ausgeschlossen sein, OK1 und UNKNOWN "
        f"müssen erhalten bleiben — bekam {tickers}")


def test_cap_within_limit_wired_into_main():
    """Quelltext-Deckung: main() nutzt tatsächlich _cap_within_limit für
    den Post-Enrichment-Filter (kein toter Code, kein Divergenz-Risiko)."""
    assert "enriched = [c for c in enriched if _cap_within_limit(c)]" in src_gr


# === D — wl_top10_json-Sanitize (squeeze-guardian-Finding 1, 16.08.2026) ===
#
# _wl_card_payload liest market_cap u.a. aus '_s.get("yf_market_cap") or
# _s.get("market_cap") or 0' (Zeile ~2650, bewusst unverändert — reine
# Export-Quelle, siehe PR-Body). Der Guardian-Lauf fand: der JSON-Dump für
# das in die Seite eingebettete WL_TOP10 (const WL_TOP10 = {...};) sanitized
# NICHT (im Gegensatz zu _write_app_data_json, das denselben Payload-Typ
# über _sanitize_for_json schickt) — eine rohe NaN würde als literales
# JS-NaN-Identifier in die Seite eingebettet (kein Parse-Crash, aber ein
# stiller Wert-Defekt in WL_TOP10[ticker].market_cap). Noch in diesem PR
# nachgezogen (json.dumps(_sanitize_for_json(_wl_top10), ...)).

def test_sanitize_for_json_replaces_nan_and_inf_with_none():
    payload = {
        "AAAA": {"market_cap": float("nan"), "price": 5.0,
                  "nested": {"x": float("inf"), "y": -float("inf")},
                  "lst": [1.0, float("nan"), "text", True]},
    }
    out = gr._sanitize_for_json(payload)
    assert out["AAAA"]["market_cap"] is None
    assert out["AAAA"]["price"] == 5.0
    assert out["AAAA"]["nested"]["x"] is None
    assert out["AAAA"]["nested"]["y"] is None
    assert out["AAAA"]["lst"] == [1.0, None, "text", True]


def test_wl_top10_json_source_uses_sanitize_for_json():
    """Quelltext-Deckung: der in die Seite eingebettete WL_TOP10-Dump läuft
    jetzt durch denselben Sanitizer wie app_data.json (_write_app_data_json)."""
    assert 'wl_top10_json = json.dumps(_sanitize_for_json(_wl_top10), default=str)' in src_gr


# === C — Zwilling im Per-Kandidat-Enrichment-Loop (~Z. 17894) ==============
#
# Struktur-Grund für reine Quelltext-Deckung statt Verhaltens-Test: dieser
# Block sitzt eingebettet in main() (kein Top-Level-def, keine Closure mit
# nur 3 einfachen Container-Variablen wie bei _add_quotes) — eine
# Verhaltens-Extraktion würde main()'s komplette Fixture-Kette (batch-Daten,
# Score-Pipeline, Dutzende globale Zwischenstände) nachbauen. Transparent
# als schwächere, aber ehrliche Coverage-Form benannt (Exzellenz-Block
# Punkt 3 des Auftrags).

def test_main_loop_cap_check_source_no_longer_has_negated_or_gotcha():
    assert 'cap = c.get("yf_market_cap") or c.get("market_cap")' not in src_gr


def test_main_loop_cap_check_source_uses_finite_guard():
    seg = src_gr[src_gr.find("# Hard filters — manual_personal-Ticker"):
                  src_gr.find("# Short-float filter: strict for US")]
    assert seg, "generate_report.py-Struktur verändert — Segment-Suche angepasst?"
    assert 'cap = c.get("yf_market_cap")' in seg
    assert "if not _finite(cap):" in seg
    assert 'cap = c.get("market_cap")' in seg
    assert "cap = cap if _finite(cap) else None" in seg
    assert "if cap is not None and cap > MAX_MARKET_CAP:" in seg


def main() -> None:
    tests = [
        # A — _add_quotes (echte get_yahoo_screener_candidates())
        ("add_quotes: NaN-Preis -> ausgeschlossen",
         test_add_quotes_nan_price_excludes_candidate),
        ("add_quotes: NaN-marketCap + über-Cap-Fallback -> ausgeschlossen",
         test_add_quotes_nan_marketcap_falls_back_and_rejects_over_cap),
        ("add_quotes: beide Cap-Felder NaN -> nicht abgelehnt (bestehend)",
         test_add_quotes_both_cap_fields_nan_is_unknown_not_rejected),
        ("add_quotes: kein stiller NaN/Fake-Wert im Dict",
         test_add_quotes_no_silent_nan_or_fake_value_in_dict),
        ("add_quotes: valider Kandidat unverändert (Regression)",
         test_add_quotes_valid_regression_unchanged),
        ("Quelltext: 'or 0'-Preis-Falle entfernt",
         test_add_quotes_source_no_longer_has_or_zero_price_gotcha),
        ("Quelltext: _add_quotes nutzt _finite()-Guard",
         test_add_quotes_source_uses_finite_guard),
        # B — _cap_within_limit (Post-Enrichment-Filter, main() ~Z. 17930)
        ("cap_within_limit: NaN primär -> Fallback -> über Cap -> reject",
         test_cap_within_limit_nan_primary_falls_back_and_rejects_over_cap),
        ("cap_within_limit: beide NaN -> unbekannt, kein Reject",
         test_cap_within_limit_both_nan_is_unknown_not_rejected),
        ("cap_within_limit: manual_personal-Ausnahme greift trotz NaN",
         test_cap_within_limit_manual_personal_exempt_even_with_nan),
        ("cap_within_limit: valide unter Cap -> keep",
         test_cap_within_limit_valid_under_cap_kept),
        ("cap_within_limit: valide über Cap -> reject",
         test_cap_within_limit_valid_over_cap_rejected),
        ("cap_within_limit: End-to-End Listen-Filter (echte Ziel-Mechanik)",
         test_cap_within_limit_end_to_end_list_filter),
        ("Quelltext: main() nutzt _cap_within_limit (kein toter Code)",
         test_cap_within_limit_wired_into_main),
        # C — Zwilling im Per-Kandidat-Loop (Quelltext-Deckung)
        ("Quelltext: main()-Loop-Cap-Check ohne negierte or-Falle",
         test_main_loop_cap_check_source_no_longer_has_negated_or_gotcha),
        ("Quelltext: main()-Loop-Cap-Check nutzt _finite()-Guard",
         test_main_loop_cap_check_source_uses_finite_guard),
        # D — wl_top10_json-Sanitize (Guardian-Finding 1)
        ("sanitize_for_json: NaN/Inf -> None, Rest unverändert",
         test_sanitize_for_json_replaces_nan_and_inf_with_none),
        ("Quelltext: wl_top10_json nutzt _sanitize_for_json",
         test_wl_top10_json_source_uses_sanitize_for_json),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # pragma: no cover
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    print()
    if failed:
        print(f"{failed} von {len(tests)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {len(tests)} Tests bestanden.")


if __name__ == "__main__":
    main()
