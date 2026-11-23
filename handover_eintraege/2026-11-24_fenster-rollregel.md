### 24.11.2026 — Fenster-Rollregel für die Edge-Suche festgeschrieben (1 PR, Easy-Merge)

- `#764` (Branch `claude/fenster-rollregel-w7p2`, kein Merge-Hash — Regel a). Easy-Entscheid 24.11.2026, reine Doku.
  Neue feste Regel SESSION_HANDOVER §7·0b + Kurzfassung CLAUDE.md: Fenster zeitlich geteilt; Blindfenster 1 = Einstiege
  ≥ 24.10.2026; Stichtag 1 als Ereignis (alle Tests mit Blindheits-Wortlaut ausgewertet), ein einheitlicher Stichtag;
  danach Suchfeld mit Suchbudget 10 und Bestätigung auf Blindfenster N+1; Regel 7 a–d für lange Läufer. Pool-Schatten
  Rang 11+ ab sofort „Pool-Schatten 1“ (Bestätigung nur auf späteren Handelstagen; Top-10 gegen Rang 11+ bis Stichtag 1
  nicht erlaubt). Neue open_items `fenster-rollregel` (Zähler, Mehrfachtest-Zählung) und `auswertungs-skripte-frist`
  (15.01.2027). §7·0a, Nutzungsregeln Pool-Schatten/Verwässerung, `outcome_path`, Minutenkurse und
  `blindes-fenster-keine-weiteren-tests` angeglichen. Freeze-Blöcke unverändert (MD5 15/15 gleich).
