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
- **Methodik-Bewertung Setup-Score gegen akademische Literatur + Scanner +
  eigene Daten** (eigene Sektion unten) — Vorzeichen-Test an echten Backtest-Daten.

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

### Roadmap-Terminierung (Entscheidung 25.05.)

**Regel:** Datum nur wenn Task **Trading-Wert UND Datenreife** hat → an
Checkpoint koppeln. Nie auf Verdacht, nie für Aufräumarbeit.

**AN 30.06.-CHECKPOINT GEKOPPELT (terminiert):**

- **Perzentil-/relativer Score:** löst Score-Inflation strukturell +
  Industriestandard. Wartet nur auf saubere Datenbasis (entsteht 30.06.
  ohnehin). Fundierteste Erkenntnis der Methodik-Bewertung — **nicht
  versanden lassen.**
- **Kalender→Handelstag Decay-Fix:** ZWINGEND in einem Zug mit
  Decay-Steilheit-Kalibrierung (sonst dieselbe Funktion zweimal angefasst).

**BEWUSST NICHT TERMINIERT — datenabhängig (Trigger = Ereignis, nicht Datum):**

- **γ-2:** braucht mehrere echte premarket-Werktage. Anzahl erst nach
  Di-26.05.-Verify klar. Datum jetzt = n=1-Falle (wie alter „30.05."-Plan,
  verworfen).
- **Borrow-Fee + Utilization in `score()`:** erst nach Entry-Modul UND
  30.06.-Datenbasis bewertbar. Nicht am Score schrauben bevor
  Edge-im-Timing geklärt.

**BEWUSST NICHT TERMINIERT — niedriger Trading-Wert (kein Aufschub-Schaden):**

- **Hygiene v1/v2→Jinja, Template-Engine:** Engineering-Vollständigkeit,
  null Trade-Wert.
