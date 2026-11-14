#!/usr/bin/env python3
"""Wahrheits-Abgleich — dauerhafter, NUR LESENDER Wächter (Easy-Entscheid
08.11.2026, Variante A aus der Diagnose vom 05.11.2026).

Vergleicht gespeicherte VERHÄLTNIS-Felder gegen frisch geladene Yahoo-Kurse,
nachgerechnet nach den Produktionsregeln:

* ``return_3d/5d/10d`` (+ ``_t1``, ``_net``, ``_vs_spy``) —
  ``ki_agent.update_backtest_returns``: Close.dropna (eigene Handelstage des
  Tickers), Entry-Index, Offsets, nur Zeilen ≤ ``last_settled_close_date`` (seit 12.11.2026);
  ``_net`` = Haircut-Formel ``backtest_history.apply_round_trip_haircut``;
  ``_vs_spy`` = Brutto minus SPY-Rendite über SPYs EIGENE Offsets.
* ``max_gain_pct`` / ``max_drawdown_pct`` (nur Einträge > 14 Kalendertage) —
  ``backtest_history._final_window`` (erste 11 finale Zeilen ab Entry) +
  ``_compute_max_gain_pct`` / ``_compute_max_drawdown``. Der Zeitpunkt des
  LETZTEN Rolling-Updates ist nicht gespeichert → ein gespeicherter Wert gilt
  als bestätigt, wenn er zum Fenster eines PRÄFIXES (≥ 2 Zeilen) passt
  (Produktion schreibt den Wert des jeweils bis dahin finalen Fensters).
* ``forward_3d/5d/10d`` (exit_shadow_log.jsonl) —
  ``ki_agent.update_exit_shadow_forwards`` + ``exit_shadow.compute_forward_return``.
* ``vix_level`` / ``market_regime`` — PRODUKTIONS-Definition (Fix 10.11.2026):
  ``backtest_history._vix_close`` / ``_market_regime_from_spy`` (Aufruf
  ``backtest_history.py:1396-1401``) nehmen den LETZTEN Wert eines Downloads
  ZUM LAUFZEITPUNKT: in der US-Sitzung ein Intraday-Stand, vor der Öffnung der
  Vortagsschluss, im Postclose (ab 16:20 ET) der Tagesschluss. Der Zeitpunkt
  ist nicht gespeichert. ``vix_level`` gilt darum als bestätigt, wenn er in der
  ^VIX-Tagesspanne (Tief bis Hoch) des Entry-Tags liegt ODER dem Tagesschluss
  ODER dem Schluss des vorigen ^VIX-Handelstags entspricht (Toleranz wie
  unten); ``market_regime`` (SPY gegen 50 Handelstage davor, +-5 %), wenn es
  ein Regime ist, das ein SPY-Kurs innerhalb der Tagesspanne ergibt, oder das
  Regime aus dem Vortagsschluss. Alles andere bleibt ``abweichung``.
  Bestätigungen über diese Laufzeit-Regel (nicht exakt der Schluss) stehen mit
  Spanne in ``laufzeit_regel`` der Log-Zeile.
* ``entry_past_return_5d`` — PRODUKTIONS-Definition je Schreibpfad (seit
  13.11.2026): Einstiege ab ``EPR_LIVE_FROM`` (laufender Postclose) = gespeicherter
  ``entry_price`` (Kurs zum Laufzeitpunkt, Split nach D über den Split-Faktor
  umgerechnet) gegen den Schluss 5 eigene Handelstage davor; Stufe-B-Backfill
  davor (und bei Dividende seit dem Nenner) Schluss gegen Schluss.

* ``entry_price`` (seit 14.11.2026, Schritt 2) — nur Einstiege ab
  ``config.TRUTH_CHECK_ENTRY_PRICE_FROM``: gespeicherter Wert gegen den
  Rohkurs-Schluss von D (bereinigter Schluss / Split-Faktor nach D), relative
  Abweichung in Prozent, Toleranz ``TRUTH_CHECK_ENTRY_PRICE_TOL_PCT`` (0,02 %);
  Dividende nach D → ``neu_adjustiert`` wie bei den anderen Feldern.

KEIN ``entry_price_t1``, kein ``rvol``. Bootstrap-Zeilen
werden übersprungen. Toleranz ``config.TRUTH_CHECK_TOLERANCE_PP`` (0,02).
Abweichung → Blick auf Dividenden/Splits im Fenster (aus derselben Kurs-
Abfrage, ``actions=True``): vorhanden → Klasse ``neu_adjustiert``, sonst
``abweichung``. Seit 13.11.2026 (``_classify_dev``): Dividende im Fenster →
``neu_adjustiert`` wie bisher, ``abs_delta`` im Log; Split im Fenster ODER Aktion
nach dem Fenster → ``neu_adjustiert`` nur bei |Δ| ≤ Rundungsschranke
(``rounding_bound``; ``regel`` + ``schranke``), sonst ``abweichung``.

Umfang je Lauf: frisch gereifte Export-Zeilen (Zeilenzahl > ``export_lines_seen``
im State), frisch vollständige Exit-Shadow-Records, Wiederholungen (Abweichung
im Vorlauf / Yahoo-Fehler) und ~10 Bestands-Ticker in fester Rotation, dazu
SPY und ^VIX. Höchstens 2 parallele Abrufe; Rate-Limit → KEIN Retry, die
restlichen Ticker zählen als ``unbekannt(rate_limit)``, der Lauf endet sauber.

SCHREIBT AUSSCHLIESSLICH ``truth_check_log.jsonl`` (eine Zeile pro Lauf) und
``truth_check_state.json``. Datendateien werden nur zum Lesen geöffnet.

Aufruf: ``python scripts/truth_check.py`` (``--now ISO`` für Determinismus,
``--dry-run`` = nichts schreiben, nur ausgeben).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import trading_date  # noqa: E402

SCHEMA_V = 1
WINDOWS = (3, 5, 10)
SHADOW_HORIZONS = (3, 5, 10)
SPY, VIX = "SPY", "^VIX"
MAX_DEVIATIONS_LOGGED = 50       # Log-Zeile bleibt klein
MAX_RETRY_KEYS = 300             # Wiederholungs-Liste gedeckelt
UNKNOWN_REASONS = ("yahoo_fehler", "ausdruecklich_leer", "rate_limit")
# Liste geprüfter, bekannter Abweichungen (Easy-Entscheid 13.11.2026). Nur per
# PR mit Easy-Merge pflegen; jeder Eintrag braucht Grund, Verweis und
# Entscheid-Datum. Ein Eintrag greift NUR, wenn gespeicherter UND neu
# berechneter Wert innerhalb der Toleranz zu den eingetragenen Werten passen.
KNOWN_FILE = "truth_check_known.json"
KNOWN_REQUIRED = ("datei", "ticker", "date", "feld", "alt", "vergleich",
                  "grund", "verweis", "entscheid_datum")

RETURN_FIELDS = tuple(
    f for w in WINDOWS
    for f in (f"return_{w}d", f"return_{w}d_t1", f"return_{w}d_net", f"return_{w}d_vs_spy"))
MAX_FIELDS = ("max_gain_pct", "max_drawdown_pct")
# entry_past_return_5d: erster Einstiegstag, den der laufende Postclose mit Wert
# geschrieben hat (Zähler = Kurs zum Laufzeitpunkt). Davor (14.05.–10.07.2026)
# stammen alle Werte aus dem Stufe-B-Backfill (Schluss/Schluss, Manifest). Beleg:
# Manifest-Daten 14.05.–10.07.; erste Nicht-Manifest-Werte 13.07.2026 (Test).
EPR_LIVE_FROM = date(2026, 7, 13)
# entry_price-Prüfung erst ab diesem Einstiegstag (config, Schritt 2 14.11.2026).
ENTRY_PRICE_FROM = date.fromisoformat(config.TRUTH_CHECK_ENTRY_PRICE_FROM)
ENTRY_PRICE_TOL_PCT = float(config.TRUTH_CHECK_ENTRY_PRICE_TOL_PCT)
SHADOW_FIELDS = tuple(f"forward_{n}d" for n in SHADOW_HORIZONS)


# ── kleine Helfer ────────────────────────────────────────────────────────────
def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _dmy(s) -> date | None:
    try:
        return datetime.strptime(s or "", "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _haircut(gross):
    """Spiegel von ``backtest_history.apply_round_trip_haircut`` (pure; der
    Import würde yfinance laden). Gleichheit belegt der Mock-Test."""
    if gross is None:
        return None
    h = abs(float(config.HAIRCUT_ROUND_TRIP_PCT)) / 100.0
    half = h / 2.0
    return round(((1.0 + float(gross) / 100.0) * (1.0 - half) / (1.0 + half) - 1.0) * 100.0, 2)


def _max_drawdown(rows) -> float | None:
    """Spiegel ``_compute_max_drawdown`` (pandas cummax überspringt NaN)."""
    if len(rows) < 2:
        return None
    peak, worst = None, None
    for r in rows:
        h, lo = _num(r.get("h")), _num(r.get("l"))
        if h is not None:
            peak = h if peak is None else max(peak, h)
        # pandas: cummax an einer NaN-High-Zeile ist NaN → Zeile zählt nicht.
        if h is None or lo is None or peak is None or peak == 0:
            continue
        v = (lo - peak) / peak * 100.0
        worst = v if worst is None else min(worst, v)
    return round(worst, 2) if worst is not None else None


def _max_gain(rows) -> float | None:
    """Spiegel ``_compute_max_gain_pct`` (pandas cummin überspringt NaN)."""
    if len(rows) < 2:
        return None
    low, best = None, None
    for r in rows:
        h, lo = _num(r.get("h")), _num(r.get("l"))
        if lo is not None:
            low = lo if low is None else min(low, lo)
        # pandas: cummin an einer NaN-Low-Zeile ist NaN → Zeile zählt nicht.
        if h is None or lo is None or low is None or low == 0:
            continue
        v = (h - low) / low * 100.0
        best = v if best is None else max(best, v)
    return round(best, 2) if best is not None else None


# ── Kursreihen ───────────────────────────────────────────────────────────────
class Series:
    """Tageszeilen eines Tickers (aufsteigend). ``rows``: Liste von Dicts
    ``{d: date, c, h, l, div, split}`` — Werte dürfen NaN/None sein."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r["d"])
        self.closes = [(r["d"], float(r["c"])) for r in self.rows if _num(r.get("c")) is not None]
        self.cidx = [d for d, _ in self.closes]
        self.own = [r for r in self.rows if _num(r.get("h")) is not None or _num(r.get("l")) is not None]

    def cpos(self, d: date) -> int:
        try:
            return self.cidx.index(d)
        except ValueError:
            return -1

    def row_at(self, d: date):
        for r in self.rows:
            if r["d"] == d:
                return r
        return None

    def has_action(self, d0: date, d1: date) -> bool:
        return self.has_dividend(d0, d1) or self.has_split(d0, d1)

    def has_dividend(self, d0: date, d1: date) -> bool:
        return any(d0 <= r["d"] <= d1 and (_num(r.get("div")) or 0.0) != 0.0 for r in self.rows)

    def has_split(self, d0: date, d1: date) -> bool:
        return any(d0 <= r["d"] <= d1 and (_num(r.get("split")) or 0.0) != 0.0 for r in self.rows)


