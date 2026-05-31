"""Gemeinsame Konfigurations-Konstanten für generate_report.py und ki_agent.py.

Änderungen an Schwellen, Timeouts und Score-Gewichten hier vornehmen —
nicht mehr in den einzelnen Skript-Dateien. Beide Skripte importieren die
Werte via ``from config import *``.
"""

import os
from pathlib import Path
from zoneinfo import ZoneInfo


# ═══════════════════════════════════════════════════════════════════════════
#  Gemeinsame HTTP-Header (Screener, RSS-Feeds, FINRA CDN)
# ═══════════════════════════════════════════════════════════════════════════
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ═══════════════════════════════════════════════════════════════════════════
#  generate_report.py — Filter, Score-Gewichte, Farbschwellen
# ═══════════════════════════════════════════════════════════════════════════

# ── Filter-Schwellen (Candidate-Pool) ────────────────────────────────────────
MIN_SHORT_FLOAT      = 15.0                # %  — Mindest-Short-Float (US)
MIN_REL_VOLUME       = 1.5                 # ×   — Mindest-Rel-Volumen US
MIN_REL_VOLUME_INTL  = 1.2                 # ×   — Mindest-Rel-Volumen internationale Watchlist
MAX_MARKET_CAP_B     = 2.0                 # Mrd. $ — Obergrenze (Small-Cap-Fokus, war 10.0)
MAX_MARKET_CAP       = MAX_MARKET_CAP_B * 1e9
MIN_PRICE            = 1.0                 # $   — Mindestkurs (Penny-Stock-Ausschluss)
MIN_SCORE            = 15.0                # Pkt — informativ; Karten unter diesem Wert bekommen Hinweis

# ── Internationales Screening ───────────────────────────────────────────────
# False: Yahoo-Screener nur für US + Watchlist-Scan deaktiviert
#        (persönliche Watchlist kann trotzdem intl Ticker enthalten — die
#         durchlaufen den is_us-Pfad mit Score-Cap 50).
# True:  Originalverhalten — DE/GB/FR/NL/CA Screener + JP/HK/KR Watchlist-Scan.
INTL_SCREENING_ENABLED = False

# ── Progressive Web App ────────────────────────────────────────────────────
# Service-Worker wurde 17.05.2026 entfernt (iOS-Safari-Cache-Quirks haben
# CSS-Merges stundenlang unsichtbar gehalten; Offline-Wert für iPhone-Trader
# = null). Lazy-Card-Rendering bleibt aktiv.
LAZY_CARDS_ENABLED = True
LAZY_CARDS_EAGER   = 3        # erste N Karten sofort vollständig rendern

# ── Karten-Cockpit-Redesign (Stage-Plan, ab 18.05.2026) ────────────────────
# Bloomberg-Stil-Cockpit-Layout fuer Top-10-Karten + Watchlist-Drawer:
# drei Sub-Score-Saeulen (Setup/Monster/KI) links, grosser Conviction-
# Donut rechts. Implementation in drei Stages:
#   Stage 1 (PR feat/card-cockpit-stage1-helpers, aktuell):
#     - _card_cockpit_html-Helper + CSS-Klassen .cockpit-* in head.jinja
#     - Flag OFF (CARD_COCKPIT_ENABLED=False) -> User sieht nichts.
#     - Helper-Code + Tests live, aber nirgends im Render-Pfad verdrahtet.
#   Stage 2 (Folge-PR):
#     - CARD_COCKPIT_ENABLED=True, v1+v2 Card-Render-Pfade
#       (_card + _build_card_ctx + card.jinja) auf Cockpit umgestellt.
#     - iPhone-Live-Verify Pflicht (Cache-Bust falls noetig).
#     - Watchlist-Drawer bekommt Cockpit automatisch via _wl_full_card_html.
#   Stage 3 (Folge-PR):
#     - Cleanup obsoleter .sb-row/.sb-num-CSS-Reste in Karten-Bereich.
#     - Methodik-Panel-Verwendung (.score-block-list .sb-lbl etc.) bleibt
#       unveraendert (eigene Konsumenten-Klasse).
CARD_COCKPIT_ENABLED = True

# ── app_data.json (kombinierter PWA-Data-Feed) ──────────────────────────────
# True: zusätzlich zu score_history.json + agent_signals.json wird eine
#       kombinierte app_data.json geschrieben — ein Fetch statt zwei.
GENERATE_APP_DATA_JSON = True

# ── Backtesting-Datensammlung ───────────────────────────────────────────────
# Bei jedem Daily-Run: Top-10-Kandidaten als Einträge in backtest_history.json
# Der KI-Agent aktualisiert return_3d / return_5d / return_10d, sobald 3/5/10
# Handelstage seit Entry vergangen sind. Einträge älter als BACKTEST_MAX_DAYS
# (Kalendertage) werden beim Schreiben automatisch entfernt.
BACKTEST_ENABLED          = True
BACKTEST_FILE             = "backtest_history.json"
BACKTEST_MAX_DAYS         = 90
BACKTEST_RETURN_WINDOWS   = [3, 5, 10]   # Handelstage → return_3d / _5d / _10d

# ── Sub-Scores (Struktur / Katalysator / Timing) ────────────────────────────
# Informative Aufspaltung des Gesamt-Scores in drei Themen-Komponenten.
# Der Gesamt-Score bleibt unverändert (score()-Funktion nicht angepasst);
# die Sub-Scores sind ergänzende Display-Metriken.
SHOW_SUB_SCORES     = True
SUB_STRUCT_MAX      = 40
SUB_CATALYST_MAX    = 35
SUB_TIMING_MAX      = 35   # vorher 30 — auf 35 erweitert für Gap+Hold-Beitrag

# Methodik-Anzeige: maximale Display-Punkte pro Sub-Score-Komponente.
# Werden ausschließlich von der Score-Methodik-Sektion gelesen (Auto-
# Generation, kein manueller HTML-Sync mehr nötig). Drift gegen score()
# bleibt manuell zu pflegen — die Werte sind die normalisierten Caps der
# jeweiligen Komponenten in `score()`.
SUB_SHORT_FLOAT_DISPLAY_PTS_MAX     = 32
SUB_DTC_DISPLAY_PTS_MAX             = 23
SUB_FLOAT_SIZE_DISPLAY_PTS_MAX      = 8
SUB_SI_TREND_DISPLAY_PTS_MAX        = 5
SUB_RVOL_DISPLAY_PTS_MAX            = 23
SUB_MOMENTUM_DISPLAY_PTS_MAX        = 14

# Sub-Score Katalysator — Komponenten-Punkte. Single source of truth für
# `_compute_sub_scores` UND die Methodik-Sektion (sonst Drift).
SUB_EARN_NEAR_PTS    = 15   # Earnings ≤ 7 Tage
SUB_EARN_MID_PTS     = 8    # Earnings ≤ 14 Tage
SUB_INSIDER_PTS      = 10   # sec_13f_note vorhanden
SUB_NEWS_PER_MATCH   = 5    # Pkt pro Keyword-Match (vor Decay-Gewicht)
SUB_NEWS_CAP         = 10   # Cap für news_pts insgesamt

# ── Agent-Boost (KI-Agent-Score als Multiplikator) ──────────────────────────
# Bei aktuellem Agent-Signal (<4h) mit hinreichend hohem KI-Agent-Score
# wird der Tages-Score multiplikativ angehoben:
#   Agent 25-49 → ×1.05    Agent 50-74 → ×1.10    Agent ≥75 → ×1.15
# Cap bei 100 bleibt.
AGENT_BOOST_ENABLED   = True
AGENT_BOOST_MAX_AGE_H = 4

# ── Pump & Dump Filter ──────────────────────────────────────────────────────
# Warnende Badges, kein Ausschluss. Zwei Erkennungspfade:
#   Flag 1: Kurs +30% in 5T UND Volumen-Rückgang (rvol_today < rvol_yesterday)
#   Flag 2: RSI > 80 UND Kurs +20% in 5T
PD_FILTER_ENABLED      = True
PD_GAIN_5D_THRESHOLD   = 0.30
PD_GAIN_5D_RSI_THRESHOLD = 0.20
PD_RSI_THRESHOLD       = 80

# ── Risk/Reward in KI-Analyse ───────────────────────────────────────────────
# Claude muss Stop-Loss, zwei Profit-Targets und R/R-Ratio ausgeben.
SHOW_RISK_REWARD          = True
RISK_REWARD_STOP_PCT      = 0.15   # 15% unter Entry
RISK_REWARD_TARGET1_PCT   = 0.20   # +20% erstes Ziel (Short-Covering)
RISK_REWARD_TARGET2_PCT   = 0.50   # +50% Squeeze-Szenario

# ── Short-Druck Indikator (Short Ladder Attack Detection) ────────────────────
# Erkennt koordinierten Verkaufsdruck: hoher SSR + fallender Kurs + hohes
# Volumen + hoher Short Float → klassisches Squeeze-Vorläufer-Signal.
SHORT_PRESSURE_SSR_MIN   = 0.60    # FINRA Daily SSR ≥ 60 %
SHORT_PRESSURE_CHG_MIN   = -0.08   # Kurs ≥ −8 %
SHORT_PRESSURE_CHG_MAX   = -0.02   # Kurs ≤ −2 %
SHORT_PRESSURE_SF_MIN    = 0.25    # Short Float ≥ 25 %
SHORT_PRESSURE_RVOL_MIN  = 1.5     # Rel. Volumen ≥ 1,5×
SHORT_PRESSURE_BONUS     = 5       # Katalysator-Score-Bonus

# ── Gamma Squeeze Detection ──────────────────────────────────────────────────
# Summiert Call-Open-Interest im Bereich ATM ±10 % über die nächsten 2
# Verfallstermine (≤ 14 Tage) und normalisiert auf durchschnittliches
# Handelsvolumen:  gamma_pressure = atm_call_oi × current_price / avg_vol_20d
# Schwellenwerte: ≥ 0.5 = möglich, ≥ 2.0 = wahrscheinlich.
GAMMA_SQUEEZE_ENABLED    = True
GAMMA_ATM_RANGE          = 0.10    # ATM ±10 % Strike-Fenster
GAMMA_MAX_DAYS_TO_EXPIRY = 14      # nur kurzlaufende Optionen zählen
GAMMA_NUM_EXPIRIES       = 2       # erste 2 Verfallstermine summieren
GAMMA_POSSIBLE_THRESHOLD = 0.5     # gamma_pressure ≥ 0.5 → möglich
GAMMA_LIKELY_THRESHOLD   = 2.0     # gamma_pressure ≥ 2.0 → wahrscheinlich
GAMMA_BONUS_POSSIBLE     = 8       # Katalysator-Bonus bei möglich
GAMMA_BONUS_LIKELY       = 15      # Katalysator-Bonus bei wahrscheinlich

