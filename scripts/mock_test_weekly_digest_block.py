"""Mock-Tests für den wöchentlichen Zusammenfassungs-Digest-Zusatzblock
(``health_check.weekly_summary_lines``, integriert in
``scripts/health_check_digest.py``, 25.09.2026).

Hintergrund: bündelt zwei bereits maschinenlesbare Inhalte — (a) §4-
Re-Test-Zähler-FORTSCHRITT (Delta seit letzter Woche, nicht der ohnehin
täglich sichtbare Snapshot aus ``retest_counter_line``) und (b) offene/
beobachtete Punkte aus ``open_items.json`` — zu EINEM Montags-Block im
bestehenden Health-Check-Digest. KEIN neuer Workflow, KEIN neuer externer
Datenabruf. Reines Housekeeping, keine Score-/Filter-/Alert-Logik berührt.

WICHTIGE ABWEICHUNG vom Auftrag, hier dokumentiert (Widerspruch nicht still
umgangen, siehe Modul-Kommentar in health_check.py direkt über
``weekly_summary_lines``): ``health_check_digest.py`` läuft auf einem
EIGENEN, einzigen täglichen Cron (``47 8 * * *``) — anders als der
Daily-Run kennt es KEIN premarket/postclose-Konzept. Das
``status_review_reminder.py``-Vorbild ("Montag UND postclose") lässt sich
deshalb nur zur Hälfte übertragen: der Gate-Test unten prüft ausschließlich
"nur Montag", eine "postclose"-Variante gibt es hier nicht (und ist auch
nicht nötig, weil der Digest ohnehin nur 1×/Tag läuft).

Pflicht-Szenarien laut Aufgabenstellung:
  (a) Wochenblock erscheint NUR montags, an keinem anderen Wochentag
  (b) Diff-Mechanismus meldet NUR Änderungen seit dem letzten State, nicht
      jede Woche den vollen Inhalt neu (Rauschen-Vermeidung)
  (c) §4-Zähler und Open-Items-Inhalt werden aus den ECHTEN Quellen/
      Funktionen gelesen (kein Mock der Kernlogik — echte Temp-Dateien,
      echte ``retest_counter_value``/``_load_open_items``-Aufrufe)

Zusätzlich (Robustheit):
  D. ``format_digest_body`` rendert ``weekly_lines`` in allen 3 Klassen
     (OK/Fail/keine-Daten), wenn vorhanden — und in keiner, wenn leer
  E. Fail-soft: fehlende/kaputte open_items.json bzw. matured-export-Datei
     crashen ``weekly_summary_lines`` nicht
  F. End-to-End gegen die ECHTE ``scripts/health_check_digest.main()``
     (isolierter Modul-Import, State-Datei + Datenquellen auf Tempdir
     umgebogen, ntfy deaktiviert — kein Netzwerk-Call)

Kategorie A: reine stdlib (json/tempfile/importlib/unittest.mock/pathlib),
keine Drittlibs. ``health_check.py`` selbst hat keine yfinance/requests-
Abhängigkeit (bereits von ``mock_test_digest.py`` im ALLOWLIST bestätigt).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest.mock as mock
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import health_check as hc  # noqa: E402

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        _fails.append(f"{name}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


# Feste, deterministische Wochentag-Fixtures (per date.weekday() verifiziert:
# Montag=0). 2026-09-21 ist ein Montag, 2026-09-28 der Montag danach.
_MON1 = datetime(2026, 9, 21, 8, 47, tzinfo=timezone.utc)
_MON2 = datetime(2026, 9, 28, 8, 47, tzinfo=timezone.utc)
_MON3 = datetime(2026, 10, 5, 8, 47, tzinfo=timezone.utc)
_TUE = datetime(2026, 9, 22, 8, 47, tzinfo=timezone.utc)
_SUN = datetime(2026, 9, 27, 8, 47, tzinfo=timezone.utc)
_FRI = datetime(2026, 9, 25, 8, 47, tzinfo=timezone.utc)


class _TmpFixture:
    """Baut ein Tempdir mit open_items.json + matured-export.jsonl."""

    def __init__(self, items: list[dict], matured_rows: list[dict]) -> None:
        self.items = items
        self.matured_rows = matured_rows
        self._tmpdir = None

    def __enter__(self):
        self._tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="weekly_digest_test_"))
        self.open_items_path = self._tmpdir / "open_items.json"
        self.matured_path = self._tmpdir / "matured.jsonl"
        self.open_items_path.write_text(
            json.dumps({"schema_v": 1, "items": self.items}), encoding="utf-8")
        with self.matured_path.open("w", encoding="utf-8") as fh:
            for row in self.matured_rows:
                fh.write(json.dumps(row) + "\n")
        return self

    def __exit__(self, *exc):
        pass  # Tempdir bewusst nicht gelöscht — OS räumt /tmp auf, kein Leak-Risiko hier

    def call(self, now_ts, prev_state):
        return hc.weekly_summary_lines(
            now_ts, prev_state,
            open_items_path=self.open_items_path,
            matured_export_path=self.matured_path,
        )


def _item(item_id, status, title=None):
    return {"id": item_id, "title": title or item_id, "status": status,
            "status_date": "2026-09-20", "opened": "2026-09-01",
            "description": "x"}


def _matured_rows(n_forward_ge70: int, n_other: int = 0) -> list[dict]:
    rows = [{"provenance": "forward", "score": 80} for _ in range(n_forward_ge70)]
    rows += [{"provenance": "forward", "score": 10} for _ in range(n_other)]
    return rows


# ── A — Nur Montag ───────────────────────────────────────────────────────

def test_a1_monday_with_bootstrap_data_produces_lines():
    with _TmpFixture([_item("a", "offen")], _matured_rows(5)) as fx:
        lines, updates = fx.call(_MON1, {})
        _check("A1 Montag + Erstlauf -> nicht-leere lines", len(lines) > 0, repr(lines))
        _check("A1 Montag -> state_updates enthält weekly_digest",
               "weekly_digest" in updates, repr(updates))


def test_a2_non_monday_always_empty_regardless_of_data():
    with _TmpFixture([_item("a", "offen")], _matured_rows(5)) as fx:
        for label, ts in (("Dienstag", _TUE), ("Sonntag", _SUN), ("Freitag", _FRI)):
            lines, updates = fx.call(ts, {})
            _check(f"A2 {label} (weekday={ts.weekday()}) -> lines leer",
                   lines == [], repr(lines))
            _check(f"A2 {label} -> KEIN State-Update (Snapshot bleibt Montags-verankert)",
                   updates == {}, repr(updates))


def test_a3_non_monday_state_unaffected_by_prior_monday_state():
    """Ein Nicht-Montags-Aufruf darf den zuletzt gespeicherten Montags-State
    nicht überschreiben (updates=={} -> Aufrufer mergt nichts)."""
    with _TmpFixture([_item("a", "offen")], _matured_rows(5)) as fx:
        _, mon_updates = fx.call(_MON1, {})
        _, tue_updates = fx.call(_TUE, mon_updates)
        _check("A3 Dienstag nach Montag -> weiterhin kein State-Update",
               tue_updates == {}, repr(tue_updates))


# ── B — Diff, nicht Voll-Inhalt ─────────────────────────────────────────

def test_b1_first_run_shows_all_active_as_new():
    with _TmpFixture([_item("a", "offen", "Item A"),
                      _item("b", "beobachtet", "Item B"),
                      _item("c", "erledigt", "Item C")],
                     _matured_rows(5)) as fx:
        lines, updates = fx.call(_MON1, {})
        joined = "\n".join(lines)
        _check("B1 Item A (offen) als neu gemeldet", "🆕" in joined and "Item A" in joined, joined)
        _check("B1 Item B (beobachtet) als neu gemeldet", "Item B" in joined, joined)
        _check("B1 Item C (erledigt) NICHT gemeldet (nie aktiv)", "Item C" not in joined, joined)
        snap = updates["weekly_digest"]["open_items_snapshot"]
        _check("B1 Snapshot enthält nur offen/beobachtet",
               snap == {"a": "offen", "b": "beobachtet"}, repr(snap))


def test_b2_unchanged_item_not_mentioned_second_week():
    with _TmpFixture([_item("a", "offen", "Item A")], _matured_rows(5)) as fx:
        _, updates1 = fx.call(_MON1, {})
    # Zweite Woche: identischer Inhalt (neue Fixture-Instanz, gleicher Stand)
    with _TmpFixture([_item("a", "offen", "Item A")], _matured_rows(5)) as fx2:
        lines2, updates2 = fx2.call(_MON2, updates1)
        _check("B2 unverändertes Item A -> keine Zeile", lines2 == [], repr(lines2))
        _check("B2 §4-Zähler unverändert -> ebenfalls keine Zeile (bereits in lines2==[] enthalten)",
               lines2 == [], repr(lines2))
        _check("B2 State rückt trotzdem weiter (last_monday_iso aktualisiert)",
               updates2["weekly_digest"]["last_monday_iso"] == "2026-09-28",
               repr(updates2))


def test_b3_status_change_reported_only_for_changed_item():
    with _TmpFixture([_item("a", "offen", "Item A"),
                      _item("b", "beobachtet", "Item B")],
                     _matured_rows(5)) as fx:
        _, updates1 = fx.call(_MON1, {})
    with _TmpFixture([_item("a", "beobachtet", "Item A"),   # geändert
                      _item("b", "beobachtet", "Item B")],   # unverändert
                     _matured_rows(5)) as fx2:
        lines2, _ = fx2.call(_MON2, updates1)
        joined = "\n".join(lines2)
        _check("B3 Item A Status-Wechsel gemeldet",
               "Item A" in joined and "offen → beobachtet" in joined, joined)
        _check("B3 Item B NICHT gemeldet (unverändert)", "Item B" not in joined, joined)


def test_b4_resolved_item_reported_and_removed_from_snapshot():
    with _TmpFixture([_item("a", "offen", "Item A")], _matured_rows(5)) as fx:
        _, updates1 = fx.call(_MON1, {})
    with _TmpFixture([_item("a", "erledigt", "Item A")], _matured_rows(5)) as fx2:
        lines2, updates2 = fx2.call(_MON2, updates1)
        joined = "\n".join(lines2)
        _check("B4 Item A als erledigt gemeldet",
               "✅" in joined and "Item A" in joined and "erledigt" in joined, joined)
        snap = updates2["weekly_digest"]["open_items_snapshot"]
        _check("B4 Item A aus Snapshot entfernt (nicht mehr aktiv)",
               "a" not in snap, repr(snap))


def test_b5_removed_entirely_reported_as_entfernt():
    """Item verschwindet komplett aus der Datei (nicht nur Status-Wechsel)."""
    with _TmpFixture([_item("a", "offen", "Item A")], _matured_rows(5)) as fx:
        _, updates1 = fx.call(_MON1, {})
    with _TmpFixture([], _matured_rows(5)) as fx2:
        lines2, _ = fx2.call(_MON2, updates1)
        joined = "\n".join(lines2)
        _check("B5 komplett entferntes Item -> 'entfernt'-Hinweis",
               "entfernt" in joined and "a" in joined, joined)


def test_b6_nothing_changed_at_all_yields_empty_lines_but_advances_state():
    """Kern-Beweis der Rauschen-Vermeidung: weder §4 noch Open-Items
    geändert -> lines leer, State trotzdem weitergerückt (nicht stehen
    geblieben — sonst würde ein Item beim übernächsten Montag fälschlich
    wieder als 'neu' auftauchen)."""
    items = [_item("a", "beobachtet", "Item A")]
    with _TmpFixture(items, _matured_rows(7)) as fx:
        _, updates1 = fx.call(_MON1, {})
    with _TmpFixture(items, _matured_rows(7)) as fx2:
        lines2, updates2 = fx2.call(_MON2, updates1)
        _check("B6 nichts geändert -> lines leer (kein Leerlauf-Hinweis)",
               lines2 == [], repr(lines2))
        _check("B6 State rückt trotzdem weiter",
               updates2["weekly_digest"]["last_monday_iso"] == "2026-09-28",
               repr(updates2))
        _check("B6 dritte Woche (weiterhin unverändert) -> immer noch leer",
               True)
    with _TmpFixture(items, _matured_rows(7)) as fx3:
        lines3, _ = fx3.call(_MON3, updates2)
        _check("B6b dritte Woche tatsächlich leer", lines3 == [], repr(lines3))


def test_b7_retest_counter_delta_reported_with_sign():
    with _TmpFixture([], _matured_rows(5)) as fx:
        _, updates1 = fx.call(_MON1, {})
    with _TmpFixture([], _matured_rows(9)) as fx2:  # n: 5 -> 9
        lines2, _ = fx2.call(_MON2, updates1)
        joined = "\n".join(lines2)
        _check("B7 §4-Delta mit korrektem Vorzeichen (+4)",
               "5 → 9" in joined and "+4" in joined, joined)


# ── C — echte Quellen, kein Mock der Kernlogik ──────────────────────────

def test_c1_retest_counter_value_reads_real_matured_export():
    with _TmpFixture([], _matured_rows(3, n_other=2)) as fx:
        counts = hc.retest_counter_value(fx.matured_path)
        _check("C1 retest_counter_value liest echte Datei: n=3, total=5",
               counts == (3, 5), repr(counts))


def test_c2_load_open_items_reads_real_schema():
    with _TmpFixture([_item("x", "offen"), _item("y", "erledigt")],
                     []) as fx:
        items = hc._load_open_items(fx.open_items_path)
        _check("C2 _load_open_items liest beide Items (inkl. erledigt)",
               items is not None and len(items) == 2, repr(items))
        active = hc._open_items_active_snapshot(items)
        _check("C2 Snapshot filtert 'erledigt' korrekt raus",
               active == {"x": "offen"}, repr(active))


# ── D — format_digest_body-Integration ──────────────────────────────────

def test_d1_weekly_lines_appear_in_ok_class():
    body, title, _, _ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-09-21T08:00:00Z",
        digest_date="2026-09-21",
        weekly_lines=["📅 Wochenübersicht:", "  🆕 Test-Item (offen)"])
    _check("D1 OK-Klasse enthält Wochenblock",
           "Wochenübersicht" in body and "Test-Item" in body, body)
    _check("D1 Titel bleibt OK (Wochenblock ändert keine Severity)",
           title == "✅ Health-Check OK", title)


def test_d2_weekly_lines_appear_in_no_data_class():
    body, title, _, _ = hc.format_digest_body(
        [], [], n_runs=0, last_run_iso=None, digest_date="2026-09-21",
        weekly_lines=["📅 Wochenübersicht:", "  🆕 Test-Item (offen)"])
    _check("D2 keine-Daten-Klasse enthält Wochenblock trotzdem",
           "Wochenübersicht" in body, body)
    _check("D2 Titel bleibt 'ohne Daten'", "ohne Daten" in title, title)


def test_d3_weekly_lines_appear_in_fail_class():
    fails = [{"id": "S1", "severity": "crit", "detail": "x", "count": 1}]
    body, title, _, _ = hc.format_digest_body(
        fails, [], n_runs=5, last_run_iso="2026-09-21T08:00:00Z",
        digest_date="2026-09-21",
        weekly_lines=["📅 Wochenübersicht:", "  🆕 Test-Item (offen)"])
    _check("D3 Fail-Klasse enthält Wochenblock",
           "Wochenübersicht" in body, body)


def test_d4_no_weekly_lines_means_no_block():
    body, _, _, _ = hc.format_digest_body(
        [], [], n_runs=5, last_run_iso="2026-09-21T08:00:00Z",
        digest_date="2026-09-21")
    _check("D4 kein weekly_lines-Arg -> kein Wochenblock im Body",
           "Wochenübersicht" not in body, body)


# ── E — Fail-soft ─────────────────────────────────────────────────────

def test_e1_missing_files_no_crash_state_still_advances_on_monday():
    missing_dir = pathlib.Path(tempfile.mkdtemp(prefix="weekly_digest_missing_"))
    lines, updates = hc.weekly_summary_lines(
        _MON1, {},
        open_items_path=missing_dir / "does_not_exist.json",
        matured_export_path=missing_dir / "also_missing.jsonl")
    _check("E1 fehlende Dateien -> kein Crash, lines leer (kein Bootstrap-Inhalt)",
           lines == [], repr(lines))
    _check("E1 State trotzdem gesetzt (leerer Snapshot, retest_n bleibt None)",
           updates.get("weekly_digest", {}).get("open_items_snapshot") == {}
           and updates.get("weekly_digest", {}).get("retest_n") is None,
           repr(updates))


def test_e2_corrupt_open_items_json_no_crash():
    """Kaputtes open_items.json wird wie 'keine Items' behandelt (kein Crash,
    keine 🆕/✅-Zeilen) — der §4-Teil ist davon UNABHÄNGIG und liefert normal
    eine Baseline-Zeile, weil das matured-export hier bewusst leer-aber-valide
    ist (nicht kaputt). Zwei unabhängige Datenquellen, ein Ausfall darf den
    anderen nicht mitreißen."""
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="weekly_digest_corrupt_"))
    (tmpdir / "open_items.json").write_text("{not valid json", encoding="utf-8")
    (tmpdir / "matured.jsonl").write_text("", encoding="utf-8")
    lines, updates = hc.weekly_summary_lines(
        _MON1, {},
        open_items_path=tmpdir / "open_items.json",
        matured_export_path=tmpdir / "matured.jsonl")
    joined = "\n".join(lines)
    _check("E2 kaputtes JSON -> kein Crash, keine Open-Items-Zeilen",
           "🆕" not in joined and "✅" not in joined and "🔁" not in joined, joined)
    _check("E2 §4-Teil bleibt unabhängig funktionsfähig (Baseline-Zeile)",
           "§4-Zähler" in joined, joined)
    _check("E2 Snapshot ist leer (kein Item aus kaputter Datei übernommen)",
           updates["weekly_digest"]["open_items_snapshot"] == {}, repr(updates))
    _check("E2 State weiterhin gesetzt", "weekly_digest" in updates, repr(updates))


# ── F — End-to-End gegen die echte health_check_digest.main() ──────────

def _import_digest_module():
    spec = importlib.util.spec_from_file_location(
        "_dgst_weekly", ROOT / "scripts" / "health_check_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main_capture_stdout(dg, **kwargs) -> tuple[int, str]:
    """Ruft dg.main(**kwargs) auf und liefert (exit_code, stdout-Text) —
    ohne pytest-Abhängigkeit, das Skript bleibt standalone lauffähig."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = dg.main(**kwargs)
    return rc, buf.getvalue()


