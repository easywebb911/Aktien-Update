# Session-Handover — Stand 18.05.2026 (Provider-Outage gefixt)

| Meta | Wert |
|---|---|
| Datum | 18.05.2026 (Montag) |
| Final-PRs heute | **11 gemerged** (PR #206-#216) |
| Session-Dauer | Abend — Outage-Diagnose + 3 Provider-Fixes + 1 Health-Check-Tweak + 1 Feature |
| Vorgänger-Handover | 17.05.2026 (PR #205, 16 PRs) |
| Trigger der Session | Health-Check-Push 18.05. mit 1 CRIT + 5 WARN |

## (1) Heute implementiert (chronologisch)

| PR | Hash | Type | Kurzbeschreibung |
|---|---|---|---|
| #206 | `1c5bf47` | diag | Read-only Provider-Probe-Workflow `diagnose_provider_probe.yml` — 4 Probes (finviz, SEC×2-UA-Vergleich, stocktwits, earningswhispers) als Diagnose-Basis für Outage seit 15.05. |
| #207 | `3813b8c` | fix | **SEC EDGAR User-Agent compliance** — `config.py:903` + `generate_report.py:1878`. Alter UA `SqueezeReport/1.0 github-actions@squeeze-report.com` → `Easy Webb easywebb@yahoo.de`. HTTP 403 → 200, edgar_8k + edgar_form4 + fetch_sec_13f wieder lebendig |
| #208 | `6f241d5` | diag | Diagnose-Workflow Probe 2 — finviz Parser-Drift-Check (4 zusätzliche curl-Steps: `/screener`-Neu, `/quote/AMC`-Neu, `quote.ashx?t=AMC`-Vergleich, `rss.ashx`-Status) |
| #209 | `ed75edb` | diag | Diagnose-Workflow Probe 2.5 — Body-Limit 50 KB → 1 MB + Markup-Sniff um 5 Marker erweitert (`tr class`, `data-key`, `Float Short`, `SF `, `short_float`) + Body-Inline 1000 → 5000 chars für Probes 5+6 |
| #210 | `5a66358` | diag | Diagnose-Workflow Probe 3 — 4 zusätzliche Inspect-Steps: `href`-Patterns + Ticker-Header-Zeile + `>Short Float<`-Markup-Kontext |
| #211 | `d3d4881` | diag | Diagnose-Workflow finviz Screener Pagination-Probe (Probe 9 ohne r-Param, Probe 10 mit r=21, Inspect 9a/10a `quote?t=`-Pattern-Verifikation) |
| #212 | `3f21e5f` | fix | **finviz fetcher — URL/Markup-Drift Mai 2026** — 5 Stellen: `get_finviz_candidates` (URL + Pagination: page 0 ohne r-Param), `get_finviz_screener_v111` (URL + Regex `quote\?t=`), `_fetch_short_float_finviz` (BS4-Migration statt Regex auf `<a>`-wrapped `<b>17.51%</b>`), RSS deaktiviert (2 Stellen), Display-Links 2× |
| #213 | `b99dfb5` | fix | **health_check S4 Tagesbasis** — `evaluate_state_invariants` bekommt neuen kwarg `backtest_has_today`, postclose-Branch checkt jetzt ob Trading-Tag insgesamt min. 1 Eintrag hat (statt nur dieser Run hat appended). False-Positives bei Re-Trigger weg (4× WARN am 17./18.05.) |
| #214 | `b48c78e` | diag | Diagnose-Workflow stocktwits Burst (5 schnelle Calls) + earningswhispers URL-Discovery (Homepage-Sniff + 4 Kandidat-URLs) |
| #215 | `981e101` | feat | **stocktwits + earningswhispers deaktivieren** — `STOCKTWITS_ENABLED=False` + `EARNINGSWHISPERS_ENABLED=False` in `config.py`. Fetcher-Bodies durch frühe `return None`/`return {}` ersetzt, Caller-Gate in `_process_ticker` umgeht den Wrapper komplett. Re-Aktivierungs-Bedingungen dokumentiert |
| #216 | `ceadba5` | feat | **positions[ticker].no_exit_alerts Opt-Out** — Boolean-Feld auf Positions-Ebene. `True` → komplettes Skip aller Exit-Push-Trigger in Phase-1 (`process_exit_signals` generate_report) + Phase-2 (`process_exit_signals` ki_agent). Propagiert via `_build_phase2_positions_payload` mit `bool()`-Wrapper. Soft-Migration (Default False bei Bestandspositionen) |

## (2) Aktive Positionen (Stand 18.05.2026 Abend)

| Ticker | Status | Anmerkung |
|---|---|---|
| **AMC** | Halt-Strategie | `no_exit_alerts=true` im Gist gesetzt 18.05. abends — alle Exit-Pushes für AMC unterdrückt |
| **IONQ** | offen | — |
| **RR** | offen | — |
| **CRMD** | offen | Conviction 98 am 14.05. gekauft, aktuell -4.79%, Plan durchhalten |

## (3) Verifikation morgen 19.05.2026

- **Health-Check-Push 11:00-12:30 Berlin erwartet:** 0 CRIT, 0-1 WARN (deutliche Verbesserung gegenüber 18.05. mit 1 CRIT + 5 WARN)
- **Workflow-Log auf `[exit_p2] SKIP all AMC: no_exit_alerts=True` prüfen** — Verifikation dass PR #216 greift
- **`provider_health.jsonl`**: keine `stocktwits`- und keine `earningswhispers`-Zeilen mehr (Caller-Gates greifen)
- **finviz-Provider sollte Erfolge zeigen** (vorher 14/14 fail) — `_FINVIZ_ACCT` mit `http_status=200`, `item_count > 0`
- **`edgar_8k` + `edgar_form4` ebenfalls grün** — SEC-UA-Fix aus PR #207
- **S4 nicht mehr in den State-Fails** bei Multi-Run-Tagen — neue Tagesbasis-Logik aus PR #213
- **`health_check_digest_state.consecutive_failures`**: `stocktwits=69` und `earningswhispers=33` bleiben zunächst stehen, werden vom 7d-Stale-Cutoff in den nächsten 7 Tagen auf 0 zurückgesetzt

## (4) Geplante Aufgaben + Wiedervorlagen

| Datum | Aufgabe |
|---|---|
| **28.05.2026** | Earliness-Trend-Logging AUC-Re-Check (PR #142) |
| **30.05.2026** | PR-γ Score-Inflation-Normalisierung aktivieren (`RVOL_NORMALIZATION_ENABLED=True` + run_phase-aware Confidence-Stufen) |
| **30.05.2026** | KI-Agent-Coverage Empirik (14T Push-Spam-Check) |
| **02.06.2026** | Chart-Indikatoren prüfen |
| **07.06.2026** | Earliness V3 Entscheidung |
| **10.06.2026 ★★★** | **GROSSPROJEKT: Entry-Timing-Modul Start** — Entry-Score 0-100 pro Top-10-Kandidat, misst Reife im Moment. Mehrwöchig, höchste Priorität |
| **30.06.2026** | Backtest belastbar auswerten (V2-only ≥70-Bucket Sample ≈ 100 + 30 Tage Score-Inflation-bereinigt) |
| **02.07.2026** | Premium-Daten-Stack |
| bei Gelegenheit | Conviction-Kalibrierung nach 5+ weiteren high-Conviction-Trades |
| bei Gelegenheit | `_SEC_HEADERS`-Duplikat in `generate_report.py:1881` zentralisieren (Single-Source-Cleanup) |

## (5) Strategische Roadmap

- **Bis 30.05.**: Datenqualitäts-Fundament (PR-γ Score-Inflation neutralisieren)
- **Bis 30.06.**: Erste belastbare V2-only Backtest-Auswertung
- **Ab 10.06.**: Entry-Timing-Modul Grossprojekt (mehrwöchig, höchste Priorität)
- **Trading-Strategie aktuell**: bewusst wenige Trades bis Datenlage belastbar — Tool als Setup-Anzeiger, nicht Signal-Geber
- **Externer Backtest-Spezialist 18.05.** hat Median-Falle bestätigt und Entry-Timing-Notwendigkeit unabhängig bekräftigt — Konsens

## (6) Code-Hygiene-Backlog

| Größe | Status | Punkt |
|---|---|---|
| groß | offen | (1) v1/v2 Render-Pfad zu Jinja konsolidieren |
| groß | offen | (2) `generate_report.py`-Monolith splitten |
| groß | offen | (3) Template-Engine statt f-Strings für HTML-Render |
| mittel | offen | Cockpit Stage 3 Cleanup (`.sb`-Reste in Karten-Bereich) |
| klein | offen | `_SEC_HEADERS`-Duplikat zentralisieren (`generate_report.py:1881` importiert nicht aus `config.py`) |
| 5× klein | erledigt | alle vorherigen kleinen Punkte gefixt |

## (7) Architektur-Anker

- **Earliness V2** live seit PR #141 (AUC 0.77, DTC-Bucket-Mapping)
- **Phase-2 Exit komplett** — 6 Trigger (score_decay, profit_lock, overheated, setup_erosion, catalyst, trend_break), jetzt mit `no_exit_alerts`-Opt-Out (PR #216)
- **Live-Polling** via Cloudflare-Worker `quote-proxy` alle 15s (Watchlist-Drawer + expandierte Top-10-Karten)
- **Konfidenz-Wasserzeichen** (Phase 2 Hybrid-Dim) + **Score-Delta T-1** auf jeder Karte
- **Karten-Cockpit-Layout** (Bloomberg-Stil, Stage 2 live seit PR #199)
- **Health-Check-Push via ntfy** — S4 jetzt tagesbasiert (PR #213), Digest-Workflow 08:47 UTC mit URL-Pattern + ASCII-Title
- **Service-Worker raus** seit PR #188 (kein Offline-Cache mehr, GH-Pages-CDN-TTL 10 min)
- **Drift-Schutz für Score-Multiplier** via AST-Tests in `mock_test_score_multiplier_sync.py`
- **Tier-3 Provider Stand 18.05.**: stocktwits + earningswhispers **deaktiviert** (`*_ENABLED=False`), finviz wieder live (URL + BS4-Migration), edgar_8k/form4/13f mit korrektem SEC-UA
- **S4-Tages-Invariante** (NEU 18.05.): `backtest_has_today`-Kwarg in `evaluate_state_invariants`, postclose-Branch nutzt Tagesbasis statt Run-Basis; Re-Trigger am selben Trading-Tag kein False-Positive mehr
- **no_exit_alerts-Schema** (NEU 18.05.): optionales Boolean-Feld in `positions[ticker]` im Gist, propagiert durch `_build_phase2_positions_payload` mit `bool()`-Wrapper in `app_data["positions"]`

## (8) Lessons

- **Backtest 18.05.**: Score zeigt aktuell keine klare Edge in oberen Buckets, aber statistisch zu klein für „anti-prädiktiv". Confounders: Score-Inflation, V1/V2-Mix, n=32. Re-Visit 30.06.
- **Spezialisten-Validierung 18.05.**: externe Bestätigung Median-Falle + Entry-Timing-Modul-Notwendigkeit
- **Health-Check funktioniert wie designed** — 1 CRIT + 5 WARN heute aufgedeckt, alle gefixt oder pragmatisch deaktiviert. Push war der Trigger für die Outage-Session
- **Diff-Lesen**: GitHub Split-View zeigt Pre+Post parallel, nicht als Doppel-Zeile missdeuten. Hunk-Header `@@ -X,N +X,N @@` gleiche `N` = saubere Ersetzung. Passiert bei PR #207 + #209
- **Vorsichts-Prinzip** explizit in JEDEM Prompt benennen („absolute Vorsicht, kein Risiko") — Easy hat das heute konsequent durchgezogen, hat sich bewährt
- **Code-These nicht als Faktum übernehmen ohne Validierung** — siehe `fetch_sec_13f` Fehl-Befund in PR #207 (instrumentierung war bereits da, ich habe sie überlesen)
- **Feature-Flag-Pattern für Provider-Deaktivierung** (`STOCKTWITS_ENABLED`, `EARNINGSWHISPERS_ENABLED`, `SEC_13F_ENABLED`) — 1-Zeilen-Flip für Re-Aktivierung, Caller-Gate ergänzt für saubere Health-Check-Ausblendung
- **Externe Empfehlungen ernst nehmen, aber erst Confounders ausschließen** bevor Score-Logik geändert wird

---

**Outage-Bilanz:** Alle 5 ursprünglich failenden Provider (finviz, SEC EDGAR 8K, SEC EDGAR Form4, Stocktwits, EarningsWhispers) sind geheilt oder bewusst deaktiviert. Plus S4-False-Positive weg. Sauberer Abend, sauberer Stand für morgen.
