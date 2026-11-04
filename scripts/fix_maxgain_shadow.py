#!/usr/bin/env python3
"""EINMALIGE Bestandskorrektur von ``max_gain_pct`` / ``max_drawdown_pct`` und
den Exit-Shadow-Forwards aus FINALEN Tageskursen (Easy-Entscheid 03.11.2026,
Mechanik-Fix #651). Aufruf über ``fix_returns_final_close_oneoff.py
--target maxgain_shadow`` (gleiche Modi und Schutzmechanik wie der
Renditen-Pfad aus #648).

Rechnet neu — mit exakt der Logik nach #651, über DIESELBEN Helfer:
  * ``max_gain_pct``, ``max_drawdown_pct`` (+ ``max_gain_pct_net``) in
    ``backtest_history.json`` UND ``matured_backtest_export.jsonl``:
    ``backtest_history._final_window`` (nur finale Tageszeilen, erste 11 ab
    Entry) → ``_compute_max_gain_pct`` / ``_compute_max_drawdown`` →
    ``apply_round_trip_haircut``. OHLC-Abruf ``auto_adjust=True`` wie der
    Daily-Run.
  * ``forward_3d/5d/10d`` in ``exit_shadow_log.jsonl``: Regel aus
    ``ki_agent.update_exit_shadow_forwards`` (Close.dropna, Signal-Index,
    nur finale Zeilen, ``exit_shadow.compute_forward_return``).

Regeln (wie #648):
  * Nur Felder, die heute einen Wert haben. Felder ohne Key werden nie
    angelegt, leere bleiben leer, Bootstrap-Zeilen unberührt.
  * Nicht korrigierbar → ``null``, nie alter Wert, nie 0.
  * 0.0-SEMANTIK: der Daily-Run schreibt bei < 2 finalen Fensterzeilen
    ``0.0`` („zu wenig Daten“ ununterscheidbar von „kein Gewinn“). Die
    Korrektur setzt in diesem Fall ``null`` (Grund ``zu_wenig_daten``) — ein
    0.0 aus Datenmangel wäre ein erfundener Wert. Ab 2 Zeilen ist ``0.0``
    ein echtes Rechenergebnis und bleibt erlaubt.
  * Archiv ``maxgain_shadow_corrections_archive_2026-11.jsonl`` (append-only,
    nie geloggt); ``restore`` spielt es zurück.

BLINDUNG: Log nur Zählungen und Abweichungs-Beträge |alt − neu|.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fix_returns_final_close_oneoff as base  # noqa: E402

BT_FILE = base.BT_FILE
EXPORT_FILE = base.EXPORT_FILE
SHADOW_FILE = "exit_shadow_log.jsonl"
ARCHIVE_FILE = "maxgain_shadow_corrections_archive_2026-11.jsonl"
MG_FIELDS = ("max_gain_pct", "max_drawdown_pct", "max_gain_pct_net")
ES_FIELDS = ("forward_3d", "forward_5d", "forward_10d")
ES_HORIZONS = (3, 5, 10)


# ── Neuberechnung ────────────────────────────────────────────────────────────
def recompute_maxgain(entry: dict, df, final_cut: date) -> dict[str, tuple]:
    """``{feld: (wert_oder_None, grund)}`` für die MG-Felder eines Records —
    dieselben Helfer wie der Rolling-Block in ``_append_backtest_entries``."""
    import backtest_history as bh
    if df is None or getattr(df, "empty", True):
        return {f: (None, "ticker_ohne_kursdaten") for f in MG_FIELDS}
    edate = base._dmy(entry.get("date"))
    win = bh._final_window(df, edate, final_cut)
    if len(win) < 2:
        return {f: (None, "zu_wenig_daten") for f in MG_FIELDS}
    # Nicht-endlich (z. B. Fenster nur aus NaN-Zeilen eines Union-Index) gilt
    # als Rechenfehler → null, nie NaN in die Datei (Guardian-Finding #652).
    dd = base._num(bh._compute_max_drawdown(win))
    mg = base._num(bh._compute_max_gain_pct(win))
    out = {"max_drawdown_pct": (dd, "neu") if dd is not None else (None, "rechenfehler"),
           "max_gain_pct": (mg, "neu") if mg is not None else (None, "rechenfehler")}
    out["max_gain_pct_net"] = ((bh.apply_round_trip_haircut(mg), "neu") if mg is not None
                               else (None, "rechenfehler"))
    return out


def recompute_shadow(rec: dict, closes, final_cut: date) -> dict[str, tuple]:
    """Forward-Felder eines Exit-Shadow-Records — Regel aus
    ``ki_agent.update_exit_shadow_forwards`` nach #651."""
    import exit_shadow
    if not closes:
        return {f: (None, "ticker_ohne_kursdaten") for f in ES_FIELDS}
    sig_dt = base._dmy(rec.get("date"))
    idx = [d for d, _ in closes]
    sig_idx = idx.index(sig_dt) if sig_dt in idx else -1
    if sig_idx < 0:
        return {f: (None, "signaltag_fehlt") for f in ES_FIELDS}
    n_final = next((i for i, d in enumerate(idx) if d > final_cut), len(idx))
    if sig_idx >= n_final:
        return {f: (None, "signaltag_nicht_final") for f in ES_FIELDS}
    sig_close = float(closes[sig_idx][1])
    out = {}
    for n in ES_HORIZONS:
        fwd = sig_idx + n
        if 0 <= fwd < n_final:
            v = base._num(exit_shadow.compute_forward_return(sig_close, float(closes[fwd][1])))
            out[f"forward_{n}d"] = (v, "neu") if v is not None else (None, "rechenfehler")
        else:
            out[f"forward_{n}d"] = (None, "zieltag_fehlt_oder_nicht_final")
    return out


