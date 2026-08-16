"""Mock-Tests für die NaN-Dichtigkeit im Preis-Pfad (27.07.2026).

BEFUND (Read-only-Diagnose 27.07.): ``_fetch_position_market_data`` las
``float(hist["Close"].iloc[-1])`` OHNE ``dropna`` — eine letzte yfinance-Zeile
mit ``Close = NaN`` liefert dann ``price = NaN`` **ohne Exception**. NaN
verliert jeden Vergleich, deshalb ließen alle Guards der *negierten* Form
(``if not isinstance(x, float) or x <= 0``) ihn durch:

  • ``trend_break``: ``drop_pct = nan`` → beide Schwellen-Vergleiche False →
    else-Zweig → **crit=True bei price=null** (Fehlalarm auf allen 6 Positionen)
  • ``_build_phase2_positions_payload``: ``cur_price is not None`` war True →
    ``price_asof`` bekam einen FRISCHEN Stempel auf einen leeren Preis
    (NaN→null erst beim Serialisieren) → #483-Preserve und die Stale-Anzeige
    (#484) wurden ausgehebelt
  • ``yfinance_singletons``-Provider-Record war blind (deckte nur ^GSPC/FX ab)

FIX: ``_finite``-Prädikat + ``dropna(subset=["Close"])`` an der Quelle +
Positions-Fetches im Provider-Record.

Tests:
  1. _finite: None/NaN/Inf/bool/str → False, echte Zahlen → True
  2. Quelle: dropna(subset=["Close"]) steht VOR dem Close-Zugriff
  3. Quelle: nur-NaN-Historie → None (kein Preis erfunden) + Fail-Zähler
  4. Quelle: Fail-Zähler auch bei leerem Frame / Exception
  5. trend_break: NaN-Preis → available=False (KEIN crit) — der Fehlalarm
  6. trend_break: NaN-ma21 → available=False
  7. trend_break: echte Zahlen → Stufung unverändert (0 / warn / crit)
  8. Payload: NaN-cur_price → Preserve greift, asof bleibt ALT
  9. Payload: heutiger Ist-Zustand (null + frischer asof) ist nicht mehr
     erzeugbar — Fixture des Live-Bugs läuft nachweisbar anders
 10. Provider-Record: Positions-Fails fließen bei SYSTEMISCHEM Ausfall in die
     coverage, http_status bleibt von SPY/FX bestimmt (kein Dauer-Alarm durch
     EINEN delisteten Ticker — auch nicht bei nur 1–2 offenen Positionen)
 11. Reset: entfernt trend_break nur bei den gelisteten Tickern
 12. Reset: idempotent (zweiter Lauf ändert nichts)
 13. Reset: fremde Trigger/Felder/Ticker unangetastet, fail-soft bei Korruption
 14-19. Je ein expliziter NaN-Fall für die übrigen gehärteten Guards derselben
     Familie (_exit_p2_scale, score_decay, profit_lock, overheated,
     setup_erosion, pnl_frac-Quelle) — jeweils MIT Gegenprobe, dass die
     Stufung für endliche Werte unverändert bleibt.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GR = (ROOT / "generate_report.py").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "scripts"))


# ── Logik-Repliken (kein generate_report-Import: zieht yfinance/requests) ──
def _finite(v) -> bool:
    """Replik von generate_report._finite (Quelltext-Gleichheit via Test 1b)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


EXIT_TREND_BREAK_CRIT_PCT = 3.0


def _trend_break(metrics, cur_price):
    """Replik des gehärteten Triggers (Stufung unverändert)."""
    if not metrics:
        return {"score": 0, "warn": False, "crit": False, "available": False,
                "reason": "Position außerhalb top10_metrics"}
    ma21 = metrics.get("ma21")
    if not _finite(ma21) or ma21 <= 0:
        return {"score": 0, "warn": False, "crit": False, "available": False,
                "reason": "EMA21 nicht verfügbar (< 21 Handelstage History)"}
    if not _finite(cur_price) or cur_price <= 0:
        return {"score": 0, "warn": False, "crit": False, "available": False,
                "reason": "cur_price fehlt"}
    drop_pct = (float(ma21) - float(cur_price)) / float(ma21) * 100.0
    if drop_pct <= 0:
        score, warn, crit = 0, False, False
    elif drop_pct <= EXIT_TREND_BREAK_CRIT_PCT:
        score, warn, crit = 50, True, False
    else:
        score, warn, crit = 100, True, True
    return {"score": score, "warn": warn, "crit": crit, "available": True,
            "details": {"ma21": round(float(ma21), 4),
                        "price": round(float(cur_price), 4),
                        "drop_pct": round(drop_pct, 2)}}


