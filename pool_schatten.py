"""Pool-Schatten (Easy-Entscheid 21./22.11.2026).

Speichert je Postclose-Tag ALLE bewerteten Kandidaten (``enriched`` nach allen
Filtern, nach ``score()`` sortiert) still mit — nicht nur die 10 angezeigten.
Die Tagesliste ist sonst später nicht wiederherstellbar (Erkundungsfeld
geschlossen 18.11.2026: Kandidatenkreis nicht nachbildbar).

NUTZUNGSREGEL (open_item ``pool-schatten``, CLAUDE.md): Pool-Schatten ist
SUCHFELD. Zeilen mit ``top10 = true`` gehören NICHT dazu (Blindfenster-Daten),
ebenso wenig ``watchlist_bypass = true`` (haben die Filter nicht bestanden).
Auswertungen nur mit vorab festgeschriebener Regel; Folgekurse werden erst
geladen, wenn Easy eine Auswertung freigibt. Jeder Fund ist „Hinweis, kein
Beleg“ und braucht eine Bestätigung auf Top-10-Daten.

Eigenschaften:
* schreibt NUR ``pool_schatten/JJJJ-MM.jsonl`` (Monat des Berichtstags),
  Klartext, append-only (atomar: tmp + replace), stabile Reihenfolge (Rang);
* nur echte Postclose-Läufe: Wochenend-Sperre + Laufzeit-Gate des
  Vintage-Guards wie ``backtest_history._append_backtest_entries``; je Zeile
  wird der Vintage-Grund nur GEKENNZEICHNET (``vintage_zeile``), nicht verworfen;
* idempotent: steht der Berichtstag schon in der Monatsdatei, wird nichts
  geschrieben;
* keine Renditen, keine Folgekurse, KEIN Abruf, KEINE Neuberechnung — nur, was
  am Kandidaten-Objekt zum Schreibzeitpunkt vorliegt; unbekannt bleibt null;
* raise-frei (``run``): ein Fehler wird gemeldet, der Daily-Run läuft weiter;
* kein Konsument außer dem Health-Check-Digest (``digest_line``/``warn_line``).
"""
from __future__ import annotations

import json
import math
import os
import statistics
from datetime import date, datetime

SCHEMA_V = 2   # v2 (22.11.2026): cik + cik_grund je Zeile; v1-Zeilen bleiben gültig
POOL_SCHATTEN_DIR = "pool_schatten"
# Rangkontrolle: die Top-10 tragen einen zurückgerechneten Auswahl-Score
# (score_raw − finra_bonus_pts, score_raw auf 2 Nachkommastellen gerundet).
RANG_TOL = 0.01
# Merkmale: was am Objekt liegt, außer Anzeige-HTML, News-Listen und internen
# Schlüsseln; einzelne Werte über dieser Länge (JSON) werden ausgelassen und
# in ``merkmale_ausgelassen`` genannt (nie still).
MERKMAL_MAX_CHARS = 2000
MERKMAL_DENY = frozenset({"news", "card_html", "sparkline_view"})
# Datenschutz (Guardian-Hinweis 22.11.): die Datei ist öffentlich — Felder mit
# Positions-/Nutzerbezug werden nie geschrieben, auch wenn sie künftig am
# Kandidaten-Objekt auftauchen.
MERKMAL_DENY_PREFIXES = ("position", "entry_", "pnl", "token", "gist", "secret")
MERKMAL_DENY_EXACT = frozenset({"shares", "thesis", "lesson"})


# ── reine Helfer ─────────────────────────────────────────────────────────────
class _Unserializable(Exception):
    pass


