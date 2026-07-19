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
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

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
    MATERIAL_8K_ENABLED,
    SCORE_NORMALIZATION_VERSION,
    SI_VELOCITY_PUB_N_REPORTS,
)
import entry_score as entry_score_module  # Entry-Timing-Score (Shadow, pure)
import material_8k as material_8k_module   # §6c FDA-/materielle-8-K-Sammlung

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


def _compute_entry_past_return_5d(
    close_at_entry: float | None,
    close_5td_before: float | None,
) -> float | None:
    """5-Trading-Day-Past-Return VOR Entry (Hypothese-A-Vorbau, 05.07.2026).

    Formel: ``(close_at_entry / close_5td_before − 1) × 100`` (in %).

    **Split-Konsistenz-Pflicht:** BEIDE Eingaben MÜSSEN Adj-Close aus DERSELBEN
    yfinance-Fetch mit ``auto_adjust=True`` sein (analog zur ``_hist_stats``-
    yf.download-Fetch in ``generate_report.py:980-982``). Der Backtest-Record
    trägt zwar ein ``entry_price`` (roher Live-Snapshot zum Report-Zeitpunkt),
    aber das darf hier NICHT als Zähler verwendet werden — sonst mischt der
    Zähler eine andere Adjust-Epoche als der Nenner, und ein Reverse-Split
    zwischen ``entry_date - 5td`` und ``entry_date`` erzeugt einen künstlichen
    Return-Sprung. Reverse-Splits sind bei Squeeze-Small-Caps häufig — daher
    zwingend Adj-Close beidseitig.

    **Look-Ahead-Konvention (KRITISCH, Docstring einfriert):**
    Dieses Feld ist REINE Analyse-/Outcome-Persistenz für die Hypothese-A-
    Auswertung („trennt schwacher Past-Return bessere Forward-Returns?"). Es
    darf NIEMALS als Score-Feature oder Filter-Kriterium in ``score()`` /
    ``_compute_sub_scores`` / ``score_bonus`` / Push-Gating gelesen werden.
    Falls je live-scharfgeschaltet: der Score-Input MUSS aus dem Live-Enrichment-
    Dict (``stock["close_5td_before_entry"]``, live in ``_process_ticker``
    gesetzt) gelesen werden, NICHT aus dem Backtest-``entry_past_return_5d``.
    Sonst entsteht Trainings-/Test-Overlap bei rückwärts backgefüllten Alt-
    Records (Overfitting auf das Backfill-Sample).

    Args:
        close_at_entry: Adj-Close am Entry-Tag (aus yfinance auto_adjust=True).
        close_5td_before: Adj-Close 5 Trading-Days vor Entry (dito).

    Returns:
        Prozent-Return, gerundet auf 2 Dezimalen. ``None`` bei:
          - fehlendem/nicht-positivem ``close_5td_before`` (IPO wenige Tage
            vor Entry → keine 5-Bar-Historie verfügbar)
          - fehlendem ``close_at_entry`` (Delisting am Entry-Tag; sehr rar)

    **`None`-Semantik (keine 0.0-Overload wie bei max_gain):** ``None`` heißt
    hier IMMER „Datenlücke" (nicht „echter 0-Return"), weil eine echte
    Null-Bewegung numerisch ``0.0`` liefert (Zähler = Nenner). ``None`` ist
    also strikt „nicht ableitbar" — Auswertung filtert.
    """
    if close_at_entry is None or close_5td_before is None:
        return None
    try:
        num = float(close_at_entry)
        den = float(close_5td_before)
    except (TypeError, ValueError):
        return None
    if den <= 0:
        return None
    try:
        return round((num / den - 1.0) * 100.0, 2)
    except (ZeroDivisionError, ValueError):
        return None


def _compute_max_gain_pct(df_window) -> float | None:
    """Max-Gain vom rolling-Tief (Cummin-Low) zum Tageshoch (High) im Fenster.

    Spiegel zu ``_compute_max_drawdown``: identische Bar-Quelle (dieselbe
    High/Low-Slice), identisches ≤10-Handelstage-Fenster, identische
    Rolling-Window-Mechanik. Reine Outcome-Persistenz — kein Score-/Filter-/
    Push-Konsument (Look-Ahead strukturell ausgeschlossen, wie Drawdown).

    Args:
        df_window: DataFrame mit Spalten ``High``/``Low`` für die ersten ≤10
                   Handelstage seit Entry (inklusive Entry-Tag als Index 0).
    Returns höchsten %-Anstieg vom rolling-Tief zum Tageshoch oder ``0.0``
    bei zu wenig Daten. ``None`` bei Exception.

    HINWEIS zur ``0.0``-Semantik (analog Drawdown): ``0.0`` bedeutet
    entweder „wirklich kein Gewinn im Fenster" ODER „noch nicht genug
    Daten (<2 Bars)". Auswertung MUSS Reifegrad-Filter (Entry ≥10
    Trading-Days alt) parallel anwenden.
    """
    try:
        if df_window is None or df_window.empty or len(df_window) < 2:
            return 0.0
        roll_low = df_window["Low"].cummin()
        up = (df_window["High"] - roll_low) / roll_low * 100.0
        return round(float(up.max()), 2)
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


