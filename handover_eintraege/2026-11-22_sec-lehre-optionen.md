### 22.11.2026 — SEC-Lehre, options_intraday-Wiedervorlage, Platzhalter im Diagnose-Workflow (1 PR)

- `#751` (Branch `claude/sec-lehre-optionen-w3m8`, kein Merge-Hash — Regel a). Easy-Entscheide 22.11.2026.
  CLAUDE.md + open_item `edgar-abrufe-ausfall-1711`: Lehre „SEC verlangt eine echte Kontaktadresse“
  (anonyme GitHub-noreply-Adresse → 403), Stand nach Secret-Korrektur (8-K/Form 4 HTTP 200, 11/13) und
  Rest-Befund ParseError für VEEA/MPT (browse-edgar löst die Ticker nicht auf → Fix b). open_item
  `options-intraday-erster-lauf`: läuft unverändert weiter, kein Bau, Wiedervorlage 02.12.2026.
  `diagnose_provider_probe.yml`: Kontaktadresse im SEC-User-Agent durch neutralen Platzhalter ersetzt.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