def _resolve_price(cur_price, prev_pos, now_iso):
    """Replik des gehärteten Preserve-Blocks (#483 + NaN-Dichtigkeit)."""
    if _finite(cur_price):
        return cur_price, now_iso
    prev_price = prev_pos.get("current_price")
    if _finite(prev_price):
        return float(prev_price), prev_pos.get("price_asof")
    return None, None


# ── 1) _finite ────────────────────────────────────────────────────────────
def test_01_finite_predicate():
    for bad in (None, float("nan"), float("inf"), float("-inf"),
                True, False, "3.5", [], {}):
        assert _finite(bad) is False, f"_finite({bad!r}) müsste False sein"
    for good in (0, 1, -2, 3.5, 1e9):
        assert _finite(good) is True, f"_finite({good!r}) müsste True sein"


def test_01b_finite_source_matches_replica():
    m = re.search(r"def _finite\(v\) -> bool:(.*?)\n\ndef ", GR, re.S)
    assert m, "_finite fehlt in generate_report.py"
    body = m.group(1)
    assert "isinstance(v, bool)" in body, "bool-Ausschluss fehlt"
    assert "math.isfinite(v)" in body, "isfinite-Prüfung fehlt"


# ── 2-4) Quelle: dropna + Fail-Zähler ─────────────────────────────────────
def test_02_dropna_before_close_access():
    m = re.search(r"def _fetch_position_market_data\(.*?\n(.*?)\n\ndef ", GR, re.S)
    assert m, "_fetch_position_market_data nicht gefunden"
    body = m.group(1)
    i_drop = body.find('dropna(subset=["Close"])')
    i_read = body.find('float(hist["Close"].iloc[-1])')
    assert i_drop != -1, "dropna(subset=['Close']) fehlt"
    assert i_read != -1, "Close-Zugriff nicht gefunden"
    assert i_drop < i_read, "dropna muss VOR dem Close-Zugriff stehen"


def test_03_nan_only_history_returns_none():
    body = re.search(r"def _fetch_position_market_data\(.*?\n(.*?)\n\ndef ",
                     GR, re.S).group(1)
    # Nach dem dropna folgt ein empty-Check mit return None + Fail-Zähler.
    seg = body[body.find('dropna(subset=["Close"])'):]
    assert re.search(r"if hist\.empty:", seg), "empty-Check nach dropna fehlt"
    assert "_POS_SINGLETON_FAIL += 1" in seg, "Fail-Zähler fehlt"
    assert "return None" in seg, "return None nach leerem Frame fehlt"


def test_04_fail_counter_on_every_failure_path():
    body = re.search(r"def _fetch_position_market_data\(.*?\n(.*?)\n\ndef ",
                     GR, re.S).group(1)
    assert body.count("_POS_SINGLETON_FAIL += 1") >= 3, (
        "Fail-Zähler muss leeren Frame, nur-NaN und Exception abdecken")
    assert "_POS_SINGLETON_OK += 1" in body, "Erfolgs-Zähler fehlt"


# ── 5-7) trend_break ──────────────────────────────────────────────────────
def test_05_trend_break_nan_price_is_unavailable():
    r = _trend_break({"ma21": 2.0769}, float("nan"))
    assert r["available"] is False, "NaN-Preis muss unavailable sein"
    assert r["crit"] is False and r["warn"] is False, (
        "NaN darf NIE crit/warn erzeugen — genau das war der Fehlalarm")
    assert r["reason"] == "cur_price fehlt"


def test_06_trend_break_nan_ma21_is_unavailable():
    r = _trend_break({"ma21": float("nan")}, 2.28)
    assert r["available"] is False and r["crit"] is False


def test_07_trend_break_grading_unchanged():
    # Kurs ÜBER EMA21 → kein Bruch (der reale AMC-Fall vom 24.07.)
    r = _trend_break({"ma21": 2.0769}, 2.28)
    assert r["available"] is True and r["crit"] is False and r["score"] == 0
    assert r["details"]["drop_pct"] == -9.78
    # knapp darunter → warn
    r = _trend_break({"ma21": 100.0}, 98.0)
    assert (r["score"], r["warn"], r["crit"]) == (50, True, False)
    # deutlich darunter → crit
    r = _trend_break({"ma21": 100.0}, 90.0)
    assert (r["score"], r["warn"], r["crit"]) == (100, True, True)


