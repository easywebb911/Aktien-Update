# SESSION_HANDOVER.md — Stand 28.05.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
- **#269 (b7497684)** — Logging-Fix in generate_report.py. Reine Log-Strings,
  keine Logik. Z.15957 neu: "index.html geschrieben (frischer Stand, vor
  S9-Check)" direkt nach fh.write(html). Z.16245 umbenannt: "Report written
  → index.html" → "Post-Render-Pipeline abgeschlossen (Write erfolgte vor
  S9-Check)". Grund: das alte Statement feuerte NACH dem S9-Check und hatte
  einen falschen Reihenfolge-Verdacht ausgelöst. Auto-Merge (Squash).
- **#270 (Squash-Merge, Hash via git log)** — S11/S12-Sammel-Frequenz-Wächter.
  Neuer Helper _last_phase_run_age_workdays (health_check.py), 2 neue Konstanten
  in config.py. S11 (warn): kein echter premarket-Run (run_phase==tsp=='premarket')
  seit >5 Werktagen. S12 (crit, NUR-REPORTING): kein echter postclose-Run
  seit >2 Werktagen. Quelle: score_inflation_log.jsonl. Feiertags-robust via
  absence-of-write-Pattern. S12-Exit-Schutz: S9-Block-Pfad filtert strikt
  id=="S9" → S12-crit blockiert NICHT (per Test + Kommentar abgesichert).
  Manueller Merge nach iPhone-Verify.
- **#271 (b2176200)** — finviz-Schwellen-Override. Neue Konstante
  DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES = {"finviz": 100} in config.py,
  ein Dict-Lookup in aggregate_provider_fails (health_check.py). Entschärft
  den finviz-Dauerfehlalarm (22 in Folge), ohne andere Provider zu berühren
  (Default bleibt 3) und ohne den Score-Pfad anzufassen. Auto-Merge (Squash).

## 2) AKTIVE POSITIONEN
- **AMC** — Halt-Strategie, no_exit_alerts=true. Conv 4, Setup stark gefallen.
  Trailing-Stop −10.2% vom Hoch im Exit-Log, score 34. Bewusst gehalten.
- **IONQ** — Conv 25, score 7, pnl +33.2%. Exit-Mechanik flaggt, aber kein
  Exit-Treiber gesetzt. Schließung = Chart-/Bauchgefühl-Call.
- HEUTE GESCHLOSSEN (im Journal, aus Watchlist raus):
  - INDI 22.05→28.05, +23.1% (+20,79€), 6d, Setup max 83, Conv 57.
  - CRDF 19.05→28.05, +1.7% (+1,29€), 9d, Setup max 89, Score 98, Conv 85
    → Datenpunkt fürs ≥70-Bucket (hoher Score, dünner Return).
- RR am 26.05. +11.5% geschlossen (Exit-Signal catalyst crit, im Journal).
- Watchlist (6): PDYN, AI, GEMI, CRMD, IONQ, AMC.

## 3) VERIFIKATION MORGEN
- **S11/S12 erstmals live im Digest** (Slot 47 8 * * *). Erwartung: S11 grün
  (premarket 27.05, ~1 Werktag), S12 grenzwertig grün (2 Werktage). iPhone-
  Verify: Safari killen → Daten löschen → ?bust=N → MASTER-PASSWORT → prüfen.
- **finviz NICHT mehr als warn** im Digest (Counter 22 < neue Schwelle 100).
- **Heute Abend 21:17-postclose:** Droppt er erneut? Falls ja, ist das der
  ERSTE echte Test des frischen S12-Wächters — und S12 würde dann morgen
  CRIT melden als ECHTER Befund (kein Fehlalarm).
- **S10-Quote:** 20.05-Kohorte (n=17) fällig heute-EOD, 21.05-Kohorte morgen-
  EOD. Sollten planmäßig fallen (Memorial-Day-Überzählung).
