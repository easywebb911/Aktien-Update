#!/usr/bin/env python3
"""WEGWERF-PROBE Tiingo (read-only, nur Zählungen) — Easy-Entscheid 14.11.2026.

Frage: Liefert Tiingo (Gratis-Konto) Tageskurse für die US-Stammaktien, die laut
FINRA innerhalb von 12 Monaten nach einem Juli-Stichtag 2018–2024 verschwunden
sind (dieselben Symbole wie P2K der Rückrechnungs-Probe, Seed 20261114)? Wenn
ja (Entscheidungsregel unten, VORAB festgeschrieben), ist eine ehrliche
Rückrechnung ab 2018 möglich.

Gemessen (nur Verfügbarkeit / Zählungen, KEINE Rendite, KEIN Gipfel):
  T0  supported_tickers.zip (öffentliche Datei, ohne Schlüssel): wie viele ALLER
      verschwundenen Symbole kennt Tiingo mit einem Zeitraum über dem Stichtag?
  T1  Kursabruf für eine Stichprobe Verschwundener: Kursreihe ab Stichtag
      vorhanden (≥ 80 % der ersten 10 Handelstage), letzter Kurstag gegen das
      Verschwinden laut FINRA, Volumen-Plausibilität gegen FINRA-ADV (gleiches
      Papier?), Roh- und bereinigte Felder vorhanden.
  T2  neu vergebene Kürzel (FINRA: gleiches Kürzel, anderer Name): liefert
      Tiingo am Stichtag das ALTE Papier (Volumen-Plausibilität, Zeitraum)?
  T3  Kontrollgruppe heute gelisteter Stammaktien: Tiingo-Schlusskurs gegen
      yfinance (roh), Toleranz vorab festgeschrieben.

GRATIS-GRENZEN (Tiingo-Doku / -Blog, Stand 14.11.2026): 50 Anfragen je Stunde,
1 000 je Tag, 500 verschiedene Symbole je Monat, 1 GB je Monat; nur persönliche
Nutzung. Diese Probe macht höchstens ``MAX_REQUESTS`` Kursabrufe (verschiedene
Symbole) im Abstand von ``PACE_S`` Sekunden (≤ 45 je Stunde) — sicher innerhalb.

SCHLÜSSEL: nur aus der Umgebung (``TIINGO_API_KEY``), nur im Header
``Authorization: Token …``, nie in einer URL; jede Log-/Artifact-Ausgabe läuft
durch ``scrub``. Fehlt der Schlüssel → Exit 2 mit Hinweis, kein Abruf.
Rate-Limit (HTTP 429 oder „exceed“ im Text) → Abbruch (Exit 3); vollständig
abgeschlossene Abschnitte bleiben Befund. Kein automatischer Neustart.
Ab ``PROBE_END`` no-op. Wird nach der Auswertung per Cleanup-PR entfernt.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_rueckrechnung as pr  # noqa: E402

PROBE_END = date(2026, 12, 31)
YEARS = tuple(range(2018, 2025))
VANISHED_N = 20          # je Jahr, Teilmenge (die ersten 20) der P2K-Stichprobe (60, Seed y+700)
REISSUED_N = 3           # je Jahr, neu vergebene Kürzel (Seed y+800)
CONTROL_N = 20
MAX_REQUESTS = len(YEARS) * (VANISHED_N + REISSUED_N) + CONTROL_N   # 181 < 500 Symbole/Monat
PACE_S = 80.0            # ≤ 45 Anfragen je Stunde (Grenze 50)
WINDOW_TRADING_DAYS = 10
COVER_MIN_FRAC = 0.8
# ENTSCHEIDUNGSREGEL — VORAB FESTGESCHRIEBEN (14.11.2026):
# Abdeckung der Verschwundenen (T1, alle Jahre zusammen) ≥ 90 % → „bauen“;
# darunter → Zahlen + Optionen (Shumway-Schranken, kürzerer Zeitraum, andere Quelle).
DECISION_MIN = 0.90
# KONTROLLE — VORAB FESTGESCHRIEBEN: ein Symbol stimmt, wenn an ≥ 95 % der
# gemeinsamen Tage |Tiingo-close − yfinance-Close| / Close ≤ 0,5 %; die Kontrolle
# ist gültig, wenn ≥ 18 von 20 Symbolen stimmen.
CTRL_TOL = 0.005
CTRL_DAY_FRAC = 0.95
CTRL_MIN_OK = 18
TIINGO_PRICES = "https://api.tiingo.com/tiingo/daily/{t}/prices"
TIINGO_ZIP = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"

KEY = {"v": ""}
COUNT = {"anfragen": 0}
CURRENT = {"abschnitt": None}


class RateLimited(Exception):
    pass


def scrub(text) -> str:
    s = str(text)
    k = KEY["v"]
    return s.replace(k, "***") if k else s


def log(msg):
    print("[tiingo_probe] " + scrub(msg), flush=True)


def section_done(result, key):
    result.setdefault("abschnitte_vollstaendig", []).append(key)
    log(f"ABSCHNITT {key} vollständig " + json.dumps(result.get(key), default=str))


def tiingo_ticker(sym: str) -> str:
    return pr.yf_symbol(sym).lower()


def covered(rows, base: date) -> bool:
    """≥ 80 % der ersten 10 Handelstage ab Stichtag mit Schlusskurs."""
    days, d = [], base
    while len(days) < WINDOW_TRADING_DAYS:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    have = {r["date"][:10] for r in rows if r.get("close") is not None}
    return sum(1 for x in days if x.isoformat() in have) >= COVER_MIN_FRAC * WINDOW_TRADING_DAYS


def ctrl_match(tiingo_rows, yf_closes: dict) -> bool:
    common = [(float(r["close"]), yf_closes[r["date"][:10]]) for r in tiingo_rows
              if r.get("close") is not None and r["date"][:10] in yf_closes]
    if len(common) < 10:
        return False
    ok = sum(1 for a, b in common if b > 0 and abs(a - b) / b <= CTRL_TOL)
    return ok >= CTRL_DAY_FRAC * len(common)


def decide(k: int, n: int) -> str:
    if n <= 0:
        return "unbestimmt"
    return "bauen" if k / n >= DECISION_MIN else "nicht_bauen_in_dieser_form"


def tiingo_prices(sym, start, end):
    """(status, rows). Schlüssel nur im Header. Pacing ≤ 45/h."""
    if COUNT["anfragen"] >= MAX_REQUESTS:
        raise RuntimeError("MAX_REQUESTS erreicht — Probe-Budget erschöpft")
    import requests
    COUNT["anfragen"] += 1
    url = TIINGO_PRICES.format(t=tiingo_ticker(sym))
    try:
        r = requests.get(url, params={"startDate": start.isoformat(), "endDate": end.isoformat(),
                                      "format": "json"},
                         headers={"Authorization": f"Token {KEY['v']}",
                                  "Content-Type": "application/json"}, timeout=60)
    except Exception as exc:  # noqa: BLE001
        time.sleep(PACE_S)
        return f"netz:{type(exc).__name__}", []
    time.sleep(PACE_S)
    txt = r.text[:300].lower()
    if r.status_code == 429 or "exceed" in txt or "rate limit" in txt:
        raise RateLimited(f"Tiingo HTTP {r.status_code}: {scrub(r.text[:200])}")
    if r.status_code != 200:
        return f"http_{r.status_code}", []
    try:
        data = r.json()
    except ValueError:
        return "kein_json", []
    return ("ok", data) if isinstance(data, list) else ("unerwartet", [])


def finra_lists():
    """Verschwundene + neu vergebene Symbole je Jahr wie P2F/P2K der Rückrechnungs-Probe."""
    st, rows = pr.settlement_dates()
    sdates = sorted({date.fromisoformat(pr.pick(x, "date")[:10]) for x in rows
                     if pr.pick(x, "symbol") == "AAPL" and pr.pick(x, "date")})
    out = {}
    for y in YEARS:
        base = pr.first_on_or_after(sdates, date(y, 7, 1))
        later = pr.first_on_or_after(sdates, base + timedelta(days=365))
        bf, lf = pr.get_file(base), pr.get_file(later)
        if not bf or not lf:
            out[y] = {"datei_fehlt": True}
            continue
        uni = {s: v for s, v in bf.items() if v["market"] in pr.LISTED_CODES and pr.is_stock(s, v["name"])}
        names = {}
        for s, v in lf.items():
            if pr.is_stock(s, v["name"]):
                names.setdefault(pr.name_key(v["name"]), set()).add(s)
        fates = {s: pr.fate(s, v, lf, names) for s, v in uni.items()}
        van = sorted(s for s, f in fates.items() if f == "verschwunden")
        reis = sorted(s for s, f in fates.items() if f == "neu_vergeben")
        out[y] = {"base": base, "later": later, "verschwunden": van, "neu_vergeben": reis,
                  "adv": {s: uni[s]["adv"] for s in uni},
                  "stichprobe_v": pr.draw_sample(van, y + 700, 60)[:VANISHED_N],
                  "stichprobe_n": pr.draw_sample(reis, y + 800, REISSUED_N)}
    return sdates, out


def probe_t0(result, lists):
    import requests
    r = requests.get(TIINGO_ZIP, timeout=120)
    t0 = {"http": r.status_code, "bytes": len(r.content or b"")}
    if r.status_code != 200:
        result["T0"] = t0
        return
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = zf.namelist()[0]
    import csv
    known = {}
    for row in csv.DictReader(io.TextIOWrapper(zf.open(name), encoding="utf-8")):
        t = (row.get("ticker") or "").lower()
        known.setdefault(t, []).append((row.get("exchange"), row.get("assetType"),
                                        row.get("startDate"), row.get("endDate")))
    t0["zeilen"] = sum(len(v) for v in known.values())
    t0["spalten"] = list(csv.DictReader(io.TextIOWrapper(zf.open(name), encoding="utf-8")).fieldnames or [])
    per = {}
    for y, L in lists.items():
        if L.get("datei_fehlt"):
            continue
        base = L["base"].isoformat()
        k_any = k_span = 0
        for s in L["verschwunden"]:
            ent = known.get(tiingo_ticker(s), [])
            k_any += bool(ent)
            k_span += any((a or "") <= base <= (b or "9999") and a for _, _, a, b in ent)
        n = len(L["verschwunden"])
        per[str(y)] = {"verschwunden": n, "kuerzel_bekannt": pr.wilson(k_any, n),
                       "zeitraum_ueber_stichtag": pr.wilson(k_span, n)}
    t0["je_jahr"] = per
    result["T0"] = t0


def probe_t1_t2(result, lists):
    t1, t2 = {}, {}
    tot_k = tot_n = 0
    for y, L in lists.items():
        if L.get("datei_fehlt"):
            continue
        base, later = L["base"], L["later"]
        res = {"geprueft": 0, "abgedeckt": 0, "status": {}, "letzter_tag_vor_spaeter_plus_30": 0,
               "volumen_plausibel": 0, "felder_roh_und_bereinigt": 0}
        for s in L["stichprobe_v"]:
            st, rows = tiingo_prices(s, base - timedelta(days=5), later + timedelta(days=60))
            res["geprueft"] += 1
            res["status"][st] = res["status"].get(st, 0) + 1
            if st != "ok" or not rows:
                continue
            cov = covered(rows, base)
            res["abgedeckt"] += cov
            last = max(date.fromisoformat(r["date"][:10]) for r in rows)
            res["letzter_tag_vor_spaeter_plus_30"] += last <= later + timedelta(days=30)
            res["felder_roh_und_bereinigt"] += all(k in rows[0] for k in ("close", "adjClose", "volume",
                                                                          "adjVolume", "splitFactor"))
            vols = [float(r["volume"]) for r in rows if date.fromisoformat(r["date"][:10]) >= base][:20]
            adv = L["adv"].get(s)
            try:
                adv = float(adv)
                res["volumen_plausibel"] += bool(vols) and adv > 0 and 0.2 <= (sum(vols) / len(vols)) / adv <= 5
            except (TypeError, ValueError):
                pass
        res["abdeckung"] = pr.wilson(res["abgedeckt"], res["geprueft"])
        tot_k += res["abgedeckt"]
        tot_n += res["geprueft"]
        t1[str(y)] = res
        log(f"T1 {y}: {json.dumps(res, default=str)}")
        r2 = {"geprueft": 0, "status": {}, "zeitraum_ueber_stichtag": 0, "volumen_plausibel_altes_papier": 0}
        for s in L["stichprobe_n"]:
            st, rows = tiingo_prices(s, base - timedelta(days=5), base + timedelta(days=30))
            r2["geprueft"] += 1
            r2["status"][st] = r2["status"].get(st, 0) + 1
            if st != "ok" or not rows:
                continue
            r2["zeitraum_ueber_stichtag"] += covered(rows, base)
            vols = [float(r["volume"]) for r in rows if date.fromisoformat(r["date"][:10]) >= base][:20]
            try:
                adv = float(L["adv"].get(s))
                r2["volumen_plausibel_altes_papier"] += bool(vols) and adv > 0 and \
                    0.2 <= (sum(vols) / len(vols)) / adv <= 5
            except (TypeError, ValueError):
                pass
        t2[str(y)] = r2
    t1["gesamt"] = {"abdeckung": pr.wilson(tot_k, tot_n), "entscheidung": decide(tot_k, tot_n),
                    "regel_min": DECISION_MIN}
    result["T1"] = t1
    result["T2"] = t2


def probe_t3(result, sdates):
    today = datetime.now(timezone.utc).date()
    last = max(d for d in sdates if d <= today)
    lf = pr.get_file(last)
    pop = [s for s, v in lf.items() if v["market"] in pr.LISTED_CODES and pr.is_stock(s, v["name"])]
    ctrl = pr.draw_sample(pop, 3, CONTROL_N)
    start = today - timedelta(days=45)
    yfd = pr.yf_download([pr.yf_symbol(s) for s in ctrl], start, today, auto_adjust=False)
    ok = n = 0
    status = {}
    for s in ctrl:
        df = yfd.get(pr.yf_symbol(s))
        st, rows = tiingo_prices(s, start, today)
        status[st] = status.get(st, 0) + 1
        n += 1
        if st != "ok" or df is None or df is pr.BATCH_ERR:
            continue
        closes = {ts.date().isoformat(): float(c) for ts, c in df["Close"].dropna().items()}
        ok += ctrl_match(rows, closes)
    result["T3"] = {"geprueft": n, "stimmt": ok, "status": status, "gueltig": ok >= CTRL_MIN_OK,
                    "kriterium": f"≥ {CTRL_MIN_OK}/{CONTROL_N} Symbole; je Symbol ≥ {CTRL_DAY_FRAC:.0%} der Tage "
                                 f"mit |Δ| ≤ {CTRL_TOL:.1%}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if datetime.now(timezone.utc).date() > PROBE_END:
        log(f"no-op: nach {PROBE_END}")
        return 0
    KEY["v"] = os.environ.get("TIINGO_API_KEY", "").strip()
    if not KEY["v"]:
        log("ABBRUCH: Secret TIINGO_API_KEY fehlt oder ist leer — Easy legt es unter "
            "Settings → Secrets and variables → Actions an. Kein Abruf.")
        return 2
    t0 = time.monotonic()
    result = {"seed": pr.SEED, "max_anfragen": MAX_REQUESTS, "takt_s": PACE_S,
              "regel_min": DECISION_MIN, "start_utc": datetime.now(timezone.utc).isoformat()}
    rc = 0
    try:
        CURRENT["abschnitt"] = "FINRA"
        sdates, lists = finra_lists()
        result["finra"] = {str(y): ({"datei_fehlt": True} if L.get("datei_fehlt") else
                                    {"stichtag": str(L["base"]), "spaeter": str(L["later"]),
                                     "verschwunden": len(L["verschwunden"]),
                                     "neu_vergeben": len(L["neu_vergeben"])}) for y, L in lists.items()}
        section_done(result, "finra")
        CURRENT["abschnitt"] = "T0"
        probe_t0(result, lists)
        section_done(result, "T0")
        CURRENT["abschnitt"] = "T3"
        probe_t3(result, sdates)
        section_done(result, "T3")
        CURRENT["abschnitt"] = "T1"
        probe_t1_t2(result, lists)
        section_done(result, "T1")
        section_done(result, "T2")
    except (RateLimited, Exception) as exc:  # noqa: BLE001
        rc = 3 if isinstance(exc, RateLimited) else 4
        result["abgebrochen_in"] = CURRENT["abschnitt"]
        result["abbruch_grund"] = scrub(f"{type(exc).__name__}: {str(exc)[:300]}")
        for k in ("finra", "T0", "T1", "T2", "T3"):
            if k not in result.get("abschnitte_vollstaendig", []):
                result.pop(k, None)
        log(f"ABBRUCH in {CURRENT['abschnitt']} — nicht gezählt; vollständig: "
            f"{result.get('abschnitte_vollstaendig', [])}; Grund: {result['abbruch_grund']}")
    result["anfragen_tiingo"] = COUNT["anfragen"]
    result["laufzeit_s"] = round(time.monotonic() - t0, 1)
    log(f"meta {json.dumps({'anfragen_tiingo': COUNT['anfragen'], 'laufzeit_s': result['laufzeit_s']})}")
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(scrub(json.dumps(result, indent=1, default=str)), encoding="utf-8")
    log(f"{'abgebrochen' if rc else 'fertig'} → {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