def _close_at(s: Series, ei: int, off: int, final_cut: date):
    pos = ei + off
    if 0 <= pos < len(s.closes) and s.cidx[pos] <= final_cut:
        return s.closes[pos][1], s.cidx[pos]
    return None, None


# ── Nachrechnen: ein Feld → (neu, (datum_von, datum_bis), quellen) ────────────
def recompute_backtest(row: dict, s: Series | None, spy: Series | None,
                       vix: Series | None, final_cut: date, today: date) -> dict:
    """``{feld: (neu_wert, (d0, d1), (quell_ticker, …))}`` NUR für Felder, die
    sich nachrechnen ließen. Nicht nachrechenbar → Feld fehlt (keine Wertung)."""
    out: dict = {}
    edate = _dmy(row.get("date"))
    if edate is None:
        return out
    tk = row.get("ticker")
    if s is not None:
        ei = s.cpos(edate)
        if ei >= 0:
            c0, _ = _close_at(s, ei, 0, final_cut)
            c1, d1t = _close_at(s, ei, 1, final_cut)
            for w in WINDOWS:
                cw, dw = _close_at(s, ei, w, final_cut)
                if c0 and c0 > 0 and cw is not None:
                    r = round((cw / c0 - 1) * 100, 2)
                    out[f"return_{w}d"] = (r, (edate, dw), (tk,))
                    out[f"return_{w}d_net"] = (_haircut(r), (edate, dw), (tk,))
                    if spy is not None:
                        si = spy.cpos(edate)
                        if si >= 0:
                            s0, _ = _close_at(spy, si, 0, final_cut)
                            sn, _ = _close_at(spy, si, w, final_cut)
                            if s0 and s0 > 0 and sn is not None:
                                out[f"return_{w}d_vs_spy"] = (
                                    round(r - (sn / s0 - 1) * 100, 2), (edate, dw), (tk, SPY))
                if c1 and c1 > 0:
                    cw1, dw1 = _close_at(s, ei, 1 + w, final_cut)
                    if cw1 is not None:
                        out[f"return_{w}d_t1"] = (round((cw1 / c1 - 1) * 100, 2), (edate, dw1), (tk,))
            # entry_past_return_5d — Rechenweg je SCHREIBPFAD (Easy-Entscheid 13.11.2026):
            #  * Laufender Postclose (Einstieg ab EPR_LIVE_FROM): Produktion rechnet
            #    s["price"] (Kurs zum Laufzeitpunkt, = gespeicherter entry_price, auf
            #    4 Stellen gerundet) / Close 5 Handelstage davor. Nachgerechnet mit dem
            #    GESPEICHERTEN entry_price (exakt), Nenner auf den eigenen Handelstagen;
            #    ein Split nach D wird über F (Rohkurs → bereinigt) umgerechnet.
            #    Dividende seit dem Nenner → bisheriger Rechenweg (Schluss/Schluss),
            #    weil die Dividenden-Bereinigung den Rohkurs nicht exakt abbildet
            #    ("kein Verhalten für Dividenden ändern").
            #  * Stufe-B-Backfill (Einstiege bis 10.07.2026, Manifest
            #    backfill_entry_past_return_5d_manifest.json): Schluss / Schluss.
            if ei >= 5:
                den, dden = s.closes[ei - 5][1], s.cidx[ei - 5]
                if den > 0:
                    ep = _num(row.get("entry_price"))
                    live = (edate >= EPR_LIVE_FROM and ep is not None and ep > 0
                            and not s.has_dividend(dden, s.rows[-1]["d"]))
                    num = ep * _split_factor_after(s, edate) if live else s.closes[ei][1]
                    out["entry_past_return_5d"] = (
                        round((num / den - 1.0) * 100.0, 2), (dden, edate), (tk,))
                    out["_epr_def"] = "laufzeitkurs" if live else "schluss"
            # entry_price (Schritt 2, 14.11.2026): Rohkurs-Schluss von D =
            # bereinigter Schluss / F (Splits nach D). Dividende nach D →
            # Klassierung über span (D .. Reihenende) wie bei den anderen Feldern.
            if edate >= ENTRY_PRICE_FROM and c0 and c0 > 0:
                out["entry_price"] = (round(c0 / _split_factor_after(s, edate), 4),
                                      (edate, s.rows[-1]["d"]), (tk,))
        # max_gain / max_drawdown nur bei Einträgen > 14 Kalendertage.
        if (today - edate).days > 14:
            win = [r for r in s.own if edate <= r["d"] <= final_cut][:11]
            if len(win) >= 2:
                span = (win[0]["d"], win[-1]["d"])
                cands_g = [_max_gain(win[:k]) for k in range(2, len(win) + 1)]
                cands_d = [_max_drawdown(win[:k]) for k in range(2, len(win) + 1)]
                out["max_gain_pct"] = (cands_g, span, (tk,))
                out["max_drawdown_pct"] = (cands_d, span, (tk,))
    if vix is not None:
        vi = vix.cpos(edate)
        if vi >= 0:
            r_e = vix.row_at(edate) or {}
            spec = {
                "schluss": round(vix.closes[vi][1], 2),
                "tief": _round2(_num(r_e.get("l"))),
                "hoch": _round2(_num(r_e.get("h"))),
                "vortag": round(vix.closes[vi - 1][1], 2) if vi >= 1 else None,
            }
            out["vix_level"] = (spec, (edate, edate), (VIX,))
    if spy is not None:
        si = spy.cpos(edate)
        if si >= 50:
            cur, ref = spy.closes[si][1], spy.closes[si - 50][1]
            if ref > 0:
                regime = _regime((cur - ref) / ref * 100.0)
                allowed = {regime}
                r_e = spy.row_at(edate) or {}
                lo, hi = _num(r_e.get("l")), _num(r_e.get("h"))
                if lo is not None and hi is not None:
                    allowed |= _regimes_between((lo - ref) / ref * 100.0,
                                                (hi - ref) / ref * 100.0)
                if si >= 51 and spy.closes[si - 51][1] > 0:
                    pc, pref = spy.closes[si - 1][1], spy.closes[si - 51][1]
                    allowed.add(_regime((pc - pref) / pref * 100.0))
                out["market_regime"] = ({"schluss": regime, "erlaubt": sorted(allowed)},
                                        (spy.cidx[si - 50], edate), (SPY,))
    return out


