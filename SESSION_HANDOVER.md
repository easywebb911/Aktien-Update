# Session-Handover — Stand 16.05.2026

## Heute implementiert (chronologisch)

Außerordentlich produktive Session — **16 PRs gemerged**, drei Major-
Pipelines abgeschlossen (RVOL-Normalisierung Phase 1, Health-Check-
Fail-Visibility, KI-Agent-Coverage-Erweiterung), zwei UX-Redesigns
(Konfidenz-Wasserzeichen, Methodik-Panel-Accordion) und mehrere
Bug-Fixes.

**Score-Inflation-Empirik-Pipeline (3-PR-Plan startet)**:
- `6d0336d` — **PR #165** refactor: RVOL-Disambiguation in ki_agent
  (4d-Basis als `rvol_4d` umbenannt + additives `rvol_20d`-Logging in
  agent_signals.json)
- `dd3d0f7` — **PR #166** feat: RVOL-Normalisierungs-Helper
  `_normalize_rvol()` + Konstanten + Feature-Flag
  (`RVOL_NORMALIZATION_ENABLED=False`)
- `f29bc95` — **PR #167** feat: `score_inflation_log` Schema v2 mit
  `drivers_raw.rel_volume_normalized` (parallele Empirik-Datensammlung)

**Health-Check-Pipeline (alle Fail-Visibility-Bugs adressiert)**:
- `2f3ad81` — **PR #168** fix: Health-Check-Digest mit 4-in-1 Fix
  (Cron `47 8`, exit 1 bei ntfy-Fail, S8-Invariant für stale Digest,
  Unicode-via-JSON-API gegen RFC-7230-Header-Bug)
- `1d756ea` — **PR #169** fix: Finnhub Provider-Health-Logging skippen
  wenn API-Key nicht konfiguriert (False-Positive eliminiert)
- `fe31d86` — **PR #175** fix: Tier-3 success_check Recalibration —
  edgar_8k/form4/13d_g/stocktwits-Fetcher returnen None bei echtem
  Outage, legitim leer zählt als success

**Frontend-UX-Verbesserungen**:
- `095e107` — **PR #170** fix: positions.current_price persistieren
  (schließt Health-Check S3 für 4 Position-Karten)
- `af019ef` — **PR #171** feat: Konfidenz-Wasserzeichen Phase 2 —
  Hybrid-Ansatz (Dimming + gepunktete Unterstreichung pro sb-num)
- `675ab88` — **PR #172** feat: Knaller-Trade-Label Phase 2 mit
  Bucket-P90/P10-Klassifikation aus backtest_history
- `086eeed` — **PR #173** feat: Knaller-Badge `▲ TOP 10%` /
  `▼ BOT 10%` statt Emoji (professioneller Look)
- `4a53a00` — **PR #174** feat: Score-Delta T-1 für Setup-Score mit
  Hybrid-Stille-Schwelle (|Δ|<2 = nichts rendern)
- `1f63cdc` — **PR #178** feat: Score-Methodik-Panel UX-Redesign —
  11 Sektionen als `<details>`-Accordion (Konfidenz default-open)
- `03ad70c` — **PR #179** fix: KI-Analyse padding-bottom in em statt
  fest 48 px (iPhone-Truncation bei großer Schrift behoben)

**Coverage-Erweiterungen (2-Phasen)**:
- `b0ad676` — **PR #176** feat: Conviction-Coverage Phase 1 —
  `apply_conviction_scores` läuft jetzt über Watchlist-Outsider-Pool
- `6b1f28d` — **PR #177** feat: KI-Agent-Coverage Phase 2 —
  `parse_monitored_tickers()` (Top-10 ∪ Watchlist ∪ Positions),
  Push-Spam-Schutz via Conviction-Gating + defensive None-Gating

## Aktive Positionen (Stand Ende 16.05.2026)

