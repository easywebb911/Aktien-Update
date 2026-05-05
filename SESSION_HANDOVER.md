# Session-Handover — Stand 05.05.2026

## Heute implementiert (chronologisch)
- a076115 — fix: Workflow-Pipeline-Bugs (watchlist_personal.json
  + agent_state.json zu git add ergänzt, Recovery-Logik
  präzisiert) nach GIST_TOKEN-Update via Repo-Settings
- 4aa8cce — feat: Phase 2 — overheated-Trigger auch außerhalb
  Top-10 (ChannelTSV erweitert via _all_metrics)
- 21dcc4c — fix: Bug A+B (c.update fehlende change_2d/change_3d,
  Position-only-Ticker im personal_tickers-Merge)
- ec7affd — feat: move_3d im overheated-Trigger aktiviert
  (3 Sub-Skalen Maximum)
- 6d358a7 — feat: pull_gist_data.py Recovery-Logik aus voriger
  app_data.json
- 0eab188 — docs: Backlog Verifikations-Aufgabe für
  POSITIONS_JSON-Secret-Löschung (Wiedervorlage 19.05.2026)
- 82911fb — feat: KI-Insight-Stream-Banner (Variante D ohne
  Emojis, Pfad 2 zwischen stats-bar und cards-grid, Hover-Pause,
  prefers-reduced-motion-Fallback, 7 Insight-Builder)
- d02b1f9 — refactor: Score-Methodik anfänger-freundlich
  (Squeeze-Story mit Feuer-Metapher Brennstoff/Funke/Flamme,
  Tooltips für Abkürzungen via native abbr-title, KI-Agent-Block
  entschlackt)
- b923a35 — feat: Profi-Details-Akkordeon mit allen
  Push-Schwellen via f-string-Injection aus config.py
- 7b1df0a — fix: KI-Analyse-Clipping-Bug via CSS :has-Selector
  (content-visibility:visible bei offener KI-Analyse)
- ee6a4c9 — feat: EUR-Stufe 1 — fx_usd_eur_computed_at +
  entry_fx/fx_estimated in positions.json (flache Schema-Struktur,
  Pfad 2)
- 7a4eba3 — feat: EUR-Stufe 2 — UI-Anzeige $X.XX / Y,YY€
  im Position-Panel (Helper _formatPositionEntry mit
  dreistufiger Fallback-Kette)
- ea52cfd — feat: EUR-Stufe 3 — USD+EUR im Eröffnungs- und
  Schließen-Dialog (Live-Preview via oninput, 4 Helper,
  closed_trades um exit_fx/exit_fx_eur/realized_pnl_eur erweitert)
- c568590 — fix: KI-Analyse-Truncation (max_tokens 600→900,
  stop_reason-Detection mit UI-Notice bei max_tokens-Stopp)
- 6eedc8b — feat: EUR-Stufe 4 — Trade-Journal historische
  EUR-Werte, entry_fx-Schema-Lücke aus Stufe 3 mitgeschlossen,
  3 Resolver-Helper

## Aktive Positionen
- GRPN · offen · läuft im Plus
- AMC · offen · läuft im Plus

## Verifikation morgen früh
- Daily-Run regeneriert index.html mit allen heutigen UI-Features:
  - KI-Insight-Stream-Banner zwischen Stat-Tiles und Cards
  - Score-Methodik im neuen Anfänger-freundlichen Format
  - Profi-Details-Akkordeon mit f-string-injizierten Schwellen
  - KI-Analyse-Clipping behoben (auch auf Karten ab Rang 4)
  - Position-Panel mit USD+EUR Einstiegskurs
  - Eröffnungs-/Schließen-Dialog mit Live-EUR-Preview
  - Trade-Journal mit historischen EUR-Werten
- Phase 2 läuft jetzt komplett für GRPN/AMC mit echten
  RSI/2T-Move/3T-Move-Werten

## Geplante Aufgaben
1. Phase 2 Stufe 3 (Push-Pipeline) — frühestens Donnerstag/
   Freitag, drei Push-Klassen, exitp2_*-Cooldown-Prefix,
   2-3 Tage Stabilitäts-Voraussetzung
