# Session-Handover — Stand 14.05.2026

## Heute implementiert (chronologisch, alle gemerged via PR)

### Earliness & Conviction

- `fa8d87f` — **feat: Earliness V2 — DTC-Niveau-Basis** (PR #141).
  Datenbelegter Refactor aus Mann-Whitney-U-Diagnose 13.05. (AUC
  **0.77** für DTC). V1-Sub-Signale (`si_accel` + `si_velocity` +
  PM-Vol-Komponente) waren aus `backtest_history` nicht rückwirkbar
  berechenbar. Neue Formel: DTC-Buckets 3/5/8/12 → 0/25/50/75/100 Pkt,
  Late-Runner-Penalty bei RVOL > 5 halbiert. `EARLINESS_FORMULA_VERSION=2`
  als Default, V1-Pfad bleibt als Rollback. Verifikation: WBTN
  Conviction 39 → 67, RR erstmals high mit 82.
- `19ff84a` — **feat: Earliness-Trend-Logging** (PR #142). Vier
  prospektive Felder pro `backtest_history`-Eintrag:
  `si_trend_5d_slope`, `rvol_buildup_5d`, `vol_stability_5d`,
  `coiled_spring_score`. Schema-Version 4. Reines Logging — kein
  Conviction-Effekt. AUC-Re-Check nach 14–30 Live-Tagen (Wiedervorlage
  28.05.).
- `fcf7151` — **fix: KI-Agent Cron-Offset 0 → 17** (PR #143).
  GitHub-Actions-Last-Peak-Vermeidung. Erwartete Coverage 45 % →
  80–90 %.
- `fbbc372` — **fix: topten_entry-Anomaly aus backtest_history**
  (PR #144). `_build_chat_synthesis_ctx` liest `yesterday_top10_set`
  jetzt aus `backtest_history` statt `score_history`. Edge-Case
  leerer Backtest: Skip mit Warning.
- `e149c78` — **fix: Daily-Run Cron-Offset 0 → 17** (PR #145).
  5 Stellen synchron: `daily-squeeze-report.yml`,
  `resolve_run_phase.py`, `mock_test_postclose_run.py`,
  `mock_test_run_phase_resolution.py`, CLAUDE.md.
- `0a9d299` — **feat: Score-Konfidenz-Stufen Phase 1** (PR #146).
  Vier qualitative Stufen (robust / mittel / provisorisch /
  heuristisch) im Methodik-Panel. CI-Lint
  `lint_score_confidence_isolation.py` stellt sicher, dass Konfidenz
  NICHT in Score-Berechnung einfließt (Trennung von Anzeige und
  Logik).

### Token-Pipeline

- `93501b9` — **fix: Settings-Panel-UI-Refresh nach Token-Submit**
  (PR #147). Behebt iPhone-„zweimal-Icon-klicken"-Workaround.
- `4e415d0` — **feat: Storage-Diagnose-Panel im Settings** (PR #148).
  Zeigt Blob-Length, Standalone-Status, Keep-Alive-Alter etc. für
  iPhone-Token-Verlust-Debug.
- `d6c1701` — **fix: buildPositionPanel — Drei Token-Zustände**
  (PR #149). Locked-State bei Session-Verlust mit Unlock-Button
  (`_unlockFromPositionPanel`) statt irreführender „Token fehlt"-
  Meldung.
- `89b53b3` — **fix: gist-Action-Token-Routing** (PR #151). Folge-Fix
  zu #149. Vier Action-Pfade durch `_ensureToken`-Wrapper
  (`wlSubmitPosition`, `wlSubmitClose`, `wlAddManual`,
  `wlRemoveFromExpanded`). Trade-Journal mit
  Drei-Zustände-Locked-Box (`.gist-locked-box` als generische CSS-
  Klasse). Behebt HIGH-Severity Geister-Position-Risiko (Repo-File-
  Delete ohne Gist-Cleanup).

### Health-Check-Projekt (5 PRs, komplett)

- `0d3088a` — **feat: Health-Check Phase 1 (S1–S7)** (PR #150).
  `health_check.py` mit 7 State-Invariants, Append-only-Persistenz in
  `health_check_log.jsonl` (30-Tage-Cutoff), Hook-Points in
  `generate_report.py:main()` und `ki_agent.py:main()`. Plus:
  Auto-Trigger des KI-Agent am Ende jedes Daily-Run (strukturelle
  Lösung für KI-Score-Drift gefangen durch S7).
- `7414563` + `5f8c7b4` — **feat: Phase 2 PR 1 — Tier-1-Provider**
  (PR #152). `record_provider_call`-Infrastruktur + try/finally-
  Wrapper-Pattern. 4 Tier-1-Provider: `yahoo_screener`, `finviz`,
  `yfinance_batch`, `yfinance_singletons` (VIX+SPY+FX). Nachtrag-
  Commit mit try/finally-Latency-Capture + Pass/Fail-Tests +
  Spec-Tabellen-Update.
- `94f2f58` — **feat: Phase 2 PR 2 — Tier-2-Provider** (PR #153). Vier
  Tier-2-Provider: `finra`, `finnhub`, `stockanalysis`,
  `earningswhispers`. Helper `_instrument_provider_call` als
  gemeinsame Abstraktion für per-Call-aggregierte Provider.
- `48fc391` — **feat: Phase 2 PR 3 — Tier-3-Provider** (PR #154).
  Sieben Tier-3-Provider (3 Social + 4 EDGAR getrennt): `stocktwits`,
  `uoa`, `news_rss`, `edgar_13f`, `edgar_8k`, `edgar_form4`,
  `edgar_13d_g`. Helper-Refactor: `instrument_provider_call` von
  `generate_report.py` nach `health_check.py` umgezogen (true reuse).
  Neuer `success_check`-Kwarg für Provider mit reichhaltigen
  fail-soft-Returns.
- `5970847` — **feat: Phase 3 — Daily-Digest-Workflow** (PR #155).
  `health_check_digest.yml` (Cron `13 8 * * *`),
  `scripts/health_check_digest.py`, 3 Push-Klassen (✅ OK / ⚠️
  Digest / 📭 keine Daten), Konsekutiv-Counter in separater
  `health_check_digest_state.json` (race-frei), Mehrfach-Trigger-
  Schutz via `last_digest_sent`-Datum, 7-Tage-Drift-Schutz für stale
  Provider.

### Methodik-Schärfung

- `4c15727` — **fix: Methodik-Display versteckte Boni sichtbar**
  (PR #156). Borrow-Rate-Bonus (+8/+15) komplett neu in Catalyst-Box.
  Float-Turnover 3-Tier statt binär (3/6/10 mit Vol/Float-Schwellen).
  UOA `<abbr>`-Tooltip mit Aufschlüsselung (10/20 + 10). Reine
  Display-Änderung, Konstanten unverändert.

---

## Aktive Positionen (im Gist `squeeze_data.json`)

- **AMC** — Bestand
- **IONQ** — Bestand
- **RR** — heute morgen 14.05. gekauft, basierend auf Top-Ten-Liste.
  Erster Conviction ≥ 75 nach V2-Aktivierung (Score 82).

**Geschlossen am 13.05.:** SABR mit −13.3 %, DMRC mit +12.8 %.

---

## Verifikation morgen (15.05.2026)

- **Health-Check-Digest** — erster Push um **09:13 deutscher Zeit**
  (08:13 UTC) via ntfy. Erwartet: „✅ Health-Check OK" bei sauberem
  Stand. Falls Push **ausbleibt**, hakt entweder der Workflow, ntfy
  oder Token (Liveness-Check by-design).
- **topten_entry-Trigger** — sollte morgen auf neue Top-10-Zugänge
  feuern (sichtbar in `push_history`-Stream).
- **KI-Agent-Coverage** — nach Cron-Verschiebung erwartet 80–90 %
  (vorher ~45 %).
- **iPhone Token-Pipeline** — keine „Token fehlt"-Bugs mehr nach
  PRs #147–#149 + #151. Position-Panel zeigt Locked-State mit
  Unlock-Button, Settings-Panel refresht nach Submit, Trade-Journal
  hat eigenen Locked-Modus.
- **Auto-Trigger Daily-Run → KI-Agent** — sollte keine
  `agent_signals`-Drift mehr produzieren. KI-Score auf Top-10-Karten
  sichtbar (war heute durch Drift weg).
- **`health_check_log.jsonl`** — bekommt täglich neue Einträge (1 pro
  Daily-Run + 1 pro KI-Agent-Tick).
- **`provider_health.jsonl`** — bekommt pro Run Provider-Zeilen (Tier
  1+2+3 entsprechend Aufruf-Pfad).

---

## Geplante Aufgaben + Wiedervorlagen

### Offene Aufgaben

- **Methodik-Display-Doku-Frage** (Standard vs. Maximum) — heute
  teilweise mit PR #156 erledigt (Borrow-Rate / Float-Turnover-Tiers
  / UOA-Tooltip). Frage offen, ob bei anderen Konstanten ähnliche
  Lücken bestehen — Inventur kann wiederholt werden falls neue
  Symptome auftreten.
- **Daily-Run-Dauer-Diagnose** — sequenzielle API-Calls sind die
  vermutete Wurzel. Profiling steht aus.
- **AMC mit 7 Exit-Pushes in 36 h** — Easy ignoriert das bewusst
  (Sonderfall). Keine Code-Aktion.

### Wiedervorlagen mit Datum

- **15.05.2026** — Erster Health-Check-Digest-Push verifizieren,
  Verifikation aller heutigen Merges, iPhone-Token-Flow im Alltag.
- **15.05.2026** — Phase 3 Exit-Signale (Blow-off-Top + IV-Crush) —
  separater Backlog-Punkt, noch nicht begonnen.
- **15.–31.05.2026** — Konsekutiv-Counter im Health-Check beobachten,
  Push-Volumen kalibrieren. Tier-2/3-Schwelle (3-in-Folge) ggf.
  nachjustieren falls zu viele/zu wenige Pushes.
- **19.05.2026** — `app_data`-Recovery + `POSITIONS_JSON`-Secret
  löschen.
- **28.05.2026** — Earliness-Trend-Logging AUC-Re-Check (14 Tage
  nach PR #142 Merge).
- **02.06.2026** — Chart-Indikatoren prüfen.
- **13.06.2026** — Earliness V3 Entscheidung (30 Tage Trend-Logging-
  Daten).
- **02.07.2026** — Premium-Daten-Stack prüfen.
- **Wiedervorlage Konfidenz-Wasserzeichen** — Phase 2 von PR #146.
  Aktuell nur Methodik-Panel-Anzeige. Phase 2 wäre visuelle Markierung
  auf Top-10-Karte (gedimmter Score bei low confidence oder Badge).
  Bewusst verschoben, um die Karte nicht zu überladen. Re-Visit wenn
  Earliness V2 nach 14–30 Tagen validiert ist.

---

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge. Drei
parallele Arbeitsstränge laufen permanent nebeneinander:

- **Bauen** — Code-Erweiterungen. **Health-Check-Projekt komplett
  abgeschlossen** mit den heutigen 5 PRs (#150, #152–#155) — ein
  großer Meilenstein. Aktuell offen: Phase 3 Exit-Signale (IV-
  basiert, Wiedervorlage 15.05.), Code-Hygiene-Backlog-Punkte
  2/3/4/5-2/6-B.
- **Sammeln** — passives Warten auf Backtest-, Earliness-,
  Conviction-, **Score-Inflations-**, **Push-Volumen-**,
  **Earliness-Trend-Logging-**, **Provider-Health-** und
  **State-Invariants-Empirik**. Jeder Daily-Run + ki_agent-Tick
  füttert die History. Aktuell: Conviction-Formel-Beobachtung nach
  V2-Aktivierung, Setup-Inflation-premarket-vs-postclose-Diff,
  Push-Volumen-pre/post-Conviction-75, neue Health-Check-Counter
  und Earliness-Trend-Felder.
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald
  genug Datenpunkte da sind. Aktuell: Daily-Run-Checks (NameError-
  Freiheit, Trigger-Verfügbarkeit, Push-Filter-Wirkung, Stale-
  Data-Drawer), Position-Verläufe (AMC/IONQ/RR), Methodik-
  Konsistenz-Pflege.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **Health-Check-Empirik** — Push-Volumen + Konsekutiv-Counter-
  Verhalten 15.–31.05.
- **Earliness-V2-Beobachtung** — Conviction-Median-Veränderung
  empirisch validieren (vorher systematisch ≈ 50, jetzt erwartet
  häufiger ≥ 75).
- **Phase 3 Exit-Signale** (Wiedervorlage 15.05.2026).
- **Score-Inflations-Empirik** auswerten — premarket-vs-postclose-
  Vergleich für identische Ticker.

**Mittelfristig (Wochen, datenabhängig)**

- **Earliness-Trend-Logging-AUC-Re-Check** (28.05.).
- **Earliness V3 Entscheidung** (13.06., 30 Live-Tage).
- **Backtest-Validierung** — Frontend-Auswertung Backtest-T+0/T+1
  funktioniert erst belastbar, sobald je Score-Bucket
  (`<50`/`50–69`/`≥70`) mindestens 30 Tage Live-R-Werte vorliegen.
  Bahn A2 (Frontend-Auswertungs-Panel) erfordert ≥ 200 Live-Einträge.
- **ntfy-Priority-Mapping nach Severity** — sobald sich das Tiering
  als sinnvoll bestätigt, ntfy-Priority an `severity` koppeln.

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
  V2-Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5 T als
Score < 50. Mit der Zwei-Run-Architektur (PR #124) wird die Backtest-
Historie nur noch mit postclose-Werten befüllt — vorherige premarket-
Einträge bleiben unverändert, müssen in der Auswertung über
`market_regime`/`vix_level`-Filter bereinigt werden.

- **Wenn ja** → Earliness-V2-Aktivierung im Score selbst (heute nur
  Conviction-Komponente) und Big-Refactor mit Rückenwind.
- **Wenn nein** → Score-Komponenten **neu kalibrieren bevor weiter
  gebaut wird**.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus. Mit
dem heutigen Stand ist das Health-Check-Projekt komplett, Earliness
V2 datenbelegt aktiviert, Token-Pipeline saniert, und die Methodik-
Anzeige zeigt versteckte Boni sichtbar an.

---

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Status zum Ende 14.05.:

- **Punkt 1 — `_record_push`-SSOT** — erledigt via PR #76.
- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** **offen.**
  Vollständige Migration zu Jinja (Phase X). Voraussetzung für Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** **offen.**
  Datei weiter gewachsen durch die heutigen 5 Health-Check-PRs +
  Methodik-Erweiterung. Hohe Risiko-Operation.
- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine
  ersetzen:** **offen.** Hängt mit Punkt 2 zusammen. Zwei CI-Lints
  als Abhilfe aktiv (`lint_jsformat_escape.py`,
  `lint_score_confidence_isolation.py`), aber die strukturelle
  Ursache bleibt.
- **Punkt 5 — Score-Methodik-Sync-Regel strukturell absichern**
  - **Schritt 1: erledigt via PR #84 (10.05.2026).**
  - **Schritt 2 (offen):** `score()` und `_compute_sub_scores()` aus
    denselben `SUB_*_DISPLAY_PTS_MAX`-Konstanten ableiten.
- **Punkt 6 — `_drivers_breakdown` mit `score()` zusammenziehen**
  - **Schritt A: erledigt via PR #83 (10.05.2026).**
  - **Schritt B (offen):** `score()` und `_compute_sub_scores()` aus
    `DRIVER_CLASSIFICATIONS` ableiten lassen.

---

## Architektur-Anker (kumuliert + heutige Erweiterungen)

### Earliness V2 — DTC-Niveau-Basis (PR #141)

- `EARLINESS_FORMULA_VERSION = 2` als Default, V1-Pfad bleibt als
  Rollback.
- DTC-Buckets 3/5/8/12 → 0/25/50/75/100 Pkt.
- Late-Runner-Penalty bei RVOL > 5 halbiert Earliness-Pkt.
- Datengrundlage: Mann-Whitney-U-Diagnose 13.05.2026 mit AUC 0.77 für
  DTC.

### Earliness-Trend-Logging (PR #142)

- 4 prospektive Felder pro `backtest_history`-Eintrag:
  `si_trend_5d_slope`, `rvol_buildup_5d`, `vol_stability_5d`,
  `coiled_spring_score`.
- `backtest_schema_version: 4` ab Merge.
- Reines Logging, kein Conviction-Effekt. AUC-Re-Check 28.05.

### `topten_entry` aus `backtest_history` (PR #144)

- `_build_chat_synthesis_ctx` liest `yesterday_top10_set` aus
  `backtest_history` statt `score_history`.
- Skip mit Warning bei leerem Vortags-Backtest.

### Cron-Offset xx:17 (PRs #143 + #145)

- KI-Agent und Daily-Run beide auf Minute 17 — Schutz gegen
  GitHub-Actions-Last-Peak-Drops zur vollen Stunde.
- 5 Stellen synchron für Daily-Run.

### Daily-Run → KI-Agent Auto-Trigger (PR #150)

- Daily-Run triggert am Ende automatisch `ki_agent.yml` via
  `gh workflow run` (non-blocking, `continue-on-error: true`).
- Workflow-Permission `actions: write` ergänzt.

### Score-Konfidenz-Stufen (PR #146)

- 4 qualitative Stufen im Methodik-Panel.
- Persistiert in `app_data.json["score_confidence"]`.
- CI-Lint `lint_score_confidence_isolation.py` verhindert Lesen in
  Score-Funktionen (Trennung Anzeige/Logik).

### Token-Pipeline saniert (PRs #147, #148, #149, #151)

- **Settings-Panel-UI-Refresh** nach jedem Token-Submit (Helper
  `_refreshGhSettingsUI`).
- **Position-Panel + Trade-Journal** mit Drei-Zustände-Routing:
  active / locked / no-config. Locked-State mit Unlock-Button.
- **4 Action-Pfade** durch `_ensureToken`-Wrapper:
  `wlSubmitPosition`, `wlSubmitClose`, `wlAddManual`,
  `wlRemoveFromExpanded`.
- **`.gist-locked-box`** als generische CSS-Klasse, wiederverwendbar.
- **Storage-Diagnose-Panel** im Settings für iPhone-Token-Debugging.
- **Helper `_unlockFromPositionPanel` / `_unlockFromTradeJournal`**
  exposed auf `window` für inline-onclick.

### Health-Check-Projekt vollständig

**Phase 1 (PR #150):**
- 7 State-Invariants (S1–S7) — S1/S2/S3 crit, S4/S5/S6/S7 warn.
- Hook-Points: `generate_report.py:main()` (alle 7) +
  `ki_agent.py:main()` (S2/S3/S6 mit `ki_agent_only=True`).
- Persistenz: `health_check_log.jsonl`, 30-Tage-Cutoff.

**Phase 2 — 15 Provider instrumentiert (PRs #152, #153, #154):**
- **Tier 1 (4):** `yahoo_screener`, `finviz`, `yfinance_batch`,
  `yfinance_singletons` (VIX+SPY+FX, Multi-Emitter-Provider).
- **Tier 2 (4):** `finra`, `finnhub`, `stockanalysis`,
  `earningswhispers`. `call_attempted`-Gating und ENABLED-Gating je
  nach Provider.
- **Tier 3 (7):** `stocktwits`, `uoa`, `news_rss` + 4 EDGAR-Keys
  (`edgar_13f`, `edgar_8k`, `edgar_form4`, `edgar_13d_g`).
- Wrapper-Helper `instrument_provider_call(acct, fn, *, success_check)`
  in `health_check.py` als gemeinsame Abstraktion.
- Persistenz: `provider_health.jsonl`, 30-Tage-Cutoff.

**Phase 3 (PR #155):**
- Workflow `.github/workflows/health_check_digest.yml`, Cron
  `13 8 * * *`.
- Tool-Skript `scripts/health_check_digest.py`.
- 3 Push-Klassen: **✅ Health-Check OK** (default-Priority), **⚠️
  Health-Check-Digest** (high, ≥ 1 crit oder ≥ 3 warn), **📭
  Health-Check ohne Daten** (high, leere JSONL).
- Konsekutiv-Counter in separater `health_check_digest_state.json`
  (race-frei, write-once-Pattern).
- Mehrfach-Trigger-Schutz via `last_digest_sent`-Datum.
- 7-Tage-Drift-Schutz für stale Provider-Counter.

### Methodik-Display versteckte Boni (PR #156)

- **Borrow-Rate-Bonus** (+8 / +15 Pkt) neu in Katalysator-Box
  (Schwellen >50 % / >100 % p.a.).
- **Float-Turnover** 3-Tier-Display (3 / 6 / 10 Pkt) mit Vol/Float-
  Schwellen (≥ 0.5 / 1.0 / 2.0).
- **UOA** mit `<abbr>`-Tooltip auf der „30" — Aufschlüsselung
  10 (weak) / 20 (strong) + 10 (Bias).
- Konstanten unverändert, reine Display-Schärfung.

---

## Lessons Learned (14.05.2026)

- **Diagnose-Schritt vor Implementation zahlt sich aus.** Bei
  Earliness war die ursprüngliche Spec (SI-Trend-5d + RVOL-Build-up
  + Coiled Spring) nicht rückwirkbar berechenbar — Diagnose
  entdeckte das **bevor** Code geschrieben wurde. Stattdessen kam
  datenbelegtes DTC-Niveau heraus mit AUC 0.77.
- **Symptom vs. Wurzel.** Token-Reentry-Bug schien iPhone-Storage-
  Verlust. Wirkliche Wurzel war `buildPositionPanel` mit passivem
  `getToken()`-Check ohne Modal-Routing. Drei Vermutungen alle falsch,
  bis die Storage-Diagnose-Anzeige Klarheit brachte.
- **PR-Aufteilung nach Risiko-Klassen statt nach Code-Größe.**
  Health-Check Phase 2 in 3 PRs nach Tier (1/2/3) erlaubte saubere
  Iteration ohne Mega-PR-Risiko.
- **Helper-Refactor erst nach 3 Wiederholungen.**
  `_instrument_provider_call` wurde erst bei PR #154 zentral nach
  `health_check.py` umgezogen — vorher hatte der Code es lokal in
  `generate_report.py`. Pattern wird erst nach drei Use-Cases
  offensichtlich.
- **Race-Conditions bei State-Files vermeiden.**
  `health_check_digest_state.json` separat statt `agent_state.json`-
  Sub-Key (das hätten mehrere parallele Writer aktualisiert).
  Spec-Wortlaut musste hier abgewichen werden — User-Freigabe vor
  Implementation.
- **Auto-Trigger statt Cron-Hoffnung.** Daily-Run triggert KI-Agent
  direkt am Ende, statt auf nächsten regulären Cron-Slot zu warten.
  Strukturelle Lösung vs. zeitliche Hoffnung.
- **iCloud-Schlüsselbund-Autofill funktioniert nicht zuverlässig**
  mit unserem Token-Modal-Setup. Bleibt als bekannte Limitation,
  lohnt nur als großer Refactor später.
- **GitHub-Pages-Crons droppen bei `:00`.** Betroffen alle Workflows
  mit Cron `0 * * * *` oder `0 X * * *`. Lösung: 17-Minuten-Offset
  zur Last-Peak-Vermeidung. Heute auf KI-Agent und Daily-Run
  angewandt, neue Workflows (Health-Check-Digest auf 13:08) nutzen
  sofort den Offset.
- **Schwellen konservativ als Default.** Health-Check Tier-2/3 erst
  ab 3-in-Folge triggern Counter, nicht ab erstem Fail. Vermeidet
  Push-Spam in den ersten Wochen.
