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

### 08.–10.10.2026 — NaN-Guard-Symmetrie (entry_past_return_5d) + Preis-Merge-Guard-/NYSE-empty-Diagnosen + Block-1-Autonomie-Regel + Setup-Edge-Re-Test-Freeze + Conviction-Erratum (7 PRs)

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
10. **Erwartung (Schätzung, kein Termin):** wie im Freeze oben. Die
    tatsächliche Rate wird gezählt (Zeilen pro Handelstag **unter V2** —
    nach Punkt 2 heute ohnehin 100 % der Population), nur die Schätzzeile
    wird bei Erreichen angepasst.

**Änderungs-Protokoll gilt identisch für dieses Erratum** (analog Freeze
oben): keine weitere Änderung ohne datierten Protokolleintrag.

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
