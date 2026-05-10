# Session-Handover — Stand 09.05.2026

## Heute implementiert (chronologisch, alle gemerged via PR)

- `24e039b` — fix: thesis/lesson über Validation-Re-Render erhalten
  (Bug A Trade-Journal) — gemerged via PR #67
- `ca4604b` — docs: CLAUDE.md Git-Workflow auf reine PR-only-Strategie
  umgestellt — gemerged via PR #68
- `f29f8ee` — feat: Phase 2 Stufe 3c-1 — Push-History-Persistenz
  (4 ntfy-Sender instrumentiert, FIFO Cap 100) — gemerged via PR #69
- `adbb079` — feat: Pre-Market-Volume als Earliness-Komponente
  (Logging-only, additiv mit change_overnight-Filter,
  EARLINESS_PTS_MAX 5→7) — gemerged via PR #70
- `46df9a5` — docs: handover update after session (Vormittag) —
  gemerged via PR #71
- `2578fc5` — fix: yfinance Multi-Ticker `group_by='ticker'` im
  Backtest-Backfill (`update_backtest_returns`) — gemerged via PR #72
- `a534352` — feat: Trade-Journal Details-Toggle für thesis/lesson
  (pro Trade-Zeile ausklappbar, lokaler In-Memory-State) — gemerged
  via PR #73
- `e2cd96b` — docs: handover update after evening session — gemerged
  via PR #74
- `4ffab93` — docs: strategische Roadmap-Sektion in
  SESSION_HANDOVER.md — gemerged via PR #75
- `0e82c53` — refactor: `_record_push` in gemeinsames Modul
  `push_history.py` ausgliedern (SSOT) — gemerged via PR #76
- `b478f96` — fix: yfinance Multi-Ticker `group_by='ticker'` in
  `fetch_yfinance` (gleicher Pattern wie PR #72, von Squeeze-Guardian
  entdeckt) — gemerged via PR #77
- `74d992d` — docs: Code-Hygiene-Backlog in SESSION_HANDOVER.md —
  gemerged via PR #78
- `0e7dc55` — chore: Guardian-Findings 2 + 3 abarbeiten
  (Architektur-Anker-Drift + F401-noqa-Kosmetik) — gemerged via PR #79

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** · offen · läuft im Plus
- **SABR** · offen · läuft im Plus

## Verifikation morgen früh nach Daily-Run + ki_agent-Tick

- `agent_signals.json` zeigt **`rvol > 0` und `chg_pct ≠ 0`** für die
  meisten Top-10-Ticker (PR #77-Wirkung — `fetch_yfinance` lieferte
  vor dem Fix systematisch `0.0` für alle Felder).
- `agent_state.json` hat `push_history`-Sub-Dict (3c-1 live, FIFO ≤ 100).
  Nach mehreren ki_agent-Ticks sollten dort mehrere Einträge stehen.