# ── Borrow-Rate-Quelle (Cost-to-Borrow, %/Jahr) ──────────────────────────────
# Quellenwechsel 01.06.2026: ursprüngliche IBKR-.php-Scrape ist seit ~Mai 2026
# HTTP 404 (Daily-Log: "IBKR Borrow Rate: HTTP 404 — Seite nicht gefunden").
# Ersatz: iBorrowDesk-JSON-API (Aufbereitung derselben IBKR-Daten, pro-Ticker,
# 31.05. Live-verifiziert: HTTP 200, daily-Liste mit fee-Prozentsatz).
#
# Konstanten-Naming bleibt "IBKR_*" aus Aufrufer-Stabilität — der Code-Touch
# beschränkt sich auf den Fetcher-Body. Cleanup (Umbenennung in IBORROWDESK_*)
# später in eigenem Doku-/Refactor-PR. Score-Schwellen (LOW/HIGH/BONUS_*)
# bleiben unverändert — quellen-unabhängig.
IBKR_BORROW_ENABLED      = True
IBORROWDESK_URL_TEMPLATE = "https://iborrowdesk.com/api/ticker/{ticker}"
IBKR_BORROW_TIMEOUT      = 8        # (connect, read) Tupel-Timeout
IBKR_BORROW_LOW          = 10.0     # < 10 %/Jahr → grau (günstig)
IBKR_BORROW_HIGH         = 50.0     # > 50 %/Jahr → rot (sehr teuer für Shorts)
IBKR_BORROW_BONUS_HOT    = 8        # Katalysator-Bonus bei > 50 %/Jahr
IBKR_BORROW_BONUS_EXTREME = 15      # Katalysator-Bonus bei > 100 %/Jahr

# ── CTB + Utilization (Display-Only, kein Score-Einfluss) ────────────────────
# Stockanalysis.com zeigt auf der Stock-Page borrow-Metriken — Cost-to-Borrow
# (jährliche Leihgebühr in %) und Utilization (%-Anteil des Floats, der
# aktuell verliehen ist). Beide Werte fließen NICHT in den Score; sie werden
# nur in der Detail-Ansicht angezeigt und in app_data.json persistiert
# (für spätere Auswertung). Fallback bei CTB: IBKR-Borrow-Rate-Tabelle
# (gleiche Daten in $/Jahr-Form, IBKR_BORROW_URL). Bei Stockanalysis-
# 403/Parse-Fehler: silently None.
STOCKANALYSIS_BORROW_ENABLED = True
STOCKANALYSIS_BORROW_TIMEOUT = 8

# ── Put/Call-Ratio in Katalysator-Sub-Score ─────────────────────────────────
# PC-Ratio < 0.5 = bullisch (viele Calls) → +Bonus
# PC-Ratio > 1.5 = bearisch (viele Puts)  → -Malus
PC_RATIO_BULL_THRESHOLD = 0.5
PC_RATIO_BEAR_THRESHOLD = 1.5
PC_RATIO_BULL_BONUS     = 5
PC_RATIO_BEAR_MALUS     = 3

# ── Relative Stärke vs. SPY in Timing-Sub-Score ─────────────────────────────
# Squeezes sind oft idiosynkratisch — die Sektor-Korrelation ist gering, der
# breite Markt-Benchmark (SPY ≙ ^GSPC) trennt die Outperformer schärfer.
# Lineare Skalierung von 0 bis ±RS_SPY_THRESHOLD_PCT auf 0..±RS_SPY_PTS_MAX.
RS_SPY_THRESHOLD_PCT   = 5.0   # ±% relative Outperformance für volle Punkte
RS_SPY_PTS_MAX         = 3     # max. ±Punkte (symmetrisch)

# ── Gap & Hold (Eröffnungs-Stärke + Tagesverlauf) ────────────────────────────
# Misst die Stärke des Eröffnungs-Gaps und ob das Gap im Tagesverlauf
# gehalten wird (EOD). Lesart:
#   gap_pct       = (today_open  − yesterday_close) / yesterday_close × 100
#   hold_threshold = today_open + GAP_HOLD_FACTOR × (today_open − yesterday_close)
# Punkte:
#   today_close > hold_threshold      → strong_hold (+GAP_PTS_STRONG_HOLD)
#   today_close zwischen open/threshold → weak_hold (+GAP_PTS_WEAK_HOLD)
#   today_close < yesterday_close      → fail (Bull-Trap, GAP_PTS_FAIL = −3)
# Gilt nur bei gap_pct ≥ GAP_THRESHOLD_PCT; sonst no_gap (0).
GAP_THRESHOLD_PCT      = 3.0
GAP_HOLD_FACTOR        = 0.5
GAP_PTS_STRONG_HOLD    = 5
GAP_PTS_WEAK_HOLD      = 2
GAP_PTS_FAIL           = -3

# ── Historischer Squeeze-Check als Score-Malus ──────────────────────────────
# Falls der Ticker innerhalb der letzten 30 / 90 Tage bereits einen Squeeze
# durchlebt hat, ist das verbleibende Potenzial eingeschränkt → Abzug.
SQUEEZE_HIST_MALUS_30D = 5
SQUEEZE_HIST_MALUS_90D = 3


# ── SEC 13F (Institutional Holdings Snapshot) ──────────────────────────────
# False: fetch_sec_13f() wird im Daily-Run übersprungen.
#        Seit Monaten ~0 Treffer pro Run bei ~0,5 s Kosten; kein Wertbeitrag.
# True:  Reaktiviert den parallelen SEC-EDGAR-Scan für US-Top-10.
SEC_13F_ENABLED = False

# ── Zusätzliche Datenquellen (erweiterte Kandidaten-Vielfalt, 2026-04) ───────
# 1) Finviz-Screener als zusätzliche Quelle (nicht nur Fallback)
FINVIZ_SCREENER_ENABLED = True
FINVIZ_MAX_TICKERS      = 50
# 2) Stockanalysis.com Wochen-SI: für US-Top-10 überschreiben
STOCKANALYSIS_SI_ENABLED = True
STOCKANALYSIS_SI_MAX_AGE_DAYS = 7
# 3) EarningsWhispers-RSS für präzisere Earnings-Termine (einmal pro Run)
EARNINGSWHISPERS_ENABLED = False  # 18.05.2026 deaktiviert — RSS-Feed tot (Probe 4 + 12/13), keine maschinen-lesbare Alternative; yfinance trägt
# 4) Zusätzliche Yahoo-US-Screener (erweitert den Pool)
EXTRA_SCREENERS = ["undervalued_growth_stocks", "day_gainers"]

# ── Farbschwellen der Kennzahlenkacheln ──────────────────────────────────────
SF_GREEN   = 30.0   # % Short Float ≥ 30 → grün
SF_ORANGE  = 15.0   # % Short Float 15-29 → orange, <15 → rot
SR_GREEN   =  8.0   # Days to Cover ≥ 8 → grün
SR_ORANGE  =  3.0   # Days to Cover 3-7 → orange, <3 → rot
RV_GREEN   =  3.0   # Rel. Volumen ≥ 3× → grün
RV_ORANGE  =  1.5   # Rel. Volumen 1.5-2.9 → orange, <1.5 → rot
MOM_GREEN  =  5.0   # Kursmomentum ≥ +5 % → grün
MOM_ORANGE = -5.0   # Kursmomentum -5…+5 % → orange, <-5 → rot

# ── FINRA-Trend-Bonus / Kombinationsbonus ────────────────────────────────────
FINRA_BONUS_MAX          = 5    # max. Bonus bei steigender FINRA-Short-Vol
FINRA_ACCELERATION_BONUS = 7    # erhöhter Bonus bei Beschleunigung
COMBO_BONUS              = 5    # Synergie-Bonus ≥ 3 von 4 Faktoren stark (generate_report.score)

# ── KI-Agent Perfect-Storm Multiplikator ─────────────────────────────────────
# Gestaffelter Score-Multiplikator wenn mehrere Trigger-Typen gleichzeitig
# aktiv sind (RVOL ≥ 2× · |chg| ≥ 3 % · News-Score ≥ 10 · Earnings ≤ 7 d).
# Belohnt synchrones Ausschlagen mehrerer Signale exponentiell statt linear.
COMBO_MULT_2     = 1.10   # 2/4 Trigger
COMBO_MULT_3     = 1.20   # 3/4 Trigger
COMBO_MULT_4     = 1.35   # 4/4 — Perfect Storm
COMBO_RVOL_MIN   = 2.0
COMBO_CHG_MIN    = 3.0
COMBO_NEWS_MIN   = 10

# ── StockTwits Sentiment (öffentliche Read-API) ──────────────────────────────
# https://api.stocktwits.com/api/2/streams/symbol/{SYM}.json
# Bei Rate-Limit (200 req/h pro IP) oder HTTP-Fehler → stiller 0-Pkt-Fallback.
STOCKTWITS_ENABLED      = False  # 18.05.2026 deaktiviert — Production-Fails seit 15.05. (14/14 parallel), Sentiment-Bonus nicht zentral
STOCKTWITS_TIMEOUT      = 5    # Sekunden
STOCKTWITS_BULL_STRONG  = 15   # Bullish-Ratio > 0.70 + Volume > 10/h
STOCKTWITS_BULL_WEAK    = 8    # Bullish-Ratio > 0.60
STOCKTWITS_BEAR_MALUS   = 5    # Bearish-Ratio > 0.70 → -Pkt

# ── Float-Turnover (Timing-Sub-Signal) ───────────────────────────────────────
# Vol/Float misst absolute Marktdurchdringung pro Tag — komplementär zu RVOL
# (relative Abweichung vs. 20-Tage-Schnitt). Punkte zählen on-top zum Score
# und werden im Timing-Sub-Score-Block aufaddiert (SUB_TIMING_MAX 25 → 30).
FLOAT_TURNOVER_LOW       = 0.5
FLOAT_TURNOVER_MID       = 1.0
FLOAT_TURNOVER_HIGH      = 2.0
FLOAT_TURNOVER_PTS_LOW   = 3
FLOAT_TURNOVER_PTS_MID   = 6
FLOAT_TURNOVER_PTS_HIGH  = 10

