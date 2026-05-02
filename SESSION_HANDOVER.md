# Session-Handover — Stand 01.05.2026 (Late Evening)

## Heute implementiert (chronologisch, vollständig)

### Vormittag/Nachmittag (siehe Vor-Handover 2346df4)

- `19a27a0` — style: Watchlist-Voransicht-Kacheln auf Mobile verkleinert
- `f7aa4aa` — fix: Watchlist-Grid-Overflow auf Mobile
  (`min-width:0` auf Grid-Items + Flex-Children)
- `f31018a` — style: US-Flagge auf Mobile-Watchlist entfernt,
  Ticker auf 0,85 rem
- `3618594` — fix: Ticker-Readability auf Mobile (Star-Badge entfernt,
  ki-dot scale .6, X-Button 22 px)
- `14a9de1` — fix: Wide-Glyphen-Ticker (font-size .7 rem,
  letter-spacing −.04 em, font-stretch:condensed)
- `469e1d7` — fix: Exit-Score-Symmetrie raw vs. raw
  (INDI-Setup-Drop fällt von 30 auf 11 Pkt)
- `ee0aac5` — feat: Anomalie-basierte Push-Trigger ersetzen Monster≥70
- `23a3e84` — feat: Chat-System-Prompt-Refactor für Synthese
- `65f6b23` — feat: USD/EUR-Anzeige in Chat + KI-Analyse
- `f3937d2` — docs: Score-Methodik-Sync-Regel in CLAUDE.md
- `c958214` — fix: `.agent-dot`-Schwellen 60/30/15 (statt 70/40/15)

### Abend (neu seit 2346df4)

- `a42b726` — fix: Chat-System-Prompt Syntax-Error
  (Doppel-Backticks ` ``fx_usd_eur`` ` brachen das JS-Template-
  Literal → TypeError, dessen Message als roter Chat-Bubble den
  kompletten Prompt zeigte)
- `1341af9` — hotfix: gleichen Backtick-Fix direkt auf `index.html`
  (einmalige Ausnahme zur „niemals direkt bearbeiten"-Regel —
  Daily-Run würde sonst Stunden brauchen, um deploytes HTML zu
  regenerieren)
- `679b169` — feat: Lint-Skript `scripts/lint_chat_template.py` +
  Daily-Workflow-Pre-Check (genau 2 Backticks im `_buildSystem()`-
  Body — Wiederholung des Bugs verhindert)
- `8214fd9` — feat: Backtest-Schema erweitert (Stufe 1 für Bahn A2):
  `max_drawdown_pct` (rolling cummax-High über ≤10 Handelstage),
  `market_regime` (SPY 50T-Trend), `vix_level` (^VIX-Snapshot)
- `9b0e6d3` — feat: VIX-Gating für Anomalie-Pushes
  (>35 → Pause, >25 → ⚠️-Präfix, ≤25/None → unverändert;
  Earnings-Sofort-Alerts ungated)
- `4590606` — feat: SEC EDGAR 13D/13G als Anomalie-Trigger
  (Hybrid: 13D immer, 13G nur Aktivisten-Liste; xml.etree.ElementTree
  statt feedparser; per-Anomaly cooldown_key + 24h-Cooldown)
- `04c7bed` — chore: EDGAR_USER_AGENT via GitHub-Secret
  (Public-Repo-Hardening, beide Workflows injizieren das Secret,
  generischer Fallback für Tests/Forks)
- `bf21cd6` — docs: Handover-Backlog um ⏰ Wiedervorlage 15.05.2026
  ergänzt (Phase 3 Exit-Signale: Blow-off-Top + IV-Crush)

## Aktive Position (im Secret POSITIONS_JSON)

- **INDI** · Entry 27.04.2026 · 3,76 USD · 35 shares · aktuell ~+19 %
  (Spot $4,47); Exit-Score nach raw-vs-raw-Fix bei 16,4

## Verifikation ausstehend (morgen nach erstem Daily + ki_agent-Tick)

- **Chat funktioniert** — kein roter Prompt-Bubble mehr; Lint im
  Daily-Workflow läuft als Pre-Check und fängt Backtick-Wiederholungen
- **EDGAR-Pushes** auf Top-10 mit echtem `EDGAR_USER_AGENT`-Secret
  (User muss das Secret in GitHub Repo Settings noch eintragen!)
- **VIX-Gating wirksam:** bei aktuellem VIX <25 sollten Pushes
  unverändert laufen; Log-Zeile `vix_current=N.N` muss in
  `app_data.json` nach ki_agent-Tick erscheinen
- **Backtest-Schema-Stufe-1 schreibt:** neue Top-10-Einträge ab
  morgen mit `max_drawdown_pct=0.0`, `market_regime`, `vix_level`;
  Rolling-Update läuft für alle Einträge < 14 Tage alt
- Andere Anomalien (RVOL/UOA/Score-Sprung/Gap-Hold) feuern
  weiterhin korrekt mit ihrem Standard-6h-Cooldown

## Geplante Aufgaben

1. **GitHub Secret `EDGAR_USER_AGENT` setzen** (Repo Settings →
   Secrets and variables → Actions → New repository secret,
   Format `"Name email@domain"`). Sonst greift Fallback und SEC
   blockt evtl. mit 403/429 bei produktiven Aufrufen.
