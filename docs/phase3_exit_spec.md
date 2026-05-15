# Phase 3 Exit-Signal Spec — Blow-off-Top

> **Status:** spec'd 15.05.2026, **noch nicht implementiert**.
> Single-Source-of-Truth für den späteren Code-Bau — alle Werte und
> Schwellen hier sind verbindlich, wenn die Implementation startet.

## Zweck

Phase 2 Exit-Trigger (`score_decay`, `profit_lock`, `overheated`,
`setup_erosion`, `catalyst`, `trend_break`) decken den Verlauf einer
gehaltenen Position über Tage und Wochen ab. Sie schmiegen sich an
graduelle Setup-Erosion, langsame PnL-Spitzen und Trend-Brüche.

**Was sie nicht abdecken**: der **parabolische Endphasen-Squeeze**,
in dem eine Aktie über wenige Tage 50 % oder mehr zulegt und dann
intraday scharf umkippt. Hier ist die Fall-Höhe bei Halten enorm und
die Phase-2-Trigger reagieren typischerweise zu spät, weil Setup-Score
und PnL-Peak erst nach dem Reversal abrutschen.

Phase 3 schließt diese Lücke mit **einem** zusätzlichen Trigger:
`blowoff_top`. IV-Crush als ursprünglich geplanter zweiter Trigger
wurde gestrichen (siehe Sektion E).

## Implementations-Voraussetzung

Phase 3 wird **nicht spekulativ implementiert**. Triggerpunkt für den
Code-Bau ist:

- Easy hält eine offene Position in einem CRMD-artigen Setup
  (parabolische +50 %-in-5-Tagen-Bewegung)
- Phase-2-Trigger haben empirisch zu spät / nicht stark genug
  reagiert (z. B. Position wurde unter Peak verkauft, weil
  `overheated` und `profit_lock` nicht klar genug ausgeschlagen
  haben)

Bis dahin **kein Code**. Die Spec ist abrufbereit, wenn der Bedarf
empirisch belegt ist.

## A) Blow-off-Top Definition

### Konzept

Ein Blow-off-Top ist der **Endpunkt eines parabolischen Anstiegs**,
markiert durch ein scharfes Intraday-Reversal nach mehreren Tagen mit
starkem Aufwärts-Momentum. Die Klassiker-Definition aus der TA-Lehre
erfordert mehrere Bedingungen:

- Mehrere Tage Aufwärts-Momentum mit Beschleunigung
- Volumen-Spike (oft 5–10× Tagesdurchschnitt)
- Intraday großer Wick nach oben + Schluss unter Tages-Mitte
- Reversal-Kerze (rote nach Serie grüner)

### Was wir empirisch aus dem Tool ableiten können

Daily-Run + KI-Agent fetchen **EOD-Bars** aus yfinance. Echte
Intraday-Bars (1-min / 5-min) gibt es nicht. Aber wir haben **Live-Quote-
Polling** für offene Drawer / Watchlist-Karten via Cloudflare-Worker
seit PR #135 — das liefert pro Ticker Spot + `change`-Tages-Prozent
in Echtzeit.

**Das ist ausreichend für eine EOD-Approximation des Blow-off-Top:**
parabolischer 5-Tage-Move (aus yfinance-Batch) + heutiger negativer
Tages-Move (aus Live-Quote oder EOD-Close-vs-Vortag-Close beim
nächsten Daily-Run).

## B) Datengrundlage

| Eingabe | Quelle | Verfügbarkeit für offene Positionen |
|---|---|---|
| `change_5d` (5-Tage-Performance in %) | yfinance Batch via `get_yfinance_batch` | ✓ — alle Pool-Tickers (Top-10 + Watchlist via `_all_metrics`, siehe Phase-2-Pipeline) |
| Heutige Tages-Veränderung in % | Live-Quote über Cloudflare-Worker (`change`-Feld) ODER `cur_close vs prev_close` aus yfinance Batch (EOD-Fallback) | ✓ |
| Live-Quote-Verfügbarkeit | Cloudflare-Worker fetcht single Yahoo-v8-Chart pro Ticker on-demand | ✓ — wenn `QUOTE_PROXY_URL` konfiguriert; sonst Fallback auf EOD |

**Keine zusätzlichen API-Integrationen nötig** — das ist ein klarer
Pluspunkt für Phase 3 gegenüber dem gestrichenen IV-Crush.