# ── News-Sentiment-Decay nach Alter ──────────────────────────────────────────
# Frische News scoren stärker als alte: pro News-Item wird ein Tages-Alter
# berechnet (basierend auf dem ``ts``-Feld aus dem RSS-pubDate) und das
# Keyword-Match mit dem entsprechenden Gewicht multipliziert. Items älter
# als die größte Stufe → weight 0.0 (effektiv ignoriert). Fallback bei
# fehlendem/korrupten ``ts``: weight 0.5 (Mittelwert, statt Item zu
# verwerfen). Items aus der „Zukunft" (negative Alter durch Clock-Drift)
# bekommen weight 1.0.
NEWS_DECAY_WEIGHTS       = {
    0: 1.0,   # heute
    1: 0.7,   # gestern
    2: 0.4,   # vorgestern
    3: 0.2,   # 3 Tage alt
}
NEWS_DECAY_FALLBACK      = 0.5   # weight bei fehlendem/parse-fehlerhaftem ts

# ── Unusual Options Activity (UOA) — yfinance Options-Chain ──────────────────
# Bewertet ungewöhnliche Optionsaktivität pro Ticker:
#   • Call-Vol/OI > 5× im ATM-Bereich (±10 % Strike)  → +UOA_ATM_STRONG Pkt
#   • Call-Vol/OI > 3× im ATM-Bereich (±10 % Strike)  → +UOA_ATM_WEAK   Pkt (5× Vorrang)
#   • Gesamt-Call-Volume > 2× Gesamt-Put-Volume       → +UOA_CP_BIAS    Pkt
# Genutzt in compute_signal(); Werte landen in agent_signals.json (uoa_score,
# uoa_drivers) und werden im nächsten Daily-Run auf der Kachel sichtbar.
UOA_ENABLED             = True
UOA_EXPIRATION_MAX_DAYS = 30
UOA_ATM_BAND_PCT        = 0.10  # ±10 % um Spot
UOA_VOL_OI_STRONG       = 5.0   # Call-Vol/OI Schwelle stark
UOA_VOL_OI_WEAK         = 3.0   # Call-Vol/OI Schwelle schwach
UOA_CP_RATIO            = 2.0   # Call/Put-Volume Schwelle
UOA_ATM_STRONG          = 20    # Pkt bei Vol/OI > UOA_VOL_OI_STRONG
UOA_ATM_WEAK            = 10    # Pkt bei Vol/OI > UOA_VOL_OI_WEAK
UOA_CP_BIAS             = 10    # Pkt bei Call/Put > UOA_CP_RATIO

# ── RVOL High-Alert + Velocity (KI-Agent) ────────────────────────────────────
# Zusätzliche Boni über die bestehenden TRIGGER_RVOL_2X/4X-Stufen hinaus:
#   ≥ 3 ×  → +RVOL_HIGH_BONUS    Pkt + ⚡-Marker im Driver
#   ≥ 5 ×  → +RVOL_EXTREME_BONUS Pkt + 🚀-Marker
# Velocity-Alert: wenn der RVOL eines Tickers zwischen zwei KI-Agent-Runs
# (alle 2 h) um Faktor ≥ RVOL_VELOCITY_FACTOR steigt → +RVOL_VELOCITY_BONUS.
RVOL_HIGH_THRESHOLD     = 3.0
RVOL_HIGH_BONUS         = 10
RVOL_EXTREME_THRESHOLD  = 5.0
RVOL_EXTREME_BONUS      = 15
RVOL_VELOCITY_FACTOR    = 1.5   # current / previous
RVOL_VELOCITY_BONUS     = 8
RVOL_VELOCITY_MIN       = 1.5   # current_rvol-Mindestschwelle für Velocity-Check

# ── RVOL-Normalisierung (Score-Inflation-Fix, Phase 1 PR-α, OFF by default) ──
# Behebt premarket→postclose-Score-Drift: 20d-Avg-RVOL ist im premarket-Run
# strukturell unter-skaliert (today_vol kumuliert intraday, 20d-Nenner fix).
# Diagnose 16.05.2026: Mean Drift +3.87 Pkt, Median +1.42 Pkt, dramatische
# Spitzen +40.2 Pkt (DMRC 13.05.2026 RVOL 0.4→2.4).
#
# Schalter-Logik (`generate_report.py:_normalize_rvol`):
#   - ENABLED=False (Default): return raw_vol / avg_20d (Status quo)
#   - ENABLED=True:
#       premarket (< 13:30 UTC): raw_vol / (avg_20d × PREMARKET_RVOL_SCALER)
#       intraday  (13:30-20:00): raw_vol / (avg_20d × max(h/6.5, INTRADAY_RVOL_MIN_FRAC))
#       postclose (≥ 20:00 UTC): raw_vol / avg_20d (unverändert, EOD-Wahrheit)
#
# PR-α (diese PR): Helper + Konstanten, ENABLED=False. Kein Verhaltens-Drift.
# PR-β: 14 Tage Empirik-Daten sammeln über rvol_20d in agent_signals.json.
# PR-γ: Aktivierung (ENABLED=True) nach Daten-Validierung + ggf. PREMARKET_RVOL_SCALER-
#        Re-Kalibrierung statt 0.10-Daumenwert.
RVOL_NORMALIZATION_ENABLED = False
PREMARKET_RVOL_SCALER      = 0.10  # Premarket-Volumen typisch ~10 % des Tagesvolumens
INTRADAY_RVOL_MIN_FRAC     = 0.10  # Floor gegen Division-Explosion in ersten Open-Minuten

# Backtest-Marker für die Score-Normalisierungs-Welle (PR-γ-1, additiv).
# Jeder neue backtest_history.json-Eintrag traegt diesen Wert. Damit die
# 30.06.-Auswertung pre-γ (raw-RVOL) sauber von post-γ (normalized-RVOL)
# trennen kann — sonst Confounder analog Bootstrap-vs-Live (#238).
# 1 = pre-γ (heutiger Stand, RVOL_NORMALIZATION_ENABLED=False)
# 2 = post-γ (wird in PR-γ-2 auf 2 gesetzt zusammen mit ENABLED=True)
SCORE_NORMALIZATION_VERSION = 1

# Soll-Wert für das Daten-Reife-Gate (Health-Check S13). Deklariert den
# ERWARTETEN Zustand von RVOL_NORMALIZATION_ENABLED. Solange γ-2 bewusst
# aus ist, Soll == Ist == False → Gate still. Sobald γ-2 laufen SOLL, hier
# auf True setzen — bleibt das Flag oben dann noch False, meldet S13 eine
# Soll-Ist-Drift (warn). Bewusst EINZIGER Soll-Haken (kein Soll-System).
EXPECTED_RVOL_NORMALIZATION = False

# ── FINRA-Trend-Konfiguration ────────────────────────────────────────────────
# Stabilisiert 2026-04: 12 Handelstage statt 6, 6 Mindest-Datenpunkte
# statt 3 — deutlich weniger Tagesausreißer, dafür mehr „Keine Daten" bei
# Nischen-Tickern mit wenig FINRA-Historie (gewollt).
SI_TREND_PERIODS        = 12    # FINRA Daily Short Volume; 12 ≈ 2,5 Wochen
SI_TREND_MIN_DATAPOINTS = 6     # Min. signifikante Datenpunkte für Trend
SI_TREND_UP_THRESHOLD   =  0.10 # ≥+10 % → steigend
SI_TREND_DOWN_THRESHOLD = -0.10 # ≤-10 % → fallend

# ── Float-Größen-Faktor ──────────────────────────────────────────────────────
FLOAT_WEIGHT          = 8           # max. Bonus bei kleinem Float
FLOAT_SATURATION_LOW  = 30_000_000  # ≤ 30 M Aktien → voll (8 Pkt)
FLOAT_SATURATION_HIGH = 50_000_000  # ≥ 50 M Aktien → 0 Pkt; linear dazwischen

# ── Score-Glättung + Trend ───────────────────────────────────────────────────
SCORE_TODAY_WEIGHT    = 0.70   # Gewicht für heutigen Rohscore
SCORE_HISTORY_WEIGHT  = 0.30   # Gewicht für Ø der letzten 3 Runs
SCORE_TREND_BONUS     = 3      # +Pkt bei SCORE_TREND_DAYS aufsteigenden Tagen
SCORE_TREND_MALUS     = 3      # -Pkt bei SCORE_TREND_DAYS fallenden Tagen
SCORE_TREND_DAYS      = 3      # Anzahl Tage für Trend-Erkennung
USE_RELATIVE_MOMENTUM = True   # Momentum vs. S&P 500 berechnen

# ── Score-History-Datei ──────────────────────────────────────────────────────
SCORE_HISTORY_FILE = "score_history.json"
SCORE_HISTORY_DAYS = 14    # ältere Einträge werden beim Laden verworfen

# ── Dynamischer Enrichment-Pool ──────────────────────────────────────────────
POOL_MIN                   = 20    # min. Kandidaten in Anreicherung
POOL_MAX                   = 75    # max. Obergrenze (Laufzeit)
POOL_SHORT_FLOAT_THRESHOLD = 10.0  # SF ≥ this % → immer im Pool
POOL_ENRICH_TIMEOUT        = 90    # s — Abbruch verbleibender Kandidaten

# ── Implizite Volatilität (Optionen) ─────────────────────────────────────────
IV_LOW                = 50    # < IV_LOW → rot
IV_HIGH               = 100   # > IV_HIGH → grün
IV_MIN_DAYS_TO_EXPIRY = 7     # Verfallstermin muss mind. N Tage entfernt sein

# ── Datenqualitäts-Features (Card-Anreicherung) ──────────────────────────────
# 1 — Daily Short Sale Ratio (aus FINRA CNMSshvol) als Tages-Proxy
SHOW_DAILY_SSR      = True
SSR_RED_THRESHOLD   = 0.40   # < 40 %  → rot
SSR_GREEN_THRESHOLD = 0.60   # > 60 %  → grün; 40–60 % orange

# 2 — Float-Plausibilität (Sanity-Check auf yfinance-Float-Werte)
FLOAT_MIN_VALID = 10_000           # < 10 000 Aktien → unplausibel
FLOAT_MAX_VALID = 50_000_000_000   # > 50 Mrd. Aktien → unplausibel

# 3 — Earnings Surprise (Beat/Miss der letzten Meldung)
SHOW_EARNINGS_SURPRISE = True

