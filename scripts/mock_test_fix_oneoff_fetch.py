"""Mock-Test: Abruf-Schutz des Korrektur-Skripts (Easy-Entscheid 04.11.2026).

Einzel-Abruf je Ticker (``fix_returns_final_close_oneoff.fetch_frames``) mit
Klassifizierung nach yfinance-Fehlertyp. Fake-yfinance, kein Netz.

  A  Klassifizierung: ok · YFTzMissingError/YFPricesMissingError → „leer“ ·
     YFRateLimitError → fehler:rate_limit · andere Exception → fehler ·
     leer ohne Meldung → fehler; hide_exceptions wird ausgeschaltet
  B  returns: Rate-Limit bei einem Ticker → rc 2, „Abruf unvollständig“, nichts
     geschrieben, kein null
  C  maxgain_shadow: dasselbe
  D  returns: ausdrücklich leerer Ticker → null erlaubt (dry_run läuft durch)
  E  Lücken-Ticker: Handelsaussetzung (Leerzeilen im Sammel-Index) und später
     Börsengang → Fenster wie Produktion bei Einzel-Download
  F  viele Ticker: jeder Rahmen hat seine eigenen Handelstage
  G  Grund je Ticker im Log, keine Werte
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import math
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

for _n in ("pandas", "requests"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
if "yfinance" not in sys.modules:
    _y = types.ModuleType("yfinance")
    _y.download = lambda *a, **k: None
    _y.Ticker = lambda *a, **k: None
    sys.modules["yfinance"] = _y

import backtest_history as bh  # noqa: E402
import trading_date  # noqa: E402
import fix_returns_final_close_oneoff as base  # noqa: E402
import fix_maxgain_shadow as mgs  # noqa: E402

UTC = _dt.timezone.utc
NOW = _dt.datetime(2026, 11, 5, 18, 0, tzinfo=UTC)
FINAL = trading_date.last_final_close_date(NOW)
NAN = float("nan")
_fails: list[str] = []


def _check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _days(start, n, skip=()):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


# ── Fake-DataFrame (Close/High/Low) ──────────────────────────────────────────
class _TS:
    def __init__(self, d): self._d = d
    def date(self): return self._d


class _Idx(list):
    @property
    def date(self): return [t.date() for t in self]


class _Ser:
    def __init__(self, idx, vals): self.index, self.values = idx, list(vals)
    def dropna(self):
        keep = [i for i, v in enumerate(self.values) if not (v is None or v != v)]
        return _Ser(_Idx(self.index[i] for i in keep), [self.values[i] for i in keep])


class _DF:
    def __init__(self, dates, close, high=None, low=None):
        self.index = _Idx(_TS(d) for d in dates)
        self.C = list(close)
        self.H = list(high if high is not None else close)
        self.L = list(low if low is not None else close)
    @property
    def empty(self): return len(self.index) == 0
    def __len__(self): return len(self.index)
    def __getitem__(self, k):
        if k == "Close":
            return _Ser(self.index, self.C)
        if isinstance(k, list):
            keep = [i for i, b in enumerate(k) if b]
            return _DF([self.index[i].date() for i in keep], [self.C[i] for i in keep],
                       [self.H[i] for i in keep], [self.L[i] for i in keep])
        raise KeyError(k)
    def dropna(self, subset=None, how="any"):
        def _nan(v): return v is None or v != v
        return self[[not (_nan(h) and _nan(l)) for h, l in zip(self.H, self.L)]]
    @property
    def iloc(self):
        s = self

        class _I:
            def __getitem__(self, k):
                return _DF([t.date() for t in s.index][k], s.C[k], s.H[k], s.L[k])
        return _I()


# ── Fake-yfinance ────────────────────────────────────────────────────────────
def _exc(name):
    return type(name, (Exception,), {})


class _FakeYf(types.ModuleType):
    def __init__(self, behaviour):
        super().__init__("yfinance")
        self.behaviour = behaviour
        self.config = types.SimpleNamespace(debug=types.SimpleNamespace(hide_exceptions=True))
        self.calls = []
        self.dl_calls = []
        self.dl = {}
        self.dl_err = {}

    def download(self, tickers, **kw):
        t = tickers[0]
        self.dl_calls.append((t, self.config.debug.hide_exceptions))
        b = self.dl.get(t, "empty")
        if isinstance(b, _DF):
            return b
        return _DF([], [])

    def Ticker(self, t):  # noqa: N802
        yf = self

        class _T:
            def history(self, **kw):
                if yf.config.debug.hide_exceptions:           # Sammelweg
                    yf.dl_calls.append((t, True))
                    b = yf.dl.get(t, "empty")
                    le = yf.dl_err.get(t)
                    self._price_history = types.SimpleNamespace(_last_error=le)
                    return b if isinstance(b, _DF) else _DF([], [])
                yf.calls.append((t, kw.get("auto_adjust")))
                b = yf.behaviour.get(t, "ok")
                if isinstance(b, list):           # Folge je Aufruf
                    b = b.pop(0) if len(b) > 1 else b[0]
                if isinstance(b, _DF):
                    return b
                if b == "empty":
                    return _DF([], [])
                if b == "ok":
                    ds = _days(_dt.date(2026, 10, 1), 30)
                    return _DF(ds, [10.0 + i * 0.1 for i in range(30)])
                raise _exc(b)("Too Many Requests" if b == "YFRateLimitError" else b)
        return _T()


@contextlib.contextmanager
def _yf(behaviour, dl=None, dl_err=None):
    fake = _FakeYf(behaviour)
    fake.dl = dl or {}
    fake.dl_err = dl_err or {}
    base.RETRY_PAUSE_S = 0.0
    orig = sys.modules.get("yfinance")
    sys.modules["yfinance"] = fake
    try:
        yield fake
    finally:
        sys.modules["yfinance"] = orig


def test_a_classify():
    beh = {"OK": "ok", "TZ": "YFTzMissingError", "PM": "YFPricesMissingError",
           "RL": "YFRateLimitError", "NET": "ConnectionError", "EMP": "empty"}
    with _yf(beh) as fake:
        frames, st = base.fetch_frames(list(beh), _dt.date(2026, 10, 1), NOW)
    _check("A ok", st["OK"] == "ok" and frames["OK"] is not None)
    _check("A Zeitzone fehlt → leer", st["TZ"] == "leer:YFTzMissingError" and frames["TZ"] is None)
    _check("A keine Kurse → leer", st["PM"] == "leer:YFPricesMissingError")
    _check("A Rate-Limit → fehler:rate_limit (ohne Wiederholung)",
           st["RL"].startswith("fehler:rate_limit") and [t for t, _ in fake.calls].count("RL") == 1)
    _check("A Netzwerkfehler → fehler (nach Wiederholung + Sammelweg)",
           st["NET"].startswith("fehler:ConnectionError") and "Wiederholung" in st["NET"], st["NET"])
    _check("A leer ohne Meldung → fehler", st["EMP"].startswith("fehler:leer_ohne_meldung"))
    _check("A hide_exceptions nach dem Lauf wieder aus", fake.config.debug.hide_exceptions is False)
    _check("A Einzel-Abruf je Ticker mit auto_adjust=True",
           set(t for t, _ in fake.calls) == set(beh) and all(a is True for _, a in fake.calls))


def test_a2_message_classification():
    PM = _exc("YFPricesMissingError")
    c = base.classify_fetch_error
    _check("A2 keine Kurszeilen im Zeitraum (ohne Yahoo-Fehler) → leer",
           c(PM("$X: possibly delisted; no price data found  (1d 2026-04-26 -> 2026-11-05)"))
           == "leer:YFPricesMissingError")
    _check('A2 Yahoo error = "No data found, symbol may be delisted" → leer',
           c(PM('$X: possibly delisted; no price data found (Yahoo error = "No data found, '
                'symbol may be delisted")')) == "leer:YFPricesMissingError")
    _check('A2 Yahoo error = "Not Found" → leer',
           c(PM('$X: possibly delisted; no price data found (Yahoo error = "Not Found")'))
           == "leer:YFPricesMissingError")
    _check('A2 Yahoo error = "Invalid Crumb" → Fehler (Sperre, nicht leer)',
           c(PM('$X: possibly delisted; no price data found (Yahoo error = "Invalid Crumb")'))
           == "fehler:YFPricesMissingError_yahoo_error")
    _check("A2 Yahoo status_code → Fehler",
           c(PM("$X: possibly delisted; no price data found (1d a -> b)(Yahoo status_code = 401)"))
           == "fehler:YFPricesMissingError_status_code")
    _check("A2 Rate-Limit → fehler:rate_limit", c(_exc("YFRateLimitError")("x")) == "fehler:rate_limit")


class _HTTPError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.response = types.SimpleNamespace(status_code=code)


def test_r_retry():
    ok_df = _DF(_days(_dt.date(2026, 10, 1), 10), [1.0] * 10)
    pauses = []
    beh = {"YYGH": ["HTTPErr", ok_df]}
    fake = _FakeYf(beh)
    fake.dl = {}
    orig = sys.modules.get("yfinance")
    sys.modules["yfinance"] = fake
    fake.Ticker_orig = fake.Ticker

    def _ticker(t):
        tk = fake.Ticker_orig(t)
        h = tk.history

        def history(**kw):
            b = beh[t][0] if isinstance(beh.get(t), list) else None
            if b == "HTTPErr":
                beh[t].pop(0)
                fake.calls.append((t, kw.get("auto_adjust")))
                raise _HTTPError(404, "HTTP Error 404: Not Found for url https://x/y?crumb=SECRET")
            return h(**kw)
        tk.history = history
        return tk
    fake.Ticker = _ticker
    try:
        fr, st = base.fetch_frames(["YYGH"], _dt.date(2026, 10, 1), NOW, sleep=pauses.append,
                                   retry_pause=5.0)
    finally:
        sys.modules["yfinance"] = orig
    _check("R Fehler → Pause → Wiederholung → Erfolg", st["YYGH"] == "ok:wiederholt"
           and pauses == [5.0] and fr["YYGH"] is ok_df, f"{st} {pauses}")
    with _yf({"YYGH": "HTTPError"}, dl={"YYGH": ok_df}) as fk:
        fr, st = base.fetch_frames(["YYGH"], _dt.date(2026, 10, 1), NOW)
    _check("R Fehler → Wiederholung Fehler → Sammelweg mit Daten → ok:sammelweg",
           st["YYGH"] == "ok:sammelweg" and fr["YYGH"] is not None, str(st))
    _check("R Sammelweg mit hide_exceptions=True, danach wieder False",
           fk.dl_calls == [("YYGH", True)] and fk.config.debug.hide_exceptions is False, str(fk.dl_calls))
    with _yf({"YYGH": "HTTPError"}, dl={"YYGH": ok_df},
             dl_err={"YYGH": "auto_adjust failed"}) as fk:
        fr, st = base.fetch_frames(["YYGH"], _dt.date(2026, 10, 1), NOW)
    _check("R Sammelweg mit verschlucktem yfinance-Fehler (z. B. auto_adjust) → nicht übernommen",
           st["YYGH"].startswith("fehler:") and fr["YYGH"] is None, st["YYGH"])
    with _yf({"YYGH": "HTTPError"}) as fk:
        fr, st = base.fetch_frames(["YYGH"], _dt.date(2026, 10, 1), NOW)
    _check("R Fehler → Fehler → Sammelweg leer → bleibt Fehler (nie null)",
           st["YYGH"].startswith("fehler:HTTPError") and "Sammelweg: keine Daten" in st["YYGH"]
           and fr["YYGH"] is None, st["YYGH"])
    with _yf({"RL": "YFRateLimitError"}) as fk:
        fr, st = base.fetch_frames(["RL"], _dt.date(2026, 10, 1), NOW)
    _check("R Rate-Limit: keine Wiederholung, kein Sammelweg", st["RL"].startswith("fehler:rate_limit")
           and len(fk.calls) == 1 and fk.dl_calls == [])
    e = _HTTPError(404, "HTTP Error 404: Not Found for url https://q/v8/chart/YYGH?crumb=SECRET&x=1")
    det = base.error_detail(e)
    _check("R Fehlertext mit Statuscode, ohne URL-Parameter",
           det.startswith("HTTP 404: ") and "SECRET" not in det and "crumb" not in det, det)


def test_s_skip():
    d = pathlib.Path(tempfile.mkdtemp())
    _returns_files(d, ("AAA", "YYGH"))
    before = _snap(d)
    buf = io.StringIO()
    with _yf({"YYGH": "HTTPError"}), contextlib.redirect_stdout(buf):
        rc_noskip = base.run("dry_run", NOW, root=d)
        rc = base.run("apply", NOW, root=d, max_null=1000, skip=frozenset({"YYGH"}))
    log = buf.getvalue()
    _check("S ohne Überspringen-Liste: Abbruch", rc_noskip == 2)
    bt = json.loads((d / base.BT_FILE).read_text(encoding="utf-8"))
    yy = [r for r in bt if r["ticker"] == "YYGH"][0]
    old = [r for r in json.loads(before[base.BT_FILE]) if r["ticker"] == "YYGH"][0]
    _check("S mit Liste: apply läuft, YYGH-Felder UNVERÄNDERT", rc == 0 and yy == old, log[-300:])
    arch = (d / base.ARCHIVE_FILE).read_text(encoding="utf-8") if (d / base.ARCHIVE_FILE).exists() else ""
    _check("S Archiv ohne YYGH", '"YYGH"' not in arch)
    _check("S Liste im Log genannt", "Übersprungen (Easy-Entscheid" in log and "YYGH" in log)
    shutil.rmtree(d)
    d = pathlib.Path(tempfile.mkdtemp())
    bt = [{"date": "05.10.2026", "ticker": t, "score": 80.0, "max_gain_pct": 77.77,
           "max_drawdown_pct": -1.0} for t in ("AAA", "YYGH")]
    (d / base.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / base.EXPORT_FILE).write_text("", encoding="utf-8")
    (d / mgs.SHADOW_FILE).write_text(json.dumps({"date": "05.10.2026", "ticker": "YYGH",
                                                  "forward_3d": 1.0}) + "\n", encoding="utf-8")
    b2 = _snap(d)
    with _yf({"YYGH": "HTTPError"}), contextlib.redirect_stdout(io.StringIO()):
        rc = mgs.run("dry_run", NOW, root=d, skip=frozenset({"YYGH"}))
    _check("S maxgain_shadow mit Liste: läuft, nichts geschrieben", rc == 0 and _snap(d) == b2)
    _check("S Ungültige Liste → ValueError", _raises(lambda: base.parse_skip("YY GH; rm")))
    _check("S unbekannter Ticker in der Liste → Fehlertext",
           "unbekannte Ticker ['ZZQQ']" in (base.check_skip(frozenset({"ZZQQ"}), [{"ticker": "AAA"}]) or ""))
    _check("S Liste > 3 → Fehlertext",
           "zu lang" in (base.check_skip(frozenset({"A", "B", "C", "D"}), [{"ticker": "A"}]) or ""))
    with _yf({}), contextlib.redirect_stdout(io.StringIO()):
        rc = mgs.run("dry_run", NOW, root=d, skip=frozenset({"ZZQQ"}))
    _check("S Tippfehler in der Liste → Abbruch rc 2, nichts geschrieben", rc == 2 and _snap(d) == b2)
    _check("S Liste geparst (Komma/Leerzeichen, Großschrift)",
           base.parse_skip("yygh, ABC  def") == frozenset({"YYGH", "ABC", "DEF"}))
    shutil.rmtree(d)


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def _returns_files(d, tickers=("AAA", "GETY")):
    bt = [{"date": "05.10.2026", "ticker": t, "score": 80.0, "return_3d": 77.77} for t in tickers]
    (d / base.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / base.EXPORT_FILE).write_text(json.dumps({"date": "06.10.2026", "ticker": "AAA",
                                                   "provenance": "forward", "return_3d": 1.0},
                                                  sort_keys=True) + "\n", encoding="utf-8")


def _snap(d):
    return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}


def test_b_returns_ratelimit():
    d = pathlib.Path(tempfile.mkdtemp())
    _returns_files(d)
    before = _snap(d)
    buf = io.StringIO()
    with _yf({"GETY": "YFRateLimitError"}), contextlib.redirect_stdout(buf):
        rc_dry = base.run("dry_run", NOW, root=d)
        rc_app = base.run("apply", NOW, root=d, max_null=1000)
    log = buf.getvalue()
    _check("B returns: Rate-Limit → dry_run rc 2", rc_dry == 2, log[-300:])
    _check("B returns: Rate-Limit → apply rc 2, nichts geschrieben", rc_app == 2 and _snap(d) == before)
    _check("B Meldung „Abruf unvollständig — nicht verwertbar“ + Grund je Ticker",
           "Abruf unvollständig — nicht verwertbar" in log and "GETY: fehler:rate_limit" in log)
    _check("G keine alten Werte im Log", "77.77" not in log)
    shutil.rmtree(d)


def test_c_maxgain_ratelimit():
    d = pathlib.Path(tempfile.mkdtemp())
    bt = [{"date": "05.10.2026", "ticker": t, "score": 80.0, "max_gain_pct": 77.77,
           "max_drawdown_pct": -1.0} for t in ("AAA", "GETY")]
    (d / base.BT_FILE).write_text(json.dumps(bt, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / base.EXPORT_FILE).write_text("", encoding="utf-8")
    (d / mgs.SHADOW_FILE).write_text(json.dumps({"date": "05.10.2026", "ticker": "AAA",
                                                  "forward_3d": 1.0}) + "\n", encoding="utf-8")
    before = _snap(d)
    buf = io.StringIO()
    with _yf({"GETY": "YFRateLimitError"}), contextlib.redirect_stdout(buf):
        rc_dry = mgs.run("dry_run", NOW, root=d)
        rc_app = mgs.run("apply", NOW, root=d, max_null=1000)
    log = buf.getvalue()
    _check("C maxgain_shadow: Rate-Limit → rc 2 (dry_run und apply), nichts geschrieben",
           rc_dry == 2 and rc_app == 2 and _snap(d) == before, log[-300:])
    _check("C Meldung + Grund je Ticker", "Abruf unvollständig" in log and "GETY: fehler:rate_limit" in log)
    shutil.rmtree(d)


def test_d_explicit_empty():
    d = pathlib.Path(tempfile.mkdtemp())
    _returns_files(d, ("AAA", "BNRG"))
    buf = io.StringIO()
    with _yf({"BNRG": "YFPricesMissingError"}), contextlib.redirect_stdout(buf):
        rc = base.run("dry_run", NOW, root=d)
    log = buf.getvalue()
    _check("D ausdrücklich leer → dry_run läuft (rc 0), Ticker als „ohne Kursdaten“",
           rc == 0 and "BNRG: leer:YFPricesMissingError" in log and "ohne Kursdaten 1" in log, log[-400:])
    shutil.rmtree(d)


def _spy_gain(w):
    return round(max(w.H) - min(w.L) + len(w) / 1000, 4)


def _spy_dd(w):
    return round(min(w.L) - max(w.H) - len(w) / 1000, 4)


def test_e_gap_and_ipo():
    own = _days(_dt.date(2026, 10, 19), 14, skip={_dt.date(2026, 10, 23)})   # Aussetzung 23.10.
    union = sorted(set(own) | {_dt.date(2026, 10, 23)})
    hi = {d: 10 + i * 0.3 for i, d in enumerate(own)}
    lo = {d: 9 + i * 0.2 for i, d in enumerate(own)}
    prod_df = _DF(own, [1.0] * len(own), [hi[d] for d in own], [lo[d] for d in own])
    batch_df = _DF(union, [1.0] * len(union), [hi.get(d, NAN) for d in union],
                   [lo.get(d, NAN) for d in union])
    orig = (bh._compute_max_gain_pct, bh._compute_max_drawdown)
    bh._compute_max_gain_pct, bh._compute_max_drawdown = _spy_gain, _spy_dd
    try:
        e = {"date": "21.10.2026"}
        prod = (_spy_gain(bh._final_window(prod_df, _dt.date(2026, 10, 21), FINAL)),
                _spy_dd(bh._final_window(prod_df, _dt.date(2026, 10, 21), FINAL)))
        scr = mgs.recompute_maxgain(e, mgs.own_days(batch_df), FINAL)
        _check("E Aussetzung im Fenster: Skript (Sammel-Index) == Produktion (Einzel)",
               (scr["max_gain_pct"][0], scr["max_drawdown_pct"][0]) == prod, f"{scr} vs {prod}")
        old = mgs.recompute_maxgain(e, batch_df, FINAL)
        _check("E Gegenprobe: ohne own_days weicht es ab (Leerzeile belegt Fensterplatz)",
               (old["max_gain_pct"][0], old["max_drawdown_pct"][0]) != prod)
        ipo = _days(_dt.date(2026, 10, 26), 8)
        ipo_df = _DF(ipo, [1.0] * 8, [5 + i for i in range(8)], [4 + i for i in range(8)])
        e2 = {"date": "21.10.2026"}                                   # Entry vor dem 1. Kurs
        p2 = _spy_gain(bh._final_window(ipo_df, _dt.date(2026, 10, 21), FINAL))
        s2 = mgs.recompute_maxgain(e2, mgs.own_days(ipo_df), FINAL)["max_gain_pct"][0]
        _check("E später Börsengang: Fenster wie Produktion", s2 == p2, f"{s2} vs {p2}")
    finally:
        bh._compute_max_gain_pct, bh._compute_max_drawdown = orig


def test_f_many_tickers():
    beh = {f"T{i}": _DF(_days(_dt.date(2026, 10, 1), 10 + i % 5, skip={_dt.date(2026, 10, 2 + i % 3)}),
                        [1.0] * (10 + i % 5)) for i in range(50)}
    with _yf(beh):
        frames, st = base.fetch_frames(list(beh), _dt.date(2026, 10, 1), NOW, workers=8)
    _check("F 50 Ticker: alle ok", all(v == "ok" for v in st.values()))
    _check("F jeder Rahmen mit eigenen Handelstagen (kein Sammel-Index)",
           all(list(frames[t].index.date) == list(beh[t].index.date) for t in beh))


def main() -> int:
    for t in (test_a_classify, test_a2_message_classification, test_r_retry, test_s_skip,
              test_b_returns_ratelimit, test_c_maxgain_ratelimit,
              test_d_explicit_empty, test_e_gap_and_ipo, test_f_many_tickers):
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
    print("Alle fix_oneoff_fetch-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