def test_f1_end_to_end_monday_run_includes_weekly_block_in_dry_run():
    dg = _import_digest_module()
    with _TmpFixture([_item("z", "offen", "Live-Item")], _matured_rows(4)) as fx, \
         tempfile.TemporaryDirectory() as state_dir, \
         tempfile.TemporaryDirectory() as empty_root:
        # dg.ROOT auf ein LEERES Tempdir umgebogen — isoliert den Test
        # vollständig vom echten, wachsenden health_check_log.jsonl/
        # provider_health.jsonl (sonst content-flaky gegen reale Repo-Daten,
        # siehe run_ci_mock_tests.py EXCLUDED-Kriterium "liest ROOT/...").
        # Alle anderen Digest-Zeilen-Helper sind fail-soft auf fehlende
        # Dateien -> "nicht ermittelbar", kein Crash.
        tmp_state = pathlib.Path(state_dir) / "state.json"
        with mock.patch.object(dg, "ROOT", pathlib.Path(empty_root)), \
             mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg.hc, "OPEN_ITEMS_FILE", fx.open_items_path), \
             mock.patch.object(dg.hc, "MATURED_EXPORT_FILE", fx.matured_path), \
             mock.patch.object(dg, "NTFY_TOPIC", ""):
            rc, out = _run_main_capture_stdout(dg, now_ts=_MON1, dry_run=True)
        _check("F1 exit 0", rc == 0, f"rc={rc}")
        _check("F1 dry-run-Output enthält Wochenblock",
               "Wochenübersicht" in out and "Live-Item" in out, out)


