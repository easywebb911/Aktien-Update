"""Mock-Tests für den change_2d/change_3d-NaN-Wurzelfix (15.08.2026).

Hintergrund: Diagnose fand 41 Zeilen mit blankem NaN in
``score_inflation_log.jsonl`` (5 Läufe, 27 Ticker), Feld ``change_2d``/
``change_3d``. Wurzel: ``get_yfinance_batch`` (generate_report.py) las
``float(_df["Close"].iloc[...])`` ohne Finite-Check — eine NaN-Zelle
(yfinance-Datenlücke) lief unbemerkt bis in ``round(nan, 2)`` = ``nan``.
Drei Konsumenten desselben Feldes:

  1. ``apply_late_runner_penalty`` (generate_report.py) — SCORE-Pfad
     (Top-10-Ranking). War UNGEHÄRTET (roher Read).
  2. ``_exit_p2_trigger_overheated`` (generate_report.py) — Exit-Trigger
     für offene Positionen. War BEREITS am 27.07.2026 auf ``_finite()``
     gehärtet.
  3. Push-Stille-Filter (ki_agent.py) — ntfy-Push-Pfad. Nutzte
     ``isinstance(x, (int, float))`` statt ``_finite()`` — NaN IST eine
     float-Instanz, das ließ sie durch.

Dieser PR fixt die Wurzel (get_yfinance_batch) UND härtet Konsument 1+3
explizit; Konsument 2 wird nur GEGENGEPRÜFT (unverändert, bereits sicher
— siehe test_17b in mock_test_nan_price_tightness.py).

WICHTIGE EHRLICHE KORREKTUR (beim Bauen entdeckt, nicht vorab behauptet):
Die Wurzel liefert nach dem Fix nie mehr NaN, sondern ``None`` bei einer
kaputten Zelle. ``apply_late_runner_penalty``s alte Ternary behandelte
``None`` bereits korrekt (0.0-Default) — der numerische AUSGANG ändert
sich dort NICHT, nur die Sichtbarkeit (kein stiller Pfad mehr, explizite
Branch + Log). Beim Push-Stille-Filter gilt dasselbe: ``isinstance(None,
(int,float))`` ist bereits ``False`` — der Root-Fix allein hätte den
Filter also schon korrekt gemacht, OHNE die ki_agent.py-Änderung. Die
``_finite()``-Härtung dort ist zusätzliches Defense-in-Depth (Konsistenz
mit dem restlichen Codebase-Muster, Schutz gegen ein theoretisches
Alt-``app_data.json`` mit einer Vor-Fix-NaN während einer Deploy-
Übergangsphase), NICHT die Schließung einer eigenständig ausnutzbaren
Lücke — das war beim ursprünglichen Diagnose-Befund unklar und wird hier
korrigiert.

Tests:
  1. Wurzel (get_yfinance_batch): NaN-Zelle → Feld bleibt UNGESETZT
     (nicht NaN, keine Fake-Zahl) — Quelltext-Deckung + Verhaltens-Replik.
  2. apply_late_runner_penalty: explizite None-Behandlung, Log-Aufruf,
     RSI-Kriterium bleibt unabhängig scharf, Ausgang bei None ==
     Ausgang bei (dem jetzt unmöglichen) NaN.
  3. ki_agent Push-Stille-Filter: _finite() statt isinstance(), Richtung
     des alten Fehlers (Push wurde fälschlich NICHT unterdrückt) belegt,
     Äquivalenz-Nachweis dass der Root-Fix allein schon reicht.
  4. Kein stiller Ersatzwert (coiled_spring-Muster) irgendwo eingeführt.
  5. Golden-Erwartung: Verhalten bei VOLLSTÄNDIGEN Daten unverändert.

Ausführung: ``python scripts/mock_test_change2d_nan_hardening.py``.
"""
from __future__ import annotations

import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

src_gr = (ROOT / "generate_report.py").read_text(encoding="utf-8")
src_ki = (ROOT / "ki_agent.py").read_text(encoding="utf-8")