# ── 8-9) Payload / Preserve ───────────────────────────────────────────────
def test_08_nan_price_preserves_old_value_and_asof():
    prev = {"current_price": 2.27, "price_asof": "2026-07-24T22:30:00Z"}
    price, asof = _resolve_price(float("nan"), prev, "2026-07-27T10:10:32Z")
    assert price == 2.27, "letzter guter Preis muss preserved werden"
    assert asof == "2026-07-24T22:30:00Z", "ALTER Stempel muss bleiben (Stale sichtbar)"


def test_09_live_bug_fixture_no_longer_reproducible():
    """Der heutige Ist-Zustand: current_price=null + FRISCHER price_asof."""
    prev_no_price = {"current_price": None, "price_asof": None}
    price, asof = _resolve_price(float("nan"), prev_no_price,
                                 "2026-07-27T10:10:32Z")
    assert price is None, "kein Preis erfunden"
    assert asof is None, (
        "FRISCHER Stempel auf leerem Preis war der Live-Bug — muss None sein")
    # Gegenprobe: mit der ALTEN Guard-Form wäre genau der Bug entstanden.
    old_guard_passes = float("nan") is not None
    assert old_guard_passes is True, (
        "Beleg: 'is not None' ließ NaN durch — deshalb _finite")


# ── 10) Provider-Record ───────────────────────────────────────────────────
def test_10_provider_record_counts_positions_but_gates_on_spy_fx():
    seg = GR[GR.find("_yfs_pos_total"):GR.find("run_phase=run_phase,",
                                               GR.find("_yfs_pos_total"))]
    assert "_POS_SINGLETON_OK" in seg and "_POS_SINGLETON_FAIL" in seg, (
        "Positions-Zähler müssen in den Record einfließen")
    assert "position_close_unusable" in seg, "Fehler-Detail fehlt"
    assert "http_status=200 if _yfs_hard_err is None else None" in seg, (
        "http_status darf NUR von SPY/FX abhängen (sonst Dauer-Alarm bei "
        "einem einzelnen delisteten Ticker)")
    # Positionen zählen NUR bei systemischem Ausfall in die harte Coverage
    assert "_pos_fails_are_systemic(_POS_SINGLETON_FAIL" in seg, (
        "Systemik-Gate fehlt — reine Proportionalität alarmiert bei kleinen "
        "Portfolios schon bei EINEM Fehlschlag")
    assert "_yfs_denom += _yfs_pos_total" in seg, "Nenner nicht proportional"


# Replik des Coverage-Pfads inkl. Systemik-Gate.
POS_FAIL_SYSTEMIC_MIN_COUNT = 2
POS_FAIL_SYSTEMIC_MIN_RATIO = 0.5


def _systemic(fail, total):
    if total <= 0 or fail <= 0:
        return False
    return (fail >= POS_FAIL_SYSTEMIC_MIN_COUNT
            and (fail / total) >= POS_FAIL_SYSTEMIC_MIN_RATIO)


def cov(spy, fx, ok, fail):
    items, denom = int(spy) + int(fx), 2.0
    if _systemic(fail, ok + fail):
        items += ok
        denom += ok + fail
    return (items / denom) * 100.0


def test_10b_coverage_math_proportional():
    assert cov(True, True, 6, 0) == 100.0    # alles gesund
    assert cov(True, True, 0, 6) == 25.0     # heutiger Fall → < 80 → Fail
    assert cov(True, True, 3, 3) == 62.5     # halbes Portfolio blind → Fail
    assert cov(True, True, 5, 1) == 100.0    # EIN Ticker tot → KEIN Fail
    assert cov(True, True, 4, 2) == 100.0    # 2 von 6 → unter Systemik-Ratio


