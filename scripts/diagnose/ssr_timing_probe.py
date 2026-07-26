#!/usr/bin/env python3
"""Read-only Timing-Probe: wann ist das Nasdaq-SSR-Tagesfile für Tag T final?

Runde 2 hat die echte Rule-201-SSR-Quelle lokalisiert:
  https://www.nasdaqtrader.com/dynamic/symdir/shorthalts/shorthalts<YYYYMMDD>.txt
  (CSV: Symbol,Security Name,Market Category,Trigger Time)

Offene Frage (Q2): liegt shorthalts<T>.txt zum Werktags-postclose (21:17 UTC)
schon VOLLSTÄNDIG vor — oder wächst es intraday und ist erst T+1 stabil?

Diese Probe feuert per `schedule` über den nächsten US-Handelstag zu mehreren
Zeitpunkten. Jeder Lauf snapshottet für die letzten Kalendertage: existiert die
Datei (echtes text/plain-CSV, NICHT die 200+HTML-Falle)? Zeilenzahl? früheste/
späteste `Trigger Time` im File? Aus der Zeitreihe (actual_utc → Zeilenzahl)
lesen wir ab, ab wann der Tag-T-Eintrag erscheint und aufhört zu wachsen.

Read-only, keyless, KEINE Secrets, KEINE Repo-Writes. Throwaway.
"""
import re
import sys
import time
import datetime as dt
import urllib.request
import urllib.error

UA = ("SqueezeReportSSRTimingProbe/1.0 "
      "(https://github.com/easywebb911/Aktien-Update; easywebb@yahoo.de)")
TMPL = "https://www.nasdaqtrader.com/dynamic/symdir/shorthalts/shorthalts{d}.txt"
CBOE = ("https://www-api.cboe.com/us/equities/market_statistics/"
        "short_sale_circuit_breakers/downloads/BatsCircuitBreakers{yr}.csv")


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(2_000_000), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, {}, b"", time.time() - t0
    except Exception as e:
        return f"ERR:{type(e).__name__}:{str(e)[:80]}", {}, b"", time.time() - t0


def _is_flat(headers, body):
    if not body or len(body) < 15:
        return False
    head = body[:400].lstrip().lower()
    if head.startswith(b"<!doctype") or b"<html" in head:
        return False
    ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    return "text/plain" in ct or "csv" in ct or b"," in body[:200]


def _trigger_span(body):
    """Früheste/späteste 'Trigger Time' (Spalte 4) im CSV — zeigt die Datums-
    Abdeckung innerhalb des Files (carry-over vs. heute)."""
    txt = body.decode("utf-8", "replace")
    stamps = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        # letzte Spalte ist die Trigger Time (Format 'M/D/YYYY H:MM:SS AM')
        cand = parts[-1].strip().strip('"')
        m = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cand)
        if m:
            stamps.append(m.group(1))
    if not stamps:
        return None, None, 0
    # deterministisch nach echtem Datum sortieren
    def _key(s):
        mo, da, yr = map(int, s.split("/"))
        return (yr, mo, da)
    stamps_sorted = sorted(set(stamps), key=_key)
    return stamps_sorted[0], stamps_sorted[-1], len(stamps)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  SSR Timing-Probe — Nasdaq shorthalts<date>.txt Finalität (Q2)     ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"ACTUAL Runner-UTC: {now.isoformat()}  ({now.strftime('%a')})")
    et = now - dt.timedelta(hours=4)  # grobe EDT-Näherung (Juli)
    print(f"~ET (UTC−4):       {et.isoformat()}  ({et.strftime('%a')})")
    print("Frage: existiert shorthalts<heute>.txt schon & wächst es noch?\n")

    for i in range(4):  # heute-UTC .. −3 Tage
        d = (now - dt.timedelta(days=i)).date()
        url = TMPL.format(d=d.strftime("%Y%m%d"))
        st, hd, body, took = _get(url)
        flat = _is_flat(hd, body)
        if flat:
            lines = len(body.decode("utf-8", "replace").splitlines())
            lo, hi, n = _trigger_span(body)
            print(f"[{d.isoformat()}] ✔ REAL  status={st} bytes={len(body)} "
                  f"zeilen={lines} trigger-daten n={n} span={lo}…{hi}  ({took:.2f}s)")
        else:
            print(f"[{d.isoformat()}] ·  status={st} flat=False bytes={len(body)} "
                  f"(nicht-existent / 200+HTML-Shell)  ({took:.2f}s)")
        time.sleep(0.3)

    # Cboe-Jahresarchiv als Finalitäts-Anker (Trigger/End/Rescinded-Dates)
    yr = now.year
    st, hd, body, took = _get(CBOE.format(yr=yr))
    if _is_flat(hd, body):
        lines = body.decode("utf-8", "replace").splitlines()
        print(f"\n[cboe {yr}] ✔ kumulativ status={st} bytes={len(body)} zeilen={len(lines)}")
        print("   Kopf: " + (lines[0] if lines else ""))
        print("   Letzte 3 Zeilen (neueste Trigger):")
        for ln in lines[-3:]:
            print("     " + ln)
    else:
        print(f"\n[cboe {yr}] · status={st} flat=False")

    print("\nFERTIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