def _finite(v) -> bool:
    """Lokale Replik (identischer Vertrag zu generate_report._finite /
    ki_agent._finite — beide dupliziert, kein Import nötig für Tests)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def _finite_cell(series_like, default_map):
    """Replik von generate_report._finite_cell für die Fake-Series unten."""
    v = series_like.get(default_map)
    return v if _finite(v) else None


# === 1 — Wurzel: get_yfinance_batch change_2d/3d/5d ========================

class _FakeCloseSeries(dict):
    """Minimal-Stand-in: unterstützt .iloc[idx] über ein dict {idx: value}."""
    class _ILoc:
        def __init__(self, outer):
            self.outer = outer

        def __getitem__(self, idx):
            return self.outer[idx]

    @property
    def iloc(self):
        return self._ILoc(self)


def _compute_change_pct(c_now, c_then):
    """Replik der gehärteten Prozent-Berechnung (ein Endpunkt-Paar).
    ``_finite()``-Check statt ``== 0``/``is None`` allein — ``NaN == 0``
    ist ``False``, ein bloßer Gleichheits-Check würde eine NaN NICHT
    fangen (dieselbe Lehre wie beim Root-Fix selbst)."""
    if not _finite(c_now) or not _finite(c_then) or c_then == 0:
        return None
    return round((c_now - c_then) / c_then * 100, 2)


def test_root_source_no_bare_float_iloc_on_close():
    """Quelltext-Deckung: der change_2d/3d/5d-Block liest Close-Zellen NUR
    noch über _finite_cell, nicht mehr über rohes float(...iloc[...]).

    Sucht im AUSFÜHRBAREN Teil des Blocks (ab dem try:) — der Docstring-
    Kommentar darüber erwähnt das alte Muster absichtlich als Doku und
    würde einen naiven String-Scan über den ganzen Block fälschlich
    triggern.
    """
    seg = src_gr[src_gr.find('        try:\n            _df = hist_batch if len(tickers) == 1'):
                 src_gr.find('# Tages-``change``-Fallback')]
    assert seg, "Root-Block (Code-Teil) nicht gefunden — Struktur geändert?"
    assert '_finite_cell(_df["Close"]' in seg
    for bad in ('float(_df["Close"].iloc[-1])', 'float(_df["Close"].iloc[-3])',
                'float(_df["Close"].iloc[-4])', 'float(_df["Close"].iloc[-6])'):
        assert bad not in seg, f"roher Read {bad!r} ist noch im Root-Block"


def test_root_source_fields_stay_unset_not_nan():
    """Quelltext-Deckung: bei einer kaputten Zelle wird das Feld NICHT
    gesetzt (kein results[ticker]['change_2d'] = nan möglich) — die
    Zuweisung steht hinter einem `is not None`-Guard."""
    seg = src_gr[src_gr.find('# change_5d und change_2d aus Batch-History.'):
                 src_gr.find('# Tages-``change``-Fallback')]
    assert 'if _c3 is not None and _c3 != 0:' in seg
    assert 'if _c4 is not None and _c4 != 0:' in seg
    assert 'if _c6 is not None and _c6 != 0:' in seg


def test_root_behavior_broken_cell_leaves_field_unset():
    """Verhaltens-Replik: eine NaN- oder fehlende Close-Zelle darf am Ende
    weder eine NaN NOCH eine fabrizierte Zahl liefern — nur None."""
    # c_now vorhanden, c_then (vor 2 Tagen) ist NaN -> None, kein Fake-Wert
    assert _compute_change_pct(10.0, float("nan")) is None
    # beide vorhanden und endlich -> echte Prozent-Zahl (Regressions-Gegenprobe)
    assert _compute_change_pct(11.0, 10.0) == 10.0
    # Nenner exakt 0 -> None statt ZeroDivisionError/Inf
    assert _compute_change_pct(11.0, 0.0) is None


def test_root_behavior_all_valid_unchanged():
    """Regression: bei vollständigen Daten liefert die Rechnung exakt
    denselben Wert wie die alte ungeschützte Formel (kein Verhaltens-Drift
    bei sauberen Daten -> Golden-Erwartung)."""
    c_now, c_then = 12.34, 11.0
    old_style = round((c_now - c_then) / c_then * 100, 2)
    new_style = _compute_change_pct(c_now, c_then)
    assert old_style == new_style


# === 2 — apply_late_runner_penalty ==========================================

LATE_RUNNER_RSI_THRESHOLD = 75
LATE_RUNNER_MOVE_2D_THRESHOLD = 0.20
LATE_RUNNER_PENALTY = 0.85


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _late_runner_penalty_replica(rsi14_raw, change_2d_raw, score_raw):
    """Replik von apply_late_runner_penalty für EINEN Stock (Kernlogik,
    identisch zur gehärteten Quelle: explizite None-Branch, kein stiller
    Ersatzwert, RSI-Kriterium unabhängig scharf)."""
    rsi14 = _safe_float(rsi14_raw or 0)
    chg2d_p = change_2d_raw
    logged_unknown = False
    if chg2d_p is None:
        chg2d_frac = 0.0
        logged_unknown = True
    else:
        try:
            chg2d_frac = float(chg2d_p) / 100.0
        except (TypeError, ValueError):
            chg2d_frac = 0.0

    rsi_hot = rsi14 > LATE_RUNNER_RSI_THRESHOLD
    move_hot = chg2d_frac > LATE_RUNNER_MOVE_2D_THRESHOLD
    if not (rsi_hot or move_hot):
        return score_raw, False, logged_unknown

    after = round(score_raw * LATE_RUNNER_PENALTY, 1)
    return after, True, logged_unknown


def test_late_runner_none_move_no_penalty_but_logged():
    """Kernfall: change_2d unbekannt (None), RSI unauffällig -> KEIN
    Abschlag (Easys explizite Erwartung), ABER als 'unknown' markiert
    (kein stiller Freifahrtschein)."""
    score, penalized, logged = _late_runner_penalty_replica(
        rsi14_raw=40.0, change_2d_raw=None, score_raw=90.0)
    assert penalized is False
    assert score == 90.0
    assert logged is True, "unbekannte Bewegung muss sichtbar markiert werden"


def test_late_runner_rsi_channel_independent_of_move():
    """RSI-Kriterium bleibt scharf, auch wenn die Bewegung unbekannt ist —
    ein heißes RSI allein reicht für den Abschlag."""
    score, penalized, logged = _late_runner_penalty_replica(
        rsi14_raw=80.0, change_2d_raw=None, score_raw=90.0)
    assert penalized is True
    assert score == round(90.0 * LATE_RUNNER_PENALTY, 1)
    assert logged is True


def test_late_runner_known_hot_move_still_penalizes():
    """Regression: ein bekannter, echter Move über der Schwelle löst
    weiterhin den Abschlag aus (RSI unauffällig)."""
    score, penalized, logged = _late_runner_penalty_replica(
        rsi14_raw=40.0, change_2d_raw=25.0, score_raw=90.0)  # 25% > 20%
    assert penalized is True
    assert logged is False
    assert score == round(90.0 * LATE_RUNNER_PENALTY, 1)


def test_late_runner_known_calm_move_no_penalty():
    """Regression: ein bekannter Move unter der Schwelle -> kein Abschlag,
    und NICHT als 'unknown' markiert (echt geprüft, nicht nur geraten)."""
    score, penalized, logged = _late_runner_penalty_replica(
        rsi14_raw=40.0, change_2d_raw=5.0, score_raw=90.0)
    assert penalized is False
    assert logged is False


def test_late_runner_none_outcome_matches_old_worst_case_nan():
    """Explizite Äquivalenz-Prüfung: die alte implizite Ternary lieferte
    für None einen expliziten 0.0-Default, für NaN aber eine ECHTE NaN
    (``chg2d_p is not None`` ist für NaN True!). Der numerische WERT
    unterscheidet sich also technisch (0.0 vs. NaN) — aber im
    NACHGELAGERTEN Vergleich ``chg2d_frac > SCHWELLE`` verhalten sich
    BEIDE identisch: ``0.0 > schwelle`` ist False, ``nan > schwelle`` ist
    ebenfalls False. Das ist der eigentliche Äquivalenz-Beweis (gleicher
    EFFEKT auf move_hot), nicht Bit-Gleichheit der Zwischenwerte — NaN
    lässt sich nicht sinnvoll mit ``==`` vergleichen (nan != nan)."""
    def _old_ternary(chg2d_p):
        try:
            return float(chg2d_p) / 100.0 if chg2d_p is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    none_frac = _old_ternary(None)
    nan_frac  = _old_ternary(float("nan"))
    assert none_frac == 0.0
    assert math.isnan(nan_frac)
    assert (none_frac > LATE_RUNNER_MOVE_2D_THRESHOLD) == \
           (nan_frac > LATE_RUNNER_MOVE_2D_THRESHOLD) == False


def test_late_runner_source_has_explicit_branch_and_log():
    """Quelltext-Deckung: keine implizite Ternary mehr, explizite
    None-Branch + log.debug-Aufruf vorhanden."""
    seg = src_gr[src_gr.find("def apply_late_runner_penalty("):
                 src_gr.find("def _fetch_premarket_volumes_batch(")]
    assert 'if chg2d_p is None:' in seg
    assert 'log.debug(' in seg
    assert 'chg2d_frac = float(chg2d_p) / 100.0 if chg2d_p is not None else 0.0' not in seg, (
        "alte implizite Ternary ist noch da")


# === 3 — ki_agent Push-Stille-Filter ========================================

def _silence_reasons_replica(rsi14, chg2d_pct, *, use_finite: bool):
    """Replik des Push-Stille-Filters — mit Schalter zwischen der ALTEN
    (isinstance) und NEUEN (_finite) Guard-Form, um die Äquivalenz explizit
    zu beweisen statt sie nur zu behaupten."""
    PUSH_RSI_MAX = 70
    PUSH_MOVE_2D_MAX = 0.20
    reasons = []
    if use_finite:
        rsi_ok, mv_ok = _finite(rsi14), _finite(chg2d_pct)
    else:
        rsi_ok  = isinstance(rsi14, (int, float))
        mv_ok   = isinstance(chg2d_pct, (int, float))
    if rsi_ok and rsi14 > PUSH_RSI_MAX:
        reasons.append("rsi")
    if mv_ok and chg2d_pct > PUSH_MOVE_2D_MAX * 100:
        reasons.append("move")
    return reasons


def test_push_filter_old_isinstance_let_nan_through_wrong_direction():
    """Belegt die Richtung des ALTEN Fehlers: isinstance(NaN, float) ist
    True, NaN verliert dann den '>'-Vergleich -> Silence-Grund wird NICHT
    gesetzt -> ein Push für eine (durch die NaN maskierte) Bewegung wird
    FÄLSCHLICH NICHT unterdrückt = fälschlich gesendet."""
    reasons_old = _silence_reasons_replica(50.0, float("nan"), use_finite=False)
    assert reasons_old == [], "Push wäre nicht unterdrückt worden (Bug bestätigt)"


def test_push_filter_new_finite_rejects_nan_and_none_identically():
    """Nach der Härtung behandelt der Filter NaN und None identisch — beide
    lösen keine 'move'-Stille aus (kann nicht geprüft werden), aber auch
    keine Exception, kein Fake-Wert."""
    r_nan  = _silence_reasons_replica(50.0, float("nan"), use_finite=True)
    r_none = _silence_reasons_replica(50.0, None,          use_finite=True)
    assert r_nan == r_none == []


def test_push_filter_root_fix_alone_already_fixes_isinstance_path():
    """WICHTIGE EHRLICHE KORREKTUR: isinstance(None, (int,float)) ist
    bereits False — der Root-Fix (NaN -> None an der Quelle) hätte den
    ALTEN isinstance-Filter also schon korrekt gemacht, OHNE die
    ki_agent.py-Änderung. Die _finite()-Härtung ist zusätzliches
    Defense-in-Depth, keine eigenständig notwendige Bugfix-Bedingung."""
    reasons_old_with_none = _silence_reasons_replica(50.0, None, use_finite=False)
    reasons_new_with_none = _silence_reasons_replica(50.0, None, use_finite=True)
    assert reasons_old_with_none == reasons_new_with_none == []


def test_push_filter_genuine_hot_move_still_silences():
    """Regression: ein echter, endlicher überhitzter Move silenced weiterhin
    korrekt (mit beiden Guard-Formen — kein Verhaltens-Drift bei validen
    Daten)."""
    r_old = _silence_reasons_replica(50.0, 25.0, use_finite=False)  # 25% > 20%
    r_new = _silence_reasons_replica(50.0, 25.0, use_finite=True)
    assert r_old == r_new == ["move"]


def test_push_filter_source_uses_finite_not_isinstance():
    """Quelltext-Deckung: ki_agent.py nutzt jetzt _finite() statt
    isinstance() für RSI UND change_2d im Push-Stille-Filter."""
    seg = src_ki[src_ki.find("# Push-Stille-Filter: bei überhitztem Setup"):
                 src_ki.find("for anom in detect_anomalies(")]
    assert seg, "Push-Stille-Filter-Segment nicht gefunden"
    assert "_finite(_rsi14)" in seg
    assert "_finite(_chg2d_pct)" in seg
    assert "isinstance(_rsi14, (int, float))" not in seg
    assert "isinstance(_chg2d_pct, (int, float))" not in seg


def test_ki_agent_has_local_finite_helper():
    """Quelltext-Deckung: ki_agent.py hat jetzt einen lokalen _finite-
    Helper (dupliziert, kein Cross-Modul-Import — analog backtest_history.py)."""
    assert "def _finite(v) -> bool:" in src_ki
    assert "if isinstance(v, bool) or not isinstance(v, (int, float)):" in src_ki


# === 4 — Kein stiller Ersatzwert irgendwo (coiled_spring-Gegenprobe) =======

def test_no_silent_fake_value_introduced_anywhere():
    """Explizite Gegenprobe gegen das coiled_spring-Muster: keiner der drei
    gehärteten Codepfade darf bei fehlenden Daten eine PLAUSIBEL
    aussehende, aber erfundene Zahl liefern — nur None/[] bzw. unveränderte
    Werte."""
    # Wurzel: fehlt/kaputt -> Feld bleibt unset (kein 0.0-Platzhalter)
    assert _compute_change_pct(None, 10.0) is None
    assert _compute_change_pct(10.0, None) is None
    # Late-Runner: unbekannte Bewegung -> Score UNVERÄNDERT (kein Abschlag
    # UND kein erfundener Bonus), nicht auf 0 oder einen Default gesetzt
    score, penalized, _ = _late_runner_penalty_replica(40.0, None, 73.4)
    assert score == 73.4 and penalized is False
    # Push-Filter: unbekannt -> kein Grund in der Liste (nicht "move: 0%"
    # oder irgendein Platzhalter-Eintrag)
    assert _silence_reasons_replica(40.0, None, use_finite=True) == []


# === Runner ==================================================================

def main() -> None:
    tests = [
        ("Wurzel: kein rohes float(...iloc...) auf Close mehr",   test_root_source_no_bare_float_iloc_on_close),
        ("Wurzel: Felder bleiben bei Bruch unset (Guard da)",     test_root_source_fields_stay_unset_not_nan),
        ("Wurzel: kaputte Zelle -> None, kein Fake-Wert",         test_root_behavior_broken_cell_leaves_field_unset),
        ("Wurzel: valide Daten unverändert (Golden-Erwartung)",   test_root_behavior_all_valid_unchanged),
        ("LateRunner: None-Move -> kein Abschlag, aber geloggt",  test_late_runner_none_move_no_penalty_but_logged),
        ("LateRunner: RSI-Kriterium unabhängig scharf",           test_late_runner_rsi_channel_independent_of_move),
        ("LateRunner: bekannter heißer Move -> weiter Abschlag",  test_late_runner_known_hot_move_still_penalizes),
        ("LateRunner: bekannter ruhiger Move -> kein Log/Abschlag", test_late_runner_known_calm_move_no_penalty),
        ("LateRunner: None ≡ alter NaN-Zahlen-Ausgang",           test_late_runner_none_outcome_matches_old_worst_case_nan),
        ("Quelltext: LateRunner explizite Branch + Log",          test_late_runner_source_has_explicit_branch_and_log),
        ("PushFilter: alter isinstance-Bug — Richtung bestätigt", test_push_filter_old_isinstance_let_nan_through_wrong_direction),
        ("PushFilter: neue _finite()-Form NaN≡None",              test_push_filter_new_finite_rejects_nan_and_none_identically),
        ("PushFilter: Root-Fix allein macht isinstance schon ok", test_push_filter_root_fix_alone_already_fixes_isinstance_path),
        ("PushFilter: echter heißer Move silenced weiterhin",     test_push_filter_genuine_hot_move_still_silences),
        ("Quelltext: PushFilter nutzt _finite() statt isinstance", test_push_filter_source_uses_finite_not_isinstance),
        ("Quelltext: ki_agent hat lokalen _finite-Helper",        test_ki_agent_has_local_finite_helper),
        ("Gegenprobe: kein stiller Fake-Wert (coiled_spring-Muster)", test_no_silent_fake_value_introduced_anywhere),
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