def _apply(entry: dict, vals: dict, fields) -> tuple[dict, list]:
    new = dict(entry)
    changes = []
    for f in fields:
        if f not in entry or entry[f] is None:
            continue
        nv, grund = vals[f]
        old = entry[f]
        if nv == old and type(nv) is type(old):
            continue
        new[f] = nv
        changes.append((f, old, nv, grund if nv is None else "neu_berechnet"))
    return new, changes


# ── Kursdaten ────────────────────────────────────────────────────────────────
def own_days(df):
    """Nur die eigenen Handelstage des Tickers: Zeilen, in denen High UND Low
    fehlen, fliegen vor der Fensterbildung raus (wie der Daily-Run bei wenigen
    Tickern — keine Leerzeilen, die einen Fensterplatz belegen)."""
    if df is None:
        return None
    out = df.dropna(subset=["High", "Low"], how="all")
    return None if getattr(out, "empty", True) else out


def fetch(tickers: list[str], start: date, now: datetime):
    """Einzel-Abruf je Ticker über ``base.fetch_frames`` (Rate-Limit-Schutz).
    Returnt ``({t: df_eigene_tage}, {t: closes})``; wirft
    ``base.AbrufUnvollstaendig`` bei unsauberem Abruf."""
    frames, status = base.fetch_frames(tickers, start, now)
    if base.report_fetch(status):
        raise base.AbrufUnvollstaendig()
    dfs = {t: own_days(frames.get(t)) for t in tickers}
    closes = {t: (base._series(frames[t]) if frames.get(t) is not None else None)
              for t in tickers}
    return dfs, closes


# ── Dateien ──────────────────────────────────────────────────────────────────
def load_shadow(root: pathlib.Path):
    raw = (root / SHADOW_FILE).read_text(encoding="utf-8")
    lines = raw.split("\n")
    trailing = bool(lines) and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    recs = []
    for ln in lines:
        o = json.loads(ln)
        if json.dumps(o, ensure_ascii=False) != ln:
            raise SystemExit("ABBRUCH: Exit-Shadow-Zeile nicht byte-gleich neu schreibbar — "
                             "nichts geändert.")
        recs.append(o)
    return recs, lines, trailing


def _mg_todo(r) -> bool:
    return (isinstance(r, dict) and r.get("source") != "bootstrap"
            and any(f in r and r[f] is not None for f in MG_FIELDS)
            and base._dmy(r.get("date")) is not None)


def _es_todo(r) -> bool:
    return (isinstance(r, dict) and any(f in r and r[f] is not None for f in ES_FIELDS)
            and base._dmy(r.get("date")) is not None)