- **Optionaler Write-Commit-Check:** Nach 20:00 UTC sollten neue backtest_history-
  Writes für die 20.05-Kohorte kommen (Fill lebt-Bestätigung).

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
- **02.06.** Chart-Indikatoren (TTM Squeeze / VWAP-Distanz / OBV-Divergenz)
  als Entry-Score-Komponenten — NICHT im Setup-Score, nur Entry-Score ab 10.06.
- **10.06. ★★★ GROSSPROJEKT HÖCHSTE PRIORITÄT:** Entry-Timing-Modul Start.
  Entry-Score 0–100 pro Top-10-Kandidat, 5 Komponenten je 20%. Shadow-Mode
  zuerst, kein Push bis Entry-AUC ~30.06. Bau-Ablauf: (1) Persistenz ✅ läuft
  | (2) 5 Normalisierungen | (3) Aggregation | (4) Entry-Score persistieren
  | (5) Cockpit-Pillar zuletzt (Frontend+iPhone-Verify).
- **30.06.** Erste belastbare Backtest-Auswertung. V2-only ≥70-Bucket n≈100
  + 30 Tage Score-Inflation-bereinigt. Re-Visit: Score ≥70 klare Edge in
  Trefferquote UND Mean-Return? Faktor-Vorzeichen (DTC, short_float) re-prüfen.
  PLUS: finviz-Rückbau (siehe Backlog), Borrow-Fee-Entscheidung.
- **Card #10 — MERKREGEL:** Bei manuellem Dispatch → HTML-Sanity-CRIT →
  SOFORT das HTML-Artefakt aus dem Actions-Run ziehen, bevor es weg ist.
  Das ist die einzige fehlende Evidenz, um das #10-Mysterium zu lösen.
  Cron-Runs sind sauber, kein prophylaktischer Fix.
- **AMWD beobachten:** delisted-Warning (yfinance kein Preis) bei einem
  Top-10-Ticker. Einzel-Symptom — erst bei Muster diagnostizieren.
- **GitHub-Ticket #4418923:** Antwort auf Lock-Auslöser (26.05.) abwarten.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.) — höchste Priorität.
- Phasen-abhängige / perzentil-basierte Schwellen statt fester phasen-blinder
  Absolut-Schwellen (an 30.06. gekoppelt).
- Borrow-Fee + Utilization in score() (laut Literatur stärkste Squeeze-
  Prädiktoren, bei mir fehlend/kosmetisch) — Entscheidung 30.06.
- Externer Dead-Man-Switch außerhalb GitHub Actions (Health-Check teilt
  Failure-Fate der Pipeline — beim Lock 26.05. schwieg der Wächter mit).
  Priorität an Lock-Ursache-Klärung gekoppelt.
- γ-2 (Pool-Inflation premarket): erst entscheidbar nach mehreren Werktagen
  echter premarket-Daten. ENABLED=False. Skalierer ~0.40 Kipppunkt (dünnes n).
- KI-Agent-Frequenz-Reduktion nur falls zweiter Abuse-Lock.

## 6) CODE-HYGIENE-BACKLOG (mit Status)
- **finviz Flag-aus (FINVIZ_SCREENER_ENABLED=False) + α (Provider komplett
  rückbauen)** → OFFEN, an 30.06. gekoppelt. Heute γ (Schwellen-Override)
  gebaut als Übergang; Flag-aus + α nach Datenkonsolidierung. SF-Quote-Pfad
  ist ungated → bei α mitentfernen. Plan-C-Netz bis dahin erhalten.
- v1/v2 → Jinja Template-Engine → OFFEN, niedriger Trading-Wert.
- Cockpit Stage 3 (.sb-Reste) → VERTAGT (.sb-conf-* live reused = #199-Falle,
  .sb-row/-num Rollback-Fallback).
- S10-Feiertags-Zähler (display-only) → an 30.06.-Decay-Fix koppeln. Bevorzugt:
  Alters-Zähler an reale yfinance-Bar-Logik koppeln (keine neue Dependency).
- Großer generate_report.py-Split → VERWORFEN (globals-Falle).

