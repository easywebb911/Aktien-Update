"""Backtest-History-Persistenz — aus generate_report.py extrahiert (Helper-Refactor 23.05.2026).

Reine Verschiebung der 12 Backtest-History-Funktionen (vormals generate_report.py
Z. 13463-13916). KEINE Logik-Aenderung.

Zwei generate_report-interne Abhaengigkeiten werden als Callable-Parameter
INJIZIERT statt importiert — vermeidet Zirkular-Import (generate_report
importiert dieses Modul), analog score_inflation_log.record_top10_inflation:
  * compute_sub_scores_fn  (= generate_report._compute_sub_scores)
  * safe_float_fn          (= generate_report._safe_float)
Beide werden nur von _build_backtest_extension gebraucht und von
_append_backtest_entries durchgereicht.

compute_score_confidence bleibt bewusst in generate_report.py (haengt an der
_SCORE_CONFIDENCE-globals()-Thematik) — NICHT Teil dieses Moduls.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import yfinance as yf

from config import (
    BACKTEST_ENABLED,
    BACKTEST_FILE,
    BACKTEST_MAX_DAYS,
    COMBO_BONUS,
    EARLINESS_TREND_LOG_WINDOW_DAYS,
    EARLINESS_TREND_MIN_FINRA_POINTS,
    EARLINESS_TREND_SI_SLOPE_CAP,
    EARLINESS_TREND_VOL_STAB_CAP,
    SCORE_NORMALIZATION_VERSION,
)

log = logging.getLogger(__name__)


def _load_backtest_history() -> list[dict]:
    """Lädt backtest_history.json als Liste. Silently [] bei fehlend/corrupt."""
    try:
        with open(BACKTEST_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_backtest_history(entries: list[dict]) -> None:
    """Schreibt backtest_history.json, sortiert nach (Datum, Ticker) für
    deterministische Git-Diffs. Pruning auf BACKTEST_MAX_DAYS erfolgt bereits
    beim Aufruf — hier nur Serialisierung."""
    with open(BACKTEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)


def _prune_backtest_history(entries: list[dict], max_days: int = None) -> list[dict]:
    """Entfernt Einträge älter als max_days Kalendertage (default BACKTEST_MAX_DAYS).

    Date-Format in entries: "DD.MM.YYYY" (matching generate_report's report_date).
    Unparsable dates werden belassen (defensiv) — keine Datenverluste durch
    Format-Wechsel. Bootstrap-Einträge (source == "bootstrap") sind
    prune-immun, damit backtest_bootstrap.py eingepflegte 365-Tage-Historie
    nicht nach 90 Tagen wieder gelöscht wird.
    """
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=max_days or BACKTEST_MAX_DAYS)
    kept: list[dict] = []
    for e in entries:
        if e.get("source") == "bootstrap":
            kept.append(e)
            continue
        d_str = e.get("date", "")
        try:
            ed = datetime.strptime(d_str, "%d.%m.%Y").date()
            if ed >= cutoff:
                kept.append(e)
        except (ValueError, TypeError):
            kept.append(e)   # keep unparseable entries to avoid data loss
    return kept


def _market_regime_from_spy(spy_hist=None) -> str:
    """SPY 50-Trading-Day-Trend → ``bull`` / ``bear`` / ``neutral``.

    Schwelle: ±5 % über die letzten 50 Handelstage. yfinance ``period="3mo"``
    liefert ~63 Handelstage; ``Close.iloc[-51]`` ist genau 50 Handelstage
    vor dem letzten Schlusskurs. Bei Daten- oder Fetch-Fehler → "neutral".
    """
    try:
        if spy_hist is None:
            spy_hist = yf.download("SPY", period="3mo",
                                   progress=False, threads=False)
        if spy_hist is None or spy_hist.empty:
            return "neutral"
        close = spy_hist["Close"].squeeze().dropna()
        if len(close) < 51:
            return "neutral"
        cur = float(close.iloc[-1])
        ref = float(close.iloc[-51])
        if ref <= 0:
            return "neutral"
        delta_pct = (cur - ref) / ref * 100.0
        if delta_pct >  5.0: return "bull"
        if delta_pct < -5.0: return "bear"
        return "neutral"
    except Exception as exc:
        log.debug("SPY market-regime fetch failed: %s", exc)
        return "neutral"


def _vix_close() -> float | None:
    """Letzter VIX-Schlusskurs (yfinance ^VIX). None bei Fetch-Fehler."""
    try:
        h = yf.download("^VIX", period="5d", progress=False, threads=False)
        if h is not None and not h.empty:
            return round(float(h["Close"].squeeze().dropna().iloc[-1]), 2)
    except Exception as exc:
        log.debug("^VIX fetch failed: %s", exc)
    return None


def _compute_max_drawdown(df_window) -> float | None:
    """Max-Drawdown vom rolling-Peak (Cummax-High) zur Tagestief (Low) im Fenster.

    Args:
        df_window: DataFrame mit Spalten ``High``/``Low`` für die ersten ≤10
                   Handelstage seit Entry (inklusive Entry-Tag als Index 0).
    Returns negativster %-Drop oder ``0.0`` bei zu wenig Daten.
    """
    try:
        if df_window is None or df_window.empty or len(df_window) < 2:
            return 0.0
        roll_peak = df_window["High"].cummax()
        dd = (df_window["Low"] - roll_peak) / roll_peak * 100.0
        return round(float(dd.min()), 2)
    except Exception:
        return None


# ── Earliness-Trend-Logging Helpers (pure, kein Side-Effect) ───────────────
# Prospektives Logging für die spätere AUC-Validierung der drei Sub-Signale,
# die aus dem heutigen backtest_history.json nicht rückwirkbar berechenbar
# sind (siehe Diagnose 13.05.2026, PR-Bericht „Trennschärfe Earliness").
# Reine Datensammlung — keine Conviction-Effekte, keine Score-Effekte.

def _compute_si_slope_5d(finra_history: list | None) -> float | None:
    """Relative Änderung short_interest neuester vs. ältester Wert im
    ersten 5-Punkte-Fenster.

    ``finra_history`` ist sortiert neueste → älteste (siehe
    ``get_finra_short_interest``). Liefert ``None`` wenn < 5 Punkte
    vorhanden oder ältester Wert nicht-positiv.
    """
    if not finra_history or len(finra_history) < EARLINESS_TREND_MIN_FINRA_POINTS:
        return None
    pts = finra_history[:EARLINESS_TREND_MIN_FINRA_POINTS]
    si_new = pts[0].get("short_interest") or 0
    si_old = pts[-1].get("short_interest") or 0
    if si_old <= 0:
        return None
    return round((si_new - si_old) / si_old, 4)


def _compute_rvol_buildup_5d(volumes_5d: list, avg_vol_20d: float | None) -> float | None:
    """Verhältnis Mittelwert-RVOL letzte 3 Tage / Mittelwert-RVOL erste 2 Tage.

    ``volumes_5d`` ist eine Liste der 5 Tagesvolumen (ältester → neuester).
    > 1 = Volumen baut auf (Earliness-Substrat), < 1 = abnehmend.
    ``None`` bei < 5 Werten, fehlendem ``avg_vol_20d`` oder Division-by-zero.
    """
    if (not volumes_5d
            or len(volumes_5d) < EARLINESS_TREND_LOG_WINDOW_DAYS
            or avg_vol_20d is None
            or avg_vol_20d <= 0):
        return None
    try:
        early_avg = sum(volumes_5d[:2]) / 2
        late_avg  = sum(volumes_5d[2:]) / 3
    except (TypeError, ValueError):
        return None
    rvol_early = early_avg / avg_vol_20d
    rvol_late  = late_avg / avg_vol_20d
    if rvol_early <= 0:
        return None
    return round(rvol_late / rvol_early, 3)


def _compute_vol_stability_5d(highs_5d: list, lows_5d: list,
                              closes_5d: list) -> float | None:
    """ATR-Range / Mittelwert-Close der letzten 5 Tage.

    Niedrig = stabile Preisrange (Coiled-Spring-Substrat). Niedrige Werte
    (z.B. 0.02 = 2 % Range) deuten auf Volatility-Compression hin.
    ``None`` bei unzureichenden Daten oder Division-by-zero.
    """
    w = EARLINESS_TREND_LOG_WINDOW_DAYS
    if (not highs_5d or not lows_5d or not closes_5d
            or len(highs_5d) < w or len(lows_5d) < w or len(closes_5d) < w):
        return None
    try:
        ranges = [h - l for h, l in zip(highs_5d, lows_5d)]
        atr = sum(ranges) / w
        avg_close = sum(closes_5d) / w
    except (TypeError, ValueError):
        return None
    if avg_close <= 0:
        return None
    return round(atr / avg_close, 4)


def _compute_coiled_spring_score(vol_stability: float | None,
                                 si_slope: float | None) -> float | None:
    """0..100 — Kombination niedrige Volatilität + positiver SI-Slope.

    Heuristische Kalibrierung (Caps via EARLINESS_TREND_*_CAP-Konstanten).
    Wird nach 14–30 Tagen Live-Daten neu kalibriert, sobald AUC-Vergleich
    gegen ``return_10d`` möglich. ``None`` bei fehlenden Eingaben.
    """
    if vol_stability is None or si_slope is None:
        return None
    # Stability invertieren (niedrig = gut). Cap bei VOL_STAB_CAP (10 %),
    # darüber → 0 Punkte für die Stability-Komponente.
    stab_cap = EARLINESS_TREND_VOL_STAB_CAP
    stability_inv = max(0.0, 1.0 - min(vol_stability, stab_cap) / stab_cap)
    # Slope: nur positiv zählt. Cap bei SLOPE_CAP (20 %).
    slope_cap = EARLINESS_TREND_SI_SLOPE_CAP
    slope_norm = max(0.0, min(si_slope, slope_cap) / slope_cap) if si_slope > 0 else 0.0
    return round(stability_inv * slope_norm * 100, 1)


def _compute_score_delta_t1(scores) -> float | None:
    """``last − prev`` aus den Sparkline-Setup-Scores (raw, oldest→newest),
    geclampt auf ±15. ``None`` bei < 2 Werten oder nicht-konvertierbar.

    Entry-Modul-Vorarbeit (Shadow-Persist) — kein Score-/Push-Effekt.
    """
    if not scores or len(scores) < 2:
        return None
    try:
        delta = float(scores[-1]) - float(scores[-2])
    except (TypeError, ValueError):
        return None
    return round(max(-15.0, min(15.0, delta)), 2)


def _compute_anomaly_freshness(latest_ts_iso, now_dt) -> float | None:
    """``max(1 − age_h/72, 0)`` aus dem jüngsten Push-Timestamp eines Tickers.

    ``None`` nur wenn gar kein (parsebarer) Timestamp vorliegt (Ticker nie
    gepusht). Push älter als 72 h → ``0.0`` (legit-leer, kein None) — das ist
    das echte Gegenargument-Signal „kein frischer Anomalie-Push".

    Entry-Modul-Vorarbeit (Shadow-Persist) — kein Score-/Push-Effekt.
    """
    if not latest_ts_iso:
        return None
    try:
        ts = datetime.fromisoformat(latest_ts_iso)
    except (TypeError, ValueError):
        return None
    age_h = (now_dt - ts).total_seconds() / 3600.0
    return round(max(1.0 - age_h / 72.0, 0.0), 4)


def _build_backtest_extension(s: dict, pool_position: int, pool_size: int,
                              agent_signals: dict, *,
                              compute_sub_scores_fn, safe_float_fn,
                              latest_push_ts_by_ticker: dict | None = None,
                              now_dt=None) -> dict:
    """Liefert das Schema-Erweiterungs-Dict (Bahn B) für einen Top-10-Eintrag.

    Felder, die retroaktiv NICHT rekonstruierbar sind:
      • Score-Komponenten + roher Pre-Smoothing-Score
      • Boni-Breakdown (combo, score-trend, agent-boost, perfect-storm, finra)
      • Pool-Kontext (Position + Größe — pool_member ist immer True für Top-10)
      • Source-Tracking aus den Fallback-Ketten

    Defaults:
      • Boni nicht aktiv  → 0.0  (Faktoren default 1.0)
      • Komponente nicht berechenbar → None  (NICHT 0)
      • Source unbekannt → "unknown"
    """
    sub = compute_sub_scores_fn(s) if s.get("short_float") is not None else None
    # Combo-Bonus aus den Bedingungen in score() rekonstruieren — Recompute
    # statt Refactor des autoritativen score()-Pfads.
    sf_val = safe_float_fn(s.get("short_float", 0))
    sr_val = safe_float_fn(s.get("short_ratio", 0))
    rv_val = safe_float_fn(s.get("rel_volume", 0))
    fd     = s.get("finra_data") or {}
    n_combo = sum([
        sf_val >= 30,
        sr_val >= 5,
        rv_val >= 2.0,
        fd.get("trend") == "up",
    ])
    combo_bonus = float(COMBO_BONUS) if n_combo >= 3 else 0.0
    # Perfect-Storm-Multiplikator: aus agent_signals.json pro Ticker (vom
    # KI-Agent persistiert in Bahn B). Default 1.0 wenn kein Signal vorhanden.
    sig = (agent_signals or {}).get(s["ticker"]) or {}

    # Earliness-Trend-Logging (prospektiv, KEIN Conviction-/Score-Effekt).
    # Vier optionale Felder + schema_version=4-Marker. Alle Werte None bei
    # unzureichenden Daten (< 5 FINRA-Punkte oder < 5 Trading-Tage).
    finra_hist = fd.get("history") or []
    hist_5d    = s.get("hist_5d") or []
    avg_vol_20 = s.get("avg_vol_20d") or 0
    volumes_5d = [d.get("volume", 0) for d in hist_5d]
    highs_5d   = [d.get("high",   0) for d in hist_5d]
    lows_5d    = [d.get("low",    0) for d in hist_5d]
    closes_5d  = [d.get("close",  0) for d in hist_5d]
    si_slope_5d   = _compute_si_slope_5d(finra_hist)
    rvol_buildup  = _compute_rvol_buildup_5d(volumes_5d, avg_vol_20)
    vol_stability = _compute_vol_stability_5d(highs_5d, lows_5d, closes_5d)
    coiled_spring = _compute_coiled_spring_score(vol_stability, si_slope_5d)

    # Entry-Score-Vorarbeit (PR vom 21.05.2026): zwei zusätzliche Felder fürs
    # spätere Entry-Timing-Modul (10.06.) — JETZT persistieren statt am
    # ~07.06., damit r10d-Outcomes bis zur Entry-AUC-Diagnose ~30.06. genug
    # Lag haben. Beide Felder sind LEGITIM-leer-tolerant (None möglich) und
    # bewusst NICHT in S10_MUSS_FIELDS — nur in S10_OBSERVED_FIELDS.
    _rv      = safe_float_fn(s.get("rel_volume"))
    _rv_yest = safe_float_fn(s.get("rel_volume_yesterday"))
    # Division-Guard analog _compute_rvol_buildup_5d. None bei fehlendem
    # Vortagswert ODER 0er-Nenner (frischer Ticker, kein Vortag).
    rvol_acceleration = (
        round(_rv / _rv_yest, 3)
        if (_rv > 0 and _rv_yest > 0)
        else None
    )

    # Entry-Modul-Vorarbeit (Shadow-Persist 25.05.2026) — kein Score-/Push-
    # Effekt, nur frühe Datensammlung. score_delta_t1 aus dem bereits am
    # Stock-Dict liegenden sparkline (apply_score_smoothing läuft VOR dem
    # Backtest-Append). anomaly_freshness aus dem per-Ticker durchgereichten
    # jüngsten Push-Timestamp (Snapshot zur Report-Zeit).
    _spark = s.get("sparkline") or {}
    score_delta_t1 = _compute_score_delta_t1(_spark.get("scores"))
    _now = now_dt or datetime.now(timezone.utc)
    _latest_push_ts = (latest_push_ts_by_ticker or {}).get(s["ticker"])
    anomaly_freshness = _compute_anomaly_freshness(_latest_push_ts, _now)

    return {
        "score_struct":         sub["struct"]   if sub is not None else None,
        "score_catalyst":       sub["catalyst"] if sub is not None else None,
        "score_timing":         sub["timing"]   if sub is not None else None,
        "score_raw":            round(float(s.get("score_raw") or 0), 2),
        "combo_bonus":          combo_bonus,
        "score_trend_bonus":    float(s.get("score_trend_bonus_pts") or 0.0),
        "agent_boost_factor":   float(s.get("agent_boost_factor") or 1.0),
        "perfect_storm_mult":   float(sig.get("combo_mult") or 1.0),
        "finra_bonus":          float(s.get("finra_bonus_pts") or 0.0),
        "pool_member":          True,
        "pool_position":        int(pool_position),
        "pool_size":            int(pool_size),
        "short_float_source":   s.get("short_float_source") or "unknown",
        "si_trend_source":      fd.get("si_trend_source") or "unknown",
        # Earliness-Trend-Logging (Schema v4 — kumulativ: v1 Original,
        # v2 Bahn B, v3 Bahn A2, v4 jetzt). Alte Einträge ohne diese
        # Felder bleiben unverändert (kein Backfill).
        "si_trend_5d_slope":      si_slope_5d,
        "rvol_buildup_5d":        rvol_buildup,
        "vol_stability_5d":       vol_stability,
        "coiled_spring_score":    coiled_spring,
        # Entry-Score-Vorarbeit (21.05.2026): RVOL-Acceleration + UOA-ATM-
        # Ratio aus dem KI-Agent-Signal-Dict. Beide LEGITIM-leer (None bei
        # fehlendem Vortagswert bzw. nicht-monitored Ticker). Schema-additiv,
        # kein backtest_schema_version-Bump.
        "rvol_acceleration":      rvol_acceleration,
        "uoa_atm_ratio":          sig.get("uoa_atm_ratio"),
        # Entry-Modul-Vorarbeit (Shadow-Persist 25.05.2026): zwei Felder
        # früh sammeln für die Entry-AUC ~30.06. Beide leer-tolerant
        # (None möglich). Schema-ADDITIV — KEIN v4→v5-Bump: der
        # S10-v4-Filter (health_check._s10_load_v4_entries, == 4) würde
        # neue Einträge sonst aus der Überwachung ausschließen.
        #   score_delta_t1:    aus s["sparkline"]["scores"] (last−prev, ±15)
        #   anomaly_freshness: aus push_history-ts (max(1−age_h/72, 0))
        "score_delta_t1":         score_delta_t1,
        "anomaly_freshness":      anomaly_freshness,
        "backtest_schema_version": 4,
    }


def _append_backtest_entries(top10: list[dict], report_date: str,
                             pool_size: int = 0, *,
                             compute_sub_scores_fn, safe_float_fn) -> int:
    """Fügt für jeden Top-10-Kandidaten einen neuen Backtest-Eintrag hinzu,
    dedupliziert nach (ticker, date), prunet auf 90 Tage und schreibt die Datei.
    Idempotent: wiederholter Aufruf am gleichen Tag ändert nichts.

    ``pool_size`` ist die Anzahl der enriched Kandidaten BEVOR der Top-10-Cut
    erfolgt — Kontext für spätere „Pool-Position vs. Return"-Auswertung.

    Returnt die Anzahl der NEU angehängten Einträge (``n_added``). Wird
    vom Health-Check S4 gelesen, um Premarket/Postclose-Disziplin zu
    überwachen (siehe ``health_check.py``).
    """
    if not BACKTEST_ENABLED:
        return 0
    # Wochenend-Schreibschutz (Diagnose 21.05.2026): manuelle workflow_
    # dispatch-Trigger am Sa/So erzeugen sonst Backtest-Einträge mit
    # Wochenend-Datum, deren Outcomes von ``ki_agent.update_backtest_returns``
    # PERMANENT geskippt werden (Yahoo liefert keine Sa/So-Closes → entry_dt
    # matcht nie gegen die Trading-Day-Index-Liste → continue-Branch). Stand
    # heutiger Backtest-History: 96 solcher Leichen.
    # Report-Anschauen am Wochenende läuft unverändert weiter — nur der
    # Backtest-Append wird geblockt. Bestehende Wochenend-Leichen werden NICHT
    # rückwirkend gelöscht (separater Cleanup-PR).
    try:
        _rd = datetime.strptime(report_date, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        _rd = None
    if _rd is not None and _rd.weekday() >= 5:
        log.warning("Wochenend-Eintrag (%s, %s) übersprungen — kein "
                    "Outcome-Lookup möglich (yfinance hat keine Sa/So-"
                    "Closes). Daily-Run/Workflow-Dispatch sollte werktags "
                    "laufen; manuelle Trigger am Wochenende sind kein "
                    "Backtest-Pfad.",
                    report_date, _rd.strftime("%A"))
        return 0
    history = _load_backtest_history()
    existing_keys = {(e.get("ticker"), e.get("date")) for e in history}
    # Agent-Signals einmalig laden (pro-Ticker-Lookup für perfect_storm_mult).
    try:
        with open("agent_signals.json", "r", encoding="utf-8") as fh:
            agent_signals = (json.load(fh) or {}).get("signals") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        agent_signals = {}

    # Push-History einmalig laden für anomaly_freshness (Shadow-Persist,
    # Entry-Modul-Vorarbeit). Self-contained analog agent_signals.json — nur
    # Lese-Snapshot, KEIN Push-/Score-Effekt. Map ticker→jüngster Push-ts;
    # ISO-8601 mit konstantem Berlin-Offset im 6-Tage-FIFO-Fenster sortiert
    # lexikalisch = chronologisch (DST-Wechsel im Fenster vernachlässigbar).
    latest_push_ts_by_ticker: dict[str, str] = {}
    try:
        with open("agent_state.json", "r", encoding="utf-8") as fh:
            _push_hist = (json.load(fh) or {}).get("push_history") or []
        for _pe in _push_hist:
            _pt, _pts = _pe.get("ticker"), _pe.get("ts")
            if not _pt or not _pts:
                continue
            # Nur echte Anomalie-Detektionen zählen für anomaly_freshness
            # (inkl. suppressed — Detektions-ts bleibt verwertbar). Exit-Pushes
            # (exit_p1/exit_p2) sind ein GEGENTEILIGES Signal (Positions-Ausstieg)
            # und earnings_immediate ist ein Event-Alarm, kein Anomalie-Signal —
            # beide dürfen die Freshness-Uhr NICHT setzen. kind ist flach (keine
            # anomaly_*-Subtypen), daher striktes ==.
            if _pe.get("kind") != "anomaly":
                continue
            if _pt not in latest_push_ts_by_ticker or _pts > latest_push_ts_by_ticker[_pt]:
                latest_push_ts_by_ticker[_pt] = _pts
    except (FileNotFoundError, json.JSONDecodeError):
        latest_push_ts_by_ticker = {}
    _now_dt = datetime.now(timezone.utc)

    # Bahn-A2-Stufe-1: Markt-Regime + VIX einmal pro Run abrufen. Werden auf
    # NEUE Einträge persistiert; die rolling Drawdown-Aktualisierung läuft
    # weiter unten für Einträge < 14 Kalendertage alt.
    _spy_hist = None
    try:
        _spy_hist = yf.download("SPY", period="3mo",
                                progress=False, threads=False)
    except Exception as _exc:
        log.debug("SPY pre-fetch for backtest schema failed: %s", _exc)
    market_regime = _market_regime_from_spy(_spy_hist)
    vix_level     = _vix_close()
    log.info("Backtest-Schema (Stufe 1): market_regime=%s, vix=%s",
             market_regime, vix_level)

    n_added = 0
    for pos, s in enumerate(top10, start=1):
        key = (s["ticker"], report_date)
        if key in existing_keys:
            continue
        fd = s.get("finra_data") or {}
        entry = {
            "date":          report_date,
            "ticker":        s["ticker"],
            "score":         round(float(s.get("score") or 0), 2),
            "entry_price":   round(float(s.get("price") or 0), 4),
            "entry_price_t1": None,   # wird am Tag T+1 von ki_agent gefüllt
            "short_float":   round(float(s.get("short_float") or 0), 2),
            "dtc":           round(float(s.get("short_ratio") or 0), 2),
            "rvol":          round(float(s.get("rel_volume") or 0), 3),
            "si_trend":      fd.get("trend", "no_data"),
            "return_3d":     None,
            "return_5d":     None,
            "return_10d":    None,
            "return_3d_t1":  None,
            "return_5d_t1":  None,
            "return_10d_t1": None,
            # Bahn A2 Stufe 1 — Schema-Erweiterung für spätere Auswertung.
            # max_drawdown_pct wird über 10 Handelstage rolling aktualisiert.
            "max_drawdown_pct": 0.0,
            "market_regime":    market_regime,
            "vix_level":        vix_level,
            # PR-γ-1 Marker: 1 = pre-γ (raw-RVOL), 2 = post-γ (normalized).
            # Heutiger Wert immer 1 (RVOL_NORMALIZATION_ENABLED=False). Wird
            # in PR-γ-2 mit der Aktivierung auf 2 hochgezählt, damit die
            # 30.06.-Backtest-Auswertung beide Welten sauber trennen kann.
            "score_normalization_version": SCORE_NORMALIZATION_VERSION,
        }
        # Bahn B: Schema-Erweiterung (rückwärtskompatibel — alte Einträge
        # bleiben mit 16 Feldern unverändert; neue bekommen 14 zusätzliche).
        entry.update(_build_backtest_extension(
            s, pool_position=pos, pool_size=pool_size,
            agent_signals=agent_signals,
            compute_sub_scores_fn=compute_sub_scores_fn,
            safe_float_fn=safe_float_fn,
            latest_push_ts_by_ticker=latest_push_ts_by_ticker,
            now_dt=_now_dt,
        ))
        history.append(entry)
        n_added += 1

    # Rolling Drawdown-Aktualisierung: pro Eintrag < 14 Kalendertage (≈10
    # Handelstage) alt die Ticker-History seit Entry holen und max_drawdown
    # neu berechnen. Ein Batch-Download für alle aktiven Ticker spart
    # Round-Trips; pro Entry wird die Datums-Slice ausgewertet.
    today_d = date.today()
    active_dd: list[tuple[dict, "datetime"]] = []
    for e in history:
        try:
            edate = datetime.strptime(e.get("date", ""), "%d.%m.%Y").date()
        except (TypeError, ValueError):
            continue
        # Nur Einträge mit dem neuen Feld aktualisieren — alte Einträge
        # ohne max_drawdown_pct bleiben unangetastet (Backwards-Compat).
        if "max_drawdown_pct" not in e:
            continue
        days_old = (today_d - edate).days
        if days_old <= 0 or days_old > 14:
            continue
        active_dd.append((e, edate))

    if active_dd:
        unique_tickers = sorted({e["ticker"] for e, _ in active_dd})
        try:
            dd_batch = yf.download(
                " ".join(unique_tickers), period="1mo",
                progress=False, threads=False,
                group_by="ticker" if len(unique_tickers) > 1 else "column",
            )
        except Exception as _exc:
            log.debug("Drawdown batch fetch failed: %s", _exc)
            dd_batch = None

        n_dd = 0
        for e, edate in active_dd:
            try:
                if dd_batch is None or dd_batch.empty:
                    continue
                df = (dd_batch[e["ticker"]] if len(unique_tickers) > 1
                      else dd_batch)
                if df is None or df.empty:
                    continue
                df_since = df[df.index.date >= edate].iloc[:11]
                dd = _compute_max_drawdown(df_since)
                if dd is not None:
                    e["max_drawdown_pct"] = dd
                    n_dd += 1
            except Exception:
                continue
        log.info("Backtest-Schema (Stufe 1): max_drawdown aktualisiert für %d/%d aktive Einträge",
                 n_dd, len(active_dd))

    history = _prune_backtest_history(history)
    # Stabil sortieren: neueste Einträge zuletzt → Git-Diff zeigt nur den Append
    def _sortkey(e):
        try:
            return (datetime.strptime(e.get("date",""), "%d.%m.%Y").date(),
                    e.get("ticker",""))
        except ValueError:
            return (datetime.min.date(), e.get("ticker",""))
    history.sort(key=_sortkey)
    _save_backtest_history(history)
    print(f"Backtest-History: +{n_added} neue Einträge, total {len(history)} "
          f"(Cut-off: {BACKTEST_MAX_DAYS} Tage)", flush=True)
    return n_added