def _round2(v):
    return round(v, 2) if v is not None else None


def _regime(delta_pct: float) -> str:
    """Spiegel der Schwellen in ``_market_regime_from_spy`` (+-5 %)."""
    return "bull" if delta_pct > 5.0 else ("bear" if delta_pct < -5.0 else "neutral")


def _regimes_between(d_lo: float, d_hi: float) -> set:
    """Alle Regime, die ein Delta im geschlossenen Intervall [d_lo, d_hi]
    ergibt (die Klassen sind monoton im Kurs)."""
    lo, hi = min(d_lo, d_hi), max(d_lo, d_hi)
    out = set()
    if hi > 5.0:
        out.add("bull")
    if lo < -5.0:
        out.add("bear")
    if lo <= 5.0 and hi >= -5.0:
        out.add("neutral")
    return out


def vix_runtime_verdict(alt: float, spec: dict, tol: float):
    """Regel für ``vix_level``: Rückgabe "schluss", "spanne" oder "vortag"
    (bestätigt, mit Regel) bzw. None (Abweichung). Pure, deterministisch."""
    eps = tol + 1e-9
    if spec.get("schluss") is not None and abs(alt - spec["schluss"]) <= eps:
        return "schluss"
    lo, hi = spec.get("tief"), spec.get("hoch")
    if lo is not None and hi is not None and min(lo, hi) - eps <= alt <= max(lo, hi) + eps:
        return "spanne"
    if spec.get("vortag") is not None and abs(alt - spec["vortag"]) <= eps:
        return "vortag"
    return None