2. Phase 3 Exit-Signale (Wiedervorlage 15.05.2026) —
   Blow-off-Top + IV-Crush
3. Score-Aufschlüsselung pro Karte (Phase Y, Backlog) —
   6 Schichten anzeigen beim Klick auf Setup-Score
4. Immediacy-Score-Feature
5. Bahn A2 (Frontend-Auswertungs-Panel) ab Ende Mai
6. UX Backtesting "Nur Live"-Modus
7. Setup-Verfall-Symmetrie weiter beobachten
8. ⏰ Wiedervorlage 19.05.2026: app_data-recovery-Logik
   bei nächstem Gist-Hiccup verifizieren, dann
   POSITIONS_JSON-Secret löschen
9. ⏰ Wiedervorlage 02.06.2026: Chart-Indikatoren prüfen
   (EMA21, VWAP-Position, Bollinger-Band-Squeeze;
   NICHT MACD/Stochastic/Ichimoku/Fibonacci)
10. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen
11. Filter-Flexibilisierung prüfen (Bahn A2)
12. Phase X — v1-Pfad-Migration (drei Schritte zusammen,
    siehe CLAUDE.md-Sektion v1/v2-Render-Pfad)
13. Phase 2 Trigger 4-6 aktivieren sobald Datenquellen da:
    Setup-Erosion (DTC/Short-Float/CtB beim Entry persistieren),
    Catalyst (Earnings-Datum + Score-3T-nach), Trend-Bruch (EMA21)

## Optional / niedrig priorisiert
- IBKR Borrow Rate liefert konstant HTTP 404 — Provider-
  Fallback prüfen
- DOUBTFUL Cleanup-Items (rel_strength_sector / sector_etf,
  MIN_REL_VOLUME_INTL)
- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert
- Watchlist-Drawer (buildWlDetails) auf neuen Score-Block
- backtest_history.json einmal cachen
- News-Decay-Logik auf UOA / Insider übertragen
- KI-Agent-eigene Anomalien in Chat-Kontext
- EDGAR_ACTIVIST_FILERS-Liste verfeinern
- Smoke-Test um weitere Pfade erweitern

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption (Single-Reader, Two-Tier-Storage)
- Watchlist-Score Single-Source-of-Truth (3-Stufen-Priorität)
- v1/v2-Render-Pfad — v2 NICHT autark, ruft v1 für Outer-Page
- Push-Silence-Filter (RSI > 75 ODER 2T-Move > 20%)
- top10_metrics + Phase 2 exit_state (read-modify-write mit
  **existing-Spread)
- JSON-Sanitizer (NaN/Infinity entfernt vor json.dump,
  allow_nan=False, beide Writer)
- USD/EUR-Anzeige (NEU): flache Schema-Struktur
  app_data.json["fx_usd_eur"] + computed_at, entry_fx in
  positions.json write-once, exit_fx/exit_fx_eur/
  realized_pnl_eur in closed_trades, Renderer-Resolver mit
  Fallback-Kette (exakte FX-Felder → Aktuell-FX)

## Smoke-Test-Status
scripts/smoke_render.js: jetzt 12 Szenarien, alle 12 grün.
Heute mehrfach erweitert: Phase 2 non-Top-10-Position,
move_3d-Trigger, KI-Insight-Banner, Position-Panel-EUR,
Open-/Close-Dialog-EUR, Trade-Journal-EUR. Smoke-Test
extrahiert die JS-Funktion direkt aus generate_report.py
(robust gegen Render-Verzug der index.html).

## Heutige große Themen
- Workflow-Pipeline restored nach GIST_TOKEN-Update
- Phase 2 läuft komplett für offene Positionen außerhalb Top-10
- USD/EUR-Migration in 4 Stufen abgeschlossen
- Score-Methodik anfänger-freundlich umgestaltet
- KI-Analyse: Clipping-Bug + Truncation-Bug beide gefixt
