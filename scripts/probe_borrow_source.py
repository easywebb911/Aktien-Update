#!/usr/bin/env python3
"""WEGWERF-PROBE (read-only) — Borrow-Ersatzquelle nach iBorrowDesk-Tod (23.07.2026).

Läuft NUR im GitHub-Actions-Runner (Sandbox ist egress-deny-all). Misst zwei
Kandidaten für Cost-to-Borrow (CTB) + Verfügbarkeit:

  Kandidat 1 — IBKR Public Shortable-Stock-File (Ursprungsquelle, die iBorrowDesk
              aufbereitete). DISCOVERY-FIRST: erst die offiziellen Landing-Pages
              nach dem echten Download-Link absuchen, Fundweg dokumentieren; dann
              eine Kandidaten-Liste von Datei-URLs (https + ftp) messen.
  Kandidat 2 — stockanalysis.com short-interest-Seite (bereits integriert) —
              liefert sie heute noch CTB oder dauerhaft leer?

KEINE Secrets, KEINE Repo-Writes im Tool-Sinne (nur Artefakt-Dateien in OUT_DIR).
Fail-soft: nie raise, alles ins Log. stdlib-only (kein pip).
"""
from __future__ import annotations
import json
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error

# Globaler Socket-Default-Timeout — deckt auch socket.gethostbyname (DNS) ab,
# das keinen eigenen Timeout-Parameter hat (Guardian-Finding 2). urllib-Calls
# überschreiben das via explizitem timeout=-Argument.
socket.setdefaulttimeout(10)

OUT_DIR = os.environ.get("OUT_DIR", "./probe-out")
os.makedirs(OUT_DIR, exist_ok=True)

# Obergrenze für aus Discovery gesammelte Datei-Kandidaten (Guardian-Finding 1):
# verhindert, dass ein breiter Landing-Page-Link-Fund × 40s-Timeout den 8-min-
# Job-Timeout sprengt, BEVOR Kandidat 2 (stockanalysis) gemessen wird.
MAX_DISCOVERED_FILE_CANDIDATES = 10

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

# Universum: aktuelle Top-10 + historische hard-to-borrow (CTB>100) + Large-Cap-Gegenprobe.
TOP10 = ["AMCX", "BATL", "CSIQ", "INDI", "INR", "KUST", "PAR", "REPL", "SHPH", "SOC"]
HARD  = ["BJDX", "FXHO", "LFVN"]        # laut Backtest-Historie CTB>100 %/J
CTRL  = ["AAPL", "MSFT"]                # langweilige Large Caps → sollten billig sein
UNIVERSE = TOP10 + HARD + CTRL


def _log(*a):
    print(*a, flush=True)


def _get(url, timeout=30, want_bytes=False):
    """HTTP(S)/FTP GET, fail-soft. Returns (status, headers_dict, body_str_or_bytes, err)."""
    req = urllib.request.Request(url, headers=HDRS)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            dt = round((time.time() - t0) * 1000)
            status = getattr(r, "status", None) or r.getcode()
            hdrs = {k: v for k, v in r.headers.items()}
            body = raw if want_bytes else raw.decode("utf-8", "replace")
            return status, hdrs, body, None, dt, len(raw)
    except urllib.error.HTTPError as e:
        dt = round((time.time() - t0) * 1000)
        return e.code, dict(getattr(e, "headers", {}) or {}), "", f"HTTPError {e.code}", dt, 0
    except Exception as e:
        dt = round((time.time() - t0) * 1000)
        return None, {}, "", f"{type(e).__name__}: {e}", dt, 0


# ── Egress / DNS ─────────────────────────────────────────────────────────────
def egress_info():
    _log("=" * 70)
    _log("RUNNER EGRESS / DNS")
    _log("=" * 70)
    st, _, body, err, dt, _ = _get("https://api.ipify.org", timeout=8)
    _log(f"public IP: {body or err} ({dt} ms)")
    for h in ["www.interactivebrokers.com", "ftp3.interactivebrokers.com",
              "stockanalysis.com", "iborrowdesk.com"]:
        try:
            _log(f"DNS {h}: {socket.gethostbyname(h)}")
        except Exception as e:
            _log(f"DNS {h}: FAIL ({e})")


# ── Kandidat 1: Discovery ────────────────────────────────────────────────────
DISCOVERY_PAGES = [
    "https://www.interactivebrokers.com/en/trading/short-selling.php",
    "https://www.interactivebrokers.com/en/pricing/short-sale-cost.php",
    "https://www.interactivebrokers.com/en/index.php?f=46301",
]

