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

---

## SEKTION 1 — Heute implementiert (chronologisch, 24.05.2026)

Alle gemergt (manueller Merge bei Schema-/Score-relevanten). Schwerpunkt:
Backend-Hygiene + Entry-Modul-Vorarbeit (zwei zuvor unfundierte Komponenten
geklärt) + read-only Methodik-Bewertung des Setup-Scores.

- **PR #256** `backtest_history.py` EXTRAHIERT aus `generate_report.py`
  (~455 Z., 12 Funktionen). Helper-Refactor, kein Verhaltens-Wechsel.
  Kopplung `_compute_sub_scores` + `_safe_float` via **Callable-Injektion**
  gelöst (kein Zirkular-Import, Muster wie `score_inflation_log`).
  `compute_score_confidence` bleibt bewusst in generate_report
  (`_SCORE_CONFIDENCE`-globals-Thematik). 4 Source-Inspektions-Mock-Tests
  mit angepasst (Pfad → backtest_history, kwargs durchgereicht) — keine
  Prüfung gelockert (assert-Count identisch).
- **PR #257** Backend-Hygiene Tier 1a/1b/1d, **deletion-only**: 2 tote
  Funktionen (`_exit_cooldown_expired_keys`, `_load_production_scores`),
  3 ungenutzte Importe (`timedelta` in backtest_history, `time as dt_time`
  in ki_agent, `date` in score_inflation_log), 2 ungenutzte Locals
  (`exc`, `base_upper`). Kein Frontend.
- **PR #258** Kaskaden-Orphan `_extract_latest_scores` entfernt (war nur
  von `_load_production_scores` aufgerufen, durch #257 verwaist).
- **PR #259** Entry-Modul-SHADOW-PERSIST: `score_delta_t1` +
  `anomaly_freshness` **additiv** ins **V4**-Backtest-Schema. Beide
  leer-tolerant, in `S10_OBSERVED_FIELDS` (atomar). **KEIN v5-Bump**
  (S10-v4-Filter-Falle). `score_delta_t1` self-contained aus
  `s["sparkline"]`; `anomaly_freshness` aus `push_history`-ts. Neuer
  Mock-Test `mock_test_entry_shadow_persist` (19/19).
- **PR #260** (Commit `6c0203b`, **manueller Merge**) `anomaly_freshness`
  kind-Filter-Korrektur: #259 maß „any-push-freshness" (exit_p1/exit_p2
  setzten fälschlich die Uhr = gegenteiliges Signal). Fix: 1 Zeile
  `if _pe.get("kind") != "anomaly": continue` — nur **kind=anomaly inkl.
  suppressed**, exits + earnings raus. `test_20` ergänzt (20/20). **v4,
  kein Bump, kein Backfill**, Decay-Helper + S10 unberührt.