| Ticker | Status | Anmerkung |
|---|---|---|
| **AMC** | offen | Watchlist-Outsider — KI-Score ab nächstem KI-Agent-Tick |
| **IONQ** | offen | Watchlist-Outsider — KI-Score ab nächstem KI-Agent-Tick |
| **RR** | offen | Watchlist-Outsider — KI-Score ab nächstem KI-Agent-Tick |
| **CRMD** | offen | Diagnose heute: **Substrat intakt** (DTC 16, SF 21 %, Float 67.5 M, SI-Trend sideways). **Conviction 58 / medium** (von 98 am Entry runter). Phase-2 `exit_pressure` **28/100** (trend_break warn 50, profit_lock 26, overheated 33). **PnL −4.79 %** vom Entry $7.93. CRMD ist **kein Phase-3-Blow-off-Top-Fall** (`change_5d < 10 %`). Strategie: durchhalten. |

**Wichtige Hinweise zur Position-Karte**:
- `current_price` ist heute NULL für alle 4 Positionen (S3-crit) → Live-PnL fehlt im Frontend-Position-Panel
- **PR #170 wirkt erst beim nächsten Daily-Run** (heute postclose 21:17 UTC). Ab morgen sichtbar
- **KPTI heute geschlossen mit −17.3 %** nach Setup-bricht-Push (Conviction-Kalibrierungs-Beobachtung gestartet — siehe Lessons)

## Verifikation morgen 17.05.2026

| Slot | Was prüfen | Bezug |
|---|---|---|
| 08:47 UTC (10:47 dt.) | Health-Check-Digest-Push mit echten Inhalten (statt 100 %-False-Positive) | PR #168 + #169 + #175 |
| Erster KI-Agent-Tick | `agent_signals.json` enthält AMC/IONQ/RR/CRMD/AI-Keys (~15 Tickers statt 10) | PR #177 |
| Position-Karten | Live-PnL sichtbar (`current_price` gesetzt) | PR #170 |
| Top-10-Karten | Konfidenz-Wasserzeichen sichtbar (gepunktete Unterstreichung bei Conviction/KI) | PR #171 |
| Trade-Journal | `▲ TOP 10%` / `▼ BOT 10%`-Badges bei abgeschlossenen Trades | PR #172 + #173 |
| Top-10-Karten | Score-Delta `▲ +5.0` bei GEMI/TNXP/SKYQ | PR #174 |
| Methodik-Panel | 11 Sektionen kollapsibel, Konfidenz default-open | PR #178 |
| KI-Analyse | iPhone bei größter Schrift: letzte Zeile sichtbar über Home-Indicator | PR #179 |
| Watchlist-Drawer (CRMD) | KI-Score-Row vorhanden (vorher fehlend, Phase 2 erweitert Coverage) | PR #177 |
| CRMD-Drawer „Aktuelle Meldungen" | News-Items vorhanden | PR #163 (gestern) |

## Geplante Aufgaben + Wiedervorlagen

| Datum | Aufgabe | Trigger |
|---|---|---|
| **17.05.** | Health-Check-Digest-Push verifizieren + iPhone-Padding-Test bei größter Schrift | sofort morgens |
| **28.05.** | Earliness-Trend-Logging AUC-Re-Check (Schema v4, 14 d Live-Daten) | Datensammlung läuft |
| **30.05.** | **PR-γ aktivieren**: `RVOL_NORMALIZATION_ENABLED = True` mit empirischem Skalierer (Median des `rel_volume_normalized / rel_volume`-Quotienten aus 14 d v2-Logs) | nach PR #167 |
| **30.05.** | KI-Agent-Coverage-Empirik: Push-Spam-Volumen messen (> 5 zusätzliche Pushes/Tag → `WATCHLIST_OUTSIDER_CONVICTION_MIN` einführen) | nach PR #177 |
| **02.06.** | Chart-Indikatoren erweitern prüfen | Backlog |
| **13.06.** | Earliness V3 Entscheidung — DTC-Bucket-Logik mit Trend-Logging-Auswertung | Datensammlung läuft |
| **02.07.** | Premium-Daten-Stack prüfen (60 d Live-Daten, Konfidenz-Re-Assessment) | Datensammlung läuft |
| nach 5+ high-Conviction-Trades | **Conviction-Kalibrierungs-Beobachtung** — heutiges KPTI-Verlust trotz Conviction 81 als erstes Indiz | empirisch |
| nach Easy-Feedback | Score-Delta T-1 Phase 2 (Conviction/Monster/KI-History-Persistenz) | wenn Setup-Delta sich bewährt |
| pending Live-Test | **Phase-3-Exit-Implementation** (Blow-off-Top) — wartet auf parabolisches Endphasen-Setup (CRMD ist nicht das) | `docs/phase3_exit_spec.md` fertig |