def recompute_shadow(row: dict, s: Series | None, final_cut: date) -> dict:
    out: dict = {}
    sdate = _dmy(row.get("date"))
    if s is None or sdate is None:
        return out
    si = s.cpos(sdate)
    n_final = next((i for i, d in enumerate(s.cidx) if d > final_cut), len(s.cidx))
    if si < 0 or si >= n_final:
        return out
    sig = s.closes[si][1]
    if sig <= 0:
        return out
    for n in SHADOW_HORIZONS:
        fi = si + n
        if fi < n_final:
            out[f"forward_{n}d"] = (round((s.closes[fi][1] - sig) / sig * 100.0, 2),
                                    (sdate, s.cidx[fi]), (row.get("ticker"),))
    return out


def _fields_of(datei: str, row: dict) -> tuple:
    if datei == "exit_shadow":
        return SHADOW_FIELDS
    return RETURN_FIELDS + MAX_FIELDS + ("vix_level", "market_regime", "entry_past_return_5d",
                                         "entry_price")


def compare_row(datei: str, row: dict, rec: dict, series: dict, tol: float,
                notes: list | None = None):
    """Vergleicht die gespeicherten Felder einer Zeile. Returnt
    ``(n_verglichen, [abweichung-dicts], max_abs_delta)``. ``notes`` (optional)
    sammelt Bestätigungen über die Laufzeit-Regel (vix_level / market_regime
    nicht exakt gleich dem Schluss-Wert) samt Spanne -- reine Transparenz."""
    devs, n_cmp, max_d = [], 0, None
    for f in _fields_of(datei, row):
        alt = row.get(f)
        if alt is None or f not in rec:
            continue
        neu, span, srcs = rec[f]
        if f == "market_regime":
            n_cmp += 1
            if alt not in neu["erlaubt"]:
                devs.append((f, alt, neu["schluss"], span, srcs, None))
            elif alt != neu["schluss"] and notes is not None:
                notes.append({"ticker": row.get("ticker"), "date": row.get("date"),
                              "feld": f, "alt": alt, "schluss": neu["schluss"],
                              "erlaubt": neu["erlaubt"], "regel": "spanne_oder_vortag"})
            continue
        if f == "vix_level":
            a = _num(alt)
            if a is None or neu.get("schluss") is None:
                continue
            n_cmp += 1
            verdict = vix_runtime_verdict(a, neu, tol)
            if verdict is None:
                delta = abs(neu["schluss"] - a)
                devs.append((f, alt, neu["schluss"], span, srcs, delta))
                max_d = delta if max_d is None else max(max_d, delta)
            elif verdict != "schluss" and notes is not None:
                notes.append({"ticker": row.get("ticker"), "date": row.get("date"),
                              "feld": f, "alt": alt, **neu, "regel": verdict})
            continue
        a = _num(alt)
        if a is None:
            continue
        if f in MAX_FIELDS:
            cands = [c for c in neu if c is not None]
            if not cands:
                continue
            n_cmp += 1
            best = min(cands, key=lambda c: abs(c - a))
            delta = abs(best - a)
            if delta > tol + 1e-9:
                devs.append((f, alt, cands[-1], span, srcs, abs(cands[-1] - a)))
                max_d = abs(cands[-1] - a) if max_d is None else max(max_d, abs(cands[-1] - a))
            continue
        if neu is None:
            continue
        if f == "entry_price":
            # relative Abweichung in Prozent (nicht pp), eigene Toleranz.
            if neu <= 0:
                continue
            n_cmp += 1
            delta = abs(neu - a) / neu * 100.0
            if delta > ENTRY_PRICE_TOL_PCT + 1e-9:
                # max_abs_delta bleibt in pp (Verhältnis-Felder) — entry_price
                # trägt seine Prozent-Abweichung in ``abw_pct`` der Abweichung.
                devs.append((f, alt, neu, span, srcs, delta))
            continue
        n_cmp += 1
        delta = abs(neu - a)
        if delta > tol + 1e-9:
            devs.append((f, alt, neu, span, srcs, delta))
            max_d = delta if max_d is None else max(max_d, delta)
    out = []
    for f, alt, neu, span, srcs, delta in devs:
        d = _classify_dev(datei, row, rec, series, f, alt, neu, span, srcs, delta)
        if f == "entry_price" and delta is not None:
            d["abw_pct"] = round(delta, 4)
        out.append(d)
    return n_cmp, out, max_d


