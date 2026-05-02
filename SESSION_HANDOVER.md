# Session-Handover — Stand 02.05.2026

## Heute implementiert (chronologisch)

- `aa8c660` — feat: hamburger menu with lucide icons replaces action tiles
- `578321d` — fix: hamburger menu corrections (title, actions, theme, sort)
- `b63c4a7` — fix: remove token reset from drawer footer to prevent mistaps
- `b900f87` — feat: hamburger menu also active on desktop
- `150f075` — style: remove redundant methodology dropdown, move disclaimer to top
- `c43327b` — style: larger app title on desktop
- `c2a62f1` — style: hide methodology section by default, show on menu click
- `7e34d81` — fix: move correct disclaimer to top, restore squeeze-score note
- `18ce2d1` — feat: ctb and utilization as display-only metrics
- `40b3a81` — docs: handover backlog filter flexibility for a2
- `949c4da` — feat: synthesis line plus categorized drivers for transparency
  (deterministische Drivers-Klassifizierung Stärke/Risiko + Top-2-Synthese-Zeile)
- `26142ee` — docs: handover reminder for premium data stack review
- `a84e075` — refactor: watchlist drawer cards use full topten layout
  (Variante A: vorgerendertes TopTen-Layout via `_wl_full_card_html`,
  IDs gestrippt, KI-Analyse umgeleitet auf `wlOpenKiAnalyse`)
- `540fedd` — feat: position tracking via private gist with ui controls
  (Phase 2: privater Gist `squeeze_data.json`, `gistLoad/gistSave`,
  Position-Open/Close-Form, `wlRemoveFromExpanded`,
  `scripts/pull_gist_data.py` mit `POSITIONS_JSON`-Fallback)
- `69456fe` — fix: watchlist drawer cards collapsed by default
  (`details-btn`/`news-btn` bleiben, neue selektor-relative
  `wlToggleDetails`/`wlToggleNews` statt ID-Lookups)
- `9487388` — fix: sparkline color thresholds and watchlist ticker lookup
  (B1: `scoreColor()` an `KI_DOT_STRONG/MODERATE/WEAK`; B2:
  `wrap.closest('[data-ticker]')` für TopTen + Watchlist gemeinsam)
- `e5a1d91` — style: weekend status into top bar instead of prominent banner
- `2e414c8` — style: methodology section visual restructuring
  (drei Score-Block-Cards Struktur/Katalysator/Timing + Boni/Malus-Pills)
- `05c3cae` — style: ki agent and anomaly trigger blocks tabular
  (KI-Agent-Boni und Anomalie-Trigger als zwei Score-Block-Cards mit
  Mono-Font-Werten, Push-Logik als Footer)
- `d61e67d` — feat: trade journal with statistics and lessons
  (Phase 2.5: Position-Close-Form mit These/Lesson, Gist-Sektion
  `closed_trades`, Trade-Journal-Sektion mit Hit-Rate +
  Setup-Score-Korrelation + Filter)

## Aktive Position

- **INDI** · Entry 27.04.2026 · 3,76 USD · 35 shares · letzter
  bekannter Stand ~+19 % (Spot $4,47).
- Nach Phase-2-Migration sollte die Position vom `POSITIONS_JSON`-
  Secret in den privaten Gist umgezogen werden — siehe Verifikation.

## Verifikation ausstehend (User-Action + nächster Daily-Run)

- **Gist-Setup einmalig:** privaten Gist anlegen mit
  `squeeze_data.json` (`{"watchlist": [], "positions": {},
  "closed_trades": []}`), Repo-Secrets `GIST_ID` + `GIST_TOKEN`
  (PAT mit `gist`-Scope) setzen.
- **Browser-Token-Scope:** der bestehende PAT in localStorage
  (`ghpat_squeeze`) muss `gist`-Scope haben — sonst `⚠ Gist-Sync
  HTTP 404` bei jedem Save.
- **INDI-Migration:** Position aus `POSITIONS_JSON`-Secret in den
  Gist kopieren (oder `pull_gist_data.py` greift solange auf den
  Legacy-Pfad zurück — keine Funktionseinbuße).
- **GIST_ID-Embed im HTML** verifizieren: `const GIST_ID = '…'` in
  der gerenderten `index.html` ≠ leerer String.
- **Drawer-Defaults:** „Details" und „Aktuelle Meldungen" in
  expandierter Watchlist-Karte zugeklappt; Toggle-Buttons öffnen
  korrekt via `wlToggleDetails`/`wlToggleNews`.
- **Sparkline-Sync:** rechtester Punkt in TopTen UND Watchlist-Karte
  hat dieselbe Farbe wie der pulsierende KI-Dot (Schwellen 60/30/15).
- **Methodik-Sektion:** drei Score-Karten + Boni/Malus-Pills + zwei
  KI-Agent-Karten + Push-Logik-Footer korrekt gerendert.
- **Trade-Journal:** „Position schließen" zeigt Form mit Verkaufsdaten
  + These/Lesson; Submit schreibt nach `closed_trades`. Hamburger-
  Menü-Eintrag „Trade-Journal" öffnet Sektion mit Statistiken.

## Geplante Aufgaben