def test_10c_small_portfolio_single_fail_is_never_an_alarm():
    """Guardian-Nit 27.07.: Tier 1 feuert OHNE Consecutive-Fenster
    (``n_consec >= 1`` → crit). Reine Proportionalität hätte bei 1–2 offenen
    Positionen einen einzelnen — womöglich transienten — Fehlschlag sofort
    unter 80 % gedrückt. Genau die Fehlalarm-Klasse, die dieser PR beseitigt.
    """
    # Ohne Gate wären das 66.7 % bzw. 75 % → crit. Mit Gate: 100 %.
    assert cov(True, True, 0, 1) == 100.0, "1 Position, 1 Fehlschlag → kein Alarm"
    assert cov(True, True, 1, 1) == 100.0, "2 Positionen, 1 Fehlschlag → kein Alarm"
    # Gegenprobe: die alte, rein proportionale Formel hätte alarmiert.
    def cov_old(spy, fx, ok, fail):
        return ((int(spy) + int(fx) + ok) / (2.0 + ok + fail)) * 100.0
    assert round(cov_old(True, True, 0, 1), 1) == 66.7
    assert cov_old(True, True, 1, 1) == 75.0
    # Systemisch bleibt systemisch, auch im kleinen Portfolio:
    assert cov(True, True, 0, 2) == 50.0, "beide Positionen blind → Fail"
    # Und die harte SPY/FX-Semantik ist davon unberührt:
    assert cov(False, True, 6, 0) == 50.0


def test_10d_systemic_predicate_edges():
    assert _systemic(0, 0) is False      # keine Positionen
    assert _systemic(0, 6) is False      # keine Fehlschläge
    assert _systemic(1, 1) is False      # EIN toter Ticker: nie Alarm
    assert _systemic(1, 6) is False
    assert _systemic(2, 6) is False      # 33 % < Ratio
    assert _systemic(2, 2) is True       # beide blind
    assert _systemic(3, 6) is True       # exakt die Hälfte
    assert _systemic(6, 6) is True       # der heutige Fall
    # Quelltext-Deckung der Replik
    assert "POS_FAIL_SYSTEMIC_MIN_COUNT = 2" in GR
    assert "POS_FAIL_SYSTEMIC_MIN_RATIO = 0.5" in GR
    assert "def _pos_fails_are_systemic(" in GR


def test_10e_counters_reset_in_main():
    """Zähler müssen — wie die übrigen Provider-Aggregatoren — beim
    main()-Start zurückgesetzt werden, sonst schleppt ein zweiter Aufruf im
    selben Prozess die Zählung des ersten mit (verfälschte coverage_pct)."""
    idx = GR.find("_provider_acct_reset(_EDGAR_13F_ACCT)")
    assert idx > 0, "Reset-Block nicht gefunden"
    seg = GR[idx:idx + 600]
    assert "_POS_SINGLETON_OK = 0" in seg and "_POS_SINGLETON_FAIL = 0" in seg, (
        "Positions-Zähler fehlen im main()-Reset-Block")


# ── 11-13) Flanken-Reset ──────────────────────────────────────────────────
def _state_fixture():
    return {"exit_push_dedupe": {
        "IONQ": {"last_active": ["trend_break"], "last_push_date": "2026-07-24",
                 "esc_alerted": False, "updated": "x"},
        "LENZ": {"last_active": ["trend_break", "catalyst"],
                 "last_push_date": "2026-07-27", "esc_alerted": False, "updated": "x"},
        "FRMM": {"last_active": [], "last_push_date": None,
                 "esc_alerted": False, "updated": "x"},
        "ZZZZ": {"last_active": ["trend_break"], "last_push_date": "2026-07-01",
                 "esc_alerted": False, "updated": "x"},
    }}


def test_11_reset_only_listed_tickers():
    from reset_exit_dedupe_trend_break import reset_dedupe
    st = _state_fixture()
    changed = reset_dedupe(st)
    d = st["exit_push_dedupe"]
    assert set(changed) == {"IONQ", "LENZ"}, f"unerwartet geändert: {changed}"
    assert d["IONQ"]["last_active"] == []
    assert d["LENZ"]["last_active"] == ["catalyst"], "fremder Trigger muss bleiben"
    assert d["ZZZZ"]["last_active"] == ["trend_break"], (
        "nicht gelisteter Ticker darf NICHT angefasst werden")
    # andere Felder unangetastet
    assert d["LENZ"]["last_push_date"] == "2026-07-27"
    assert d["IONQ"]["esc_alerted"] is False


def test_12_reset_idempotent():
    from reset_exit_dedupe_trend_break import reset_dedupe
    st = _state_fixture()
    reset_dedupe(st)
    snapshot = json.dumps(st, sort_keys=True)
    changed2 = reset_dedupe(st)
    assert changed2 == [], "zweiter Lauf darf nichts ändern"
    assert json.dumps(st, sort_keys=True) == snapshot, "State muss identisch bleiben"