- `backtest_history.json`: erste R-Werte für die 21./22.04.2026-DAILY-
  Einträge sollten gefüllt sein (Backfill-Fix `2578fc5` wirkt — der
  erste KI-Agent-Commit der die Datei je modifiziert hat ist
  `8774206`, direkt nach Merge von PR #72).
- **Frontend Backtest-Panel „Nur Live (DAILY)"** zeigt erste konkrete
  Median-R-Werte pro Score-Bucket statt `—`. Mindest-n=5-Schwelle wird
  evtl. erst nach 1–2 Tagen Backfill erreicht.
- Trade-Journal: bei nächstem Close zeigen `thesis` und `lesson`
  korrekte Werte (Bug A live), und der Details-Toggle erscheint nur
  bei Trades mit nicht-leeren Notes (PR #73).
- Earliness-Logs zeigen ggf. dritte Komponente `pm_vol_match` in
  Workflow-stdout (Stage 1 ist by-design Logging-only).

## Geplante Aufgaben

1. **Phase 2 Stufe 3c-2** — Materialisierung `push_history` in
   `app_data.json` (NACH 1–2 Tagen Live-Lauf von 3c-1).
2. **Phase 2 Stufe 3c-3** — UI Notification-History (NACH 3c-2).
3. **Stufe Mittel-2** — Score-Effekt für Earliness aktivieren NACH
   1–2 Daily-Runs mit drei Komponenten.
4. **Backtest-T+0/T+1-Auswertung** — Frontend-Verifikation nach
   1–2 Backfill-Tagen: pro Score-Bucket (`<50`, `50–69`, `≥70`)
   sollte `n > 0` für `return_3d/5d/10d` auftauchen, Median-Werte
   ersetzen die `—`-Anzeige.
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
14. **Phase X** — v1-Pfad-Migration (siehe auch Code-Hygiene Punkt 2).
15. **Phase 2 Trigger 4–6** — Setup-Erosion, Catalyst, Trend-Bruch.
16. **Tier-2-Insight-Builder** als Reserve.

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge. Drei
parallele Arbeitsstränge:

- **Bauen** — Code-Erweiterungen (neue Trigger, UI-Ergänzungen,
  Persistenz-Schichten).
- **Sammeln** — passives Warten auf Backtest- und Earliness-Empirik
  (jeder Daily-Run + ki_agent-Tick füttert die History).
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald
  genug Datenpunkte da sind.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Stufe Mittel-2** — Earliness-Score-Effekt aktivieren, sobald
  1–2 Daily-Runs mit drei Komponenten (`accel_match`/`velocity_match`/
  `pm_vol_match`) in den Logs plausible Werte zeigen.
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Phase 2 Stufe 3c-2** — `push_history` in `app_data.json`
  materialisieren, danach **Stufe 3c-3** UI-Notification-History.

**Mittelfristig (Wochen, datenabhängig)**

- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte vorliegen.
  Aktuell: Bucket-Mediane existieren noch nicht (`—`-Anzeige), seit
  PR #72 läuft der Backfill aber endlich; erste Werte ab morgen,
  statistisch belastbar in ~30 Tagen.
- **Bahn A2** — Frontend-Auswertungs-Panel (≥ 200 Live-Backtest-
  Einträge erforderlich).

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
  Daten, sobald die PM-Vol-Komponente kalibriert ist.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog,
  aber natürliche Erweiterung sobald die Single-Stock-Edge
  empirisch sitzt.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5T
als Score < 50.

- **Wenn ja** → Earliness-Score-Aktivierung und Big-Refactor mit
  Rückenwind, weil die Score-Komponenten als Ganzes das richtige
  Signal produzieren.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor weiter
  gebaut wird**. Eine Earliness-Bonus-Aktivierung auf einem
  unkalibrierten Score würde Bug auf Bug stapeln.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus —
neue Features werden so gewählt, dass sie *unterstützen* (z. B.
Phase 2 Stufe 3c-2 verbessert Audit-Spur, ohne Score-Logik zu
berühren), nicht *verändern*.

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
- **CLAUDE.md auf reine PR-only-Strategie umgestellt** — ALLE
  Änderungen (Code + Doku) via Branch + PR (PR #68).
- **Backtest-Backfill-Diagnose Stufe 1 + 2 read-only durchgezogen** —
  0/451 DAILY-Einträge mit R-Werten gefunden, Schema/Counts/Cluster-
  Analyse, vier Hypothesen empirisch auf eine reduziert (yfinance
  Multi-Ticker-Form-Mismatch), Live-Probe verifiziert. Fix in
  PR #72: ein zusätzliches `group_by='ticker'` im `yf.download`-Call.
- **CLAUDE.md-Earliness-Konsistenz read-only verifiziert** — genau
  eine Sektion, `EARLINESS_PTS_MAX = 7`, drei Komponenten korrekt
  dokumentiert, keine Doppel-Sektion durch Sandbox-Verlust.
- **PM-Vol Live-Status verifiziert** — Stage 1 ist Logging-only,
  Felder werden by-design **nicht** persistiert.
- **Trade-Journal Detail-Ansicht** — pro Trade ausklappbarer
  Details-Toggle, nur wenn thesis ODER lesson nicht-leer (PR #73).
- **`_record_push` Single-Source-of-Truth** — Duplikat in ki_agent
  + generate_report eliminiert, Helper liegt jetzt zentral in
  `push_history.py` (PR #76, −72 Zeilen netto).
- **Squeeze-Guardian-Konformitäts-Check** über alle 8 PRs — fand
  einen produktiven stillen Datenverlust (`fetch_yfinance` in
  ki_agent.py:420 hatte denselben yfinance-`group_by`-Bug wie
  PR #72; live-verifiziert in `agent_signals.json`: `rvol=0.0`
  und `chg_pct=0.0` für **alle 10** Signale → RVOL-Explosion- und
  Score-Sprung-Anomalien konnten nicht mehr feuern). Fix als
  Single-Liner in PR #77, plus Drift-Cleanup in PR #79.
- **Code-Hygiene-Backlog** explizit dokumentiert (PR #78) — fünf
  offene Refactor-Punkte (v1/v2-Migration, Monolith-Split, Template-
  Engine, Methodik-Auto-Generation, Drivers-/Score-SSOT) als
  Wiedervorlage.

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
  produziert Stage-Bugs (PR #72 für `update_backtest_returns`,
  PR #77 für `fetch_yfinance` — beide identischer Pattern).
- **Read-only-Diagnose vor blindem Fix lohnt sich.** Beim Backtest-
  Backfill-Bug wären ohne Stufe-2-Probe (Live-yfinance-Form-
  Verifikation) die vier Hypothesen — `--ours`-Recovery,
  `ei < 0`-Lookup, yfinance-Multi-Ticker-Fail, Funktion-läuft-nie —
  alle plausibel geblieben. Eine zielgerichtete Probe in der Sandbox
  hat die Hypothese auf eine eindeutige reduziert.
- **Squeeze-Guardian-Konformitäts-Check nach Multi-PR-Sessions ist
  kein Overhead, sondern Versicherung.** Heute hat ein Routine-Run
  einen produktiven stillen Datenverlust aufgedeckt (rvol=0.0 in
  allen 10 ki_agent-Signalen), der ohne den Check Tage unbemerkt
  weitergelaufen wäre. Nach jeder Session mit ≥ 3 Code-PRs
  empfehlenswert.
- **Backtest-Verteilungs-Erkenntnis (10.05.2026) — Median allein
  unterschätzt die Edge.** Squeeze-Renditen sind extrem rechtsschief;
  einzelne Knaller treiben den Mean weit über den Median, ohne dass
  der Median sie sieht. Konkrete Beobachtung nach PR #86 (Mean-Feature):
  - Score ≥ 70, 10T-T+1: **Median +4.1 %** vs **Mean +12.2 %** (3× Spread)
  - Score 50–69, 10T-T+0: **Median −0.3 %** vs **Mean +2.5 %** (Vorzeichen-Wechsel)
  - Score < 50: Median und Mean nah beieinander → symmetrische Negativ-
    Verteilung, keine versteckten Knaller.

  **Implikation für Trading:** Bei asymmetrischer Auszahlungs-Struktur
  (Stops klein, Gewinne durchlaufen lassen) ist Mean der relevantere
  Indikator. Median ist nicht falsch, aber unvollständig — er glättet
  genau die Squeeze-Knaller weg, die das Setup ausmachen.

  **Korrektur der Erst-Interpretation vom 09.05.2026:** Der ≥70-Bucket
  hat sehr wohl Edge, sie ist nur in der Verteilungs-Schiefe versteckt.
  Die ursprüngliche Diagnose „kein klarer Sortier-Effekt an der Spitze"
  war ein Median-Artefakt. Diese Erkenntnis ist primärer Input für die
  spätere Score-Lackmus-Test-Bewertung (siehe Strategische Roadmap):
  Mean ≥ Median × 2 im ≥70-Bucket gilt als positive Bestätigung der
  Score-Edge.

## Code-Hygiene-Backlog

Code-Hygiene-Punkte aus der Diskussion vom 09.05.2026. Punkt 1
(`_record_push`-SSOT, PR #76), Punkt 5 Schritt 1 (Score-Formel-Box
auto-generiert, PR #84) und Punkt 6 Schritt A (DRIVER_CLASSIFICATIONS-
Tabelle, PR #83) sind erledigt. Verbleibende Punkte sind als
Wiedervorlage offen — anfassen wenn konkreter Anlass besteht (geplante
Erweiterung wäre ohne Refactor unverhältnismäßig komplex) oder als
bewusste Aufräum-Session.

- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** vollständige
  Migration zu Jinja (Phase X). Aktuell delegiert `generate_html_v2()`
  am Ende an `generate_html_v1()` (Outer-Page) — keine Autarkie. Drei-
  Schritt-Migration nötig (page.jinja, wl_card.jinja-Refactor von
  `_wl_full_card_html`, autarkes v2). Voraussetzung für Punkt 3.

- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** ~12 000 Zeilen
  in einer Datei. Modulisierung in `score/`, `data_fetch/`, `frontend/`,
  `backtest/` reduziert kognitive Last und macht Tests fokussierter. Hohe
  Risiko-Operation — erfordert Render-Test-Schutznetz (`JINJA_RENDER_TEST=1`)
  + Smoke-Tests, sonst silent Drift.

- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine ersetzen:**
  hängt mit Punkt 2 zusammen. Aktuell ist die JS-Sektion ein Python-f-String,
  was `${...}`-Eskapes (`${{...}}`) erzwingt und ein Lint-Skript
  (`scripts/lint_chat_template.py`) als Sicherheitsnetz braucht. Mit echter
  Template-Engine wären beide Sicherheitsnetze überflüssig.

- **Punkt 5 — Score-Methodik-Sync-Regel strukturell absichern**
  - **Schritt 1: erledigt via PR #84 (10.05.2026)** — Score-Formel-Box
    auto-generiert aus `config.py`-Konstanten `SUB_*_DISPLAY_PTS_MAX`.
    Strukturell drift-geschützt für Sub-Score-Caps; manueller HTML-Sync
    für diese Werte entfällt.
  - **Schritt 2 (offen):** `score()` und `_compute_sub_scores()` aus
    denselben Konstanten ableiten, statt eigene Caps zu rechnen —
    eliminiert die letzte Drift-Quelle in dem Bereich (heute kann
    z. B. ein Score-Faktor von 32 auf 35 wandern, ohne dass
    `SUB_SHORT_FLOAT_DISPLAY_PTS_MAX` mitgepflegt wird).

- **Punkt 6 — `_drivers_breakdown`-Klassifikations-Regeln in gemeinsamen
  Helper mit `score()` ziehen**
  - **Schritt A: erledigt via PR #83 (10.05.2026)** — `DRIVER_CLASSIFICATIONS`-
    Tabelle als Single-Source-of-Truth für `_drivers_breakdown`,
    Hybrid-Schema mit Callables für dynamische Labels/Gewichte,
    bit-identisch zur vorherigen Inline-Logik (3 Mock-Stocks verifiziert).
  - **Schritt B (offen):** `score()` und `_compute_sub_scores()` aus
    `DRIVER_CLASSIFICATIONS` ableiten lassen, sofern sinnvoll umsetzbar —
    macht Klassifikator + Score-Berechnung zur gemeinsamen Spec, dann
    ist die Score-Faktor ↔ Display-Cap-Drift aus Schritt 2 von Punkt 5
    auf demselben Weg eliminiert.

## Architektur-Anker (eingeführt/geändert in dieser Session)

- **`agent_state.json["push_history"]`** (Phase 2 Stufe 3c-1) —
  FIFO-Ringpuffer mit Cap `PUSH_HISTORY_MAX = 100`, instrumentiert
  in `_send_anomaly_ntfy`, `_send_exit_p2_push` (3 Severities),
  `send_ntfy_alert` (earnings_immediate) sowie `_send_exit_ntfy`
  (Daily-Run, 2 Aufrufstellen). Helper `_record_push` lebt als
  Single-Source-of-Truth in `push_history.py` (Repo-Root) und wird
  von `ki_agent.py` und `generate_report.py` per `from push_history
  import _record_push` eingezogen — bei Schema-Änderung nur diese
  eine Stelle anpassen (PR #76). Daily-Summary-E-Mail ist explizit
  ausgenommen.
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
- **yfinance Multi-Ticker `group_by='ticker'` ist Pflicht-Invariante.**
  Sowohl `update_backtest_returns` (PR #72) als auch `fetch_yfinance`
  (PR #77) hatten den default-`group_by='column'`-Bug. Default-Form
  liefert MultiIndex `(Field, Ticker)` → `hist[ticker]`-Lookup wirft
  `KeyError`, der typischerweise von einem `try/except` still
  geschluckt wird. **Jeder neue `yf.download(tickers, ...)` mit
  Multi-Ticker-Liste muss `group_by='ticker'` explizit setzen.**
  Stand 09.05.2026 sind alle bekannten Aufrufstellen gefixt.
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
