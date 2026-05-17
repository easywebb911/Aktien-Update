# Session-Handover — Stand 17.05.2026

| Meta | Wert |
|---|---|
| Datum | 17.05.2026 (Sonntag, Tag 4 Sprint-Phase) |
| Final-PRs heute | **8 gemerged** |
| Session-Dauer | lang (Vormittag → spät Abend) |
| Memory-Updates | Service-Worker-Entfernung (CLAUDE.md Cache-Strategie), PR-Status-Regel ohne Webhook-Warten, AMC-Halt-Strategie (Wiedervorlage) |
| Vorgänger-Handover | PR #187 (Stand 16.05.2026 spät Abend, 23 PRs) |

## Heute implementiert (chronologisch)

Vier Themen-Cluster über den Tag: **iOS-Cache-Diagnose** (SW raus + Konfidenz-Layout-Fixes), **Hygiene-Backlog-Abschluss** (5/2 + 6/B), **UX-Cleanups** (RS-Doppel-Zeile + Cursor-Reste), **Push-Pipeline-Fix** (Health-Check ntfy) plus **Chat-Erweiterung** (Watchlist im LLM-Kontext).

**Service-Worker-Entfernung (iOS-Safari-Cache-Quirks):**
- `f7a9e37` — **PR #188** chore: Service-Worker komplett raus. `service_worker.js` (git rm), `_write_service_worker` + Aufruf + `SW_ENABLED`-Konstante entfernt, SW-Registration durch Unregister-Block ersetzt (Cleanup alter SW-Instanzen + Cache-Wipe beim nächsten Page-Load). PR #185/#186 waren stundenlang unsichtbar weil WebKit-HTTP-Cache (`max-age=600`) durch SW's `fetch(req)` ohne `cache:'reload'` aktiv genutzt wurde. Easy ist iPhone-Trader, dauerhaft online → Offline-Wert = null.

**Doku-Konsolidierung Workflow-Mechanik:**
- `884de4d` — **PR #189** docs: PR-Status-Meldungsregel in CLAUDE.md. Repo hat keine GitHub-Actions-CI-Workflows für PR-Validation — Claude meldete bisher fälschlich „Warte auf Webhook-Events". Neue Regel: Auto-Merge-PR → direkt mergen, Manuell-Merge-PR → „Ready for Merge"-Meldung mit Klassifikations-Grund. Spart Ping-Pong-Cycle.

**UX-Cleanups (Frontend-Hygiene):**
- `840367d` — **PR #190** feat: RS-vs-SPY-Detail-Zeile zusammengeführt. Zwei `<tr>`-Zeilen mit identischem Prozent-Wert (`Rel. Stärke (20T) -11.3% vs. S&P 500 (Aktie -7.3%)` + `RS vs. SPY (20T) -11.3% (-3 Pkt)`) waren Restzeilen aus PR-Welle 30.04.2026 (Sektor-RS-Ablösung). Vereint zu einer Zeile: `RS vs. SPY (20T) -11.3% (Aktie -7.3%, -3 Pkt)`. Mit Orphan-Locals-Cleanup (`_rs20`/`_p20` raus) + v1/v2-Sync.
- `93aef4e` — **PR #193** fix: Setup-Score `cursor:pointer` Reste entfernt + agent-dot Tooltip. Tote CSS-Reste (`cursor:pointer` + `:hover/:focus-visible` auf `.sb-row[data-sb="setup"] .sb-num`) aus früherer Quick-Sort-Click-Funktionalität, die ins Hamburger-Menü migriert wurde — kein JS-Handler dahinter. Plus: `agent-dot` bekommt `title="KI-Status (stündlich) - Live-Quote-Status erscheint über Setup-Score beim Aufklappen"` als Klärung der Dot-Inkonsistenz.

**Code-Hygiene-Backlog Abschluss (alle 5 kleinen Punkte erledigt):**
- `f850b99` — **PR #191** chore: AST-Drift-Schutz für `score()`-Multiplier ↔ `SUB_*_DISPLAY_PTS_MAX`-Konstanten (Code-Hygiene-Punkt 5/2). Neuer Mock-Test `mock_test_score_multiplier_sync.py` parsed AST der `score()`- und `_compute_sub_scores`-Funktionen, vergleicht Multiplier-Literale mit Konstanten-Werten. Drift-resistent (liest aktuellen Konstanten-Wert zur Laufzeit). Verifiziert via CFG-Mutation-Simulation.
- `2c31e09` — **PR #192** chore: AST-Drift-Schutz erweitert auf `DRIVER_CLASSIFICATIONS` (Code-Hygiene-Punkt 6/B). Erweitert PR #191-Test um zwei neue Tests (#06 + #07) mit präzisem Lambda-Walker (extrahiert nur unmittelbare BinOp-Mult-Operanden, ignoriert Display-Only-Caps wie `min(..., 10.0)`-RSI-Cap → Falsch-positiv-Schutz). Damit alle drei Stellen mit Sub-Score-Multiplikatoren (`score()`, `_compute_sub_scores`, `DRIVER_CLASSIFICATIONS`) zentral abgesichert.

