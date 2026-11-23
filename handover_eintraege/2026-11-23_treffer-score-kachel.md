### 23.11.2026 — Treffer-Score als violette Kachel mit Tageswert (1 PR, Easy-Merge)

- `#762` (Branch `claude/treffer-score-kachel-v8m4`, kein Merge-Hash — Regel a). Easy-Entscheid 23.11.2026.
  Treffer-Score als dritte Cockpit-Säule unter KI (`_treffer_pillar_html`): „+12,4 %“, „Rang x von N“
  (nur Top-10 desselben Laufs) bzw. „Watchlist“, Schild „UNVALIDIERT · TEST LÄUFT“, Stand „vorläufig HH:MM Uhr“
  oder „Stand TT.MM.“; Violett (`--treffer-col`) unabhängig vom Wert, kein Balken. Vorschau-Lauf rechnet mit
  dem aktuellen Kurs (`compute_for_top10(intraday=True)`, derselbe Kern) und schreibt `suw_daily.jsonl` nie;
  Rückfall auf den letzten Abendwert nur bis 3 Handelstage, ohne Rang; sonst „—“ mit Grund. Watchlist außerhalb
  der Top-10 mit Wert ohne Rang (kein zusätzlicher Abruf). Postclose für die Top-10 unverändert. Golden neu
  (nur Treffer-Stellen). Handover §7·0: „grau“ → „neutrale Akzentfarbe, nie Ampelfarbe“ (Easy bestätigt mit
  Merge). open_item `anzeige-ampelfarben-unvalidiert`.
