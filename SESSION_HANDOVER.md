# SESSION_HANDOVER.md — Stand 09.10.2026 (Woche 15.08.–09.10.: NaN-Härtungskette + Push-Gating unvalidierter Trading-Signale + H5/Netto/SPY-Vorabregistrierungs-Ausbau + Open-Items-Tracker + Health-Check-Wochendigest + MFE/MAE-Bestandsaufnahme + §4-Diskrepanz geklärt + Finviz-v111-Parser-Fix + Handover-Staleness-CI-Check + hist_5d-Diagnose-Kette (Gap-Log + Verschiebe-Fix, S10-crit seit 03.10. abgeklungen) + NYSE-empty-Detail-Logging + Open-Items-Oktober-Rundgang + US-Feiertage algorithmisch + SI-Timestamp-Logging + NaN-Guard-Symmetrie entry_past_return_5d + Preis-Merge-Guard-/NYSE-empty-Diagnosen + Block-1-Autonomie-Regel)

**Zweck:** vollständige Übergabe an eine **neue Code-Session ohne Kontext der
alten**. Dieses Dokument + `CLAUDE.md` müssen zusammen ausreichen, um am
Projektstand direkt weiterzuarbeiten. Reine Doku, kein Logik-Touch.

**Ergänzend (seit 22.09.2026):** `open_items.json` im Repo-Root hält
strukturierte offene Diagnose-/Beobachtungspunkte (Status
`offen`/`beobachtet`/`erledigt`) — getrennt von der Prosa hier, aber
zusammen mit diesem Dokument zu konsultieren (CLAUDE.md-Abschnitt
„`scripts/lint_open_items_consistency.py`"). Ein mechanischer CI-Check
schlägt an, wenn ein Punkt dort beim Aktualisieren ersatzlos
verschwindet, ohne explizit auf „erledigt" gesetzt worden zu sein —
genau der Bug-Modus, der diese Datei nötig machte. **Wichtig:** auf
einem ad-hoc-PR ist der Check präventiv-sichtbar VOR dem Merge; beim
„Gute Nacht"-Direct-main-Commit (der diese Datei hier ersetzt) feuert
ein zweiter, push-getriggerter Workflow **erst NACH** dem Commit — rein
detektiv, verhindert den Verlust nicht, macht ihn nur sichtbar. Ein
roter Check-Run auf einem main-Commit braucht also einen Follow-up-Fix.

**Datums-Basis (belegt, nicht Erinnerung):** Repo-Stand **27.09.2026**.
**15.08.–27.09.2026** (PRs #533–#566, 33 PRs, alle git-belegt gemergt,
thematisch gruppiert — volle Details unten unter „## 1) HEUTE
IMPLEMENTIERT"): **⚠ Push-Gating unvalidierter Trading-Signal-Pushes**
(`#544`/`#545`, 06.09. — **5 Push-Typen deaktiviert**, siehe Hervorhebung
im Log) · **NaN-Härtungskette** (Gruppe A, mehrwöchig: `#533`–`#536` +
`#557`–`#559` + `#561`) · **Vorabregistrierungs-Ausbau** (H5 finalisiert
`#548`, Netto-/Haircut-Felder `#549`, SPY-Benchmark `#554`, FINRA-
Wiedervorlage `#543`) · **NYSE-/Reg-SHO-Diagnose-Kette** (`#538`/`#539`/
`#542`/`#546`/`#550`/`#551`) · **Exit-Pipeline-Fix + Frontend-/Anzeige-
Fixes** (`#537`/`#540`/`#552`/`#553`) · **Doku-/Backlog-Pflege**
(`#541`/`#555`/`#556`) ·
**Open-Items-Tracker** (`#560`) · **Health-Check-Wochendigest** (`#562`) ·
**MFE/MAE-Bestandsaufnahme** (§6q, `#563`) · **Finviz-v111-Parser-Fix**
(`#565`) · **Open-Items-Nachtrag** (16 Punkte, `#566`). **§4-Zähler-
Diskrepanz vom 18.09. GEKLÄRT** (Ursache: reiner Zeitversatz zwischen
zwei Zählzeitpunkten, kein Logik-Bug — siehe §4-Protokolleintrag
27.09.2026); aktueller Live-Stand **n=144/250**, nachgerechnet
**27.09.2026, 07:16:50 UTC** direkt gegen `matured_backtest_export.jsonl`.

**Vorheriger Bogen — Woche 03.–08.08.2026** (PRs #500–#512, alle git-belegt
gemergt): Prune-Konsequenz-
Doku (`40565b4` #500) · **Matured-Export** append-only/prune-immun (`a01acb2`
#501) + Reife-Gate #2 `days_old>14` (`6bdf517` #503) · **Guardian-Pflichtregel**
in `CLAUDE.md` (`b19c3f2` #502) + Alt-Stellen angeglichen (`3e96391` #504) ·
**§4-Exit-B.1-Vorabregistrierung EINGEFROREN 05.08.** (`a4fcbcd` #505) + forward-
Disambiguierung (`bdf84f2` #506) · **Earnings-Sofort-Push „Earnings-Alert"** statt
„Squeeze Alert" (`fdf885f` #507) · **Panel 90-Tage-Rollfenster-Ehrlichkeit**
(`e9a4245` #508) · **§4-Re-Test-Zähler** im Health-Check-Push (`d6c51b0` #509) ·
**inst_ownership-Key-Fix** `heldPercentInstitutions` nach Wegwerf-Probe (`bcf350d`
#510-Probe → `2ad9d9e` #511-Cleanup → `5c67fca` #512-Fix). **Vorheriger
Bogen 16.–17.07.:** am **16.07.** die **entry_past_return_5d Stufe-B-Backfill-Kette**
— **#442** (Backfill-Skript + Workflow, Merge `cd6947a`), **#443** (Gate-Diff-
Verteilungs-Logging, Merge `344e23d`), **#444** (Gate begründet kalibriert, Merge
`610349c`); am **17.07.** der **LIVE-LAUF DURCH** (`5d8e78d` — **465/470 Records
gefüllt**, Gate PASS, Manifest mit 465 Einträgen). Davor 16.07.: **#440** (Merge
`53b72d1` / feat `e90fd5f` — `ki_sentiment_source`-Fallback-Flag); 15.07.: **#436**
(Bootstrap-Shell Phase 1, `4270cce`/`77b42d6`), **#437** (si_velocity-Rename,
`5788485`/`a8c5c7f`), **#438** (Einheiten-Fix Frontend, squash `ae45803`) — alle
git-belegt.

*(Hinweis für die nächste Session: alle Hashes/Zahlen hier aus dem Repo verifiziert
[`git log`, `git show --stat 5d8e78d`, Manifest-Länge 465], nicht aus Erinnerung —
Präzedenz-Fehler früherer Handover [„Stand 15.07." bei 12.07.-PRs] so vermieden.)*

Struktur (9 Blöcke): (1) Heute implementiert · (2) Aktive Positionen ·
(3) Verifikation · (4) Wiedervorlagen · (5) Strategische Roadmap ·
(6) Hygiene-Backlog · (7) Architektur-Anker · (8) Lessons · (9) Arbeitsweise-
Anker.

---

## 1) HEUTE IMPLEMENTIERT (chronologisch, mit Hashes)

### 15.08.–27.09.2026 — Sechs-Wochen-Nachtrag (33 PRs, thematisch gruppiert)

*(Diese Sektion schließt eine Lücke: Block 1 hatte zuvor bei PR #532/
15.08.2026 aufgehört, obwohl seither 31 weitere PRs gemergt wurden — eine
read-only Konsistenz-Diagnose 27.09.2026 hat das aufgedeckt. Alle Hashes/
PR-Nummern per `git log` verifiziert, nicht aus Erinnerung. Bewusst
thematisch statt einzeln chronologisch gruppiert, um den Block lesbar zu
halten — Reihenfolge innerhalb jedes Clusters ist chronologisch.)*

**⚠ Trading-relevant, gesondert hervorgehoben — Push-Gating unvalidierter
Trading-Signal-Pushes (`#544` Merge `addf87a0` + `#545` `356a7ce5`,
06.09.2026):** Easy-Entscheid, **5 unvalidierte Trading-Signal-Push-Typen
deaktiviert**: Earnings-Sofort-Alert, Exit-Signale Phase 2 (beide Kanäle),
alle 7 Anomalie-Trigger (inkl. `conviction_high`), Exit-Signale Phase 1
(beide Untertypen), Legacy Alert-Monitor `alert.py`. **4 Infra-Pushes
bleiben unverändert aktiv:** Health-Check-Digest, HTML-Sanity-CRIT-
Notfallnetz, Lit-Check-Weekly-Reminder, Status-Review-Wecker. Rückweg:
Flags in `config.py` zurück auf `True`. Dokumentiert als Architektur-Anker
§7l. **Wer den aktuellen Push-Zustand des Tools verstehen will, muss
diesen Punkt kennen** — er überlagert praktisch jeden an anderer Stelle
in dieser Datei beschriebenen Push-Mechanismus (Anomalie-Push-System,
Exit-Signale, Earnings-Sofort-Alert — deren Beschreibungen weiter unten
bleiben technisch korrekt, sind aber aktuell alle **scharf gestellt, aber
deaktiviert**).

- **NaN-Härtungskette (Gruppe A, mehrwöchig):** `#533` (`71bffa4b`, 15.08.)
  Bestandsrecord-Reparatur ARCT/COLL/GO/IBTA · `#534` (`41750f11`, 16.08.)
  `change_2d`/`change_3d`-NaN-Wurzelfix + 3 Konsumenten · `#535`
  (`83c7a17b`, 16.08.) 3 weitere Sibling-Fundstellen aus #534 (Preis/RVOL/
  Watchlist/UOA) · `#536` (`84de2385`, 16.08.) NaN-Bypass im Preis-/
  Market-Cap-K.o.-Filter · `#557` (`d058107e`/`a42fb31d`, 21.09.)
  Schreibpfad-Härtung `backtest_history.py` (score/entry_price/
  short_float/dtc/rvol/si_slope/si_velocity_pub) — fand 1 bereits
  kontaminierten Bestandsrecord (**TTGT, 20.07.2026,
  `si_velocity_pub=-1.0`**), **gemeldet, NICHT gefixt** (jetzt in
  `open_items.json` nachgetragen) · `#558` (`4488f975`, 22.09.)
  `score_inflation_log._safe_float` → `_coerce_float` (Namensgleichheit
  zur echten, sicheren Funktion täuschte Sicherheit vor, die nicht
  bestand) · `#559` (`92c8c20e`/`98decc55`, 22.09.) **4. CI-Gate**
  `lint_nan_bypass_fields.py` — Baseline **70 bereits bestehende, offene
  Gruppe-A-Funde** in `_BASELINE_KNOWN_OPEN` eingetragen, NICHT gefixt
  (Tech-Debt-Liste, jetzt ebenfalls in `open_items.json`) · `#561`
  (`642ea1b3`, 25.09.) Diagnostik-Logging `_extract_hist_5d` (S10-crit
  `coiled_spring_score`-Nullbefund).

- **Vorabregistrierungs-/Backtest-Ausbau:** `#543` (`1b182c85`, 02.09.)
  SR-FINRA-2026-012-Wiedervorlage, zusätzliche Prüf-Quellen · `#548`
  (`ecc59d88`, 12.09.) **H5-Vorabregistrierung finalisiert** (Bausteine
  final, 16-Zellen-Kreuztabelle, Holm, Ausreißer-Verfahren) · `#549`
  (`5b1ac5ae`, 13.09.) Haircut-/Netto-Return-Felder (`return_Nd_net`,
  `max_gain_pct_net`) · `#554` (`8afcab12`, 18.09.) SPY-Benchmark-
  Vergleich (`return_Nd_vs_spy`) — beide Felder explizit NICHT
  automatisch Teil der §4/H5-Bindung (siehe §4-Protokolleintrag 18.09.).

- **NYSE-/Reg-SHO-Diagnose-Kette:** `#538` (`3ced2a6f`, 21.08.)
  `_resolve_nyse` auf bestätigten API-Endpunkt umgestellt · `#539`
  (`202e7ccc`, 22.08.) Lit-Check H-Kapitaldruck-Hypothese
  (Svoboda-Dämpfer) · `#542` (`2e9686a4`, 02.09.) NYSE-Fetch-
  Fehlerursache in `reg_sho_history` mitgeloggt · `#546` (`1fffc999`,
  12.09.) `_last_workday_before()` feiertags-bewusst (Labor-Day-Vorfall) ·
  `#550` (`d4d138a7`/`8e6db089`, 13.09.) NYSE-Referer-Header-A/B-Probe
  (read-only, dispatch-only) · `#551` (`5095c09a`, 13.09.)
  Finviz-Provider-Health-Coverage statt All-or-Nothing-`http_status`
  (behebt strukturellen Immer-Fail-Bug im Digest).

- **Exit-Pipeline-Fix + Frontend-/Anzeige-Fixes:** `#537` (`ec83a311`,
  17.08.) **Backend-Bug** in `_exit_p2_score_at()`/`_compute_exit_state()`
  — `n_back=0`-Guard ließ `current_score` (und kaskadierend
  `peak_score_since_entry` + die Exit-Trigger `score_decay`/`profit_lock`)
  immer auf `None`/`available:False` stehen, kein Anzeige-Bug (Guardian-
  Präzisierung 27.09.) · `#540` (`30670fdc`, 26.08.) `_translate()`
  erkennt Googles Fehlerseite statt sie als Übersetzung zu übernehmen ·
  `#552` (`c39cd3fb`, 17.09.) ATM-IV-Zero-Sentinel als `None` behandelt ·
  `#553` (`90d9825d`, 18.09.) News-Anzeige-Max-Age-Cutoff (30 Tage).

- **Doku-/Backlog-Pflege:** `#541` (`783420ba`, 29.08.) Beobachtungspunkt
  §6n ≥90-Score-Bucket-Persistenz · `#555` (`50ab04e3`, 18.09.)
  Backlog-Vermerke Validierungs-Badge + Alpha-Pipeline · `#556`
  (`4a17cd96`, 19.09.) §4-Protokolleintrag Brutto-Bindung +
  Marktregime-Beobachtungspunkt + n-Diskrepanz-Vermerk (**Ursache jetzt
  geklärt, siehe §4-Sektion**).

- **Infrastruktur (jeweils eigene, größere Ergänzung):** `#560`
  (`7f4ecb11`, 22.09.) **Open-Items-Tracker** (`open_items.json` +
  `lint_open_items_consistency.py`) · `#562` (`9fe65b0c`, 25.09.)
  **Wöchentlicher Zusammenfassungs-Block** im Health-Check-Digest
  (Montag-Gate, §4-Delta + Open-Items-Diff) · `#563` (`2f413621`, 26.09.)
  §6q **MFE/MAE-Bestandsaufnahme** nach Score-Bucket (Beobachtungspunkt,
  keine Vorabregistrierung).

- **Datenpfad-Fix + Open-Items-Nachtrag:** `#565` (`f854d37d`, 27.09.)
  **Finviz-v111-Screener-Parser-Fix** — Regex → BS4-Tabellen-Parsing
  (analog `get_finviz_candidates()`/`_fetch_short_float_finviz()`), live
  verifiziert gegen 12 echte Ticker (XNDU/TYRA/SRZN/SHOE/PRME/OXM/ORIC/
  MATW/LRMR/IMVT/GRAL/AESI); Datenpfad lieferte seit Einführung (21.04.,
  `35911455`) vermutlich nie einen Kandidaten (0/1636
  `backtest_history.json`-Einträge mit `finviz_v111` in `source_pools`)
  · `#566` (`3ca21754`, 27.09.) **16 Open-Items nachgetragen** —
  systematische Durchsuchung aller 9 Blöcke von SESSION_HANDOVER.md nach
  bereits bekannten, aber im Tracker bisher nicht erfassten offenen
  Punkten (`squeeze-report-archiv.md` existiert nicht im Repo, weder
  aktuell noch historisch — daher nicht durchsucht).

### 28.09.–06.10.2026 — Handover-Staleness-Check + hist_5d-Diagnose-Kette (Gap-Log + Verschiebe-Fix) + NYSE-empty-Detail-Logging (6 PRs)

*(Nachtrag per Staleness-Grep 06.10.2026: Block 1 hinkte 7 PRs hinter
main hinterher — höchste gemergte PR #573, höchste hier erwähnte PR
#566. Alle Hashes/PR-Nummern per `git log` verifiziert.)*

- **Infrastruktur — Handover-Staleness-CI-Check:** `#568` (`6c578eb6`/
  `66dd44e8`, 28.09.) **Handover-Staleness-Hinweis** als 7. advisory
  Check in `pr-checks.yml` — vergleicht bei jedem PR die höchste
  gemergte PR-Nummer (`gh pr list --state merged --limit 1`,
  GitHub-API statt Git-Log-Tiefe) gegen die höchste in Block 1 erwähnte
  PR-Nummer (Regex `#(\d+)\b`, Wortgrenze schützt gegen CSS-Hex-Codes
  in der Prosa), Schwelle 3, IMMER `exit 0` (advisory, kein CI-Fail) —
  genau der Check, der diesen Nachtrag hier ausgelöst hat. Follow-up
  (`66dd44e8`) behebt zwei von squeeze-guardian gefundene ungefangene
  Exception-Pfade (`UnicodeDecodeError` bei Locale-Mismatch im
  `gh`-Subprocess bzw. beim Lesen von `SESSION_HANDOVER.md`).

- **S10-Diagnose-Kette (`coiled_spring_score`/`rvol_buildup_5d`/
  `vol_stability_5d`, Fortsetzung aus `#561`):** `#571` (`d3b7cf53`/
  `02ddf1f1`, 30.09.) **`hist_5d_gap_log.jsonl`** — persistiert dieselben
  Diagnose-Zeilen aus `#561` zusätzlich in einer eigenen JSONL-Datei
  statt nur im ephemeren GitHub-Actions-Konsolenoutput (Follow-up
  `02ddf1f1` behebt einen Guardian-BLOCKER: die Datei fehlte im
  Workflow-`git add`) · `#572` (`88dfb086`, 02.10., gemerged 03.10.)
  **Ein-Tag-Verschiebung bei unvollständigem letzten Tag** —
  `_extract_hist_5d` verwarf bisher den GESAMTEN Ticker, wenn nur der
  jeweils neueste Tag im 5-Tage-Fenster unvollständig war (High/Low/
  Close NaN bei intaktem Volume, 69–78/70–78 Ticker betroffen über zwei
  Vorfälle 30.09./01.10.); verschiebt das Fenster jetzt stattdessen
  einmalig um einen Tag, wenn genug Roh-Historie vorhanden ist. Die 3
  chronisch toten Ticker (BHV/NWCLW/PMVP) bleiben bewusst unberührt.
  **Wirkung verifiziert** (`health_check_log.jsonl`, S10): crit (100 %
  null) durchgehend bis 02.10., ab dem Postclose-Lauf 03.10. auf warn
  (50 % null) gesunken, im Premarket-Lauf 06.10. **vollständig clear**
  (0 State-Fails) — S10-crit seit 03.10. nicht mehr aufgetreten.

- **NYSE-/Reg-SHO-Diagnose-Kette (Fortsetzung aus `#542`/`#546`/
  `#550`):** `#573` (`c783a042`, 06.10.) **NYSE-"empty"-Diagnose-Detail**
  — seit Handelstag 28.09.2026 liefert `_resolve_nyse()` durchgehend
  `nyse_result="empty"` (HTTP 200, nicht-leerer Body, 0 Symbole nach dem
  `isalpha()`-Filter), ohne dass der State bisher erkennen ließ, OB es
  weiterhin die bekannte Ziffern-Platzhalterzeile war oder etwas
  anderes. Kein Code-/Config-Change im Übergangsfenster gefunden —
  Ursache vermutlich extern, nicht bestätigt (Live-Sandbox-Zugriff auf
  `www.nyse.com` strukturell blockiert, kein Signal über NYSE selbst
  erreichbar). Ab sofort persistiert `state["nyse_empty_detail"]`
  (separates Feld, Byte-Länge/Zeilenzahl/Preview) bei jedem `empty`-Lauf
  neu — `restricted` bleibt unverändert `None`, nie `False`.
  `open_items.json` um zwei Einträge ergänzt:
  `nyse-regsho-empty-streak` (offen, der obige Befund) und
  `nyse-referer-probe-status` (beobachtet, rückwirkend für den
  13.09.2026 aus `#550` erfassten, zuvor verlorenen Referer-A/B-Probe-
  Befund — beide Varianten lieferten damals HTTP 403, Hypothese nicht
  bestätigt).

- **Doku-/Backlog-Pflege:** `#569` (`a9345e92`, 28.09.) **AKUT-
  Verifikationsliste (§3) als abgeschlossen markiert** — 6 Live-Verify-
  Punkte waren seit 76 Tagen (14./15.07.) unverändert offen, obwohl
  längst durch Dauerbetrieb/direkte iPhone-Verifikation bestätigt;
  `open_items.json`-Eintrag `block3-akut-verifikationsliste-stale` auf
  `erledigt` gesetzt · `#570` (`135b6955`, 29.09.) **§6j
  apple-touch-icon als erledigt markiert** — trug seit 15.07.2026
  fälschlich „Status: OFFEN", obwohl der Fix bereits 4 Tage später
  (PR #462, 19.07.) gelandet war; `open_items.json`-Eintrag
  `s6j-apple-touch-icon-missing` auf `erledigt` gesetzt.

---

### 07.10.2026 — Open-Items-Oktober-Rundgang + US-Feiertage algorithmisch + SI-Timestamp-Logging (4 PRs)

*(Nachtrag per Staleness-Grep 07.10.2026: Block 1 hinkte main hinterher —
höchste gemergte PR #578, höchste hier erwähnte PR #573. Höchste gemergte
PR per `gh pr list --state merged` ermittelt (GitHub-API), NICHT per
Merge-Commit-Titel-Grep `"Merge pull request #N"` — dieses Pattern hätte
#577 übersehen, weil dessen Merge-Commit einen custom `commit_title`
("feat(calendar): ... (#577)") statt der GitHub-Standardformulierung
trägt. Alle vier PR-Titel gegen die tatsächliche API-Antwort abgeglichen
— keine Abweichung zur Kurzbeschreibung des Auftrags.)*

- **Doku-/Backlog-Pflege — Oktober-Rundgang:** `#575` (`c1eb0a4a`, Merge
  `142d1c30`, 07.10.) **4 `open_items.json`-Einträge nach Oktober-
  Diagnose aktualisiert** — `s6k-stand-zeile-zwei-zeiten` auf `erledigt`
  (Beleg PR #465), `s6g-institutional-ownership-sammelfeld-open` bleibt
  offen/beobachtet mit korrigiertem Titel (Sammelfeld live seit
  10.08.2026), `s6c-news-fda-lookahead-source-unclear` bleibt offen mit
  geklärter Quelle (SEC-EDGAR-8-K, Commit `513fa5f2`),
  `pr532-or0-sibling-bugs` bleibt offen mit aktualisierter Beschreibung
  (FINRA-Teilaspekt durch PR #557 gefixt, `_detect_recent_squeeze`-Lücke
  bleibt) · `#576` (`df762779`, Merge `34e6e1d6`, 07.10.) **Oktober-
  Entscheidungsrunde** — vier Punkte von Easy bewusst verworfen (Status
  `erledigt` mit Datum + Kurzgrund, da das Schema keinen eigenen
  „verworfen"-Status kennt): `s6f-v1-v2-render-path-not-unified`,
  `s6l-cockpit-stage3-cleanup`, `s6m-trading-days-elapsed-holiday-blind`,
  `h5-outlier-ticker-cause-unverified`; `ttgt-si-velocity-pub-anomaly`
  bleibt `beobachtet` mit Entscheidung „kein Backfill, Bestandsdaten
  nicht anfassen"; `nyse-referer-probe-status` in
  `nyse-regsho-empty-streak` eingeklappt (Referer-A/B-Hypothese vom
  13.09. zeigte keinen Unterschied, anderes Fehlerbild als der aktuelle
  HTTP-200-leer-Befund).

- **US-Börsenfeiertage vollständig algorithmisch (s6b):** `#577`
  (`16d2a7d0` + Follow-up `7525f892`, Merge `bf0f8306`, 07.10.) löst die
  Wartungs-Bombe `s6b-us-holidays-hardcoded-until-2027` — die 5
  beweglichen Feiertage (MLK Day, Presidents Day, Memorial Day, Labor
  Day, Thanksgiving), die bisher nur für 2025–2027 hartcodiert waren und
  2028 ausgelaufen wären, werden jetzt wie Good Friday (PR #407) über
  Nth-Weekday-of-Month-/Last-Weekday-of-Month-Formeln berechnet.
  Zusammen mit den Fixdatum-Feiertagen (Neujahr inkl. Samstag-Sonderregel,
  Juneteenth, Independence Day, Christmas) sind jetzt alle 10
  NYSE-Feiertage/Jahr in `config.py` UND im JS-Spiegel
  (`generate_report.py` `generate_html_v1`) algorithmisch, Range
  2020–2050. Exakt gegen die vormals hartcodierte 2025–2027-Liste
  verifiziert (Mengen-Diff leer) + Python↔JS-Vollparität via echter
  Node-Ausführung bewiesen (310 Einträge, 0 Diff). Neuer Test
  `scripts/mock_test_us_holidays_algorithmic.py` im CI-Allowlist
  registriert; `mock_test_good_friday.py` an die neue Architektur
  angepasst (nur stale Implementierungsdetail-Assertions, Verhalten
  unverändert). `open_items.json` `s6b-us-holidays-hardcoded-until-2027`
  auf `erledigt` gesetzt.

- **SI-Positions-Timestamp-Silent-Fail jetzt sichtbar:** `#578`
  (`1ee96dcb` + Follow-up `4939357a`, Merge `79339d29`, 07.10.) löst
  `si-position-history-timestamp-format-silent-fail-risk` —
  `_si_settlement_from_ts` schluckte einen Timestamp-Format-Fehler (z. B.
  falls yfinance `dateShortInterest` künftig als Timestamp statt
  Epoch-Int liefert) bisher ohne jede Log-Zeile. Genau eine
  `log.warning` im Fehlerpfad ergänzt (Funktionsname, Rohwert ≤40
  Zeichen, Ausnahmetyp); Rückgabewert/Kontrollfluss bleiben
  byte-identisch (weiterhin `None`, weiterhin fail-soft). Modul-Zähler
  `_SI_SETTLEMENT_PARSE_FAIL_COUNT` loggt nur beim ersten Vorkommen pro
  Lauf (Log-Flut-Schutz, da `_persist_si_position_history` über den
  vollen enriched US-Pool läuft). Direkt benachbarter Silent-Pattern in
  `_si_pub_date` bewusst nicht mitgefixt, im PR-Text gemeldet; squeeze-
  guardian fand zusätzlich zwei weitere, ebenfalls out-of-scope
  Kandidaten (`_parse_de_date`, Pruning-`except` in
  `_save_si_position_history`) — siehe neuer Open-Item-Eintrag
  `timestamp-silent-fail-siblings-unlogged` in `open_items.json`.
  `scripts/lint_nan_bypass_fields.py`-Baseline um 40 Einträge um +27
  Zeilen nachgeführt (reine Zeilen-Korrektur, mechanisch per
  AST-Rohfund-Vergleich main-vs-Branch verifiziert).

---

### 08.–11.10.2026 — NaN-Guard-Symmetrie (entry_past_return_5d) + Preis-Merge-Guard-/NYSE-empty-Diagnosen + Block-1-Autonomie-Regel + Setup-Edge-Re-Test-Freeze + Conviction-Erratum + Oktober-Nachträge-Bündel + KI-Score-Coverage-Fix + Freeze-Digest-Zähler (10 PRs)

*(Nachtrag per Staleness-Grep 09.10.2026, GitHub-API `gh pr list --state
merged` — NICHT Commit-Titel-Grep: höchste gemergte PR war zu Beginn
dieses Nachtrags #582, höchste hier erwähnte PR #578 — Rückstand 4.
Erwartete PRs #579–#582 bestätigt, keine Abweichung. Ab diesem Nachtrag
gilt die neue Block-1-Pflicht-Regel (CLAUDE.md, Abschnitt „Arbeits-Regeln
für Claude Code" → „Block-1-Pflicht"): jeder künftige PR trägt seinen
eigenen Eintrag selbst mit — ein Rückstand wie dieser soll strukturell
nicht mehr entstehen, nicht nur per Session-Disziplin.)*

- **Block-1-Nachtrag #575–578:** `#579` (Branch-Commit `e3827dbf`, Merge
  `df692aed`, 07.10.) zieht den vorherigen Cluster „07.10.2026" (PRs
  #575–578, oben) nach und erfasst zusätzlich das neue Open-Item
  `timestamp-silent-fail-siblings-unlogged` (offen) für drei weitere,
  aus demselben Silent-Fail-Muster wie PR #578 bekannte, bewusst nicht
  mitgefixte Stellen (`_si_pub_date`, `_parse_de_date`, Pruning-`except`
  in `_save_si_position_history`).

- **NaN-Guard-Symmetrie `entry_past_return_5d`:** `#580` (Branch-Commits
  `95e71b80`/`8f47fa60`/`cd477d2c`, Merge `86065195`, 08.10.) härtet
  `_compute_entry_past_return_5d` (`backtest_history.py`) gegen denselben
  NaN-blinden `<=0`-Guard, der bei den PR-#557-Geschwistern
  (`_compute_si_slope_5d`/`_compute_si_velocity_pub`) bereits gefixt
  wurde — Zähler UND Nenner über `_finite()` geprüft, Verhalten für
  endliche Werte byte-identisch (Test-Nachweis `mock_test_entry_past_
  return_5d.py`, Sektion D+E). `open_items.json`: `pr532-or0-sibling-
  bugs`-Beschreibung korrigiert (die `_detect_recent_squeeze`-Lücke
  sitzt bei `prior_vol`/`win_vol`, NICHT bei `c0`/`c1` — ein künftiger
  Fix dort ist Manual-Merge, da Score-Logik-Touch), zwei neue Items
  `cur-close-close-5td-before-entry-unguarded-source` (offen,
  diagnose-first) und `entry-score-is-not-none-vs-finite-dormant-gap`
  (beobachtet). Guardian fand eine kosmetische Zeilenangabe-Ungenauigkeit
  (`c0`/`c1`), vor Merge direkt korrigiert (`cd477d2c`).

- **Diagnose-Nachtrag `cur_close`-Preis-Merge-Guard:** `#581`
  (Branch-Commit `2da36648`, Merge `b50d7ef0`, 09.10.) trägt eine reine
  read-only-Diagnose zu `cur-close-close-5td-before-entry-unguarded-
  source` nach: ein zentraler Merge-Guard (`generate_report.py:18061-
  18080`, PR #535/16.08.2026) verhindert strukturell, dass ein NaN aus
  `cur_close`/`close_5td_before_entry` je das Feld `"price"` erreicht —
  laut Grep der einzige Konsument von `get_yfinance_data`/
  `get_yfinance_batch` im gesamten File. Historie (`git log`-belegt):
  die Lücke wurde am 15.08.2026 explizit als „höchste Priorität"
  benannt, aber nie an der Quelle selbst gefixt — Einstufung übersehen,
  kein Beleg für Absicht. `pr532-or0-sibling-bugs` um einen Scheduling-
  Hinweis ergänzt (Fix für `_detect_recent_squeeze` bewusst erst nach
  n=250 im §4-Re-Test, explizit als neue Entscheidung markiert, nicht
  als bestehende Protokollbindung des §4-Änderungs-Protokolls).

- **Diagnose-Nachtrag NYSE-Reg-SHO-„empty"-Serie:** `#582`
  (Branch-Commit `b2def166`, Merge `90a43cbf`, 09.10.) trägt eine
  weitere read-only-Diagnose zu `nyse-regsho-empty-streak` nach (Status
  `offen` → `beobachtet`): das seit PR #573 persistierte
  `nyse_empty_detail` zeigt für drei Läufe (06./07./08.10.) ein
  byte-identisches Platzhalter-Muster zum bereits am 21.08.2026
  dokumentierten Fall — kein geänderter Aufbau, keine Sperrseite.
  Semantik bleibt intakt (`restricted=null`/`reason=source_empty`, nie
  `false`; Stichprobe Ticker WOLF); kein Konsument außer der Sammlung
  selbst betroffen. Ursachen SR-FINRA-2026-012 und PR #546 ausgeschlossen
  (sachlich bzw. zeitlich). Entscheidung: weiter beobachten, späterer
  Entscheidungspunkt bei ca. 20 Handelstagen in Folge (ab ca. 26.10.2026)
  vermerkt.

- **Block-1-Autonomie-Regel + dieser Nachtrag selbst:**
  `#583` (Branch-Commit `1b155499`, 09.10., kein Merge-Hash genannt — per
  neuer Regel a) steht der vor dem Merge noch nicht fest) zieht die vier
  PRs oben nach (dieser Cluster)
  UND trägt in `CLAUDE.md`
  (Abschnitt „Arbeits-Regeln für Claude Code") die neue „Block-1-
  Pflicht"-Regel ein: jeder künftige PR ergänzt seinen eigenen Block-1-
  Eintrag selbst, als zusätzlichen Commit auf demselben Branch VOR
  Ready/Merge (Ausnahme: ein PR, der nur den Block-1-Eintrag selbst
  ändert, braucht keinen weiteren Eintrag für sich — gilt hier NICHT,
  da dieser PR zusätzlich CLAUDE.md ändert). Ersetzt die bisherige,
  nur als Session-Disziplin/Prompt-Konvention gelebte Regel „Staleness-
  Grep vor Ready, Rückstand melden" (in CLAUDE.md selbst nie als Text
  vorhanden — nur in `SESSION_HANDOVER.md`-Chronik-Erwähnungen und im
  CI-Hinweis-Skript) durch „Rückstand selbst beheben, im selben PR,
  ohne Rückfrage". Konsistenz mit dem CI-Hinweis aus PR #568
  (`scripts/check_handover_staleness.py`) geprüft und bestätigt: die
  Funktion `compute_staleness` behandelt einen negativen Rückstand
  (PR erwähnt die eigene, noch nicht gemergte Nummer voraus) laut
  eigenem Docstring explizit als „kein Fund" — ein PR-eigener,
  vorab eingetragener Eintrag zählt weder im Entwurf noch nach dem
  Merge als Rückstand.

- **Setup-Edge-Re-Test-Freeze (Block-1-Pflicht befolgt):** `#584`
  (Branch-Commit `3eb82bd4`, 10.10., kein Merge-Hash genannt — Regel a)
  greift, der steht vor dem Merge noch nicht fest) friert in
  `SESSION_HANDOVER.md` direkt nach dem §4-Block eine neue, eigenständige
  Vorabregistrierung **„Setup-Edge-Re-Test (Score-Trennschärfe)"** ein
  (am 05.08.2026 bewusst nicht-registrierte Frage, ob der Score selbst
  gute von schlechten Aktien trennt — anders als §4, das nur Exit-Timing
  prüft). Population `provenance=forward` ∧ Eintrittsdatum strikt nach
  Freeze-Datum (10.10.2026 ET, vorläufig gesetzt mit Korrektur-Klausel
  falls der Merge einen anderen ET-Tag trifft); zwei Holm-k=2-Zielgrößen
  (AUC `return_5d≥+5%`, AUC `return_10d>0`), Auslöser n≥250 ohne
  Zwischenauswertung, 4-teiliges Erfolgskriterium inkl. einer von Easy
  festgelegten 0,55-Punktschätzungs-Schwelle, vier offen benannte
  Grenzen. SCHRITT-0-Grep (Pflicht lt. Auftrag): kein genereller
  Score-Formel-Änderungs-Detektor existiert —
  `SCORE_NORMALIZATION_VERSION` (`config.py:473`) ist ein manueller,
  nur auf die RVOL-Normalisierungs-Welle (γ-1/γ-2) begrenzter Marker,
  `backtest_schema_version` eine Schema-Form- keine Formel-Version;
  Health-Check S13b überwacht nur 3 benannte Konstanten auf Drift.
  `mann_whitney_u_auc`/Holm (`scripts/stats_helpers.py:60`/`:152`) und
  der Cluster-Doppellauf (`scripts/cluster_purge.py`) bestätigt
  vorhanden und bereits produktiv genutzt; der Bootstrap
  (`bootstrap_mean_ci`, `scripts/expectancy_diagnose.py`) existiert mit
  Default N=1000, ist aber frei auf N=2000 parametrisierbar — ein
  dediziertes stehendes N=2000-Skript existiert nicht, frühere Läufe
  waren vermutlich Ad-hoc-Aufrufe. Nutzerangaben (472 Zeilen,
  21.07.–25.09., Buckets 20/109/162/181, ~10/Tag) direkt gegen
  `matured_backtest_export.jsonl` nachgezählt — alle bestätigt, keine
  Abweichung. `open_items.json`: neuer Eintrag
  `setup-edge-retest-freeze` (beobachtet) verknüpft den
  `_detect_recent_squeeze`-Fix (`pr532-or0-sibling-bugs`) mit zwei
  offenen Optionen (vor vs. nach n=250), keine Vorentscheidung. Lint
  grün (26 Items, nichts gelöscht).

- **Conviction-Zusatznutzen-Erratum (Block-1-Pflicht befolgt):** `#585`
  (Branch-Commit `0e37e1e7`, 10.10., kein Merge-Hash genannt — Regel a)
  greift) erweitert den Setup-Edge-Re-Test-Freeze aus `#584` um einen
  dritten Test (c): Zusatznutzen `conviction_score` gegenüber `score`
  allein, gemessen als gepaarter ΔAUC für `return_5d≥+5%`, Holm-Familie
  von k=2 auf k=3 erweitert. Kein bestehender Satz des Freeze-Blocks
  geändert — reiner ERRATUM-Zusatz plus eine Ergänzung an der alten
  Kalenderpunkt-Zeile „Conviction-Edge P3" (als ERSETZT markiert, nicht
  gelöscht). Vor der Änderung geprüft: Freeze-PR #584 gemergt
  (`328b3fc4`), seither **0 Commits** auf `main` — kein Outcome der
  bestätigenden Population je ausgewertet. Population zusätzlich auf
  `EARLINESS_FORMULA_VERSION=2`-Zeilen beschränkt; V2-Umstellung
  git-belegt auf **PR #141, Merge `ab3041b1`, 14.05.2026**
  (Feat-Commit `fa8d87f0`, Skala-Wechsel `EARLINESS_PTS_MAX` 7→100),
  seither nie geändert (`git log -S` über die gesamte Historie: genau
  ein Treffer). Da die früheste Forward-Zeile am 21.07.2026 liegt, sind
  100 % der heutigen Population bereits unter V2 — Filter ist aktuell
  ein No-op, bleibt Zukunftssicherung. Conviction-Gewichte 33/28/28/11
  ebenfalls git-belegt nie geändert seit Einführung (`6970d277`, je ein
  Treffer pro Literal). Nutzerangaben (472 Forward-Zeilen alle mit
  `conviction_score`; 634 `backtest_history.json`-Records mit
  `conviction_score` ab 13.07.2026, davon 100 ungereift) direkt
  nachgezählt — exakt bestätigt, keine Abweichung. Offener Punkt,
  bewusst nicht gebaut: ein **gepaarter Bootstrap für eine
  AUC-Differenz existiert im Repo nicht** (nur ein einfacher
  Mittelwert-Bootstrap in `scripts/expectancy_diagnose.py`) — muss bei
  Auswertung nach n≥250 erst gebaut werden. `open_items.json`: kein
  neuer Eintrag, bestehender `setup-edge-retest-freeze` ergänzt. Lint
  grün (26 Items, unverändert in der Anzahl).

- **Oktober-Nachträge gebündelt (Block-1-Pflicht befolgt):** `#586`
  (Branch-Commit `33c11af1`, 10.10., kein Merge-Hash genannt — Regel a)
  greift) bündelt 7 Doku-Nachträge in einem PR: (1) SR-FINRA-2026-012 als
  zurückgezogen (05.08.2026, SEC-Filing-Seite „WITHDRAWN") dokumentiert,
  alte Wiedervorlage erledigt-markiert (Text ergänzt, nicht gelöscht),
  neuer Beobachtungseintrag für ein mögliches Nachfolger-Filing mit
  Wiedervorlage beim Monatsrundgang; Code-Prüfung ergab, dass
  `FINRA_PUB_OFFSET_BUSINESS_DAYS`/`N=3` nur vorausschauend auf das
  Filing verweisen und bereits heute an FINRA Rule 4560 (Status quo)
  hängen — kein Korrekturbedarf. (2) Neuer offener Eintrag für den
  fehlenden gepaarten Bootstrap (ΔAUC, Setup-Edge-Erratum Test c) +
  stehendes N=2000-Skript für Tests a/b, Auslöser-Vorschlag n≥200 (Easy
  entscheidet). (3) KI-Score-Coverage-Diagnose vom selben Tag (reine
  Chat-Diagnose, keine eigene PR) nachgetragen. (4) Neue IBKR-Spur
  (Borrow-Daten, Status `beobachtet`) + Querverweis im Utilization-Bau-
  Kandidaten-Pool. (5) Monatsrundgang November (02.11.2026) als
  Wiedervorlage vermerkt. (6) Lit-Check 10.10.2026 ergänzt. (7)
  Arbeitsweise-Notiz zu Unteragenten-gestützten Lese-Diagnosen (§9l).
  **Abweichung gemeldet:** die im Auftrag genannte „16 % der Records"
  für den stummen Borrow-Bonus ließ sich nicht reproduzieren (eigene
  Zählung: 0 % seit 23.07.2026, ~12,9 % über die gesamte Feldhistorie)
  — nur die git-belegte Kernaussage „seit 23.07. faktisch tot"
  (Commit `ad981064`) wurde übernommen, die „16 %"-Zahl bewusst nicht.
  `open_items.json`: 4 neue Einträge (26→30), ein bestehender Eintrag
  auf `erledigt` gesetzt (Beschreibung ergänzt, nicht ersetzt), nichts
  gelöscht. Lint grün.

- **KI-Score-Coverage-Fix (Block-1-Pflicht befolgt, Manual-Merge, Merge
  durch Easy aussteht):** `#587` (Branch-Commit `0a674c0d`, 11.10., kein
  Merge-Hash genannt — Regel a) greift). Behebt die 10.10.-Diagnose (nur
  30 % Coverage, Cron-Kollision postclose/ki_agent) — `generate_report.
  _compute_fresh_ki_signals_for_backtest(top10)` berechnet synchron,
  GENAU für die finalen Top-10-Ticker, direkt vor dem Backtest-Append
  einen frischen KI-Wert (Reuse `ki_agent._process_ticker`, lazy
  importiert). **Score-Unabhängigkeit belegt** (Call-Order-Trace):
  `apply_agent_boost`/`apply_monster_score`/`apply_conviction_scores`
  laufen nach der Top-10-Membership-Fixierung und lesen/schreiben
  `ki_signal_score` direkt oder indirekt — die neue Funktion schreibt
  deshalb nirgends auf das Stock-Dict zurück, nur in einen neuen
  `fresh_ki_signals=`-Parameter von `_append_backtest_entries`/
  `_build_backtest_extension`. Variante A (synchron im Daily-Run)
  gewählt — Variante B (Workflow-Reihenfolge) ist strukturell untauglich
  (zirkuläre Abhängigkeit: ki_agent kann die künftige Top-10 nie vorab
  kennen), Variante C (additives `agent_signals.json`) löst weder
  Erstauftritt-Ticker noch Zeitstempel-Synchronität. Zeitbudget empirisch
  geprüft (GitHub-Actions-API, 5 Runs 08.–10.10.): Daily-Run dauert
  ~70–85 s gesamt bei 10-Min-Timeout. Neues additives Feld
  `ki_signal_ts` (UTC-ISO, Schema bleibt v4), `score=None` bei
  Fehlschlag bleibt ehrliches None (kein Fallback auf stale Werte).
  `claude_sentiment_score`-Fehlerarten jetzt `log.warning` + Lauf-
  Zähler (Verhalten unverändert). 17 neue Tests + 1 angepasster
  bestehender Test (Source-Pattern-Drift, Verhalten unverändert),
  Golden-Test byte-identisch (441766 Bytes). `lint_nan_bypass_fields.py`:
  61 Baseline-Zeilennummern nachgeführt (reine Verschiebung, kein
  inhaltlicher Fund). **Kein KI-Freeze in diesem PR.**

- **Setup-Edge-Freeze Punkt-9-Erratum (Option A) + Freeze-Digest-Zähler
  (Block-1-Pflicht befolgt, Auto-Merge):** `#588` (Branch-Commit
  `2a10bcdd`, 11.10., kein Merge-Hash genannt — Regel a) greift). TEIL 1
  (Doku): Easy entscheidet sich bei Punkt 9 des Setup-Edge-Re-Test-Freeze
  für **Option A** — der `_detect_recent_squeeze`-Fix
  (`open_items.json`, `pr532-or0-sibling-bugs`) wird erst nach Auswertung
  ALLER drei Tests (§4, Setup-Edge-Re-Test, Conviction-Zusatznutzen)
  umgesetzt. ERRATUM-Vermerke an beiden gleichlautenden Punkt-9-Stellen
  (Freeze-Block + Conviction-Erratum) ergänzt, `open_items.json`-Eintrag
  entsprechend ergänzt (append-only, Status bleibt „offen"). TEIL 2
  (Code, `health_check.py`): neuer Digest-Zähler „🧪 Freeze-Zähler" für
  die Setup-Edge/Conviction-Freeze-Population (`provenance=="forward"`
  UND Eintrittsdatum strikt nach dem Freeze-Datum UND `return_5d`/
  `return_10d` gefüllt, alle Scores) — reine Zeilen-/Tage-Zählung, keine
  Outcome-Statistiken, display-only (kein Alarm, kein S-Check, keine
  Push-Änderung). §4-Zähler (`_count_matured_retest`) auf gemeinsamen
  Lese-Helper (`_read_matured_export_rows`) umgestellt —
  Vorher/Nachher-Beleg per Test, dass der Rückgabewert unverändert
  bleibt (`(181, 1167)` gegen die echte `matured_backtest_export.jsonl`,
  sowohl vor als auch nach dem Refactor). Neue Konstanten in
  `config.py` (`SETUP_EDGE_FREEZE_DATE`, `SETUP_EDGE_FREEZE_N_TARGET`).
  23 neue Tests (`scripts/mock_test_freeze_zaehler.py`), in Allowlist
  registriert. `lint_nan_bypass_fields.py`-Baseline für `health_check.py`
  627→630 nachgeführt (3 neue Import-Zeilen, Fund selbst unverändert).
  squeeze-guardian-Pflichtlauf: keine blockierenden Findings. Optional
  (iv) aus dem Auftrag (Export-weite `ki_signal_ts`-Zeilenzahl) bewusst
  nicht gebaut — redundant zu (iii), im PR dokumentiert.

### 12.–13.10.2026 — IBKR-Spur (Borrow-Daten) geschlossen + KI-Score-Edge-Test-Freeze (2 PRs)

- **IBKR-Spur (Borrow-Daten) geschlossen (Block-1-Pflicht befolgt,
  Auto-Merge):** `#589` (Branch-Commit `9e805fa0`, 13.10., kein
  Merge-Hash genannt — Regel a) greift). IBKR hat auf Easys Mail an
  `apiintegration@interactivebrokers.com` geantwortet (12.10.2026): OAuth
  für die Trading Web API ist auf Institutional- und Financial-Advisor-
  Konten beschränkt, Privat-/Joint-/Retirement-/Trust-Konten sind
  ausgeschlossen. Privatkunden bleiben nur Client Portal Gateway oder
  TWS API — beide brauchen einen dauerhaft laufenden Rechner mit
  interaktivem 2FA-Login, nicht vereinbar mit GitHub Actions/iPhone-only.
  Verleihquote (Utilization) bleibt nur manueller Handcheck in der
  IBKR-App. **Entscheidung (Easy, 12.10.2026): Nicht bauen.**
  `open_items.json` (`ibkr-borrow-data-spur`): Status `beobachtet` →
  `erledigt`, Ergebnis + Entscheidung + Wiedervorlage 02.11.2026 ergänzt
  (append-only, 30 Items vorher/nachher unverändert). Reine Doku, kein
  Code/Workflow/Score-Touch, Setup-Edge-Re-Test-Freeze unberührt
  (verifiziert). Kein älterer IBKR-Teilplan gefunden, der als überholt
  zu markieren wäre.

- **KI-Score-Edge-Test-Freeze (Block-1-Pflicht befolgt, Auto-Merge, reine
  Doku):** `#590` (Branch-Commit `a99e4213`, 13.10., kein Merge-Hash
  genannt — Regel a) greift). Vorabregistrierung für die Frage,
  ob `ki_signal_score` (KI-Score-Coverage-Fix, PR #587, Variante A, seit
  11.10.2026 aktiv) gute von schlechten Aktien trennt — strukturell 1:1
  analog zum Setup-Edge-Re-Test-Freeze (10.10.2026) aufgebaut, **eigene**
  Holm-Familie k=2 (nicht mit der dortigen k=3-Familie zusammengelegt,
  Nachteil „5 Tests ohne gemeinsame Korrektur" offen benannt).
  **SCHRITT-0-Befund:** `ki_signal_ts` existiert in **0 von 1177**
  Export-Zeilen (`matured_backtest_export.jsonl`) — die 10 Zeilen vom
  12.10.2026 mit diesem Feld (in `backtest_history.json` bestätigt,
  `return_5d`/`return_10d` dort 0 von 10 gefüllt) erreichen das
  Export-File frühestens ca. 27.10.2026 (Reife-Gate 14 Kalendertage,
  `matured_export.py:160-171`) — **keine** Export-Schema-Änderung nötig,
  reine Zeitfrage, Feld läuft additiv/ohne Whitelist durch. Population:
  `provenance=="forward"` UND `ki_signal_ts` vorhanden UND Eintrittsdatum
  `>= 12.10.2026`, nur aus dem Export, Backfill nie. Auslöser n≥250,
  Erfolgskriterium identisch zum Setup-Edge-Vorbild (Holm-signifikant,
  Bootstrap-CI-Untergrenze > 0,5, Cluster-Doppellauf gleiche Richtung,
  Punktschätzer ≥ 0,55). Bewusst **ohne** Terminschätzung (Abweichung vom
  Setup-Edge-Vorbild dokumentiert) — Rate erst ab echten Daten (ca. ab
  27.10.) berechenbar. `open_items.json`: neuer Eintrag
  `ki-score-edge-freeze`, Status `beobachtet`, Wiedervorlage 28.10.2026
  (30→31 Items). Kein Code, kein Digest-Umbau in diesem PR — reine Doku.
  Setup-Edge-Re-Test-Freeze-Block + beide Errata **byte-identisch
  unverändert** (verifiziert per Diff-Vergleich gegen den Vorzustand).

### 16.10.2026 — KI-Score-Edge-Test-Freeze-Erratum (1 PR)

- **KI-Score-Edge-Test-Freeze — Randfall ohne verwertbaren Score
  entschieden (Block-1-Pflicht befolgt, Auto-Merge, reine Doku):**
  `#591` (Branch-Commit `4a0c7b04`, 16.10., kein Merge-Hash genannt —
  Regel a) greift). Erratum zum KI-Score-Edge-Test-Freeze (`#590`): der
  dort in Punkt 2 offen gelassene Randfall — `ki_signal_ts` vorhanden,
  aber `ki_signal_score` fehlgeschlagen/nicht verwertbar — ist
  entschieden (**Easy, 16.10.2026**): solche Zeilen zählen **nicht**
  zur Population. Population präzisiert: `provenance=="forward"` UND
  `ki_signal_ts` vorhanden UND `ki_signal_score` numerisch/endlich
  (nicht `None`) UND Eintrittsdatum `>= 12.10.2026`, nur aus
  `matured_backtest_export.jsonl`. Ausgeschlossene Zeilen werden bei der
  Auswertung nur als Zahl berichtet (Anteil), nie getestet — kein
  Ergebnis-Bias, da die Zuordnung allein vom Einstiegstag abhängt.
  Einschränkung bei Ausschlussanteil > 20 % benannt (kein
  Abbruchkriterium, nur Hervorhebung in der Bewertung). Folgeauftrag
  (Digest-Zeile „KI n = X/250") präzisiert, dieselbe Population zu
  zählen. **SCHRITT-0-Befund:** 40 Zeilen mit `ki_signal_ts` in
  `backtest_history.json` (10/Tag für 12.–15.10.2026), 0 von 40 mit
  nicht-verwertbarem Score, 0 von 40 mit `return_5d`/`return_10d`
  gefüllt — kein STOPP. Bestehender „keine Vorentscheidung"-Vermerk
  nicht gelöscht, nur um Verweis „entschieden 16.10., siehe Erratum"
  ergänzt. `open_items.json` (`ki-score-edge-freeze`): Erratum-Satz
  ergänzt, Status bleibt `beobachtet` (31→31 Items). Setup-Edge-Re-Test-
  Freeze-Block + beide Errata sowie alle anderen Teile des KI-Freeze
  **byte-identisch unverändert** (heading-anchorter Diff). Kein Code,
  kein Schema, keine Workflows.

### 17.10.2026 — Options-Rohketten-Sammelfeld (Lit-Check Muravyev/Pearson/Pollet + Baig/Strong/Zaynutdinova) (1 PR)

- **Options-Rohketten-Sammelfeld `options_chain_raw.jsonl` (Block-1-Pflicht
  befolgt, Manual-Merge — neues JSONL-Schema, Easy mergt am iPhone):**
  `#592` (Branch-Commit `f1bd5ec0`, 17.10., kein Merge-Hash genannt —
  Regel a) greift). Lit-Check-Funde
  (siehe Eintrag oben): Leihgebühr aus Optionspreisen
  (Muravyev/Pearson/Pollet) + Net-Delta-Gamma-Maße (Baig/Strong/
  Zaynutdinova, „Seeking Gamma") brauchen Bid/Ask/LastPrice/Volumen/
  LastTradeDate je Strike, die `_extract_oi_rows()` heute verwirft.
  Neue Datei sammelt diese Rohdaten für die Top-10, NUR postclose,
  moneyness-gefiltert (±30 % um den Spot) — **KEINE Berechnung** (keine
  Leihgebühr, kein Delta), **KEIN Score-/Filter-/Push-/Anzeige-Effekt**.

  **Zero-New-Fetch-Design:** `_fetch_next_expiry_chain` bekommt einen
  additiven `raw_sink`-Parameter (Default `None`, byte-identisch für alle
  bestehenden Aufrufer/Tests — bewiesen per Test). `main()` wrappt den
  `fetch_fn`, den `_persist_options_oi_history` ohnehin aufruft, mit
  einem Capture-Callback, der dieselbe Kette in einen Cache spiegelt —
  `_persist_options_chain_raw` liest NUR aus diesem Cache, macht selbst
  **keinen** Yahoo-Request. `options_oi_history.json` bleibt
  **byte-identisch** (Test-Beleg: identischer Output mit/ohne
  Capture-Wrapper um denselben `fetch_fn`).

  **Scope-Entscheidung, bewusst dokumentiert:** nur der „nächste" Verfall
  (identisch zu options_oi_history.json, volle Top-10) — NICHT der für
  `atm_iv`/`pc_ratio`/Gamma gewählte Verfall aus `get_options_data()`
  (deckt nur die ersten 5 US-Ticker ab, `_OPTS_TOP_N=5`; ein Hook dort
  hätte den PR auf eine komplexere Funktion für nur Teil-Abdeckung
  ausgeweitet). JSON-Schema (`expiries`-Liste) ist für eine spätere
  Erweiterung offen.

  **Digest-Zeile** „📦 Options-Rohkette" (`health_check.py`,
  `options_chain_raw_liveness_line`) — display-only, fail-soft, zeigt
  Zeilenzahl + Bid&Ask-Brauchbarkeits-Anteil am ATM-nahen Fenster (±10 %)
  des letzten Sammel-Tages (Kernzweck: Yahoo liefert nach Börsenschluss
  oft Bid/Ask=0). Bestehende Digest-Zeilen unverändert (Vorher/Nachher-
  Beleg: `options_oi_history.json`-Zeile byte-identisch).

  **Workflow-Änderung (Manual-Merge-Grund):**
  `.github/workflows/daily-squeeze-report.yml` bekommt einen neuen
  `git add options_chain_raw.jsonl`-Eintrag (ohne den wäre die Datei bei
  jedem Checkout verloren, analog Lehre #501 bei options_oi_history.json).

  **open_items.json:** neuer Eintrag `options-chain-raw-sammelfeld`,
  Status `beobachtet`, Wiedervorlagen 1) Digest-Qualitätscheck nach ca.
  10 Handelstagen (Bid&Ask-Anteil — bei schlechtem Wert separat
  entscheiden, ob ein Intraday-Abgriff sinnvoll ist, NICHT jetzt bauen)
  2) Monatsrundgang 02.11.2026.

  Golden byte-identisch, alle bestehenden Tests + 155 CI-Tests grün,
  `lint_nan_bypass_fields.py` grün (Baseline-Zeilennummern nachgeführt,
  reine Verschiebung, keine inhaltliche Änderung). Regel 8c nicht
  einschlägig (kein `score()`/Top-10-Touch).

### 21.10.2026 — News-Coverage-Watchdog (Karten-News-Totalausfall ab 02.10.2026) (1 PR)

- **News-Coverage-Watchdog `news_coverage_history.jsonl` (Block-1-Pflicht
  befolgt, Manual-Merge — neues JSONL-Schema + Workflow-Änderung, Easy
  mergt am iPhone):** `#593` (Branch-Commit `6b6f4c16`, 21.10., kein
  Merge-Hash genannt — Regel a) greift).

  **Befund + Zeitverlauf (SCHRITT 0a, verifiziert per
  `app_data.json`-Commit-Historie):** alle Karten (Top-10 + Watchlist)
  zeigten „Keine Nachrichten verfügbar". `watchlist_cards[*].news`:
  5/5 bis 29.09. 12:55 Uhr, **Ausfall 1** 29.09. 15:52 bis 30.09. 00:34
  Uhr (0/5), Recovery 30.09. 12:36 Uhr (wieder 5/5 bis 01.10. 23:13),
  **Ausfall 2** ab 02.10. 02:16 Uhr (0/5) — **durchgängig bis mindestens
  21.10.2026 (19+ Tage, geprüft bis zum aktuellsten Commit)**, kein
  einziger Lauf dazwischen mit News. Für Top-10-Karten existierte **kein**
  persistierter Zähler (gleicher Code-Pfad, nicht separat geprüft, aber
  strukturell identisch betroffen).

  **Warum bemerkte das kein Wächter? (SCHRITT 0b, mit Fundstellen):**
  (i) `get_yahoo_news()` (generate_report.py) fängt jede Exception mit
  `except Exception: return []` — der einzige Hinweis war eine **stdout-
  Zeile** (`print(f"News {ticker}: …")` in `get_combined_news()`), die
  niemand liest; es gab **keinen** persistierten Zähler.
  (ii) Das Provider-Health-Framework (`health_check.py`,
  `HEALTH_CHECK_PROVIDER_TIER`/`_EXPECTED`) kennt **keinen** Provider-Key
  für diesen Pfad — der einzige „News"-Provider-Key ist `news_rss`
  (`ki_agent.py`), der aber eine **komplett andere, unabhängige**
  News-Pipeline misst (5 eigene RSS-Quellen: Yahoo-RSS + Google News +
  UnusualWhales + MarketBeat + SeekingAlpha, `ki_agent.py:2992-3020`) —
  diese lief während des Karten-Ausfalls unbeeinträchtigt weiter
  (`provider_health.jsonl`, letzter `news_rss`-Eintrag: `http_status=200`,
  `30/75 calls failed` = 60 % Erfolg, **kein** Tier-3-Alarm, da
  `coverage_pct=None` und `http_status==200`). Genau DESHALB zeigte der
  KI-Block weiterhin News-Treffer (z. B. „News: acquisition" bei DFH),
  während die Karte „Keine Nachrichten" zeigte — zwei komplett getrennte
  Pipelines, nur eine davon beobachtet.
  (iii) **Inventur aller externen Datenquellen** (vollständige Tabelle
  unten) zeigt: 11 Quellen haben einen persistierten Pro-Lauf-Zähler +
  Digest-Zeile (teils mit Warnung bei Ausfall), **6 Quellen haben gar
  nichts** — darunter ausgerechnet der Karten-News-Pfad.
  (iv) `health_check`/Digest prüfen **Lauf-Erfolg und strukturelle
  Invarianten** (S1–S14: „hat `app_data.json` X Ticker", „ist der State
  frisch genug" etc.) sowie **Provider-Mechanik** (HTTP-Status,
  Call-Erfolgsrate) — **nicht** den tatsächlichen **Dateninhalt** einer
  einzelnen Anzeige-Komponente. `squeeze-guardian` prüft **PR-Diffs**
  (Architektur-Konformität gegen CLAUDE.md, tote Call-Sites, Krypto) —
  er läuft **nie gegen Live-Daten** und hätte einen reinen
  Laufzeit-Datenausfall (kein Code wurde geändert) grundsätzlich nicht
  erkennen können.

  **Inventur-Tabelle (SCHRITT 0b-iii, Kurzform — Spalten: Zähler? ·
  Digest-Zeile? · Warnung bei Ausfall?):**

  | Quelle | Zähler | Digest | Warnung | Anmerkung |
  |---|---|---|---|---|
  | yahoo_screener | ✓ | ✓ | ✓ (Tier 1) | |
  | yfinance_batch | ✓ | ✓ | ✓ (Tier 1) | |
  | yfinance_singletons | ✓ | ✓ | ✓ (Tier 1) | ^VIX/^GSPC/EURUSD |
  | finviz | ✓ | ✓ | ✓ (Tier 2) | seit 19.05. Tier 2 |
  | finra | ✓ | ✓ | ✓ (Tier 2) | |
  | stockanalysis | ✓ | ✓ | ✓ (Tier 2) | |
  | borrow (iBorrowDesk) | ✓ | ✓ | ✓ (Tier 2) | |
  | earningswhispers | ✓ | ✓ | ✓ (Tier 2) | |
  | quote_proxy | ✓ | ✓ | ✓ (Tier 2) | |
  | stocktwits | ✓ | ✓ | ✓ (Tier 3) | aktuell deaktiviert |
  | uoa | ✓ | ✓ | ✓ (Tier 3) | |
  | news_rss (ki_agent, 5 RSS-Quellen) | ✓ | ✓ | ✓ (Tier 3) | **misst NICHT die Karten-News** |
  | edgar_13f / 8k / form4 / 13d_g | ✓ | ✓ | ✓ (Tier 3) | |
  | options_oi_history | ✓ (eigene Datei) | ✓ | (nur „überfällig") | |
  | options_chain_raw | ✓ (eigene Datei) | ✓ | (nur „überfällig") | |
  | ftd_history / reg_sho_history | ✓ (eigene Datei) | ✓ | (nur „überfällig") | |
  | inst_ownership_history | ✓ (eigene Datei) | ✓ | (nur „überfällig") | |
  | **Karten-News** (`get_yahoo_news`/`get_combined_news`) | **war: ✗** | **war: ✗** | **war: ✗** | **diese PR schließt die Lücke** |
  | `get_options_data()` (atm_iv/pc_ratio) | ✗ (nur stdout) | ✗ | ✗ | deckt nur 5/10 Top-10-US ab |
  | `get_earnings_date()`/`get_earnings_surprise()` | ✗ (nur stdout) | ✗ | ✗ | |
  | ki_agent `fetch_reddit_mentions()` | ✗ | ✗ | ✗ | |
  | ki_agent `fetch_fda_calendar()` | ✗ | ✗ | ✗ | |
  | ki_agent `fetch_openinsider()` | ✗ | ✗ | ✗ | |

  Die letzten 5 Zeilen (Lücken) sind in `open_items.json`
  (`datenquellen-coverage-inventur`) festgehalten — **kein Code gebaut**,
  Entscheidung bei Easy.

  **Mini-Stopp 0c (Konsumenten) — KEIN STOPP ausgelöst:** `s["news"]`/
  `news_summary()`/`_compute_sub_scores()`-`news_pts` (Katalysator-
  Sub-Score) wurden gegrept und per AST-Funktionskörper-Scan geprüft —
  `_compute_sub_scores()` wird **ausschließlich** von `_sub_scores_html()`
  aufgerufen (reine Anzeige-Funktion, Docstring bestätigt: „ergeben NICHT
  den Gesamt-Score"). `score()`, `score_bonus()`,
  `compute_conviction_score()`, `apply_conviction_scores()`,
  `apply_agent_boost()` enthalten **0 Treffer** für „news" (AST-Body-Scan
  über alle fünf Funktionen). `backtest_history.py`/
  `matured_backtest_export.py` enthalten **0 Treffer**. Betroffen ist NUR
  der Anzeige-Teilwert Katalysator-Sub-Score + der Karten-News-Text.

  **Gebaut:**
  1. **Instrumentierung** `get_yahoo_news()`: Modul-Akkumulator
     `_NEWS_COVERAGE_ACCT` (raw/kept/dropped_by_age/Exception-Typ-Zähler,
     analog `ki_agent._KI_SENTIMENT_ERROR_COUNTS`), Exception-Typ jetzt im
     Log sichtbar.
  2. **RSS-Fallback** in `get_combined_news()`: liefert `yfinance`
     (`get_yahoo_news`) 0 verwertbare Items (Exception/leer/alles zu alt
     — alle drei Fälle münden in `== []`), wird derselbe Yahoo-RSS-Feed
     abgefragt, den `ki_agent.fetch_yahoo_news` nutzt
     (`feeds.finance.yahoo.com/rss/2.0/headline`), über die vorhandene
     `_rss_news()`-Helper — gleiche Item-Struktur, gleicher Altersfilter
     (`NEWS_MAX_AGE_DAYS_DISPLAY`). **Liefert yfinance: 0 zusätzliche
     Requests, Verhalten byte-identisch** (Test-Beleg).
     **Widerspruch korrigiert:** der alte Kommentar „Die 5 anderen
     RSS-Quellen tragen die News-Versorgung" in `get_combined_news()` war
     **falsch** für diesen Pfad (dort war `fv_items` bereits fest `[]`) —
     er beschrieb tatsächlich ki_agent.py's eigene Pipeline. Kommentar
     richtiggestellt, nicht stillschweigend übermalt.
  3. **Persistenz** `news_coverage_history.jsonl` (append-only, JEDE
     Phase — kein zusätzlicher Fetch, daher auch premarket sinnvoll,
     anders als `options_oi`/`options_chain_raw`), idempotent über
     `(date, run_phase)`. Flag `NEWS_COVERAGE_LOG_ENABLED=True`.
  4. **Digest** (`health_check.py`): „📰 News-Abdeckung: letzter Lauf
     Top-10 x/10 · Watchlist y/z · Quelle yfinance a / RSS b" +
     separate Warnzeile „⚠️ News-Abdeckung 0 in allen N Läufen der
     letzten 24 h" — NUR wenn die Summe über das **gesamte** Fenster 0
     ist (bewusst streng, einzelne Ticker haben legitim keine News).
     Kein Push, nur Digest. Bestehende Digest-Zeilen/Zähler unverändert
     (Vorher/Nachher-Gegenprobe gegen `origin/main`).

  **Ursachenstand: UNBELEGT.** Zwei Hypothesen bleiben offen (yfinance
  `stk.news` liefert von den Runnern nichts mehr vs. Yahoo liefert nur
  noch Items, die der 30-Tage-Altersfilter komplett verwirft) — die
  Sandbox hat keinen Yahoo-Zugriff (403 bestätigt), nur der echte Runner
  kann das klären. Die neuen raw/kept/dropped_age/Exception-Typ-Zähler
  im ersten echten Lauf (premarket oder postclose) liefern die
  entscheidenden Zahlen.

  **Rückweg:** `NEWS_COVERAGE_LOG_ENABLED=False` schaltet Persistenz +
  Digest-Zeilen ab (RSS-Fallback bleibt aktiv — reine Anzeige-
  Verbesserung, kein Risiko). `git revert` des Merge-Commits entfernt den
  gesamten Code-/Doku-Stand.

  **Kein Eingriff in `score()`/Top-10/Filter/Push/`apply_agent_boost`/
  Conviction** (Regel 8c nicht einschlägig, explizit geprüft und
  bestätigt — siehe Mini-Stopp 0c oben). `open_items.json`: zwei neue
  Einträge `news-coverage-watchdog` + `datenquellen-coverage-inventur`
  (beide `beobachtet`, 32→34 Items). Golden byte-identisch, Score-/Top-10-
  Gegenprobe (identische Scores + Sortierreihenfolge mit/ohne News auf
  Fixture-Daten) grün, 156 CI-Tests grün (14 neue), `lint_nan_bypass_
  fields.py` grün (Baseline-Zeilennummern nachgeführt, reine
  Verschiebung).

### 21.10.2026 — Generischer Daten-Abdeckungs-Wächter (Folge-PR zum News-Coverage-Watchdog) (1 PR)

- **Generischer Daten-Abdeckungs-Wächter `coverage_history.jsonl` (Block-1-
  Pflicht befolgt, Manual-Merge — neues JSONL-Schema + Workflow-Änderung in
  BEIDEN Workflows, Easy mergt am iPhone):** `#594` (Branch-Commit
  `29842631`, 21.10., kein Merge-Hash genannt — Regel a) greift). Schließt
  die Inventur-Lücke aus `#593` ab: 6 Quellen ohne Zähler/Digest/Warnung.

  **SCHRITT 0a — die 6 Lücken-Quellen, Abdeckungs-Definition + Legitim-Leer-Regel:**

  | Quelle | Fundstelle | "Abdeckung" = | Legitim leer, wenn … |
  |---|---|---|---|
  | `options_atm` | `generate_report.py:get_options_data` (Z. 1929) | Call beantwortet (kein echter Fehler), NICHT ob pc_ratio/atm_iv gefunden wurden | Ticker hat keine Optionskette, keinen aktuellen Spot-Preis, oder leere Calls/Puts — alles ohne Exception |
  | `earnings_date` | `generate_report.py:get_earnings_date` (Z. 2096) | Call beantwortet | Ticker hat legitim keinen anstehenden Earnings-Termin im Kalender |
  | `earnings_surprise` | `generate_report.py:get_earnings_surprise` (Z. 2130) | Call beantwortet | Keine Earnings-History, fehlende Spalten, oder kein matching Actual/Estimate-Paar |
  | `reddit_mentions` | `ki_agent.py:fetch_reddit_mentions` (Z. 889) | Call über ALLE Subreddits beantwortet (kein Netzwerk-Fehler in irgendeinem Sub) | Genuin 0 Mentions in den überwachten Subreddits heute |
  | `fda_calendar` | `ki_agent.py:fetch_fda_calendar` (Z. 1059) | RSS-Feed beantwortet (1× pro Tick) | Genuin keine PDUFA/Approval-Keyword-Treffer im 30-Tage-Fenster heute |
  | `openinsider` | `ki_agent.py:fetch_openinsider` (Z. 1107) | RSS-Feed beantwortet | Genuin keine Insider-Käufe (nur Verkäufe oder gar keine Filings) im Lookback-Fenster |

  **Restrisiko bewusst dokumentiert (nicht verschwiegen):** bei
  `earnings_date`/`earnings_surprise` ist denkbar, dass an manchen Tagen
  legitim KEINER der ~10 Top-10-Ticker einen anstehenden Termin/eine
  Historie hat (Earnings-Saison-Lücken) — die 24h-Fenster-Schwelle ist
  deshalb bewusst grob kalibriert (siehe `open_items.json`
  "coverage-waechter-baseline").

  **SCHRITT 0b — Schema-Entscheidung (per Beleg):** EIN generisches
  `coverage_history.jsonl` (Feld `quelle` statt 6 Spezialdateien) gewählt,
  NICHT das bestehende Tier-2/3-`provider_health.jsonl`-Framework erweitert
  — Begründung: dessen Konsekutiv-Trigger misst "3 aufeinanderfolgende
  DIGEST-Zyklen" (anderer Zeitbegriff als die hier geforderte "0 in allen
  Läufen eines 24h-Fensters", analog `#593`), eine Erweiterung hätte die
  bestehende Aggregationslogik für die 11 bereits abgedeckten Quellen
  anfassen müssen (Risiko für bestehende Zähler). `news_coverage_history.
  jsonl` bleibt unverändert (eigenes, reicheres Schema mit RSS-Fallback +
  Top-10/Watchlist-Split passt nicht verlustfrei in die generische Form).
  EIN gemeinsamer Persist-/Digest-Helfer (`health_check.persist_coverage_
  row`/`coverage_liveness_line`/`coverage_warn_line`/`coverage_overview_
  line`) bedient alle 6 Quellen — Single-Source-of-Truth statt 6×Code-
  Duplikat.

  **SCHRITT 0c — Mini-Stopp Konsumenten: KEIN STOPP, aber Widerspruch
  transparent berichtet.** AST-Scan bestätigt: `options`/`earnings_days`/
  `earnings_surprise` werden in `score()`/`score_bonus()` NICHT gelesen;
  `_compute_sub_scores()` liest sie zwar, ist aber (unverändert seit `#593`-
  Prüfung) AUSSCHLIESSLICH Aufrufer von `_sub_scores_html()` — reine
  Anzeigefunktion. **Ehrlich berichtet statt verschwiegen:** `insider`
  (`fetch_openinsider`) und — über `compute_signal` — potenziell `reddit`/
  `fda_calendar`-Treffer fließen BEREITS (vorbestehend, nicht Teil dieser
  PR) in `ki_signal_score` ein, der via `apply_agent_boost` einen
  ×1,05–1,15-Multiplikator auf den echten Score anwendet. Das ist
  **bestehendes Verhalten, von dieser PR nicht verändert** — die
  Instrumentierung fügt ausschließlich Side-Effect-Zähler in den
  jeweiligen `except`-Zweigen hinzu, OHNE Rückgabewerte zu berühren
  (Test-Beleg: `test_*_behavior_unchanged`-Tests in
  `scripts/mock_test_coverage_watchdog.py`, je Quelle ein Fehler-Fall +
  ein Legitim-Leer-Fall, beide mit identischem Rückgabewert wie vor der
  Instrumentierung).

  **SCHRITT 0d — Workflow-Commit (Manual-Merge-Grund):** `coverage_history.
  jsonl` wird von BEIDEN Workflows beschrieben (3 Quellen aus
  `daily-squeeze-report.yml`, 3 aus `ki_agent.yml`) — `git add` in BEIDEN
  Workflow-Dateien ergänzt (Lehre #501), sonst gingen die jeweils anderen
  Workflows ihre eigenen Zeilen bei jedem Checkout verloren.

  **SCHRITT 0e — Machbarkeitsbericht (NICHT gebaut, nur Diagnose):**
  *Existierende Zweit-Quellen:* `earnings_date` hatte bereits einen
  EarningsWhispers-RSS-Override (`EARNINGSWHISPERS_ENABLED`) — ist aber
  seit 18.05.2026 selbst tot (RSS-Feed down). `openinsider` überlappt
  konzeptionell mit dem bereits aktiven SEC-Form-4-Fetcher
  (`fetch_sec_form4`, Tier-3 `edgar_form4`) — beide erfassen Insider-
  Transaktionen, unterschiedliche Darstellung. Für `options_atm`,
  `earnings_surprise`, `fda_calendar` existiert KEINE zweite Quelle im
  Code. `reddit_mentions` hat mit StockTwits (`fetch_stocktwits_
  sentiment`) eine konzeptionell ähnliche, aber andere Plattform — auch
  diese ist aktuell deaktiviert (`STOCKTWITS_ENABLED=False`).
  *Automatischer Diagnose-/Draft-PR-Mechanismus bei Digest-Warnung:* zwei
  Wege geprüft, beide NICHT gebaut. (A) **Scheduled GitHub Action mit
  Claude-Code-GitHub-Action:** braucht ein API-Key-/OAuth-Secret im Repo,
  läuft als Workflow-Step, der bei erkannter Warnzeile eine Diagnose-
  Session startet und einen Draft-PR öffnet. Kosten: API-Nutzung pro Lauf
  (variabel, deckelbar), vernachlässigbare Actions-Minuten. Risiko:
  nicht-deterministische Diagnose, falsche Fehlzuordnung. (B) **Scheduled
  Remote-Agent (Claude Code Cloud-Session):** braucht eine an dieses Repo
  gebundene Umgebung + einen Cron-Trigger, der Digest/`coverage_history.
  jsonl` liest und bei Fund eine Diagnose-Session mit Draft-PR-Auftrag
  startet. Kosten: Session-Nutzung (höhere Größenordnung als ein reiner
  API-Call, da breitere Exploration). Beide Wege brauchen DIESELBE
  Rückfallebene wie die bestehende `squeeze-guardian`-Pflicht: Manual-
  Merge, nie Self-Merge aus einer vollautomatisierten Session heraus.
  **Pfad-Sperre für Score-/Freeze-Dateien technisch möglich:** ja — ein
  CI-Guard-Skript (`git diff --name-only`/AST-Funktionskörper-Scan gegen
  eine feste Verbotsliste: `score()`/`score_bonus()`/
  `compute_conviction_score()`/`apply_*_scores()`/
  `backtest_history.json`/`matured_backtest_export.jsonl`/die Freeze-
  Blöcke in SESSION_HANDOVER.md) kann einen automatisiert erzeugten PR
  VOR dem Draft-Öffnen oder als eigener CI-Check ablehnen — analog der in
  dieser Session selbst genutzten heading-anchored-Diff-Technik. Eine
  reine CLAUDE.md-Anweisung an den Agenten ist KEIN technischer Schutz,
  nur ein zusätzlicher (bereits bestehender) Verhaltens-Hinweis — der
  CI-Guard ist der empfohlene technische Backstop, unabhängig davon,
  welcher der beiden Wege gewählt wird. **Beide Wege NICHT gebaut** —
  reiner Bericht per Auftrag.

  **Gebaut:** je Quelle ein fail-soft Akkumulator (erwartet/erhalten/
  Fehlertyp, Seiteneffekt-Zähler NUR in den jeweiligen `except`-Zweigen —
  legitime Leer-Pfade zählen NICHT), Flag `COVERAGE_LOG_ENABLED=True`,
  Persistenz `coverage_history.jsonl` (idempotent über `(date, run_phase,
  quelle)`), Digest-Zeile je Quelle + Warnzeile bei 0-Erhalten-in-allen-
  Läufen-eines-24h-Fensters + EINE Übersichtszeile „N von M Quellen unter
  Baseline". Kein Push, nur Digest. Bestehende Digest-Zeilen/Zähler
  unverändert.

  **Kein Eingriff in `score()`/Top-10/Filter/Push/`apply_agent_boost`/
  Conviction** durch diese PR (Regel 8c nicht einschlägig — siehe Mini-
  Stopp 0c, inkl. der transparent berichteten Vor-Bestands-Situation).
  `open_items.json`: `datenquellen-coverage-inventur` auf `erledigt`
  gesetzt, neuer Eintrag `coverage-waechter-baseline` (`beobachtet`,
  34→35 Items). Golden byte-identisch, Score-/Top-10-Gegenprobe (options/
  earnings-Felder auf Fixture) grün, 157 CI-Tests grün (22 neue in
  `mock_test_coverage_watchdog.py`), `lint_nan_bypass_fields.py` grün
  (Baseline-Zeilennummern nachgeführt, reine Verschiebung in
  generate_report.py UND ki_agent.py).

  **Rückweg:** `COVERAGE_LOG_ENABLED=False` schaltet Persistenz+Digest ab
  (Instrumentierungs-Zähler selbst bleiben als No-Op aktiv — kein Risiko).
  `git revert` des Merge-Commits entfernt den gesamten Stand.

### 22.10.2026 — Stiller-Leer-Ausfall-Erweiterung (Folge-PR zum generischen Daten-Abdeckungs-Wächter) (1 PR)

- **Stiller-Leer-Ausfall-Erweiterung `coverage_history.jsonl` (additives
  Schema, Block-1-Pflicht befolgt, Manual-Merge — Schema-Erweiterung,
  Easy mergt am iPhone):** `#595` (Branch-Commit `c97f8df3`, 22.10., kein
  Merge-Hash genannt — Regel a) greift). Schließt eine Lücke in
  `#594`: der Wächter zählte bisher nur `n_erwartet`/`n_fehler`
  (Exceptions) — ein STILLER Ausfall (Quelle antwortet, liefert aber
  leer/`None` OHNE Exception) blieb unsichtbar. Genau dieses Muster ließ
  die Karten-News 19 Tage unbemerkt (`#593`).

  **SCHRITT 0a — "Daten erhalten" je Quelle + stille Schluck-Pfade (ohne
  `_coverage_record_error`-Treffer):**

  | Quelle | "Daten erhalten" = | Stiller Schluck-Pfad (Antwort ok, inhaltlich leer, KEINE Exception) |
  |---|---|---|
  | `options_atm` | `get_options_data()` liefert nicht-leeres Dict (`pc_ratio`/`atm_iv`/`expiry` gesetzt) | `if not expiries: return {}` + `if calls.empty or puts.empty: return {}` — legitim bei Tickern ohne Optionsmarkt, ABER würde auch eine Yahoo-API-Strukturänderung (immer leere `expiries`) identisch maskieren |
  | `earnings_date` | `get_earnings_date()` liefert `(days, date_str)` ≠ `(None, None)` | `cal is None`/leere `dates`-Liste/alle Termine in der Vergangenheit — legitim bei Tickern ohne anstehenden Termin, ABER ein Format-Wechsel bei `yf.Ticker.calendar` (weder `DataFrame` noch `dict`) liefert identisch `(None, None)` |
  | `earnings_surprise` | `get_earnings_surprise()` liefert nicht-`None`-Dict | `hist is None`/leer/fehlende Spalten/kein Actual-Estimate-Paar — legitim bei fehlender Historie, ABER eine Spalten-Umbenennung bei yfinance liefert identisch `None` |
  | `reddit_mentions` | `fetch_reddit_mentions()` liefert `count > 0` | **Konkretester Fund:** `resp.json().get("data",{}).get("children",[])` liefert `[]` OHNE Exception, wenn Reddit statt echter Suchergebnisse eine Rate-Limit-/Fehler-JSON mit HTTP 200 zurückgibt (`{"error":429,...}`) — von "genuin 0 Mentions" nicht unterscheidbar |
  | `fda_calendar` | `fetch_fda_calendar()` liefert nicht-leeres Dict | gültige RSS-Struktur mit 0 `<item>`-Treffern — legitim an den meisten Tagen (kein PDUFA-Approval), ABER identisch zu einer stillen Feed-URL-/Struktur-Änderung |
  | `openinsider` | `fetch_openinsider()` liefert `count > 0` | gültige RSS-Struktur mit 0 passenden `<item>`-Treffern — dieselbe Doppeldeutigkeit wie bei `fda_calendar` |

  **Widerspruch/Grenze ehrlich benannt:** bei KEINER der 6 Quellen ist
  "leer" technisch von "Fehler" sauber trennbar, ohne die Zielsysteme
  selbst zu befragen (z. B. Yahoo/Reddit/FDA-Betreiber fragen "ist euer
  Feed gerade kaputt?") — die hier gebaute Lösung behandelt das
  statistisch (Fenster-Aggregation über Zeit), nicht strukturell. Das ist
  eine bewusste, dokumentierte Grenze, keine vollständige Lösung.

  **SCHRITT 0b — Mini-Stopp: KEIN STOPP.** Das Zählen von `n_mit_daten`
  ist eine reine BEOBACHTUNG des bereits berechneten Rückgabewerts an den
  jeweiligen Call-Sites (`main()` in generate_report.py,
  `_process_ticker`/`main()` in ki_agent.py) — kein Rückgabewert, keine
  Anfragezahl geändert (Test-Beleg: `test_*_zero_behavior_change`-Tests
  je Quelle in `scripts/mock_test_coverage_silent_empty.py`).

  **Gebaut:**
  1. Neues additives Feld `n_mit_daten` in `coverage_history.jsonl`
     (`None`/`null` wenn der Aufrufer es nicht setzt — alte Zeilen vor
     dieser PR bleiben lesbar, werden fail-soft aus den Fenstern
     ausgeschlossen statt als `0` fehlinterpretiert).
  2. Zwei Digest-Warnzeilen-Fenster (`config.py`):
     `COVERAGE_SILENT_EMPTY_WINDOW_HOURS_DENSE` (24 h) für `options_atm`/
     `earnings_date` (mehrere Ticker pro Lauf — ein Komplettausfall ist
     schon nach 1 Tag verdächtig), `COVERAGE_SILENT_EMPTY_WINDOW_HOURS_
     SPARSE` (24×7 = 168 h) für die übrigen 4 Quellen (ein einzelner
     leerer Tag ist dort normal). `coverage_overview_line` berücksichtigt
     jetzt BEIDE Warnarten (Call-Ebene + Inhalts-Ebene).
  3. Bestehende Digest-Zeilen/Zähler unverändert (Vorher/Nachher-Beleg
     gegen `origin/main`).

  **Ziel erreicht (Exzellenz-Block):** ein Ausfall nach dem Karten-News-
  Muster erscheint bei `options_atm`/`earnings_date` spätestens nach 24 h,
  bei den übrigen 4 Quellen spätestens nach 7 Tagen im Digest
  (Fixture-Belege je Quelle in `scripts/mock_test_coverage_silent_empty.py`).

  Golden byte-identisch, Score-/Top-10-Gegenprobe grün, 158 CI-Tests grün
  (14 neue in `mock_test_coverage_silent_empty.py`), `lint_nan_bypass_
  fields.py` grün (Baseline nachgeführt, reine Verschiebung in
  generate_report.py UND ki_agent.py). `open_items.json`:
  `coverage-waechter-baseline` additiv um die neuen Schwellen ergänzt
  (35→35 Items, keine neuen Einträge — reine Beschreibungs-Erweiterung).

  **Rückweg:** `git revert` des Merge-Commits entfernt den gesamten
  Stand (altes Schema ohne `n_mit_daten` bleibt für `COVERAGE_LOG_
  ENABLED=True` weiterhin funktionsfähig, da additiv).

### 22.10.2026 — Fällige Wiedervorlagen im Digest (Folge-PR zur Open-Items-Pflege) (1 PR)

- **Fällige Wiedervorlagen automatisch im täglichen Health-Check-Digest
  (additives Schema, Block-1-Pflicht befolgt, Manual-Merge — neues Feld
  in `open_items.json`, Easy mergt am iPhone):** `#596` (Branch-Commit
  `fab38aba`, 22.10., kein Merge-Hash genannt — Regel a) greift). Bisher
  hingen alle Wiedervorlage-Termine ausschließlich an Easys/Claudes
  Erinnerung — reiner Freitext in `description`-Feldern bzw.
  `SESSION_HANDOVER.md`, keine automatische Erinnerung.

  **SCHRITT 0a (Python-Inspektion):** 0 von 35 Items hatten irgendein
  maschinenlesbares Datumsfeld. 8 Items erwähnen "Wiedervorlage" im
  Freitext; 32 von 35 enthalten irgendeinen datumsförmigen String (meist
  unrelated `opened`/`status_date`).

  **SCHRITT 0b — Mini-Stopp: neues Feld `faellig_am` (optionales ISO-
  Datum) nötig → Manual-Merge.** Alle Konsumenten von `open_items.json`
  gegrept — `.get()`-basiert, additiv-sicher.

  **SCHRITT 0c — vier benannte Termine, NICHT programmatisch aus
  Freitext geparst, sondern manuell zugeordnet:** `nyse-regsho-empty-
  streak` → `2026-10-26` (wörtlich im Item-Text). `ki-score-edge-freeze`
  → `2026-10-28` (wörtlich im Item-Text, "WIEDERVORLAGE 28.10.2026").
  `options-chain-raw-sammelfeld` → `2026-10-28` — dieses Item trägt
  ZWEI Wiedervorlagen (näher ~10 Handelstage nach 17.10., ferner
  02.11.-Monatsrundgang), das Feld hält nur EIN Datum pro Item → trägt
  Wiedervorlage 1, Wiedervorlage 2 bleibt Freitext-only, transparent als
  Nachtrag im Item selbst dokumentiert. 02.11.-Monatsrundgang selbst
  **nicht** zusätzlich abgesichert — hat laut diesem Dokument bereits
  einen eigenen geplanten Cloud-Lauf-Trigger (09:00 Berlin).

  **Ehrlich benannter Widerspruch:** `ibkr-borrow-data-spur` erwähnt
  ebenfalls die 02.11.-Wiedervorlage, ist aber bereits `status:
  "erledigt"` — `due_items_lines()` listet nur `offen`/`beobachtet`,
  ein `faellig_am` dort würde nie im Digest erscheinen. Bewusst
  **nicht** ergänzt, hier nur gemeldet.

  **Gebaut:** `health_check.due_items_lines(now_ts, path=...)` —
  Berlin-Zeitzonen-korrekt (`astimezone(ZoneInfo("Europe/Berlin"))` vor
  dem Datumsvergleich, da ein UTC-Lauf kurz nach Mitternacht in Berlin
  schon den nächsten Kalendertag sieht), fail-soft, `erledigt`-Items nie
  gelistet. Zwei Zeilenarten: `📅 Heute fällig: <id> – <Kurztitel>` /
  `⏰ Überfällig seit N Tagen: <id>`. Täglich verdrahtet in
  `scripts/health_check_digest.py` (kein Montag-Gate wie der
  Wochenblock). `format_digest_body` bekommt den additiven Parameter
  `due_items_lines_` (vor `weekly_lines` in allen drei Response-
  Klassen, Backward-kompatibel). `lint_open_items_consistency.py`
  erweitert: `faellig_am` muss, wenn gesetzt, ein valides ISO-Datum
  sein. `open_items.json`: drei Items um `faellig_am` ergänzt (siehe
  oben), 35→35 Items (keine neuen Einträge, nur Felder).

  **Neue Regel für künftige Wiedervorlagen:** ab sofort bekommt jede
  neu entstehende Wiedervorlage mit konkretem Kalenderdatum (nicht
  relativ/zähler-basiert) ein `faellig_am`-Feld im zugehörigen
  `open_items.json`-Item — sonst bleibt sie unsichtbar für den Digest
  und hängt wieder an reiner Erinnerung.

  Golden byte-identisch, 159 CI-Tests grün (14 neu in
  `scripts/mock_test_open_items_due_digest.py`: heute fällig,
  überfällig, `erledigt` nie gelistet, fehlendes/kaputtes Datum
  fail-soft, Zeitzonen-Grenze, fehlende/kaputte Datei, Lint-
  Validierung, `format_digest_body`-Verdrahtung + Backward-Compat,
  Score-Gegenprobe), alle Lints grün (keine Baseline-Verschiebung
  nötig). Setup-Edge-Re-Test-Freeze- und KI-Score-Edge-Test-Freeze-
  Block byte-identisch unverändert (heading-anchorter Diff). Kein
  `score()`-/Top-10-/Filter-/Push-Touch.

  **Rückweg:** `git revert` des Merge-Commits — `open_items.json`
  bleibt dann ohne `faellig_am`-Felder (rückwärtskompatibel, da
  additiv), der Digest zeigt wieder keine Fälligkeits-Zeilen.

### 22.10.2026 — Freeze-Auswertungs-Autorun (Setup-Edge/Conviction + KI-Score) (1 PR)

- **Freeze-Auswertungs-Autorun `scripts/freeze_eval.py` (Block-1-Pflicht
  befolgt, Manual-Merge — neues Schema `eval_results.jsonl` + neuer
  Workflow-Step, Easy mergt am iPhone):** `#597` (Branch-Commit
  `ebb1eda7`, 22.10., kein Merge-Hash genannt — Regel a) greift). Setzt
  den Auftrag "Auswertung startet bei n=250 von
  selbst" um — die eingefrorenen Setup-Edge/Conviction- (10.10.2026 +
  Erratum) und KI-Score-Edge-Test-Freezes (13.10.2026 + Erratum 16.10.)
  laufen jetzt automatisch EINMAL, sobald ihr jeweiliger Auslöser (n>=250)
  erreicht ist, statt auf manuelles Anstoßen zu warten.

  **SCHRITT 0 (read-only, VOR dem Bau) fand zwei Lücken im Freeze-Text,
  gemeldet statt gefüllt (OBERSTE REGEL):** (1) kein numerischer Bootstrap-
  Seed in beiden Freezes ("fester Seed" ohne Zahl, zirkulärer Verweis auf
  §4, das selbst keine Zahl nennt); (2) keine Ausschluss-Regel für
  fehlenden `conviction_score` in Test c (im Gegensatz zum KI-Score-
  Freeze, der den analogen Fall explizit regelt). Easy hat per **ERRATUM
  22.10.2026** (eigener Block direkt nach den beiden Freeze-Blöcken,
  BEIDE Freezes inkl. ihrer bisherigen Errata byte-identisch belassen —
  heading-anchorter Diff-Beleg) entschieden: Seed=42 (beide Familien),
  95% zweiseitiges Perzentil-Intervall (2,5./97,5.), Test-c-Ausschluss-
  Regel als Spiegel der KI-Score-Regel vom 16.10. Keine Outcome-Werte
  wurden dabei eingesehen.

  **Gebaut:**
  1. `scripts/freeze_eval.py` — reine, synthetisch getestete Statistik-
     Primitive (`bootstrap_auc_ci`, `paired_bootstrap_delta_auc` nach dem
     im Conviction-Erratum wörtlich spezifizierten Verfahren,
     `cluster_double_run`) + Familien-Orchestrierung
     (`evaluate_setup_edge_family` Tests a/b/c Holm k=3,
     `evaluate_ki_score_family` Tests a/b eigene Holm-Familie k=2) +
     `run_due_evaluations` (File-I/O, Trigger-Check, Sperre).
  2. **Sperre = `eval_results.jsonl` selbst** (kein separates Lock-Feld):
     ein Test-ID mit bereits vorhandener Zeile wird NIE erneut
     ausgewertet, auch bei weiterhin erfülltem Auslöser — kein Peeking.
  3. **Fehlender KI-Score-Populationszähler** (health_check.py) ergänzt
     — die KI-Score-Freeze-Doku (13.10.) hatte ihn bewusst offen gelassen
     ("Dieser PR baut nur die Doku, kein Digest-Code"); jetzt exakt nach
     Erratum 16.10.2026 implementiert (`_is_ki_score_population_row`,
     `_count_ki_score_freeze_population`), Single-Source-of-Truth-Reuse
     der Setup-Edge-Helper (`_is_freeze_population_row` etc.) wo möglich.
  4. Zwei neue Digest-Zeilen (`health_check.eval_status_line`): vor
     Auslösung `"🧪 <Familie>: n = x/250, ca. y Zeilen/Tag"`, nach
     einmaliger Auslösung `"🧪 <Familie> ausgewertet: <Verdikt>, Details
     in eval_results.jsonl"`. Zusätzlich EIN ntfy-Push pro Familie, nur
     bei Auslösung.
  5. `config.EVAL_AUTORUN_ENABLED` (Default `False`) — Master-Switch,
     Rückweg: `False` setzen UND `git revert` des Merge-Commits.
  6. `.github/workflows/health_check_digest.yml`: Commit-Step um
     `eval_results.jsonl` erweitert (analog zum bestehenden State-File-
     Save/Restore/git-add-Muster — Lehre #501, sonst ginge ein neu
     geschriebenes `eval_results.jsonl` beim nächsten `reset --hard`
     verloren).

  **Verdikt-Logik** (Freeze-Grenzen-Klausel wörtlich umgesetzt): "Beleg"
  nur wenn ALLE vier Erfolgskriterien erfüllt sind, sonst "Unklar" — NIE
  "keine Edge" bei n≈250 (per Fixture belegt: Null-Effekt-Fixture liefert
  durchgehend "Unklar", nie eine falsch-positive "Beleg"-Meldung).

  **Entwicklung ausschließlich auf synthetischen Fixtures** (Auftrags-
  Vorgabe) — keine echten `return_*`-Werte wurden angesehen. Fixture-
  Belege: starker eingebauter Effekt → `point_auc` nahe 1,0, CI-
  Untergrenze > 0,5; kein Effekt → `point_auc` nahe 0,5, CI schließt 0,5
  ein; echter Conviction-Zusatznutzen → ΔAUC deutlich > 0 (Test c
  "Beleg"); Conviction ≈ Score + Rauschen → ΔAUC ≈ 0 (Test c "Unklar").
  Determinismus belegt (gleicher Seed → zweimal identisches Ergebnis).
  Sperre belegt (zweiter Lauf auf denselben Daten erzeugt keine neue
  Zeile, keinen zweiten Push).

  Golden byte-identisch, 160 CI-Tests grün (29 Checks neu in
  `scripts/mock_test_freeze_eval_autorun.py`, 48 Einzel-Assertions),
  `lint_nan_bypass_fields.py` grün (Baseline-Zeilennummer nachgeführt,
  reine Verschiebung). `open_items.json`: drei Items additiv aktualisiert
  (`paired-bootstrap-auc-delta-setup-edge` → `erledigt`, Infrastruktur ist
  jetzt gebaut; `setup-edge-retest-freeze` + `ki-score-edge-freeze` →
  Nachtrag, Status bleibt `beobachtet`, Auslöser ist noch nicht erreicht;
  35→35 Items). Kein `score()`-/Top-10-/Filter-/Push-/Conviction-Touch.

  **Rückweg:** `config.EVAL_AUTORUN_ENABLED = False` setzen UND
  `git revert` des Merge-Commits — `eval_results.jsonl` (falls bis dahin
  bereits etwas ausgelöst hat) bleibt als reine Analyse-Persistenz
  stehen, kein Konsument liest sie außerhalb des Digests.

### 22.10.2026 — Holm-Input Test c präzisiert + Freeze-Auswertungs-Autorun scharf geschaltet (1 PR)

- **Erratum 22.10.2026 (b) + Scharfschaltung `config.EVAL_AUTORUN_ENABLED`
  (Block-1-Pflicht befolgt, Manual-Merge — Erratum-Block + Master-Switch-
  Flip, Easy mergt am iPhone):** `#598` (Branch-Commit `e7582bf1`, 22.10.,
  kein Merge-Hash genannt — Regel a) greift). Schließt die von PR #597
  selbst (Code-Kommentar +
  squeeze-guardian) offen geflaggte Lücke: der Holm-Input `p_c` für Test c
  (Conviction-Zusatznutzen) war implementiert als Mann-Whitney-p von
  `AUC(conviction_score)` gegen den Split, nirgends aber **wörtlich** als
  diese Lesart festgelegt — nur strukturparallel zu Tests a/b gewählt.

  **Erratum 22.10.2026 (b)** (eigener Block direkt nach Erratum 22.10.2026
  (a), beide Freeze-Blöcke + alle bisherigen Errata byte-identisch belassen
  — heading-anchorter Diff-Beleg): `p_c` ist jetzt verbindlich der
  **zweiseitige Bootstrap-p-Wert der ΔAUC-Verteilung selbst** (aus dem
  bereits für das CI berechneten gepaarten Bootstrap, N=2000, Seed 42):
  `p_c = min(1, 2 · min(Anteil Resamples mit ΔAUC≤0, Anteil Resamples mit
  ΔAUC≥0))` — **nicht** der p-Wert von `AUC(conviction_score)` gegen 0,5.
  Die Teilbedingung „`AUC(conviction_score) ≥ 0,55`" (Erfolgskriterium
  (iv)) bleibt als reine Punktschätzungs-Schwelle unverändert.

  **Gebaut:** `scripts/freeze_eval.py:paired_bootstrap_delta_auc` liefert
  jetzt zusätzlich `p_two_sided` (Proportion auf der bereits berechneten
  Resample-Verteilung, kein zweiter Bootstrap-Lauf). `evaluate_setup_edge_
  family` liest `p_c` jetzt aus `cluster_c_delta` statt `cluster_c_auc`.
  Tests a, b und die KI-Score-Familie unverändert (Fixture-Belege
  identisch zu vorher). Fixture-Tuning: der bisherige "kein Zusatznutzen"-
  Fixture-Zweig in `scripts/mock_test_freeze_eval_autorun.py` nutzte einen
  zu deterministischen Score-Return-Zusammenhang (AUC≈0,98) — dort wurde
  selbst die kleinste Rausch-Degradierung durch `conviction_score`
  hochsignifikant (`p_c≈0,002`), was die erwartete "kein Zusatznutzen →
  `p_c` groß"-Demonstration verdeckt hätte. Auf ein schwächeres, realistischeres
  Signal (AUC≈0,55–0,65) umgestellt — Beleg: `p_c≈0,47` für identische
  Seeds bei echtem Nicht-Effekt, `p_c=1,0` exakt bei identischen Scores
  (reine Formel-Verriegelung, neuer Test).

  **`config.EVAL_AUTORUN_ENABLED = True`** (vorher `False`) — der Automat
  für beide Familien ist jetzt aktiv. **Vorher belegt (reine Zählung,
  keine `return_*`-Werte eingesehen):** Setup-Edge/Conviction n=0/250,
  KI-Score n=0/250 (beide aus `matured_backtest_export.jsonl`, 1247
  Export-Zeilen gesamt) — das Scharfschalten startet heute **nachweislich
  keine** Auswertung. Smoke-Test gegen die echten Repo-Daten (dry-run)
  bestätigt: kein `eval_results.jsonl` wird angelegt, beide Digest-Zeilen
  bleiben im Vor-Auslöser-Format.

  Golden byte-identisch, 160 CI-Tests grün (3 Tests neu/ersetzt in
  `scripts/mock_test_freeze_eval_autorun.py`: Formel-Verriegelung `p_c`,
  Holm-Input-Quelle explizit geprüft, Scharfschaltung-ohne-Trigger auf
  synthetischer Fixture — die vorherige „Default False"-Prüfung wurde
  durch eine „explizit deaktiviert"-Variante ersetzt, da der Produktions-
  Default jetzt `True` ist), alle 5 Lints grün (keine Baseline-
  Verschiebung nötig). `open_items.json`: zwei Items additiv aktualisiert
  (`setup-edge-retest-freeze` + `ki-score-edge-freeze` → Nachtrag „scharf
  geschaltet, n=0/250 nachweislich nicht ausgelöst", Status bleibt
  `beobachtet`; 35→35 Items). Kein `score()`-/Top-10-/Filter-/Push-/
  Conviction-Touch (einziger Push-Pfad ist der in PR #597 bereits gebaute,
  heute mangels Auslöser inaktive Ergebnis-Push).

  **Rückweg:** `config.EVAL_AUTORUN_ENABLED = False` setzen UND
  `git revert` des Merge-Commits.

### 22.10.2026 — News-Coverage-Reihenfolge-Fehlalarm-Fix + KI-Agent-Coverage-Stiller-Kollaps-Fix (1 PR)

- **Zwei Bugfixes am Coverage-Watchdog-System selbst (Block-1-Pflicht
  befolgt, Auto-Merge — reine Logging-/Wächter-Korrektur ohne Schema-
  Änderung):** `#599` (Branch-Commit `29b06d60`, 22.10., kein Merge-Hash
  genannt — Regel a) greift) behebt zwei
  eigenständige Befunde im erst gestern/vorgestern eingeführten Coverage-
  Watchdog-System (`#594`/`#595`/`#596`).

  **Befund A — News-Wächter-Fehlalarm (Reihenfolge-Bug):** der Aufruf
  `_persist_news_coverage(top10, enriched, run_phase=run_phase)` saß in
  `main()` (generate_report.py) VOR dem eigentlichen News-Fetch+Attach-
  Block ("Step 3"), nicht danach. `_news_coverage_pool_split` zählt über
  `s.get("news")` — das Feld existierte zum Zählzeitpunkt noch gar nicht,
  jeder Lauf zählte deshalb strukturell 0/0, unabhängig davon ob die
  Karten tatsächlich News hatten (laut `app_data.json` hatten sie: WOLF 3,
  GRPN 3, IONQ 3, AMC 3, VEEA 2). Der Kommentar am Call-Site ("News wurden
  in Step 3 ohnehin geholt") war beim Einführungs-PR faktisch falsch —
  Step 3 lief zu dem Zeitpunkt noch NICHT. **Fix:** Call-Site nach den
  News-Fetch+Attach-Block verschoben (läuft weiterhin in jeder Phase, kein
  zusätzlicher Fetch), Kommentar + Docstring korrigiert. Beleg:
  End-to-End-Test (`scripts/mock_test_news_coverage_watchdog.py`) simuliert
  die reparierte Reihenfolge auf Fixture-Daten — Zähler ist jetzt >0 wenn
  News gesetzt sind, Request-Count (`yfinance_raw`) unverändert.

  **Befund B — KI-Agent-Coverage schreibt nur sporadisch (stiller
  Idempotenz-Kollaps):** Ursache war der Idempotenz-Schlüssel in
  `health_check.persist_coverage_row`/`_load_coverage_keys`:
  `(date, run_phase, quelle)`. `ki_agent.py` ruft das bei JEDEM stündlichen
  Tick mit der KONSTANTEN Phase `run_phase="ki_agent_tick"` auf — der
  Schlüssel kollabierte dadurch ALLE Ticks eines Tages auf einen einzigen
  erlaubten Write (der erste Tick, 04:47, schrieb; 10:11/11:55/15:17/19:16
  desselben Tages wurden als "bereits vorhanden" übersprungen — nur auf
  `log.info`, praktisch unsichtbar). `generate_report.py`s eigene Aufrufe
  (`run_phase="premarket"`/`"postclose"`, je höchstens 1×/Tag) waren davon
  nicht betroffen — dort passte die Schlüssel-Form zufällig. **Fix:**
  neue Schlüssel-Komponente `tick_hour` (= `now_fn().strftime("%H")`, NUR
  wenn `run_phase=="ki_agent_tick"`, sonst `None` — generate_report.py's
  Verhalten bleibt dadurch exakt unverändert, per Regressionstest belegt).
  `tick_hour` wird zusätzlich additiv persistiert. Zusätzlich (explizit
  verlangt): Persist-Fehler in `ki_agent.py` jetzt `log.warning` statt
  `log.debug`.

  **Nicht angefasst (harte Grenze eingehalten):** `score()`,
  `ki_signal_score`, `apply_agent_boost`, Top-10, Filter, Push, Conviction,
  `return_*`-Felder, Freeze-Blöcke/Errata — alle byte-identisch.

  7 neue Tests (3× News-Coverage-Reihenfolge, 4× Coverage-Idempotenz/
  Legacy-Row/Log-Level), Golden byte-identisch, alle 5 Lints grün
  (`lint_nan_bypass_fields.py`-Baseline nachgeführt, reine
  Zeilennummern-Verschiebung durch die Call-Site-Verlegung + Docstring-
  Erweiterung — keine neuen NaN-Bypass-Funde).

  **Teil 2 (reine Diagnose, kein Code-Effekt):** drei KI-Agent-Quellen
  (`reddit_mentions`, `openinsider`, `fda_calendar`) liefern seit
  mindestens 17.08.2026 (belegt per GitHub-Actions-Workflow-Log,
  `"Reddit: geblockt — Score 0."` + FDA-404 auf eine FDA.gov-Anti-Bot-
  Apology-Seite) keine echten Daten mehr — Details siehe PR-Beschreibung
  #599 und Abschlussbericht dieser Session.

  **Rückweg:** `git revert` des Merge-Commits von PR #599.

### 23.10.2026 — Reddit-Aufmerksamkeits-Schattensammlung (ApeWisdom) (1 PR)

- **Neue Schattensammlung für Reddit-Aufmerksamkeit (Block-1-Pflicht
  befolgt, Manual-Merge — neue externe API + neues JSONL-Schema, Easy
  mergt am iPhone):** `#600` (Branch-Commit `601788b9`, 23.10., kein
  Merge-Hash genannt — Regel a) greift) setzt
  Easys Entscheid vom selben Tag um: die seit mind. 27.07.2026 toten
  ki_agent.py-Quellen `reddit_mentions`/`openinsider`/`fda_calendar`
  (siehe PR #599-Bericht) werden NICHT live reaktiviert, bevor die
  laufende KI-Score-Freeze-Auswertung (`#597`/`#598`, Stand 22.10.2026
  n=0/250) abgeschlossen ist. Stattdessen entsteht eine komplett
  SEPARATE, additive Reddit-Aufmerksamkeits-Zeitreihe über die
  öffentliche ApeWisdom-API (apewisdom.io, kein Key/Login nötig) — als
  Datenbasis für eine spätere, eigene Hypothesenprüfung NACH dem Freeze.

  **SCHRITT 0 (read-only, vor dem Bau):**
  - **0a** ApeWisdom-API: öffentlicher Endpunkt
    `GET https://apewisdom.io/api/v1.0/filter/{filter}/page/{page}`,
    Felder `ticker`/`mentions`/`mentions_24h_ago`/`rank`/`rank_24h_ago`/
    `upvotes`. Kein Key/Login, laut Produktbeschreibung dediziert für
    Reddit-Stock-Mentions gebaut. Rate-Limit offiziell undokumentiert
    (Community-Berichte ~20 Req/Min/IP) — **kein** Mini-Stopp-Trigger
    (nicht kostenpflichtig, kein Login, keine gefundene ToS-Untersagung
    von automatisiertem Abruf). Exakte Feld-Semantik NICHT live
    gegen die API verifiziert — Websuche + Trainingswissen, kein
    `WebFetch` möglich (Sandbox-Netzwerk-Policy blockt die Domain, siehe
    0b).
  - **0b** Erreichbarkeit vom GitHub-Actions-Runner: aus dieser Sandbox
    NICHT prüfbar (`curl` über den Agent-Proxy liefert `403 CONNECT
    tunnel failed` — Policy-Denial, nicht die ApeWisdom-API selbst).
    Erster echter Workflow-Lauf ist der Beleg.
  - **0c** Universum: Top-10 ∪ persönliche Watchlist (identischer Pool
    wie `_news_pool` — kein neuer Pool-Bau), aktuell ~14-15 Ticker. EIN
    Bulk-Abruf der ApeWisdom-"all-stocks"-Gesamtliste pro Lauf
    (`APEWISDOM_API_PAGES=2` × 100 Einträge = Top-200), lokal gegen den
    Pool gefiltert — **kein** Request pro Ticker (Easy-Vorgabe). Macht
    die Anfragezahl unabhängig von der Pool-Größe: max. 2 Requests/Lauf
    × 2 Läufe/Tag (premarket + postclose) = 4 Requests/Tag gesamt.
  - **0d** Mini-Stopp Konsumenten: Grep bestätigt — `apewisdom`/
    `APEWISDOM` kommt in KEINER anderen Datei vor außer
    `generate_report.py`, `health_check.py`, `config.py`,
    `scripts/health_check_digest.py` und den neuen Tests. `score()`,
    `_compute_sub_scores()`, `apply_agent_boost()` (generate_report.py)
    und `compute_signal()` (ki_agent.py) lesen das Wort nirgends — zudem
    per Source-Inspektions-Test verriegelt
    (`scripts/mock_test_apewisdom_shadow.py`, Abschnitt 7). Mini-Stopp
    git-add-in-allen-Workflow-Listen (Lehre #501): `coverage_history.jsonl`
    ist bereits in beiden Workflows ge-add-ed (apewisdom_shadow ist nur
    eine 7. Quelle in dieser bestehenden Datei, kein neues git add nötig);
    die NEUE `apewisdom_attention_history.jsonl` läuft NUR in
    `daily-squeeze-report.yml` (nie über den stündlichen ki_agent-Tick —
    bewusst, siehe Befund-B-Lehre aus #599) → git add NUR dort ergänzt,
    `ki_agent.yml` braucht keinen Eintrag.

  **BAU:**
  - `generate_report.py`: `_fetch_apewisdom_attention()` (EIN Bulk-Abruf,
    paginiert, fail-soft → `{}` bei jedem Fehler) +
    `_persist_apewisdom_attention()` (append-only JSONL, eine Zeile je
    Ticker und Tag, idempotent über `(date, ticker)` — Lehre aus #599
    bewusst umgangen: läuft NUR hier, max. 2×/Tag, nie stündlich). Beide
    Funktionen hängen in `main()` direkt nach dem News-Coverage-Persist-
    Call, nutzen den bereits gebauten `_news_pool`.
  - Flag `APEWISDOM_SHADOW_ENABLED=True` (config.py) schaltet den
    gesamten Baustein ab — additiv.
  - **Generischer Daten-Abdeckungs-Wächter:** `apewisdom_shadow` als 4.
    Quelle in `_COVERAGE_ACCT` (generate_report.py) + neuer Eintrag in
    `config.COVERAGE_QUELLEN` + `COVERAGE_SILENT_EMPTY_SPARSE_QUELLEN`
    (Small-Cap-Abdeckung ist strukturell sparse, nicht dense — bewusste
    Einordnung gegen Alarm-Müdigkeit). Besonderheit: EIN Bulk-Call bedient
    den ganzen Pool — bei Fetch-Fehler wird `n_fehler` auf die GANZE
    Pool-Größe gesetzt (nicht nur 1), sonst hätte `n_erhalten` fälschlich
    fast den vollen Pool gezeigt, obwohl der einzige zugrundeliegende
    Call gescheitert ist.
  - Neue, eigene Digest-Zeile `apewisdom_attention_digest_line()`
    (health_check.py) — Format „🗣 Reddit-Schatten (ApeWisdom): läuft ·
    {n} Ticker · {m} Punkte" (Summe der Mentions am letzten Sammel-Tag).
    In `format_digest_body()` (neuer `apewisdom_line`-Parameter, additiv
    in allen 3 Klassen) + `scripts/health_check_digest.py` verdrahtet.
  - **Harte Grenzen eingehalten:** kein Eingriff in `score()`,
    `ki_signal_score`, `apply_agent_boost`, Top-10, Filter, Push,
    Conviction, Exit; keine neue Bibliothek (nur `requests`, bereits
    importiert); keine `return_*`-Werte; Freeze-Blöcke byte-identisch.

  19 neue Tests (`scripts/mock_test_apewisdom_shadow.py` — Fetch/Parse,
  Persist/Schema/Coverage-Buchung, Idempotenz, COVERAGE_QUELLEN-
  Eintragung, Digest-Zeile, `format_digest_body`-Verdrahtung, Grep-Beleg
  + Score-/Top-10-Gegenprobe), Golden byte-identisch, alle 5 Lints grün
  (`lint_nan_bypass_fields.py`-Baseline erneut nachgeführt — reine
  Zeilenverschiebung durch die ~160 neuen Zeilen vor der Hauptschleife,
  per Diff-Hunk-Arithmetik exakt nachgerechnet und gegen den frischen
  Lint-Lauf verifiziert, keine neuen NaN-Bypass-Funde).
  `open_items.json`: zwei neue Einträge `reddit-shadow-apewisdom`
  (beobachtet, Wiedervorlage nach KI-Score-Freeze-Auswertung) +
  `openinsider-fda-tot` (erledigt/dokumentiert — Begründung: OpenInsider
  ist redundant zu der bereits vorhandenen SEC-Form-4-Quelle, FDA-Calendar
  hat keinen gefundenen kostenlosen Ersatz) — 35→37 Items.

  **Widerspruch zu melden (EXZELLENZ-BLOCK-Pflicht):** ApeWisdoms
  Reddit-Liste konzentriert sich erfahrungsgemäß auf liquide Mega-/
  Large-Caps (GME/AMC/TSLA-Klasse) — viele der hier typischen Squeeze-
  Kandidaten (Small-/Micro-Caps) könnten in den Top-200 schlicht NICHT
  auftauchen. Das wäre dann ein legitimes „nicht erwähnt", kein Fehler —
  aber die praktische Abdeckung für genau die Ticker, die diesem Tool am
  meisten nutzen würden, könnte dünn ausfallen. Erst die echte Live-
  Baseline (Wiedervorlage nach dem KI-Score-Freeze) zeigt, ob
  `APEWISDOM_API_PAGES` erhöht werden muss.

  **Rückweg:** `config.APEWISDOM_SHADOW_ENABLED = False` setzen UND
  `git revert` des Merge-Commits von PR #600.

### 23.10.2026 — Technische Schutz-Sperre gegen Wächter-Eingriffe in geschützte Logik (1 PR)

- **`scripts/lint_protected_zones.py` — neuer 8. PR-CI-Check (Block-1-Pflicht
  befolgt, Manual-Merge — neue Sperr-Logik mit scharfer Wirkung auf den
  täglichen Wächter-Agenten, Easy mergt am iPhone):** `#601` (Branch-Commit
  `c2251738`, 23.10., kein Merge-Hash genannt — Regel a) greift) setzt
  Easys Entscheid vom 22.10.2026 um: der
  tägliche „Wächter"-Agent (Claude Code Remote Session) erstellt und merged
  `[Wächter]`-PRs selbständig, ohne menschliche Freigabe pro PR. Diese
  Sperre ist eine MECHANISCHE Zweitsicherung gegen einen unbeabsichtigten
  Eingriff in Score-/Filter-/Push-/Exit-Logik oder die Freeze-Auswertung —
  unabhängig von der Session-Disziplin des Wächters selbst.

  **SCHRITT 0 (read-only, vor dem Bau):**
  - **0a** Geschützte Bereiche identifiziert (vollständige Liste siehe
    `_PROTECTED_FUNCTIONS`/`_PROTECTED_CONST_PREFIXES`/`_SENTINEL_FILES`/
    `_PROTECTED_WHOLE_FILES` im Lint-Skript): 20 benannte Funktionen in
    `generate_report.py` (`score`, `score_bonus`, `apply_monster_score`,
    `apply_agent_boost`, `apply_score_smoothing`,
    `apply_late_runner_penalty`, `compute_conviction_score`,
    `apply_conviction_scores`, `compute_earliness_pts`,
    `_earliness_pts_v1/v2`, `compute_exit_score`, `process_exit_signals`,
    `_compute_exit_state`, `_detect_recent_squeeze`, `_float_turnover_pts`,
    `_gap_hold_pts`, `_rs_spy_pts`, `_normalize_rvol`,
    `_compute_sub_scores`) + 4 in `ki_agent.py`
    (`compute_signal`, `detect_anomalies`, `fetch_uoa_signal`,
    `_stocktwits_pts`) + 2 in `backtest_history.py`
    (`_build_backtest_extension`, `_append_backtest_entries`); 25
    Konstanten-Präfixe in `config.py` (u. a. `MIN_PRICE`,
    `MIN_SHORT_FLOAT`, `MIN_REL_VOLUME`, `MAX_MARKET_CAP`, `ANOMALY_`,
    `EXIT_`, `COMBO_`, `SCORE_`, `AGENT_BOOST_`, `SQUEEZE_HIST_MALUS_`,
    `EARLINESS_`, `RVOL_`, `TRIGGER_`, `PUSH_` u.v.m. — minus 8 bewusst
    ausgeschlossener Display-/Status-Konstanten wie `SCORE_CONFIDENCE_*`);
    4 Sentinel-Marker-Zonen für inline-Logik in `main()` (siehe unten); alle
    `VORABREGISTRIERUNG`/`ERRATUM`-Überschriften in `SESSION_HANDOVER.md`;
    `scripts/freeze_eval.py` + `scripts/stats_helpers.py` als ganze
    Dateien. **Fehlendes gemeldet (0a-Pflicht):** die Konstanten-Liste ist
    Präfix-basiert, nicht erschöpfend aufgezählt — ein neuer Score-Pfad
    mit untypischem Namen (kein bekanntes Präfix) würde NICHT automatisch
    erfasst; Pflege-Hinweis in der Doku ergänzt.
  - **0b** Bestehende PR-CI ist `.github/workflows/pr-checks.yml`
    (Trigger `pull_request`, advisory, kein required-Status-Check) — fährt
    bereits 7 Lints + Mock-Test-Allowlist-Runner. **Kein neuer Workflow
    nötig** — ein 8. Step reicht, direkt nach dem bereits vorhandenen
    „Fetch PR base"-Step (der auch vom Open-Items-Consistency-Check
    mitgenutzt wird).

  **Widerspruch zu melden (EXZELLENZ-BLOCK-Pflicht):** `main()` in beiden
  Haupt-Dateien mischt Score-/Filter-/Push-Logik UND reine Logging-/
  Diagnose-Calls in denselben Codeblöcken (z. B. `log.info`-Zeilen
  zwischen den eigentlichen Filter-Checks der Top-10-Pipeline). Eine
  chirurgisch genaue AST-Trennung ist dort nicht robust automatisierbar —
  deshalb 4 bewusst GROSSZÜGIG geschnittene Sentinel-Marker-Zonen
  (`# PROTECTED-ZONE-START/END: <name>`-Kommentare direkt im Code
  eingefügt, nicht hartkodierte Zeilennummern — lintet live gegen den
  jeweiligen Basis-Stand): `filter-top10-selection`
  (generate_report.py, Hard-Filter + Cap-Filter + Top-10-Auswahl +
  FINRA-Bonus + finale Sortierung + Score-Smoothing-Aufruf) sowie
  `push-gate-phase-flag` + `push-gate-vix` + `push-gate-silence-conviction`
  (ki_agent.py, die komplette Gating-Reihenfolge `vix_pause → cooldown →
  silence_filter → conviction_gate → push`). Diese Zonen schützen auch ein
  paar benachbarte Logging-Zeilen mit — akzeptierte Überprotektion,
  dokumentiert statt versteckt.

  **BAU:**
  - `scripts/lint_protected_zones.py` — vergleicht `git diff --unified=0
    <base> -- <datei>` gegen `PROTECTED_ZONES_BASE_REF` (Default
    `origin/main`, im Workflow der PR-Basis-SHA), parst die
    `@@ -oldstart,oldcount@@`-Hunk-Header und prüft Zeilen-Überlappung
    gegen die vier Zonen-Kategorien (AST-Funktionen, AST-Konstanten,
    Sentinel-Marker, Markdown-Überschriften-Anker) — EIN gemeinsamer
    Überlappungs-Mechanismus für alle vier Kategorien.
  - **Ausnahme-Modell (bewusst eine Kombination, nicht nur eine der beiden
    im Auftrag vorgeschlagenen Optionen):** trägt der PR-Titel das Präfix
    `[Wächter]` → **NIEMALS** Ausnahme möglich, auch nicht per Label (Kern-
    Garantie — ein reines Label-Modell wäre schwächer, weil derselbe
    Wächter-Token, der mergen darf, vermutlich auch Labels setzen könnte).
    Sonst (Nicht-Wächter-PR, i. d. R. ein von Easy angestoßener manueller
    PR) → Ausnahme NUR über das Label `protected-ok` (nur von Easy gesetzt,
    GitHub-Repo-Berechtigung regelt das, nicht der Lint selbst) — ein
    reines Titel-Modell allein hätte JEDEN Nicht-Wächter-PR stillschweigend
    befreit, auch versehentliche Score-Eingriffe in eigentlich unrelated
    PRs. Die Kombination schließt beide Lücken.
  - Neuer 8. Step in `.github/workflows/pr-checks.yml` ("Lint protected
    zones"), direkt nach "Lint open-items consistency" — nutzt denselben
    bereits gefetchten PR-Basis-SHA, zusätzlich `PR_TITLE` +
    `PR_LABELS` aus dem `pull_request`-Event-Kontext (keine zusätzliche
    GitHub-API-Berechtigung nötig).

  **Nicht angefasst (harte Grenze eingehalten):** keine Änderung an
  geschützter Logik selbst (nur Kommentar-Marker eingefügt — Golden
  byte-identisch bestätigt); keine neuen Bibliotheken (nur `subprocess`
  für `git`-Aufrufe, stdlib); Freeze-Blöcke byte-identisch.

  22 neue Tests (`scripts/mock_test_lint_protected_zones.py` — 12
  Pure-Funktions-Tests + 10 End-to-End-Szenarien gegen Temp-Git-Repos,
  inkl. aller 5 im Auftrag geforderten Fixture-Belege: score()-Änderung
  rot, Logging-Funktion-Änderung grün, Freeze-Block-Änderung rot,
  config-Schwelle rot, git-add-Zeile im Workflow grün — plus zusätzlich
  verifiziert: Wächter-PR kann NICHT per Label umgehen, Nicht-Wächter-PR
  OHNE Label bleibt trotzdem rot [Default blockierend], Sentinel-Zone-
  Touch wird erkannt), Golden byte-identisch, alle 7 Lints grün
  (`lint_nan_bypass_fields.py`-Baseline erneut nachgeführt — reine
  Zeilenverschiebung durch die neuen Sentinel-Marker-Kommentare, per
  Diff-Hunk-Arithmetik exakt nachgerechnet, keine neuen NaN-Bypass-Funde).

  **Guardian-Finding behoben (noch im selben PR, nicht als Folge-PR
  verschoben):** `_compute_sub_scores` fehlte initial in der Funktionsliste
  — obwohl bereits anderswo im Projekt
  (`scripts/lint_score_confidence_isolation.py`, CLAUDE.md "Score-
  Methodik-Sync-Regel") als kritische Score-Berechnungsfunktion
  eingestuft (SI-Trend-/Short-Pressure-/Borrow-/PC-Ratio-Boni fließen
  dort direkt in den Score ein). Nachgetragen, 20 statt 19 Funktionen.
  `_drivers_breakdown` bewusst NICHT ergänzt (Guardian-Einschätzung:
  Display-/Methodik-Sync-Helfer, keine eigenständige Score-Berechnung).

  **Rückweg:** den neuen Step aus `pr-checks.yml` entfernen (oder
  `scripts/lint_protected_zones.py` so ändern, dass er immer exit 0
  liefert) UND `git revert` des Merge-Commits.

### 23.10.2026 — Veraltete Status-Etiketten (SCORE_STATUS_LABELS) aktualisiert (1 PR)

- **Drei Status-Einträge in `config.SCORE_STATUS_LABELS` auf die aktuellen
  Freeze-Mechanismen umgestellt (Block-1-Pflicht befolgt, Anzeige/Golden —
  Auto-Merge nach grünen Tests):** `#602` (Branch-Commit `48ed95fa`,
  23.10., kein Merge-Hash genannt — Regel a) greift) korrigiert
  veraltete Re-Test-Bedingungen, die durch die
  zwischenzeitlich aufgesetzten Freeze-Auswertungen (Setup-Edge-Re-Test
  10.10.2026, Conviction Test c Erratum 10.10.2026, KI-Score-Edge-Test
  13.10.2026/Erratum 16.10.) überholt waren.

  **SCHRITT 0 — geprüfte Anzeige-Texte (vollständige Liste):**
  | Fundstelle | Bewertung | Aktion |
  |---|---|---|
  | `SCORE_STATUS_LABELS["setup"]` | veraltet (`review_by: 2026-09-30` überfällig, kalendergetrieben obwohl der echte Freeze automatisch bei n≥250 auswertet) | geändert |
  | `SCORE_STATUS_LABELS["conviction"]` | veraltet (Text/`review_cond` nennen „Re-Test 28.07.“/„WIN-Bucket ≥ 20“ — durch Test c im Setup-Edge-Freeze ersetzt) | geändert |
  | `SCORE_STATUS_LABELS["ki"]` | veraltet (`review_cond` nennt „WIN-Bucket ≥ 20 UND zweites Marktregime“ — durch den KI-Score-Edge-Test-Freeze ersetzt) | geändert |
  | `SCORE_STATUS_LABELS["monster"]` | korrekt (falsifiziert, kein Re-Test geplant) | unverändert |
  | `SCORE_STATUS_LABELS["earliness"]` | korrekt (falsifiziert, kein Re-Test geplant) | unverändert |
  | `SCORE_STATUS_LABELS["exit_pressure"]` | **unklar — STOPP, nur gemeldet** (siehe unten) | unverändert |
  | Entry-Shadow „Erhebung läuft“ (generate_report.py, Methodik-Info + Tooltip) | korrekt — zeitlose Beschreibung einer dauerhaft laufenden Schattensammlung, kein Bezug zu einem abgelaufenen Termin | unverändert |
  | Conviction-Action-Text „Aggregations-Anzeige, nicht validiert.“ (`compute_conviction_score`) | korrekt — bleibt zutreffend, zusätzlich: liegt in einer `lint_protected_zones.py`-geschützten Funktion, wäre ohnehin nicht ohne Label änderbar | unverändert |
  | `app.html` | enthält dieselben Texte (Build-Artefakt), wird vom nächsten echten Daily-Run automatisch aus dem neuen `config.py`-Stand neu geschrieben — nicht hand-editiert | n/a |

  **exit_pressure — STOPP, nur gemeldet:** der Auftrag vermutete einen Bezug
  zu „§4-Re-Test n=215/250“ — dieser Wert wurde **nirgends** belegt
  (einziger gefundener n-Stand in `SESSION_HANDOVER.md`: Setup-Edge/
  Conviction UND KI-Score beide `n=0/250`, Stand 22.10.2026, PR #598-
  Block-1-Eintrag). `exit_pressure` hat laut eigenem Kommentar im Dict
  **keinen** Validierungs-Pfad (Closed-Trades-Schema offen) — anders als
  setup/conviction/ki gibt es **keinen** automatischen n≥250-Auslöser, auf
  den `review_by` umgestellt werden könnte. `review_by: 2026-09-30` bleibt
  deshalb unverändert überfällig — der Status-Drift-Wecker feuert
  weiterhin wöchentlich dafür (korrektes Verhalten: ein echtes, ungelöstes
  Review darf nicht stillschweigend verschwinden).

  **Bewusste Abweichung von der wörtlichen Vorschlags-Formulierung:**
  `status_date` wurde **nicht** auf heute gesetzt (obwohl die
  Pflege-Pflicht-Kommentar-Referenz im Auftrag das suggerierte) —
  `config.py`s eigene Feld-Doku sagt explizit „Datum des REGISTRIERTEN
  Befunds … NICHT der Render-Zeitstempel“, und der zitierte Pflege-Pflicht-
  Satz bezieht sich wörtlich auf „ein Status-Wechsel **nach einem
  Re-Test**“ — heute hat kein Re-Test stattgefunden (n weiterhin 0/250),
  nur die Prosa wurde korrigiert. `status_date` bleibt daher die
  ursprünglichen Befund-Daten (30.06./28.07./15.07.2026).

  **Badge-Länge (Widerspruch gemeldet statt umgangen):** die im Auftrag
  vorgeschlagenen Texte („… (n=250)“) wären für Setup/KI deutlich länger
  als heute (heute je ein Wort: „unvalidiert“/„heuristisch“, 11 Zeichen).
  CSS erlaubt Zeilenumbruch (`white-space:normal`, Conviction trug schon
  53 Zeichen), die Vorgabe „nicht länger als heute“ ließ sich für diese
  zwei Badges aber nicht einhalten, ohne die neue Information komplett
  wegzulassen. Kompromiss: kurze Badges „unvalidiert · Test läuft“ /
  „heuristisch · Test läuft“ (25 statt 11 Zeichen, Kernwort unverändert —
  Farbe/`status_kind` bleiben korrekt) statt der vollen „(n=250)“-Vorschlags-
  Formulierung; das „n ≥ 250“-Detail lebt stattdessen in `review_cond`
  (Methodik-Panel, nicht auf der Karte). Conviction wurde dabei sogar
  **kürzer** (22 statt 53 Zeichen).

  **Golden-Diff (Beleg, 3 Zeilen geändert):** ausschließlich die drei
  `cockpit-status-badge`-Spans + die `_conf_class`-Tooltip/aria-label-Texte
  für Setup/KI/Conviction — Datum-Teile (`Befund 2026-06-30` etc.)
  byte-identisch erhalten, kein anderer Teil der Seite berührt.

  **Mini-Stopp geprüft:** `SCORE_STATUS_LABELS`/`SCORE_STATUS_KINDS` stehen
  bereits in `lint_protected_zones.py`s `_CONST_EXCLUDE` (reine
  Anzeigetexte, kein Score-Effekt) — der Lint lässt diesen PR ohne Label
  durch, kein Umgehen nötig.

  **Nicht angefasst (harte Grenze eingehalten):** `score()`,
  `ki_signal_score`, `apply_agent_boost`, Top-10, Filter, Push,
  `compute_conviction_score`/`apply_conviction_scores` — alle unverändert
  (per `lint_score_confidence_isolation.py` + `lint_protected_zones.py`
  bestätigt). Freeze-Blöcke byte-identisch. Keine `return_*`-Werte.

  1 neuer Test (`scripts/mock_test_status_review_reminder.py`, Beleg gegen
  die REALE config: setup/conviction/ki feuern beim Status-Drift-Wecker
  nicht mehr, exit_pressure weiterhin — wie gefordert), 1 Testdatei-Anpassung
  (`scripts/mock_test_score_confidence.py`, Literal-String nachgezogen),
  Golden neu erzeugt, alle 7 Lints + 162 Allowlist-Tests grün.

  **Rückweg:** `git revert` des Merge-Commits.

### 23.10.2026 — [Wächter] Digest: bekannt tote Quellen als ℹ️ statt ⚠️ (1 PR)

- **Digest kennzeichnet reddit_mentions / openinsider / fda_calendar als
  „ℹ️ bekannt tot (siehe open_items)" (Easy-Entscheid 23.10.2026, Klasse A,
  Wächter-Self-Merge bei grünen Gates):** `#603` (Branch
  `claude/waechter-bekannt-tote-quellen-k7q2`, kein Merge-Hash genannt —
  Regel a) greift). Befund: der Digest meldete die drei seit mind.
  27.07.2026 toten, bewusst nicht reparierten Quellen täglich mit je zwei
  ⚠️-Zeilen und zählte sie als „3 von 7 Quellen unter Baseline" — echter
  Dauerzustand, aber reiner Lärm. Änderung (nur Digest-Body, keine Push-
  Klasse berührt): `health_check.COVERAGE_KNOWN_DEAD_QUELLEN` (Mapping
  Quelle → open_item), `known_dead_coverage_quellen` /
  `coverage_known_dead_line` / `coverage_recovered_line`,
  `coverage_overview_line(exclude=…)` (tote Quellen weder in N noch M,
  Zusatz „· K bekannt tot (ausgenommen)"), Verdrahtung in
  `scripts/health_check_digest.py`. Neues open_item
  `bekannt-tote-quellen-digest` (beobachtet) — die Kennzeichnung gilt NUR,
  solange es offen/beobachtet ist; erledigt/fehlend/unlesbar → wieder
  normale ⚠️ (fail-safe). Liefert eine Quelle im 24h-Fenster wieder Daten →
  normale Zeilen + „🆕 <quelle> liefert wieder Daten". Kein Score-/Filter-/
  Push-/Exit-/Freeze-Bezug. 1 neuer Testfall in
  `scripts/mock_test_coverage_watchdog.py`. **Rückweg:** `git revert` des
  Merge-Commits.

*(Zwei-PR-Kette aus einer read-only Diagnose 15.08.2026: das Backtesting-Panel
meldete einen Browser-`JSON.parse`-Fehler. Diagnose fand nackte JSON-`NaN`-
Token in `backtest_history.json`, Ursache `_extract_hist_5d`
[`row.get("Volume", 0) or 0`-Falle, NaN ist truthy → keine Ersetzung],
Ursprungs-Bug seit `19ff84a3`/14.05.2026. Erst der Schreibpfad, dann — nach
explizitem Easy-Entscheid — die vier bereits betroffenen Bestands-Records.)*

- **PR #532 — merged `7d916bfd` — fix:** **Wurzel-Fix im Schreibpfad, NUR
  zukünftige Records.** `_extract_hist_5d` (generate_report.py) nutzt jetzt
  `_finite()` pro Zelle; NaN/Inf in irgendeiner der 4 OHLCV-Zellen verwirft
  den GESAMTEN Trading-Tag (nicht nur die Zelle — Trend-Berechnungen
  brauchen eine lückenlose 5-Tage-Kette). `_compute_rvol_buildup_5d` /
  `_compute_vol_stability_5d` / `_compute_coiled_spring_score`
  (backtest_history.py) auf `_finite()`-Guards umgestellt statt reinem
  `<= 0`/`is None` — letzterer war der wichtigste Fix: `is None` lässt NaN
  durch, wodurch `coiled_spring_score` sich vorher zu einem STILLEN
  Fake-`0.0` auflöste statt zum dokumentierten `None`. `_save_backtest_
  history` jetzt atomar (tmp + os.replace). Neue
  `_sanitize_backtest_entries_for_write` als zweites, LAUTES Netz (NaN/Inf
  → null + Pflicht-Log Ticker/Datum/Feldpfad, deckt seit dem Guardian-
  Nachtrag `b41d94c8` auch Tupel ab). Guardian ✅ (2 Läufe, 1× Infra-
  Timeout + Retry; 3 Findings, 1 behoben [Tupel], 2 dokumentiert/begründet
  zurückgewiesen). 134 CI-Tests grün, Golden byte-identisch. **Sibling-Bugs
  gemeldet, NICHT gefixt:** FINRA-`short_interest`-`or 0`-Muster
  (`_compute_si_slope_5d`/`_compute_si_velocity_pub`), mehrere Entry-/
  Matured-Export-Felder mit demselben `or 0`-Muster, ein `<= 0`-Slip in der
  Squeeze-Detection-Historienscan-Funktion. **Datenpfad-Touch → manueller
  Merge.**
- **`3be1bb77` — fix(data):** **Bestandsrecord-Reparatur — 4 Records, 12
  Zeilen.** Easy-Entscheid 15.08.: `rvol_buildup_5d` + `vol_stability_5d`
  (nackte NaN-Token) UND `coiled_spring_score` (stiller Fake-`0.0` aus dem
  NaN-Eingang) bei genau **ARCT, COLL, GO, IBTA (13.08.2026)** auf `null`
  gesetzt. Begründung: Artefakte des obigen Bugs, keine Messungen — `null`
  macht aus „kaputt" ein ehrliches „fehlt". **Vollständigkeitsprüfung**
  (vor der Korrektur, alle 695 v4-Records): exakt diese 4 Records tragen
  die stille `coiled_spring_score==0.0`-bei-NaN/None-Eingang-Signatur —
  keine weiteren Instanzen gefunden. 409 Records mit `coiled_spring_
  score==0.0` aus LEGITIMEN finiten Eingängen (hohe Volatilität / negativer
  SI-Slope) sind unverändert korrekt geblieben. **§4-Check:** keiner der 4
  Records (ticker, date=13.08.2026) ist in `matured_backtest_export.jsonl`
  vorhanden (0 Treffer) — Reife-Schranke >14 Kalendertage bei 2 Tagen Alter
  noch nicht erreicht, kein Konflikt mit dem append-only §4-Freeze (§4-
  Freeze-Block selbst unangetastet). Record-Count (1707) und Zeilenzahl
  (67083) vor/nach identisch, strikter JSON-Parse (NaN-ablehnend, wie der
  Browser) erfolgreich, Golden byte-identisch. **Bestandsänderung an
  potenziell §4-relevanten Daten → manueller Merge, KEIN Self-Merge.**

---

### Woche 03.–08.08.2026 — Matured-Export · §4-Vorabregistrierung · Guardian-Pflicht · Anzeige-Ehrlichkeit

- **`40565b4` — #500 — docs:** Prune-Konsequenz für die Sept-Re-Tests + Drei-Zonen-
  Schrumpf (Momentaufnahme 03.08.).
- **`a01acb2` — #501 + `6bdf517` — #503 — feat:** **Matured-Export** `matured_backtest_export.jsonl`
  (append-only, **prune-immun**, Analyse-only, KEIN Frontend-Konsument). #501 baut
  Export + Provenance (`backfill`/`forward`); #503 verschärft das Reife-Gate auf
  `return_10d` gefüllt **UND** `days_old > 14` Kalendertage (Rolling-Felder
  `max_gain_pct`/`max_drawdown_pct` erst ab Kalendertag 15 final). Aufruf im
  postclose-Pfad, fail-soft, Flag `MATURED_EXPORT_ENABLED`.
- **`b19c3f2` — #502 + `3e96391` — #504 — docs:** **Guardian-Pflichtregel** (`CLAUDE.md`):
  `squeeze-guardian`-**Lauf** vor JEDER Ready-Meldung / JEDEM Self-Merge, ungefragt,
  ohne Ausnahme (auch Doku); **Urteil bleibt advisory/kein Gatekeeper**. #504 gleicht
  die drei Alt-Stellen an (eine Wahrheit).
- **`a4fcbcd` — #505 + `bdf84f2` — #506 — docs:** **§4-Vorabregistrierung EINGEFROREN
  05.08.** (Exit-B.1, Def A: `provenance=forward` ∧ `score≥70`, Quelle Matured-Export;
  Setup-Edge herausgenommen; Änderungs-Protokoll-Regel). #506 disambiguiert „forward"
  (Paper-C datums-basiert vs. §4 provenance-basiert). **§4-Block ist ab hier
  änderungs-protokoll-geschützt.**
- **`fdf885f` — #507 — fix:** **Earnings-Sofort-Push umbenannt** „Squeeze Alert" →
  **„Earnings-Alert"** (`ki_agent.py:send_ntfy_alert`, einzige Aufrufstelle =
  Earnings-Pfad; alter Titel war Refactor-Rest). Raketen-Emoji raus, Score-Zahlen
  raus (hatten nie eine Push-Schwelle), Tag `calendar`, Body „anstehendes Earnings-
  Ereignis, kein Squeeze-Signal". Trigger unverändert.
- **`e9a4245` — #508 — fix(display):** **Backtesting-Panel** — Datenpunkt-Zahl als
  **90-Tage-Rollfenster** ehrlich gemacht (graue Zeile „kann sinken, ohne Datenverlust;
  gereifte Records dauerhaft prune-immun gesichert").
- **`d6c51b0` — #509 — feat(health-check):** **§4-Re-Test-Zähler** im täglichen
  Digest-Push (`📊 Re-Test-Zähler (§4): n = X/250 · Export N Zeilen`), fail-soft,
  backend-only. Export-Zeilenzahl macht stillen Export-Ausfall täglich sichtbar.
- **`bcf350d` #510 → `2ad9d9e` #511 → `5c67fca` #512 — inst_ownership-Key-Fix:**
  Wegwerf-Probe (#510) belegte: die verdrahteten `.info`-Keys
  (`institutionHeldPercentOutstanding`/`institutionsPercentHeld`) existieren NICHT
  (`<KEY-FEHLT>` 33/33); Standard-Key **`heldPercentInstitutions`** trägt (Coverage
  30/30, Streuung voll, >100 % bei stark geshorteten Titeln real). #511 Probe-Cleanup,
  #512 **Key-Fix** (beide Lese-Stellen + JS-Drawer-Skala ×100 + null-Guard). Karten-
  Zeile „Institutioneller Anteil" war seit jeher stumm, zeigt jetzt echte Werte.
  **KEIN Score-Touch, KEIN Sammelfeld** (offen, §6g).

### 17.07.2026 — entry_past_return_5d Stufe-B-Backfill (Paper C) DURCH + Gate-Kalibrierung

### `5d8e78d` — 17.07. — LIVE-LAUF DURCH
**★★ entry_past_return_5d Stufe-B-Backfill LIVE — 465/470 Records gefüllt.** Der
`mode=live`-Dispatch von `backfill_entry_past_return_5d.yml` lief sauber durch.
**Gate PASS** (aus dem Live-Log): **42 verifiziert · 41 exakt bei 0.000 · median
= 0.0 · mean-Inlier = 0.0 · 1 Einzel-Artefakt AMCX 0.05** (Yahoo-Bar-Revision auf
frischem Referenz-Bar, kein systematischer Fehler). **Ergebnis:** **465/470**
v4-Alt-Records mit `entry_past_return_5d` gefüllt, **5 skipped** (delisted / IPO
< 6 Bars, davon **4 few-bars**), **Alignment 0** Entry-Tage ohne Bar, `flock` ok,
Atomic Write ok. Der Commit `5d8e78d` trägt **zwei** Dateien: `backtest_history.
json` (465 None → Werte) + **`backfill_entry_past_return_5d_manifest.json` mit 465
(ticker,date)-Einträgen** (Provenienz für den chirurgischen `--undo`). git-belegt:
`git show --stat 5d8e78d` = 465 Deletions in backtest_history + 1862 Insertions
Manifest; Manifest-Länge = 465. **Rückweg falls nötig:** Workflow `mode=undo`
(Manifest-basiert, nullt **nur** die 465 — die vorwärts gesammelten OoS-Records
bleiben unberührt).

### PR #444 — 16.07. — Merge `610349c`
**★ Konsistenz-Gate begründet kalibriert (Verteilungs-Urteil statt starrem
±0.01/Record).** Der frühere Gate-Check verwarf jeden Record mit `|recompute −
stored| > 0.01` — der 16.07.-Dry-Run zeigte aber `n=32 · exakt=31 · 1 Ausreißer
(AMCX 5.11→5.16) · median 0.0` = **Daten-Artefakt** (Yahoo revidiert frische
Referenz-Bars), kein Rechenfehler. Kalibriert auf ein **Verteilungs-Urteil** mit
5 Wächtern (PASS ⇔ alle): ≥ 20 verifiziert · **median-|diff| < 0.001** (Mehrheits-
Drift > 50 %) · **mean-|diff| der Inlier < 0.003** (Minderheits-Drift < 50 %) · ≤ 1
Ausreißer > 0.01 · **kein** Ausreißer ≥ 0.5 pp (hard cap). **Guardian-Runde 2**
fand den **median-Blindfleck** (fängt nur > 50 %-Verschiebungen) → **mean-of-Inlier-
Wächter `GATE_MEAN_MAX=0.003`** ergänzt (der eine erlaubte Ausreißer ist kein
Inlier → verzerrt den mean nicht). **Guardian-Runde 3** fand einen Docstring-
Overclaim („winzig … deutlich < 0.003") → präzisiert + **Boundary-Test I10**
(9×0.0099 mean-Inlier ≈0.00278 PASS ↔ 10×0.0099 ≈0.00309 FAIL) verankert die
Schwelle. Nur Gate-Schwelle + Doku + Tests — **kein** Compute-/Write-/Undo-Pfad-
Drift. CI 104 grün, Guardian ✅. **Gate-Schwellen-Logik → manueller Merge.**

### PR #443 — 16.07. — Merge `344e23d`
**★ Gate-Diff-Verteilung im dry-run-fetch loggen (Diagnose).** Rein Logging, keine
Gate-/Toleranz-/Write-Pfad-Berührung. `gate_diff_distribution` + `summarize_diffs`
loggen die **volle** Diff-Verteilung aller Referenz-Records (pro Record ticker/
date/stored/recomputed/|diff| **plus beide Bar-Details** Zähler `iloc[-1]` + Nenner
`iloc[-6]` je Datum+Adj-Close → Revisions-Hypothese am konkreten Bar prüfbar).
Diese Messung trennte belegbar **Daten-Artefakt** (31 exakt bei 0.000 / 1 Ausreißer /
median 0) von **systematischem Fehler** — die empirische Grundlage für die #444-
Kalibrierung. **Diagnose-Erweiterung → manueller Merge.**

### PR #442 — 16.07. — Merge `cd6947a`
**★★ entry_past_return_5d Stufe-B-Backfill-Skript + Workflow (Stufe 1, kein Live-
Lauf).** `scripts/backfill_entry_past_return_5d.py` (Load → Filter v4-only/is-None →
**Konsistenz-Gate** → Bulk-Fetch → Compute `_compute_entry_past_return_5d` importiert
→ Atomic Write) + `backfill_entry_past_return_5d.yml` (`workflow_dispatch`-only,
Modi **dry-run-fetch / live / undo**). **Doppelter Race-Schutz** (`fcntl.flock` +
Cron-Fenster-Guard ±30 min um 06:17/21:17). **Gate als HARTE Live-Vorbedingung**
(bei FAIL exit 1, KEIN Write). **KRITISCHER Guardian-Fund im `--undo`-Pfad (als
Lesson §8z6):** der erste Entwurf identifizierte die zurückzusetzenden Records per
**Recompute-Match** — aber die **vorwärts gesammelten OoS-Records matchen dieselbe
Formel/Preisquelle** → `--undo` hätte die **konfirmatorische Evidenz zerstört**.
**Fix:** ein **Manifest** (`backfill_entry_past_return_5d_manifest.json`) protokolliert
die tatsächlich gefüllten `(ticker,date)`; `--undo` nullt **nur** diese (reine
Dict-Op, kein Recompute), verweigert ohne Manifest (kein Raten). **Mutationstest L4
belegt:** ein vorwärts gesammelter Record mit identischem Wert **überlebt** `--undo`.
CI grün, Guardian ✅ (2 Läufe). **Neues Skript + Workflow → manueller Merge.**

### 16.07.2026 — ki_signal-Re-Test-Confound-Flag

### PR #440 — 16.07. — Merge `53b72d1` (feat `e90fd5f`)
**★ `ki_sentiment_source`-Flag (LLM vs. Keyword-Fallback).** Additives Backtest-
Feld ∈ {`"llm"`,`"keyword"`,`"none"`} (None auf Alt-Records, **forward-only**,
rückwirkend nicht rekonstruierbar). Markiert pro Record, ob der ki_signal-News-
Anteil vom Claude-Haiku-Call oder vom Keyword-Fallback stammt — schließt genau
den Confound-Anker #2, der beim ki_signal-Re-Test 15.07. **nicht bestimmbar** war
(kein Per-Record-Flag existierte). Klassifikation in `ki_agent.compute_signal` am
`claude_sentiment_score`-Call (`"llm"`=Score gesetzt · `"keyword"`=None+Headlines
da · `"none"`=keine Headlines) → `meta` → signal-Dict (`agent_signals.json`) →
`apply_agent_boost` setzt `s[...]` → `_build_backtest_extension` → **`entry.update`
(die #411-Durchreichung)**. S10_OBSERVED (kein MUSS/LAG), Schema **v4** (additiv).
**Look-Ahead-frei** (reine Persistenz, kein Score-Read — Test F verriegelt). Test
`mock_test_ki_sentiment_source` (26 Checks): 3 Zustände + **#411-Merge-Assertion**
(alle 3 kommen im Record an, ausgeführt) + Alt-Record-None-Toleranz. CI 103/103,
Golden unverändert. Guardian ✅. **Schema/Append-Pfad → manueller Merge.**

### 15.07.2026 — PWA-Cache-Strukturfix Phase 1 (Flip) + si_velocity-Rename

### PR #436 — 15.07. — Merge `4270cce` (feat `77b42d6`)
**★★ Bootstrap-Shell PHASE 1 (Flip) — `index.html` wird zur Weiche.** Der
strukturelle iOS-PWA-Launcher-Cache-Fix ist scharf: `index.html` = **winzige
754-B-Shell** (Apple-Meta ×3 [`capable`/`status-bar-style`/`title`],
`location.replace('app.html?v=' + Date.now())`, `<noscript>`-Refresh + sichtbarer
Fallback-`<a href="app.html">`); `app.html` = voller Content (**787 KB**). Beide
Write-Sites app.html-**first** (Deploy-Race-Mitigation), Error-Page schreibt
**nur** `app.html` + Shell (begründet: eine Fehlerseite braucht keinen zweiten
Content-Write). **Ziel-Mechanik-Test T7** (`mock_test_bootstrap_shell_phase1`,
Test E): gecachte Shell → bei JEDEM Launch via `Date.now()` eine **frische
`?v=`-URL** für `app.html` → Launcher-Cache trifft nur die Weiche, nie den Inhalt.
**Rollback = Ein-Zeilen-Revert** (Shell-Konstante zurück auf vollen Write; Parser
lesen seit Phase 0 `app.html` mit index-Fallback → unschädlich). **Guardian ✅**
(Parser-Fan-out vollständig, S9 sicher). **Deploy-Pfad + Golden → manueller
Merge.**

### PR #437 — 15.07. — Merge `5788485` (refactor `a8c5c7f`)
**★ Rename `finra_data.si_velocity` → `si_shares_per_day` + Label.** Irreführender
Name (misst absolute Shares/Tag des täglichen Short-VOLUMENS, keine
Änderungsraten-„Velocity", Nomenklatur-Falle §8m). Label „SI Velocity (tägl. Ø)"
→ **„SI-Volumen Δ (tägl. Ø)"**. 5 Reads + Write + Payload (`app_data.json`) + v1/v2-
Display-Row + `card.jinja`-ctx-Key + Frontend-JS konsistent umbenannt; 3 Test-
Fixtures + Golden (2 Zeilen, rename-only). **`si_velocity_pub` unangetastet** —
strikte `_pub`-Guard-Muster, keine Regex-Überlappung. **Korrektur der alten
§6a-Angabe:** waren **5 Reads (nicht 7)**, **KEIN KI-Boost-Konsument** (einziger
Nicht-Display-Read = dormanter V1-Rollback). v1==v2 byte-identisch verifiziert.
Guardian ✅. **Golden + persistiertes Feld → manueller Merge.**

### PR #438 — 15.07. — squash `ae45803`
**★ Einheiten-Fix Frontend (Folge #437).** Der Watchlist-Drawer-JS zeigte
`si_shares_per_day` als **Prozent** (`fmt(v,2)+'%'` → `259.00%`) mit Alt-Label
**„SI-Velocity"** — beides falsch (Feld = Shares/Tag; „Velocity" = der von #437
entfernte Begriff). Angeglichen an die kanonische Python-Row: Vorzeichen +
0 Dezimalstellen + deutsche `.`-Tausender (`toLocaleString('de-DE')`) +
„Aktien/Tag" + optional „⚡ Beschleunigung"; `0`/`null` → „—". Label → **„SI-Volumen
Δ (tägl. Ø)"**. **JS==Python byte-identisch über 14 Fälle** (Node vs. Python
gegenübergestellt: Vorzeichen, `.`-Tausender ≥1000, Beschleunigung, 0→„—",
Negative). Golden 2 Zeilen (Wert + Label). **Frontend-Tweak (Display-Format +
Label) → Auto-Merge** (kein Datenpfad/Score/Schema).

### 14.07.2026 (Nachmittag) — KI-Anzeige-Fixes + PWA-Cache-Strukturfix Phase 0

### PR #432 — 14.07. — Merge `67dd86e` (feat `98748ff`)
**★ KI-Pillar-Zahl live nachziehen (`renderAgentSignals`).** Frontend-Fix zur
Diagnose 14.07.: der frische ki-Score liegt im Client vor (`app_data.agent_
signals`, deckt alle 10 Top-10 ab) und wird schon für Dot/`dataset.kiScore`
genutzt — aber die server-gerenderte **KI-Pillar-Zahl** blieb bei „—" (Neu-
Einsteiger nach Top-10-Rotation: Daily-Run rendert VOR dem Tick) oder stale.
`renderAgentSignals` patcht jetzt in der bestehenden Karten-Schleife **Zahl +
Farbe + Balken** aus `signals[ticker].score` (Farb-Schwellen identisch zu
server `_tri_score_color`: ≥60 grün / ≥30 orange / <30 rot). **Live-Effekt (reale
Daten):** 6 Karten füllten sich (GRPN/INDI/FXHO/NTLA/FDMT/VSTM), 2 stale-
Korrekturen (FRMM 43→28, WOLF 18→10). **Konfidenz-Wasserzeichen (#425/#426)
UNBERÜHRT** — nur `textContent`+`style`, **kein** `classList`-Touch (Test B6).
Neuer `mock_test_ki_pillar_live_patch` (node: Zahl/Farbe/Balken/Stale/Graceful-
Empty/Wasserzeichen). Golden mit-aktualisiert. **Frontend + Golden → manueller
Merge (Easy-Freigabe).**

### PR #433 — 14.07. — `3167981` (squash)
**★ Recalculate-Reload cache-bustend (#373-Inkonsistenz behoben).** Der
Recalculate-Abschluss-Reload (Countdown-Auto + `_manualReload`) nutzte plain
`window.location.reload()` → respektiert den GitHub-Pages `max-age=600`. Beide
Stellen auf das **bestehende** `?v=`-Muster von `reloadPage` angeglichen
(`window.location.replace(location.pathname + '?v=' + Date.now())`). Kein neues
Muster (bewusst nicht `reloadPage()` aufgerufen — btn-Side-Effect vermieden).
`mock_test_service_worker_removed` um 4 Assertions erweitert (bustendes Muster +
kein plain reload() mehr). Golden mit-aktualisiert. **Frontend-Tweak (proven
Pattern) → Auto-Merge.** *(Wichtig: behebt nur den In-App-Reload — das PWA-
Launcher-Cache-Problem bleibt, s. #434/§4.)*

### PR #434 — 14.07. — Merge `268d955` (feat `8ed7505` + test `0f38c7f` + chore `263d656`)
**★★ Bootstrap-Shell PHASE 0 — `app.html` Content-Pfad + Parser-Repoint (KEIN
Flip).** Vorbereitung des strukturellen iOS-PWA-Launcher-Cache-Fixes.
**`index.html` bleibt die volle Seite** (Golden **byte-identisch** → kein
Content-/Score-/Pipeline-Touch bewiesen); `app.html` wird zusätzlich byte-
identisch geschrieben, und **alle Content-Parser** lesen jetzt `app.html` mit
**Fallback `index.html`** (Zero-Downtime für die erste Zyklus-Runde):
- `config.APP_HTML = Path("app.html")` (INDEX_HTML bleibt = Seite).
- `ki_agent.parse_top_tickers` (**die Top-10-Quelle**), `alert.parse_index_html`
  (eigenes `APP_HTML`), **S9** `html_path="app.html"` + crit-Re-Read,
  `smoke_render.js` — alle → `_src = app.html|index.html`.
- Doppel-Write (Content + Error-Page) nach beide Dateien; Workflow `git add
  app.html`; Jekyll-Test um `app.html` erweitert.
- **S9-Sicherheit:** einziger `sys.exit`-Pfad — fail-soft, fehlende `app.html`
  → **WARN, nie crit** (`health_check.py:917`); `app.html` wird **vor** S9
  geschrieben.
**Guardian ✅** (Konsumenten vollständig repointed, kein übersehener Parser, S9
sicher; zwei kosmetische Log-Strings `_src.name` nachgezogen — `263d656`).
`0f38c7f`: Test CI-minimal-safe gemacht (§8n — ki_agent zieht pandas, nicht im
CI-Install → D/E Source-Grep hart + Live-Lauf best-effort). Neuer
`mock_test_bootstrap_shell_phase0` (18 Checks). **Deploy-Pfad + Health-Check +
Parser → manueller Merge (Easy-Freigabe).** **Phase 1 (Flip) erst nach Zyklus-
Verify (§3/§4).**

---

### 14.07.2026 (Vormittag) — Absicherung + Panel-Vollzug

### PR #429 — 14.07. — `3ed4cfd` (squash)
**★ Station-1-Regressions-Netz `entry_past_return_5d` (KEIN Bug-Fix).** Reines
Absicherungs-Netz (Test I in `mock_test_entry_past_return_5d.py`) — **ehrlich
als „grün bei korrektem Code" deklariert, KEIN Mutations-Beweis eines Bugs.**
Live-Call (echter Aufruf, kein Source-Grep): `get_yfinance_data` +
`get_yfinance_batch` (treibt das **nested** `_hist_stats`, Closure → nicht
isoliert aufrufbar) mit Fixture-Bar-History → `close_5td_before_entry ==
iloc[-6]` (non-null); Edge `< 6 Bars` → sauber `None`. **pandas-gated** (CI-
Minimal = `stdlib+jinja2+pyyaml`; ohne pandas sauberer Skip, analog H-
ImportError-Skip). **Non-vacuous verifiziert** (interne Diligence): lokale
Mutation `iloc[-6]→iloc[-1]` färbt I1/I2 rot, danach `git checkout` revertiert.
Bestehende #411-Merge-Assertion (G1–G3) unangetastet, **kein** Logik-Touch an
`generate_report.py`. **Test-only → Auto-Merge.** *(Kontext: der historische
#411-Bug lag im `c.update`-Merge, nicht in Station 1 — Station war nie kaputt;
das Netz verriegelt sie gegen künftige Regression.)*

### PR #430 — 14.07. — Merge `57c6b10` (feat `930633d`)
**★ Status-Panel 6. Eintrag `si_position_history`.** Sechster Sammel-Status-
Eintrag im `#bt-section`-Panel (#412), **gegen die REALE `si_position_history.
json` gebaut** (28 Ticker / 56 Punkte, je 2 — Struktur bestätigt, nicht
angenommen). Gerenderter Eintrag: `Short-Interest-Position (si_position_history)
· n=28 (28 Ticker) · sammelt · unvalidiert · auswertbar ab ~Q4 2026 (mehrere
Settlement-Zyklen)`. Eigenschaften:
- **Separate Datei → eigener clientseitiger Fetch** (`_btSiCollectStatus`), mit
  Fehler-Toleranz. **Graceful-Empty:** fehlende/leere/kaputte Datei → `n=0`,
  kein JS-Error (Guard bleibt, auch wenn die Datei existiert).
- **Zähl-Logik dynamisch:** primär Ticker mit ≥2 Serienpunkten (auswertbares
  1-Monats-Delta), Gesamt-Ticker als Kontext. Pure `_btSiCount` (node-testbar).
- **Weg-A:** Label/Status/Dateiname zentral in `config.SI_POSITION_STATUS_ROW`,
  server-injiziert → **kein** Frontend-Literal, Look-Ahead-Guards bleiben grün.
- **Rein anzeigend:** keine Serien-Werte (kein `shares_short`, kein Delta).
Golden mit-aktualisiert (nur der neue Eintrag, 47 Insertions, keine
Kontamination der 5). Tests: `mock_test_collect_status_panel` um D (Source-
Wiring) + E (node: Zähl-Logik/Graceful-Empty/KEINE Werte). **Frontend + Golden +
Auffanglinie-Wortwahl → manueller Merge (Easy-Freigabe erteilt).**

---

### 13.07.2026 — SI-Quellen-Durchbruch + Monster-Neutralisierung

*(Roter Faden 13.07.2026: eine **SI-Quellen-Suche als Probe-vor-Bau-Kette** →
Durchbruch → Bau → Doku, dann ein **Monster-Score-Neutralisierungs-Doppel**.
Ablauf: #419 korrigiert die Schritt-B-Einordnung (B teilt A's Datenblocker) →
#420/#421/#422 sind read-only Probe-Workflows (FINRA/Nasdaq/Finnhub, dann
yfinance-`.info`) mit dem **Wendepunkt #422**: `dateShortInterest` ist gratis
4/4 befüllt → #423 baut die `si_position_history.json`-Forward-Sammlung
(entblockt Paper A **und** B daten-seitig) → #424 sichert die Entblockung in
der Doku → #425/#426 neutralisieren den unvalidierten `monster_score`
vollständig (Anzeige neutral-grau, Push raus, Signal-Zähler monster-frei über
`ki_signal_score≥70`). Vortage 11.–12.07.: Auffanglinien-Frontend (#412
Status-Panel, #414 Empfehlungsblock raus) + Lit-Reminder #413 + Paper-Plan
#415/#416/#417 + Handover-Refresh #418. Davor 03.–10.07.: `max_gain_pct`-
Backfill-Kette → Hypothese-C-Null → Kombi-Sammel-Felder → yfinance-Cap →
pub_date-Kette #407/#408/#409.)*

### PR #419 — 13.07. — `ac2b2a0` (squash)
**Doku:** Schritt-B-Einordnung korrigiert. Die frühere Framing „Schritt B geht
**ohne** A" war falsch: B (SI-Zuwachs in Paper-Buckets) braucht dieselbe
ausstehende SI-**Positions**-Zeitreihe wie A. `si_velocity_pub` misst die
3-Tage-Änderung des Tages-Short-**VOLUMENS** (Fluss), das Paper aber den
1-Monats-Zuwachs der ausstehenden **POSITION** (Bestand) → doppelter Mismatch
(Größe + Fenster). §4/§6i entsprechend geschärft. Reine Doku, **Auto-Merge**.

### PR #420 — 13.07. — Merge `ca807d6` (`dfeb54d` + `e416eaf`)
**★ Read-only SI-Quellen-Probe-Workflow** (`workflow_dispatch`, schreibt
nichts). `dfeb54d`: FINRA-Short-Interest-Probe; `e416eaf`: um **Nasdaq** +
**Finnhub** erweitert (3 Quellen, ein Lauf). Zweck: klären, ob die ausstehende
SI-Position gratis settlement-datiert erreichbar ist. Befund: FINRA-API anonym
erreichbar, aber **OTC-only**; Nasdaq nur Nasdaq-gelistete (NYSE `null`, volle
Historie Paid); Finnhub Short-Interest nur Premium. **Neuer Workflow →
manueller Merge.**

### PR #421 — 13.07. — Merge `121b98e` (`5519a69`)
**★ Probe-Nachtrag TEST 1–4** — FINRA `marketCategoryCode`-Verteilung. K.o.-
Klärung: die FINRA `EquityShortInterest`-API liefert trotz des Namens
ausschließlich **OTC**-Ticker; gelistete Namen (NASDAQ/NYSE) fehlen → für
unsere Namen wertlos. Read-only, kein Repo-Write. **Manueller Merge.**

### PR #422 — 13.07. — Merge `fedf7fd` (`49ef407`)
**★★ DER WENDEPUNKT — yfinance `.info` SI-Probe (read-only).** Frage: ist
`dateShortInterest` befüllt? Antwort **4/4 Ticker befüllt** — `sharesShort`,
`sharesShortPriorMonth`, `dateShortInterest`, `sharesShortPreviousMonthDate`,
echte Settlement-Daten (30.06. + 29.05.), plausible Positions-Größen
(`sharesShort` ≪ `floatShares` → **Bestand**, nicht Volumen → umgeht die
Namens-Falle §8m). Alle vier Felder liegen im **selben `.info`-Dict**, das der
Batch-Lauf ohnehin holt → **kein Extra-Call**. Dieser Befund kippt den
A+B-Datenblocker. Read-only. **Manueller Merge.**

### PR #423 — 13.07. — Merge `5fc8a63` (feat `faf8c8d` + test `c55a883` + fix `c3f2ac8`)
**★★ SI-Positions-Zeitreihe `si_position_history.json` — ENTBLOCKT Paper A+B
(daten-seitig).** Forward-only Sammlung der ausstehenden SI-**Position** aus der
gratis yfinance-`.info`-Quelle (#422-Befund). Schema `{ticker:[{settlement_
date, shares_short, short_pct_float, pub_date, seeded?}]}`. Eigenschaften:
- **4 `yf_*`-Felder** aus `_hist_stats` (Batch) + `get_yfinance_data`
  (Singleton-Fallback), durch die `c.update`-Merge-Whitelist gereicht
  (**#411-Lehre**, §8j) — Merge-Assertion mutations-belegt scharf (der Test
  fälscht die Merge-Whitelist und beweist, dass die Felder dann fehlen).
- **Seed-2-Punkte** beim Erststart pro Ticker (Vormonat aus `sharesShortPrior
  Month` + `sharesShortPreviousMonthDate`, `short_pct_float=None` ehrlich,
  `seeded=true`; + aktueller Punkt) → **1-Monats-Positions-Delta ab Tag 1**
  messbar (= exakt das Paper-Maß).
- **Dedup** auf `settlement_date` (neuer Punkt nur bei geändertem Datum;
  `settlement_ts=None` → kein Punkt, fail-soft).
- **Retention** `SI_POSITION_HISTORY_DAYS=400` + `SI_POSITION_HISTORY_MAX_
  POINTS=24`/Ticker (**kein** 14d-`SCORE_HISTORY_DAYS`-Leak), atomarer Write,
  Workflow-`git add` für Cross-Run-Persistenz.
- **pub_date** via `finra_publication_date` (#408, settlement + 7 Handelstage,
  holiday-robust) — das Look-Ahead-Werkzeug ist jetzt **gegenständlich**.
- **Look-Ahead-Isolation**: reine Analyse-/Outcome-Persistenz, **NIEMALS**
  Score-/Filter-/Conviction-/Push-Feature (Grep-Guard-Test analog
  `entry_past_return_5d`; kein Read in `ki_agent`/`health_check`/Score-Funktionen).
- **Voller enriched US-Pool** (non-US übersprungen — yfinance-SI ist US-FINRA).

Rein additiv: separate Datei, **kein** Backtest-Schema-Touch (kein S10, kein
v4-Bump), Golden unberührt. `c3f2ac8`: CI-Minimal-Install-Rot behoben (Test
stubbt jetzt `requests`+`watchlist` — Sandbox-CI-Env-Divergenz, §8n). Files:
`daily-squeeze-report.yml` +5, `config.py` +11, `generate_report.py` +198,
`mock_test_si_position_history.py` +344, `run_ci_mock_tests.py`. **98 CI-Tests
grün, Guardian ✅. Neue Datei/Schema + neuer Workflow-Step → manueller Merge.**

### PR #424 — 13.07. — `20f78b6` (squash)
**Doku:** Handover A+B-Entblockung gesichert (SI-Positions-Zeitreihe via
yfinance). Aktualisiert §4 (A/B-Zeilen ✅ ENTBLOCKT) + §6i (Blocker REVIDIERT +
GEBAUT) auf den #423-Stand. Reine Doku, **Auto-Merge**.

### PR #425 — 13.07. — Merge `74b1532` (feat `df1f770`)
**★ Monster-Score neutralisiert (Anzeige + Push + Signal-Zähler).** Der
`monster_score` ist unvalidiert (30.06. AUC-Kollaps 0.76 n=13 → 0.51 n=20,
§8e) und darf **kein** Aktions-/Rendite-Signal mehr suggerieren. Drei Wirkungen:
- **Konfidenz-Tier** von setup-erbend auf **heuristisch** (🔴) fix gesetzt —
  `monster_score` erbt nicht mehr die Setup-Robustheit.
- **Push `monster_backup` komplett RAUS** aus `ki_agent.detect_anomalies`
  (war früher die lauteste Push-Klasse, dominiert von NVAX/GRPN).
- **`n_signals`-Zähler monster-frei**: zählt seit 13.07. über `ki_signal_
  score ≥ 70` (vorher `monster_score ≥ 70`) — konsistent zum grünen Dot der
  KI-Agent-Statusleiste; **Zähler bleibt load-bearing** (Statusleiste intakt,
  §8p — erst Konsument, dann Definition ändern, nicht löschen).

BLEIBT: `apply_monster_score`, Persistenz, `score_history`, Sortier-Option
`data-sort="monster"`. CLAUDE.md synchron (Konfidenz-/Anomaly-Tabelle,
Gating-Text, Deprecated `ANOMALY_MONSTER_BACKUP`). Files: `CLAUDE.md`,
`config.py`, `generate_report.py`, `ki_agent.py`, `mock_test_monster_
neutralization.py` +191, `mock_test_score_confidence.py`, Golden −1.
**14 Checks + voller CI 99 grün, Guardian ✅. Push-/Score-Anzeige-Touch →
manueller Merge.**

### PR #426 — 13.07. — Merge `db8bb21` (feat `82be888`)
**★ Monster-Feinschliff (Optik + Earnings-Body + Test-Label).** Nachschärfung
zu #425:
- **A** — Monster-**Zahl + Progress-Bar neutral-grau** (`#22c55e→#94a3b8`) in
  **beiden** Render-Pfaden (v1 `_card` + v2/Cockpit) statt Ampel-Grün.
  Konstante `_MONSTER_NEUTRAL_COLOR = "#94a3b8"` (`generate_report.py:4590`).
- **B** — Earnings-Sofort-Alert-**Body ohne 🔥-Monster-Aufmacher** (der
  Feuer-Emoji suggerierte Monster-Edge im Push-Text).
- **C** — Test-Label: `mock_test_push_inflation_gating` nutzte „monster_backup"
  als generisches Gating-Label → auf **`perfect_storm`** umbenannt (realer
  high-severity gegateter Trigger); Header-Prosa nennt `monster_backup` als
  historisch entfernt.

Golden mit-aktualisiert (nur Monster-Farbe `#22c55e→#94a3b8`, Setup/KI
unverändert — Diff-verifiziert, keine Kontamination). `mock_test_monster_
neutralization` um A2 (Neutral-Farbe beide Pfade) + B (Earnings-Body, Push
abgefangen) erweitert; `card_cockpit_stage1`-Namespace um die neue Konstante
ergänzt. **Voller CI 99 grün, Guardian ✅. Anzeige-/Push-Touch → manueller
Merge.**

---

### Vortage 11.–12.07.2026 (voriger Session-Bogen — Kontext)

### PR #411 — 11.07. — im Deploy `7e112ac` gelandet (Fix belegt `generate_report.py:16446-16451`)
**★ Bugfix `entry_past_return_5d` — gedroppter Pre-Entry-Nenner.** Der Nenner
`close_5td_before_entry` wurde in `_hist_stats` korrekt berechnet, aber im
`c.update`-Enrichment-Merge (`generate_report.py def main()`) **nicht in die
Key-Whitelist aufgenommen** → fiel weg → `_compute_entry_past_return_5d(price,
None)` = None (50/50 Records None). **KEIN** Namens-Mismatch. Fix rein additiv:
(a) Merge reicht `close_5td_before_entry` aus `yfd` durch (heute belegt
`generate_report.py:16451` mit Kommentar „…blieb s.get(...) None, der
Backtest-Nenner…"); (b) `get_yfinance_data` (Fallback) berechnet+returnt den
Wert; (c) Mock-Test um **Merge-Assertion** + End-to-End-Non-Null-Kernbeweis
erweitert. Wirkt **vorwärts** (Alt-None bleibt None, kein Backfill). Golden
byte-identisch. Guardian ✓. **Manueller Merge.**
*(Hinweis: die im vorigen Handover für #411 genannten Hashes `902671a` /
`dd31fdb` existieren im aktuellen Repo NICHT — vermutlich Branch-lokal
vor Squash. Belegbar ist nur die Landung im Code, s. o.)*

### PR #412 — 11./12.07. — Merge `84c4e7f` (feat `7823757` + `0b8f161`)
**★ Sammel-Felder-Status-Panel** (neutral, Datenerhebungs-Fortschritt). Neue
read-only `.bt-tile--wide` in `#bt-section` + `_btCollectStatus(data)`: zeigt
pro Sammel-Feld (`max_gain_pct`, `conviction_score`, `days_to_earnings`,
`entry_past_return_5d`, `si_velocity_pub`) einen **dynamischen non-null-Zähler**
aus `_btData` + Status — **KEINE Feld-Werte, kein Signal** (Auffanglinie,
analog #406). **Look-Ahead-Guard-Fix (`0b8f161`):** Feldnamen in
`config.COLLECT_STATUS_FIELDS`, als JS-Render-Konstante injiziert → keine
Backtest-Feldnamen-Literale im Source → alle 3 Look-Ahead-Guards bleiben grün
(Weg-A-Muster §7a-bis). Golden mit-aktualisiert. Guardian ✓. **Manueller Merge.**

### PR #413 — 12.07. — Merge `5756926` (feat `ae1c825`)
**★ Wöchentlicher Lit-Check-Reminder** (standalone). Neuer Workflow
`lit_reminder.yml` (Cron `33 16 * * 5` = Fr 18:33 Berlin) + `scripts/lit_
reminder.py`: **ein** fixer ntfy-Push „📚 Wöchentlicher Reminder: Squeeze-
Forschung Web-Check fällig". **Null Trade-Pipeline-Touch**, `permissions:
contents: read`. Muster: `health_check_digest` (URL-Pattern, ASCII-Title-Strip).
Guardian ✓. **Manueller Merge.**

### PR #414 — 12.07. — Merge `f15ca9b` (refactor `4eb2c73`)
**★ „Erste Erkenntnisse"-Empfehlungsblock ENTFERNT.** `_btRenderRecommendation`
rankte Score-Buckets nach Median-Rendite und gab eine wörtliche „Empfehlung:
Score X + max. Haltedauer YT." aus — ein als Trade-Signal lesbarer Edge-Claim,
im Widerspruch zur Auffanglinie + 30.06.-Null. Sauber entfernt (Funktion +
Aufruf + `#bt-reco`-Div + `.bt-reco*`-CSS); **`_btBucketStats` BLEIBT**
(Median-Kachel + Knaller-Label-Sync). Golden rein entfernend. **Manueller Merge.**

### PR #415/#416/#417/#418 — 12.07. — `fb25b4c` / `22f976f` / `ef78b40` / `05de38c` (squash)
**Doku-Kette:** #415 Paper-Verwertungsplan (Svoboda-Befunde §5 + 3-Schritt-Plan
§4 + Backlog §6g/§6h + Lessons §8h/§8i); #416 Schritt D (Ausblick,
`squeeze_probability`); #417 Schritt-A-Blocker verankert *(seit #423 revidiert,
s. §6i)*; #418 Handover-Voll-Refresh. Reine Doku, **Auto-Merge**.

---

### Historischer Block 03.–10.07.2026 (belegt, unverändert)

### PR #400 — 03.07. — `a936886` (squash)
**★ Backfill thin-slice-Zähler** (Guardian-Nachbesserung aus #399). Pure Helper
`classify_outcome(df_len, mg) → str` (4 Klassen `none`/`thin_slice`/
`filled_zero`/`filled`). `compute_and_apply_backfill`-Return um `n_thin_slice`
erweitert. Trennt stille Datenlücken von echten Null-Gains. **Manueller Merge.**

### PR #401 — 03./04.07. — Merge `55be1dd` (Nachbesserung `7056cb2`)
**★ Backfill-Workflow `workflow_dispatch`.** `backfill_max_gain_pct.yml` —
manual-only, `cancel-in-progress: false`, `git add backtest_history.json`,
Idempotenz-Guard. Guardian ✓. **Manueller Merge.**

### `85cbbe9` — 04.07. — Live-Lauf
**★★ MAX_GAIN_PCT-Backfill DURCH — 330/330 Records, 0 thin-slice.** Alle reifen
Alt-Records tragen `max_gain_pct` (129 unique Tickers). Hypothese-C-Sample sofort
auswertbar.

### 04.07. — Hypothese-C-Auswertung (dokumentiert in #405)
**★★ 3 Schwellen +10/+30/+50 %:** Seed 04072026, Bootstrap N=2000, k=6 Holm.
**0/6 Holm-Rejects.** Alle AUC-CIs enthalten 0.5. **Auffanglinie über drei
Auswertungstage bestätigt.** Setup-Score bleibt Attention-Router/Screener.

### PR #402 — 02.07. — `0da83af` (Nachbesserung `498aeaf`)
**★ `entry_past_return_5d` Stufe A** (Reversal-/Momentum-Substrat). Adj-Close
beidseitig (Split-Konsistenz), None-Semantik STRIKT. **Kein neuer yf-Fetch.**
Look-Ahead-Konvention EINFROREN. Schema v4 unverändert. Guardian ✓. **Manuell.**

### PR #403 — 03.07. — Merge `b4d6b1d`
**★ Requirements-Cap-Semantik.** `yfinance==1.4.1 → >=1.4.1,<1.5` (analog
`pandas`/`peewee`). Löst #393-Segfault ohne Minor-Sprung. **Manueller Merge.**

### PR #404 — 04.07. — `1594f20`
**★ `days_to_earnings` Stufe A** (Katalysator × Score). Snapshot in
**Kalendertagen**, point-in-time (Fetch AM Report-Tag). Backfill strukturell
unmöglich. Look-Ahead EINFROREN. Guardian ✓. **Manueller Merge.**

### PR #405/#406 — 04./08.07. — `805c9df` / `7e4bde0`
#405 Doku-Refresh (Auto). #406 **★ Conviction-Level-Texte neutralisiert**
(„Aggregations-Anzeige, nicht validiert"), Golden mit-aktualisiert. **Auto-Merge.**

### PR #407/#408/#409 — 09./10.07. — `f7513a9` (`b87474a`) / `57d8f18` / `a52ef48` (`83ac7da`)
#407 **★ Good Friday algorithmisch** (Meeus, Python+JS-Spiegel bit-identisch).
#408 **★ `finra_publication_date`** (settlement + 7 Business-Days, `scripts/
business_days.py`). #409 **★ `si_velocity_pub`** (Look-Ahead-freier SI-Volumen-
Rate über N=3 publizierte Reports, `pub_date`-Filter). Alle drei **manueller
Merge**, Guardian ✓.

---

## 2) AKTIVE POSITIONEN

**Kanonische Quelle: privater Gist** (`squeeze_data.json`, `positions`-Sub-
Objekt). Aus der Sandbox nicht direkt lesbar — `app_data.json`-Mirror ist der
letzte Daily-Run-Snapshot; bei Abweichung gewinnt der Gist. Zwischen Runs kann
`current_price` stale sein (S3-Merge-Tag-Muster, §8 — kein Ausfall-Indiz).

**Stand `app_data.json` — letzter erfolgreicher Daily-Run `last_daily_run_ts =
2026-07-13T09:48:58Z` (premarket, 13.07.):** **7 offene Positionen.**

| Ticker | entry_date | entry_price | current_price | shares | Hold-Flag |
|---|---|---|---|---|---|
| AMC   | 2026-05-01 | $1.50   | $1.89   | 500 | ✓ `no_exit_alerts=True` |
| IONQ  | 2026-05-11 | $49.10  | $42.86  | 40  | — |
| PDYN  | 2025-01-20 | $11.52  | $5.28   | 150 | — |
| AI    | 2026-06-01 | $11.00  | $8.95   | 10  | — |
| WOLF  | 2026-07-03 | $50.97  | $35.29  | 7   | — |
| FRMM  | 2026-07-06 | $6.95   | $5.96   | 15  | — |
| LENZ  | 2026-07-07 | $6.00   | $5.59   | 15  | — |

**Änderungen seit 12.07.-Handover:** Positions-Set unverändert (dieselben 7).
`current_price`-Werte sind der **13.07.-premarket**-Snapshot — zwischen Runs
stale (kein Ausfall-Indiz, §8). Details (P&L, These, Lessons) ausschließlich im
Gist / Trade-Journal, nicht Session-Kontext.

**Hold-Flag-Regel unverändert:** `AMC` trägt weiterhin `no_exit_alerts=True`
(bewusster Buy-and-Hold-Skip aller Exit-Pushes). Andere Positionen bekommen
Exit-Pushes; **Schutzschicht seit PR #381** (21.06.): Exit-Push-Pipeline feuert
**nicht** an Wochenenden oder US-Feiertagen (`config.US_MARKET_HOLIDAYS`) UND
nur bei `available=True`.

---

## 3) VERIFIKATION (nächste Handelstage, konkrete Beobachtungspunkte)

### Woche 03.–08.08. — Verifikation ausstehend (nächster Deploy / Digest)

- **★★ inst_ownership-Zeile erscheint (#512).** Nach dem nächsten Daily-Deploy zeigt
  die Karten-Zeile „Institutioneller Anteil" **echte %-Werte** (war seit jeher stumm,
  0 % Coverage durch tote Keys). Server-Render war schon korrekt (×100), JS-Drawer
  jetzt auch. **Passiv beobachten.**
- **★★ Earnings-Alert-Name live (#507).** Der nächste After-Hours-Earnings-Push (nur
  bei `earnings_days 0–1` + frisches 8-K/News) heißt **„Earnings-Alert: {ticker}"**,
  📅 statt 🚀, ohne Score-Zahl, Body „anstehendes Earnings-Ereignis, kein Squeeze-Signal".
- **★ Panel-Rollfenster-Zeile live (#508).** Backtesting-Panel zeigt unter der
  Datenpunkt-Zahl die graue Rollfenster-Zeile nach nächstem Deploy.
- **★★ §4-Re-Test-Zähler im Digest (#509).** Der tägliche Health-Check-Push (Cron
  08:47 UTC) trägt `📊 Re-Test-Zähler (§4): n = X/250 · Export N Zeilen`. **Beobachten:**
  n wächst forward; Export-Zeilenzahl steigt bei jedem postclose (stiller Ausfall
  sonst sichtbar). Stand 05.08.-postclose: **n=2** (FRMM, ANAB), Export 705 Zeilen —
  bereits verifiziert (erster Forward-Batch, 10 vom 21.07. korrekt nachgezogen).
- **★ Matured-Export forward wächst (#501/#503).** `matured_backtest_export.jsonl`
  bleibt append-only/prune-immun; 0 Doppel-Keys, 0 Records mit `days_old ≤ 14` bei
  Export — Kriterien im Echtbetrieb bestätigt.

### ✅ AUFGELÖST (17.07. — entry_past_return_5d Stufe-B-Backfill durch)

- **★★ BACKFILL LIVE DURCH — Gate PASS, 465/470 gefüllt.** Der `mode=live`-Lauf
  (`5d8e78d`) schrieb `entry_past_return_5d` auf **465** der 470 v4-Alt-Records
  (5 skipped: delisted/IPO < 6 Bars). **Gate PASS** belegt (42 verifiziert / 41
  exakt 0.000 / median 0.0 / mean-Inlier 0.0 / 1 AMCX-Artefakt 0.05). Manifest mit
  **465 Einträgen** git-belegt. **Nächster Handelstag — passiv:** der Sammel-Panel-
  Zähler `entry_past_return_5d` (§3 LAUFEND, war 10) springt beim nächsten Deploy
  auf **~475** (465 Backfill + weiter gesammelte Vorwärts-Records). Kein Bau —
  reine Beobachtung. **Rückweg jederzeit:** `mode=undo` (nullt nur die 465).
- **★ Trennung explorativ vs. konfirmatorisch bleibt Pflicht (§4/§5):** die 465
  backgefüllten Records sind **RETROSPEKTIV/IN-SAMPLE**, die ab 13.07. vorwärts
  gesammelten (aktuell 42, +10/Handelstag) die **konfirmatorische** Evidenz — in
  jeder Paper-C-Auswertung **getrennt ausweisen, NICHT poolen** (§8z1-Klasse).

### ✅ AUFGELÖST (14.07.-Vormittag, aus dem 13.07.-Postclose belegt)

- **★★ `entry_past_return_5d` — VERIFIZIERT (non-null greift).** Der 13.07.-
  Postclose schrieb **10/10 non-null** Records (Beispiel ABEO **11.09**,
  Werte-Spektrum `[-7.28 … +11.09]`, plausibel als 5-Tage-Return). Present 60 /
  non-null 10 — die 50 present-None sind **pre-fix Alt-Bestand** (06.–10.07.,
  forward-only, kein Backfill). **Der #411-Merge-Fix war korrekt**; das Feld
  sammelt. Der 14.07.-Vormittag-„0 non-null"-Alarm war ein **Zähl-Artefakt**
  (Gesamt-present zählte die 50 Alt-None mit) → §8-Lesson. Compute an **allen 3
  Pfaden** (`get_yfinance_data:907`, `_hist_stats`-Batch `:1089`, Fallback
  `:1106`) defined-before-use + pre-entry-sauber — **kein** UnboundLocalError
  (die „:1222 aus `c`"-Fehldiagnose ist widerlegt: `:1222` ist ein Dict-Key
  `ma200`, es gibt in `get_yfinance_data` keine Variable `c`). Ab #429 zusätzlich
  durch das Station-1-Regressions-Netz verriegelt.

- **★★ `si_position_history.json` — VERIFIZIERT (Seed greift).** Datei existiert,
  **28 Ticker · 56 Punkte · je 2** (Vormonat `seeded:true` + aktuell). Struktur
  exakt wie §4-Plan (`{ticker:[{settlement_date, shares_short, short_pct_float,
  pub_date, seeded}]}`). `pub_date` holiday-robust bestätigt (`2026-05-29 →
  06-09`, `2026-06-30 → 07-10` — überspringt Fr 03.07. Independence Day). Seit
  #430 im Status-Panel sichtbar (n=28). **Restkante — ✅ sichtbar gemacht (PR #578,
  07.10.2026):** falls yfinance `dateShortInterest` künftig als `Timestamp` statt
  epoch-int liefert, wird der Punkt weiterhin fail-soft übersprungen (Rückgabewert/
  Kontrollfluss unverändert) — aber jetzt mit genau einer `log.warning`-Zeile pro
  Lauf statt stillem Datenverlust.

### ✅ AUFGELÖST (15.07. — Bootstrap-Shell Phase 0 + Phase 1)

- **★★ PHASE-0-ZYKLUS-VERIFY — ✅ ERLEDIGT (alle drei grün).** Über **2 Postclose-
  Läufe** verifiziert: **(a)** `app.html` byte-identisch zum Content (md5-Vergleich),
  **(b)** **S9 grün** im Health-Log (kein WARN/crit; S9 prüft seit #434 `app.html`),
  **(c)** `ki_agent` zog die Top-10 aus `app.html` **10/10 inkl. Neu-Einsteiger**.
  → Freigabe-Bedingung für Phase 1 war damit sauber erfüllt.

- **★★ BOOTSTRAP-SHELL PHASE 1 — ✅ LIVE + iOS-Adoption durchgeführt (#436).** Der
  Flip ist scharf (`index.html` = 754-B-Shell, `app.html` = Content), die einmalige
  iOS-Home-Icon-Neuanlage ist erfolgt. **Der PWA-Launcher-Cache ist damit
  strukturell gelöst** — jeder Launch bounct über eine frische `?v=`-URL auf frische
  Bytes.

- **★★ GERÄTE-VORFALL 15.07. abends — korrupter lokaler Safari-Zustand (NICHT
  Pipeline/Shell).** Nach der Adoption zeigte **ein** Safari trotz nachweislich
  frischem Server eine alte Seite („Seite kann nicht geöffnet werden" bei direkter
  `app.html`-URL), während der **PC korrekt lud**. **Ursache:** korrupter lokaler
  Safari-Website-Daten-Zustand für die github.io-Domain — **nicht** die Pipeline,
  **nicht** die Shell (die Server-Antwort war belegbar frisch). **Fix:** Safari-
  Website-Daten für github.io gelöscht → sofort frisch. **Nebenwirkung:**
  `localStorage` weg → Watchlist + Token neu anlegen (Präzedenz #234). → Lesson §8x
  („Server frisch ≠ Gerät frisch").

### ✅ AKUT — ABGESCHLOSSEN (Sammel-Review 28.09.2026)

Alle sechs Punkte nach 76 Tagen unverändertem Verifikations-Stand gesammelt
durchgegangen (Diagnose 28.09.2026, `open_items.json`-Eintrag
`block3-akut-verifikationsliste-stale`) und geschlossen. Originaltext je
Punkt unverändert erhalten, nur Status-Zeile angehängt — **einzige echte
Live-Neu-Verifikation heute ist Punkt 4** (Monster-Kachel, von Easy live am
iPhone geprüft); die übrigen fünf sind funktional durch nachfolgenden
Betrieb bzw. bereits im Dokument vorhandene Belege bestätigt, nicht heute
neu getestet.

- **★ FINALER LANGZEIT-BEWEIS der Shell (morgen früh, PASSIV).** Nach dem nächsten
  **Postclose** einmal das Home-Icon tippen: zeigt die **„Stand: HH:MM"-Zeile** den
  **neuen Marktdaten-Stand** (nicht die gestrige eingefrorene Seite)? Das ist der
  finale Beweis, dass der Launcher dauerhaft frische Bytes zieht. Kein Bau — reine
  Beobachtung.
  **✅ Erledigt, funktional bestätigt durch nachfolgenden Betrieb (28.09.2026)** —
  keine separate explizite Einzel-Bestätigung im Dokument gefunden, aber
  reibungsloser Dauerbetrieb der Bootstrap-Shell seit Monaten ohne
  Stale-Meldung gilt als hinreichender Beleg.

- **★ KLARSTELLUNG Stand-Zeile (Zwei-Run-Architektur, kein Bug):** **„Stand: HH:MM"
  = MARKTDATEN-Zeit** (nur volle Daily-Runs schreiben die Seite, 2×/Werktag) ·
  **„KI: HH:MM" = Agent-Tick** (stündlich, patcht nur `agent_signals.json` live).
  Beide dürfen **auseinanderliegen** — die HTML-Hülle ist legitim so alt wie der
  letzte Daily-Run, während die KI-Zeile frisch ist. **Kein Einfrieren, kein
  Defekt** (Diagnose 15.07.: Symptom „Seite 10:36, KI 17:50" war reines Timing).
  **Kein Task — reine Doku-Klarstellung (28.09.2026),** kein Verify-Bedarf.

- **★ KI-Karten nach Deploy (#432):** nach dem nächsten Deploy zeigen **alle 10**
  Top-10-Karten einen KI-Score (die 6 vormals „—" gefüllt, Farben konsistent).
  **Cache-Bust nötig** (iOS/Browser) — der Launcher-Cache bleibt das separate
  Phase-1-Thema.
  **✅ Erledigt (28.09.2026)** — PR #432 dokumentiert bereits im eigenen Eintrag
  eine Live-Bestätigung mit echten Daten am selben Tag (6/10 Karten gefüllt
  beobachtet: GRPN/INDI/FXHO/NTLA/FDMT/VSTM).

- **★ Monster-Kachel neutral-grau — iPhone-Blick (#425/#426):** Monster-Zahl +
  Progress-Bar müssen **grau** (`#94a3b8`) statt Ampel-Grün erscheinen, in
  **beiden** Karten-Pfaden (Top-10 + Watchlist-Drawer). Live-Verify am iPhone
  **noch ausstehend** (kein Golden-Ersatz für visuelle Korrektheit, §8 „Source
  grün ≠ Browser korrekt"). Earnings-Push-Body (falls einer feuert): **ohne
  🔥-Monster-Aufmacher**. → abhaken, sobald per iPhone bestätigt.
  **✅ Erledigt, iPhone-verifiziert 28.09.2026** — Easy hat die Kachel-Farbe live
  am iPhone geprüft, rendert korrekt grau/neutral.

- **★ Lit-Check-Reminder — erster Push (#413):** erster planmäßiger ntfy-Push
  **kommenden Freitag ~18:33 Berlin** (Cron `33 16 * * 5`). Watch: Push kommt
  an, Tag `books`. Bleibt er aus → `NTFY_TOPIC`-Secret prüfen (Workflow ist
  fail-visible: exit 1 bei Send-Fehler trotz gesetztem Topic).
  **✅ Erledigt (28.09.2026)** — funktional bestätigt durch wochenlangen aktiven
  Betrieb: spätere Lit-Check-Einträge (21.08., 09.09.2026) belegen laufenden
  Cron-Betrieb weit über den ersten Push hinaus.

- **★ Status-Panel 6. Eintrag (#430) — live sichtbar:** nach nächstem Deploy im
  `#bt-section` prüfen: Zeile „Short-Interest-Position (si_position_history) ·
  n=28 (28 Ticker) · sammelt …" erscheint, **keine** Serien-Werte. Graceful-
  Empty ist per Test gesichert.
  **✅ Erledigt (28.09.2026)** — funktional bestätigt durch nachfolgende Nutzung
  als etablierte Datenquelle (§4/§5 referenzieren `si_position_history`
  seither durchgehend als aktive, produktive Quelle).

### LAUFEND (kein Einzeltermin — wachsen pro postclose-Werktag)

- **★ Sammel-Felder-Status-Panel — Zähler (#412):** die Kachel zählt dynamisch
  non-null aus `_btData`. Stand 14.07. (aus `backtest_history.json`, 1958
  Records): `max_gain_pct` **400** · `conviction_score` **100** ·
  `days_to_earnings` **51** (60 present) · `entry_past_return_5d` **10**
  (60 present) · `si_velocity_pub` **20**. **Sechster Eintrag (#430):**
  `si_position_history` **n=28** (Ticker mit ≥2 Punkten, aus separater Datei).
  Watch: Zähler steigen automatisch; keine Feld-Werte im Output.
- **★ `si_velocity_pub` / `days_to_earnings` — Reifung (§4):** Auswertung erst
  bei n≥40. `si_velocity_pub` erwartet `None` in den ersten Wochen (< 3
  eligible publizierte Reports vor Entry), Zahlenwert nach ~6–8 Wochen.
- **★ `max_gain_pct` — Verteilung:** Stand 14.07. **400 present / 400 non-null**
  (330 Backfill 04.07. + Vorwärts). Watch: keine `None`-Persistierung bei reifen
  Records (≥10 Trading-Days).

### KEINE VERIFIKATION MEHR NÖTIG (abgeschlossen)

- Karfreitag algorithmisch (#407) — nächste Live-Verify erst Fr 02.04.2027
  (`US_HOLIDAYS.includes("2027-04-02")`).
- yfinance-Cap `>=1.4.1,<1.5` (#403) — Actions-Läufe seit 04.07. stabil ohne
  Segfault; nur bei Cap-Aufhebung (§6e) wieder relevant.
- „Erste Erkenntnisse"-Empfehlungsblock (#414) — entfernt, `node --check` grün.
- Independence Day Fr 03.07.2026 (Holiday-Skip #381 verifiziert).
- Redeploy-Auto-Trigger aus (#357 seit 13.06. verifiziert).
- Hypothese-C-Auswertung (durchgeführt 04.07., §4 erledigt-null).

---

## 4) GEPLANTE AUFGABEN + WIEDERVORLAGEN (mit Daten)

### RE-TEST-KALENDER (kanonisch, Stand 05.08.2026)

| Datum | Was | n-Ziel | Notiz |
|---|---|---|---|
| ✅ **DURCHGEFÜHRT 15.07.** | ki_signal_score-Edge-Re-Test | n=55 gereift | **KEIN belegter Effekt** (Details §5). Re-Test-Bedingung neu **datengetrieben, nicht kalendarisch:** **WIN-Bucket ≥ 20** (aktuell nur 13!) **UND zweites Marktregime** im Sample. Nicht „~Mitte Aug" — die Kalender-Angabe war irreführend, es zählt der WIN-Bucket + Regime-Diversität. |
| **~Ende Juli / Anfang Aug** (korrigiert) | Conviction-Edge (Prüfpunkt P3 aus 30.06.) | n ≥ 100 gereift | **Termin vorgezogen** (Sammel-Raten-Diagnose 15.07.): 112 gesammelt / 20 gereift → n≥100 gereift bereits ~Ende Juli/Anfang Aug (das frühere „~Ende Aug" war Puffer). Composite aus Setup/Earliness/Anomaly/Regime — Aggregations-Anzeige, Edge selbst unbelegt. **ERSETZT (10.10.2026)** — kein Zielgröße/Kriterium war hier je festgelegt; siehe Erratum-Block „Erweiterung vor Auswertung — Test (c) Conviction-Zusatznutzen" im Setup-Edge-Re-Test-Freeze unten (Test (c), Holm k=3). Diese Zeile bleibt als Historie stehen, nicht gelöscht. |
| **datumsfrei · Auslöser n≥250** | **Exit-B.1-Re-Test** — **vorabregistriert (eingefroren 05.08.2026)** | n ≥ 250 · `score≥70` ∧ `provenance=forward` | Volle Registrierung im Block direkt unter der Tabelle. Quelle `matured_backtest_export.jsonl` (append-only, prune-immun). **n=144 (nachgerechnet 27.09.2026, 07:16:50 UTC — siehe Protokolleintrag unten).** Projektion ~Mitte Nov. 2026 (unsicher, **kein Termin**). |
| **entfällt** | ~~Setup-Edge-Re-Test~~ — **NICHT vorabregistriert** (Herausnahme 05.08.2026) | — | Zielgröße/Schwelle/Erfolgskriterium wurden **nie festgelegt** (Ursprung #394 = 15 gesammelte Hypothesen, 0/15 Holm — welche geprüft werden soll, wurde nie bestimmt). Neu-Registrierung mit **eigenem Freeze-Datum** bei Bedarf; **bis dahin existiert kein Setup-Edge-Re-Test.** Details im Block unten. |

### VORABREGISTRIERUNG — eingefroren 05.08.2026

**(Ersetzt den früheren September-Termin und den #500-Prune-Deckel ~145 — eine
Wahrheit, keine Parallel-Angabe.)**

**Datenquelle & n-Definition (Definition A).** Gezählt wird **ausschließlich aus
`matured_backtest_export.jsonl`** (append-only, **prune-immun**) — **NICHT** aus
`backtest_history.json` (das unterliegt dem 90-Tage-Prune `BACKTEST_MAX_DAYS=90`).
Damit ist der frühere **~145-Deckel aus #500 aufgehoben**: der gereifte Pool verfällt
nicht mehr. **n = Records mit `score ≥ 70` UND `provenance == "forward"`** (Outcome
erst nach Export-Existenz gereift = sauberes Out-of-Sample). **Heute n = 0.**

- **In-Sample zählt NIE:** die **242** `score≥70`-Records im heutigen Export tragen
  alle `provenance=backfill` — ihr Outcome war beim 04.08.-Import bereits bekannt.
  Sie sind **kein** OoS und zählen **nie** zum n. (**242 ist die Gesamtzahl** — die
  14 unten sind eine **Teilmenge davon**, NICHT additiv: 242, nicht 256.)
- **Davon 14** `score≥70`-Records mit entry ≥ 13.07. (alle ebenfalls
  `provenance=backfill`, da `provenance=forward` heute 0): zählen **ebenfalls nicht**
  zum primären n, werden aber **separat als Sensitivitäts-Gegenprobe** ausgewiesen
  („**OoS nach Datum, Outcome bei Import bekannt**") — nie ins primäre n gemischt. Die
  übrigen **228** sind In-Sample nach **Datum UND Herkunft**.

**Auslöser (datumsfrei):** Der Test läuft, **sobald n ≥ 250** erreicht ist — **kein
Kalendertermin**. **Projektion** bei Takt ~**3,6** `score≥70`-Forward-Records/
Handelstag: **~Mitte November 2026** — ausdrücklich eine **unsichere Schätzung, kein
Termin** (der Takt schwankt mit Marktphase / Top-10-Rotation).

**Vorabregistrierter Test — Exit-B.1 (Exit-Timing-Hinweis).**
- **Zielgröße:** Return-Differenz **Δ(5d−10d)** und **Δ(3d−10d)** im **`score≥70`-
  Bucket** (Früh-raus-Vorteil gegenüber dem 10-Tage-Halten).
- **Erfolgskriterium** (globale Erfolgs-Definition §5, an die Δ-pp-Metrik gebunden) —
  belegte Edge **nur wenn**: **(a)** Holm-signifikant über die **zwei** vorab
  benannten Größen Δ(5d−10d) und Δ(3d−10d) (**k = 2**); **(b)** das **Bootstrap-CI
  der Δ schließt 0 aus** (untere Grenze > 0 in der erwarteten Richtung — ersetzt für
  diese pp-Metrik die AUC-CI-Formulierung); **(c)** plausibel im Regime-Split
  reproduzierbar. **Punktschätzung ist nie Beleg.**
- **Auswertungsverfahren (verbatim wie bisher):** `mann_whitney_u_auc` + Holm +
  Cluster-Doppellauf, Bootstrap-CI, **N = 2000**, fester Seed.
- **Altzahlen sind REFERENZ, NICHT die Schwelle:** die In-Sample-Punktschätzung vom
  01.07. (Δ(5d−10d) **+3,81 pp**, Δ(3d−10d) **+4,67 pp**, n=110) dient **nur zur
  Einordnung der Richtung** — sie ist **ausdrücklich keine Zielmarke**. Die Schwelle
  ist allein das Kriterium (a)/(b)/(c) oben.

**Setup-Edge-Re-Test — NICHT (mehr) vorabregistriert (Herausnahme 05.08.2026).**
Zielgröße/Schwelle/Erfolgskriterium wurden **nie festgelegt** (Ursprung #394 = **15
gesammelte Hypothesen, 0/15 Holm** — welche davon geprüft werden soll, wurde nie
bestimmt). Deshalb aus dem registrierten Kalender **herausgenommen**. Wird bei Bedarf
als **neue** Registrierung mit **eigenem Freeze-Datum** aufgesetzt; **bis dahin
existiert kein Setup-Edge-Re-Test.** (Keine der 15 Hypothesen wird hier
vorausgewählt.)

**Freeze-Status 05.08.2026 — warum Definition A (nicht B).** „Forward" ist an
**`provenance=forward`** gebunden (**A**), **nicht** an entry-Datum ≥ 13.07. (**B**).
Grund, git-belegt: ein sauberer, unangetasteter Freeze **strikt vor** dem 13.07.
liegt **nicht** vor — die Outcomes wurden **nach** dem 13.07. angesehen (**explorativer
Paper-C-Read `f3f09ae`, 17.07.**) und die Population wurde **nach** dem 13.07.
nachjustiert (**#494 `d2b1d5b`, 29.07.**). Records, deren Outcome beim 04.08.-Backfill-
Import bereits bekannt war, können daher **kein** OoS sein — nur `provenance=forward`
ist kontaminationsfrei (deckt sich mit der Datei-Eigen-Semantik `backfill →
In-Sample-Vorsicht`).

**Änderungs-Protokoll (bindend ab 05.08.2026):** **Keine Änderung an diesem §4-
Registrierungsblock ohne datierten Protokolleintrag**, der die Änderung **und ihren
Grund** festhält — jede spätere Anpassung muss so als Bruch sichtbar bleiben.

**Protokolleintrag 18.09.2026** (Grund: `return_Nd_net` [PR #549, 12.09.] und
`return_Nd_vs_spy` [PR #554, 18.09.] wurden **NACH** dem 05.08.-Freeze eingeführt
und sind daher **nicht** Teil der eingefrorenen „Return-Differenz"-Definition).
Die bindende §4-Auswertung (Δ(5d−10d), Δ(3d−10d)) rechnet **ausschließlich** mit
den **BRUTTO-Feldern** `return_5d`/`return_3d`/`return_10d` — bestätigt sowohl
durch den zeitlichen Freeze-Vorrang (die Netto-/SPY-Felder existierten zum
Freeze-Zeitpunkt schlicht nicht) als auch durch die Selbstauskunft beider
einführenden PRs in `config.py` — **nicht wortgleich**: PR #554
(`return_Nd_vs_spy`) bestätigt explizit „Fließt NICHT automatisch in
bestehende Vorabregistrierungen (§4 Exit-B.1, H5) ein", während PR #549
(`return_Nd_net`) die Frage offen lässt („Ob/wie diese Felder in bestehende
oder künftige Vorabregistrierungen einfließen, ist NICHT Teil dieser
Änderung — bleibt eine offene Entscheidung"). Beide schließen eine
automatische Übernahme also aus bzw. lassen sie ausdrücklich ungeklärt —
keiner der beiden PRs beansprucht, die Brutto-Bindung selbst zu ändern.
Bei Erreichen von n=250 werden
**zusätzlich, rein informativ und NACHRANGIG** zur bindenden Brutto-Auswertung
folgende Zusatzausweise mitgeliefert: **(a)** eine Netto-Sensitivitätsrechnung
mit `return_Nd_net`, **(b)** eine SPY-bereinigte Zusatzrechnung mit
`return_Nd_vs_spy`. Beide sind **NIEMALS** Ersatz für das bindende Brutto-
Kriterium und ändern nicht dessen Erfolgs-/Misserfolgs-Bewertung — sie dienen
ausschließlich der Einordnung (z. B. „hält die Brutto-Edge auch nach Kosten-/
Marktbereinigung stand"). Sollte eine künftige Registrierung (z. B. eine
Fortsetzung von Exit-B.1 oder ein neuer Test) stattdessen direkt Netto oder
SPY-bereinigt als bindendes Kriterium verwenden wollen, bedarf das einer
**eigenen, neuen Vorabregistrierung mit eigenem Freeze-Datum** — keine
rückwirkende Umwidmung dieses Blocks.

**Beobachtungspunkt — Marktregime-Kontext (sofort nutzbar, Daten bereits
vollständig vorhanden, kein Warten nötig, Stand 18.09.2026):** `market_regime`
(bull/bear/neutral) und `vix_level` sind auf allen aktuellen Primär-n-Records
bereits zu **100 %** befüllt. Bei der Ergebnis-Interpretation bei n=250 soll
dieser Kontext mitberichtet werden (war die Sammelperiode markttechnisch eher
freundlich oder schwierig), um ein positives Ergebnis nicht fälschlich als
reine Squeeze-Edge zu werten, falls es primär ein günstiges Marktumfeld
widerspiegelt.

**Korrektur-Vermerk — §4-Zähler-Diskrepanz (Stand 18.09.2026, GEKLÄRT
27.09.2026):** der zuletzt im Health-Check-Digest angezeigte §4-Zähler-Stand
zeigte **n=118**, eine direkte Nachzählung in `matured_backtest_export.jsonl`
nach der exakten eingefrorenen Definition (`score≥70 ∧ provenance=forward`)
ergab am selben Tag **n=130**. Ursprünglich nicht geklärt, ob das auf eine
Diskrepanz zwischen Digest-Anzeige und tatsächlichem Export-Stand hindeutet
oder sich einfach durch Zeitabstand erklärt — als offener Punkt vermerkt.

**Ursache jetzt geklärt (Diagnose 27.09.2026):** reiner **Zeitversatz
zweier Zählzeitpunkte, KEIN Logik-Bug.** `_count_matured_retest()` ist seit
Einführung (`#509`, 08.08.2026) **byte-identisch** mit dem heutigen Code
(git-belegt: `git show d6c51b01:health_check.py` vs. aktueller Stand,
Diff = 0). Nachweis per historischem `matured_backtest_export.jsonl`-Stand
zu den jeweiligen Daily-Run-Commits: der Wert **n=118** entspricht exakt dem
Datei-Stand nach dem **14.09.2026**-Postclose-Commit (`6b6846a5`), **n=130**
exakt dem Stand nach dem **17.09.2026**-Postclose-Commit (`21e318a1`) —
beide re-berechnet mit derselben, unveränderten Zähllogik. Die Zahlenreihe
über die Postclose-Commits 09.–18.09. wächst glatt monoton (112 → 114 → 114
→ 118 → 122 → 127 → 130 → 134, für 09./10./11./14./15./16./17./18.09. —
Guardian-nachgerechnet), keine Anomalie, kein Sprung. Der im Vermerk zitierte
„Digest-Wert n=118" stammte also von einem **~4 Tage älteren** Digest-Lauf
(14.09.) und wurde einer **taggleich frischen** manuellen Nachzählung
(18.09., die zufällig exakt den 17.09.-Postclose-Stand traf) gegenüber-
gestellt — zwei unterschiedliche Zeitpunkte auf demselben, gesund wachsenden
Zähler, kein Mess- oder Logikfehler. **Aktueller Live-Stand: n=144/250**,
nachgerechnet **27.09.2026, 07:16:50 UTC** direkt gegen die aktuelle
`matured_backtest_export.jsonl` (1057 Zeilen gesamt).

**Protokolleintrag 27.09.2026** (bindend gemäß Änderungs-Protokoll-Regel
oben): Anlass = Konsistenz-Diagnose 27.09.2026 fand die vorstehende
Diskrepanz ungeklärt vor. Änderung an diesem Block: (a) der obige
„Korrektur-Vermerk" wurde um die Ursachenklärung ergänzt (Text nicht
gelöscht, nur ergänzt — Nachvollziehbarkeit bleibt erhalten), (b) die
Re-Test-Kalender-Tabelle und dieser Absatz zeigen jetzt den lebenden
Wert n=144 statt des eingefrorenen `n=0` vom 05.08.-Freeze-Moment. **Die
eingefrorene §4-Definition selbst (`score≥70 ∧ provenance=forward`,
Brutto-Bindung) ist NICHT verändert** — nur die angezeigte Zählung wurde
aktualisiert und ihre Historie erklärt.

### VORABREGISTRIERUNG — Setup-Edge-Re-Test (Score-Trennschärfe), eingefroren 10.10.2026

**Verhältnis zu §4 oben.** Der §4-Re-Test (Exit-B.1) prüft **Δ(5d−10d)** und
**Δ(3d−10d)** im `score≥70`-Bucket — ein **Exit-Timing-Hinweis**, **keine**
Aussage darüber, ob der Score gute von schlechten Aktien trennt. Dieser
Block registriert **diese separate Frage** neu, nachdem sie am 05.08.2026
(§4-Freeze oben, Abschnitt „Setup-Edge-Re-Test — NICHT [mehr] vorabregistriert")
bewusst aus der Registrierung genommen wurde — Zielgröße/Schwelle/
Erfolgskriterium waren dort nie festgelegt (Ursprung #394 = 15 gesammelte
Hypothesen, 0/15 Holm). Struktur, Wortwahl und Pflicht-Angaben sind bewusst
analog zu §4 gehalten, damit beide Registrierungen vergleichbar bleiben.

**Datenquelle & n-Definition — identisch zu §4.** Gezählt wird ausschließlich
aus `matured_backtest_export.jsonl` (append-only, prune-immun) — **nicht** aus
`backtest_history.json` (90-Tage-Prune `BACKTEST_MAX_DAYS=90`). Reine Zählung
per 10.10.2026 (Diagnose vor diesem Freeze, keine Outcome-Werte enthalten):
**472** gereifte Forward-Zeilen (`provenance=="forward"` ∧ `return_5d`/
`return_10d` befüllt), Zeitraum **21.07.–25.09.2026** (47 Handelstage, Ø
**10,04** Zeilen/Handelstag), Score-Bucket-Verteilung **40–49: 20 · 50–59:
109 · 60–69: 162 · ≥70: 181** (keine Zeile < 40). Diese 472 Zeilen sind
**explorativ** (Panel- und Dossier-Auswertungen haben Teile davon gesehen,
siehe Hintergrund-Zählung des Auftrags) und gehen **nie** in den
bestätigenden Test unten ein — sie dienen hier nur der Lage-Einordnung
(Takt, Bucket-Verteilung), exakt wie die 242 In-Sample-Records im
§4-Block oben nie ins dortige n einfließen.

**EINGEFRORENE VORGABEN**

1. **Frage:** Trennt der Setup-Score (Feld `score`, wie im §4 verwendet)
   Aktien mit gutem von schlechtem Forward-Ergebnis innerhalb der
   ausgewählten Top-10-Population?
2. **Population (bestätigend):** `provenance=="forward"` **UND**
   Eintrittsdatum strikt **NACH** dem Merge-Tag dieses PRs (ET-Datum des
   Merges, vom Code eingetragen, **„Freeze-Datum"**); alle Scores; gezählt
   allein aus `matured_backtest_export.jsonl`; Backfill nie. Die 472 Zeilen
   oben (vor dem Freeze) sind explorativ und werden nie eingerechnet.
   **Freeze-Datum = 10.10.2026** (ET-Kalendertag, America/New_York) — gesetzt
   unter der Annahme, dass Branch-Erstellung, Guardian-Lauf und Merge dieses
   PR im selben Arbeitsgang noch am 10.10.2026 ET abschließen (bei
   Autorierung dieses Textes: 16:17 EDT, deutlicher Abstand zur ET-Mitternacht).
   **Sicherheitsklausel:** Weicht der tatsächliche Merge-Zeitpunkt (ET-Datum
   des Merge-Commits laut GitHub) von diesem Datum ab, ist das **nach dem
   Änderungs-Protokoll unten zu korrigieren** (datierter Protokolleintrag,
   Text nicht stillschweigend überschrieben) — analog zur §4-Disziplin oben.
   Das Datumsformat ist durchgehend `DD.MM.YYYY`, identisch zum `date`-Feld
   in `matured_backtest_export.jsonl` (= ET-Handelstag, siehe
   `generate_report.py:_marktdaten_timestamp`-Docstring, Zeilen ~7611–7613:
   „`report_date` = `%d.%m.%Y` in America/New_York") — Vergleich
   „Eintrittsdatum > Freeze-Datum" ist damit ein reiner String-/Datums-
   Vergleich zweier bereits-ET-Werte im selben Format, **keine**
   UTC/ET-Konvertierung zur Auswertungszeit nötig.
3. **Zielgrößen, Holm k=2** (Verfahren wie §4: `mann_whitney_u_auc`,
   `scripts/stats_helpers.py:60`, + `multiple_testing_correction`,
   `scripts/stats_helpers.py:152`):
   (a) Trennschärfe (AUC) des Scores für **„return_5d ≥ +5 %"**
       (Trefferdefinition aus Dossier §6);
   (b) Trennschärfe des Scores für **„return_10d > 0"**.
4. **Auslöser:** `n ≥ 250` bestätigende Zeilen mit `return_5d` **und**
   `return_10d` gefüllt. **Kein Kalenderdatum.** **Keine Zwischenauswertung**
   der Outcomes vor Erreichen von n=250.
5. **Erfolgskriterium — ALLE vier Bedingungen:**
   (i) Holm-signifikant;
   (ii) untere Grenze des Bootstrap-Intervalls (N=2000, fester Seed, wie §4)
        über 0,5;
   (iii) Cluster-Doppellauf (mit und ohne detektierbare Cluster, wie §4 —
        `scripts/cluster_purge.py`, `classify_cluster_records`) liefert
        dieselbe Richtung;
   (iv) Punktschätzung ≥ **0,55**.
   Eine Punktschätzung allein ist **nie** ein Beleg. **Die Schwelle 0,55 ist
   eine Festlegung von Easy, kein Naturwert** — anders als bei §4 (dort reicht
   „CI schließt 0,5 aus"), weil Easy hier zusätzlich eine Mindest-Praxisrelevanz
   verlangt, keine bloße statistische Signifikanz.
6. **Bindend ist brutto** (`return_5d` / `return_10d`). Netto (`_net`) und
   SPY-bereinigt (`_vs_spy`) sowie Regime-Split (`market_regime`,
   `vix_level`) werden **zusätzlich und nachrangig** ausgewiesen — niemals
   Ersatz für das bindende Brutto-Kriterium (identische Bindungs-Logik wie
   im §4-Protokolleintrag 18.09.2026 oben).
7. **Erwartung (Schätzung, kein Termin):** ~10 Zeilen pro Handelstag plus
   ca. zwei Wochen Reifezeit → n=250 grob **Anfang Dezember 2026**. Diese
   Zeile ist **nicht bindend** — bei Erreichen wird die tatsächliche Rate
   gezählt und **nur diese Schätzzeile** angepasst (analog §4: „Projektion
   ~Mitte November 2026, unsicher, kein Termin").
8. **Grenzen — offen benannt:**
   (a) **Range-Restriktion:** Der Score wird nur innerhalb der Top-10-Auswahl
       geprüft, nicht gegen das gesamte Universum (keine Zeile < 40 in der
       Hintergrund-Zählung). Ein Ergebnis gilt nur für diese Auswahl.
   (b) Bei n≈250 sind nur **deutliche** Trennschärfen erkennbar; ein
       schwacher Effekt bleibt „unklar" und gilt **nicht** als Beleg für
       „keine Edge".
   (c) **Score-Änderungen während des Tests:** Jede Änderung an `score()`
       oder an der Top-10-Auswahl vor der Auswertung braucht einen Eintrag
       hier (Datum, PR) und ist im Bericht auszuweisen; sie macht den Test
       **nicht** still ungültig, aber **sichtbar**. (SCHRITT-0-Grep-Befund:
       es existiert **kein** automatischer Score-Formel-Änderungs-Detektor
       — `SCORE_NORMALIZATION_VERSION`, `config.py:473`, ist ein **manueller,
       eng gefasster** Marker nur für die RVOL-Normalisierungs-Welle [γ-1/γ-2],
       persistiert als `score_normalization_version` pro Record,
       `backtest_history.py:1404`; `backtest_schema_version` [config.py,
       `backtest_history.py:1062`, ==4] ist eine Schema-**Form**-Version,
       keine Formel-Version. Health-Check S13b [`CONSISTENCY_EXPECTED_STATE`,
       `config.py:495-499`] überwacht nur drei benannte Konstanten
       [`RVOL_NORMALIZATION_ENABLED`, `SCORE_NORMALIZATION_VERSION`,
       `EARLINESS_FORMULA_VERSION`] auf Soll-Ist-Drift, als `warn` — **keine**
       generische Erkennung für Änderungen an `COMBO_BONUS`, einem
       `SUB_*_DISPLAY_PTS_MAX`-Wert oder einer Filter-Schwelle. Ein
       Score-Änderungs-Eintrag hier bleibt deshalb **manuelle Disziplin**,
       nicht automatisch erzwingbar.)
   (d) Das Backtest-Panel zeigt weiter Trefferquoten nach Score; sie sind
       **keine** Evidenz für diesen Test.
9. **Abhängigkeit — `_detect_recent_squeeze`-Fix** (`open_items.json`,
   ID `pr532-or0-sibling-bugs`, bewusst bis n=250 im §4-Re-Test
   zurückgestellt — siehe dortiger Eintrag „ERGÄNZUNG 08.10.2026"): der Fix
   ist eine Score-Änderung im Sinne von Punkt 8c. **Zwei Optionen, keine
   Vorentscheidung hier:**
   - **Option A:** Der Fix wird erst **nach Auswertung BEIDER Tests**
     (§4 Exit-B.1 UND dieser Setup-Edge-Re-Test) umgesetzt — verlängert die
     störungsfreie Sammelphase für beide Registrierungen gleichzeitig,
     verzögert aber eine bekannte Malus-Korrektur zusätzlich.
   - **Option B:** Der Fix wird vor Erreichen von n=250 umgesetzt und als
     Eintrag nach Punkt 8c ausgewiesen (Datum, PR, Vorher/Nachher-Vergleich)
     — der Malus wirkt nur verschärfend (nie score-erhöhend), betrifft also
     nur, ob knapp-über-70-Records nachträglich unter die Schwelle fallen;
     der Bruch wird sichtbar dokumentiert statt verzögert.
   **Easy entscheidet.** Der bestehende `open_items.json`-Eintrag verknüpft
   den Fix heute nur mit §4, nicht mit diesem neuen Test — diese Lücke wird
   mit dem SCHRITT-2-Eintrag unten geschlossen.

   **ERRATUM 11.10.2026 — Easy-Entscheidung zu Punkt 9: Option A.** Der
   `_detect_recent_squeeze`-Fix (`open_items.json`, ID
   `pr532-or0-sibling-bugs`) wird **erst nach Auswertung BEIDER Tests**
   (§4 Exit-B.1 **und** dieser Setup-Edge-Re-Test, inklusive des
   Conviction-Zusatznutzen-Erratums „Test c" weiter unten) umgesetzt —
   nicht früher. Option B ist damit entfallen. Diese Entscheidung gilt
   zugleich für den gleichlautenden, noch offenen Punkt 9 der „EINGEFRORENEN
   ERGÄNZUNG" (Conviction-Zusatznutzen-Erratum) weiter unten — dort war
   ebenfalls „keine Vorentscheidung" vermerkt; dieses Erratum löst beide
   Stellen einheitlich auf, ohne deren Text zu ändern. Der Text von Punkt 9
   selbst bleibt oben unverändert stehen (reine Ergänzung, keine Streichung).

**Änderungs-Protokoll (bindend ab Freeze-Datum, analog §4):** Keine Änderung
an diesem Block ohne datierten Protokolleintrag, der die Änderung und ihren
Grund festhält.

**ERRATUM 10.10.2026 — Erweiterung vor Auswertung (Test c, Conviction-Zusatznutzen).**
Grund: Easy-Entscheidung — Conviction wird im selben Freeze mit-registriert,
damit die Frage „bringt Conviction gegenüber dem Score selbst etwas?" nicht
später separat und außerhalb der Freeze-Disziplin aufgesetzt werden muss.
**Ausdrücklich festgehalten: Zum Zeitpunkt dieses Erratums wurden KEINE
Outcomes der bestätigenden Population (Tests a/b/c) ausgewertet** — seit dem
Freeze-Merge (`328b3fc4`, PR #584, 10.10.2026) ist kein einziger weiterer
Commit auf `main` gelandet (git-belegt), also erst recht keine Auswertung.
Dieses Erratum ändert **keinen bestehenden Satz** des obigen Freeze-Blocks —
reine Ergänzung.

**EINGEFRORENE ERGÄNZUNG**

1. **Frage (c):** Trennt der Conviction-Score (Feld `conviction_score`)
   Aktien mit gutem von schlechtem Forward-Ergebnis **besser** als der
   Setup-Score allein?
2. **Population:** wie im Freeze oben (`provenance=="forward"`,
   Eintrittsdatum strikt nach dem Freeze-Datum, alle Scores, nur aus
   `matured_backtest_export.jsonl`, Backfill nie), **zusätzlich** nur Zeilen
   unter `EARLINESS_FORMULA_VERSION 2`. **V2-Umstellung: 14.05.2026, PR #141
   (Merge `ab3041b1`), Feat-Commit `fa8d87f0` („feat: Earliness V2 —
   DTC-Niveau-Basis")** — Skala `EARLINESS_PTS_MAX` wechselte dort von **7
   (V1) auf 100 (V2)**, git-belegt (`git show fa8d87f0^:config.py` vs.
   `git show fa8d87f0:config.py`). Seither **nie** zurückgesetzt oder erneut
   geändert (einziger Setz-Zeitpunkt im gesamten `config.py`-Verlauf,
   `git log -p -S EARLINESS_FORMULA_VERSION` zeigt genau einen Treffer).
   Da die früheste Forward-Zeile der bestehenden Population am 21.07.2026
   liegt — rund 10 Wochen nach der V2-Umstellung — sind **alle** Zeilen ab
   Freeze-Datum automatisch unter V2 entstanden; die Versions-Filterung ist
   damit für die heutige Datenlage ein No-op, bleibt aber als
   Zukunftssicherung in der Population-Definition (falls der Export je
   rückwirkend ältere Zeilen aufnehmen sollte — laut Freeze-Text oben nie
   vorgesehen). Ältere Zeilen (vor 14.05.2026, V1-Skala) werden **nie**
   eingerechnet, auch nicht hypothetisch.
3. **Zielgröße (c):** ΔAUC = AUC(`conviction_score`) − AUC(`score`) für
   „`return_5d ≥ +5 %`" auf **denselben** Zeilen (gepaarter Bootstrap,
   N=2000, fester Seed wie im Freeze oben). Verfahren: `mann_whitney_u_auc`
   (`scripts/stats_helpers.py:60`) liefert je Resample die Einzel-AUC für
   `conviction_score` und für `score`; die Differenz wird je Resample
   gebildet, die Verteilung der Differenzen über N=2000 Resamples ergibt das
   CI. **Fundstellen-Prüfung (Exzellenz-Punkt 4):** ein fertiger,
   **gepaarter** Bootstrap für eine AUC-Differenz existiert im Repo
   **nicht** — `bootstrap_mean_ci` (`scripts/expectancy_diagnose.py`) ist
   ein **einfacher** Mittelwert-Bootstrap für eine einzelne Werteliste,
   kein Differenz-von-zwei-AUCs-Bootstrap. **Wird hier nicht gebaut**
   (Auftrag: nur Doku). Benötigt bei Auswertung: eine neue
   Auswertungsfunktion, die (a) pro Resample denselben Zeilen-Index
   resampled (damit `conviction_score` und `score` auf identischen Zeilen
   verglichen werden — „gepaart"), (b) auf diesem Resample zweimal
   `mann_whitney_u_auc` aufruft (Gewinner- vs. Verlierer-Split nach
   `return_5d≥+5%`, einmal mit `conviction_score`-Werten, einmal mit
   `score`-Werten) und (c) die Differenz der beiden AUCs sammelt — analog
   zum bestehenden `bootstrap_mean_ci`-Muster, aber auf Paaren statt auf
   einer einzelnen Liste. Existiert erst zur Auswertungszeit (nach
   Erreichen von n≥250), nicht heute.
4. **Holm:** Die Familie wird von **k=2** (Tests a, b aus dem Freeze oben)
   auf **k=3** (Tests a, b, c) erweitert — vor jeder Auswertung
   beschlossen, damit zulässig (`multiple_testing_correction`,
   `scripts/stats_helpers.py:152`, akzeptiert jede Familiengröße generisch,
   keine Code-Änderung nötig). Der Auslöser **n ≥ 250 bestätigende Zeilen
   bleibt unverändert und gemeinsam** für alle drei Tests; **keine
   Zwischenauswertung**.
5. **Erfolgskriterium (c) — ALLE vier Bedingungen:**
   (i) Holm-signifikant (k=3);
   (ii) untere Grenze des gepaarten Bootstrap-Intervalls für ΔAUC über 0;
   (iii) Cluster-Doppellauf (mit und ohne detektierbare Cluster — wie Freeze
        oben, `scripts/cluster_purge.py`, `classify_cluster_records`)
        liefert dieselbe Richtung;
   (iv) Punktschätzung ΔAUC ≥ **+0,02** **UND** AUC(`conviction_score`)
        selbst ≥ **0,55**.
   Beide Schwellen (+0,02 und 0,55) sind **Festlegungen von Easy, keine
   Naturwerte**. Eine Punktschätzung allein ist **nie** ein Beleg.
6. **Brutto bindend**; netto (`_net`), SPY-bereinigt (`_vs_spy`) und
   Regime-Split (`market_regime`, `vix_level`) **nachrangig**, identisch zur
   Bindungslogik im Freeze oben (§4-Protokolleintrag 18.09.2026).
7. **Grenzen — offen benannt:**
   (a) Conviction enthält den Score zu 33 % (`setup`-Komponente, Cap 33 von
       100, `CLAUDE.md:791`/`generate_report.py:7169-7172`) — ΔAUC misst nur
       den **Zusatznutzen** der restlichen 67 % (Earliness 28, Anomaly 28,
       Regime 11), nicht Conviction „von Grund auf".
   (b) Range-Restriktion wie im Freeze oben — nur Top-10-Auswahl, nicht
       gegen das Gesamtuniversum.
   (c) Bei n≈250 ist ein **kleiner** Zusatznutzen nicht erkennbar; „kein
       Beleg" heißt dann **„unklar"**, nicht „keine Edge".
   (d) Änderung der Conviction-Gewichte (33/28/28/11,
       `CLAUDE.md:791-794`/`generate_report.py:7169-7214`), der
       Earliness-Formel-Version oder der Komponenten **nach** diesem
       Erratum: Eintrag mit Datum und PR hier erforderlich; die betroffenen
       Zeilen werden im Doppellauf **mit und ohne** diese Zeilen ausgewiesen
       (analog Punkt 8c im Freeze oben). Git-Historie bislang (geprüft
       10.10.2026): **keine** einzige Änderung an 33/28/28/11 seit
       Einführung (`git log -p --all -S` auf die jeweiligen Code-Literale
       `min(33,`/`min(28,`/`= 28`/`= 11` in `compute_conviction_score`
       liefert je genau einen Treffer — die Einführung selbst, keine
       spätere Änderung).
   (e) Der Push-Schwellenwert `ANOMALY_CONVICTION_MIN_THRESHOLD = 75` ist
       **keine** Evidenz für diesen Test — reine Produktions-Steuerung.
8. Der alte Kalenderpunkt **„Conviction-Edge (P3)"** (Re-Test-Kalender-
   Tabelle oben, Zeile „~Ende Juli / Anfang Aug") ist mit diesem Erratum
   **als ERSETZT markiert** (Verweis auf diesen Abschnitt eingetragen) —
   **nicht gelöscht**, bleibt als Historie stehen.
9. **Abhängigkeit `_detect_recent_squeeze`** (siehe Freeze-Punkt 9 oben,
   `open_items.json`-ID `pr532-or0-sibling-bugs`): der Fix wirkt über die
   Setup-Komponente (33 % Gewicht) **auch** auf `conviction_score`, nicht
   nur auf `score` — betrifft also **beide** Größen dieses erweiterten
   Freezes gleichermaßen. Die zwei Optionen aus Freeze-Punkt 9 (A: Fix
   nach Auswertung BEIDER/ALLER Tests; B: Fix vor n=250 mit explizitem
   8d-Eintrag hier) gelten unverändert, jetzt für drei statt zwei Tests.
   Keine Vorentscheidung.

   **ERRATUM 11.10.2026 — siehe Freeze-Punkt 9 oben.** Easy hat sich für
   Option A entschieden (Fix erst nach Auswertung ALLER drei Tests,
   inklusive dieses Conviction-Zusatznutzen-Tests). Siehe dortigen
   ERRATUM-Vermerk für den vollen Wortlaut — hier nur Querverweis, kein
   doppelter Text.
10. **Erwartung (Schätzung, kein Termin):** wie im Freeze oben. Die
    tatsächliche Rate wird gezählt (Zeilen pro Handelstag **unter V2** —
    nach Punkt 2 heute ohnehin 100 % der Population), nur die Schätzzeile
    wird bei Erreichen angepasst.

**Änderungs-Protokoll gilt identisch für dieses Erratum** (analog Freeze
oben): keine weitere Änderung ohne datierten Protokolleintrag.

### VORABREGISTRIERUNG — KI-Score-Edge-Test (ki_signal_score), eingefroren 13.10.2026

**Verhältnis zum Setup-Edge-Re-Test oben.** Dieser Block prüft eine **andere
Größe** (`ki_signal_score` statt `score`), ist aber **strukturell identisch**
aufgebaut — Definitionen, Metriken, Bootstrap-Verfahren und
Erfolgskriterien sind bewusst 1:1 vom Setup-Edge-Re-Test-Freeze oben
übernommen, **nicht neu erfunden**, damit beide Registrierungen
vergleichbar bleiben. Am Setup-Edge-Re-Test-Freeze (inkl. beider dortiger
Errata) ändert dieser Block **nichts**.

**Auslöser für diese Registrierung:** der KI-Score-Coverage-Fix (PR #587,
Variante A, Merge 11.10.2026) ist aktiv — Beleg: alle 10 Zeilen des
Postclose-Laufs vom 12.10.2026 tragen `ki_signal_score` **und**
`ki_signal_ts` (vorher 3–4 von 10, ohne Zeitstempel). Easy will wissen, ab
wann feststeht, ob der KI-Score gute von schlechten Aktien trennt — dieser
Test wird deshalb **vorab** festgeschrieben, bevor ein Ergebnis existiert.

**Datenquelle & n-Definition — identisch zu §4/Setup-Edge.** Gezählt wird
ausschließlich aus `matured_backtest_export.jsonl` (append-only,
prune-immun) — **nicht** aus `backtest_history.json`
(90-Tage-Prune `BACKTEST_MAX_DAYS=90`). **SCHRITT-0-Zählung per 13.10.2026
(keine Outcome-Werte enthalten):** `ki_signal_ts` existiert in **0** von
1177 Export-Zeilen (0 × `ki_signal_score`-mit-Zeitstempel, davon
unabhängig 744 Zeilen mit dem älteren, timestamp-losen
`ki_signal_score`-Feld und 512 mit `ki_sentiment_source` — beide **nicht**
Teil dieser Population, siehe Punkt 2). Grund: das Reife-Gate
(`return_10d` gefüllt **und** `days_old > 14` Kalendertage,
`matured_export.py:160–171`) lässt die ersten 10 Zeilen mit
`ki_signal_ts` (alle Einstiegsdatum 12.10.2026, in
`backtest_history.json` bestätigt, `return_5d`/`return_10d` dort aktuell
**0 von 10** gefüllt) frühestens **ca. 27.10.2026** ins Export-File
einlaufen (12.10. + 14 Kalendertage + nächster Daily-Run-Export-Pass).
Das Feld läuft **ohne Whitelist** durch `matured_export.py` (voller
Pass-Through, kein Feld-Filter) — **keine Export-Schema-Änderung nötig**,
reine Zeitfrage.

**EINGEFRORENE VORGABEN**

1. **Frage:** Trennt der KI-Score (Feld `ki_signal_score`) Aktien mit
   gutem von schlechtem Forward-Ergebnis innerhalb der ausgewählten
   Top-10-Population?
2. **Population (bestätigend):** `provenance=="forward"` **UND**
   `ki_signal_ts` **vorhanden** (Schlüssel-Präsenz-Prüfung, analog
   `health_check._freeze_ki_coverage_last_report_day`, nicht `.get(...)
   is not None` — Zeilen mit `ki_signal_score` **ohne** Zeitstempel sind
   **ausgeschlossen**, das sind Altwerte aus dem früheren
   `agent_signals`-Pfad vor dem Coverage-Fix) **UND** Eintrittsdatum
   `>= 12.10.2026` (erster Tag mit Fresh-KI-Berechnung, siehe
   SCHRITT-0-Zählung oben); alle Scores; gezählt allein aus
   `matured_backtest_export.jsonl`; Backfill nie. **Abweichung vom
   Setup-Edge-Vorbild bewusst dokumentiert:** dort ist die Datumsschranke
   „strikt NACH dem Merge-Tag" (ausschließend), hier `>= 12.10.2026`
   (einschließend) — weil die Populationsgrenze hier **datengetrieben**
   ist (erster Tag mit der neuen Berechnung) statt PR-merge-getrieben;
   das Freeze-Datum dieses Blocks (13.10.2026) liegt ohnehin einen Tag
   nach 12.10.2026, es wird also **kein** Tag vor der eigentlichen
   Fix-Aktivierung eingerechnet. **Grenzfall, noch nicht beobachtet:**
   `ki_signal_ts` kann laut Code (`backtest_history.py:904-912`) **auch
   dann** gesetzt sein, wenn der Fresh-Versuch für den Ticker fehlschlug
   (`ki_signal_score=None`, „versucht, aber kein Wert" statt stillem
   Weglassen) — eine solche Zeile zählt nach dieser Definition zur
   Population (`n`), liefert aber **keinen** auswertbaren AUC-Datenpunkt
   für diesen Ticker. Keine Vorentscheidung hier, ob solche Zeilen aus
   `n` herausgerechnet oder nur aus der eigentlichen AUC-Berechnung
   ausgeschlossen werden — das entscheidet sich **zur Auswertungszeit**
   anhand der dann tatsächlich beobachteten Häufigkeit. **Entschieden
   16.10.2026, siehe Erratum unten** (dieser Satz bleibt zur
   Nachvollziehbarkeit stehen, keine Streichung).
3. **Zielgrößen, Holm k=2** (Verfahren wie §4/Setup-Edge:
   `mann_whitney_u_auc`, `scripts/stats_helpers.py:60`, +
   `multiple_testing_correction`, `scripts/stats_helpers.py:152`):
   (a) Trennschärfe (AUC) des KI-Scores für **„return_5d ≥ +5 %"**;
   (b) Trennschärfe des KI-Scores für **„return_10d > 0"**.
4. **Eigene Holm-Familie (k=2), NICHT mit der Setup/Conviction-Familie
   (k=3) zusammengelegt.** Begründung: beide Testfamilien wurden
   **getrennt gestartet und getrennt formuliert** — der Setup/Conviction-
   Freeze (10.10.2026) prüft den Setup-Score und dessen
   Conviction-Zusatznutzen, dieser Block prüft eine **andere, erst seit
   12.10.2026 überhaupt belastbar vorliegende** Größe
   (`ki_signal_score`) mit **eigenem** Reifefenster. Eine nachträgliche
   Zusammenlegung in eine gemeinsame Familie wäre selbst eine Änderung
   am bereits eingefrorenen Setup/Conviction-Block — genau das, was
   dessen Änderungs-Protokoll verbietet. **Nachteil, offen benannt:**
   insgesamt laufen damit **5 Tests** (a, b, c aus dem Setup/Conviction-
   Freeze + a, b hier) **ohne gemeinsame Korrektur** über alle fünf —
   die tatsächliche Familienweise-Fehlerrate liegt höher als die pro
   Familie ausgewiesenen 0,05. Akzeptiert, weil beide Familien
   inhaltlich unabhängige Hypothesen sind (verschiedene Scores,
   verschiedene Datenfenster) und eine künstliche Zusammenlegung über
   zwei bereits-eingefrorene Blöcke hinweg mehr Komplexität als Nutzen
   brächte.
5. **Auslöser:** `n ≥ 250` bestätigende Zeilen dieser Population mit
   `return_5d` **und** `return_10d` gefüllt. **Kein Kalenderdatum.**
   **Keine Zwischenauswertung** der Outcomes vor Erreichen von n=250.
6. **Erfolgskriterium — ALLE vier Bedingungen:**
   (i) Holm-signifikant (eigene Familie k=2);
   (ii) untere Grenze des Bootstrap-Intervalls (N=2000, fester Seed,
        `bootstrap_mean_ci`-Muster, beim Endlauf) über 0,5;
   (iii) Cluster-Doppellauf (mit und ohne detektierbare Cluster,
        `scripts/cluster_purge.py`, `classify_cluster_records`) liefert
        dieselbe Richtung;
   (iv) Punktschätzung ≥ **0,55**.
   Eine Punktschätzung allein ist **nie** ein Beleg. Die Schwelle 0,55
   ist identisch zur Setup-Edge-Schwelle — eine Festlegung von Easy,
   kein Naturwert.
7. **Bindend ist brutto** (`return_5d`/`return_10d`). Netto (`_net`) und
   SPY-bereinigt (`_vs_spy`) sowie Regime-Split (`market_regime`,
   `vix_level`) werden **zusätzlich und nachrangig** ausgewiesen —
   niemals Ersatz für das bindende Brutto-Kriterium (identische
   Bindungs-Logik wie im Setup-Edge-Block oben).
8. **Nicht-konfirmatorischer Kontext (deskriptiv, KEIN eigener Test,
   keine Entscheidungsgrundlage):** Aufteilung nach
   `ki_sentiment_source` (`llm` vs. `keyword`) — zeigt nur, ob die
   beiden Quellen unterschiedlich aussehen, begründet **keine**
   gesonderte Schlussfolgerung und fließt **nicht** in Holm/
   Erfolgskriterium ein.
9. **Zeitverzug — ausdrücklich OHNE Terminschätzung** (Abweichung vom
   Setup-Edge-Vorbild, das eine grobe Schätzung „Anfang Dezember 2026"
   nennt — hier bewusst **nicht**, weil die erste Datenlage noch
   fehlt): erste Zeilen dieser Population laufen frühestens ca.
   **27.10.2026** ins Export-File ein (Reife-Gate, 14 Kalendertage ab
   12.10.2026). Der Auswertungstermin selbst ist **offen, erst
   berechnen, wenn die Rate im Digest sichtbar ist (ab ca. 27.10.)** —
   keine Rate-Schätzung vor dem ersten echten Datenpunkt.
10. **Grenzen — offen benannt:**
    (a) **Range-Restriktion:** wie im Setup-Edge-Block — der KI-Score
        wird nur innerhalb der Top-10-Auswahl geprüft, nicht gegen das
        gesamte Universum.
    (b) Bei n≈250 sind nur **deutliche** Trennschärfen erkennbar; ein
        schwacher Effekt bleibt „unklar" und gilt **nicht** als Beleg
        für „keine Edge".
    (c) **Same-Day-Look-ahead möglich:** der Fresh-KI-Wert wird im
        selben Postclose-Lauf mit Nachrichten **bis zur Laufzeit**
        berechnet (`_compute_fresh_ki_signals_for_backtest`,
        `generate_report.py:4515`) — der Wert kann also Information
        tragen, die zum offiziellen Entry-Zeitpunkt (regulärer
        Schlusskurs) noch nicht öffentlich/verarbeitet war. Keine
        Quantifizierung dieses Effekts, nur offen benannt.
    (d) **Fresh-Wert ohne RVOL-Velocity-Bonus:** der synchron berechnete
        Fresh-Wert deckt nicht exakt denselben Berechnungspfad wie der
        reguläre stündliche `ki_agent`-Tick ab (siehe bestehender
        KI-Coverage-Diagnose-Eintrag, Guardian-Finding 11.10.2026 zu
        PR #587) — ein Ergebnis gilt **nur für diesen Rechenweg**, nicht
        für `ki_signal_score` im Allgemeinen.
    (e) **Score-Änderungen während des Tests (Regel 8c-Erweiterung,
        analog Setup-Edge-Punkt 8c):** jede Änderung an
        `_compute_fresh_ki_signals_for_backtest`
        (`generate_report.py:4515`), an `FRESH_KI_SIGNAL_ENABLED`
        (`config.py:189`), am Haiku-Modell, am Prompt oder am Cap der
        News-Komponente ist im **Block 1 zu loggen** (Datum, PR) und
        führt zu einem **Erratum mit Neustart-Bewertung der
        Population** — analog zur Setup-Edge-Disziplin, macht den
        bisherigen Test nicht still ungültig, aber sichtbar. Es
        existiert **kein** automatischer Detektor für diese Änderungen
        (identischer SCHRITT-0-Befund wie beim Setup-Edge-Block, Punkt
        8c dort) — manuelle Disziplin.
    (f) Das Backtest-Panel zeigt weiter Trefferquoten nach Score; sie
        sind **keine** Evidenz für diesen Test.
11. **Offener Folgeauftrag (kein Termin, Easy entscheidet den
    Zeitpunkt):** ab ca. 27.–28.10.2026 prüfen, ob die ersten Zeilen mit
    `ki_signal_ts` im Export (`matured_backtest_export.jsonl`)
    angekommen sind (reine Zählung, siehe Punkt 9). Sobald das der Fall
    ist: Digest-Zeile **„KI n = X/250"** in der bestehenden
    „🧪 Freeze-Zähler"-Zeile (`health_check.py`, PR #588) ergänzen —
    display-only, fail-soft, **dieselben Zählhelfer wiederverwenden**
    wie die bestehende Setup/Conviction-Freeze-Zeile (kein zweiter
    Zählweg). Dieser PR baut **nur die Doku**, kein Digest-Code.

**Änderungs-Protokoll (bindend ab Freeze-Datum, analog §4/Setup-Edge):**
Keine Änderung an diesem Block ohne datierten Protokolleintrag, der die
Änderung und ihren Grund festhält.

**ERRATUM 16.10.2026 — Randfall „ki_signal_ts ohne verwertbaren
ki_signal_score" (Punkt 2 oben) entschieden.** Grund: Easy-Entscheidung
16.10.2026. **Ausdrücklich festgehalten: Zum Zeitpunkt dieses Erratums
wurden KEINE Outcomes der Population ausgewertet** — SCHRITT-0-Zählung
16.10.2026 (reine Zählung, keine Returns angesehen): 40 Zeilen in
`backtest_history.json` tragen `ki_signal_ts` (10 pro Tag für
12./13./14./15.10.2026, 16.10. hat beim Zähl-Zeitpunkt noch keinen
Postclose-Eintrag), **0 von 40** mit nicht-verwertbarem
`ki_signal_score` (None/nicht-numerisch/nicht-endlich — alle 40 bislang
numerisch und endlich), **0 von 40** mit `return_5d` oder `return_10d`
gefüllt. Dieses Erratum ändert **keinen bestehenden Satz** der obigen
„EINGEFRORENEN VORGABEN" — reine Ergänzung, Punkt 2 bleibt oben
unverändert stehen (nur um den Verweis-Satz „Entschieden 16.10.2026,
siehe Erratum unten" ergänzt, siehe dort).

**Population — präzisiert (ersetzt NICHT Punkt 2, konkretisiert ihn):**
`provenance=="forward"` **UND** `ki_signal_ts` vorhanden **UND**
`ki_signal_score` numerisch und endlich (nicht `None`, kein `NaN`/`Inf`,
kein `bool`) **UND** Eintrittsdatum `>= 12.10.2026`, ausschließlich aus
`matured_backtest_export.jsonl`, Backfill nie. **Nur diese Zeilen zählen
zu `n` und zur AUC-Berechnung.**

**Entscheidung — Zeilen ohne verwertbaren Wert werden NICHT gezählt.**
Zeilen mit `ki_signal_ts` vorhanden, aber ohne verwertbaren
`ki_signal_score` (fehlgeschlagene Fresh-Berechnung — „versucht, aber
kein Wert", siehe Punkt 2) sind von der Population **ausgeschlossen**.
Sie werden bei der Auswertung **nur als Zahl berichtet** („x Zeilen
ausgeschlossen, Anteil y %"), **nie getestet**.

**Begründung.** Die Zuordnung „gehört diese Zeile zur Population" hängt
**allein vom Einstiegstag und der Datenverfügbarkeit zum Freeze-Zeitpunkt
der Zeile ab** (hat `ki_signal_ts`, hat `ki_signal_score`), **nicht vom
späteren Forward-Ergebnis** — deshalb entsteht durch den Ausschluss
**kein Ergebnis-Bias** (kein Cherry-Picking nach Outcome). Zeilen ohne
Score liefern schlicht **keinen** AUC-Datenpunkt — sie könnten technisch
nicht getestet werden, selbst wenn man sie in `n` beließe.

**Einschränkung — ausdrücklich benannt.** Fehlt der KI-Wert **systematisch**
bei bestimmten Aktientypen (z. B. Tickers ohne verarbeitbare
Nachrichtenlage, Claude-Haiku-Timeout/Rate-Limit-Muster, siehe
`claude_sentiment_score`-Fail-Soft-Pfad), gilt ein späteres Ergebnis
**nur für die Teilmenge mit verwertbarem Wert**, nicht für alle Aktien
der ursprünglichen Top-10-Auswahl. Der Ausschlussanteil (`x Zeilen
ausgeschlossen, Anteil y %`) ist **mit jeder Auswertung zu nennen**;
liegt er **über 20 %**, ist das in der Bewertung **als Einschränkung
hervorzuheben** — **kein Abbruchkriterium**, der Test läuft trotzdem.

**Folgeauftrag-Präzisierung (Punkt 11 oben, additiv — Punkt 11 selbst
bleibt unverändert stehen):** Die geplante Digest-Zeile „KI n = X/250"
(Wiedervorlage 28.10.2026) muss **exakt diese präzisierte Population**
zählen (`ki_signal_ts` vorhanden **UND** `ki_signal_score` numerisch/
endlich **UND** Eintrittsdatum ≥ 12.10.2026) — **nicht** nur
`ki_signal_ts`-Präsenz allein, sonst würde der Zähler Zeilen ohne
verwertbaren Wert mitzählen, die laut dieser Entscheidung nie zu `n`
gehören.

**Widerspruchs-Check (Exzellenz-Punkt 2):** Kein kollidierender Satz an
anderer Stelle im Freeze-Block gefunden — Punkt 5 („Auslöser: n≥250
bestätigende Zeilen **dieser Population**") verweist bereits generisch
auf „diese Population" und wird durch diese Präzisierung automatisch
konsistent, ohne eigene Änderung zu brauchen. Die „Datenquelle &
n-Definition"-Absatz oben (vor den EINGEFRORENEN VORGABEN) beschreibt nur
die Dateiquelle, trifft keine score-bezogene Aussage — keine Kollision.

**Änderungs-Protokoll gilt identisch für dieses Erratum** (analog
Setup-Edge/§4): keine weitere Änderung ohne datierten Protokolleintrag.

### ERRATUM 22.10.2026 — Bootstrap-Verfahrensdetails für beide Edge-Test-Freezes (Setup-Edge/Conviction UND KI-Score)

**Grund.** Eine read-only SCHRITT-0-Diagnose (22.10.2026, Vorbereitung des
automatischen Auswertungs-Auslösers "Auswertung startet bei n=250 von
selbst") fand drei Lücken im Bootstrap-Verfahren beider oben stehender
Freeze-Blöcke, zitiert aus den Blöcken selbst:

1. **Kein numerischer Seed.** Setup-Edge/Conviction-Freeze, Punkt 5(ii):
   *„...N=2000, fester Seed, wie §4) über 0,5"*. KI-Score-Freeze, Punkt
   6(ii): *„...N=2000, fester Seed, `bootstrap_mean_ci`-Muster, beim
   Endlauf) über 0,5"*. Beide verweisen zirkulär (auf §4 bzw. ein
   Code-Muster) — **keine Zahl** steht in irgendeinem der beiden Blöcke
   oder im §4-Block selbst. Repo-weite Prüfung: der einzige numerische
   Seed ist `RNG_SEED=42` in `scripts/expectancy_diagnose.py` — eine
   **andere, bereits abgeschlossene** Auswertung (Paper-C-Hypothesen),
   von keinem der beiden Freezes namentlich referenziert.
2. **Kein CI-Perzentil.** „Bootstrap-Intervall"/„Bootstrap-CI" wird in
   keinem der beiden Blöcke auf eine konkrete Methode (95%/90%,
   ein-/zweiseitig, Perzentil-Methode) festgelegt.
3. **Keine Ausschluss-Regel für fehlenden `conviction_score` in Test c.**
   Der KI-Score-Freeze regelt den Fall „Wert fehlt/unbrauchbar" explizit
   (Erratum 16.10.2026, „Population — präzisiert"). Der Conviction-
   Erratum (10.10.2026, Test c) tut das nicht — Punkt 7 „Grenzen — offen
   benannt" (a)–(e) nennt diesen Fall nirgends. `conviction_score` kann
   aber `None` sein (`backtest_history.py:936-939`, wenn
   `apply_conviction_scores` keinen Wert liefert).

**Ausdrücklich festgehalten: Zum Zeitpunkt dieses Erratums wurden KEINE
Outcomes (`return_*`-Werte) irgendeiner Population eingesehen** — die
Lücken wurden rein durch Lesen des Freeze-Texts selbst und Grep auf
Code-Konstanten (`RNG_SEED`, `config.py`) gefunden, nicht durch
Dateninspektion. Dieses Erratum ändert **keinen bestehenden Satz** der
beiden obigen Freeze-Blöcke (inkl. ihrer jeweiligen Errata) — reine
Ergänzung.

**ENTSCHEIDUNG EASY (22.10.2026):**

1. **Bootstrap-Seed: `42`**, identisch für **beide** Test-Familien
   (Setup-Edge/Conviction UND KI-Score). `N=2000` bleibt unverändert.
2. **Bootstrap-Intervall: 95 %, zweiseitig, Perzentil-Methode**
   (2,5. und 97,5. Perzentil der Resample-Verteilung). „Intervall über
   0,5" (Erfolgskriterium (ii) in beiden Freezes) heißt konkret: **2,5.-
   Perzentil > 0,5**. Für ΔAUC (Test c) gilt die im Erratum 10.10.2026
   genannte Schwelle (ΔAUC-Punktschätzung ≥ +0,02 UND AUC(conviction) ≥
   0,55) **unverändert als Erfolgskriterium**; das 95%-Perzentil-Intervall
   für ΔAUC wird **zusätzlich** berichtet (Erfolgskriterium (ii) dort:
   „untere Grenze... über 0" — mit derselben 2,5./97,5.-Perzentil-Methode).
3. **Test c (Conviction) — Ausschluss-Regel, Spiegel der KI-Score-Regel
   vom 16.10.2026:** Zeilen mit fehlendem oder nicht numerisch-endlichem
   `conviction_score` werden aus Test c **ausgeschlossen**, gezählt und
   als Anteil berichtet; liegt der Anteil über 20 %, wird das als
   **Einschränkung im Ergebnis genannt** — **kein Abbruchkriterium**, der
   Test läuft trotzdem (identische Logik zu Erratum 16.10.2026). Test c
   rechnet AUC(conviction) und AUC(score) auf **exakt derselben
   Teilmenge** (gepaarter Bootstrap über dieselben Zeilen-Indices — eine
   Zeile ohne `conviction_score` wird für **beide** Größen in Test c
   ausgeschlossen, nicht nur für `conviction_score`). **Tests a und b
   bleiben unverändert** — ihre Population (nur `score`, immer vorhanden)
   ist von dieser Regel nicht betroffen.
4. **Auslöser unverändert:** gemeinsam `n ≥ 250` für a, b, c (Setup-Edge/
   Conviction-Freeze) bzw. a, b (KI-Score-Freeze). Test c berichtet
   zusätzlich seine **eigene, nach der Ausschluss-Regel reduzierte** n
   (Haupt-n bleibt die gemeinsame Zählung aus Freeze-Punkt 4, Test c
   zeigt separat `n_verwertbar` nach Ausschluss).

**Was dieses Erratum NICHT ändert:** alle Populations-Definitionen,
Zielgrößen, Erfolgsschwellen (0,55 / +0,02), Holm-Familien (k=3 bzw. k=2),
Brutto-Bindung und Grenzen-Absätze beider Freezes bleiben wörtlich wie
eingefroren. Nur die drei oben genannten, bis dahin unspezifizierten
Verfahrensdetails sind jetzt festgelegt.

**Änderungs-Protokoll gilt identisch für dieses Erratum** (analog
Setup-Edge/§4/KI-Score-Erratum 16.10.): keine weitere Änderung ohne
datierten Protokolleintrag.

### ERRATUM 22.10.2026 (b) — Holm-Input für Test c (Conviction-Zusatznutzen) präzisiert

**Anlass.** PR #597 (Freeze-Auswertungs-Autorun) flaggte — sowohl im Code-
Kommentar selbst als auch im squeeze-guardian-Bericht — dass die
implementierte Lesart für den Holm-Input `p_c` von Test c (Mann-Whitney-p
von `AUC(conviction_score)` selbst gegen den Split) **nirgends wörtlich**
im Freeze- oder Erratum-Text festgelegt war, sondern nur strukturparallel
zu Tests a/b gewählt wurde. Dieses Erratum legt die Lesart jetzt
verbindlich fest — **ohne Outcomes (`return_*`-Werte) einzusehen**, reine
Verfahrensklärung.

**ENTSCHEIDUNG EASY (22.10.2026):** Zielgröße von Test c ist laut Erratum
10.10.2026 Punkt 3 **ΔAUC = AUC(conviction_score) − AUC(score)** (gepaart).
Holm-Input `p_c` ist daher der **zweiseitige Bootstrap-p-Wert der ΔAUC-
Verteilung** aus dem gepaarten Bootstrap (N=2000, Seed 42):

```
p_c = min(1, 2 · min(Anteil Resamples mit ΔAUC ≤ 0, Anteil Resamples mit ΔAUC ≥ 0))
```

**NICHT** der p-Wert von `AUC(conviction_score)` gegen 0,5. Die
Teilbedingung „`AUC(conviction_score) ≥ 0,55`" (Erfolgskriterium (iv))
bleibt davon **unberührt** — sie ist und bleibt eine reine
Punktschätzungs-Schwelle, keine Signifikanzaussage.

**Was dieses Erratum NICHT ändert:** alle Populations-Definitionen,
Zielgrößen, Erfolgsschwellen (0,55 / +0,02), Holm-Familien (k=3 bzw. k=2),
Brutto-Bindung, Grenzen-Absätze und die drei Verfahrensdetails aus Erratum
22.10.2026 (a) oben (Seed=42, N=2000, 95% zweiseitig Perzentil 2,5./97,5.,
Test-c-Ausschluss-Regel) bleiben wörtlich wie zuvor festgelegt. Nur die
konkrete Berechnungsvorschrift für `p_c` ist jetzt fixiert.

**Änderungs-Protokoll gilt identisch für dieses Erratum.**

### WIEDERVORLAGEN — dated (Stand 08.08.2026, NICHT Teil des §4-Freeze)

- **14.08.2026 — SEC-Entscheid `SR-FINRA-2026-012` (SI-Meldepflicht).** Erwartet:
  **wöchentliches** SI-Reporting (statt bimonatlich) + **„arranged financing" zählt
  künftig als SI**. **Risiko für den laufenden §4-Exit-B.1-Test:** ein struktureller
  **SI-Sprung** durch die neue Definition wäre ein **Zeitreihen-Bruch** in der
  Datenbasis → dann greift die **Änderungs-Protokoll-Regel** (datierter Eintrag +
  Grund, bevor §4 angepasst wird). Am 14.08. den Entscheid lesen und die Konsequenz
  für `finra`-Pfad / `FINRA_PUB_OFFSET_BUSINESS_DAYS` (§7c) einordnen.
  **Zusatz (02.09.2026):** Für künftige Prüfungen zusätzlich zur SEC-Filing-Seite
  (sec.gov/rules-regulations/self-regulatory-organization-rulemaking/sr-finra-2026-012)
  folgende Quellen checken: (1) Federal Register (federalregister.gov) für die
  offizielle SEC-Order/Entscheidung, (2) FINRA Regulatory Notices (finra.org) —
  dort kündigt FINRA nach einer etwaigen Genehmigung das Wirksamkeitsdatum der
  Regeländerung an, taucht also erst NACH einer SEC-Genehmigung auf, nicht vorher.
  Stand 02.09.2026: keine der drei Quellen zeigt eine Entscheidung nach der
  verlängerten Frist vom 14.08.2026 — weiterhin offen, über 3 Wochen überfällig.
  **✅ ERLEDIGT 10.10.2026 — zurückgezogen 05.08.2026.** Laut SEC-Filing-Seite
  (sec.gov/rules-regulations/self-regulatory-organization-rulemaking/
  sr-finra-2026-012, Titel „WITHDRAWN on 08/05/2026", zuletzt aktualisiert
  05.08.2026) wurde das Filing zurückgezogen — **vor** der oben notierten
  02.09.-Prüfung, die das offenbar nicht erfasst hat (Seite war zu dem
  Zeitpunkt vermutlich schon auf „WITHDRAWN", aber nicht als solche erkannt
  oder die Prüfung schaute auf andere der drei Quellen). Diese Wiedervorlage
  ist damit **beendet** — kein SEC-Entscheid steht mehr aus, weil das
  zugrundeliegende Filing nicht mehr existiert. **Kein struktureller SI-
  Sprung droht aus diesem Filing** mehr für den laufenden §4-Exit-B.1-Test.
  Ein **Nachfolger-Filing wurde bei einer Suche am 10.10.2026 nicht
  gefunden** (nicht auszuschließen, nur begrenzte Suchtiefe) — eigener
  Beobachtungspunkt direkt unten.
- **Beobachtungseintrag — Nachfolger-Filing zu SR-FINRA-2026-012? (angelegt
  10.10.2026, kein Datum, Wiedervorlage beim Monatsrundgang.)** Seit dem
  05.08.-Rückzug keine neue SEC-/FINRA-Einreichung zum selben Thema
  (wöchentliches SI-Reporting / „arranged financing" als SI) gefunden —
  Suchtiefe am 10.10. begrenzt (keine Volltext-Datenbank-Abfrage, nur
  Web-Suche). Beim nächsten Monatsrundgang (siehe unten, geplant
  02.11.2026) erneut auf den drei Quellen aus dem 02.09.-Zusatz prüfen
  (SEC-Filing-Seite, Federal Register, FINRA Regulatory Notices).
  **Code-Prüfung (10.10.2026, nichts geändert):** `FINRA_PUB_OFFSET_BUSINESS_DAYS`
  (§7c, `config.py:526`) und die `N=3`-Fenstergröße für `si_velocity_pub`
  (§7c-Umfeld, `config.py:~551`) referenzieren SR-FINRA-2026-012 **nur in
  vorausschauenden Kommentaren** („plant höhere Frequenz, evtl. wöchentlich
  → möglicherweise kürzerer Delay", „verkürzt automatisch das Fenster
  proportional, N zentral anpassbar") — **beide Konstanten hängen bereits
  heute an FINRA Rule 4560 (Status quo, bimonatlich), nicht am
  zurückgezogenen Filing.** Kein Code-Pfad nimmt an, die neue Regel sei
  bereits in Kraft — beide Stellen sind rein konditional formuliert
  („falls/wenn die Regel käme"). **Kein Korrekturbedarf am Code.**
- **~Mitte Aug 2026 — Paper-C konfirmatorischer OoS-Test.** Läuft, sobald (a)
  Forward-`return_10d` der ab 13.07. gesammelten Records gereift ist UND (b) `n_win`
  an **beiden** Zielen ≥ Floor 40 — mit Regime-Vorbehalt (§5 Confound 1). Datengetrieben,
  nicht kalendarisch (Datum nur Schätzung).
- **Herkunft/Vollständigkeit im Matured-Export — ✅ GESCHLOSSEN 11.08.2026 (Easy:
  kein Zusatzfeld).** Die Paper-C-Forward-Charge (Entry ≥ 13.07.) rollt ~**11.–12.10.**
  über die 90-Tage-Kante aus `backtest_history.json`. Der Matured-Export ist
  **prune-immun** und hat die gereiften 13.07.-Records seit dem **04.08.-Backfill-Batch**
  bereits drin — **mit `provenance=backfill`** (NICHT `forward`: `provenance` markiert den
  Export-Lauf, nicht die Datumsgrenze — `forward` beginnt erst bei entry ≥ 21.07.,
  #506-Disambiguierung). **Entscheid Easy 11.08.: kein zweites, forward-artiges Feld.**
  Grund: die In-Sample/OoS-Trennung (Datumsgrenze 13.07.) ist über das `date`-Feld auf
  jeder prune-immunen Export-Zeile ablesbar; ein Zusatzfeld würde die #506-Disambiguierung
  (§4-provenance vs. Paper-C-Datum) wieder verwässern UND das eingefrorene §4-Artefakt
  berühren (Änderungs-Protokoll). Vollständigkeit überwacht der §4-Zähler #509 ohnehin
  täglich (Export-Zeilenzahl darf nicht schrumpfen).
- **`ssr_restriction`-Verify (#491-Wiedervorlage) — ✅ GESCHLOSSEN 10.08.2026.**
  Wegwerf-Probe #515 (Muster #510, read-only, dispatch-only) bewies den Positiv-Pfad
  live: erstes/mittleres/letztes heute-restringiertes Cboe-Symbol → `restricted_t=True`,
  Aggregat-Kreuzcheck Modul-Sicht == Roh-Ground-Truth **53 = 53 identisch** → Symbol-
  Konvention sauber, keine stille Zuordnungs-Lücke. Probe-Datei per Cleanup entfernt.
- **10c-1a-Vormerkung (SEC Short-Position-Reporting) — präzise Termine.** **Form SHO:
  Q1/2028 (02/2028)** · **erste Meldung: 28.09.2028** · **öffentliche Dissemination:
  29.03.2029**. Reine Vormerkung (fern), kein Bau — beim SR-FINRA-2026-012-Entscheid
  (oben) mitdenken, ob sich die SI-Datenlandschaft davor schon verschiebt.
- **Lit-Check 09.09.2026 — Allen/Haas/Pirovano/Tengulov (2025, *Journal of
  Banking & Finance*, „How prevalent are short squeezes? Evidence from the US
  and Europe").** Bereits bekannte Studie, jetzt mit Detail zu den Treibern:
  für **MARKET squeezes** sind Short Interest, Firmengröße, Kursdispersion
  (Price Dispersion) und Turnover die wirtschaftlich bedeutsamsten
  Determinanten; für **LENDER squeezes** sind es indikative Gebühr (Fee),
  verleihbare Menge (Lendable Quantity) und Utilization. Von den vier
  Market-Squeeze-Treibern deckt das Tool bereits **drei** ab (Short Interest
  via FINRA, Firmengröße via Market-Cap-Filter, Turnover via Volume-Signale)
  — **Price Dispersion fehlt komplett**.

  **GEPARKT, nicht weiter verfolgen ohne neuen Anlass:** die exakte Definition
  von „Price Dispersion" in dieser Studie (Analystenschätzungs-Streuung?
  Bid-Ask-Spread? realisierte Volatilität?) konnte per Web-Recherche NICHT
  geklärt werden — der Volltext liegt nur bei ScienceDirect hinter einer
  Bezahlschranke, die SSRN-Working-Paper-Version verlinkt auf dieselbe
  Abstract-Seite ohne PDF, keine frei zugängliche Kopie auffindbar (Stand
  09.09.2026, mehrere Suchansätze erfolglos). Eine Klärung bräuchte
  tatsächlichen Volltext-Zugang (Bibliothek, Autoren-Anfrage, o. ä.) — kein
  Fall für weitere Web-Suche bei künftigen Lit-Checks, außer der Zugang
  ändert sich.
- **Lit-Check 10.10.2026 (Kurzfassung, Anschluss an den 09.09.-Eintrag
  oben).** (a) SR-FINRA-2026-012 zurückgezogen (Details oben). (b)
  Fails-to-Deliver als Squeeze-Signal: **Nullbefund** — keine belastbare
  Studie gefunden. (c) Lotterie-/MAX-Effekt und Exit-Regeln: **Nullbefund**
  — keine neue Arbeit gefunden. (d) Schultz (*Journal of Financial and
  Quantitative Analysis*, 2024, „Short Squeezes and Their Consequences"):
  bestätigt **Utilization als stärksten Squeeze-Prädiktor** in der
  Literatur — ändert am heutigen Kurs/Bau nichts (keine neue Quelle dafür
  gefunden, siehe IBKR-Spur unten). (e) Kostenlose Utilization-Quelle:
  Tiefensuche **negativ** — siehe „IBKR-Spur (Borrow-Daten)" unten.
- **IBKR-Spur (Borrow-Daten) — angelegt 10.10.2026, Status `beobachtet`
  (siehe `open_items.json`, ID `ibkr-borrow-data-spur`).** Kurzfassung: IBKR
  Web-API-Snapshot-Felder `7636` (Shortable Shares) / `7637` (Fee Rate) /
  `7644` (Shortable) sind laut IBKR-Doku ohne genannte Abo-Pflicht abrufbar
  — `7637` (Fee Rate) wäre ein möglicher Ersatz für die seit **23.07.2026**
  toten CTB-Quellen (`IBKR_BORROW_ENABLED`/`STOCKANALYSIS_BORROW_ENABLED`,
  beide `False` seit Commit `ad981064`/01.08.2026, Borrow-Bonus laut
  Commit-Message dort bereits „seit 23.07. faktisch 0" — **git-belegt,
  Datum bestätigt**). Zugang liefe über First-Party-OAuth
  (`apiintegration@interactivebrokers.com`), Eignung für Privatkunden
  ungeklärt, Schlüssel könnte laut Entwickler-Angaben auch Handel erlauben
  → nur mit Zweitnutzer ohne Handelsrechte erwägen. Anfrage-Entwurf liegt
  vor, Absendung durch Easy aussteht. **Utilization selbst** (IBKR-App
  „Verleihquote", für Easy dort gratis sichtbar) ist in **keiner**
  gefundenen API enthalten (weder Web-API-Feldliste noch
  IBKR-Claude-Connector) — kein kostenloser automatischer Weg gefunden,
  bis dahin Handcheck. Volldetails im `open_items.json`-Eintrag.

  **ERGEBNIS 12.10.2026 — GESCHLOSSEN (`open_items.json`-Status
  `erledigt`).** IBKR hat auf Easys Mail an
  `apiintegration@interactivebrokers.com` geantwortet: OAuth für die
  Trading Web API ist auf **Institutional-** und **Financial-Advisor**-
  Konten beschränkt (Entscheidung des Web-API-Entwicklungsteams und des
  Managements) — Privat-, Joint-, Retirement- und Trust-Konten sind
  **ausgeschlossen**. Privatkunden bleiben nur Client Portal Gateway oder
  TWS API, jeweils live oder paper; beide brauchen einen **dauerhaft
  laufenden Rechner mit interaktivem 2FA-Login** und sind damit mit
  GitHub Actions und der iPhone-only-Arbeitsweise **nicht vereinbar**.
  Die Verleihquote (Utilization) bleibt damit weiterhin nur manuell in
  der IBKR-App abrufbar. **Entscheidung (Easy, 12.10.2026): Nicht bauen.**
  Handcheck der Verleihquote bei einzelnen Kandidaten in der IBKR-App
  bleibt manuell und optional. **Wiedervorlage 02.11.2026** (Monats-
  rundgang): nur prüfen, ob IBKR den Zugang für Privatkonten geöffnet hat
  — ein Satz, keine Arbeit. Kein Widerspruch zu einem älteren IBKR-
  Teilplan gefunden (Grep über dieses Dokument und `open_items.json` nach
  „Wegwerf"/„Key-Generierung": keine IBKR-spezifische Fundstelle außer
  den hier referenzierten) — nichts als überholt zu markieren.
- **Lit-Check 17.10.2026 — zwei Funde, Sammelfeld statt Berechnung.**
  **Fund 1 (Muravyev/Pearson/Pollet, Gies/Illinois, Oktober 2025, vermutlich
  *Journal of Financial Economics*, „Why does options market information
  predict stock returns?"):** die Leihgebühr einer Aktie lässt sich
  näherungsweise aus Optionspreisen ablesen (Abweichung von der
  Put-Call-Parität — Formel siehe unten). Interessant, weil die CTB-Quellen
  seit 23.07.2026 tot sind und die IBKR-Spur (oben) geschlossen ist.
  **Fund 2 (Baig/Strong/Zaynutdinova, Arbeitspapier „Seeking Gamma", AEA
  2026, Programmseite-Version 19.12.2025):** Gamma-Squeeze-Ereignisse
  werden dort über **Net Delta Open Interest**/**Net Delta Volume**
  (delta-gewichtet) gemessen — unser bestehendes Gamma-Signal
  (`GAMMA_SQUEEZE_ENABLED`, `generate_report.py:1890-1908`) ist gröber
  (reine Call-OI-Summe im ATM-Fenster, kein Delta-Gewicht). **Arbeitspapier-
  Charakter ausdrücklich benannt:** die Programmseite nennt teils
  widersprüchliche Zahlen (5,13 % gegenüber 5,79 % für denselben
  Kennwert in unterschiedlichen Versionen) und die genaue Ereignis-
  Definition („Gamma-Squeeze-Tag") ist aus der verfügbaren Fassung nicht
  abschließend rekonstruierbar — Vorsicht vor Übernahme konkreter
  Schwellenwerte aus dieser Quelle.

  **Umsetzbarkeits-Verdikt (beide Funde, Diagnose + Bau 17.10.2026, `#592`):**
  Sammelfeld **ja**, Berechnung **nein** (noch nicht) — **kein Score-
  Eingriff**. Beide Rechenwege brauchen Bid/Ask/LastPrice/Volumen/
  LastTradeDate je Strike, die `_extract_oi_rows()` (options_oi_history.json)
  heute verwirft, obwohl sie im selben `option_chain()`-Abruf bereits
  vorliegen (Diagnose-Beleg: SCHRITT 0a unten). **Entscheidung (Easy,
  17.10.2026):** Sammelfeld bauen (`options_chain_raw.jsonl`,
  `OPTIONS_CHAIN_RAW_ENABLED`); Auswertung frühestens nach 2–3 Monaten
  Datenlage und nur nach eigener, neuer Pre-Registration (analog zum
  KI-Score-Edge-Test-Freeze oben) — **Termin nicht geschätzt.**

  **SCHRITT-0a-Befund (reine Zählung, 17.10.2026, keine Returns
  angesehen):** 443 von 501 Punkten in `options_oi_history.json` haben
  mindestens einen Strike mit sowohl Call-IV > 0 als auch Put-IV > 0 zum
  gleichen Verfall — ein rückwirkend teilweise rechenbarer IV-Unterschied
  ist also in der Datenlage vorhanden (reine Zahl, keine Bewertung der
  Güte). Der in der options_oi_history.json gespeicherte Verfall ist der
  „nächste" (`_fetch_next_expiry_chain`, `exps[0]`, keine Mindest-Tage-
  Schranke) — **nicht notwendig derselbe** wie der für `atm_iv`/`pc_ratio`
  gewählte (`get_options_data`, Filter `IV_MIN_DAYS_TO_EXPIRY = 7`,
  `config.py:745`); beide Selektionslogiken sind unabhängig und können
  auf unterschiedliche Verfälle fallen. Das neue Sammelfeld nutzt
  bewusst NUR den „nächsten" Verfall (identisch zu options_oi_history.json)
  — siehe PR-Text für die Scope-Begründung (get_options_data deckt nur
  die ersten 5 US-Ticker ab, nicht die volle Top-10).

  **Rechenweg zur späteren Auswertung (dokumentiert, NICHT gebaut):**
  `q = −(1/T)·ln((C − P + K·e^(−rT)) / S)` (C/P = Call-/Put-Mittelpreis,
  S = Kurs, K = Strike, T = Restlaufzeit in Jahren, r = Zinssatz). Bei
  Aktien ohne Dividende entspricht `q` näherungsweise der Leihgebühr.
  (i) **Kein Zinssatz im Repo** (`risk_free`/`zinssatz`/`RISK_FREE`: 0
  Treffer) — eine neue Konstante wäre nötig. (ii) **Empfindlichkeit:**
  analytisch `dq/dr = K·e^(−rT) / (C−P+K·e^(−rT))` — für kurzlaufende,
  nahe-am-Geld-Optionen ≈ 1, d. h. **ein 1-Prozentpunkt-Fehler bei r
  erzeugt ungefähr einen 1-Prozentpunkt-Fehler bei q** (numerisch
  geprüft: S=K=10, T=30 Tage, q=20 % → r=5 %: q=20,00 %; r=6 %:
  q=21,01 %). (iii) **Bekannte Verzerrungen:** amerikanische Puts mit
  vorzeitigem Ausübungsrecht (überschätzt P bei teurem Borrow → q
  überschätzt), Dividenden (in der Formel nicht erfasst), ungenaue
  Mittelpreise bei breitem Spread. **Ausdrücklich festgehalten:** die
  Güte der echten Leihgebühr ist NICHT prüfbar (kein Vergleichswert im
  Repo, CTB-Quellen seit 23.07.2026 tot) — die **Vorhersagekraft gegen
  Renditen** ist es dagegen schon, über eine künftige, eigene
  Pre-Registration (analog KI-Score-Edge-Test).

  **Dateiwachstum (grobe Rechnung, Diagnose 17.10.2026):**
  `options_chain_raw.jsonl` wächst analog `options_oi_history.json`
  (dasselbe Sammel-Muster, zusätzliche Felder pro Strike) — Schätzung
  ca. **15 KB/Tag**, **kein Prune/Cap** (append-only, analog
  options_oi_history.json — ein verlorener Snapshot kommt nie zurück).
  Bei Erreichen von ca. **10 MB** neu bewerten (Rotation/Kompression/
  Cap-Diskussion), nicht vorher.

  **Regel-8c-Hinweis:** Dieser PR berührt `score()`/die Top-10-Auswahl
  **nicht** — Regel 8c (Setup-Edge-/KI-Score-Edge-Freeze, Score-Änderungs-
  Log-Pflicht) ist **nicht einschlägig**, ausdrücklich festgehalten, kein
  Log-Eintrag in einem der beiden Freeze-Blöcke nötig.
- **KI-Score-Coverage-Diagnose — abgeschlossen 10.10.2026 (read-only, keine
  PR, reine Chat-Diagnose, hier nachträglich dokumentiert).** Von 472
  gereiften Forward-Zeilen haben nur **144 (30 %)** einen `ki_signal_score`
  (`ki_sentiment_source`: 120 „keyword", 24 „llm"; bei Score ≥70: 62 von
  181). **Ursache (belegt):** Cron-Kollision — `daily-squeeze-report.yml:25`
  (postclose `17 21 * * 1-5`) und `ki_agent.yml:9` (`17 * * * *`) feuern
  zur selben Minute; der Daily-Run liest `agent_signals.json` vom letzten
  **committeten** Tick (Beispiel 08./09.10.: 3 h 12 min alt), die Datei wird
  pro Tick **komplett überschrieben** (nur aktueller Top-10/Watchlist/
  Positions-Pool, `ki_agent.py:335-337`/`126-178`); der vom Daily-Run selbst
  angestoßene Auto-Tick läuft **nach** dem Backtest-Append
  (`apply_agent_boost` ca. `generate_report.py:18412` vor
  `_append_backtest_entries` ca. `:18684`). 4 Tage mit 0 % Abdeckung
  (05.08., 03.09., 14.09., 16.09.), keine klare Rang-Korrelation. Forward-
  Returns sind Close-Close ab regulärem Schlusskurs sauber; der
  gespeicherte Score kann Nachbörsen-Kurs (`USE_PREPOST_DATA=True`,
  `config.py:1200`) und Post-Close-News bis zum Tick-Zeitpunkt tragen
  (mild, nicht beziffert — Tick-Zeitstempel wird nicht pro Record
  persistiert). LLM-Anteil nur 16,7 % — `claude_sentiment_score` fällt bei
  jeder Exception still auf `None` zurück (`log.debug`), konkrete Ursache
  (Rate-Limit/Timeout/Parse) nicht bestimmbar; API-Key ist verdrahtet
  (`ki_agent.yml:53`). Modell/Prompt/Cap seit 23.04.2026 unverändert
  (`68490659`), `compute_signal` seit 11.06.2026 nur einmal berührt
  (`e90fd5f1`, PR #440, rein additiv) — alle 472 Zeilen unter einer
  Konfiguration. Redundanz zum Setup-Score (r=0,691) stammt aus dem
  15.07.-Re-Test (n=55, anderes Fenster, weiter oben in diesem Dokument
  dokumentiert) — **nicht neu berechnet für die aktuelle Population.**
  **Empfehlung (Entscheidung offen, Easy):** Coverage-Fix (Manual-Merge:
  Daily-Run bekommt KI-Werte für die eigene Top-10 vor dem Append,
  Tick-Zeitstempel mitspeichern, Fehlerarten des LLM-Aufrufs loggen) VOR
  einer KI-Registrierung; danach llm/keyword als Kontext-Split statt
  eigener Test (llm-Stratum n=24 zu klein). **Bis dahin kein Freeze für
  den KI-Score.** Überschlag (kein Termin): bei 30 % Abdeckung ≈3
  Datensätze/Handelstag → n=250 ≈ Februar 2027; bei voller Abdeckung ≈10/Tag
  → ≈ Anfang Dezember 2026. Volldetails + Hypothesen-Prüfung im
  `open_items.json`-Eintrag `ki-score-coverage-diagnose-10-10-2026`.
- **KI-Score-Coverage-Fix gebaut (11.10.2026, Manual-Merge, Merge durch
  Easy aussteht).** Setzt die obige Empfehlung um:
  `generate_report._compute_fresh_ki_signals_for_backtest(top10)` berechnet
  jetzt synchron, im selben postclose-Lauf, GENAU für die finalen Top-10-
  Ticker einen frischen KI-Wert (Reuse von `ki_agent._process_ticker`, lazy
  importiert) — direkt vor dem Backtest-Append, NACH `apply_agent_boost`/
  `apply_monster_score`/`apply_conviction_scores` (Call-Order-Beleg:
  Top-10-Membership wird VOR dem Boost fixiert, bleibt unberührt; der
  frische Wert fließt NIE zurück in `score()`/Ranking/Push/Conviction —
  nur in den Backtest-Record). Neues additives Feld `ki_signal_ts`
  (UTC-ISO, Schema bleibt v4) markiert, wann der Fresh-Versuch stattfand;
  `score=None` bei echtem Fehlschlag bleibt ehrliches None (kein
  Fallback auf den alten stale Wert). **Daten mit `ki_signal_ts` sind die
  Population für einen späteren KI-Freeze; Zeilen ohne `ki_signal_ts`
  sind explorativ.** Zusätzlich: `claude_sentiment_score`-Fehlerarten
  (Timeout/HTTP/Parse/Rate-Limit) jetzt mit `log.warning` + aggregiertem
  Lauf-Zähler sichtbar (vorher nur `log.debug`), Verhalten (Keyword-
  Fallback) unverändert. Golden-Test byte-identisch, 17 neue + 1
  angepasster Mock-Test grün, `score_multiplier_sync`/`nan_bypass_fields`
  (Zeilen-Shift, kein inhaltlicher Fund) grün. **Kein KI-Freeze in diesem
  PR** — nur die Coverage-Grundlage. PR-Nummer + Hashes siehe Block 1
  (chronologischer Eintrag, Block-1-Pflicht).
- **Geplanter Auftrag „Squeeze Report Monatsrundgang November"** — einmalig,
  **Montag 02.11.2026, 09:00 Berlin-Zeit (= 08:00 UTC)**, Cloud-Lauf, nur
  lesend, Automatik-Modus. Bereitet Gruppen A–D vor, legt nur Gruppe B zur
  Entscheidung vor. Prüft: NYSE-empty-Serie (Entscheidungspunkt ~26.10.,
  siehe `open_items.json`-ID `nyse-regsho-empty-streak`), §4-Re-Test-Stand,
  SEC/FINRA-Nachfolger-Filing (siehe Beobachtungseintrag oben), Block-1-
  Rückstand.

#### ⚠ Datenherkunft des vorabregistrierten Exit-B.1-Re-Tests — gap-NaN-Erkennbarkeitsgrenze (Stand 29.07.2026)

**Gilt für den vorabregistrierten Exit-B.1-Re-Test oben (Score≥70-Bucket): bei der
Vorabregistrierung mitlesen.** (Bewusst hier verankert
statt in einem Code-Kommentar: die Re-Test-Vorabregistrierung wird an genau dieser
Kalender-Stelle gelesen, ein `# `-Kommentar in `generate_report.py`/`backtest_history.py`
nicht.)

**Herkunft:** #493 (`ce2e690`) hat `_gap_hold_pts`/`_rs_spy_pts` gegen NaN
gehärtet — eine degradierte yfinance-Bar ohne `dropna` lieferte `gap_pct=NaN`, das
an der `is None`-Guard vorbeirutschte und einen falschen `weak_hold`/`fail`-Beitrag
in den Timing-Score schrieb. „Schritt B" (Rück-Scan der Alt-Records) ist bewusst
als **Doku** umgesetzt, **nicht** als Flag/Schema-Feld — Begründung in (3).

**1) DIE GRENZE (Datumsbedingung, keine eingefrorene Stückzahl).** Die gap-NaN-
**Erkennbarkeit** reicht nur bis **11.07.2026** zurück — dem Beginn der
`app_data.json`-Git-Historie. Das einzige Nachweissignal ist `gap_states`
(`state ∈ {weak_hold, fail, strong_hold}` **und** `pct = null`); ältere app_data-
Stände existieren nicht mehr. **Für Backtest-Records mit Datum ≤ 10.07.2026 gibt es
kein Signal — sie sind UNBEKANNT, ausdrücklich NICHT „sauber".** Die 11.07.-Grenze
ist ein historischer Fakt (Datum), keine Fälligkeit/Projektion (Anti-Drift #488).
Die absolute Zahl der Unbekannten wächst nicht, aber ihr **Anteil sinkt** mit jedem
neuen Record — die Zahlen unten deshalb nur als **datierte Momentaufnahme** lesen.

**2) DIE DREI ZONEN (Stand 29.07.2026, Zahlen als Momentaufnahme, `git`-belegt):**
- **betroffen: 0** — im gesamten beobachtbaren Fenster kein einziger kontaminierter
  Backtest-Record.
- **geprüft & sauber: 122** (Handelstage 13.–28.07.2026) — jeder der 12 postclose-
  Append-Läufe hatte für seine angehängten Ticker nicht-NaN-`gap_states`.
- **unbekannt: 1792** (Datum ≤ 10.07.2026, zurück bis 22.04.2025) — kein Signal.
  **Unbekannt ≠ geprüft-sauber.** Ein fehlendes Signal darf nie als „sauber"
  gelesen werden.
  **Nachtrag 03.08.2026:** Diese Absolutzahl ist eine datierte Momentaufnahme und
  **schrumpft** durch den 90-Tage-Prune (`BACKTEST_MAX_DAYS`) — die 120 April/Mai-
  Records, die inzwischen über die 90-Tage-Kante gerollt sind, lagen genau in dieser
  Zone; „unbekannt" steht am 03.08. bei **~1672** (nicht mehr 1792). Die Zonen-Zahlen
  **nehmen ab**, nicht nur anteilig verschieben — die „Anteil sinkt"-Notiz unter (1)
  meinte die Proportion, nicht die Absolutzahl. (Auch „geprüft-sauber: 122" beginnt zu
  prunen, sobald die 13.07.-Records 90 Tage alt sind, ~ab Mitte Oktober.)

**3) DIE MECHANIK (warum der Nullbefund — und warum KEIN Flag).** Der Backtest-
Append läuft **nur postclose** (`_append_backtest_entries` nur bei
`run_phase=="postclose"`, Werktag-Abend ~21 UTC, konsolidierte Bars) **und ist
idempotent** (`if (ticker,date) in existing_keys: continue` — der **erste** Append
friert die Score-Felder ein, spätere Re-Renders überschreiben sie **nie**). Die
realen NaN-Ereignisse trafen (a) **premarket-Läufe**, die grundsätzlich **nicht**
appenden, und (b) **Wochenend-/Post-Append-Re-Renders** mit degradierten Bars, die
idempotent übersprungen werden. Beides wirkt auf **Live-Anzeige + Ranking**, **nie
auf einen eingefrorenen Backtest-Score**. Ein Flag würde deshalb nur „Datum ≤
10.07.2026" bedeuten — ein **Datums-Schnitt, kein Befund**; dafür lohnt kein neues
Schema-Feld auf den Auswertungsdaten. Der Wert liegt darin, dass **Grenze +
Mechanik dort stehen, wo sie bei der Sept-Vorabregistrierung gelesen werden.**

**4) KORREKTUR.** Die frühere Arbeitshypothese „15.07. und 27.07. sind
kontaminiert" (aus dem 2-Tage-Fund der Schritt-A-Diagnose) steht **nirgends
schriftlich** — nicht im Handover, nicht in `CLAUDE.md`, nicht in einem Code-
Kommentar (`grep` über `#493`/gap-NaN-Kontamination leer). **Nichts zu
korrigieren.** Beleg für die Auflösung: an beiden Tagen lag der NaN nur im
**premarket**-Lauf (Live-Anzeige), die Backtest-Records kamen vom sauberen
postclose-Lauf — z. B. **15.07. KUST** `score=80.52` und **27.07. GRPN**
`score=89.46` (Erst-Append-Commit `6e005607e`, `gap_states NaN=[]`).

**5) HINWEIS FÜR DIE VORABREGISTRIERUNG.** Der Exit-B.1-Re-Test läuft auf dem
Score≥70-Bucket. **Unter n-Definition A (`provenance=forward`)** stammt das gezählte
Material ausschließlich aus entry ≥ ~20.07.2026 — also **innerhalb** des gap-NaN-
beobachtbaren Fensters (≥ 11.07.), **nicht** aus der unbekannten Zone (≤ 10.07.). Der
frühere Hinweis „überwiegend unbekannte Zone" galt für das Zählen aus dem gepruneten
`backtest_history.json` und ist mit Definition A **hinfällig**; die 242 In-Sample-
Records (teils in der unbekannten Zone) zählen ohnehin nie zum n. Eine etwaige
Sensitivitäts-Gegenprobe (die 14 date-Forward-backfill-Records) wird **dort**
bewertet — nicht hier, kein Ausschluss-Automatismus.

**Sammel-Rate (gemessen 15.07., Hard-Facts):** **10 Records/Handelstag** (nur
postclose, nur Top-10) = das Maximum ohne Populations-Wechsel. **Hard-Stop:
`return_10d`-Reifung = 10 Handelstage** (immutabel — jeder Record braucht ~2
Kalenderwochen, bevor er zählt). Warten ist hier **kein** Engpass, sondern der
eingebaute Out-of-Sample-Schutz (§8).
| **Herbst 2026 / Q4 (OoS)** | **Hypothese H5 (Kombi Score × Katalysator × Momentum × SI)** | n ≥ 40 pro Feld-Kombi | **Vorab-registriert** (§5). Out-of-Sample über die **fünf** Look-Ahead-freien Sammel-Bausteine (§5). Feste Klammer, keine nachträgliche Schmälerung. |

### PAPER-PLAN-STATUS (Svoboda et al. 2026 — 4 Schritte A–C + Ausblick D, je 1/Tag)

**Kurz-Status 17.07.:** **A + B daten-seitig ENTBLOCKT** (13.07., yfinance-
SI-Position via #423) — **auswertbar nach ~2–3 Settlement-Zyklen** (der Seed
gibt ein 1-Monats-Delta ab Tag 1, echte OoS-Statistik erst mit n≥40 paper-
treuen Squeeze-Events, ~2–3 Monate). **C:** explorativer Read **durchgeführt
17.07.** — **KEIN belegter Effekt** (konfirmatorische Klammer leer; Details §5
„PAPER-C-READ" + Abgrenzungsblock unten). Nächster C-Schritt = **konfirmatorischer
OoS-Test, datengetrieben ~ab 27.07.** (Forward-`return_10d` gereift + n_win beide
Ziele ≥ Floor 40). **D bedingt** (nur nach belegten A–C). **Nächster aktiver
Schritt: A/B-AUSWERTUNG sobald Settlement-Zyklen da; C wartet auf OoS-Reifung —
bis dahin SAMMELN, kein Bau nötig.**

Vorregistriert, **Schwellen aus FREMDEM Datensatz** (Overfitting-Schutz). Kein
Zeitdruck. Volle Paper-Befunde in §5.

| Schritt | Was | Status / Disziplin |
|---|---|---|
| **A** ✅ **ENTBLOCKT (daten-seitig, 13.07.)** | Binäre Zielvariable `squeeze_event` (Peak ≥ +30 % in 1 Handelswoche **UND** SI-Rückgang ≥ 20 %) **neben** `return_10d`. Adressiert „Häufigkeit ≠ Rendite-Edge" (§8h). | **SI-Positions-Quelle gefunden (yfinance, gratis) + gebaut (#423):** `si_position_history.json` sammelt die ausstehende SI-**Position** settlement-datiert **forward-only**. SI-Rückgang ≥ 20 % messbar. **Vorbedingung jetzt = Sammelzeit** (Seed gibt Startpunkte sofort), **kein** Daten-Blocker mehr. Peak-Seite via yfinance ohnehin machbar. Voller Befund §6i. **Nicht abspecken** (§8l: ohne Covering-Komponente kollabiert `squeeze_event` in die widerlegte Hypothese C). |
| **B** ✅ **ENTBLOCKT (daten-seitig, 13.07.)** | SI-Zuwachs in die 3 Literatur-Buckets (7–17 / 17–25 / > 25 % SI-Zuwachs). B **teilt A's Datenblocker** (Korrektur #419: nicht „ohne A"). | **Paper-treu machbar über dieselbe SI-Positions-Zeitreihe wie A** (`si_position_history.json` — 1-Monats-Positions-Delta via `sharesShort` vs. `sharesShortPriorMonth`). Auf `si_velocity_pub` (Volumen) werden die Paper-Schwellen weiter **nicht** gelegt (Nomenklatur-Falle §8m). |
| **C** *(explorativ backgefüllt 17.07. + sammelt vorwärts)* | **Momentum als Haupthypothese** (`entry_past_return_5d` **positiv** = vorheriger Aufwärtstrend verstärkt), Reversal nur kurzfristige Nebenhypothese. Korrigiert die frühere „Reversal-Substrat"-Framing (§5). | Richtung vor der Auswertung fixiert (Paper: Momentum > Reversal). **Stufe-B-Backfill durch (465 Records, `5d8e78d`)** — diese sind **RETROSPEKTIV/IN-SAMPLE** (de-risken die Hypothese explorativ), die ab 13.07. **vorwärts** gesammelten (42, +10/HT) sind **konfirmatorisch**. **NICHT poolen** (§4-Abgrenzung unten). Kein nachträgliches Umdrehen. |

#### ⚠️ Paper-C-Auswertung — IN-SAMPLE vs. OoS-Abgrenzung (KRITISCH, vor jedem Read lesen)

Nach dem 17.07.-Backfill koexistieren **zwei Populationen** von
`entry_past_return_5d`-Records, die **niemals gepoolt** werden dürfen:

- **EXPLORATIV / IN-SAMPLE** — die **465 backgefüllten** Alt-Records (`5d8e78d`).
  Sie sind look-ahead-**sicher** (nur Pre-Entry-Adj-Close), aber ihr Beweiswert ist
  **exploratorisch**: „ist die Momentum-Beziehung überhaupt da?". Sie **ersetzen
  NICHT** den vorregistrierten Vorwärts-Test (In-Sample-Falle, §8z1-Klasse).
- **KONFIRMATORISCH / OoS** — die ab **13.07. vorwärts** gesammelten Records
  (aktuell **42**, wachsend **10/Handelstag**). Nur diese tragen den registrierten
  Out-of-Sample-Nachweis.

**⚠ Begriffs-Disambiguierung „forward" (nicht verwechseln):** Hier — im Paper-C-
Momentum-Test (`entry_past_return_5d`) — ist „forward"/„vorwärts" **datums-basiert**
gemeint: die **ab 13.07.2026 gesammelten** Records (Quelle: `backtest_history.json`-
Backfill/Manifest). Das ist **NICHT** dasselbe „forward" wie in der **§4-Exit-B.1-
Vorabregistrierung**, wo `provenance=forward` gemeint ist (**Definition A**,
Herkunftsfeld aus `matured_backtest_export.jsonl`). **Zwei verschiedene Tests, zwei
verschiedene Datenquellen, zwei verschiedene „forward"-Begriffe** — nie gleichsetzen.

**Regel:** jede Paper-C-Auswertung muss explorativ (backfilled) und konfirmatorisch
(forward, hier datums-basiert — siehe Disambiguierung oben) **getrennt ausweisen**. **Explorativer Read DURCHGEFÜHRT 17.07.** (Slot-29
registriert, Details §5 „PAPER-C-READ"): **KEIN belegter Effekt** — konfirmatorische
Klammer leer (OoS `return_10d` 0 gereift, `max_gain` n_win=3 < Floor); In-Sample nur
explorativ (Peak-spezifischer Momentum-Hinweis auf `max_gain_pct`, AUC ~0.61 Holm-
signifikant, aber **kein** Endpunkt-Effekt auf `return_10d`, r=+0.07 zu Setup).
**Nächster Schritt (datengetrieben):** **konfirmatorischer** OoS-Test sobald (a)
Forward-`return_10d` gereift (~ab 27.07.) UND (b) n_win an beiden Zielen ≥ Floor 40 —
mit Regime-Vorbehalt (§5 Confound 1). **Rückweg** falls nötig: Workflow `mode=undo`
(Manifest-basiert, nullt nur die 465, OoS-Records unberührt).
| **D** *(Ausblick, bedingt)* | `squeeze_probability`-Score nach Paper-Modell aus den **validierten** Einzelfaktoren. Deklaration + Bedingungen unten. | **NUR falls A–C einzeln out-of-sample tragen.** Kein automatischer Folge-Schritt. |

**Backlog aus dem Paper** (§6g/§6h): Institutional-Ownership-Faktor (dämpfend),
Crash-Blind-Zone (Marktrückgang > 3 % → Modell blind). **§6h erledigt 08.08. als
ANZEIGE-Banner** (kein harter Filter — Begründung in §6h).

#### Schritt D — Deklaration + Bedingungen (KRITISCH, vor jedem Bau lesen)

**Was der Score IST und NICHT ist:** `squeeze_probability` misst die
**WAHRSCHEINLICHKEIT eines Squeeze-Ereignisses**, **NICHT die erwartete
Rendite**. Er ist ein **Attention-/Monitoring-Signal, KEIN Kaufsignal**
(Auffanglinie: **Häufigkeit ≠ Rendite-Edge**). Diese Trennung ist die
Existenzbedingung des Scores.

**Bau-Bedingungen (alle vier zwingend):**

- **(a)** Nur bauen **NACHDEM** A, B, C **einzeln** out-of-sample getragen
  haben (Erfolgs-Definition §5). Kein Bau auf Punktschätzungen.
- **(b)** Gewichte aus den **VALIDIERTEN** Faktoren ableiten (Paper-Modell-
  Struktur), **NICHT** frei aus unseren Testdaten optimieren (`monster_score`-
  Falle §8e).
- **(c)** **Separate, eigenständige Achse** neben dem Setup-Score — kein Merge
  in `score()`, keine Rückkopplung (analog Score-Konfidenz-Isolation).
- **(d)** Im Frontend **klar als „Wahrscheinlichkeit, nicht Empfehlung"
  deklariert** — gleiche neutrale Sprache/Optik wie das Status-Panel (#412).

### ✅ STATUS-PANEL — 6. Eintrag `si_position_history` — ERLEDIGT (PR #430, 14.07.)

Vorarbeit 13.07. (Read-only-Diagnose) → Bau 14.07. **nach** dem ersten Postclose-
Seed, gegen die reale Datei. Umgesetzt exakt nach Plan: separater client-Fetch
(`_btSiCollectStatus`) mit Graceful-Empty (fehlende Datei → `n=0`), Zähl-Logik
„Ticker mit ≥2 Punkten" (dynamisch, `_btSiCount`), Label/Status/Dateiname zentral
in `config.SI_POSITION_STATUS_ROW` (Weg-A, kein Frontend-Literal), rein anzeigend
(keine Serien-Werte), Golden + Panel-Tests (D/E) grün. Live: **n=28**. Details in
§1 (PR #430). Live-Sicht-Check nach Deploy in §3 (AKUT).
### ✅ BOOTSTRAP-SHELL PHASE 0 + 1 — ERLEDIGT (#434 + #436, 14.–15.07.)

Beide Phasen live. **Phase 0** (#434): `app.html` = kanonischer Content-Pfad, alle
Parser repointed (Fallback `index.html`), S9 auf `app.html`. **Phase 1** (#436): der
Flip — `index.html` = 754-B-Shell mit `location.replace('app.html?v=' + Date.now())`.
Phase-0-Zyklus-Verify grün über 2 Postclose-Läufe, iOS-Adoption durchgeführt (§3).
**Rollback bleibt Ein-Zeilen-Revert** der Shell-Konstante (Parser lesen seit Phase 0
`app.html` mit index-Fallback → unschädlich). **Finaler Langzeit-Beweis (Icon-Tap
nach Postclose zeigt frischen Marktdaten-Stand) passiv offen — §3.**

### Erledigt (nicht mehr im Backlog)

- **Hypothese C (Peak-Ziel, +10/+30/+50 %) — ERLEDIGT 04.07.2026.** Null belegt
  (0/6 Holm). Wiedervorlage frühestens Herbst 2026 (falls je ein Setup-Re-Test **neu**
  registriert wird — heute **nicht** vorabregistriert, siehe RE-TEST-KALENDER).

### Bau-Kandidaten (nicht Bau-Priorität — konkurrieren nach Re-Test-Befunden)

Reihenfolge erst nach belegten/nicht-belegten Edges. Pool: Synthetische
Utilization, Katalysator-Gating, Exit-Mechanik-Spec, Reddit-Velocity,
424B-Dilution (§5).

---

## 5) STRATEGISCHE ROADMAP — Edge-Suche

### EDGE-BEFUND (Stand 13.07.2026): AUFFANGLINIE UNVERÄNDERT

**Kernbotschaft:** Über **vier** Auswertungen (30.06. Endpunkt-Return · 01.07.
Exit-Timing · 04.07. Peak-Ziel · **17.07. Paper-C-Momentum**) hat **kein Prädiktor**
eine belegte Edge nach Erfolgs-Definition gezeigt. Das Tool ist **Attention-
Router / Screener**, **kein Alpha-Generator**. Nichts an dieser Linie hat sich
seit 30.06. verschoben.

**Erfolgs-Definition (einmal fixiert, nicht aufweichen):** „belegte Edge" nur
wenn (a) Holm-signifikant über der pre-registrierten Klammer, **UND** (b)
Bootstrap-CI-Untergrenze der AUC > 0.5, **UND** (c) plausibel im Regime-Split
reproduzierbar. Punktschätzung ist nie Beleg.

### PAPER-C-READ (Momentum) — 17.07., EXPLORATIV: KEIN belegter Effekt

Erster Paper-C-Read nach dem Backfill (465 In-Sample + 42 OoS-Records; read-only,
Seed 17072026, N=2000, `mann_whitney_u_auc` + Holm + Cluster-Doppellauf). Prädiktor
`entry_past_return_5d` kontinuierlich, Haupthypothese Momentum-positiv (AUC > 0.5),
zwei Ziele. **Verdikt: KEIN belegter Effekt — die konfirmatorische Klammer ist LEER.**

**(B) KONFIRMATORISCH / OoS — nicht auswertbar (registrierte Floor-Regel):**
- `return_10d`: **0 gereift** (alle 42 OoS-Records 13.–16.07. → reift erst ~27.07.).
- `max_gain_pct`: n=42, aber **n_win=3** → unter Floor 40; die Roh-AUC 1.0 wäre ein
  3-Punkte-Artefakt → **nicht gerechnet** (nicht als Beleg dargestellt).

**(A) EXPLORATIV / IN-SAMPLE — de-risking, KEIN Beleg per Konstruktion.** Die zwei
Ziele **WIDERSPRECHEN** sich:

| Ziel | AUC (with/without) | CI-lo | roh-p | Holm-Reject (k=4) |
|---|---|---|---|---|
| `max_gain_pct ≥ 30 %` | **0.604 / 0.616** | 0.540 / 0.547 | 0.0009 | **JA** |
| `return_10d` (WIN≥+10/LOSS≤−5) | 0.476 / 0.464 | 0.405 / 0.379 | 0.52 / 0.37 | nein |

**Lesart (registriert, NICHT umgedeutet):** falls da was ist, ist es **PEAK-
SPEZIFISCH** — Momentum-Aktien spiken höher, geben es bis Tag 10 zurück. Konsistent
zu Exit-Hinweis B.1 (früh raus) und zum Paper (misst Wahrscheinlichkeit, nicht
Rendite). Das `return_10d`-AUC < 0.5 wird bei p=0.37–0.52 **NICHT als „Reversal
bestätigt"** gelesen — es ist schlicht kein Effekt auf den Endpunkt.

**Bemerkenswert (erstmals):** der **erste** Prädiktor mit Holm-signifikanter
In-Sample-Trennung, der **NICHT mit Setup redundant** ist — `corr(EPR, score)`
**r=+0.074** (vs. ki_signal r=0.69). Ein etwaiger Effekt wäre **inkrementell** zum
Setup-Score.

**Confounds (dämpfen, vorab ausgewiesen):**
1. **REGIME-VORBEHALT (der Killer):** In-Sample **96 % bull** (445/20, VIX 17.0,
   EPR-Median 10.48) vs. OoS-Fenster **52/48 bull/neutral** (VIX 16.5, EPR-Median
   **1.50**) — **verschiedenes Regime UND Kandidaten-Profil**. **Konsequenz:** der
   spätere OoS-Test ist **KEIN sauberer Nachfolger** — ein künftiges „in-sample ja,
   OoS nein" darf **NICHT automatisch als Falsifikation** gelesen werden (kann
   Regime-Differenz sein); umgekehrt kann der bull-lastige Peak-Effekt ein
   **Bull-Volatilitäts-Artefakt** sein (Pre-Move + Peak in Bull beide aufgebläht).
2. **Cluster-Doppellauf (#391):** 79/465 In-Sample-Followups, Ergebnis **stabil**
   (0.604→0.616, beide Reject); OoS 0 Followups (with==without kollabiert).
3. **Selektions-Unabhängigkeit BELEGT (#402):** `entry_past_return_5d` floss **NIE**
   in Score/Top-10-Selektion (grep: nur Write-Path + S10-Label + Kommentare) — die
   backgefüllten Records selektierte ein Score, der den Prädiktor nicht kannte.
4. **Holm k=4** (nur In-Sample-Zellen mit gültigem p; OoS liefert strukturell keinen
   p → nicht in k). Robust: auch bei Design-Maximum k=8 bliebe p=0.0009 < 0.00625.

**Nächster Schritt (datengetrieben, NICHT kalendarisch):** konfirmatorischer OoS-Test
sobald **(a)** `return_10d` der Forward-Records gereift (~ab **27.07.** erster
Schwung) **UND (b)** n_win an **beiden** Zielen über Floor 40 — mit dem Regime-
Vorbehalt (Confound 1) im Blick. Registrierung bleibt wie am 17.07. fixiert
(Momentum positiv, kontinuierlich, beide Ziele, Slot-29-Erfolgsdefinition). **Die
465 In-Sample-Zahlen dürfen im OoS-Test NIE als Beleg auftreten.**

### FRONTEND-KONSISTENZ ERREICHT (Stand 13.07.)

Nirgends im Frontend wird mehr eine **suggerierte Edge ohne Beleg** gezeigt —
konsequent an den belegten Zustand angepasst:

| Fläche | PR | Wirkung |
|---|---|---|
| Conviction-Level-Texte | #406 | „Aggregations-Anzeige, nicht validiert" statt Handlungs-Suggestion |
| „Erste Erkenntnisse"-Empfehlungsblock | #414 | komplett entfernt (war als Trade-Signal lesbar) |
| Sammel-Felder-Status-Panel | #412 | neutrale Zähler, **keine** Feld-Werte/Signale |
| **Monster-Score** | **#425/#426** | Tier **heuristisch**, Push `monster_backup` **raus**, Zahl+Bar **neutral-grau**, Earnings-Body ohne 🔥, `n_signals` monster-frei |

### KOMBI-ZIEL H5 (aktiv verfolgt, vorab-registriert)

**Score × Katalysator × Momentum × SI** als Interaktion. **JETZT FÜNF Look-
Ahead-freie Sammel-Bausteine live:**

| Baustein | Ort | Deploy | Sammel-Zweck |
|---|---|---|---|
| `max_gain_pct` (#397) | `backtest_history.json` | 02.07. | Peak-Amplitude im ≤10-TD-Fenster |
| `entry_past_return_5d` (#402) | `backtest_history.json` | 02.07. | Momentum-/Reversal-Substrat vor Entry |
| `days_to_earnings` (#404) | `backtest_history.json` | 04.07. | Katalysator-Nähe (point-in-time) |
| `si_velocity_pub` (#409) | `backtest_history.json` | 10.07. | SI-Änderungsrate über 3 publizierte Reports — **Tages-Short-VOLUMEN** (Fluss), Look-Ahead-frei via `pub_date` |
| **`si_position_history` (#423)** | **eigene `si_position_history.json`** | **13.07.** | ausstehende SI-**POSITION** als settlement-datierte Zeitreihe (Bestand) — das **Paper-SI-Maß** für A/B; forward-only, Seed-2-Punkte |

**Wichtige Abgrenzung (Nomenklatur-Falle §8m):** `si_velocity_pub` (Volumen,
Fluss) und `si_position_history` (Position, Bestand) messen **verschiedene
Dinge** — die Paper-Schwellen 7/17/25 % gelten **nur** für die Positions-
Zeitreihe, **nicht** für das Volumen-Signal. Beide koexistieren mit
verschiedenen Zwecken im Kombi-Ziel.

**Auswertungs-Plan:** Out-of-Sample im Herbst/Q4 2026 bei n≥40 pro Feld-
Kombination, gepaart mit Score-Buckets. Feste Klammer vor der Auswertung.
**Schwellen literatur-abgeleitet** (Svoboda et al.: SI-Buckets 7–17/17–25/> 25 %,
Momentum positiv), **NICHT** frei aus unseren Daten optimiert.

**MASTER-SCORE-VORBEHALT:** Ein Master-Score (gewichtete Kombination) wird
**NUR NACH** belegter Kombi-Edge gebaut. Gewichte **NICHT** frei aus Testdaten
(`monster_score`-Falle §8e: 0.76 n=13 → 0.51 n=20). **Out-of-Sample-Pflicht.**
Die Paper-Modell-Variante ist **Schritt D** (§4) — ein `squeeze_probability`-
Score, der **Wahrscheinlichkeit statt Rendite** misst.

#### VORABREGISTRIERUNG H5 (Freeze-Datum: 12.09.2026) — volle Kette

Ersetzt die bisherige Unklarheit (Zielbegriff + n≥40-Schwelle + Herbst/Q4-
Fenster waren registriert, die konkrete Mechanik nicht). Ab hier gilt für
diesen Block dieselbe **Änderungs-Protokoll-Regel** wie für §4-Exit-B.1
(siehe unten) — keine stille Anpassung.

**Warum nur 4 der 5 oben gelisteten Bausteine in die Interaktion einfließen:**
`max_gain_pct` und `si_velocity_pub` sind bewusst **nicht** Teil der vier
Interaktions-Prädiktoren unten. `max_gain_pct` ist eine **Outcome**-Metrik
(Peak-Amplitude nach Entry, siehe Hypothese-C-Einordnung weiter oben in
dieser Sektion) — kein Prädiktor, der zum Entry-Zeitpunkt vorliegt.
`si_velocity_pub` misst ein **anderes** Konzept als `si_position_history`
(Volumen/Fluss statt Position/Bestand, siehe „Nomenklatur-Falle §8m" oben)
— die Paper-Schwellen und der SI-Trend-Baustein unten beziehen sich explizit
auf die Positions-Zeitreihe, nicht auf die Velocity-Reihe. Beide bleiben als
eigenständige Sammel-Bausteine bestehen (Tabelle oben), fließen aber nicht
in diese spezifische 4-Wege-Interaktion ein.

**1) Bausteine (final, ersetzt vorherige Unklarheit):**
- **SCORE** = Setup-Score aus `matured_backtest_export.jsonl` (`score`-Feld).
- **KATALYSATOR** = `days_to_earnings`. **Nicht** `material_8k_events` —
  letzteres ist ein Sammelbecken verschiedener Ereignistypen (Item-Codes
  1.01 bis 9.01 gemischt) und war nie Teil dieser H5-Dokumentation.
- **MOMENTUM** = `entry_past_return_5d`.
- **SI** = `si_position_history.json`, verknüpft via Ticker-Match + Join-
  Punkt „letzter Punkt mit `pub_date ≤ entry_date`" (look-ahead-sicher —
  **nicht** `settlement_date`, das läge im Median ~10 Tage voraus, siehe
  Lag-Messung in der vorbereitenden Diagnose 12.09.2026).
- **SI-TREND** = Delta zwischen den beiden jüngsten look-ahead-sicheren
  Punkten (Settlement-Abstand typischerweise ~30 Tage).

**2) Zellen-Definition (Kreuztabelle, KEINE Regression mit
Interaktionstermen):** bei ~200 Records und vier Dimensionen ist eine
Regression mit Interaktionstermen overfitting-anfällig (zu viele
Freiheitsgrade pro Beobachtung) — Kreuztabelle mit vorab fixierten,
groben Buckets ist die robustere Wahl. Vier binäre Dimensionen × 2 ergibt
**16 Zellen**:

| Dimension | Split | Regel |
|---|---|---|
| Score-Stufe | ≥70 / <70 | etablierte Projekt-Schwelle (unverändert aus bestehender Score-Klassifikation) |
| Momentum-Vorzeichen | positiv / negativ | `entry_past_return_5d ≥ 0` → positiv, `< 0` → negativ (Grenzfall exakt 0 zählt als positiv, fixe Konvention) |
| Katalysator-Nähe | nah / fern | **Median-Split auf `days_to_earnings`** — der Median wird **zum Auswertungszeitpunkt** auf dem dann vorliegenden Forward-Sample berechnet, **nicht heute aus den ~208 Diagnose-Records fixiert** (ein aus der heutigen Kleinstichprobe abgeleiteter Zahlenwert wäre selbst schon eine Form von Overfitting auf eine Zwischenmenge, die für das Herbst/Q4-Sample nicht mehr repräsentativ sein muss) |
| SI-Richtung | fällt / steigt | **grobes Vorzeichen** des SI-Trends (Punkt 1) — **nicht** die scharfe Svoboda-20%-Schwelle. Grund: bei n=2 von 342 trend-fähigen Records in der Diagnose-Stichprobe feuert die scharfe Schwelle praktisch nie und wäre nicht auswertbar; das Vorzeichen ist die einzige Auflösung, die genug Fälle in beiden Zellen erwarten lässt |

**3) Stichprobe:** n≥40 pro Zelle (bestehende Registrierung), **nur
`provenance=forward`** (gleiche OoS-Disziplin wie bei allen anderen §4-
Tests). **Reife-Einschätzung (Stand 12.09.2026, KEIN Ergebnis, nur
Machbarkeits-Einordnung):** die vorbereitende Diagnose zählte ~208
forward-Records mit allen vier Bausteinen gleichzeitig gefüllt. Auf 16
Zellen verteilt wären das im (unrealistischen) Idealfall gleicher
Verteilung ~13 Records/Zelle — **klar unter n≥40**. Da die Verteilung
über Score/Momentum/Katalysator/SI erfahrungsgemäß nicht gleichmäßig ist
(einzelne Zellen werden dünner, andere dichter sein als der Schnitt),
ist auch das eine **optimistische** Überschlagsrechnung. Das bestätigt,
dass das Herbst/Q4-Fenster tatsächlich für **spätere** Reife gedacht war
und nicht für den heutigen Stand — die Registrierung bleibt bestehen,
der Test **löst erst aus, wenn n≥40 in jeder der 16 Zellen erreicht ist**
(datengetrieben, kein Kalendertermin, analog Exit-B.1-Auslöser-Logik).

**4) Multiple-Testing-Korrektur:** Holm-Korrektur über alle **16 Zellen**
(`scripts/stats_helpers.py::multiple_testing_correction`, gleiches
Verfahren wie bei Exit-B.1). Kein Cherry-Picking einzelner Zellen ohne
Korrektur — alle 16 gehen in den Holm-Lauf, unabhängig vom Einzelergebnis.

**5) Ausreißer-Behandlung (vorab festgelegt, nicht nachträglich):** Der in
der Diagnose beobachtete Extremwert (+18.064,8 % Δ bei einem einzelnen
Ticker, nicht verifiziert ob Datenfehler oder echter Meme-Spike) wird wie
folgt behandelt — **zwei getrennte Ebenen:**
  - **Primäre Zellen-Zuordnung (SI-Richtung):** braucht nur das **Vorzeichen**
    des Delta, keine Magnitude. Ein Ausreißer verschiebt bestenfalls, in
    welche der zwei Zellen (fällt/steigt) ein einzelner Record fällt — er
    kann die Zellen-Zuordnung selbst nicht durch seine Größe verzerren.
    Für die primäre Kreuztabelle ist **keine** Winsorizing-Aktion nötig.
  - **Sekundäre/deskriptive Auswertung** (falls die kontinuierliche Δ%-
    Verteilung zusätzlich berichtet wird, z. B. Median/Mittelwert pro
    Zelle als Kontext): **Winsorizing bei P5/P95**, berechnet **auf dem
    jeweiligen Analyse-Sample zum Auswertungszeitpunkt** (nicht heute mit
    einem Diagnose-Wert fixiert — gleiche Logik wie beim Median-Split in
    Punkt 2). Median statt Mittelwert ist ohnehin die primäre
    Kennzahl — robust gegenüber Einzelausreißern per Konstruktion, das
    Winsorizing ist zusätzliche Absicherung für Mittelwert-Nebenangaben.

**6) Zielgröße (Outcome) + Erfolgs-Definition:** **Zielgröße ist `return_10d`**
aus `matured_backtest_export.jsonl` (dasselbe Reifungs-Feld, das den Export
selbst zum „gereiften" Record macht — kein neues Outcome-Konzept). Pro Zelle
wird `return_10d` dieser Zelle gegen die restlichen 15 Zellen zusammen via
`mann_whitney_u_auc` verglichen (identisches Verfahren wie Exit-B.1) — daraus
16 p-Werte für die Holm-Korrektur aus Punkt 4. Erfolgs-Definition identisch
zum bestehenden globalen Standard — Edge nur belegt, wenn **(a)**
Holm-signifikant über alle 16 Zellen, **UND**
**(b)** Bootstrap-CI (N=2000, fester Seed, analog Exit-B.1) schließt Null
aus, **UND** **(c)** im Regime-Split plausibel reproduzierbar.
**Punktschätzung allein ist nie Beleg.**

**7) Bekannte, akzeptierte Datenlücke:** `si_position_history.json`
beginnt erst 15.05.2026 (settlement) / 27.05.2026 (`pub_date`) —
Export-Records mit früherem Entry-Datum haben strukturell keinen validen
SI-Wert. Das ist **kein Fehler**, sondern eine akzeptierte
Sammel-Untergrenze.

**Änderungs-Protokoll (bindend ab 12.09.2026, analog §4-Exit-B.1):** Keine
Änderung an diesem Registrierungsblock ohne datierten Protokolleintrag,
der die Änderung und ihren Grund festhält.

### PAPER-BEFUND (Svoboda/Kapounek/Albrecht 2026, ausgewertet 12.07.)

**Quelle:** *North American Journal of Economics and Finance* 2026, DOI
`10.1016/j.najef.2026.102637`; frei als Working Paper mendelu 104/2025.
Untersucht **genau unser Setup**: 70 NASDAQ-Small-Caps 2018–2021, rare-event-
Logit.

**Kern-Erkenntnisse:**

- **ZIEL-DEFINITION:** Squeeze = Peak **> +30 % in 1 Handelswoche** UND
  **SI-Rückgang ≥ 20 %** UND Attention-Spike. Misst die **WAHRSCHEINLICHKEIT**
  (binär), **NICHT** den Return → erklärt unsere Nullbefunde: **Häufigkeit ≠
  Rendite-Edge** (§8h). → Schritt A.
- **SI-SCHWELLEN-BUCKETS (stärkster Fund, nur diese 3 signifikant):** SI-Zuwachs
  **7–17 % → +78 %**, **17–25 % → +210 %**, **> 25 % → +10 %** (Squeeze-
  Wahrscheinlichkeit). → Schritt B (Buckets statt linear).
- **VORLAUF:** SI **+1 % einen Monat voraus → +3,9 %**; stärkster Effekt bei 1
  Monat, signifikant bis 6 Monate. Stützt den prospektiven Positions-Delta-Pfad.
- **MOMENTUM > REVERSAL:** Effekt **stärker bei vorherigem AUFWÄRTStrend**;
  Reversal nur kurzfristig. → `entry_past_return_5d` **Haupthypothese POSITIV**
  (Momentum). → Schritt C.
- **DÄMPFER / GRENZEN:** Institutional Ownership dämpft (**−6 % je +1 %**);
  **Marktkap + Markttrend NICHT signifikant**; bei **Marktrückgang > 3 % ist das
  Modell blind**. → §6g/§6h.

**Konsistenz zur Auffanglinie:** Das Paper belegt eine Edge auf **fremden
Daten** für ein **binäres Wahrscheinlichkeits-Ziel** — hebt unsere Return-
Auffanglinie NICHT auf. Verwertung strikt **Out-of-Sample auf unseren Daten mit
literatur-abgeleiteten Schwellen** (= `monster_score`-Overfitting-Schutz §8e).

### LITERATUR-KONSENS (S&P Global / State Street / diverse 2026)

Kombi-Ansatz **Constraint × Katalysator × Peak-Ziel gleichzeitig** ist der
Profi-Kurs. Einziger dokumentierter Profi-Vorsprung: **bezahlte Lending-Daten**
(Utilization, Cost-to-Borrow-Tick, $10–50k/Jahr). Gratis-Zugang gibt es nicht.
Synthetische Utilization ist im Bau-Kandidaten-Pool. **Verweis (10.10.2026):**
siehe „IBKR-Spur (Borrow-Daten)" (oben in Section 4) + `open_items.json`-ID
`ibkr-borrow-data-spur` — eine mögliche Fee-Rate-Quelle (IBKR-Feld `7637`),
Utilization selbst bleibt ohne gefundene freie API.

### BAU-KANDIDATEN (nach Re-Test-Befund, kein Termin, keine Priorität)

- Synthetische Utilization (Substitute für bezahltes Lending-Feed)
- Katalysator-Gating (nur trade wenn Katalysator im 7-Tage-Fenster)
- Exit-Mechanik-Spec (Trailing statt Fest-Stop, B.2-Konsequenz)
- Reddit-Velocity (post-30.06.-Kandidat, Attention-Signal)
- 424B-Dilution-Filter (Regel-Screen, nicht Score-Feature)

### Auswertungs-Historie (belegt)

- **30.06. Endpunkt-Return (#394):** 0/15 Holm bei k=15. Earliness-Re-Test
  (n=78, AUC 0.77 aus 13.05.) fällt OoS auf 0.47–0.52.
- **01.07. Exit-Timing B (#395):** B.1 (Score≥70, n=110) Δ(5d−10d) +3.81 pp
  CI [+1.00,+6.63] roh-p 0.0057; Δ(3d−10d) +4.67 pp roh-p 0.0073 — **erster
  echter Punktschätzungs-Vorteil**, aber nicht Holm-belegt → „Hinweis, nicht
  belegt". Re-Test n≥250 ~Ende Sept. B.2 (Fest-Stops): 4 Holm-Rejects — feste
  Stops schaden systematisch.
- **04.07. Hypothese C (Peak-Ziel):** 0/6 Holm. **ERLEDIGT.**
- **15.07. ki_signal-Edge-Re-Test (n=55 gereift, Fenster 11.–30.06.):** **KEIN
  belegter Effekt** (Slot-29-Erfolgsdefinition auf beiden Seiten verfehlt).
  Registriert: Primär (ki_signal als Ranker für `return_10d`, AUC via
  `mann_whitney_u_auc`) + Sekundär (OLS-Setup-bereinigtes Residual) × Cluster
  with/without → Holm **k=4**.
  - **Primär:** AUC **0.606**, Bootstrap-CI **[0.434, 0.768]**, roh-p **0.28**.
  - **Residual (Setup-bereinigt):** AUC **0.582**, CI **[0.399, 0.760]**, roh-p **0.40**.
  - **Holm k=4 → 0/4 Rejects** (auch Bonferroni 0). CI-Untergrenze beide < 0.5.
  - **Deutung (wichtig, kein toter Faden):** beide Punktschätzungen lehnen
    **POSITIV** (roh + Setup-bereinigt) — ki_signal rankt Gewinner leicht über
    Verlierer. Richtung stimmt, nur bei diesem n nicht belegt → **Re-Test-
    Kandidat**, nicht verworfen.
  - **Die drei Engpässe (wichtiger als der Nullbefund):** (1) **WIN-Bucket nur
    n=13** (nicht die 55!) — DER Präzisions-Killer, macht die CIs breit. (2)
    **r=0.691 Redundanz zu Setup** (frisch gemessen) → Nullbefund ist ehrlich
    „mit Setup redundant", **nicht** „KI wertlos". (3) **Ein-Regime-Fenster**
    (Low-VIX-Bull, 3 Wochen, Kandidaten-Returns netto negativ, Median −6,3 %) →
    selbst ein signifikanter Befund wäre schwach generalisierbar.
  - **Methodik-Notiz:** `cluster_followups = 0` (post-#346 keine Preis-Einfrier-
    Cluster mehr) → der #391-Doppellauf **kollabiert**, with/without identisch.
    **k=4 bewusst behalten** (konservativ, keine nachträgliche Schmälerung).
  - **Re-Test-Bedingung (datengetrieben, ersetzt „~Mitte Aug"): WIN-Bucket ≥ 20
    UND zweites Marktregime im Sample.** Confound-Anker #2 (LLM-Fallback-Mix) ist
    ab #440 messbar (`ki_sentiment_source`).

---

## 6) CODE-HYGIENE-BACKLOG (Status je Punkt)

### 6a. Alt-`finra_data.si_velocity` → `si_shares_per_day` umbenannt
**Status: ✅ ERLEDIGT (15.07.).** Displayfeld hatte irreführenden Namen:
`(newest_SI − oldest_SI) / len(history)` ist **Shares/Tag absolut**
(~90-Tage-FINRA-History), keine „Velocity" im Änderungsraten-Sinn
(Nomenklatur-Falle §8m). Umbenannt zu `si_shares_per_day`; Label
„SI Velocity (tägl. Ø)" → **„SI-Volumen Δ (tägl. Ø)"**. Ein PR, keine
Staffelung (Diagnose 15.07.).
**Korrektur der früheren Touch-Flächen-Angabe (war falsch, grep 09.07.):**
nicht 7 Reads, sondern **5** (`_wl_card_payload`-Payload, `_earliness_pts_v1`
dormant, v1-Display-Row, v2-Display-Row, Frontend-JS) + Write + 3 Test-Fixtures;
**KEIN KI-Boost-Konsument** (die frühere Angabe war unzutreffend — der einzige
Nicht-Display-Read ist der dormante V1-Rollback-Pfad bei
`EARLINESS_FORMULA_VERSION==1`). `si_velocity_pub` (Backtest, relativ,
pub_date-gefiltert) **unangetastet** — dessen Look-Ahead-Guard nutzt strikte
`_pub`-Muster, keine Überlappung. Kein Alt-Backtest-Feld betroffen
(`si_velocity` nie in `backtest_history.json`); app_data.json wird pro Lauf
komplett neu geschrieben → keine Migrations-Lesart nötig. Golden mit-aktualisiert
(2 Zeilen, rename-only).

### 6b. 5 andere bewegliche US-Feiertage algorithmisch berechnen — ✅ ERLEDIGT (PR #577)
**Status: ERLEDIGT.** Alle 10 NYSE-Feiertage/Jahr (die 5 vormals bis 2027
hartkodierten — MLK Day, Presidents Day, Memorial Day, Labor Day,
Thanksgiving — plus Good Friday [schon seit #407] plus die 4
Fixdatum-Feiertage mit Wochenend-Beobachtung) sind jetzt algorithmisch via
Nth-Weekday-of-Month-/Last-Weekday-of-Month-Formeln, Range 2020–2050, Python
(`config.py`) UND JS-Spiegel (`generate_report.py`) synchron. Exakt gegen die
vormals hartcodierte 2025–2027-Liste verifiziert (Mengen-Diff leer) +
Python/JS-Vollparität via Node-Ausführung. Kein manueller Pflege-Bedarf mehr
für 2028+.

### 6c. News-/FDA-Katalysator (Look-Ahead-Quelle geklärt, Score-Entscheidung offen)
**Status: Quelle GEKLÄRT (06.10.2026); Score-Faktor-Entscheidung OFFEN.**
Voraussetzung war eine belegbar **point-in-time** verfügbare News-/FDA-
Announcement-Quelle. Commit `513fa5f2` (19.07.2026, „material_8k_events … §6c")
hat die Diagnose durchgeführt und SEC-EDGAR-8-K (CIK-anchored,
`acceptance_datetime` ≤ Report-Zeit) als point-in-time-Quelle identifiziert +
dafür ein forward-only Sammelfeld gebaut (REINE Analyse-/Outcome-Persistenz,
Look-Ahead-Konvention bewusst eingefroren, NIEMALS als Score-Feature gelesen).
Offen bleibt die NEUE Frage: ob aus `material_8k_events` je ein Score-Faktor
gebaut wird — bisher bewusst nicht angegangen.

### 6d. `entry_past_return_5d` Stufe-B-Backfill (Paper C) — ✅ ERLEDIGT (#442/#443/#444 + Live-Lauf 17.07.)
**Status: ERLEDIGT.** #402 war Stufe A (Live-Vorwärts). Stufe B — der einmalige
yfinance-Backfill von `entry_past_return_5d` über die v4-Alt-Records — ist gebaut
(#442, Skript + Workflow), diagnostiziert (#443, Gate-Diff-Logging), kalibriert
(#444, Verteilungs-Gate) und **LIVE DURCH** (`5d8e78d`, **465/470 gefüllt**, Gate
PASS). **Warum legitim war (Sammel-Raten-Diagnose 15.07.):** der Past-Return ist
aus **historischen Adj-Close-Preisen** rekonstruierbar → **reine Preis-Größe, kein
Modell-State, kein Look-Ahead** (split-safe) — der **einzige** echte Seed-Analog
zum SI-2-Punkte-Trick, ohne Populations-Wechsel. **Abgrenzung blieb strikt:**
`conviction_score`/`ki_signal_score` **NICHT** backgefüllt (Modell-Zustand zum
Entry = Look-Ahead). **Beweiswert-Grenze (§4/§8z1):** die 465 Records sind
**explorativ/IN-SAMPLE**, ersetzen NICHT den vorwärts gesammelten OoS. **Rückweg:**
`mode=undo` (Manifest-basiert, nullt nur die 465).

### 6e. yfinance-Cap-Aufhebung nach 1.5.x-Stabilisierung
**Status: OFFEN.** #403 hat `>=1.4.1,<1.5` gecappt. Sobald 1.5.x als stabil
belegt: Cap schrittweise lockern. Kein Termin — wartet auf externes Signal.

### 6f. v1/v2-Render-Pfad → reines Jinja — bewusst VERWORFEN (Easy-Entscheid 07.10.2026)
**Status: VERWORFEN.** `generate_html_v2()` delegiert an v1; v1-Löschung
erfordert `templates/page.jinja` + `_wl_full_card_html`-Umbau (§7g). Großer
Umbau, kein Trading-Wert — Easy-Entscheid 07.10.2026: nicht angehen.

### 6g. Institutional-Ownership-Faktor (Paper-Dämpfer) — Anzeige-Key-Fix + Sammelfeld DURCH, Hypothesen-Runde offen
**Status: Anzeige-Key-Fix ERLEDIGT (#510–#512, 07.08.); Sammelfeld LIVE seit
10.08.2026 (korrigiert 06.10.2026); Hypothesen-Runde NACH Paper C weiterhin
OFFEN.** Svoboda et al.: hoher Institutional-Ownership
**dämpft** (**−6 % je +1 %**) — der erste Faktor, der GEGEN einen Squeeze spräche.
Datenquelle yfinance **`heldPercentInstitutions`** (ein BRUCH); die früher
verdrahteten Keys (`institutionHeldPercentOutstanding`/`institutionsPercentHeld`)
existierten im `.info`-Dict NICHT (Wegwerf-Probe #510: `<KEY-FEHLT>` 33/33) → #512
gefixt, Coverage **30/30** am Universum, Streuung voll, quartalsweise 13F-Latenz
bleibt (forward-only unproblematisch). Sammelfeld
`inst_ownership_history.json` (**forward-only, S10_OBSERVED-additiv**,
`none=unbeobachtbar`, **NIE 0**) läuft seit 10.08.2026 (`config.py
INST_OWNERSHIP_HISTORY_ENABLED`/`_FILE`, `generate_report.py:3643-3731`) — beide
unten genannten Caveats sind darin bereits umgesetzt. Weiterhin **kein
Score-Effekt ohne OoS-Beleg** — die Hypothesen-Runde selbst bleibt Kandidat NACH
Paper C.

**Zwei Registrierungs-Caveats (VOR jedem Sammelfeld-/Score-Schritt entscheiden):**
1. **Werte > 100 % roh einfrieren** — bei stark geshorteten Titeln real (HTZ 118,7 %;
   Shorts erzeugen synthetische Bestände), NICHT deckeln.
2. **Farb-Semantik hoch = grün kollidiert mit der Dämpfer-These** — die Karte färbt
   aktuell **hohe** Inst-Beteiligung **grün** („gut"), Svoboda sagt aber hoch =
   Dämpfer (für einen Squeeze schlecht). **Bewusst NICHT geändert** (Fundstelle
   `generate_report.py` ~5602/6139, Schwellen 60/30) — erst nach der Hypothesen-Runde
   entscheiden.

**Zusatz-Hinweis (Lit-Check 21.08.2026):** Eine zweite, unabhängige Studie
(Bhojraj/Yu/Zhao 2026, *Management Science*, „In Search of Shares: Benchmarked
Ownership, Short Covering, and Price Efficiency") liefert einen zu Svoboda
ergänzenden, aber NICHT identischen Befund: hohe benchmark-gebundene/passive
institutionelle Beteiligung ist mit stärkerem Kurs-Überschießen bei hoch
geshorteten Aktien um Gewinnankündigungen verbunden — verstärkt also Preis- und
Volumenwirkung von Short-Covering. Svoboda misst die Wahrscheinlichkeit eines
Squeeze-Auftretens generell; Bhojraj misst die Größe des Überschießens bei
bereits laufendem Short-Covering — zwei unterschiedliche Zielgrößen, kein
direkter Widerspruch, aber ein zweiter Hinweis darauf, dass institutionelle
Beteiligung nicht als einheitlicher Block behandelt werden sollte (Typ aktiv
vs. passiv/indexgebunden könnte gegensätzlich wirken).

**Praktische Konsequenz für die künftige Hypothesenprüfung:** Falls die
H-Kapitaldruck-Hypothese getestet wird, sollte die Erwartung nicht
„institutionelle Beteiligung dämpft immer" lauten — ein Nullbefund könnte
gemischte, sich aufhebende Effekte verdecken statt „keine Wirkung" zu bedeuten.
Aktuell datenseitig NICHT umsetzbar (13F-Daten unterscheiden i. d. R. nicht
sauber zwischen aktiv/passiv) — reiner Dokumentations-Vermerk für später, kein
Sammelfeld-Ausbau jetzt.

### 6h. Crash-Filter / Markt-Blind-Zone (Paper-Grenze)
**Status: ✅ ERLEDIGT mit ANZEIGE-BANNER (08.08.2026), harter Filter BEWUSST
VERWORFEN.** Paper: bei **Marktrückgang > 3 %** ist das Modell **blind**.
Diagnose 08.08. (read-only, §6h): Screener/Score/Exits reagieren **gar nicht**
auf die Marktlage; Conviction-Regime + Pushes reagieren **nur via VIX** (WARN 25
/ PAUSE 35), nie auf den reinen Tages-SPY-Move. Im beobachtbaren Fenster
(13.07.–07.08.) blieb VIX 14,9–20,7 (immer < 25) → der Blind-Fleck wurde **nie
ausgelöst**, kein Live-Beweis für Rausch-Verhalten.

**Entscheidung (Easy):** **reines Anzeige-Banner, KEIN harter Filter, KEIN
Push-Gate, KEINE Score-Änderung.** Begründung: ein Panik-Tag ist der Moment zum
**Hinsehen**, nicht zum **Auto-Unterdrücken** — ein harter Crash-Ausschluss
würde echte, gerade in Panik zündende Squeezes (Short-Covering in stark
geshorteten Namen) **töten**. Der ursprüngliche Paper-Kandidat (Regel-Screen)
ist damit **verworfen**, nicht nur verschoben.

**Gebaut:** dezenter Header-Banner (`#hdr-market-stress`, Muster Staleness-Pill,
anzeige-only, fail-soft) leitet den heutigen `^GSPC`-Tagesmove aus dem **bereits
gefetchten** `spx_daily_perf` ab (KEINE neue Datenquelle, kein neuer Fetch) und
flaggt zwei Stufen: **≤ −3 %** rot „Markt-Stress … besonderer Vorsicht", **−3 %
< move ≤ −2 %** gelb „Markt schwach … vorsichtig", sonst versteckt. Fail-soft:
SPY nicht ermittelbar / None / NaN → `null` → **kein Banner, kein Fehler, Lauf
unverändert**. Schwellen `MARKET_STRESS_STRONG_PCT` / `MARKET_STRESS_MILD_PCT`
in `config.py`. **Kein** Score-/Push-/Filter-/Export-Touch (per Test + git diff
verriegelt). Test `scripts/mock_test_market_stress_banner.py` (31 Cases:
Ziel-Mechanik durch den Render-Pfad, Fail-soft, Klassifikation, Isolation).

### 6i. Paper-Schritte A **UND B** — ✅ ENTBLOCKT (FINAL REVIDIERT, 13.07.)
**Status: BLOCKER REVIDIERT + GEBAUT (#423, 13.07.).** Der frühere gemeinsame
Daten-Blocker (A und B brauchen die ausstehende SI-**Positions**-Zeitreihe) ist
aufgelöst — nicht über kostenpflichtige Profi-Feeds, sondern über eine
**gratis** yfinance-Quelle im eigenen Werkzeug.

**Externe Quellen erschöpfend als untauglich belegt (Proben #420/#421):**
- **FINRA `EquityShortInterest`-API:** anonym erreichbar, liefert
  `currentShortShareNumber` + `settlementDate` — aber **OTC-only**
  (`marketCategoryCode`-Verteilung, TEST 1–4 #421), gelistete Ticker fehlen.
- **Nasdaq:** nur Nasdaq-gelistete, NYSE `null`; volle Historie Paid (Data Link).
- **Finnhub:** Short-Interest nur Premium.
- **Namens-Falle (bleibt gültig, §8m):** internes `finra_data.history` = FINRA
  **Reg SHO Daily Short VOLUME** (`CNMSshvol`), **NICHT** die ausstehende
  Position.

**Auflösung (Durchbruch, Probe #422):** **yfinance `.info` liefert die POSITION
gratis** — `sharesShort` + `sharesShortPriorMonth` + `dateShortInterest` +
`sharesShortPreviousMonthDate`. Read-only-Probe **4/4 Ticker befüllt**, echte
Settlement-Daten (30.06. + 29.05.), Positions-Größen (`sharesShort` ≪
`floatShares` → Bestand). Alle vier Felder im **selben `.info`-Dict** → **kein
Extra-Call**.

**Gebaut (#423, Guardian ✅ + 98 CI-Tests grün):** `si_position_history.json`
(Schema/Seed/Dedup/Retention/Look-Ahead in §1 + §7h). **Konsequenz:** Schritt A
(`squeeze_event` mit echtem SI-Rückgang ≥ 20 %) **und** Schritt B (SI-Zuwachs in
Paper-Buckets, 1-Monats-Positions-Delta) sind **daten-seitig möglich** — beide
messen die Position (Bestand). **Kein Backfill der ~470 v4-Alt-Records** (keine
time-queryable Gratis-Historie — die Serie ist forward-only; **betrifft die
SI-Positions-Serie, NICHT `entry_past_return_5d` aus §6d** — jenes ist eine
rekonstruierbare Preis-Größe und wurde deshalb backgefüllt). **Vorbedingung =
reine Sammelzeit**: n≥40 paper-treue Squeeze-Events mit messbarem SI-Rückgang
**~2–3 Monate**; der Seed liefert Startpunkte sofort. **Nächster Schritt nach
Sammelzeit: A/B-Auswertung gegen `si_position_history.json`** (OoS, §5).

**`si_velocity_pub` bleibt getrennt** (Tages-Volumen-Momentum) — Paper-Schwellen
7/17/25 % werden **nicht** daraufgelegt (§8m). **Restkante — ✅ sichtbar gemacht
(PR #578, 07.10.2026):** falls yfinance `dateShortInterest` künftig als
`Timestamp` statt epoch-int liefert, wird der Punkt weiterhin fail-soft
übersprungen (Rückgabewert/Kontrollfluss unverändert) — aber jetzt mit genau
einer `log.warning`-Zeile pro Lauf statt stillem Datenverlust (§3).

**Lesson (§8o):** Die Lösung lag im **eigenen Werkzeug** (yfinance spiegelt die
FINRA-SI-Position gratis) — gefunden erst **nach** erschöpfendem externem
Quellen-Check und **Verifikations-Probe (#422) statt Blind-Bau**.

### 6j. `apple-touch-icon` fehlt (Shell zeigt ggf. Blank-Screenshot beim Re-Add)
**Status: ERLEDIGT (PR #462, 19.07.2026) — technisch verifiziert 29.09.2026**
(valides 180×180-PNG `apple-touch-icon.png` im Repo-Root, korrekter
`<link rel="apple-touch-icon" sizes="180x180" ...>`-Tag an allen vier
Fundstellen, grüner Regressionstest `mock_test_bootstrap_shell_phase1.py`;
kein visueller iPhone-Live-Check — Easy verzichtet darauf, technische
Bestätigung reicht). Ursprünglicher Befund (Guardian-Hinweis aus #436): das
Repo hatte nur `favicon.svg`, kein `apple-touch-icon`-PNG, iOS nahm beim
„Zum Home-Bildschirm hinzufügen" mangels Icon einen Seiten-Screenshot.
**Randnotiz (29.09.2026):** der Icon-Tag lebt an **zwei getrennten
Stellen** — `templates/head.jinja` (speist `app.html`, die volle Seite)
und ein separater `_SHELL_HTML`-Plain-String in `generate_report.py`
(speist `index.html`, die Bootstrap-Shell). Beide aktuell identisch, aber
**keine gemeinsame Quelle** — bei einer künftigen Icon-Änderung müssen
beide Stellen synchron gepflegt werden. Kein akutes Problem.

### 6k. Stand-Zeile zeigt beide Zeiten — ✅ ERLEDIGT (#465, 21.07.2026, korrigiert 06.10.2026)
**Status: ERLEDIGT.** Die Header-Zeile zeigte früher nur die Marktdaten-Zeit
(„Stand: HH:MM"); weil die KI-Zeile stündlich vorläuft, wirkte die Seite morgens
scheinbar „eingefroren", obwohl die Zwei-Run-Architektur genau so gedacht war
(§3-Klarstellung). PR #465 (`d4b80983`, 21.07.2026, „Karten-Klarheit —
Beschriftungs-Präzision") rendert die Zeile seither **zweiteilig** —
„Marktdaten HH:MM · KI HH:MM" via client-seitigem `_renderKiTime()` aus
`_AGENT_SIGNALS.updated` — die Divergenz ist damit selbsterklärend statt
verdächtig. Reine Anzeige, kein Datenpfad. Nur hier nie als erledigt
nachgetragen worden (Diagnose 06.10.2026).

### 6l. Cockpit Stage 3 — obsolete `.sb-`-Reste im Karten-Bereich — bewusst VERWORFEN (Easy-Entscheid 07.10.2026)
**Status: VERWORFEN.** Kein Termin, nie als toter Code verifiziert — Easy-
Entscheid 07.10.2026: nicht angehen.
Backlog-Anker für den Stage-3-Cleanup des Karten-Cockpit-Redesigns. **Quelle des
3-Stage-Plans bleibt `CLAUDE.md` (Sektion „Karten-Cockpit-Redesign", Stage-Tabelle,
Stage 3 = „offen") — hier KEINE Kopie der Tabelle** (zwei Volltexte driften
auseinander; genau deshalb fehlte dieser Anker bisher). Dieser Eintrag trägt nur
Backlog-Status + Scope-Warnung.

**Auslöser (BEFUND, kein Auftrag):** `CARD_COCKPIT_ENABLED = True` (`config.py:70`,
Stage 2 scharf) macht den Cleanup **erst aktivierbar** — vorher wäre `.sb-` im
Karten-Bereich der lebende Pfad gewesen.

**Ist-Zustand (per grep gegen `main` verifiziert; Zeilennummern können durch
spätere Commits verschieben):** `_score_block_inner_html` noch definiert
(`generate_report.py:4769`) mit **2 Call-Sites** (`:5260`, `:5798`); `.sb-`-Klassen
(`sb-row`/`sb-num`/`sb-conf`/`sb-lbl`/`sb-fill`/`sb-delta`) in `generate_report.py`
**und** `templates/head.jinja` vielfach vorhanden.

**Scope-Warnung (ZWINGEND vor jedem Entfernen — blind greppen = Bug):**
- **Karten-Scope vs. Methodik-Panel-Scope MUSS getract werden.** Die Methodik-Panel-
  Nutzung (`.score-block-list .sb-lbl` u. ä.) bleibt **LEBEND** — eigener Konsument,
  eigenes CSS-Scope.
- **`.sb-conf-*`** (`-robust`/`-mittel`/`-prov`/`-heur`, aus **PR #171**) werden im
  Cockpit **wiederverwendet** (auf `.cockpit-pillar-value` / `.cockpit-donut-number`,
  siehe CLAUDE.md-Sektion „Konfidenz-Wasserzeichen") → **nicht** entfernen.
- **`.sb-row` / `.sb-num`** sind bewusster **Rollback-Fallback** (Flag-OFF-Pfad).
- **OFFEN / NICHT getract:** ob die Karten-`.sb-`-Vorkommen tatsächlich toter Code
  sind, ist **nicht** verifiziert — das ist Teil der Stage-3-Diagnose, keine hier
  behauptete Tatsache.

### 6m. `_trading_days_elapsed` feiertags-blind → `return_10d` füllt 1–3 Tage zu früh — bewusst VERWORFEN (Easy-Entscheid 07.10.2026)
**Status: VERWORFEN.** Bewusster, im Code-Docstring selbst dokumentierter
Kompromiss — Easy-Entscheid 07.10.2026: nicht angehen. Ursprünglich Backlog-
Befund (04.08.2026).
`_trading_days_elapsed` (`ki_agent.py:367`) zählt Handelstage seit Entry als
**Mo–Fr strikt**, ohne US-Feiertage abzuziehen. Folge: bei einem Feiertag im
Fenster meldet die Funktion 10 „Handelstage" schon nach 1–3 Kalendertagen zu
früh → `update_backtest_returns` schreibt `return_10d`, obwohl real erst 9 echte
Handelstage vergangen sind. Betrifft **nur** das Reife-Signal `return_10d`, nicht
das Rolling-Fenster von `max_gain_pct`/`max_drawdown_pct` (die laufen kalender-
basiert über `days_old <= 14`).

**Warum jetzt nur Backlog, nicht Fix:** Der Matured-Export (§7 / PR dieser
Session) umgeht das Symptom bereits — sein Reife-Gate #2 verlangt zusätzlich zu
`return_10d` ein `days_old > 14` **Kalendertage**, wodurch das zu frühe
`return_10d`-Füllen für den Export folgenlos bleibt (Rolling-Felder sind bei
Kalendertag 15 garantiert final). Ein echter Fix (Feiertagsliste in der
Trading-Day-Zählung berücksichtigen, analog #407/§6b) würde `return_10d` selbst
korrekt spät füllen — betrifft dann auch das Backtest-Panel und die
return_10d-basierten Auswertungen. Vor dem Bau: prüfen, ob die
`config.US_MARKET_HOLIDAYS`-Menge (heute nur bis 2027 hartkodiert, §6b) den
Zähl-Zeitraum abdeckt. Kein Trading-Wert, Genauigkeits-Hygiene.

### 6n. ≥90-Score-Bucket-Persistenz seit 29.06.2026 (Beobachtungspunkt, 29.08.2026)
**Status: OFFEN. Kein Auftrag, kein Termin — reiner Beobachtungspunkt für die
künftige Hypothesen-Runde, NICHT vorregistriert.** Setup-Score ≥90 ist seit
W27 (29.06.) durchgehend selten (0–5 % der Top-10-Einträge pro Woche),
gegenüber 0–12,5 % in den ersten Live-Wochen (29.05.–26.06.) — keine Erholung
bis heute. Der breitere ≥70/≥80-Bereich hat sich dagegen seit Ende Juli (W31)
erholt und liegt aktuell auf/über Anfangsniveau — das ist **kein** allgemeiner
Score-Rückgang, sondern eng auf die absolute Spitze begrenzt.

**Ausgangshypothese (unbewiesen, nicht vorregistriert):** zeitliche Koinzidenz
mit dem `market_regime`-Feld (aus `_market_regime_from_spy()`, reine Logging-
Persistenz ohne Score-Rückkanal laut Code), das exakt ab W29 (13.07., mit
Verzug zum Score-Einbruch) von `"bull"` auf `"neutral"` kippt und dort bleibt.
`score_timing` (Momentum-/RS-vs-SPY-Komponenten) fällt parallel von ~15–21 auf
~10–14, erholt sich dann zeitgleich mit der ≥70/80-Erholung. Kausalität nicht
belegt, nur Koinzidenz zweier eigenständig berechneter Felder. Für spätere,
sauber vorregistrierte Prüfung vormerken, nicht vorab als Erkenntnis behandeln.

**Ausgeschlossen als Erklärung (bereits geprüft):** `score_normalization_version`
(konstant), `combo_bonus`/`score_trend_bonus`/`agent_boost_factor`/
`perfect_storm_mult`/`finra_bonus` (keine Abwärtstendenz), `pool_size` (keine
Verengung). K.o.-Filter-Schwellen (`config.py`) wurden **nicht** auf
Änderungshistorie geprüft — offene Lücke.

### 6o. Validierungs-Badge-Verstärkung (UI, nicht gebaut, Backlog)
**Status: OFFEN. Kein Auftrag, kein Termin — Backlog-Idee, niedrige Priorität,
reine UI-Frage ohne Score-/Filter-Bezug.** Externer Qualitätscheck (17.09.2026)
bemängelte, dass unvalidierte/falsifizierte Scores (z. B. „Monster 94 · OoS-
kollabiert") die Zahl visuell stärker wirken lässt als den danebenstehenden
Validierungsstatus — psychologisch könnte „94" wie ein starkes Signal wirken,
obwohl der Text direkt daneben Gegenteiliges sagt. Die bereits vorhandene
`SCORE_STATUS_LABELS`-Badge-Logik könnte hier verstärkt werden (z. B. Badge
prominenter/näher an der Zahl, oder Zahl selbst visuell gedämpft bei
falsifiziertem/kollabiertem Status). Nicht umgesetzt, nicht priorisiert über
„niedrig" hinaus.

### 6p. Alpha-Pipeline (großes Konzept, bewusst zurückgestellt)
**Status: ZURÜCKGESTELLT. Kein Termin, kein Teil-Bau ohne Edge-Beweis.**
Externer Qualitätscheck (17.09.2026) schlug einen kompletten Umbau zu einem
Cross-Sectional-Alpha-Ranking-System vor (Layer-Architektur Raw Data → Alpha-
Faktoren → Excess-Return-Prognose → Position-Sizing → Portfolio, mit Walk-
Forward-Validierung und Research-Lock). Konzeptionell fundiert, aber die
Voraussetzung (eine bewiesene Edge, die es zu rangieren gäbe) ist aktuell nicht
erfüllt — Exit-B.1 bei n unter 250, H5 methodisch eingefroren aber nicht
zellenreif (siehe §4/§5 oben). **Entscheid: NICHT bauen, solange keine der
beiden laufenden Vorabregistrierungen ein positives, Holm-signifikantes
Ergebnis zeigt.** Aus dem Vorschlag bereits isoliert umgesetzt: SPY-Benchmark-
Vergleich (`return_Nd_vs_spy`, PR #554, 18.09.2026). Der Rest des Konzepts
bleibt als Ganzes zurückgestellt.

### 6q. Deskriptive MFE/MAE-Bestandsaufnahme nach Score-Bucket (26.09.2026, Beobachtungspunkt)
**Status: OFFEN. Kein Auftrag, kein Termin — reine Bestandsaufnahme für die
künftige Hypothesen-Runde, KEINE Vorabregistrierung, KEIN Ersatz für §4
Exit-B.1.** Score-Bucket × `max_gain_pct` (MFE-Äquivalent) /
`max_drawdown_pct` (MAE-Äquivalent) über 352 `provenance=forward`-Records aus
`matured_backtest_export.jsonl`. Median MFE steigt NICHT monoton mit dem
Score-Bucket (16.4→22.2→23.1→21.7→23.6 über die Buckets 40–90), Mean MFE
dagegen deutlich klarer steigend (20.6→27.8→30.5→36.4→42.1) — wachsende
Rechtsschiefe bei höheren Score-Buckets, reine Verteilungsbeobachtung. Der
90–100-Bucket (n=6) ist zu klein für jede Aussage.

`score_timing` zeigt ein klareres Muster als `score_catalyst` (Timing:
Median MFE 19.6→21.4→29.4 über drei Terzile; Catalyst: praktisch kein
Unterschied zwischen aktiv/inaktiv) — möglicher Beobachtungspunkt für die
künftige H5-Interaktionsauswertung, NICHT vorab als Erkenntnis werten.

**Wichtige Einschränkungen:** Sample fast ausschließlich
`market_regime=neutral` (322/352), 0 `bear`-Records — keine Aussage über
andere Marktregime möglich. Ticker wiederholen sich stark (z. B. WOLF 6–8×
im Sample) — effektive unabhängige Stichprobengröße kleiner als die
Zeilenzahl. Kein Multiple-Testing korrigiert (> 20 Einzelvergleiche) —
bewusst, da reine Bestandsaufnahme. Brutto-vs-Netto-Vergleich (`max_gain_pct`
vs. `max_gain_pct_net`) aktuell nicht belastbar (nur 70/352 Records mit
Netto-Feld, Reifegrenze aus PR #549 noch nicht erreicht).

---

## 7) ARCHITEKTUR-ANKER

### 7a. Analyse-Persistenz-Felder — Look-Ahead-Konvention

Vier Felder im `backtest_history.json` sind **reine Analyse-/Outcome-Persistenz**,
**NIEMALS Score-Feature aus dem Backfield lesen** (Konvention seit #402):

| Feld | PR | Zweck | Live-Score-Read (falls je nötig) |
|---|---|---|---|
| `max_gain_pct` | #397 | Peak im ≤10-TD-Fenster | Rolling-Update-Slice, nicht Backfill-Feld |
| `entry_past_return_5d` | #402 | Momentum-/Reversal-Substrat | `s["close_5td_before_entry"]` (Enrichment) |
| `days_to_earnings` | #404 | Katalysator-Nähe | `s["earnings_days"]` (Enrichment) |
| `si_velocity_pub` | #409 | SI-Volumen-Rate über 3 Publikations-Reports | `s["finra_data"]["history"]` mit eigenem `_compute_si_velocity_pub`-Aufruf |

**Grund:** Backgefüllte Alt-Records würden Trainings-/Test-Overlap erzeugen →
Overfitting, kein echter OoS-Nachweis. Verankert per Konsumenten-Isolations-
Test (grep über `generate_report.py`/`ki_agent.py`/`health_check.py` muss leer
bleiben). **`si_position_history` (#423)** folgt derselben Konvention, liegt aber
in eigener Datei (§7h).

### 7a-bis. `config.COLLECT_STATUS_FIELDS` — Display-Reads von Backtest-Feldnamen (Weg-A, #412)

Das Status-Panel muss Backtest-Feldnamen **anzeigen** — die Look-Ahead-Guards
verbieten aber jedes Namens-Literal im Score-Pfad-Source. **Lösung (Weg A):**
Feldnamen + Labels + Status in `config.COLLECT_STATUS_FIELDS`, zur Render-Zeit
als JS-Konstante injiziert (`json.dumps`) → kein Feldnamen-Literal im Source,
Guards bleiben grün. **Muster für JEDEN künftigen Display-Read von Backtest-
Feldnamen** (config ist nicht guard-überwacht). Verankert per Test-Assertion A8.

### 7b. `scripts/business_days.py` — Handelstags-Arithmetik

Pure-stdlib-Modul mit `next_trading_day(d)` und `finra_publication_date(
settlement_date, offset=None)`. Nutzt `config.US_MARKET_HOLIDAYS` als **Single-
Source-of-Truth**. **Bewusst kein Cross-Import** in `cluster_purge` (strikte
Reihenfolge-Disziplin für die 30.06.-Auswertung).

### 7c. `finra_publication_date` = settlement + 7 US-Handelstage

FINRA Rule 4560. Konstante `FINRA_PUB_OFFSET_BUSINESS_DAYS = 7` in `config.py` —
zentral anpassbar (SR-FINRA-2026-012 plant höhere Frequenz / kürzeren Delay).
Konsument seit #423 auch `si_position_history` (pub_date je Punkt).

### 7d. Good Friday algorithmisch (Meeus) — Doppel-Spiegel

`config.US_MARKET_HOLIDAYS` (Python) UND `US_HOLIDAYS`-Array in
`generate_report.py` (JS, `_goodFriday(year)` + `_GOOD_FRIDAYS`) müssen **bit-
identisch** bleiben. Verankert im Test `mock_test_good_friday`.

### 7e. Auswertungs-Chain (Stats-Helpers + cluster_purge)

- `stats_helpers.py` (#389 AUC/Mann-Whitney-U + Yates; #390 Bonferroni +
  Holm-step-down) — pure stdlib, fixture-only.
- `cluster_purge.py` (#391 `previous_trading_day` holiday-robust +
  `classify_cluster_records`) — fixture-only, Reihenfolge-Disziplin (kein Import
  in `generate_report`/`ki_agent`/`health_check`/`backtest_history`).

### 7f. Schema v4 strikt additiv — kein Bump

`backtest_schema_version` bleibt **4**. Neue Backtest-Felder gehen **immer** in
`S10_OBSERVED_FIELDS` (keine MUSS-/LAG-Checks), sonst feuert
`_s10_check_unknown_fields` ein dauerhaftes WARN (Lehre #388). **`si_position_
history` umgeht das komplett** — eigene Datei, kein S10, kein v4-Touch.

### 7g. Render-Pfad v1/v2 (unverändert)

`generate_html_v2()` **delegiert** am Ende an `generate_html_v1()`. **Wer v1
löscht, killt v2 mit.** Vollständige Migration braucht `templates/page.jinja` +
Umbau von `_wl_full_card_html()`. Details in `CLAUDE.md` → §v1/v2 Render-Pfad.

### 7h. `si_position_history.json` — SI-Positions-Zeitreihe (NEU #423)

**Eigene Datei** (nicht Backtest-Schema). Schema
`{ticker:[{settlement_date, shares_short, short_pct_float, pub_date, seeded?}]}`.

- **Quelle:** yfinance `.info` (4 `yf_*`-Felder — `sharesShort`,
  `sharesShortPriorMonth`, `dateShortInterest`, `sharesShortPreviousMonthDate`),
  aus dem **bestehenden** `.info`-Dict → kein Extra-Call.
- **Seed-2-Punkte** beim Erststart pro Ticker (Vormonat + aktuell) →
  1-Monats-Delta ab Tag 1. `seeded=true` markiert den Backfill-Vormonatspunkt,
  `short_pct_float=None` dort ehrlich.
- **Dedup** auf `settlement_date` (neuer Punkt nur bei Änderung; `None` → kein
  Punkt).
- **Retention** `SI_POSITION_HISTORY_DAYS=400` + `SI_POSITION_HISTORY_MAX_
  POINTS=24`/Ticker (**kein** 14d-`SCORE_HISTORY_DAYS`-Leak). Atomarer Write,
  Workflow-`git add` für Cross-Run-Persistenz.
- **pub_date** via `finra_publication_date` (#408, §7c).
- **Look-Ahead-Isolation (eingefroren):** reine Analyse-Persistenz, **NIE**
  Score-/Filter-/Conviction-/Push-Feature. Grep-Guard-Test analog
  `entry_past_return_5d`. Auswertung nur `pub_date ≤ entry_date`.
- **Pool:** voller enriched **US**-Pool (non-US übersprungen — yfinance-SI ist
  US-FINRA).

### 7i. `yf_*`-Felder-Konvention (Merge-Whitelist, #411-Klasse)

Neue Felder aus dem bestehenden yfinance-`.info`-Dict werden über die **explizite
`c.update`-Merge-Whitelist** in `generate_report.py def main()` durchgereicht
(die vier `yf_*`-Felder von #423, Muster wie `close_5td_before_entry`). **Ein
in `_hist_stats` berechnetes Feld ist NICHT automatisch im Stock-Dict** — fehlt
der Key in der Whitelist, fällt er still weg (das war der #411-Bug, §8j). Regel:
bei jedem neuen enrichment-getragenen Feld die Whitelist ergänzen **und** die
Merge-Assertion im Test scharfstellen (mutations-belegt: Whitelist fälschen →
Feld muss fehlen).

### 7j. Monster-Konfidenz jetzt heuristisch (#425)

`monster_score` erbt **nicht mehr** die Setup-Robustheit — Tier fix
**heuristisch (🔴)**. `monster_score` ist unvalidiert (§8e). Anzeige neutral-grau
(`_MONSTER_NEUTRAL_COLOR = "#94a3b8"`, beide Render-Pfade), **kein** Push mehr
(`monster_backup` entfernt), Earnings-Body ohne 🔥. Berechnung/Persistenz/Sortier-
Option bleiben. CLAUDE.md-Anomaly-/Konfidenz-Tabelle synchron.

### 7k. `n_signals`-Definition = `ki_signal_score ≥ 70` (#425)

Der Signal-Zähler der KI-Agent-Statusleiste zählt seit 13.07. über
`ki_signal_score ≥ 70` (`ki_agent.py:3218-3241`), vorher `monster_score ≥ 70`.
Konsistent zum grünen Dot (`sc≥70`) der Statusleiste. **Load-bearing** — nicht
löschen; bei Änderung erst Konsument (Statusleiste), dann Definition (§8p).

### 7l. Push-Benachrichtigungs-Audit (06.09.2026, PR #544 gemergt)

Nach vollständiger Inventur aller 9 ntfy-Push-Typen hat Easy entschieden,
alle Trading-Handlungsaufforderungen abzuschalten, bis eine Edge tatsächlich
validiert ist. **Deaktiviert** (Flags in `config.py`, Default `False`):
Earnings-Sofort-Alert, Exit-Signale Phase 2 (beide Kanäle: Bundle/Warnung +
Eskalation), Anomalie-Trigger komplett (alle 7 Untertypen inkl.
`conviction_high`), Exit-Signale Phase 1 (beide Untertypen), Legacy
Alert-Monitor (`alert.py`, bereits praktisch stillgelegt). **Weiterhin
aktiv, unverändert:** Health-Check-Digest, HTML-Sanity-CRIT-Notfallnetz,
Lit-Check Weekly Reminder, Status-Review-Wecker — reine Infrastruktur/
Housekeeping ohne Trading-Bezug.

**Wichtig:** nur der ntfy-Versand ist unterbunden, die zugrundeliegende
Berechnung/Persistierung (`push_history`, Score, Exit-Pressure,
Anomalie-Erkennung) läuft unverändert weiter — keine Datenverluste für
eine spätere Edge-Validierung. **Rückweg:** die 5 neuen Flags in
`config.py` zurück auf `True` setzen, kein Code-Umbau nötig.

**Auslöser der Entscheidung:** 94,6 % der Anomalie-Events wurden zwar
ohnehin schon gegatet (Diagnose-Stichprobe aus `push_history`, n=56 Events
über ~36 Tage, Session-Inventur 06.09.2026 vor PR #544 — nicht separat als
Skript/Artefakt im Repo abgelegt), aber der einzige durchkommende Typ
(`conviction_high`) war fälschlich als „KAUFSIGNAL" beschriftet, obwohl
Conviction laut eigenem Status-Label unvalidiert ist — widersprach der
Projekt-Ehrlichkeitsregel.

---

## 8) LESSONS

*(Neueste zuerst: 8z7 vom 17.07.; 8z4–8z6 vom 16.–17.07.; 8z1–8z3 vom 15.07.-Abend; 8v–8y vom
15.07.; 8s–8u vom 14.07.-Nachmittag; 8q–8r vom 14.07.-Vormittag; 8n–8p vom 13.07.;
8j–8m vom 11.–12.07.; etablierte 8a–8i darunter.)*

### 8z7. Zwei Ziele können sich widersprechen — und genau das ist informativ (17.07.)

Der Paper-C-Read trennte `entry_past_return_5d` **peak**-seitig (`max_gain_pct ≥ 30 %`,
In-Sample-AUC ~0.61, Holm-signifikant), aber **NICHT** endpunkt-seitig (`return_10d`,
AUC ~0.47, p~0.5). Ein naiver Ein-Ziel-Read hätte je nach Ziel-Wahl „Signal!" **oder**
„nichts" gemeldet — beides irreführend. Die **Kombination** ist die eigentliche
Information: **Peak-Trennung ohne Endpunkt-Trennung ist die Signatur „spikt und fällt
zurück"**, nicht „kein Signal" und nicht „durables Edge". Das deckt sich mit dem
Exit-B.1-Hinweis (früh raus) und der Paper-Kern-Aussage (Squeeze-Wahrscheinlichkeit ≠
Rendite-Edge). **Regel:** bei Prädiktoren mit plausibel unterschiedlicher Wirkung auf
Peak vs. Haltedauer **beide Ziele vorab registrieren** — der Widerspruch ist ein
Befund, kein Rauschen. (Voraussetzung: die Ziel-Trennung VOR den Zahlen festlegen,
sonst wird sie zum nachträglichen Freiheitsgrad — hier via Slot-29 sauber vorab.)

### 8z4. Rückweg-Falle: Provenienz protokollieren, nicht rekonstruieren (16.07.)

**Der wichtigste Fund der Backfill-Kette.** Der erste `--undo`-Entwurf identifizierte
die zurückzusetzenden Records per **Recompute-Match** (Wert nachrechnen, bei Treffer
nullen). Das ist falsch: zwei Pfade — der Backfill **und** die vorwärts gesammelte
Live-Pipeline — erzeugen über **dieselbe Formel/Preisquelle denselben Wert**. Der
Wert identifiziert also **nicht den Urheber**. Ein Recompute-`--undo` hätte die
konfirmatorisch (seit 13.07.) gesammelten **OoS-Records mit-genullt** — die Evidenz
zerstört, die der Backfill gerade nicht anfassen darf. **Regel:** wer etwas rückgängig
machen können muss, **protokolliert die Provenienz** (Manifest der tatsächlich
gefüllten `(ticker,date)`), statt sie aus dem Ergebnis zu **rekonstruieren**. Der
Guardian fing das via EXZELLENZ-Kriterium 5 (Rückweg belegt); Mutationstest L4
verriegelt es (Forward-Record mit gleichem Wert überlebt `--undo`).

### 8z5. Gate-Kalibrierung: ein FAIL ist kein Grund zum Lockern — erst messen WARUM (16.07.)

Das Konsistenz-Gate schlug an (AMCX `|Δ|`=0.05 > 0.01). Der falsche Reflex wäre,
die Toleranz hochzudrehen („Gummi-Gate"). Richtig: **erst die Diff-VERTEILUNG
messen** (#443-Logging) — `41 exakt bei 0.000 / 1 Ausreißer / median 0.0` trennte
belegbar **Daten-Artefakt** (Yahoo revidiert **frische** Referenz-Bars) von
**systematischem Fehler** (der hätte viele Records verschoben). Gelockert wurde erst
**mit Beleg** und **mit weiterhin scharfen Wächtern**: der **median** fängt
Mehrheits-Drift (> 50 %), der **mean-of-Inlier** fängt Minderheits-Drift (< 50 %,
Guardian-Runde-2-Fund), der **hard cap** fängt jeden großen Sprung. Test I2/I7/I10
belegen: Systematik FAILt weiter, das Einzel-Artefakt PASSt. **Regel:** Schwellen
kalibriert man an gemessenen Verteilungen, nicht an dem einen Record, der stört.

### 8z6. Referenz-Records sind die JÜNGSTEN (revisions-anfällig), Targets die ÄLTESTEN (settled) (16.07.)

Das Gate rechnet die bereits-non-null Records (13.–15.07., die **jüngsten** Bars)
nach — genau die, die Yahoo **noch nachträglich revidiert** (Split-/Adjustierungs-
Settle). Die Backfill-**Targets** dagegen sind die **älteren** Records (14.05.–
10.07., **settled**). Ein Gate auf frischen Bars stresst also den **Worst Case**:
wenn selbst die revisions-anfälligen Referenz-Records flach recompilieren (median 0),
sind die settled Targets erst recht stabil. Das AMCX-Artefakt ist genau dieser
Effekt — kein Alarm, sondern die erwartete Bar-Revision am jüngsten Rand.

### 8z1. Universums-Verbreiterung ist ein SCHEIN-Beschleuniger (15.07.)

Bei der Sammel-Raten-Diagnose war der verlockendste „Hebel", Rang 11–40 des
enrichten Pools (statt nur Top-10) in `backtest_history` zu schreiben —
**technisch trivial, null Fetch-Kosten** (die Ränge sind schon enricht, sonst
gäbe es keine Top-10-Sortierung). ABER: das **wechselt die Population** (score-
gerankte Top-10 ≠ „alle Small-Caps mit SI>X"), **zerstört die Vergleichbarkeit
zur 30.06.-Baseline** (Alt-/Neu-Records dürfen nicht gepoolt werden, andere DGP)
und **schmälert die Vorregistrierung nachträglich** (die Kombi-Hypothese lebt von
einer konsistenten Selektionsregel = `monster_score`-Overfitting-Falle §8e).
**Regel:** „billig zu bauen" ist kein Argument für einen Sammel-Hebel — der
teuerste Fehler ist gerade der, der so billig aussieht. **NICHT tun.**

### 8z2. Wartezeit ist kein Engpass, sondern der Out-of-Sample-Schutz (15.07.)

Die Sammlung läuft bereits an ihrer legitimen **Maximal-Rate** (10 Top-10-Records/
Handelstag), gebunden an die immutabele `return_10d`-Reifung (10 Handelstage). Das
**Neue-Marktphase-Prinzip** — ein Re-Test soll in einem **anderen Regime** laufen
(OoS-Beweiswert) — bleibt als generelle Disziplin gültig, ist aber **an keinen
bestimmten Test und keinen Termin gebunden**: der frühere „Setup-Re-Test ~Ende Sept"
ist seit **05.08.2026 nicht mehr vorabregistriert** und hat **keinen Termin**
(§4-Herausnahme, keine Ersatz-Spezifikation). „Beschleunigen" hieße, entweder
die Population zu wechseln (§8z1) oder die Reifungsuhr zu schlagen (unmöglich) —
in jedem Fall **Beweiswert wegoptimieren**. Der einzige risikofreie Zeitgewinn:
den ki_signal-Read vorziehen, wenn n reif ist (getan 15.07.), + der price-basierte
`entry_past_return_5d`-Backfill (§6d). Warten ist der wissenschaftlich richtige Weg.

### 8z3. Confound-Anker brauchen persistierte Daten — VOR dem Re-Test prüfen (15.07.)

Beim ki_signal-Re-Test war der Confound „LLM-Fallback-Mix" **nicht bestimmbar**,
weil das persistierte Record kein Flag trug, ob der News-Anteil LLM- oder Keyword-
gescort war. Der Confound konnte weder bestätigt noch ausgeschlossen werden → Flag
nachgerüstet (#440, `ki_sentiment_source`) — aber **forward-only**, für die
Alt-Records bleibt er blind. **Regel:** vor jedem Re-Test prüfen, ob die
**Confound-Fragen aus den vorhandenen Daten überhaupt beantwortbar** sind — fehlt
ein Provenienz-/Kontext-Feld, ist der Nullbefund unvollständig interpretierbar.
Confound-Flags sind Vorlauf-Arbeit (Sammelbeginn), nicht Nachrüstung.

### 8v. Ziel-Mechanik zuerst belegen — „nichts bricht" ≠ „Ziel erreicht" (15.07.)

Der **erste** Phase-1-Prompt hatte kein Ziel-Mechanik-Kriterium: alle Tests wären
grün gewesen (Shell klein, Apple-Meta da, Parser lesen app.html), **ohne** dass der
eigentliche **SINN** des Umbaus gesichert war — dass eine **gecachte** Shell bei
jedem Launch via `Date.now()` eine **frische `?v=`-URL** erzeugt. Erst die
nachgeschobene Selbstprüfung erzwang **Test E** (`mock_test_bootstrap_shell_phase1`:
gecachte Shell → 2 Launches → 2 verschiedene URLs). **Regel:** ein Bau muss belegen,
dass er **sein Ziel erreicht**, nicht nur dass nichts bricht — sonst ist die
Kern-Mechanik ungetestet, obwohl die Suite grün ist. → §9e Kriterium 5.

### 8w. Handover-Angaben sind selbst fehlbar — messen schlägt lesen, auch bei eigener Doku (15.07.)

§6a nannte für den `si_velocity`-Rename **„7 Reads + KI-Boost-Konsument"**.
Gemessen (grep im Code) waren es **5 Reads** und **KEIN** KI-Boost-Konsument (der
einzige Nicht-Display-Read ist der dormante V1-Rollback-Pfad). Auf die
Handover-Zahl blind gebaut hätte man einen nicht-existenten Konsumenten „gefixt"
und die echte Touch-Fläche unterschätzt. **Regel:** vor jedem Bau die
Handover-/Doku-Angabe **gegen den Code messen** — auch die eigene Doku ist eine
Behauptung, kein Beleg (verwandt mit §8r). Falschangabe im selben PR korrigiert.

### 8x. Server frisch ≠ Gerät frisch — bei Cache-Symptomen erst die Ebenen trennen (15.07.)

Nach der iOS-Adoption zeigte **ein** Safari eine alte Seite, während der **PC
korrekt** lud und die Server-Antwort nachweislich frisch war. Ursache war ein
**korrupter lokaler Safari-Website-Daten-Zustand** für die Domain — **nicht** die
Pipeline, **nicht** die Shell. Hätte man nur die Pipeline diagnostiziert, hätte man
stundenlang am falschen Ende gesucht. **Regel:** bei Cache-Symptomen **zuerst
Server-Antwort vs. Geräte-Zustand trennen** — ein Kontroll-Gerät (PC / anderes
Handy) isoliert sofort, ob das Problem serverseitig oder lokal ist. Fix lokal:
Website-Daten löschen (Nebenwirkung: `localStorage` weg → Watchlist/Token neu,
Präzedenz #234).

### 8y. Draft-PRs verstecken die grüne Merge-Box; Legacy-Status „pending/0" ist kein Fehler (15.07.)

Bei #437 wirkte „der grüne Haken fehlt", obwohl der **advisory `pr-checks.yml`-
Check grün war** (`conclusion: success`). Zwei Fallen: **(1)** Ein **Draft**-PR
blendet die zusammengefasste „Ready to merge"-Box + den Merge-Button aus — der
Check kann grün sein, es sieht aber aus wie „Haken fehlt"; **Fix:** auf „Ready for
review" stellen. **(2)** Die **kombinierte Commit-Status-API** meldet
`pending / total_count: 0` — das ist **kein** Fehlschlag, sondern die **Abwesenheit**
der Legacy-Status-Kontexte (kein Workflow postet einen `status`, nur einen modernen
`check_run`). **Regel:** Check-Zustand über `get_check_runs` (nicht die Legacy-
`get_status`-API) lesen; bei „Haken fehlt" zuerst Draft-State prüfen.

### 8s. `index.html` ist DATENQUELLE, nicht nur die Seite (14.07.)

Was wie „die ausgelieferte Seite" aussieht, ist zugleich der **Content-Parse-
Pfad**: `ki_agent.parse_top_tickers` (**die Top-10-Quelle**), `alert.parse_
index_html` (Morgen-Baseline) und der **S9-Health-Check** lesen `index.html` als
**Daten**. Ein Umbenennen/Verschieben dort ist ein **Content-Parser-Refactor mit
Fan-out über ~8 Dateien** (config, ki_agent, alert, generate_report-Write+S9,
smoke_render.js, Workflow-`git add`, Jekyll-Test), **kein Frontend-Tweak**. Ein
übersehener Parser = **stiller Bruch** (KI-Agent scort nichts / Alarm leer / S9-
crit → kein Deploy). **Regel:** vor jeder Änderung an `index.html`-Struktur ALLE
Reader greppen (`*.py`/`*.js`/`*.yml`), Repoint mit Fallback, Guardian-Zweitblick
auf Konsumenten-Vollständigkeit (Präzedenz #434 Phase 0).

### 8t. iOS-PWA-Launcher öffnet die parameterlose start_url — `?v=` greift dort NIE (14.07.)

Der `?v=`-Cache-Bust (#373) wirkt **nur** bei In-App-Refresh + JSON-Fetches — der
**Home-Icon-Launcher** öffnet die **parameterlose start_url** aus dem iOS-
Standalone-Webapp-Cache, wo kein `?v=` anhängt. GitHub Pages liefert HTML mit
`Cache-Control: max-age=600`, das **nicht änderbar** ist (github.io erlaubt keine
eigenen HTTP-Header, kein `_headers`). Der **einzige strukturelle Fix** ist eine
**Bootstrap-Shell** (Phase 0 #434 → Phase 1 §4): die gecachte start_url wird zur
winzigen Weiche auf `app.html?v=`. Auch der #433-Recalc-Reload-Fix erreicht den
Launcher nicht.

### 8u. §8n-Erweiterung — Tests, die ki_agent importieren, ziehen pandas → rot in CI-minimal (14.07.)

`import ki_agent` (oder `generate_report`) zieht **pandas/yfinance**, die im CI-
Minimal-Install (`stdlib+jinja2+pyyaml`) **fehlen** → der Test ist lokal grün,
in der advisory CI rot (`bootstrap_shell_phase0`, Run #29361033915). **Muster
(CI-safe):** die Invariante per **Source-Inspektion** hart verankern (Präzedenz
`mock_test_ki_agent_coverage`, das ki_agent NIE importiert, nur `read_text`);
den echten Funktions-Lauf nur **best-effort** (`try: import … except: skip`),
sodass er in Dev-Envs läuft, in CI sauber übersprungen wird. Verifikation:
**immer auch die CI-minimal-Bedingung lokal simulieren** (Import-Block auf
pandas/numpy), nicht nur im vollen Env testen.

### 8q. Verify-Zählung muss Alt-Records ausklammern (14.07.-Fehlalarm)

Ein Gesamt-Zähler über **present-vs-non-null** kann einen **funktionierenden**
Fix als „greift nicht" fehldeuten. Am 14.07.-Vormittag las `entry_past_return_5d`
scheinbar „0 non-null" — tatsächlich war der 13.07.-Postclose **10/10 non-null**;
die vermeintliche Null kam daher, dass die **50 pre-fix Alt-None-Records**
(06.–10.07., forward-only, kein Backfill) im present-Gesamtzähler mitliefen und
den Blick verstellten. **Regel:** bei Feld-Verify nach einem Vorwärts-Fix **nur
Records SEIT dem Fix-Merge zählen** (bzw. nach `date`/`schema`-Marker filtern) —
nie den rohen present-vs-non-null-Gesamtquotienten als „Fix greift"-Kriterium.

### 8r. Messen schlägt Lesen — instrumentierter Lauf statt Code-Lese-Theorie (14.07.)

Statisches Code-Lesen verortete die `entry_past_return_5d`-Ursache **zweimal
falsch** (erst „Namens-Mismatch", dann „:1222 aus Variable `c` → UnboundLocal
Error"). Beide Theorien waren durch die **Daten** widerlegt (13.07.-Postclose
non-null) UND durch den Code (`:1222` ist ein Dict-Key `ma200`; es gibt keine
Variable `c` in `get_yfinance_data`; Compute an allen 3 Pfaden defined-before-use).
**Regel:** bei widersprüchlicher Diagnose **erst die Ist-Daten messen** (und den
echten Datenfluss instrumentieren/prüfen), bevor eine Code-Lese-Theorie zum
Fix erhoben wird — messen schlägt lesen. Das Station-1-Regressions-Netz (#429)
verriegelt den Compute jetzt als Netz (ehrlich: grün bei korrektem Code, kein
Bug-Beweis).

### 8n. Externe Gratis-Quellen für SI-Position existieren NICHT — aber yfinance spiegelt sie (13.07.)

Der erschöpfende externe Quellen-Check (Proben #420/#421, inkl. Asien/
international) ergab: die ausstehende SI-Position ist gratis settlement-datiert
**nicht** direkt erreichbar — FINRA `EquityShortInterest`-API ist trotz des
Namens **OTC-only**, Nasdaq nur teil-abgedeckt, Finnhub Premium. **Aber:**
yfinance `.info` **spiegelt die FINRA-SI-Position gratis** (`sharesShort` etc.,
Probe #422 4/4 befüllt). **Lehre:** vor „Quelle existiert nicht"-Schluss auch
das **eigene Werkzeug** prüfen — ein bereits genutzter Provider kann das gesuchte
Feld längst tragen. Lösung im eigenen Stack schlägt externen Feed.

### 8o. Probe-vor-Bau statt Blind-Bau; Grep-False-Positives (13.07.)

- **Probe-vor-Bau:** ein unbestätigter Daten-Blocker wird **erst** durch eine
  read-only Actions-Probe (#422 yfinance `.info`, schreibt nichts) verifiziert,
  **dann** gebaut (#423). Drei Diagnose-Runden zuvor hatten „nur Paid"
  eingestuft — die Probe kippte das mit 4/4 realen Records.
- **Probe-Grep-False-Positives:** ein String-Match (z. B. „short interest" in
  einer **Fehlermeldung**) ist **kein** echter Record. Immer den `jq`-Inhalt /
  die tatsächlichen Feldwerte prüfen, nicht nur das Vorkommen des Strings.

### 8p. Load-bearing-Zähler nicht blind entfernen — erst Konsument, dann Definition (13.07.)

`n_signals` speiste die KI-Agent-Statusleiste. Beim Monster-Ausbau (#425) wäre
ein blindes Löschen des `monster_score≥70`-Zählers ein Statusleisten-Bruch
gewesen. **Richtig:** die **Definition** auf `ki_signal_score≥70` umstellen
(Statusleiste bleibt intakt, monster-frei), **nicht** den Zähler entfernen.
Regel: bei „Feld X wird deprecated" zuerst alle Konsumenten kartieren; einen
load-bearing Zähler **umdefinieren**, nicht streichen.

### 8j. Merge-Whitelist-Bug-Klasse (Lehre #411, 11.07.)

Ein Feld kann in `_hist_stats` **korrekt berechnet** und im Append **korrekt
gelesen** werden — und trotzdem dauerhaft `None` sein, wenn der `c.update`-
Enrichment-Merge den Key **nicht in seiner Whitelist** führt (er fällt still
weg). `entry_past_return_5d` war so 50/50 None. **Regel:** bei jedem neuen
enrichment-getragenen Feld den `c.update`-Merge prüfen — und der **Test muss den
MERGE assertieren** (nicht nur Compute + Append). Präzedenz: `hist_5d`-Merge-Gap
(21.05.). **Angewandt in #423** (4 `yf_*`-Felder, Merge-Assertion mutations-belegt).

### 8k. Look-Ahead-Guards vs. legitime Display-Reads (Lehre #412, 11.07.)

Wenn ein **Anzeige**-Feature Backtest-Feldnamen referenzieren muss, aber die
Guards jedes Namens-Literal im Score-Pfad verbieten: **Feldnamen nach `config.py`
auslagern + als Render-Konstante injizieren** (Weg A, §7a-bis) — **NICHT** die
Guards lockern.

### 8l. Peak-only ≠ Squeeze — die Covering-Komponente ist der Kern (Lehre #417, 12.07.)

Der Paper-`squeeze_event` ist Peak ≥30 % **UND** SI-Rückgang ≥20 %. Lässt man die
SI-Rückgang-(Covering-)Komponente weg, **kollabiert `squeeze_event` in ein reines
Peak-≥30 %-Binär = die bereits widerlegte Hypothese C** (0/6 Holm). Also: **nicht
abspecken** — der SI-Rückgang IST das Unterscheidungsmerkmal echter Squeezes vom
bloßen Kursspike. (Genau deshalb war die SI-Positions-Zeitreihe #423 die
Vorbedingung, nicht Kür.)

### 8m. „short_interest" intern = Daily Short VOLUME, nicht Position (Nomenklatur-Falle)

Was im Code `finra_data.history` / „short_interest" heißt, ist FINRA **Reg SHO
Daily Short VOLUME** (`CNMSshvol`) — das Short-Sale-**Volumen** des Tages, **NICHT**
die ausstehende Short-**Position**. Volumen-Rückgang ≠ Shorts covern. Bei jeder
SI-Analyse zuerst klären, **welche** Größe die Quelle liefert (Volumen vs. Position
vs. % of float). Die echte ausstehende SI liegt als bimonatlicher yfinance-
Snapshot vor — seit #423 als forward-only Zeitreihe (`si_position_history.json`)
gesammelt. `si_velocity_pub` bleibt Volumen; Paper-Schwellen 7/17/25 % gelten
**nur** für die Positions-Zeitreihe.

### 8a. S10_OBSERVED_FIELDS = Whitelist bekannter Felder (Lehre #388)

Additive neue **Backtest**-Felder MÜSSEN in `config.S10_OBSERVED_FIELDS`, sonst
feuert `_s10_check_unknown_fields` dauerhaft WARN. (Nicht relevant für Felder in
eigenen Dateien wie `si_position_history.json`.)

### 8b. Pinless Deps = latente Wochenend-Bombe (#393 → #403)

`yfinance==1.4.1 → 1.5.1` Minor-Sprung → SIGSEGV Exit-139 im Batch-Fetch. Fix
#393 (Hard-`==`), Verfeinerung #403 (Cap `>=1.4.1,<1.5`). Grundregel: transitive
Deps mit expliziten Caps pinnen.

### 8c. Erfolgs-Definition VOR der ersten Zahl

Holm-signifikant UND CI-Untergrenze > 0.5. Punktschätzung nie Beleg. Verankert
im 30.06./01.07./04.07.-Befund (§5).

### 8d. Edge-Schönrechnen-Schutz BIDIREKTIONAL

Ein invertierter Befund (AUC < 0.5) ist **nicht** automatisch handelbare
Short-Edge. Gleiche Erfolgs-Definition beidseitig.

### 8e. Kleine-n-Zerfall (`monster_score`-Falle)

`monster_score`-AUC 0.76 (n=13) → 0.51 (n=20) — Scheinpräzision bei kleinem n.
Master-Score-Gewichte NIE frei aus Testdaten. Out-of-Sample-Pflicht (§5). **Grund
für die Monster-Neutralisierung #425/#426.**

### 8f. Refactor-Konsumenten-Falle: IMMER greppen VOR Namens-/Struktur-Änderung

- #407: JS-Spiegel `US_HOLIDAYS` wäre bei „nur Python fixen" gerissen — Guardian
  ROT-Blocker, JS-Meeus in `b87474a` gefixt.
- #409: STOPP wegen Naming-Kollision `si_velocity` (alt) vs. neu → Weg A →
  `si_velocity_pub`.

**Regel:** bei Namens-/Struktur-Änderung ZUERST grep über alle Konsumenten
(Python + JS + Frontend + Backtest + Doku); dann STOPP-Meldung mit Weg-A/B wenn
Kollision.

### 8g. Look-Ahead-Disziplin bei Katalysator / SI

- **Katalysator** (`days_to_earnings` #404): point-in-time-Fetch AM Report-Tag.
  Kein Backfill.
- **SI** (`si_velocity_pub` #409 + `si_position_history` #423): `pub_date`-Filter
  Pflicht (nur `pub_date ≤ entry_date`), Fundament #408.
- **Trainings-/Test-Overlap-Verbot:** kein Analyse-Feld darf im Live-Score-Read
  auftauchen.

### 8h. Häufigkeit ≠ Rendite-Edge (Paper-Lehre 12.07.)

Svoboda et al. misst **Squeeze-WAHRSCHEINLICHKEIT** (binär), **nicht** Return —
und findet dort signifikante SI-Bucket-Effekte. Unsere gesamte Edge-Suche testete
**Return** und fand 0 belegte Edges. **Lehre:** ein Prädiktor kann die **Ereignis-
Häufigkeit** trennen, ohne die **Rendite** zu trennen — zwei verschiedene Ziele
(→ Schritt A binäres `squeeze_event`). **Aber:** ein binärer Beleg auf fremden
Daten ist KEINE handelbare Rendite-Edge — die Return-Auffanglinie bleibt bis zum
OoS-Beleg.

### 8i. Crash-Blind-Zone + Ownership-Dämpfer (Paper-Grenzen 12.07.)

Paper: bei **Marktrückgang > 3 % blind**; **Institutional Ownership dämpft**
(−6 % je +1 %); **Marktkap + Markttrend nicht signifikant**. Konsequenz:
Crash-Tage ~~ausschließen~~ → **als Anzeige-Banner geflaggt statt gefiltert**
(§6h, Entscheid 08.08.: harter Ausschluss verworfen, um Panik-Squeezes nicht zu
töten), Ownership als Dämpfer-Kontext (§6g, Staleness-Vorbehalt), keinen
Marktkap-/Trend-Score bauen.

### 8j. Prompt-Prämissen sind Prüfaufträge, keine Tatsachen (08/2026)

Eine im Auftrag mitgelieferte Prämisse **immer erst am Repo/an den Daten
verifizieren**, bevor darauf gebaut wird — und bei Abweichung **melden statt
still angleichen**. Zwei belegte Vorfälle 08/2026: (a) „~19 gereifte Records/HT"
war eine unfiltrierte Zahl, der §4-Zähler meint aber score≥70-forward (~3,6/HT) —
Skala-Verwechslung; (b) „der Health-Check liest den Export bereits (S10/S13)" war
falsch (S10 liest `backtest_history.json`, kein Modul las den Matured-Export) →
der darauf gebaute „kein neuer Leser"-Constraint war hinfällig. Beide Male hat die
Read-only-Verifikation den Fehlbau verhindert. **Regel:** Prämisse ≠ Fakt; grep
zuerst.

---

## 9) ARBEITSWEISE-ANKER (KRITISCH für neue Session)

**CLAUDE.md** führt einen `Arbeits-Regeln für Claude Code`-Abschnitt (Vorsichts-
Prinzip, Trading-Wert-Filter, Zeit-Schätzungs-Regel, Uhrzeit-Regel) plus Auto-
Merge-Regel, squeeze-guardian-Routine, PR-Status-Meldung, v1/v2-Render-Pfad,
Score-Methodik-Sync-Regel. Die folgenden Regeln müssen zusätzlich hier stehen,
weil sie den Session-Modus ab Prompt 1 prägen.

### 9a. Diagnose-first bei allem mit Schema-/Score-/Daten-Impact

Vor jeder nicht-trivialen Änderung: **read-only Diagnose zuerst.** User-Trigger
„DIAGNOSE-AUFTRAG (READ-ONLY) — Nichts ändern, nur lesen/greppen, mit Pfad/Zeile
belegen" → **null Code-Change**, nur Belege. Erst danach kleiner Bau-Schritt mit
Verifikation zwischen den Schritten. **Vor jeder Namens-/Struktur-Änderung: alle
Konsumenten greppen** (§8f), bei Kollision STOPP + Weg-A/B.

### 9b. „absolute Vorsicht, kein Risiko" — Prompt-Signatur des Users

Verbindliche Priorität: bei Zweifel → STOPP + kurze Rückfrage, NICHT auf Annahmen
aufbauen. Silent-Umbauen ohne Belegung ist verboten.

### 9c. Web-Check proaktiv als Standard-Option (NEU)

Bei **Datenquellen-Blockern, Forschungsfragen, Vergleichen** bietet Claude von
sich aus einen **Web-Check** an (nicht erst auf Nachfrage) — die SI-Quellen-Suche
13.07. hat gezeigt, dass ein früher externer + eigener-Werkzeug-Check einen
monatealt geglaubten Blocker kippen kann (§8n). Ergänzt vom
`lit_reminder.yml`-Wochen-Push (#413) als fester Rhythmus.

### 9d. Probe-vor-Bau-Muster (NEU)

Eine **unbestätigte Annahme über eine Datenquelle** wird **nie blind gebaut**,
sondern zuerst durch eine **read-only Actions-Probe** verifiziert (schreibt
nichts ins Repo, `workflow_dispatch`). Erst der 4/4-Real-Record-Befund (#422)
rechtfertigte den Bau (#423). Grep-Treffer in Fehlermeldungen sind kein Beleg —
`jq`-Inhalt prüfen (§8o).

### 9e. Exzellenz-Selbstprüfung vor „Ready"-Meldung (Build-PRs) — SIEBEN Kriterien

**Erweitert 15.07. von 4 auf 7 Kriterien** (Ziel-Mechanik, Annahmen-Klären,
Rückweg — nach der Phase-1-Lesson §8v). Gilt für **JEDEN** Bau-Prompt, mit
belegbaren Punkten (nicht Behauptungen):

1. **Widersprüche** — Diff-Beleg dass nur der beabsichtigte Scope getroffen wird
   (Doc-only: kein Logik-Touch).
2. **Nachweise** — Kern-Verhalten mit **Testausgabe / Repo-Beleg**, nicht
   behaupten (Hashes/Feldnamen/Zahlen aus Repo, Datums-Basis aus Repo).
3. **Fragile Annahmen** — None-Semantik, Edge-Cases, Timezone explizit.
4. **Determinismus** — Tests grün, CI-Runner grün, AST-Compile grün.
5. **ZIEL-MECHANIK ZUERST** — belegen, dass der Bau **sein Ziel erreicht**, nicht
   nur dass nichts bricht. Die Kern-Mechanik braucht einen eigenen Test/Beweis
   (§8v: die Suite kann grün sein, während der Sinn ungesichert ist).
6. **ANNAHMEN KLÄREN, NICHT ANNEHMEN** — Golden-Gegenstand, Konsumenten,
   Umgebungen (CI-minimal vs. Dev), Doku-Zahlen **messen** statt lesen (§8w). Bei
   Unklarheit prüfen, nicht raten.
7. **RÜCKWEG BELEGT** — bei Deploy-/Struktur-Eingriffen ist der **Rollback-Weg
   Pflicht** und wird im PR-Text genannt (z. B. „Revert = Ein-Zeilen-Shell-
   Rückbau; Parser lesen app.html mit Fallback → unschädlich").

„Anspruch: exzellent" heißt genau diese sieben.

### 9f. Manueller Merge vs. Auto-Merge — Klassifikations-Sicht

Kurzform (Detail in `CLAUDE.md`):
- **Manuell**: neue Workflows, neue JSON-Schemas/Dateien, neue API-Integrationen,
  Score/Conviction/Filter/Exit-Logik, Backtest-Schema-Touch (auch additiv),
  Push-/Anzeige-Score-Touch (z. B. Monster #425/#426).
- **Auto**: Doku (CLAUDE.md, SESSION_HANDOVER), Frontend-Text-Tweaks, CSS,
  Helper-Refactor, Bugfixes ohne Schwellen-Änderung, State-Logging, Mock-Test,
  backward-compat-Aliase.

**Im Zweifel: manuell.** **Dieser Handover-PR ist reine Doku → Auto-Merge.**

### 9g. squeeze-guardian-Zweitblick

Vor manuellem Merge **empfohlen** (Bonus, kein Gatekeeper). Claude initiiert den
Aufruf explizit via Task/Agent-Tool (der PostToolUse-Hook ist nur ein `echo`-
Reminder). Nicht-deterministisch. Ersetzt NICHT Easy's Bedeutungs-Validierung.

### 9h. Rate-Limit / API-Fehler beim Merge

Kein Retry-Loop bei GitHub-Rate-Limits im Merge-Pfad. Meldung an User. Retry-Loop
nur bei Netzwerk-Push-Fehlern (2s/4s/8s/16s, max 4).

### 9i. Reihenfolge-Disziplin Edge-Auswertung

**Erst sammeln, dann auswerten.** Keine Edge-Zahl vorziehen bevor n das vor-
registrierte Ziel erreicht (§4). Erfolgs-Definition VOR der Zahl. Multiple-
Testing-Klammer VOR der Auswertung fixieren.

### 9j. Rollen + Uhrzeit

- **Claude:** Diagnose + Prompt-Formulierung + Einordnung. **Mensch:**
  Entscheidung + Merge.
- **Zeit:** Claude hat nur Datum („Today's date is …") — vor zeitabhängigen
  Aussagen `date -u` im Bash prüfen (belegt hier: 13.07. 21:36 UTC) oder User
  fragen. Nie raten.

### 9k. Session-Handover-Regel

Bei „Gute Nacht" / „Feierabend" / „Bis morgen": Claude aktualisiert
`SESSION_HANDOVER.md` automatisch (alle 9 Blöcke), direkt auf `main` (bzw. Doku-
PR mit Auto-Merge) mit `docs: handover update after session JJJJ-MM-TT`. Bei
größeren Übergängen: alle 9 Blöcke komplett neu, aus Repo/Logs belegt, nichts
erfunden — **Hashes/Datum/Zahlen belegen, nicht aus Erinnerung** (dieser Refresh:
alle #419–#426-Hashes + Datums-Basis git-belegt).

### 9l. Subagent-gestützte read-only Diagnosen (NEU, 10.10.2026)

Claude startet reine Lese-Diagnosen jetzt teils selbst über einen
Unteragenten — **ohne** `gh`-/PR-/Actions-Zugriff, **kein** Schreibzugriff.
Bau, Actions-Logs, PR-Daten und Open-Item-Einträge laufen weiterhin
ausschließlich über die Haupt-Session („Code"). Der Unteragent dient nur
der parallelen/entlasteten Durchführung reiner Grep-/Git-Log-/Zählungs-
Diagnosen (analog dem bestehenden `squeeze-guardian`-Zweitblick, §9g, aber
für Diagnose statt Review) — keine neue Berechtigungsstufe, keine
Ausnahme von den PR-/Merge-Regeln oben.

---

**Ziel dieses Dokuments:** neue Session arbeitet ab Prompt 1 im selben Modus,
ohne Wieder-Etablierung. Widersprüche zwischen SESSION_HANDOVER und CLAUDE.md →
CLAUDE.md gewinnt (dort steht die Codebase-Wahrheit; hier steht der Projektstand).