def test_13_reset_failsoft_on_corruption():
    from reset_exit_dedupe_trend_break import reset_dedupe
    assert reset_dedupe({}) == []
    assert reset_dedupe({"exit_push_dedupe": None}) == []
    assert reset_dedupe({"exit_push_dedupe": {"IONQ": "kaputt"}}) == []
    assert reset_dedupe({"exit_push_dedupe": {"IONQ": {"last_active": None}}}) == []


# ── 14-18) NaN-Fall je weiterem gehärtetem Trigger ────────────────────────
# Dieselbe Guard-Familie wie trend_break: negierte Form ODER blankes
# ``is None`` / ``isinstance``. Keiner der fünf erzeugte einen FALSCHEN crit
# (die Skala clampt NaN zufällig auf 0), aber alle meldeten ``available:true``
# auf leeren Werten — dieselbe Lüge über die Datenlage. Für endliche Werte
# ist jede Härtung nachweislich identisch (je ein Gegenbeispiel-Assert).

def _scale(value, warn, crit):
    """Replik des gehärteten _exit_p2_scale."""
    if not _finite(value) or value <= 0:
        return 0, False, False
    if value >= crit:
        return 100, True, True
    if value >= warn:
        denom = max(1e-9, crit - warn)
        sub = 50.0 + 50.0 * (value - warn) / denom
        return int(round(min(100.0, max(50.0, sub)))), True, False
    sub = 50.0 * value / max(1e-9, warn)
    return int(round(min(50.0, max(0.0, sub)))), False, False


def _profit_lock(pnl_frac, peak_pnl_frac):
    """Replik des gehärteten Profit-Lock (nur PnL-Zweig)."""
    if not _finite(pnl_frac):
        return {"crit": False, "available": False, "reason": "kein aktueller Preis"}
    drawdown = None
    if _finite(peak_pnl_frac) and peak_pnl_frac > 0:
        drawdown = max(0.0, peak_pnl_frac - pnl_frac)
    _s, _w, c = _scale(drawdown, 0.15, 0.25)
    return {"crit": c, "available": True,
            "details": {"pnl_pct": round(pnl_frac, 4)}}


def _moves(chg2d_pct, chg3d_pct):
    """Replik der gehärteten Überhitzungs-Konvertierung."""
    m2 = (chg2d_pct / 100.0) if _finite(chg2d_pct) else None
    m3 = (chg3d_pct / 100.0) if _finite(chg3d_pct) else None
    return m2, m3, (m3 is not None)


def _to_f(v):
    """Replik des gehärteten setup_erosion-_to_f."""
    try:
        f = float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
    return f if _finite(f) else None


def test_14_scale_nan_is_zero_and_grading_unchanged():
    assert _scale(float("nan"), 0.15, 0.25) == (0, False, False), (
        "NaN muss explizit auf 0/False/False fallen")
    # Stufung für echte Zahlen unverändert
    assert _scale(None, 0.15, 0.25) == (0, False, False)
    assert _scale(0.0,  0.15, 0.25) == (0, False, False)
    assert _scale(0.30, 0.15, 0.25) == (100, True, True)
    assert _scale(0.15, 0.15, 0.25)[1] is True
    assert _scale(0.075, 0.15, 0.25) == (25, False, False)
    assert "if not _finite(value) or value <= 0:" in GR, (
        "_exit_p2_scale nicht gehärtet")


def test_15_score_decay_nan_score_is_unavailable():
    assert "if not _finite(cur_score) or len(entries) < 4:" in GR, (
        "score_decay: NaN-Score passiert weiterhin den Guard")
    assert "        if not _finite(ref):" in GR, (
        "score_decay: NaN-Referenzscore passiert weiterhin den Guard")
    # Verhalten: NaN-Score → available False, niemals crit
    cur = float("nan")
    assert not (_finite(cur) and len([1, 2, 3, 4]) >= 4)


