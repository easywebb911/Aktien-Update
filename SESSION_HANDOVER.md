# Session-Handover — Stand 06.05.2026

## Heute implementiert (chronologisch)
- 1b64353 — fix: NameError 'ticker' in generate_report.py:6178
  (JS-Kommentar mit {ticker}-Token in Python-f-String — durch
  EUR-Stufe 3 ea52cfd eingeschleppt, Daily-Workflow scheiterte)
- 726debf — fix: KI-Insight Score-Sprung (Builder #4) zeigt
  veraltete Tickers wie XRX. Aktualitäts-Filter (lastDate ===
  today) + Universums-Cross-Check gegen setup_scores/
  monster_scores ergänzt
- 4dfc140 — chore: node_modules/ in .gitignore (jsdom für
  Smoke-Test, kein Repo-Inhalt)
- cc9e9f9 — fix: Watchlist-Drift zwischen Browser und Gist —
  3 von 4 Frontend-Schreibpfaden updaten den Gist nicht.
  Helper _wlGistSyncWatchlist in wlAddManual, wlToggle,
  wlRemoveTicker eingebaut. SNBR-Resurrection beim
  nächsten Workflow-Tick gestoppt.
- 742a1ab — feat: KI-Insight-Stream Tier-1-Erweiterung —
  5 neue Builder (Earnings ≤3T, FINRA-Trend-Beschleunigung,
  RVOL-Spike, Position-PnL-Highlight, Insider-Käufe).
  Damit 12 Insight-Quellen statt 7 — Banner robust gegen
  ruhige Tage.

## Aktive Positionen
- GRPN · offen · läuft im Plus
- AMC · offen · läuft im Plus

## Verifikation morgen früh
- Daily-Run regeneriert index.html mit:
  - KI-Insight-Banner mit 12 Builder-Quellen (sollte
    deutlich häufiger ≥4 Items haben)
  - XRX-Stale-Bug behoben (Aktualitäts-Filter aktiv)
  - Watchlist-Drift behoben (User-Edits werden
    Gist-synchronisiert)
- SNBR sollte nach heutigem Entfernen wegbleiben
  (verifiziert)

## Offene Tests/Beobachtungen
- Beim nächsten Cmd+Shift+R: schauen ob Unlock-Modal
  (nur Master-Passwort) oder Setup-Modal (Token + 2 PW)
  kommt. Setup-Modal würde auf localStorage-Eviction
  hindeuten (z.B. iOS Safari Storage-Räumung).

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
   (EMA21, VWAP-Position, Bollinger-Band-Squeeze)
10. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen
11. Filter-Flexibilisierung prüfen (Bahn A2)
12. Phase X — v1-Pfad-Migration (drei Schritte zusammen)
13. Phase 2 Trigger 4-6 aktivieren (Setup-Erosion,
    Catalyst, Trend-Bruch)
14. Tier-2-Insight-Builder als Reserve falls 12er-Suite
    nicht reicht: Sektor-Cluster, Days-to-Cover-Spitze,
    52w-Distance

## Optional / niedrig priorisiert
- IBKR Borrow Rate liefert konstant HTTP 404
- DOUBTFUL Cleanup-Items
- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert
- Watchlist-Drawer (buildWlDetails) auf neuen Score-Block
- backtest_history.json einmal cachen
- News-Decay-Logik auf UOA / Insider übertragen
- KI-Agent-eigene Anomalien in Chat-Kontext
- EDGAR_ACTIVIST_FILERS-Liste verfeinern
- Smoke-Test um weitere Pfade erweitern
- Verwaister Remote-Branch claude/diagnose-xrx-banner-bug
  bereits gelöscht, andere Feature-Branches (last week,
  2 weeks ago) ggf. aufräumen

## Architektur-Anker (in CLAUDE.md, hier als Reminder)
- Master-Passwort-Token-Encryption (Single-Reader,
  Two-Tier-Storage)
- Watchlist-Score Single-Source-of-Truth
- v1/v2-Render-Pfad — v2 NICHT autark
- Push-Silence-Filter
- top10_metrics + Phase 2 exit_state
- JSON-Sanitizer (NaN/Infinity)
- USD/EUR-Anzeige (flache Schema-Struktur, write-once
  entry_fx)
- Frontend-Watchlist-Sync (NEU): Browser muss bei jedem
  Watchlist-Edit BEIDE Stores updaten (Repo-File via wlSave
  + Gist via _wlGistSyncWatchlist), sonst werden User-Edits
  vom nächsten Workflow-Tick zurückgerollt.

## Smoke-Test-Status
scripts/smoke_render.js: jetzt 14 Szenarien, alle 14 grün.
Heute erweitert: KI-Insight-Score-Sprung-Filter,
Watchlist-Sync, 5 neue Insight-Builder.
Echter f-String-Crash-Test (generate_html_v1-Aufruf mit
Mock) ist jetzt Standard-Pflichtcheck nach NameError-Bug
mit {ticker}.

## Heutige große Themen
- Daily-Workflow-Crash NameError {ticker} sofort gefixt
- Watchlist-Drift-Bug zwischen Frontend und Gist behoben
- KI-Insight-Banner robust gegen Stale-Daten + ruhige Tage
- Phase 2 EUR-Migration (Stufe 4 von gestern verifiziert)
