#!/usr/bin/env python3
"""Read-only Machbarkeits-Probe: SSR-Flag (Short-Sale-Restriction, Reg-SHO Rule 201).

Läuft AUSSCHLIESSLICH auf dem GitHub-Actions-Runner (unrestricted egress) —
die interaktive Sandbox ist egress-deny-all (403 auf alle externen Hosts).
Keyless. KEINE Repo-Writes, KEINE Secrets. Höfliche Timeouts + UA. Misst die
fünf Fragen; Output komplett ins Run-Log + Artefakt.

WICHTIGE BEGRIFFS-TRENNUNG (muss der Befund klarstellen):
  • Rule 201 SSR  = Short-Sale-CIRCUIT-BREAKER: triggert bei −10% Intraday,
    gilt Rest des Tages + Folgetag. DAS wollen wir.
  • Rule 203 Reg-SHO THRESHOLD = persistente Fails-to-Deliver-Liste. Das ist
    die bekannte NasdaqTrader-„regsho/nasdaqth<date>.txt"-Datei — ein ANDERES
    Konstrukt. Die Probe misst beide und markiert die Trennung explizit.

Discovery-first (ablesen, nicht raten): Phase A holt Landing-Pages und liest
Download-Links per Regex ab; Phase B testet bekannte keyless Flat-Files
datumsfest über die letzten Handelstage; Phase C probiert SSR-Kandidaten.
"""
import json
import re
import sys
import time
import datetime as dt
import urllib.parse
import urllib.request
import urllib.error

UA = ("SqueezeReportSSRProbe/1.0 "
      "(https://github.com/easywebb911/Aktien-Update; easywebb@yahoo.de)")

# ── Kandidaten-Landing-Pages (Discovery: Download-Links ablesen) ─────────────
LANDING_PAGES = [
    ("cboe_ssr_page",
     "https://www.cboe.com/us/equities/market_statistics/short_sale_circuit_breaker/"),
    ("nasdaqtrader_regsho_index",
     "https://www.nasdaqtrader.com/Trader.aspx?id=RegSHOThreshold"),
    ("nyse_shortsales",
     "https://www.nyse.com/regulation/short-sales"),
    ("cboe_ssr_bzx_api",
     "https://www.cboe.com/us/equities/market_statistics/short_sale_circuit_breaker/BZX/"),
]

# ── Bekannte keyless Flat-Files: Reg-SHO THRESHOLD (Rule 203) — Format/Access-
#    Baseline + datumsfeste Adressierung (Q7). NICHT Rule 201, wird als solches
#    markiert. Templates mit {d}=YYYYMMDD. ─────────────────────────────────────
THRESHOLD_TEMPLATES = [
    ("nasdaq_threshold",   "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{d}.txt"),
    ("nasdaqbx_threshold", "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqbxth{d}.txt"),
    ("nasdaqpsx_threshold","https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqpsxth{d}.txt"),
    ("nyse_threshold",     "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nyseth{d}.txt"),
    ("nysemkt_threshold",  "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nysemktth{d}.txt"),
    ("nysearca_threshold", "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nysearcath{d}.txt"),
]

# ── Rule-201-SSR-KANDIDATEN (das eigentliche Ziel). Mehrere Shapes/Hosts —
#    der Runner meldet, welche 200 keyless liefern. {d}=YYYYMMDD, {dash}=YYYY-MM-DD.
SSR_TEMPLATES = [
    # Cboe Short Sale Circuit Breaker (stärkster Kandidat, je Venue BZX/BYX/EDGX/EDGA)
    ("cboe_bzx_ssr_csv",  "https://www.cboe.com/us/equities/market_statistics/short_sale_circuit_breaker/csv/?mkt=bzx&dt={dash}"),
    ("cboe_bzx_ssr_json", "https://www.cboe.com/us/equities/market_statistics/short_sale_circuit_breaker/json/?mkt=bzx&dt={dash}"),
    ("cboe_bzx_ssr_dated","https://www.cboe.com/us/equities/market_statistics/short_sale_circuit_breaker/BZX/{dash}/"),
    # NasdaqTrader — evtl. eigener SSR/Circuit-Breaker-Flat-File
    ("nasdaq_ssr_cb",     "https://www.nasdaqtrader.com/dynamic/symdir/shortsalecircuitbreaker/ssrcb{d}.txt"),
    ("nasdaq_ssr_alt",    "https://www.nasdaqtrader.com/dynamic/symdir/regsho/ssr{d}.txt"),
    # NYSE — API-Guess
    ("nyse_ssr_api",      "https://www.nyse.com/api/regulatory/short-sale-restrictions/download?selectedDate={dash}"),
]

