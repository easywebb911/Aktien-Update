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

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen · läuft im Plus
- **SABR** · offen · läuft im Plus

## Verifikation morgen früh nach Daily-Run + ki_agent-Tick

- `agent_state.json` hat `push_history`-Sub-Dict (3c-1 live, FIFO ≤ 100)
- `app_data.json` zeigt `premarket_volume` in Stock-Dicts
- Earliness-Logs zeigen ggf. dritte Komponente `pm_vol_match`
- Trade-Journal: bei nächstem Close zeigen `thesis` und `lesson` korrekte
  Werte (Bug A live)

## Geplante Aufgaben

1. **Phase 2 Stufe 3c-2** — Materialisierung `push_history` in
   `app_data.json` (NACH 1–2 Tagen Live-Lauf von 3c-1)
2. **Phase 2 Stufe 3c-3** — UI Notification-History (NACH 3c-2)
3. **Stufe Mittel-2** — Score-Effekt für Earliness aktivieren NACH
   1–2 Daily-Runs mit drei Komponenten
4. **Backtest-T+0/T+1-Auswertung** — System wartet auf 5 Live-Trades
   pro Score-Bucket × Zeithorizont, Datenbasis ist noch zu jung.
   Beobachten.
5. **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
   Daten
6. **Phase 3 Exit-Signale** — Wiedervorlage 15.05.2026
7. **Score-Aufschlüsselung pro Karte** (Phase Y)
8. **Immediacy-Score-Feature**
9. **Bahn A2** — Frontend-Auswertungs-Panel
10. **UX Backtesting „Nur Live"-Modus**
11. ⏰ **Wiedervorlage 19.05.2026** — `app_data`-recovery +
    `POSITIONS_JSON`-Secret löschen
12. ⏰ **Wiedervorlage 02.06.2026** — Chart-Indikatoren
13. ⏰ **Wiedervorlage 02.07.2026** — Premium-Daten-Stack
14. **Phase X** — v1-Pfad-Migration
15. **Phase 2 Trigger 4–6** — Setup-Erosion, Catalyst, Trend-Bruch
16. **Tier-2-Insight-Builder** als Reserve

## Heutige große Themen

- **GRPN-Stop-Loss vom Vortag aufgearbeitet** — These und Lesson
  manuell im Gist nachgepflegt.
- **Trade-Journal Bug A** diagnostiziert mit Browser-DevTools-
  Reproduktion, lokal gefixt, gemerged.
- **Bug B** war im Parallel-Chat schon gefixt → redundant.
- **Phase 2 Stufe 3c-1** implementiert + reproduziert nach Sandbox-
  Verlust, gemerged.
- **Pre-Market-Volume als 3. Earliness-Komponente** implementiert +
  reproduziert, gemerged.
- **Multi-Session-Konflikt** mit parallelem Chat erkannt und via
  Patch-Migration aufgelöst (Patches und Sandbox später verloren).
- **Sandbox-Push-Restriktion** erkannt: alle `main`-Pushes via Code
  liefern HTTP 403, Branch-Pushes funktionieren weiterhin.
- **CLAUDE.md auf reine PR-Strategie umgestellt** — ALLE Änderungen
  (Code + Doku) via Branch + PR, User merged manuell via GitHub-
  Webseite.

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
  1m-Bars, America/New_York 04:00–09:30). Filter: `avg_vol_20d > 0`
  ∧ `change_overnight ≥ 0` ∧ `change_5d < EARLINESS_MAX_CHANGE_5D_PCT`.
  Stock-Dict-Feld `premarket_volume` wird vor `compute_earliness_pts`
  gefüllt. Stufe 1 bleibt: kein Score-Effekt, nur Logging + Persistenz.
- **`closed_trades`-Schema unverändert** — Bug-A-Fix war reine
  Frontend-State-Cache-Logik (`_POS_PANEL_FORM_STATE`), keine
  Schema-Migration. `wlSubmitClose` cached Textareas
  (`_cacheCloseFormFields`) vor jedem Validation-/gistSave-Fail-
  Re-Render; `wlCancelCloseForm` und Submit-Erfolg verwerfen den
  Cache. Single Helper `_escAttr` für HTML-Escape der Initial-
  Content-Injection in Textareas.
- **Git-Workflow: PR-only.** Kein direkter `main`-Push mehr,
  Branch-Name-Pattern `claude/<beschreibung>-<random>`, manueller
  Merge via GitHub-UI nach Review. Begründung in CLAUDE.md
  (Sandbox-Restriktion seit 09.05.2026, alle main-Pushes 403).