# ── Lauf ─────────────────────────────────────────────────────────────────────
def run(mode: str, now: datetime, root: pathlib.Path = base.ROOT, prices=None,
        max_null: int | None = None) -> int:
    import trading_date
    final_cut = trading_date.last_final_close_date(now)
    bt, _bt_raw, ex, ex_lines, ex_trailing = base.load_files(root)
    sh, sh_lines, sh_trailing = load_shadow(root)
    base._check_unique({BT_FILE: bt, EXPORT_FILE: ex, SHADOW_FILE: sh})
    shas = {f: base._sha(root / f) for f in (BT_FILE, EXPORT_FILE, SHADOW_FILE)}

    recs_mg = [r for r in bt if _mg_todo(r)] + [r for r in ex if _mg_todo(r)]
    recs_es = [r for r in sh if _es_todo(r)]
    tickers = sorted({r["ticker"] for r in recs_mg + recs_es if r.get("ticker")})
    if not tickers:
        print("Nichts zu tun.")
        return 0
    start = min(base._dmy(r["date"]) for r in recs_mg + recs_es) - timedelta(days=10)
    if prices is None:
        try:
            dfs, closes = fetch(tickers, start, now)
        except base.AbrufUnvollstaendig:
            return 2
    else:
        dfs, closes = prices
        dfs = {t: own_days(df) for t, df in dfs.items()}
    ohne = sorted(t for t in tickers if dfs.get(t) is None and not closes.get(t))
    base._print_counters(root)
    print(f"Stand: final_cut={final_cut.isoformat()} · Ticker {len(tickers)} · "
          f"ohne Kursdaten {len(ohne)}: {ohne}")

    archive: list[dict] = []
    stats = Counter()
    devs: dict[str, list[float]] = {}
    seen = set()

    def _process(lst, datei, todo, fields, calc, keyed_pops):
        new_lst = []
        for r in lst:
            if not todo(r):
                new_lst.append(r)
                continue
            vals = calc(r)
            new, ch = _apply(r, vals, fields)
            new_lst.append(new)
            for f in fields:
                if f in r and r[f] is not None:
                    stats[(datei, f, "felder")] += 1
            for f, old, nv, grund in ch:
                stats[(datei, f, "neu" if nv is not None else f"null:{grund}")] += 1
                archive.append({"datei": datei, "date": r.get("date"), "ticker": r.get("ticker"),
                                "feld": f, "alt": old, "neu_oder_null": nv, "grund": grund})
            pops = base._pops(r) if keyed_pops else []
            for f in fields:
                if f.endswith("_net"):
                    continue
                ov, nv = base._num(r.get(f)), base._num(new.get(f))
                key = (r.get("ticker"), r.get("date"), f)
                if ov is None or nv is None or key in seen:
                    continue
                seen.add(key)
                for k in ("alle", *(f"pop:{p}" for p in pops)):
                    devs.setdefault(f"{f}|{k}", []).append(abs(ov - nv))
        return new_lst

    mg_calc = lambda r: recompute_maxgain(r, dfs.get(r["ticker"]), final_cut)  # noqa: E731
    es_calc = lambda r: recompute_shadow(r, closes.get(r["ticker"]), final_cut)  # noqa: E731
    new_ex = _process(ex, EXPORT_FILE, _mg_todo, MG_FIELDS, mg_calc, True)
    new_bt = _process(bt, BT_FILE, _mg_todo, MG_FIELDS, mg_calc, True)
    new_sh = _process(sh, SHADOW_FILE, _es_todo, ES_FIELDS, es_calc, False)
    base.verify_untouched(ex, new_ex, MG_FIELDS)
    base.verify_untouched(bt, new_bt, MG_FIELDS)
    base.verify_untouched(sh, new_sh, ES_FIELDS)

    for datei, fields in ((EXPORT_FILE, MG_FIELDS), (BT_FILE, MG_FIELDS), (SHADOW_FILE, ES_FIELDS)):
        for f in fields:
            n = stats[(datei, f, "felder")]
            neu = stats[(datei, f, "neu")]
            nulls = {k[2][5:]: v for k, v in stats.items()
                     if k[0] == datei and k[1] == f and k[2].startswith("null:")}
            print(f"[{datei}] {f}: Felder {n} · unverändert {n - neu - sum(nulls.values())} · "
                  f"neu {neu} · null {sum(nulls.values())} {dict(sorted(nulls.items()))}")
    n_null = sum(v for k, v in stats.items() if k[2].startswith("null:"))
    print(f"Auf null gesetzt gesamt (alle Dateien): {n_null}")
    print("Abweichung |alt − neu| (je Ticker/Datum/Feld einmal):")
    for f in ("max_gain_pct", "max_drawdown_pct"):
        for k in ("alle", "pop:§4", "pop:Setup-Edge", "pop:KI-Score"):
            base._dist(f"  {f} {k}", devs.get(f"{f}|{k}", []))
    for f in ES_FIELDS:
        base._dist(f"  {f} alle", devs.get(f"{f}|alle", []))

    with tempfile.TemporaryDirectory() as _td:
        _tp = pathlib.Path(_td) / EXPORT_FILE
        _tp.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                               for r in new_ex), encoding="utf-8")
        c_before = base._counters(str(root / EXPORT_FILE))
        c_after = base._counters(str(_tp))
    print(f"Zähler nach Korrektur (berechnet): {c_after} · "
          f"{'unverändert' if c_after == c_before else 'GEÄNDERT'}")

    if mode in ("dry_run", "verify"):
        print(f"Modus {mode}: nichts geschrieben.")
        return 0

    if max_null is None:
        print("ABBRUCH: --max-null fehlt (Zahl „Auf null gesetzt gesamt“ aus dem dry_run "
              "angeben). Nichts geschrieben.")
        return 2
    if n_null > max_null:
        print(f"ABBRUCH: {n_null} Felder würden auf null gesetzt (> {max_null} aus dem dry_run) — "
              "Kursabruf vermutlich anders/gestört. Nichts geschrieben.")
        return 2
    if len(ohne) > base.MAX_TICKERS_OHNE_DATEN:
        print(f"ABBRUCH: {len(ohne)} Ticker ohne Kursdaten (> {base.MAX_TICKERS_OHNE_DATEN}) — "
              "Kursabruf vermutlich gestört. Nichts geschrieben.")
        return 2
    if c_after != c_before:
        print("ABBRUCH: die Korrektur würde Freeze-Zähler ändern. Nichts geschrieben — "
              "Easy entscheidet.")
        return 2
    if any(base._sha(root / f) != h for f, h in shas.items()):
        print("ABBRUCH: Dateien seit dem Lesen geändert. Nichts geschrieben.")
        return 2

    ex_text = base._ser_ex([json.dumps(n, sort_keys=True, ensure_ascii=False) if o != n else ln
                            for o, n, ln in zip(ex, new_ex, ex_lines)], ex_trailing)
    sh_text = base._ser_ex([json.dumps(n, ensure_ascii=False) if o != n else ln
                            for o, n, ln in zip(sh, new_sh, sh_lines)], sh_trailing)
    bt_text = base._ser_bt(new_bt)
    base.verify_untouched(bt, json.loads(bt_text), MG_FIELDS)
    base.verify_untouched(ex, [json.loads(x) for x in ex_text.split("\n") if x], MG_FIELDS)
    base.verify_untouched(sh, [json.loads(x) for x in sh_text.split("\n") if x], ES_FIELDS)
    if not archive:
        print("Modus apply: keine Änderung nötig, nichts geschrieben.")
        return 0
    arch = root / ARCHIVE_FILE
    prev = arch.read_text(encoding="utf-8") if arch.exists() else ""
    base._atomic_write(arch, prev + "".join(json.dumps(a, ensure_ascii=False) + "\n"
                                            for a in archive))
    base._atomic_write(root / EXPORT_FILE, ex_text)
    base._atomic_write(root / SHADOW_FILE, sh_text)
    base._atomic_write(root / BT_FILE, bt_text)
    print(f"Modus apply: geschrieben — {len(archive)} Felder, Archiv {ARCHIVE_FILE}.")
    return 0