- **Cockpit Stage 3 `.sb`-Cleanup:** vertagt (#199-Falle, Risiko > Nutzen).
  Datum würde Druck für riskanten Null-Nutzen-Eingriff erzeugen.

### Wiedervorlage: premarket-Cron-Drift beobachten (ab 26.05.)

**Kontext:** #253 (8:17 UTC) belegt erfolgreich Mo 25.05. — aber Drift
**+3h43m**, nur **1h30m Marge** bis 13:30 UTC. **n=1.**

**Erkenntnis (Diagnose 26.05.): KEIN Zielkonflikt Drift vs. Daten-Dünne.**
premarket-`rel_volume` = letzter **VORTAGS-Tagesbar** (yfinance daily),
NICHT Live-PM-Liquidität → über das gesamte premarket-Fenster
(03:18–09:56 ET) **KONSTANT, zeit-unabhängig gefüllt**. Datendünne ist ein
OPEN-/Intraday-Effekt (Partial-Bar), nicht premarket. **Früherer Cron daher
DATENSEITIG GRATIS.** (Einziges live-PM-Feld wäre
`_fetch_premarket_volumes_batch` → nur Earliness V1, inaktiv seit V2.)
Phasen-Logik: `_session_phase` (`score_inflation_log.py:41–68`),
premarket = alles vor 09:30 ET / 13:30 UTC, **keine Untergrenze**. 8:17 UTC
= 04:17 ET = 17 min nach PM-Start (04:00 ET).

**Beobachten (Di 26. / Mi 27. / Do 28.05.):** premarket-Run-Timestamp
gegen 13:30 UTC. Drift sammeln, **NICHT auf n=1 reagieren.**

**Gestufte Entscheidung (Trigger statt Datum):**

- Drift bleibt ~3–4h → **nichts ändern**, 8:17 reicht.
- Drift wiederholt **> 4,5h** (Marge < 40 min) ODER premarket-Run kippt auf
  `tsp=open` (23.05.-Muster `run_phase=premarket / tsp=open`) → Cron
  **DIREKT auf 6:17 UTC**. KEIN Zwischenschritt 7:17 — früher ist gratis,
  also max. Reserve nehmen.
- Statt Drift ein **Cron-DROP** (Run fehlt GANZ, nicht nur spät) → zweiter
  premarket-Slot (`cron: '17 6'` UND `'17 8 * * 1-5'`). Redundanz gegen
  gedroppten Slot. Kosten: 2 premarket-Runs/Tag (doppelte log-Zeilen +
  ki_agent-Trigger). **NUR wenn DROP empirisch auftritt, nicht prophylaktisch.**

**Merge-Klasse falls gebaut:** neuer/geänderter Workflow-Cron =
**manueller Merge**.

**Offen Di 26.05.:** premarket-Run um 11:37–11:52 UTC noch nicht committet
(nur KI-Agent-Ticks 04:35 / 08:44 UTC, kein neuer Daily-Run; keine
26.05.-premarket-Zeile im score_inflation_log). Bei Ausbleiben bis
~12:30 UTC ggf. **Tag 1 eines Drift-/Drop-Musters.**

### Wiedervorlage: Abuse-Lock-Beobachtung + Frequenz-Reduktion (ab 27.05.)

**Ursache Lock 26.05. NICHT eindeutig (n=1).** Drei Kandidaten:
(1) KI-Agent-Hourly 24/7, (2) einmaliger 24.05.-Dev-Burst (23 Commits),
(3) Auto-Trigger-Kette / API-Muster. Commit-Last moderat (8–13/Werktag)
→ wahrscheinlicher Trigger ist die **RUN-/API-Last**, nicht die Commit-Zahl.

**Zwei Spuren parallel — erst handeln wenn EINE Antwort da ist:**

1. **GitHub-Ticket #4418923** — konkret nach dem Auslöser gefragt
   (Run-Frequenz? Commits? API-Muster?). Eine konkrete Support-Antwort
   schlägt jede Heuristik → dann gezielt fixen.
2. **Beobachten Mi 27. / Do 28. / Fr 29.05.: erneuter Lock?**
   - **KEIN Lock** → war der einmalige 24.05.-Burst, **KEINE Reduktion nötig**.
   - **ZWEITER Lock** → struktureller Trigger bewiesen.

**NICHT auf n=1 reagieren, NICHT prophylaktisch ausdünnen.**

**Reduktions-Hebel (falls nötig):** KI-Agent-Hourly nur im Handelsfenster
(~12–22 UTC werktags), off-hours/WE ausgedünnt → 24/Tag → ~10–12/Tag
(Faktor ~2). Berührt **NICHT** die premarket-Sammlung oder den
postclose-Append (separater Daily-Workflow). S7-Coverage bleibt via
Daily-Auto-Trigger erhalten. **Merge-Klasse: Workflow-Cron = manueller Merge.**

**Pipeline-Integrität nach Lock (26.05. verifiziert): sauber.** Schema v4
intakt, Shadow-Felder (`score_delta_t1` / `anomaly_freshness`) da, kein
Doppel-Append (18 unique Ticker trotz 2 postclose-Runs), keine Korruption
(alle JSON/JSONL parsen, 0 kaputte Zeilen). **Offene Nuance (niedrig):**
26.05.-Entry-Tag-Scores evtl. aus dem 03:21-Snapshot (stale premarket-RVOL)
statt 21:35-EOD — für 30.06. im Blick, **nicht fixen**.

**premarket-Verify #253: für 26.05. VERLOREN** (gedrifteter Slot ∩
Lock-Fenster — null `run_phase=premarket`-Zeile heute, beide Daily-Runs
resolveten postclose). Verschoben auf nächsten sauberen Werktag **Mi 27.05.**
γ-2 bleibt bei n≈1 echten premarket-Tagen.

**WARN-Status (selbstheilend erwartet):**
- **S8 Digest-Lücke** — der 8:47-Digest-Cron starb im Lock,
  `last_digest_sent` steht auf 25.05 (zur Run-Zeit 45.6 h alt). Heilt beim
  nächsten erfolgreichen 8:47-Cron.
- **S10 return_5d Rolling-Update** — 13/61 gealterte Einträge ohne Outcome
  (21%), Holiday-Wochenende + Lock-Disruption. Ein sauberer postclose-Tag
  zeigt, ob echt fortbestehend.
