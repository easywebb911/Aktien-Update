# Session-Handover — Stand 03.05.2026 (Abend-Update)

## Heute implementiert (chronologisch)
- 8a71e30 — fix: leftover _sort_keeping_manual_last call site
- 4b04322, e2e1b81, a31ddfb, 864d818 — feat: Phase 3
  Master-Passwort-Token-Encryption (mehrere Iterationen,
  inkl. iOS-Storage-Quirk-Fixes und Settings-Panel-Routing-Fix)
- 53b1d4e — feat: Auto-Redeploy-Workflow (redeploy-on-source-change)
- 71a78fc — chore: Setup-Score-Tooltip entfernt
- 415177e — refactor: Voll-Breite-Layout NUR für Watchlist-
  Drawer (rückgängig auf Top-10)
- ef38982 — fix: Toggle-Chevrons vereinheitlicht (▼ U+25BC)
- abfdd9c — chore: drei statische Quick-Fragen im Chat
- 6e5a4a3 — feat: KI-Score als dritte Sortier-Option +
  Methodik-Sync
- c2118cd — chore: Stockanalysis-Outline-Button (lila Pille weg)
- 498a269 — feat: Watchlist-Tiles kompakt + 3D + Mini-Ring
- 214b7fd — feat: Top-10-Karten-3D-Look (Variante 1B)
- 211c198 — feat: Stat-Tiles eingelassen-3D
- 22a5c82 — feat: TopTen-Banner E3 magazin-haft mit Akzentpunkt
- 0de397b — fix: .sort-ki-Layout für KI-Sortier-Modus
- df4aab5 — fix: Watchlist-Score Single-Source-of-Truth
  (3-Stufen-Priorität: WL_TOP10 → _WL_CARDS → WL_SCORES)
- d82cfcd — feat: Push-Silence-Filter (RSI > 75 ODER 2-Tages-
  Move > 20%) inkl. Methodik-Sync
- a97696b — fix: inTop-ReferenceError in wlRender +
  defensive Härtung _wlScoreOf
- ee91390 — chore: scripts/smoke_render.js (5 Szenarien,
  manuell via node ausführbar)
- e04ba6b — chore: 6 SAFE_DEAD-Items entfernt (RS_SECTOR_*,
  _sector_rs_row, .chart-badge-s, verwaister Kommentar)
- a395233 — docs: v1/v2-Render-Pfad-Architektur-Anker
  (Code-Kommentar + CLAUDE.md-Sektion + Backlog-Eintrag)

## Aktive Position (im Secret POSITIONS_JSON)
- INDI · Entry 27.04.2026 · 3,76 USD · 35 shares
  (in dieser Session nicht berührt)

## Verifikation ausstehend
- Push-Silence-Filter: erst beim nächsten ki_agent-Tick
  aktiv. Beobachten, ob überhitzte Anomalien (z.B. XRX-artige
  Fälle) jetzt korrekt unterdrückt werden mit
  "Bewegung gelaufen"-Badge.
- Watchlist-Score-Konsistenz: nach nächstem Daily-Run
  prüfen, dass Tile + Detail-Card identische Scores zeigen.

## Geplante Aufgaben
1. Phase 2 Exit-Signale (UI-First) nach 1 Woche Live-Test
2. Immediacy-Score-Feature
3. Bahn A2 (Frontend-Auswertungs-Panel) ab Ende Mai
4. UX Backtesting "Nur Live"-Modus
5. Setup-Verfall-Symmetrie weiter beobachten
6. ⏰ Wiedervorlage 15.05.2026: Phase 3 Exit-Signale prüfen
   (Blow-off-Top + IV-Crush)
7. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen
8. Filter-Flexibilisierung prüfen (Bahn A2)
9. Phase X — v1-Pfad-Migration (drei Schritte zusammen):
   page.jinja anlegen, _wl_full_card_html ohne
   Regex-Stripping neu, generate_html_v2 autark.
   Erst dann v1 entfernen. JINJA_RENDER_TEST muss vorher
   die Outer-Page byte-vergleichen können.

## Optional / niedrig priorisiert
- IBKR Borrow Rate liefert konstant HTTP 404 — Provider-
  Fallback prüfen (Stockanalysis o.ä.); aktuell fällt der
  Borrow-Rate-Driver in _drivers_breakdown still aus.
- DOUBTFUL Cleanup-Items aus Diagnose-Bericht prüfen:
  rel_strength_sector / sector_etf (im JS noch gelesen?),
  MIN_REL_VOLUME_INTL (Intl-Screening-Reaktivierung möglich?)
- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer (buildWlDetails) auf neuen Score-Block
  migrieren
- backtest_history.json einmal cachen statt zwei Disk-Reads
- News-Decay-Logik auf UOA / Insider übertragen via
  _news_age_weight(), sobald Persistenz da ist
- KI-Agent-eigene Anomalien (UOA-Vol/OI / RVOL-Vortagsvergleich
  / Gap+Hold-Combo) auch in den Chat-Kontext einspeisen
- EDGAR_ACTIVIST_FILERS-Liste über Live-Beobachtung verfeinern
- Smoke-Test-Suite ggf. um weitere kritische Pfade erweitern

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption: Single-Reader-Pattern
  getToken(), Two-Tier-Storage localStorage encrypted +
  sessionStorage runtime, versioniertes Krypto-Schema (v:1)
- Watchlist-Score Single-Source-of-Truth: 3-Stufen-Priorität
  WL_TOP10 → _WL_CARDS → WL_SCORES, defensive _wlScoreOf
  mit try/catch, Re-Render-Hook nach app_data-Fetch
- v1/v2-Render-Pfad: v2 ist NICHT autark, ruft
  generate_html_v1 für Outer-Page. Wer v1 löscht, killt v2 mit.
  Migration nur in einem Zug (3 Schritte).
- Push-Silence-Filter: Stille bei RSI > 75 ODER 2T-Move > 20%,
  Earnings + EDGAR ausgenommen. Schwellen in config.py.
- top10_metrics in app_data.json: read-modify-write mit
  **existing-Spread bewahrt sie zwischen ki_agent-Ticks.

## Heutige Smoke-Test-Bewährung
scripts/smoke_render.js wurde heute eingeführt und sofort
zweimal automatisch beim Konstanten-Cleanup + Architektur-
Anker-Commit zur Verifikation genutzt — beide Male alle
5 Szenarien grün. Manuell ausführbar via:
  npm install jsdom (in /tmp empfohlen, nicht im Repo)
  node scripts/smoke_render.js
