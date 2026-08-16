"""Mock-Tests für den n_back=0-Guard-Bug in _exit_p2_score_at (16.08.2026).

Hintergrund (Diagnose 16.08.2026): ``_exit_p2_score_at(entries, n_back)``
hatte den Guard ``if not entries or n_back <= 0 or n_back >= len(entries):
return None``. ``n_back=0`` soll laut Docstring „der letzte Eintrag selbst"
(aktueller Score) liefern — der ``<= 0``-Guard verwarf das fälschlich
IMMER, unabhängig davon wie viele echte Einträge in ``entries`` standen.

Einziger Aufrufer mit ``n_back=0`` ist ``_compute_exit_state()``
(``cur_score = _exit_p2_score_at(entries, 0) if entries else None``) —
``current_score`` war dadurch für JEDE Position mit Top-10-Score-Historie
strukturell dauerhaft ``None`` (bestätigt am 16.08.2026 mit den echten
WOLF/ARCT-Werten aus score_history.json: 60.3 / 82.95, trotzdem
``current_score: None`` in app_data.json). Kascadiert in
``peak_score_since_entry`` (Ratchet kann nie initialisieren, solange
``cur_score`` immer None ist). Betrifft zwei der sechs Phase-2-Exit-Trigger:
``_exit_p2_trigger_score_decay`` und ``_exit_p2_trigger_profit_lock`` waren
für jede Top-10-erfahrene Position strukturell ``available: False``.

Fix: Guard von ``n_back <= 0`` auf ``n_back < 0`` — nur negative Offsets
werden abgelehnt, ``n_back=0`` (aktueller Score) ist jetzt gültig. Die
Obergrenze ``n_back >= len(entries)`` bleibt unverändert.

Grep-Beleg (16.08.2026): ``_exit_p2_score_at`` hat genau ZWEI Aufrufer im
gesamten Repo — ``_exit_p2_trigger_score_decay`` (n ∈ {3,5,7}, Zeile
~16403) und ``_compute_exit_state`` (n_back=0, Zeile ~16862). Kein
dritter/unbekannter Aufrufer gefunden.

Golden-Test-Einordnung: ``_exit_p2_score_at``/``_compute_exit_state`` sind
NICHT im Call-Graph von ``generate_html_v1`` (Phase-2-Exit-Pipeline
schreibt ausschließlich nach ``app_data.json``, nicht in den HTML-Render-
Pfad) — ``mock_test_outer_page_golden.py`` bleibt erwartungsgemäß byte-
identisch, separat verifiziert.

Test-Standard (Lehre aus #535/#536): treibt die ECHTEN, unveränderten
Top-Level-Funktionen ``_exit_p2_score_at`` und ``_compute_exit_state`` an
(realer Modul-Import mit Heavy-Dependency-Stubs, kein Logik-Replikat, keine
Extraktion nötig — beide sind Top-Level-``def``).

Ausführung: ``python scripts/mock_test_exit_p2_score_at_nback_fix.py``.
"""
from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime, timezone

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


# === A — _exit_p2_score_at (echte Funktion, direkter Aufruf) ================

# 8 Einträge, aufsteigend datiert — Index -1 = "heute" = 64.0.
ENTRIES_8 = [
    ["01.08.2026", 50.0], ["02.08.2026", 52.0], ["03.08.2026", 54.0],
    ["04.08.2026", 56.0], ["05.08.2026", 58.0], ["06.08.2026", 60.0],
    ["07.08.2026", 62.0], ["08.08.2026", 64.0],
]


def test_n_back_0_returns_last_entry_not_none():
    """Der eigentliche Fix: n_back=0 liefert jetzt den letzten Eintrag."""
    result = gr._exit_p2_score_at(ENTRIES_8, 0)
    assert result == 64.0, f"Erwarte 64.0 (letzter Eintrag), bekam {result!r}"


def test_n_back_0_with_real_wolf_data_matches_score_history():
    """Reproduziert exakt den diagnostizierten WOLF-Fall aus score_history.json."""
    wolf_entries = [["12.08.2026", 67.63], ["13.08.2026", 60.3]]
    result = gr._exit_p2_score_at(wolf_entries, 0)
    assert result == 60.3, f"Erwarte 60.3 (WOLF letzter Eintrag), bekam {result!r}"


def test_n_back_3_5_7_unchanged_regression():
    """Bestehender Aufrufer (_exit_p2_trigger_score_decay, n ∈ {3,5,7}) darf
    sich NICHT ändern — alle drei Werte waren schon vor dem Fix gültig
    (n > 0), der Guard-Wechsel <=0 -> <0 betrifft sie nicht."""
    assert gr._exit_p2_score_at(ENTRIES_8, 3) == 58.0
    assert gr._exit_p2_score_at(ENTRIES_8, 5) == 54.0
    assert gr._exit_p2_score_at(ENTRIES_8, 7) == 50.0


def test_n_back_negative_still_returns_none():
    """Untergrenze bleibt geschützt — nur negative Offsets sind ungültig."""
    assert gr._exit_p2_score_at(ENTRIES_8, -1) is None
    assert gr._exit_p2_score_at(ENTRIES_8, -100) is None


def test_n_back_at_or_above_length_still_returns_none():
    """Obergrenze 'n_back >= len(entries)' unverändert (Auftrags-Vorgabe:
    diese Grenze bleibt bestehen)."""
    assert gr._exit_p2_score_at(ENTRIES_8, 8) is None   # == len(entries)
    assert gr._exit_p2_score_at(ENTRIES_8, 9) is None   # > len(entries)


