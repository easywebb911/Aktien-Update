"""Mock-Tests für Quellenwechsel Borrow-Rate (01.06.2026):
ehemals IBKR-.php-Scrape (tot, HTTP 404 seit Mai), jetzt iBorrowDesk-JSON.

Pattern: Source-Inspektion (kein Live-HTTP, keine Test-Runtime im Projekt).
Spec aus User-Live-Probe 31.05.2026:
    GET https://iborrowdesk.com/api/ticker/{SYMBOL}
    → {"country", "cusip", "daily": [{"available", "date", "fee",
        "high_fee", "low_fee", "rebate", "high_rebate", "low_rebate"}]}
    fee = annualisierter Prozentsatz (AMC 0.5768 = 0,58 % p.a.)
    daily[-1] = aktuellster Wert (chronologisch aufsteigend)

Verifiziert (Source-Inspektion):
1) Neue Konstante IBORROWDESK_URL_TEMPLATE in config.py.
2) Alte IBKR_BORROW_URL (.php-Scrape) entfernt.
3) _ibkr_borrow_load + _IBKR_BORROW_CACHE entfernt (kein Tabellen-Cache mehr).
4) fetch_ibkr_borrow_rate ruft IBORROWDESK_URL_TEMPLATE.
5) Browser-User-Agent gesetzt (iBorrowDesk blockt nackte UAs).
6) daily[-1]["fee"]-Extraktion.
7) Fail-soft-Branches: RequestException → None, Non-200 → None,
   JSON-Parse-Fehler → None, leere daily-Liste → None, fee=None → None.
8) Funktionsname + Signatur unverändert (alle 3 Aufrufer unberührt).
9) success_check an emit-site (gen._report.py ~15938) verlangt
   cost_to_borrow is not None — Stille-Tod-Härtung.
10) coverage_pct an stockanalysis-record_provider_call gesetzt.

Pythonische Replikation:
11) Spec-konformes JSON → fetch-Logik liefert daily[-1]["fee"].
12) Edge-Cases (leere daily, fehlendes fee, fee=None, daily=None, payload=None).

Ausführung: ``python scripts/mock_test_borrow_iborrowdesk.py``.
Exit 0 bei Erfolg, 1 bei AssertionError.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC_GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
SRC_CONFIG = (ROOT / "config.py").read_text(encoding="utf-8")


# ── 1) Konstanten ──────────────────────────────────────────────────────────


def test_01_url_template_present():
    assert 'IBORROWDESK_URL_TEMPLATE' in SRC_CONFIG, \
        "IBORROWDESK_URL_TEMPLATE-Konstante fehlt in config.py"
    assert 'iborrowdesk.com/api/ticker/{ticker}' in SRC_CONFIG, \
        "iBorrowDesk-URL nicht im erwarteten Format"


def test_02_old_ibkr_php_url_removed():
    # IBKR_BORROW_URL = "...stock-borrow-rates.php" → tot, sollte raus
    assert 'stock-borrow-rates.php' not in SRC_CONFIG, \
        "Alte tote IBKR-.php-URL noch in config.py — sollte entfernt sein"
    # Auch im Code (Aufrufer) — vorher referenzierte _ibkr_borrow_load die URL
    assert 'IBKR_BORROW_URL' not in SRC_GR, \
        "IBKR_BORROW_URL-Referenz noch in generate_report.py — sollte raus"


def test_03_score_thresholds_preserved():
    # Score-Schwellen sind Quelle-unabhängig, MÜSSEN bleiben
    for const in ('IBKR_BORROW_LOW', 'IBKR_BORROW_HIGH',
                  'IBKR_BORROW_BONUS_HOT', 'IBKR_BORROW_BONUS_EXTREME',
                  'IBKR_BORROW_ENABLED', 'IBKR_BORROW_TIMEOUT'):
        assert const in SRC_CONFIG, \
            f"Score-Schwellen-Konstante {const} unerwartet entfernt"


# ── 2) Cache + Loader entfernt ─────────────────────────────────────────────


def test_04_module_cache_removed():
    # _IBKR_BORROW_CACHE war Modul-State für die alte Tabellen-Load-Pattern
    assert '_IBKR_BORROW_CACHE' not in SRC_GR, \
        "Veralteter _IBKR_BORROW_CACHE-Modul-State noch da — entfernen"


def test_05_table_loader_removed():
    assert 'def _ibkr_borrow_load' not in SRC_GR, \
        "Veraltete _ibkr_borrow_load-Funktion noch da — entfernen (kein " \
        "Tabellen-Download mehr bei pro-Ticker-API)"
    # Auch BeautifulSoup-Tabellen-Scrape sollte weg sein
    assert 'soup.find_all("tr")' not in SRC_GR, \
        "Reste des HTML-Tabellen-Scrapes noch da"


# ── 3) Neuer Fetcher ───────────────────────────────────────────────────────


def _fetcher_body() -> str:
    start = SRC_GR.index('def fetch_ibkr_borrow_rate')
    # Bis zur nächsten def auf top-level
    rest = SRC_GR[start + 1:]
    end_offset = rest.index('\ndef ')
    return SRC_GR[start:start + 1 + end_offset]


def test_06_fetcher_signature_unchanged():
    """Funktionsname + Signatur (Aufrufer-Stabilität) bleiben."""
    body = _fetcher_body()
    assert 'def fetch_ibkr_borrow_rate(ticker: str) -> float | None' in body, \
        "Signatur fetch_ibkr_borrow_rate(ticker: str) -> float | None verloren"


def test_07_fetcher_uses_iborrowdesk_url():
    body = _fetcher_body()
    assert 'IBORROWDESK_URL_TEMPLATE.format(ticker=' in body, \
        "Fetcher nutzt nicht IBORROWDESK_URL_TEMPLATE.format(ticker=…)"
    assert '.upper()' in body, "ticker.upper()-Normalisierung fehlt"


def test_08_browser_user_agent_set():
    """iBorrowDesk blockt nackte Script-UAs."""
    body = _fetcher_body()
    assert 'Mozilla/5.0' in body, "Browser-User-Agent fehlt"
    assert 'Chrome/' in body, "Chrome-UA-Marker fehlt"


def test_09_accept_json_header():
    body = _fetcher_body()
    assert 'application/json' in body, "Accept: application/json fehlt"


def test_10_timeout_uses_tuple():
    body = _fetcher_body()
    assert 'IBKR_BORROW_TIMEOUT, IBKR_BORROW_TIMEOUT' in body, \
        "(connect, read)-Timeout-Tupel fehlt"


def test_11_daily_last_fee_extraction():
    body = _fetcher_body()
    assert 'daily[-1]' in body, "daily[-1]-Extraktion nicht erkennbar"
    assert 'latest.get("fee")' in body, \
        "fee-Lookup auf latest-Element fehlt"


def test_12_enabled_flag_respected():
    body = _fetcher_body()
    assert 'IBKR_BORROW_ENABLED' in body, \
        "Enabled-Flag wird nicht gecheckt"
    # Pre-Network-Gate (Flag + leerer ticker)
    assert 'if not IBKR_BORROW_ENABLED or not ticker:' in body, \
        "Pre-Network-Gate fehlt — sollte Flag + leerer ticker abfangen"


# ── 4) Fail-soft-Branches ──────────────────────────────────────────────────


def test_13_request_exception_fail_soft():
    body = _fetcher_body()
    assert 'except requests.RequestException' in body, \
        "RequestException nicht gefangen"
    # Innerhalb des except: return None
    exc_idx = body.index('except requests.RequestException')
    after_exc = body[exc_idx:exc_idx + 300]
    assert 'return None' in after_exc, \
        "RequestException-Branch returnt nicht None"


def test_14_non_200_fail_soft():
    body = _fetcher_body()
    assert 'status_code != 200' in body, \
        "Non-200-Status-Check fehlt"


def test_15_json_parse_fail_soft():
    body = _fetcher_body()
    # entweder ValueError oder json.JSONDecodeError im except
    assert 'ValueError' in body and 'JSONDecodeError' in body, \
        "JSON-Parse-Fehler nicht beide Exception-Typen gefangen"


def test_16_empty_daily_fail_soft():
    body = _fetcher_body()
    assert 'isinstance(daily, list)' in body, \
        "daily-Typ-Check fehlt (sollte list sein)"
    assert 'not daily' in body, "Leere-Liste-Check fehlt"


def test_17_missing_fee_fail_soft():
    body = _fetcher_body()
    assert 'fee is None' in body, "fee=None-Check fehlt"


def test_18_cast_fail_soft():
    body = _fetcher_body()
    assert 'except (TypeError, ValueError)' in body, \
        "float(fee)-Cast-Fehler nicht gefangen"


# ── 5) Stille-Tod-Härtung ──────────────────────────────────────────────────


def test_19_success_check_at_emit_site():
    """gen._report.py ~15938 emit-site: borrow_metrics mit explizitem
    success_check (cost_to_borrow is not None)."""
    # Block um den Aufruf
    idx = SRC_GR.index('fetch_borrow_metrics')
    while True:
        next_idx = SRC_GR.find('fetch_borrow_metrics', idx + 1)
        if next_idx < 0:
            break
        idx = next_idx
        # _instrument_provider_call-Wrapper-Site finden
        block = SRC_GR[max(0, idx - 400):idx + 300]
        if '_instrument_provider_call' in block and '_STOCKANALYSIS_ACCT' in block:
            # success_check muss gesetzt sein (Wrapper-Aufruf streckt sich
            # über mehrere Zeilen → wir prüfen das Block-Fenster)
            block_after = SRC_GR[idx:idx + 400]
            assert 'success_check' in block_after, \
                "success_check am borrow-emit-site fehlt (Stille-Tod-Lücke)"
            assert 'cost_to_borrow' in block_after, \
                "success_check prüft nicht cost_to_borrow"
            assert 'is not None' in block_after, \
                "success_check sollte 'is not None' verlangen, nicht " \
                "Truthiness (None-Float-Wert 0.0 wäre dann fälschlich Fail)"
            return
    assert False, "Borrow-emit-site mit _instrument_provider_call nicht gefunden"


def test_20_coverage_pct_at_stockanalysis_record():
    """record_provider_call(provider='stockanalysis', …) setzt coverage_pct."""
    idx = SRC_GR.index('provider="stockanalysis"')
    block = SRC_GR[max(0, idx - 200):idx + 600]
    assert 'coverage_pct=' in block, \
        "coverage_pct nicht an stockanalysis-record-Site gesetzt"
    # Sollte aus _sa_acct kommen (successes/calls), nicht hardcodiert
    assert '_sa_acct' in block, \
        "coverage_pct sollte aus _sa_acct ableiten"
    assert 'successes' in block and 'calls' in block, \
        "coverage_pct-Berechnung sollte successes/calls referenzieren"


# ── 6) Pythonische Replikation der Parse-Logik ─────────────────────────────


def _replicate_parse(payload) -> float | None:
    """Replikation der fetch_ibkr_borrow_rate-Parse-Logik (ohne HTTP).
    Spec aus User-Live-Probe 31.05."""
    daily = (payload or {}).get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, list) or not daily:
        return None
    latest = daily[-1]
    if not isinstance(latest, dict):
        return None
    fee = latest.get("fee")
    if fee is None:
        return None
    try:
        return round(float(fee), 4)
    except (TypeError, ValueError):
        return None


def test_21_replicate_amc_spec():
    """User-Live-Probe AMC 31.05.: fee=0.5768 = 0,58 % p.a."""
    payload = {
        "country": "USA",
        "cusip": "00165C104",
        "daily": [
            {"available": 350000, "date": "2026-05-30 21:00",
             "fee": 0.62, "high_fee": 0.70, "low_fee": 0.55,
             "rebate": -0.30, "high_rebate": -0.20, "low_rebate": -0.40},
            {"available": 360000, "date": "2026-05-31 21:00",
             "fee": 0.5768, "high_fee": 0.60, "low_fee": 0.50,
             "rebate": -0.28, "high_rebate": -0.18, "low_rebate": -0.38},
        ],
    }
    assert _replicate_parse(payload) == 0.5768


def test_22_replicate_single_day_entry():
    """daily mit nur einem Eintrag — daily[-1] = daily[0]."""
    payload = {"daily": [{"date": "2026-05-31", "fee": 12.34}]}
    assert _replicate_parse(payload) == 12.34


def test_23_replicate_empty_daily():
    assert _replicate_parse({"daily": []}) is None


def test_24_replicate_missing_daily_key():
    assert _replicate_parse({"country": "USA"}) is None


def test_25_replicate_daily_none():
    assert _replicate_parse({"daily": None}) is None


def test_26_replicate_payload_none():
    assert _replicate_parse(None) is None


def test_27_replicate_payload_not_dict():
    """JSON-Payload als List statt Dict (unerwartet, aber fail-soft)."""
    assert _replicate_parse(["unexpected"]) is None


def test_28_replicate_latest_not_dict():
    """daily-Eintrag selbst nicht-Dict (unerwartet, fail-soft)."""
    assert _replicate_parse({"daily": ["string-instead-of-dict"]}) is None


def test_29_replicate_fee_none():
    assert _replicate_parse({"daily": [{"date": "...", "fee": None}]}) is None


def test_30_replicate_fee_missing_key():
    assert _replicate_parse({"daily": [{"date": "..."}]}) is None


def test_31_replicate_fee_not_castable():
    """fee als String, nicht-numerisch."""
    assert _replicate_parse(
        {"daily": [{"date": "...", "fee": "not-a-number"}]}) is None


def test_32_replicate_fee_zero_returns_zero():
    """Wichtig: fee=0.0 IST ein gültiger Wert (kein Bonus, aber kein Fail).
    Edge-Case gegen Truthiness-Bug (0.0 == falsy in Python)."""
    assert _replicate_parse({"daily": [{"fee": 0.0}]}) == 0.0


# ── 7) Option B — eigener _BORROW_ACCT (01.06.2026) ───────────────────────


def test_b1_borrow_acct_declared():
    """Eigener Akkumulator-Slot getrennt von _STOCKANALYSIS_ACCT."""
    assert "_BORROW_ACCT" in SRC_GR, "_BORROW_ACCT-Konstante fehlt"
    # Decl muss Standard-Akku-Struktur haben
    decl_idx = SRC_GR.index("_BORROW_ACCT")
    decl_block = SRC_GR[decl_idx:decl_idx + 300]
    for field in ('"latency_ms"', '"calls"', '"failures"',
                  '"successes"', '"last_error_repr"'):
        assert field in decl_block, \
            f"_BORROW_ACCT-Decl fehlt Feld {field}"


def test_b2_borrow_acct_used_at_borrow_emit_site():
    """borrow-_instrument_provider_call-Site nutzt _BORROW_ACCT,
    NICHT _STOCKANALYSIS_ACCT (sonst Mischung mit SI → Stille-Tod-
    Risiko bei coverage ~50 %).

    Präzise: prüft die EINE Stelle ``_instrument_provider_call(
    _BORROW_ACCT, fetch_borrow_metrics, …)`` und schließt aus, dass
    eine Variante mit _STOCKANALYSIS_ACCT als Akku für
    fetch_borrow_metrics existiert.
    """
    # Positive Erwartung: _instrument_provider_call mit _BORROW_ACCT
    # und fetch_borrow_metrics als Funktions-Argument.
    import re as _re
    positive = _re.search(
        r"_instrument_provider_call\s*\(\s*\n?\s*_BORROW_ACCT\s*,\s*"
        r"fetch_borrow_metrics",
        SRC_GR,
    )
    assert positive, \
        "borrow-emit-site nutzt nicht _BORROW_ACCT als 1. Argument von " \
        "_instrument_provider_call mit fetch_borrow_metrics"
    # Negativ-Check: KEIN Aufruf _instrument_provider_call(_STOCKANALYSIS_ACCT,
    # fetch_borrow_metrics, …) — das wäre die alte gemischte Variante.
    negative = _re.search(
        r"_instrument_provider_call\s*\(\s*\n?\s*_STOCKANALYSIS_ACCT\s*,\s*"
        r"fetch_borrow_metrics",
        SRC_GR,
    )
    assert negative is None, \
        "Alte Variante _instrument_provider_call(_STOCKANALYSIS_ACCT, " \
        "fetch_borrow_metrics, …) existiert noch — Option-B-Trennung " \
        "verletzt"


def test_b3_borrow_acct_reset_at_main_start():
    """main() muss _BORROW_ACCT zurücksetzen (analog _STOCKANALYSIS_ACCT)."""
    assert "_provider_acct_reset(_BORROW_ACCT)" in SRC_GR, \
        "_BORROW_ACCT wird nicht im main()-Reset-Block initialisiert"


def test_b4_borrow_provider_in_tier_map():
    """config.HEALTH_CHECK_PROVIDER_TIER hat einen 'borrow'-Eintrag (Tier 2)."""
    assert '"borrow":' in SRC_CONFIG, \
        "config.HEALTH_CHECK_PROVIDER_TIER hat keinen 'borrow'-Eintrag"
    # Prüfen: Tier-Wert ist 2 (Tier-2: warn-Konsekutiv)
    # Wir suchen den Eintrag im TIER-Block
    tier_block_start = SRC_CONFIG.index("HEALTH_CHECK_PROVIDER_TIER")
    tier_block = SRC_CONFIG[tier_block_start:tier_block_start + 1500]
    # Schmaler Pattern-Check: "borrow": 2
    import re as _re
    m = _re.search(r'"borrow"\s*:\s*(\d)', tier_block)
    assert m and m.group(1) == "2", \
        f"borrow-Tier sollte 2 sein, gefunden: {m.group(1) if m else 'fehlt'}"


def test_b5_borrow_provider_in_expected_map():
    """config.HEALTH_CHECK_PROVIDER_EXPECTED hat 'borrow' (None = variabel)."""
    expected_start = SRC_CONFIG.index("HEALTH_CHECK_PROVIDER_EXPECTED")
    expected_block = SRC_CONFIG[expected_start:expected_start + 1200]
    assert '"borrow"' in expected_block, \
        "HEALTH_CHECK_PROVIDER_EXPECTED fehlt 'borrow'-Eintrag"


def test_b6_record_provider_call_for_borrow():
    """Es gibt einen record_provider_call(provider='borrow', …)-Aufruf
    SEPARAT vom stockanalysis-Eintrag."""
    assert 'provider="borrow"' in SRC_GR, \
        "Kein record_provider_call(provider='borrow') gefunden"
    # Vergewissern: zwei separate record-Aufrufe (stockanalysis + borrow)
    # — NICHT nur einer, der den Namen geändert hat
    assert 'provider="stockanalysis"' in SRC_GR, \
        "stockanalysis-record-Pfad ist verschwunden — SI sollte da bleiben"


def test_b7_borrow_record_uses_borrow_acct_for_coverage():
    """Der borrow-record_provider_call leitet coverage_pct AUS _BORROW_ACCT
    ab (nicht aus _STOCKANALYSIS_ACCT — sonst wäre die Trennung sinnlos)."""
    idx = SRC_GR.index('provider="borrow"')
    block = SRC_GR[max(0, idx - 500):idx + 500]
    assert '_BORROW_ACCT' in block or '_b_acct' in block, \
        "borrow-record-Block referenziert weder _BORROW_ACCT noch _b_acct"
    assert 'coverage_pct=' in block, \
        "borrow-record setzt kein coverage_pct"


def test_b8_si_record_uses_stockanalysis_acct():
    """Gegenprobe: der stockanalysis-record (jetzt SI-only) nutzt
    weiter _STOCKANALYSIS_ACCT."""
    idx = SRC_GR.index('provider="stockanalysis"')
    block = SRC_GR[max(0, idx - 500):idx + 500]
    assert '_STOCKANALYSIS_ACCT' in block or '_sa_acct' in block, \
        "stockanalysis-record nutzt nicht mehr _STOCKANALYSIS_ACCT"


# ── 8) Pythonische Replikation: iBorrowDesk-Tod bei lebendem SI ────────────


def _simulate_coverage(borrow_ok: int, borrow_total: int,
                       si_ok: int, si_total: int):
    """Replikation der Option-B-Trennung:
    - Vorher (gemischter _STOCKANALYSIS_ACCT): coverage_pct = (borrow_ok + si_ok) / (borrow_total + si_total) × 100
    - Nachher (separate _BORROW_ACCT + _STOCKANALYSIS_ACCT):
        borrow-coverage_pct = borrow_ok / borrow_total × 100
        si-coverage_pct     = si_ok / si_total × 100
    Returnt (mixed_pct, borrow_pct, si_pct).
    """
    mixed = round((borrow_ok + si_ok) / max(1, borrow_total + si_total) * 100, 1)
    borrow = round(borrow_ok / max(1, borrow_total) * 100, 1)
    si = round(si_ok / max(1, si_total) * 100, 1)
    return mixed, borrow, si


def test_b9_dead_iborrowdesk_alive_si_yields_zero_coverage_under_split():
    """Stiller iBorrowDesk-Tod bei lebendem SI:
    - Gemischter Akku (alt): coverage_pct = 50 % → knapp UNTER Tier-2-
      Schwelle (50 %, ``DIGEST_COVERAGE_THRESHOLD_TIER23``), kein Alarm
      → genau der Stille-Tod-Bug, den Option B verhindern soll.
    - Getrennte Akkus (neu): borrow-coverage = 0 %, si-coverage = 100 %
      → borrow flaggt sicher als Tier-2-fail, SI bleibt grün.
    """
    mixed, borrow, si = _simulate_coverage(
        borrow_ok=0, borrow_total=10,    # iBorrowDesk tot
        si_ok=10, si_total=10            # SI lebt
    )
    # Vor Option B (gemischter Akku) — knapp unter Schwelle
    assert mixed == 50.0, \
        f"Sanity-Check: gemischter Akku-Coverage 50 % erwartet, ist {mixed}"
    # Nach Option B — sauberer Borrow-fail
    assert borrow == 0.0, \
        f"Getrennter borrow-Akku sollte 0 % zeigen, ist {borrow}"
    assert si == 100.0, \
        f"Getrennter SI-Akku sollte 100 % zeigen, ist {si}"


def test_b10_borrow_threshold_50pct_alarm_boundary():
    """Bei gemischtem Akku liegt 50 % EXAKT auf der Tier-2-Schwelle (50,
    DIGEST_COVERAGE_THRESHOLD_TIER23). cov_fail = cov < threshold →
    50 < 50 ist False, KEIN Alarm. Nach Option-B-Trennung: borrow=0 < 50
    → Alarm sicher."""
    from health_check import DIGEST_COVERAGE_THRESHOLD_TIER23
    mixed, borrow, _ = _simulate_coverage(0, 10, 10, 10)
    assert (mixed < DIGEST_COVERAGE_THRESHOLD_TIER23) is False, \
        "Mixed coverage 50 % UNTER Tier-2-Schwelle (50) erwartet als False" \
        " — sonst Test-Annahme falsch"
    assert (borrow < DIGEST_COVERAGE_THRESHOLD_TIER23) is True, \
        "Getrennter borrow=0 % MUSS unter Tier-2-Schwelle sein"


# ── 9) Aufrufer-Stabilität ─────────────────────────────────────────────────


def test_33_fetch_borrow_metrics_unchanged():
    """fetch_borrow_metrics (Aufrufer) bleibt unverändert in der
    Aufrufreihenfolge: Stockanalysis primär (heute None) → IBKR-Fallback
    (jetzt iBorrowDesk unter der Haube)."""
    idx = SRC_GR.index('def fetch_borrow_metrics')
    rest = SRC_GR[idx + 1:]
    end = rest.index('\ndef ')
    body = SRC_GR[idx:idx + 1 + end]
    assert 'fetch_stockanalysis_borrow(ticker)' in body, \
        "fetch_borrow_metrics ruft fetch_stockanalysis_borrow nicht mehr"
    assert 'fetch_ibkr_borrow_rate(ticker)' in body, \
        "fetch_borrow_metrics ruft fetch_ibkr_borrow_rate nicht mehr"
    # Aufrufreihenfolge: Stockanalysis VOR IBKR (heute irrelevant da
    # Stockanalysis None, aber Architektur bleibt)
    sa_idx = body.index('fetch_stockanalysis_borrow')
    ibkr_idx = body.index('fetch_ibkr_borrow_rate')
    assert sa_idx < ibkr_idx, \
        "Aufrufreihenfolge geändert — sollte stockanalysis → ibkr bleiben"


# ── Runner ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        # Konstanten
        test_01_url_template_present,
        test_02_old_ibkr_php_url_removed,
        test_03_score_thresholds_preserved,
        # Cache/Loader entfernt
        test_04_module_cache_removed,
        test_05_table_loader_removed,
        # Neuer Fetcher
        test_06_fetcher_signature_unchanged,
        test_07_fetcher_uses_iborrowdesk_url,
        test_08_browser_user_agent_set,
        test_09_accept_json_header,
        test_10_timeout_uses_tuple,
        test_11_daily_last_fee_extraction,
        test_12_enabled_flag_respected,
        # Fail-soft
        test_13_request_exception_fail_soft,
        test_14_non_200_fail_soft,
        test_15_json_parse_fail_soft,
        test_16_empty_daily_fail_soft,
        test_17_missing_fee_fail_soft,
        test_18_cast_fail_soft,
        # Stille-Tod-Härtung
        test_19_success_check_at_emit_site,
        test_20_coverage_pct_at_stockanalysis_record,
        # Replikation
        test_21_replicate_amc_spec,
        test_22_replicate_single_day_entry,
        test_23_replicate_empty_daily,
        test_24_replicate_missing_daily_key,
        test_25_replicate_daily_none,
        test_26_replicate_payload_none,
        test_27_replicate_payload_not_dict,
        test_28_replicate_latest_not_dict,
        test_29_replicate_fee_none,
        test_30_replicate_fee_missing_key,
        test_31_replicate_fee_not_castable,
        test_32_replicate_fee_zero_returns_zero,
        # Option B — eigener _BORROW_ACCT
        test_b1_borrow_acct_declared,
        test_b2_borrow_acct_used_at_borrow_emit_site,
        test_b3_borrow_acct_reset_at_main_start,
        test_b4_borrow_provider_in_tier_map,
        test_b5_borrow_provider_in_expected_map,
        test_b6_record_provider_call_for_borrow,
        test_b7_borrow_record_uses_borrow_acct_for_coverage,
        test_b8_si_record_uses_stockanalysis_acct,
        # Stille-Tod-Replikation (Borrow-Tod vs. SI-Lebend)
        test_b9_dead_iborrowdesk_alive_si_yields_zero_coverage_under_split,
        test_b10_borrow_threshold_50pct_alarm_boundary,
        # Aufrufer
        test_33_fetch_borrow_metrics_unchanged,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} Tests bestanden.")
    sys.exit(1 if failed else 0)