- **finviz=16 consecutive_failures** — eingefroren auf 25.05-Stand (Digest-
  State stale), Tier-2-Coverage-Lücke obskurer Smallcaps, **kein Bug**.

### #253 premarket-Verify ERFOLGREICH (27.05.)

Erster sauberer Verify-Tag. premarket-Run **11:49 UTC**, `run_phase == tsp ==
premarket`, **kein `open`-Kippen** (23.05.-Drift-Muster nicht wiedergekehrt).
Drift **+3h32m** (Mo 25.05. war +3h43m → stabil), Marge **1h41m** vor 13:30.
5 Anomalien premarket detektiert (GEMI/GRPN/LUCK/RR×2), **alle conviction-gated
suppressed** (<75) — Pipeline aktiv, kein Spam. **γ-2-Sammlung jetzt n≈2**
(25.05. + 27.05.). **Cron 8:17 bleibt, kein Eingriff.**

**Nebenbefund (niedrig, beobachten):** Ein **02:53-UTC-postclose-Run**
(gedrifteter 21:17-Cron der Vornacht +~5,5h ODER manuell) verkürzte das
Morgen-Anomaly-Fenster (Ticks postclose-gated bis 11:49, Pushes aus). EOD-Daten
zeitunabhängig gültig → datenseitig unkritisch. Für die Cron-Drift-Wiedervorlage:
beobachten, ob der **postclose-Cron systematisch in die Nacht driftet** (gleicher
Mechanismus wie premarket-Drift, nur am anderen Tagesende).

### S10 return_5d — KEIN Pipeline-Problem, Holiday-/Lock-Nachlauf (27.05.)

Ursache bewiesen (read-only). Fill = `update_backtest_returns()` in
**ki_agent.py:380**, läuft stündlich pro Tick, indexiert reale yfinance-Bars,
idempotent. **LÄUFT und HOLT NACH** (Beweis: 18.05.-Eintrag, return_5d am
Lock-Tag fällig, ist gefüllt). Steigende Quote (21%→38%) = zwei harmlose
Ursachen: (1) Alters-Zähler `_trading_days_elapsed` / `_s10_trading_days_elapsed`
ignorieren US-Feiertage → Memorial Day 25.05. als Handelstag mitgezählt → S10
flaggt 19./20.05.-Kohorte **~1 Tag ZU FRÜH** (vor Existenz des realen EOD-Bars).
(2) 26.05.-Lock-Fill-Gap.

**Vorhersage (Verifikations-Trigger):** 27.05.-EOD füllt 19.05.-Kohorte (13),
28.05.-EOD die 20.05.-Kohorte (17). **Quote MUSS bis Do/Fr fallen.**
**Beobachten Do 28./Fr 29.05.:** Quote fällt → Nachlauf bestätigt, erledigt.
Bleibt hoch/steigt nach 2 sauberen EOD-Zyklen → echtes Problem, neu
diagnostizieren. **KEIN Fix jetzt.**

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
  Perzentil normiert werden statt gegen feste Absolutwerte. **Bestätigt durch
  die Methodik-Bewertung (unten): within-run-Rang ist die robuste Messgröße —
  UND es ist Scanner-Industriestandard (Fintel/Ortex relativ/perzentil).**

### Roadmap-Kandidat: Externer Dead-Man-Switch (Liveness der Mechanik-Überwachung)

**Kein Sofort-Fix.** Ein Liveness-Check **AUSSERHALB** GitHub Actions, der
alarmiert, wenn der erwartete Health-Push **AUSBLEIBT** (z.B. externer Cron /
Healthchecks.io-artiger Dienst, der ein Signal vom Digest erwartet und bei
Stille selbst pingt). So alarmiert die **Stille selbst** — schließt den blinden
Fleck aus der Sektion-8-Lesson „Wächter teilt das Failure-Fate des Überwachten"
(26.05.): der heutige Abuse-Lock blieb unbemerkt, weil der Health-Digest im
selben Actions-Umfeld mit-starb.

**Priorität:** erst **nach** Lock-Ursache-Klärung bewerten (Ticket #4418923 +
Beobachtung 27.–29.05.). Falls Locks kein Muster sind, ist der Hebel niedriger.

