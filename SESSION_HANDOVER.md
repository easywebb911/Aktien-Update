# SESSION_HANDOVER.md — Stand 14.07.2026 (Nachmittag)

**Zweck:** vollständige Übergabe an eine **neue Code-Session ohne Kontext der
alten**. Dieses Dokument + `CLAUDE.md` müssen zusammen ausreichen, um am
Projektstand direkt weiterzuarbeiten. Reine Doku, kein Logik-Touch.

**Datums-Basis (belegt, nicht Erinnerung):** `date -u` in der Sandbox liefert
**Di 14.07.2026 ~06:56 UTC**. Der **postclose-Run 13.07.** ist durch (`e9fd8cc
"Daily squeeze report 2026-07-13"`, Health-Log `2026-07-13T22:13:24Z
[postclose]`) — damit sind die gestrigen Verifikationspunkte auflösbar (§3).
PRs #429/#430 tragen Commit-Datum **2026-07-14** (git belegt: #429 `3ed4cfd`,
#430 feat `930633d` / Merge `57c6b10`). Die #419–#426-Kette lief am **13.07.**

*(Hinweis für die nächste Session: der vorige Handover war fälschlich „Stand
15.07.2026" tituliert, obwohl die damals beschriebenen PRs #415–#418 laut git
am **12.07.** gemergt wurden. Datum hier aus Repo korrigiert.)*

Struktur (9 Blöcke): (1) Heute implementiert · (2) Aktive Positionen ·
(3) Verifikation · (4) Wiedervorlagen · (5) Strategische Roadmap ·
(6) Hygiene-Backlog · (7) Architektur-Anker · (8) Lessons · (9) Arbeitsweise-
Anker.

---

## 1) HEUTE IMPLEMENTIERT (chronologisch, mit Hashes)

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
  #430 im Status-Panel sichtbar (n=28). **Restkante bleibt vermerkt** (Beobachtung,
  kein Blocker): falls yfinance `dateShortInterest` künftig als `Timestamp` statt
  epoch-int liefert, wird der Punkt fail-soft **still** übersprungen.

### AKUT (weiterhin offen)