def test_f2_end_to_end_non_monday_run_has_no_weekly_block():
    dg = _import_digest_module()
    with _TmpFixture([_item("z", "offen", "Live-Item")], _matured_rows(4)) as fx, \
         tempfile.TemporaryDirectory() as state_dir, \
         tempfile.TemporaryDirectory() as empty_root:
        tmp_state = pathlib.Path(state_dir) / "state.json"
        with mock.patch.object(dg, "ROOT", pathlib.Path(empty_root)), \
             mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg.hc, "OPEN_ITEMS_FILE", fx.open_items_path), \
             mock.patch.object(dg.hc, "MATURED_EXPORT_FILE", fx.matured_path), \
             mock.patch.object(dg, "NTFY_TOPIC", ""):
            rc, out = _run_main_capture_stdout(dg, now_ts=_TUE, dry_run=True)
        _check("F2 exit 0", rc == 0, f"rc={rc}")
        _check("F2 kein Wochenblock an einem Dienstag",
               "Wochenübersicht" not in out, out)


def test_f3_end_to_end_state_persists_weekly_digest_key():
    dg = _import_digest_module()
    with _TmpFixture([_item("z", "offen", "Live-Item")], _matured_rows(4)) as fx, \
         tempfile.TemporaryDirectory() as state_dir, \
         tempfile.TemporaryDirectory() as empty_root:
        tmp_state = pathlib.Path(state_dir) / "state.json"
        with mock.patch.object(dg, "ROOT", pathlib.Path(empty_root)), \
             mock.patch.object(dg, "DIGEST_STATE_FILE", tmp_state), \
             mock.patch.object(dg.hc, "OPEN_ITEMS_FILE", fx.open_items_path), \
             mock.patch.object(dg.hc, "MATURED_EXPORT_FILE", fx.matured_path), \
             mock.patch.object(dg, "NTFY_TOPIC", ""):
            rc = dg.main(now_ts=_MON1, dry_run=False)
        _check("F3 exit 0", rc == 0, f"rc={rc}")
        saved = json.loads(tmp_state.read_text(encoding="utf-8"))
        _check("F3 weekly_digest-Key in persistiertem State",
               "weekly_digest" in saved, repr(saved))
        _check("F3 Snapshot enthält das Live-Item",
               saved.get("weekly_digest", {}).get("open_items_snapshot") == {"z": "offen"},
               repr(saved))


