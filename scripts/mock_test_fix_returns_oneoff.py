"""Mock-Test: einmalige Renditen-Bestandskorrektur (Schritt 2/3, 03.11.2026).

Fake-Kurse, kein Netz, fester Zeitpunkt.

  01 Gleichheit: recompute() == ki_agent.update_backtest_returns() (nach #647)
     für dieselben Kurse und denselben Zeitpunkt (alle Ziel-Felder)
  02 korrekter Wert → unverändert, nicht im Archiv
  03 Intraday-Wert → neu berechnet (Schluss T+N), Grund neu_berechnet
  04 Ticker ohne Kurse → null (Grund ticker_ohne_kursdaten), nie 0, nie alt
  05 Einstiegstag fehlt → null; Zieltag nicht final → null
  06 leeres Feld bleibt leer; fehlender Key wird nicht angelegt; Bootstrap unberührt
  07 dry_run schreibt nichts (Dateien byte-gleich, kein Archiv)
  08 apply: Archiv-Zeilen vollständig (alle 7 Schlüssel), Zahl = Änderungen
  09 apply: Reihenfolge/Zeilenzahl gleich, unveränderte Zeilen byte-gleich,
     geänderte Zeilen nur in Ziel-Feldern anders
  10 apply ist idempotent (zweiter Lauf ändert nichts, Archiv wächst nicht)
  11 restore stellt beide Dateien byte-genau wieder her
  12 Sicherheit: zu viele Ticker ohne Kurse / Dateien zwischendurch geändert
     → Abbruch, nichts geschrieben
  13 Blindung: Log enthält keine alten Renditewerte
  14 Workflow-YAML: nur workflow_dispatch, Default dry_run, Rechte je Job,
     concurrency, keine Secrets, Abbruch-Prüfungen vorhanden
  15 Determinismus: gleiche Eingabe → gleiche Ausgabe
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _install_stubs():
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")
    if "yfinance" not in sys.modules:
        yf_stub = types.ModuleType("yfinance")
        yf_stub.download = lambda *a, **k: None
        yf_stub.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf_stub


_install_stubs()
import ki_agent  # noqa: E402
import fix_returns_final_close_oneoff as fx  # noqa: E402

UTC = _dt.timezone.utc
NOW = _dt.datetime(2026, 11, 5, 18, 0, tzinfo=UTC)          # Do 13:00 ET (Sitzung)
FINAL = _dt.date(2026, 11, 4)
_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _days(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


# Kurse: Mo 19.10.2026 … Do 05.11.2026 (letzte Zeile = laufender Tag)
DATES = _days(_dt.date(2026, 10, 19), 14)
VALS = [10.0, 10.4, 10.9, 11.3, 10.8, 11.6, 12.1, 12.7, 12.2, 13.0, 13.4, 12.9, 13.8, 14.6]
SPYV = [500.0 + i for i in range(14)]
CLOSES = list(zip(DATES, VALS))
SPY = list(zip(DATES, SPYV))
assert DATES[-1] == _dt.date(2026, 11, 5)


# ── Fake-pandas für update_backtest_returns ─────────────────────────────────
class _TS:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Iloc:
    def __init__(self, v): self._v = v
    def __getitem__(self, i): return self._v[i]


class _Closes:
    def __init__(self, pairs):
        self.index = [_TS(d) for d, _ in pairs]
        self._v = [v for _, v in pairs]
    @property
    def iloc(self): return _Iloc(self._v)
    def __len__(self): return len(self._v)
    def dropna(self): return self
    def squeeze(self): return self


class _DF:
    empty = False
    def __init__(self, pairs): self._c = _Closes(pairs)
    def __contains__(self, k): return k == "Close"
    def __getitem__(self, k):
        if k == "Close":
            return self._c
        raise KeyError(k)


def _blank(date, ticker="AAA", **extra):
    e = {"date": date, "ticker": ticker, "score": 80.0, "entry_price": 10.0,
         "entry_price_t1": None}
    for w in (3, 5, 10):
        e[f"return_{w}d"] = None
        e[f"return_{w}d_net"] = None
        e[f"return_{w}d_vs_spy"] = None
        e[f"return_{w}d_t1"] = None
    e.update(extra)
    return e


def _ki_fill(entries):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(entries, tmp)
    tmp.close()

    class _Yf:
        def download(self, tickers, *a, **k):
            return _DF(SPY) if tickers == "SPY" else _DF(CLOSES)
    orig = (ki_agent.BACKTEST_FILE, ki_agent.yf, ki_agent.BACKTEST_ENABLED)
    try:
        ki_agent.BACKTEST_FILE, ki_agent.yf, ki_agent.BACKTEST_ENABLED = tmp.name, _Yf(), True
        with contextlib.redirect_stdout(io.StringIO()):
            ki_agent.update_backtest_returns(now_utc=NOW)
    finally:
        ki_agent.BACKTEST_FILE, ki_agent.yf, ki_agent.BACKTEST_ENABLED = orig
    out = json.loads(pathlib.Path(tmp.name).read_text(encoding="utf-8"))
    pathlib.Path(tmp.name).unlink()
    return out


def test_01_equivalence():
    dates = ["19.10.2026", "20.10.2026", "22.10.2026", "26.10.2026", "29.10.2026", "02.11.2026"]
    filled = _ki_fill([_blank(d) for d in dates])
    n_cmp = 0
    ok = True
    for e in filled:
        vals = fx.recompute(e, CLOSES, SPY, FINAL)
        for f in fx.TARGET_FIELDS:
            n_cmp += 1
            if vals[f][0] != e.get(f):
                ok = False
                print(f"      Unterschied {e['date']} {f}")
    _check(f"01 recompute == update_backtest_returns ({n_cmp} Felder)", ok)
    _check("01 Vergleich enthält gefüllte UND leere Felder",
           any(v is not None for e in filled for v in (e["return_3d"],))
           and any(e["return_10d"] is None for e in filled))


def _good(date):
    return fx.recompute({"date": date}, CLOSES, SPY, FINAL)


def test_02_06_correct_record():
    v = _good("19.10.2026")
    e = {"date": "19.10.2026", "ticker": "AAA", "return_3d": v["return_3d"][0],
         "return_3d_net": v["return_3d_net"][0], "x": 1}
    new, ch = fx.correct_record(e, CLOSES, SPY, FINAL)
    _check("02 korrekter Wert → unverändert", ch == [] and new == e, str(ch))
    e2 = dict(e, return_3d=77.77)
    new, ch = fx.correct_record(e2, CLOSES, SPY, FINAL)
    _check("03 Intraday-Wert → neu", new["return_3d"] == v["return_3d"][0]
           and ch == [("return_3d", 77.77, v["return_3d"][0], "neu_berechnet")], str(ch))
    new, ch = fx.correct_record(e2, None, SPY, FINAL)
    _check("04 ohne Kurse → null", new["return_3d"] is None and new["return_3d_net"] is None
           and all(g == "ticker_ohne_kursdaten" for *_, g in ch), str(ch))
    _check("04 nie 0", 0 not in (new["return_3d"], new["return_3d_net"]))
    new, ch = fx.correct_record(dict(e2, date="18.10.2026"), CLOSES, SPY, FINAL)
    _check("05 Einstiegstag fehlt → null", new["return_3d"] is None
           and ch[0][3] == "einstiegstag_fehlt", str(ch))
    # Entry 02.11.: T+3 = 05.11. (laufender Tag) → nicht final
    e3 = {"date": "02.11.2026", "ticker": "AAA", "return_3d": 5.5, "entry_price_t1": 9.9}
    new, ch = fx.correct_record(e3, CLOSES, SPY, FINAL)
    _check("05 Zieltag nicht final → null", new["return_3d"] is None
           and dict((f, g) for f, _, _, g in ch)["return_3d"] == "zieltag_fehlt_oder_nicht_final",
           str(ch))
    _check("05 entry_price_t1 (T+1 final) neu berechnet",
           new["entry_price_t1"] == round(VALS[DATES.index(_dt.date(2026, 11, 3))], 4))
    e4 = {"date": "19.10.2026", "ticker": "AAA", "return_3d": None, "y": 2}
    new, ch = fx.correct_record(e4, CLOSES, SPY, FINAL)
    _check("06 leeres Feld bleibt leer, fehlender Key nicht angelegt",
           new == e4 and ch == [] and "return_5d" not in new)


def _write_files(d: pathlib.Path):
    v19, v26 = _good("19.10.2026"), _good("26.10.2026")
    bt = [
        {"date": "19.10.2026", "ticker": "AAA", "score": 81.0, "return_3d": v19["return_3d"][0],
         "return_5d": 66.66, "return_5d_net": 1.23, "entry_price_t1": v19["entry_price_t1"][0],
         "notiz": "ä"},
        {"date": "26.10.2026", "ticker": "AAA", "score": 72.5, "return_3d": 77.77,
         "return_3d_vs_spy": 70.0, "return_10d": None},
        {"date": "26.10.2026", "ticker": "ZZZ", "score": 90.0, "return_3d": 3.3},
        {"date": "19.10.2026", "ticker": "AAA", "source": "bootstrap", "return_3d": 55.55},
    ]
    ex = [
        {"date": "19.10.2026", "ticker": "AAA", "score": 81.0, "provenance": "forward",
         "return_3d": v19["return_3d"][0], "return_5d": 66.66, "exported_at": "x"},
        {"date": "22.10.2026", "ticker": "AAA", "score": 75.0, "provenance": "forward",
         "return_3d": _good("22.10.2026")["return_3d"][0], "exported_at": "y"},
    ]
    (d / fx.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / fx.EXPORT_FILE).write_text(
        "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in ex),
        encoding="utf-8")
    return v26


PRICES = ({"AAA": CLOSES, "ZZZ": None}, SPY)


def _run(mode, d, prices=PRICES):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fx.run(mode, NOW, root=d, prices=prices)
    return rc, buf.getvalue()


def _snap(d):
    return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}


def test_07_15_files():
    d = pathlib.Path(tempfile.mkdtemp())
    v26 = _write_files(d)
    before = _snap(d)
    rc, log = _run("dry_run", d)
    _check("07 dry_run rc 0", rc == 0, log[-400:])
    _check("07 dry_run schreibt nichts", _snap(d) == before)
    _check("13 Blindung: alte Werte nicht im Log",
           all(s not in log for s in ("77.77", "66.66", "55.55", "70.0")), log)
    rc2, log2 = _run("dry_run", d)
    _check("15 Determinismus: gleiche Eingabe → gleiches Log", log == log2)

    rc, log = _run("apply", d)
    _check("08 apply rc 0", rc == 0, log[-400:])
    arch = [json.loads(l) for l in (d / fx.ARCHIVE_FILE).read_text(encoding="utf-8").splitlines()]
    keys = {"datei", "date", "ticker", "feld", "alt", "neu_oder_null", "grund"}
    _check("08 Archiv-Zeilen vollständig", arch and all(set(a) == keys for a in arch), str(arch[:1]))
    bt_new = json.loads((d / fx.BT_FILE).read_text(encoding="utf-8"))
    bt_old = json.loads(before[fx.BT_FILE])
    ex_new_lines = (d / fx.EXPORT_FILE).read_text(encoding="utf-8").splitlines()
    ex_old_lines = before[fx.EXPORT_FILE].decode().splitlines()
    n_diff = sum(1 for o, n in zip(bt_old, bt_new) for k in o if o[k] != n[k]) + \
        sum(1 for o, n in zip(ex_old_lines, ex_new_lines)
            for k, v in json.loads(o).items() if json.loads(n)[k] != v)
    _check("08 Archiv-Zeilen = Zahl geänderter Felder", len(arch) == n_diff, f"{len(arch)} vs {n_diff}")
    _check("08 Intraday-Werte korrigiert",
           bt_new[1]["return_3d"] == v26["return_3d"][0] and bt_new[0]["return_5d"] == _good("19.10.2026")["return_5d"][0])
    _check("08 _vs_spy neu", bt_new[1]["return_3d_vs_spy"] == v26["return_3d_vs_spy"][0])
    _check("04 Ticker ohne Kurse (ZZZ) → null", bt_new[2]["return_3d"] is None)
    _check("06 Bootstrap unberührt", bt_new[3] == bt_old[3])
    _check("06 leeres return_10d bleibt leer", bt_new[1]["return_10d"] is None)
    _check("09 Zeilenzahl/Reihenfolge gleich",
           len(bt_new) == len(bt_old) and len(ex_new_lines) == len(ex_old_lines)
           and [(r["ticker"], r["date"]) for r in bt_new] == [(r["ticker"], r["date"]) for r in bt_old])
    _check("09 unveränderte Export-Zeile byte-gleich", ex_new_lines[1] == ex_old_lines[1])
    ok = True
    for o, n in zip(bt_old + [json.loads(x) for x in ex_old_lines],
                    bt_new + [json.loads(x) for x in ex_new_lines]):
        if list(o) != list(n) or any(o[k] != n[k] for k in o if k not in fx.TARGET_FIELDS):
            ok = False
    _check("09 alle anderen Felder gleich, Schlüssel-Reihenfolge gleich", ok)
    _check("09 Umlaut erhalten (ensure_ascii=False)", '"notiz": "ä"' in (d / fx.BT_FILE).read_text(encoding="utf-8"))
    _check("09 kein .tmp liegen geblieben", not any(p.suffix == ".tmp" for p in d.iterdir()))

    after_apply = _snap(d)
    rc, log = _run("apply", d)
    _check("10 zweiter apply ändert nichts", _snap(d) == after_apply, log[-300:])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fx.restore(root=d, apply=True)
    snap = _snap(d)
    _check("11 restore: backtest_history.json byte-genau wie vorher",
           snap[fx.BT_FILE] == before[fx.BT_FILE])
    _check("11 restore: Export byte-genau wie vorher", snap[fx.EXPORT_FILE] == before[fx.EXPORT_FILE])
    shutil.rmtree(d)


def test_12_safety():
    d = pathlib.Path(tempfile.mkdtemp())
    _write_files(d)
    before = _snap(d)
    many = ({**{f"T{i}": None for i in range(fx.MAX_TICKERS_OHNE_DATEN + 1)}, "AAA": CLOSES, "ZZZ": None}, SPY)
    orig_todo_tickers = None
    # mehr Ticker ohne Kurse als erlaubt: Records für T0..Tn ergänzen
    bt = json.loads(before[fx.BT_FILE])
    bt += [{"date": "19.10.2026", "ticker": f"T{i}", "return_3d": 1.0}
           for i in range(fx.MAX_TICKERS_OHNE_DATEN + 1)]
    (d / fx.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    before = _snap(d)
    rc, log = _run("apply", d, prices=many)
    _check("12 zu viele Ticker ohne Kurse → Abbruch, nichts geschrieben",
           rc == 2 and _snap(d) == before and "ABBRUCH" in log, log[-300:])
    del orig_todo_tickers
    shutil.rmtree(d)

    d = pathlib.Path(tempfile.mkdtemp())
    _write_files(d)
    before = _snap(d)
    orig_sha = fx._sha
    calls = {"n": 0}

    def _sha_changes(p):
        calls["n"] += 1
        return orig_sha(p) + ("x" if calls["n"] > 2 else "")
    fx._sha = _sha_changes
    try:
        rc, log = _run("apply", d)
    finally:
        fx._sha = orig_sha
    _check("12 Datei zwischendurch geändert → Abbruch, nichts geschrieben",
           rc == 2 and _snap(d) == before and "seit dem Lesen" in log, log[-300:])
    shutil.rmtree(d)


def test_12b_duplicates():
    d = pathlib.Path(tempfile.mkdtemp())
    _write_files(d)
    bt = json.loads((d / fx.BT_FILE).read_text(encoding="utf-8"))
    bt.append(dict(bt[0]))
    (d / fx.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    before = _snap(d)
    try:
        _run("apply", d)
        aborted = False
    except SystemExit as exc:
        aborted = "doppelte" in str(exc)
    _check("12 doppelte (ticker, date) → Abbruch, nichts geschrieben", aborted and _snap(d) == before)
    shutil.rmtree(d)


def test_14_workflow():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/fix_returns_oneoff.yml").read_text(encoding="utf-8"))
    on = wf.get(True) or wf.get("on")
    src = (ROOT / ".github/workflows/fix_returns_oneoff.yml").read_text(encoding="utf-8")
    _check("14 nur workflow_dispatch", list(on) == ["workflow_dispatch"])
    inp = on["workflow_dispatch"]["inputs"]["mode"]
    _check("14 Input mode dry_run|apply, Default dry_run",
           inp["default"] == "dry_run" and inp["options"] == ["dry_run", "apply"])
    _check("14 Workflow-Rechte: nur Lesen", wf["permissions"] == {"contents": "read"})
    _check("14 dry_run-Job nur Lesen", wf["jobs"]["dry_run"]["permissions"] == {"contents": "read"})
    _check("14 apply-Job contents: write", wf["jobs"]["apply"]["permissions"]["contents"] == "write")
    _check("14 concurrency gesetzt, kein Abbruch laufender Läufe",
           wf["concurrency"]["cancel-in-progress"] is False)
    _check("14 keine Secrets", "secrets." not in src)
    _check("14 Abbruch bei aktivem Daily/KI-Lauf", "daily-squeeze-report.yml ki_agent.yml" in src)
    _check("14 Abbruch bei geändertem Stand auf main",
           "origin/main:backtest_history.json" in src and "origin/main:matured_backtest_export.jsonl" in src)
    _check("14 dry_run belegt: keine Datei geändert", "git diff --exit-code" in src)


def main() -> int:
    for t in (test_01_equivalence, test_02_06_correct_record, test_07_15_files,
              test_12_safety, test_12b_duplicates, test_14_workflow):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle fix_returns_oneoff-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
