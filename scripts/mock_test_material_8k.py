"""Mock-Tests für ``material_8k`` (§6c FDA-/materielle-8-K-Sammelfeld).

FIXTURE-ONLY — kein Netzwerk, kein Kontakt mit ``backtest_history.json`` oder
SEC-EDGAR. Alle I/O über injizierte Fakes. Stdlib-only (kein requests/yfinance
beim Import → CI-ALLOWLIST-tauglich).

Verifiziert:
- (A) CIK-Auflösung: eindeutig → CIK10; mehrdeutig (2 CIKs) → None;
      unbekannt → None (fail-soft, kein Ticker-Match auf Filings).
- (B) Point-in-time-Fenster: NUR 8-K mit acceptance <= now UND >= now-lookback;
      Nicht-8-K-Forms raus; qualifizierende item_codes-Filter; Sortierung asc.
- (C) Look-ahead-Ausschluss: 8-K mit acceptance NACH now_utc wird verworfen.
- (D) Cap N + truncated-Flag: > N qualifizierende → erste N + truncated=True.
- (E) matched_terms aus dem EXHIBIT (nicht nur Mantel): EX-99-Doc-Auswahl +
      case-insensitive Term-Scan, stabile Reihenfolge.
- (F) End-to-end collect_for_ticker / collect_material_8k_events mit Fakes:
      FDA-Ticker → matched_term; Non-Pharma → 8-K da, matched_terms leer;
      no_cik / fetch_failed fail-soft; Determinismus (2 Läufe identisch).
- (G) Wrapper-Schema + S10-Disziplin: material_8k_events in S10_OBSERVED_FIELDS,
      NICHT in MUSS/LAG; Schema bleibt v4; Feld im _build_backtest_extension-
      Return; Sammlung mit now_utc=_now_dt (Report-Zeit) verdrahtet.
- (H) Kein Score-/Filter-/Push-Read (Look-Ahead-Isolation): der Feld-Key und
      der Collector erscheinen in keinem Score-Pfad (generate_report/ki_agent/
      health_check).
- (I) Kein Top-Level-``requests``-Import (Lazy-I/O → Import bleibt stdlib-only).
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config           # noqa: E402
import material_8k as m  # noqa: E402

_fails: list[str] = []


def _check(name, cond, msg=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {msg}")
        _fails.append(name)


NOW = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)
QUAL = ("1.01", "2.02", "5.02", "7.01", "8.01")
CORE = ("Complete Response Letter", "PDUFA", "received FDA approval")


def _submissions(rows):
    """rows: list of (form, items, acceptance, accession, primary)."""
    return {"filings": {"recent": {
        "form": [r[0] for r in rows],
        "items": [r[1] for r in rows],
        "acceptanceDateTime": [r[2] for r in rows],
        "accessionNumber": [r[3] for r in rows],
        "primaryDocument": [r[4] for r in rows],
    }}}


# ── (A) CIK-Auflösung ─────────────────────────────────────────────────────────
def test_cik():
    ct = {"0": {"cik_str": 1815776, "ticker": "LENZ", "title": "LENZ"},
          "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
          "2": {"cik_str": 111, "ticker": "DUP", "title": "A"},
          "3": {"cik_str": 222, "ticker": "DUP", "title": "B"}}
    idx = m.build_cik_index(ct)
    _check("A1 eindeutige CIK zero-padded",
           m.resolve_cik("LENZ", idx) == "0001815776",
           m.resolve_cik("LENZ", idx))
    _check("A2 lower/space-tolerant", m.resolve_cik("  lenz ", idx) == "0001815776")
    _check("A3 mehrdeutig (2 CIKs) → None", m.resolve_cik("DUP", idx) is None)
    _check("A4 unbekannt → None", m.resolve_cik("ZZZZ", idx) is None)
    _check("A5 kaputter Input → leerer Index",
           m.build_cik_index(None) == {} and m.build_cik_index([1, 2]) == {})


# ── (B)+(C) Fenster + Look-ahead ──────────────────────────────────────────────
def test_window():
    rows = [
        # in Fenster, qualifizierend (7.01)
        ("8-K", "7.01,9.01", "2025-11-05T16:05:00.000Z", "a-1", "d1.htm"),
        # qualifizierend, aber acceptance NACH now → look-ahead, raus
        ("8-K", "8.01", "2025-11-06T12:00:00.000Z", "a-2", "d2.htm"),
        # nur 9.01 (Exhibit-Träger, KEIN Standalone-Qualifier) → raus
        ("8-K", "9.01", "2025-11-05T10:00:00.000Z", "a-3", "d3.htm"),
        # nur administrativ 5.03 → raus
        ("8-K", "5.03", "2025-11-05T11:00:00.000Z", "a-4", "d4.htm"),
        # 10-Q (kein 8-K) → raus
        ("10-Q", "", "2025-11-05T09:00:00.000Z", "a-5", "d5.htm"),
        # qualifizierend (2.02) aber vor Fenster (> 5 Tage) → raus
        ("2.02 falsch als form?", "2.02", "2025-10-01T12:00:00.000Z", "a-6", "d6.htm"),
        # qualifizierend (8.01), früher im Fenster → soll VOR a-1 sortiert sein
        ("8-K", "8.01,9.01", "2025-11-04T20:00:00.000Z", "a-7", "d7.htm"),
        # 8-K/A Amendment, qualifizierend → zählt
        ("8-K/A", "2.02", "2025-11-05T08:00:00.000Z", "a-8", "d8.htm"),
    ]
    ev = m.select_windowed_8k(_submissions(rows), now_utc=NOW, lookback_days=5,
                              qualifying_items=QUAL, cik="0001815776")
    accs = [e["accession"] for e in ev]
    _check("B1 nur qualifizierende 8-K im Fenster",
           accs == ["a-7", "a-8", "a-1"], accs)
    _check("C1 look-ahead (acceptance>now) ausgeschlossen", "a-2" not in accs)
    _check("B2 9.01-only ausgeschlossen (kein Standalone-Qualifier)", "a-3" not in accs)
    _check("B3 administrativ 5.03 ausgeschlossen", "a-4" not in accs)
    _check("B4 out-of-window (>lookback) ausgeschlossen", "a-6" not in accs)
    _check("B5 item_codes geparst", ev[2]["item_codes"] == ["7.01", "9.01"], ev[2]["item_codes"])
    _check("B6 8-K/A Amendment zählt", "a-8" in accs)
    _check("B7 aufsteigend nach acceptance sortiert",
           ev[0]["acceptance_datetime"] < ev[-1]["acceptance_datetime"])
    _check("B8 kein internes _sort_dt/_primary_document leakt in Roh-Event",
           all("_sort_dt" not in e for e in ev))


# ── (D) Cap + truncated ───────────────────────────────────────────────────────
def test_cap():
    rows = [("8-K", "8.01", f"2025-11-05T0{i}:00:00.000Z", f"c-{i}", f"d{i}.htm")
            for i in range(9)]  # 9 qualifizierende > cap 8
    wrap = m.collect_for_ticker(
        "X", now_utc=NOW, cik_index={"X": {"0000000001"}}, ua="ua", timeout=5,
        lookback_days=5, qualifying_items=QUAL, core_terms=CORE, cap_n=8,
        max_docs=3, get_json=lambda u, a, t: _submissions(rows) if "submissions" in u else None,
        get_text=lambda u, a, t: None, deadline=None, sleep_s=0)
    _check("D1 > cap → truncated=True", wrap["truncated"] is True)
    _check("D2 genau N=8 Events behalten", len(wrap["events"]) == 8, len(wrap["events"]))
    _check("D3 erste N nach acceptance (früheste behalten)",
           wrap["events"][0]["accession"] == "c-0")


# ── (E) Doc-Auswahl + Term-Scan ──────────────────────────────────────────────
def test_docs_and_terms():
    idx = {"directory": {"item": [
        {"name": "prim8k.htm", "type": "8-K"},
        {"name": "ex991.htm", "type": "EX-99.1"},
        {"name": "ex11.htm", "type": "EX-10.1"},
        {"name": "img.jpg", "type": "GRAPHIC"},
    ]}}
    docs = m.select_scan_docs(idx, "prim8k.htm", max_docs=3)
    _check("E1 primary + EX-99 gewählt, Nicht-Text/Nicht-99 raus",
           docs == ["prim8k.htm", "ex991.htm"], docs)
    _check("E2 max_docs begrenzt",
           len(m.select_scan_docs(idx, "prim8k.htm", max_docs=1)) == 1)
    _check("E3 Term-Scan case-insensitive + stabile Reihenfolge",
           m.scan_terms_in_text("we RECEIVED fda APPROVAL and got a pdufa date",
                                CORE) == ["PDUFA", "received FDA approval"])
    _check("E4 kein Match → leer", m.scan_terms_in_text("nothing here", CORE) == [])
    _check("E5 None-Text → leer", m.scan_terms_in_text(None, CORE) == [])


# ── (F) End-to-end + fail-soft + Determinismus ───────────────────────────────
def test_end_to_end():
    ct = {"0": {"cik_str": 1815776, "ticker": "LENZ", "title": "LENZ"},
          "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
    sub_lenz = _submissions([("8-K", "7.01,9.01", "2025-11-05T16:05:00.000Z",
                              "0001-25-1", "d1.htm")])
    sub_aapl = _submissions([("8-K", "2.02,9.01", "2025-11-04T21:00:00.000Z",
                              "0002-25-1", "a1.htm")])
    idx_json = {"directory": {"item": [
        {"name": "d1.htm", "type": "8-K"},
        {"name": "ex991.htm", "type": "EX-99.1"}]}}

    def gj(url, ua, t):
        if "company_tickers" in url:
            return ct
        if "CIK0001815776" in url:
            return sub_lenz
        if "CIK0000320193" in url:
            return sub_aapl
        if "index.json" in url:
            return idx_json
        return None

    def gt(url, ua, t):
        # Doc-URL trägt die DASH-freie Accession + int(cik) im Pfad
        # (…/edgar/data/1815776/…/ex991.htm) — nur LENZ (CIK 1815776)
        # bekommt den FDA-Exhibit-Text.
        if "ex991.htm" in url and "/1815776/" in url:
            return "Company announced it received FDA approval for aceclidine."
        return "cover page only, no catalyst text"

    res = m.collect_material_8k_events(
        ["LENZ", "AAPL", "ZZZZ"], now_utc=NOW, get_json=gj, get_text=gt,
        sleep_s=0, qualifying_items=QUAL, core_terms=CORE)
    _check("F1 FDA-Ticker collected + matched_term aus Exhibit",
           res["LENZ"]["collected"] and
           res["LENZ"]["events"][0]["matched_terms"] == ["received FDA approval"],
           res["LENZ"])
    _check("F2 FDA-Event trägt cik + item_codes roh",
           res["LENZ"]["events"][0]["cik"] == "0001815776" and
           res["LENZ"]["events"][0]["item_codes"] == ["7.01", "9.01"])
    _check("F3 Non-Pharma: 8-K da, matched_terms LEER (kein FDA-Fehlmatch)",
           res["AAPL"]["collected"] and len(res["AAPL"]["events"]) == 1 and
           res["AAPL"]["events"][0]["matched_terms"] == [], res["AAPL"])
    _check("F4 unbekannter Ticker → no_cik fail-soft",
           res["ZZZZ"]["collected"] is False and res["ZZZZ"]["reason"] == "no_cik")

    # fetch_failed: submissions liefert None
    def gj_fail(url, ua, t):
        return ct if "company_tickers" in url else None
    res2 = m.collect_material_8k_events(["LENZ"], now_utc=NOW, get_json=gj_fail,
                                        get_text=lambda *a: None, sleep_s=0)
    _check("F5 submissions None → fetch_failed fail-soft",
           res2["LENZ"]["collected"] is False and
           res2["LENZ"]["reason"] == "fetch_failed")

    # company_tickers None → alle fetch_failed
    res3 = m.collect_material_8k_events(["LENZ"], now_utc=NOW,
                                        get_json=lambda *a: None,
                                        get_text=lambda *a: None, sleep_s=0)
    _check("F6 company_tickers None → alle fetch_failed",
           res3["LENZ"]["reason"] == "fetch_failed")

    # Determinismus: gleicher now + gleiche Fakes → identisch
    r_a = m.collect_material_8k_events(["LENZ"], now_utc=NOW, get_json=gj,
                                       get_text=gt, sleep_s=0, core_terms=CORE)
    r_b = m.collect_material_8k_events(["LENZ"], now_utc=NOW, get_json=gj,
                                       get_text=gt, sleep_s=0, core_terms=CORE)
    _check("F7 Determinismus (gleicher Report-Zeitpunkt+Daten → gleich)",
           r_a == r_b)

    _check("F8 leere Ticker-Liste → leeres Dict",
           m.collect_material_8k_events([], now_utc=NOW) == {})

    # F9: HARTER Gesamt-Cap am Ticker-Loop-Kopf (Guardian-Fix). Deterministisch
    # via injizierter monotonic-Uhr: erster Call (deadline-Berechnung) = 0,
    # danach 100 → Budget (1 s) sofort überschritten → alle Ticker budget_skip,
    # KEIN collect_for_ticker gestartet.
    seq = iter([0.0] + [100.0] * 50)
    orig_mono = m.time.monotonic
    m.time.monotonic = lambda: next(seq)
    try:
        res_b = m.collect_material_8k_events(
            ["LENZ", "AAPL"], now_utc=NOW, get_json=gj, get_text=gt,
            run_budget_s=1.0, sleep_s=0, core_terms=CORE)
    finally:
        m.time.monotonic = orig_mono
    _check("F9 Gesamt-Budget erschöpft → alle Ticker budget_skip (kein Stau)",
           all(res_b[t]["reason"] == "budget_skip" and res_b[t]["events"] == []
               for t in ("LENZ", "AAPL")), res_b)


# ── (G) Wrapper-Schema + S10-Disziplin ───────────────────────────────────────
def test_s10_and_schema():
    _check("G1 material_8k_events in S10_OBSERVED_FIELDS",
           "material_8k_events" in config.S10_OBSERVED_FIELDS)
    _check("G2 NICHT in S10_MUSS_FIELDS", "material_8k_events" not in config.S10_MUSS_FIELDS)
    _check("G3 NICHT in S10_LAG_FIELDS", "material_8k_events" not in config.S10_LAG_FIELDS)
    src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("G4 Feld im _build_backtest_extension-Return",
           '"material_8k_events":' in src)
    _check("G5 Schema bleibt v4 (kein v5-Bump)",
           '"backtest_schema_version": 4' in src and
           '"backtest_schema_version": 5' not in src)
    _check("G6 Sammlung mit now_utc=_now_dt (Report-Zeit) verdrahtet",
           "collect_material_8k_events(_m8k_tickers, now_utc=_now_dt)"
           in re.sub(r"\s+", " ", src).replace("\\", ""))
    _check("G7 config-Konstanten vorhanden",
           config.MATERIAL_8K_CAP_N == 8 and
           config.MATERIAL_8K_QUALIFYING_ITEMS == ("1.01", "2.02", "5.02", "7.01", "8.01") and
           config.MATERIAL_8K_CORE_TERMS == ("Complete Response Letter", "PDUFA", "received FDA approval"))


# ── (H) Look-Ahead-Isolation: kein Score-/Filter-/Push-Read ──────────────────
def test_look_ahead_isolation():
    for fn in ("generate_report.py", "ki_agent.py", "health_check.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        _check(f"H1 kein 'material_8k_events'-Literal in {fn}",
               "material_8k_events" not in src, fn)
        _check(f"H2 kein collect_material_8k_events-Call in {fn}",
               "collect_material_8k_events" not in src, fn)
    # Collector-Import ausschließlich in backtest_history (Persistenz-Pfad).
    bh = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check("H3 material_8k nur in backtest_history importiert",
           "import material_8k" in bh)


# ── (I) Kein Top-Level requests-Import ───────────────────────────────────────
def test_no_toplevel_requests():
    tree = ast.parse((ROOT / "material_8k.py").read_text(encoding="utf-8"))
    toplevel_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            toplevel_imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            toplevel_imports.append(node.module or "")
    _check("I1 kein Top-Level 'requests' (Lazy-I/O)",
           "requests" not in toplevel_imports, toplevel_imports)
    _check("I2 kein Top-Level 'yfinance'", "yfinance" not in toplevel_imports)


def main():
    test_cik()
    test_window()
    test_cap()
    test_docs_and_terms()
    test_end_to_end()
    test_s10_and_schema()
    test_look_ahead_isolation()
    test_no_toplevel_requests()
    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print("✓ Alle Tests bestanden (material_8k: CIK + Fenster + Look-ahead + "
          "Cap + Exhibit-Term-Scan + fail-soft + Determinismus + S10 + "
          "Look-Ahead-Isolation + Lazy-I/O).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