def _compute_si_velocity_pub(finra_history: list | None,
                             entry_date: "date | None",
                             n_reports: int | None = None) -> float | None:
    """Look-Ahead-freie SI-Änderungsrate über die letzten N PUBLIZIERTEN Reports.

    Namensgebung: der ``_pub``-Suffix grenzt bewusst gegen das ältere
    Displayfeld ``finra_data.si_shares_per_day`` in ``generate_report.py`` ab
    (dort: absolute Shares/Tag über die volle FINRA-History, kein pub_date-
    Filter, rein Anzeige + KI-Boost). Beide Größen koexistieren; verschiedene
    Zwecke, verschiedene Formel, verschiedene Look-Ahead-Eigenschaften.

    Look-Ahead-KERNFILTER (Pflicht): berücksichtigt AUSSCHLIESSLICH Reports mit
    ``pub_date <= entry_date``. Ein Report, dessen ``pub_date`` NACH
    ``entry_date`` liegt, wird verworfen — auch wenn sein ``settlement_date``
    davor lag. Das ist der Zweck des ``finra_publication_date``-Fundaments
    (#408): FINRA-Reports werden ~7 Handelstage NACH Settlement öffentlich
    (Rule 4560), ein Backtest zum Entry-Datum darf nur nutzen, was zu
    diesem Zeitpunkt PUBLIZIERT war.

    ``finra_history`` ist sortiert neueste → älteste (siehe
    ``generate_report.get_finra_short_interest``). Jeder Eintrag trägt
    ``pub_date`` (ISO-String) neben ``settlement_date``. Alt-Einträge ohne
    ``pub_date``-Feld werden als NICHT eligible gewertet (konservativ, keine
    Guess-Rekonstruktion).

    Formel: relative Änderung ``(si_newest - si_oldest) / si_oldest`` über
    das N-Report-Fenster (default ``SI_VELOCITY_PUB_N_REPORTS`` aus config.py).
    Gerundet auf 4 Nachkommastellen (analog ``_compute_si_slope_5d``).

    None-Semantik STRIKT (keine 0.0-Overload — im Gegensatz zu
    ``max_gain_pct``/``max_drawdown_pct``):
      • ``finra_history`` fehlt/leer                           → None
      • ``entry_date`` ist None                                 → None
      • ``n_reports < 2`` (kein Rate berechenbar)               → None
      • < ``n_reports`` Einträge mit ``pub_date <= entry_date`` → None
      • ``si_oldest <= 0`` (Division-Guard)                     → None

    LOOK-AHEAD-KONVENTION EINFROREN (analog ``entry_past_return_5d`` #402,
    ``days_to_earnings`` #404): dieses Feld ist REINE Analyse-/Outcome-
    Persistenz für die spätere si_velocity_pub-Edge-Auswertung. Es darf
    NIEMALS als Score-Feature/Filter-Kriterium aus dem Backtest-Field
    gelesen werden. Falls je live-scharfgeschaltet, MUSS der Score-Input
    aus dem Live-Enrichment-Dict ``s["finra_data"]["history"]`` berechnet
    werden — sonst Trainings-/Test-Overlap bei backgefüllten Alt-Records.
    """
    if n_reports is None:
        n_reports = SI_VELOCITY_PUB_N_REPORTS
    if entry_date is None or not finra_history or n_reports < 2:
        return None
    eligible: list[dict] = []
    for entry in finra_history:
        pub_iso = entry.get("pub_date")
        if not pub_iso:
            continue
        try:
            pub_d = datetime.strptime(pub_iso, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if pub_d <= entry_date:
            eligible.append(entry)
        if len(eligible) >= n_reports:
            break
    if len(eligible) < n_reports:
        return None
    si_new = eligible[0].get("short_interest") or 0
    si_old = eligible[n_reports - 1].get("short_interest") or 0
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


def _compute_score_delta_t1_raw(scores) -> float | None:
    """UNGECAPPTE ``last − prev`` aus den Sparkline-Setup-Scores (raw,
    oldest→newest). ``None`` bei < 2 Werten oder nicht-konvertierbar.

    Twin-Feld zu ``_compute_score_delta_t1`` (29.05.2026): identische
    Quelle + Guard-Logik, aber OHNE ±15-Clamp. Grund: das geclampte
    ``score_delta_t1`` zensiert die rohe Verteilung (raw-Range −57…+30
    laut CLAUDE.md) und ist retroaktiv nicht rekonstruierbar
    (score_history pruned + Sparkline-Index-Drift). Dieses Roh-Feld
    macht die Cap-vs-Perzentil-Entscheidung ~30.06. ehrlich. Shadow-
    Persist — kein Score-/Push-Effekt.
    """
    if not scores or len(scores) < 2:
        return None
    try:
        delta = float(scores[-1]) - float(scores[-2])
    except (TypeError, ValueError):
        return None
    return round(delta, 2)


def _compute_anomaly_push_age_h(latest_ts_iso, now_dt) -> float | None:
    """ROHES Push-Alter in Stunden VOR der Decay-Transform.

    ``None`` nur wenn gar kein (parsebarer) Timestamp vorliegt — identische
    Guard-Logik wie ``_compute_anomaly_freshness``, aber ohne
    ``max(1 − age_h/72, 0)``-Decay + 0-Floor. Grund: das transformierte
    ``anomaly_freshness`` quetscht alles > 72 h auf 0.0 (ununterscheidbar
    von „exakt 72 h"); die push_history-FIFO (Cap 100) macht das rohe
    age_h retroaktiv unrekonstruierbar. Dieses Feld erhält den Rohwert
    für eine spätere Decay-Steilheit-Kalibrierung (~30.06.). Shadow-
    Persist — kein Score-/Push-Effekt.
    """
    if not latest_ts_iso:
        return None
    try:
        ts = datetime.fromisoformat(latest_ts_iso)
    except (TypeError, ValueError):
        return None
    age_h = (now_dt - ts).total_seconds() / 3600.0
    return round(age_h, 2)


def _build_backtest_extension(s: dict, pool_position: int, pool_size: int,
                              agent_signals: dict, *,
                              compute_sub_scores_fn, safe_float_fn,
                              latest_push_ts_by_ticker: dict | None = None,
                              now_dt=None,
                              material_8k: dict | None = None,
                              entry_date: "date | None" = None) -> dict:
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
    # Twin-Roh-Feld (29.05.2026): ungecappt, gleiche Quelle/Guard.
    score_delta_t1_raw = _compute_score_delta_t1_raw(_spark.get("scores"))
    _now = now_dt or datetime.now(timezone.utc)
    _latest_push_ts = (latest_push_ts_by_ticker or {}).get(s["ticker"])
    anomaly_freshness = _compute_anomaly_freshness(_latest_push_ts, _now)
    # Twin-Roh-Feld (29.05.2026): rohes Push-Alter h, vor Decay/0-Floor.
    anomaly_push_age_h = _compute_anomaly_push_age_h(_latest_push_ts, _now)

    # Entry-Timing-Score (Shadow-Mode, 06.06.2026) — rechnet + persistiert,
    # KEIN Push/KEINE Anzeige/KEIN Score-/Filter-Effekt. Logik in entry_score.py
    # (pure, stdlib). push_history_available = Map gefüllt (Option (c)): bei
    # leerer Map (agent_state.json fehlt/korrupt → {}) fällt anomaly raus statt
    # alle Scores fälschlich zu drücken; bei gefüllter Map zählt anomaly=None
    # als echte 0 ("nie gepusht"). Flag wird mitpersistiert → Ausfall-Tage am
    # 30.06. filterbar.
    push_history_available = bool(latest_push_ts_by_ticker)
    entry_score, entry_components, entry_n_components = (
        entry_score_module.compute_entry_score(
            anomaly_freshness, score_delta_t1, sig.get("uoa_atm_ratio"),
            rvol_buildup, si_slope_5d,
            push_history_available=push_history_available,
        )
    )

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
        # Twin-Roh-Felder (Shadow-Persist 29.05.2026) für die ehrliche
        # Cap-vs-Perzentil-Auswertung ~30.06. Beide ungecappt/un-
        # transformiert, leer-tolerant (None). Schema-ADDITIV — KEIN
        # v4→v5-Bump (S10-Loader filtert == 4). Bestehende geclampte/
        # transformierte Twins (score_delta_t1 / anomaly_freshness)
        # bleiben unverändert.
        "score_delta_t1_raw":     score_delta_t1_raw,
        "anomaly_push_age_h":     anomaly_push_age_h,
        # Cost-to-Borrow-Persistenz (01.06.2026): CTB fließt seit #292
        # (iBorrowDesk) in den Setup-Score (Katalysator-Bonus), wurde aber
        # nicht ins backtest_history geschrieben → CTB-Edge-Auswertung
        # ~30.06. unmöglich. s["cost_to_borrow"] ist zum Schreibzeitpunkt
        # gesetzt (Borrow-Loop generate_report.py:15951 läuft vor dem
        # Append, identische top10-Dict-Objekte). LEGITIM-leer (None bei
        # Smallcaps ohne iBorrowDesk-Eintrag bzw. nicht-US-Ticker im
        # <3-Safety-Net-Fallback). Reiner Persist-Read, KEIN Score-Effekt.
        # Schema-ADDITIV — KEIN v4→v5-Bump (S10-Loader filtert == 4).
        # utilization bewusst NICHT mitpersistiert (keine Gratis-Quelle,
        # fließt nicht in den Score — fokussiert auf CTB).
        "cost_to_borrow":         s.get("cost_to_borrow"),
        # Entry-Timing-Score (Shadow-Mode 06.06.2026) — rechnet + persistiert,
        # KEIN Push/KEINE Anzeige/KEIN Score-/Filter-Effekt. Re-Norm-Aggregat
        # (Option B) der 5 normalisierten Komponenten (entry_score.py).
        # entry_components ist das Sub-Dict der 5 normalisierten Werte (0–100
        # oder None); entry_n_components = Anzahl eingehender Komponenten (0–5,
        # für die 30.06.-Frage „treffen dünne Scores schlechter?").
        # push_history_available (Option (c)): False = agent_state-leere Map
        # (Daten-Ausfall, anomaly fiel raus) → Ausfall-Tage 30.06. filterbar.
        # Schema-ADDITIV — KEIN v4→v5-Bump (S10-Loader filtert == 4).
        "entry_score":             entry_score,
        "entry_components":        entry_components,
        "entry_n_components":      entry_n_components,
        "push_history_available":  push_history_available,
        # KI-/Monster-Edge-Persistenz (11.06.2026): zwei additive Felder für
        # die 30.06.-Auswertung, ob der KI-Pfad eigenständigen Edge trägt.
        #   monster_score:    KI-×1.20/×0.80-Transform des Setup-Scores
        #                     (apply_monster_score, gen 3396). Zum Append-Zeit
        #                     IMMER gesetzt für Top-10, aber auf Alt-Einträgen
        #                     ABWESEND → leer-tolerant (None) → nur S10_OBSERVED,
        #                     KEIN MUSS-/LAG-Check.
        #   ki_signal_score:  roher ki_agent-Score (apply_agent_boost, gen 2937).
        #                     LEGITIM None, wenn der Ticker keinen agent_signals-
        #                     Eintrag hat → ebenfalls nur S10_OBSERVED.
        # Schema-ADDITIV — KEIN v4→v5-Bump (S10-Loader filtert == 4). KEIN
        # Push/keine Anzeige/kein Score-/Filter-Effekt (reiner Persist-Read).
        "monster_score":           (round(float(s.get("monster_score")), 2)
                                     if s.get("monster_score") is not None
                                     else None),
        "ki_signal_score":         (round(float(s.get("ki_signal_score")), 2)
                                     if s.get("ki_signal_score") is not None
                                     else None),
        # LLM-Fallback-Provenienz (16.07.2026): "llm" | "keyword" | "none" —
        # markiert, ob der ki_signal-News-Anteil vom Claude-Haiku-Call oder vom
        # Keyword-Fallback stammt (ANTHROPIC_API_KEY fehlt / Timeout / Parse).
        # Adressiert den ki_signal-Re-Test-Confound (Sample-Heterogenität, 15.07.:
        # LLM- vs. Keyword-gescorte News nicht unterscheidbar). Von
        # apply_agent_boost aufs Stock-Dict gesetzt (gen ~3226); hier read-through
        # in den Record (der entry.update-Merge Z. 1031 = die #411-Durchreichung).
        # LEGITIM None auf Alt-Records (forward-only, rückwirkend NICHT
        # rekonstruierbar) → nur S10_OBSERVED, KEIN MUSS/LAG. String, kein Round.
        # KEIN Push/keine Anzeige/kein Score-/Filter-Effekt (reiner Persist-Read).
        "ki_sentiment_source":     s.get("ki_sentiment_source"),
        # Conviction-Edge-Persistenz (28.06.2026, VORWÄRTS-ERHEBUNG):
        # additive zwei Felder für die spätere Edge-Validierung der
        # Conviction-Achse (Cockpit-Donut, ≥75-Push-Gating). Setzt voraus,
        # dass apply_conviction_scores(top10, ...) VOR dem Append-Aufruf
        # gelaufen ist (Reihenfolge-Tausch generate_report.py: Conviction-
        # Block VOR _append_backtest_entries). Bei Alt-Records ohne das
        # Feld bleibt der Reader-Default None — alle Konsumenten sind
        # .get(...)-tolerant.
        #   conviction_score:      0..100, Komposit aus 4 Komponenten
        #                          (setup 33 / earliness 28 / anomaly 28 /
        #                          regime 11, siehe compute_conviction_score).
        #   conviction_components: {setup, earliness, anomaly, regime} —
        #                          Sub-Objekt mit jeder Komponente einzeln.
        # Schema-ADDITIV — KEIN v4→v5-Bump (S10-Loader filtert == 4). KEIN
        # Push/keine Anzeige/kein Score-/Filter-Effekt (reiner Persist-Read).
        # S10-DISZIPLIN (Guardian-Korrektur 28.06.): beide Felder MÜSSEN in
        # S10_OBSERVED_FIELDS (Whitelist bekannter Felder) — sonst feuert
        # _s10_check_unknown_fields ab dem ersten Record mit diesen Feldern
        # ein dauerhaftes WARN. OBSERVED-Eintrag betrifft Alt-Records NICHT
        # (kein min_n/lag-Check, nur Auto-Detect-Suppression). NICHT in
        # S10_MUSS_FIELDS/_LAG_FIELDS: dort würde wegen der None-Belegung
        # auf Alt-Einträgen tatsächlich ein false-positive feuern. Präzedenz:
        # monster_score/ki_signal_score sind im selben OBSERVED-Block.
        "conviction_score":        (
            round(float(_cv.get("score")), 2)
            if isinstance(_cv := s.get("conviction"), dict)
               and _cv.get("score") is not None
            else None
        ),
        "conviction_components":   (
            {
                "setup":     _cvc.get("setup"),
                "earliness": _cvc.get("earliness"),
                "anomaly":   _cvc.get("anomaly"),
                "regime":    _cvc.get("regime"),
            }
            if isinstance(s.get("conviction"), dict)
               and isinstance(_cvc := (s.get("conviction") or {}).get("components"), dict)
            else None
        ),
        # Hypothese-A-Vorbau (05.07.2026, VORWÄRTS-ERHEBUNG, Stufe A):
        # 5-Trading-Day-Past-Return VOR Entry, aus Adj-Close beidseitig
        # (Split-Konsistenz). Zähler cur_close und Nenner
        # close_5td_before_entry stammen aus derselben yfinance
        # auto_adjust=True-Fetch (_hist_stats in generate_report.py:980).
        # Reine Analyse-/Outcome-Persistenz für die Reversal-Entry-
        # Auswertung „führt schwacher Past-Return zu stärkerem Forward-
        # Return?" — KEIN Score-/Filter-/Push-/Anzeige-Effekt.
        # Look-Ahead-Konvention (KRITISCH, siehe _compute_entry_past_return_5d-
        # Docstring): falls je live-scharfgeschaltet, MUSS der Score-Input
        # aus dem Live-Enrichment-Dict s["close_5td_before_entry"] gelesen
        # werden — NIE aus diesem Backfill-Field. Sonst Trainings-/Test-
        # Overlap bei rückwärts backgefüllten Alt-Records.
        # Schema-ADDITIV — KEIN v4→v5-Bump (S10-Loader filtert == 4). S10-
        # Disziplin: MUSS in S10_OBSERVED_FIELDS, NICHT in MUSS/LAG (None
        # legitim bei IPO < 6 Bars vor Entry).
        "entry_past_return_5d":    _compute_entry_past_return_5d(
            s.get("price"),
            s.get("close_5td_before_entry"),
        ),
        # Katalysator-Vorbau (05.07.2026, Stufe A — Hypothese H5): Kalendertage
        # bis zum nächsten AM Report-Tag bekannten Earnings-Termin. Snapshot
        # aus dem Live-Enrichment (``s["earnings_days"]``, gesetzt in Step 3c
        # von ``generate_report.py:16502-16540`` via EarningsWhispers-Override
        # bzw. yfinance-Fallback zu ``get_earnings_date``). Rohwert = Anzahl
        # KALENDERTAGE (`(edate - _today_et).days` in Zeile 16514) — konsistent
        # zum Live-Score-Konsumenten ``_compute_sub_scores`` (Z. 3746-3749,
        # Bucket-Schwellen ≤7 / ≤14). Handelstage würden Divergenz zum Live-
        # Score-Feld erzeugen und wären inkonsistent — daher Kalender.
        #
        # Point-in-time-Sauberkeit (Look-Ahead ausgeschlossen): Der Fetch läuft
        # AM Report-Tag; die Quelle (EarningsWhispers-Cache / yfinance.calendar)
        # kann keinen später-angekündigten Termin liefern, den es zum Fetch-
        # Zeitpunkt noch nicht gab. Der Wert ist der AM Entry-Tag bekannte
        # nächste Termin. Bei späterer Revision (Firma verschiebt Datum) bleibt
        # der Backtest-Snapshot AM Report-Tag → korrekt für die Frage „hat der
        # Score die AM Entry-Tag erwartete Earnings-Nähe berücksichtigt?".
        #
        # None-Semantik: legitim None bei fehlendem Earnings-Kalender (kein
        # Coverage bei EarningsWhispers UND yfinance leer; z. B. Micro-Caps
        # ohne öffentliche Earnings-Termine, ETFs). Auswertung filtert None.
        #
        # Look-Ahead-Konvention EINFROREN (analog entry_past_return_5d
        # aus PR #402): reine Analyse-/Outcome-Persistenz. NIEMALS als Score-
        # Feature/Filter-Kriterium in score()/_compute_sub_scores/score_bonus/
        # Push-Gating lesen. Live-Score liest bereits ``s["earnings_days"]``
        # aus dem Enrichment-Dict — dieser Pfad bleibt der KANONISCHE Score-
        # Read. Bei künftigem Score-Bau: aus Live-Enrichment, NIE aus dem
        # Backtest-Field days_to_earnings (sonst Trainings-/Test-Overlap).
        # Backfill der Alt-Records **STRUKTURELL NICHT MÖGLICH** — heutiger
        # Fetch liefert aktuelle Termine, nicht die vom damaligen Report-Tag.
        # Nur Vorwärts-Erhebung.
        #
        # S10-Klassifikation: MUSS in S10_OBSERVED_FIELDS (Lehre #388), NICHT
        # in MUSS/LAG (None legitim). Schema bleibt v4 (additiv, KEIN Bump).
        "days_to_earnings":        (
            int(s.get("earnings_days"))
            if s.get("earnings_days") is not None
            else None
        ),
        # si_velocity_pub (PR-3, 09.07.2026 — VORWÄRTS-ERHEBUNG, Look-Ahead-frei):
        # Relative Änderungsrate des Short Interest über die letzten
        # SI_VELOCITY_PUB_N_REPORTS (=3) PUBLIZIERTEN Reports vor entry_date.
        # Der ``_pub``-Suffix grenzt bewusst gegen das ältere Displayfeld
        # ``finra_data.si_shares_per_day`` in generate_report.py ab (dort: absolute
        # Shares/Tag über die volle FINRA-History, KEIN pub_date-Filter —
        # bleibt unverändert). Beide Größen koexistieren.
        #
        # Look-Ahead-Filter (Kern-Zweck): NUR Reports mit ``pub_date <=
        # entry_date`` — Reports, deren pub_date nach entry_date liegt,
        # werden ausgeschlossen, auch wenn ihr Settlement davor lag.
        # ``pub_date`` stammt aus der FINRA-history (PR #408, live via
        # ``scripts.business_days`` in generate_report — hier reiner Read,
        # kein Import: settlement + 7 Handelstage, holiday-robust dank #407
        # Karfreitag).
        #
        # Formel: ``(si[0] - si[N-1]) / si[N-1]`` (dimensionslos, gerundet
        # 4 Stellen). None bei < N eligible Reports, fehlendem entry_date,
        # oder si_oldest <= 0.
        #
        # LEGITIM leer (None) bei jungen Tickern mit < 3 SI-Reports oder
        # Tickern ohne FINRA-Coverage → nur OBSERVED, KEIN MUSS/LAG-Check.
        #
        # Look-Ahead-Konvention EINFROREN (analog entry_past_return_5d
        # #402, days_to_earnings #404): dieses Feld darf NIEMALS als
        # Score-Feature aus dem Backtest-Field gelesen werden — Live-
        # Score-Reads MÜSSEN aus ``s["finra_data"]["history"]`` neu
        # berechnen. Schema bleibt v4 (additiv, KEIN Bump).
        "si_velocity_pub":         _compute_si_velocity_pub(
            (s.get("finra_data") or {}).get("history"),
            entry_date,
        ),
        # Materielle-8-K-Sammelfeld (§6c, 19.07.2026, VORWÄRTS-ERHEBUNG,
        # forward-only): pro-Ticker vorab gesammeltes Wrapper-Dict
        # {collected, reason, cik, truncated, events[]} mit den point-in-time-
        # sauber gesammelten materiellen 8-K aus SEC-EDGAR. In DEMSELBEN
        # Record wie score (co-existent → corr(feature,score) auswertbar).
        # ``material_8k`` ist None wenn MATERIAL_8K_ENABLED=False ODER der
        # Ticker nicht in der Sammel-Liste war (Re-Run-Dedup) → Feld=None
        # (reader-tolerant). REINE Analyse-/Outcome-Persistenz, KEIN Score-/
        # Filter-/Push-/Anzeige-Effekt → nur S10_OBSERVED, KEIN MUSS/LAG.
        # Look-Ahead-Konvention EINGEFROREN (analog entry_past_return_5d):
        # NIEMALS als Score-Feature lesen. Schema bleibt v4 (additiv).
        "material_8k_events":      material_8k,
        "backtest_schema_version": 4,
    }


