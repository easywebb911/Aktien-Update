"""Mock-Test: Kursverlauf ab Einstieg (scripts/outcome_path_update.py) und
Freeze „Paper C handelbar“ (Easy-Auftrag 12.11.2026). Ohne Netz, synthetische
Kurse — keine echten Ergebnisdaten werden gelesen oder ausgewertet.

Geprüft:
  1. Zielfeld: max(High Tag 1–10) / Close D − 1; Tag D zählt NICHT (großes
     Hoch/Tief an D ändert nichts); Drawdown aus Low Tag 1–10; Netto über
     apply_round_trip_haircut.
  2. Gap über das Ziel (Eröffnung + Hoch an Tag 1 ≥ +30 %) zählt als Treffer.
  3. Fehlender Handelstag / Halbzeile / leerer Ticker / Kalender-Abweichung →
     Kennzahlen null + Grund (unbekannt ≠ 0).
  4. Split im Fenster: angepasste Reihe → Kennzahl unverändert, nur Kennzeichen.
  5. Reife: Tag 10 nicht final → keine Zeile; Retry-Fenster vor null + Grund.
  6. Append-only: bestehende Bytes unverändert, kein Doppel-Schreiben.
  7. Reihenfolge-Sicherung: Einstiege ≥ 24.10.2026 nur mit Freeze-Block.
  8. Determinismus: gleiche Kurse (beliebige Zeilen-Reihenfolge) → gleiche Werte.
  9. Rate-Limit: kein Retry, offene Zeilen bleiben offen.
 10. Blindheit: Log/State enthalten keine Kennzahl; Export wird nie geschrieben.
 11. Freeze-Block: vorhanden, MD5-Pin, Überschrift = config.
 12. Digest-Zeile: drei Zustände.
 13. Endgültiger Kurs (12.11.2026): Lauf am Abend von Tag 10 (16:30/18:53/
     20:30 ET) schreibt nichts, Folgetag 06:59 ET nichts, 07:05 ET schreibt;
     Gegenprobe alte Grenze (16:20 ET) hätte geschrieben; Digest meldet
     „wartet“ nicht als kaputt/überfällig; Determinismus über UTC-Mitternacht.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import tempfile
import types
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)
for _m in ("yfinance", "bs4", "deep_translator"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import config  # noqa: E402
import health_check as hc  # noqa: E402
import outcome_path_update as op  # noqa: E402
from backtest_history import apply_round_trip_haircut  # noqa: E402

# 13.11.2026: neu gepinnt nach zwei datierten Protokolleinträgen (Auslöser 500,
# Zielfeld nicht vom max_gain-Fehler betroffen) — vorher 6d7e3d02…
FREEZE_MD5 = "2cb8a9454cc039f75b81a4a5166b8634"  # 12.11.2026 abends: Protokolleintrag Export-Korrektur
_fails: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        _fails.append(name)


D = date(2026, 11, 2)                    # Montag
WIN = op.expected_window(D)              # D + 10 Handelstage


def bars(close_d=10.0, highs=None, lows=None, d_high=None, d_low=None, skip=None,
         half=None, split_at=None):
    highs = highs or [10.5] * 10
    lows = lows or [9.5] * 10
    out = []
    for i, d in enumerate(WIN):
        if skip is not None and i == skip:
            continue
        if i == 0:
            r = {"d": d, "o": 9.0, "h": d_high or 10.2, "l": d_low or 8.9, "c": close_d}
        else:
            r = {"d": d, "o": 10.0, "h": highs[i - 1], "l": lows[i - 1], "c": 10.0}
        r["div"], r["split"] = 0.0, (0.1 if split_at == i else 0.0)
        if half is not None and i == half:
            r["h"] = float("nan")
        out.append(r)
    return out


def test_window():
    check("Fenster: D + 10 Handelstage", len(WIN) == 11 and WIN[0] == D)
    check("Fenster: kein Wochenende", all(d.weekday() < 5 for d in WIN))
    # 26.11.2026 Thanksgiving: Fenster ab 20.11. überspringt ihn
    w = op.expected_window(date(2026, 11, 20))
    check("Fenster: Feiertag übersprungen", date(2026, 11, 26) not in w and len(w) == 11)


def test_core():
    r = op.build_record("AAA", D, bars(highs=[10.5] * 9 + [13.2]), fetched_utc="x")
    check("Zielfeld = max High 1–10 / Close D − 1", r["max_gain_from_entry_pct"] == 32.0, r)
    check("Drawdown = min Low 1–10 / Close D − 1", r["max_drawdown_from_entry_pct"] == -5.0, r)
    check("Netto = apply_round_trip_haircut",
          r["max_gain_from_entry_pct_net"] == round(apply_round_trip_haircut(32.0), 2))
    check("kein Grund", r["grund"] is None and r["close_d"] == 10.0)
    r2 = op.build_record("AAA", D, bars(d_high=20.0, d_low=5.0), fetched_utc="x")
    check("Tag D zählt nicht (Hoch 20 / Tief 5 an D)",
          r2["max_gain_from_entry_pct"] == 5.0 and r2["max_drawdown_from_entry_pct"] == -5.0, r2)
    gap = bars(highs=[13.6] + [10.5] * 9)
    gap[1]["o"] = 13.4
    r3 = op.build_record("AAA", D, gap, fetched_utc="x")
    check("Gap über das Ziel → Treffer (Hoch des Gap-Tags)",
          r3["max_gain_from_entry_pct"] == 36.0 and r3["max_gain_from_entry_pct"] >= 30.0)


def test_unknown():
    r = op.build_record("AAA", D, bars(skip=4), fetched_utc="x")
    check("fehlender Tag → null + Grund",
          r["max_gain_from_entry_pct"] is None and r["grund"] == "fehlender_tag"
          and r["grund_tag"] == WIN[4].isoformat(), r)
    r = op.build_record("AAA", D, bars(half=7), fetched_utc="x")
    check("Halbzeile → null + Grund", r["max_gain_from_entry_pct"] is None
          and r["grund"] == "halbzeile", r)
    r = op.build_record("AAA", D, [], fetched_utc="x")
    check("leerer Ticker → null + Grund", r["grund"] == "ticker_ohne_kursdaten"
          and r["max_drawdown_from_entry_pct"] is None)
    b = bars()
    b.append({"d": date(2026, 11, 7), "o": 10, "h": 50, "l": 1, "c": 10, "div": 0, "split": 0})
    r = op.build_record("AAA", D, b, fetched_utc="x")
    check("Handelstag außerhalb des Kalenders → null + Grund",
          r["grund"] == "kalender_abweichung" and r["max_gain_from_entry_pct"] is None, r)
    r = op.build_record("AAA", D, bars(close_d=0.0), fetched_utc="x")
    check("Close D = 0 → null", r["max_gain_from_entry_pct"] is None and r["grund"] == "halbzeile")


def test_split():
    r = op.build_record("AAA", D, bars(highs=[10.5] * 9 + [13.2], split_at=5), fetched_utc="x")
    check("Split im Fenster: nur Kennzeichen, Kennzahl aus angepasster Reihe",
          r["split_im_fenster"] is True and r["max_gain_from_entry_pct"] == 32.0, r)
    b = bars()
    b[3]["div"] = 0.12
    check("Dividende im Fenster gekennzeichnet",
          op.build_record("AAA", D, b, fetched_utc="x")["dividende_im_fenster"] is True)


def test_determinism():
    a = op.build_record("AAA", D, bars(highs=[11, 12, 10, 14, 9, 10, 10, 10, 10, 10]),
                        fetched_utc="x")
    rows = bars(highs=[11, 12, 10, 14, 9, 10, 10, 10, 10, 10])
    rows.reverse()
    b = op.build_record("AAA", D, rows, fetched_utc="x")
    check("Determinismus: Reihenfolge der Tageszeilen egal", a == b)


def _write_inputs(tmp: pathlib.Path, rows):
    (tmp / "bh.json").write_text(json.dumps(rows), encoding="utf-8")
    (tmp / "ex.jsonl").write_text("", encoding="utf-8")


def test_run_flow():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        ho_freeze = tmp / "ho_ok.md"
        ho_freeze.write_text("x\n" + config.OUTCOME_PATH_FREEZE_HEADING + "\n", encoding="utf-8")
        ho_none = tmp / "ho_no.md"
        ho_none.write_text("nichts\n", encoding="utf-8")
        old = date(2026, 10, 1)            # vor Replikationsfenster
        new = D                             # im Replikationsfenster
        young = date(2026, 11, 20)          # Tag 10 noch nicht final
        _write_inputs(tmp, [{"ticker": "OLD", "date": old.strftime("%d.%m.%Y")},
                            {"ticker": "NEW", "date": new.strftime("%d.%m.%Y")},
                            {"ticker": "YNG", "date": young.strftime("%d.%m.%Y")},
                            {"ticker": "BST", "date": "01.08.2026", "bootstrap": True}])
        calls = []

        def fetch(t, start, end_excl):
            calls.append(t)
            base = old if t == "OLD" else new
            w = op.expected_window(base)
            return [{"d": d, "o": 10, "h": 11, "l": 9, "c": 10, "div": 0, "split": 0} for d in w]

        now = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
        logs = []
        out, st = tmp / "op.jsonl", tmp / "st.json"
        kw = dict(now_utc=now, fetch_fn=fetch, out_path=out, state_path=st,
                  backtest_path=tmp / "bh.json", export_path=tmp / "ex.jsonl",
                  log=logs.append)
        s1 = op.run(handover_path=ho_none, **kw)
        check("ohne Freeze: Zeile ≥ 24.10. gesperrt, alte geschrieben",
              s1["geschrieben"] == 1 and s1["gesperrt_ohne_freeze"] == 1, s1)
        check("nicht reif (Tag 10 > final) → nicht geschrieben", s1["nicht_reif"] == 1, s1)
        check("Bootstrap-Zeile ignoriert", "BST" not in calls)
        before = out.read_bytes()
        s2 = op.run(handover_path=ho_freeze, **kw)
        after = out.read_bytes()
        check("mit Freeze: Zeile ≥ 24.10. geschrieben", s2["geschrieben"] == 1, s2)
        check("append-only: alte Bytes unverändert", after.startswith(before))
        s3 = op.run(handover_path=ho_freeze, **kw)
        check("idempotent: kein Doppel-Schreiben", s3["geschrieben"] == 0
              and len(out.read_text().splitlines()) == 2, s3)
        txt = "\n".join(logs) + st.read_text()
        check("Blindheit: Log/State ohne Kennzahl",
              "max_gain" not in txt and "drawdown" not in txt and "10.0" not in txt, txt[:300])
        check("Export nie geschrieben", (tmp / "ex.jsonl").read_text() == "")


def test_retry_and_ratelimit():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        ho = tmp / "ho.md"
        ho.write_text(config.OUTCOME_PATH_FREEZE_HEADING + "\n", encoding="utf-8")
        _write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")},
                            {"ticker": "BBB", "date": D.strftime("%d.%m.%Y")}])
        day10 = op.expected_window(D)[-1]

        def fetch_missing(t, s, e):
            return [r for r in bars(skip=3)]

        kw = dict(fetch_fn=fetch_missing, out_path=tmp / "op.jsonl", state_path=tmp / "st.json",
                  backtest_path=tmp / "bh.json", export_path=tmp / "ex.jsonl",
                  handover_path=ho, log=lambda *_: None)
        early = datetime.combine(day10 + timedelta(days=2), datetime.min.time(), timezone.utc) \
            + timedelta(hours=23)
        s = op.run(now_utc=early, **kw)
        check("Retry-Fenster: unvollständig → noch nicht geschrieben",
              s["geschrieben"] == 0 and s["erneut_versuchen"] == 2, s)
        late = early + timedelta(days=config.OUTCOME_PATH_RETRY_DAYS)
        s = op.run(now_utc=late, **kw)
        check("nach Retry-Fenster: null + Grund geschrieben",
              s["geschrieben"] == 2 and s["davon_null_nach_grund"] == {"fehlender_tag": 2}, s)

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        ho = tmp / "ho.md"
        ho.write_text(config.OUTCOME_PATH_FREEZE_HEADING + "\n", encoding="utf-8")
        _write_inputs(tmp, [{"ticker": t, "date": D.strftime("%d.%m.%Y")} for t in ("A1", "B2", "C3")])
        calls = []

        class YFRateLimitError(Exception):
            pass

        def fetch_rl(t, s, e):
            calls.append(t)
            raise YFRateLimitError("too many")

        now = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
        s = op.run(now_utc=now, fetch_fn=fetch_rl, out_path=tmp / "op.jsonl",
                   state_path=tmp / "st.json", backtest_path=tmp / "bh.json",
                   export_path=tmp / "ex.jsonl", handover_path=ho, log=lambda *_: None)
        check("Rate-Limit: Abbruch, kein Retry, nichts geschrieben",
              s["rate_limit_abbruch"] and s["geschrieben"] == 0 and len(calls) <= 2, (s, calls))


def test_freeze_block():
    text = (ROOT / "SESSION_HANDOVER.md").read_text(encoding="utf-8").split("\n")
    head = config.OUTCOME_PATH_FREEZE_HEADING
    idx = [i for i, l in enumerate(text) if l == head]
    check("Freeze-Block vorhanden (einmal)", len(idx) == 1)
    if idx:
        i = idx[0]
        j = i + 1
        while j < len(text) and not re.match(r"^#{1,3}\s", text[j]):
            j += 1
        md5 = hashlib.md5("\n".join(text[i:j]).encode("utf-8")).hexdigest()
        check("Freeze-Block MD5-Pin", md5 == FREEZE_MD5, md5)
    check("Sammler prüft dieselbe Überschrift", op.FREEZE_HEADING == head)
    src = (ROOT / "scripts" / "outcome_path_update.py").read_text(encoding="utf-8")
    check("Sammler öffnet Export nur lesend",
          not re.search(r"open\([^)]*export[^)]*['\"]w", src))


def test_digest():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        now = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
        line = hc.outcome_path_liveness_line(tmp / "op.jsonl", tmp / "st.json", now_ts=now)
        check("Digest: noch nie gelaufen", "sammelt ab dem ersten Lauf" in line, line)
        (tmp / "st.json").write_text(json.dumps({"last_run_utc": "2026-11-24T23:55:00+00:00"}))
        (tmp / "op.jsonl").write_text(json.dumps({"date": "02.11.2026"}) + "\n")
        line = hc.outcome_path_liveness_line(tmp / "op.jsonl", tmp / "st.json", now_ts=now)
        check("Digest: läuft", line.startswith("📈 Kursverlauf: läuft · 1 Zeilen")
              and "02.11.2026" in line, line)
        line = hc.outcome_path_liveness_line(tmp / "op.jsonl", tmp / "st.json",
                                             now_ts=now + timedelta(days=10))
        check("Digest: überfällig", "überfällig" in line, line)
        (tmp / "st.json").write_text("{kaputt")
        line = hc.outcome_path_liveness_line(tmp / "op.jsonl", tmp / "st.json", now_ts=now)
        check("Digest: kaputt", "unlesbar" in line, line)
        check("Digest-Zeile ohne Kennzahl", "max_gain" not in line)


def test_settled_boundary():
    import trading_date
    ny = trading_date._NY
    day10 = op.expected_window(D)[-1]

    def et(d, hh, mm):
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=ny).astimezone(timezone.utc)

    def one(now, patch_old=False):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            ho = tmp / "ho.md"
            ho.write_text(config.OUTCOME_PATH_FREEZE_HEADING + "\n", encoding="utf-8")
            _write_inputs(tmp, [{"ticker": "AAA", "date": D.strftime("%d.%m.%Y")}])
            orig = trading_date.last_settled_close_date
            if patch_old:
                trading_date.last_settled_close_date = trading_date.last_final_close_date
            try:
                st = op.run(now_utc=now, fetch_fn=lambda t, s, e: bars(),
                            out_path=tmp / "op.jsonl", state_path=tmp / "st.json",
                            backtest_path=tmp / "bh.json", export_path=tmp / "ex.jsonl",
                            handover_path=ho, log=lambda *_: None)
            finally:
                trading_date.last_settled_close_date = orig
            line = hc.outcome_path_liveness_line(tmp / "op.jsonl", tmp / "st.json",
                                                 now_ts=now.timestamp())
            return st, line

    for hh, mm in ((16, 30), (18, 53), (20, 30)):
        st, line = one(et(day10, hh, mm))
        check(f"Tag-10-Abend {hh:02d}:{mm:02d} ET → nichts geschrieben",
              st["geschrieben"] == 0 and st["nicht_reif"] == 1, st)
        check(f"Digest {hh:02d}:{mm:02d} ET: wartet ≠ kaputt/überfällig",
              "kaputt" not in line and "unlesbar" not in line and "überfällig" not in line, line)
        st_old, _ = one(et(day10, hh, mm), patch_old=True)
        check(f"Gegenprobe alte Grenze {hh:02d}:{mm:02d} ET hätte geschrieben (rot)",
              st_old["geschrieben"] == 1, st_old)
    nxt = day10 + timedelta(days=1)
    st, _ = one(et(nxt, 6, 59))
    check("Folgetag 06:59 ET → nichts geschrieben", st["geschrieben"] == 0, st)
    st, _ = one(et(nxt, 7, 5))
    check("Folgetag 07:05 ET → geschrieben", st["geschrieben"] == 1, st)
    a = trading_date.last_settled_close_date(et(day10, 18, 53))   # UTC = Tag 10
    b = trading_date.last_settled_close_date(et(day10, 20, 30))   # UTC = Folgetag
    check("Determinismus: gleiche Grenze über UTC-Mitternacht", a == b, (a, b))
    src = (ROOT / "scripts" / "outcome_path_update.py").read_text(encoding="utf-8")
    check("Quelle: last_settled_close_date, kein last_final_close_date-Aufruf",
          "last_settled_close_date(now_utc)" in src and "last_final_close_date(" not in src)


def run_all() -> int:
    for t in (test_window, test_core, test_unknown, test_split, test_determinism,
              test_run_flow, test_retry_and_ratelimit, test_freeze_block, test_digest,
              test_settled_boundary):
        print(t.__name__)
        t()
    print()
    if _fails:
        print(f"{len(_fails)} Tests fehlgeschlagen: {_fails}")
        return 1
    print("Alle outcome_path-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