def _classify_dev(datei, row, rec, series, f, alt, neu, span, srcs, delta) -> dict:
    """Klassierung einer Abweichung (Easy-Entscheide 13.11.2026):
    * Dividende IM Fenster (irgendeine Quelle) → ``neu_adjustiert`` wie bisher,
      zusätzlich ``abs_delta`` im Log (Beobachtung, kein Verhaltenswechsel).
    * sonst Split im Fenster ODER Aktion nach dem Fenster → ``neu_adjustiert`` nur,
      wenn |Δ| ≤ Rundungsschranke (``rounding_bound``); sonst ``abweichung``.
      Felder ohne herleitbare Schranke (max_*, vix, regime) → ``abweichung``.
    * keine Aktion → ``abweichung``."""
    d = {"datei": datei, "ticker": row.get("ticker"), "date": row.get("date"),
         "feld": f, "alt": alt, "neu": neu, "klasse": "abweichung"}
    if f == "entry_past_return_5d" and rec.get("_epr_def"):
        d["definition"] = rec["_epr_def"]
    is_ep = f == "entry_price"   # delta in % (abw_pct), keine Rundungsschranke
    if any(series.get(t) is not None and series[t].has_dividend(span[0], span[1]) for t in srcs):
        d["klasse"] = "neu_adjustiert"
        d["regel"] = "dividende_im_fenster"
        if delta is not None and not is_ep:
            d["abs_delta"] = round(delta, 4)
        return d
    split_in = any(series.get(t) is not None and series[t].has_split(span[0], span[1]) for t in srcs)
    bfield, bsrc = f, srcs[0] if srcs else None
    if f.endswith("_vs_spy"):
        spy = series.get(SPY)
        spy_quiet = spy is not None and spy.rows and not spy.has_action(span[0], spy.rows[-1]["d"])
        bfield = f[: -len("_vs_spy")] if spy_quiet else None
    elif len(srcs) != 1:
        bfield = None
    bound = None
    if bfield and delta is not None:
        bound = rounding_bound(series.get(bsrc), bfield, span,
                               b_exact=(f == "entry_past_return_5d"
                                        and rec.get("_epr_def") == "laufzeitkurs"))
    if bound is not None:
        d["schranke"] = round(bound, 4)
        if delta <= bound + 1e-9:
            d["klasse"] = "neu_adjustiert"
            d["regel"] = "rundung_split_im_fenster" if split_in else "rundung_nach_aktion"
            return d
    if split_in:
        d["regel"] = "split_nach_d" if is_ep else "split_im_fenster_ueber_schranke"
    return d


# ── Rundungsschranke nach Kapitalmaßnahme (Easy-Entscheid 13.11.2026) ─────────
# BJDX-Klasse: Split/Dividende NACH dem Rechenfenster. Yahoo bereinigt dann die
# ganze Reihe neu und liefert die Kurse auf einem anderen Raster (BJDX: Reverse-
# Split 1:4 am 03.11.2026, Rohkurse seither auf 0,001 gerundet → bereinigt auf
# 0,004). Ein früher gespeichertes Verhältnis kann dadurch um eine Rundungsgröße
# abweichen. KEINE pauschale Freistellung: ``neu_adjustiert`` nur, wenn
#   (a) die Kursreihe des Laufs eine Aktion (Split/Dividende) zwischen
#       Fensterbeginn und Reihenende (= heute) belegt UND
#   (b) |Δ| ≤ Schranke S aus Kursniveau und Nachkommastellen:
#       F(d)  = Π 1/split_ratio aller Splits NACH dem Kurstag d (Rohkurs = bereinigt / F),
#       k     = größte Nachkommastellenzahl der Rohkurse im Fenster (7 signifikante
#               Stellen — Yahoo liefert float32, ~7,2 Dezimalstellen),
#       h(d)  = 0,5 · 10^-k · F(d)  (halbes Rohkurs-Raster, in bereinigten Einheiten),
#       S     = 100 · (b/a) · (h_a/a + h_b/b) + 0,01   (Verhältnis b/a − 1; 0,01 =
#               Rundung beider Prozentwerte auf 2 Stellen); für ``_net`` der Brutto-
#               Anteil mal Haircut-Faktor (<1) + 0,01.
# Gilt nur für Felder der Form Kurs b / Kurs a − 1 eines Tickers (return_Nd, _t1,
# _net, forward_Nd, entry_past_return_5d). Darüber → weiter ``abweichung``.
RATIO_PREFIXES = ("return_", "forward_", "entry_past_return_5d")
_SIG_DIGITS = 7


def _decimals(v: float) -> int:
    t = f"{float(f'{v:.{_SIG_DIGITS}g}'):.{_SIG_DIGITS + 3}f}".rstrip("0").rstrip(".")
    return len(t.split(".")[1]) if "." in t else 0


def _split_factor_after(s: Series, d: date) -> float:
    f = 1.0
    for r in s.rows:
        sp = _num(r.get("split"))
        if r["d"] > d and sp and sp > 0:
            f *= 1.0 / sp
    return f