# 4 — Put/Call-Ratio Schwellen (neue Semantik: <0.5 bullisch, >1.5 bearisch)
SHOW_PUT_CALL_RATIO = True
PC_BULLISH  = 0.50
PC_BEARISH  = 1.50

# 6 — Historische Squeeze-Erkennung (90-Tage-Fenster)
SQUEEZE_DETECTION_DAYS = 90
SQUEEZE_MIN_GAIN       = 0.50   # ≥ +50 % in 5 Handelstagen
SQUEEZE_MIN_RVOL       = 3.0    # gleichzeitig Volumen ≥ 3× Ø


# ═══════════════════════════════════════════════════════════════════════════
#  ki_agent.py — Alert-Schwellen, Signal-Scores, Trigger
# ═══════════════════════════════════════════════════════════════════════════

# ── Alert-Basis-Schwellen ────────────────────────────────────────────────────
ALERT_THRESHOLD         = 25   # Fallback (wird durch Phasen-Schwellen ersetzt)
ALERT_THRESHOLD_STRONG  = 70   # Score ≥ → ⚡⚡ Starker Alert (deprecated als Push-Trigger; siehe ANOMALY_* unten)
ALERT_COOLDOWN_HOURS    = 2    # Mindeststunden zwischen Alerts je Ticker (Earnings-Sofort-Alert)

# ── Anomalie-Push-Trigger (ersetzt Monster≥70-Schwelle) ──────────────────────
# Push feuert nur bei „echten" Anomalien, nicht bei jedem Top-10-Monster-Score.
# Begründung: User checkt Top-10 selbst — Push ist für Ereignisse, die sonst
# übersehen würden. Jeder Trigger-Typ hat eigenen Cooldown via Key-Prefix
# „anomaly_<trigger>_<ticker>" in agent_state.json.
ANOMALY_TRIGGERS_ENABLED          = True
ANOMALY_COOLDOWN_HOURS            = 6   # pro (Ticker × Trigger-Typ)

# RVOL-Explosion: heutiger RVOL ≥ X UND ≥ Y× des Vortags
ANOMALY_RVOL_TODAY                = 5.0
ANOMALY_RVOL_VS_YESTERDAY         = 2.0

# UOA-Extreme: Call-Vol/OI im ATM-Bereich ≥ X
ANOMALY_UOA_VOL_OI                = 10.0

# Score-Sprung: Setup heute − gestern (raw aus score_history) ≥ X Pkt
ANOMALY_SCORE_JUMP                = 15

# Gap+Hold + RVOL Combo: gap_pct ≥ X UND state==strong_hold UND RVOL ≥ Y
ANOMALY_GAP_PCT                   = 5.0
ANOMALY_GAP_RVOL                  = 3.0

# Perfect Storm: gleichzeitig aktive Trigger im KI-Combo-Multiplikator
ANOMALY_PERFECT_STORM_TRIGGERS    = 4

# Monster-Backup: nur extreme Werte (frühere Schwelle 70 → jetzt 90)
ANOMALY_MONSTER_BACKUP            = 90

# Conviction-Hochstufung: Aktions-Signal wenn conviction_score (aus
# app_data.json["conviction_scores"]) ≥ Schwelle erreicht UND vorheriger
# Tick noch darunter lag (Threshold-Crossing — kein erneuter Push bei
# sustained high). prev_conviction_scores wird in agent_state.json
# persistiert (Key: "prev_conviction_scores").
ANOMALY_CONVICTION_HIGH_THRESHOLD = 75

# Conviction-Gating: Anomaly-Pushes (außer conviction_high selbst) werden
# nur an ntfy gesendet, wenn der Ticker mindestens diese Conviction
# erreicht. push_history wird in jedem Fall geschrieben — bei
# unterdrücktem Push mit suppressed=True + suppress_reason. Ticker
# ohne Conviction-Score (z.B. nicht in heutigen conviction_scores)
# pushen konservativ wie bisher (keine Filterung).
#
# Seit 12.05.2026 auf 75 angehoben (vorher 50). Diagnose ergab ~10
# Pushes/Tag, davon 51 % monster_backup mit dauerhaft hohen Setup-
# Scores aber moderater Conviction. Mit 75 fließen nur noch echte
# Aktions-Substrate durch — gleiche Schwelle wie conviction_high
# (= aktiver Aktions-Push). Beide Konstanten bleiben semantisch
# getrennt: HIGH triggert den eigenen conviction_high-Push beim
# Threshold-Crossing, MIN ist das Gating für ALLE anderen Anomaly-
# Trigger. Bei zukünftigen Re-Kalibrierungen sind beide unabhängig
# anpassbar.
ANOMALY_CONVICTION_MIN_THRESHOLD  = 75

# Earnings-Sofort-Alert (Per-Event-Dedup). Cooldown gilt pro
# (Ticker × Earnings-Date) — verhindert Mehrfach-Pushes für dasselbe
# Earnings-Event innerhalb des EARNINGS_IMMEDIATE_HOURS-Fensters.
# 24h ist großzügig: ein Earnings-Event dauert keine 24h, eine
# Wiederholung wäre also definitiv ein Bug.
EARNINGS_IMMEDIATE_COOLDOWN_HOURS = 24

# ── VIX-Gating für Anomalie-Pushes ──────────────────────────────────────────
# Bei hohem VIX (Krise/Panik) sind Squeeze-Setups oft Bull-Traps. Schwellen:
#   VIX > ANOMALY_VIX_PAUSE_THRESHOLD → alle Anomalie-Pushes pausiert
#   VIX > ANOMALY_VIX_WARN_THRESHOLD  → Push läuft, Message bekommt „⚠️ VIX X.X"-Präfix
#   sonst (oder None bei Fetch-Fehler) → unverändert
# Earnings-Sofort-Alerts werden NICHT gegated (Time-Critical).
ANOMALY_VIX_PAUSE_THRESHOLD       = 35.0
ANOMALY_VIX_WARN_THRESHOLD        = 25.0

# ── Push-Stille-Filter (Bewegung-gelaufen-Heuristik) ────────────────────────
# Ticker mit Anomalie + überhitztem Setup bekommen KEINEN Push, weil die
# Bewegung statistisch keine Einstiegs-Gelegenheit mehr ist. Anomalie bleibt
# in agent_signals.json (UI zeigt „📊 Bewegung gelaufen"-Label).
#   • RSI(14)        > PUSH_RSI_MAX    → silenced
#   • 2-Tages-Move   > PUSH_MOVE_2D_MAX → silenced
# Earnings-Sofort-Alerts und EDGAR 13D/13G-Filings sind explizit AUSGENOMMEN
# (Sofort-Charakter unabhängig vom Setup-Zustand).
PUSH_RSI_MAX                      = 75.0
PUSH_MOVE_2D_MAX                  = 0.20   # 20 %; Fraction (Close[-1]/Close[-3] − 1)

# ── Late-Runner-Penalty (Score-Multiplikator für überhitzte Setups) ─────────
# Setups mit RSI > LATE_RUNNER_RSI_THRESHOLD oder 2-Tages-Move >
# LATE_RUNNER_MOVE_2D_THRESHOLD haben statistisch ihren Move bereits
# gemacht — der hohe Score reflektiert vergangene Bewegung statt
# Frühindikation. Score wird mit LATE_RUNNER_PENALTY (< 1.0) multipliziert,
# damit „leise Akkumulation"-Kandidaten im Ranking nach oben rutschen.
# Wirkt nach apply_score_smoothing, vor apply_monster_score.
LATE_RUNNER_PENALTY               = 0.85
LATE_RUNNER_RSI_THRESHOLD         = 75
LATE_RUNNER_MOVE_2D_THRESHOLD     = 0.20   # Fraction (gleich PUSH_MOVE_2D_MAX, semantisch eigenständig)

# ── Earliness-Sub-Score — DTC-Niveau-Basis (Mittel-Refactor Stufe 2) ────────
# Datenbeleg: Diagnose 13.05.2026 — DTC (Spot) trennt Gewinner (return_10d
# ≥ +10 %) und Verlierer (return_10d ≤ −5 %) über 14d am stärksten
# (Mann-Whitney-U → AUC 0.77; Median Gewinner 10.05, Verlierer 5.40, n=78).
# Sub-Signale „SI-Trend 5d-Slope" / „RVOL-Build-up 5d" / „Coiled Spring"
# aus der ursprünglichen Mittel-Refactor-Stufe-1 sind aus dem heutigen
# backtest_history.json nicht rückwirkbar berechenbar — werden nicht
# weiter geführt.
#
# Operationalisierung: hoher DTC = Short-Stack bereits aufgebaut = mehr
# Squeeze-Brennstoff = „Setup ist reif für die Bewegung". RVOL > 5 als
# Negativ-Marker (Verlierer-Bucket-Mean RVOL = 2.56 vs Gewinner 1.46, mit
# Outliers bis 17.9× — Late-Runner-Pattern, kein Earliness-Substrat mehr).
#
# Version-Schalter: ``EARLINESS_FORMULA_VERSION = 2`` ist der scharfe
# Pfad. Version 1 (alte Stufe-1-Logik mit accel/velocity/pm_vol) bleibt
# im Code-Branch erhalten als Notfall-Rollback — bei strukturellen
# Problemen mit der DTC-Hypothese (nach 30 Tagen Live-Daten reevaluieren).
EARLINESS_FORMULA_VERSION         = 2

# Skala: V2 nutzt 0..100, V1 nutzt 0..7. Conviction-Normalisierung in
# compute_conviction_score ist relativ (earliness_pts / EARLINESS_PTS_MAX
# × 28), funktioniert für beide Skalen identisch.
EARLINESS_PTS_MAX                 = 100    # V2 (vorher 7 = V1)

# DTC-Bucket-Schwellen (Spot-Wert ``s["short_ratio"]``).
EARLINESS_DTC_BUCKET_1_MIN        = 3.0    # < 3   → Bucket 0 →   0 Pkt
EARLINESS_DTC_BUCKET_2_MIN        = 5.0    # < 5   → Bucket 1 →  25 Pkt
EARLINESS_DTC_BUCKET_3_MIN        = 8.0    # < 8   → Bucket 2 →  50 Pkt
EARLINESS_DTC_BUCKET_4_MIN        = 12.0   # < 12  → Bucket 3 →  75 Pkt
                                           # ≥ 12 → Bucket 4 → 100 Pkt
EARLINESS_DTC_BUCKET_PTS          = (0, 25, 50, 75, 100)

