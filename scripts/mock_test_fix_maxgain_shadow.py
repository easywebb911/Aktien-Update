"""Mock-Test: Korrektur max_gain/max_drawdown + Exit-Shadow-Forwards (03.11.2026).

``fix_returns_final_close_oneoff.py --target maxgain_shadow`` →
``scripts/fix_maxgain_shadow.py``. Fake-Kurse, kein Netz, fester Zeitpunkt.

  01 Gleichheit max_gain/max_drawdown/net: Skript == Rolling-Block in der
     ECHTEN ``_append_backtest_entries`` (gleicher Zeitpunkt, gleiche Kurse;
     _compute_* durch deterministische Spione ersetzt — gilt für beide Wege)
  02 Gleichheit Forward-Felder: Skript == ``ki_agent.update_exit_shadow_forwards``
  03 laufender Tag zählt nicht (Fenster/Forward)
  04 korrekt → unverändert; intraday → neu; fehlende Kurse → null (nie 0);
     < 2 Fensterzeilen → null (Grund zu_wenig_daten), nicht 0.0
  05 dry_run schreibt nichts
  06 apply: Archiv vollständig (7 Schlüssel, Zahl = geänderte Felder),
     andere Felder/Reihenfolge/Zeilenzahl byte-gleich, Bootstrap unberührt,
     kein Key angelegt
  07 apply idempotent; restore byte-genau
  08 Abbrüche: max_null fehlt/überschritten, Datei zwischendurch geändert
  09 target=returns unverändert: CLI ohne --target ruft den #648-Pfad
  10 Workflow: Input target (Default returns), Exit-Shadow-Datei im Blob-
     Vergleich und im Commit, beide Archive
  11 Blindung: alte Werte nicht im Log; Determinismus
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
    for name in ("pandas", "requests"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    if "yfinance" not in sys.modules:
        yf_stub = types.ModuleType("yfinance")
        yf_stub.download = lambda *a, **k: None
        yf_stub.Ticker = lambda *a, **k: None
        sys.modules["yfinance"] = yf_stub


_install_stubs()
import ki_agent  # noqa: E402
import exit_shadow  # noqa: E402
import backtest_history as bh  # noqa: E402
import trading_date  # noqa: E402
import fix_returns_final_close_oneoff as base  # noqa: E402
import fix_maxgain_shadow as mgs  # noqa: E402

UTC = _dt.timezone.utc
ET = _dt.timezone(_dt.timedelta(hours=-5))
NOW = _dt.datetime(2026, 11, 5, 18, 0, tzinfo=UTC)          # Do 13:00 ET (Sitzung)
FINAL = trading_date.last_final_close_date(NOW)            # 04.11.
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


# ── Fake-OHLC-DataFrame ──────────────────────────────────────────────────────
class _TS:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Idx(list):
    @property
    def date(self): return [t.date() for t in self]


class _DF:
    def __init__(self, dates, high, low, close):
        self.index = _Idx(_TS(d) for d in dates)
        self.H, self.L, self.C = list(high), list(low), list(close)
    @property
    def empty(self): return len(self.index) == 0
    def __len__(self): return len(self.index)
    def __getitem__(self, k):
        if isinstance(k, list):
            keep = [i for i, b in enumerate(k) if b]
            return _DF([self.index[i].date() for i in keep], [self.H[i] for i in keep],
                       [self.L[i] for i in keep], [self.C[i] for i in keep])
        raise KeyError(k)
    @property
    def iloc(self):
        s = self

        class _I:
            def __getitem__(self, k):
                return _DF([t.date() for t in s.index][k], s.H[k], s.L[k], s.C[k])
        return _I()


def _spy_gain(w):
    return round((max(w.H) / min(w.L) - 1) * 100 + len(w) / 1000, 2)


def _spy_dd(w):
    return round(-(max(w.H) - min(w.L)) - len(w) / 1000, 2)


DATES = _days(_dt.date(2026, 10, 19), 14)                   # 19.10. … 05.11. (laufend)
HIGH = [10 + i * 0.3 for i in range(14)]
LOW = [9 + i * 0.25 for i in range(14)]
CLOSE = [9.5 + i * 0.28 for i in range(14)]
DF = _DF(DATES, HIGH, LOW, CLOSE)
CLOSES = list(zip(DATES, CLOSE))


@contextlib.contextmanager
def _patched_compute():
    orig = (bh._compute_max_gain_pct, bh._compute_max_drawdown)
    bh._compute_max_gain_pct, bh._compute_max_drawdown = _spy_gain, _spy_dd
    try:
        yield
    finally:
        bh._compute_max_gain_pct, bh._compute_max_drawdown = orig


def _production_rolling(entries, now_et):
    """Echte _append_backtest_entries (top10 leer) — nur der Rolling-Block wirkt."""
    store = {"h": [dict(e) for e in entries]}

    class _Yf:
        def download(self, *a, **k): return DF

    class _D(_dt.date):
        @classmethod
        def today(cls): return now_et.date()
    orig = (bh._load_backtest_history, bh._save_backtest_history, bh._prune_backtest_history,
            bh.yf, bh.date, bh.BACKTEST_ENABLED)
    try:
        bh._load_backtest_history = lambda: store["h"]
        bh._save_backtest_history = lambda h: store.__setitem__("h", h)
        bh._prune_backtest_history = lambda h: h
        bh.yf, bh.date, bh.BACKTEST_ENABLED = _Yf(), _D, True
        with contextlib.redirect_stdout(io.StringIO()):
            bh._append_backtest_entries([], "04.11.2026", compute_sub_scores_fn=lambda s: {},
                                        safe_float_fn=lambda v, d=None: v, now_et=now_et)
    finally:
        (bh._load_backtest_history, bh._save_backtest_history, bh._prune_backtest_history,
         bh.yf, bh.date, bh.BACKTEST_ENABLED) = orig
    return store["h"]


def _mg_entry(date, ticker="AAA"):
    return {"date": date, "ticker": ticker, "score": 80.0,
            "max_drawdown_pct": 0.0, "max_gain_pct": 0.0, "max_gain_pct_net": 0.0}


def test_01_03_maxgain_equivalence():
    now_et = NOW.astimezone(ET)
    with _patched_compute():
        prod = _production_rolling([_mg_entry(d) for d in ("22.10.2026", "26.10.2026", "29.10.2026")],
                                   now_et)
        ok, n = True, 0
        for e in prod:
            vals = mgs.recompute_maxgain(e, DF, trading_date.last_final_close_date(now_et))
            for f in mgs.MG_FIELDS:
                n += 1
                if vals[f][0] != e[f]:
                    ok = False
                    print(f"      Unterschied {e['date']} {f}")
        _check(f"01 Skript == echte _append_backtest_entries ({n} Felder)", ok)
        _check("01 Vergleich nicht trivial (Werte ≠ Startwert 0.0)",
               all(e["max_gain_pct"] != 0.0 for e in prod))
        w = bh._final_window(DF, _dt.date(2026, 10, 29), FINAL)
        _check("03 Fenster ohne laufenden Tag 05.11.", _dt.date(2026, 11, 5) not in w.index.date)


def _es_rec(date, ticker="AAA", **kw):
    r = {"date": date, "ticker": ticker, "schema_v": 1, "forward_3d": None,
         "forward_5d": None, "forward_10d": None}
    r.update(kw)
    return r


def _ki_fill_shadow(recs, closes, now):
    d = pathlib.Path(tempfile.mkdtemp())
    log = d / "exit_shadow_log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")

    class _C:
        def __init__(self, pairs):
            self.index = [_TS(x) for x, _ in pairs]
            self._v = [v for _, v in pairs]
        @property
        def iloc(self):
            v = self._v

            class _I:
                def __getitem__(self, i): return v[i]
            return _I()
        def __len__(self): return len(self._v)
        def dropna(self): return self

    class _CDF:
        def __contains__(self, k): return k == "Close"
        def __getitem__(self, k): return _C(closes)

    class _Yf:
        def download(self, *a, **k): return _CDF()
    orig = (exit_shadow.EXIT_SHADOW_LOG, ki_agent.yf)
    try:
        exit_shadow.EXIT_SHADOW_LOG, ki_agent.yf = str(log), _Yf()
        with contextlib.redirect_stdout(io.StringIO()):
            ki_agent.update_exit_shadow_forwards(now_utc=now)
    finally:
        exit_shadow.EXIT_SHADOW_LOG, ki_agent.yf = orig
    out = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l]
    shutil.rmtree(d)
    return out


def test_02_03_shadow_equivalence():
    recs = [_es_rec(d) for d in ("19.10.2026", "22.10.2026", "28.10.2026", "30.10.2026", "05.11.2026")]
    filled = _ki_fill_shadow(recs, CLOSES, NOW)
    ok = all(mgs.recompute_shadow(r, CLOSES, FINAL)[f][0] == r[f] for r in filled for f in mgs.ES_FIELDS)
    _check("02 Skript == ki_agent.update_exit_shadow_forwards", ok)
    _check("02 Vergleich enthält gefüllte UND leere Felder",
           any(r["forward_3d"] is not None for r in filled) and any(r["forward_10d"] is None for r in filled))
    v = mgs.recompute_shadow(_es_rec("02.11.2026"), CLOSES, FINAL)
    _check("03 Forward mit Zieltag = laufender Tag → null", v["forward_3d"][0] is None
           and v["forward_3d"][1] == "zieltag_fehlt_oder_nicht_final", str(v))


def test_04_rules():
    with _patched_compute():
        good = mgs.recompute_maxgain({"date": "22.10.2026"}, DF, FINAL)
        e = {"date": "22.10.2026", "ticker": "AAA", "max_gain_pct": good["max_gain_pct"][0],
             "max_drawdown_pct": good["max_drawdown_pct"][0], "x": 1}
        new, ch = mgs._apply(e, good, mgs.MG_FIELDS)
        _check("04 korrekt → unverändert", ch == [] and new == e)
        e2 = dict(e, max_gain_pct=77.77)
        new, ch = mgs._apply(e2, good, mgs.MG_FIELDS)
        _check("04 abweichend → neu", new["max_gain_pct"] == good["max_gain_pct"][0]
               and ch[0][3] == "neu_berechnet")
        v = mgs.recompute_maxgain({"date": "22.10.2026"}, None, FINAL)
        _check("04 ohne Kurse → null, nie 0",
               all(v[f] == (None, "ticker_ohne_kursdaten") for f in mgs.MG_FIELDS))
        v = mgs.recompute_maxgain({"date": "04.11.2026"}, DF, FINAL)    # nur 1 finale Zeile
        _check("04 < 2 Fensterzeilen → null (zu_wenig_daten), nicht 0.0",
               all(v[f] == (None, "zu_wenig_daten") for f in mgs.MG_FIELDS), str(v))
    v = mgs.recompute_shadow(_es_rec("19.10.2026"), None, FINAL)
    _check("04 Forward ohne Kurse → null", all(v[f][0] is None for f in mgs.ES_FIELDS))
    v = mgs.recompute_shadow(_es_rec("18.10.2026"), CLOSES, FINAL)
    _check("04 Signaltag fehlt → null", all(v[f] == (None, "signaltag_fehlt") for f in mgs.ES_FIELDS))


def _write(d: pathlib.Path):
    with _patched_compute():
        g = mgs.recompute_maxgain({"date": "22.10.2026"}, DF, FINAL)
    bt = [
        {"date": "22.10.2026", "ticker": "AAA", "score": 81.0, "max_gain_pct": 77.77,
         "max_drawdown_pct": g["max_drawdown_pct"][0], "max_gain_pct_net": 1.0, "notiz": "ä"},
        {"date": "26.10.2026", "ticker": "ZZZ", "score": 70.0, "max_gain_pct": 5.0,
         "max_drawdown_pct": -3.0},
        {"date": "22.10.2026", "ticker": "AAA", "source": "bootstrap", "max_gain_pct": 55.55},
        {"date": "23.10.2026", "ticker": "AAA", "score": 60.0, "max_gain_pct": None},
    ]
    ex = [{"date": "22.10.2026", "ticker": "AAA", "provenance": "forward", "score": 81.0,
           "max_gain_pct": 77.77, "max_drawdown_pct": g["max_drawdown_pct"][0], "exported_at": "x"},
          {"date": "26.10.2026", "ticker": "AAA", "provenance": "forward", "score": 75.0,
           "return_10d": 1.0, "exported_at": "y"}]
    sh = [_es_rec("19.10.2026", forward_3d=66.66, forward_5d=1.0, forward_10d=2.0, signal_price=1.0),
          _es_rec("02.11.2026", forward_3d=3.0),
          _es_rec("22.10.2026", ticker="ZZZ", forward_3d=4.0)]
    (d / base.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / base.EXPORT_FILE).write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                                              for r in ex), encoding="utf-8")
    (d / mgs.SHADOW_FILE).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sh),
                                     encoding="utf-8")


PRICES = ({"AAA": DF, "ZZZ": None}, {"AAA": CLOSES, "ZZZ": None})


def _run(mode, d, max_null=1000):
    buf = io.StringIO()
    with _patched_compute(), contextlib.redirect_stdout(buf):
        rc = mgs.run(mode, NOW, root=d, prices=PRICES, max_null=max_null)
    return rc, buf.getvalue()


def _snap(d):
    return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}


def test_05_08_files():
    d = pathlib.Path(tempfile.mkdtemp())
    _write(d)
    before = _snap(d)
    rc, log = _run("dry_run", d)
    _check("05 dry_run rc 0 + schreibt nichts", rc == 0 and _snap(d) == before, log[-300:])
    _check("11 Blindung: alte Werte nicht im Log", all(s not in log for s in ("77.77", "66.66", "55.55")))
    rc2, log2 = _run("dry_run", d)
    _check("11 Determinismus", log == log2)
    rc, log = _run("apply", d)
    _check("06 apply rc 0", rc == 0, log[-300:])
    arch = [json.loads(l) for l in (d / mgs.ARCHIVE_FILE).read_text(encoding="utf-8").splitlines()]
    keys = {"datei", "date", "ticker", "feld", "alt", "neu_oder_null", "grund"}
    _check("06 Archiv-Zeilen vollständig", arch and all(set(a) == keys for a in arch))
    n_changed = 0
    ok_rest = True
    for name, fields in ((base.BT_FILE, mgs.MG_FIELDS), (base.EXPORT_FILE, mgs.MG_FIELDS),
                         (mgs.SHADOW_FILE, mgs.ES_FIELDS)):
        if name == base.BT_FILE:
            o_l, n_l = json.loads(before[name]), json.loads((d / name).read_text(encoding="utf-8"))
        else:
            o_l = [json.loads(x) for x in before[name].decode().splitlines()]
            n_l = [json.loads(x) for x in (d / name).read_text(encoding="utf-8").splitlines()]
        if len(o_l) != len(n_l):
            ok_rest = False
        for o, n in zip(o_l, n_l):
            if list(o) != list(n) or any(o[k] != n[k] for k in o if k not in fields):
                ok_rest = False
            n_changed += sum(1 for k in o if k in fields and o[k] != n[k])
    _check("06 Archiv-Zeilen = geänderte Felder", len(arch) == n_changed, f"{len(arch)} vs {n_changed}")
    _check("06 andere Felder, Reihenfolge, Zeilenzahl gleich; kein Key angelegt", ok_rest)
    bt_new = json.loads((d / base.BT_FILE).read_text(encoding="utf-8"))
    _check("06 Bootstrap unberührt, leeres Feld bleibt leer",
           bt_new[2]["max_gain_pct"] == 55.55 and bt_new[3]["max_gain_pct"] is None)
    _check("04 ZZZ ohne Kurse → null", bt_new[1]["max_gain_pct"] is None and bt_new[1]["max_drawdown_pct"] is None)
    sh_new = [json.loads(x) for x in (d / mgs.SHADOW_FILE).read_text(encoding="utf-8").splitlines()]
    _check("06 Forward korrigiert / null wenn Zieltag nicht final",
           sh_new[0]["forward_3d"] == mgs.recompute_shadow(sh_new[0], CLOSES, FINAL)["forward_3d"][0]
           and sh_new[1]["forward_3d"] is None and sh_new[2]["forward_3d"] is None)
    _check("06 unveränderte Export-Zeile byte-gleich",
           (d / base.EXPORT_FILE).read_text(encoding="utf-8").splitlines()[1]
           == before[base.EXPORT_FILE].decode().splitlines()[1])
    after = _snap(d)
    _run("apply", d)
    _check("07 apply idempotent", _snap(d) == after)
    with contextlib.redirect_stdout(io.StringIO()):
        mgs.restore(root=d, apply=True)
    s = _snap(d)
    _check("07 restore byte-genau (alle drei Dateien)",
           all(s[n] == before[n] for n in (base.BT_FILE, base.EXPORT_FILE, mgs.SHADOW_FILE)))
    shutil.rmtree(d)

    d = pathlib.Path(tempfile.mkdtemp())
    _write(d)
    before = _snap(d)
    rc, log = _run("apply", d, max_null=None)
    _check("08 max_null fehlt → Abbruch", rc == 2 and _snap(d) == before)
    rc, log = _run("apply", d, max_null=0)
    _check("08 max_null überschritten → Abbruch", rc == 2 and _snap(d) == before)
    orig = base._sha
    calls = {"n": 0}

    def _sha2(p):
        calls["n"] += 1
        return orig(p) + ("x" if calls["n"] > 3 else "")
    base._sha = _sha2
    try:
        rc, log = _run("apply", d)
    finally:
        base._sha = orig
    _check("08 Datei zwischendurch geändert → Abbruch", rc == 2 and _snap(d) == before
           and "seit dem Lesen" in log, log[-200:])
    shutil.rmtree(d)


def test_09_10_cli_workflow():
    called = {}
    orig_run, orig_mgs = base.run, mgs.run
    base.run = lambda *a, **k: called.setdefault("returns", True) and 0
    mgs.run = lambda *a, **k: called.setdefault("maxgain", True) and 0
    try:
        base.main(["--mode", "dry_run"])
        _check("09 ohne --target → Renditen-Pfad (#648)", called == {"returns": True}, str(called))
        called.clear()
        base.main(["--mode", "dry_run", "--target", "maxgain_shadow"])
        _check("09 --target maxgain_shadow → neuer Pfad", called == {"maxgain": True}, str(called))
    finally:
        base.run, mgs.run = orig_run, orig_mgs
    import yaml
    src = (ROOT / ".github/workflows/fix_returns_oneoff.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(src)
    on = wf.get(True) or wf.get("on")
    t = on["workflow_dispatch"]["inputs"]["target"]
    _check("10 Input target, Default returns", t["default"] == "returns"
           and t["options"] == ["returns", "maxgain_shadow"])
    _check("10 Exit-Shadow-Datei im Blob-Vergleich + Commit",
           "origin/main:exit_shadow_log.jsonl" in src and "git add backtest_history.json "
           "matured_backtest_export.jsonl exit_shadow_log.jsonl" in src)
    _check("10 beide Archive im Commit", "maxgain_shadow_corrections_archive_2026-11.jsonl" in src
           and "return_corrections_archive_2026-11.jsonl" in src)
    _check("10 target an dry_run und apply durchgereicht", src.count('--target "$TARGET"') == 2)


def main() -> int:
    for t in (test_01_03_maxgain_equivalence, test_02_03_shadow_equivalence, test_04_rules,
              test_05_08_files, test_09_10_cli_workflow):
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
    print("Alle fix_maxgain_shadow-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
