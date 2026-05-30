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
- **#274 (4fd0f00) — 29.05.** S8-Referenzwechsel. _digest_age_hours
  (health_check.py:125+) misst jetzt last_successful_run (ISO-Timestamp)
  statt last_digest_sent (YYYY-MM-DD). Behebt täglichen Selbstdefekt-
  Fehlalarm: last_digest_sent warf Stunden weg + Mitternacht-UTC-Referenz
  + stabiler Cron-Drift auf ~12:00Z → S8 meldete bei GESUNDEM Digest jeden
  Vormittag warn (identische Tageswerte = Stempel-Pattern). Vorab-Check:
  last_successful_run wird EXKLUSIV vom Digest-Workflow geschrieben
  (kein KI-Tick) → kein toter Wächter, per Source-Inspection-Test
  abgesichert. Zwei-Felder-Architektur erhalten (_already_sent_today
  nutzt last_digest_sent weiter). Manueller Merge nach iPhone-Verify.
- **#279 (eafe053) — 29.05.** Entry-Vorarbeit: zwei ungecappte Twin-Roh-
  Felder additiv im backtest_history-Persist. score_delta_t1_raw (ungecappt,
  neben dem ±15-geclampten score_delta_t1) + anomaly_push_age_h (rohes
  Push-Alter in h, vor der Decay-Transform). Grund: beide Original-Felder
  sind zensiert + retroaktiv NICHT rekonstruierbar (score_history pruned
  14d, push_history FIFO-100) → ohne Rohwerte wäre die 30.06.-Cap-vs-
  Perzentil-Auswertung zirkulär. Sammeln ab nächstem postclose-Run.
  schema bleibt v4, beide in S10_OBSERVED_FIELDS, atomar. Manueller Merge.

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
  DESIGN-ENTSCHEIDUNGEN (Verteilungs-Diagnose 29.05., empirisch belegt):
  - NORMALISIERUNG: mit FESTEN Caps starten, NICHT Perzentil — Daten zu dünn
    für stabile Perzentile (n≥100 nötig, nur si_trend_5d_slope erreicht das
    mit n=142). Perzentil-Entscheidung an 30.06. koppeln, bis dahin Rohwerte
    sammeln (#279).
  - si_trend_5d_slope: Schema PERFEKT bestätigt (Links-Bodung −0.98, langer
    Rechts-Tail bis p99=374). Asymmetrische Normierung wie geplant.
  - rvol_acceleration: 'bimodal' ist Mythos — real kontinuierlich Pareto
    (median 1.47, max 135.7). Cap 3.0 deckt 84% ab, als Start ok.
  - score_delta_t1: geplante 'symmetrische ±15' war ein CAP-Artefakt, nicht
    Datenbefund (raw asymmetrisch −57…+30, 54% 0-Spike). Schwächste Komponente
    (Spec sagt das selbst) → klein gewichten, raw via #279 ab jetzt sammeln.
  - uoa_atm_ratio: Start-Schwellen ~0.75/1.5/2.5 statt 1.25/3.0/5-10 (reale
    max 2.46, enge ATM-Berechnung — Details im UOA-Befund-Eintrag). n=43 knapp,
    final 30.06.
  - anomaly_freshness: 95% leer (sparser als geplante 80-90%), n=7 nicht-leer.
    Bringt mit 5% Coverage kaum Information — schwach wie erwartet.
- **30.06.** Erste belastbare Backtest-Auswertung. V2-only ≥70-Bucket n≈100
  + 30 Tage Score-Inflation-bereinigt. Re-Visit: Score ≥70 klare Edge in
  Trefferquote UND Mean-Return? Faktor-Vorzeichen (DTC, short_float) re-prüfen.
  PLUS: finviz-Rückbau (siehe Backlog), Borrow-Fee-Entscheidung.
  PLUS: Seit 29.05. (#279) werden score_delta_t1_raw + anomaly_push_age_h
  ungecappt gesammelt → Cap-vs-Perzentil-Entscheidung für alle 5 Komponenten
  ist 30.06. auf ECHTEN (nicht zensierten) Verteilungen entscheidbar, nicht
  mehr zirkulär.
- **#281 (a04de49) — 30.05.** Option C: Token-Session-Wrap gegen
  tägliches Master-PW-Re-Entry. Nach Master-PW-Unlock wird der Token mit
  random AES-GCM-Key gewrappt + in IndexedDB persistiert (Store
  squeeze_session). 7-TAGE-ROLLING-WINDOW (NICHT 30 — iOS-ITP räumt
  script-writable Storage nach 7d Inaktivität; jeder Open verlängert +
  resettet ITP-Timer). Beim App-Open wird VOR dem Master-PW-Modal der
  Session-Unwrap versucht (async-Trampolin in _ensureToken, Signatur
  synchron unverändert, alle 8 Aufrufer unberührt). Master-PW bleibt
  Anker. Fail-soft: jeder Fehlerpfad (IDB-Fail/Quota/privater Modus/
  Decrypt-Fail/Ablauf) fällt STILL auf Master-PW-Modal zurück.
  Zusätzlich Queue-Refactor: _tokPending Single-Slot → FIFO-Callback-
  Queue (_tokPendingQueue + _drainTokPendingQueue), 11 Konsumenten
  umgestellt, schließt async-Fenster-Race bei parallelen _ensureToken-
  Aufrufen. 22/22 Tests grün. Manueller Merge nach iPhone-Verify.
  Wirkung: 5-20 Master-PW-Eingaben/Woche → 0 bei regelmäßiger Nutzung.
- **UOA-Befund (Diagnose 29.05., entscheiden 30.06.):** uoa_atm_ratio
  wird im Code STRUKTURELL ENG berechnet — nur ATM-Band (±10%), nur Calls,
  nur nächste Expiration (ki_agent.py:1146-1158). Die Schwellen (intern
  UOA_VOL_OI_WEAK=3.0 / STRONG=5.0 / ANOMALY_UOA_VOL_OI=10.0) stammen aber
  aus der breiten Industrie-Konvention (Total-Vol/OI über alle Strikes +
  Expirationen). Folge: reale Werte max 2.46 (n=43) → obere Schwellen
  strukturell UNERREICHBAR. ZWEI Konsequenzen:
  (a) Entry-Komponente uoa: vorläufige Start-Schwellen ~0.75/1.5/2.5 für
      10.06.-Bau (n=43 knapp), finale Kalibrierung 30.06.
  (b) UOA-Anomaly-Push ist DE FACTO TOT (ANOMALY_UOA_VOL_OI=10.0 nie
      erreichbar) — feuert nie, ohne Fehler (stiller Tod). Für ein
      Squeeze-Tool ist UOA ein gewollter Kern-Indikator → soll repariert
      werden.
  ENTSCHEIDUNG 30.06. (n≈100): Variante 1 = enge ATM-Berechnung behalten +
  Schwellen rekalibrieren (klein, misst aber nur Ausschnitt) ODER Variante 2
  = Berechnung auf Total-Vol/OI umbauen (breite Industrie-Definition,
  Anomaly-Push lebt automatisch wieder, professioneller). Beide Fragen
  (Entry-Komponente + Anomaly-Push) hängen an derselben ATM-vs-Total-
  Entscheidung und werden GEMEINSAM entschieden. Code-Logik vor 10.06.
  NICHT anfassen — Shadow-Persist + 30.06.-Datenbasis abwarten.
- **Card #10 — MERKREGEL:** Bei manuellem Dispatch → HTML-Sanity-CRIT →
  SOFORT das HTML-Artefakt aus dem Actions-Run ziehen, bevor es weg ist.
  Das ist die einzige fehlende Evidenz, um das #10-Mysterium zu lösen.
  Cron-Runs sind sauber, kein prophylaktischer Fix.
- **AMWD beobachten:** delisted-Warning (yfinance kein Preis) bei einem
  Top-10-Ticker. Einzel-Symptom — erst bei Muster diagnostizieren.
- **GitHub-Ticket #4418923 — AUFGEKLÄRT (29.05., geschlossen):** Antwort vom
  GitHub-Support liegt vor. Der 26.05.-Vorfall war ein GitHub-Actions-INCIDENT
  (githubstatus.com/incidents/gnftqj9htp0g, resolved), KEIN Account-Lock,
  KEINE Abuse-Erkennung, KEINE Kompromittierung. Account nicht geflaggt/
  suspendiert. Login/Repo war die ganze Zeit erreichbar — nur Actions-
  Pipeline lief nicht. 2FA-Auffälligkeit = bestehende gültige Session,
  harmlos. Sicherheitsmaßnahmen (2FA neu, Passwort neu, Token-Neuaufbau)
  waren vorsichtig-richtig, im Nachhinein nicht nötig.
- **08.06.2026:** Backup-/Disaster-Recovery-Konzept. Read-only-
  Bestandsaufnahme zuerst: Was liegt NUR auf GitHub? Existiert lokaler
  Clone? Gibt es bereits Daten-Export? Schwerpunkt nicht-aufholbare Daten
  (backtest_history.json, score_inflation_log.jsonl, score_history.json) —
  Code via Clone ohnehin verteilt. Schützt gegen Account-Sperrung
  (vgl. 26.05.-Lock) UND Hack (Löschung/Manipulation). Terminiert VOR
  10.06.-Entry-Modul, das neue wertvolle Daten produziert.
- **Token-Re-Entry-Komfort — ERLEDIGT (30.05., #281):** Option C gebaut
  + iPhone-verifiziert. 7-Tage-Rolling-Window statt der ursprünglich
  angedachten 30 Tage (iOS-ITP-Realismus, in der Diagnose 30.05. belegt).
  Details siehe Sektion 1 / Architektur-Anker. Folge-Layer WebAuthn/
  Touch-ID bleibt optionale Roadmap-Idee, falls 7-Tage je nicht reicht.

## 5) STRATEGISCHE ROADMAP
- Entry-Timing-Modul (★★★, 10.06.) — höchste Priorität.
- Phasen-abhängige / perzentil-basierte Schwellen statt fester phasen-blinder
  Absolut-Schwellen (an 30.06. gekoppelt).
- Borrow-Fee + Utilization in score() (laut Literatur stärkste Squeeze-
  Prädiktoren, bei mir fehlend/kosmetisch) — Entscheidung 30.06.
- Externer Dead-Man-Switch außerhalb GitHub Actions (Health-Check teilt
  Failure-Fate der Pipeline — beim 26.05.-Vorfall schwieg der Wächter mit).
  Begründung aktualisiert (29.05.): Auslöser war ein Actions-Incident
  (Ticket #4418923 aufgeklärt), kein Lock — was den Punkt STÄRKER macht:
  auch ohne Account-Problem kann die gesamte GitHub-Actions-Pipeline (inkl.
  Health-Check-Wächter) gleichzeitig ausfallen. Ein echter Dead-Man-Switch
  MUSS extern (außerhalb GitHub Actions) laufen, sonst teilt er das
  Failure-Fate der Pipeline, die er überwachen soll.
- γ-2 (Pool-Inflation premarket): erst entscheidbar nach mehreren Werktagen
  echter premarket-Daten. ENABLED=False. Skalierer ~0.40 Kipppunkt (dünnes n).
- ~~KI-Agent-Frequenz-Reduktion nur falls zweiter Abuse-Lock.~~
  **GEGENSTANDSLOS (29.05.):** Kein Abuse-Trigger existierte (Ticket #4418923
  aufgeklärt = Actions-Incident), Begründung entfällt.
- Backup/Disaster-Recovery (Wiedervorlage 08.06.): Doppelter Boden gegen
  GitHub-Account-Verlust. Optionen gestaffelt: (a) lokaler git mirror
  (sofort/gratis, deckt Code) | (b) Daten-Export außerhalb GitHub
  (deckt nicht-aufholbare JSON/JSONL) | (c) Spiegel auf anderer Plattform/
  anderem Account (härtester Schutz gegen Hack — kompromittierter Account
  kann nicht beide löschen). Verwandt mit Roadmap-Punkt externer
  Dead-Man-Switch (beim 26.05.-Lock schwieg der Health-Check mit).

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
- **S8 misst seit #274 last_successful_run (ISO-Timestamp), NICHT mehr
  last_digest_sent (YYYY-MM-DD).** last_successful_run wird EXKLUSIV von
  scripts/health_check_digest.py:307 geschrieben (per Source-Inspection-Test
  in mock_test_s8_last_successful_run.py zementiert — bei künftigem
  Fremd-Schreibpfad schlägt der Test sofort an, S8 würde sonst zum toten
  Wächter). last_digest_sent (YYYY-MM-DD) bleibt für _already_sent_today
  (Mehrfach-Trigger-Schutz) → Zwei-Felder-Architektur bewusst erhalten.
- **Token-Session-Wrap (seit #281, 30.05.):** Nach Master-PW-Unlock
  liegt der Token zusätzlich AES-GCM-gewrappt in IndexedDB (Store
  squeeze_session, random Key, KEIN PBKDF2 — kein Passwort). 7-Tage-
  Rolling, fail-soft auf Master-PW-Modal. _ensureToken versucht
  Session-Unwrap VOR Modal (async-Trampolin, sync Signatur). _tokPending
  ist eine FIFO-Queue (_tokPendingQueue), KEIN Single-Slot — bei Refactor
  des Token-Pfads beibehalten, sonst Callback-Verlust bei parallelen
  _ensureToken-Aufrufen. _clearAllTokens MUSS den IDB-Record mitlöschen
  (Geist-Session-Schutz). Master-PW-Blob (PBKDF2-600k, localStorage)
  bleibt unveränderter Anker.

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
- **Datums-Stempel + Mitternacht-Referenz = struktureller Fehlalarm:**
  S8 maß last_digest_sent als YYYY-MM-DD ab Mitternacht UTC. Bei stabilem
  Cron-Drift (~12:00Z Push) erzeugt das täglich mehrere Stunden warn bei
  funktionierendem Digest — NICHT über Schwellen-Tuning reparierbar, nur
  über Referenz-Wechsel auf echten ISO-Liveness-Timestamp. Falsifizierbare
  Trennung stale-vs-real: identische Tageswerte = Selbstdefekt, monoton
  steigend = echter Drop (#274). Vor solchem Referenz-Wechsel IMMER alle
  Schreib-Stellen des neuen Felds greppen (toter-Wächter-Falle).
- **Schwellen-Skala muss zur Berechnungs-Definition passen:** Industrie-
  Standard-Schwellen (UOA Total-Vol/OI 3-10x) wurden 1:1 auf eine enger
  definierte Code-Metrik (ATM-Band, Call-only, single-expiration)
  übertragen → strukturell unerreichbar, Alarm feuert nie. Klasse:
  stiller Tod durch Skalen-Mismatch, kein Code-Fehler. Bei jedem neuen
  Indikator prüfen: passt die Schwelle zur tatsächlichen Werteskala der
  Berechnung?
- **iOS-ITP killt 'persistente' Storage-Versprechen:** WebKit räumt
  script-writable Storage (inkl. IndexedDB) nach 7d Inaktivität — ein
  30-Tage-Komfort-Fenster ist auf iOS-PWA illusorisch. Lösung: kurzes
  Fenster + Rolling-Refresh bei jeder Nutzung (verlängert UND resettet
  den ITP-Timer). Der Komfort kommt vom Rolling, nicht von der initialen
  Fenster-Länge. Ehrliche Spec im Code zementiert (Test prüft: kein
  30-Tage-Versprechen). Zweitlehre: async-Fenster in einem vorher
  synchronen Pfad kann latente Single-Slot-Races real machen — bei
  async-Umbau alle Callback-Slots auf Queues prüfen.
