### 17.11.2026 — Erkundungsfeld: rvol-Regel wie im Tool (1 PR, Manual-Merge)

- `#?` (Branch `claude/erkundungsfeld-rvol-vorrang-93ce`, kein Merge-Hash — Regel a).
  Easy-Entscheid 17.11.: genau ein Fix nach der Fehl-Analyse (`#743`). Regeltext + Schwelle zuerst ins
  open_item `erkundungsfeld-plan` (Commit `24f507da`), dann Code: `scripts/erkundungsfeld.py` wendet
  rvol >= 1,5 nicht mehr hart an, sondern als Vorrang wie `generate_report.py` (`top10_vol`: mindestens
  10 Namen über 1,5 → nur diese, sonst alle nach Score; `select_tool_order`). Plätze 11–30 bei geltendem
  Vorrang nicht aufgefüllt. Bericht `rvol_regel` (aufgefüllte Tage). Fehl-Analyse-Modus nutzt dieselbe
  Auswahl. SEC-Nenner, Vorfilter, Kandidatenkreis, Schwelle unverändert. Test 15 angepasst, Tests 47–53
  neu. Lauf „voll“ startet Easy; unter 5 → Vorschlag „Feld schließen“.
- **Guardian-Lauf vor Ready:** siehe PR-Bericht.