def test_empty_entries_returns_none():
    assert gr._exit_p2_score_at([], 0) is None
    assert gr._exit_p2_score_at([], 3) is None


def test_dict_form_entries_supported():
    """Dict-Form ({date, score}) muss identisch zur Tuple-Form funktionieren."""
    dict_entries = [{"date": "01.08.2026", "score": 50.0},
                     {"date": "02.08.2026", "score": 64.0}]
    assert gr._exit_p2_score_at(dict_entries, 0) == 64.0
    assert gr._exit_p2_score_at(dict_entries, 1) == 50.0


def test_source_guard_uses_n_back_less_than_zero():
    """Quelltext-Deckung: der alte '<= 0'-Bug ist raus, '< 0' ist drin."""
    seg = src_gr[src_gr.find("def _exit_p2_score_at("):
                  src_gr.find("def _exit_p2_trigger_score_decay(")]
    assert seg, "generate_report.py-Struktur verändert — Segment-Suche angepasst?"
    assert "n_back <= 0" not in seg, "alter Bug-Guard noch vorhanden"
    assert "n_back < 0" in seg
    assert "n_back >= len(entries)" in seg, "Obergrenze darf nicht verändert sein"


# === B — _compute_exit_state (echte Funktion): current_score jetzt gefüllt =

def _now_fixed() -> datetime:
    return datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_compute_exit_state_current_score_filled_for_ticker_with_history():
    """End-to-End mit den echten WOLF-Werten: current_score/peak_score_
    since_entry müssen jetzt gefüllt sein, nicht None (der diagnostizierte
    Live-Symptom-Fall)."""
    position = {"entry_date": "2026-08-01", "entry_price": 5.0}
    history = {"WOLF": [["12.08.2026", 67.63], ["13.08.2026", 60.3]]}
    state = gr._compute_exit_state(
        "WOLF", position, history, cur_price=5.5, metrics=None,
        prev_state=None, now_utc=_now_fixed())
    assert state["current_score"] == 60.3, (
        f"current_score muss der letzte score_history-Eintrag sein, "
        f"bekam {state['current_score']!r}")
    assert state["peak_score_since_entry"] == 60.3, (
        f"peak_score_since_entry muss beim ersten Lauf (prev_state=None) "
        f"mit current_score initialisieren, bekam "
        f"{state['peak_score_since_entry']!r}")


def test_compute_exit_state_no_history_still_none_regression():
    """Regression: ein Ticker OHNE score_history-Einträge (wie AMC/IONQ/
    PDYN — nie in Top-10) bleibt korrekt None, aus einem ANDEREN Grund
    (leere entries), nicht aus dem Guard-Bug."""
    position = {"entry_date": "2026-08-01", "entry_price": 5.0}
    history: dict = {}  # Ticker nie in score_history.json (kein Top-10-Verlauf)
    state = gr._compute_exit_state(
        "AMC", position, history, cur_price=5.5, metrics=None,
        prev_state=None, now_utc=_now_fixed())
    assert state["current_score"] is None
    assert state["peak_score_since_entry"] is None


def test_compute_exit_state_peak_ratchets_up_not_down():
    """Regression: Ratchet-up-only bleibt erhalten — ein niedrigerer
    current_score als der bestehende peak darf peak NICHT senken."""
    position = {"entry_date": "2026-08-01", "entry_price": 5.0}
    history = {"ARCT": [["13.08.2026", 70.47], ["14.08.2026", 82.95]]}
    prev_state = {"peak_score_since_entry": 90.0}  # höherer Alt-Peak
    state = gr._compute_exit_state(
        "ARCT", position, history, cur_price=5.5, metrics=None,
        prev_state=prev_state, now_utc=_now_fixed())
    # current_score wird auf 1 Nachkommastelle gerundet zurückgegeben
    # (round(82.95, 1) == 83.0) — nur die Anzeige-Rundung, kein Bug.
    assert state["current_score"] == 83.0
    assert state["peak_score_since_entry"] == 90.0, (
        "Ratchet darf einen höheren Alt-Peak nicht auf den niedrigeren "
        f"aktuellen Score zurücksetzen, bekam {state['peak_score_since_entry']!r}")


def main() -> None:
    tests = [
        # A — _exit_p2_score_at
        ("n_back=0 -> letzter Eintrag (der Fix)",
         test_n_back_0_returns_last_entry_not_none),
        ("n_back=0 mit echten WOLF-Werten (60.3)",
         test_n_back_0_with_real_wolf_data_matches_score_history),
        ("n_back=3/5/7 unverändert (Regression bestehender Aufrufer)",
         test_n_back_3_5_7_unchanged_regression),
        ("n_back<0 weiterhin None",
         test_n_back_negative_still_returns_none),
        ("n_back>=len(entries) weiterhin None",
         test_n_back_at_or_above_length_still_returns_none),
        ("leere entries -> None",
         test_empty_entries_returns_none),
        ("Dict-Form entries unterstützt",
         test_dict_form_entries_supported),
        ("Quelltext: Guard ist 'n_back < 0', Obergrenze unverändert",
         test_source_guard_uses_n_back_less_than_zero),
        # B — _compute_exit_state End-to-End
        ("compute_exit_state: current_score jetzt gefüllt (WOLF-Fall)",
         test_compute_exit_state_current_score_filled_for_ticker_with_history),
        ("compute_exit_state: kein history -> weiterhin None (Regression)",
         test_compute_exit_state_no_history_still_none_regression),
        ("compute_exit_state: Peak-Ratchet bleibt nach oben gesperrt",
         test_compute_exit_state_peak_ratchets_up_not_down),
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