## C) Trigger-Bedingung

### Logik

```
Bedingung 1 (Parabolisch):  change_5d ≥ EXIT_BLOWOFF_5D_PCT  (50.0 %)
Bedingung 2 (Reversal):     today_change_pct ≤ EXIT_BLOWOFF_REVERSAL_PCT  (-5.0 %)

trigger = Bedingung 1 UND Bedingung 2  →  crit
einzelne Bedingung allein               →  no trigger
```

**Bewusst konservativ**: 50 % in 5 Trading-Tagen ist eine deutlich
strengere Schwelle als alles in `overheated` (35 % in 3 d / 25 % in 2 d).
Damit feuert `blowoff_top` **nur** bei echten Endphasen-Setups und
nicht bei normaler Volatilität. Empirisch gehen wir von <1 Treffer
pro Monat aus.

### Score-Output (Phase-2-konform)

```
crit  (beide Bedingungen erfüllt)  →  score = 100, crit = True
sonst                              →  score = 0,   crit = False
```

Kein `warn`-Zwischenzustand. Die Bedingung ist binär — entweder beide
Sub-Conditions sind erfüllt (dann ist es ein echtes Endphasen-Signal)
oder eine fehlt (dann nicht).

### Datenquelle für `today_change_pct`

Reihenfolge (analog Phase-2-Trigger):

1. **Live-Quote** (`window._QUOTE_DATA[ticker].change`, siehe
   `_quoteFetchOnce`-Pfad) — primärer Pfad im Frontend wenn Drawer
   offen. Backend hat darauf keinen direkten Zugriff.
2. **EOD-Vergleich** (`cur_close vs prev_close` aus yfinance Batch) —
   primärer Pfad im Daily-Run / KI-Agent-Tick. Funktioniert
   verlässlich postclose, premarket-Snapshots sind unter-skaliert.

Das bedeutet: **`blowoff_top` triggert primär im postclose-Daily-Run**
(21:17 UTC), weil dann der Tages-Close vs. Vortag-Close eindeutig
ist. Premarket-Triggers wären unzuverlässig (Tages-Move noch nicht
ausgeprägt).

## D) Integration in bestehende Pipeline

### Hook-Point

`_compute_exit_state` in `generate_report.py:14111` — neuer Eintrag im
`triggers`-Dict:

```python
triggers = {
    "score_decay":   _exit_p2_trigger_score_decay(...),       # bestehend
    "profit_lock":   _exit_p2_trigger_profit_lock(...),
    "overheated":    _exit_p2_trigger_overheated(...),
    "setup_erosion": _exit_p2_trigger_setup_erosion(...),
    "catalyst":      _exit_p2_trigger_catalyst(...),
    "trend_break":   _exit_p2_trigger_trend_break(...),
    "blowoff_top":   _exit_p3_trigger_blowoff_top(metrics),   # NEU
}
```

### Gewichtung

```python
weights = {
    "score_decay":   0.30,
    "profit_lock":   0.25,
    "overheated":    0.20,   # UNVERÄNDERT — siehe unten
    "setup_erosion": 0.15,
    "catalyst":      0.05,
    "trend_break":   0.05,
    "blowoff_top":   0.05,   # NEU
}
```

Summe = 1.05. Das `composite`-Pressure-Score wird in
`_compute_exit_state` per Gewichts-Normierung (`weighted / total_w`)
auf [0..100] gebracht — kein Problem mit Summe > 1.0.

**Bewusste Entscheidung: `overheated`-Gewicht NICHT reduzieren.**
- `overheated` hat seinerseits drei Sub-Skalen (RSI, 2T-Move, 3T-Move)
  mit Schwellen 25–35 % über kurze Zeitspannen.
- `blowoff_top` triggert erst bei 50 % über 5 d **plus** Reversal.
- Beide Trigger feuern selten gleichzeitig (50 % in 5 d ist die
  strengere Bedingung). Wenn sie es tun, soll der Pressure-Score
  bewusst hoch sein — die Verschmelzung ist gewollt.

### Trigger-Datenbedarf

`_exit_p3_trigger_blowoff_top(metrics)` braucht aus dem `metrics`-Dict:

- `metrics["change_5d"]` (Float in %, kann None sein)
- `metrics["change_today_pct"]` (Float in %) — entweder aus
  `(cur_close - prev_close) / prev_close * 100`, beides bereits in
  `_all_metrics` enthalten

