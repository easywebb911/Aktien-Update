"""Gemeinsame Konfigurations-Konstanten für generate_report.py und ki_agent.py.

Änderungen an Schwellen, Timeouts und Score-Gewichten hier vornehmen —
nicht mehr in den einzelnen Skript-Dateien. Beide Skripte importieren die
Werte via ``from config import *``.
"""

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
# Service-Worker + Lazy Loading für schnellere PWA-Erfahrung.
# SW_CACHE_VERSION wird bei jedem Report-Run automatisch auf einen Zeitstempel
# gesetzt — alte Caches werden dadurch beim nächsten Besuch invalidiert.
SW_ENABLED         = True
LAZY_CARDS_ENABLED = True
LAZY_CARDS_EAGER   = 3        # erste N Karten sofort vollständig rendern

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
SUB_TIMING_MAX      = 25

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

# ── IBKR Stock Borrow Rates (public Web-Scraping) ────────────────────────────
# Holt Borrow Rates von https://www.interactivebrokers.com/en/trading/stock-borrow-rates.php
# Seite wird einmal pro Run gescraped + gecacht. Bei HTTP-Fehler, Timeout,
# fehlendem Ticker oder Cloudflare-Block → borrow_rate = None (kein Absturz).
IBKR_BORROW_ENABLED      = True
IBKR_BORROW_URL          = "https://www.interactivebrokers.com/en/trading/stock-borrow-rates.php"
IBKR_BORROW_TIMEOUT      = 8        # (connect, read) Tupel-Timeout — hart genug gegen Cloudflare-Hänger
IBKR_BORROW_LOW          = 10.0     # < 10 %/Jahr → grau (günstig)
IBKR_BORROW_HIGH         = 50.0     # > 50 %/Jahr → rot (sehr teuer für Shorts)
IBKR_BORROW_BONUS_HOT    = 8        # Katalysator-Bonus bei > 50 %/Jahr
IBKR_BORROW_BONUS_EXTREME = 15      # Katalysator-Bonus bei > 100 %/Jahr

# ── Put/Call-Ratio in Katalysator-Sub-Score ─────────────────────────────────
# PC-Ratio < 0.5 = bullisch (viele Calls) → +Bonus
# PC-Ratio > 1.5 = bearisch (viele Puts)  → -Malus
PC_RATIO_BULL_THRESHOLD = 0.5
PC_RATIO_BEAR_THRESHOLD = 1.5
PC_RATIO_BULL_BONUS     = 5
PC_RATIO_BEAR_MALUS     = 3

# ── Relative Stärke vs. Sektor-ETF in Timing-Sub-Score ──────────────────────
# RS > +5 % → +Bonus (Ticker schlägt Sektor deutlich)
# RS < −5 % → −Malus (Ticker hinkt Sektor hinterher)
RS_SECTOR_THRESHOLD    = 5.0
RS_SECTOR_BULL_BONUS   = 3
RS_SECTOR_BEAR_MALUS   = 2

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
EARNINGSWHISPERS_ENABLED = True
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
STOCKTWITS_ENABLED      = True
STOCKTWITS_TIMEOUT      = 5    # Sekunden
STOCKTWITS_BULL_STRONG  = 15   # Bullish-Ratio > 0.70 + Volume > 10/h
STOCKTWITS_BULL_WEAK    = 8    # Bullish-Ratio > 0.60
STOCKTWITS_BEAR_MALUS   = 5    # Bearish-Ratio > 0.70 → -Pkt

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

# 5 — Relative Stärke gegen Sektor-ETF (statt nur gegen S&P 500)
USE_SECTOR_RS = True
SECTOR_ETF_MAP = {
    "Technology":            "QQQ",
    "Communication Services":"QQQ",
    "Healthcare":            "XBI",
    "Biotechnology":         "XBI",
    "Energy":                "XLE",
    "Financial":             "XLF",
    "Financial Services":    "XLF",
    "Consumer":              "XRT",
    "Consumer Cyclical":     "XRT",
    "Consumer Defensive":    "XRT",
}
SECTOR_ETF_DEFAULT = "SPY"
SECTOR_ETFS_ALL    = ("QQQ", "XBI", "XLE", "XLF", "XRT", "SPY")

# 6 — Historische Squeeze-Erkennung (90-Tage-Fenster)
SQUEEZE_DETECTION_DAYS = 90
SQUEEZE_MIN_GAIN       = 0.50   # ≥ +50 % in 5 Handelstagen
SQUEEZE_MIN_RVOL       = 3.0    # gleichzeitig Volumen ≥ 3× Ø


# ═══════════════════════════════════════════════════════════════════════════
#  ki_agent.py — Alert-Schwellen, Signal-Scores, Trigger
# ═══════════════════════════════════════════════════════════════════════════

# ── Alert-Basis-Schwellen ────────────────────────────────────────────────────
ALERT_THRESHOLD         = 25   # Fallback (wird durch Phasen-Schwellen ersetzt)
ALERT_THRESHOLD_STRONG  = 70   # Score ≥ → ⚡⚡ Starker Alert
ALERT_COOLDOWN_HOURS    = 2    # Mindeststunden zwischen Alerts je Ticker

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
SEC_HEADERS    = {"User-Agent": "SqueezeReport/1.0 github-actions@squeeze-report.com"}
