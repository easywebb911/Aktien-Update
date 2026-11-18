### 18.11.2026 — [Wächter] FINRA-Abruf der Datenprüfung Short Float repariert (1 PR)

- `#?` (Branch `claude/waechter-finra-csi-sortierung`, kein Merge-Hash — Regel a).
  Befund: erster Postclose mit PR C (18.11. 03:07 UTC) — Short Float 12 von 12 „nicht prüfbar“
  (`finra_fehler`), Cache `finra_si_cache.json` leer. Ursache: `aktienbasis_check.fetch_finra` sendete
  `sortFields: ["-settlementDate"]`; FINRA antwortet darauf mit HTTP 400 („Sorting is allowed only if all
  partitions keys are specified in EQUAL CompareFilter … settlementDate“). Änderung: kein `sortFields`,
  stattdessen `dateRangeFilters` auf `settlementDate` (120 Tage bis heute, Limit 50); `normalize_records`
  sortiert wie bisher lokal. Live-Probe aus der Sitzung: FGL 30.10.2026 Bestand 28.526 (= Anker). Test 40 in
  `scripts/mock_test_aktienbasis_check.py`. Kein Score-/Filter-/Auswahl-Effekt (nur Kennzeichen/Rohwerte).
  Beleg im echten Lauf: nächster Daily-Run, Log-Zeile `[aktienbasis]`.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