- **S8-Digest-Fehlalarm (#255) verifiziert weg** — Retry-Push-Fix
  (fetch → reset → push, max 5) greift; `last_digest_sent` springt aufs
  aktuelle Datum, S8-WARN verschwunden.

**Read-only Diagnose dieser Session (kein Code, fundierte Entscheidungen):**

- premarket-Cron-Drift, RVOL-γ-2-Pool-Inflation, S8-Digest-Ursache,
  backtest_history-Extrahierbarkeit, Entry-Komponenten-Verteilungen.
- **Methodik-Bewertung Setup-Score gegen akademische Literatur** (eigene
  Sektion unten) — Vorzeichen-Test an echten Backtest-Daten.

---

## SEKTION 2 — Aktive Positionen (im Secret `POSITIONS_JSON`)

> **Top-10 = Such-Stream für NEUE Einstiege, nicht Hold-Liste.** Die
> gehaltenen Positionen sind separat; Top-10-Membership ≠ „halten".

- **AMC** — Halt, `no_exit_alerts=true` (bewusste Buy-and-Hold, kein Exit-Druck-Push)
- **IONQ** — unverändert
- **RR** — Earnings waren 22.05., catalyst-Exit feuerte korrekt
- **CRMD** — mehrere **Trailing-Stop-Exit-Alerts am 24.05.**, halten

---

## SEKTION 3 — Verifikation Di 26.05. (erster Handelstag)

Alle brauchen einen Daily-Run → **frühestens Di 26.05.** (Mo 25.05.
Memorial Day, Börse + premarket-Cron-Sinn entfallen).

- **#253 premarket-Cron (★ erster echter Test):** Cron wurde 22.05. von
  `17 10` auf **`17 8 * * 1-5` (8:17 UTC)** verschoben gegen GitHub-Drift
  (2.4–3.6 h beobachtet). Prüfen:
  - Lief der Daily-Run mit **`run_phase=premarket` VOR 13:30 UTC** (US-Open)?
  - Kamen **Morgen-Anomaly-Pushes** aufs iPhone (ggf. ~1 h später durch Drift)?
  - Schreibt `score_inflation_log` `trading_session_phase=premarket`?
  - Status im **Health-Check-Digest (ntfy)** sichtbar?
- **#259/#260 Shadow-Persist:** beim ersten postclose-Run prüfen, dass
  `score_delta_t1` + `anomaly_freshness` als Keys in jedem V4-Eintrag
  erscheinen (Wert numerisch/None, beides legitim). `anomaly_freshness`
  wird meist 0/None sein (erwartet — sparse).
- **#255 Digest-S8 (laufend):** Retry-Push-Fix prüfen — `last_digest_sent`
  aktuell, S8-WARN weg. WE-Digest-Cron (08:47 UTC) lief evtl. Sa/So,
  read-only prüfbar.
- **ERLEDIGT (nicht mehr offen):** #244 Trend-Felder (si_trend_5d_slope
  n=98/99, rvol_buildup/vol_stability/coiled_spring 0 % null im jüngsten
  Run), #251 rvol_acceleration (n=21) + uoa_atm_ratio (n=15) befüllt,
  return_3d/5d-Backfill (S10-WARN war 23.05. weg).

---

## SEKTION 4 — Planned Tasks + Wiedervorlagen

### Roadmap (datiert)

- **Di 26.05.2026** — #253-premarket-Verify + #259/#260-Shadow-Persist-Verify
  (s. Sektion 3).
- **NACH Di-Verify** — **premarket-Sammel-Wächter** in Health-Check
  (MECHANIK): ≥ 1 echter `run_phase=premarket`-Run in ~5 Werktagen, sonst
  WARN. **Erst bauen wenn die Sammlung tatsächlich läuft — NICHT auf n=0
  scharfschalten** (sonst Dauer-Fehlalarm bevor der erste premarket-Run da ist).