def test_16_profit_lock_nan_pnl_is_unavailable():
    r = _profit_lock(float("nan"), 0.40)
    assert r["available"] is False and r["crit"] is False, (
        "NaN-PnL muss unavailable sein — sonst available:true bei pnl_pct:null")
    # Stufung für echte Zahlen unverändert: 40 % Peak, jetzt 5 % → 35 pp DD
    r = _profit_lock(0.05, 0.40)
    assert r["available"] is True and r["crit"] is True
    assert r["details"]["pnl_pct"] == 0.05
    # NaN-Peak wird ignoriert statt zu vergiften
    r = _profit_lock(0.05, float("nan"))
    assert r["available"] is True and r["crit"] is False
    assert "if not _finite(pnl_frac):" in GR, "profit_lock nicht gehärtet"


def test_17_overheated_nan_move_is_not_available():
    m2, m3, m3_av = _moves(float("nan"), float("nan"))
    assert m2 is None and m3 is None, "NaN-Move darf nicht als Zahl zählen"
    assert m3_av is False, (
        "move_3d_available:true bei move_3d_pct:null war die stille Lüge")
    # echte Zahlen unverändert
    m2, m3, m3_av = _moves(12.5, 30.0)
    assert (m2, m3, m3_av) == (0.125, 0.30, True)
    assert "if _finite(chg2d_pct) else None" in GR, "overheated nicht gehärtet"


def test_17b_overheated_none_and_nan_move_are_equivalent():
    """Verifiziert (15.08.2026-Diagnose-Folge): der change_2d/change_3d-
    Wurzelfix in get_yfinance_batch liefert jetzt ``None`` statt einer
    rohen NaN bei einer kaputten/fehlenden Close-Zelle. Dieser Konsument
    (bereits 27.07.2026 auf ``_finite()`` gehärtet) MUSS beide Eingänge
    identisch behandeln, sonst hätte der Root-Fix sein Verhalten verändert."""
    nan_result  = _moves(float("nan"), float("nan"))
    none_result = _moves(None, None)
    assert nan_result == none_result == (None, None, False), (
        nan_result, none_result)


def test_18_setup_erosion_nan_driver_counts_as_missing():
    assert _to_f(float("nan")) is None, "NaN muss wie 'kein Wert' wirken"
    assert _to_f(None) is None
    assert _to_f("kaputt") is None
    assert _to_f("12.5") == 12.5 and _to_f(3) == 3.0   # unverändert
    assert "return f if _finite(f) else None" in GR, "_to_f nicht gehärtet"
    assert "if not _finite(entry_v) or entry_v <= 0 or not _finite(cur_v):" in GR, (
        "_drop_and_stage nicht gehärtet")


def test_19_pnl_source_guard_is_finite():
    """``_compute_exit_state``: pnl_frac entsteht nur aus endlichen Preisen."""
    assert ("if (_finite(entry_price) and entry_price > 0\n"
            "            and _finite(cur_price) and cur_price > 0):") in GR, (
        "pnl_frac-Quelle nicht explizit NaN-dicht")
    # Gegenprobe: die alte truthy-Form war zufällig dicht, die neue ist es
    # nachweisbar — 0.0 fällt in BEIDEN Formen raus (keine Verhaltensänderung).
    for ep, cp in ((0.0, 5.0), (5.0, 0.0), (float("nan"), 5.0),
                   (5.0, float("nan"))):
        old = bool(ep and ep > 0 and cp and cp > 0)
        new = bool(_finite(ep) and ep > 0 and _finite(cp) and cp > 0)
        assert old == new is False, f"Divergenz bei ({ep}, {cp})"
    assert bool(_finite(2.0) and 2.0 > 0 and _finite(3.0) and 3.0 > 0) is True


# ── 20-23) Score-Pfad-Härtung: _gap_hold_pts + _rs_spy_pts (29.07.2026) ────
sys.path.insert(0, str(ROOT))  # config.py liegt im Repo-Root
import config  # noqa: E402  (nur Konstanten, kein yfinance)


def _gap_replica(cur_open, prev_close, price, *, hardened):
    """Replik von _gap_hold_pts. ``hardened=True`` = HEAD (_finite-Guard),
    ``hardened=False`` = alter is-None-Guard (Durchschlag-Gegenprobe)."""
    if hardened:
        if (not _finite(cur_open) or not _finite(prev_close)
                or not _finite(price) or prev_close <= 0):
            return None, "unknown", 0.0
    else:
        if cur_open is None or prev_close is None or price is None or prev_close <= 0:
            return None, "unknown", 0.0
    cur_open = float(cur_open); prev_close = float(prev_close); price = float(price)
    gap_size = cur_open - prev_close
    gap_pct = gap_size / prev_close * 100.0
    if gap_pct < config.GAP_THRESHOLD_PCT:
        return gap_pct, "no_gap", 0.0
    hold = cur_open + config.GAP_HOLD_FACTOR * gap_size
    if price > hold:
        return gap_pct, "strong_hold", float(config.GAP_PTS_STRONG_HOLD)
    if price < prev_close:
        return gap_pct, "fail", float(config.GAP_PTS_FAIL)
    return gap_pct, "weak_hold", float(config.GAP_PTS_WEAK_HOLD)


