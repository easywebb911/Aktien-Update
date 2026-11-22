#!/usr/bin/env python3
"""Mock-Test Haiku-Sichtbarkeit (Easy-Entscheid 22.11.2026, Vorschlag A).

Belegt:
  (A) KEIN Score-Effekt: ``claude_sentiment_score`` liefert für dieselben
      (vorgetäuschten) API-Antworten exakt dieselben Rückgabewerte wie die
      Fassung auf origin/main (alt, aus git geladen) — 7 Fälle.
  (B) Unverändert: max_tokens, Modell, Prompt-Text, Parser, compute_signal.
  (C) Zähler je Lauf (Versuche/Erfolge), Reset je Lauf.
  (D) Rohantwort nur beim ERSTEN Parse-Fehler je Lauf, gekürzt, ohne Schlüssel.
  (E) provider_health-Zeile „ki_sentiment“ (bestehendes Schema), kein Alarm
      bei reinen Parse-Fehlern; Digest-Zeile.
Kein Netz, feste Eingaben.
"""
from __future__ import annotations

import importlib.util
import io
import logging
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from mock_test_ki_score_coverage_fix import ka  # noqa: E402  (installiert Stubs)
import health_check as hc  # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class _Resp:
    def __init__(self, code, payload=None, text=""):
        self.status_code = code
        self._p = payload
        self.text = text

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


def _msg(text):
    return {"content": [{"type": "text", "text": text}]}


CASES = [
    ("ok", _Resp(200, _msg('{"score": 12, "reason": "short"}'))),
    ("ok_fence", _Resp(200, _msg('```json\n{"score": 40, "reason": "x"}\n```'))),
    ("abgeschnitten", _Resp(200, _msg('{\n  "score": 8,\n  "reason": "The company reported'))),
    ("komma", _Resp(200, _msg('{"score": 5, "reason": "a "b" c"}'))),
    ("leer", _Resp(200, {"content": []})),
    ("http429", _Resp(429, None, "rate")),
    ("http500", _Resp(500, None, "boom")),
]
KEY = "test-key-zaehler-SECRET"


def _run(mod, resp):
    rq = sys.modules["requests"]
    orig_post = rq.post
    orig_env = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = KEY
    rq.post = lambda *a, **k: resp
    try:
        return mod.claude_sentiment_score("TST", ["eine Schlagzeile"])
    finally:
        rq.post = orig_post
        if orig_env is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = orig_env


# ── (A) alt gegen neu ────────────────────────────────────────────────────────
alt = None
try:
    src = subprocess.run(["git", "show", "origin/main:ki_agent.py"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp()) / "ki_agent_alt.py"
    tmp.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ki_agent_alt", tmp)
    alt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alt)
except Exception as exc:  # noqa: BLE001
    print(f"(alt nicht ladbar: {exc!r})")
if alt is not None and not hasattr(alt, "_KI_SENTIMENT_CALLS"):
    for name, resp in CASES:
        a = _run(alt, resp)
        n = _run(ka, resp)
        check(f"A {name}: Rückgabe alt == neu ({n})", a == n, f"alt={a} neu={n}")
else:
    print("HINWEIS: Vergleich alt/neu übersprungen (origin/main enthält den Nachtrag "
          "bereits oder ist nicht verfügbar) — Rückgabewerte unten direkt geprüft.")
exp = {"ok": (12, "short"), "ok_fence": (30, "x"), "abgeschnitten": (None, ""),
       "komma": (None, ""), "leer": (None, ""), "http429": (None, ""), "http500": (None, "")}
for name, resp in CASES:
    check(f"A' {name}: erwarteter Rückgabewert", _run(ka, resp) == exp[name], _run(ka, resp))

# ── (B) unverändert ─────────────────────────────────────────────────────────
import config  # noqa: E402
check("B1 max_tokens 50, Modell unverändert",
      config.KI_SENTIMENT_MAX_TOKENS == 50
      and config.KI_SENTIMENT_MODEL == "claude-haiku-4-5-20251001")
if alt is not None:
    import inspect
    sig = inspect.getsource(alt.compute_signal) == inspect.getsource(ka.compute_signal)
    check("B2 compute_signal byte-gleich zu origin/main", sig)
    old_src = inspect.getsource(alt.claude_sentiment_score)
    new_src = inspect.getsource(ka.claude_sentiment_score)
    for needle in ('"max_tokens": KI_SENTIMENT_MAX_TOKENS', '"model":      KI_SENTIMENT_MODEL',
                   'parsed = json.loads(text)', 'Antworte NUR mit', 'flags=re.MULTILINE'):
        check(f"B3 unverändert in claude_sentiment_score: {needle}",
              needle in new_src and new_src.count(needle) == old_src.count(needle))

# ── (C) Zähler ──────────────────────────────────────────────────────────────
ka._reset_tier3_accumulators()
for name, resp in CASES:
    _run(ka, resp)
