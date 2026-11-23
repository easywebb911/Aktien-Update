### 23.11.2026 — open_item edgar-abrufe-ausfall-1711 geschlossen (1 PR, Self-Merge)

- `#763` (Branch `claude/edgar-item-schliessen-q3k8`, kein Merge-Hash — Regel a). Easy-Auftrag 23.11.2026.
  Status „beobachtet“ → „erledigt“ mit Beleg: Ursachen count=5 (#737), Teilausfall 17.11. 22:25 bis 20.11. (Ursache unbelegt,
  seit Fix (b) weg), Kontaktadresse/403 (20.11. 20:21 bis 21.11. 17:33 UTC, Secret 21.11.), Ticker-Suche VEEA/MPT
  (#753); provider_health edgar_8k/edgar_form4 22.11. 11:34 und 19:41 UTC je 13/13 HTTP 200, danach fehlerfrei.
  Bleibende Lücken benannt: Berichtstag 20.11. (`material_8k_events`, `_14d` fetch_failed bei allen 10,
  `letzter_termin_8k` leer), KI-Score-Bausteine 8-K/Form 4 17.–20.11., `edgar_13d_g`-Pushes im Ausfallzeitraum.
  Digest-Punkt (c) → neues open_item `digest-totalausfall-quelle`. CLAUDE.md-Zeitangabe 403 korrigiert.
