# Session-Handover — Stand 24.05.2026

> **Datums-Kontext:** Heute So 24.05.2026. **Mo 25.05. = Memorial Day
> (US-Börse zu).** Erster Handelstag wieder **Di 26.05.** Alle Live-
> Verifikationen, die einen postclose-/premarket-Daily-Run brauchen,
> frühestens Di 26.05.

## Premium-Ziel

> „Ein System, das sich so weit selbst überwacht, dass meine menschliche
> Aufmerksamkeit komplett frei wird für die Fragen, die nur ich beantworten kann."

**Leitlinie:** KI überwacht die **Mechanik** (Feld leer, Provider down,
Struktur kaputt, Daten-Drift). Mensch validiert die **Bedeutung** (ist die
Edge echt? trägt das Setup? kaufe ich oder schau ich nur?).

**Vorhandene Bausteine (alle live auf `main`):**

- **HTML-Sanity S9 Stufe 1 + 2** (PR #237 + #241) — DOM-Defekte, blockt Push bei CRIT
- **`quote_proxy` Tier-2-Probe** (PR #242) — Worker-Tod + Yahoo-v8-Bruch serverseitig
- **Health-Check S1–S10** — State-Invariants + Daten-Integritäts-Check (S10, PR #246)
- **Provider-Health Tier 1–3** — Latenz/Coverage-Telemetrie
- **Code als read-only Diagnose-/Rat-Agent** — Easy frägt, Code prüft + rät ehrlich, Easy entscheidet

**Prinzip:** Schicht für Schicht. Jede neue Sonde wird geprüft, bevor die
nächste draufkommt. **Nicht durch „muss gelingen", sondern durch
prüfen-verstehen-entscheiden.**

## Heute implementiert (chronologisch, 24.05.2026)

Alle gemergt. Schwerpunkt: Backend-Hygiene + Entry-Modul-Vorarbeit (die
zwei zuvor unfundierten Komponenten geklärt).

- **PR #256** `backtest_history.py` EXTRAHIERT aus `generate_report.py`
  (~455 Z., 12 Funktionen). Helper-Refactor, kein Verhaltens-Wechsel.
  Kopplung `_compute_sub_scores` + `_safe_float` via Callable-Injektion
  gelöst (kein Zirkular-Import, Muster wie `score_inflation_log`).
  `compute_score_confidence` bleibt bewusst in generate_report
  (`_SCORE_CONFIDENCE`-globals-Thematik). 4 Source-Inspektions-Mock-Tests
  mit angepasst (Pfad → backtest_history, kwargs durchgereicht) — keine
  Prüfung gelockert (assert-Count identisch).
- **PR #257** Backend-Hygiene Tier 1a/1b/1d: 2 tote Funktionen
  (`_exit_cooldown_expired_keys`, `_load_production_scores`), 3 ungenutzte
  Importe (`timedelta` in backtest_history, `time as dt_time` in ki_agent,
  `date` in score_inflation_log), 2 ungenutzte Locals (`exc`, `base_upper`).
  Deletion-only, kein Frontend.
- **PR #258** Kaskaden-Orphan `_extract_latest_scores` entfernt (war nur
  von `_load_production_scores` aufgerufen, durch #257 verwaist).
- **PR #259** Entry-Modul-SHADOW-PERSIST: `score_delta_t1` +
  `anomaly_freshness` additiv ins V4-Backtest-Schema. Beide leer-tolerant,
  in `S10_OBSERVED_FIELDS` (atomar). **KEIN v5-Bump** (S10-v4-Filter-Falle).
  `score_delta_t1` self-contained aus `s["sparkline"]`; `anomaly_freshness`
  aus `push_history`-ts. Neuer Mock-Test `mock_test_entry_shadow_persist`
  (19/19).
- **PR #260** `anomaly_freshness` kind-Filter-Korrektur: #259 maß
  „any-push-freshness" (exit_p1/exit_p2 setzten fälschlich die Uhr =
  gegenteiliges Signal). Fix: 1 Zeile `if _pe.get("kind") != "anomaly":
  continue` — nur Anomalien (inkl. suppressed) zählen. test_20 ergänzt
  (20/20). v4, kein Bump, Decay-Helper + S10 unberührt.

**Vorbereitende Read-only-Diagnosen (kein Code, fundierten die Entscheidungen):**

- premarket-Cron-Drift, RVOL-γ-2-Pool-Inflation, S8-Digest-Fehlalarm-
  Ursache, backtest_history-Extrahierbarkeit, Entry-Komponenten-Verteilungen.

## Aktive Position (im Secret `POSITIONS_JSON`)

- **AMC** — Halt, `no_exit_alerts=true`
- **IONQ**, **RR** — unverändert (RR Earnings waren 22.05., catalyst-Exit feuerte korrekt)
- **CRMD** — mehrere Trailing-Stop-Alerts, halten

## Verifikation ausstehend

Alle brauchen einen Daily-Run → **frühestens Di 26.05.** (Mo 25.05.
Memorial Day, Börse + premarket-Cron-Sinn entfallen).

- **#253 premarket-Cron (★ erster Test Di 26.05.):** Cron wurde 22.05.
  von `17 10` auf `17 8 * * 1-5` (8:17 UTC) verschoben gegen GitHub-Drift
  (2.4–3.6 h beobachtet). Prüfen: lief der Daily-Run Di ~8:17–11:52 UTC
  **vor** 13:30 UTC US-Open, mit `run_phase=premarket`? Kamen Morgen-
  Anomaly-Pushes? Schreibt `score_inflation_log` `trading_session_phase=premarket`?
- **#259/#260 Shadow-Persist (Di 26.05.):** beim ersten postclose-Run
  prüfen, dass `score_delta_t1` + `anomaly_freshness` als Keys in jedem
  V4-Eintrag erscheinen (Wert numerisch/None, beides legitim). `anomaly_freshness`
  wird meist 0/None sein (erwartet — sparse).
- **#255 Digest-S8 (laufend):** Retry-Push-Fix (fetch+reset+push, max 5).
  Prüfen: `last_digest_sent` springt aufs aktuelle Datum, S8-WARN
  verschwindet. WE-Digest-Cron (08:47 UTC) lief evtl. Sa/So — Stand
  read-only prüfbar.
- **ERLEDIGT (nicht mehr offen):** #244 Trend-Felder (si_trend_5d_slope
  n=98, rvol_buildup/vol_stability/coiled_spring 0 % null im jüngsten Run),
  #251 rvol_acceleration (n=21) + uoa_atm_ratio (n=15) befüllt,
  return_3d/5d-Backfill (S10-WARN war 23.05. weg).

## Geplante Aufgaben + Wiedervorlagen

### Roadmap (datiert)

- **Di 26.05.2026** — #253-premarket-Verify (erster Handelstag) +
  #259/#260-Shadow-Persist-Verify.
- **~04.06.2026** — Earliness-AUC erste Schätzung r5d (AUC-Uhr startete
  21.05. neu wegen hist_5d-Bug). Kriterium: n + Klassen-Balance prüfen
  BEVOR AUC gerechnet (Lehre #238: schöne Zahl auf dünnem n = trügerisch).
- **02.06.2026** — Chart-Indikatoren (TTM Squeeze / VWAP / OBV) als
  Entry-Score-Komponenten.
- **10.06.2026** — ★★★ **Entry-Timing-Modul START** (höchste Prio,
  mehrwöchig). Plan in „Architektur-Anker" unten. Alle 5 Komponenten
  haben jetzt eine begründete Start-Normierung (s. u.).
- **~24.–30.06.2026** — Entry-AUC-Diagnose (`entry_score × return_5d/10d`).
  Plus: erste belastbare Backtest-Auswertung (daily-≥70-Bucket-CI kreuzt
  Null nicht mehr — Kriterium aus #238).
- **02.07.2026** — Premium-Daten-Stack.

### γ-2 (RVOL-Normalisierung) — Status: datengated, NICHT mehr 30.05.-fix

- Master-Switch-Variante verworfen (premarket-Pool-Inflation, Cap-Sättigung
  würfelt Ranking ρ=−0.04). Parallel-Feld-Plan: 3 Drifts (Combo/short_pressure/
  Earliness) alle im Score-only-Scope ≈0, mit L2752-raw-Pin entschärfbar.
- **Echter Blocker: premarket-Daten fehlten (n=1), weil der Cron driftete.
  #253 behebt die Sammlung.** γ-2 erst entscheidbar nach mehreren Werktagen
  echter premarket-Daten (Skalierer 0.10 ist Daumenwert; Kipppunkt-Sweep
  deutet ~0.40, aber n=6 vorläufig). Re-Evaluieren nach 26.05.-Sammelstart.

### Entry-Modul — alle 5 Komponenten jetzt fundiert normierbar

- **`score_delta_t1`: SYMMETRISCH ±15 starten.** Verteilung (n=74, score_history):
  Median 0, Mean −1.85, Zentrum sauber bei 0. Vorbehalte dokumentiert:
  35 %-0-Spike (ein Drittel → neutral 50, null Trennschärfe → wird voraussichtlich
  SCHWÄCHSTE Komponente, beim 30.06.-Gewichts-Check einsortieren, nicht
  nachjustieren) + negativer Tail schwerer (min −57 vs max +30, ±15-Cap clampt
  abwärts mehr). **Perzentil-Variante vertagt an 30.06.** (n zu dünn = Overfitting).
- **`anomaly_freshness`: MITTEL-VARIANTE** (kind=anomaly inkl. suppressed,
  exits + earnings_immediate raus — #260). Coverage ~33 % (strikt-gesendet
  nur 6 %) → meist 0/None, erwartet schwach. **Decay-Steilheit** (HWZ 1–3
  Handelstage, tot ab 5) NICHT jetzt kalibrieren — linearer Platzhalter
  `max(1−age_h/72,0)` reicht solange Feld meist 0. Vertagt an 30.06.
- **3 fundierte aus Recherche:** `rvol_acceleration` (Cap 3.0; in unserem
  Universe selten+explosiv, nicht graduell), `uoa_atm_ratio` (kontinuierlich,
  lückig), `si_trend_5d_slope` (asymmetrisch: links ~−1 gebodet, rechts
  Tail bis +374 — symmetrische Normierung falsch).

### Sonstige geplante Aufgaben

- **HTML-Sanity Phase 1c** (nach 1b stabil): 10er-Assertion-Liste +
  Setup-Pillar-Range-Check.
- **Sortino + Kelly-Inputs** ans `expectancy_diagnose.py` (CLI, kein Frontend).

## Optional / niedrig priorisiert

### Datenposten / Caveats fürs 30.06.

- **Kalender-Aging-Bias `anomaly_freshness`** (read-only verifiziert,
  NICHT gefixt): `_compute_anomaly_freshness` (backtest_history.py:263)
  rechnet **Kalenderstunden** (72 h-Horizont), nicht Handelstage. Folge im
  Sammelzeitraum ab jetzt: wochenend-überspannende Einträge nach unten
  verzerrt (Fr-Anomalie → Mo-Eintrag = 0 statt ~0.6–0.8). Beim 30.06.-AUC:
  schwaches `anomaly_freshness` könnte teils Mess-Artefakt sein → wochenend-
  überspannende Einträge separat betrachten. Handelstag-Umstellung gehört
  SEMANTISCH in die 30.06.-Decay-Kalibrierung (in einem Zug). Entscheidung:
  nicht jetzt fixen (Bias klein gegen 0-Anteil).
- **Kontaminationsfenster:** ~1–2 Tage any-push-Einträge zwischen
  #259-Merge und #260, kein Backfill. Für 30.06.-AUC vernachlässigbar —
  ggf. per Datum ausklammern.

### Code-Hygiene-Backlog

- ✅ Cockpit Stage 3 `.sb`-Cleanup (20.05.) — **Stage-3-Re-Eval 24.05.:
  NICHT lohnend.** `.sb-conf-*` werden im Cockpit (`.cockpit-pillar-value`/
  `-donut-number`) wiederverwendet (#199-Falle), `.sb-lbl/.sb-pts/.sb-note`
  sind Methodik-Panel-Scope (live). Nur `.sb-row/.sb-num/...` im toten
  Flag=False-Fallback (= Rollback-Pfad). Verworfen bis Cockpit-Stabilität.
- ✅ **`backtest_history.py`-Split — ERLEDIGT 24.05. (PR #256).**
- ✅ **Backend-Dead-Code — ERLEDIGT 24.05. (PR #257/#258).**
- 🔧 Offen (niedriger Trading-Wert): v1/v2-Render → Jinja (niemals ohne
  klaren Trading-Wert), Template-Engine statt f-strings,
  `generate_report.py`-Großsplit (verworfen — globals-Falle, f-String-Block).

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **`backtest_history.py` ist ein eigenes Modul** (seit #256). 12 Funktionen,
  via Callable-Injektion (`compute_sub_scores_fn`, `safe_float_fn`) entkoppelt
  — kein Zirkular-Import. `generate_report` importiert es. `_test_extended_schema`
  + 4 Mock-Tests source-inspizieren backtest_history (nicht mehr generate_report)
  für die verschobenen Funktionen.
- **Entry-Shadow-Persist (seit #259/#260):** `score_delta_t1` +
  `anomaly_freshness` sammeln ab Di 26.05. pro V4-Backtest-Eintrag. Schema
  bleibt **v4** (additiv). `anomaly_freshness` nur kind=anomaly (inkl.
  suppressed). **WICHTIG für Entry-Modul-Bau:** wenn `entry_score` selbst
  persistiert wird (10.06.) und ein v4→v5-Bump erwogen wird — der
  S10-v4-Filter (`_s10_load_v4_entries`, `== 4`) muss DANN mit auf `>= 4`
  angepasst werden, sonst fallen neue Einträge aus S10-Überwachung.
- **Entry-Timing-Modul — Plan (Start 10.06.):**
  - **Andock:** ADDITIV in Score-Pipeline (Vorbild `apply_conviction_scores`),
    Aufruf nach `apply_conviction_scores`. 4. Cockpit-Pillar Setup → Monster
    → KI → **Entry**. KEIN `generate_report.py`-Split.
  - **5 Komponenten, je 20 % heuristisch zum Start** (Normierung s.
    „Entry-Modul" oben): `rvol_acceleration` (Cap 3.0), `anomaly_freshness`
    (mittel, linear-Platzhalter), `score_delta_t1` (symmetrisch ±15),
    `si_trend_5d_slope` (asymmetrisch), `uoa_atm_ratio` (kontinuierlich).
    MEIDEN: `coiled_spring_score`, binärer `uoa_score`.
  - **Bau-Schritte 2–5 am 10.06.:** `compute_entry_score` +
    `apply_entry_scores` + `entry_score`/`entry_components`/
    `entry_score_version` persistieren. v5-Bump NUR mit S10-Loader-Anpassung
    (s. o.). Marker `entry_score_version=1`, v2-Kalibrierung nach 30.06.-AUC.
- **HTML-Sanity S9 Stufe 1+2** live (#237/#241): CRIT blockt Push via
  `sys.exit(1)`. Einziger HTML-Aware-Check; S1–S8 lesen nur JSONL/Dicts.
- **`quote_proxy` Tier-2** (#242): 1× pro Daily-Run Worker-Ping. CORS bewusst
  nicht (Browser-only-Klasse).
- **Backtest-Schreibpfad** (#244): nur an Trading-Tagen; `hist_5d` propagiert
  via c.update ins Stock-Dict → Trend-Felder gefüllt.
- **`last_successful_run`** (#243) = Workflow-Lauf-Liveness (`n_runs > 0`);
  `last_digest_sent` = ntfy-Push-Marker für S8 — unterschiedliche Dinge.
- **#253 premarket-Cron** auf `17 8 * * 1-5` (8:17 UTC) gegen GitHub-Drift.
  `run_phase` steuert: `_normalize_rvol`-Short-Circuit (postclose=Pass-through),
  Backtest-Append-Gate (nur postclose), anomaly_pushes (nur premarket=Morgen).
- **#255 Digest-Commit** nutzt Retry-Push (fetch → reset --hard origin/main →
  frische digest-state → commit → push, bei Reject neu fetchen, max 5).
  Ersetzt die alte Rebase-`--ours`-Logik (verwarf unter Rebase die frische
  Schreibung). `--ours`-im-Rebase bei daily-run/ki_agent ist GEWOLLTES
  Last-Write-Wins (regenerierbare Files), KEIN Bug — nicht anfassen.
- **Bestehende Anker unverändert:** Earliness V2 (DTC, AUC 0.77), Phase-2
  Exit (6 Trigger), Live-Polling Cloudflare-Worker, Cockpit-Layout seit #199,
  Token-Encryption AES-GCM/PBKDF2, Service-Worker raus seit #188,
  Conviction-Schwelle 75. RVOL-Norm: PR-α fertig+OFF, β sammelt, γ-1 gemergt,
  γ-2 datengated offen (ENABLED=False, postclose=Pass-through).

## Lessons aus dieser Session (24.05.)

- **Semantik-Mismatch ≠ Dünndaten:** `anomaly_freshness` (#259) maß
  „any-push" statt „anomaly" — exit-Pushes setzten die Freshness-Uhr
  (gegenteiliges Signal). Das war ein **Definitions-Bug**, kein bloßes
  n-zu-klein. Read-only-Diagnose der push_history-kinds deckte es auf,
  BEVOR die Komponente gewichtet wurde. Lehre: bei jedem neuen Feld die
  Datenquelle-Semantik prüfen, nicht nur die Datenmenge.
- **Vorwärts > rückblickend:** der `score_history`-/`push_history`-Snapshot
  ist rückblickend + dünn. Die belastbare Entscheidungsgrundlage ist die
  VORWÄRTSGERICHTETE Shadow-Persist (#259/#260, sammelt ab 26.05.). Bei
  n≥100 zum 30.06.: Verteilung absichern + AUC gegen return_10d.
- **Erwartete Schwäche ≠ Defekt:** `score_delta_t1` (35 %-0-Spike) +
  `anomaly_freshness` (~33 % Coverage) werden zum Start die schwächsten
  Komponenten sein. Beim 30.06.-Gewichts-Check als ERWARTET einsortieren,
  nicht als Bug nachjustieren.
- **Dead-Code-Kaskade:** `_load_production_scores` entfernen (#257) verwaiste
  `_extract_latest_scores` → Folge-PR #258. Bei Löschungen die Aufrufer-Kette
  des Gelöschten mit-prüfen (Scope-Disziplin: Kaskade als eigenen PR, nicht
  im selben ungefragt).
- **S10-v4-Filter-Falle:** additive Backtest-Felder NICHT auf v5 bumpen —
  `_s10_load_v4_entries` filtert `== 4`, ein Bump würde neue Einträge still
  aus der gesamten S10-Überwachung nehmen. v4 behalten + S10_OBSERVED
  erweitern ist der saubere additive Pfad.
- **Diff-Lesen verschärft:** Unified-Diff zeigt Kontext-Zeilen (alt) neben
  neuen — gepaarte `fi`/`}`-Zeilen können wie Syntaxfehler/Reste aussehen.
  Vor „Code kaputt"-Meldung vollständigen Stand + `bash -n`/`py_compile`
  + Keyword-Count statt Diff-Augenschein.
- **GitHub-Cron ist best-effort:** Vormittags-UTC-Crons driften 2–4 h oder
  droppen. Kritische Crons früh genug legen (Puffer bis 13:30 UTC) oder
  robustes Retry — nicht auf Pünktlichkeit verlassen.
- **Arbeitsprinzip — drei getrennte Rollen** (Standing, bestätigt):
  **Diagnose** (read-only, Fakten ohne Meinung) → **Rat** (Code wägt ab,
  darf widersprechen, „nichts bauen" ist valide) → **Entscheidung** (Easy
  allein, Trading-Wert-Filter). KI macht Mechanik, Mensch macht Bedeutung.
  Belegt heute: anomaly_freshness-Definition aus Diagnose, nicht Heuristik;
  Cockpit-Stage-3 + großer Split als „nicht lohnend" verworfen; 5 PRs
  nach klarer Rat-Empfehlung gemergt.