_LINK_RE = re.compile(r'''href=["']([^"']+?\.(?:csv|txt|json|xlsx?))["']''', re.I)
_TICKER_RE = re.compile(r'\b[A-Z][A-Z0-9.\-]{0,5}\b')


def _get(url, timeout=25):
    """Return (status:int|str, headers:dict, body:bytes, secs:float). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(600_000)  # cap
            return r.status, dict(r.headers), body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, dict(getattr(e, "headers", {}) or {}), (e.read(4000) if hasattr(e, "read") else b""), time.time() - t0
    except Exception as e:
        return f"ERR:{type(e).__name__}:{str(e)[:80]}", {}, b"", time.time() - t0


def _recent_dates(n=12):
    """Letzte n Kalendertage (heute rückwärts) als (YYYYMMDD, YYYY-MM-DD).
    Wochenenden bewusst mitgeführt — der Runner meldet, welche Datei existiert
    (Handelstage). now() ist Runner-Wallclock (UTC)."""
    today = dt.datetime.now(dt.timezone.utc).date()
    out = []
    for i in range(n):
        d = today - dt.timedelta(days=i)
        out.append((d.strftime("%Y%m%d"), d.strftime("%Y-%m-%d")))
    return out


def _looks_texty(headers, body):
    ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    return ("text" in ct or "csv" in ct or "json" in ct
            or body[:1].isalpha() if body else False)


def _first_lines(body, n=6):
    try:
        txt = body.decode("utf-8", "replace")
    except Exception:
        return "<binary>"
    return "\n".join(txt.splitlines()[:n])


def _extract_tickers(body):
    """Grobe Ticker-Extraktion aus einem TXT/CSV-Body (Symbol-Spalte heuristisch)."""
    try:
        txt = body.decode("utf-8", "replace")
    except Exception:
        return set()
    toks = set()
    for line in txt.splitlines()[1:]:  # skip header
        parts = re.split(r'[|,;\t]', line.strip())
        if parts and parts[0]:
            cand = parts[0].strip().upper()
            if _TICKER_RE.fullmatch(cand):
                toks.add(cand)
    return toks


def phase_a_discovery():
    print("\n═══ PHASE A — Landing-Page-Discovery (Download-Links ablesen) ═══")
    found_links = {}
    for name, url in LANDING_PAGES:
        st, hd, body, took = _get(url)
        ct = hd.get("Content-Type", hd.get("content-type", "?"))
        print(f"\n[{name}] {url}")
        print(f"  → status={st}  ct={ct}  bytes={len(body)}  {took:.2f}s")
        if isinstance(st, int) and st == 200 and body:
            links = sorted(set(_LINK_RE.findall(body.decode('utf-8', 'replace'))))
            print(f"  → {len(links)} Daten-Link(s) im HTML:")
            for lk in links[:15]:
                print(f"      {lk}")
            found_links[name] = links
            # Snippet, das 'short sale'/'circuit'/'SSR' erwähnt
            txt = body.decode('utf-8', 'replace').lower()
            for kw in ("short sale circuit", "rule 201", "ssr", "restricted"):
                idx = txt.find(kw)
                if idx >= 0:
                    print(f"  → kw '{kw}' @{idx}: …{txt[idx:idx+90].strip()}…")
                    break
        time.sleep(0.6)
    return found_links


def phase_b_threshold(universe):
    print("\n═══ PHASE B — Reg-SHO THRESHOLD (Rule 203, NICHT SSR) — Baseline/Access/Q7 ═══")
    print("  (bekanntes keyless Flat-File-Format; misst Access + datumsfeste Adressierung)")
    dates = _recent_dates(12)
    per_venue_hits = {}
    for name, tmpl in THRESHOLD_TEMPLATES:
        print(f"\n[{name}] {tmpl}")
        resolved = 0
        for d, dash in dates:
            url = tmpl.format(d=d)
            st, hd, body, took = _get(url, timeout=20)
            if isinstance(st, int) and st == 200 and body and len(body) > 20:
                tks = _extract_tickers(body)
                ov = sorted(set(tks) & set(universe))
                if resolved == 0:
                    print(f"  ✓ {dash}: 200 ct={hd.get('Content-Type','?')} bytes={len(body)} "
                          f"lines={len(body.splitlines())} tickers~{len(tks)} overlap={len(ov)} {ov[:8]}")
                    print("    Kopf:\n      " + _first_lines(body, 4).replace("\n", "\n      "))
                resolved += 1
                per_venue_hits.setdefault(name, []).append((dash, len(tks), len(ov)))
            time.sleep(0.25)
        print(f"  → {resolved}/{len(dates)} Datumsdateien aufgelöst")
    return per_venue_hits


def phase_c_ssr(universe, discovered):
    print("\n═══ PHASE C — Rule-201-SSR-KANDIDATEN (das eigentliche Ziel) ═══")
    dates = _recent_dates(8)
    any_hit = False
    # C1: hardcodierte Template-Kandidaten
    for name, tmpl in SSR_TEMPLATES:
        print(f"\n[{name}] {tmpl}")
        shown = 0
        for d, dash in dates:
            url = tmpl.format(d=d, dash=dash)
            st, hd, body, took = _get(url, timeout=20)
            ok = isinstance(st, int) and st == 200 and body and len(body) > 20
            if ok and shown < 2:
                ct = hd.get("Content-Type", "?")
                tks = _extract_tickers(body)
                ov = sorted(set(tks) & set(universe))
                print(f"  ✓ {dash}: 200 ct={ct} bytes={len(body)} tickers~{len(tks)} "
                      f"overlap={len(ov)} {ov[:10]}")
                print("    Kopf:\n      " + _first_lines(body, 6).replace("\n", "\n      "))
                any_hit = True
                shown += 1
            elif shown == 0 and dash == dates[0][1]:
                print(f"  · {dash}: status={st} ct={hd.get('Content-Type','?')} bytes={len(body)}")
            time.sleep(0.25)
    # C2: aus Phase A entdeckte Links direkt testen
    print("\n[C2] Aus Phase-A-Discovery entdeckte Links testen:")
    tested = set()
    for src, links in (discovered or {}).items():
        for lk in links:
            full = lk if lk.startswith("http") else urllib.parse.urljoin(
                "https://www.cboe.com/", lk)
            if full in tested:
                continue
            tested.add(full)
            st, hd, body, took = _get(full, timeout=20)
            tks = _extract_tickers(body) if (isinstance(st, int) and st == 200) else set()
            ov = sorted(set(tks) & set(universe))
            print(f"  [{src}] {full}\n     → status={st} ct={hd.get('Content-Type','?')} "
                  f"bytes={len(body)} tickers~{len(tks)} overlap={len(ov)} {ov[:8]}")
            if isinstance(st, int) and st == 200 and body:
                print("     Kopf:\n       " + _first_lines(body, 5).replace("\n", "\n       "))
                any_hit = True
            time.sleep(0.4)
            if len(tested) >= 20:
                break
    return any_hit


def main(argv):
    uni_path = argv[1] if len(argv) > 1 else "scripts/diagnose/ssr_probe_universe.json"
    uni_doc = json.load(open(uni_path))
    universe = uni_doc.get("universe") or uni_doc
    now = dt.datetime.now(dt.timezone.utc)
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  SSR-Flag Machbarkeits-Probe (read-only, Runner-egress)            ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"Runner-UTC now: {now.isoformat()}  (Wochentag {now.strftime('%a')})")
    print(f"Universum: n={len(universe)}  (Top-10 + Watchlist + Recent-Sample)")
    print(f"  {universe}")
    print("\nERINNERUNG: Rule 201 SSR (−10% Circuit-Breaker) ≠ Rule 203 Threshold "
          "(FTD-Liste). Phase B misst Threshold (Access-Baseline), Phase C sucht "
          "das echte SSR-Konstrukt.")

    discovered = phase_a_discovery()
    thr = phase_b_threshold(universe)
    ssr_hit = phase_c_ssr(universe, discovered)

    print("\n═══ VERDIKT-ROHDATEN (Auswertung erfolgt im Chat) ═══")
    print(f"Q1 Quellen: Threshold-Venues aufgelöst = {sorted(thr.keys())}")
    print(f"Q1 SSR-Kandidat lieferte verwertbare Liste: {ssr_hit}")
    print("Q2 Timing: siehe Phase-B/C-Datums-Auflösung relativ zu Runner-UTC oben "
          "(heutiges Datum vorhanden? Zeilenzahl vs. Vortag).")
    print("Q3 Venue-Abdeckung: overlap-Zahlen je Venue oben.")
    print("Q4 Häufigkeit: overlap-Counts über die Datumsreihe (Phase B) / SSR (Phase C).")
    print("Q5 Feld-Format: Kopf-Zeilen je Liste oben — Spalten auf 'Trigger-Datum' "
          "vs. 'carry-over' prüfen.")
    print("\nFERTIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