**Ebenen-Trennung beachten:** das ist Liveness der **MECHANIK-Überwachung
selbst** — eine Ebene **über** dem geplanten premarket-Sammel-Wächter (der
überwacht die Daten-Sammlung, nicht das Monitoring-System).

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
- 📅 **AN 30.06.-DECAY-FIX KOPPELN — S10-Feiertags-Zähler (display-only):**
  Die Alters-Zähler `_trading_days_elapsed` / `_s10_trading_days_elapsed`
  ignorieren US-Feiertage → wiederkehrender ~1-Tag-Fehlalarm in
  Feiertagswochen. Fill bleibt korrekt (indexiert reale Bars), nur S10-Flag
  kosmetisch zu früh. Gleiche Kalender→Handelstag-Klasse wie der bereits an
  30.06. gekoppelte Decay-Fix → dort mit-erledigen. Nicht datenkritisch.
  Fix-Optionen (Präferenz absteigend): **(a)** Alters-Zähler an die
  reale-Bar-Logik koppeln, die der Fill SCHON nutzt (yfinance-Bars = echte
  Handelstage) — keine neue Dependency, im-Haus-konsistent. **(b)**
  `holidays`-Paket (leichtgewichtig, nur US-Feiertage abziehen). **(c)**
  `pandas_market_calendars` / `exchange_calendars` (mächtig, aber schwere
  Dependency — angesichts Run-/API-Last-Sensitivität nach dem 26.05.-Lock
  eher meiden).

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
  fallen neue Einträge aus S10. ADDITIV HALTEN.**
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
- **Range-Restriction (methodisch, neu 24.05.):** Literatur-Faktor-Vorzeichen
  gelten für den BREITMARKT. Bei vorgefiltertem Universe (SF ≥ 15 %) greift
  Range-Restriction — Breitmarkt-Edges können innerhalb der gefilterten
  Cohorte verschwinden. **Eigene Daten schlagen Literatur-Analogie.**
- **Arbeitsprinzip — drei getrennte Rollen** (Standing): **Diagnose**
  (read-only, Fakten ohne Meinung) → **Rat** (Code wägt ab, darf
  widersprechen, „nichts bauen" ist valide) → **Entscheidung** (Easy allein,
  Trading-Wert-Filter). KI macht Mechanik, Mensch macht Bedeutung.
- **Wächter teilt das Failure-Fate des Überwachten (26.05.):** Der
  Health-Check-Digest läuft im **selben** GitHub-Actions-Umfeld wie die
  Pipeline. Beim Abuse-Lock 26.05. starb der 8:47-Digest-Cron mit allem
  anderen (git fetch 403) → kein Health-Push den ganzen Tag; die Sperre fiel
  **nicht durch den Wächter** auf, sondern durch manuellen Blick in die
  Actions-UI. Kernproblem: ein Monitoring, das **mit** dem überwachten System
  zusammen ausfällt, hat einen blinden Fleck — bei Account-/Infra-Ausfall
  schweigt der Wächter mit, statt zu alarmieren. Gegen das Premium-Ziel die
  relevante Lücke: **Wer überwacht, ob der Überwacher lebt?** → Roadmap-Kandidat
  „Externer Dead-Man-Switch" in Sektion 5.
- **Steigender Health-Check-WARN ≠ automatisch echter Bug (27.05.):** S10
  return_5d stieg 21%→38% über 6 Runs — sah nach eskalierendem Problem aus,
  war aber Holiday-Überzählung + Lock-Gap, Fill voll funktionsfähig. Lehre:
  bei steigendem WARN erst die **Mechanik** prüfen (läuft der Fill? holt er
  nach?), bevor „eskaliert = kaputt" geschlossen wird. Eine **falsifizierbare
  Vorhersage** (Quote fällt bis Do/Fr) trennt Nachlauf von echtem Defekt
  sauberer als Bauchgefühl.

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