# Late-Runner-Penalty auf den Earliness-Wert. Semantisch eigenständig zu
# apply_late_runner_penalty, das auf s["score"] wirkt (×0.85 bei RSI > 75
# oder chg2d > 20 %). Beide Penalties wirken parallel — bewusste Doppel-
# Bestrafung von Late-Runnern, siehe CLAUDE.md.
EARLINESS_LATE_RUNNER_RVOL_MAX    = 5.0    # RVOL > 5× → halbieren
EARLINESS_LATE_RUNNER_FACTOR      = 0.5    # ×0.5

# ── DEPRECATED — Earliness V1 (Mittel-Refactor Stufe 1, accel/velocity/PM-Vol) ──
# Werden NICHT entfernt: bleiben für den Version-1-Branch in
# compute_earliness_pts (Notfall-Rollback via EARLINESS_FORMULA_VERSION=1).
# Neue Code-Pfade sollen NICHT auf diese Konstanten zugreifen — V2 ersetzt
# die Sub-Signale komplett.
EARLINESS_ACCEL_PTS               = 3      # V1-only: si_accel + niedriger 5T-Move
EARLINESS_VELOCITY_PTS            = 2      # V1-only: si_velocity + niedriger RSI
EARLINESS_VELOCITY_THRESHOLD      = 100    # V1-only: tägliche FINRA-Velocity-Schwelle
EARLINESS_MAX_CHANGE_5D_PCT       = 5.0    # V1-only: Move noch nicht groß
EARLINESS_MAX_RSI                 = 60     # V1-only: RSI noch im normalen Bereich
EARLINESS_PM_VOL_LOW_PCT          = 3.0    # V1-only: ≥3 % PM-vs-Avg → +1
EARLINESS_PM_VOL_HIGH_PCT         = 8.0    # V1-only: ≥8 % PM-vs-Avg → +2
EARLINESS_PM_VOL_PTS_LOW          = 1      # V1-only
EARLINESS_PM_VOL_PTS_HIGH         = 2      # V1-only
EARLINESS_PTS_MAX_V1              = 7      # V1-only-Cap (für Rollback-Pfad)

# ── Earliness-Trend-Logging (prospektiv, KEIN Conviction-/Score-Effekt) ─────
# Felder werden ab dieser PR pro neuem Backtest-Eintrag persistiert, damit
# nach 14–30 Tagen Live-Daten ein AUC-Vergleich gegen return_10d möglich ist
# (analog zur DTC-Validierung 13.05.2026, die V2 belegt hat). Drei
# Sub-Signale aus der ursprünglichen Diagnose, die aus dem heutigen
# backtest_history.json NICHT rückwirkbar berechenbar waren: SI-Trend
# 5d-Slope, RVOL-Build-up 5d, Vol-Stability 5d (ATR-Proxy). Plus
# abgeleiteter Coiled-Spring-Composite.
EARLINESS_TREND_LOG_WINDOW_DAYS    = 5     # 5-Trading-Tage-Fenster
EARLINESS_TREND_MIN_FINRA_POINTS   = 5     # Slope braucht ≥ 5 SI-Werte
EARLINESS_TREND_SI_SLOPE_CAP       = 0.20  # 20 % cap für coiled_spring-Norm
EARLINESS_TREND_VOL_STAB_CAP       = 0.10  # 10 % ATR/Close cap für coiled_spring-Norm

# ── Score-Konfidenz-Stufen (rein anzeigend, KEIN Score-/Conviction-Effekt) ──
# Vier qualitative Stufen (statt prozentual, um „85 %-Garantie"-Trap zu
# vermeiden). Werden im Methodik-Panel angezeigt. Trennung von Score-
# Berechnungs-Pfaden wird vom Linter `scripts/lint_score_confidence_isolation.py`
# erzwungen.
#
# Schwellen für `compute_score_confidence`:
#   ≥ N_ROBUST + AUC-Test belegt        → "robust"      (🟢)
#   ≥ N_MITTEL UND AUC-Test belegt       → "mittel"      (🟡)
#   ≥ N_MITTEL ohne AUC-Test ODER
#   ≥ N_PROVISORISCH mit AUC-Test        → "provisorisch" (🟠)
#   < N_PROVISORISCH ODER keine Validierung → "heuristisch" (🔴)
SCORE_CONFIDENCE_N_ROBUST         = 500    # Datenpunkte mit Returns für robust
SCORE_CONFIDENCE_N_MITTEL         = 50     # Datenpunkte für mittel
SCORE_CONFIDENCE_N_PROVISORISCH   = 1      # mind. 1 Datenpunkt für provisorisch
SCORE_CONFIDENCE_MAX_AGE_DAYS     = 14     # Snapshot älter → 🔴-Hinweis im Panel

# ── SEC EDGAR 13D/13G Filings (Anomalie-Trigger) ────────────────────────────
# Hybrid-Filter:
#   • 13D / 13D/A: jeder Filing-Eintrag löst einen Push aus (aktive Stake-
#     Erklärung — squeeze-relevant unabhängig vom Filer).
#   • 13G / 13G/A: nur wenn Filer-Name eines der EDGAR_ACTIVIST_FILERS-
#     Substrings enthält (passive Stake — uninteressant außer von „Smart-
#     Money"-Firmen).
# SEC verlangt einen User-Agent mit Kontakt-E-Mail (Default funktioniert
# für Tests; User soll später eigene Adresse eintragen).
# Cooldown 24h pro (Ticker × Filing-Typ) — Filings sind selten genug,
# Amendment-Folgen werden so unterdrückt.
EDGAR_FILINGS_ENABLED  = True
EDGAR_RSS_URL          = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=SC+13&owner=include&count=40&output=atom"
)
# User-Agent kommt aus GitHub-Secret EDGAR_USER_AGENT (analog zu
# POSITIONS_JSON, NTFY_TOPIC). Public Repo: keine Kontakt-E-Mail im Code.
# Default-Fallback ist generisch und funktioniert für Tests/Forks; SEC
# blockt aber bei produktiven Aufrufen ohne korrekten Kontakt-Header.
EDGAR_USER_AGENT       = os.environ.get(
    "EDGAR_USER_AGENT",
    "Squeeze Report contact@example.com",
)
EDGAR_LOOKBACK_HOURS   = 6
EDGAR_COOLDOWN_HOURS   = 24
EDGAR_HTTP_TIMEOUT     = 10

# Aktivist-/Smart-Money-Liste — nur für 13G-Filter relevant. Match
# case-insensitive, Substring (z. B. "Pershing" matched „Pershing Square
# Capital Management LP"). User darf erweitern.
EDGAR_ACTIVIST_FILERS  = [
    "Icahn",
    "Ackman", "Pershing Square",
    "Cohen", "Point72",
    "Burry", "Scion",
    "Loeb", "Third Point",
    "Singer", "Elliott",
    "Peltz", "Trian",
    "Einhorn", "Greenlight",
    "Hohn", "Children's Investment",
    "Kovacs", "Engaged Capital",
    "Smith", "Starboard",
    "Marcato",
    "ValueAct",
    "Carlson", "Carlson Capital",
    "Jana Partners",
    "Land and Buildings",
    "Sachem Head",
    "Glenview",
    "Corvex",
    "Sarissa",
    "RBC Capital",
    "BlackRock",   # bei 13G ebenfalls relevant
    "Vanguard",    # ebenfalls
]

# ── KI-Score-Dot-Schwellen (Frontend-Pulsieren neben Ticker) ─────────────────
# Steuert die Farbe des pulsierenden .agent-dot auf der Top-10- und Watchlist-
# Kachel. Schwellen sind an die apply_monster_score-Semantik gekoppelt:
#   ≥ KI_DOT_STRONG (60)   → grün  — Monster wird mit ×1.20 geboostet
#   ≥ KI_DOT_MODERATE (30) → orange — sichtbares Signal, aber nicht boost-würdig
#   ≥ KI_DOT_WEAK (15)     → rot   — Rauschen-Untergrund
#   sonst                   → grau  — kein/kaum Signal, statisch (kein Pulsieren)
KI_DOT_STRONG    = 60
KI_DOT_MODERATE  = 30
KI_DOT_WEAK      = 15

# ── Exit-Signale für offene Positionen ───────────────────────────────────────
# positions.json wird zur Laufzeit aus dem GitHub Secret POSITIONS_JSON
# erzeugt (siehe daily-squeeze-report.yml + ki_agent.yml). Schema:
#   { "TICKER": { "entry_date": "YYYY-MM-DD", "entry_price": 12.34 } }
# Der Daily-Run berechnet pro offener Position einen Exit-Score 0–100 aus
# vier Komponenten (Trailing-Stop 40 %, Setup-Verfall 25 %, Distribution
# 20 %, Time-Decay 15 %). Bei Exit-Score ≥ EXIT_ALERT_THRESHOLD oder
# pnl_pct ≥ EXIT_PROFIT_TAKE_PCT geht ein ntfy-Push raus, mit eigenem
# Cooldown (separater Key-Prefix "exit_"/"profit_" in agent_state.json).
EXIT_ENABLED              = True
EXIT_ALERT_THRESHOLD      = 60     # Exit-Score ≥ → ntfy
EXIT_PROFIT_TAKE_PCT      = 50.0   # PnL ≥ % seit Entry → Profit-Take-Push
EXIT_TRAILING_STOP_PCT    = 12.0   # Drawdown vom Hoch → Trailing-Komponente max
EXIT_SETUP_DROP_THRESHOLD = 20     # Setup-Score-Fall vs. Entry-Tag → max
EXIT_DISTRIBUTION_RVOL    = 3.0    # heute RVOL ≥ + Tagesperformance < 0
EXIT_TIME_DECAY_DAYS      = 10     # Stagnation ab Tag X
EXIT_TIME_DECAY_MOVE_PCT  = 8.0    # ohne Tagesbewegung ≥ % zählt als Stagnation
EXIT_WEIGHT_TRAILING      = 0.40
EXIT_WEIGHT_SETUP         = 0.25
EXIT_WEIGHT_DISTRIBUTION  = 0.20
EXIT_WEIGHT_TIMEDECAY     = 0.15
EXIT_COOLDOWN_HOURS       = 4      # Exit-/Profit-Cooldown je (Ticker, Typ)

