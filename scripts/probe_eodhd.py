#!/usr/bin/env python3
"""WEGWERF-PROBE EODHD-Abdeckung (read-only, nur Zählungen) — Easy-Auftrag 15.11.2026.

Gleiche Bauart wie ``probe_tiingo.py``; dieselben 140 verschwundenen Stammaktien
(Seeds wie dort, ``probe_tiingo.finra_lists``), dieselben Stichtage, dieselbe
Zählweise (``probe_tiingo.covered``: ≥ 80 % der ersten 10 Handelstage ab
Stichtag mit Schlusskurs).

ENTSCHEIDUNGSREGEL — VORAB FESTGELEGT (Easy 15.11.2026, nicht ändern):
  Anteil der 140 mit Kursen ab Stichtag ≥ 90 % → „bauen möglich“, sonst
  „nicht bauen“. Ist die Kontrolle (20 heute gelistete Aktien gegen yfinance,
  Kriterium wie Tiingo T3) ungültig → „ungültig“.

STUFE 1 (``--stufe 1``, ohne Bezahl-Tarif, ≤ 6 EODHD-Abrufe):
  E0  Schlüssel vorhanden ja/nein (nie ausgegeben); /api/user → NUR die Felder
      subscriptionType, dailyRateLimit, apiRequests, apiRequestsDate (keine
      Namen/E-Mail).
  E1  exchange-symbol-list/US (delisted=1, type=common_stock): Zeilen, Felder,
      Typen; Abgleich gegen ALLE verschwundenen FINRA-Kürzel je Jahr und gegen
      die 140 — Kürzel-Treffer und Kürzel+Name-Treffer (die Liste hat keine
      Zeiträume; wiederverwendete Kürzel lassen sich nur über den Namen trennen).
  E2  Kurs-Zugang aus echten Antworten: ein verschwundenes Stichproben-Symbol am
      Stichtag 2018, AAPL im Juli 2018 (Jahre zurück), AAPL letzte 10 Tage.
  Ausgabe ``weiter_zu_stufe_2`` nur wenn Listen-Quote der 140 ≥ 90 % UND der
  2018-Kursabruf des verschwundenen Symbols Zeilen liefert. Sonst MINI-STOPP.

STUFE 2 (``--stufe 2``, nur nach Stufe-1-Freigabe): Kurse für die 140 (T1),
  21 neu vergebene Kürzel (T2), Kontrolle 20 (T3) — und, weil das Tiingo-
  Artifact keine Einzelergebnisse enthält, dieselben 140 erneut bei Tiingo
  (Header-Auth, ≤ 45/h, dieselben Symbole → kein neues Monats-Symbol) für die
  Tabelle Tiingo vs. EODHD je Aktie. Vorher Kontingent-Prüfung über /api/user:
  reicht es nicht für alle 181 EODHD-Abrufe → Abbruch ohne Abruf (Exit 3).

SCHLÜSSEL: EODHD erwartet den Schlüssel als Query-Parameter ``api_token``. Die
URL wird NIE ausgegeben; Fehler werden nur mit dem Ausnahme-Typ geloggt; jede
Ausgabe läuft durch ``scrub`` (beide Schlüssel). Kein Ergebnisfeld, keine
Rendite — nur „Kurs vorhanden ja/nein“ und Zeilen-/Felderzählungen.
Ab ``PROBE_END`` no-op. Rückweg: Workflow + Skript + Test per Commit entfernen.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import probe_rueckrechnung as pr  # noqa: E402
import probe_tiingo as pt  # noqa: E402

PROBE_END = date(2026, 12, 31)
EODHD_BASE = "https://eodhd.com/api"
DECISION_MIN = pt.DECISION_MIN            # 0.90 — dieselbe Schwelle wie Tiingo
LIST_GATE_MIN = 0.90                      # Stufe-1-Gate: Listen-Quote der 140
STUFE1_MAX_CALLS = 6
STUFE2_EODHD_CALLS = len(pt.YEARS) * (pt.VANISHED_N + pt.REISSUED_N) + pt.CONTROL_N  # 181
QUOTA_RESERVE = 2
EODHD_PACE_S = 1.5
USER_FIELDS = ("subscriptionType", "dailyRateLimit", "apiRequests", "apiRequestsDate")
TIINGO_EXPECTED = (97, 140)               # Ergebnis Lauf 43626657445 (Reproduktions-Prüfung)

KEY = {"v": ""}
COUNT = {"eodhd": 0, "limit": STUFE1_MAX_CALLS}
OUT = {"p": ""}


class RateLimited(Exception):
    pass


def scrub(text) -> str:
    s = str(text)
    for k in (KEY["v"], pt.KEY["v"]):
        if k:
            s = s.replace(k, "***")
    return s


def log(msg):
    print("[eodhd_probe] " + scrub(msg), flush=True)


def write_out(result) -> None:
    if not OUT["p"]:
        return
    out = pathlib.Path(OUT["p"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(scrub(json.dumps(result, indent=1, default=str)), encoding="utf-8")


def section(result, key):
    result.setdefault("abschnitte_vollstaendig", []).append(key)
    log(f"ABSCHNITT {key} vollständig " + json.dumps(result.get(key), default=str))
    write_out(result)


def norm(sym) -> str:
    """Kürzel-Schreibweise vereinheitlichen: Großbuchstaben, Punkt/Schrägstrich/
    Leerzeichen → Strich, eine ``.US``-Endung entfernt."""
    s = (sym or "").strip().upper()
    if s.endswith(".US"):
        s = s[:-3]
    return pr.yf_symbol(s)


def eod_symbol(sym) -> str:
    return norm(sym) + ".US"


def eodhd_get(path, params, *, kind="json"):
    """(status, data). Schlüssel nur als Query-Parameter, URL wird nie ausgegeben."""
    if COUNT["eodhd"] >= COUNT["limit"]:
        raise RuntimeError("EODHD-Abrufbudget dieses Laufs erschöpft")
    import requests
    COUNT["eodhd"] += 1
    q = dict(params)
    q["api_token"] = KEY["v"]
    q.setdefault("fmt", "json")
    try:
        r = requests.get(f"{EODHD_BASE}/{path}", params=q, timeout=120)
    except Exception as exc:  # noqa: BLE001 — Meldung kann die URL enthalten → nur Typ
        time.sleep(EODHD_PACE_S)
        return f"netz:{type(exc).__name__}", None
    time.sleep(EODHD_PACE_S)
    if r.status_code == 429:
        raise RateLimited("EODHD HTTP 429")
    if r.status_code != 200:
        return f"http_{r.status_code}", None
    try:
        return "ok", r.json()
    except ValueError:
        return "kein_json", None


def user_info():
    st, data = eodhd_get("user", {})
    if st != "ok" or not isinstance(data, dict):
        return {"status": st}
    return {"status": st, **{k: data.get(k) for k in USER_FIELDS if k in data}}


def eod_rows(sym, start, end):
    st, data = eodhd_get(f"eod/{eod_symbol(sym)}", {"from": start.isoformat(),
                                                     "to": end.isoformat(), "period": "d"})
    if st != "ok":
        return st, []
    return ("ok", data) if isinstance(data, list) else ("unerwartet", [])


def row_summary(st, rows):
    return {"status": st, "zeilen": len(rows),
            "felder": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
            "erster_tag": rows[0].get("date") if rows else None,
            "letzter_tag": rows[-1].get("date") if rows else None}


def list_index(rows):
    """{norm(code): [name_key, …]} aus der EODHD-Liste."""
    idx = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        idx.setdefault(norm(r.get("Code")), []).append(pr.name_key(r.get("Name")))
    return idx


def match(sym, finra_name, idx):
    """(kuerzel_treffer, kuerzel_und_name_treffer)."""
    ent = idx.get(norm(sym))
    if not ent:
        return False, False
    nk = pr.name_key(finra_name)
    return True, bool(nk) and nk in ent


def finra_names(L):
    """Namen der Symbole am Stichtag (für den Kürzel+Name-Abgleich)."""
    bf = pr.get_file(L["base"]) or {}
    return {s: v.get("name") for s, v in bf.items()}


def stufe1(result, lists):
    result["E0"] = {"schluessel_vorhanden": True, "user": user_info()}
    section(result, "E0")
    st, rows = eodhd_get("exchange-symbol-list/US", {"delisted": "1", "type": "common_stock"})
    rows = rows if isinstance(rows, list) else []
    types, exch = {}, {}
    for r in rows:
        if isinstance(r, dict):
            types[str(r.get("Type"))] = types.get(str(r.get("Type")), 0) + 1
            exch[str(r.get("Exchange"))] = exch.get(str(r.get("Exchange")), 0) + 1
    idx = list_index(rows)
    e1 = {"status": st, "zeilen": len(rows),
          "felder": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
          "typen": types, "boersen": exch, "kuerzel_verschieden": len(idx), "je_jahr": {}}
    tot = {"alle": [0, 0, 0], "stichprobe": [0, 0, 0]}
    for y, L in lists.items():
        if L.get("datei_fehlt"):
            continue
        names = finra_names(L)
        rec = {}
        for key, syms in (("alle", L["verschwunden"]), ("stichprobe", L["stichprobe_v"])):
            k = kn = 0
            for s in syms:
                a, b = match(s, names.get(s), idx)
                k += a
                kn += b
            n = len(syms)
            rec[key] = {"n": n, "kuerzel": pr.wilson(k, n), "kuerzel_und_name": pr.wilson(kn, n)}
            tot[key][0] += k
            tot[key][1] += kn
            tot[key][2] += n
        e1["je_jahr"][str(y)] = rec
    for key, (k, kn, n) in tot.items():
        e1[f"gesamt_{key}"] = {"kuerzel": pr.wilson(k, n), "kuerzel_und_name": pr.wilson(kn, n)}
    result["E1"] = e1
    section(result, "E1")
    # E2 — Kurs-Zugang aus echten Antworten
    L18 = lists.get(2018) or {}
    probe_sym = next((s for s in L18.get("stichprobe_v", []) if norm(s) in idx), None)
    e2 = {"verschwunden_2018_symbol_in_liste": probe_sym is not None}
    if probe_sym and L18.get("base"):
        st2, rws = eod_rows(probe_sym, L18["base"] - timedelta(days=5), L18["base"] + timedelta(days=30))
        e2["verschwunden_2018"] = row_summary(st2, rws)
    base18 = L18.get("base") or date(2018, 7, 13)
    st3, rws3 = eod_rows("AAPL", base18 - timedelta(days=5), base18 + timedelta(days=30))
    e2["aapl_2018"] = row_summary(st3, rws3)
    today = datetime.now(timezone.utc).date()
    st4, rws4 = eod_rows("AAPL", today - timedelta(days=14), today)
    e2["aapl_aktuell"] = row_summary(st4, rws4)
    result["E2"] = e2
    section(result, "E2")
    result["E0"]["user_nach_stufe1"] = user_info()
    q = (e1.get("gesamt_stichprobe") or {}).get("kuerzel") or {}
    kurse_ok = bool((e2.get("verschwunden_2018") or {}).get("zeilen"))
    result["stufe1_gate"] = {
        "listen_quote_stichprobe": q.get("anteil"), "schwelle": LIST_GATE_MIN,
        "kurse_verschwunden_2018": kurse_ok,
        "weiter_zu_stufe_2": bool(q.get("anteil") is not None and q["anteil"] >= LIST_GATE_MIN
                                   and kurse_ok)}


def decide_label(k, n, ctrl_ok):
    d = pt.decide(k, n, ctrl_ok)
    if not ctrl_ok:
        return "ungültig"
    return {"bauen": "bauen möglich"}.get(d, "nicht bauen" if n > 0 else "unbestimmt")


def stufe2(result, lists, sdates):
    u = user_info()
    result["E0"] = {"schluessel_vorhanden": True, "user": u}
    try:
        rest = int(u.get("dailyRateLimit")) - int(u.get("apiRequests")) - QUOTA_RESERVE
    except (TypeError, ValueError):
        rest = None
    need = STUFE2_EODHD_CALLS + 1        # + 1 Listen-Abruf
    result["kontingent"] = {"rest": rest, "benoetigt": need}
    if rest is None or rest < need:
        raise RateLimited(f"Kontingent reicht nicht (Rest {rest}, benötigt {need}) — "
                          "kein Abruf, Easy entscheidet")
    COUNT["limit"] = COUNT["eodhd"] + STUFE2_EODHD_CALLS + 1
    # Liste erneut (1 Abruf, im Reserve-Puffer): Widerspruch „Liste kennt Kürzel,
    # Kurse fehlen“ je Aktie ausweisen, nicht glätten.
    _st, _rows = eodhd_get("exchange-symbol-list/US", {"delisted": "1", "type": "common_stock"})
    idx = list_index(_rows if isinstance(_rows, list) else [])
    # T3 Kontrolle (EODHD gegen yfinance), Kriterium wie Tiingo
    today = datetime.now(timezone.utc).date()
    last = max(d for d in sdates if d <= today)
    lf = pr.get_file(last)
    pop = [s for s, v in lf.items() if v["market"] in pr.LISTED_CODES and pr.is_stock(s, v["name"])]
    ctrl = pr.draw_sample(pop, 3, pt.CONTROL_N)
    start = today - timedelta(days=45)
    yfd = pr.yf_download([pr.yf_symbol(s) for s in ctrl], start, today, auto_adjust=False)
    ok = n = 0
    status = {}
    for s in ctrl:
        df = yfd.get(pr.yf_symbol(s))
        st, rows = eod_rows(s, start, today)
        status[st] = status.get(st, 0) + 1
        n += 1
        if st != "ok" or df is None or df is pr.BATCH_ERR:
            continue
        closes = {ts.date().isoformat(): float(c) for ts, c in df["Close"].dropna().items()}
        ok += pt.ctrl_match(rows, closes)
    ctrl_ok = ok >= pt.CTRL_MIN_OK
    result["T3"] = {"geprueft": n, "stimmt": ok, "status": status, "gueltig": ctrl_ok}
    section(result, "T3")
    # T1 + T2 (EODHD), dazu Tiingo erneut je Aktie
    pt.KEY["v"] = os.environ.get("TIINGO_API_KEY", "").strip()
    per, t1, t2 = [], {}, {}
    tot_e = tot_n = 0
    for y in pt.YEARS:
        L = lists.get(y) or {}
        if L.get("datei_fehlt"):
            continue
        base, later = L["base"], L["later"]
        res = {"geprueft": 0, "abgedeckt": 0, "status": {}, "volumen_plausibel": 0,
               "felder_roh_und_bereinigt": 0, "letzter_tag_vor_spaeter_plus_30": 0}
        for s in L["stichprobe_v"]:
            st, rows = eod_rows(s, base - timedelta(days=5), later + timedelta(days=60))
            res["geprueft"] += 1
            res["status"][st] = res["status"].get(st, 0) + 1
            cov = bool(st == "ok" and rows and pt.covered(rows, base))
            res["abgedeckt"] += cov
            if st == "ok" and rows:
                last_d = max(date.fromisoformat(str(r["date"])[:10]) for r in rows)
                res["letzter_tag_vor_spaeter_plus_30"] += last_d <= later + timedelta(days=30)
                res["felder_roh_und_bereinigt"] += all(k in rows[0] for k in ("close", "adjusted_close", "volume"))
                vols = [float(r.get("volume") or 0) for r in rows
                        if date.fromisoformat(str(r["date"])[:10]) >= base][:20]
                try:
                    adv = float(L["adv"].get(s))
                    res["volumen_plausibel"] += bool(vols) and adv > 0 and 0.2 <= (sum(vols) / len(vols)) / adv <= 5
                except (TypeError, ValueError):
                    pass
            t_st, t_cov = "nicht_abgefragt", None
            if pt.KEY["v"]:
                t_st, t_rows = pt.tiingo_prices(s, base - timedelta(days=5), later + timedelta(days=60))
                t_cov = bool(t_st == "ok" and t_rows and pt.covered(t_rows, base))
            per.append({"jahr": y, "symbol": s, "eodhd": cov, "eodhd_status": st,
                        "in_liste": norm(s) in idx, "tiingo": t_cov, "tiingo_status": t_st})
        res["abdeckung"] = pr.wilson(res["abgedeckt"], res["geprueft"])
        tot_e += res["abgedeckt"]
        tot_n += res["geprueft"]
        t1[str(y)] = res
        r2 = {"geprueft": 0, "status": {}, "zeitraum_ueber_stichtag": 0}
        for s in L["stichprobe_n"]:
            st, rows = eod_rows(s, base - timedelta(days=5), base + timedelta(days=30))
            r2["geprueft"] += 1
            r2["status"][st] = r2["status"].get(st, 0) + 1
            r2["zeitraum_ueber_stichtag"] += bool(st == "ok" and rows and pt.covered(rows, base))
        t2[str(y)] = r2
        result["T1_T2_teil_jahre"] = {"T1": dict(t1), "T2": dict(t2)}
        write_out(result)
    t1["gesamt"] = {"abdeckung": pr.wilson(tot_e, tot_n), "regel_min": DECISION_MIN,
                    "kontrolle_gueltig": ctrl_ok, "entscheidung": decide_label(tot_e, tot_n, ctrl_ok)}
    result["T1"], result["T2"] = t1, t2
    section(result, "T1")
    section(result, "T2")
    result["vergleich"] = vergleich(per)
    result["je_aktie"] = per
    section(result, "vergleich")


def vergleich(per):
    """Tabelle Tiingo vs. EODHD je Aktie (nur ja/nein-Zählungen)."""
    rows = [p for p in per if p["tiingo"] is not None]
    n = len(rows)
    both = sum(1 for p in rows if p["tiingo"] and p["eodhd"])
    only_e = sum(1 for p in rows if p["eodhd"] and not p["tiingo"])
    only_t = sum(1 for p in rows if p["tiingo"] and not p["eodhd"])
    none = sum(1 for p in rows if not p["tiingo"] and not p["eodhd"])
    t_miss = sum(1 for p in rows if not p["tiingo"])
    t_k = sum(1 for p in rows if p["tiingo"])
    in_list_no_px = sum(1 for p in per if p.get("in_liste") and not p["eodhd"])
    px_not_in_list = sum(1 for p in per if p["eodhd"] and not p.get("in_liste"))
    return {"widerspruch_liste_ja_kurse_nein": in_list_no_px,
            "widerspruch_kurse_ja_liste_nein": px_not_in_list,
            "n": n, "beide": both, "nur_eodhd": only_e, "nur_tiingo": only_t, "keiner": none,
            "tiingo_fehlt": t_miss, "davon_eodhd_liefert": only_e,
            "vereinigung": pr.wilson(both + only_e + only_t, n),
            "tiingo_reproduziert": (t_k, n) == TIINGO_EXPECTED,
            "tiingo_jetzt": [t_k, n], "tiingo_lauf_43626657445": list(TIINGO_EXPECTED)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stufe", choices=("1", "2"), required=True)
    args = ap.parse_args(argv)
    if datetime.now(timezone.utc).date() > PROBE_END:
        log(f"no-op: nach {PROBE_END}")
        return 0
    KEY["v"] = os.environ.get("EODHD_API_KEY", "").strip()
    vorhanden = "ja" if KEY["v"] else "nein"
    log(f"Secret EODHD_API_KEY vorhanden: {vorhanden}")
    if not KEY["v"]:
        log("ABBRUCH: Secret EODHD_API_KEY fehlt — Easy legt es an. Kein Abruf.")
        return 2
    OUT["p"] = args.out
    t0 = time.monotonic()
    result = {"stufe": args.stufe, "seed": pr.SEED, "regel_min": DECISION_MIN,
              "start_utc": datetime.now(timezone.utc).isoformat()}
    rc = 0
    try:
        sdates, lists = pt.finra_lists()
        result["finra"] = {str(y): ({"datei_fehlt": True} if L.get("datei_fehlt") else
                                    {"stichtag": str(L["base"]), "spaeter": str(L["later"]),
                                     "verschwunden": len(L["verschwunden"]),
                                     "stichprobe": len(L["stichprobe_v"]),
                                     "neu_vergeben_stichprobe": len(L["stichprobe_n"])})
                           for y, L in lists.items()}
        section(result, "finra")
        if args.stufe == "1":
            stufe1(result, lists)
        else:
            stufe2(result, lists, sdates)
    except (RateLimited, Exception) as exc:  # noqa: BLE001
        rc = 3 if isinstance(exc, (RateLimited, pt.RateLimited)) else 4
        result["abbruch_grund"] = scrub(f"{type(exc).__name__}: {str(exc)[:300]}")
        log(f"ABBRUCH — vollständig: {result.get('abschnitte_vollstaendig', [])}; "
            f"Grund: {result['abbruch_grund']}")
    result["anfragen_eodhd"] = COUNT["eodhd"]
    result["anfragen_tiingo"] = pt.COUNT["anfragen"]
    result["laufzeit_s"] = round(time.monotonic() - t0, 1)
    log("meta " + json.dumps({k: result[k] for k in ("anfragen_eodhd", "anfragen_tiingo", "laufzeit_s")}))
    if args.stufe == "1" and "stufe1_gate" in result:
        log("STUFE1_GATE " + json.dumps(result["stufe1_gate"]))
    write_out(result)
    log(f"{'abgebrochen' if rc else 'fertig'} → {args.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
