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


def main():
    _test_s10_and_schema()
    _test_look_ahead_isolation()
    _test_hist_stats_wiring()
    _test_formula_and_guards()

    print()
    if _fails:
        print(f"✗ {len(_fails)} Test(s) fehlgeschlagen: {_fails}")
        return 1
    print(
        "✓ Alle Tests bestanden (entry_past_return_5d: Formel + Split-Konsistenz + "
        "None-Semantik + S10 + Look-Ahead-Isolation + Live-Wiring)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