# ── Phase 2 Exit-Signal-Daten-Pipeline (Stufe 1/3 — kein UI/Push) ────────────
# Pro offener Position berechnet der Daily-Run sechs Trigger-Sub-Scores
# (jeweils 0–100) und einen gewichteten Composite ("exit_pressure").
# Persistiert unter app_data.json["positions"][ticker]["exit_state"]; ki_agent
# bewahrt die Sektion via **existing-Spread zwischen Ticks. Mapping: Werte
# unter WARN-Schwelle werden linear auf 0–50 skaliert, WARN..CRIT linear auf
# 50..100, ≥ CRIT auf 100. Trigger ohne Datenbasis (Setup-Erosion ohne
# Entry-Snapshot, Trend-Bruch ohne EMA21, Catalyst ohne Earnings-Vergangenheits-
# Lookup) werden als ``available: false`` ausgewiesen und vom Composite
# ausgeschlossen — der Composite normiert über die Summe der verfügbaren
# Gewichte, damit ein einziger aktiver Trigger nicht durch "available: false"-
# Trigger künstlich verwässert wird.
EXIT_PHASE2_ENABLED          = True

# 1) Score-Verfall (Composite-Gewicht 30 %) — Drop in raw score_history
EXIT_SCORE_DROP_3D_WARN      = 8
EXIT_SCORE_DROP_3D_CRIT      = 15
EXIT_SCORE_DROP_5D_WARN      = 12
EXIT_SCORE_DROP_5D_CRIT      = 20
EXIT_SCORE_DROP_7D_WARN      = 15
EXIT_SCORE_DROP_7D_CRIT      = 25

# 2) Profit-Lock (25 %) — Drawdown vom Peak-PnL und Peak-Score
EXIT_PROFIT_LOCK_WARN_PCT    = 0.15   # Drawdown ≥ 15 Prozentpunkte vom Peak-PnL
EXIT_PROFIT_LOCK_CRIT_PCT    = 0.25
EXIT_PEAK_SCORE_DROP_WARN    = 10     # Score ≥ 10 Pkt unter peak_score_since_entry
EXIT_PEAK_SCORE_DROP_CRIT    = 20

# 3) Überhitzung (20 %) — RSI + Kurzzeit-Move
EXIT_RSI_WARN                = 75
EXIT_RSI_CRIT                = 82
EXIT_MOVE_2D_WARN            = 0.20
EXIT_MOVE_2D_CRIT            = 0.25
EXIT_MOVE_3D_WARN            = 0.28
EXIT_MOVE_3D_CRIT            = 0.35

# 4) Setup-Erosion (15 %) — Entry-Snapshot vs. heute. Misst, wie stark sich
#    die Short-Squeeze-Mechanik seit Entry abgeschwächt hat. Drei Drivers
#    (relative Drops): dtc_drop, sf_drop, ctb_drop. Trigger ist „live" seit
#    der Schema-Erweiterung im Position-Open (entry_dtc / entry_short_float
#    / entry_cost_to_borrow / entry_snapshot_ts im Gist).
#    Schwellen einheitlich pro Driver (nicht per-Driver wie früher geplant),
#    siehe CLAUDE.md Phase-2-Sektion.
SETUP_EROSION_WARN_THRESHOLD = 0.30   # 30 % relative Abnahme → warn (50)
SETUP_EROSION_CRIT_THRESHOLD = 0.50   # 50 % relative Abnahme → crit (100)
SETUP_EROSION_COMBO_DRIVERS_MIN = 2   # ≥ 2 Drivers in warn → combo-crit
# Deprecated: alte per-Driver-Konstanten — Trigger nutzt jetzt einheitlich
# SETUP_EROSION_WARN/CRIT_THRESHOLD. Werden vom Code nicht mehr gelesen,
# bleiben aber als Hinweis auf die alte Spec stehen.
EXIT_DTC_DROP_WARN_PCT       = 0.25   # DEPRECATED → SETUP_EROSION_WARN_THRESHOLD
EXIT_DTC_DROP_CRIT_PCT       = 0.40   # DEPRECATED → SETUP_EROSION_CRIT_THRESHOLD
EXIT_SHORT_FLOAT_DROP_WARN_PP = 4     # DEPRECATED — alte PP-Variante, nicht in Verwendung
EXIT_SHORT_FLOAT_DROP_CRIT_PP = 8     # DEPRECATED
EXIT_CTB_DROP_WARN_PCT       = 0.30   # DEPRECATED → SETUP_EROSION_WARN_THRESHOLD
EXIT_CTB_DROP_CRIT_PCT       = 0.50   # DEPRECATED → SETUP_EROSION_CRIT_THRESHOLD

# 5) Catalyst (5 %) — Earnings-Fenster: feuert, wenn die nächste
#    Earnings-Veröffentlichung innerhalb CATALYST_DAYS_WINDOW Handels-
#    tage liegt (Earnings-Datum heute → crit, 1..N Tage entfernt → warn).
#    Forward-looking: hohes binäres Risiko, Position vor Earnings
#    schließen oder bewusst halten. Datenquelle Primär = Finnhub
#    Earnings Calendar (FINNHUB_API_KEY in env), Fallback yfinance
#    `Ticker.calendar`.
CATALYST_DAYS_WINDOW         = 2
# 6) Trend-Bruch (5 %) — Kurs vs. EMA21. Sub-Score-Stufung:
#    drop_pct = (ma21 − price) / ma21 × 100
#      drop ≤ 0 (Kurs ≥ EMA21)               → 0   (kein Trigger)
#      0 < drop ≤ EXIT_TREND_BREAK_CRIT_PCT   → 50  (warn)
#      drop > EXIT_TREND_BREAK_CRIT_PCT       → 100 (crit)
EXIT_TREND_BREAK_CRIT_PCT    = 3.0

# Composite-Gewichte (Summe = 1.0)
EXIT_PHASE2_W_SCORE_DECAY    = 0.30
EXIT_PHASE2_W_PROFIT_LOCK    = 0.25
EXIT_PHASE2_W_OVERHEATED     = 0.20
EXIT_PHASE2_W_SETUP_EROSION  = 0.15
EXIT_PHASE2_W_CATALYST       = 0.05
EXIT_PHASE2_W_TREND_BREAK    = 0.05

# ── Phase 2 Stufe 3 Push-Schwellen + Cooldowns (3b-1: nur Log, kein Push) ────
# Drei Push-Klassen, ihre Schwellenwerte und Cooldown-Dauern. In Stufe 3b-1
# nur als Log-Output ausgewertet (process_exit_signals in ki_agent.py),
# echter Push-Versand folgt in Stufe 3b-2/3c.
EXIT_PUSH_ESCALATION_THRESHOLD     = 75   # exit_pressure > 75 → Eskalation
EXIT_PUSH_WARNING_THRESHOLD_LOW    = 55   # 55 ≤ exit_pressure ≤ 75 → Warnung
EXIT_PUSH_WARNING_THRESHOLD_HIGH   = 75
EXIT_PUSH_WARNING_COOLDOWN_HOURS   = 12   # pro Ticker
EXIT_PUSH_TRIGGER_COOLDOWN_HOURS   = 24   # pro (Ticker × Trigger-Name)

# ── Phase 2 Stufe 3c-1 Push-History-Persistenz ───────────────────────────────
# Ringpuffer in agent_state.json["push_history"]. FIFO-Cap entkoppelt
# Wachstum vom Tick-Volumen — bei stündlichem ki_agent + Daily-Run reichen
# 100 Einträge für ca. 4 Tage Historie, danach rollen ältere raus.
PUSH_HISTORY_MAX = 100

# ── Phasenabhängige Alert-Schwellen ──────────────────────────────────────────
# Zurückgesetzt — Bootstrap-Backtesting nicht mit Live-Scores vergleichbar.
# Kalibrierung nach 60+ Tagen Live-Daten.
ALERT_THRESHOLD_REGULAR    = 25   # 09:30–16:00 ET Regulärer Handel
ALERT_THRESHOLD_PREMARKET  = 20   # 04:00–09:30 ET
ALERT_THRESHOLD_AFTERHOURS = 20   # 16:00–20:00 ET
ALERT_THRESHOLD_CLOSED     = 35   # Wochenende / außerhalb der Handelszeit

# ── Pre/Post-Market + Earnings-Sofort-Alert ──────────────────────────────────
USE_PREPOST_DATA         = True   # prepost=True im 1m-Intraday-Download
EARNINGS_IMMEDIATE_ALERT = True   # Sofort-Alert bei frischer Earnings-Meldung
EARNINGS_IMMEDIATE_HOURS = 2      # 8-K/News muss innerhalb N Stunden liegen

# ── Score-Punkte je Einzelsignal ─────────────────────────────────────────────
SCORE_PRICE_UP_3       = 15   # Kurs +3 % intraday
SCORE_PRICE_UP_7       = 25   # Kurs +7 % intraday
SCORE_RVOL_2X          = 15   # Rel. Volumen ≥ 2×
SCORE_RVOL_4X          = 25   # Rel. Volumen ≥ 4×
SCORE_INTRADAY_RANGE   = 10   # (Hoch-Tief)/Open ≥ 5 %
SCORE_REDDIT_5         = 10   # Reddit-Erwähnungen ≥ 5 in 4h
SCORE_REDDIT_15        = 20   # Reddit-Erwähnungen ≥ 15 in 4h
SCORE_REDDIT_SENTIMENT = 10   # Positiver Sentiment ≥ 0.3
SCORE_SEC_8K           = 15   # Neue 8-K in letzten 24h
SCORE_SEC_8K_RELEVANT  = 25   # 8-K mit Earnings/FDA-Keywords
SCORE_NEWS_KEYWORD     = 15   # News-Keyword-Treffer (je Treffer, Cap 30)

# ── KI-Sentiment (Claude Haiku für News-Headlines statt Keyword-Zählung) ──
# Falls ANTHROPIC_API_KEY in der Umgebung vorhanden ist und KI_SENTIMENT_ENABLED
# gesetzt ist, werden die letzten 3 Schlagzeilen per Claude Haiku ausgewertet.
# Fällt bei API-Fehlern/fehlendem Key automatisch auf Keyword-Zählung zurück.
KI_SENTIMENT_ENABLED = True
KI_SENTIMENT_MODEL   = "claude-haiku-4-5-20251001"
KI_SENTIMENT_MAX_TOKENS = 50
KI_SENTIMENT_MAX_SCORE  = 30   # Cap (gleich wie Keyword-Zählung)
KI_SENTIMENT_HEADLINES  = 3    # letzte N Schlagzeilen senden