# ── Vintage-Guard (M1) — Backtest-Append-Schutz gegen stale Captures ────────
# Empirie 09.06.2026: 11/11 Cluster-Tage entstanden durch PRE-OPEN-Runs, die
# vor Session-Schluss des report_date die Vortags-Bar capturen und via
# existing_keys einfrieren. Gate: appende nur wenn (1) now_et >= report_date@
# 16:00 ET UND (2) die captured Tagesbar (s["bar_date"]) auf report_date
# datiert ist. REIN Backtest-Append — score_history/app_data/Pushes unberührt.
_VINTAGE_GUARD_LOG = "vintage_guard_log.jsonl"
_VINTAGE_EASTERN   = ZoneInfo("America/New_York")
_VINTAGE_MKT_OPEN  = time(9, 30)
_VINTAGE_MKT_CLOSE = time(16, 0)


def _vintage_gate_decision(report_date: str, bar_date, now_et: datetime
                           ) -> tuple[str, str]:
    """PURE Vintage-Guard-Entscheidung — env-frei, deterministisch.

    Returnt ``(action, reason)`` mit ``action`` ∈ {``"append"``, ``"skip"``}.

    - ``report_date``: ``dd.mm.yyyy``-String (wie persistiert).
    - ``bar_date``: ISO-String ``yyyy-mm-dd`` der captured Tagesbar, oder None.
    - ``now_et``: tz-aware ET-Zeitpunkt des Runs.

    Logik (Zeit zuerst, dann Bar-Datum):
    - ``now_et < report_date@16:00 ET`` → skip (``pre_open`` falls vor
      Markt-Open bzw. report_date noch nicht erreicht, sonst ``before_close``).
    - Zeit OK, ``bar_date`` fehlt/unparsbar → **append** (Missing-Regel,
      konservativ: lieber unsicherer Eintrag als stiller Datenverlust).
    - Zeit OK, ``bar_date != report_date`` → skip (``holiday_or_prior_bar``).
    - Sonst → append (``ok``).
    Garbage-report_date → append (``no_report_date``) — kein Gate ohne Datum.
    Datumsvergleich strikt auf ``date``-Objekten (kein String-Vergleich).
    """
    try:
        rd = datetime.strptime(report_date, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return "append", "no_report_date"
    rd_close = datetime(rd.year, rd.month, rd.day,
                        _VINTAGE_MKT_CLOSE.hour, _VINTAGE_MKT_CLOSE.minute,
                        tzinfo=_VINTAGE_EASTERN)
    if now_et < rd_close:
        if now_et.date() < rd or now_et.time() < _VINTAGE_MKT_OPEN:
            return "skip", "pre_open"
        return "skip", "before_close"
    if bar_date is None:
        return "append", "missing_bar"
    try:
        bd = datetime.strptime(str(bar_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "append", "missing_bar"
    if bd != rd:
        return "skip", "holiday_or_prior_bar"
    return "append", "ok"


def _log_vintage_skip(report_date: str, bar_date, now_et: datetime | None,
                      reason: str, ticker_count: int) -> None:
    """Append-only-Beobachtungs-Log nach ``vintage_guard_log.jsonl`` (eigene
    Datei, vom Digest/health_check NICHT gelesen — reines Sicherheitsnetz).
    ``now_utc`` MIT geloggt: ein Skip um ~22:xx UTC (Post-Close) mit
    Vortags-Bar ist VERDÄCHTIG (Bar-Lag-False-Skip eines legitimen Runs) und
    so im Log unterscheidbar vom harmlosen ~04:xx-UTC-Pre-Open-Skip.
    Fail-soft: Schreibfehler werden geloggt, nie re-raised."""
    try:
        rec = {
            "ts_utc":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "report_date":  report_date,
            "bar_date":     bar_date,
            "now_et":       now_et.isoformat() if now_et is not None else None,
            "now_utc":      (now_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                             if now_et is not None else None),
            "reason":       reason,
            "ticker_count": ticker_count,
            "schema_v":     1,
        }
        with open(_VINTAGE_GUARD_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("vintage_guard_log Schreibfehler — übersprungen: %s", exc)


def _append_backtest_entries(top10: list[dict], report_date: str,
                             pool_size: int = 0, *,
                             compute_sub_scores_fn, safe_float_fn,
                             now_et: datetime | None = None) -> int:
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

    # Vintage-Guard run-level Zeit-Gate (M1): kein Append vor Session-Schluss
    # (16:00 ET) des report_date. Früher Return VOR _load/_save → existing_keys
    # bleibt unbelegt → ein späterer korrekter Post-Close-Run appended frisch.
    # Spart außerdem den SPY/VIX-Fetch bei einem geskippten Pre-Open-Run.
    if now_et is None:
        now_et = datetime.now(_VINTAGE_EASTERN)
    if _rd is not None:
        _t_act, _t_reason = _vintage_gate_decision(
            report_date, _rd.isoformat(), now_et)
        if _t_act == "skip":   # nur Zeit-Gate kann hier greifen (bar==report)
            _log_vintage_skip(report_date, _rd.isoformat(), now_et,
                              _t_reason, len(top10))
            log.info("Vintage-Guard: Append übersprungen (%s, now_et=%s) — %s",
                     report_date, now_et.isoformat(), _t_reason)
            return 0

    history = _load_backtest_history()
    existing_keys = {(e.get("ticker"), e.get("date")) for e in history}
    # Vintage-Guard per-entry Bar-Datums-Tally (gesammelt, EIN Log nach Loop).
    _vg_skip_prior: list[tuple[str, str]] = []
    _vg_missing: list[str] = []
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

    # Materielle-8-K-Sammelfeld (§6c, forward-only, KEIN Score-Effekt). EINMAL
    # pro Run nur für Ticker OHNE bereits persistiertes (ticker, report_date).
    # Idempotenz-Präzisierung (Guardian): der Filter greift auf denselben
    # existing_keys-Schlüssel wie der Append-Loop → bereits persistierte Paare
    # lösen KEINEN EDGAR-Call aus. Ein Ticker, der am per-entry Vintage-Gate
    # hängt (noch NICHT persistiert), wird pro Run erneut gesammelt — bounded
    # und fail-soft, und im postclose-Pfad (einziger Aufrufer) praktisch selten
    # (Run-Level-Gate now_et>=16:00 ET ist erfüllt, bar_date=report_date). now_utc
    # = _now_dt = Report-Zeitpunkt → Point-in-time-Obergrenze (acceptance <=
    # _now_dt). Fail-soft: bei Ausfall bleibt der Wrapper leer (collected=False).
    material_8k_by_ticker: dict[str, dict] = {}
    if MATERIAL_8K_ENABLED:
        _m8k_tickers = [s["ticker"] for s in top10
                        if (s["ticker"], report_date) not in existing_keys]
        if _m8k_tickers:
            try:
                material_8k_by_ticker = material_8k_module.\
                    collect_material_8k_events(_m8k_tickers, now_utc=_now_dt)
            except Exception as _exc_m8k:
                log.warning("material_8k: Sammlung fehlgeschlagen "
                            "(fail-soft): %s", _exc_m8k)
                material_8k_by_ticker = {}

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
        # Vintage-Guard per-entry: Zeit ist hier bereits OK (Run-Level-Gate
        # oben). Bar-Datum prüfen — Vortags-/Feiertags-Bar → skip; fehlend →
        # append (Missing-Regel).
        _e_act, _e_reason = _vintage_gate_decision(
            report_date, s.get("bar_date"), now_et)
        if _e_act == "skip":
            _vg_skip_prior.append((s["ticker"], str(s.get("bar_date"))))
            continue
        if _e_reason == "missing_bar":
            _vg_missing.append(s["ticker"])
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
            # Hypothese-C-Vorbau (02.07.2026): additiv, KEIN v4-Bump.
            # Spiegel zu max_drawdown_pct — identische Slice + Rolling-
            # Update-Mechanik, reine Outcome-Persistenz (kein Score-Konsument).
            "max_gain_pct": 0.0,
            "market_regime":    market_regime,
            "vix_level":        vix_level,
            # PR-γ-1 Marker: 1 = pre-γ (raw-RVOL), 2 = post-γ (normalized).
            # Heutiger Wert immer 1 (RVOL_NORMALIZATION_ENABLED=False). Wird
            # in PR-γ-2 mit der Aktivierung auf 2 hochgezählt, damit die
            # 30.06.-Backtest-Auswertung beide Welten sauber trennen kann.
            "score_normalization_version": SCORE_NORMALIZATION_VERSION,
        }
        # Bahn B: Schema-Erweiterung (rückwärtskompatibel — alte Einträge
        # bleiben unverändert; neue bekommen die zusätzlichen Extension-Felder).
        entry.update(_build_backtest_extension(
            s, pool_position=pos, pool_size=pool_size,
            agent_signals=agent_signals,
            compute_sub_scores_fn=compute_sub_scores_fn,
            safe_float_fn=safe_float_fn,
            latest_push_ts_by_ticker=latest_push_ts_by_ticker,
            now_dt=_now_dt,
            # §6c: pro-Ticker vorab gesammeltes materielle-8-K-Wrapper-Dict
            # (None wenn disabled / Ticker nicht in der Sammel-Liste).
            material_8k=material_8k_by_ticker.get(s["ticker"]),
            # entry_date für si_velocity_pub Look-Ahead-Filter (PR-3).
            # ``_rd`` ist bereits am Funktions-Anfang (Wochenend-Schreib-
            # schutz Z. 889) aus ``report_date`` (dd.mm.yyyy) geparst; bei
            # unparsbarem Wert ist ``_rd = None`` → Helper returnt sauber
            # None (keine Guess-Rekonstruktion).
            entry_date=_rd,
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
        n_mg = 0
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
                # Spiegel-Update max_gain_pct (Hypothese-C-Vorbau, 02.07.2026).
                # Guard „in e" hält Alt-Records ohne das Feld unangetastet
                # (Backwards-Compat analog Drawdown-Backfill-Semantik).
                if "max_gain_pct" in e:
                    mg = _compute_max_gain_pct(df_since)
                    if mg is not None:
                        e["max_gain_pct"] = mg
                        n_mg += 1
            except Exception:
                continue
        log.info("Backtest-Schema (Stufe 1): max_drawdown aktualisiert für %d/%d, max_gain für %d/%d aktive Einträge",
                 n_dd, len(active_dd), n_mg, len(active_dd))

    # Vintage-Guard per-entry Skip-Beobachtung (ein Log je Grund-Klasse).
    if _vg_skip_prior:
        _sample_bar = _vg_skip_prior[0][1]
        _log_vintage_skip(report_date, _sample_bar, now_et,
                          "holiday_or_prior_bar", len(_vg_skip_prior))
        log.info("Vintage-Guard: %d Einträge mit Vortags-/Feiertags-Bar "
                 "übersprungen (%s, bar=%s, now_et=%s)",
                 len(_vg_skip_prior), report_date, _sample_bar,
                 now_et.isoformat() if now_et else "?")
    if _vg_missing:
        _log_vintage_skip(report_date, None, now_et,
                          "missing_bar", len(_vg_missing))

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