Externe Bewertung des Setup-Scores gegen akademische Literatur + kommerzielle
Scanner + eigene Daten. **Read-only, KEINE Score-Änderung. Reine
Bestandsaufnahme + Bestätigung der Entry-Modul-Strategie. Stand `main @ c1ec26d`.**

### Kern-Erkenntnis (empirisch belegt, nicht nur Literatur)

Der Setup-Score lädt **WITHIN-RUN ≈ 0** auf den Forward-Return (Spearman
ALL 10d **−0.01 n.s.**). Er ist **KEIN Return-Prädiktor, sondern ein
DISPERSIONS-/DISPOSITIONS-Selektor.** Tail-Check beweist: hohe Scores liefern
fettere Tails in **BEIDE** Richtungen, mit leichter Schlagseite zum **LINKEN**
Tail (große Verlierer sitzen eher noch höher im Score als große Gewinner —
bootstrap **74 % vs 59 %** in oberer Score-Hälfte). Das ist exakt die
**„Pulverfass-Detektor, kein Zündungs-Detektor"-These — jetzt an echten Daten belegt.**

### Vorzeichen-Test (return_10d, within-run-Perzentil = inflations-robust)

Datenquelle: `backtest_history.json` (1577 Einträge). **ZWEI Populationen:**
- **bootstrap n=1012** (Backfill, ROHER `score()` ohne Pipeline) — größer,
  robuster, misst aber ANDEREN Score als live.
- **live n=565** (`source=none`, volle Pipeline = angezeigter Score) — nur
  ~14 Runs / 1 Monat.

Score-Aggregat: bootstrap **−0.070** (p .04) / live **+0.116** (p .02) →
**GEGENLÄUFIG**. Globale neg. Ladung (−0.08 signifikant) verschwindet
within-run fast komplett → war überwiegend **BETWEEN-RUN-ARTEFAKT**
(Score-Inflation), kein Querschnitts-Signal.

### Faktor-Ebene (Literatur-Test, within-run 10d)

| Faktor | bootstrap | live | Literatur erwartet |
|---|---|---|---|
| short_float | −0.03 | −0.01 (beide ≈0, n.s.) | stark negativ |
| DTC | −0.05 | **+0.187 (p .0002)** ← entgegen Literatur | stark negativ |
| rvol | **−0.085 (p .01)** | +0.094 (p .06) ← widersprüchlich | (nicht Teil der These) |

→ Literatur erwartet SF + DTC **stark negativ**. In den Daten **NICHT belegt.**
**GRUND = RANGE-RESTRICTION:** Hard-Filter SF ≥ 15 % schneidet das Sample auf
die hochgeshortete Cohorte. Die akademische „mehr SI = schlechter"-Beziehung
gilt über den BREITMARKT (Apple bis Meme); innerhalb der oberen SI-Region ist
die Steigung weg. **Kein Widerspruch zur Literatur — Literatur auf
abgeschnittenen Bereich angewandt.**

### Base-Rate (hart)

Typischer Kandidat **VERLIERT** über 10d: Median live **−3.85 %** / bootstrap
**−2.05 %**. Positive Mean (live +0.61) kommt AUSSCHLIESSLICH aus dem rechten
Tail (max **+1007 %**). Ohne Entry-Timing = Handel einer **negativen
Erwartung** mit seltenen Knallern. Monster-Winner (≥ +25 %) sitzen nur im
**55.–60. Score-Perzentil** → Score trennt den rechten Tail NICHT. Genau das
muss das Entry-Modul leisten.

### Literatur-Stand (Quellen, für spätere Referenz)

1. **Short-Interest → Returns:** ~25 Jahre einhellig NEGATIV im Breitmarkt
   (Senchack/Starks 1993, Desai 2002, Asquith 2005, Boehmer 2008, Diether 2009).
   Short-Seller = informierte Trader.
2. **DTC stärkster Einzel-Prädiktor:** Hong (NBER) „DTC stärkerer Prädiktor
   schlechter Returns als Short-Ratio". Boehmer global (38 Länder): DTC +
   Utilization robusteste Vorhersagekraft über 5–60 Tage.