1. **`pull_gist_data.py` Watchlist-Round-Trip** (optional): aktuell
   schreibt das Skript `watchlist_personal.json` nur, wenn der Gist
   eine nicht-leere Watchlist liefert. Phase-3-Idee: vollständigen
   Gist↔Repo-Sync auch in Browser-Adds aktivieren (`wlAddManual`
   schreibt parallel in den Gist), damit die Repo-Datei eines Tages
   entfallen kann.
2. **Trade-Journal: Bulk-Export** (CSV-Download für externe Auswertung).
3. **Trade-Journal: Editieren bestehender Einträge** (These/Lesson
   nachträglich ergänzen, ohne Trade neu zu schließen).
4. **GitHub Secret `EDGAR_USER_AGENT` setzen** (sofern noch offen).
5. **Phase 2 Exit-Signale UI** (Frontend für Exit-Score-Block + P&L
   in der Watchlist-Karte) — kann jetzt auf das Position-Panel
   aufsetzen.
6. **Bahn A2 (Frontend-Auswertungs-Panel)** ab Ende Mai
   (≥ 200 Live-Einträge).
7. **UX Backtesting „Nur Live"-Modus**: Erklärungstext bei n=0.
8. **Setup-Verfall-Symmetrie weiter beobachten** (jetzt raw vs. raw).
9. **⏰ Wiedervorlage 15.05.2026: Phase 3 Exit-Signale prüfen**
   (Blow-off-Top + IV-Crush; Voraussetzung: Phase 1 ~2 Wochen live).
10. **⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen**
    (Ortex / Fintel etc. nur wenn ROI passt; nach Bahn-A2-Auswertung).
11. **Filter-Flexibilisierung prüfen (Bahn A2)** — Mid-Caps + Non-US-
    Bahnen, Voraussetzung: Bahn-A2-Datenbasis ab Juli 2026.

## Optional / niedrig priorisiert

- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- `backtest_history.json` einmal cachen statt zwei Disk-Reads
- Alte `RS_SECTOR_*`-Konstanten + `_sector_rs_row()` ganz entfernen
- News-Decay-Logik auf UOA / Insider übertragen via `_news_age_weight()`
- KI-Agent-eigene Anomalien (UOA-Vol/OI / RVOL-Vortagsvergleich /
  Gap+Hold-Combo) auch in den Chat-Kontext einspeisen
- `EDGAR_ACTIVIST_FILERS`-Liste über Live-Beobachtung verfeinern
- Score-Popup (`showScoreExplain`) im Watchlist-Drawer nachrüsten
  (`closest('article')` schlägt fehl, da Wrapper gestrippt)

## Architektur-Anker (nicht in CLAUDE.md, wichtig)

- **`_wl_full_card_html(s)`** ist die Single Source of Truth für die
  Watchlist-Drawer-Open-Ansicht. Strippt `<article>`-Wrapper,
  Rank-Badge, `wl-add-btn` und alle stale `id="…N"`-Attribute aus dem
  `_card(0, s)`-Output. `details-btn`/`news-btn` bleiben sichtbar mit
  selektor-relativen Onclick-Targets `wlToggleDetails(this)` /
  `wlToggleNews(this)`. KI-Analyse-Klick → `wlOpenKiAnalyse(ticker)`.
- **Single-Source-Pattern für Karten-Ticker-Lookup:** `data-ticker` ist
  sowohl auf `<article class="card">` als auch auf `<div class="wl-card">`
  gesetzt. JS-Logik nutzt `el.closest('[data-ticker]')?.dataset.ticker`
  statt ID-basierter Lookups, damit beide Karten-Typen denselben Code
  nutzen können (`drawSparkline`-Live-Sync ist erstes Beispiel).
- **Sparkline-Schwellen an Config-Konstanten gekoppelt:** `scoreColor()`
  liest `KI_DOT_STRONG/MODERATE/WEAK` per f-string-Injection. Dot- und
  Sparkline-Endpunkt-Farbe driften nicht mehr — Schwellen-Änderung in
  `config.py` reicht.
- **Methodik-Layout-Klassen:** `.score-blocks` / `.score-block-card` /
  `.score-block-head` / `.score-block-name` / `.score-block-badge` /
  `.score-block-list` (mit `.sb-lbl` + `.sb-pts`) sind generische
  Karten-Bausteine — zweimal verwendet (Score-Formel + KI-Agent),
  optional Mono-Font-Modifier `.ki-agent-blocks .sb-pts`.
- **Inline-Status-Pattern (Top-Bar statt Banner):** Wochenend-Hinweis
  als `<span class="hdr-nontrading" hidden>` neben `.hdr-ts`. Pillen-
  Look mit dezentem Orange-Akzent. Pattern für künftige
  Statuszeilen wiederverwendbar.
- **Trade-Journal-Datenmodell ist Browser-only:**
  `closed_trades`-Sektion lebt nur im Gist + `_GIST_DATA`-Cache.
  `pull_gist_data.py` ignoriert sie. Python-Code (`compute_exit_score`,
  `process_exit_signals`) sieht keine geschlossenen Trades.
- **`window._SCORE_HISTORY` ist Pflicht-Bridge** für Trade-Journal:
  `wlSubmitClose` ermittelt `max_setup_score` durch Scan der
  History zwischen `entry_date` und `exit_date` (DE→ISO-Konvertierung
  inline). Ohne diese Bridge fehlt der Setup-Score-Korrelations-
  Wert; Render bleibt fail-soft mit `—`.