def _rs_replica(rs, *, hardened):
    """Replik von _rs_spy_pts."""
    if hardened:
        if not _finite(rs):
            return None, 0.0
    else:
        if rs is None:
            return None, 0.0
    rs = float(rs)
    T = config.RS_SPY_THRESHOLD_PCT
    clamped = max(-T, min(T, rs))
    return rs, float(round(clamped / T * config.RS_SPY_PTS_MAX))


def test_20_gap_hold_nan_is_unknown_zero():
    nan = float("nan")
    # NaN muss JETZT den unknown/0-Ausgang nehmen (nicht +2/−3):
    assert _gap_replica(nan, nan, 10.0, hardened=True) == (None, "unknown", 0.0)
    assert _gap_replica(nan, 100.0, 95.0, hardened=True) == (None, "unknown", 0.0)
    assert _gap_replica(50.0, nan, 55.0, hardened=True) == (None, "unknown", 0.0)
    # DURCHSCHLAG-Gegenprobe: der alte Guard erzeugte still weak_hold/fail —
    # der Fixture läuft nachweisbar ANDERS als vorher.
    assert _gap_replica(nan, nan, 10.0, hardened=False)[1] == "weak_hold"
    assert _gap_replica(nan, 100.0, 95.0, hardened=False)[1] == "fail"
    assert _gap_replica(nan, nan, 10.0, hardened=True)[1] != \
        _gap_replica(nan, nan, 10.0, hardened=False)[1]


def test_21_gap_hold_finite_grading_unchanged():
    # Gegenprobe endlich: jede Stufe unverändert (open 100, prev 90 → gap 11.1%).
    assert _gap_replica(100.0, 90.0, 200.0, hardened=True)[1] == "strong_hold"
    assert _gap_replica(100.0, 90.0, 95.0, hardened=True)[1] == "weak_hold"
    assert _gap_replica(100.0, 90.0, 80.0, hardened=True)[1] == "fail"
    # kleiner Gap (< Schwelle) → no_gap
    assert _gap_replica(100.0, 99.0, 101.0, hardened=True)[1] == "no_gap"
    # endliche Werte: hardened == unhardened (byte-gleich)
    for co, pc, pr in [(100.0, 90.0, 200.0), (100.0, 90.0, 80.0), (100.0, 99.0, 101.0)]:
        assert _gap_replica(co, pc, pr, hardened=True) == \
               _gap_replica(co, pc, pr, hardened=False)


def test_22_rs_spy_nan_is_none_zero():
    nan = float("nan")
    # NaN muss (None, 0) liefern — NICHT den +RS_SPY_PTS_MAX-Bonus:
    assert _rs_replica(nan, hardened=True) == (None, 0.0)
    # DURCHSCHLAG: der alte Guard klammerte NaN auf +max → falscher Bonus.
    assert _rs_replica(nan, hardened=False) == (nan, float(config.RS_SPY_PTS_MAX)) \
        or math.isnan(_rs_replica(nan, hardened=False)[0])
    assert _rs_replica(nan, hardened=False)[1] == float(config.RS_SPY_PTS_MAX)
    # Gegenprobe endlich: Stufung unverändert (± clamp), hardened == unhardened.
    for v in (10.0, -10.0, 2.5, 0.0):
        assert _rs_replica(v, hardened=True) == _rs_replica(v, hardened=False)
    assert _rs_replica(10.0, hardened=True)[1] == float(config.RS_SPY_PTS_MAX)
    assert _rs_replica(-10.0, hardened=True)[1] == float(-config.RS_SPY_PTS_MAX)


