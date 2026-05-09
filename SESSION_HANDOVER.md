# Session-Handover — Stand 09.05.2026

## Heute implementiert (chronologisch, alle gemerged via PR)

- `24e039b` — fix: thesis/lesson über Validation-Re-Render erhalten
  (Bug A Trade-Journal) — gemerged via PR #67
- `ca4604b` — docs: CLAUDE.md Git-Workflow auf reine PR-Strategie
  umgestellt — gemerged via PR #68
- `f29f8ee` — feat: Phase 2 Stufe 3c-1 — Push-History-Persistenz
  (4 ntfy-Sender instrumentiert, FIFO Cap 100) — gemerged via PR #69
- `adbb079` — feat: Pre-Market-Volume als Earliness-Komponente
  (Logging-only, additiv mit change_overnight-Filter,
  EARLINESS_PTS_MAX 5→7) — gemerged via PR #70
- `2578fc5` — fix: yfinance Multi-Ticker `group_by='ticker'` im
  Backtest-Backfill (`update_backtest_returns`) — gemerged via PR #72
- `a534352` — feat: Trade-Journal Details-Toggle für thesis/lesson
  (pro Trade-Zeile ausklappbar, lokaler In-Memory-State) — gemerged
  via PR #73

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen · läuft im Plus
- **SABR** · offen · läuft im Plus

## Verifikation morgen früh nach Daily-Run + ki_agent-Tick

- `agent_state.json` hat `push_history`-Sub-Dict (3c-1 live, FIFO ≤ 100).
- `app_data.json` zeigt — sobald Stage 1.5 die Persistenz nachzieht —
  `premarket_volume` in den Stock-Dicts (aktuell by-design nur in
  Workflow-stdout-Logs sichtbar).
- Earliness-Logs zeigen ggf. dritte Komponente `pm_vol_match`.
- Trade-Journal: bei nächstem Close zeigen `thesis` und `lesson` korrekte
  Werte (Bug A live).
