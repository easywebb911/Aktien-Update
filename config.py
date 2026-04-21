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
COMBO_BONUS              = 5    # Synergie-Bonus ≥ 3 von 4 Faktoren stark

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
ALERT_THRESHOLD         = 15   # Fallback (wird durch Phasen-Schwellen ersetzt)
ALERT_THRESHOLD_STRONG  = 70   # Score ≥ → ⚡⚡ Starker Alert
ALERT_COOLDOWN_HOURS    = 2    # Mindeststunden zwischen Alerts je Ticker

# ── Phasenabhängige Alert-Schwellen ──────────────────────────────────────────
ALERT_THRESHOLD_REGULAR    = 15   # 09:30–16:00 ET Regulärer Handel
ALERT_THRESHOLD_PREMARKET  = 15   # 04:00–09:30 ET
ALERT_THRESHOLD_AFTERHOURS = 15   # 16:00–20:00 ET
ALERT_THRESHOLD_CLOSED     = 15   # Wochenende / außerhalb der Handelszeit

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
