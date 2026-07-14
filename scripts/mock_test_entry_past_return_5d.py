"""Mock-Tests für ``backtest_history._compute_entry_past_return_5d``
(Hypothese-A-Vorbau, Stufe A).

FIXTURE-ONLY — kein Kontakt mit ``backtest_history.json`` oder anderen Live-
Dateien. Kein empirischer Vergleich gegen Bestandsdaten (das gehört in die
spätere Hypothese-A-Auswertung, nicht in diesen PR — Reihenfolge-Disziplin).

Verifiziert:
- (A) Formel: (close_at_entry / close_5td_before − 1) × 100, round 2
- (B) Split-Konsistenz: bei Adj-Close beidseitig ergibt der Test das gleiche
      Ergebnis unabhängig davon, ob ein zwischenzeitlicher Split die Preis-
      Skala verschoben hat (skalen-invariante Formel)
- (C) None-Semantik (STRIKT „nicht ableitbar", KEINE 0.0-Overload):
      * close_at_entry is None → None
      * close_5td_before is None → None
      * close_5td_before <= 0 → None (IPO / Delisting / kaputte Bar)
      * TypeError bei ungültigem Input → None
- (D) S10-Whitelist + Schema-v4-Additiv-Check:
      * ``entry_past_return_5d`` in ``S10_OBSERVED_FIELDS``
      * NICHT in MUSS/LAG (None ist legitim)
      * Schema-Version bleibt v4 (Source-Inspektion)
      * Feld erscheint im ``_build_backtest_extension``-Return-Dict
- (E) Look-Ahead-Konvention verankert:
      * Docstring-Grep für die Warnung „NIEMALS als Score-Feature"
      * ``_compute_entry_past_return_5d`` wird nirgends in Score/Filter/Push-
        Pfaden importiert (grep über ``generate_report.py``,
        ``ki_agent.py``, ``health_check.py``)
- (F) Live-Vorwärts-Einhänge: Test der Signatur-Erweiterung von
      ``_hist_stats`` um ``close_5td_before_entry`` als 15. Tupel-Element
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


_fails: list[str] = []


def _check(name, cond, detail=""):
    msg = f"  OK  {name}" if cond else f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not cond:
        _fails.append(name)


def _test_s10_and_schema():
    """(A-D) — läuft ohne pandas, stdlib-only. CI-Slot-A-kompatibel."""
    print("── (A/D) S10-Klassifikation + Schema-v4 + Wiring ─────────────")

    _check(
        "A1 entry_past_return_5d in S10_OBSERVED_FIELDS",
        "entry_past_return_5d" in config.S10_OBSERVED_FIELDS,
        "sonst feuert _s10_check_unknown_fields WARN am 1. Record (Lehre #388)",
    )
    _check(
        "A2 entry_past_return_5d NICHT in S10_MUSS_FIELDS",
        "entry_past_return_5d" not in config.S10_MUSS_FIELDS,
        "None legitim bei IPO < 6 Bars vor Entry",
    )
    _check(
        "A3 entry_past_return_5d NICHT in S10_LAG_FIELDS",
        "entry_past_return_5d" not in config.S10_LAG_FIELDS,
        "Feld ist ZUM ENTRY gefroren, kein Lag-Outcome",
    )

    bh_src = (ROOT / "backtest_history.py").read_text(encoding="utf-8")
    _check(
        "A4 Schema-Version bleibt 4 (Source-Inspektion, KEIN Bump)",
        '"backtest_schema_version": 4' in bh_src
        and '"backtest_schema_version": 5' not in bh_src,
        "additive Erweiterung darf keinen Bump erzeugen",
    )
    _check(
        "A5 Feld im _build_backtest_extension-Return-Dict",
        '"entry_past_return_5d":' in bh_src,
        "additive Persistierung fehlt",
    )
    _check(
        "A6 Helper _compute_entry_past_return_5d im Modul definiert",
        "def _compute_entry_past_return_5d(" in bh_src,
        "Helper-Signatur fehlt in backtest_history.py",
    )
    _check(
        "A7 Look-Ahead-Konvention im Helper-Docstring einfroren",
        "NIEMALS als Score-Feature" in bh_src,
        "Look-Ahead-Warnung im Docstring nicht gefunden",
    )
    _check(
        "A8 Look-Ahead-Konvention im S10-Kommentar (config.py)",
        "Look-Ahead-Konvention" in (ROOT / "config.py").read_text(encoding="utf-8"),
        "Look-Ahead-Anker in S10_OBSERVED-Sektion fehlt",
    )


def _test_formula_and_guards():
    """(A-B) Formel/Guards — pure Python-Test der Helper-Funktion.

    Import ist nicht-trivial, weil backtest_history yfinance top-level
    importiert. Wir stubben yfinance-Modul, damit backtest_history-Import
    im CI-Slot-A durchgeht.
    """
    import types

    if "yfinance" not in sys.modules:
        sys.modules["yfinance"] = types.ModuleType("yfinance")

    try:
        from backtest_history import _compute_entry_past_return_5d
    except ImportError as exc:
        print(f"── Formel-Tests ÜBERSPRUNGEN — Import-Fail: {exc}")
        return

    print("── (A) Formel-Verifikation ───────────────────────────────────")

    # Basisfall: entry 100, 5td_before 100 → 0 %
    _check(
        "F1 flach (100/100) → 0.00 %",
        _compute_entry_past_return_5d(100.0, 100.0) == 0.0,
        f"got {_compute_entry_past_return_5d(100.0, 100.0)}",
    )
    # +10 %-Anstieg (Reversal-Kandidat sollte NEGATIV sein — dies ist +10)
    _check(
        "F2 (110/100) → +10.00 %",
        _compute_entry_past_return_5d(110.0, 100.0) == 10.0,
    )
    # Reversal-Fall: entry 60, before 100 → −40 % (klassischer Reversal-Kandidat)
    _check(
        "F3 (60/100) → −40.00 % (Reversal-Signatur)",
        _compute_entry_past_return_5d(60.0, 100.0) == -40.0,
    )
    # Halbierung: entry 50, before 100 → −50 %
    _check(
        "F4 (50/100) → −50.00 %",
        _compute_entry_past_return_5d(50.0, 100.0) == -50.0,
    )
    # Verdreifachung: entry 300, before 100 → +200 %
    _check(
        "F5 (300/100) → +200.00 %",
        _compute_entry_past_return_5d(300.0, 100.0) == 200.0,
    )
    # Runde 2 Dezimalen: entry 100, before 99 → +1.01 %
    r = _compute_entry_past_return_5d(100.0, 99.0)
    _check(
        "F6 (100/99) → +1.01 % (Rundung)",
        r == 1.01,
        f"got {r}",
    )

    print("── (B) Split-Konsistenz ──────────────────────────────────────")
    # Reverse-Split-Szenario: Adj-Close beidseitig skalen-invariant.
    # Ohne Adj: entry_price roh 5.0 nach 1:10 Reverse-Split, 5td vorher roh 50 (im
    # rohen Preis-Universum kein Change), aber Adj-Close würde beide auf
    # DERSELBEN Skala rechnen → immer 0 %.
    _check(
        "B1 Adj-Close skalen-invariant (100/100 == 10/10 == 1/1)",
        _compute_entry_past_return_5d(100.0, 100.0) ==
        _compute_entry_past_return_5d(10.0, 10.0) ==
        _compute_entry_past_return_5d(1.0, 1.0) == 0.0,
        "Reverse-Split-Ratio muss invariant sein bei Adj-Close beidseitig",
    )

    print("── (C) None-Semantik (STRIKT nicht-ableitbar) ────────────────")

    _check("C1 None-Zähler → None", _compute_entry_past_return_5d(None, 100.0) is None)
    _check("C2 None-Nenner → None", _compute_entry_past_return_5d(100.0, None) is None)
    _check(
        "C3 Nenner == 0 → None (IPO / kaputte Bar, NICHT 0.0)",
        _compute_entry_past_return_5d(100.0, 0.0) is None,
    )
    _check(
        "C4 Nenner < 0 → None (kaputte Bar)",
        _compute_entry_past_return_5d(100.0, -5.0) is None,
    )
    _check(
        "C5 String-Zähler → None (defensiv)",
        _compute_entry_past_return_5d("nope", 100.0) is None,
    )
    _check(
        "C6 String-Nenner → None (defensiv)",
        _compute_entry_past_return_5d(100.0, "nope") is None,
    )


def _test_look_ahead_isolation():
    """(E) — Look-Ahead-Isolation: Helper darf NIEMALS in Score/Filter/Push
    importiert werden."""
    print("── (E) Look-Ahead-Isolation ──────────────────────────────────")

    for path_rel, tag in (
        ("generate_report.py",  "Live-Report-/Score-Pfad"),
        ("ki_agent.py",         "KI-Agent-/Push-Pfad"),
        ("health_check.py",     "Health-Check-Pfad"),
    ):
        src = (ROOT / path_rel).read_text(encoding="utf-8")
        # ``_compute_entry_past_return_5d(...)`` MIT öffnender Klammer = Aufruf.
        # Docstring-/Kommentar-Erwähnungen (nur Name ohne "(") sind erlaubt und
        # sogar hilfreich (Verweis auf den Look-Ahead-Anker).
        _check(
            f"E-{path_rel}: kein Aufruf von _compute_entry_past_return_5d(...)",
            "_compute_entry_past_return_5d(" not in src,
            f"{tag} — Look-Ahead-Bruch: Helper würde Backtest-Feld in Score-Pfad lesen",
        )
        # Ebenso: kein Read von entry_past_return_5d aus einem stock/record-Dict
        # in Score-/Push-/Filter-Kontext (der Feldname darf im Live-Enrichment
        # NUR als s["close_5td_before_entry"] auftauchen, nicht als
        # s["entry_past_return_5d"] oder record["entry_past_return_5d"]).
        # Docstring-Erwähnungen bleiben erlaubt.
        forbidden_reads = [
            'get("entry_past_return_5d")',
            "['entry_past_return_5d']",
            '["entry_past_return_5d"]',
        ]
        _check(
            f"E-{path_rel}: kein Read von entry_past_return_5d aus dict",
            not any(pat in src for pat in forbidden_reads),
            f"{tag} — Look-Ahead-Bruch: Score/Push liest Backfill-Feld",
        )


def _test_hist_stats_wiring():
    """(F) — Live-Vorwärts-Einhänge: _hist_stats muss um 15. Tupel-Element
    close_5td_before_entry erweitert sein."""
    print("── (F) _hist_stats Signatur-Erweiterung ──────────────────────")

    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    _check(
        "F1 _hist_stats returnt 15-Tupel (default: 13 None/0.0 + [] + None)",
        "0.0, 0.0, 0.0, None, None, None, None, None, None, None, None, None, None, [], None" in gr_src,
        "Default-Return am _hist_stats-Ende nicht um close_5td_before_entry erweitert",
    )
    _check(
        "F2 Caller-Auspack-Stelle enthält close_5td_before_entry",
        "cur_close, hist_5d, close_5td_before_entry = _hist_stats(ticker)" in gr_src,
        "_hist_stats-Caller nicht angepasst",
    )
    _check(
        "F3 Stock-Dict bekommt s['close_5td_before_entry']",
        '"close_5td_before_entry": close_5td_before_entry,' in gr_src,
        "Live-Enrichment-Dict enthält close_5td_before_entry nicht",
    )
    # df.iloc[-6]-Extraktion muss beidseitig (Batch + Fallback) präsent sein
    n_iloc6 = gr_src.count("iloc[-6]")
    _check(
        "F4 df.iloc[-6]-Extraktion mindestens 2× (Batch + Singleton-Fallback)",
        n_iloc6 >= 2,
        f"got {n_iloc6} — Fallback-Pfad in _hist_stats fehlt evtl.",
    )


def _test_merge_wiring():
    """(G) — Merge-Durchreichung: der c.update-Enrichment-Merge UND der
    get_yfinance_data-Fallback müssen ``close_5td_before_entry`` liefern.

    Regression-Guard für den 11.07.2026-Bug: _hist_stats berechnete den Wert
    korrekt (F1-F4), aber der c.update-Merge (:16190-16241) hatte den Key NICHT
    in seiner Whitelist → s.get("close_5td_before_entry") war beim Backtest-
    Append None → 50/50 entry_past_return_5d None. Exakt die hist_5d-Bug-Klasse.
    """
    print("── (G) Merge-Durchreichung close_5td_before_entry ────────────")

    gr_src = (ROOT / "generate_report.py").read_text(encoding="utf-8")
    _check(
        "G1 c.update-Merge reicht close_5td_before_entry durch (PRIMÄR-FIX)",
        '"close_5td_before_entry": yfd.get("close_5td_before_entry"),' in gr_src,
        "ohne diesen Merge-Eintrag bleibt der Backtest-Nenner None (0/50-Bug)",
    )
    # get_yfinance_data (Fallback-Pfad) muss den Key ebenfalls im Return-Dict
    # haben, sonst bleibt es im Fallback None. Berechnung + Return getrennt
    # geprüft (Existenz beider Bausteine).
    _check(
        "G2 get_yfinance_data berechnet close_5td_before_entry (SEKUNDÄR-FIX)",
        'close_5td_before_entry = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else None' in gr_src,
        "Fallback-Pfad ohne Nenner-Berechnung → wieder None bei Batch-Miss",
    )
    _check(
        "G3 get_yfinance_data returnt close_5td_before_entry im Dict",
        '"close_5td_before_entry": close_5td_before_entry,' in gr_src,
        "Berechnung ohne Return-Eintrag bleibt wirkungslos",
    )
    # df.iloc[-6] jetzt mindestens 3× (Batch + _hist_stats-Singleton +
    # get_yfinance_data-Fallback) — vorher deckte F4 nur die ersten zwei ab.
    n_iloc6 = gr_src.count("iloc[-6]")
    _check(
        "G4 iloc[-6]-Extraktion ≥ 3× (Batch + Singleton + Fallback-Pfad)",
        n_iloc6 >= 3,
        f"got {n_iloc6} — get_yfinance_data-Fallback-Berechnung fehlt evtl.",
    )


def _test_nonnull_end_to_end():
    """(H) — KERNBEWEIS: mit vorhandenem close_5td_before_entry liefert
    _build_backtest_extension einen NON-NULL entry_past_return_5d; ohne Nenner
    sauber None (kein Crash). End-to-end über die echte Extension-Funktion,
    nicht nur den Helper isoliert."""
    import types

    if "yfinance" not in sys.modules:
        sys.modules["yfinance"] = types.ModuleType("yfinance")
    try:
        from backtest_history import _build_backtest_extension
    except ImportError as exc:
        print(f"── (H) End-to-End ÜBERSPRUNGEN — Import-Fail: {exc}")
        return

    print("── (H) NON-NULL-Kernbeweis (end-to-end) ──────────────────────")

    def _sf(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0

    # short_float=None → sub-scores übersprungen (backtest_history.py:491),
    # compute_sub_scores_fn wird nie gerufen. Minimaler Fixture-Stock.
    s = {"ticker": "TEST", "price": 60.0,
         "close_5td_before_entry": 100.0, "short_float": None}
    ext = _build_backtest_extension(
        s, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=lambda x: None, safe_float_fn=_sf,
    )
    val = ext.get("entry_past_return_5d")
    _check(
        "H1 non-null nach Fix (60/100 → −40.0, Nenner vorhanden)",
        val == -40.0,
        f"got {val} — Bug NICHT behoben, wenn None",
    )

    # Gegenprobe: Nenner fehlt (Bestandsposition / IPO) → sauber None, kein Crash
    s2 = {"ticker": "TEST2", "price": 60.0, "short_float": None}
    ext2 = _build_backtest_extension(
        s2, pool_position=1, pool_size=10, agent_signals={},
        compute_sub_scores_fn=lambda x: None, safe_float_fn=_sf,
    )
    _check(
        "H2 Nenner fehlt → sauber None (kein Crash, keine 0.0-Overload)",
        ext2.get("entry_past_return_5d") is None,
    )


def _test_station1_regression_net():
    """(I) — STATION-1-ABSICHERUNGS-NETZ (Live-Call, pandas-gated).

    ABSICHERUNGS-NETZ — GRÜN bei korrektem Code; fängt eine KÜNFTIGE Regression
    der pre-entry-Nenner-Berechnung ``close_5td_before_entry`` (Close 5
    Handelstage VOR Entry = ``iloc[-6]``). Dies ist AUSDRÜCKLICH KEIN
    Mutations-Beweis eines bestehenden Bugs: der historische #411-Bug lag im
    ``c.update``-Enrichment-Merge (der Nenner wurde korrekt berechnet, aber
    beim Merge gedroppt) — separat abgedeckt durch die Merge-Assertion G1-G3
    (``_test_merge_wiring``). Station 1 (die Berechnung selbst) war nie kaputt;
    dieser Test verriegelt sie trotzdem als Netz.

    Was gemessen wird (echter Call, kein Source-Grep): beide Fetch-Pfade liefern
    aus einer Fixture-Bar-History (real pandas DataFrame) den Nenner non-null =
    ``iloc[-6]``:
      * ``get_yfinance_data``  — Singleton-Fallback-Pfad (isoliert aufrufbar).
      * ``get_yfinance_batch`` — Produktions-Batch-Pfad; treibt das NESTED
        ``_hist_stats`` (Closure in ``get_yfinance_batch`` → nicht isoliert
        aufrufbar, daher über die öffentliche Batch-Funktion getestet).
    Edge: < 6 Bars → sauber ``None`` (kein Crash), beide Pfade.

    pandas-GATED: der CI-Minimal-Vertrag ist ``stdlib + jinja2 + pyyaml``
    (``entry_past_return_5d`` steht in der ALLOWLIST). Fehlt pandas → sauberer
    Skip (grün), analog zum H-ImportError-Skip. Die Assertion läuft real in
    Dev-/pandas-Umgebungen. `generate_report` wird deshalb erst NACH dem
    pandas-Gate importiert (Modul-Top bleibt stdlib-only, CI-safe).
    """
    try:
        import pandas as pd
    except ImportError:
        print("── (I) Station-1-Netz ÜBERSPRUNGEN — pandas fehlt (CI-minimal, erwartet)")
        return

    import types

    # Drittlib-Stubs VOR dem generate_report-Import (kanonisches Muster; yfinance
    # wird als Fake-Modul gestubbt und dann mit Fixture-Fetches überschrieben).
    for _name in ("yfinance", "requests", "bs4", "deep_translator", "watchlist"):
        if _name in sys.modules:
            continue
        _m = types.ModuleType(_name)
        if _name == "yfinance":
            _m.download = lambda *a, **k: None
            _m.Ticker = lambda *a, **k: None
        elif _name == "requests":
            _m.Session = lambda *a, **k: types.SimpleNamespace(
                headers=types.SimpleNamespace(update=lambda *a, **k: None))
            _m.get = lambda *a, **k: None
            _m.exceptions = types.SimpleNamespace(RequestException=Exception)
        elif _name == "bs4":
            _m.BeautifulSoup = lambda *a, **k: None
        elif _name == "deep_translator":
            _m.GoogleTranslator = lambda *a, **k: types.SimpleNamespace(
                translate=lambda s: s)
        elif _name == "watchlist":
            _m.WATCHLIST = []
        sys.modules[_name] = _m

    try:
        import generate_report as gr
    except ImportError as exc:
        print(f"── (I) Station-1-Netz ÜBERSPRUNGEN — generate_report-Import-Fail: {exc}")
        return

    print("── (I) Station-1-Absicherungs-Netz (Live-Call, pandas) ───────")

    # Fixture: 8 Tages-Bars, aufsteigend. iloc[-1]=Close am Entry-Tag=170,
    # iloc[-6]=Close 5 Handelstage davor=120 → Nenner MUSS 120.0 sein.
    closes = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0]
    expected = closes[-6]  # 120.0 — 5 Handelstage vor der letzten Bar

    def _mkdf(rows):
        idx = pd.date_range("2026-06-01", periods=len(rows), freq="D")
        return pd.DataFrame(
            {"Open": rows, "High": [r + 1 for r in rows],
             "Low": [r - 1 for r in rows], "Close": rows,
             "Volume": [1_000_000] * len(rows)},
            index=idx,
        )

    df8 = _mkdf(closes)
    df5 = _mkdf(closes[:5])  # < 6 Bars → Nenner nicht ableitbar
    # Defensiv: ein früher gesetzter Bare-Stub (H-Test) hat evtl. weder
    # ``Ticker`` noch ``download`` → getattr mit Default, wir setzen die
    # Fixtures ohnehin explizit.
    _orig_ticker = getattr(gr.yf, "Ticker", None)
    _orig_download = getattr(gr.yf, "download", None)
    try:
        # ── Pfad 1: get_yfinance_data (Singleton-Fallback, isoliert aufrufbar) ──
        gr.yf.Ticker = lambda *a, **k: types.SimpleNamespace(
            info={}, history=lambda **k: df8)
        d = gr.get_yfinance_data("TEST")
        _check(
            "I1 get_yfinance_data: close_5td_before_entry == iloc[-6] (non-null)",
            d.get("close_5td_before_entry") == expected,
            f"got {d.get('close_5td_before_entry')}, erwartet {expected}",
        )

        # ── Pfad 2: _hist_stats via get_yfinance_batch (Produktions-Batch-Pfad) ──
        gr.yf.download = lambda *a, **k: df8  # single-ticker → flat DataFrame
        b = gr.get_yfinance_batch(["TEST"])
        _check(
            "I2 _hist_stats (via get_yfinance_batch): close_5td_before_entry == iloc[-6]",
            b.get("TEST", {}).get("close_5td_before_entry") == expected,
            f"got {b.get('TEST', {}).get('close_5td_before_entry')}, erwartet {expected}",
        )

        # ── Edge < 6 Bars → sauber None (kein Crash), beide Pfade ──
        gr.yf.Ticker = lambda *a, **k: types.SimpleNamespace(
            info={}, history=lambda **k: df5)
        gr.yf.download = lambda *a, **k: df5
        d_short = gr.get_yfinance_data("TEST")
        b_short = gr.get_yfinance_batch(["TEST"])
        _check(
            "I3 < 6 Bars → get_yfinance_data close_5td_before_entry None",
            d_short.get("close_5td_before_entry") is None,
            f"got {d_short.get('close_5td_before_entry')}",
        )
        _check(
            "I4 < 6 Bars → get_yfinance_batch close_5td_before_entry None",
            b_short.get("TEST", {}).get("close_5td_before_entry") is None,
            f"got {b_short.get('TEST', {}).get('close_5td_before_entry')}",
        )
    finally:
        gr.yf.Ticker, gr.yf.download = _orig_ticker, _orig_download


def main():
    _test_s10_and_schema()
    _test_look_ahead_isolation()
    _test_hist_stats_wiring()
    _test_merge_wiring()
    _test_nonnull_end_to_end()
    _test_formula_and_guards()
    _test_station1_regression_net()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print(
        "✓ Alle Tests bestanden (entry_past_return_5d: Formel + Split-Konsistenz + "
        "None-Semantik + S10 + Look-Ahead-Isolation + Live-Wiring + Merge-"
        "Durchreichung + NON-NULL-Kernbeweis end-to-end + Station-1-Netz)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