3. **Squeeze-Wahrscheinlichkeit (≠ Return):** SI/Float/Turnover laden POSITIV
   auf Squeeze-Likelihood. Trennung Squeeze-Disposition (positiv) vs.
   erwarteter Return (negativ) ist DER Schlüssel — Literatur trennt sauber,
   Setup-Score vermischte beides.
4. **Utilization** (% verfügbarer Aktien verliehen) = laut Studie „einziger
   bester Prädiktor von Squeezes". **FEHLT im Score komplett.** Datenseitig
   schwer (kein freier Feed), aber konzeptionell wichtigste fehlende Variable.
5. **Cost-to-Borrow:** Praktiker-Konsens „besserer Squeeze-Indikator als
   SI-Ratio". Alle großen Scanner (Fintel/Ortex) gewichten zentral. Bei UNS
   nur display-only im Katalysator-Sub-Score (> 50 %:8 / > 100 %:15),
   **NICHT in autoritativem `score()`.**
6. **RVOL richtungs-AMBIG:** einerseits High-Volume-Return-Premium (positiv),
   andererseits Erschöpfungs-/Reversal-Signal (Blow-off-Top, negativ über
   2/5/20d). RVOL als pauschal +23-Pkt-Faktor ohne Richtungs-Kontext
   überschätzt das Signal.
7. **Kommerzielle Scanner** (Fintel/Ortex/ShortSqueeze): alle Multi-Faktor
   0–100, aber (a) RELATIV/perzentil („50 = Durchschnitt, relativ zu Peers")
   statt absolut → immun gegen Inflation, (b) Borrow-Fee zentral gewichtet,
   (c) als „Risiko/Wahrscheinlichkeit" geframt, nicht „Einstieg". **Bestätigt
   Setup/Entry-Trennung.**

### Handlungs-Konsequenz: KEINE Score-Umgewichtung

Begründung: (1) Kein Faktor mit robustem konsistentem Vorzeichen — DTC +0.19
von EINEM +1006 %-Ausreißer in 14 Runs getrieben, umgewichten =
Ausreißer-Overfit. (2) bootstrap/live messen verschiedene Scores. (3)
within-run ≈ 0 + symmetrische Tail-Anreicherung **BESTÄTIGT** das Design
statt es zu widerlegen.

### 3 fundierte Strategie-Anker (jetzt empirisch, nicht nur plausibel)

- **A. Entry-Modul = einziger Hebel.** Edge liegt NICHT im Setup-Level
  (Monster nur 55.–60. Perzentil). Stärkste mögliche Bestätigung des
  10.06.-Vorhabens.
- **B. Score-Inflation real + groß** (neg. Ladung verschwindet within-run) →
  perzentil-/relativer Score (Roadmap-Idee + γ-Thema) ist strukturell richtig
  UND Scanner-Industriestandard, nicht nur Option.
- **C. Negative Median-Base-Rate einkalkulieren** → harte Version der
  „wenige Trades, Conviction kein Solo-Signal"-Disziplin.

### Re-Prüfpunkte 30.06. (an AUC-Checkpoint)

- (i) Faktor-Vorzeichen mit ≥ 5–6 Wochen live OHNE +1006 %-Ausreißer
  (winsorized / Median).
- (ii) Wird `rvol` auch live robust negativ? (dann echter Kandidat — aber
  rvol = Timing, nicht das SF/DTC-Literatur-Argument).
- (iii) Trennt das Entry-Modul den rechten Tail, den der Score allein nicht fasst?
- **ROADMAP-KANDIDATEN (kein Druck, nach Entry-Start):** **Borrow-Fee +
  Utilization** vom display-only in autoritativen `score()` (laut Literatur
  die 2 stärksten Squeeze-Prädiktoren, bei uns kosmetisch bzw. fehlend). Erst
  nach Entry-Modul + sauberer 30.06.-Datenbasis bewerten.

### Lehre (methodisch)

Literatur-Faktor-Vorzeichen gelten für den Breitmarkt. Bei vorgefiltertem
Universe (SF ≥ 15 %) **Range-Restriction beachten** — Breitmarkt-Edges können
innerhalb der gefilterten Cohorte verschwinden. **Eigene Daten schlagen
Literatur-Analogie.**
