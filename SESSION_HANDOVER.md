# SESSION_HANDOVER.md — Stand 15.07.2026

**Zweck:** vollständige Übergabe an eine **neue Code-Session ohne Kontext der
alten**. Dieses Dokument + `CLAUDE.md` müssen zusammen ausreichen, um am
Projektstand direkt weiterzuarbeiten. Reine Doku, kein Logik-Touch.

Struktur (9 Blöcke): (1) Heute implementiert · (2) Aktive Positionen ·
(3) Verifikation · (4) Wiedervorlagen · (5) Strategische Roadmap ·
(6) Hygiene-Backlog · (7) Architektur-Anker · (8) Lessons · (9) Arbeitsweise-
Anker.

---

## 1) HEUTE IMPLEMENTIERT (chronologisch, mit Hashes)

*(Roter Faden 11.07.–15.07.2026: ein entry_past_return_5d-Bugfix (#411, Nenner
im Merge gedroppt) → dann konsequente Auffanglinien-Umsetzung im Frontend
(#412 neutrales Sammel-Felder-Status-Panel, #414 Entfernung des als Trade-Signal
lesbaren „Erste Erkenntnisse"-Empfehlungsblocks — analog #406) → wöchentlicher
Lit-Check-Reminder standalone (#413) → Paper-Verwertung: Svoboda-Befunde +
3-Schritt-Plan (#415), Ausblick-Schritt D (#416), Schritt-A-Blocker verankert
(#417). Davor 03.07.–10.07.: Backfill-Kette `max_gain_pct` (#400/#401/`85cbbe9`
330/330) → Hypothese-C-Null (0/6 Holm) → Kombi-Sammel-Felder (#402/#404/#409) →
yfinance-Cap (#403) → Doku (#405/#406) → Karfreitag/pub_date-Kette (#407/#408/
#409).)*

### PR #411 — 11.07. — Merge `902671a` (feat `dd31fdb`)
**★ Bugfix `entry_past_return_5d` — gedroppter Pre-Entry-Nenner.** Der Nenner
`close_5td_before_entry` wurde in `_hist_stats` korrekt berechnet, aber im
`c.update`-Enrichment-Merge (`generate_report.py` `def main()`) **nicht in die
Key-Whitelist aufgenommen** → fiel weg → `_compute_entry_past_return_5d(price,
None)` = None (50/50 Records None). **KEIN** Namens-Mismatch. Fix rein additiv:
(a) Merge reicht `close_5td_before_entry` aus `yfd` durch; (b) `get_yfinance_data`
(Fallback-Pfad) berechnet+returnt den Wert aus der 1y-history; (c) Mock-Test um
**Merge-Assertion** + End-to-End-Non-Null-Kernbeweis (node) erweitert. Wirkt
**vorwärts** — die 50 Alt-None-Records bleiben None (kein Backfill). Golden
byte-identisch (Change nicht im Render-f-String). Guardian ✓. **Manueller Merge.**

### PR #412 — 11.07. — Merge `84c4e7f` (feat `7823757` + `0b8f161`)
**★ Sammel-Felder-Status-Panel** (neutral, Datenerhebungs-Fortschritt). Neue
read-only `.bt-tile--wide` in `#bt-section` + `_btCollectStatus(data)`: zeigt pro
Sammel-Feld (max_gain_pct, conviction_score, days_to_earnings, entry_past_return_
5d, si_velocity_pub) einen **dynamischen non-null-Zähler** aus `_btData` + Status
(„sammelt/unvalidiert/auswertbar ab ~Datum") — **KEINE Feld-Werte, kein Signal**
(Auffanglinie, analog #406). **Look-Ahead-Guard-Fix (`0b8f161`):** Feldnamen
leben in `config.COLLECT_STATUS_FIELDS`, als JS-Render-Konstante injiziert → keine
Backtest-Feldnamen-Literale im `generate_report.py`-Source → alle 3 Look-Ahead-
Isolations-Guards bleiben unverändert grün. Golden mit-aktualisiert. Guardian ✓.
**Manueller Merge.**

### PR #413 — 11.07. — Merge `5756926` (feat `ae1c825`)
**★ Wöchentlicher Lit-Check-Reminder** (standalone). Neuer Workflow
`lit_reminder.yml` (Cron `33 16 * * 5` = Fr 18:33 Berlin) + `scripts/lit_
reminder.py`: **ein** fixer ntfy-Push „📚 Wöchentlicher Reminder: Squeeze-
Forschung Web-Check fällig". **Null Trade-Pipeline-Touch** — kein Cooldown/
Silence/push_history/agent_state, `permissions: contents: read` (schreibt nichts
ins Repo). Eigene Kategorie (Priority `default`, Tag `books`). Muster: health_
check_digest (URL-Pattern, ASCII-Title-Strip). Guardian ✓. **Manueller Merge.**

### PR #414 — 11.07. — Merge `f15ca9b` (refactor `4eb2c73`)
**★ „Erste Erkenntnisse"-Empfehlungsblock ENTFERNT.** `_btRenderRecommendation`
rankte Score-Buckets nach Median-Rendite und gab eine wörtliche „Empfehlung:
Score X + max. Haltedauer YT." mit farbigen Rendite-Zahlen aus — ein als
Trade-Signal lesbarer Edge-Claim, im Widerspruch zur Auffanglinie + 30.06.-Null.
Sauber entfernt (Funktion + Aufruf + `#bt-reco`-Div + `.bt-reco*`-CSS);
**`_btBucketStats` BLEIBT** (weiter von der Median-Kachel + Knaller-Label-Sync
konsumiert). Gerenderter JS besteht `node --check` (kein Dangling-Ref). Golden
rein entfernend (0 add / 67 del). **Manueller Merge.**

### PR #415 — 15.07. — `fb25b4c` (squash)
**Doku:** Paper-Verwertungsplan — Svoboda/Kapounek/Albrecht-Befunde (§5) +
3-Schritt-Plan (§4) + Backlog (§6g/§6h) + Lessons (§8h/§8i). Reine Doku,
**Auto-Merge**.

### PR #416 — 15.07. — `22f976f` (squash)
**Doku:** Schritt D (Ausblick) — `squeeze_probability`-Score nach Paper-Modell,
mit kritischer Deklaration (Wahrscheinlichkeit ≠ Rendite) + vier Bau-Bedingungen.
Reine Doku, **Auto-Merge**.

### PR #417 — 15.07. — `ef78b40` (squash)
**Doku:** Schritt-A-Blocker — Coverage-Check negativ (SI-Zeitreihe fehlt);
§4-Zeile ⛔ BLOCKIERT + §6i voller Befund. Reine Doku, **Auto-Merge**.

---

### PR #400 — 03.07. — `a936886` (squash-merged)
**★ Backfill thin-slice-Zähler** (Guardian-Nachbesserung aus #399).
Neuer pure Helper `classify_outcome(df_len, mg) → str` mit vier Klassen
(`none` / `thin_slice` / `filled_zero` / `filled`).
`compute_and_apply_backfill`-Return-Tupel um `n_thin_slice` erweitert.
Live-`log.warning` wenn > 0. Trennt stille Datenlücken (`mg=0.0` bei
`df_len<2`) von echten Null-Gains. 54/54 fixture-Tests grün. Kein
Verhaltens-Effekt am Füll-Vorgang — nur Diagnose. **Manueller Merge.**

### PR #401 — 03./04.07. — Merge `55be1dd` (Guardian-Nachbesserung `7056cb2`)
**★ Backfill-Workflow `workflow_dispatch`.**
Neuer `.github/workflows/backfill_max_gain_pct.yml` — manual-only,
`concurrency.cancel-in-progress: false`, `git add backtest_history.json`
(genau eine Datei), `git diff --staged --quiet && exit 0`-Idempotenz-Guard.
Guardian ✓ (Finding 4 Kommentar-Präzisierung im `7056cb2`-Nachtrag).
**Manueller Merge.** Anschließend:

### `85cbbe9` — 04.07. — Live-Lauf
**★★ MAX_GAIN_PCT-Backfill DURCH — 330/330 Records gefüllt, 0 thin-slice.**
Commit „chore: max_gain_pct backfill (einmalig, 330/330 Records gefüllt,
0 thin-slice)". Alle 330 reifen Alt-Records in `backtest_history.json`
tragen jetzt `max_gain_pct` (129 unique Tickers). Kein thin-slice →
keine stillen Datenlücken. Hypothese-C-Sample sofort auswertbar.

### 04.07. — Hypothese-C-Auswertung (kein PR, dokumentiert in #405)
**★★ 3 Schwellen +10 % / +30 % / +50 %:** Seed 04072026, Bootstrap
N=2000, k=6 gemeinsame Holm-Klammer über 3 Schwellen × 2 Cluster-Läufe.
**Kernbefund: 0/6 Holm-Rejects.** Alle AUC-CIs enthalten 0.5.
Baseline-Peak-Raten 95.8 % (C-10) / 35.5 % (C-30) / 15.2 % (C-50). C-50
Δ +5.44 pp / +5.76 pp mit AUC 0.562/0.561 zeigt richtungs-plausible
Punktschätzung, aber roh-p 0.164/0.213 → NICHT „Hinweis"-Kategorie.
Regime-Robust (pre/post-#346-Split konsistent). **Auffanglinie über
drei Auswertungstage bestätigt** (30.06. Endpunkt + 01.07. Exit-Timing
B.1 + 04.07. Peak). **Setup-Score bleibt Attention-Router / Screener.**

### PR #402 — 02.07. — `0da83af` (Guardian-Nachbesserung `498aeaf`)
**★ `entry_past_return_5d` Stufe A** (Hypothese-A-Vorbau, Reversal-Entry).
Additive Live-Vorwärts-Erhebung: `_compute_entry_past_return_5d(close_at_
entry, close_5td_before)` mit Adj-Close BEIDSEITIG (Split-Konsistenz-
Pflicht, Reverse-Splits bei Squeeze-Small-Caps häufig). `_hist_stats`-
Tupel um Element `close_5td_before_entry` erweitert; Batch + Singleton-
Fallback beide angepasst. **Kein neuer yf-Fetch** — nutzt bestehende
`hist_batch`. **None-Semantik STRIKT** (nicht 0.0-Overload wie
`max_gain_pct`): `None` = nicht ableitbar, echte Null-Bewegung liefert
`0.0`. Look-Ahead-Konvention EINFROREN im Docstring + S10-Kommentar +
Test E1-E6. Schema v4 unverändert. 24 fixture-only Tests grün.
Guardian ✓ (4 informative Findings, F1+F2 in `498aeaf` behoben:
Testname-Rename + CLAUDE.md-Anker). **Manueller Merge.**

### PR #403 — 03.07. — Merge `b4d6b1d`
**★ Requirements-Cap-Semantik.** `yfinance==1.4.1 → yfinance>=1.4.1,<1.5`
(analog `pandas>=3.0.3,<3.1`, `peewee>=4.1.0,<4.2`). Löst
`#393`-Segfault-Bridge-Trade-off („`==`-Pin sperrt auch 1.4.x-Bugfixes")
ohne den Minor-Sprung wieder zuzulassen, der den SIGSEGV verursachte.
Cap-Kontrolle: kein `>=` ohne Obergrenze bei den drei Ziel-Paketen.
Kein Konflikt mit `pr-checks.yml` (installiert bewusst separat).
**Manueller Merge.** Live-Verify: nächster Actions-Lauf soll
`1.4.1 / 3.0.3 / 4.1.0` ziehen (§3).

### PR #404 — 04.07. — `1594f20`
**★ `days_to_earnings` Stufe A** (Hypothese-H5-Vorbau, Katalysator ×
Score). Additive Live-Vorwärts-Erhebung, Snapshot des AM Report-Tag
bekannten nächsten Earnings-Termins in **Kalendertagen** (konsistent zum
Live-Score-Konsumenten `_compute_sub_scores:3746-3749`, Bucket-Schwellen
≤7 / ≤14). Wert 1:1 aus `s["earnings_days"]` (Live-Enrichment via
EarningsWhispers-Cache + yfinance-Fallback in `generate_report.py:16502-
16540`). Point-in-time-sauber: Fetch AM Report-Tag → keine später-
angekündigten Termine leaken. **Backfill STRUKTURELL NICHT MÖGLICH** —
heutiger Fetch ≠ damaliger Termin; nur Vorwärts-Erhebung. Look-Ahead-
Konvention EINFROREN (analog #402). Ein-Feld-Invariante, `int()`-Cast
defensiv, None-Semantik klar (`0 = Earnings HEUTE ≠ None`). 15
fixture-only Tests grün. Guardian ✓ ohne Findings. **Manueller Merge.**

### PR #405 — 04.07. — `805c9df`
**Doku:** SESSION_HANDOVER.md komplett auf 04.07.2026 aktualisiert
(alle 8 damaligen Sektionen). Reine Doku, Auto-Merge.

### PR #406 — 08.07. — Merge `7e4bde0`
**★ Conviction-Level-Texte neutralisiert.** Frontend-Sprach-Fix an
belegten Zustand: aus Handlungs-Suggestion („Erwartungswert positiv") →
neutrale Aggregations-Beschreibung („Aggregations-Anzeige, nicht
validiert"). Panel-H4 „Aktions-Empfehlung" → „Aggregations-Ansicht",
Pill ≥75 → „hohe Konvergenz". Kein Score-/Filter-Effekt. Golden-Snapshot
mit-aktualisiert (byte-identisch nach `UPDATE_GOLDEN=1`). Konsumenten-
Grep: 0 Selektor-/JS-Key-Treffer außerhalb Golden/Runtime. **Auto-Merge.**

### PR #407 — 09.07. — Merge `f7513a9`, JS-Spiegel `b87474a`
**★ Good Friday algorithmisch in `US_MARKET_HOLIDAYS`** (Meeus-/Butcher-
Oster-Formel, pure stdlib). Karfreitag = Ostersonntag − 2 Tage, bit-exact
für den Gregorianischen Kalender ab 1583. Python-Set (`config.US_MARKET_
HOLIDAYS`) UND JS-Spiegel (`generate_report.py`-embedded `US_HOLIDAYS`)
**bit-identisch** synchronisiert (Test `mock_test_good_friday` erzwingt
Symmetrie). Range 2020–2050 abgedeckt. Ersetzt frühere Hardcode-Liste,
die 2028 auslaufen wäre. **Manueller Merge (Schema/Kalender-Touch).**
Guardian ✓ (ROT-Blocker JS-Spiegel gefunden und in `b87474a` gefixt).

### PR #408 — 09.07. — `57d8f18`
**★ `finra_publication_date`-Helper (settlement + 7 Business-Days).**
Basis für Look-Ahead-freie SI-Analysen. Neues Modul
`scripts/business_days.py` (~130 Zeilen, pure stdlib) mit
`next_trading_day(d)` und `finra_publication_date(settlement_date,
offset=None)`. Konstante `FINRA_PUB_OFFSET_BUSINESS_DAYS = 7` in
`config.py` (kapselt FINRA-Rule-4560-Dissemination-Delay; SR-FINRA-2026-012
plant höhere Frequenz → Offset zentral anpassbar). Live-Enrichment in
`generate_report.get_finra_short_interest`: jeder `history`-Entry bekommt
zusätzlich `pub_date` (ISO-String). Holiday-robust dank #407. Modul-
Isolation: kein Cross-Import in `cluster_purge` (Reihenfolge-Disziplin).
34 fixture-only Test-Assertions (A–I) inkl. manueller Karfreitag-Rechnung
Do 26.03. → Di 07.04.2026 (nicht Mo 06.04. — belegt PR-#407-Kern-Nutzen).
Guardian ✓ ohne Blocker. **Manueller Merge.**

### PR #409 — 10.07. — `a52ef48` (Kosmetik-Nachbesserung `83ac7da`)
**★ `si_velocity_pub` — Look-Ahead-freier SI-Rate über N=3 publizierte
Reports.** PR-3 der 3-PR-Kette (#407 → #408 → #409). Neuer pure Helper
`_compute_si_velocity_pub(finra_history, entry_date, n_reports=None)` in
`backtest_history.py`. Formel `(si[0] − si[N-1]) / si[N-1]` (relativ,
gerundet 4) über die letzten `SI_VELOCITY_PUB_N_REPORTS=3` PUBLIZIERTEN
Reports mit `pub_date ≤ entry_date`. Neues Backtest-Feld
`si_velocity_pub` in `_build_backtest_extension` (entry_date-Kwarg neu,
`_append_backtest_entries` reicht das aus dem Wochenend-Guard bereits
existierende `_rd` durch). **Naming-Isolation:** der `_pub`-Suffix
grenzt bewusst gegen das ältere Displayfeld `finra_data.si_velocity`
in `generate_report.py` ab (absolute Shares/Tag über volle Historie,
kein pub_date-Filter, KI-Boost-Konsument — bleibt unangetastet).
Beide Größen koexistieren mit verschiedenen Zwecken. 34 fixture-only
Test-Assertions (A–G), inkl. LOOK-AHEAD-KERNBEWEIS B1–B4 (Report mit
`settlement ≤ entry_date` ABER `pub_date > entry_date` MUSS
ausgeschlossen werden). Look-Ahead-Konvention EINFROREN im Docstring.
S10_OBSERVED_FIELDS-Whitelist. Schema bleibt v4. Guardian ✓ ohne
Blocker (kosmetischer Doppel-Kommentar in `83ac7da` gefixt).
**Manueller Merge.**

---

## 2) AKTIVE POSITIONEN

**Kanonische Quelle: privater Gist** (`squeeze_data.json`, `positions`-Sub-
Objekt). Aus der Sandbox nicht direkt lesbar — `app_data.json`-Mirror ist
der letzte Daily-Run-Snapshot; bei Abweichung gewinnt der Gist. Zwischen
Runs kann `current_price` stale sein (S3-Merge-Tag-Muster, §8 — kein
Ausfall-Indiz).

**Stand `app_data.json` — letzter erfolgreicher Daily-Run `last_daily_run_
ts = 2026-07-11T22:30:56Z` (postclose, 11.07.):** **7 offene Positionen.**

| Ticker | entry_date | entry_price | current_price | shares | Hold-Flag |
|---|---|---|---|---|---|
| AMC   | 2026-05-01 | $1.50   | $1.89   | 500 | ✓ `no_exit_alerts=True` |
| IONQ  | 2026-05-11 | $49.10  | $42.86  | 40  | — |
| PDYN  | 2025-01-20 | $11.52  | $5.28   | 150 | — |
| AI    | 2026-06-01 | $11.00  | $8.95   | 10  | — |
| WOLF  | 2026-07-03 | $50.97  | $35.29  | 7   | — |
| FRMM  | 2026-07-06 | $6.95   | $5.96   | 15  | — |
| LENZ  | 2026-07-07 | $6.00   | $5.59   | 15  | — |

**Änderungen seit 11.07.-Handover:** Positions-Set unverändert (dieselben 7).
`current_price`-Werte sind der 11.07.-postclose-Snapshot — zwischen Runs stale
(kein Ausfall-Indiz, §8). Details (P&L, These, Lessons) ausschließlich im
Gist / Trade-Journal, nicht Session-Kontext.

**Hold-Flag-Regel unverändert:** `AMC` trägt weiterhin `no_exit_alerts=
True` (bewusster Buy-and-Hold-Skip aller Exit-Pushes). Andere Positionen
bekommen Exit-Pushes; **Schutzschicht seit PR #381** (21.06.): Exit-Push-
Pipeline feuert **nicht mehr an Wochenenden oder US-Feiertagen**
(`config.US_MARKET_HOLIDAYS`, gemeinsames Shared-Set mit S4-Health-Check)
UND nur bei `available=True`.

---

## 3) VERIFIKATION (nächste Handelstage, konkrete Beobachtungspunkte)

### AKUT (ab 15.07.2026)

- **★★ `entry_past_return_5d` — Bugfix-Live-Verify (PR #411):** der
  Merge-Durchreich-Fix wirkt **vorwärts**. Stand 15.07.:
  **50 present / 0 non-null** (Alt-Records vor dem Fix bleiben None). Der
  **nächste postclose-Run nach dem #411-Merge** sollte erstmals Records mit
  **non-null** `entry_past_return_5d` anlegen (etablierte Ticker mit ≥6 Bars
  vor Entry). Watch: `non-null`-Zähler > 0 in `backtest_history.json` bzw.
  in der neuen Status-Kachel (#412). Das ist der Kern-Beleg, dass der Fix
  greift.

- **★ Lit-Check-Reminder — erster Push (PR #413):** erster planmäßiger
  ntfy-Push **kommenden Freitag ~18:33 Berlin** (Cron `33 16 * * 5`). Watch:
  Push kommt an, Titel „Lit-Check-Reminder", Tag `books`. Bleibt er aus →
  `NTFY_TOPIC`-Secret prüfen (Workflow ist fail-visible: exit 1 bei
  Send-Fehler trotz gesetztem Topic).

- **★ Sammel-Felder-Status-Panel — Zähler wachsen (PR #412):** die Kachel
  in `#bt-section` zählt dynamisch aus `_btData`. Stand 15.07.:
  `max_gain_pct` 390 · `conviction_score` 90 · `days_to_earnings` 42 ·
  `entry_past_return_5d` 0 · `si_velocity_pub` 10 (non-null). Watch: Zähler
  steigen automatisch pro postclose-Run; keine Feld-Werte im Output (nur
  Zähler + Status).

- **★ `si_velocity_pub` / `days_to_earnings` — Reifung (§4):** wachsen jeden
  postclose-Werktag. Auswertung erst bei n≥40 reif (§4-Kalender). `si_
  velocity_pub` erwartet `None` in den ersten Wochen (< 3 eligible publizierte
  Reports vor Entry), Zahlenwert nach ~6–8 Wochen.

- **★ `max_gain_pct` — Verteilung wächst:** Stand 15.07. **390 present /
  390 non-null** (330 Backfill 04.07. + Vorwärts). Watch: Log-Zeile
  `max_gain für M/N aktive Einträge` im postclose-Log; keine `None`-
  Persistierung bei reifen Records (≥10 Trading-Days).

- **★ Karfreitag algorithmisch (#407) — nächste Verifikation Fr
  02.04.2027:** `US_MARKET_HOLIDAYS`-Enthaltensein + JS-Spiegel
  `US_HOLIDAYS.includes("2027-04-02")`. Bis dahin keine Live-Verify nötig.

### KEINE VERIFIKATION MEHR NÖTIG (abgeschlossen)

- yfinance-Cap `>=1.4.1,<1.5` (#403) — Actions-Läufe seit 04.07. stabil
  ohne Segfault; Dauer-Watch entfällt (nur bei Cap-Aufhebung §6, wieder
  relevant).
- „Erste Erkenntnisse"-Empfehlungsblock (#414) — entfernt, `node --check`
  grün, Golden rein entfernend; nichts nachzubeobachten.
- Independence Day Fr 03.07.2026 (Holiday-Skip PR #381 verifiziert).
- Redeploy-Auto-Trigger aus (PR #357 seit 13.06. verifiziert).
- Hypothese-C-Auswertung (durchgeführt 04.07., §4 erledigt-null).

---

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)

### RE-TEST-KALENDER (kanonisch, Stand 15.07.)

| Datum | Was | n-Ziel | Notiz |
|---|---|---|---|
| **~Mitte Aug 2026** | ki_signal_score-Edge-Re-Test | n_reif ≥ 40 | LOOK-AHEAD SAUBER — LLM-basiert `temperature=0`, Score zum Erhebungszeitpunkt eingefroren, deterministisch reproduzierbar über gespeicherten Wert. Eigenständiges Signal = Kombi-Kandidat. |
| **~Ende Aug 2026** | Conviction-Edge (Prüfpunkt P3 aus 30.06.) | n ≥ 100 | Vorwärts-Erhebung seit PR #388 (28.06.). Composite aus Setup/Earliness/Anomaly/Regime — Aggregations-Anzeige, deren Edge selbst noch nicht belegt ist. |
| **~Ende Sept 2026** | Setup-Edge-Re-Test | n ≥ 250 | Andere Marktphase zwingend (30.06.-Sample war Mai–Juni-lastig, 91 % pre-#346). |
| **~Ende Sept 2026** | Exit-Timing B.1-Hinweis-Re-Test | n ≥ 250 | 01.07. Punktschätzung Δ ~+4 pp (5d/3d vs 10d in Score≥70-Bucket), Holm-negativ — Re-Test zur Bestätigung. |
| **Herbst 2026 (OoS)** | **Hypothese H5 (Kombi Score × Katalysator × Reversal × SI-Velocity)** | n ≥ 40 pro Feld-Kombi | **Vorab-registriert** (§5). Out-of-Sample-Auswertung über die vier Look-Ahead-freien Sammel-Felder (`max_gain_pct` #397, `entry_past_return_5d` #402, `days_to_earnings` #404, `si_velocity_pub` #409). Feste Klammer, keine nachträgliche Schmälerung. |

### PAPER-VERWERTUNGSPLAN (Svoboda et al. 2026, ausgewertet 15.07.) — 4 Schritte (A–C + Ausblick D), je 1/Tag

Vorregistriert, **Schwellen aus FREMDEM Datensatz** (= Overfitting-Schutz:
nichts frei aus unseren Daten optimiert). Kein Zeitdruck — je ein Schritt pro
Tag. Volle Paper-Befunde in §5. Auswertung bleibt Out-of-Sample im Herbst.

| Schritt | Was | Vorbedingung / Disziplin |
|---|---|---|
| **A** ⛔ **BLOCKIERT** | Binäre Zielvariable `squeeze_event` (Peak ≥ +30 % in 1 Handelswoche **UND** SI-Rückgang ≥ 20 %) **neben** `return_10d`. Adressiert den Paper-Kern „Häufigkeit ≠ Rendite-Edge" (§8). | **Coverage-Check 15.07. NEGATIV:** SI-Rückgang mit Gratis-Daten **nicht** messbar → **ZURÜCKGESTELLT**. Kein Feld-Bau, sondern Datenquellen-Projekt. Voller Befund in **§6i**. B/C brauchen A NICHT als Vorbedingung. |
| **B** ➡ **NÄCHSTER SCHRITT** | `si_velocity_pub` in die **3 Literatur-Buckets** (7–17 % / 17–25 % / > 25 % SI-Zuwachs) klassifizieren statt linear — nur diese drei waren im Paper signifikant. **Auswertbar OHNE A** (A ist blockiert, §6i — B braucht A nicht). | Buckets sind Literatur-fix, NICHT aus unseren Daten kalibriert. Additive Auswertungs-Spalte, kein Score-Effekt. |
| **C** | **Momentum als Haupthypothese** (`entry_past_return_5d` **positiv** = vorheriger Aufwärtstrend verstärkt), Reversal nur noch **kurzfristige Nebenhypothese**. Korrigiert die frühere „Reversal-Substrat"-Framing (§5). | Richtung vor der Auswertung fixiert (Paper: Momentum > Reversal). Kein nachträgliches Umdrehen. |
| **D** *(Ausblick, bedingt)* | `squeeze_probability`-Score nach Paper-Modell: die **validierten** Einzelfaktoren (SI-Buckets, Momentum, ggf. Ownership) zu einem Squeeze-**Wahrscheinlichkeits**-Score zusammenführen (rare-event-logit-artig, wie Svoboda et al.). Details + Deklaration unten. | **NUR falls A–C einzeln out-of-sample tragen.** Kein automatischer Folge-Schritt — eigene Anordnung nach belegten A–C-Befunden. |

**Backlog aus dem Paper** (§6): Institutional-Ownership-Faktor (dämpfend),
Crash-Filter (Marktrückgang > 3 % → Modell blind).

#### Schritt D — Deklaration + Bedingungen (KRITISCH, vor jedem Bau lesen)

**Was der Score IST und NICHT ist:** `squeeze_probability` misst die
**WAHRSCHEINLICHKEIT eines Squeeze-Ereignisses**, **NICHT die erwartete
Rendite**. Er ist ein **Attention-/Monitoring-Signal, KEIN Kaufsignal**
(Auffanglinie: **Häufigkeit ≠ Rendite-Edge** — man kann die Lottery-Chance
überzahlen; ein häufiges Ereignis mit schlechtem Auszahlungsprofil ist kein
Trade). Diese Trennung ist die Existenzbedingung des Scores, nicht eine
Fußnote.

**Bau-Bedingungen (alle vier zwingend):**

- **(a)** Nur bauen **NACHDEM** A, B, C **einzeln** out-of-sample getragen
  haben (nach unserer Erfolgs-Definition §5 — Holm-signifikant + CI-Untergrenze
  > 0.5 + Regime-robust). Kein Bau auf Punktschätzungen.
- **(b)** Gewichte aus den **VALIDIERTEN** Faktoren ableiten (Paper-Modell-
  Struktur), **NICHT** frei aus unseren Testdaten optimieren — das wäre die
  `monster_score`-Falle (§8e: 0.76 n=13 → 0.51 n=20).
- **(c)** **Separate, eigenständige Achse** neben dem bestehenden Setup-Score
  — kein Merge in `score()`, keine gegenseitige Rückkopplung (analog der
  Score-Konfidenz-Isolation, CLAUDE.md-Lint).
- **(d)** Im Frontend **klar als „Wahrscheinlichkeit, nicht Empfehlung"
  deklariert** — gleiche neutrale Sprache/Optik wie das Sammel-Felder-Status-
  Panel (#412), niemals als Kauf-/Rendite-Signal gerahmt.

### Erledigt (nicht mehr im Backlog)

- **Hypothese C (Peak-Ziel, 3 Schwellen +10/+30/+50 %) — ERLEDIGT
  04.07.2026.** Null belegt (0/6 Holm-Rejects). Nicht als offen führen.
  Wiedervorlage frühestens Herbst 2026 gemeinsam mit Setup-Re-Test.

### Bau-Kandidaten (nicht Bau-Priorität — konkurrieren nach Re-Test-Befunden)

Reihenfolge erst festlegen, wenn Re-Tests belegte / nicht belegte Edges
liefern. Kandidaten-Pool: Synthetische Utilization, Katalysator-Gating,
Exit-Mechanik-Spec, Reddit-Velocity, 424B-Dilution (§5).

---

## 5) STRATEGISCHE ROADMAP — Edge-Suche

### EDGE-BEFUND (Stand 11.07.2026): AUFFANGLINIE EINGETRETEN

**Kernbotschaft:** Über **drei** aufeinanderfolgende Auswertungstage
(30.06. Endpunkt-Return · 01.07. Exit-Timing · 04.07. Peak-Ziel) hat
**kein Prädiktor** eine belegte Edge nach Erfolgs-Definition (Holm-
signifikant UND Bootstrap-CI-Untergrenze > 0.5) gezeigt. Das Tool ist
**Attention-Router / Screener**, **kein Alpha-Generator**.

**Erfolgs-Definition (einmal fixiert, nicht aufweichen):** Ein Prädiktor
gilt als „belegte Edge" nur wenn (a) Holm-signifikant über der pre-
registrierten Klammer, **UND** (b) Bootstrap-CI-Untergrenze der AUC
> 0.5, **UND** (c) plausibel im Regime-Split reproduzierbar. Alles
darunter ist „kein belegter Effekt". Punktschätzung ist nie Beleg.

### 30.06.2026 — Endpunkt-Return (PR #394)

Setup / Earliness / Monster / ki_signal / Entry-Shadow / Conviction
(datenleer) / Velocity: **0/15 Holm-Rejects** bei k=15, Bonferroni-
Schwelle 0.00333. Vier Confounds beim ≥70-Setup-Test (pre-#346-Sample
91 %, Mai-Juni-Marktphase, in-sample, CI-Untergrenze knapp unter 0.5).
Earliness-Re-Test (n=78, AUC 0.77 aus 13.05.) fällt Out-of-Sample auf
0.47–0.52.

### 01.07.2026 — Exit-Timing Hypothese B (PR #395)

**B.1** (Endpunkt-Vergleich Score≥70-Bucket, n=110):
Δ(5d−10d) = +3.81 pp CI [+1.00, +6.63] roh-p 0.0057;
Δ(3d−10d) = +4.67 pp CI [+1.24, +7.84] roh-p 0.0073.
**Erster echter Punktschätzungs-Vorteil der gesamten Edge-Suche**, aber
nicht Holm-belegt (kleinstes p ~3× über Bonferroni-Schwelle 0.00179) →
Kategorie **„Hinweis, nicht belegt"**. Re-Test-Kandidat n ≥ 250,
~Ende September 2026.

**B.2** (Drawdown-Stop-Approximation): alle 16 Δ negativ, 4 Holm-
Rejects — feste Stops schaden systematisch (Trigger-Häufigkeit 87–95 %).
Approximations-Charakter dokumentiert.

### 04.07.2026 — Hypothese C: Peak-Ziel (0/6 Holm)

Details in §1. Drei Schwellen (+10 / +30 / +50 %) parallel getestet über
zwei Cluster-Läufe, k=6 gemeinsame Holm-Klammer. Kein Trennkraft-Nachweis
über alle drei Peak-Amplituden. **ERLEDIGT.**

### KOMBI-ZIEL H5 (aktiv verfolgt, vorab-registriert)

**Score × Katalysator × Reversal × SI-Velocity** als Interaktion — das
Wette-Ziel, für das das Tool ab jetzt Daten sammelt. **Vier Look-Ahead-
freie Sammel-Felder sind live:**

| Feld | Deploy | Sammel-Zweck |
|---|---|---|
| `max_gain_pct` (#397) | 02.07. | Peak-Amplitude im ≤10-Trading-Day-Fenster |
| `entry_past_return_5d` (#402) | 02.07. | Reversal-Substrat vor Entry |
| `days_to_earnings` (#404) | 04.07. | Katalysator-Nähe (point-in-time) |
| `si_velocity_pub` (#409) | 10.07. | SI-Änderungsrate über 3 publizierte Reports (Look-Ahead-frei via pub_date) |

**Auswertungs-Plan:** Out-of-Sample im Herbst 2026 bei ausreichend n
(≥ 40 pro Feld-Kombination), gepaart mit Score-Buckets. Feste Klammer
vor der Auswertung fixieren — keine nachträgliche Schmälerung. **Schwellen
literatur-abgeleitet** (Svoboda et al., PAPER-BEFUND unten: SI-Buckets
7–17/17–25/> 25 %, Momentum positiv), **NICHT** frei aus unseren Daten
optimiert.

**MASTER-SCORE-VORBEHALT:** Ein Master-Score (gewichtete Kombination
der vier Felder) wird **NUR NACH** belegter Kombi-Edge gebaut. Gewichte
werden **NICHT** frei aus Testdaten optimiert — das wäre die
`monster_score`-Falle (Overfitting auf kleines n, Zerfall bei
Out-of-Sample: 0.76 n=13 → 0.51 n=20 dokumentiert). **Out-of-Sample-
Pflicht.** Die Paper-Modell-Variante dieses Master-Scores ist **Schritt D**
des Verwertungsplans (§4) — ein `squeeze_probability`-Score, der bewusst
**Wahrscheinlichkeit statt Rendite** misst und erst nach belegten A–C-Befunden
gebaut wird.

### PAPER-BEFUND (Svoboda/Kapounek/Albrecht 2026, ausgewertet 15.07.)

**Quelle:** Svoboda/Kapounek/Albrecht, *North American Journal of Economics
and Finance* 2026, DOI `10.1016/j.najef.2026.102637`; frei als Working Paper
mendelu 104/2025. Untersucht **genau unser Setup**: 70 NASDAQ-Small-Caps
2018–2021, rare-event-Logit. Volltext ausgewertet 15.07.

**Kern-Erkenntnisse:**

- **ZIEL-DEFINITION:** Squeeze = Peak **> +30 % in 1 Handelswoche** UND
  **SI-Rückgang ≥ 20 %** UND Attention-Spike. Das Paper misst die
  **WAHRSCHEINLICHKEIT** (binär), **NICHT** den Return — das erklärt unsere
  bisherigen Nullbefunde direkt: **Häufigkeit ≠ Rendite-Edge** (§8). → Schritt A.
- **SI-SCHWELLEN-BUCKETS (stärkster Fund, nur diese 3 signifikant):**
  SI-Zuwachs **7–17 % → +78 %**, **17–25 % → +210 %**, **> 25 % → +10 %
  zusätzlich** (Squeeze-Wahrscheinlichkeit). → Schritt B (Buckets statt linear).
- **VORLAUF:** SI **+1 % einen Monat voraus → +3,9 %**; stärkster Effekt bei
  1 Monat, signifikant bis 6 Monate. Stützt den prospektiven `si_velocity_pub`-
  Pfad (Look-Ahead-frei via `pub_date`).
- **MOMENTUM > REVERSAL:** Effekt **stärker bei vorherigem AUFWÄRTStrend**;
  Reversal nur kurzfristig. → `entry_past_return_5d` **Haupthypothese POSITIV**
  (Momentum), Reversal nur Nebenhypothese. Korrigiert die frühere „Reversal-
  Substrat"-Framing im KOMBI-ZIEL oben. → Schritt C.
- **DÄMPFER / GRENZEN:** Institutional Ownership dämpft (**−6 % je +1 %**);
  **Marktkapitalisierung und Markttrend NICHT signifikant**; bei
  **Marktrückgang > 3 % ist das Modell blind** (systemische Krise). → §6-Backlog
  (Ownership-Faktor + Crash-Filter).

**Konsistenz zur Auffanglinie:** Das Paper belegt eine Edge auf **fremden
Daten** für ein **binäres Wahrscheinlichkeits-Ziel** — es hebt unsere
Return-Auffanglinie NICHT auf. Die Verwertung ist strikt **Out-of-Sample auf
unseren Daten mit literatur-abgeleiteten (NICHT frei optimierten) Schwellen**
— das ist genau der `monster_score`-Overfitting-Schutz (§8e). Erst ein
Out-of-Sample-Beleg nach unserer Erfolgs-Definition zählt.

### LITERATUR-KONSENS (S&P Global / State Street / diverse 2026)

Der Kombi-Ansatz **Constraint × Katalysator × Peak-Ziel gleichzeitig**
ist exakt der Kurs, den Profi-Häuser fahren. Einziger dokumentierter
Profi-Vorsprung ist **bezahlte Lending-Daten** (Utilization,
Cost-to-Borrow-Tick — Zugang $10–50k/Jahr). Gratis-Zugang gibt es nicht.
Synthetische Utilization (Substitute aus `si_short_ratio` × `avg_volume`)
ist im Bau-Kandidaten-Pool.

### BAU-KANDIDATEN (nach Re-Test-Befund, kein Termin, keine Priorität)

- Synthetische Utilization (Substitute für bezahltes Lending-Feed)
- Katalysator-Gating (nur trade wenn Katalysator im 7-Tage-Fenster)
- Exit-Mechanik-Spec (Trailing statt Fest-Stop, B.2-Konsequenz)
- Reddit-Velocity (post-30.06.-Kandidat, Attention-Signal)
- 424B-Dilution-Filter (Regel-Screen, nicht Score-Feature)

---

## 6) CODE-HYGIENE-BACKLOG (Status je Punkt — alle OFFEN, kein Termin)

### 6a. Alt-`finra_data.si_velocity` → `si_shares_per_day` umbenennen
**Status: OFFEN.** Nach PR #409 hat das Displayfeld einen irreführenden
Namen: `(newest_SI − oldest_SI) / len(history)` ist **Shares/Tag
absolut** (~90-Tage-FINRA-History), nicht „Velocity" im Sinne einer
Änderungsrate. Rename zu `si_shares_per_day`, eigener PR. Touch-Fläche
gemäß grep 09.07.: 7 aktive Reads (`generate_report.py:2308-2350,
2504-2505, 3346-3348, 5067-5080, 5603-5617, 5993, 11948-11949`);
CLAUDE.md-Sync; KI-Boost-Konsument. Kein Alt-Backtest-Feld betroffen
(Feld wurde nie ins Backtest-Schema geschrieben). Blast-Radius mittel.

### 6b. 5 andere bewegliche US-Feiertage algorithmisch berechnen
**Status: OFFEN.** Nach PR #407 ist nur **Karfreitag** algorithmisch
im Set (Meeus-Osterformel). Fünf weitere bewegliche Feiertage
(**MLK Day**, **Presidents Day**, **Memorial Day**, **Labor Day**,
**Thanksgiving**) sind weiterhin **hartkodiert** bis 2027 einschließlich.
Laufen 2028 aus → derselbe Wartungs-Bombe-Effekt wie Karfreitag vor #407.
Kandidat für Wartungs-PR: analog #407 mit den etablierten „Nth-Weekday-
of-Month"-Formeln. Range 2020–2050. Kein Trading-Wert, aber
Vorbeugungs-Hygiene.

### 6c. News-/FDA-Katalysator (Look-Ahead-Quelle ungeklärt)
**Status: OFFEN.** Nicht implementiert. Voraussetzung für Aktivierung
ist eine belegbar **point-in-time** verfügbare News-/FDA-Announcement-
Quelle (heutige News-Feeds sind revisionsanfällig; FDA-RSS ist zwar
zeitgestempelt, aber Kalender-Vorschauen nicht point-in-time-sauber).
Nur zulässig, wenn die Quelle beweisbar zum Report-Zeitpunkt existierte.
Vor dem Bau: Diagnose-Auftrag „welche Quelle ist point-in-time?".

### 6d. Reversal-Backfill Stufe B/C für Hypothese A
**Status: OFFEN.** PR #402 ist Stufe A (Live-Vorwärts). Stufe B
(einmaliger yfinance-Backfill für die ~420 v4-Alt-Records) wäre analog
zum `backfill_max_gain_pct.py`-Muster möglich, aber `fetch_start =
earliest_edate − 14 Kalendertage`. Nur bauen wenn Hypothese A explizit
angeordnet ist zu testen. Beschleunigt die Auswertung von „~Ende Aug"
auf „~Mitte Juli", wenn gewollt.

### 6e. yfinance-Cap-Aufhebung nach 1.5.x-Stabilisierung
**Status: OFFEN.** PR #403 hat `yfinance>=1.4.1,<1.5` gecappt. Sobald
1.5.x in einem Test-Env oder Community-Consensus als stabil belegt ist,
Cap auf `<1.6` lockern (schrittweise) oder komplett auf `>=1.5` öffnen.
Kein Termin — wartet auf externes Signal.

### 6f. v1/v2-Render-Pfad → reines Jinja
**Status: OFFEN (niedrig).** `generate_html_v2()` delegiert am Ende an
`generate_html_v1()`; v1-Löschung erfordert `templates/page.jinja` +
`_wl_full_card_html`-Umbau. Details im Architektur-Anker unten und in
`CLAUDE.md`. Kein Trading-Wert, reine Aufräum-Hygiene.

### 6g. Institutional-Ownership-Faktor (Paper-Dämpfer)
**Status: OFFEN (Paper-abgeleitet 15.07.).** Svoboda et al. finden: hoher
Institutional-Ownership **dämpft** die Squeeze-Wahrscheinlichkeit (**−6 % je
+1 %**). Kandidat als zusätzlicher Auswertungs-Faktor. Datenquelle yfinance
`heldPercentInstitutions` — **Vorbehalt: potenziell stale** (nicht point-in-
time, quartalsweise 13F-Latenz). Vor Nutzung read-only klären, ob der Wert
überhaupt zeitnah genug ist; sonst nur als grober Dämpfer-Kontext, nicht als
scharfer Score-Faktor. Kein Score-Effekt ohne Out-of-Sample-Beleg.

### 6h. Crash-Filter / Markt-Blind-Zone (Paper-Grenze)
**Status: OFFEN (Paper-abgeleitet 15.07.).** Paper: bei **Marktrückgang > 3 %**
ist das Squeeze-Modell **blind** (systemische Krise überlagert idiosynkratische
Squeezes). Kandidat: Tage mit Markt-Tagesrückgang > 3 % (z. B. `^GSPC`) aus der
Auswertung **ausschließen** (Regel-Screen, kein Score-Feature). Marktkap +
Markttrend waren im Paper **nicht** signifikant — also kein Regime-Score, nur
der harte Crash-Ausschluss.

### 6i. Paper-Schritt A (`squeeze_event`) — BLOCKIERT durch fehlende SI-Zeitreihe
**Status: ZURÜCKGESTELLT (Coverage-Check 15.07. negativ).** Schritt A des
Verwertungsplans (§4) ist mit den vorhandenen Gratis-Daten **nicht baubar**:

- **Keine ausstehende-SI-Zeitreihe.** Es existieren nur **Entry-Snapshots**
  (`short_float` via yfinance `shortPercentOfFloat`, Einzelwert/Record). yfinance
  UND stockanalysis liefern nur den **aktuellen** Wert — **nicht** settlement-
  datierte Historie, also **nicht rekonstruierbar** für „~2–6 Wochen nach Entry".
- **Namens-Falle:** was intern `finra_data.history` / „short_interest" heißt, ist
  FINRA **Reg SHO Daily Short VOLUME** (`CNMSshvol`-Dateien), **NICHT** die
  ausstehende Short-Position. Volumen-Rückgang ≠ Shorts covern.
- **Coverage heute = 0**, Backfill der 470 v4-Records **unmöglich** (keine
  time-queryable Quelle). Damit ist der **SI-Rückgang ≥ 20 %** (Kern der Paper-
  Definition) **nicht messbar**.
- **Peak-only nicht abspecken:** ein reines Peak-≥30 %-Binär = **widerlegte
  Hypothese C** (04.07., 0/6 Holm). Ohne SI-Rückgang kollabiert `squeeze_event`
  in das bereits falsifizierte Peak-Ziel → null neue Information.

**Konsequenz:** Schritt A ist **kein Feld-Bau, sondern ein DATENQUELLEN-PROJEKT**
— die offizielle **FINRA-bimonatliche Short-Interest-Datei** (settlement-datiert)
integrieren + SI-by-settlement persistieren + **forward-only** sammeln; n ≥ 40
erst **~2–3 Monate nach Bau**. Die `pub_date`-Mechanik (#408, settlement + 7
Handelstage) wäre das richtige Look-Ahead-Werkzeug, ist aber **gegenstandslos
ohne SI-Serie**. Alternativ: bezahltes tägliches SI-/Utilization-Feed (der in §5
dokumentierte Profi-Vorsprung, $10–50k/Jahr). **Bau erst bei bewusster
Anordnung.** Die Peak-Seite (längeres Fenster) wäre via yfinance machbar — sie
ist NICHT der Blocker; der Blocker ist ausschließlich die SI-Serie.

**Schritte B (SI-Buckets aus `si_velocity_pub`) + C (Momentum-Framing) sind
UNBERÜHRT** und laufen ohne A weiter (§4).

---

## 7) ARCHITEKTUR-ANKER

### 7a. Analyse-Persistenz-Felder — Look-Ahead-Konvention

Vier Felder im `backtest_history.json` sind **reine Analyse-/Outcome-
Persistenz**, **NIEMALS Score-Feature aus dem Backfield lesen**
(Look-Ahead-Konvention, ursprünglich in PR #402 einfriert):

| Feld | PR | Zweck | Live-Score-Read (falls je nötig) |
|---|---|---|---|
| `max_gain_pct` | #397 | Peak im ≤10-TD-Fenster | Rolling-Update-Slice, nicht Backfill-Feld |
| `entry_past_return_5d` | #402 | Reversal-Substrat | `s["close_5td_before_entry"]` (Enrichment) |
| `days_to_earnings` | #404 | Katalysator-Nähe | `s["earnings_days"]` (Enrichment) |
| `si_velocity_pub` | #409 | SI-Rate über 3 Publikations-Reports | `s["finra_data"]["history"]` mit eigenem `_compute_si_velocity_pub`-Aufruf |

**Grund:** Backgefüllte Alt-Records würden Trainings-/Test-Overlap
erzeugen, sobald ein Score sie liest → Overfitting auf das Backfill-
Sample, kein echter Out-of-Sample-Nachweis mehr. Verankert per Test in
allen vier Mock-Tests (Konsumenten-Isolations-Klasse; grep über
`generate_report.py`/`ki_agent.py`/`health_check.py` muss leer bleiben).

### 7a-bis. `config.COLLECT_STATUS_FIELDS` — Display-Reads von Backtest-Feldnamen (Weg-A-Muster, #412)

Das Sammel-Felder-Status-Panel (#412) muss die Backtest-Feldnamen (`si_velocity_
pub` etc.) **anzeigen** — aber die Look-Ahead-Isolations-Guards (§7a) verbieten
per Regex-/Literal-Grep, dass diese Namen als Dict-Key-Literale in
`generate_report.py` auftauchen. **Lösung (Weg A, von Easy gewählt statt Guard-
Lockerung):** Feldnamen + Labels + Status leben in `config.COLLECT_STATUS_FIELDS`
und werden zur Render-Zeit als JS-Konstante `_COLLECT_STATUS_FIELDS` injiziert
(`json.dumps`) → **kein** Feldnamen-Literal im Score-Pfad-Source, Guards bleiben
unverändert grün. **Muster für JEDEN künftigen Display-Read von Backtest-
Feldnamen:** Namen nach `config.py` (config ist nicht guard-überwacht und nennt
die Felder ohnehin in `S10_OBSERVED_FIELDS`), von dort injizieren — Guards NICHT
lockern. Verankert per Test-Assertion A8 in `mock_test_collect_status_panel.py`.

### 7b. `scripts/business_days.py` — Handelstags-Arithmetik

Pure-stdlib-Modul mit `next_trading_day(d)` und
`finra_publication_date(settlement_date, offset=None)`. Nutzt
`config.US_MARKET_HOLIDAYS` als **Single-Source-of-Truth**. Trivial-
symmetrisch zu `scripts/cluster_purge.py:previous_trading_day` (bewusst
kein Cross-Import — `cluster_purge` hat strikte Reihenfolge-Disziplin:
„kein Import in `generate_report`/`ki_agent`/`health_check`/
`backtest_history`" für die 30.06.-Auswertung).

### 7c. `finra_publication_date` = settlement + 7 US-Handelstage

FINRA Rule 4560 (SI-Reports werden 7 Handelstage nach Settlement
öffentlich). Konstante `FINRA_PUB_OFFSET_BUSINESS_DAYS = 7` in `config.
py` — zentral anpassbar (SR-FINRA-2026-012 plant höhere Frequenz und
möglicherweise kürzeren Delay).

### 7d. Good Friday algorithmisch (Meeus) — Doppel-Spiegel

`config.US_MARKET_HOLIDAYS` (Python) UND `US_HOLIDAYS`-Array in
`generate_report.py` (JS, embedded als IIFE mit `_goodFriday(year)` +
`_GOOD_FRIDAYS`) müssen **bit-identisch** bleiben. Verankert im Test
`mock_test_good_friday`. Alle sonstigen Kalender-Änderungen an
US-Feiertagen: beide Spiegel synchron pflegen.

### 7e. Auswertungs-Chain (Stats-Helpers + cluster_purge)

- `stats_helpers.py` (PR #389 AUC / Mann-Whitney-U mit Tie-Korrektur +
  Yates-Stetigkeitskorrektur; PR #390 Bonferroni + Holm-step-down mit
  Label-Rückordnung) — pure stdlib, fixture-only-Test.
- `cluster_purge.py` (PR #391 `previous_trading_day` holiday-robust +
  `classify_cluster_records` mit `is_cluster_followup`-Flag für
  Doppel-Lauf-Disziplin) — fixture-only, Reihenfolge-Disziplin-Docstring
  (kein Import in `generate_report`/`ki_agent`/`health_check`/
  `backtest_history` — der Grund, warum `business_days.py` eigenständig
  ist).

### 7f. Schema v4 strikt additiv — kein Bump

`backtest_schema_version` bleibt **4**. Neue Felder gehen **immer** in
`S10_OBSERVED_FIELDS` (Whitelist bekannter Felder, keine MUSS-/LAG-
Checks). Sonst feuert `_s10_check_unknown_fields` am ersten Record mit
neuem Feld ein dauerhaftes WARN (Lehre #388). Für rein optional-leere
Felder (`None` legitim, z. B. junge Ticker ohne SI-Coverage): NICHT in
MUSS/LAG, sondern nur OBSERVED.

### 7g. Render-Pfad v1/v2 (unverändert seit CLAUDE.md-Doku)

`generate_html_v2()` **delegiert** am Ende an `generate_html_v1()` —
rendert nur Karten-Snippets, Outer-Page (Header, Watchlist, Backtesting,
Chat-Glue, JS, Footer) kommt weiter aus v1. **Wer v1 löscht, killt v2
mit.** Vollständige Migration braucht `templates/page.jinja` + Umbau
von `_wl_full_card_html()`. Details in `CLAUDE.md` → §v1/v2 Render-Pfad.

---

## 8) LESSONS

*(Neueste zuerst: 8j–8m vom 11.–15.07. stehen als eigener Block oben; die
etablierten 8a–8i darunter — inkl. 8h/8i Paper-Lehren vom 15.07.)*

### 8j. Merge-Whitelist-Bug-Klasse (Lehre #411, 11.07.)

Ein Feld kann in `_hist_stats` **korrekt berechnet** und im Append **korrekt
gelesen** werden — und trotzdem dauerhaft `None` sein, wenn der dazwischenliegende
`c.update`-Enrichment-Merge (`generate_report.py` `def main()`) den Key **nicht in
seiner expliziten Key-Whitelist** führt und ihn fallenlässt. `entry_past_return_
5d` war so 50/50 None. **Regel:** bei jedem neuen enrichment-getragenen Feld auch
den `c.update`-Merge prüfen — und der **Test muss den MERGE assertieren**, nicht
nur Compute + Append (die alten F2/F3-Tests prüften nur `_hist_stats`/Stock-Dict
und ließen den Bug durch). **Präzedenz:** identische Klasse wie der historische
`hist_5d`-Merge-Gap (Kommentar direkt daneben im Merge, Diagnose 21.05.).

### 8k. Look-Ahead-Guards vs. legitime Display-Reads (Lehre #412, 11.07.)

Wenn ein **Anzeige**-Feature Backtest-Feldnamen referenzieren muss, aber die
Look-Ahead-Isolations-Guards jedes Namens-Literal im Score-Pfad-Source verbieten:
**Feldnamen nach `config.py` auslagern und als Render-Konstante injizieren**
(Weg A, §7a-bis) — **NICHT** die Guards lockern. Guard-Sinn bleibt scharf, Display
funktioniert. Der Guard konnte Display- vs. Score-Read nicht unterscheiden; die
Config-Injektion umgeht das sauber, statt den Schutz aufzuweichen.

### 8l. Peak-only ≠ Squeeze — die Covering-Komponente ist der Kern (Lehre #417, 15.07.)

Der Paper-`squeeze_event` ist Peak ≥30 % **UND** SI-Rückgang ≥20 %. Lässt man die
SI-Rückgang-(Covering-)Komponente weg (weil die SI-Zeitreihe fehlt, §6i),
**kollabiert `squeeze_event` in ein reines Peak-≥30 %-Binär = die bereits
widerlegte Hypothese C** (0/6 Holm). Also: **nicht abspecken** — ohne die
Covering-Komponente misst man nichts Neues. Der SI-Rückgang IST das
Unterscheidungsmerkmal echter Squeezes vom bloßen Kursspike.

### 8m. „short_interest" intern = Daily Short VOLUME, nicht Position (Nomenklatur-Falle, 15.07.)

Was im Code `finra_data.history` / „short_interest" heißt, ist FINRA **Reg SHO
Daily Short VOLUME** (`CNMSshvol`-Dateien) — das Short-Sale-Volumen des Tages,
**NICHT** die ausstehende Short-Position. Ein Rückgang des Tages-Volumens ≠ Shorts
covern. Bei jeder SI-Analyse zuerst klären, **welche** Größe eine Quelle liefert
(Volumen vs. ausstehende Position vs. % of float). Die echte ausstehende SI liegt
nur als bimonatlicher yfinance-Snapshot vor (keine Zeitreihe, §6i).

### 8a. S10_OBSERVED_FIELDS = Whitelist bekannter Felder (Lehre #388)

Additive neue Felder in `backtest_history.py` MÜSSEN in
`config.S10_OBSERVED_FIELDS`, sonst feuert `_s10_check_unknown_fields`
am ersten geschriebenen Record dauerhaft WARN. Guardian-Blocker-Fix in
`c0f53f7` hat das etabliert. Bei jedem neuen Feld: OBSERVED-Whitelist
ergänzen (nicht MUSS/LAG, wenn None legitim).

### 8b. Pinless Deps = latente Wochenend-Bombe (PR #393 → #403)

`yfinance==1.4.1 → 1.5.1` Minor-Sprung im Runner-Image führte zu
SIGSEGV Exit-139 im Batch-Fetch (Run #818). Fix in #393 (Hard-`==`),
Verfeinerung in #403 (Cap `>=1.4.1,<1.5` — erlaubt Bugfix-Nachfluss,
sperrt Minor-Sprung). Grundregel: **transitive Deps mit expliziten
Caps pinnen**, sonst gehen Wochenenden mit fremden Auto-Updates verloren.

### 8c. Erfolgs-Definition VOR der ersten Zahl (30.06.-Fenster)

Vor der Auswertung fixieren: Holm-signifikant UND CI-Untergrenze > 0.5.
Sonst „kein belegter Effekt", Punktschätzung nie Beleg. Kein
Schönrechnen. Verankert im 30.06./01.07./04.07.-Befund (§5).

### 8d. Edge-Schönrechnen-Schutz BIDIREKTIONAL

Ein invertierter Befund (AUC < 0.5 in eine Richtung) ist **nicht**
automatisch handelbare Short-Edge. Gleiche Erfolgs-Definition gilt
beidseitig. Sonst schmuggelt man sich Short-Edge über die Hintertür in
eine Long-Edge-Analyse.

### 8e. Kleine-n-Zerfall (`monster_score`-Falle)

`monster_score`-AUC ging von 0.76 (n=13) auf 0.51 (n=20) — Scheinpräzision
bei kleinem n. Konsequenz: Master-Score-Gewichte NIE frei aus Testdaten
optimieren. Out-of-Sample-Pflicht (§5).

### 8f. Refactor-Konsumenten-Falle: IMMER greppen VOR Namens-/Struktur-Änderung

- PR #407: JS-Spiegel `US_HOLIDAYS` wäre bei „nur Python fixen" gerissen
  worden — Guardian ROT-Blocker gefunden, JS-Meeus in `b87474a` gefixt.
- PR #409: STOPP-Meldung wegen Naming-Kollision `si_velocity` (alt,
  Display) vs. neu (Backtest, Look-Ahead-Filter). Weg A gewählt →
  `si_velocity_pub` als klarer Suffix.

**Regel:** bei Namens-/Struktur-Änderung ZUERST grep über alle
Konsumenten (Python + JS + Frontend + Backtest + Doku); dann
STOPP-Meldung mit sauberen Weg-A/B-Optionen wenn Kollision.

### 8g. Look-Ahead-Disziplin bei Katalysator / SI

- **Katalysator** (`days_to_earnings` #404): point-in-time-Fetch AM
  Report-Tag zwingend. Kein Backfill möglich (heutiger Fetch ≠
  damaliger Termin).
- **SI-Velocity** (`si_velocity_pub` #409): `pub_date`-Filter
  Pflicht — nur Reports mit `pub_date ≤ entry_date`. `pub_date`-
  Fundament in PR #408 (settlement + 7 Handelstage, holiday-robust).
- **Trainings-/Test-Overlap-Verbot:** kein Analyse-Feld darf im
  Live-Score-Read auftauchen. Verankert per Konsumenten-Isolations-
  Test in allen vier Mock-Tests.

### 8h. Häufigkeit ≠ Rendite-Edge (Paper-Lehre 15.07.)

Svoboda et al. (2026) misst **Squeeze-WAHRSCHEINLICHKEIT** (binär: Peak
> +30 % in 1 Woche + SI-Rückgang ≥ 20 %), **nicht** den Return — und findet
dort signifikante SI-Bucket-Effekte (7–17 % → +78 %, 17–25 % → +210 %,
> 25 % → +10 %). Unsere gesamte 30.06./01.07./04.07.-Edge-Suche testete
dagegen **Return** (`return_10d` / Peak-Amplitude) und fand 0 belegte Edges.
**Lehre:** ein Prädiktor kann die **Ereignis-Häufigkeit** trennen, ohne die
**Rendite** zu trennen — das sind zwei verschiedene Ziele. Deshalb Schritt A
(binäres `squeeze_event` neben `return_10d`). **Aber:** ein binärer Beleg auf
fremden Daten ist KEINE handelbare Rendite-Edge — die Return-Auffanglinie
bleibt bis zum Out-of-Sample-Beleg bestehen.

### 8i. Crash-Blind-Zone + Ownership-Dämpfer (Paper-Grenzen 15.07.)

Paper: bei **Marktrückgang > 3 % ist das Modell blind** (systemische Krise);
**Institutional Ownership dämpft** (−6 % je +1 %); **Marktkap + Markttrend
nicht signifikant**. Konsequenz für jede künftige Squeeze-Auswertung:
Crash-Tage ausschließen (§6h), Ownership als Dämpfer-Kontext (§6g, Daten-
Staleness-Vorbehalt), keinen Marktkap-/Trend-Score bauen (im Paper wertlos).

---

## 9) ARBEITSWEISE-ANKER (KRITISCH für neue Session)

**CLAUDE.md** führt einen `Arbeits-Regeln für Claude Code`-Abschnitt
mit vier Prinzipien (Vorsichts-Prinzip, Trading-Wert-Filter, Zeit-
Schätzungs-Regel, Uhrzeit-Regel). Zusätzlich stehen dort:
- **Auto-Merge-Regel + Ausnahmen** (`§Auto-Merge-Regel`) — Liste der
  manuell-merge-pflichtigen PR-Klassen.
- **squeeze-guardian-Routine** (`§squeeze-guardian`) — Bonus vor manuellem
  Merge, kein Gatekeeper.
- **PR-Status-Meldung** (`§PR-Status-Meldung nach Push`) — kanonische
  Klassifikations-Tabelle.
- **v1/v2-Render-Pfad** (`§v1/v2 Render-Pfad`).
- **Score-Methodik-Sync-Regel** (`§Score-Methodik-Sync-Regel`).

Die folgenden Regeln müssen zusätzlich explizit hier stehen, weil sie
in CLAUDE.md nicht oder nicht vollständig geführt werden — sie prägen
den Session-Modus so stark, dass eine neue Session sie ab Prompt 1
anwenden muss:

### 9a. Diagnose-first bei allem mit Schema-/Score-/Daten-Impact

Vor jeder nicht-trivialen Änderung (mehr als 1–2 Zeilen Refactor,
Schema-Erweiterung, Logik-Touch): **read-only Diagnose zuerst.** Der
User löst dies häufig mit „DIAGNOSE-AUFTRAG (READ-ONLY) — Nichts ändern,
nur lesen/greppen, mit Pfad/Zeile belegen" aus. Bei diesem Trigger:
**null Code-Change**, nur Belege liefern. Erst danach — auf explizite
Anordnung — kleiner Bau-Schritt mit Verifikation zwischen den Schritten.

**Vor jeder Namens-/Struktur-Änderung: alle Konsumenten greppen** (§8f).
Bei Kollisions-Verdacht STOPP-Meldung mit sauberen Weg-A/B-Optionen —
NIEMALS silent umbenennen.

### 9b. „absolute Vorsicht, kein Risiko" — Prompt-Signatur des Users

Jeder Auftrag des Users trägt „absolute Vorsicht, kein Risiko" als
Signatur. Das ist die verbindliche Priorität: bei Zweifel → STOPP + kurze
Rückfrage, NICHT auf Annahmen aufbauen. Silent-Umbauen ohne Belegung
ist verboten.

### 9c. Exzellenz-Selbstprüfung vor „Ready"-Meldung (Build-PRs)

Der User verlangt vor jeder Ready-Meldung eine **Exzellenz-Selbstprüfung**
mit belegbaren Punkten (nicht Behauptungen):

1. **Widersprüche** — Diff-Beleg dass nur der beabsichtigte Scope
   getroffen wird (bei Doc-only: kein Logik-Touch; bei additiv:
   ein Feld / eine Signatur).
2. **Nachweise** — Kern-Verhalten mit **Testausgabe** belegen, nicht
   behaupten (LOOK-AHEAD-Filter greift → tatsächlichen `filter-value`
   vs. hypothetischen `leak-value` ausgeben).
3. **Fragile Annahmen** — None-Semantik, Edge-Cases, Division-Guards,
   Timezone-Semantik explizit durchgehen.
4. **Determinismus** — Tests grün, mehrere Läufe identisch, CI-Runner
   grün, AST-Compile grün.

Auftrags-Vokabel „Anspruch: exzellent" heißt genau das.

### 9d. Manueller Merge vs. Auto-Merge — Klassifikations-Sicht

Detaillierte Liste in `CLAUDE.md` (`§Auto-Merge-Regel`). Kurzform:
- **Manuell**: neue Workflows, neue JSON-Schemas, neue API-Integrationen,
  Score/Conviction/Filter/Exit-Logik-Änderungen, Backtest-Schema-Touch
  (auch additiv).
- **Auto**: Doku (CLAUDE.md, SESSION_HANDOVER), Frontend-Text-Tweaks,
  CSS, Helper-Refactor, Bugfixes ohne Schwellen-Änderung, State-Logging,
  Mock-Test-Erweiterungen, backward-compat-Aliase.

**Im Zweifel: manuell.** Kein automatisches Verschieben eines
manuell-merge-pflichtigen PR-Typs in die Auto-Kategorie „weil klein".

### 9e. squeeze-guardian-Zweitblick

Vor manuellem Merge **empfohlen** (Bonus, kein Gatekeeper). Claude
initiiert den Aufruf explizit via Task/Agent-Tool — der PostToolUse-Hook
ist ein `echo`-Reminder, kein Auto-Spawn. Mensch entscheidet nach
Guardian-Befund. Nicht-deterministisch (gleicher Diff → ggf. andere
Findings). Ersetzt NICHT Easy's Bedeutungs-Validierung.

### 9f. Rate-Limit / API-Fehler beim Merge

Kein Retry-Loop bei GitHub-Rate-Limits im Merge-Pfad. Meldung an User;
Mensch merged per iPhone / anderer Session. Retry-Loop nur bei
Netzwerk-Push-Fehlern (2s/4s/8s/16s Exponential-Backoff, max 4).

### 9g. Reihenfolge-Disziplin Edge-Auswertung

**Erst sammeln, dann auswerten.** Keine Edge-Zahl vorziehen bevor n
das vor-registrierte Ziel erreicht (§4). Erfolgs-Definition steht **vor**
der Zahl. Multiple-Testing-Klammer (Bonferroni oder Holm) VOR der
Auswertung fixieren, nicht nachträglich schmälern.

### 9h. Rollen + Uhrzeit

- **Claude:** Diagnose + Prompt-Formulierung + Einordnung. **Mensch:**
  Entscheidung + Merge.
- **Zeit:** Claude hat nur Datum („Today's date is …"), kein
  Uhrzeit-Zugriff. Vor zeitabhängigen Aussagen (Cron-Slot-Wartezeit,
  „läuft der Workflow heute schon?") **immer den User fragen** oder
  `date -u` im Bash prüfen. Nie raten.

### 9i. Session-Handover-Regel

Bei „Gute Nacht" / „Feierabend" / „Bis morgen" (oder Varianten): Claude
aktualisiert `SESSION_HANDOVER.md` automatisch. Struktur:
- Chronologische Commit-Liste
- Aktive Position (aus Gist / app_data)
- Verifikation ausstehend
- Geplante Aufgaben
- Optional / niedrig priorisiert
- Architektur-Anker (nur wenn diese Session welche eingeführt hat)

Direkt auf `main` committen mit Message `docs: handover update after
session JJJJ-MM-TT`. Bei größeren Session-Übergängen (User-Auftrag):
**alle 9 Blöcke** komplett neu, aus Repo/Logs belegt, nichts erfunden.

---

**Ziel dieses Dokuments:** neue Session arbeitet ab Prompt 1 im selben
Modus, ohne Wieder-Etablierung. Widersprüche zwischen SESSION_HANDOVER
und CLAUDE.md → CLAUDE.md gewinnt (dort steht die Codebase-Wahrheit;
hier steht der Projektstand).
