# SESSION_HANDOVER.md — Stand 17.07.2026 (entry_past_return_5d Backfill DURCH + Gate-Kalibrierung + Paper-C-Read)

**Zweck:** vollständige Übergabe an eine **neue Code-Session ohne Kontext der
alten**. Dieses Dokument + `CLAUDE.md` müssen zusammen ausreichen, um am
Projektstand direkt weiterzuarbeiten. Reine Doku, kein Logik-Touch.

**Datums-Basis (belegt, nicht Erinnerung):** Repo-Stand **17.07.2026**. Session-
Bogen 16.–17.07.: am **16.07.** die **entry_past_return_5d Stufe-B-Backfill-Kette**
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
  #430 im Status-Panel sichtbar (n=28). **Restkante bleibt vermerkt** (Beobachtung,
  kein Blocker): falls yfinance `dateShortInterest` künftig als `Timestamp` statt
  epoch-int liefert, wird der Punkt fail-soft **still** übersprungen.

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

### AKUT (weiterhin offen)

- **★ FINALER LANGZEIT-BEWEIS der Shell (morgen früh, PASSIV).** Nach dem nächsten
  **Postclose** einmal das Home-Icon tippen: zeigt die **„Stand: HH:MM"-Zeile** den
  **neuen Marktdaten-Stand** (nicht die gestrige eingefrorene Seite)? Das ist der
  finale Beweis, dass der Launcher dauerhaft frische Bytes zieht. Kein Bau — reine
  Beobachtung.

- **★ KLARSTELLUNG Stand-Zeile (Zwei-Run-Architektur, kein Bug):** **„Stand: HH:MM"
  = MARKTDATEN-Zeit** (nur volle Daily-Runs schreiben die Seite, 2×/Werktag) ·
  **„KI: HH:MM" = Agent-Tick** (stündlich, patcht nur `agent_signals.json` live).
  Beide dürfen **auseinanderliegen** — die HTML-Hülle ist legitim so alt wie der
  letzte Daily-Run, während die KI-Zeile frisch ist. **Kein Einfrieren, kein
  Defekt** (Diagnose 15.07.: Symptom „Seite 10:36, KI 17:50" war reines Timing).

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
| ✅ **DURCHGEFÜHRT 15.07.** | ki_signal_score-Edge-Re-Test | n=55 gereift | **KEIN belegter Effekt** (Details §5). Re-Test-Bedingung neu **datengetrieben, nicht kalendarisch:** **WIN-Bucket ≥ 20** (aktuell nur 13!) **UND zweites Marktregime** im Sample. Nicht „~Mitte Aug" — die Kalender-Angabe war irreführend, es zählt der WIN-Bucket + Regime-Diversität. |
| **~Ende Juli / Anfang Aug** (korrigiert) | Conviction-Edge (Prüfpunkt P3 aus 30.06.) | n ≥ 100 gereift | **Termin vorgezogen** (Sammel-Raten-Diagnose 15.07.): 112 gesammelt / 20 gereift → n≥100 gereift bereits ~Ende Juli/Anfang Aug (das frühere „~Ende Aug" war Puffer). Composite aus Setup/Earliness/Anomaly/Regime — Aggregations-Anzeige, Edge selbst unbelegt. |
| **~Mitte/Ende Sept 2026** (bestätigt) | Setup-Edge-Re-Test | n ≥ 250 gereift | Andere Marktphase zwingend (30.06.-Sample Mai–Juni-lastig, 91 % pre-#346). **Engpass gemessen:** Score≥70-Anteil nur **36 %** (~2,7 gereifte Score≥70-Records/Handelstag) → das bindet n≥250, nicht die Roh-Rate. |
| **~Mitte/Ende Sept 2026** (bestätigt) | Exit-Timing B.1-Hinweis-Re-Test | n ≥ 250 | 01.07. Punktschätzung Δ ~+4 pp (5d/3d vs 10d in Score≥70-Bucket), Holm-negativ — Re-Test zur Bestätigung. |

**Sammel-Rate (gemessen 15.07., Hard-Facts):** **10 Records/Handelstag** (nur
postclose, nur Top-10) = das Maximum ohne Populations-Wechsel. **Hard-Stop:
`return_10d`-Reifung = 10 Handelstage** (immutabel — jeder Record braucht ~2
Kalenderwochen, bevor er zählt). Warten ist hier **kein** Engpass, sondern der
eingebaute Out-of-Sample-Schutz (§8).
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

**Regel:** jede Paper-C-Auswertung muss explorativ (backfilled) und konfirmatorisch
(forward) **getrennt ausweisen**. **Explorativer Read DURCHGEFÜHRT 17.07.** (Slot-29
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
  (0/6 Holm). Wiedervorlage frühestens Herbst 2026 mit Setup-Re-Test.

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

### 6j. `apple-touch-icon` fehlt (Shell zeigt ggf. Blank-Screenshot beim Re-Add)
**Status: OFFEN (klein, kosmetisch).** Das Repo hat nur `favicon.svg`, **kein**
`apple-touch-icon`-PNG. Beim „Zum Home-Bildschirm hinzufügen" nimmt iOS mangels
Icon einen **Seiten-Screenshot** — nach dem Phase-1-Flip ist das die (fast leere)
„Lädt…"-Shell. Kandidat: `apple-touch-icon.png` (180×180) ins Repo + Link-Tag in
Shell **und** voller Seite. Rein kosmetisch (Home-Icon-Optik), kein Funktions-Bug.
Guardian-Hinweis aus #436.

### 6k. Stand-Zeile könnte beide Zeiten zeigen (Verwirrung „eingefroren?")
**Status: OFFEN (Kosmetik/UX).** Die Header-Zeile zeigt nur die Marktdaten-Zeit
(„Stand: HH:MM"). Weil die KI-Zeile stündlich vorläuft, wirkt die Seite morgens
scheinbar „eingefroren", obwohl die Zwei-Run-Architektur genau so gedacht ist
(§3-Klarstellung). Kandidat: die Zeile explizit **zweiteilig** rendern —
z. B. „Marktdaten 10:36 · KI 19:39" — dann ist die Divergenz selbsterklärend statt
verdächtig. Reine Anzeige, kein Datenpfad.

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
Handelstag), gebunden an die immutabele `return_10d`-Reifung (10 Handelstage) und
für Setup an die **neue-Marktphase-Auflage** (Kalender). Diese Auflage ist **by
design**: der Setup-Re-Test „~Ende Sept" ist absichtlich so terminiert, dass er in
einem **anderen Regime** läuft (OoS-Beweiswert). „Beschleunigen" hieße, entweder
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

---

**Ziel dieses Dokuments:** neue Session arbeitet ab Prompt 1 im selben Modus,
ohne Wieder-Etablierung. Widersprüche zwischen SESSION_HANDOVER und CLAUDE.md →
CLAUDE.md gewinnt (dort steht die Codebase-Wahrheit; hier steht der Projektstand).