# ── Auslöse-Schwellen (Trigger) ──────────────────────────────────────────────
TRIGGER_PRICE_UP_3 = 2.0   # ab +2 % → SCORE_PRICE_UP_3
TRIGGER_PRICE_UP_7 = 5.0   # ab +5 % → SCORE_PRICE_UP_7
TRIGGER_RVOL_2X    = 1.5   # ab 1.5× → SCORE_RVOL_2X
TRIGGER_RVOL_4X    = 3.0   # ab 3× → SCORE_RVOL_4X

# ── Earnings-Nähe (Tage bis Termin) ──────────────────────────────────────────
SCORE_EARNINGS_NEAR = 25   # ≤ EARNINGS_NEAR_DAYS
SCORE_EARNINGS_MID  = 15   # ≤ EARNINGS_MID_DAYS
SCORE_EARNINGS_FAR  = 8    # ≤ EARNINGS_FAR_DAYS
EARNINGS_NEAR_DAYS  = 3
EARNINGS_MID_DAYS   = 7
EARNINGS_FAR_DAYS   = 45

# ── FDA PDUFA-Nähe ───────────────────────────────────────────────────────────
SCORE_PDUFA_NEAR = 25   # PDUFA in 1–7 Tagen
SCORE_PDUFA_MID  = 15   # PDUFA in 8–30 Tagen

# ── Konfidenz-Berechnung ─────────────────────────────────────────────────────
MAX_SIGNAL_TYPES      = 6    # Anzahl betrachteter Signalkategorien
CONFIDENCE_CAP_SINGLE = 40   # max. Konfidenz bei nur 1 Signaltyp aktiv
CONFIDENCE_MIN_MULTI  = 70   # min. Konfidenz bei ≥ 3 Signaltypen aktiv

# ── Tägliche Zusammenfassung ─────────────────────────────────────────────────
SEND_DAILY_SUMMARY       = True
DAILY_SUMMARY_HOUR_ET    = 16
DAILY_SUMMARY_MINUTE_ET  = 30
DAILY_SUMMARY_WINDOW_MIN = 5    # ±Minuten Toleranzfenster

# ── News-/SEC-Keywords + Reddit-Konfiguration ────────────────────────────────
NEWS_KEYWORDS = {
    "squeeze", "short squeeze", "short interest",
    "analyst upgrade", "earnings beat",
    "short seller", "covering", "gamma squeeze", "options activity",
    "unusual volume", "breakout", "catalyst", "fda approval",
    "merger", "acquisition", "buyout", "takeover", "partnership",
    "contract", "revenue beat", "guidance raised", "insider buying",
    "institutional buying", "short covering", "forced liquidation",
    "margin call", "halt", "circuit breaker", "activist investor",
}
SEC_RELEVANT_KEYWORDS = {
    "earnings", "revenue", "results", "approval", "fda",
    "pdufa", "nda", "bla", "guidance", "outlook",
}
REDDIT_POSITIVE   = {"squeeze", "moon", "calls", "breakout", "short"}
REDDIT_NEGATIVE   = {"puts", "short", "crash", "dump"}
REDDIT_SUBS       = ["wallstreetbets", "stocks", "shortsqueeze"]
REDDIT_LOOKBACK_H = 4

# ── OpenInsider — Insider-Käufe ──────────────────────────────────────────────
INSIDER_LOOKBACK_DAYS = 30
SCORE_INSIDER_BUY     = 20   # beliebiger Insider
SCORE_INSIDER_CSUITE  = 30   # C-Suite (CEO/CFO/President/…)

# ── FINRA Daily Short Sale Volume (ki_agent) ─────────────────────────────────
FINRA_DAILY_SSR_MID  = 0.50   # Short-Vol-Anteil ≥ 50 %
FINRA_DAILY_SSR_HIGH = 0.70   # Short-Vol-Anteil ≥ 70 %
SCORE_FINRA_SSR_MID  = 15
SCORE_FINRA_SSR_HIGH = 25

# ── SEC Form 4 — Insider-Transaktionen ───────────────────────────────────────
FORM4_LOOKBACK_DAYS  = 7
SCORE_FORM4_ANY      = 10   # beliebige Form-4-Einreichung
SCORE_FORM4_PURCHASE = 20   # Form-4 mit Kauf ("Purchase"/"Acquisition")

# ── Dateipfade + URL ─────────────────────────────────────────────────────────
STATE_FILE   = Path("agent_state.json")
SIGNALS_FILE = Path("agent_signals.json")
INDEX_HTML   = Path("index.html")
PWA_URL      = "https://easywebb911.github.io/Aktien-Update/"

# ── Zeitzonen ────────────────────────────────────────────────────────────────
BERLIN  = ZoneInfo("Europe/Berlin")
EASTERN = ZoneInfo("America/New_York")

# ── Service-spezifische HTTP-Header ──────────────────────────────────────────
REDDIT_HEADERS = {"User-Agent": "SqueezeAgent/1.0"}
SEC_HEADERS    = {"User-Agent": "Easy Webb easywebb@yahoo.de"}

# ── ntfy.sh Push-Notifications ───────────────────────────────────────────────
# Leer = deaktiviert. Topic frei wählbar (z.B. "squeeze-xk7q2m9p"); auf
# https://ntfy.sh/<topic> oder per ntfy-App abonnieren.
NTFY_TOPIC   = os.environ.get("NTFY_TOPIC", "")
NTFY_ENABLED = True

# ── Health-Check (Phase 1 — State-Invariants) ────────────────────────────────
# Frühwarnsystem für stille Datenausfälle (Pipeline grün, Artefakt kaputt).
# Spec: docs/health_check_spec.md. Persistenz: health_check_log.jsonl im
# Repo-Root, 30-Tage-Cutoff (analog score_inflation_log.jsonl).
HEALTH_CHECK_S2_MIN_TICKERS         = 8    # setup_scores ≥ 8 Tickers
HEALTH_CHECK_S5_MIN_INFLATION_LINES = 10   # neue Zeilen in score_inflation_log
HEALTH_CHECK_S6_MIN_MONSTER_NONZERO = 3    # monster_scores > 0
HEALTH_CHECK_S7_MIN_AGENT_OVERLAP   = 5    # |agent_signals ∩ top10|
HEALTH_CHECK_S8_MAX_AGE_HOURS       = 26   # max Alter last_digest_sent
                                            # (>26 h = mindestens ein
                                            #  Daily-Digest-Slot verpasst)
# S11/S12 — Phasen-Sammel-Frequenz-Wächter (additiv zu S1–S10/S8).
# Erkennen stillen Tod der Sammel-Mechanik: mehrere Werktage ohne
# echten premarket-/postclose-Run (run_phase == tsp == 'premarket'
# bzw. 'postclose' im score_inflation_log). Holiday-/WE-robust durch
# „absence of state-write"-Pattern — an Feiertagen/Wochenenden feuert
# der Cron strukturell nicht, daher keine Erwartung → keine false-positives.
HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET = 5   # warn ab Werktagen ohne echten premarket-Run
HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE = 2   # crit (NUR-REPORTING) ab Werktagen ohne echten postclose-Run
HEALTH_CHECK_CUTOFF_DAYS            = 30   # JSONL-Prune-Cutoff

# Quote-Proxy-Probe (Tier-2-Provider, 1× pro Daily-Run):
QUOTE_PROXY_PROBE_TICKER            = "NVDA"   # Bench-Ticker für Worker-Ping
QUOTE_PROXY_PROBE_TIMEOUT_S         = 5.0      # Sekunden HTTP-Timeout
# Origin-Header: identisch zum echten Client-Browser. Drift zwischen
# diesem Wert und der Worker-ALLOWED_ORIGINS-Liste würde die Probe
# weiterhin durchlaufen lassen (Worker fällt auf Allowlist[0] zurück
# statt 403), aber so simuliert die Probe den Client möglichst genau.
QUOTE_PROXY_PROBE_ORIGIN            = "https://easywebb911.github.io"

# Phase 2 — Provider-Health-Instrumentierung. Tier-Zuordnung (1=crit,
# 2=warn-3-in-Folge, 3=warn-3-in-Folge) gemäß
# docs/health_check_spec.md. Phase 2 PR 1 instrumentiert nur Tier-1;
# Tier-2/3 werden in Folge-PRs ergänzt.
HEALTH_CHECK_PROVIDER_TIER = {
    # Tier 1 (crit, sofortiger Alarm bei Fail)
    "yahoo_screener":      1,
    "yfinance_batch":      1,   # Pool-Batch (OHLCV/RSI/EMA21/change_2d_3d)
    "yfinance_singletons": 1,   # ^VIX + ^GSPC (SPY) + EURUSD=X
    # Tier 2 (warn, 3-in-Folge-Trigger — Konsekutiv-Persistenz in Phase 3)
    "finviz":              2,   # Stufe-3-Fallback (v161+v111+Quote-Page), nicht primär — herabgestuft 19.05.2026
    "finra":               2,   # FINRA Short-Volume Sums (3 File-Downloads)
    "finnhub":             2,   # Earnings Calendar (pro offene Position)
    "stockanalysis":       2,   # NUR SI-Pfad (Borrow seit 01.06.2026 separat, s.u.)
    "borrow":              2,   # Borrow-Orchestrator (iBorrowDesk-JSON +
                                # Stockanalysis-tot-primary). Eigener Akku/
                                # Provider-Key seit Quellenwechsel 01.06.2026
                                # — sonst würde Borrow-Tod nur 50 % coverage
                                # drücken, knapp unter Tier-2-Schwelle.
    "earningswhispers":    2,   # RSS Calendar (1× pro Daily-Run)
    "quote_proxy":         2,   # Cloudflare-Worker → Yahoo v8 chart-Probe
                                # (Frontend-Live-Quote-Pipeline-Health; 1×
                                # pro Daily-Run; CORS bewusst ungeprüft —
                                # Browser-only; nur Worker-tot + Yahoo-Bruch)
    # Tier 3 (warn, 3-in-Folge-Trigger — Konsekutiv-Persistenz in Phase 3).
    # Klärung 15.05.2026: getrennte Provider-Keys statt Spec-Wortlaut-
    # Aggregate, für saubere Coverage-Granularität.
    "stocktwits":          3,   # Social-Sentiment (per-Top-10, KI-Agent)
    "uoa":                 3,   # Unusual Options Activity (per-Top-10)
    "news_rss":            3,   # 5+ RSS-Quellen (Finviz/Google/Yahoo/UW/MB/SA)
    "edgar_13f":           3,   # SEC 13F-Filings (per-Top-10)
    "edgar_8k":            3,   # SEC 8-K-Filings (per-Top-10, KI-Agent)
    "edgar_form4":         3,   # SEC Form 4 Insider (per-Top-10, KI-Agent)
    "edgar_13d_g":         3,   # SEC 13D/G-Filings (1× pro KI-Agent-Tick)
}