- **★★ PHASE-0-ZYKLUS-VERIFY — KRITISCHE Vorbedingung für Phase 1 (#434).**
  Nach dem **nächsten Daily-Run** (heute ~21:17 UTC postclose) read-only prüfen,
  ob der `app.html`-Content-Pfad sauber trägt — **alle drei** müssen stimmen,
  sonst **Phase 1 (Shell-Flip) NICHT freigeben:**
  - **(a)** `app.html` existiert im Repo (Daily-Run schrieb + committete es via
    `git add app.html`).
  - **(b)** **S9 grün** im Health-Log (kein WARN/crit; `state_fails` ohne S9) —
    S9 prüft seit #434 `app.html`.
  - **(c)** `ki_agent`-Tick zieht die Top-10 aus `app.html` (Log „Top-Ticker aus
    app.html: …") → **KI-Scores kommen weiter** auf den Karten.
  **Erst wenn (a)+(b)+(c) sauber → Phase 1 freigeben (§4). NICHT vorziehen.**

- **★ KI-Karten nach Deploy (#432):** nach dem nächsten Deploy zeigen **alle 10**
  Top-10-Karten einen KI-Score (die 6 vormals „—" gefüllt, Farben konsistent).
  **Cache-Bust nötig** (iOS/Browser) — der Launcher-Cache bleibt das separate
  Phase-1-Thema.

- **★ Monster-Kachel neutral-grau — iPhone-Blick (#425/#426):** Monster-Zahl +
  Progress-Bar müssen **grau** (`#94a3b8`) statt Ampel-Grün erscheinen, in
  **beiden** Karten-Pfaden (Top-10 + Watchlist-Drawer). Live-Verify am iPhone
  **noch ausstehend** (kein Golden-Ersatz für visuelle Korrektheit, §8 „Source
  grün ≠ Browser korrekt"). Earnings-Push-Body (falls einer feuert): **ohne
  🔥-Monster-Aufmacher**. → abhaken, sobald per iPhone bestätigt.

- **★ Lit-Check-Reminder — erster Push (#413):** erster planmäßiger ntfy-Push
  **kommenden Freitag ~18:33 Berlin** (Cron `33 16 * * 5`). Watch: Push kommt
  an, Tag `books`. Bleibt er aus → `NTFY_TOPIC`-Secret prüfen (Workflow ist
  fail-visible: exit 1 bei Send-Fehler trotz gesetztem Topic).

- **★ Status-Panel 6. Eintrag (#430) — live sichtbar:** nach nächstem Deploy im
  `#bt-section` prüfen: Zeile „Short-Interest-Position (si_position_history) ·
  n=28 (28 Ticker) · sammelt …" erscheint, **keine** Serien-Werte. Graceful-
  Empty ist per Test gesichert.

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

### RE-TEST-KALENDER (kanonisch, Stand 13.07.)

| Datum | Was | n-Ziel | Notiz |
|---|---|---|---|
| **~Mitte Aug 2026** | ki_signal_score-Edge-Re-Test | n_reif ≥ 40 | LOOK-AHEAD SAUBER — LLM-basiert `temperature=0`, Score zum Erhebungszeitpunkt eingefroren, deterministisch reproduzierbar. Eigenständiges Signal = Kombi-Kandidat. |
| **~Ende Aug 2026** | Conviction-Edge (Prüfpunkt P3 aus 30.06.) | n ≥ 100 | Vorwärts-Erhebung seit PR #388 (28.06.). Composite aus Setup/Earliness/Anomaly/Regime — Aggregations-Anzeige, deren Edge selbst noch nicht belegt ist. |
| **~Ende Sept 2026** | Setup-Edge-Re-Test | n ≥ 250 | Andere Marktphase zwingend (30.06.-Sample Mai–Juni-lastig, 91 % pre-#346). |
| **~Ende Sept 2026** | Exit-Timing B.1-Hinweis-Re-Test | n ≥ 250 | 01.07. Punktschätzung Δ ~+4 pp (5d/3d vs 10d in Score≥70-Bucket), Holm-negativ — Re-Test zur Bestätigung. |
| **Herbst 2026 / Q4 (OoS)** | **Hypothese H5 (Kombi Score × Katalysator × Momentum × SI)** | n ≥ 40 pro Feld-Kombi | **Vorab-registriert** (§5). Out-of-Sample über die **fünf** Look-Ahead-freien Sammel-Bausteine (§5). Feste Klammer, keine nachträgliche Schmälerung. |

### PAPER-PLAN-STATUS (Svoboda et al. 2026 — 4 Schritte A–C + Ausblick D, je 1/Tag)

**Kurz-Status 13.07.:** **A + B daten-seitig ENTBLOCKT** (13.07., yfinance-
SI-Position via #423) — **auswertbar nach ~2–3 Settlement-Zyklen** (der Seed
gibt ein 1-Monats-Delta ab Tag 1, echte OoS-Statistik erst mit n≥40 paper-
treuen Squeeze-Events, ~2–3 Monate). **C sammelt** (`entry_past_return_5d` ab
erstem Postclose non-null). **D bedingt** (nur nach belegten A–C). **Nächster
aktiver Schritt: A/B-AUSWERTUNG sobald Settlement-Zyklen da — bis dahin
SAMMELN, kein Bau nötig.**

Vorregistriert, **Schwellen aus FREMDEM Datensatz** (Overfitting-Schutz). Kein
Zeitdruck. Volle Paper-Befunde in §5.

| Schritt | Was | Status / Disziplin |
|---|---|---|
| **A** ✅ **ENTBLOCKT (daten-seitig, 13.07.)** | Binäre Zielvariable `squeeze_event` (Peak ≥ +30 % in 1 Handelswoche **UND** SI-Rückgang ≥ 20 %) **neben** `return_10d`. Adressiert „Häufigkeit ≠ Rendite-Edge" (§8h). | **SI-Positions-Quelle gefunden (yfinance, gratis) + gebaut (#423):** `si_position_history.json` sammelt die ausstehende SI-**Position** settlement-datiert **forward-only**. SI-Rückgang ≥ 20 % messbar. **Vorbedingung jetzt = Sammelzeit** (Seed gibt Startpunkte sofort), **kein** Daten-Blocker mehr. Peak-Seite via yfinance ohnehin machbar. Voller Befund §6i. **Nicht abspecken** (§8l: ohne Covering-Komponente kollabiert `squeeze_event` in die widerlegte Hypothese C). |
| **B** ✅ **ENTBLOCKT (daten-seitig, 13.07.)** | SI-Zuwachs in die 3 Literatur-Buckets (7–17 / 17–25 / > 25 % SI-Zuwachs). B **teilt A's Datenblocker** (Korrektur #419: nicht „ohne A"). | **Paper-treu machbar über dieselbe SI-Positions-Zeitreihe wie A** (`si_position_history.json` — 1-Monats-Positions-Delta via `sharesShort` vs. `sharesShortPriorMonth`). Auf `si_velocity_pub` (Volumen) werden die Paper-Schwellen weiter **nicht** gelegt (Nomenklatur-Falle §8m). |
| **C** *(sammelt)* | **Momentum als Haupthypothese** (`entry_past_return_5d` **positiv** = vorheriger Aufwärtstrend verstärkt), Reversal nur kurzfristige Nebenhypothese. Korrigiert die frühere „Reversal-Substrat"-Framing (§5). | Richtung vor der Auswertung fixiert (Paper: Momentum > Reversal). `entry_past_return_5d` non-null ab erstem Postclose (§3). Kein nachträgliches Umdrehen. |
| **D** *(Ausblick, bedingt)* | `squeeze_probability`-Score nach Paper-Modell aus den **validierten** Einzelfaktoren. Deklaration + Bedingungen unten. | **NUR falls A–C einzeln out-of-sample tragen.** Kein automatischer Folge-Schritt. |

**Backlog aus dem Paper** (§6g/§6h): Institutional-Ownership-Faktor (dämpfend),
Crash-Filter (Marktrückgang > 3 % → Modell blind).

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
### BOOTSTRAP-SHELL PHASE 1 (Flip) — NACH Phase-0-Zyklus-Verify (§3)

**Vorbedingung: der Phase-0-Zyklus-Verify (§3) muss sauber sein** (app.html
existiert, S9 grün, ki_agent zieht Top-10 aus app.html). **Nicht vorziehen.**

**Bau:** `index.html`-Content durch eine **winzige Shell** ersetzen:
- `<script>location.replace('app.html?v=' + Date.now())</script>` (eindeutige
  URL → Cache-Miss auf dem Content).
- **Apple-Meta zwingend** (`apple-mobile-web-app-capable` / `-status-bar-style`
  / `-title`) — sonst verliert der Launch **Standalone/Icon/Titel**.
- `<noscript><meta http-equiv="refresh" content="0; url=app.html"></noscript>`
  + sichtbarer Fallback-`<a href="app.html">`-Link.
- Viewport-Meta.

**Übergang (einmalige User-Adoption):** iOS hat die alte volle `index.html` im
Standalone-Cache → der Launcher zeigt sie weiter, bis adoptiert. Robustester Weg:
**Home-Icon löschen + neu „Zum Home-Bildschirm hinzufügen"** (re-captured die
start_url frisch). Alternativen: in-App „Aktualisieren" (`?v=`) oder `?bust=999`
+ Safari-App komplett beenden.

**Rollback:** Revert-PR macht `index.html` wieder zur vollen Seite — **unschädlich**,
weil die Parser seit Phase 0 `app.html` (mit index-Fallback) lesen.

**Restrisiko:** Deploy-Race (Shell live, bevor `app.html` deployed ist) → weiße
Seite ~5 Min. **Mitigiert** durch (a) `app.html`-first-Deploy (Phase 0 schreibt
es bereits), (b) `<noscript>`-Refresh + sichtbarer Fallback-Link in der Shell.

**Klassifikation:** Frontend + Golden + neue Datei-Struktur → **manueller Merge**;
Golden-Update (Shell-Content ≠ volle Seite — bewusste, große Golden-Änderung).

### Erledigt (nicht mehr im Backlog)

- **Hypothese C (Peak-Ziel, +10/+30/+50 %) — ERLEDIGT 04.07.2026.** Null belegt
  (0/6 Holm). Wiedervorlage frühestens Herbst 2026 mit Setup-Re-Test.

### Bau-Kandidaten (nicht Bau-Priorität — konkurrieren nach Re-Test-Befunden)

Reihenfolge erst nach belegten/nicht-belegten Edges. Pool: Synthetische
Utilization, Katalysator-Gating, Exit-Mechanik-Spec, Reddit-Velocity,
424B-Dilution (§5).

---

## 5) STRATEGISCHE ROADMAP — Edge-Suche

### EDGE-BEFUND (Stand 13.07.2026): AUFFANGLINIE UNVERÄNDERT

**Kernbotschaft:** Über **drei** aufeinanderfolgende Auswertungstage (30.06.
Endpunkt-Return · 01.07. Exit-Timing · 04.07. Peak-Ziel) hat **kein Prädiktor**
eine belegte Edge nach Erfolgs-Definition gezeigt. Das Tool ist **Attention-
Router / Screener**, **kein Alpha-Generator**. Nichts an dieser Linie hat sich
seit 30.06. verschoben.

**Erfolgs-Definition (einmal fixiert, nicht aufweichen):** „belegte Edge" nur
wenn (a) Holm-signifikant über der pre-registrierten Klammer, **UND** (b)
Bootstrap-CI-Untergrenze der AUC > 0.5, **UND** (c) plausibel im Regime-Split
reproduzierbar. Punktschätzung ist nie Beleg.

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
Synthetische Utilization ist im Bau-Kandidaten-Pool.

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

---

## 6) CODE-HYGIENE-BACKLOG (Status je Punkt)

### 6a. Alt-`finra_data.si_velocity` → `si_shares_per_day` umbenennen
**Status: OFFEN.** Displayfeld hat irreführenden Namen: `(newest_SI −
oldest_SI) / len(history)` ist **Shares/Tag absolut** (~90-Tage-FINRA-History),
nicht „Velocity". Rename zu `si_shares_per_day`, eigener PR. Touch-Fläche gemäß
grep 09.07.: 7 aktive Reads; CLAUDE.md-Sync; KI-Boost-Konsument. Kein Alt-
Backtest-Feld betroffen. Blast-Radius mittel. **Vor Rename: alle Konsumenten
greppen** (§8f).

### 6b. 5 andere bewegliche US-Feiertage algorithmisch berechnen
**Status: OFFEN.** Nach #407 ist nur **Karfreitag** algorithmisch. Fünf weitere
(**MLK Day**, **Presidents Day**, **Memorial Day**, **Labor Day**,
**Thanksgiving**) sind **hartkodiert bis 2027** → laufen 2028 aus (gleiche
Wartungs-Bombe wie Karfreitag vor #407). Kandidat: analog #407 mit „Nth-Weekday-
of-Month"-Formeln, Range 2020–2050. Kein Trading-Wert, Vorbeugungs-Hygiene.

### 6c. News-/FDA-Katalysator (Look-Ahead-Quelle ungeklärt)
**Status: OFFEN.** Voraussetzung: belegbar **point-in-time** verfügbare
News-/FDA-Announcement-Quelle. Vor dem Bau: Diagnose-Auftrag „welche Quelle ist
point-in-time?".

### 6d. Reversal-Backfill Stufe B/C für Hypothese A
**Status: OFFEN.** #402 ist Stufe A (Live-Vorwärts). Stufe B (einmaliger
yfinance-Backfill der ~420 v4-Alt-Records) analog `backfill_max_gain_pct.py`,
aber `fetch_start = earliest_edate − 14 Kalendertage`. Nur bauen wenn Hypothese
A explizit angeordnet ist. Beschleunigt Auswertung.

### 6e. yfinance-Cap-Aufhebung nach 1.5.x-Stabilisierung
**Status: OFFEN.** #403 hat `>=1.4.1,<1.5` gecappt. Sobald 1.5.x als stabil
belegt: Cap schrittweise lockern. Kein Termin — wartet auf externes Signal.

### 6f. v1/v2-Render-Pfad → reines Jinja
**Status: OFFEN (niedrig).** `generate_html_v2()` delegiert an v1; v1-Löschung
erfordert `templates/page.jinja` + `_wl_full_card_html`-Umbau (§7g). Kein
Trading-Wert.

### 6g. Institutional-Ownership-Faktor (Paper-Dämpfer)
**Status: OFFEN (Paper-abgeleitet 12.07.).** Svoboda et al.: hoher Institutional-
Ownership **dämpft** (**−6 % je +1 %**). Datenquelle yfinance
`heldPercentInstitutions` — **Vorbehalt: potenziell stale** (quartalsweise
13F-Latenz). Vor Nutzung read-only klären. Kein Score-Effekt ohne OoS-Beleg.

### 6h. Crash-Filter / Markt-Blind-Zone (Paper-Grenze)
**Status: OFFEN (Paper-abgeleitet 12.07.).** Paper: bei **Marktrückgang > 3 %**
ist das Modell **blind**. Kandidat: Tage mit Markt-Tagesrückgang > 3 % (`^GSPC`)
aus der Auswertung **ausschließen** (Regel-Screen). Marktkap + Markttrend im
Paper **nicht** signifikant → kein Regime-Score, nur harter Crash-Ausschluss.

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
time-queryable Gratis-Historie — die Serie ist forward-only). **Vorbedingung =
reine Sammelzeit**: n≥40 paper-treue Squeeze-Events mit messbarem SI-Rückgang
**~2–3 Monate**; der Seed liefert Startpunkte sofort. **Nächster Schritt nach
Sammelzeit: A/B-Auswertung gegen `si_position_history.json`** (OoS, §5).

**`si_velocity_pub` bleibt getrennt** (Tages-Volumen-Momentum) — Paper-Schwellen
7/17/25 % werden **nicht** daraufgelegt (§8m). **Restkante (Beobachtungspunkt,
kein Blocker):** falls yfinance `dateShortInterest` künftig als `Timestamp`
statt epoch-int liefert, wird der Punkt fail-soft **still** übersprungen (kein
Crash, aber Datenverlust ohne Log) — für die Wiedervorlage vermerkt (§3).

**Lesson (§8o):** Die Lösung lag im **eigenen Werkzeug** (yfinance spiegelt die
FINRA-SI-Position gratis) — gefunden erst **nach** erschöpfendem externem
Quellen-Check und **Verifikations-Probe (#422) statt Blind-Bau**.

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

---

## 8) LESSONS

*(Neueste zuerst: 8s–8u vom 14.07.-Nachmittag; 8q–8r vom 14.07.-Vormittag;
8n–8p vom 13.07.; 8j–8m vom 11.–12.07.; etablierte 8a–8i darunter.)*

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
Crash-Tage ausschließen (§6h), Ownership als Dämpfer-Kontext (§6g,
Staleness-Vorbehalt), keinen Marktkap-/Trend-Score bauen.

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

### 9e. Exzellenz-Selbstprüfung vor „Ready"-Meldung (Build-PRs)

Vor jeder Ready-Meldung, mit belegbaren Punkten (nicht Behauptungen):
1. **Widersprüche** — Diff-Beleg dass nur der beabsichtigte Scope getroffen wird
   (Doc-only: kein Logik-Touch).
2. **Nachweise** — Kern-Verhalten mit **Testausgabe / Repo-Beleg**, nicht
   behaupten (Hashes/Feldnamen/Zahlen aus Repo, Datums-Basis aus Repo).
3. **Fragile Annahmen** — None-Semantik, Edge-Cases, Timezone explizit.
4. **Determinismus** — Tests grün, CI-Runner grün, AST-Compile grün.

„Anspruch: exzellent" heißt genau das.

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

---

**Ziel dieses Dokuments:** neue Session arbeitet ab Prompt 1 im selben Modus,
ohne Wieder-Etablierung. Widersprüche zwischen SESSION_HANDOVER und CLAUDE.md →
CLAUDE.md gewinnt (dort steht die Codebase-Wahrheit; hier steht der Projektstand).