## 7) ARCHITEKTUR-ANKER
- Earliness V2 (DTC, AUC 0.77) | Phase-2 Exit komplett (6 Trigger) |
  Live-Polling Cloudflare-Worker quote-proxy.easywebb.workers.dev |
  Conviction-Schwelle 75 (#123) | Token AES-GCM+PBKDF2 (classic ghp_).
- run_phase steuert: normalize-Short-Circuit, Backtest-Append-Gate (nur
  postclose), anomaly_pushes (nur premarket).
- **"Echter Phasen-Run" nur via score_inflation_log nachweisbar:
  run_phase==trading_session_phase. date in backtest_history ist KEIN Beweis
  (Manual-Frühdispatch möglich).** (Basis für S11/S12.)
- S10-Loader filtert backtest_schema_version==4 (additiv halten!).
- backtest_history.py eigenes Modul seit #256 (Callable-Injection).
  Idempotenz-Key (ticker, report_date), report_date = heute Berlin (hart).
- return_5d-Fill = update_backtest_returns() in ki_agent.py:380 (stündlich,
  indexiert reale yfinance-Bars, idempotent).
- **S9-CRIT-Exit-Pfad (generate_report.py:16128) filtert STRIKT id=="S9".
  Neue crit-Checks (S12) blockieren NICHT. Bei Refactor id=="S9"-Filter
  UNBEDINGT beibehalten — niemals auf severity=="crit" allein umstellen.**
- Health-Check-Reihenfolge: fh.write(html) bei Z.15955 VOR S9-Check (16112).
- Provider-Schwellen: Default DIGEST_CONSECUTIVE_THRESHOLD=3, Override-Dict
  DIGEST_CONSECUTIVE_THRESHOLD_OVERRIDES={"finviz":100}.
- Service-Worker raus seit #188.
- Cron-Inventar: ki_agent 17 * * * * (24/Tag, NICHT phasen-gated), daily
  premarket 17 8 * * 1-5, daily postclose 17 21 * * 1-5, health-digest
  47 8 * * *, watchlist 0 7 * * 0.

## 8) LESSONS (28.05.2026)
- **Card #10 CRIT — unlösbar ohne Artefakt:** Render-Code mehrfach geprüft,
  KEIN deterministischer Leer-Cockpit-Pfad. Tritt nur bei manuellen Dispatches
  in Intraday-Pool-Volatilität auf, Cron sauber. Der exakte Trigger liegt im
  ephemeren HTML-Artefakt, das bei CRIT nie committet wird. Ehrlich als
  unlösbar-ohne-Evidenz eingeordnet statt blind gefixt. → Merkregel (Sektion 4).
- **Log-Statement-Position kann Diagnose in die Irre führen:** Das "Report
  written"-Log feuerte NACH dem Check und erzeugte einen falschen Reihenfolge-
  Verdacht. Präzise Log-Position spart künftige Fehldiagnosen (#269).
- **postclose-Drop = permanenter Datenverlust:** report_date ist hart auf
  "heute Berlin", kein Backfill-Pfad. Jeder gedroppte postclose-Cron zerstört
  irreversibel einen EOD-Snapshot fürs 30.06.-Sample. → Motivation für S12.
- **Health-Counter agnostisch zur Fallback-Wirkung:** Der Provider-Aggregator
  zählt jede fehlerhafte Run-Zeile, egal ob der Fallback griff. → Mechanik-
  Fehlalarm möglich. "Folgenlos für die Daten ≠ folgenlos fürs Monitoring"
  (finviz: 100/100 SF aus yfinance, aber 22-Runs-Dauerwarn = Alarm-Müdigkeit).
- **Flag-aus ist nicht null-Risiko:** Counter friert 7d ein (DIGEST_STALE_DAYS),
  SF-Quote-Pfad ungated → konditionale Stille. γ (Schwellen-Override) ist
  deterministisch + kleinerer Touch. Provider-spezifische Schwellen als
  Dict-Pattern (wiederverwendbar) statt Magic-Number-Einzelkonstante.