def _clean(v):
    """JSON-taugliche Kopie; NaN/±Inf → None (unbekannt ≠ 0). Nicht abbildbare
    Typen → _Unserializable."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    # numpy-/pandas-Skalare ohne Import erkennen
    item = getattr(v, "item", None)
    if callable(item):
        try:
            return _clean(item())
        except Exception as exc:  # noqa: BLE001
            raise _Unserializable(type(v).__name__) from exc
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    raise _Unserializable(type(v).__name__)


def merkmale_of(c: dict) -> tuple[dict, list[str]]:
    """Alle am Kandidaten vorliegenden Werte (sortiert), ohne Neuberechnung."""
    out: dict = {}
    skipped: list[str] = []
    for k in sorted(str(x) for x in c.keys()):
        if (k in MERKMAL_DENY or k in MERKMAL_DENY_EXACT or k.startswith("_")
                or k.endswith("_html") or k.lower().startswith(MERKMAL_DENY_PREFIXES)):
            continue
        try:
            v = _clean(c[k])
            s = json.dumps(v, ensure_ascii=False, sort_keys=True)
        except (_Unserializable, TypeError, ValueError):
            skipped.append(f"{k}:typ")
            continue
        if len(s) > MERKMAL_MAX_CHARS:
            skipped.append(f"{k}:laenge")
            continue
        out[k] = v
    return out, skipped


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def selection_rule(enriched: list, top10: list, min_rvol: float) -> dict:
    """Bildet die Auswahlregel des Laufs nach (generate_report.py, geschützte
    Zone filter-top10-selection) — nur nachlesend, nichts wird ausgewählt.
    Liefert Tagesregel, Vorrang-Menge und ob die tatsächliche Top-10 dazu passt.
    """
    def _rv_ok(c) -> bool:
        # exakt wie im Lauf: c.get("rel_volume", 0) >= MIN_REL_VOLUME (NaN → False)
        try:
            return bool(c.get("rel_volume", 0) >= min_rvol)
        except TypeError:
            return False
    vol = [c for c in enriched if _rv_ok(c)]
    if len(enriched) < 3:
        regel, expected = "notnetz", list(enriched)
    elif len(vol) >= 10:
        regel, expected = "vorrang", vol[:10]
    else:
        regel, expected = "auffuellen", enriched[:10]
    exp_ids = {id(c) for c in expected}
    act_ids = {id(c) for c in top10}
    return {"regel": regel, "vorrang_ids": {id(c) for c in vol},
            "vorrang_n": len(vol), "konsistent": exp_ids == act_ids}


def score_auswahl(c: dict, in_top10: bool) -> tuple[float | None, str]:
    """Der Wert, nach dem ``enriched`` sortiert wurde (``score()``).

    Außerhalb der Top-10 unverändert ``c["score"]``. In der Top-10 wurde
    ``score`` danach verändert (FINRA-Bonus, Glättung, …); zurückgerechnet aus
    ``score_raw − finra_bonus_pts``. Bei Kappung auf 100 nicht rückrechenbar."""
    if not in_top10:
        return _num(c.get("score")), "direkt"
    raw = _num(c.get("score_raw"))
    bonus = _num(c.get("finra_bonus_pts"))
    if raw is None:
        return None, "fehlt"
    if bonus is None:
        bonus = 0.0
    if bonus > 0 and raw >= 100.0:
        return None, "nicht_rueckrechenbar"
    return round(raw - bonus, 4), ("zurueckgerechnet" if bonus > 0 else "score_raw")


def rang_check(rows: list[dict], tol: float = RANG_TOL) -> int:
    """Selbstkontrolle (Easy 22.11.): in Rangfolge muss score_auswahl
    nicht steigen. Setzt ``rang_konsistent`` je Zeile (None ohne Wert);
    gibt die Zahl inkonsistenter Zeilen zurück."""
    known = [(i, r["score_auswahl"]) for i, r in enumerate(rows)
             if r.get("score_auswahl") is not None]
    bad: set[int] = set()
    for (i, a), (j, b) in zip(known, known[1:]):
        if b > a + tol:
            bad.add(i)
            bad.add(j)
    for i, r in enumerate(rows):
        if r.get("score_auswahl") is None:
            r["rang_konsistent"] = None
        else:
            r["rang_konsistent"] = i not in bad
    return len(bad)


def _de_to_iso(report_date: str) -> str | None:
    try:
        return datetime.strptime(report_date, "%d.%m.%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def _default_cik_fn():
    """CIK aus dem im Lauf ohnehin gebauten Index von ``material_8k`` (kein
    Abruf). Rückgabe ``fn(ticker) -> (cik | None, grund | None)``."""
    import material_8k
    index, grund = material_8k.last_cik_index()

    def fn(ticker):
        if not index:
            return None, grund or "tickerliste_nicht_geladen"
        cik = material_8k.resolve_cik(ticker, index)
        return (cik, None) if cik else (None, "keine eindeutige CIK")
    return fn


def build_rows(enriched: list, top10: list, *, report_date: str, run_ts: str,
               code_sha: str | None, min_rvol: float, now_et,
               gate_fn, cik_fn=None) -> tuple[list[dict], dict]:
    """Zeilen für den Berichtstag; Reihenfolge = Rang (stabil)."""
    date_iso = _de_to_iso(report_date)
    if cik_fn is None:
        def cik_fn(_t):
            return None, "cik_nicht_ermittelt"
    rule = selection_rule(enriched, top10, min_rvol)
    top_pos = {id(c): i for i, c in enumerate(top10, start=1)}
    vorrang_rank: dict[int, int] = {}
    for c in enriched:
        if id(c) in rule["vorrang_ids"]:
            vorrang_rank[id(c)] = len(vorrang_rank) + 1
    rows: list[dict] = []
    for rang, c in enumerate(enriched, start=1):
        in_top = id(c) in top_pos
        sa, quelle = score_auswahl(c, in_top)
        try:
            act, grund = gate_fn(report_date, c.get("bar_date"), now_et)
        except Exception:  # noqa: BLE001
            act, grund = "append", "nicht_pruefbar"
        if act == "skip" and c.get("letzte_zeile") == "vortag_rueckfall":
            grund = "zeile_nicht_fuellbar"
        merk, ausgelassen = merkmale_of(c)
        try:
            cik, cik_grund = cik_fn(c.get("ticker"))
        except Exception as exc:  # noqa: BLE001
            cik, cik_grund = None, f"fehler:{type(exc).__name__}"
        rows.append({
            "schema_v": SCHEMA_V,
            "date": date_iso,
            "ticker": c.get("ticker"),
            "cik": cik,
            "cik_grund": cik_grund,
            "run_ts": run_ts,
            "code_sha": code_sha,
            "rang": rang,
            "rang_vorrang": vorrang_rank.get(id(c)),
            "pool_size": len(enriched),
            "rvol_vorrang": id(c) in rule["vorrang_ids"],
            "tag_regel": rule["regel"],
            "top10": in_top,
            "top10_regel": rule["regel"] if in_top else None,
            "top10_anzeige_rang": top_pos.get(id(c)),
            "top10_markierung_konsistent": rule["konsistent"],
            "score_auswahl": sa,
            "score_auswahl_quelle": quelle,
            "rang_konsistent": None,
            "watchlist_bypass": bool(c.get("manual_personal")),
            "price": _num(c.get("price")),
            "bar_date": c.get("bar_date"),
            "letzte_zeile": c.get("letzte_zeile"),
            "vintage_zeile": grund,
            "source": c.get("source"),
            "source_pools": _clean(c.get("source_pools")),
            "merkmale": merk,
            "merkmale_ausgelassen": ausgelassen,
        })
    n_bad = rang_check(rows)
    return rows, {"regel": rule["regel"], "vorrang_n": rule["vorrang_n"],
                  "top10_konsistent": rule["konsistent"], "rang_inkonsistent": n_bad}


def month_path(root, date_iso: str) -> str:
    return os.path.join(str(root), POOL_SCHATTEN_DIR, f"{date_iso[:7]}.jsonl")


def _read_jsonl(path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except FileNotFoundError:
        pass
    return out


def write_day(rows: list[dict], root) -> tuple[str, int]:
    """Hängt die Zeilen eines Tages an die Monatsdatei an (atomar). Steht der
    Tag schon drin → nichts schreiben. Wirft bei I/O-Fehlern (``run`` fängt)."""
    if not rows:
        return "leer", 0
    date_iso = rows[0]["date"]
    path = month_path(root, date_iso)
    if any(r.get("date") == date_iso for r in _read_jsonl(path)):
        return "schon_vorhanden", 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = b""
    if os.path.exists(path):
        with open(path, "rb") as fh:
            old = fh.read()
        if old and not old.endswith(b"\n"):
            old += b"\n"
    new = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                  for r in rows).encode("utf-8")
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(old + new)
    os.replace(tmp, path)
    return "geschrieben", len(rows)


def _default_gate():
    from backtest_history import _vintage_gate_decision  # lazy (pandas-frei im Test)
    return _vintage_gate_decision


def run(enriched, top10, *, report_date: str, root: str = ".",
        now_et=None, run_ts: str | None = None, code_sha: str | None = None,
        min_rvol: float | None = None, gate_fn=None, write_fn=None,
        cik_fn=None) -> dict:
    """Postclose-Hook. Raise nie: Fehler → ``status = fehler`` + Grund."""
    try:
        from zoneinfo import ZoneInfo
        if now_et is None:
            now_et = datetime.now(ZoneInfo("America/New_York"))
        if run_ts is None:
            run_ts = now_et.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        if min_rvol is None:
            from config import MIN_REL_VOLUME
            min_rvol = MIN_REL_VOLUME
        gate_fn = gate_fn or _default_gate()
        write_fn = write_fn or write_day
        date_iso = _de_to_iso(report_date)
        if date_iso is None:
            return {"status": "uebersprungen", "grund": "kein_berichtstag"}
        if date.fromisoformat(date_iso).weekday() >= 5:
            return {"status": "uebersprungen", "grund": "wochenende", "date": date_iso}
        act, grund = gate_fn(report_date, date_iso, now_et)
        if act == "skip":
            return {"status": "uebersprungen", "grund": grund, "date": date_iso}
        if cik_fn is None:
            try:
                cik_fn = _default_cik_fn()
            except Exception as exc:  # noqa: BLE001
                def cik_fn(_t, _g=f"fehler:{type(exc).__name__}"):
                    return None, _g
        rows, info = build_rows(list(enriched), list(top10), report_date=report_date,
                                run_ts=run_ts, code_sha=code_sha, min_rvol=min_rvol,
                                now_et=now_et, gate_fn=gate_fn, cik_fn=cik_fn)
        info["cik_null"] = sum(1 for r in rows if r.get("cik") is None)
        status, n = write_fn(rows, root)
        return {"status": status, "date": date_iso, "zeilen": n,
                "pool_size": len(rows), "top10": sum(1 for r in rows if r["top10"]),
                **info}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fehler", "grund": f"{type(exc).__name__}: {str(exc)[:160]}"}


def log_line(res: dict) -> str:
    st = res.get("status")
    if st in ("geschrieben", "schon_vorhanden"):
        txt = (f"[pool_schatten] {st} {res.get('date')}: {res.get('zeilen')} Zeilen "
               f"(pool_size {res.get('pool_size')}, Top-10 {res.get('top10')}, "
               f"Regel {res.get('regel')}, Vorrang {res.get('vorrang_n')})")
        if not res.get("top10_konsistent", True):
            txt += " ⚠ Top-10-Markierung passt nicht zur Auswahlregel"
        if res.get("rang_inkonsistent"):
            txt += f" ⚠ {res['rang_inkonsistent']} Zeilen rang_konsistent=false"
        if res.get("cik_null") is not None:
            txt += f" · CIK fehlt {res['cik_null']}"
        return txt
    return f"[pool_schatten] {st}: {res.get('grund')}"


def is_warning(res: dict) -> bool:
    return (res.get("status") == "fehler" or res.get("top10_konsistent") is False
            or bool(res.get("rang_inkonsistent")))


# ── Digest (einziger Konsument) ──────────────────────────────────────────────
def _all_rows(root) -> list[dict]:
    d = os.path.join(str(root), POOL_SCHATTEN_DIR)
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".jsonl"))
    except FileNotFoundError:
        return []
    rows: list[dict] = []
    for n in names:
        rows.extend(_read_jsonl(os.path.join(d, n)))
    return rows


def _fmt(d_iso: str) -> str:
    return f"{d_iso[8:10]}.{d_iso[5:7]}."


def digest_line(root) -> str:
    """„Pool-Schatten: läuft · letzter Tag · Zeilen · Kandidaten je Tag (Median)“."""
    try:
        rows = _all_rows(root)
        if not rows:
            return "🗂 Pool-Schatten: sammelt ab dem nächsten Postclose (noch keine Zeile)"
        per_day: dict[str, int] = {}
        for r in rows:
            d = r.get("date")
            if isinstance(d, str):
                per_day[d] = per_day.get(d, 0) + 1
        last = max(per_day)
        med = statistics.median(per_day.values())
        med_s = f"{med:.0f}" if float(med).is_integer() else f"{med:.1f}".replace(".", ",")
        txt = (f"🗂 Pool-Schatten: läuft · letzter Tag {_fmt(last)} · Zeilen {len(rows)} "
               f"· Kandidaten je Tag (Median) {med_s}")
        # CIK (schema_v ≥ 2, 22.11.2026): am letzten Tag ohne CIK, mit Gründen.
        day = [r for r in rows if r.get("date") == last and (r.get("schema_v") or 1) >= 2]
        if day:
            miss: dict[str, int] = {}
            for r in day:
                if r.get("cik") is None:
                    g = str(r.get("cik_grund") or "?")
                    miss[g] = miss.get(g, 0) + 1
            n_miss = sum(miss.values())
            txt += f" · CIK {len(day) - n_miss}/{len(day)}"
            if n_miss:
                txt += " (fehlt: " + ", ".join(f"{k} {v}" for k, v in
                                              sorted(miss.items(), key=lambda x: (-x[1], x[0]))) + ")"
        return txt
    except Exception:  # noqa: BLE001
        return "🗂 Pool-Schatten: Status nicht ermittelbar"


def warn_line(root, bh_path) -> str | None:
    """Warnung, wenn der jüngste Postclose-Tag (backtest_history) keine
    Pool-Zeilen hat — erst ab der ersten geschriebenen Zeile (vorher kein
    Fehlalarm für Tage vor dem Start)."""
    try:
        rows = _all_rows(root)
        days = {r.get("date") for r in rows if isinstance(r.get("date"), str)}
        if not days:
            return None
        with open(bh_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        bt = set()
        for e in data if isinstance(data, list) else []:
            if isinstance(e, dict) and not e.get("bootstrap"):
                iso = _de_to_iso(str(e.get("date", "")))
                if iso:
                    bt.add(iso)
        if not bt:
            return None
        last_bt = max(bt)
        if last_bt > max(days):
            return f"⚠️ Pool-Schatten: Postclose {_fmt(last_bt)} ohne Zeilen"
        return None
    except Exception:  # noqa: BLE001
        return None
