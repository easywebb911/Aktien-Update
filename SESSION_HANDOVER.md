# Session-Handover — Stand 01.05.2026

## Heute implementiert (chronologisch)

- `19a27a0` — style: Watchlist-Voransicht-Kacheln auf Mobile verkleinert
  (4 Spalten bleiben, Padding/Schrift/Icons ~50 % geschrumpft,
  Touch-Target X-Button via ::before-Overlay 44×44)
- `f7aa4aa` — fix: Watchlist-Grid-Overflow auf Mobile
  (`min-width:0` auf Grid-Items + Flex-Children, Ticker mit
  `text-overflow:ellipsis`)
- `f31018a` — style: US-Flagge auf Mobile-Watchlist entfernt,
  Ticker auf 0,85 rem
- `3618594` — fix: Ticker-Readability auf Mobile
  (Star-Badge entfernt, ki-dot `scale(.6)`, X-Button 22 px,
  letter-spacing kondensiert)
- `14a9de1` — fix: Wide-Glyphen-Ticker (GRPN/GOOG/MMMM)
  (font-size 0,7 rem, letter-spacing −0,04 em, `font-stretch:condensed`)
- `469e1d7` — fix: Exit-Score-Symmetrie raw vs. raw
  (`setup_today` jetzt aus `score_history.latest`, nicht mehr aus
  `setup_scores`-smoothed; INDI-Drop fällt von 30 auf 11 Pkt)
- `ee0aac5` — feat: Anomalie-basierte Push-Trigger ersetzen Monster≥70
  (sechs Trigger: RVOL-Explosion / UOA-Extreme / Score-Sprung /
  Gap+Hold-Combo / Perfect Storm / Monster ≥90 als Backup;
  Cooldown 6 h pro Ticker × Trigger-Typ; `gap_states` neu in
  `app_data.json`, `uoa_atm_ratio` neu in `agent_signals`)
- `23a3e84` — feat: Chat-System-Prompt-Refactor für Synthese statt
  Score-Wiedergabe (Anomalien zuerst → Position-Kontext → Score
  als Kontext; explizite Kritik-Erlaubnis;
  `_build_chat_synthesis_ctx()` baut neuen strukturierten Context
  mit Yesterday-Diff, Anomalien, Top-10-Eintritten/-Austritten,
  Position-PnL)
- `65f6b23` — feat: USD/EUR-Anzeige in Chat + KI-Analyse
  (yfinance EURUSD=X im Daily-Run, `fx_usd_eur` in `app_data.json`,
  Modul-Variable `_FX_USD_EUR`, Format „$4.47 (4,11 €)" verbindlich
  via System-Prompt; `window._FX_USD_EUR` als Frontend-Bridge)
- `f3937d2` — docs: Score-Methodik-Sync-Regel in CLAUDE.md
  (Pflichtanpassung der Methodik-Sektion bei jeder relevanten
  Code-Änderung, sieben Bereiche dokumentiert, Negativliste)
- `c958214` — fix: `.agent-dot`-Schwellen an `apply_monster_score`-
  Semantik gekoppelt (60/30/15 statt 70/40/15;
  `KI_DOT_STRONG/MODERATE/WEAK` als Konstanten in `config.py`,
  via f-String-Interpolation in JS injiziert; Grün-Quote
  verdoppelt sich)

## Aktive Position (im Secret POSITIONS_JSON)

- **INDI** · Entry 27.04.2026 · 3,76 USD · 35 shares · aktuell
  ~+19 % (Spot $4,47); Exit-Score nach raw-vs-raw-Fix bei 16,4

## Verifikation ausstehend (morgen nach erstem Daily + ki_agent-Tick)

- Watchlist-Layout auf realem iPhone — kein Ticker-Cut, X-Button
  weiterhin treffsicher (44×44-Hit-Area)
- Anomalie-Push-System: erster echter Push einer Anomalie statt
  Monster≥70-Auslösung; `agent_state.json.cooldowns` enthält
  `anomaly_<trigger>_<ticker>`-Keys
- `app_data.json` enthält neue Top-Level-Felder `gap_states` und
  `fx_usd_eur` nach Daily; ki_agent-Tick preserviert beide
- Chat synthetisiert (zeigt Anomalien zuerst, nicht Top-1-Score)
- KI-Analyse-Output enthält EUR-Beträge in Klammern bei Einstieg/
  Stop-Loss/Profit-Targets
