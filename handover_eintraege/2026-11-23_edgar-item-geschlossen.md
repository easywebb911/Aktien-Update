### 23.11.2026 — open_item edgar-abrufe-ausfall-1711 geschlossen (1 PR, Self-Merge)

- `#763` (Branch `claude/edgar-item-schliessen-q3k8`, kein Merge-Hash — Regel a). Easy-Auftrag 23.11.2026.
  Status „beobachtet“ → „erledigt“ mit Beleg: Ursachen count=5 (#737), Kontaktadresse/403 (Secret 21.11.),
  Ticker-Suche VEEA/MPT (#753); provider_health edgar_8k/edgar_form4 22.11. 11:34 und 19:41 UTC je 13/13 HTTP 200.
  Bleibende Lücke benannt: Berichtstag 20.11. — `material_8k_events`, `material_8k_events_14d` bei allen 10
  Einträgen `fetch_failed`, `letzter_termin_8k` leer; bei Auswertungen als unbekannt führen. Nur Doku/open_items.
