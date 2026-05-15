# Session-Handover — Stand 15.05.2026

## Heute implementiert (chronologisch, alle gemerged via PR)

### Anzeige & Trade-Journal

- `82bfb27` — **fix: Intraday-Snapshot-Label im Header** (PR #158).
  `_renderRunPhasePill(phase, generatedAt)` mit dritter Anzeige-
  Klasse — bei `premarket` + UTC ∈ [13:30, 20:00) zeigt der Pill
  jetzt „Intraday-Snapshot" statt irreführendem „Pre-Open-Vorschau".
  Disambiguation aus `app_data.generated_at`. Backend (`run_phase`-
  Logik + Override + Backtest-Schutz) unverändert.
- `1a4d0d9` — **feat: Trade-Journal-Eröffnungs-These** (PR #159).
  Neue Open-Form-Textarea `pos-thesis-{ticker}` (rows=3, maxlength
  500, optional). Plus 5 zusätzliche Auto-Snapshot-Felder beim
  Position-Open: `entry_monster_score`, `entry_ki_score`,
  `entry_rvol`, `entry_si_trend`, `entry_conviction_components`.
  Close-Form mit dreistufigem Pre-Fill (Cache → `entry_thesis` →
  `''`). Neuer `_cacheOpenFormFields`-Helper analog Phase-2-Cache.

### Health-Check-Stabilisierung

- `c6cdb37` — **fix: Health-Check JSONL-Persistenz + Cron-Offset**
  (PR #160). Drei strukturelle Bugs in einem Fix:
  - `daily-squeeze-report.yml` + `ki_agent.yml`: `git add
    health_check_log.jsonl` + `provider_health.jsonl` ergänzt (war
    Follow-up-Bug aus Phase-2-PRs #152–#154 — Files wurden lokal
    geschrieben, aber nie commited)
  - `health_check_digest.yml`: Cron `13 8 * * *` → `21 8 * * *`
    (Last-Peak-Vermeidung analog ki_agent `xx:17`-Pattern)
  - `scripts/health_check_digest.py`: detaillierteres Logging im
    ntfy-Send-Pfad (Success-HTTP-Status, Exception-Type)

  Adressiert das Symptom „kein Digest-Push heute morgen" — State-
  Commit war erst um 10:37 UTC statt geplant 08:13, JSONL-Files
  permanent leer.

### Phase-3-Exit-Spec

- `d3e0c42` — **docs: Phase 3 Exit-Signal Spec — Blow-off-Top**
  (PR #161). Initiale Spec-Datei `docs/phase3_exit_spec.md` mit
  Sektionen A–E. IV-Crush als ursprünglich geplanter zweiter Trigger
  **gestrichen** (Easy handelt Aktien nicht Optionen; yfinance-IV-
  Coverage nur Top-5; IV-Historie nicht persistiert).
- `af259f6` — **docs: Phase 3 Spec Erweiterung** (PR #162). Sektionen
  E (Risiken-Bewertung), G (Aufwand), H (Implementations-Bedingung
  mit Pass/Fail-Kriterien) ergänzt. CRMD-Live-Test-Kontext explizit
  als „natürlicher Triggerpunkt" für Implementations-Entscheidung
  verankert.

  Blow-off-Top-Trigger-Bedingung verbindlich festgelegt:
  - `change_5d ≥ 50 %` UND
  - Live-Quote heute ≤ −5 % (vs. Vortag-Close)
  - Beide Bedingungen müssen erfüllt sein → crit
  - Gewicht 0.05 im Composite-Pressure
  - Implementation **erst nach Live-Test** bei CRMD-artigem Setup,
    in dem Phase-2-Trigger empirisch zu spät reagiert haben

### News-Coverage

- `82a3d8c` — **feat: News-Coverage auf persönliche Watchlist**
  (PR #163, **bei Session-Ende noch nicht gemerged**). News-Pool
  erweitert von `top10` auf `top10 ∪ manual_personal` aus
  `enriched`. ThreadPool-Workers von 13 → 16. Set-Dedup verhindert
  Doppel-Fetch. Adressiert das Symptom „Aktuelle Meldungen leer"
  auf der CRMD-Watchlist-Karte trotz frischer Earnings — CRMD ist
  heute nicht in den Top-10, daher fetchte `get_combined_news` ihn
  nicht.

### Doku-Updates

- `e0b3ba2` — **docs: SESSION_HANDOVER update Stand 14.05.2026**
  (PR #157, heute Morgen)
- Auto-Merge-Regel ab 15.05. in CLAUDE.md verankert (über PR #161
  mit-eingeführt): Code mergt selbst nach grünem Guardian +
  grünen Tests; manueller Easy-Merge bleibt für neue Workflows /
  Schemas / API-Integrationen / Score-Logik

---

## Aktive Positionen (im Gist `squeeze_data.json`)

**4 aktive Positionen:** AMC · IONQ · RR · CRMD

### Neuer Trade heute: CRMD

- Am **14.05.2026** gekauft mit **Conviction 98** (höchster bisher
  beobachteter Wert nach Earliness-V2-Aktivierung)
- Nach **positiven Earnings 15.05.** Sell-the-news-Reaktion mit
  **−3.2 % P&L** auf Position
- **Plan: durchhalten** — Squeeze-Substrat intakt:
  - DTC 16 Tage
  - Short Float 21 %
  - SI-Trend stabil
- Tool-`exit_pressure` aktuell **22/100** stützt den „halten"-Plan
- Doppelt relevant: CRMD ist der **natürliche Live-Test-Kandidat
  für Phase-3-Spec** — wenn Phase-2-Trigger den Verlauf sauber
  steuern, wird Phase 3 nicht implementiert. Wenn Position trotz
  fundamentaler Stärke ins Drawdown läuft und die Phase-2-Trigger
  zu spät schließen, wird Phase 3 nach `docs/phase3_exit_spec.md`
  gebaut.

---

## Verifikation morgen (16.05.2026)

- **Erster Health-Check-Digest-Push** um **10:21 deutscher Zeit**
  (08:21 UTC). Nach PR #160-Merge + heute laufender JSONL-
  Persistenz sollte morgen erstmals ein `✅ Health-Check OK`
  ankommen (statt `📭` wegen leerer JSONL-Files).
- **News auf CRMD-Karte** nach PR #163-Merge + nächstem Daily-Run
  sichtbar — „Aktuelle Meldungen"-Drawer zeigt echte Items statt
  „Keine Nachrichten verfügbar".
- **Intraday-Snapshot-Label** beim nächsten US-Session-Run
  (Re-deploy oder manueller Trigger zwischen 13:30 und 20:00 UTC)
  sichtbar.
- **Trade-Journal-Eröffnungs-These** bei nächster Position-Eröffnung
  testen — Textarea unter Stückzahl, Pre-Fill beim Schließen.

---

## Geplante Aufgaben + Wiedervorlagen

### Offene Aufgaben

- **Phase-3-Implementation** auf CRMD-Live-Test warten:
  - Phase-2-Trigger schließen sauber (max −10 % vom Peak) →
    Phase 3 nicht nötig, Spec bleibt im Backlog
  - Phase-2-Trigger schließen zu spät (> −20 % vom Peak) → Phase 3
    nach `docs/phase3_exit_spec.md` implementieren
- **KI-Agent-Coverage-Erweiterung** (Option B aus News-Diagnose
  15.05.): KI-Score / StockTwits / UOA / EDGAR / FINRA-SSR auch für
  Watchlist-Outsider? Push-Frage (Anomaly-Pushes für Non-Top-10-
  Tickers gewünscht?) muss geklärt werden bevor Implementation.

### Wiedervorlagen mit Datum

- **16.05.2026** — Health-Check-Digest-Push erstmals mit echten
  Daten verifizieren (10:21 deutscher Zeit)
- **16.05.2026** — News auf CRMD-Karte verifizieren
- **17.05.2026** — Intraday-Label im US-Session-Fenster verifizieren
- **15.–31.05.2026** — Health-Check Konsekutiv-Counter beobachten,
  Push-Volumen kalibrieren
- **19.05.2026** — `app_data`-Recovery + `POSITIONS_JSON`-Secret
  löschen
- **28.05.2026** — Earliness-Trend-Logging AUC-Re-Check (14 Tage
  nach PR #142 Merge)
- **02.06.2026** — Chart-Indikatoren prüfen
- **13.06.2026** — Earliness V3 Entscheidung (30 Tage Trend-
  Logging-Daten)
- **02.07.2026** — Premium-Daten-Stack prüfen
- **Wiedervorlage Konfidenz-Wasserzeichen** — Phase 2 von PR #146.
  Re-Visit wenn Earliness V2 nach 14–30 Tagen validiert ist.
- **Wiedervorlage Knaller-Trade-Label** — einzelne Outlier-Trades
  markieren statt nur Bucket-Skew-Statistik. Eigenes Feature, kein
  akuter Bedarf.

---

## Strategische Roadmap

### Übergeordnetes Ziel

Squeeze-Früherkennungssystem mit empirisch validierter Edge. Drei
parallele Arbeitsstränge laufen permanent nebeneinander:

- **Bauen** — Code-Erweiterungen. Health-Check-Projekt komplett
  abgeschlossen (PRs #150, #152–#155, gestern). Heute kleinere
  UI/UX-Härtungen + Phase-3-Spec ohne Code. Aktuell offen:
  Phase-3-Implementation (wartet auf CRMD-Live-Test), KI-Agent-
  Coverage-Erweiterung, Code-Hygiene-Backlog-Punkte 2/3/4/5-2/6-B.
- **Sammeln** — passives Warten auf Backtest-, Earliness-,
  Conviction-, Score-Inflations-, Push-Volumen-, Earliness-Trend-
  Logging-, Provider-Health- und State-Invariants-Empirik. Jeder
  Daily-Run + ki_agent-Tick füttert die History. Plus seit heute:
  **CRMD-Live-Trade als spezifischer Datenpunkt** für Phase-3-
  Empirik.
- **Validieren** — Score-Logik gegen reale R-Werte testen, sobald
  genug Datenpunkte da sind. Aktuell: Daily-Run-Checks, Position-
  Verläufe (AMC / IONQ / RR / CRMD), Methodik-Konsistenz-Pflege.
  **Heute starker Tag für „Validieren"** — CRMD ist der erste
  Conviction-98-Trade nach V2-Aktivierung, sein Verlauf liefert
  empirische Datenbasis für die Phase-3-Implementations-Entscheidung.

### Drei Zeit-Achsen

**Kurzfristig (Tage bis 1–2 Wochen, aktiv planbar)**

- **CRMD-Live-Test-Beobachtung** — Phase-2-Exit-Trigger-Verhalten
  bei sell-the-news → recovery- oder breakdown-Pfad.
- **Health-Check-Empirik** — Push-Volumen + Konsekutiv-Counter-
  Verhalten 15.–31.05.
- **Earliness-V2-Beobachtung** — Conviction-Median-Veränderung
  empirisch validieren (CRMD-98 ist erster Datenpunkt).
- **Score-Inflations-Empirik** auswerten.

**Mittelfristig (Wochen, datenabhängig)**

- **Earliness-Trend-Logging-AUC-Re-Check** (28.05.).
- **Earliness V3 Entscheidung** (13.06., 30 Live-Tage).
- **Phase-3-Implementations-Entscheidung** — nach CRMD-Position-
  Close oder spätestens nach 30 Trading-Tagen.
- **Backtest-Validierung** — Frontend-Auswertung erfordert ≥ 200
  Live-Einträge je Score-Bucket. Bahn A2 läuft seit Zwei-Run-
  Architektur (PR #124) mit nur postclose-Werten.
- **ntfy-Priority-Mapping nach Severity**.

**Längerfristig (Monate, Empirik-basiert)**

- **Big-Refactor Zwei-Achsen-Ranking** — nach 30+ Tagen Earliness-
  V2-Daten.
- **Premium-Daten-Stack** (Wiedervorlage 02.07.2026).
- **Sektor-Rotation / Marktkontext** — noch nicht im Backlog.

### Lackmus-Test

**Phase 3 Validieren ist der entscheidende Test.** Backtest muss
zeigen: Score ≥ 70 hat einen klar besseren Median-R-Wert nach 5 T
als Score < 50. Mit der Zwei-Run-Architektur wird die Historie nur
noch mit postclose-Werten befüllt — saubere Datenbasis.

- **Wenn ja** → Earliness-V2-Aktivierung im Score selbst und
  Big-Refactor mit Rückenwind.
- **Wenn nein** → Score-Komponenten neu kalibrieren bevor weiter
  gebaut wird.

Bis der Test laufen kann, ist passives Sammeln der primäre Modus.
Mit dem heutigen Stand sind alle Tools für Trade-Auswertung scharf:
Health-Check-Digest läuft ab 16.05. mit echten Daten, News-Coverage
deckt persönliche Watchlist ab, Trade-Journal hat Eröffnungs-These
+ erweiterten Score-Snapshot, Intraday-Label disambiguiert das
Header-Pill.

---

## Code-Hygiene-Backlog

Aus der Diskussion vom 09.05.2026. Status zum Ende 15.05.:

- **Punkt 1 — `_record_push`-SSOT** — erledigt via PR #76.
- **Punkt 2 — v1/v2 Render-Pfad in `generate_report.py`:** **offen.**
  Vollständige Migration zu Jinja (Phase X). Voraussetzung für Punkt 3.
- **Punkt 3 — Monolith `generate_report.py` aufsplitten:** **offen.**
  Datei weiter gewachsen durch heutige UI-Tweaks (Intraday-Label,
  Trade-Journal-These, News-Coverage). Hohe Risiko-Operation.
- **Punkt 4 — HTML/JS-im-f-String-Pattern durch Template-Engine
  ersetzen:** **offen.** Zwei CI-Lints als Abhilfe aktiv, aber
  strukturelle Ursache bleibt.
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

### Intraday-Snapshot-Label (PR #158)

- `_renderRunPhasePill(phase, generatedAt)` mit drei Anzeige-Klassen.
- Disambiguation **clientseitig** aus `app_data.generated_at`-Timestamp
  → kein Backend-Refactor, `run_phase`-Semantik unverändert (weiterhin
  nur premarket/postclose, Backtest-Schutz wirkt wie zuvor).
- Beide premarket-Varianten teilen CSS-Klasse `hdr-runphase-premarket`
  (gelb = „Daten nicht final").

### Trade-Journal-Eröffnungs-These (PR #159)

- `positions[ticker]` hat jetzt **`entry_thesis`** (User-Freitext,
  optional, max 500 Zeichen) **plus 12 entry_*-Snapshot-Felder**:
  `entry_score`, `entry_score_bucket`, `entry_conviction_score`,
  `entry_conviction_level`, `entry_conviction_components` (Sub-Objekt
  mit setup/earliness/anomaly/regime), `entry_dtc`, `entry_short_float`,
  `entry_cost_to_borrow`, `entry_monster_score`, `entry_ki_score`,
  `entry_rvol`, `entry_si_trend`, `entry_snapshot_ts`, plus FX-Felder.
- Pre-Fill beim Schließen **dreistufig**: Cache (Bug-A-Recovery) →
  `pos.entry_thesis` → `''`. `_escAttr` umschließt für XSS-Schutz.
- Bestandspositionen ohne `entry_thesis` (vor 15.05. eröffnet) fallen
  graceful auf leeren Pre-Fill — Soft-Migration.

### Health-Check-JSONL-Persistenz (PR #160)

- `daily-squeeze-report.yml` und `ki_agent.yml`: `git add` für
  `health_check_log.jsonl` und `provider_health.jsonl` ergänzt.
- Digest-Cron auf `21 8 * * *` verschoben (Last-Peak-Vermeidung).
- ntfy-Send-Logging: Success-HTTP-Status + Exception-Type für
  Diagnose-Schärfung.

### Phase-3-Exit-Spec (PRs #161 + #162)

- `docs/phase3_exit_spec.md` als Single-Source-of-Truth für die
  spätere Implementation. Sektionen A–H.
- Blow-off-Top als einziger Phase-3-Trigger:
  - `change_5d ≥ 50 %` UND Live-Quote heute ≤ −5 %
  - Gewicht 0.05 im Composite-Pressure
  - `overheated`-Gewicht **nicht reduzieren** (bewusste
    Spezialisierung — 50 % in 5 d ist deutlich strenger)
- IV-Crush **gestrichen** (Aktien-Trader, yfinance-Limits).
- **Implementation pending** — auf CRMD-Live-Test-Auswertung warten.

### News-Coverage-Pool (PR #163)

- `get_combined_news`-Pool ist **Set-Union** `top10 ∪ manual_personal`.
- ThreadPool `max_workers=16` deckt erweiterten Pool ab.
- Attachment via `_news_by_ticker`-Dict → Loop über `enriched`.
- Top-10-Stocks bekommen news weiterhin direkt (Referenz-equal);
  Watchlist-Outsider via `_wl_card_payload → watchlist_cards`.

### Auto-Merge-Regel (CLAUDE.md, ab 15.05.2026)

- **Auto-Merge erlaubt für**: Doku, Frontend-Tweaks, Workflow-Tweaks
  innerhalb existierender YAMLs, Helper-Refactor, State-Logging,
  Mock-Tests, Backward-compat-Aliase.
- **Manueller Easy-Merge mit Code-Review-Pflicht für**: neue Workflow-
  Dateien, neue JSON-Schemas, neue API-Integrationen, Score-/
  Conviction-/Filter-Logik-Änderungen.
- Im Zweifel: lieber Easy-Merge anfragen als Auto-Merge.

### Frühere Architektur-Anker (Bestand aus 14.05.2026)

- **Earliness V2** DTC-Niveau-Basis als Default (`EARLINESS_FORMULA_VERSION=2`,
  V1 als Rollback-Pfad). PR #141.
- **Earliness-Trend-Logging** — 4 prospektive Felder im Backtest-
  Schema v4. PR #142.
- **`topten_entry`** liest aus `backtest_history`. PR #144.
- **KI-Agent und Daily-Run beide auf `xx:17`-Cron**. PRs #143 + #145.
- **Daily-Run-Auto-Trigger KI-Agent**. PR #150.
- **Score-Konfidenz-Stufen** in `app_data.json` mit CI-Lint-Isolation.
  PR #146.
- **Token-Pipeline saniert**: Settings-Panel-UI-Refresh,
  Drei-Zustände-Routing für Position-Panel + Trade-Journal, 4
  Action-Pfade durch `_ensureToken`-Wrapper, `.gist-locked-box`-
  CSS-Klasse, Storage-Diagnose-Panel. PRs #147, #148, #149, #151.
- **Health-Check-Projekt vollständig**: 7 State-Invariants + 15
  Provider (4 Tier 1 / 4 Tier 2 / 7 Tier 3) + Daily-Digest 08:21 UTC.
  PRs #150, #152, #153, #154, #155.
- **Methodik-Display zeigt versteckte Boni**: Borrow-Rate-Tiers,
  Float-Turnover-3-Tier, UOA-Aufschlüsselung. PR #156.

---

## Lessons Learned (15.05.2026)

- **Ausbleibender Health-Check-Push war wertvolles Liveness-Signal.**
  Zwei strukturelle Bugs auf einmal enthüllt: JSONL-Persistenz fehlte
  komplett (Folgefehler aus Phase-2-PRs #152–#154) UND Cron-Slot
  gedroppt. Beide in einem kleinen Fix (PR #160) adressiert. Die
  „Liveness-Check by Absence"-Idee aus der Health-Check-Spec hat sich
  in der ersten Woche bewährt.

- **Spec-Workshop ohne Implementation als eigenständiger Wert.**
  Phase-3-Spec heute geschrieben ohne Code zu produzieren. Ergebnis:
  IV-Crush konnte sauber abgewählt werden (Daten-Limits + zu wenig
  Aktien-Trading-Wert), Blow-off-Top als spezifischer Endphase-
  Trigger ausgearbeitet. Implementation wartet auf empirischen
  Live-Test (CRMD) statt auf Engineering-Bauchgefühl.

- **Auto-Merge-Regel: Trade-off Vier-Augen vs. Workflow-Geschwindigkeit.**
  Neue Regel reduziert manuelle Merges für Doku/Frontend/Workflow-
  Tweaks drastisch. Manueller Merge bleibt nur bei strukturell
  riskanten Änderungen (neue Schemas, neue APIs, Score-Logik). Erste
  Erfahrung: deutlich flüssigerer Workflow, kein qualitativer Verlust.

- **CRMD-Trade als Live-Datenpunkt für Phase-3-Spec.** Conviction 98
  vor Earnings gekauft, positive Earnings, Sell-the-news-Reaktion.
  Tool-Exit-Druck 22/100 stützt „halten"-Plan. Wenn Position trotz
  Sell-the-news im Recovery-Pfad bleibt → Phase 2 reicht aus. Wenn
  schlechter Verlauf → Phase 3 als spezifischer Endphase-Trigger
  validiert. **Single Live-Trade gibt die Implementations-Entscheidung
  für ein Feature, das sonst spekulativ gebaut worden wäre.**

- **Coverage-Lücken zeigen sich erst bei Position-Halt.** News-
  Fetcher war auf Top-10 beschränkt. Easy bemerkte das erst, als CRMD
  nach Earnings aus Top-10 fiel. Trading-Wert-Filter etabliert
  (12.05.) hat sich bewährt: nicht „Engineering-Vollständigkeit"
  sondern „hilft das bei nächster Trade-Entscheidung" als
  Priorisierungs-Maßstab.

- **Karten-Anzeige soll Datenlücken klar kommunizieren — oder besser
  schließen.** CRMD „Aktuelle Meldungen leer" war kein Bug sondern
  fehlende Coverage. Aber visuell vom User nicht unterscheidbar.
  PR #163 löst es mit echten Daten — Option C (Frontend-Hinweis) wäre
  nur Symptom-Bekämpfung gewesen. **Echte Daten schlagen Erklär-
  Tooltips.**