- `backtest_history.json`: erste R-Werte für die 21./22.04.2026-Einträge
  sollten nach 1–2 ki_agent-Ticks gefüllt sein (Backfill-Fix `2578fc5`
  wirkt — der erste KI-Agent-Commit der die Datei je modifiziert hat
  ist `8774206`, direkt nach Merge von PR #72).
- Trade-Journal: Details-Toggle erscheint bei jedem Trade mit thesis
  ODER lesson nicht-leer; Trades ohne Notes bleiben kompakt.

## Geplante Aufgaben

1. **Phase 2 Stufe 3c-2** — Materialisierung `push_history` in
   `app_data.json` (NACH 1–2 Tagen Live-Lauf von 3c-1).
2. **Phase 2 Stufe 3c-3** — UI Notification-History (NACH 3c-2).
3. **Stufe Mittel-2** — Score-Effekt für Earliness aktivieren NACH
   1–2 Daily-Runs mit drei Komponenten.
4. **Backtest-T+0/T+1-Auswertung** — Frontend-Verifikation nach 1–2
   Backfill-Tagen: pro Score-Bucket (`<50`, `50–69`, `≥70`) sollte
   `n > 0` für `return_3d/5d/10d` auftauchen, Median-Werte ersetzen
   die `—`-Anzeige.
5. **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
   Daten.
6. **Phase 3 Exit-Signale** — Wiedervorlage 15.05.2026.
7. **Score-Aufschlüsselung pro Karte** (Phase Y).
8. **Immediacy-Score-Feature**.
9. **Bahn A2** — Frontend-Auswertungs-Panel.
10. **UX Backtesting „Nur Live"-Modus**.
11. ⏰ **Wiedervorlage 19.05.2026** — `app_data`-recovery +
    `POSITIONS_JSON`-Secret löschen.
12. ⏰ **Wiedervorlage 02.06.2026** — Chart-Indikatoren.
13. ⏰ **Wiedervorlage 02.07.2026** — Premium-Daten-Stack.
14. **Phase X** — v1-Pfad-Migration.
15. **Phase 2 Trigger 4–6** — Setup-Erosion, Catalyst, Trend-Bruch.
16. **Tier-2-Insight-Builder** als Reserve.

## Heutige große Themen

- **GRPN-Stop-Loss vom Vortag aufgearbeitet** — These und Lesson
  manuell im Gist nachgepflegt.
- **Trade-Journal Bug A** diagnostiziert mit Browser-DevTools-
  Reproduktion, lokal gefixt, gemerged (PR #67).
- **Bug B** war im Parallel-Chat schon gefixt → redundant.
- **Phase 2 Stufe 3c-1** implementiert + reproduziert nach Sandbox-
  Verlust, gemerged (PR #69).
- **Pre-Market-Volume als 3. Earliness-Komponente** implementiert +
  reproduziert, gemerged (PR #70).
- **Multi-Session-Konflikt** mit parallelem Chat erkannt und via
  Patch-Migration aufgelöst (Patches und Sandbox später verloren).
- **Sandbox-Push-Restriktion** erkannt: alle `main`-Pushes via Code
  liefern HTTP 403, Branch-Pushes funktionieren weiterhin.
- **CLAUDE.md auf reine PR-Strategie umgestellt** — ALLE Änderungen
  (Code + Doku) via Branch + PR (PR #68).
- **Backtest-Backfill-Diagnose Stufe 1 + 2 read-only durchgezogen** —
  0/451 DAILY-Einträge mit R-Werten gefunden, Schema/Counts/Cluster-
  Analyse, vier Hypothesen empirisch auf eine reduziert (yfinance
  Multi-Ticker-Form-Mismatch), Live-Probe verifiziert. Fix in
  PR #72: ein zusätzliches `group_by='ticker'` im `yf.download`-Call.
  Erster KI-Agent-Commit der `backtest_history.json` je modifiziert
  hat (`8774206`) bestätigt, dass der Fix wirkt.
- **CLAUDE.md-Earliness-Konsistenz read-only verifiziert** — genau
  eine Sektion, `EARLINESS_PTS_MAX = 7`, drei Komponenten korrekt
  dokumentiert, keine Doppel-Sektion durch Sandbox-Verlust.
- **PM-Vol Live-Status verifiziert** — `premarket_volume` /
  `earliness_pts` / `earliness_breakdown` werden by-design **nicht**
  in `app_data.json` / `index.html` / `backtest_history.json`
  persistiert; Stage 1 ist reines Logging in stdout. Spätere Persistenz
  (z. B. Stage Mittel-2 oder ein Stage 1.5) müsste das nachziehen.
- **Trade-Journal Detail-Ansicht** — pro Trade ausklappbarer
  Details-Toggle, nur wenn thesis ODER lesson nicht-leer (PR #73).

## Wichtige Lernerfahrungen

- **Multi-Session-Arbeit am gleichen Repo nicht mehr machen.**
  Parallele Chat-Sandboxes erzeugen redundante Implementierungen,
  Konflikte und verlorene Patches, sobald eine Sandbox abgebaut wird.
  Single-Session pro Tag ist die Defaultregel.
- **Sandbox-Verluste sind erwartbar.** Code-Stand IMMER über PR auf
  GitHub spiegeln — der gemergte main ist die einzige verlässliche
  Persistenz. Lokale Branches und uncommittete Diffs sind flüchtig.
- **`main`-Pushes sind in der Sandbox blockiert (HTTP 403).** Die
  hybride „Doku direkt main / Code via PR"-Variante hat NICHT
  funktioniert (auch reine Doku-Pushes werden abgewiesen). Ergebnis:
  PR-only-Workflow für alle Änderungen, dokumentiert in CLAUDE.md.
- **Git-Diff vor Commit prüfen.** Mehrfach hat sich die Pflicht-
  Checkliste „nur file X im Diff" als nützlicher Letztcheck erwiesen,
  bevor ein Commit raus geht — verhindert versehentliches Mit-
  Committen von Sandbox-Artefakten (z. B. `node_modules/jsdom`).
- **yfinance-Default Multi-Ticker-Form ist `(Field, Ticker)`, nicht
  `(Ticker, Field)`.** `yf.download(['AMC','DDD'], ...)` ohne
  `group_by`-Param liefert MultiIndex columns mit Field auf Top-Level
  → `hist[ticker]` wirft `KeyError`. Bei jedem `yf.download(tickers,
  …)` mit Ticker-Liste **explizit `group_by='ticker'` setzen**, sonst
  fällt der `hist[ticker]`-Lookup silently in einen `try/except` und
  produziert Stage-Bugs (siehe `update_backtest_returns` vor PR #72).
- **Read-only-Diagnose vor blindem Fix lohnt sich.** Beim Backtest-
  Backfill-Bug wären ohne Stufe-2-Probe (Live-yfinance-Form-
  Verifikation) die vier Hypothesen — `--ours`-Recovery,
  `ei < 0`-Lookup, yfinance-Multi-Ticker-Fail, Funktion-läuft-nie —
  alle plausibel geblieben. Eine zielgerichtete Probe in der Sandbox
  hat die Hypothese auf eine eindeutige reduziert.

## Architektur-Anker (eingeführt/geändert in dieser Session)

- **`agent_state.json["push_history"]`** (Phase 2 Stufe 3c-1) —
  FIFO-Ringpuffer mit Cap `PUSH_HISTORY_MAX = 100`, instrumentiert
  in `_send_anomaly_ntfy`, `_send_exit_p2_push` (3 Severities),
  `send_ntfy_alert` (earnings_immediate) sowie `_send_exit_ntfy`
  (Daily-Run, 2 Aufrufstellen). Helper `_record_push` ist in
  `ki_agent.py` und `generate_report.py` dupliziert; Schema-
  Änderungen müssen beide Stellen synchron treffen. Daily-Summary-
  E-Mail ist explizit ausgenommen.
- **Earliness-Indikator: 3 statt 2 Komponenten** — neu PM-Vol
  (`pm_vol_match`) zusätzlich zu `accel_match` + `velocity_match`,
  Cap `EARLINESS_PTS_MAX` von 5 auf 7. Datenquelle
  `_fetch_premarket_volumes_batch` (yfinance `prepost=True`,
  1m-Bars, America/New_York 04:00–09:30, **bereits mit
  `group_by='ticker'`**). Filter: `avg_vol_20d > 0` ∧
  `change_overnight ≥ 0` ∧ `change_5d < EARLINESS_MAX_CHANGE_5D_PCT`.
  Stock-Dict-Feld `premarket_volume` wird vor `compute_earliness_pts`
  gefüllt. Stufe 1 bleibt: kein Score-Effekt, nur Logging + Persistenz.
- **`closed_trades`-Schema unverändert** — Bug-A-Fix war reine
  Frontend-State-Cache-Logik (`_POS_PANEL_FORM_STATE`), keine
  Schema-Migration. `wlSubmitClose` cached Textareas
  (`_cacheCloseFormFields`) vor jedem Validation-/gistSave-Fail-
  Re-Render; `wlCancelCloseForm` und Submit-Erfolg verwerfen den
  Cache. Single Helper `_escAttr` für HTML-Escape der Initial-
  Content-Injection in Textareas.
- **`update_backtest_returns` nutzt `yf.download(group_by='ticker')`** —
  Top-Level der MultiIndex columns ist nun der Ticker, `hist[ticker]`
  liefert ein flaches DataFrame mit `['Open','High','Low','Close',
  'Adj Close','Volume']`. Der bestehende `_closes_for`-Lookup
  funktioniert ohne weitere Änderung. Single-Ticker-Pfad
  (`len(tickers) == 1`) bleibt der Direktzugriff `df = hist`.
  **Invariante:** Jeder neue Multi-Ticker-`yf.download` im Codebase
  muss explizit `group_by='ticker'` setzen.
- **Trade-Journal Details-Toggle** (PR #73) — pro Trade-Zeile
  ausklappbarer Detail-Block für `thesis` und `lesson`, **nur wenn
  mindestens eines der beiden Felder nicht-leer ist**. State lebt in
  einem In-Memory-Set `_tjExpanded` (Modul-Scope, kein localStorage,
  kein Gist-Roundtrip), keyed über
  `closed_at|ticker|entry_date|exit_date`. `tjToggleDetails(btn)`
  macht DOM-Direct-Manipulation und aktualisiert das Set parallel,
  damit Filter-Wechsel den State korrekt rekonstruieren. Schema
  `closed_trades` ist nicht angefasst.
- **Git-Workflow: PR-only.** Kein direkter `main`-Push mehr,
  Branch-Name-Pattern `claude/<beschreibung>-<random>`, manueller
  Merge via GitHub-UI nach Review. Begründung in CLAUDE.md
  (Sandbox-Restriktion seit 09.05.2026, alle main-Pushes 403).
