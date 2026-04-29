# Session-Handover — Stand 30.04.2026

## Heute implementiert (chronologisch)

- `d7c645b` — feat: Float Turnover als Timing-Sub-Signal
  (Vol/Float, +3/+6/+10 Pkt bei ≥0,5 / 1,0 / 2,0 ·
  Timing-Cap 25 → 30 · graceful Fallback)
- `a3f03f5` — docs: Auto-Handover-Regel bei „Gute Nacht"
  (CLAUDE.md-Sektion mit fester Struktur + Edge-Cases)
- `c1ee76d` — feat: News-Sentiment-Decay nach Alter
  (T+0 = 1.0, T+1 = 0.7, T+2 = 0.4, T+3 = 0.2,
  ≥4 Tage = 0.0 · Fallback 0.5 bei fehlendem ts)
- `9d521fd` — feat: Gap+Hold-Timing-Signal, RS-vs-SPY ersetzt RS-vs-Sektor
  (Strong Hold +5 / Weak Hold +2 / Fail −3 · linear ±3 für RS-SPY ·
  Timing-Cap 30 → 35 · `cur_open` + `prev_close` neu im Stock-Dict)

## Aktive Position (im Secret POSITIONS_JSON)

- **INDI** · Entry 27.04.2026 · 3,76 USD · 35 shares

## Verifikation ausstehend (morgen nach erstem Daily + ki_agent-Tick)

- Float-Turnover-Werte in Detail-Zeilen + Sub-Score Timing
- News-Decay-Wirkung: alte Headlines scoren niedriger (Stichprobe
  ein Ticker mit ≥3-Tage-alten „squeeze"-News prüfen)
- Gap+Hold-Zeile in Karten-Detail (Strong/Weak/Fail/no_gap)
- RS-vs-SPY-Zeile ersetzt RS-vs-Sektor (alte Zeile darf nirgends
  mehr auftauchen)
- Score-Methodik-Sektion zeigt: Timing (0–35), neue Komponenten
  korrekt aufgelistet
- Score-Verteilung Top-10: erwartet leicht höher (im Mittel +3..+5
  Punkte durch Gap-Hold + RS-SPY linearisiert + Turnover)
- Exit-Signale für INDI nach 4 Tagen Haltedauer (sollte noch keine
  Time-Decay-Komponente triggern; Trailing/Setup-Verfall realistisch)

## Geplante Aufgaben

1. **Immediacy-Score-Feature** (vorab-diagnostiziert in dieser Session):
   - Earnings hat als einziger Katalysator vollständige Datums-Persistenz
   - News hat `ts` im Memory, aber nicht persistiert → Datenmodell
     muss erweitert werden für Immediacy
   - Insider hat `pubDate` im Filter, wird aber verworfen
   - UOA / Gamma / P/C sind reine T+0 ohne Spur
   - Erst `agent_signals.json`-Schema um `*_dt`-Felder ergänzen
     bevor das Feature live geht
2. **Phase 2 Exit-Signale** (UI-First): Frontend für Position-Eintragen
   ohne JSON, Watchlist-Karten mit Exit-Score-Block + P&L. Erst nach
   1 Woche Live-Test von Phase 1.
3. **Bahn A2 (Frontend-Auswertungs-Panel)** ab Ende Mai (≥ 200 Live-
   Einträge, Monster-Score als Dimension).
4. **UX Backtesting „Nur Live"-Modus**: Erklärungstext bei n=0
   („Live-Renditestatistik verfügbar ab Mitte Mai").

## Optional / niedrig priorisiert

- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer auf neuen Score-Block migrieren
- `backtest_history.json` einmal cachen statt zwei Disk-Reads
- Alte `RS_SECTOR_*`-Konstanten + `_sector_rs_row()` ganz entfernen
  (aktuell deprecated, aber noch im Code für Rückwärtskompatibilität)
- News-Decay-Logik auf UOA / Insider übertragen via
  `_news_age_weight()`-Wiederverwendung, sobald Persistenz da ist

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **Single Source of Truth pro Sub-Signal:** jedes neue Timing-Signal
  hat genau einen Helper (`_float_turnover_pts`, `_gap_hold_pts`,
  `_rs_spy_pts`), der von `score()`, `_compute_sub_scores()` und
  der Detail-Zeile (`_*_row_html()`) gemeinsam genutzt wird. Pattern
  fortsetzen, keine duplizierten Schwellenvergleiche
- **Score-Block-Cap-Konvention:** RV+Mom werden weiterhin auf 25 von
  37 normiert (`(rv_pts + mom_pts) * 25.0 / 37.0`); neue Signale
  werden ungescaled obendrauf addiert; `SUB_TIMING_MAX` deckt die
  Erweiterung ab. Beim nächsten Add: Cap entsprechend anheben, RV+Mom-
  Faktor 25/37 nicht anfassen
- **`cur_open` + `prev_close` im Stock-Dict** — werden in `_hist_stats()`
  und `get_yfinance_data()` extrahiert; Konsumenten: Gap+Hold-Helper
  und (potentiell) künftige Intraday-Strength-Signale
- **RS-vs-Sektor deprecated:** `rel_strength_sector` und `sector_etf`
  bleiben im Datenmodell und in den Konstanten, werden aber nicht
  mehr gerendert/bewertet. `_sector_rs_row()` ist nicht mehr verdrahtet
- **Auto-Handover-Regel:** `CLAUDE.md` definiert jetzt verbindlich die
  Struktur und den Trigger („Gute Nacht" + Varianten). Künftige
  Sessions folgen automatisch diesem Format
