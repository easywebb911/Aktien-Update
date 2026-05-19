# Session-Handover — Stand 19.05.2026 (Outage-Tag-2 + PR #226 Revert)

| Meta | Wert |
|---|---|
| Datum | 19.05.2026 (Dienstag) |
| Final-PRs heute | **11 gemerged** (PR #217-#227, davon 1 Revert) |
| Session-Dauer | Tag — durchgehende Diagnose- + Refactor-Iteration |
| Vorgänger-Handover | 18.05.2026 (PR #217, 11 PRs) |
| Trigger der Session | Health-Check-Push 19.05. mit 1 CRIT + 4 WARN |

## (1) Heute implementiert (chronologisch)

| PR | Hash | Type | Kurzbeschreibung |
|---|---|---|---|
| #217 | `dcc997a` | docs | SESSION_HANDOVER.md update — 18.05.2026 Provider-Outage gefixt |
| #218 | `1f8db09` | diag | finviz Probe 14 — Per-Ticker-Quote-Page Block-Test (8 Tickers AMC/IONQ/RR/CRMD/GME/NVDA/AAPL/TSLA, 0.3s Sleep) |
| #219 | `156bc9d` | diag | log.warning für finviz fallback stage 3 — zeigt welche Tickers obskure Coverage-Lücke haben |
| #220 | `2fe99db` | fix | **finviz Tier-1 → Tier-2** — Stufe-3-Fallback, nicht primäre Datenquelle. Coverage 50-60% kein CRIT mehr, sondern 3-in-Folge-WARN |
| #221 | `93af750` | refactor | `_SEC_HEADERS`-Duplikat eliminiert — Single-Source aus `config.SEC_HEADERS` |
| #222 | `d711e99` | feat | **HTTP-Status aus requests.HTTPError** propagiert (Variante D) — 5 Inline-Emit-Sites, `[HTTP 403]`-Suffix bei HTTPError |
| #223 | `d1b477e` | feat | **Aggregator-Provider mit Exception-Repr** im `error`-Feld (Variante E) — 6 Aggregator-Sites + `last_error_repr` first-fail-wins in `provider_acct_record` |
| #224 | `446f9e7` | cleanup | Stufe-3-Log entfernt (Diagnose aus PR #219 erledigt — H1 bestätigt: obskure Smallcaps wie ENHA/CRNT/SCOR/PBT) |
| #225 | `e36d7d6` | fix | **Stufe-3-Skip bei `yf_sf > 0`** — spart 3-5 unnötige finviz-Calls/Run für Tickers mit kleinem aber validem SF (CRNT 0.22, SCOR 0.35, PBT 0.25) |
| #226 | `5d3f41d` | feat+refactor | Score-Delta-T-1 ins Cockpit + Rollback-Pfad entfernt + .sb-Reste aufgeräumt — **REVERTED durch #227** wegen Watchlist-Bruch |
| #227 | `3998d0b` | revert | PR #226 reverted — Watchlist-Ticker auf iPhone verschwunden, Bug-Analyse offen |

## (2) Aktive Positionen (Stand 19.05.2026 Abend)

| Ticker | Status | Anmerkung |
|---|---|---|
| **AMC** | Halt-Strategie | `no_exit_alerts=true` im Gist seit PR #216 — alle Exit-Pushes unterdrückt |
| **IONQ** | offen | — |
| **RR** | offen | — |
| **CRMD** | offen | Conviction 98 am 14.05. gekauft, aktuell ≈ −5%, Plan durchhalten |

**Keine neuen Trades heute** trotz CRDF Setup 99.7 — bewusste Disziplin gegeben Backtest-Lage (keine klare Edge ≥70-Bucket).

## (3) Verifikation morgen 20.05.2026

- **Health-Check-Push 11:00-12:30 Berlin erwartet:** 0 CRIT, 0-1 WARN
  - finviz nach Tier-Downgrade kein CRIT mehr (Tier-2 = 3-in-Folge → WARN)
  - stocktwits + earningswhispers fallen aus dem 24h-Window (Vor-#215-Einträge entfernt)
  - S8 (Digest-Push-Lag) heilt sich automatisch nach erstem 0-Fail-Push
- **`provider_health.jsonl`** zeigt echte HTTP-Status (403/429/...) statt `null` in den 6 Inline-Providern + aussagekräftiges `error`-Feld in den 6 Aggregator-Providern (statt nur `"N/M calls failed"`)
- **Watchlist-Karten wieder sichtbar auf iPhone** nach Revert-PR #227
- **`_FINVIZ_ACCT["calls"]`** geht runter (Stufe-3-Skip aus #225 + Tier-Downgrade aus #220)
- **Score-Delta T-1 auf Karten:** **weiterhin NICHT sichtbar** (Bug aus Cockpit-Wechsel — wurde durch #226 versucht zu heilen, ist mit Revert wieder offen)

## (4) Geplante Aufgaben + Wiedervorlagen

| Datum | Aufgabe |
|---|---|
| **20.05.2026** | Cockpit Stage 3 Re-Versuch mit Bug-Analyse VORAB — was im Cleanup hat den Watchlist-Drawer gebrochen? Verdachts-Kandidat: `_wl_full_card_html`-Regex-Strip oder gelöschte Mock-Test-Schutz-Schicht |
| **28.05.2026** | Earliness-Trend-Logging AUC-Re-Check (PR #142, Schema v4, 14 d Live-Daten) |
| **30.05.2026** | PR-γ Score-Inflation-Normalisierung aktivieren (`RVOL_NORMALIZATION_ENABLED=True` + run_phase-aware Confidence-Stufen) |
| **30.05.2026** | KI-Agent-Coverage Empirik (14 T Push-Spam-Check) |
| **02.06.2026** | Chart-Indikatoren prüfen — TTM Squeeze, VWAP, OBV als Entry-Score-Komponenten |
| **07.06.2026** | Earliness V3 Entscheidung |
| **10.06.2026 ★★★** | **GROSSPROJEKT: Entry-Timing-Modul Start** — Entry-Score 0-100 pro Top-10-Kandidat. Mehrwöchig, höchste Priorität |
| **30.06.2026** | Backtest belastbar auswerten (V2-only ≥ 70-Bucket Sample ≈ 100 + 30 Tage Score-Inflation-bereinigt) |
| **02.07.2026** | Premium-Daten-Stack prüfen |
| bei Gelegenheit | Conviction-Kalibrierung nach 5+ weiteren high-Conviction-Trades |
| offen | Score-Delta T-1 im Cockpit sichtbar machen (separater Folge-PR nach Bug-Analyse aus #226) |

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
| mittel | offen | Cockpit Stage 3 Cleanup Re-Versuch (Watchlist-Bug verstehen, dann sauber durchziehen) |
| klein | erledigt PR #221 | `_SEC_HEADERS`-Duplikat zentralisiert |
| 5× klein | erledigt früher | alle vorherigen kleinen Punkte gefixt |

## (7) Architektur-Anker

- **Earliness V2** live seit PR #141 (AUC 0.77, DTC-Bucket-Mapping)
- **Phase-2 Exit komplett** — 6 Trigger, mit `no_exit_alerts`-Opt-Out (PR #216)
- **Live-Polling** via Cloudflare-Worker `quote-proxy` alle 15 s
- **Konfidenz-Wasserzeichen** + **Score-Delta T-1** — Score-Delta seit Cockpit-Wechsel unsichtbar (offen)
- **Karten-Cockpit-Layout** (Bloomberg-Stil, Stage 2 live seit PR #199, Stage 3 reverted)
- **Health-Check-Push via ntfy** — S4 jetzt tagesbasiert (PR #213)
- **Service-Worker raus** seit PR #188
- **Drift-Schutz für Score-Multiplier** via AST-Tests
- **Tier-3 Provider Stand**: stocktwits + earningswhispers deaktiviert (PR #215), finviz wieder live aber **Tier-2** (PR #220)
- **HTTP-Status + Error-Repr in `provider_health.jsonl`** seit PR #222 + #223 — Diagnose-Infrastruktur deutlich besser
- **`_SEC_HEADERS` Single-Source** aus `config.py` seit PR #221
- **finviz-Stufe-3-Skip bei `yf_sf > 0`** seit PR #225 — spart 3-5 HTTP-Calls/Run

## (8) Lessons

- **Health-Check funktioniert wie designed**: heute morgen 1 CRIT + 4 WARN aufgedeckt, alle gefixt oder pragmatisch klassifiziert. Push war Trigger der ganzen Session.
- **finviz war kein Bug**: Stufe-3-Fallback erwischt obskure Smallcaps ohne Coverage — **Tier-Downgrade statt Code-Fix** war die richtige Antwort. Lesson: vor dem Provider-Fix-PR immer prüfen welcher Stufe der Provider in der Fallback-Kette ist.
- **`yf_sf > 0` als Skip-Bedingung** spart Calls: triviale Optimierung mit großem Effekt — verstreute kleine Fixes lohnen sich, wenn sie aus Diagnose-Daten folgen.
- **HTTP-Status in JSONL ist jetzt verfügbar**: bei nächstem Outage sofort Diagnose-Klarheit statt erst Probe-Workflow aufzusetzen. Investitionswert hoch.
- **PR #226 Lesson — Cockpit-Cleanup brach Watchlist**: Mock-Tests aus Stage 1 wurden gelöscht „weil obsolet" — sie deckten aber den `_wl_full_card_html`-Strip-Pfad ab. **NIE Schutz-Tests löschen ohne zu prüfen welche orthogonalen Pipelines sie abdecken.**
- **Bei größeren UI-Refactors: iPhone-Verify auch für Watchlist-Drawer**, nicht nur Top-10. Watchlist hat eigenen Render-Pfad via Regex-Strip aus `_card`-Output.
- **Disziplin-Lesson**: CRDF Setup 99.7 nicht getradet trotz starker Karte — gegeben Backtest-Stand (keine klare Edge ≥ 70) richtige Entscheidung. Tool als Setup-Anzeiger, nicht Signal-Geber.
- **Revert-Disziplin**: bei Tool-Bruch zuerst reverten, dann diagnostizieren. Today: PR #226-Bruch in ~5 min via PR #227 zurückgerollt, Easy konnte Watchlist normal weiter benutzen. Bug-Analyse separat in nächster Session.

---

**Tag-Bilanz:** 10 saubere PRs durchgekommen, 1 stiller Watchlist-Bug gefangen + sofort zurückgerollt. Tool lebt, Diagnose-Infrastruktur deutlich besser als gestern. Score-Delta-T-1-Sichtbarkeit bleibt für morgen offen.