def test_23_source_uses_finite_at_gap_and_rs_and_source():
    # Quelle: _finite_cell an cur_open/prev_close (3 Fetch-Pfade × 2 Werte).
    assert '_finite_cell(hist["Open"], -1)' in GR
    assert '_finite_cell(hist["Close"], -2)' in GR
    assert '_finite_cell(df["Open"], -1)' in GR
    assert '_finite_cell(df2["Open"], -1)' in GR
    assert GR.count("_finite_cell(") >= 6, "erwartet ≥6 _finite_cell-Aufrufe"
    # Guard _gap_hold_pts: _finite statt is None.
    gap = re.search(r"def _gap_hold_pts\(.*?\n(.*?)\n\ndef ", GR, re.S).group(1)
    assert "not _finite(cur_open)" in gap and "not _finite(prev_close)" in gap
    assert "cur_open is None or prev_close is None" not in gap, "alter None-Guard noch da"
    # Guard _rs_spy_pts: _finite statt is None.
    rs = re.search(r"def _rs_spy_pts\(.*?\n(.*?)\n\ndef ", GR, re.S).group(1)
    assert "not _finite(rs)" in rs
    assert "if rs is None:" not in rs, "alter None-Guard in _rs_spy_pts noch da"


def main() -> int:
    tests = [
        ("01 _finite-Prädikat",                                  test_01_finite_predicate),
        ("01b _finite-Quelltext deckt Replik",                   test_01b_finite_source_matches_replica),
        ("02 dropna VOR Close-Zugriff",                          test_02_dropna_before_close_access),
        ("03 nur-NaN-Historie → None + Fail-Zähler",             test_03_nan_only_history_returns_none),
        ("04 Fail-Zähler auf allen Fehlerpfaden",                test_04_fail_counter_on_every_failure_path),
        ("05 trend_break: NaN-Preis → KEIN crit",                test_05_trend_break_nan_price_is_unavailable),
        ("06 trend_break: NaN-ma21 → unavailable",               test_06_trend_break_nan_ma21_is_unavailable),
        ("07 trend_break: Stufung unverändert",                  test_07_trend_break_grading_unchanged),
        ("08 NaN → Preserve + ALTER asof",                       test_08_nan_price_preserves_old_value_and_asof),
        ("09 Live-Bug-Fixture nicht mehr erzeugbar",             test_09_live_bug_fixture_no_longer_reproducible),
        ("10 Provider-Record: Positionen zählen mit",            test_10_provider_record_counts_positions_but_gates_on_spy_fx),
        ("10b Coverage proportional (1 tot ≠ Alarm)",            test_10b_coverage_math_proportional),
        ("10c Kleines Portfolio: 1 Fail ≠ Alarm",                test_10c_small_portfolio_single_fail_is_never_an_alarm),
        ("10d Systemik-Prädikat Randfälle",                      test_10d_systemic_predicate_edges),
        ("10e Zähler-Reset in main()",                           test_10e_counters_reset_in_main),
        ("11 Reset nur gelistete Ticker",                        test_11_reset_only_listed_tickers),
        ("12 Reset idempotent",                                  test_12_reset_idempotent),
        ("13 Reset fail-soft bei Korruption",                    test_13_reset_failsoft_on_corruption),
        ("14 _exit_p2_scale: NaN → 0, Stufung gleich",           test_14_scale_nan_is_zero_and_grading_unchanged),
        ("15 score_decay: NaN-Score → unavailable",              test_15_score_decay_nan_score_is_unavailable),
        ("16 profit_lock: NaN-PnL → unavailable",                test_16_profit_lock_nan_pnl_is_unavailable),
        ("17 overheated: NaN-Move → nicht available",            test_17_overheated_nan_move_is_not_available),
        ("17b overheated: None ≡ altes NaN-Verhalten",           test_17b_overheated_none_and_nan_move_are_equivalent),
        ("18 setup_erosion: NaN-Driver = fehlend",               test_18_setup_erosion_nan_driver_counts_as_missing),
        ("19 pnl_frac-Quelle explizit NaN-dicht",                test_19_pnl_source_guard_is_finite),
        ("20 _gap_hold_pts: NaN → unknown/0 (Durchschlag)",      test_20_gap_hold_nan_is_unknown_zero),
        ("21 _gap_hold_pts: endliche Stufung unverändert",       test_21_gap_hold_finite_grading_unchanged),
        ("22 _rs_spy_pts: NaN → (None,0), +bonus weg",           test_22_rs_spy_nan_is_none_zero),
        ("23 Quelle+Guard: _finite_cell/_finite verdrahtet",     test_23_source_uses_finite_at_gap_and_rs_and_source),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Total: {len(tests)} | Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