**Push-Pipeline-Bug-Fix (Health-Check):**
- `116b92f` (via PR #194) — **PR #194** fix: Health-Check-Digest ntfy von JSON-API auf URL-Pattern umgestellt. Diagnose 17.05.: `last_digest_sent` war seit Tagen `null` — PR #168-JSON-API funktionierte auf ntfy.sh nicht zuverlässig. Alle anderen ntfy-Sender im Tool (`ki_agent._send_anomaly_ntfy`, `_send_exit_p2_push`, `send_ntfy_alert`, `generate_report._send_exit_ntfy`) nutzen das URL-Pattern und funktionieren. Adoptiert: `POST https://ntfy.sh/{TOPIC}` + Header (Title ASCII-gestrippt via `.encode("ascii", "ignore")` für latin-1-Constraint) + UTF-8-Body als `data=`.

**Chat-Erweiterung (LLM-Kontext):**
- `1e466be` — **PR #195** feat: Watchlist-Tickers im Chat-Kontext. Neuer Top-Level-Key `watchlist[]` in `STOCKS_CTX` analog `today_top10[]` (17 Felder pro Ticker). Easy bekommt für AI/AMC/IONQ/RR/CRMD konkrete Tool-Daten statt generischer Antworten. Top-10-Mitglieder ausgeschlossen (keine Duplikation). System-Prompt-Sektion „WATCHLIST-DATENQUELLE" mit klarer LLM-Anweisung: nutze `watchlist`, **keine generischen Antworten mehr**, Watchlist ist **nicht** gerankt.

## Aktive Positionen (Stand Ende 17.05.2026)

| Ticker | Status | Anmerkung |
|---|---|---|
| **AMC** | offen | **Halt-Strategie** — Easy hält langfristig, Exit-Pushes irrelevant. Wiedervorlage: `no_exit_alerts: true`-Flag im Gist-Schema (Feature-Request, wenn nächster AMC-Exit-Push nervt). |
| **IONQ** | offen | Watchlist-Outsider — KI-Score live ab nächstem KI-Agent-Tick |
| **RR** | offen | Watchlist-Outsider |
| **CRMD** | offen | Diagnose vom 16.05.: Substrat intakt (DTC 16, SF 21 %, SI-Trend sideways). PnL −4.8 % vom Entry $7.93. Kein Phase-3-Fall (kein parabolischer Reversal). Strategie: durchhalten. |

## Verifikation morgen 18.05.2026

| Slot / Aktion | Was prüfen | Bezug |
|---|---|---|
| **11:00–12:30 Berlin** (Cron 08:47 UTC + ~1.5h Verspätung) | **Erster echter Health-Check-Push** — Erwartung: WARN-Push mit 6 Tier-2/3-Provider-Fails (stocktwits/edgar_8k/form4/earningswhispers/finviz/finnhub) | **PR #194** |
| Falls weiter kein Push | Workflow-Logs in GitHub-Actions-UI inspizieren (`_ntfy_send` loggt HTTP-Status + Body-Snippet) | Fallback-Diagnose |
| Nach Daily-Run-Deploy | RS-vs-SPY: nur EINE Detail-Zeile pro Karte (kein Duplikat), Aktie-Klammer + Punkte-Klammer beide drin | PR #190 |
| Top-10 + Watchlist-Drawer | Setup-Score-Zahl: Text-Cursor (kein Hand-Cursor), Hover über agent-dot zeigt Tooltip „KI-Status (stündlich)..." | PR #193 |
| Chat (Hamburger-Menü) | Frage „Wie sieht AI aktuell aus?" — Antwort muss konkrete Setup/KI/short_float/RSI nennen (nicht generisch) | PR #195 |
| Browser-Cache | Keine Service-Worker-Reste mehr aktiv. Easy musste einmalig nach 17.05.-Deploy Cache-Bust durchführen (`?bust=999` + Tab schließen + Safari-App beenden). Ab dann jeder Refresh frisch vom CDN. | PR #188 |
| Konfidenz-Tabelle Methodik | **Offen** vom 16.05.: Layout-Bug auf iPhone — Web-Inspector-Diagnose ausstehend bis Easy am Mac sitzt und iPhone per USB inspizieren kann | Memory-offen |

## Geplante Aufgaben + Wiedervorlagen

| Datum / Trigger | Aufgabe | Bezug |
|---|---|---|
| **18.05.** | Health-Check-Push-Verifikation + iPhone-Web-Inspector-Diagnose Konfidenz-Tabelle | sofort morgens |
| **18.05.** | PR #175-Verdachtsfall — Tier-3 success_check zeigt heute weiter 100% Fail-Rate bei stocktwits/edgar_8k/form4/news_rss/uoa. Separate Diagnose-Welle nach Bestätigung dass Push-Pipeline läuft. | nach #194-Validierung |
| **28.05.** | Earliness-Trend-Logging AUC-Re-Check (Schema v4, 14 d Live-Daten) | Datensammlung läuft |
| **30.05.** | **PR-γ aktivieren**: `RVOL_NORMALIZATION_ENABLED = True` mit empirischem Skalierer aus 14 d v2-Logs | nach PR #167 |
| **30.05.** | KI-Agent-Coverage-Empirik: Push-Spam-Volumen messen (> 5 zusätzliche Pushes/Tag → `WATCHLIST_OUTSIDER_CONVICTION_MIN` einführen) | nach PR #177 |
| **02.06.** | Chart-Indikatoren erweitern prüfen | Backlog |
| **13.06.** | Earliness V3 Entscheidung — DTC-Bucket-Logik mit Trend-Logging-Auswertung | Datensammlung läuft |
| **02.07.** | Premium-Daten-Stack prüfen (60 d Live-Daten, Konfidenz-Re-Assessment) | Datensammlung läuft |
| nach 5+ high-Conviction-Trades | **Conviction-Kalibrierungs-Beobachtung** — KPTI-Verlust trotz Conviction 81 vom 16.05. als erstes Indiz | empirisch |
| nach Easy-Feedback | Score-Delta T-1 Phase 2 (Conviction/Monster/KI-History-Persistenz) | wenn Setup-Delta sich bewährt |
| pending Live-Test | **Phase-3-Exit-Implementation** (Blow-off-Top) — wartet auf parabolisches Endphasen-Setup | `docs/phase3_exit_spec.md` fertig |
| **bei nächstem nervigen AMC-Push** | **AMC-Halt-Strategie** — `no_exit_alerts: true`-Flag im Gist-Schema (`positions[ticker]`). Guard-Check in `process_exit_signals` skipt Push-Generation. Manuell-Merge-PR wegen Push-Pipeline-Touch. ~30-45 min Aufwand. | Wiedervorlage |
| **Q3 2026** | **Beliebige-Tickers-Live-Pull im Chat** — Cloudflare-Worker um vollständige Squeeze-Daten erweitern + async-Datenfluss zur Chat-Laufzeit + Quota-Management. Aufwand 3-5 Tage. | latent |
| **Offen** vom 16.05. | **Konfidenz-Tabelle iPhone-Layout-Bug** — zwei falsche Theorien (PR #185/#186) durchprobiert, Mac+iPhone-Web-Inspector-Diagnose unausweichlich | Easy-Aktion |

**Erledigt heute**:
- ~~Service-Worker-Entfernung~~ → PR #188
- ~~PR-Status-Regel ohne Webhook-Warten~~ → PR #189
- ~~RS-vs-SPY Doppel-Anzeige~~ → PR #190
- ~~AST-Drift-Schutz Score-Multiplier (5/2)~~ → PR #191
- ~~AST-Drift-Schutz DRIVER_CLASSIFICATIONS (6/B)~~ → PR #192
- ~~Setup-Score-Cursor-Altlast + agent-dot-Tooltip~~ → PR #193
- ~~Health-Check ntfy URL-Pattern (Push-Fix)~~ → PR #194
- ~~Watchlist im Chat-Kontext~~ → PR #195

## Strategische Roadmap

| Pipeline | Status | Nächster Meilenstein |
|---|---|---|
| Score-Inflation-Pipeline | PR-α/β live (#166, #167), PR-γ am **30.05.** | Empirische Aktivierung |
| Conviction-Kalibrierung | Beobachtung gestartet (KPTI 16.05. als erstes Indiz) | nach 5+ weiteren high-Conviction-Trades |
| Phase-3 Exit-Trigger (Blow-off-Top) | Spec fertig (`docs/phase3_exit_spec.md`) | wartet auf parabolisches Setup |
| Earliness V2 → V3 | V2 live mit AUC 0.77 | V3-Entscheidung am 13.06. |
| KI-Agent-Coverage | Phase 2 live (15 Tickers) | Empirik-Auswertung 30.05. |
| **Health-Check-Push-Pipeline** | **PR #194 — Push-Fix deployt 17.05.** | **18.05. erster echter Push erwartet** |
| **Cache-Strategie** | **SW komplett raus (#188)** — statische Seite, max-age=600 als einzige Cache-Schicht | Bei Offline-Wunsch: dann mit `cache: 'reload'` im SW-Fetch |
| **Chat-Watchlist-Coverage** | live ab nächstem Daily-Run | Beliebige-Tickers-Live-Pull als Q3-Backlog |
| Backtest-Datenpunkte | 1.590+ heute | belastbare Live-Statistik ab Juli 2026 |

## Code-Hygiene-Backlog mit Status

| Punkt | Status |
|---|---|
| (1) `_record_push`-Helper als Single-Source-of-Truth | ✅ erledigt PR #76 |
| (5/1) `score()` aus `SUB_*_DISPLAY_PTS_MAX`-Konstanten (Methodik-Cap-Drift-Schutz) | ✅ erledigt PR #84 |
| (6/A) `_drivers_breakdown` als Single Source of Truth via `DRIVER_CLASSIFICATIONS` | ✅ erledigt PR #83 |
| **(Bonus) RS-vs-Sektor Dead-Code-Cleanup** | ✅ erledigt PR #183 |
| **(Bonus) `.sb-lbl` Spezifitäts-Scoping** | ✅ erledigt PR #185 (sauber, hat aber iPhone-Bug nicht gelöst) |
| **(Bonus) Methodik-Listen Grid-Layout** | ✅ erledigt PR #186 (sauber, hat aber iPhone-Bug nicht gelöst) |
| **(5/2) `score()`-Multiplier AST-Drift-Schutz** | **✅ erledigt PR #191** |
| **(6/B) DRIVER_CLASSIFICATIONS AST-Drift-Schutz** | **✅ erledigt PR #192** |
| (2) v1/v2 Render-Pfad → reines Jinja (`page.jinja` + `wl_card.jinja`) | pending — größerer Refactor |
| (3) `generate_report.py` Monolith splitten | pending — größerer Refactor |
| (4) Template-Engine statt f-Strings | pending — überlappt mit (2) und (3) |

**Alle 5 kleinen Hygiene-Punkte erledigt.** Verbleibend nur die 3 großen Refactors, die bewusste größere Sessions brauchen.

## Architektur-Anker (heute zementiert)

- **Cache-Strategie ohne Service-Worker** (CLAUDE.md → „Cache-Strategie"): Frontend ist gewöhnliche statische Seite. SW entfernt 17.05. weil iOS-Safari-WebKit-Cache durch `fetch(req)` ohne `cache:'reload'` transparent genutzt wurde. Konsequenz: CSS-/Doku-/Frontend-Änderungen sofort sichtbar bei nächstem Reload (modulo GitHub-Pages-CDN-TTL 10 min). Offline-Modus weg. Falls künftig Offline-Wunsch: bewusste neue Strategie mit `cache: 'reload'`.
- **PR-Status-Meldungsregel** (CLAUDE.md → „PR-Status-Meldung nach Push"): Repo hat keine CI-Workflows für PR-Validation — passives Warten auf Webhook-Events ist Lärm. Standard-Abschluss-Meldung je nach Klassifikation: direkt mergen / „Ready for Merge — wartet auf Easy-Freigabe" / „blockiert wegen Fehlermeldung X". `subscribe_pr_activity` ist Ausnahme (Review-Comment-Webhooks kommen real).
- **AST-Drift-Schutz-Pattern** (`mock_test_score_multiplier_sync.py`): drei Stellen mit Sub-Score-Multiplikatoren (`score()`, `_compute_sub_scores`, `DRIVER_CLASSIFICATIONS`) zentral via AST-Inspektion abgesichert. Präzise Walker-Extraktion (nur BinOp-Mult-Operanden in Lambda-Bodies, keine Subtree-Walks → kein Falsch-positiv durch Display-Only-Caps). Drift-resistent: liest aktuellen Konstanten-Wert zur Laufzeit, keine hartcodierten Erwartungen im Test.
- **ntfy-Sender-Pattern** (CLAUDE.md → Health-Check-Phase-3): immer URL-Pattern (`POST https://ntfy.sh/{topic}` + `data=`-Body + Header), ASCII-only Title (latin-1-Header-Constraint), UTF-8-Body. JSON-API auf ntfy.sh wird nicht mehr verwendet (verified-broken). Faustregel für künftige Sender.
- **Watchlist-im-Chat-Pattern** (CLAUDE.md → Chat-Verhalten): zusätzlicher `watchlist[]`-Top-Level-Key in `STOCKS_CTX` analog `today_top10[]`. Skip wenn Top-10-Mitglied (keine Duplikation). System-Prompt-Hinweis: nicht gerankt, gleiche Datenqualität.
- **CSS-Reste-bei-Feature-Migration** (CLAUDE.md → CSS-Spezifitäts-Scope): bei Feature-Migration immer auch `cursor:pointer` / `:hover` / `:focus-visible` auf den betroffenen Selektoren mit-aufräumen.

## Lessons heute

1. **Service-Worker-Caching kann CSS-Fixes versteckt halten** — PR #185 und #186 waren auf main + deployed, aber iOS-Safari servierte stundenlang die alte CSS-Version. Lesson: bei UX-Bugs nach CSS-PR **immer erst Cache-Bust testen** bevor neue Diagnose-Welle. Hätten wir das vor PR #186 gemacht, hätten wir Service-Worker als Ursache schneller erkannt.
2. **„Engineering-Theater raus" als Prinzip** — Easy ist iPhone-Trader, immer online → Offline-Wert war null, SW-Pipeline reine technische Komplexität ohne realen Trader-Wert. Diese Asymmetrie (Implementations-Aufwand vs. tatsächliche User-Nutzung) ist ein wiederkehrendes Pattern. Vor jedem PR die Frage: „nutzt Easy das wirklich?".
3. **Diagnose vor Code: zwei CSS-Theorien-PRs (#185/#186) waren vermeidbar** wenn wir nach #185-Test-Verifikation zuerst die deployed-Page geprüft hätten („deployed = sichtbar?"). Service-Worker als Cache-Layer wurde übersehen, weil das HTML-File auf main den Fix hatte. Bei UX-Bugs künftig: **Layer-Stack durchgehen** (Code → Build → CDN → Browser-Cache → Service-Worker → DOM) bevor neue Theorie gebaut wird.
4. **AST-basierte Mock-Tests sind eleganter als Code-Refactor** wenn nur Drift-Schutz das Ziel ist (PR #191/#192). Statt `score()` umzuschreiben (Score-Logik-Touch → manueller Merge), Drift via Test absichern (Auto-Merge). Beste Trade-off: passive Hygiene-Tests > aktive Refactors für Hygiene-Punkte.
5. **ntfy-URL-Pattern statt JSON-API** — PR #194-Diagnose hätte mit „analoge-Pattern-Beobachtung beim Design" früher kommen können. Vier funktionierende Sender im Tool zeigten alle dasselbe URL-Pattern; der Digest-Workflow nutzte als einziger JSON-API. Lesson: bei neuen API-Aufrufen **vor Implementation prüfen wie analoge Aufrufe woanders im Tool aussehen** — Konsistenz mit bereits-bewährtem Pattern ist günstiger als Theorie-Wahl.
6. **Easy nutzt App-Chat und Claude-Chat komplementär** — App-Chat (PR #195) braucht keine Web-Suche, weil Easy primär nach Tool-Daten fragt (Setup, KI-Score, Risk-Reward). Web-Suche-Fragen passieren in Claude-Chat. Klare Tool-Trennung: App-Chat = Tool-Daten-LLM, Claude-Chat = Reasoning-LLM mit Web-Zugriff.
7. **Source-Inspektion vs. Live-Verifikation** (Wiederholung aus 16.05.) bestätigt sich: heute haben wir vor Push-Pipeline-Fix den Workflow-Run-Log nicht eingesehen — Diagnose lief mit Schluss „Push-Fail", korrekt aber spekulativ über JSON-API. Real-Verifikation morgen Vormittag bestätigt (oder widerlegt) die Theorie.
8. **Code-Hygiene-Backlog-Abschluss heute** — alle 5 kleinen Punkte gemeinsam mit den 3 wichtigen Bug-Fixes (Service-Worker, ntfy, RS-Doppel) plus 2 UX-Cleanups plus Chat-Erweiterung in EINEM Tag = 8 PRs. Hohe Velocity möglich durch klare Klassifikation (Diagnose → Spec → Implementation → Auto-Merge). Lesson: Diagnose-Schritte bezahlen sich nicht nur in Bug-Prevention, sondern auch in PR-Durchsatz.