**Erledigt heute**:
- ~~Konfidenz-Wasserzeichen Phase 2~~ → PR #171
- ~~Knaller-Trade-Label~~ → PR #172 + #173
- ~~Tier-3 success_check Recalibration~~ → PR #175
- ~~positions.current_price S3-Fix~~ → PR #170
- ~~Methodik-Panel UX-Redesign~~ → PR #178

## Optional / niedrig priorisiert

- **Drei-stufiges Provider-Health-Schema** (`ok` / `empty` / `fail`) — heute 2-stufig mit besserer Semantik reicht
- **Stündliche `current_price`-Updates** via KI-Agent-Tick — heute 2× täglich via Daily-Run reicht
- **Skeleton-UI** für ladenden Card-State — abgelehnt (kein akuter Bedarf)
- **Hotkeys** — abgelehnt (iPhone-Fokus)

## Strategische Roadmap

| Pipeline | Status | Nächster Meilenstein |
|---|---|---|
| Score-Inflation-Pipeline | PR-α/β heute (#166, #167), PR-γ am **30.05.** | Empirische Aktivierung nach 14 d v2-Daten |
| Conviction-Kalibrierung | Beobachtung gestartet (KPTI als erstes Indiz) | nach 5+ weiteren high-Conviction-Trades |
| Phase-3 Exit-Trigger (Blow-off-Top) | Spec fertig (`docs/phase3_exit_spec.md`) | wartet auf parabolisches Setup, NICHT CRMD |
| Earliness V2 → V3 | V2 läuft live mit AUC 0.77 | V3-Entscheidung am 13.06. |
| Backtest-Datenpunkte | 1263 (Bootstrap + Daily) heute | belastbare Live-Statistik ab Juli 2026 |
| KI-Agent-Coverage | Phase 2 live (15 Tickers) | Empirik-Auswertung 30.05. |

## Code-Hygiene-Backlog mit Status

| Punkt | Status |
|---|---|
| (1) v1/v2 Render-Pfad-Doku-Anker | erledigt PR #76 |
| (5/1) `score()` aus DISPLAY_PTS_MAX-Konstanten (Methodik-Cap-Drift-Schutz) | erledigt PR #84 |
| (6/A) `_drivers_breakdown` als Single Source of Truth | erledigt PR #83 |
| (2) v1/v2 Render-Pfad → reines Jinja (`page.jinja` + `wl_card.jinja`) | pending — größerer Refactor |
| (3) `generate_report.py` Monolith splitten | pending — größerer Refactor |
| (4) Template-Engine statt f-Strings | pending |
| (5/2) `score()` aus DISPLAY_PTS_MAX (Berechnungs-Seite) | pending |
| (6/B) `score()` aus DRIVER_CLASSIFICATIONS | pending |

**Heute keine Hygiene-PRs** — Fokus lag auf Feature-Pipelines + Bug-Fixes.

## Architektur-Anker (in dieser Session zementiert)

- **Auto-Merge-Regel ab 16.05.2026 final**: Subagent (squeeze-guardian) ist
  **Bonus, kein Gatekeeper**. Claude mergt selbst sobald Tests grün sind.
  Manueller Easy-Merge nur bei „neue JSON-Schemas, neue Workflow-Dateien,
  neue API-Integrationen, Score-/Conviction-/Filter-Logik-Änderungen".
- **Sandbox-Force-Push-Workaround**: Stacked-PR-Pattern wenn nötig
  (direkt-auf-`main` HTTP 403 seit 09.05.2026).
- **Caution-Prinzip**: read-only Diagnose VOR jeder Code-Änderung. User
  fragt explizit „NUR DIAGNOSE, kein Code" — Claude hält sich strikt daran.
- **Trading-Wert-Filter**: vor jedem PR die Frage „bringt das Trading
  konkret weiter?" — heute z. B. mehrere Phase-1-PRs (Coverage,
  Konfidenz) statt theoretischer Hygiene.