# Erwartete Item-Counts pro Provider — Basis für Coverage-Berechnung.
# ``None`` = variabel (Coverage-Berechnung übersprungen, coverage_pct
# bleibt null in der JSONL-Zeile).
HEALTH_CHECK_PROVIDER_EXPECTED = {
    "yahoo_screener":      None,   # Pool-Größe schwankt natürlich
    "finviz":              None,   # v161 + v111-Pool variabel
    "yfinance_batch":      None,   # ticker-abhängig (Pool-Größe)
    "yfinance_singletons": 3,      # ^VIX + ^GSPC + EURUSD=X
    # Tier 2
    "finra":               None,   # Universum aller US-Tickers, Subset variabel
    "finnhub":             None,   # 1 Call pro Position; emittiert nur bei calls>0
    "stockanalysis":       None,   # N pro Top-10 (ENABLED-gated, NUR SI)
    "borrow":              None,   # N pro Top-10 (Borrow-Orchestrator)
    "earningswhispers":    None,   # RSS-Feed-Größe schwankt (~30–80)
    "quote_proxy":         1,      # genau 1 Probe-Quote (Bench-Ticker NVDA)
    # Tier 3 — alle Coverage-variabel (per-Top-10-Aufrufe schwanken)
    "stocktwits":          None,
    "uoa":                 None,
    "news_rss":            None,   # 5+ RSS-Quellen × N Top-10
    "edgar_13f":           None,
    "edgar_8k":            None,
    "edgar_form4":         None,
    "edgar_13d_g":         None,
}


# ── Digest-Konsekutiv-Schwelle: provider-spezifische Overrides ────────────
#
# Basis-Konstante ``DIGEST_CONSECUTIVE_THRESHOLD = 3`` lebt aus historischen
# Gründen in ``health_check.py:1116`` (zusammen mit den Coverage-Schwellen
# DIGEST_COVERAGE_THRESHOLD_TIER1/TIER23). Bewusste Inkonsistenz akzeptiert
# — die Override-Konstante lebt hier zentral in config.py, der Default wird
# in health_check.py weiter direkt verwendet (Override-Lookup via
# ``.get(prov, DIGEST_CONSECUTIVE_THRESHOLD)`` in
# ``aggregate_provider_fails``).
#
# WAS:
#   Pro-Provider-Override für die N-in-Folge-Schwelle, ab der ein
#   Tier-2/3-Provider als ``warn`` aggregiert wird. Default bleibt 3.
#
# WARUM finviz:
#   - finviz ist seit 19.05.2026 dokumentiert von Tier 1 → Tier 2 herab-
#     gestuft (HEALTH_CHECK_PROVIDER_TIER["finviz"]=2, oben).
#   - Empirisch (28.05.2026): finviz speist als SF-Quelle 0/100 der letzten
#     backtest_history-Einträge — yfinance deckt 100/100 ab, kein finviz-
#     only Score-/Conviction-/Filter-Feld existiert (verifiziert per
#     Source-Inspection).
#   - Der 22-in-Folge-Alarm ist daher Mechanik-Rauschen (Provider zählt
#     Failures agnostisch zur Wirkung), keine Datenqualitäts-Frage.
#   - Schwelle 100 lässt einen ECHTEN Tier-1-Rückkehr-Ausfall weiterhin
#     sichtbar (33× Lag gegenüber Default ist akzeptabel, weil finviz
#     dokumentiert Tier-2 ist).
#
# 30.06.-BACKLOG (Option α aus der Diagnose 28.05.):
#   Strukturelle Aufräumung — Provider zurückbauen (finviz-Pfade entfernen,
#   Aggregator-Emit am Daily-Run-Ende konditional). Diese Schwelle hier
#   wird damit obsolet und sollte entfernt werden.
#
# Pflege:
#   Neuer Provider-Override → einfach Schlüssel ergänzen, KEIN Code-Touch
#   in health_check.py nötig (Lookup ist dict-getrieben). Override-Dict
#   leer/fehlend → fällt sauber auf Default 3 zurück.
DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES = {
    "finviz": 100,
}


# ── Health-Check S10 — Daten-Integritäts-Check (Phase 1, additiv) ──────────
#
# Erkennt wenn ein MUSS-gefülltes Feld in ``backtest_history.json`` dauerhaft
# leer bleibt (Pattern hist_5d-Bug 14.05.–21.05.2026: drei Trend-Felder zu
# 100 % null, eine Woche unbemerkt). Premium-Ziel-Baustein: das System fragt
# sich selbst, ob die Daten-Mechanik durchläuft.
#
# Phase 1 ist bewusst minimal — nur die hist_5d-Bug-Klasse + die wahr-
# scheinlichste rolling-Update-Bug-Klasse (return_3d/5d). Phase 2 wird die
# Listen erweitern (restliche V4-MUSS-Felder, return_10d, agent_signals.json,
# score_history.json), sobald 2–4 Wochen Betrieb gezeigt haben, dass die
# Schwellen + false-positive-Rate beherrscht sind.
#
# Schwellen-Logik:
#   - MUSS-Felder: pct_null in letzten 20 V4-Einträgen → warn ≥ warn_pct,
#     crit ≥ crit_pct. CRIT nur für die „stiller-Tod"-Klasse.
#   - LAG-Felder: pct_null in gealterten Einträgen (≥ lag_trading_days alt)
#     → warn ≥ warn_pct. **Nie crit** (fehlende Outcomes ärgerlich, nicht akut).
#   - Wochenend-Filter beim Laden: Einträge mit weekday() ≥ 5 werden
#     ausgeklammert (die 96 Bestands-Leichen würden sonst LAG-Pfad
#     dauerhaft false-positive machen).

S10_MUSS_FIELDS = {
    # Vier Trend-Felder aus PR #142 (Schema v4). hist_5d-Propagation seit
    # PR #244 wieder funktional → Felder sollen ab nächstem postclose-Run
    # gefüllt sein.
    "rvol_buildup_5d":     {"warn_pct": 30.0, "crit_pct": 70.0},
    "vol_stability_5d":    {"warn_pct": 30.0, "crit_pct": 70.0},
    "coiled_spring_score": {"warn_pct": 30.0, "crit_pct": 70.0},
    "si_trend_5d_slope":   {"warn_pct": 30.0, "crit_pct": 70.0},
}

S10_LAG_FIELDS = {
    "return_3d": {"lag_trading_days": 3, "warn_pct": 20.0},
    "return_5d": {"lag_trading_days": 5, "warn_pct": 20.0},
}

# Negativliste: bekannte V4-Felder, die wir bewusst NICHT prüfen.
# Wer ein NEUES Feld einführt, das hier nicht steht, löst Auto-Detect-WARN
# aus („Feld X aufgetaucht, nicht klassifiziert") und wird dadurch zur
# Klassifikation gezwungen. Genau das Premium-Ziel-Prinzip: das System
# bemerkt, was es nicht versteht.
#
# Liste wurde aus den 37 keys aller V4-Einträge in backtest_history.json
# am 21.05.2026 abgeleitet. Minus die 6 in S10_MUSS_FIELDS + S10_LAG_FIELDS.
S10_OBSERVED_FIELDS = frozenset({
    # Core (immer gesetzt)
    "date", "ticker", "score", "entry_price", "rvol", "dtc",
    "short_float", "si_trend", "backtest_schema_version",
    "short_float_source", "si_trend_source",
    # V4-Setup-Snapshot
    "score_struct", "score_catalyst", "score_timing", "score_raw",
    "combo_bonus", "finra_bonus", "agent_boost_factor",
    "perfect_storm_mult", "score_trend_bonus",
    "pool_member", "pool_position", "pool_size",
    "market_regime", "vix_level",
    # PR-γ-1 Marker (additiv, kein Score-Effekt) — siehe SCORE_NORMALIZATION_VERSION.
    # Ohne diesen Eintrag wuerde S10-Auto-Detect am ersten Daily-Run nach
    # γ-1-Merge ein false-positive WARN "Unklassifiziert: score_normalization_version"
    # ausloesen (PR #246).
    "score_normalization_version",
    # Entry-Score-Vorarbeit (21.05.2026): zwei Sub-Signale fuer das Entry-
    # Timing-Modul (geplant 10.06.). Beide LEGITIM-leer-tolerant, daher
    # nur OBSERVED (kein MUSS-Check, kein LAG-Check). rvol_acceleration
    # ist None wenn rel_volume_yesterday fehlt/0. uoa_atm_ratio ist None
    # wenn Ticker nicht im KI-Agent-monitored-Pool.
    "rvol_acceleration", "uoa_atm_ratio",
    # Entry-Modul-Vorarbeit (Shadow-Persist 25.05.2026): zwei weitere
    # vorgezogene Felder für die Entry-AUC ~30.06. Beide LEGITIM-leer-
    # tolerant (None möglich) → nur OBSERVED, kein MUSS-/LAG-Check.
    # score_delta_t1 ist None bei < 2 Sparkline-Werten; anomaly_freshness
    # ist None wenn der Ticker nie gepusht wurde (0.0 = Push älter 72 h).
    "score_delta_t1", "anomaly_freshness",
    # Twin-Roh-Felder (Shadow-Persist 29.05.2026): ungecappte/un-
    # transformierte Pendants für die Cap-vs-Perzentil-Auswertung ~30.06.
    # score_delta_t1_raw = score_delta_t1 OHNE ±15-Clamp; anomaly_push_age_h
    # = rohes Push-Alter h VOR der Decay-/0-Floor-Transform. Beide leer-
    # tolerant (None) → nur OBSERVED. Schema bleibt v4.
    "score_delta_t1_raw", "anomaly_push_age_h",
    # LAG-Felder, später (Phase 2)
    "entry_price_t1",
    "return_10d", "return_10d_t1",
    "return_3d_t1", "return_5d_t1",
    "max_drawdown_pct",
})

S10_WINDOW_SIZE          = 20    # Letzte N V4-Einträge für MUSS-Check
S10_MUSS_MIN_N           = 5     # Unter dieser Stichprobengröße → skip (zu früh)
S10_LAG_MIN_AGED_N       = 10    # Unter dieser Stichprobengröße → skip