def rounding_bound(s: Series | None, field: str, span, *, b_exact: bool = False) -> float | None:
    """Schranke S (pp) oder ``None`` (Regel greift nicht: kein Kursverhältnis-
    Feld, keine belegte Aktion seit Fensterbeginn, Kurse fehlen). Pure."""
    if s is None or not s.rows or not any(field.startswith(p) for p in RATIO_PREFIXES) \
            or field.endswith("_vs_spy"):
        return None
    d0, d1 = span
    if not s.has_action(d0, s.rows[-1]["d"]):
        return None
    ia = s.cpos(d0) + (1 if "_t1" in field else 0)
    ib = s.cpos(d1)
    if s.cpos(d0) < 0 or ib < 0 or ia > ib:
        return None
    (da, a), (db, b) = s.closes[ia], s.closes[ib]
    if a <= 0 or b <= 0:
        return None
    win = [(d, c) for d, c in s.closes if d0 <= d <= d1]
    k = max(_decimals(c / _split_factor_after(s, d)) for d, c in win)
    ha = 0.5 * 10.0 ** -k * _split_factor_after(s, da)
    # b_exact: Zähler ist ein gespeicherter Wert (entry_price), keine Kursreihe → kein Rundungsanteil.
    hb = 0.0 if b_exact else 0.5 * 10.0 ** -k * _split_factor_after(s, db)
    core = 100.0 * (b / a) * (ha / a + hb / b)
    if field.endswith("_net"):
        h = abs(float(config.HAIRCUT_ROUND_TRIP_PCT)) / 200.0
        core *= (1.0 - h) / (1.0 + h)
    return core + 0.01


# ── Yahoo-Abruf (injizierbar) ────────────────────────────────────────────────
_EMPTY_DESCRIPTIONS = ("not found", "no data found")


def classify_fetch_error(exc: BaseException) -> str:
    """``rate_limit`` / ``ausdruecklich_leer`` / ``yahoo_fehler`` — nach dem
    Muster des Korrektur-Skripts #648/#653 (Klassen-NAME, läuft ohne yfinance)."""
    name = type(exc).__name__
    if name == "YFRateLimitError" or "RateLimit" in name:
        return "rate_limit"
    if name == "YFTzMissingError":
        return "ausdruecklich_leer"
    if name == "YFPricesMissingError":
        msg = str(exc)
        if "Yahoo status_code =" in msg:
            return "yahoo_fehler"
        marker = '(Yahoo error = "'
        if marker in msg:
            desc = msg.split(marker, 1)[1].split('")', 1)[0].lower()
            return ("ausdruecklich_leer" if any(k in desc for k in _EMPTY_DESCRIPTIONS)
                    else "yahoo_fehler")
        return "ausdruecklich_leer"
    return "yahoo_fehler"


def yahoo_fetch(ticker: str, start: date, end: date):
    """Echter Abruf: ``Ticker.history(auto_adjust=True, actions=True)`` —
    Dividenden/Splits kommen in DERSELBEN Antwort mit (kein Zusatz-Request).
    Returnt Liste von Tageszeilen; wirft bei Fehlern (Klassifikation oben)."""
    import yfinance as yf
    try:
        yf.config.debug.hide_exceptions = False
    except Exception:  # noqa: BLE001
        pass
    df = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(),
                                   interval="1d", auto_adjust=True, actions=True)
    if df is None or getattr(df, "empty", True):
        raise LookupError("leer_ohne_meldung")
    rows = []
    for ts, rec in df.iterrows():
        rows.append({"d": ts.date(), "c": rec.get("Close"), "h": rec.get("High"),
                     "l": rec.get("Low"), "div": rec.get("Dividends", 0.0),
                     "split": rec.get("Stock Splits", 0.0)})
    return rows


def fetch_all(tickers: list[str], starts: dict, end: date, fetch_fn, *, workers: int):
    """Abruf in fester Reihenfolge, max. ``workers`` parallel. Rate-Limit →
    KEIN Retry; alle danach noch nicht begonnenen Abrufe entfallen und zählen
    als ``rate_limit``. Returnt ``({t: Series}, {t: grund})``."""
    stop = threading.Event()
    series, unknown = {}, {}
    lock = threading.Lock()

    def _one(t):
        if stop.is_set():
            with lock:
                unknown[t] = "rate_limit"
            return
        try:
            rows = fetch_fn(t, starts[t], end)
        except Exception as exc:  # noqa: BLE001
            reason = classify_fetch_error(exc)
            if reason == "rate_limit":
                stop.set()
            with lock:
                unknown[t] = reason
            return
        s = Series(rows or [])
        with lock:
            if not s.closes:
                unknown[t] = "ausdruecklich_leer"
            else:
                series[t] = s

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(_one, tickers))
    return series, unknown