- **~04.06.2026** — Earliness-AUC erste Schätzung r5d (AUC-Uhr startete
  21.05. neu wegen hist_5d-Bug). Kriterium: n + Klassen-Balance prüfen
  BEVOR AUC gerechnet (Lehre #238: schöne Zahl auf dünnem n = trügerisch).
- **02.06.2026** — **Chart-Indikatoren** (TTM Squeeze / VWAP / OBV) als
  **Entry-Score-Komponenten** (NICHT Setup-Score — Setup bleibt unberührt).
- **10.06.2026** — ★★★ **Entry-Timing-Modul START** (höchste Prio,
  mehrwöchig). Design v1 in Sektion 5. Alle 5 Komponenten haben begründete
  Start-Normierung.
- **~24.–30.06.2026** — Entry-AUC-Diagnose (`entry_score × return_5d/10d`)
  + **erste belastbare Backtest-Auswertung**: V2-only (`score ≥ 70`-Bucket,
  n≈100) + 30 Tage inflations-bereinigt, daily-≥70-Bucket-CI kreuzt Null
  nicht mehr (Kriterium #238).
- **Nach Entry-Start** — **wiederkehrendes Entry-Komponenten-Screening als
  Health-Check-Baustein** (INHALT, nicht nur Mechanik): laufende AUC-/
  Coverage-Überwachung der Entry-Komponenten.
- **02.07.2026** — Premium-Daten-Stack.

### γ-2 (RVOL-Normalisierung) — Status: datengated, NICHT mehr 30.05.-fix

- Master-Switch verworfen (premarket-Pool-Inflation, Cap-Sättigung würfelt
  Ranking ρ=−0.04). Parallel-Feld-Plan: 3 Drifts (Combo/short_pressure/
  Earliness) im Score-only-Scope ≈0, mit L2752-raw-Pin entschärfbar.
- **Echter Blocker: premarket-Daten fehlten (n=1), weil der Cron driftete.
  #253 behebt die Sammlung.** γ-2 erst entscheidbar nach mehreren Werktagen
  echter premarket-Daten (Skalierer 0.10 = Daumenwert; Kipppunkt-Sweep
  deutet ~0.40, aber n=6 vorläufig). Re-Evaluieren nach 26.05.-Sammelstart.

### Sonstige geplante Aufgaben

- **HTML-Sanity Phase 1c** (nach 1b stabil): 10er-Assertion-Liste +
  Setup-Pillar-Range-Check.
- **Sortino + Kelly-Inputs** ans `expectancy_diagnose.py` (CLI, kein Frontend).

---

## SEKTION 5 — Strategische Roadmap (Entry-Timing-Modul)

### Entry-Timing-Modul — Design v1 (Bau-Start 10.06.)

- **Andock:** ADDITIV in die Score-Pipeline (Vorbild `apply_conviction_scores`),
  Aufruf NACH `apply_conviction_scores`. 4. Cockpit-Pillar: Setup → Monster
  → KI → **Entry**. **KEIN `generate_report.py`-Split.** Setup-Score bleibt
  unberührt (Entry ist eigene Achse).
- **5 Komponenten, je 0–100, Entry-Score = Schnitt je 20 % heuristisch zum Start:**
  | Komponente | Start-Normierung | Fehlend → |
  |---|---|---|
  | `rvol_acceleration` | Cap **3.0** (selten + explosiv, nicht graduell) | 50 |
  | `score_delta_t1` | **symmetrisch ±15** | 50 |
  | `si_trend_5d_slope` | **asymmetrisch** (links ~−1 gebodet, rechts Tail bis +374) | 50 |
  | `uoa_atm_ratio` | kontinuierlich **1.25 / 3.0 / 5–10×** | 50 |
  | `anomaly_freshness` | linearer Platzhalter `max(1−age_h/72, 0)` | **0** |
  - **MEIDEN:** `coiled_spring_score`, binärer `uoa_score`.
- **Start SHADOW** (persistiert `entry_score`/`entry_components`/
  `entry_score_version=1`, **kein Push**). Push erst NACH Entry-AUC
  (~30.06.) + Kalibrierung.
- **Bau-Schritte 2–5 am 10.06.:** `compute_entry_score` + `apply_entry_scores`
  + Persistenz. **v5-Bump NUR mit S10-Loader-Anpassung** (`_s10_load_v4_entries`
  `== 4` → `>= 4`), sonst fallen neue Einträge aus S10.

### Schwellen-Philosophie

- **Phasen-/perzentil-basierte Schwellen statt fester Absolut-Schwellen**
  (γ-getrennte Roadmap-Idee). Score-Inflation macht absolute Cutoffs
  zeitabhängig — Entry-Komponenten sollen, wo möglich, gegen Run-Rang/
  Perzentil normiert werden statt gegen feste Absolutwerte. Im Einklang mit
  der Methodik-Bewertung (Sektion unten): within-run-Rang ist die robuste
  Messgröße.

---

## SEKTION 6 — Code-Hygiene-Backlog (mit Status)

- ✅ **ERLEDIGT 24.05.:** `backtest_history.py`-Split (#256), Backend-
  Dead-Code (#257/#258).
- 🔧 **OFFEN (niedriger Trading-Wert):** v1/v2-Render → Jinja (niemals ohne
  klaren Trading-Wert), Template-Engine statt f-strings.
- ❌ **VERWORFEN:** `generate_report.py`-Großsplit — **globals-Falle**
  (`_SCORE_CONFIDENCE`/`_FX_USD_EUR`) + 6806-Zeilen-f-String-Block machen
  den Split fragil; kein Trading-Wert.
- ⏸ **VERTAGT:** Cockpit Stage 3 `.sb`-Reste. `.sb-conf-*` werden im
  Cockpit (`.cockpit-pillar-value`/`-donut-number`) **live reused**
  (#199-Falle); `.sb-lbl/.sb-pts/.sb-note` sind Methodik-Panel-Scope (live).
  Nur `.sb-row/.sb-num/...` im toten Flag=False-Fallback (Rollback-Pfad).
  **Null Trading-Wert** → verworfen bis Cockpit-Stabilität.

---

## SEKTION 7 — Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **`backtest_history.py` = eigenes Modul** (seit #256). 12 Funktionen, via
  Callable-Injektion (`compute_sub_scores_fn`, `safe_float_fn`) entkoppelt
  — kein Zirkular-Import. `generate_report` importiert es. `_test_extended_schema`
  + 4 Mock-Tests source-inspizieren backtest_history (nicht mehr generate_report)
  für die verschobenen Funktionen.
- **Entry-Shadow-Persist (seit #259/#260):** `score_delta_t1` +
  `anomaly_freshness` sammeln ab Di 26.05. pro V4-Eintrag. Schema bleibt
  **v4** (additiv). `anomaly_freshness` nur **kind=anomaly inkl. suppressed**.
  **S10-Loader `_s10_load_v4_entries` filtert `schema_version == 4` — bei
  künftigem entry_score-v5-Bump (10.06.) MUSS der Filter auf `>= 4`, sonst
  fallen neue Einträge aus S10.**
- **Earliness V2** (DTC-Niveau-Basis, AUC 0.77 in 14d-Stichprobe).
- **Earliness-Trend-Logging** (#244): si_trend_5d_slope / rvol_buildup_5d /
  vol_stability_5d / coiled_spring_score — **0 % null** im jüngsten Run.
  Schreibpfad nur an Trading-Tagen; `hist_5d` propagiert via `c.update`.
- **Phase-2 Exit komplett** (6 Trigger: score_decay/profit_lock/overheated/
  setup_erosion/catalyst/trend_break), alle Push-Klassen scharf.
- **Live-Quote-Polling** Cloudflare-Worker (gesund, `quote_proxy` Tier-2
  #242: 1× pro Daily-Run Worker-Ping; CORS bewusst browser-only).
- **Conviction-Schwelle 75** (#123): HIGH_THRESHOLD (conviction_high-Push)
  + MIN_THRESHOLD (Gating aller anderen Anomaly-Pushes), numerisch gleich,
  konzeptionell getrennt.
- **Token-Encryption** AES-GCM + PBKDF2 (600k Iter).
- **RVOL-Normalisierung:** PR-α fertig + **OFF** (`ENABLED=False`), PR-β
  sammelt, γ-1 gemergt, **γ-2 offen** (datengated). postclose =
  Pass-through-Short-Circuit.
- **`run_phase` steuert** drei Dinge: `_normalize_rvol`-Short-Circuit
  (postclose=Pass-through) · Backtest-Append-Gate (nur postclose) ·
  anomaly_pushes (nur premarket=Morgen).
- **HTML-Sanity S9 Stufe 1+2** (#237/#241): CRIT blockt Push via
  `sys.exit(1)`. Einziger HTML-Aware-Check; S1–S8 lesen nur JSONL/Dicts.
- **`last_successful_run`** (#243) = Workflow-Liveness (`n_runs > 0`);
  `last_digest_sent` = ntfy-Push-Marker für S8 — unterschiedliche Dinge.
- **#253 premarket-Cron** auf `17 8 * * 1-5` (8:17 UTC) gegen GitHub-Drift.
- **#255 Digest-Commit** nutzt Retry-Push (fetch → reset --hard origin/main →
  frische digest-state → commit → push, bei Reject neu fetchen, max 5).
  `--ours`-im-Rebase bei daily-run/ki_agent ist GEWOLLTES Last-Write-Wins
  (regenerierbare Files), KEIN Bug — nicht anfassen.
- **Service-Worker raus** seit #188 (statische Seite, kein Offline-Cache).

---

## SEKTION 8 — Lessons

- **Caution-Prinzip:** read-only Diagnose vor jeder nicht-trivialen
  Code-Änderung. „NUR DIAGNOSE, kein Code" wird strikt eingehalten.
- **Refactor-Konsumenten-Prinzip:** vor Merge eines Refactors die
  Konsumenten greppen (Source-Inspektions-Tests fanden 4 betroffene
  Mock-Tests bei #256; Dead-Code-Kaskade #257→#258).
- **iPhone-Verify-Protokoll:** nach Cache-Wipe ist Master-PW-Re-Entry
  Pflicht (Unlock-Modal). Live-Verifikation auf iPhone vor Merge bei
  Layout-Symptomen (Mock-Tests sichern CSS-Source, nicht Computed-Layout).
- **Diff-Lesen verschärft:** Unified-Diff zeigt Kontext-Zeilen (alt) neben
  neuen — gepaarte `fi`/`}` können wie Reste/Syntaxfehler aussehen. Vor
  „Code kaputt"-Meldung vollständigen Stand + `bash -n`/`py_compile` +
  Keyword-Count statt Augenschein.
- **Daten-Reife (grün ≠ gefüllt):** Pipeline kann grün laufen während das
  Artefakt falsch ist (Semantik-Mismatch #259). Datenquelle-Semantik prüfen,
  nicht nur Datenmenge.
- **GitHub-Cron ist best-effort:** Vormittags-UTC-Crons driften 2–4 h oder
  droppen. Kritische Crons früh genug legen (Puffer bis 13:30 UTC) oder
  robustes Retry — nicht auf Pünktlichkeit verlassen.
- **Trading-Wert-Filter steuert Diagnose-Tiefe:** vor jedem PR „bringt das
  Trading konkret weiter?". Engineering-Hygiene ohne Trade-Impact → Backlog.
- **Zeitschätzung 2–3× überschätzt:** etablierte Patterns sind Routine
  geworden; bewusst kürzer schätzen.
- **Arbeitsprinzip — drei getrennte Rollen** (Standing): **Diagnose**
  (read-only, Fakten ohne Meinung) → **Rat** (Code wägt ab, darf
  widersprechen, „nichts bauen" ist valide) → **Entscheidung** (Easy allein,
  Trading-Wert-Filter). KI macht Mechanik, Mensch macht Bedeutung.

---

## PLUS — Zwei Entry-Komponenten geklärt (24.05.)

- **`score_delta_t1`: SYMMETRISCH ±15 starten.** Verteilung (n=74,
  score_history): Median 0, Mean −1.85, Zentrum sauber bei 0. Vorbehalte:
  **35 %-0-Spike** (ein Drittel → neutral 50, null Trennschärfe → wird
  voraussichtlich SCHWÄCHSTE Komponente; beim 30.06.-Gewichts-Check
  einsortieren, NICHT nachjustieren) + negativer Tail schwerer (min −57 vs
  max +30, ±15-Cap clampt abwärts mehr). **Perzentil-Variante vertagt an
  30.06.** (n zu dünn = Overfitting).
- **`anomaly_freshness`: MITTEL-VARIANTE** (kind=anomaly **inkl. suppressed**,
  exits + earnings_immediate **raus** — #260). Coverage ~33 % (strikt-gesendet
  nur 6 %) → meist 0/None, erwartet schwach. **Decay-Steilheit** (HWZ 1–3
  Handelstage, tot ab 5) NICHT jetzt kalibrieren — linearer Platzhalter
  `max(1−age_h/72, 0)` reicht solange Feld meist 0. Vertagt an 30.06.
- **Kalender-Aging-Bias** (read-only verifiziert, **NICHT gefixt**):
  `_compute_anomaly_freshness` (backtest_history.py:263) rechnet
  **Kalenderstunden** (72 h), nicht Handelstage. Folge: wochenend-
  überspannende Einträge nach unten verzerrt (Fr-Anomalie → Mo-Eintrag = 0
  statt ~0.6–0.8). **Reiner Datenposten fürs 30.06.** — Handelstag-Umstellung
  gehört SEMANTISCH in die 30.06.-Decay-Kalibrierung (in einem Zug). Nicht
  jetzt fixen (Bias klein gegen 0-Anteil).
- **Kontaminationsfenster:** ~1–2 Tage any-push-Einträge zwischen #259-Merge
  und #260, kein Backfill — für 30.06.-AUC vernachlässigbar, ggf. per Datum
  ausklammern.
- **Alle 5 Komponenten haben jetzt eine begründete Start-Normierung**
  (s. Sektion 5).

---

## PLUS — Methodik-Bewertung Setup-Score (24.05., read-only)

Externe Literatur-Bewertung + Vorzeichen-Test an echten Backtest-Daten.
**Reine Bestandsaufnahme — KEINE Score-Änderung. Vorzeichen-Festschreibung
für die Live-Pipeline erst 30.06.**

### Literatur-Stand (7 Punkte, verdichtet)

1. Akademische Breitmarkt-Literatur: hohes **Short-Interest** UND hohe
   **Days-to-Cover** sagen im DURCHSCHNITT **negative** Forward-Returns
   voraus (informierte Short-Seller).
2. Der Setup-Score gewichtet genau diese zwei am stärksten **positiv**:
   `short_float` 32 + DTC 23 = **55/100**.
3. Kern-Hypothese: hoher Setup-Score misst **Squeeze-Disposition**, lädt aber
   im Mittel **negativ/null** auf erwarteten Return — Edge nur aus dem
   **Tail (Zündung)**, nicht aus dem Setup-Level.
4. Confounder-Disziplin Pflicht: (a) Score-Inflation → **within-run-Rang**
   statt absoluter Cutoffs; (b) V1/V2-Earliness irrelevant (wirkt nur auf
   Conviction); (c) rechtsschiefes Sample → Median UND Mean + n getrennt.
5. Range-Restriction-Lehre: Universe ist auf `SF ≥ 15 %` vorgefiltert →
   die Breitmarkt-Monotonie „mehr SI = schlechter" greift INNERHALB der
   bereits hoch-geshorteten Cohorte nicht mehr.
6. Negative Base-Rate: der typische Squeeze-Kandidat **verliert** über 10d;
   positive Erwartung kommt ausschließlich aus dem rechten Tail.
7. Tail-These prüfbar: fängt der Score wenigstens den rechten Tail (die
   Knaller), auch wenn der Mittelwert negativ/null lädt?

### Datenbasis

`backtest_history.json`, n=1577. **Zwei Populationen** (Haupt-Confounder):
- **bootstrap** (n=1012, Apr 2025–Apr 2026): roher `score()`, retroaktiv.
- **live** (`source=none`, n=565, Apr–Mai 2026, ~14 Runs): volle Pipeline.
Returns: `return_{3,5,10}d` (+ `_t1` als Robustheits-Spiegel). 10d non-null:
1401. Within-run-Perzentil-Pooling (Median 4 Ticker/Run → keine Per-Run-Quintile).

### Vorzeichen-Test (Setup-Score ↔ Forward-Return)

- **Global Spearman:** ALL −0.08 @10d (signifikant, p≈.002).
- **Within-run (inflations-robust):** ALL **≈ 0** (−0.01 @10d, n.s.).
  → Die globale negative Ladung ist überwiegend ein **Between-Run-Artefakt**
  (Score-Inflation/Zeit), KEIN Querschnitts-Signal.
- **bootstrap vs live gegenläufig:** bootstrap −0.07 @10d (p≈.04) vs live
  **+0.116 @10d (p≈.02)**.

### Faktor-Ebene (within-run @10d) — der eigentliche Literatur-Test

| Faktor | bootstrap | live | Literatur erwartet |
|---|---|---|---|
| short_float | −0.028 (n.s.) | −0.012 (n.s.) | stark negativ |
| DTC | −0.050 (n.s.) | **+0.187 (p≈.0002)** | stark negativ |
| rvol | **−0.085 (p≈.01)** | +0.094 (p≈.06) | (nicht Teil der These) |

→ **Weder SF noch DTC zeigen das robuste negative Vorzeichen.** SF ≈ 0
in beiden. DTC ≈ 0 (bootstrap) bis **klar positiv** (live) — entgegengesetzt
zur Literatur. Einzig `rvol` bootstrap-negativ, aber live-positiv (widersprüchlich).

### Negative Base-Rate + Tail-Check

- **Skew:** Median return_10d NEGATIV überall (ALL −2.05, live −3.85),
  Mean positiv nur tail-getrieben (ALL +1.04, max +1007 %).
- **Tail-Check (Score-Within-Run-Perzentil-Median):** hoher Score
  über-repräsentiert **BEIDE** Tails. Große Verlierer sogar eher höher im
  Score als große Gewinner (bootstrap: 74 % der Bottom-Decile vs 59 % der
  Top-Decile in oberer Score-Hälfte). Monster-Winner (≥+25 %) nur
  55.–60. Perzentil → **der Score fängt den rechten Tail NICHT sauber.**

### Fazit + Strategie-Anker

- Der Setup-Score lädt within-run **≈ 0** directional → er ist ein
  **Dispersions-/Disposition-Selektor**, kein Richtungs-Prädiktor. Das
  **bestätigt die Disposition-These empirisch.**
- **KEINE Score-Umgewichtung.** Kein Faktor robust + konsistent negativ;
  bootstrap/live widersprüchlich; −0.08 global ≈0 within-run fitten = Rauschen.
- **3 Strategie-Anker:** (1) Score findet das Pulverfass, nicht die Richtung
  → das **Entry-Timing-Modul ist der korrekte Hebel**. (2) Die Edge liegt in
  der **Zündungs-Erkennung**, nicht im Setup-Level. (3) „Setup misst
  Disposition"-These ist datenbelegt.
- **30.06.-Re-Prüfpunkte:** (i) Faktor-Vorzeichen mit mehr live-Runs **ohne**
  den +1007 %-Ausreißer (Winsorize/Median-Fokus); (ii) ob `rvol` auch live
  robust negativ wird (dann echter Score-Kandidat — aber Timing, nicht das
  SF/DTC-Literatur-Argument); (iii) ob das Entry-Modul den rechten Tail
  trennt, den der Score allein nicht trennt.
- **Roadmap-Kandidaten (NICHT jetzt, 30.06. mit-evaluieren):** **Borrow-Fee +
  Utilization** als mögliche **autoritative `score()`-Faktoren** prüfen
  (eigene Literatur-Basis, heute nur im Katalysator-Sub-Score bzw. ungescored).
  Erst bei robustem Vorzeichen + Trading-Wert.
- **Entscheidbarkeit:** Für die Live-Pipeline **noch nicht entscheidbar**
  (14 Runs / 1 Monat, ein Ausreißer kippt Vorzeichen). bootstrap robuster,
  misst aber einen anderen (rohen) Score. → **30.06. abwarten.**
