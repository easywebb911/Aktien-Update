# Session-Handover — Stand 17.05.2026 (FINAL, 16 PRs)

| Meta | Wert |
|---|---|
| Datum | 17.05.2026 (Sonntag, Tag 4 Sprint-Phase) |
| Final-PRs heute | **16 gemerged** (PR #188-#204) |
| Session-Dauer | sehr lang (Vormittag → spät Abend, mit Cockpit-Endphase) |
| Memory-Updates | Service-Worker-Entfernung, PR-Status-Regel ohne Webhook-Warten, AMC-Halt-Strategie, Entry-Timing-Modul ab 10.06. (höchste Priorität), Earliness V3 vorgezogen 13.06.→07.06., Karten-Cockpit-Redesign live |
| Vorgänger-Handover | PR #197 (Stand früher Abend, 9 PRs) → dieser PR final mit 16 PRs |
| **Magic-Marker** | **200 PRs gesamt im Repo erreicht mit PR #200 (Cockpit-Donut-Tuning)** |

## Heute implementiert (chronologisch, 16 PRs)

Fünf Themen-Cluster: **iOS-Cache-Diagnose** (SW raus), **Workflow-Mechanik** (PR-Status-Regel), **UX-Cleanups** (RS-Doppel, Cursor-Reste), **Hygiene-Abschluss** (5/2 + 6/B), **Push-Pipeline-Fix** (Health-Check ntfy), **Chat-Erweiterung** (Watchlist) — plus großes **Karten-Cockpit-Redesign** als Abend-Sprint.

### Vormittag/Nachmittag (8 PRs, Bug-Fixes + Hygiene + Chat)

**iOS-Cache-Diagnose:**
- `f7a9e37` — **PR #188** chore: Service-Worker komplett raus. WebKit-HTTP-Cache hatte PR #185/#186 stundenlang versteckt.

**Workflow-Mechanik:**
- `884de4d` — **PR #189** docs: PR-Status-Meldungsregel in CLAUDE.md (keine Webhook-Events in CI-losen Repos).

**UX-Cleanups:**
- `840367d` — **PR #190** feat: RS-vs-SPY-Detail-Zeile zusammengeführt (Doppel-Anzeige weg).
- `93aef4e` — **PR #193** fix: Setup-Score `cursor:pointer` Reste entfernt + agent-dot-Tooltip.

**Code-Hygiene-Backlog-Abschluss (alle 5 kleinen Punkte erledigt):**
- `f850b99` — **PR #191** chore: AST-Drift-Schutz für `score()`-Multiplier ↔ `SUB_*`-Konstanten (5/2).
- `2c31e09` — **PR #192** chore: AST-Drift-Schutz erweitert auf `DRIVER_CLASSIFICATIONS` (6/B).

**Push-Pipeline-Fix:**
- `116b92f` — **PR #194** fix: Health-Check-Digest ntfy von JSON-API auf URL-Pattern. `last_digest_sent` war seit Tagen `null`. Erster echter Push wird 18.05. ~11:00 Berlin erwartet.

**Chat-Erweiterung:**
- `1e466be` — **PR #195** feat: Watchlist-Tickers im Chat-Kontext. AI/AMC/IONQ/RR/CRMD bekommen konkrete Tool-Daten statt generischer Antworten.

**Doku-Zwischenstand:**
- `e9b56bc` — **PR #197** docs: SESSION_HANDOVER mit Entry-Timing-Modul-Großprojekt als höchste Roadmap-Priorität.

### Abend-Sprint (7 PRs, Karten-Cockpit-Redesign)

3-Stage-Plan + iterative Feintuning-Iterationen nach iPhone-Verify.

**Cockpit-Architektur:**
- `c508fd5` — **PR #198** feat: Karten-Cockpit Stage 1 (Helper `_card_cockpit_html` + CSS-Klassen `.cockpit-*` + 15 Mock-Tests, Flag `CARD_COCKPIT_ENABLED=False` → user-invisible).
- `[merged manuell]` — **PR #199** feat: Karten-Cockpit Stage 2 (Flag flippt auf `True`, `_card` (v1) + `_build_card_ctx` (v2) + `card.jinja` umgestellt via `card_header_html`-Context-Var, Watchlist-Drawer profitiert automatisch über `_wl_full_card_html`-Regex-Strip, Live-Polling-Selector erweitert um `.cockpit-header-right`).

**Iterative Feintuning-Mini-PRs nach iPhone-Live-Verify:**
- `a988b0f` — **PR #200** fix: Cockpit-Donut 185→160 px (Conviction-Zahl 50→42 px). **🎯 Magic-200 erreicht: 200 PRs gesamt im Repo.**
- `0f941fd` — **PR #202** fix: Cockpit-Header-Typografie elegant (Kurs 26 px weight 400, Change 11 px weight 400) + Donut 160→150 px.
- `f265f50` — **PR #203** fix: Cockpit-Donut 150→135 px + horizontales Padding 14 px (analog `.card-top`).
- `eceffb1` — **PR #204** fix: Cockpit-Donut final 135→120 px (Conviction-Zahl 32 px).

**Donut-Tuning-Sequenz (5 Iterationen):** 185 → 160 → 150 → 135 → **120** px. Conviction-Zahl: 50 → 42 → 40 → 36 → **32** px.

## Aktive Positionen (Stand Ende 17.05.2026)

| Ticker | Status | Anmerkung |
|---|---|---|
| **AMC** | offen | **Halt-Strategie** — Easy hält langfristig, Exit-Pushes irrelevant. Wiedervorlage: `no_exit_alerts: true`-Flag im Gist-Schema wenn nächster AMC-Exit-Push nervt. |
| **IONQ** | offen | Watchlist-Outsider — KI-Score live ab nächstem KI-Agent-Tick |
| **RR** | offen | Watchlist-Outsider |
| **CRMD** | offen | Substrat intakt (DTC 16, SF 21 %, SI-Trend sideways). PnL −4.8 % vom Entry $7.93. **Hauptaufhänger für Entry-Timing-Modul** (siehe 10.06.) — Setup 98 robust beim Entry, aber Timing schlecht. Strategie: durchhalten. |

## Verifikation morgen 18.05.2026

| Slot / Aktion | Was prüfen | Bezug |
|---|---|---|
| **11:00–12:30 Berlin** (Cron 08:47 UTC + ~1.5h Verspätung) | **Erster echter Health-Check-Push** — Erwartung: WARN-Push mit 6 Tier-2/3-Provider-Fails | **PR #194** |
| Falls weiter kein Push | Workflow-Logs in GitHub-Actions-UI inspizieren | Fallback-Diagnose |
| Nach Daily-Run-Deploy | **Cockpit-Layout final** sichtbar — Donut 120 px, Conviction-Zahl 32 px, Säulen Setup→Monster→KI links, Kurs 26 px schlank rechts, Change 11 px farbig mit ▲/▼ | **PR #198-#204** |
| Top-10 + Watchlist-Drawer | Cockpit-Layout in beiden Pfaden bündig zur Sub-Score-Zone (Padding 14 px angeglichen) | PR #203 |
| Chat (Hamburger-Menü) | Frage „Wie sieht AI aktuell aus?" → konkrete Daten (Setup, KI, short_float, RSI) statt generisch | PR #195 |
| Karten-Layout bei großer Schrift | Kein Layout-Drift, alles bündig | PR #198-#204 |
| Konfidenz-Tabelle iPhone-Layout-Bug | **Weiter offen** vom 16.05. — Web-Inspector-Diagnose ausstehend | Easy-Aktion |

## Geplante Aufgaben + Wiedervorlagen

| Datum / Trigger | Aufgabe | Bezug |
|---|---|---|
| **18.05.** | Health-Check-Push-Verifikation + Cockpit-iPhone-Verify + Chat-Watchlist-Test | sofort morgens |
| **18.05.** | PR #175-Verdachtsfall — Tier-3 success_check weiter 100% Fail-Rate. Separate Diagnose-Welle nach Push-Pipeline-Bestätigung. | nach #194-Validierung |
| **28.05.** | Earliness-Trend-Logging AUC-Re-Check (Schema v4, 14 d Live-Daten) | Datensammlung läuft |
| **30.05.** | **PR-γ aktivieren**: `RVOL_NORMALIZATION_ENABLED = True` mit empirischem Skalierer | nach PR #167 |
| **30.05.** | KI-Agent-Coverage-Empirik: Push-Spam-Volumen messen | nach PR #177 |
| **02.06.** | Chart-Indikatoren erweitern prüfen | Backlog |
| **07.06.** | **Earliness V3 Entscheidung** — DTC-Bucket-Logik mit Trend-Logging-Auswertung. **Fundament für Entry-Timing-Modul.** Datum vorgezogen von 13.06. | Datensammlung läuft |
| **★★★ 10.06. ★★★** | **ENTRY-TIMING-MODUL — GROSSPROJEKT, HÖCHSTE PRIORITÄT.** Neuer Entry-Score 0-100 misst „Reife im Moment" (Earliness-Trend, RVOL-Beschleunigung, Anomaly-Frische, Score-Delta, Optionsfluss). Backtest-validiert gegen `return_3d`/`return_5d`. Aufhänger: CRMD-Lesson. Mehrwöchig (3-5 Wochen). | nach Earliness V3 |
| **02.07.** | Premium-Daten-Stack prüfen (60 d Live-Daten) | Datensammlung läuft |
| nach 5+ high-Conviction-Trades | **Conviction-Kalibrierungs-Beobachtung** — KPTI-Verlust 16.05. als erstes Indiz | empirisch |
| nach Easy-Feedback | Score-Delta T-1 Phase 2 (Conviction/Monster/KI-History-Persistenz) | wenn Phase 1 bewährt |
| pending Live-Test | **Phase-3-Exit-Implementation** (Blow-off-Top) — wartet auf parabolisches Setup, nicht CRMD | `docs/phase3_exit_spec.md` fertig |
| **bei nächstem nervigen AMC-Push** | **AMC-Halt-Strategie** — `no_exit_alerts: true`-Flag im Gist-Schema. ~30-45 min Aufwand, Manuell-Merge wegen Push-Pipeline-Touch. | Wiedervorlage |
| **bei nächster ruhiger Session** | **Karten-Cockpit Stage 3** — Cleanup obsoleter `.sb-row` / `.sb-num`-Reste aus Karten-Bereich (Methodik-Panel-Verwendung bleibt — eigene Konsumenten-Klasse). Folge-PR zu #198/#199. | Wiedervorlage |
| **Q3 2026** | **Beliebige-Tickers-Live-Pull im Chat** — Cloudflare-Worker erweitern + async Datenfluss. Aufwand 3-5 Tage. | latent |
| **Offen** vom 16.05. | **Konfidenz-Tabelle iPhone-Layout-Bug** — Mac+iPhone-Web-Inspector-Diagnose unausweichlich | Easy-Aktion |

**Erledigt heute (16 PRs):**
- ~~Service-Worker-Entfernung~~ → PR #188
- ~~PR-Status-Regel~~ → PR #189
- ~~RS-vs-SPY Doppel-Anzeige~~ → PR #190
- ~~AST-Drift-Schutz Score-Multiplier (5/2)~~ → PR #191
- ~~AST-Drift-Schutz DRIVER_CLASSIFICATIONS (6/B)~~ → PR #192
- ~~Setup-Score-Cursor + agent-dot-Tooltip~~ → PR #193
- ~~Health-Check ntfy URL-Pattern~~ → PR #194
- ~~Watchlist im Chat-Kontext~~ → PR #195
- ~~Karten-Cockpit Stage 1 (Helper + CSS, Flag OFF)~~ → PR #198
- ~~Karten-Cockpit Stage 2 (Aktivierung, v1+v2 + Watchlist)~~ → PR #199
- ~~Cockpit-Donut 185→160 + Conviction 50→42~~ → PR #200 (Magic-200)
- ~~Cockpit-Typografie elegant + Donut 160→150~~ → PR #202
- ~~Cockpit-Donut 150→135 + Padding 14px~~ → PR #203
- ~~Cockpit-Donut final 135→120 + Conviction 32~~ → PR #204

## Strategische Roadmap

| Pipeline | Status | Nächster Meilenstein |
|---|---|---|
| Score-Inflation-Pipeline | PR-α/β live (#166, #167), PR-γ am **30.05.** | Empirische Aktivierung |
| Conviction-Kalibrierung | Beobachtung gestartet | nach 5+ weiteren high-Conviction-Trades |
| Phase-3 Exit-Trigger (Blow-off-Top) | Spec fertig | wartet auf parabolisches Setup |
| Earliness V2 → V3 | V2 live mit AUC 0.77 | **V3-Entscheidung am 07.06.** (vorgezogen) |
| **★ Entry-Timing-Modul (NEU)** | Spec-Phase | **Start ab 10.06. nach Earliness V3.** Höchste Priorität, mehrwöchig. CRMD-Lesson liefert Aufhänger. |
| KI-Agent-Coverage | Phase 2 live (15 Tickers) | Empirik 30.05. |
| **Health-Check-Push-Pipeline** | **PR #194 deployt 17.05.** | **18.05. erster echter Push** |
| **Cache-Strategie** | SW komplett raus (#188) | kein weiterer Schritt nötig |
| **Karten-Cockpit-Redesign** | **Stage 2 live (PR #198-#204)** — Donut 120 px, Padding 14 px, schlanke Typografie | Stage 3 Cleanup als Folge-PR |
| **Chat-Watchlist-Coverage** | live ab nächstem Daily-Run | Beliebige-Tickers-Live-Pull Q3-Backlog |

## Code-Hygiene-Backlog mit Status

| Punkt | Status |
|---|---|
| (1) `_record_push`-Helper Single-Source-of-Truth | ✅ erledigt PR #76 |
| (5/1) `score()` aus `SUB_*_DISPLAY_PTS_MAX` (Methodik-Cap-Drift-Schutz) | ✅ erledigt PR #84 |
| (6/A) `_drivers_breakdown` Single-Source-of-Truth via `DRIVER_CLASSIFICATIONS` | ✅ erledigt PR #83 |
| (Bonus) RS-vs-Sektor Dead-Code-Cleanup | ✅ erledigt PR #183 |
| (Bonus) `.sb-lbl` Spezifitäts-Scoping | ✅ erledigt PR #185 |
| (Bonus) Methodik-Listen Grid-Layout | ✅ erledigt PR #186 |
| **(5/2) `score()`-Multiplier AST-Drift-Schutz** | ✅ erledigt PR #191 |
| **(6/B) DRIVER_CLASSIFICATIONS AST-Drift-Schutz** | ✅ erledigt PR #192 |
| (2) v1/v2 Render-Pfad → reines Jinja | pending — größerer Refactor |
| (3) `generate_report.py` Monolith splitten | pending — größerer Refactor |
| (4) Template-Engine statt f-Strings | pending — überlappt mit (2)+(3) |
| **(Bonus, neu) Karten-Cockpit Stage 3** — `.sb-row`/`.sb-num`-Reste aus Karten-Bereich entfernen | offen, bei nächster ruhiger Session |

**Alle 5 kleinen Punkte abgeschlossen.** Verbleibend nur 3 große Refactors + Cockpit Stage 3 Cleanup als kleine Wartung.

## Architektur-Anker (heute zementiert)

- **Cache-Strategie ohne Service-Worker** (PR #188): Frontend ist statische Seite, max-age=600 als einzige Cache-Schicht.
- **PR-Status-Meldungsregel** (PR #189): Repo hat keine CI für PR-Validation — passives Webhook-Warten ist Lärm. Standard: direkt mergen / „Ready for Merge" / „blockiert".
- **AST-Drift-Schutz-Pattern** (PR #191/#192): Sub-Score-Multiplier zentral über 3 Stellen (`score()`, `_compute_sub_scores`, `DRIVER_CLASSIFICATIONS`) via AST-Inspektion abgesichert.
- **ntfy-Sender-Pattern**: immer URL-Pattern, ASCII-Title, UTF-8-Body. JSON-API auf ntfy.sh = verified-broken.
- **Watchlist-im-Chat-Pattern** (PR #195): zusätzlicher `watchlist[]`-Top-Level-Key in `STOCKS_CTX` analog `today_top10[]`.
- **3-Stage-Approach für UI-Redesigns** (PR #198/#199 + Folge-Tuning): Stage 1 Helper-Vorbereitung mit Feature-Flag (no-op), Stage 2 Aktivierung + iPhone-Verify-Pflicht, Stage 3 Cleanup. Feature-Flag-Mechanik (`CARD_COCKPIT_ENABLED`) ermöglicht Rollback ohne Code-Touch — Fallback-Branches bleiben.
- **Iteratives Mini-PR-Tuning** (PR #200/#202/#203/#204): nach Stage 2 wurden 5 Feinjustierungen in eigenständigen Mini-PRs durchgeführt (Donut-Größe 185→120 px, Typografie, Padding) — jede einzeln auf iPhone verifizierbar.
- **Cockpit-Layout-Pattern**: Bloomberg-Stil mit 3 Sub-Score-Säulen links (100 px) + Conviction-Donut rechts (120 px). Header zweispaltig (Ticker+Badges links / Kurs+Change rechts). Padding analog `.card-top` (`14px 14px 10px`).

## Lessons heute

1. **Service-Worker-Caching kann CSS-Fixes versteckt halten** — PR #185/#186 waren auf main + deployed, aber iOS-Safari servierte stundenlang die alte CSS-Version. Lesson: bei UX-Bugs nach CSS-PR **immer erst Cache-Bust testen** bevor neue Diagnose.
2. **„Engineering-Theater raus" als Prinzip** — Easy ist iPhone-Trader, immer online → Offline-SW war reine technische Komplexität ohne Trader-Wert. Vor jedem PR: „nutzt Easy das wirklich?"
3. **Diagnose vor Code: PR #185 + #186 vermeidbar** wenn Service-Worker früher als Layer in der Diagnose-Kette geprüft. Bei UX-Bugs künftig: **Layer-Stack durchgehen** (Code → Build → CDN → Browser-Cache → Service-Worker → DOM).
4. **AST-basierte Mock-Tests > Code-Refactor** für Drift-Schutz (PR #191/#192). Auto-Merge statt manueller-Merge bei score()-Touch.
5. **ntfy-URL-Pattern statt JSON-API** (PR #194). Lesson: vor neuer API-Implementation **prüfen wie analoge Aufrufe woanders im Tool aussehen**.
6. **Easy nutzt App-Chat und Claude-Chat komplementär** (PR #195): App-Chat braucht keine Web-Suche, Tool-Daten reichen.
7. **3-Stage-Approach bei größeren UI-Redesigns bewährt** (PR #198/#199): Stage 1 mit Feature-Flag erlaubt vorbereitende Code-/CSS-Arbeit ohne User-Effekt. Stage 2 Aktivierung mit iPhone-Verify-Pflicht. Stage 3 Cleanup als separater PR. Rollback per Flag-Flip ohne Code-Touch.
8. **Iteratives Feintuning per Mini-PRs ist sehr effektiv** (PR #200/#202/#203/#204): nach Stage 2 zeigte iPhone-Live-Verify mehrere Anpassungen nötig (Donut 5× verkleinert, Typografie, Padding). Jeder Mini-PR <10 LoC, Auto-Merge, schneller iPhone-Verify-Zyklus. Besser als ein großer „alles polieren"-PR.
9. **Magic-200 erreicht** (PR #200 = 200 PRs gesamt im Repo). Tag-4-Sprint mit 16 PRs = hohe Velocity. Pattern: klare Klassifikation + Diagnose → Spec → Implementation → Auto-Merge.
10. **Easy entscheidet über Pausen, nicht Claude.** Pausen-Vorschläge nur bei konkreten Sicherheitsbedenken oder fehlenden Daten — sonst durcharbeiten.
11. **CRMD-Lesson liefert Aufhänger für Entry-Timing-Modul-Großprojekt** (Wiedervorlage 16.05.→17.05. zementiert): Setup-Score 98 beim Entry war robust und korrekt klassifiziert, aber Timing schlecht. Aktuelle Score-Pipeline misst „Reife des Substrats", nicht „Reife im Moment". Architektur-Lücke, kein Pech.
12. **Code-Hygiene-Backlog-Abschluss in einer Session** — alle 5 kleinen Punkte (PR #76/#83/#84/#191/#192) jetzt erledigt. Verbleibend nur 3 große Refactors. Backlog-Diät durch AST-Test-Strategie statt Code-Refactor.