c = ka._KI_SENTIMENT_CALLS
check("C1 Versuche 7, Erfolge 2", c["versuche"] == 7 and c["erfolg"] == 2, c)
check("C2 Fehlerarten gezählt (parse 3, rate 1, http 1)",
      ka._KI_SENTIMENT_ERROR_COUNTS["parse_error"] == 3
      and ka._KI_SENTIMENT_ERROR_COUNTS["rate_limit"] == 1
      and ka._KI_SENTIMENT_ERROR_COUNTS["http_other"] == 1)
ka._reset_tier3_accumulators()
check("C3 Reset je Lauf", ka._KI_SENTIMENT_CALLS == {"versuche": 0, "erfolg": 0,
                                                     "rohantwort_geloggt": False})
os.environ.pop("ANTHROPIC_API_KEY", None)
ka.claude_sentiment_score("TST", ["x"])
check("C4 ohne Schlüssel kein Versuch gezählt", ka._KI_SENTIMENT_CALLS["versuche"] == 0)

# ── (D) Rohantwort-Log ──────────────────────────────────────────────────────
buf = io.StringIO()
h = logging.StreamHandler(buf)
ka.log.addHandler(h)
try:
    ka._reset_tier3_accumulators()
    _run(ka, CASES[2][1])
    _run(ka, CASES[3][1])
finally:
    ka.log.removeHandler(h)
logtxt = buf.getvalue()
check("D1 Rohantwort genau einmal je Lauf", logtxt.count("Haiku-Rohantwort") == 1, logtxt)
check("D2 gekürzt auf ≤ 80 Zeichen, Anfang sichtbar", "'{\\n  \"score\": 8" in logtxt, logtxt)
check("D3 kein Schlüssel/Header im Log", KEY not in logtxt and "x-api-key" not in logtxt)

# ── (E) provider_health-Zeile + Digest ──────────────────────────────────────
ka._reset_tier3_accumulators()
check("E1 ohne Versuch keine Zeile", ka._ki_sentiment_provider_kwargs() is None)
for name, resp in CASES[:5]:
    _run(ka, resp)
kw = ka._ki_sentiment_provider_kwargs()
check("E2 Zeile: provider ki_sentiment, HTTP 200 (API erreicht), Erfolge 2, Fehlertext",
      kw["provider"] == "ki_sentiment" and kw["http_status"] == 200 and kw["item_count"] == 2
      and kw["error"] == "parse_error 3/5", kw)
ka._reset_tier3_accumulators()
_run(ka, CASES[5][1])
check("E3 nur Rate-Limit → http_status None (echter Ausfall bleibt sichtbar)",
      ka._ki_sentiment_provider_kwargs()["http_status"] is None)
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "ph.jsonl")
    hc.record_provider_call(**kw, path=p)
    rows = hc.read_all_provider(p)
    check("E4 Zeile im bestehenden Schema geschrieben",
          len(rows) == 1 and rows[0]["provider"] == "ki_sentiment"
          and rows[0]["schema_v"] == hc.SCHEMA_V_PROVIDER, rows)
    counters = {}
    fails = hc.aggregate_provider_fails(rows, counters, tier_map={}) if hasattr(
        hc, "aggregate_provider_fails") else []
    check("E5 reine Parse-Fehler lösen keinen Provider-Alarm aus",
          not any((f or {}).get("provider") == "ki_sentiment" for f in (fails or [])
                  if isinstance(f, dict)), fails)
rows2 = [{"provider": "ki_sentiment", "run_ts": "2026-11-22T11:34:45Z",
          "error": "parse_error 12/13", "item_count": 1},
         {"provider": "ki_sentiment", "run_ts": "2026-11-22T03:15:00Z",
          "error": "parse_error 11/12", "item_count": 1},
         {"provider": "edgar_8k", "run_ts": "2026-11-22T11:34:45Z"}]
line = hc.ki_sentiment_digest_line(rows2)
check("E6 Digest-Zeile", line == "🤖 Haiku: 12/13 Parse-Fehler (letzter Lauf 11:34 UTC) · "
      "24 h: 23/25 in 2 Läufen", line)
check("E7 Digest ohne Zeilen / kaputt wirft nicht",
      hc.ki_sentiment_digest_line([]).startswith("🤖 Haiku")
      and hc.ki_sentiment_digest_line(None).startswith("🤖 Haiku"))
dg = (ROOT / "scripts" / "health_check_digest.py").read_text(encoding="utf-8")
check("E8 Digest verdrahtet", "hc.ki_sentiment_digest_line(prov_entries)" in dg)

print()
if FAILS:
    print(f"FEHLER: {len(FAILS)} Test(s) rot: {FAILS}")
    sys.exit(1)
print("Alle Checks grün.")