def discovery():
    _log("=" * 70)
    _log("KANDIDAT 1 — IBKR DISCOVERY-FIRST (Landing-Pages nach Download-Link)")
    _log("=" * 70)
    found = set()
    for url in DISCOVERY_PAGES:
        st, hd, body, err, dt, sz = _get(url, timeout=25)
        _log(f"\n[discovery] {url}\n  status={st} bytes={sz} {dt}ms err={err}")
        if not body:
            continue
        # Links, die nach Short-Availability-Datei aussehen
        links = re.findall(r'href=["\']([^"\']+)["\']', body, re.IGNORECASE)
        cand = [l for l in links if re.search(
            r'(short|borrow|avail|usa\.txt|\.txt|ftp3|download)', l, re.IGNORECASE)]
        for l in cand:
            found.add(l)
        for l in sorted(set(cand))[:25]:
            _log(f"    link: {l}")
        # Direkte Erwähnung von ftp3/usa.txt im Klartext
        for m in re.findall(r'(ftp3\.interactivebrokers\.com[^\s"\'<>]*|usa\.txt)', body, re.IGNORECASE):
            found.add(m)
            _log(f"    mention: {m}")
    _log(f"\n[discovery] gesamt {len(found)} Kandidaten-Links/Mentions gesammelt.")
    return found


# ── Kandidat 1: Datei-Endpoints messen ───────────────────────────────────────
# CANDIDATES (zu verifizieren — NICHT als Wahrheit gesetzt). Der historisch
# dokumentierte, keyless-öffentliche IBKR-Short-Availability-Pfad ist ftp3/usa.txt;
# https-Spiegel + Alt-Pfade werden mitgemessen. Discovery oben kann weitere liefern.
FILE_CANDIDATES = [
    "https://www.interactivebrokers.com/en/index.php?f=2226",   # region/download page
    "https://ftp3.interactivebrokers.com/usa.txt",
    "http://ftp3.interactivebrokers.com/usa.txt",
    "ftp://ftp3.interactivebrokers.com/usa.txt",
    "ftp://shortstock:@ftp3.interactivebrokers.com/usa.txt",
]

def parse_ibkr_file(body: str):
    """IBKR-Shortable-File ist pipe-delimited. Header-Zeile trägt Timestamp,
    Spalten historisch: SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE.
    SPALTEN-basiert parsen (Header lesen), nicht Byte-Position."""
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return None, None, {}
    header_ts = lines[0]  # z.B. "#BOF USA|<ts>" o.ä. — roh zurückgeben
    # Spalten-Header suchen: Zeile die SYM und FEE/AVAILABLE nennt
    col_idx = None
    cols = None
    for l in lines[:5]:
        parts = [p.strip().upper() for p in l.split("|")]
        if any("SYM" in p for p in parts) and any("FEE" in p for p in parts):
            cols = parts
            break
    # Feld-Positionen bestimmen (falls Spalten-Header vorhanden)
    idx = {}
    if cols:
        for i, c in enumerate(cols):
            if "SYM" in c: idx["sym"] = i
            if "FEE" in c: idx["fee"] = i
            if "AVAIL" in c: idx["avail"] = i
            if "REBATE" in c: idx["rebate"] = i
    # Default-Positionen (historisches Schema) falls kein Spalten-Header:
    if "sym" not in idx:
        idx = {"sym": 0, "rebate": 5, "fee": 6, "avail": 7}
    table = {}
    for l in lines:
        if l.startswith("#"):
            continue
        parts = l.split("|")
        if len(parts) <= max(idx.values()):
            continue
        sym = parts[idx["sym"]].strip().upper()
        def g(k):
            try:
                return parts[idx[k]].strip()
            except Exception:
                return None
        table[sym] = {"fee": g("fee"), "avail": g("avail"), "rebate": g("rebate")}
    return header_ts, idx, table


