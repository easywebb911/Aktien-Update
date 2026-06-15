# SESSION_HANDOVER.md — Stand 13.06.2026

## 1) HEUTE IMPLEMENTIERT (mit Hashes)
*(Session 10.–13.06. Hashes aus `git log` auf main, verifiziert. Roter Faden:
erst die letzte Sicherheits-Lücke schließen (XSS), dann zwei Edge-SAMMEL-
Pendants scharfschalten (Vintage-Guard, Exit-Shadow) + KI-Edge-Felder additiv;
dann die Off-Schedule-WURZEL schließen (#357 Redeploy), die `.jsonl`-Resolver-
Lücke + Cron-Doku-Drift bereinigen, und das Entry-Modul mit der Cockpit-Caption
sichtbar abschließen — alles Shadow/Schutz/Hygiene, KEIN Live-Score-/Push-Effekt.)*

- **#343 (feat `db4e720`, Merge `ed6806f`) — 10.06.** **★ XSS-Härtung C1+M2.**
  Stored-XSS im News-Render + `company`/`sector`-Feldern: `_escH`-Escaping (inkl.
  Anführungszeichen, Attribut-Kontext) + `n.link`-Whitelist `^https?://`
  (Escaping allein stoppt `javascript:` NICHT). Damit ist der **einzige Pfad zu
  echtem Konto-/Token-Schaden** (XSS → sessionStorage-PAT) dicht. Frontend-
  Security, manueller Merge + Guardian.
- **#346 (feat `c0d0874` + refactor `0683567`, Merge `422be31`) — 10.06.**
  **★ Vintage-Guard M1 LIVE.** β+-Gate in `_append_backtest_entries` — Backtest-
  Append NUR wenn `bar_date == report_date` (date-Objekt-Vergleich) UND
  `now_et >= 16:00 ET`. Skippt Pre-Open-Runs (Bar=Vortag), Feiertage (Bar=Vortag,
  OHNE Python-Feiertagsliste — datengetrieben), Intraday-only-Tage (now<16:00).
  Schützt jedes KÜNFTIGE Edge-Sample vor der Freitag-Cluster-Verseuchung (52 %
  stale-Rate unter recurring Tickern). Skip kehrt VOR existing_keys-Belegung
  zurück → späterer Post-Close-Run appended frisch. Missing bar_date → APPEND
  (konservativ, kein stiller Datenverlust). bar_date in-memory (kein Schema-Bump).
  Skip-Beobachtung in `vintage_guard_log.jsonl` (eigene Datei, digest-frei).
  Guardian ✅, 78/78 Runner, 18/18 Boundary-Mock. Manueller Merge.
- **#350 (feat `e7a3ed1`, Merge `0066277`) — 11.06.** **★ Exit-Shadow-Log LIVE.**
  `exit_shadow_log.jsonl` sammelt pro Handelstag pro offener Position den
  `exit_state` (`exit_pressure` + 6 Trigger-Sub-Scores + peaks + `signal_price`)
  + Forward-Return-Backfill (`forward_3d/5d/10d`). Validierungs-Pendant zum
  Entry-Shadow (#336) — bisher liefen Exit-Trigger live (Pushes) OHNE Edge-Messung.
  Hook NUR im Daily-Run `_build_phase2` (gen:15273, exit_state wird dort einmal
  berechnet; ki_agent liest nur). **GATE:** nur postclose + `now_et>=16:00 ET`
  (nicht-finale Preise raus). **RE-WRITE by (ticker,date)**, kein Append.
  **Backfill:** Reuse `_close_at` (settled re-fetch → vintage-/auto_adjust-immun),
  **ABBRUCH-BEDINGUNG** (`forward_10d` gesetzt → fertig, nie wieder anfassen →
  skaliert). **KONVENTION: NEGATIVER `forward_Nd` = GUTES Exit-Signal** (Kurs
  fiel nach Warnung). Null Live-Effekt, eigene Datei, kein Schema/S10/Push/
  Ratchet-Touch. Guardian ✅, 79/79, 35/35 Boundary. Manueller Merge.
- **#353 (feat `e62b118`, Merge `1e41d78`) — 11.06.** **★ Backtest-Felder
  monster_score + ki_signal_score (additiv, v4).** Zwei additive Felder im
  Return-Dict von `_build_backtest_extension` (`backtest_history.py`), aus
  `s.get(...)` gelesen, **leer-tolerant** (None): `monster_score` (KI-×1.20/×0.80-
  Transform des Setup, `apply_monster_score`) fehlt auf Alt-Einträgen vor diesem
  PR; `ki_signal_score` (roher ki_agent-Score, `apply_agent_boost`) ist None ohne
  agent_signals-Eintrag. **`backtest_schema_version` BLEIBT 4** (S10-Loader
  filtert hart ==4 — kein Bump). `expected_keys` in `_test_extended_schema`
  **atomar** mitgepflegt (#329-Tripwire) + None-Asserts + Non-None-Passthrough.
  `S10_OBSERVED_FIELDS` ergänzt (OBSERVED/optional, KEIN MUSS-/LAG-Check). Zweck:
  30.06.-Auswertung des KI-/Monster-Edge ermöglichen. KEIN Score-/Filter-/Push-/
  Anzeige-Effekt. Golden byte-identisch, 79/79, Guardian ✅. Manueller Merge.
- **#355 — 11.06.** **★ S4-Zeit-Gate (16:00 ET).** S4 („backtest_history-Eintrag
  fehlt") feuerte vormittags fälschlich `warn` — alte Annahme „postclose-Run ⇒
  Eintrag da", seit Vintage-Guard #346 falsch (Append vor 16:00 ET legitim
  geskippt; ausgelöst von Pre-Open-Runs mit `run_phase=postclose` um 00:09/01:53
  ET). Fix: S4 erwartet den heutigen Eintrag erst wenn `now_et >= report_date@16:00
  ET` (zoneinfo, DST-korrekt) — **SYMMETRIE zum Vintage-Guard-Producer-Gate**.
  **Zähne erhalten:** nach 16:00 ET feuert S4 weiter bei Append-Crash UND
  Bar-Lag-Skip (liest NICHT `vintage_guard_log` — der Bar-Lag-Skip soll sichtbar
  bleiben, §3-Verify-Signal). Wochenend-Gate nur ergänzt (OR). `today_iso`
  unparsbar → konservativ S4 feuert. `severity` bleibt `warn`, kein
  Score-/Push-/Render-Touch. `now_utc` war im Evaluator schon vorhanden (keine
  neue Plumbing). Guardian ✅, 40/40 health_check, 79/79 CI-Gate. Manueller Merge.
- **#357 — 11.06.** **★★ WURZEL-FIX: Redeploy-Auto-Trigger entfernt.**
  `redeploy-on-source-change.yml` (#194/#196) dispatchte bei **jedem** Code-Merge
  auf `main` einen **vollen** `daily-squeeze-report.yml`-Run (Fetch+Score+**Pushes**+
  score_history-Write+ki_agent-Trigger) statt nur `index.html` zu deployen — die
  **gemeinsame Wurzel** (Easy-Verify Actions-Log) von Pre-Open-Pushes auf nicht-
  finalen Daten, S3-/S4-Fehlalarmen, Freitag-Cluster-Kontamination und score_history-
  Churn. **Fix:** `on: push` → `on: workflow_dispatch` (nur manuell), **reversibel**
  (push-Block auskommentiert, Run-Logik erhalten — nicht gelöscht, falls später
  Render-Only). Render-Only-Alternative verworfen (kein vollständiger committeter
  Render-Input; ki_agent-Trigger sitzt workflow-seitig). **Scope strikt:**
  `daily-squeeze-report.yml` (2 Crons + dispatch) + `ki_agent.yml` UNBERÜHRT (leerer
  Diff); kein Python-/Render-/Score-/Push-Touch. **Rest-Kante** (kein Defekt):
  Recalculate-Button dispatcht weiter direkt (gen:9559/10575) — bewusste Einzelaktion,
  s. §6-b. Guardian ✅, 79/79 CI-Gate, Golden byte-identisch. Manueller Merge.
- **#359 (Merge `76e13f5`) — 12.06.** **★ `.jsonl`-Resolver-Lücke geschlossen
  (union).** `.gitattributes merge=union` für die **5 PURE Append-Logs**
  (`score_inflation_log`, `health_check_log`, `provider_health`,
  `finra_history_health`, `vintage_guard_log` — alle `open(...,"a")`) → Rebase-
  Append-Konflikte lösen ohne Daily-Run-Abort, beide Zeilen erhalten (`git rebase`
  respektiert den Driver — empirisch belegt). **`exit_shadow_log.jsonl` BEWUSST
  AUSGENOMMEN** (Full-Rewrite + Re-Write-by-(ticker,date) + Backfill → union
  erzeugte Duplikat-Keys, empirisch belegt). Guard-Test `mock_test_gitattributes_
  union_merge` (Kat. A), CI-Gate **79→80**. Self-merge. Details + Korrektur der
  „stiller-Verlust"-Annahme: §6 + §8.
- **#362 (feat `4be6aa3`, Merge `49c28d3`) — 12.–13.06.** **★ Cockpit-Entry-
  Shadow-Caption LIVE** (live-verifiziert iPhone). Dezente Caption unter
  `cockpit-body`: „Entry-Shadow {score} · {n}/5 Komp. · unvalidiert bis 30.06.".
  **Ansatz (A) client-side, REIN ADDITIV:** Server rendert nur leeren `hidden`
  Hook `.cockpit-entry-shadow[data-es-ticker]`; JS füllt aus `window._BT_DATA`
  (latest Entry/Ticker, DD.MM.YYYY-chronologisch), **nur wenn `entry_score`
  not-None** (0 IST ein Wert), sonst Element entfernt. Preload schreibt in den
  BESTEHENDEN `_BT_DATA`-Cache (kein Doppel-Fetch). `backtest_history.py` (#336)
  unberührt; Drawer-Strip übersteht der Hook (nur `id=`-Strip). Damit ist das
  Entry-Modul vom Shadow-Daten-Sammeln bis zur (unvalidierten) Anzeige komplett.
  Guardian ✅, CI 80/80, Golden mit-committet (nur Hook+JS, body-only). Manueller
  Merge + iPhone-Verify.
- **Doku-PRs (11.–13.06.):** #358 (`46bf50a`, #357-Wurzel-Fix-Handover), #360
  (`2b85698`) + #361 (`dbd3ae1`) — **Cron-Doku-Drift `17 10`→`17 6` vollständig
  bereinigt** (CLAUDE.md + `resolve_run_phase.py`-Docstring + Test-Daten; repo-weit
  kein `17 10` mehr, verifiziert). Inhalte in §3–§8 eingearbeitet.
- **Doku-Konsolidierungs-PRs (10.–11.06.):** #344 (Security-Strang/Audit 09.06.),
  #345 (M3-Entscheidung PAT classic), #347 (Vintage-Guard + score_delta), #348
  (S3/S7-Merge-Tag-Erklärung), #349 (DBI-8.88 aufgelöst + trend_break-Rest-Kante),
  #351 (Exit-Shadow-Notizen), #352 (Edge-Programm-Roadmap). **Inhalte sind in
  §3–§8 eingearbeitet** — keine separate Aufzählung mehr nötig.
- **Vorherige Session (06.–07.06., NICHT erneut gelistet):** CI-Gate #329–#335
  (Schema-Tripwire, stale-Reds, Golden-Liveness-Stub, tier2-AST, Allowlist-Runner)
  + Kern-Meilenstein **Entry-Score Shadow #336**. Durable Anker leben in §6/§7.

## 2) AKTIVE POSITIONEN
**Quelle: `app_data.json`-Positions-Mirror (`run_phase=postclose`, `generated
2026-06-13T18:44Z`) — der private Gist (kanonisch) ist im Sandbox NICHT direkt
lesbar (kein `GIST_ID`/`GIST_TOKEN`). Stand = letzte Daily-Run-Materialisierung
→ bei Abweichung Gist gewinnt.** **8 offene Positionen** — unverändert seit
09.06., gegengeprüft gegen `exit_shadow_log.jsonl` 12.06. (identische 8 Ticker).
(Historie: vorher 9; CRMD/GEMI/LFVN geschlossen seit 07.06., LUCK/DBI neu 09.06.):

| Ticker | Entry | Shares | no_exit_alerts | current_price* |
|---|---|---:|---|---|
| **AMC** | 01.05. @ 1.50 | 500 | **True** (Hold) | None |
| **IONQ** | 11.05. @ 49.10 | 40 | False | None |
| **PDYN** | 20.01.2025 @ 11.52 | 150 | False | None |
| **AI** | 01.06. @ 11.00 | 10 | **False** (bewusst) | None |
| **RBOHF** | 03.06. @ 0.67 | 1300 | False | 0.216 |
| **GIII** | 05.06. @ 33.71 | 4 | False | None |
| **LUCK** | 09.06. @ 8.07 | 10 | False | None |
| **DBI** | 09.06. @ 7.41 | 10 | False | None |

\* `current_price` = **Stand letzter Run**; meist `None` (S3-Merge-Tag-Muster,
§8 — yfinance gesund, Exit-Logik pausiert sauber bei None). NICHT als Ausfall
interpretieren.

**AI:** Exit-Pushes bewusst akzeptiert (Hold-These Siebel, kein `no_exit_alerts`-
Flag) — kein To-do. Nur AMC trägt das Hold-Flag. **DBI:** 8.88-Strang vollständig
aufgelöst (§8) — P&L korrekt (User-roh 7.41), kein Defekt.

## 3) VERIFIKATION (nächster Handelstag + dated Termine)
*(08.06.-Verifies ERLEDIGT: erster Entry-Score live + FINRA-SSR-Recovery +
Wochenend-Digest-Selbstheilung bestätigt — entfallen.)*

- **✅ ERLEDIGT — #357 Redeploy-Auto-Trigger BESTANDEN (13.06.):** Beleg = #362
  (eine `generate_report.py`-Änderung) wurde gemergt und löste **KEINEN**
  automatischen Daily-Run aus — die deployte `index.html` blieb auf dem letzten
  Cron-Stand (Diagnose 12.06.: erst der reguläre Post-Close regeneriert sie). Der
  Auto-Pfad ist tot; nur der manuelle Dispatch/Recalculate triggert noch. Verify
  geschlossen. (Bewusste Konsequenz: UI-/Template-Änderungen werden erst beim
  nächsten Cron oder manuellem Dispatch sichtbar — kein Defekt, der #357-Trade-off.)
- **✅ ERLEDIGT — Exit-Shadow Datei-Commit (Tag 1+2 sauber):** `exit_shadow_log.jsonl`
  committet vom Post-Close `a9c07ac` (11.06. 21:12Z, 8 Records) UND fortgeschrieben
  `2956849` (12.06. 22:50Z, +8 Records 12.06.); 11.06-Records via Re-Write-by-
  (ticker,date) **unverändert** erhalten, `exit_state`+6 Trigger+signal_price gefüllt.
  **OFFEN (einziger noch nie belegter Pfad) → ~16.06.:** füllt der ki_agent-Backfill
  die `forward_3d` auf den 11.06-Records? (11.06 + 3 Handelstage ≈ 16.06; Backfill
  bisher 0× gelaufen). **NEBENBEI ab ~16.06.:** geht der Daily-Run je rot mit
  „Konflikt in nicht-JSON-Dateien" + `exit_shadow_log.jsonl`? (ab Backfill-Start
  wird ki_agent 2. exit_shadow-Schreiber = erste reale Konflikt-Chance). Bleibt es
  ruhig → der Merge-Strang ist endgültig erledigt (s. §6: key-aware-Driver verworfen).
- **✅ GEPRÜFT 13.06 — Vintage-Guard-Log sauber:** nur **2 Skips, beide `pre_open`**
  (11.06. 04:09Z/05:53Z = 00:09/01:53 ET) — KEIN ~22:xx-UTC-Bar-Lag-False-Skip. Die
  12.06-Post-Close-Läufe (20:52/22:50Z, post-16:00 ET) appendeten korrekt
  (backtest_history 12.06=10). Seit #357 keine NEUEN Skips (Pre-Open-Dispatch-Quelle
  versiegt). **Nächster Watch:** identisch zum exit_shadow-Konflikt-Watch ab ~16.06.
- **★ FINRA-History-Sample (~23.06., `finra_history_health.jsonl`, digest-frei):**
  14–30 d Sample für evidenzbasierte Wächter-Schwelle des Daily-Run-FINRA-History-
  Fetch (speist `si_trend_5d_slope`, bislang UNMONITORED). **ACHTUNG: `coverage_pct`
  ist in PROZENT gespeichert**, nicht als 0–1-Bruch — nicht um Faktor 100 verrechnen.
- **★★ Backtest-Hauptauswertung — AN `return_10d`-REIFE GEKOPPELT, NICHT ans Datum
  (realistisch eher Anfang Juli als 30.06. punktgenau):** Setup-≥70-Edge im
  **DOPPEL-LAUF** (Cluster) · Entry-Shadow-Komponenten · KI-/monster-Edge (#353) ·
  Conviction-Methodik · Earliness-Re-Test. **Cap-Nachschärfung = EDGE-TEST**
  (Forward-Return am-Cap vs unter-Cap), NICHT nur Verteilung (s. §4). Qualität vor
  Pünktlichkeit: viele Komponenten-Träger sind erst seit 06.–12.06. → `return_10d`
  teils noch unreif bis ~Ende Juni.

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)
- **✅ Cockpit-Entry-Shadow-Caption ERLEDIGT (#362, 12.–13.06., §1/§7):** die
  Anzeige (display-only, Label „unvalidiert bis 30.06.") ist live. **Wichtige
  Abgrenzung:** das ist NUR die *Anzeige* des Shadow-Werts — die **LIVE-
  Scharfschaltung** des Entry-Scores (als Push-/Trade-Signal) bleibt weiterhin
  gated bis nach dem 30.06.-Readout. Anzeige ≠ Aktivierung.
- **30.06. — Backtest-Auswertung (erweitert):**
  - Setup-Score ≥70-Edge (schema_v4) · Earliness-Konfidenz-Re-Test (AUC) ·
    Conviction-Methodik-Diagnose · **NEU: KI-/monster-Edge** (`monster_score` /
    `ki_signal_score` seit #353) · **Entry-Shadow-Auswertung** (treffen dünne
    Scores schlechter via `entry_n_components`? Ausfall-Tage via
    `push_history_available=False` filtern) → DANN Push-/Live-Entscheidung.
    **Präzisierung Zielgröße (Gutachten 15.06.):** Entry-Score primär gegen
    **BEWEGUNGS-GESCHWINDIGKEIT** validieren — 1T/2T-Max-Return + Zeit-bis-+10 % —
    **NICHT** gegen 10-Tage-Return. Begründung: misst der Entry-Score kurzfristige
    Beschleunigung, würde ein Test gegen 10D-Return ihn systematisch benachteiligen
    (falsche Falsifizierung). Keine neue Komplexität, nur die korrekte Zielgröße
    eines ohnehin geplanten Tests (kohärent neben dem `entry_n_components`-Check).
  - **Entry-Cap-Trockenlauf (13.06., read-only, NICHT gebaut — Methode validiert):**
    Rohverteilung + Cap-/Clamp-Anschlag der 5 echten `compute_entry_score`-Inputs
    gegen `backtest_history.json` (Twins genutzt: `score_delta_t1_raw`,
    `anomaly_push_age_h`). Befund: **nur `score_delta` (±15-Clamp) cap-verdächtig**
    (13–17 % \|raw\|>15, höchste bindende Rate); `uoa` (3 % ≥4.0 — großzügig),
    `rvol_buildup` (8.5 % ≥6.0 — clippt sinnvoll den 154er-Tail), `si_slope` (Buckets
    gleichmäßig ~18–23 %) **solide**; `anomaly` (28 % Floor >72h) **n≈39 zu dünn**.
    **KEY-METHODE für den echten Lauf:** Anschlag-Rate allein sagt NICHT „Cap falsch"
    → der eigentliche Schritt ist der **EDGE-TEST** (haben am-Cap-Einträge andere
    `return_10d` als unter-Cap? Mann-Whitney) — braucht `return_10d`-Reife. `si_slope`
    NIE roh skalieren (max 10 200 → Bucketing zwingend). **Verteilungs-Wächter-Modul
    VERWORFEN (13.06.):** die Rohdaten + Twins sind bereits persistiert → einmalige
    read-only-Auswertung statt periodischem Wächter (Daten da, kein Sammel-Bedarf;
    Nordstern: Mensch validiert Bedeutung einmal). Über-Engineering vermieden.
  - **Freitag-Cluster-Kontamination (Diagnose 09.06.):** 37,5 % der ≥70-Einträge
    tragen Score mit ~1-Tag-Daten-Versatz (Pre-Open-Re-Run friert Vortags-Bar ein;
    Signatur = `entry_price` exakt == Vortags-`entry_price` desselben Tickers).
    **PFLICHT für 30.06.:** ≥70-Edge im **DOPPEL-LAUF** rechnen — mit UND ohne die
    detektierbaren Cluster-Einträge. Hält die Edge in beiden → robust, Caveat
    reicht. Kippt sie → Edge-Schluss **VERTAGEN, NICHT filtern** (40 % Erstauftritte
    sind uncheckbar = nicht reparierbarer blinder Fleck). `entry_price` selbst ist
    nur Diagnose-Tabelle (Returns nutzen `_close_at(0)`, geschützt); der **Score**
    ist das Problem (datumstreue Auswertungs-Eingabe). Vintage-Guard M1 (#346)
    schützt nur KÜNFTIGE Samples, NICHT das eingebackene 30.06.-Sample.
  - **Quellen-Präzisierung (09.06.):** datumstreuer Score-Konsum läuft über
    `health_check.py:619` (S13-≥70-Edge) + bt-Panel-Buckets. KEIN Source-Fix
    rettet das eingebackene Sample — nur der Doppel-Lauf zählt.
  - **si_trend-slope uncapped (FIP 08.06. = 521.84):** falls die 30.06.-Auswertung
    rohen slope statt Bucket nutzt → Ausreißer-Risiko (Division-durch-klein,
    unbegrenzt). Entry-INPUT selbst ist gecappt (Bucket-Edges) → kein
    Verzerrungsrisiko im entry_score. score_delta_t1 ist NICHT betroffen
    (strukturell ±100-gebunden, Caveat geklärt 10.06., s. §8).
  - FDA-Move-Muster (Wiedervorlage 08.05.).
- **Exit-Shadow-Auswertung ~Ende Juli (nach 30.06.-Entry-Readout):** pro Trigger
  die `forward_Nd`-Verteilung nach Fires — feuert ein Trigger chronisch falsch
  (positiver forward = Kurs stieg trotz Verkaufs-Warnung)? **Konkreter Verdacht:
  trend_break** — 00:57-Massen-Fire 11.06. (IONQ/PDYN/RBOHF/DBI gleichzeitig) +
  08.06. PDYN+IONQ drehten nach Signal hoch. Auswertung via `GROUP BY
  (date,trigger)`. **SAMPLE-CAVEAT:** nur ~8 offene Positionen → dünn + hoch
  autokorreliert, ~150 Records bis Ende Juli, LOW-POWER. KEIN robuster AUC (wie
  Setup n~1200), nur qualitativer Erstblick (Wächter-Block-Lehre 04.06.). Falls
  ein Trigger nachweislich Rauschen → aus Push-Pipeline nehmen.
- **FINRA-History-Wächter (nach ~23.06.-Sample):** evidenzbasierte Schwelle für
  `finra_history_health.jsonl` setzen (graceful `None` bei FINRA-Tod; kein Blocker).
  Offen separat: Stale-Cache-Frische.

## 5) STRATEGISCHE ROADMAP
- **Nordstern unverändert:** Maschine prüft Mechanik, Mensch validiert Bedeutung.
- **Trading-Wert-Disziplin auf BLÖCKE, nicht nur Tasks:** vor jedem Arbeitsblock
  fragen „berührt das Trading/Edge?". Die CI-Gate-Kette (#329–#335) war teils
  Verzettelung (Engineering-Selbstzweck) — wertvoll fürs Suite-Vertrauen, aber
  kein direkter Edge. Filter auf ganze Ketten anwenden.
- **Entry-/Exit-/KI-Module jetzt im Shadow → Daten sammeln, DANN erst Push-/Live-
  Entscheidung.** Kein vorzeitiges Scharfschalten.
- **Annahmen-Inventur (Runde 1) abgeschlossen:** #1 Gist-Body (#322) ✅, #2
  Screener-Pool (#325) ✅, #3 FINRA/DTC (Wächter optional, s. §4), #4 RVOL-Phasen
  = γ-2 (blockiert).
- γ-2 RVOL-Normalisierung (★, BLOCKIERT): **4 Vorbedingungen offen** — premarket-
  Daten dünn · Cron-Drift #295 · `rel_volume_raw` ungebaut · Skalierer ungestützt.
  **KRITISCH bei Aktivierung (sicherheitskritisch, wortgetreu):** in
  `CONSISTENCY_EXPECTED_STATE` BEIDE Soll **paaren** — `EXPECTED_RVOL_NORMALIZATION→True`
  **UND** `SCORE_NORM_VERSION→2`; wird nur EINES geflippt → **S13-Drift**.
  **Reihenfolge:** Daten → Sweep → `rel_volume_raw` → Schwellen → Flip. #298
  überwacht `RVOL_NORM_ENABLED` / `SCORE_NORM_VERSION` / `EARLINESS_FORMULA_VERSION`.
- Externer Dead-Man-Switch (Cloudflare-Worker) gegen Cron-Drops (~20 %).
- Borrow-Fee + Utilization in score() (bei reifer CTB-Coverage).

### EDGE-VALIDIERUNGS-PROGRAMM (Stand 13.06.)
**Leitprinzip:** jedes Signal, das eine Entscheidung beeinflusst, braucht eine
Edge-Messung, BEVOR ihm vertraut wird. **REIHENFOLGE-DISZIPLIN:** immer erst
sammeln → auswerten → DANN nächsten Strang öffnen. NICHT parallel starten.

**Abgedeckt/laufend:**
- **Setup-Score ≥70:** Entry-Backtest, Readout 30.06. (Doppel-Lauf wg. Cluster).
- **Entry-Score-Komponenten:** Shadow seit #336 (07.06.), Auswertung 30.06.
- **Exit-Trigger:** Shadow seit #350 (11.06.), Auswertung ~Ende Juli.
- **KI-/Monster-Edge:** Backtest-Felder seit #353 (11.06.) — `monster_score`
  (KI-Transform) + `ki_signal_score` (roh). **Im 30.06.-Haupt-Run mitprüfbar**
  (kein eigener Strang nötig, die Felder hängen am bestehenden Backtest-Sample).
  Frage: trägt der KI-Pfad eigenständigen Edge über den Setup-Score hinaus?

**Offene Edge-Kandidaten (ERST NACH 30.06.-Entry-Readout — NICHT jetzt starten):**
1. **Conviction-Score (stärkster Kandidat):** Gewichte 33/28/28/11 unvalidiert,
   wird bewusst nur per Chart+Instinkt genutzt. Gleiche Lücke wie Exit vor #350 —
   angezeigter Score beeinflusst Wahrnehmung, Edge nie gemessen. Frage: sagt hoher
   Conviction bessere Forward-Returns voraus? Steht als 30.06.-Methodik-
   Wiedervorlage; ggf. eigener Shadow-Strang DANACH (analog Exit-Shadow: sammeln →
   forward-return-paaren → Verteilung je Conviction-Level).
2. **Push-Auslösung selbst:** ob die Push-SEVERITY-Tiers/Auslöse-Schwellen lohnen —
   sind gepushte Momente besser als ungepushte? Teilweise vom Entry-Shadow erfasst,
   aber die Push-Entscheidung selbst ungemessen. Niedriger als Conviction.

(Earliness-Konfidenz n=78/AUC 0.77: kein neuer Faden — bleibt der Re-Test in der
bestehenden 30.06.-Wiedervorlage, hier nur Querverweis.)

**Bewusst NICHT auf der Liste (Over-Engineering):** einzelne Setup-Sub-Signale
(gap_hold/rs_spy etc.) isoliert validieren — sie sind Bestandteile des Setup-
Scores, dessen Gesamt-Edge ohnehin gemessen wird; kein eigener Entscheidungs-Bezug.

**Nächster Schritt nach 30.06.:** Exit-Shadow ~Ende Juli auswerten, DANN
entscheiden ob Conviction einen eigenen Shadow verdient — mit den Erkenntnissen
aus Entry + Exit + KI/monster. Erst sammeln lassen, was läuft.

### Hebel-Hypothesen H1–H6 (Edge-Auswertung 30.06., ZU PRÜFEN, NICHT Erkenntnis)
**Kanonischer Anker** für die 30.06.-Edge-Auswertung. **Alles Hypothese, kein
Befund** — nicht als gesichertes Ergebnis lesen. (Namespace-Hinweis: dieses
„H1–H6" = **Hebel-Hypothesen**; das „H1 Storage-Redesign" in §6 ist der
**Security-Audit-Namespace** — andere Nummerierung, nicht verwechseln.)

**Ausgangsbefund (roh, vor Bereinigung):** Roher Setup-Score zeigt **KEINE
Trennschärfe** — Trefferquote sinkt mit Score (28 / 29 / 28 / 25 / 23 % für
≥40..≥80, „Nur Live"); ≥70-Mediane alle negativ (3T −1,7 / 5T −1,4 / 10T −1,9;
n=215). Daraus die sechs Hypothesen:

- **H1 — Expectancy statt Trefferquote:** Erwartungswert unter mechanischer
  Cut-Loss/Let-Run-Regel, **netto nach Kosten** — NICHT Anteil ≥+5 %. Fester
  Auswertungsbestandteil. Konvexe Lotterie-Auszahlung sichtbar (<50-Bucket Median
  10T −3,7 % ABER Ø +7,6 %, Range bis +978 %).
  **Schärfung (3. Gutachten 15.06.):** zusätzlich zu Expectancy **SPIKE-TARGETS**
  testen — Anteil mit +20 %/+50 %/+100 % Max-Return je erreicht (ja/nein) +
  Time-to-Peak. Begründung: bei konvexer Auszahlung misst Stichtags-Return (10T)
  die Spitze weg; „Wahrscheinlichkeit eines großen Spikes" erfasst die Konvexität
  direkt. **Unter dieselbe Multiple-Testing-Korrektur stellen wie die übrigen
  Targets** (mehr Targets = mehr Tests, sonst unterläuft es die Korrektur).
- **H2 — Schwanz-Anomalie (Falsifizierungstest):** Hält der fette rechte Schwanz im
  <50-Bucket **nach Cluster-Purge UND nach Entfernen des Top-1-Ausreißers**? JA →
  ernst nehmen (Score rankt Konvexität falsch). NEIN → Artefakt (n=131).
  **Schärfung (2. Gutachten 15.06.):** nicht nur Top-1 entfernen, sondern auch
  **Top-5** — wenn die Edge nach Entfernen der fünf größten Gewinner verschwindet,
  existiert praktisch keine robuste Handelbarkeit (Lotterie-Profil bei n≈250–450).
- **H3 — Exit als eigentliche Edge:** Bei schwachem Entry trägt Exit-Disziplin die
  Rendite. Verknüpft mit der Exit-Mechanik-Spec (Begutachtung C, ~Ende Juli).
- **H4 — Score als Universums-Filter, nicht Prädiktor:** SI-Trend stützt (seitwärts
  36 % schlägt steigend/fallend je 27 %, richtungsblind).
- **H5 — Katalysator-Overlay:** FDA/Earnings bedingen (vgl. 08.05.-Tell). Verknüpft
  mit dem Katalysator-Gating-Vorschlag (Begutachtung C).
- **H6 — Crowded-Trade (Hypothese, NICHT Befund):** inverse Score-Korrelation evtl.
  crowded trade ODER teils Cluster-Artefakt (37,5 % unbereinigt) — **erst nach
  Cluster-Purge entscheiden**, NICHT vorab als Alarmsignal behandeln.

**AUFFANGLINIE (wichtigste Zeile):** Falls keine Netto-Edge → das Tool ist ein
**Risiko-/Monitoring-Instrument, KEIN Alpha-Generator.** Schützt vor Edge-
Schönrechnen. (Positiv lesbar als „Attention-Router" — s. Begutachtungs-Subsektion B.)

### Externe Begutachtung 15.06. — zu prüfende Vorschläge (NICHT Erkenntnis)
**Status:** Vorschläge eines externen Gutachters zum Projektdossier — **dokumentiert,
nicht validiert.** Alle unterliegen der **Vorleistungs-Logik: erst Edge-Validierung,
dann Bau.** Die „H#"-Labels verweisen auf die **Hebel-Hypothesen H1–H6** (Subsektion
direkt oben — gemeinsame Nummerierung). Kein Punkt ist „umzusetzen", bevor der
jeweilige Auslöser greift.

**A) Auswertungs-Methode (zur 30.06.-Hauptauswertung, ergänzend zur Methoden-Härtung):**
- **Bootstrapping (zu 30.06.):** Konfidenzintervalle für den Erwartungswert via
  Ziehen-mit-Zurücklegen aus den Live-Daten (z. B. 10.000 synthetische Verläufe).
  Begründung: bei n≈250–450 + asymmetrischer Verteilung ist ein Punkt-Erwartungswert
  ohne KI wertlos. **Ergänzt** die bestehende Multiple-Testing-/Doppel-Lauf-Härtung
  (§3/§4), ersetzt sie nicht.
- **Fraktionales Kelly (NACH positiver Expectancy):** falls Expectancy nach
  Cluster-/Reife-Bereinigung positiv → Positionsgrößen-Konsequenz gegen Ruin-Risiko
  bei langen Verlustserien (konvexe Auszahlung = hohe Drawdown-Wahrscheinlichkeit).
  **Risk-Management-Schicht, KEIN Signal** — greift erst, wenn überhaupt ein Edge
  belegt ist.

**B) Auffanglinie-Reframe (positiv, deckt sich mit Nordstern):**
- **„Attention-Router":** Falls die 30.06.-Auswertung **kein** systematisches Alpha
  zeigt → das System ist trotzdem ein hochpräziser **Scanner**, der täglich die
  wenigen Kandidaten präsentiert, bei denen der Mensch manuell nach Katalysatoren
  sucht. Das **IST eine legitime Edge** (Effizienzgewinn), nicht nur Fallback —
  macht die Auffanglinie positiv statt resignativ (Nordstern: Mensch validiert
  Bedeutung). Reine Deutungs-/Haltungs-Notiz, kein Bau.

**C) Backlog-Vorschläge (NACH Validierung, je eigene Diagnose, kein Druck):**
- **Synthetische Utilization (NACH Validierung):** Composite aus iBorrowDesk —
  Fee-Veränderungsrate (z. B. `Fee_Delta_3d`) × Erschöpfungsrate verfügbarer Aktien
  (× Kehrwert `Shares_Available`). Näher an echter Utilization als FINRA-Flow.
  **BESTÄTIGT + konkretisiert** den bestehenden §5-Backlog-Punkt „Borrow-Fee +
  Utilization in score()" (keine neue Idee, sondern dessen Ausgestaltung). Als neue
  Score-Komponente **edge-validierungspflichtig** (nicht blind einbauen).
- **Katalysator-Gating (↗ H5 Hebel-Hypothesen, NACH Validierung):** Earnings-/FDA-Kalender via Finnhub
  (Key vorhanden) oder Benzinga Free. Leitidee: Setup-Score 60 **mit** Katalysator >
  Score 85 im luftleeren Raum. **WICHTIG:** nur das **Kalender-Gating** automatisieren
  — die Katalysator-**Bewertung** bleibt diskretionär/menschlich (Nordstern).
- **Exit-Mechanik-Spec (↗ H3 Hebel-Hypothesen, Startpunkt ~Ende Juli):** asymmetrische Exit-Logik im
  exit_shadow testen — **Time-Stop** (Exit wenn nach 3 Handelstagen kein Momentum)
  + großzügiger **Trailing-Stop** für Gewinner. Konkreter Startpunkt für die
  Exit-Shadow-Auswertung ~Ende Juli (s. §4 Exit-Shadow-Auswertung).

**D) Bewusst NICHT aufgenommen (abgelehnt mit Begründung):**
- **„Rate-of-Change statt Absolutwerte" als neue Idee** — verworfen: **teils bereits
  umgesetzt** (`score_delta_t1`, `rvol_buildup_5d`, `si_trend_5d_slope` SIND
  Veränderungsraten); der Rest fällt in den **↗ H4-Test** (Hebel-Hypothesen), kein neuer Strang.
- **Inverse Korrelation als gesicherter „Crowded-Trade"-Befund** — verworfen als
  *Befund*: bleibt **Hypothese (↗ H6 Hebel-Hypothesen)**, erst nach Cluster-Purge
  prüfbar — NICHT als gesichert führen.

## 6) CODE-HYGIENE-BACKLOG (Status je Punkt)
- **★ Vintage-Guard M1 ERLEDIGT (#346, 10.06.) — vormals „Option A / Pre-Open-Re-
  Run-Guard" in diesem Backlog, jetzt LIVE (Anker §7).** Restkanten:
  - **(a) M2 After-Hours-Capture = PHANTOM (aufgelöst 10.06., §8):** alle Price-
    Captures laufen `prepost=False` → `iloc[-1]` ist regulärer Session-Close, kein
    After-Hours-Print. **KEIN Fix nötig.** Die frühere 09.06.-Diagnose „M1 + M2
    dieselbe Wurzel → EIN kombinierter Guard" ist damit **gegenstandslos** — M1
    allein deckt den realen Fehlermodus (Pre-Open-Re-Run). After-Hours-P&L
    ohnehin schon erledigt (#338).
  - **(b) Pre-Open-Run-QUELLE — WURZEL GEKLÄRT + AUTOMATISCH GESCHLOSSEN (#357,
    11.06.):** Die Quelle der Off-schedule-`postclose`-Runs ist **belegt** (Easy-
    Verify Actions-Log): `redeploy-on-source-change.yml` (#194/#196) dispatchte bei
    **jedem** Code-Merge auf `main` einen **vollen** `daily-squeeze-report.yml`-Run
    (Fetch+Score+Pushes+score_history+ki_agent) statt nur `index.html` zu deployen;
    `run_phase` war UTC-abgeleitet (`else → postclose`), bei Pre-Open-Merges im
    falschen ET-Fenster. **Das war die gemeinsame Wurzel** der drei Symptome
    (Vintage-Cluster #346, S3-`current_price`-Churn, S4-Vormittags-Fehlalarm #355)
    UND des §8-S3/S7-Merge-Tag-Churns — **dieselbe Quelle**, nicht zwei Klassen
    (frühere „andere Klasse"-Trennung damit überholt). **Fix #357:** `on: push`-Auto-
    Trigger entfernt → `on: workflow_dispatch` (reversibel, push-Block auskommentiert).
    Ein Code-Merge löst **keinen** automatischen Daily-Run mehr aus.
    **REST-KANTE (kein Defekt, optional):** der Frontend-**Recalculate-Button**
    dispatcht den Daily-Run weiterhin **direkt** via GitHub-API (`GH_WORKFLOW=
    'daily-squeeze-report.yml'`, gen:9559/10575) — **bewusste, seltene Einzelaktion**,
    nicht der Auto-Pfad. Ein nächtlicher Tap KÖNNTE noch einen Pre-Open-Run auslösen.
    Optionaler Folge-PR: ein **Zeit-Warn-Gate** im Button (Hinweis bei Pre-Open-
    Dispatch) — **kein Druck**, kein akuter Schaden (Easys Wahl). „Wurzel zu" heißt
    präzise: **automatische Wurzel zu, manuelle Einzelaktion bleibt.**
  - **(c) si_trend-slope uncapped (FIP 521.84):** der EINE echte uncapped-
    Explosions-Punkt, relevant nur falls die 30.06.-Auswertung rohen slope statt
    Bucket nutzt. Optional begleitend **W2** = 14–30 d silent-log der 3 uncapped
    Rohfelder (`si_trend_5d_slope` max 521.84 / `rvol_buildup_5d` max 153.55 /
    `rvol_acceleration` max 135.72).
- **trend_break-Exit-Trigger auto_adjust-Rest-Kante (theoretisch, kein Bau):**
  `_exit_p2_trigger_trend_break` (gen:14726) vergleicht roh `cur_price` vs adjusted
  `ma21` NUR bei **Nicht-top10-Position MIT Corporate Action im EMA21-Fenster
  (~21 Handelstage)** → könnte `exit_pressure` leicht inflationieren (5%-Gewicht).
  Aktuell **keine** Position betroffen (DBI-Strang §8 bestätigt: keine offene
  Position mit Corp-Action zwischen Entry und heute). **Fix-Konflikt:**
  `current_price` dient zwei Konsumenten mit gegensätzlichem Bedarf (trend_break
  will adjusted, Exit-PnL will roh) → **NICHT** global `auto_adjust` flippen; falls
  je nötig, surgisch nur die `ma21`-Quelle im Nicht-top10-Fallback angleichen. Nur
  bauen, wenn Easy-Verify einen frischen Split einer Nicht-top10-Position zeigt.
- **H1 Storage-Redesign (Option d, OFFEN, kein Druck):** echte Privatheit der
  Gist-Daten nur via auth-gated Store statt URL-lesbarem Gist (Privacy-Akzeptanz
  c bewusst getroffen, §7) — optionaler Roadmap-Punkt.
- **M1 CSP-Meta in `head.jinja` (Security, OPTIONAL):** Defense-in-depth gegen
  künftige XSS-Klassen; `connect-src` sorgfältig allowlisten, iPhone-Verify;
  manuell + Guardian. Niedrig — der reale XSS-Pfad ist seit #343 dicht.
- **requests-Stub-PR** (die 3 TEMP-EXCLUDED `entry_score_persistence`,
  `health_check_ntfy_url_pattern`, `ntfy_fail_visibility` `requests`-stubben →
  zurück in ALLOWLIST, Gate **79→82**): **OPTIONAL**, Easy: „nicht dringend, kein
  Trading-Wert". TEMP-Kommentar-Nummer verweist auf „#336" — bei Bau korrigieren.
- **topten_entry_anomaly / watchlist_drawer_live_momentum** (letzte 2 B-Tests,
  lesen echte Repo-Daten) → stubben für gate-tauglich. Niedrig.
- **JSONL-Resolver-Lücke — KORRIGIERTER BEFUND + via union GESCHLOSSEN (12.06.):**
  Der Konflikt-Recovery-Block in `daily-squeeze-report.yml` löst nur `*.json`
  auto auf (`grep '\.json$'` + `--ours`); `*.jsonl` matcht die Regex NICHT →
  ein `.jsonl`-**Rebase-Konflikt** landet im „Nicht-JSON"-Zweig und **bricht den
  GESAMTEN Daily-Run-Push ab** (`rebase --abort; exit 1`, inkl. index.html/app_data/
  backtest). **Korrektur der alten Notiz:** das ist ein **sichtbarer Hard-Abort,
  KEIN stiller Sammelverlust** (empirisch belegt, Diagnose 12.06.) — greift nur
  bei seltenem echtem Konflikt. **Fix:** `.gitattributes merge=union` für die **5
  PURE Append-Logs** (`score_inflation_log`, `health_check_log`, `provider_health`,
  `finra_history_health`, `vintage_guard_log` — alle `open(...,"a")`) → Append-
  Konflikte lösen ohne Abort, beide Zeilen erhalten (`git rebase` respektiert den
  Driver, empirisch belegt). **`exit_shadow_log.jsonl` BEWUSST AUSGENOMMEN:** Full-
  Rewrite (`open(...,"w")`) + Re-Write-by-(ticker,date) + Forward-Backfill → union
  erzeugte Duplikat-Keys (empirisch belegt) → bleibt beim Abort-Verhalten (selten,
  selbstheilend via nächsten Re-Write). Workflow-Resolver-Block unverändert (union
  verhindert, dass die 5 Dateien überhaupt als Konflikt ankommen).
  **Key-aware-Merge-Driver für exit_shadow VERWORFEN (Diagnose 13.06.):** **0 reale
  Konflikte** seit #350 (4 saubere Commits), und der 2. Schreiber (ki_agent-Backfill)
  war **nie aktiv** → das Problem existiert strukturell noch nicht. Custom Driver =
  mittlerer Aufwand + Runner-Config-Fragilität für ein Null-Vorkommen-Problem (Trading-
  Wert-Filter: durchgefallen — Telemetrie, kein Live-Signal, selbstheilend). **FALLS
  je real** (Watch ab ~16.06., wenn Backfill anläuft): die richtige Antwort ist die
  bestehende **`--ours`-Auto-Resolve um exit_shadow erweitern (~1 Zeile)** — union ging
  wegen Re-Write-Duplikaten nicht, `--ours` hat dieses Problem NICHT (nimmt eine
  konsistente Vollversion). **KEIN** custom Driver.
- **Recovery-Umleitung bei Gist-Body-Korruption** (Folge-PR zu #322): bei
  `body_ok=False` Positionen erhalten statt `{}`. OFFEN.
- **Toter v2-else-Zweig entfernen** (Option b) — OPTIONAL, Easys Architektur-
  Entscheidung. Isoliert halten (Lektion #226), Dict-Key `"price_str"` behalten.
- **Finnhub-SI-Reserve** (gratis, Key da) als SF-Reserve falls Kette dünn. Niedrig.
- **FINRA-Provider unmonitored (niedrig):** Der Daily-Run-FINRA-History-Fetch
  (speist `si_trend`) hat KEINEN `provider_health`-Record. `provider_health['finra']`
  überwacht nur den ki_agent-SSR-Fetch (anderer Pfad, wochenend-still = normal).
  Optionaler Wächter-PR, niedrig — Fetch läuft + ist wochenend-robust. Aufgreifen
  nach Entry-Stabilisierung. (Datierter Schwellen-Schritt nach dem ~23.06.-Sample:
  s. §4 „FINRA-History-Wächter" — dieser §6-Punkt ist die Backlog-Status-Notiz der
  Überwachungs-Lücke selbst.)
- **Wächter-Block GESCHLOSSEN (erledigt) + Rest:** **premarket-Wächter = S11 live**
  (`run_phase==tsp=='premarket'`, 5-Werktage-Schwelle). **Borrow = Tier-2 registriert**,
  `aggregate_provider_fails` greift (3-in-Folge < 50 % → Digest), transiente Dips
  sind false-fire-sicher. **OFFEN/niedrig:** ein expliziter **borrow-Wächter „S15"
  (vorgeschlagen, S15 noch unbelegt — S1–S14 existieren)** NUR, falls je ein echtes
  Ausfall-Sample beobachtet wird — sonst wäre die Schwelle geraten (Miss-Risiko bei
  langsamem Decay 60–70 %). Aufgreifen nur evidenzbasiert, kein Druck.
- **or-0-Defaults Persist-Fix** · **finviz Flag-aus + α** · **Borrow-Naming
  (`IBKR_*`→`IBORROWDESK_*`)** · **v1/v2→Jinja** · **Cockpit Stage 3 (.sb-Reste)**
  → alle OFFEN, niedrig/vertagt.
- **Volle 86-Suite in CI** (über die 79 hinaus): inkrementell nach Hermetik-Triage
  (die 2 B + 5 ENV + 3 requests-TEMP bleiben außen bzw. brauchen Stubs).
- **Security-Backlog (Audit 09.06., alle niedrig/optional):** **M3 ERLEDIGT als
  bewusste Entscheidung (09.06.):** PAT bleibt **CLASSIC** — fine-grained scheiterte
  26.05. mit 403 bei Workflow-Dispatch/Gist (belegte Betriebslehre, **NICHT erneut
  vorschlagen**). Scopes `repo`+`gist`+`workflow` = betriebsnotwendiges Minimum,
  bewusst belassen (Leak-Pfad seit #343 dicht). **M4** Worker-offener-Proxy
  (Quota-DoS) + **L1** LLM-Error-Sink: bewusst AKZEPTIERT. **CVE-Check**
  (pip-audit/Dependabot) = Easy extern (Sandbox hat kein Netz).
- **ERLEDIGT diese Session (10.–13.06.):** XSS C1+M2 (#343), Vintage-Guard M1
  (#346, schließt den „Option A / Pre-Open-Guard"-Backlog-Punkt), Exit-Shadow-Log
  (#350), KI-/monster-Backtest-Felder (#353), S4-Zeit-Gate (#355), Redeploy-Wurzel-
  Fix (#357), `.jsonl`-Resolver-union (#359), Cron-Doku-Drift (#360/#361),
  Cockpit-Entry-Shadow-Caption (#362). Cron-Inventar via #360/#361 zwischen
  CLAUDE.md + `resolve_run_phase.py` + Test repo-weit konsistent (`17 6`).
- **ERLEDIGT Vorsession (06.–07.06.):** Schema-Tripwire (#329), 5 stale Reds (#330),
  Golden-Liveness (#331), tier2-String-Gating-AST (#332), CI-Gate Phase 1+2
  (#333/#335), health_check-Stub (#334), Entry-Score Shadow (#336).

## 7) ARCHITEKTUR-ANKER
**★ NEU diese Session (10.–13.06.):**
- **★ XSS-Sink-Härtung (#343):** `_escH` (Attribut-Kontext inkl. Quotes) +
  `n.link`-Whitelist `^https?://` an den News-/`company`/`sector`-DOM-Sinks.
  Escaping allein stoppt `javascript:` NICHT → Whitelist zwingend. Schließt den
  einzigen Pfad XSS → sessionStorage-PAT.
- **★ Vintage-Guard M1 (#346):** β+-Gate in `_append_backtest_entries` — Backtest-
  Append nur wenn `bar_date == report_date` (date-Objekt) UND `now_et >= 16:00 ET`;
  sonst Skip VOR existing_keys-Belegung (→ späterer Post-Close-Run appended frisch).
  Datengetriebener Feiertags-Schutz OHNE Liste (Bar=Vortag → skip). Missing
  bar_date → APPEND (konservativ). bar_date in-memory (kein Schema-Bump). Skip-
  Beobachtung in `vintage_guard_log.jsonl` (eigene Datei, digest-frei). **M1 fängt
  NICHT M2** — M2 ist Phantom (§8), kein zweiter Guard nötig.
- **★ Exit-Shadow-Log (#350):** `exit_shadow_log.jsonl` — pro Handelstag pro
  offener Position `exit_state` (pressure + 6 Trigger) + Forward-Return-Backfill.
  Hook NUR im Daily-Run `_build_phase2` (einziger exit_state-Compute; ki_agent
  liest/backfillt nur). Gate postclose+`now_et>=16:00 ET`; Re-Write-by-(ticker,date);
  Backfill reuse `_close_at` (settled, vintage-/auto_adjust-immun) mit
  Abbruchbedingung (forward_10d fertig→skip). **Konvention: negativer forward_Nd =
  gutes Exit-Signal.** Null Live-Effekt, eigene Datei, digest-frei. Sample inhärent
  dünn (nur offene Positionen, autokorreliert) → low-power Erstblick, kein AUC.
- **★ KI-/Monster-Backtest-Felder (#353):** `monster_score` + `ki_signal_score`
  additiv im `_build_backtest_extension`-Return, leer-tolerant (None). **Schema v4
  unverändert** (S10-Loader ==4); `expected_keys` atomar (#329-Tripwire); beide nur
  in `S10_OBSERVED_FIELDS` (kein MUSS-/LAG-Check, da legitim None). Reiner Persist-
  Read, kein Score-/Push-/Render-Pfad liest sie.
- **★ S4-Zeit-Gate (#355):** S4-postclose-Zweig erwartet den heutigen Eintrag erst
  ab `now_et >= report_date@16:00 ET` (`health_check.py`, `_S4_EASTERN` +
  `_S4_MKT_CLOSE_HOUR=16`, zoneinfo/DST-korrekt) — **Symmetrie zum Vintage-Guard-
  Producer-Gate (#346)**. NUR Zeit, NICHT Bar: nach 16:00 ET feuert S4 weiter bei
  Append-Crash UND Bar-Lag-Skip; S4 bleibt **guard-unkenntnis** (liest NICHT
  `vintage_guard_log`, sonst Zahn-Verlust). `_before_close` via OR neben das
  bestehende `_skip_weekend` (ergänzt, nicht ersetzt). `today_iso` None/unparsbar →
  konservativ S4 feuert. `now_utc` war im Evaluator bereits vorhanden (default
  `datetime.now`, keine Plumbing aus generate_report). `severity` bleibt `warn`.
  S12/S3/S7/Vintage-Guard/Produzent unberührt.
- **★★ Redeploy-Auto-Trigger entfernt (#357):** `redeploy-on-source-change.yml`
  feuert **nicht mehr** auf `push` zu `main` (`on: push` → `on: workflow_dispatch`,
  reversibel via auskommentiertem push-Block). **Wurzel-Schließung:** ein Code-Merge
  erzeugt **keinen** automatischen vollen Daily-Run mehr → keine Off-Schedule-
  `postclose`-Runs im Pre-Open-ET-Fenster, keine Pre-Open-Pushes/score_history-Churn
  aus Merges. Die Symptom-Netze **bleiben** (Vintage-Guard #346, S4-Gate #355,
  postclose-Anomaly-Suppression) — greifen jetzt nur seltener. **Direkter Dispatch-
  Pfad bleibt:** der Recalculate-Button POSTet weiter an `daily-squeeze-report.yml`
  (gen:9559/10575) — bewusste Einzelaktion, kein Auto-Pfad (Rest-Kante §6-b).
- **★ `.jsonl`-union-Merge (#359):** `.gitattributes merge=union` für 5 Append-Logs
  (`open(...,"a")`) → Rebase-Append-Konflikte ohne Daily-Run-Abort. `exit_shadow_log`
  ausgenommen (Full-Rewrite/Backfill → union dupliziert). `git rebase` respektiert
  den built-in union-Driver (kein Runner-Config nötig). Guard-Test schützt die
  Klassifikation; CI 80.
- **★ Cockpit-Entry-Shadow-Caption (#362):** client-side Anzeige aus `window._BT_DATA`
  unter `cockpit-body` (`.cockpit-entry-shadow[data-es-ticker]`, server nur leerer
  `hidden` Hook → JS füllt nur bei `entry_score` not-None, 0=Wert). REIN ADDITIV,
  `backtest_history.py`/#336 unberührt; Drawer-Strip-immun (nur `id=`-Strip). Preload
  reused den `_BT_DATA`-Cache. Display-only, Label „unvalidiert bis 30.06." — KEINE
  Live-Aktivierung (s. §4).

**Bestehende Anker (unverändert):**
- **★★ Entry-Score (`entry_score.py`, #336):** PURES stdlib-Modul, bewusst getrennt
  von `backtest_history.py`/yfinance → CI-gate-bar ohne yfinance. Shadow: nur
  `backtest_history` schreibt + `_test_extended_schema` prüft die 4 Felder; KEIN
  Render-/Push-/Score-Pfad liest sie. Berechnung nur **postclose**
  (`generate_report.py if run_phase=="postclose"`). **Entry-Entscheidungen
  (gemergt, exakt):** `ENTRY_UOA_CAP=4.0`, `ENTRY_RVOL_BUILDUP_CAP=6.0` (n=227),
  `ENTRY_SI_TREND_EDGES=(-0.8,-0.2,1.0,5.0)` ≤-Konvention → 0/25/50/75/100,
  score_delta `(x+15)/30×100`, anomaly `×100`; Aggregation = **Re-Norm Option B**
  (kein Neutral-50, Gleichgewichtung, 0 Komponenten→None); anomaly-None = **Option
  (c) run-level** (push-Map gefüllt+None→echte 0; Map leer→drop;
  `push_history_available` persistiert). Schema **v4 additiv** (S10 filtert ==4),
  Tripwire #329 scharf. **Status: Modul komplett** — Berechnung + Persistenz
  (`entry_score`/`entry_components`/`entry_n_components`/`push_history_available`)
  + CI-gate-bar + Anzeige (Cockpit-Caption #362, s. oben) — durchgängig
  **Shadow/unvalidiert** bis 30.06.
- **★ CI Allowlist-Runner + Drift-Guard (#335, live):** `run_ci_mock_tests.py` fährt
  eine STATISCHE Allowlist (**80** seit #359), kein Laufzeit-Glob für die Auswahl;
  **Drift-Guard:** jeder neue `mock_test_*` MUSS in ALLOWLIST ODER EXCLUDED stehen,
  sonst failt der Runner. Advisory — **`permissions: contents: read` NIE aufweiten**
  (sonst blockt es den Self-Merge). Minimal-Install **jinja2+pyyaml** (BEWUSST KEIN
  requests/pandas_ta — Sandbox≠CI-Lehre, §8). EXCLUDED=10 (2 B + 5 yfinance-ENV +
  3 requests-TEMP).
- **★ Screener-Pool-Floor (#325):** `yahoo_screener` Tier-1-Inhalts-Check auf
  ROH-item_count (FLOOR=120), NICHT pool_size (POOL_MIN-Backfill maskiert).
- **★ AST-robuste provider_health-Test-Anker (#327/#332):** Struktur- UND String-
  Gating-Tests ankern per AST (record-call→Try / kwarg / enclosing-if), NICHT per
  Byte-Distanz.
- **Advisory PR-CI (#316):** `pr-checks.yml`, `on: pull_request`, NICHT required,
  `check_run`-Signal, blockiert Self-Merge nicht.
- **S14 + Gist-Body-Sanity (#314 + #322):** `last_successful_gist_pull` nur bei
  `body_ok`; S14 WARN@26h; fängt Token-Tod UND Body-Korruption.
- **Outer-Page-Golden (#312):** Render-LOGIK-Netz, fixe Fixtures, pandas_ta-
  invariant; seit #331 auch Liveness-gestubbt (data-unabhängig). Output-Change →
  `UPDATE_GOLDEN` + Golden mit-committen (Pflicht). Backtest-/main()-Code ändert
  das Golden NICHT (nur der HTML-f-String) — bestätigt bei #346/#350/#353.
- **`_DAILY_REPORT_COUNTS`-Modul-Global (#320)** (kein WL_TOP10-Leak).
- **report_date + _today_iso = US-Eastern (#304).** backtest-T+0 = `_close_at(0)`
  (#303). „Echter Phasen-Run" = run_phase==tsp (S11/S12).
- **S9-CRIT-Exit-Pfad filtert STRIKT id=="S9".**
- **Health-Check-Schichten:** S1–S7 State | S8 Digest-Liveness | S9 HTML-Sanity
  (einziger CRIT-Block) | S10 Daten-Integrität v4 | S11/S12 Phasen-Frequenz | S13
  Daten-Reife + Konsistenz | S14 Gist-Pull-Liveness.
- **Borrow = iBorrowDesk-JSON (#292), Inhalts-success_check.** CTB persistiert (#309).
- **squeeze-guardian (#306/#319):** echo-Hook spawnt Agent NICHT; Architektur =
  manuelle EMPFOHLENE Routine, Bonus kein Gatekeeper.
- **Cron-Inventar (verifiziert; Doku-Drift `17 10`→`17 6` via #360/#361 bereinigt,
  repo-weit kein `17 10` mehr):** ki_agent `17 * * * *`, daily premarket
  `17 6 * * 1-5` (real ~12 UTC nach Actions-Drift), postclose `17 21 * * 1-5`,
  health-digest `47 8 * * *`, watchlist `0 7 * * 0`, pr-checks `on: pull_request`.
  checkout@v5.
- **★ Security-Audit 09.06. (read-only, 6 Bereiche):** Token-Krypto bestätigt
  **solide** (PBKDF2 600k, AES-GCM, frische IV+Salt pro Verschlüsselung, Master-PW
  nie persistiert). **C1+M2 GEFIXT (#343)** — XSS-Sinks dicht (s. oben).
- **★ Privacy-Akzeptanz (Entscheidung c, 09.06., Easy):** Repo public + Gist-ID im
  gerenderten `index.html` → der secret Gist (Positionen/Stückzahlen/Watchlist) ist
  für jeden Page-Besucher **anonym LESBAR** (kein Write, kein Token-Zugriff — reines
  Lese-/Privacy-Risiko). **BEWUSST AKZEPTIERT**, weil: (1) Repo-privat bricht Pages
  auf Free-Plan + Actions-Minuten-Limit; (2) Strip der committeten Mirror-Files
  **VERWORFEN** — `app_data.positions.exit_state` ist das **EINZIGE** Cross-Run-
  Ratchet-Gedächtnis (peak_score/peak_pnl/prev_exit_pressure, gen `15224/15250`;
  `pull_gist_data.py:192` übernimmt es nicht) → voller Strip = Peak-Reset jeden Run
  = falscher Exit-Druck (**HARD-BREAK, Trading-Schaden**); `agent_state.push_history`
  nicht strippbar (Entry-Score-Input + ki_agent-FIFO). Rest-Strip ≈0 Gewinn (dieselben
  Daten liegen im akzeptierten Gist offen). **NICHT erneut vorschlagen ohne neue
  Lage.** Echte Privatheit nur via Storage-Redesign (Option d, §6).

## 8) LESSONS
- **★ Sandbox ≠ CI-Env (06.06.):** der Sandbox HAT `requests` (+ pyyaml etc.), der
  Minimal-CI-Install (jinja2+pyyaml) NICHT → „grün geboren" ist NUR gegen einen Env
  beweisbar, in dem ALLE CI-fehlenden Deps blockiert sind, **nie** gegen die Sandbox.
  Fix: CI-Sim mit Dep-Blocker vor jedem „grün"-Claim.
- **Diff-Anzeige ≠ finaler Stand:** ein Diff zeigt entfernte Zeilen (`-`), die wie
  noch-aktive Steps aussehen → den FINALEN Datei-Stand greppen, nicht den Diff
  interpretieren (Doppellauf-Fehlalarm bei #335).
- **None ist nicht gleich None:** „keine Daten" (Pipeline-Ausfall) vs „echtes
  Nichts" (legit kein Wert) muss am SCHREIBPFAD unterschieden werden, nicht am Feld
  (Entry-anomaly Option-(c); analog jetzt die leer-toleranten KI-Felder #353). Per-
  Feld nicht trennbar → Run-Level-Flag + Mini-Stopp für Easys Entscheidung.
- **Trading-Wert-Filter auf BLÖCKE:** die CI-Kette war teils Selbstzweck. Vor einer
  ganzen Arbeitskette fragen „Edge oder Hygiene?", nicht nur pro Task.
- **★ Inhalts-Plausibilität ist eine fehlende Überwachungsschicht (09.06.):**
  S10/Schema/Golden decken Liveness + Null/Schema, aber NICHT Wert-Plausibilität
  (Range/Freeze/Vintage) — belegte Lücke (S10 prüft nur `is None`,
  `health_check.py:404`). Der Freitag-Cluster wurde per ZUFALL gefunden. **LINIE**
  (gegen Over-Engineering + Wächter-Block-Lehre 04.06.): Wächter NUR wo (1) der
  Defekt belegt Trading-Entscheidungen/Edge verzerrt UND (2) der Check wurzel-nah +
  niedrig-Falsch-Positiv ist. Sonst Caveat oder silent-log-first. **FP-Baseline:**
  Slow-Update-Freeze (SF/dtc 85 %, score_struct 70 %) ist LEGITIM. **Selbst-
  Begrenzung:** signatur-lose Defekte sind strukturell unsichtbar — kein Wächter
  darf vorgeben, alles zu fangen.
- **★ Raw-vs-Smoothed-Skalen nicht mischen (10.06., score_delta-Diagnose):** die
  Karten-Δ-Anzeige rechnet auf RAW-score_history-Werten, der angezeigte Score ist
  SMOOTHED — `smoothed + raw_delta` rekonstruiert nichts (der „130,4"-Phantom-
  Widerspruch; CBRL −40,9 ist ein echter ~41-Pkt-Tagesschwung, beide Operanden
  ∈[0,100]). Beim Diagnostizieren scheinbarer Wert-Widersprüche zuerst klären, ob
  beide Operanden DIESELBE Skala/Verarbeitungsstufe haben. UND: „uncapped" ≠
  „explosionsgefährdet" — eine Differenz zweier ≤100-Werte ist strukturell ±100-
  gebunden (harmlos, score_delta), eine Division-durch-klein (si_trend-slope) ist es
  nicht. Vor „Ausreißer-Risiko" die mathematische Schranke prüfen.
- **★ S3/S7-Digest-Spike an aktiven Merge-Tagen ERKLÄRT (10.06.):** Viele manuelle
  Dispatches + „Redeploy index.html on source change" (#194, **feuerte** pro main-
  Merge — **Auto-Trigger seit #357/11.06. entfernt**) erzeugten an Tagen mit mehreren
  PRs eine Run-Dichte, die transiente **S3** (current_price-Lücken bei Nicht-Top10-
  Positionen, yfinance gesund) und **S7** (top10-Drift, stündlicher ki_agent kommt
  nicht nach) auslöste. **SELBSTHEILEND, kein Provider-Ausfall, kein Loop.** Exit-
  Logik pausiert sauber bei `current_price=None` (`generate_report.py:14673` →
  `available=False`). Bei ähnlichem Digest an einem Merge-Tag: **erst Actions-Liste
  prüfen** (manuelle Dispatches?), bevor man eine Provider-Diagnose startet.
  **NACHTRAG (#357):** der Redeploy war **dieselbe** Quelle wie die §6-b-Pre-Open-
  `postclose`-Runs (nicht „separater Faden", wie früher hier vermutet) — mit dem
  Auto-Trigger-Aus ist diese Merge-Tag-Run-Dichte für den **automatischen** Pfad
  geschlossen; nur noch bewusste manuelle Dispatches/Recalculate können sie erzeugen.
- **★ DBI-8.88-Strang vollständig aufgelöst (10.06.) — KEIN Bau, P&L aller 8
  Positionen korrekt.** Kette: **(1)** M2 After-Hours-Capture = **Phantom** (alle
  Price-Captures `prepost=False` → `iloc[-1]` ist regulärer Session-Close). **(2)**
  auto_adjust-Mismatch breit = **Phantom**: P&L nutzt Positions-`entry_price` aus
  Gist/User (roh) gegen Live-Worker-Quote (roh) — beide roh, konsistent; das 8.88
  ist das **Backtest**-entry_price (adjusted, display-only `_btRenderTable`), ein
  ANDERES Feld als `positions.entry_price` (7.41 User). **(3)** Split-Accounting:
  PDYN-Reverse-Split 07/2023, Entry 01/2025 = danach → keine Divergenz; RBOHF kein
  auffindbarer Split. Keine offene Position von Corporate Action zwischen Entry und
  heute betroffen. **LESSON:** „sieht komisch aus" (8.88) ≠ Defekt — Backtest-Feld
  vs. Positions-Feld nicht verwechseln; P&L ist epochen-konsistent (User-roh +
  Live-roh), bewusst NICHT am auto_adjust-Capture.
- **★ „Sichtbarer Abort ≠ stiller Verlust" + Merge-Strategie folgt der Schreib-
  Semantik (12.06., .jsonl-Resolver):** Eine ältere Notiz nannte die `.jsonl`-
  Resolver-Lücke „stillen Sammelverlust" — die Code-Lese zeigte das Gegenteil: der
  Block bricht **laut** ab (`rebase --abort; exit 1`), kein Silent-Drop. **Vor dem
  Fix den tatsächlichen Failure-Modus am Code verifizieren, nicht die alte Annahme
  fortschreiben.** UND: `merge=union` ist NUR korrekt für **echte Append-Logs**
  (`open(...,"a")`, eindeutige Timestamps); bei **Full-Rewrite/keyed** Dateien
  (`open(...,"w")`, Re-Write/Backfill — hier exit_shadow) erzeugt union **Duplikat-
  Keys** = Korruption. **Vor jedem Merge-Driver pro Datei die Schreib-Semantik
  prüfen** (Append vs. Rewrite), nicht pauschal anwenden. Beides empirisch belegt
  (Rebase-Konflikt-Szenario nachgestellt), bevor darauf gebaut wurde.
- **★ „Daten schon da" → einmalige Auswertung statt Wächter; und Anschlag-Rate ≠
  Cap-Entscheid (13.06., Entry-Cap-Trockenlauf):** Ein periodisches Verteilungs-
  Wächter-Modul wurde **verworfen**, weil die Rohwerte + Twins längst persistiert
  sind — eine **einmalige read-only-Auswertung** reicht, ein Dauer-Wächter wäre
  Über-Engineering (Nordstern: Mensch validiert Bedeutung einmal). UND: eine
  **Anschlag-Rate** („Cap bindet bei X %") sagt NICHT, ob der Cap *falsch* ist —
  dafür braucht es den **Edge-Test** (haben am-Cap-Einträge andere Forward-Returns?).
  Verteilung ist notwendig, nicht hinreichend. Vor „Cap nachschärfen" immer den
  Return-gepaarten Edge-Test, nicht nur das Histogramm. (Cap-Entscheid daher an
  `return_10d`-Reife gekoppelt, nicht ans Kalenderdatum — Qualität vor Pünktlichkeit.)