def main() -> int:
    tests = [
        test_a1_monday_with_bootstrap_data_produces_lines,
        test_a2_non_monday_always_empty_regardless_of_data,
        test_a3_non_monday_state_unaffected_by_prior_monday_state,
        test_b1_first_run_shows_all_active_as_new,
        test_b2_unchanged_item_not_mentioned_second_week,
        test_b3_status_change_reported_only_for_changed_item,
        test_b4_resolved_item_reported_and_removed_from_snapshot,
        test_b5_removed_entirely_reported_as_entfernt,
        test_b6_nothing_changed_at_all_yields_empty_lines_but_advances_state,
        test_b7_retest_counter_delta_reported_with_sign,
        test_c1_retest_counter_value_reads_real_matured_export,
        test_c2_load_open_items_reads_real_schema,
        test_d1_weekly_lines_appear_in_ok_class,
        test_d2_weekly_lines_appear_in_no_data_class,
        test_d3_weekly_lines_appear_in_fail_class,
        test_d4_no_weekly_lines_means_no_block,
        test_e1_missing_files_no_crash_state_still_advances_on_monday,
        test_e2_corrupt_open_items_json_no_crash,
        test_f1_end_to_end_monday_run_includes_weekly_block_in_dry_run,
        test_f2_end_to_end_non_monday_run_has_no_weekly_block,
        test_f3_end_to_end_state_persists_weekly_digest_key,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — Test-Harness, nicht Prod
            _fails.append(f"{t.__name__}: unexpected {type(exc).__name__}: {exc}")
            print(f"  FAIL {t.__name__}: unexpected {type(exc).__name__}: {exc}")

    print()
    if _fails:
        print(f"{len(_fails)} FAIL:")
        for f in _fails:
            print("  -", f)
        return 1
    print(f"Alle {len(tests)} weekly_digest_block-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