def probe_ibkr_files(discovered):
    _log("=" * 70)
    _log("KANDIDAT 1 — IBKR DATEI-ENDPOINTS MESSEN")
    _log("=" * 70)
    # Discovery-Funde, die absolute URLs sind, mit aufnehmen
    urls = list(FILE_CANDIDATES)
    disc_abs = [d for d in discovered if d.startswith("http") or d.startswith("ftp")]
    if len(disc_abs) > MAX_DISCOVERED_FILE_CANDIDATES:
        _log(f"[file] {len(disc_abs)} Discovery-URLs gefunden — gekappt auf "
             f"{MAX_DISCOVERED_FILE_CANDIDATES} (Rest im Discovery-Log sichtbar).")
    urls.extend(disc_abs[:MAX_DISCOVERED_FILE_CANDIDATES])
    best = None
    for url in urls:
        want_ftp = url.startswith("ftp")
        st, hd, body, err, dt, sz = _get(url, timeout=40, want_bytes=False)
        lm = hd.get("Last-Modified") or hd.get("last-modified")
        date_h = hd.get("Date") or hd.get("date")
        _log(f"\n[file] {url}\n  status={st} bytes={sz} {dt}ms err={err}")
        _log(f"  Last-Modified={lm}  Date={date_h}")
        if body and sz > 200 and "|" in body[:2000]:
            with open(os.path.join(OUT_DIR, "ibkr_sample.txt"), "w") as f:
                f.write(body[:5000])
            hts, idx, table = parse_ibkr_file(body)
            _log(f"  HEADER/erste Zeile: {hts!r}")
            _log(f"  Spalten-Idx: {idx}  · geparste Symbole: {len(table)}")
            if table:
                best = (url, hts, lm, date_h, table)
                # erste 3 Zeilen roh zeigen (Format-Beleg)
                for l in body.splitlines()[:4]:
                    _log(f"    raw: {l[:160]}")
                break
    return best


def coverage_report(best):
    _log("=" * 70)
    _log("KANDIDAT 1 — ABDECKUNG + PLAUSIBILITÄT am echten Universum")
    _log("=" * 70)
    if not best:
        _log("KEINE IBKR-Datei erfolgreich geparst → keine Abdeckung messbar.")
        return
    url, hts, lm, date_h, table = best
    _log(f"Quelle: {url}")
    _log(f"Header/Timestamp-Zeile: {hts!r}")
    _log(f"HTTP Last-Modified: {lm} · Date: {date_h}")
    hits = 0
    for t in UNIVERSE:
        row = table.get(t.upper())
        tag = "TOP10" if t in TOP10 else ("HARD" if t in HARD else "CTRL")
        if row:
            hits += 1
            _log(f"  [{tag:5}] {t:6} fee={row.get('fee')}  avail={row.get('avail')}  rebate={row.get('rebate')}")
        else:
            _log(f"  [{tag:5}] {t:6} — nicht in Datei")
    _log(f"\nTrefferquote: {hits}/{len(UNIVERSE)}")
    _log("Plausibilitäts-Check: HARD-Ticker sollten teure Fee zeigen, CTRL (AAPL/MSFT) billig.")


# ── Kandidat 2: stockanalysis Re-Check ───────────────────────────────────────
def stockanalysis_recheck():
    _log("=" * 70)
    _log("KANDIDAT 2 — stockanalysis.com CTB-Re-Check (bereits integriert)")
    _log("=" * 70)
    patterns = [
        r'(?:Cost\s*to\s*Borrow|Borrow\s*Fee|CTB\s*Fee)[^<]*</t[dh]>\s*<t[dh][^>]*>\s*([\d.]+)\s*%',
        r'"costToBorrow"\s*:\s*([\d.]+)',
        r'"borrowFee"\s*:\s*([\d.]+)',
    ]
    hits = 0
    for t in TOP10 + HARD:   # Large Caps hier egal
        url = f"https://stockanalysis.com/stocks/{t.lower()}/short-interest/"
        st, hd, body, err, dt, sz = _get(url, timeout=12)
        ctb = None
        if body:
            for p in patterns:
                m = re.search(p, body, re.IGNORECASE)
                if m:
                    ctb = m.group(1)
                    break
        paywall = bool(body) and bool(re.search(r'(subscribe|upgrade to|Pro members|premium)', body, re.IGNORECASE))
        if ctb is not None:
            hits += 1
        _log(f"  {t:6} status={st} bytes={sz} CTB={ctb} paywall_marker={paywall} err={err}")
    _log(f"\nstockanalysis CTB-Treffer: {hits}/{len(TOP10)+len(HARD)}")


def main():
    _log("### WEGWERF-PROBE Borrow-Ersatzquelle — START")
    _log(f"Universum ({len(UNIVERSE)}): TOP10={TOP10} HARD={HARD} CTRL={CTRL}")
    egress_info()
    discovered = discovery()
    best = probe_ibkr_files(discovered)
    coverage_report(best)
    stockanalysis_recheck()
    # Maschinen-lesbares Kurz-Fazit ins Artefakt
    summary = {
        "ibkr_file_parsed": bool(best),
        "ibkr_source_url": best[0] if best else None,
        "ibkr_header_line": best[1] if best else None,
        "ibkr_last_modified": best[2] if best else None,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    _log("\n### WEGWERF-PROBE — ENDE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:   # fail-soft: Probe darf den Workflow nie rot machen
        _log(f"FATAL (fail-soft): {type(e).__name__}: {e}")
        sys.exit(0)
