# Session-Handover — Stand 29.04.2026

## Heute implementiert (chronologisch)

- `74e2a43` — perf: Pages-Verify nur bei manuellem Trigger
  (Cron-Laufzeit 1m 48s → ~1m 07s)
- `c1d50f4` — fix: Alert liest Monster + KI aus app_data.json
  (Single Source of Truth, save_signals() preserved monster_scores)
- `5f2848f` — fix: Chat-Scroll innerhalb .chat-msgs statt .chat-panel
  (min-height:0 + overflow-y:auto, iOS-Properties)
- `8b6675f` — fix: smoothed Setup-Score in app_data.setup_scores
  persistiert (Alert + Kachel jetzt vollständig konsistent)
- `82c05ad` — chore: ki_agent stündlich statt alle 2h
  (Cooldown 2h unverändert)
- `bdcc8f3` — feat: Exit-Signale Phase 1
  (positions.json aus GitHub Secret POSITIONS_JSON,
  4 Komponenten: Trailing 40 % / Setup-Verfall 25 % /
  Distribution 20 % / Time-Decay 15 %, Alert ≥ 60,
  Profit-Take ≥ +50 %, Cooldown 4 h)
- `1c7cc42` — docs: Score-Methodik-Sektion aktualisiert
  (UOA, StockTwits, RVOL, Velocity, Perfect-Storm,
  ki_agent stündlich, Datenquellen vervollständigt)

## Aktive Position (im Secret POSITIONS_JSON)

- **INDI** · Entry 27.04.2026 · 3,76 USD · 35 shares

## Verifikation ausstehend (morgen nach erstem Daily + ki_agent-Tick)

- Alert-Konsistenz Setup/Monster/KI = Kachel-Werte
- UOA-Werte in Logs + `agent_signals.json`
- Score-Methodik-Sektion live aktualisiert
- Exit-Signal-Lauf für INDI (vermutlich kein Alert wegen junger Position)
- Cron-Laufzeit ~1m 07s ohne Pages-Verify

## Geplante Aufgaben

1. **Phase 2 Exit-Signale** (UI-First mit Workflow-Trigger):
   - Frontend für Position-Eintragen ohne JSON
   - Watchlist-Karten mit Exit-Score-Block + P&L
   - Erst nach 1 Woche Live-Test von Phase 1
2. **Bahn A2 (Frontend-Auswertungs-Panel)** ab Ende Mai
   (braucht ≥ 200 Live-Einträge, Monster-Score als Dimension)
3. **UX Backtesting „Nur Live"-Modus**: Erklärungstext bei n=0
   („Live-Renditestatistik verfügbar ab Mitte Mai")

## Optional / niedrig priorisiert

- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer auf neuen Score-Block migrieren
- `backtest_history.json` einmal cachen statt zwei Disk-Reads

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- `_score_block_inner_html()` = kanonische Quelle für Score-Block
- `_tri_score_color()` = kanonische Farbfunktion (≥60 grün,
  30–59 orange, <30 rot)
- Sort-Modus client-seitig via `localStorage['squeeze_sort_mode']`
- `app_data.json` = Single Source of Truth für Frontend +
  Alert-Lookup (`monster_scores`, `setup_scores`,
  `agent_signals.signals`)
- `save_signals()` ist Read-Modify-Write: preserved
  `monster_scores` + `setup_scores` + `watchlist_cards`
  (Owner: Daily), überschreibt nur `agent_signals` +
  `score_history` (Owner: ki_agent)
- `positions.json` niemals committen (in `.gitignore`), kommt aus
  GitHub Secret `POSITIONS_JSON`