def restore(root: pathlib.Path = base.ROOT, apply: bool = False) -> int:
    """Spielt das Archiv zurück: ``alt`` dort, wo heute noch ``neu_oder_null``
    steht (später geänderte Werte bleiben unangetastet)."""
    rows = [json.loads(l) for l in (root / ARCHIVE_FILE).read_text(encoding="utf-8").splitlines() if l]
    bt, _r, ex, ex_lines, ex_tr = base.load_files(root)
    sh, sh_lines, sh_tr = load_shadow(root)
    files = {BT_FILE: bt, EXPORT_FILE: ex, SHADOW_FILE: sh}
    base._check_unique(files)
    idx = {name: {(r.get("ticker"), r.get("date")): r for r in lst
                  if isinstance(r, dict) and r.get("source") != "bootstrap"}
           for name, lst in files.items()}
    touched = {EXPORT_FILE: set(), SHADOW_FILE: set()}
    n_ok = n_skip = 0
    for a in reversed(rows):
        r = idx.get(a["datei"], {}).get((a["ticker"], a["date"]))
        if r is None or r.get(a["feld"]) != a["neu_oder_null"]:
            n_skip += 1
            continue
        r[a["feld"]] = a["alt"]
        n_ok += 1
        if a["datei"] in touched:
            touched[a["datei"]].add((a["ticker"], a["date"]))
    print(f"restore: zurückgespielt {n_ok} · übersprungen {n_skip}")
    if not apply:
        print("restore (Probe): nichts geschrieben.")
        return 0
    base._atomic_write(root / EXPORT_FILE, base._ser_ex(
        [json.dumps(o, sort_keys=True, ensure_ascii=False)
         if (o.get("ticker"), o.get("date")) in touched[EXPORT_FILE] else ln
         for o, ln in zip(ex, ex_lines)], ex_tr))
    base._atomic_write(root / SHADOW_FILE, base._ser_ex(
        [json.dumps(o, ensure_ascii=False)
         if (o.get("ticker"), o.get("date")) in touched[SHADOW_FILE] else ln
         for o, ln in zip(sh, sh_lines)], sh_tr))
    base._atomic_write(root / BT_FILE, base._ser_bt(bt))
    return 0