# ── Dateien (nur lesend) + State/Log (einzige Schreibziele) ──────────────────
def load_known(path: pathlib.Path) -> list:
    """Bekannte Fälle laden. Fail-safe: fehlende/kaputte Datei oder ein
    unvollständiger Eintrag → dieser Eintrag (bzw. alle) greift NICHT, die
    Abweichung alarmiert wie bisher."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("eintraege") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for e in items:
        if not isinstance(e, dict) or any(e.get(k) in (None, "") for k in KNOWN_REQUIRED):
            continue
        if _num(e.get("alt")) is None or _num(e.get("vergleich")) is None:
            continue
        out.append(e)
    return out


def apply_known(devs: list, known: list, tol: float) -> list:
    """Pure: setzt ``klasse`` von ``abweichung`` auf ``bekannt``, wenn ein
    Eintrag mit gleicher (datei, ticker, date, feld) existiert und BEIDE Werte
    (gespeichert ``alt`` und neu berechnet ``neu``) innerhalb ``tol`` zu den
    eingetragenen Werten passen. Sonst unverändert (voller Alarm)."""
    idx = {(e["datei"], e["ticker"], e["date"], e["feld"]): e for e in known}
    out = []
    def _close(x, ref):
        # entry_price: relative Toleranz in Prozent (ENTRY_PRICE_TOL_PCT), sonst pp.
        if d.get("feld") == "entry_price":
            return ref != 0 and abs(x - ref) / abs(ref) * 100.0 <= ENTRY_PRICE_TOL_PCT + 1e-9
        return abs(x - ref) <= tol + 1e-9

    for d in devs:
        e = idx.get((d.get("datei"), d.get("ticker"), d.get("date"), d.get("feld")))
        a, n = _num(d.get("alt")), _num(d.get("neu"))
        if (d.get("klasse") == "abweichung" and e is not None and a is not None and n is not None
                and _close(a, float(e["alt"]))
                and _close(n, float(e["vergleich"]))):
            d = dict(d, klasse="bekannt", verweis=e["verweis"])
        out.append(d)
    return out


def _read_jsonl(path: pathlib.Path) -> list:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    out.append(None)
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    obj = None
                out.append(obj if isinstance(obj, dict) else None)
    except FileNotFoundError:
        return []
    return out


def load_state(path: pathlib.Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def _key(datei, ticker, d) -> str:
    return f"{datei}|{ticker}|{d}"


def plan_scope(export_rows: list, shadow_rows: list, state: dict | None, rot_n: int):
    """Bestimmt die Zeilen dieses Laufs + den Folge-State (ohne Ergebnisse).
    Returnt ``(scope, rotation, n_frisch, new_state)``; ``scope`` =
    ``{key: (datei, row)}`` in fester Reihenfolge."""
    first_run = state is None
    st = dict(state or {})
    exp = [r for r in export_rows if r and r.get("source") != "bootstrap"]
    # Exit-Shadow: nur Records mit mindestens einem gefüllten Forward-Feld.
    shd = [r for r in shadow_rows if r and any(r.get(f) is not None for f in SHADOW_FIELDS)]
    by_key = {}
    for r in exp:
        by_key[_key("export", r.get("ticker"), r.get("date"))] = ("export", r)
    for r in shd:
        by_key[_key("exit_shadow", r.get("ticker"), r.get("date"))] = ("exit_shadow", r)

    complete_shadow = {_key("exit_shadow", r.get("ticker"), r.get("date"))
                       for r in shd if r.get("forward_10d") is not None}
    n_lines = len(export_rows)
    if first_run:
        # Erstlauf: Bestand gilt als "gesehen"; geprüft wird nur die Rotation.
        st["export_lines_seen"] = n_lines
        st["shadow_checked"] = sorted(complete_shadow)
        st["rotation_pos"] = 0
    seen = int(st.get("export_lines_seen") or 0)
    scope: dict = {}
    n_frisch = 0
    for r in export_rows[seen:]:
        if r and r.get("source") != "bootstrap":
            k = _key("export", r.get("ticker"), r.get("date"))
            if k not in scope:
                scope[k] = ("export", r)
                n_frisch += 1
    checked = set(st.get("shadow_checked") or [])
    for k in sorted(complete_shadow - checked):
        scope.setdefault(k, by_key[k])
        n_frisch += 1
    for k in list(st.get("recheck") or []) + list(st.get("retry") or []):
        if k in by_key:
            scope.setdefault(k, by_key[k])
    tickers = sorted({r.get("ticker") for r in exp + shd if r.get("ticker")})
    rotation = []
    if tickers:
        pos = int(st.get("rotation_pos") or 0) % len(tickers)
        rotation = [tickers[(pos + i) % len(tickers)] for i in range(min(rot_n, len(tickers)))]
        st["rotation_pos"] = (pos + len(rotation)) % len(tickers)
    rot_set = set(rotation)
    for k, (datei, r) in by_key.items():
        if r.get("ticker") in rot_set:
            scope.setdefault(k, (datei, r))
    st["export_lines_seen"] = n_lines
    st["shadow_checked"] = sorted(checked | complete_shadow)
    return scope, rotation, n_frisch, st


def run(now: datetime, root: pathlib.Path = ROOT, fetch_fn=None, *,
        write: bool = True, score_fetch=None, score_rsi=None) -> dict:
    """Ein Lauf. Liest Export + Exit-Shadow, schreibt NUR Log + State."""
    fetch_fn = fetch_fn or yahoo_fetch
    tol = float(config.TRUTH_CHECK_TOLERANCE_PP)
    delisted = set(config.TRUTH_CHECK_DELISTED)
    # Vergleichs-Referenz = ENDGÜLTIGER Schlusskurs (Fix 12.11.2026, open_item
    # rendite-forward-abendzeile-nicht-final): Close von Tag X erst ab 07:00 ET
    # des Folgetags (trading_date.last_settled_close_date, wie #680/#681). Vorher
    # 16:20 ET — der Lauf 18:07 ET verglich dann teils gegen einen vorläufigen
    # Abend-Close (Fehlalarm oder übersehener Fehler). ET-Datum statt UTC-Datum
    # (Determinismus unabhängig vom UTC-Datum des Laufs).
    final_cut = trading_date.last_settled_close_date(now)
    today = now.astimezone(trading_date._NY).date()

    export_rows = _read_jsonl(root / config.MATURED_EXPORT_FILE)
    shadow_rows = _read_jsonl(root / "exit_shadow_log.jsonl")
    state_path = root / config.TRUTH_CHECK_STATE_FILE
    scope, rotation, n_frisch, new_state = plan_scope(
        export_rows, shadow_rows, load_state(state_path), int(config.TRUTH_CHECK_ROTATION_N))

    # Abruf-Plan: frühestes benötigtes Datum je Ticker.
    need: dict = {}
    min_bt = None
    for datei, r in scope.values():
        t, d = r.get("ticker"), _dmy(r.get("date"))
        if not t or d is None or t in delisted:
            continue
        need[t] = min(need.get(t, d), d)
        if datei == "export":
            min_bt = d if min_bt is None else min(min_bt, d)
    starts = {t: d - timedelta(days=15) for t, d in need.items()}
    order = []
    if min_bt is not None:
        starts[SPY] = min_bt - timedelta(days=110)   # 50 Handelstage für das Regime
        starts[VIX] = min_bt - timedelta(days=10)
        order = [SPY, VIX]
    order += sorted(need)
    end = today + timedelta(days=2)
    series, unknown = fetch_all(order, starts, end, fetch_fn,
                                workers=int(config.TRUTH_CHECK_MAX_WORKERS))

    known = load_known(root / KNOWN_FILE)
    cnt = {"stimmt": 0, "abweichung": 0, "neu_adjustiert": 0, "bekannt": 0, "nicht_pruefbar": 0}
    unk = {k: 0 for k in UNKNOWN_REASONS}
    devs_all, max_d, n_cmp_total = [], None, 0
    runtime_notes: list = []
    recheck, retry = [], []
    for k, (datei, r) in scope.items():
        t = r.get("ticker")
        if t in delisted:
            cnt["nicht_pruefbar"] += 1
            continue
        if t in unknown:
            unk[unknown[t]] += 1
            if unknown[t] in ("yahoo_fehler", "rate_limit"):
                retry.append(k)
            continue
        s = series.get(t)
        rec = (recompute_shadow(r, s, final_cut) if datei == "exit_shadow"
               else recompute_backtest(r, s, series.get(SPY), series.get(VIX), final_cut, today))
        n_cmp, devs, md = compare_row(datei, r, rec, series, tol, notes=runtime_notes)
        devs = apply_known(devs, known, tol)
        n_cmp_total += n_cmp
        if n_cmp == 0:
            unk["ausdruecklich_leer"] += 1
            continue
        if md is not None:
            max_d = md if max_d is None else max(max_d, md)
        if any(d["klasse"] == "abweichung" for d in devs):
            cnt["abweichung"] += 1
        elif any(d["klasse"] == "bekannt" for d in devs):
            cnt["bekannt"] += 1
        elif devs:
            cnt["neu_adjustiert"] += 1
        else:
            cnt["stimmt"] += 1
        if devs:
            recheck.append(k)
            devs_all.extend(devs)

    # Score-Abgleich (Fix B / Wächter, Easy-Entscheid 14.11.2026): gespeicherter
    # Abend-Score je Postclose-Top-10-Zeile gegen Nachrechnung aus endgültigen
    # Kursen. Eigener Block; zählt NICHT in die Feld-Abweichungen oben.
    prev_state = load_state(state_path) or {}
    checked = set(prev_state.get("score_abgleich_abende") or [])
    try:
        import score_check
        sc_kwargs = {}
        if score_fetch is not None:
            sc_kwargs["fetch"] = score_fetch
        if score_rsi is not None:
            sc_kwargs["rsi_fn"] = score_rsi
        score_block, sc_done = score_check.run_score_check(
            _read_jsonl(root / "score_inflation_log.jsonl"), final_cut, checked, **sc_kwargs)
    except Exception as exc:  # noqa: BLE001 — nie den Wahrheits-Abgleich brechen
        score_block, sc_done = {"fehler": f"{type(exc).__name__}: {str(exc)[:120]}"}, []
    new_state["score_abgleich_abende"] = sorted(checked | set(sc_done))[-120:]

    new_state["recheck"] = recheck
    new_state["retry"] = retry[:MAX_RETRY_KEYS]
    new_state["last_run_ts"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    new_state["schema_v"] = SCHEMA_V
    line = {
        "schema_v": SCHEMA_V,
        "run_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_zeilen": len(scope),
        "n_frisch": n_frisch,
        **cnt,
        "unbekannt": unk,
        "felder_verglichen": n_cmp_total,
        "max_abs_delta": round(max_d, 4) if max_d is not None else None,
        "abweichungen": devs_all[:MAX_DEVIATIONS_LOGGED],
        "abweichungen_gekuerzt": max(0, len(devs_all) - MAX_DEVIATIONS_LOGGED),
        # Bestätigungen über die Laufzeit-Regel (vix_level/market_regime) mit
        # Spanne -- Beleg, dass kein Feld pauschal ausgenommen ist (Fix 10.11.2026).
        "laufzeit_regel": runtime_notes[:MAX_DEVIATIONS_LOGGED],
        "rotation": rotation,
        "ticker_geprueft": sorted(t for t in need),
        "ticker_unbekannt": {t: v for t, v in sorted(unknown.items()) if t in need},
        "rate_limit_abbruch": any(v == "rate_limit" for v in unknown.values()),
        "score_abgleich": score_block,
    }
    if write:
        with open(root / config.TRUTH_CHECK_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False, separators=(",", ":"),
                                default=str) + "\n")
        tmp = state_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(new_state, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, state_path)
    return line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--now", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = (datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now
           else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    line = run(now, write=not a.dry_run)
    u = line["unbekannt"]
    print(f"Wahrheits-Abgleich: {line['n_zeilen']} Zeilen · {line['stimmt']} stimmt · "
          f"{line['abweichung']} Abweichung · {line['neu_adjustiert']} neu-adjustiert · "
          f"{line['bekannt']} bekannt (geprüft) · "
          f"unbekannt Yahoo {u['yahoo_fehler']} / leer {u['ausdruecklich_leer']} / "
          f"Rate-Limit {u['rate_limit']} · nicht prüfbar {line['nicht_pruefbar']} · "
          f"max |Δ| {line['max_abs_delta']}")
    for d in line["abweichungen"]:
        print(f"  {d['klasse']}: {d['ticker']} {d['date']} {d['feld']} alt={d['alt']} neu={d['neu']}")
    sb = line.get("score_abgleich") or {}
    print(f"Score-Abgleich: {len(sb.get('abende') or [])} Abende · {sb.get('zeilen', 0)} Zeilen · "
          f"|Δ|≥0,5: {sb.get('abw_ab_05', 0)} · |Δ|≥0,05: {sb.get('abw_ab_005', 0)} · "
          f"Wechsel 70 (mit |Δ|≥0,5): {sb.get('wechsel70_mit_abw', 0)} · Info-Wechsel 70: "
          f"{sb.get('wechsel70_info', 0)} · max Rangwechsel {sb.get('rang_wechsel_max', 0)} · "
          f"Modell nicht reproduziert {sb.get('modell_nicht_reproduziert', 0)}"
          + (f" · Fehler {sb['fehler']}" if sb.get("fehler") else ""))
    return 0   # Befunde wertet S16 aus; der Lauf selbst bleibt grün.


if __name__ == "__main__":
    sys.exit(main())