- **Zeit-Schätzungs-Regel**: Claude überschätzt Aufwand typisch 2-3× —
  bei nächster Session bei Aufwand-Angaben bewusst reduzieren oder
  Easy-Feedback abwarten.
- **Uhrzeit-Regel**: Claude weiß die echte Uhrzeit nicht — bei zeit-
  abhängigen Diagnosen (Cron-Slots, Wartezeiten) immer Easy fragen
  statt zu raten.
- **`<details>`-Accordion-Pattern** etabliert (PR #178) — Standard für
  künftige Methodik-Erweiterungen.
- **Hybrid-Stille-Schwelle-Pattern** (PR #174) — visuelle Hervorhebung
  nur ab signifikantem Delta (`|Δ| < 2` = nichts rendern). Anwendbar
  auf künftige Delta-/Trend-Anzeigen.
- **em-Padding für aufklappbare Mobile-Container** (PR #179) — CLAUDE.md-
  Pflege-Hinweis dokumentiert. Pattern für künftige iPhone-Bottom-Edge-
  Probleme.
- **Provider-Health-success_check-Semantik klarer** (PR #175) — „Call
  funktioniert" statt „Daten gefunden". Fetcher returnen `None` bei
  echtem Outage. Vorbild für künftige Tier-Provider.

## Lessons heute

1. **Tier-3-success_check-Bug-Klasse** war breiter als gedacht — Finnhub-
   Diagnose (PR #169) führte zu 4 weiteren Providern mit demselben
   Symptom (edgar_8k/form4/13d_g/stocktwits, PR #175). Eine Diagnose,
   fünf Fixes. **Pattern-Diagnose schlägt Einzelfall-Fix.**
2. **2-Phasen-Approach für Coverage-Erweiterungen** — Conviction-Coverage
   musste vor KI-Agent-Coverage gehen (Push-Spam-Schutz). Ohne Phase 1
   wäre Phase 2 broken gewesen (Gating-Filter hätte nicht gegriffen
   für Watchlist-Outsider).
3. **KPTI-Verlust trotz Conviction 81 high** = Kalibrierungs-Indiz.
   Conviction war hoch, aber Setup brach trotzdem. Erste Empirik gegen
   die `ANOMALY_CONVICTION_MIN_THRESHOLD = 75`-Schwelle gestartet —
   Beobachtung nach 5+ weiteren high-Conviction-Trades.
4. **CRMD ist kein Phase-3-Fall** — Pre-Earnings-Spike-Klassiker, nicht
   parabolischer Endphasen-Squeeze. `change_5d < 10 %`, kein Reversal-
   Pattern. Phase-3-Implementation wartet auf eine andere Position-Klasse.
5. **Score-Inflation-Empirik braucht 14 Tage Daten** bevor PR-γ-Aktivierung
   sinnvoll ist. Heute Helper + Schema v2 gebaut, OFF by default.
   Aktivierung am 30.05. mit echten Daten statt 0.10-Daumenwert.
6. **Knaller-Definition: Hybrid mit Floor schlägt reine P90/P10** — bei
   flachen Buckets (Median ≈ 0) wäre 3×-Median-Definition sinnlos. P90
   plus absoluter Floor (≥ 10 %) ist robust ab Trade #1.
7. **Skeleton-UI abgelehnt, Hotkeys abgelehnt** — iPhone-Fokus dominiert
   UX-Entscheidungen. Desktop-Power-User-Features sind out of scope.
8. **Diagnose-Reports vorm Code zahlen sich aus** — 8+ NUR-DIAGNOSE-
   Aufträge heute, jedes Mal saubere Bug-/Architektur-Klärung vor
   Implementation. Verhindert Fehl-Refactors.
9. **CSS-Padding fest in px vs em-skaliert mit Schrift** — schlummernder
   Mobile-UX-Bug (PR #179). Pattern für weitere Container im Backlog
   prüfen.
10. **`<details>`-Pattern ist Mobile-Gold** — 3500 px → ~700 px Methodik-
    Panel (PR #178). Native Browser-Accessibility, kein JS, Tap-Target
    automatisch. Vorbild für andere lange Read-only-Sektionen.
