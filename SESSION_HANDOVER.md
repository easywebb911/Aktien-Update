# Session-Handover — Stand 03.05.2026

## Heute implementiert (chronologisch)
- 8a71e30 — fix: leftover _sort_keeping_manual_last call site
  (1c4dafe-Refactor-Reststand: zweiter Aufruf in main() nach
  post-enrichment Score-Smoothing-Block übersehen, hätte beim
  nächsten Daily-Run NameError geworfen; ersetzt durch
  top10.sort(key=lambda x: x.get("score") or 0, reverse=True)
  analog erste Call-Site. Repo-weit _sort_keeping_manual_last,
  manual_forced, rank-manual jetzt komplett verschwunden.)
- 4b04322 — feat: Phase 3 — Master-Passwort-Token-Encryption
  (WebCrypto AES-GCM 256 + PBKDF2-SHA256 600k Iterationen,
  Schema-Version v:1 im Blob; getToken() als Single-Reader,
  _setSessionToken/_clearAllTokens als einzige Schreibpfade;
  3 Modals: Setup/Unlock/Migrate; Cold-Start-Hook migriert
  bestehenden Klartext-Token; 14 Token-Reads umgestellt in
  Watchlist-Sync, Gist-Sync, Workflow-Trigger, Settings;
  401/403-Handler räumt alle Token-Slots; Esc schließt Modals,
  Inputs leeren beim Close. CLAUDE.md neue Sektion ergänzt.)

## Aktive Position (im Secret POSITIONS_JSON)
- INDI · Entry 27.04.2026 · 3,76 USD · 35 shares
  (Stand vom Vor-Handover, in dieser Session nicht berührt)

## Verifikation ausstehend
- Nächster Daily-Run muss ohne NameError durchlaufen
  (8a71e30 entfernt den Crash-Pfad).
- Master-Passwort-Flow auf Desktop + iPhone bereits manuell
  verifiziert in dieser Session — keine offene Verifikation.

## Geplante Aufgaben
1. GitHub Secret EDGAR_USER_AGENT setzen (aus Vor-Handover offen)
2. Phase 2 Exit-Signale (UI-First) nach 1 Woche Live-Test
3. Immediacy-Score-Feature
4. Bahn A2 (Frontend-Auswertungs-Panel) ab Ende Mai
5. UX Backtesting "Nur Live"-Modus
6. Setup-Verfall-Symmetrie weiter beobachten
7. ⏰ Wiedervorlage 15.05.2026: Phase 3 Exit-Signale prüfen
   (Blow-off-Top + IV-Crush)
8. ⏰ Wiedervorlage 02.07.2026: Premium-Daten-Stack prüfen
9. Filter-Flexibilisierung prüfen (Bahn A2)

## Optional / niedrig priorisiert
- IBKR Borrow Rate liefert konstant HTTP 404 — Provider-Fallback
  prüfen (Stockanalysis o.ä.); aktuell fällt der Borrow-Rate-
  Driver in _drivers_breakdown still aus.
- Per-Ticker Alert-Lock falls Alert-Loop parallelisiert wird
- Watchlist-Drawer (buildWlDetails) auf neuen Score-Block migrieren
- backtest_history.json einmal cachen statt zwei Disk-Reads
- Alte RS_SECTOR_*-Konstanten + _sector_rs_row() ganz entfernen
- News-Decay-Logik auf UOA / Insider übertragen via
  _news_age_weight(), sobald Persistenz da ist
- KI-Agent-eigene Anomalien (UOA-Vol/OI / RVOL-Vortagsvergleich /
  Gap+Hold-Combo) auch in den Chat-Kontext einspeisen
- EDGAR_ACTIVIST_FILERS-Liste über Live-Beobachtung verfeinern

## Architektur-Anker (nicht in CLAUDE.md, wichtig)
- Single-Reader-Pattern für GitHub-Token: getToken() ist der
  einzige Lese-Pfad, _setSessionToken / _clearAllTokens die
  einzigen Schreibpfade. Direktzugriffe auf
  localStorage[TOK_KEY] / sessionStorage[TOK_KEY] sind
  verboten — Lint-Idee für später: grep auf
  localStorage.(get|set|remove)Item.*TOK_KEY mit erwartetem
  Treffer-Count 0.
- Token-Storage zweistufig: localStorage[TOK_ENC_KEY=
  'ghpat_squeeze_encrypted'] persistent verschlüsselt,
  sessionStorage[TOK_KEY='ghpat_squeeze'] Klartext nur Session.
  Master-Passwort lebt nur im Memory.
- Krypto-Schema versioniert (v:1 im Blob) — bei Upgrade
  (z.B. Argon2 statt PBKDF2) v:2 einführen, Migration über
  altes Passwort entschlüsseln + mit neuem Schema neu
  verschlüsseln. Nicht still ändern.
- Watchlist-Ticker außerhalb Top-10 erscheinen ausschließlich
  in der Watchlist-Sektion (durch 1c4dafe etabliert,
  durch 8a71e30 verfestigt). Kein manual_forced-Bucket mehr
  in der Top-10-Liste.