- `.agent-dot` zeigt mehr Grün; mind. 2 Tickers ≥60 KI-Score
  pulsieren grün

## Geplante Aufgaben

1. **Phase 2 Exit-Signale** (UI-First): Frontend für Position-
   Eintragen ohne JSON, Watchlist-Karten mit Exit-Score-Block + P&L.
   Erst nach 1 Woche Live-Test von Phase 1.
2. **Immediacy-Score-Feature** (Vorab-Diagnose vom 30.04. liegt vor):
   Datenmodell-Erweiterung nötig — `*_dt`-Felder in
   `agent_signals.json` für Insider/News/UOA persistieren, dann
   Frische-Ranking implementieren.
3. **Bahn A2 (Frontend-Auswertungs-Panel)** ab Ende Mai
   (≥ 200 Live-Einträge, Monster-Score als Dimension).
4. **UX Backtesting „Nur Live"-Modus**: Erklärungstext bei n=0
   („Live-Renditestatistik verfügbar ab Mitte Mai").
5. **Setup-Verfall-Symmetrie weiter beobachten**: jetzt raw vs. raw —
   ein paar Tage prüfen ob Drops jetzt seltener triggern (sollten).

## Optional / niedrig priorisiert

- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer (`buildWlDetails`) auf neuen Score-Block migrieren
- `backtest_history.json` einmal cachen statt zwei Disk-Reads
- Alte `RS_SECTOR_*`-Konstanten + `_sector_rs_row()` ganz entfernen
- News-Decay-Logik auf UOA / Insider übertragen via
  `_news_age_weight()`-Wiederverwendung, sobald Persistenz da ist
- KI-Agent-eigene Anomalien (UOA / RVOL-Vortagsvergleich /
  Gap+Hold-Combo) auch in den Chat-Kontext einspeisen — aktuell
  nur Daily-Run-zugängliche Trigger

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **Anomalie-Push-System** ersetzt Monster-Schwelle: sechs Trigger,
  per-Trigger-Cooldown via Key-Prefix `anomaly_<trigger>_<ticker>`
  in `agent_state.json`. Earnings-Sofort-Alert behält Vorrang.
- **`uoa_atm_ratio` + `uoa_cp_ratio`** sind jetzt persistiert in
  `agent_signals.signals[ticker]` — UOA-Extreme-Trigger liest direkt,
  keine String-Parses mehr. `fetch_uoa_signal` returnt jetzt
  `(score, drivers, meta)`.
- **`gap_states` in `app_data.json`** (`{ticker: {pct, state}}`),
  geschrieben vom Daily-Report via `_gap_hold_pts()`. KI-Agent liest
  für Gap+Hold-Combo-Trigger; `save_signals()` Read-Modify-Write
  preserviert das Feld.
- **`_FX_USD_EUR` Modul-Variable** als Single-Source-of-Truth für
  USD→EUR. Daily-Run setzt sie via yfinance EURUSD=X, fail-soft
  mit `app_data.json`-Fallback und Notnagel `0.92`. Frontend-Bridge
  `window._FX_USD_EUR` für externe JS-Konsumenten (KI-Analyse).
- **Strukturierter Chat-Kontext** — `STOCKS_CTX` ist jetzt ein Dict
  (nicht mehr Liste): `today_top10`, `anomalies_today`,
  `topten_changes`, `positions`, `today_date`, `yesterday_date`,
  `fx_usd_eur`. Chip-Vorschläge sprechen Anomalie-Mover und
  Position an, nicht mehr Top-1-Score.
- **Exit-Score raw-vs-raw** — `setup_at_entry` und `setup_today`
  beide aus `score_history` (raw). `setup_scores` (smoothed) wird
  nur fürs Frontend genutzt. Alter raw/smoothed-Mismatch ist Bug-
  History.
- **`KI_DOT_STRONG/MODERATE/WEAK` als config-Konstanten** —
  Dot-Schwellen sind explizit an `apply_monster_score`-Semantik
  (≥60 → Boost) gekoppelt. JS-Block liest sie via f-String-
  Interpolation; künftige Schwellen-Anpassungen in einer Datei.
- **Score-Methodik-Sync-Regel** (CLAUDE.md `f3937d2`):
  Methodik-Sektion in `generate_report.py:4170+` muss bei jeder
  Filter-/Score-/Boni-/Trigger-/Datenquellen-Änderung im selben
  Commit mit aktualisiert werden — automatisch, ohne User-
  Aufforderung.
