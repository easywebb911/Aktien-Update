### 23.11.2026 — Verkürzte Handelstage 2027/2028 nachgetragen + open_item feste Handelszeiten (1 PR, Easy-Merge)

- `#761` (Branch `claude/early-close-2027-2028-z4k1`, kein Merge-Hash — Regel a). Easy-Entscheid 23.11.2026.
  `config.US_EARLY_CLOSE_DAYS` um 26.11.2027, 03.07.2028, 24.11.2028 ergänzt (je 13:00 ET; Quelle NYSE
  hours-calendars, von Claude nachgeschlagen — nur Fußnoten gelesen, für 2027 kein weiterer verkürzter Tag).
  `US_MARKET_HOLIDAYS` 2027/2028 geprüft: gefüllt (je 10 Tage, regelbasiert), 24.12.2027 als voller Feiertag
  enthalten. Neues open_item `verkuerzte-handelstage-feste-zeiten` (Pille, Frontend, minute_bars,
  resolve_run_phase, get_market_phase → Earnings-Sofort-Alert verspätet; kein Bau). Test 52 Checks.
