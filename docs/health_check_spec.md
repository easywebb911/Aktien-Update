# Health-Check-Workflow Spec

> **Status:** Spec-Dokument für die spätere Implementierungs-Session.
> **Kein Code, keine Implementierung in diesem Dokument.**
> Single-Source-of-Truth für die Anforderungen — alle Werte, Tier-
> Zuordnungen und Schwellen hier sind verbindlich für den Code-Bau.

## Zweck

Frühwarnsystem für Tool-Funktion und Datenquellen-Verfügbarkeit.
Hintergrund: der score_history-Pruning-Bug (PR #119) blieb **11 Tage
unentdeckt**, obwohl Symptome im Git-Log sichtbar waren (-48/-112 Zeilen
pro Daily-Run statt Anwachsen). Dieser Workflow soll solche stillen
Ausfälle automatisch erkennen — zwei orthogonale Bug-Klassen:

- **State-Invariants** (Outcome-Artefakte sind plausibel) — fangen
  Bugs wie #119, wo Pipeline-Code grün lief aber das geschriebene
  Artefakt sich falsch verhielt.
- **Provider-Health** (externe Datenquellen funktionieren) — fangen
  stille Datenausfälle (yfinance liefert leere History, Finviz blockt
  403, FINRA-Auth expired) während der Daily-Run scheinbar durchläuft.

Beide Klassen ergänzen Mock-Tests (Code-Logik) — siehe
SESSION_HANDOVER „Drei Achsen von Tests/Checks".

## Architektur

- **Detection-Frequenz:** nach jedem Daily-Run (premarket + postclose)
  UND nach jedem ki_agent-Tick (stündlich).
- **Persistenz:** `health_check_log.jsonl` + `provider_health.jsonl`
  im Repo-Root, 30-Tage-Cutoff (Pattern wie
  `score_inflation_log.jsonl`: append-only JSONL,
  `datetime.fromisoformat`-Cutoff, atomare `tmp + replace`-Writes
  beim Pruning).
- **Alarm-Modus:** **silent Logging** in der Detection-Phase. Pro
  Run nur Schreiben, kein Push. **Täglicher Digest-Push um 08:00 UTC**
  aggregiert die letzten 24 h.
- **Positives Feedback:** Bei **0 Fails** über die letzten 24 h →
  „alles grün"-Bestätigungs-Push. Damit ist die Push-Pipeline selbst
  täglich auf Liveness geprüft — wenn dieser Push ausbleibt, weiß
  Easy, dass ntfy oder der Digest-Workflow ausgefallen ist.

## State-Invariants (13)

**Lauf-Kontext:** S2/S3/S6/S8 laufen in BEIDEN Pfaden (Daily-Run +
ki_agent-Tick), alle übrigen nur im Daily-Run (``if not ki_agent_only``).
S9–S13 sind nach S1–S8 ergänzt; Detail-Sektionen weiter unten (S7-, S13-
Begründung).

| ID | Invariant | Severity | Lauf | Konkret geprüft |
|----|-----------|----------|------|-----------------|
| **S1** | `score_history.json` hat neue Einträge für Top-10-Ticker | **crit** | Daily | Letzter Eintrag pro Top-10-Ticker hat heutiges Datum |
| **S2** | `setup_scores` enthält ≥ 8 Tickers | **crit** | beide | `len(app_data.setup_scores) ≥ HEALTH_CHECK_S2_MIN_TICKERS` (8) |
| **S3** | Aktive Positionen haben `current_price != null` | **crit** | beide | Für jeden Ticker in `positions`: `positions_out[t].current_price != null` |
| **S4** | `backtest_history` hat heutigen Eintrag im `postclose`-Pfad (Tages-Basis); premarket darf nicht in den Backtest schreiben (Run-Basis) | warn | Daily | postclose: `any(e.date == today for e in backtest_history)`. premarket: `n_appended > 0` → WARN |
| **S5** | `score_inflation_log.jsonl` bekommt pro Run ≥ 10 Zeilen | warn | Daily | `wc -l`-Diff nach Run |
| **S6** | `monster_scores`: ≥ 3 Tickers > 0 | warn | beide | `sum(1 for s in monster_scores.values() if s > 0) ≥ 3` |
| **S7** | `agent_signals` ∩ Top-10 ≥ 5 | warn | Daily | `len(set(agent_signals.keys()) & set(top10_tickers)) ≥ HEALTH_CHECK_S7_MIN_AGENT_OVERLAP` |
| **S8** | Digest-Push-Pipeline frisch | warn | beide | Digest-Alter ≤ `HEALTH_CHECK_S8_MAX_AGE_HOURS` (26 h). Misst seit #274 `last_successful_run` (ISO-Timestamp), nicht mehr `last_digest_sent`. `None` → kein Fail (Erstaufsetzen) |
| **S9** | HTML-Sanity des gerenderten `index.html` | **crit**/warn | Daily | DOM-Klassen-Counts via `check_html_assertions`. crit wenn HTML-Fail crit, sonst warn; Check-Eigenfehler → warn. **Einziger CRIT-Block-Pfad** (`sys.exit` filtert strikt id=="S9"-crit) |
| **S10** | Daten-Integrität `backtest_history` (schema_v==4) | warn/**crit** | Daily | MUSS-Felder dauerhaft null (crit/warn je Schwelle), LAG-Felder ohne Outcome nach Trading-Tag-Lag (warn), Auto-Detect unklassifizierter Felder (warn) |
| **S11** | premarket-Sammel-Frequenz | warn | Daily | kein echter premarket-Run (`run_phase==tsp=='premarket'`) seit > `HEALTH_CHECK_S11_MAX_WORKDAYS_NO_PREMARKET` (5) Werktagen; Quelle `score_inflation_log` |
| **S12** | postclose-Sammel-Frequenz | **crit** | Daily | kein echter postclose-Run (`run_phase==tsp=='postclose'`) seit > `HEALTH_CHECK_S12_MAX_WORKDAYS_NO_POSTCLOSE` (2) Werktagen. **crit = NUR-REPORTING** (blockiert NICHT) |
| **S13** | Daten-Reife-Gate + Konsistenz-Wächter | warn | Daily | **Doppel-Baustein.** (a) Daten-Reife-Gate (#297): Status der 3 30.06.-Auswertungen (Setup-Edge ≥70/schema_v4, Entry-AUC, CTB-Edge) je vorhanden/reif_5d/reif_10d via log.info, kein Fail. (b) Konsistenz-Wächter (Projekt C, #298): Soll-Ist-Drift je config-Konstante aus `CONSISTENCY_EXPECTED_STATE` — ein warn pro Drift |
| **S14** | Gist-Pull-Liveness (Composite) | warn | beide | Marker-Alter `last_successful_gist_pull` (`gist_pull_state.json`) ≤ `HEALTH_CHECK_S14_MAX_AGE_HOURS` (26 h). Geschrieben NUR im HTTP-Gist-Erfolgszweig von `pull_gist_data.py` (#310). `None` → kein Fail (Erstaufsetzen, analog S8). **COMPOSITE** — Detail sagt „Gist-Pull seit N h nicht erfolgreich", NICHT „Token tot": altert bei totem `GIST_TOKEN` (Stille-Tod 02.06.) UND bei mehrtägigem ki_agent-/daily-Cron-Drop. Beide Pfade: ki_agent-Tick liest alten Working-Tree-Marker bei Pull-Fail → ~1 h Detektionslatenz. **Out-of-Scope** (separater PR): Body-Korruption (HTTP-200 + kaputtes `squeeze_data.json` → Marker fälschlich frisch) |

### S14 — Gist-Pull-Liveness (Stille-Tod-Härtung Schritt 2/2, 03.06.2026)

Fängt den Vorfall 02.06.2026: ein toter `GIST_TOKEN` ließ den Gist-Read über
Tage scheitern, der Recovery-Fallback in `pull_gist_data.py` überbrückte
still (geschlossene Positionen RR/CRDF/INDI wurden als offen materialisiert →
Geister-Exit-Pushes). Der `last_successful_gist_pull`-Marker (#310, Schritt
1/2) wird NUR im HTTP-Gist-Erfolgszweig geschrieben → altert genau bei
anhaltendem Gist-Read-Fehler.

**Composite-Charakter (bewusst):** S14 ist kein reiner Token-Monitor. Der
Marker altert auch, wenn beide Workflows (ki_agent stündlich 7×/Woche, daily
2×/Werktag) über > 26 h nicht laufen/committen — eine andere Fehlerklasse
(Cron-Drop), aber ebenfalls alarmwürdig. Der Detail-Text formuliert daher
neutral „Gist-Pull seit N h nicht erfolgreich". Operatoren disambiguieren
über die übrigen Provider-Health-Signale.

**Schwelle 26 h:** im Gesund-Zustand schreibt der ki_agent den Marker
stündlich (Cron `17 * * * *`, jeden Tag inkl. Wochenende) → realer Healthy-
Max-Gap ~3–6 h (GitHub-Scheduled-Cron-Verzug). 26 h = > 4× Marge → praktisch
null Fehlalarm, fängt den Token-Tod trotzdem innerhalb ~1 Tag statt
„mehrtägig". KEIN Wochenend-Bias (ki_agent läuft Sa/So weiter).

**Out-of-Scope (separater PR):** Body-Korruption — HTTP-200 + kaputtes
`squeeze_data.json` → `_extract_data` kollabiert still auf `{}` → Marker würde
fälschlich als Erfolg aktualisiert. Andere Fehlerklasse als der Token-Tod
(dort ist `_http_get_gist` bereits `None`). `_extract_data` bewusst unberührt.

### S7 — Begründung (KI-Score-Drift, 14.05.2026)

Diagnose 14.05.2026: Daily-Run rendert auf allen Top-10-Karten ohne
KI-Score, weil ``agent_signals.json`` die Top-10-Ticker vom Vortag
enthält und der heutige Daily-Run komplett andere Tickers selektiert
hat. Schnittmenge = ∅ → ``apply_agent_boost`` matcht keinen Ticker →
``s["ki_signal_score"]`` bleibt None → Render-Pfad lässt die KI-Score-
Zeile weg.

S7 fängt diese Klasse von Drift-Bug. Strukturelle Hauptlösung: der
Daily-Run triggert seit dieser PR automatisch einen KI-Agent-Tick am
Ende (``gh workflow run ki_agent.yml``, non-blocking). S7 ist das
Restrisiko-Netz für die Lücke zwischen Trigger und Tick-Completion
bzw. für gedroppte ki_agent-Cron-Slots.

**ki_agent-Tick prüft S7 NICHT** — wäre tautologisch, weil der Tick
selbst ``agent_signals.json`` schreibt und naturgemäß auf der Top-10
arbeitet, die er via ``parse_top_tickers()`` aus index.html zieht.

### S13 — Daten-Reife-Gate (30.06.-Auswertungen, 31.05.2026)

Rein lesender Status-Reporter (``evaluate_data_maturity_gate`` in
``health_check.py``). Meldet „laufend" (``log.info`` aus
``evaluate_state_invariants``, nur Daily-Run, fail-soft analog S10) die
Stichproben-Reife der drei 30.06.-Auswertungen — und warnt NUR bei einer
deklarierten Vorbedingungs-Verletzung.

**Vier Status-Zeilen (immer da, auch ohne Fail):**
1. **Setup-Edge** (``score >= 70``, ``backtest_schema_version == 4`` via
   ``_s10_load_v4_entries``): vorhanden / reif_5d / reif_10d.
2. **Entry-AUC** (``entry_score`` gesetzt): vorhanden / reif_5d / reif_10d,
   sonst „Modul ungebaut, n=0" (Modul-Start 10.06.).
3. **CTB-Edge** (``cost_to_borrow`` gesetzt): mit_CTB / reif_5d / reif_10d,
   sonst „Persistenz ungebaut, n=0".
4. **Konsistenz-Wächter** (Projekt C): je config-Konstante
   ``name=Ist/Soll [OK|DRIFT]`` (s. u.).

**Reife-Definition:** „reif" = Forward-Label ``return_5d`` / ``return_10d``
nicht ``None``. Beide werden GETRENNT gemeldet, weil die 30.06.-Auswertung
**noch nicht als Code codifiziert** ist — das Gate nimmt keine der beiden
Definitionen vorweg. Bei Codifizierung der Auswertung die hier gezählte
Definition damit abgleichen (gleiche Bucket-Grenze ≥70, gleicher
schema_v==4-Filter).

**Konsistenz-Wächter (Projekt C) — 4. Status-Zeile + Drift-Warns:** Soll
vs. Ist je deklarierter config-Konstante aus ``CONSISTENCY_EXPECTED_STATE``
(Single-Source-Dict in ``config.py``). IST wird live via
``getattr(config, name)`` gelesen; pro driftendem Wert ein WARN (severity
``warn``, id ``S13``, ``detail`` nennt Konstante + Soll + Ist). Solange
Ist==Soll ist das Gate **still**.

Erst-Umfang = drei STABILE, getattr-lesbare Konstanten, deren stiller Drift
echten Schaden anrichtet:

| Konstante | Soll | Schaden bei Drift |
|---|---|---|
| ``RVOL_NORMALIZATION_ENABLED`` | ``EXPECTED_RVOL_NORMALIZATION`` (False) | γ-2-Erwartung ≠ realer Flag-Zustand |
| ``SCORE_NORMALIZATION_VERSION`` | 1 | pre/post-γ-Confounder in der 30.06.-Auswertung |
| ``EARLINESS_FORMULA_VERSION`` | 2 | Fall auf 1 = Conviction-Earliness-Bruch |

**Aufnahme-Regel:** NUR stabile, ``getattr``-lesbare Konstanten mit
Schaden-bei-stillem-Drift. NICHT aufnehmen: volatile Tunables (Conviction-
Schwellen, Provider-ENABLED-Flags, Override-Dicts), Crons (Drift entsteht
zur Laufzeit, nicht im YAML-Wert → S11/S12), Code-Literale (``schema_v==4``
→ AST nötig). Bei γ-2: ``SCORE_NORMALIZATION_VERSION``-Soll gemeinsam mit
``RVOL`` auf 2/True ziehen (gepaart).

**Kein neues Schema-Feld, kein Score-/Filter-/Auswertungs-Touch.** Liest
nur bestehende backtest_history-Felder + zwei config-Flags.

## Provider-Tiers

> **Phase-2-Implementations-Status** (Stand PR „Health-Check Phase 2
> Tier-1"): die vier Tier-1-Aggregate sind in `provider_health.jsonl`
> instrumentiert. Tier 2 + 3 folgen in Folge-PRs. Diagnose-Klärung
> (15.05.2026):
> - VIX/SPY/FX als logischer Provider `yfinance_singletons` (Tier 1).
>   Daily-Run emittiert eine Zeile (SPY + FX, max 2 items), KI-Agent
>   eine Zeile (VIX, max 1 item). Phase-3-Digest aggregiert.
> - Tier-3 (StockTwits/UOA/News): 3 getrennte Provider-Zeilen statt
>   Spec-Wortlaut-Aggregat.
> - EDGAR: 4 getrennte Provider-Zeilen (`edgar_13f`, `edgar_8k`,
>   `edgar_form4`, `edgar_13d_g`).

### Tier-1 (crit, sofortiger Alarm bei Fail)

- **Yahoo Screener** (primäre Ticker-Quelle) — Provider-Key
  `yahoo_screener`
- **Finviz v161 / v111 / Quote-Page-Fallback** (rel_volume,
  short_float, Sektoren) — Provider-Key `finviz` (Aggregat)
- **yfinance Batch** (Preise, RSI, EMA21, change_2d/3d) —
  Provider-Key `yfinance_batch`
- **yfinance Singletons** (^VIX + ^GSPC + EURUSD=X) —
  Provider-Key `yfinance_singletons`

### Tier-2 (warn, erst bei wiederholtem Fail)

- **FINRA Short-Volume Sums** — Provider-Key `finra`
- **Finnhub Earnings Calendar** — Provider-Key `finnhub`
- **Stockanalysis-Konsolidierung** — Provider-Key `stockanalysis`
- **EarningsWhispers** — Provider-Key `earningswhispers`

### Tier-3 (warn, erst bei wiederholtem Fail)

Klärung 15.05.2026: keine Aggregate, sondern getrennte Provider-Keys
für saubere Coverage-Berechnung und Phase-3-Digest-Granularität.

- **StockTwits** — Provider-Key `stocktwits` (Social-Sentiment)
- **UOA (Options-Activity)** — Provider-Key `uoa` (Calls/Puts-Ratio)
- **News-RSS** — Provider-Key `news_rss` (Finviz / Google / Yahoo /
  UnusualWhales / MarketBeat / SeekingAlpha)
- **EDGAR 13F-Filings** — Provider-Key `edgar_13f`
- **EDGAR 8-K-Filings** — Provider-Key `edgar_8k`
- **EDGAR Form 4 (Insider-Transaktionen)** — Provider-Key `edgar_form4`
- **EDGAR 13D/13G (Stake-Erklärungen)** — Provider-Key `edgar_13d_g`

## Provider-Trigger-Bedingungen

| Bedingung | Tier-1 (crit) | Tier-2/3 (warn) |
|-----------|---------------|-----------------|
| HTTP-Fehler 4xx/5xx | sofort | 3 in Folge |
| Coverage < 80 % | sofort | < 50 % |
| Werte alle NaN/null | sofort | 3 Runs in Folge |
| Letzte Aktualisierung > 24 h | sofort | > 48 h |
| Latenz > 30 s | nur Log | nur Log |

## Persistenz-Schema

### `provider_health.jsonl` (eine Zeile pro Provider pro Run)

```json
{
  "run_ts":       "<UTC-ISO-8601>",
  "run_phase":    "premarket|postclose|ki_agent_tick",
  "provider":     "<name>",
  "tier":         1,
  "http_status":  200,
  "latency_ms":   <int>,
  "item_count":   <int>,
  "coverage_pct": <float>|null,
  "nan_pct":      <float>|null,
  "error":        "<string>"|null
}
```

### `health_check_log.jsonl` (eine Zeile pro Run mit Aggregat)

```json
{
  "run_ts":    "<UTC-ISO-8601>",
  "run_phase": "...",
  "state_fails": [
    {"id": "S1", "detail": "..."}
  ],
  "provider_fails": [
    {
      "provider":    "...",
      "tier":        1,
      "reason":      "...",
      "consecutive": <int>
    }
  ]
}
```

## Daily-Digest-Format

> **Phase-3-Implementations-Status:** umgesetzt mit Workflow
> `.github/workflows/health_check_digest.yml`, Tool-Skript
> `scripts/health_check_digest.py` und Helper-Erweiterungen in
> `health_check.py`. Klärungen 15.05.2026:
> - **Cron-Offset auf `13 8 * * *`** (statt Spec-Wortlaut `0 8`)
>   analog ki_agent xx:17 als Schutz gegen GitHub-Actions-Last-Peak-
>   Drops zur vollen Stunde.
> - **Counter-Storage in separater Datei** `health_check_digest_state.json`
>   statt `agent_state.json["provider_health_state"]` — letzteres hätte
>   Race-Conditions mit ki_agent (stündliche Writes) + Daily-Run +
>   Digest-Workflow auf demselben State-Slot erzeugt. Die separate
>   Datei ist write-once (nur Digest-Workflow schreibt).
> - **`📭 Health-Check ohne Daten`-Klasse** zusätzlich zu OK/Digest
>   (Frischbild-Edge-Case: leere JSONL-Files signalisieren Run-Ausfall,
>   nicht „alles grün").
> - **Mehrfach-Trigger-Schutz**: `last_digest_sent`-Datum verhindert
>   doppelten Push am selben Tag bei manuellem `workflow_dispatch`.
> - **7-Tage-Drift-Schutz**: stale Provider-Counter (z. B. dauerhaft
>   `ENABLED=False`) werden automatisch zurückgesetzt.

Digest-Workflow läuft täglich 08:13 UTC, liest die letzten 24 h aus
beiden `.jsonl`-Files, aggregiert nach Severity, schickt **einen**
Push.

### Bei Fails (≥ 1 crit oder ≥ 3 warn)

ntfy-Priority `high`, Titel `⚠️ Health-Check-Digest`. Body-Format
(verbindliche Reihenfolge):

```
⚠️ Health-Check-Digest <YYYY-MM-DD>
🔴 <N crit> · 🟡 <N warn> · ✅ <N ok>

State-Fails:
  • S1: score_history stagniert (Top-10 ohne heutiges Datum)
  • S3: AMC ohne current_price (5 Runs in Folge)

Provider-Fails:
  • Yahoo Screener (Tier 1): HTTP 503 sofort
  • Finnhub (Tier 2): 3× Coverage 0%

Letzter erfolgreicher Run: <ISO-Timestamp>
```

Felder weglassen, wenn leer (keine State-Fails → Sektion entfällt
komplett, kein „—"-Platzhalter).

### Bei 0 Fails

ntfy-Priority `default`, Titel `✅ Health-Check OK`. Kurzer
Bestätigungs-Push:

```
✅ Health-Check OK <YYYY-MM-DD>
24h ohne Fails. <N> Runs geprüft (premarket + postclose + ki_agent).
Letzter Run: <ISO-Timestamp>
```

Zweck: Push-Pipeline-Liveness-Check. Wenn dieser Push **ausbleibt**,
weiß Easy ohne weiteres Hinschauen, dass entweder der Digest-Workflow
nicht lief, ntfy down ist, oder Token-Probleme bestehen.

## Implementierungs-Hinweise (für spätere Code-Session)

- **Modul `scripts/health_check.py`** analog dem
  `scripts/push_history.py`-Pattern. Zwei Helper:
  `record_run(state_results, provider_results, run_phase)` und
  `prune_logs(max_days=30)`.
- **Hook-Points:**
  - am Ende von `main()` in `generate_report.py` (Daily-Run, beide
    Phasen)
  - am Ende von `ki_agent.py` (stündlicher Tick)
- **Digest-Workflow:** separater
  `.github/workflows/health_check_digest.yml` mit Cron `0 8 * * *`.
  Liest beide `.jsonl`, baut Push-Body, schickt via NTFY-Topic.
- **Mock-Tests:** für jeden State-Invariant + jede Provider-Tier-
  Klasse je ein Fail-Pfad + Pass-Pfad. Analog
  `mock_test_score_inflation_log.py`-Stil (`scripts/mock_test_*.py`,
  keine pytest-Abhängigkeit, plain assertions + Runner).
- **Idempotenz:** Re-Run am selben Tag (z. B. zweimaliger
  workflow_dispatch) darf nicht doppelt zählen. Empfohlen: pro
  Provider-Tier-Klasse pro `run_phase` höchstens ein Eintrag pro
  Stunden-Slot via `(run_ts hour-truncated, run_phase, provider)`-
  Dedup-Key.
- **Provider-Probes:** pro Provider ein leichter Probe-Call (z. B.
  Yahoo Screener „Test-Ticker AAPL", FINRA „Test-Date 2025-01-02",
  yfinance „SPY 1 day"). Probes laufen im selben Workflow wie die
  echte Datenabfrage und nutzen die in-process Latency-Messung —
  keine zusätzlichen HTTP-Calls.
- **Provider-State-Persistenz für „N in Folge":** Counter in
  `agent_state.json["provider_health_state"]` pro Provider, Reset
  bei erfolgreichem Run.
- **Fail-soft:** Ein Bug im Health-Check-Modul darf den Daily-Run
  NICHT crashen. Try/except + WARNING-Log, kein Re-Raise.

## Out-of-Scope für erste Iteration

- **Trend-Erkennung** („Coverage sinkt seit 7 Tagen kontinuierlich")
- **Self-Healing** (Auto-Retry bei transient errors)
- **Provider-Failover** (Finviz down → alternative Quelle)
- **Frontend-Anzeige** des Health-Status (kommt evtl. später als
  Aufklapp-Sektion analog zum Push-Historien-UI)
- **Multi-Channel-Eskalation** (E-Mail bei mehrfachen crit-Fails) —
  erst nach Empirik, ob ntfy reicht

## Pflege

- Bei Schema-Änderung an einem der `.jsonl`-Files: Version-Marker im
  Eintrag (`"schema_v": 1`) ergänzen + Migrations-Pfad im Reader
  dokumentieren.
- Neue Provider hinzufügen: Tier-Zuordnung in dieser Spec eintragen,
  Probe-Logik in `health_check.py` ergänzen, Mock-Test ergänzen.
- Schwellen-Änderungen (z. B. Coverage 80 % → 90 %): hier in der
  Tabelle aktualisieren UND als Konstante in `config.py` mit Bezug
  auf diese Spec-Sektion.

## Verlinkung

- **SESSION_HANDOVER Backlog-Punkt 15** verweist auf dieses Dokument
  als Spec-Quelle.
- **CLAUDE.md** sollte beim Code-Bau eine Sektion „Health-Check-
  Workflow" bekommen, die diese Spec referenziert (kein Duplikat —
  Single-Source-of-Truth hier in `docs/health_check_spec.md`).