Falls eines fehlt: `available=False`, kein Trigger. Graceful fallback.

### Push-Klasse

`blowoff_top` landet in der **trigger-Klasse** in
`process_exit_signals` (ki_agent.py:1820):

- Cooldown: 24 h pro `(ticker × "blowoff_top")` — Standard für
  trigger-Klasse (`EXIT_PUSH_TRIGGER_COOLDOWN_HOURS = 24`)
- ntfy-Priority: `high` mit Tag `rotating_light`
- Body-Format: `🔻 Exit-Signal {ticker}: blowoff_top crit (5d
  +XX %, heute -X %)`

Eskalation und Warnung sind unverändert — beide reagieren auf den
Composite-Pressure-Score, der durch `blowoff_top` mit Gewicht 0.05
beeinflusst wird.

### Konstanten in `config.py` (neuer Block)

```python
# Phase 3 Exit-Trigger — Blow-off-Top
EXIT_BLOWOFF_5D_PCT          = 50.0   # 5-Tage-Performance ≥ N %
EXIT_BLOWOFF_REVERSAL_PCT    = -5.0   # heutige Tages-Performance ≤ N %
EXIT_PHASE3_W_BLOWOFF_TOP    = 0.05   # Gewicht im Composite-Pressure
```

## E) IV-Crush — gestrichen

IV-Crush war ursprünglich als zweiter Phase-3-Trigger geplant
(„Implied Volatility kollabiert nach Earnings oder Squeeze-Peak,
Options-Premium verfällt schnell"). Im Spec-Workshop 15.05.2026
gestrichen aus zwei Gründen:

1. **Daten-Limits**:
   - `atm_iv` wird heute nur für die Top-5 US-Tickers gefetcht
     (`_OPTS_TOP_N = 5`). Offene Positionen außerhalb der Top-5
     (z. B. Watchlist-only) haben keinen `atm_iv`-Wert.
   - Keine IV-Historie persistiert. Für einen IV-Crush-Vergleich
     bräuchten wir entweder `iv_history.json` (neues Schema +
     Persistenz-Pipeline) oder `entry_atm_iv` als Snapshot beim
     Position-Open (PR-#159-Pattern erweitern).
   - yfinance-Options-Daten sind notorisch instabil (häufige
     Format-Änderungen, fehlerhafte Returns an Wochenenden / bei
     niedriger Optionen-Liquidität).

2. **Trading-Wert für Aktien-Halter gering**:
   - IV-Crush ist primär ein **Optionsschein-Verkäufer**-Signal
     (Optionspremium verfällt). Wer Aktien direkt hält, profitiert
     nicht direkt davon.
   - Bei einem Aktien-Halter ist das relevantere Signal der
     **Kurs-Reversal selbst**, nicht der IV-Drop — und Kurs-Reversal
     fängt `blowoff_top` bereits ab.

Falls IV-Crush in einer späteren Phase relevant wird (z. B. wenn
Easy auf Options-Trading umstellt), kann die Spec ergänzt werden.
Bis dahin ist `blowoff_top` der einzige Phase-3-Trigger.

## Verifikations-Plan (für die spätere Implementation)

Vor Code-Bau: dieses Spec-File als Anker; nach Code-Bau
verifizieren mit:

- Mock-Tests: 4 Cases (parabolisch+Reversal=crit, nur parabolisch=no
  trigger, nur Reversal=no trigger, fehlende Daten=available=False)
- Empirik nach 2–4 Wochen Live-Daten: wie oft hat `blowoff_top`
  gefeuert? Bei welchen Tickers? Konflikte mit `overheated`?
- Falls zu selten / zu spät: Schwellen anpassen
  (`EXIT_BLOWOFF_5D_PCT` 50 → 40, `EXIT_BLOWOFF_REVERSAL_PCT`
  −5 → −3)

## Pflege

- Schwellen-Änderungen: nur in `config.py`, Code-Logik liest rein
  über Konstanten.
- Falls Phase 3 später um weitere Trigger erweitert wird (Volume-
  Climax, Gap-and-Fail u. ä.): diese Spec ergänzen, neue Sektionen
  D2/D3 ergänzen.
- Falls IV-Crush reaktiviert wird (Easy auf Options-Trading): Sektion
  E reaktivieren und Implementations-Plan ausarbeiten.