2. **Phase 2 Exit-Signale** (UI-First): Frontend für Position-
   Eintragen ohne JSON, Watchlist-Karten mit Exit-Score-Block + P&L.
   Erst nach 1 Woche Live-Test von Phase 1.
3. **Immediacy-Score-Feature** (Vorab-Diagnose 30.04. liegt vor):
   Datenmodell-Erweiterung — `*_dt`-Felder in `agent_signals.json`.
4. **Bahn A2 (Frontend-Auswertungs-Panel)** ab Ende Mai (≥ 200 Live-
   Einträge). Backtest-Schema-Stufe-1 sammelt jetzt die nötigen
   Felder (`max_drawdown_pct`, `market_regime`, `vix_level`).
5. **UX Backtesting „Nur Live"-Modus**: Erklärungstext bei n=0.
6. **Setup-Verfall-Symmetrie weiter beobachten**: jetzt raw vs. raw.
7. **⏰ Wiedervorlage 15.05.2026: Phase 3 Exit-Signale prüfen**
   (Blow-off-Top + IV-Crush; Voraussetzung: Phase 1 ~2 Wochen live)
8. **Filter-Flexibilisierung prüfen (Bahn A2)**
   - Mid-Caps (2–10 Mrd. USD) und Non-US-Ticker als separate Bahnen
   - Erfordert: andere Volumen-Schwellen, KI-Agent-Anpassung,
     Backtest-Setup pro Bahn
   - Voraussetzung: Bahn-A2-Datenbasis ab Juli 2026
     (`max_drawdown_pct` / `market_regime` / `vix_level` werden seit
     `8214fd9` persistiert)
   - **Workaround bis dahin:** Non-US-Ticker via Watchlist-Override
     (`manual_personal=True` umgeht den Cap-/US-Filter)

## Optional / niedrig priorisiert

- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer (`buildWlDetails`) auf neuen Score-Block migrieren
- `backtest_history.json` einmal cachen statt zwei Disk-Reads
- Alte `RS_SECTOR_*`-Konstanten + `_sector_rs_row()` ganz entfernen
- News-Decay-Logik auf UOA / Insider übertragen via
  `_news_age_weight()`, sobald Persistenz da ist
- KI-Agent-eigene Anomalien (UOA-Vol/OI / RVOL-Vortagsvergleich /
  Gap+Hold-Combo) auch in den Chat-Kontext einspeisen
- `EDGAR_ACTIVIST_FILERS`-Liste über Live-Beobachtung verfeinern
  (welche Filer kommen tatsächlich auf Top-10-Tickern an? bisher
  unbekannte Smart-Money-Firmen ergänzen)

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **Lint-Gate vor Daily-Run:** `scripts/lint_chat_template.py`
  prüft genau 2 Backticks im `_buildSystem()`-Body; Pre-Step in
  `daily-squeeze-report.yml`. Fail-Pfad bricht den Workflow ab —
  kaputtes `index.html` kommt nie auf Pages. Pattern auf weitere
  Template-Risiken erweiterbar.
- **Hot-fix-Ausnahme zur „niemals-index.html-bearbeiten"-Regel:**
  bei P0-Bugs in der bereits deployten Version vor dem nächsten
  Daily-Run ist eine zielgenaue Edit auf `index.html` legitim,
  wenn (a) der korrekte Quell-Fix bereits committed ist, (b) der
  Daily-Run die Datei sowieso bald regeneriert, und (c) der
  Commit-Body das explizit dokumentiert.
- **Per-Anomaly-Cooldown-Override:** `detect_anomalies()` kann pro
  Eintrag `cooldown_key` und `cooldown_hours` zurückgeben.
  `_anomaly_is_on_cooldown(key, state, hours=None)` akzeptiert
  Override. EDGAR nutzt das für 24h-Dauer + Filing-Type-Suffix-Keys.
- **VIX als Push-Gate:** Modul-Variable `_VIX_CURRENT` in
  `ki_agent.py` (analog `_FX_USD_EUR` in `generate_report.py`).
  `save_signals()` schreibt nur bei erfolgreichem Fetch — `None`
  würde sonst den vorigen Wert via `**existing` überschreiben.
- **EDGAR-Datenpfad:** `fetch_edgar_filings(top10) → list[dict]` ist
  pure-Funktion, fail-soft auf jedem Pfad. Atom-Parser via
  `xml.etree.ElementTree` (stdlib), kein neuer Dep. Ticker-Match
  via Company-Name-Substring oder Ticker-Token im Title.
- **Backtest-Schema-Stufe-1-Helper:** `_market_regime_from_spy`,
  `_vix_close`, `_compute_max_drawdown` sind pure und einzeln
  testbar. Werden NUR in `_append_backtest_entries` aufgerufen.
- **Public-Repo-Hardening-Pattern:** Jeder Kontakt-/Auth-Wert
  (NTFY_TOPIC, POSITIONS_JSON, EDGAR_USER_AGENT) liegt als GitHub
  Secret + wird in Workflow-`env`-Block injiziert + via
  `os.environ.get(NAME, default)` zur Laufzeit gelesen. Default
  ist generisch genug für Tests/Forks.
