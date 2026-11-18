#!/usr/bin/env python3
"""Mock-Test EDGAR Fix (a) (Easy-Entscheid 17./18.11.2026).

  1  SEC_HEADERS-User-Agent kommt aus dem Secret EDGAR_USER_AGENT (Rückfall
     Platzhalter), keine feste Kontaktadresse im Quelltext
  2  fehlgeschlagener SEC-Abruf (HTTP 400 wie am 16.11.2026) → None und der
     Fehlergrund landet im Provider-Akkumulator (first-fail-wins)
  3  Ausnahme (Timeout) → None, Grund mit Ausnahme-Typ
  4  HTTP 200 ohne Einträge → (False, "", None), kein Fehlergrund
  5  Form 4 analog
  6  Provider-Fehler setzt sec_ok False; Lauf-Warnung je EDGAR-Quelle
Kein Netz (requests.get wird ersetzt).
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from unittest import mock

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []
FALLBACK_UA = "Squeeze Report contact" + "@" + "example.com"
TEST_UA = "Testlauf Kennung-123"


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def _ua(env_val):
    env = {k: v for k, v in os.environ.items() if k != "EDGAR_USER_AGENT"}
    if env_val is not None:
        env["EDGAR_USER_AGENT"] = env_val
    r = subprocess.run([sys.executable, "-c", "import config; print(config.SEC_HEADERS['User-Agent'])"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    return r.stdout.strip()


# 1 User-Agent aus dem Secret
check(_ua(TEST_UA) == TEST_UA, "UA aus EDGAR_USER_AGENT")
check(_ua(None) == FALLBACK_UA, "ohne Secret: Platzhalter")
check(_ua("") == FALLBACK_UA, "leeres Secret: Platzhalter")
_cfg = (ROOT / "config.py").read_text(encoding="utf-8")
_i = _cfg.index("SEC_HEADERS    =")
_blk = _cfg[_i:_i + 200]
_fixed = [a for a in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", _blk) if not a.endswith("example.com")]
check('os.environ.get("EDGAR_USER_AGENT")' in _blk and not _fixed,
      "config.SEC_HEADERS: keine feste Adresse außer dem Platzhalter")
for wf, step in ((".github/workflows/ki_agent.yml", "Run KI-Agent"),
                 (".github/workflows/daily-squeeze-report.yml", "Generate squeeze report")):
    d = yaml.safe_load((ROOT / wf).read_text(encoding="utf-8"))
    steps = [s for j in d["jobs"].values() for s in j["steps"] if s.get("name") == step]
    check(len(steps) == 1 and steps[0].get("env", {}).get("EDGAR_USER_AGENT") == "${{ secrets.EDGAR_USER_AGENT }}",
          f"{wf}: Schritt '{step}' setzt EDGAR_USER_AGENT")

import types  # noqa: E402


def _install_stubs():
    """Saubere CI-Umgebung (nur jinja2 + pyyaml): pandas/requests/yfinance stubben."""
    if "pandas" not in sys.modules:
        try:
            import pandas  # noqa: F401
        except ImportError:
            sys.modules["pandas"] = types.ModuleType("pandas")
    try:
        import requests  # noqa: F401
    except ImportError:
        rq = types.ModuleType("requests")
        rq.get = lambda *a, **k: None
        rq.post = lambda *a, **k: None
        exc = types.ModuleType("requests.exceptions")

        class _ReqExc(Exception):
            pass

        class Timeout(_ReqExc):
            pass
        exc.RequestException, exc.Timeout = _ReqExc, Timeout
        rq.exceptions = exc
        rq.RequestException, rq.Timeout = _ReqExc, Timeout
        sys.modules["requests"] = rq
        sys.modules["requests.exceptions"] = exc
    if "yfinance" not in sys.modules:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            yf = types.ModuleType("yfinance")
            yf.download = lambda *a, **k: None
            yf.Ticker = lambda *a, **k: None
            sys.modules["yfinance"] = yf


_install_stubs()
import ki_agent as ka  # noqa: E402


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


FEED_EMPTY = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

# 2 HTTP 400
ka._reset_tier3_accumulators()
with mock.patch.object(ka.requests, "get",
                       return_value=_Resp(400, "Invalid count, Received: 5,\n Count must be one of: 10, 20")), \
     mock.patch.object(ka.time, "sleep"):
    r1 = ka.fetch_sec_8k("AAPL")
    r2 = ka.fetch_sec_8k("MSFT")
err = ka._EDGAR_8K_ACCT.get("last_error_repr") or ""
check(r1 is None and r2 is None, "HTTP 400 → None (Provider-Fehler)")
check(err.startswith("HTTP 400: Invalid count, Received: 5, Count must be one of")
      and err.endswith("(erster Fehler: AAPL)"),
      f"Fehlergrund im Akkumulator, erster gewinnt: {err!r}")

# 3 Ausnahme
ka._reset_tier3_accumulators()
with mock.patch.object(ka.requests, "get", side_effect=ka.requests.exceptions.Timeout("read timeout")), \
     mock.patch.object(ka.time, "sleep"):
    r3 = ka.fetch_sec_8k("IONQ")
check(r3 is None and (ka._EDGAR_8K_ACCT["last_error_repr"] or "").startswith("Timeout: read timeout"),
      f"Timeout → None + Grund: {ka._EDGAR_8K_ACCT['last_error_repr']!r}")

# 4 legitim leer
ka._reset_tier3_accumulators()
with mock.patch.object(ka.requests, "get", return_value=_Resp(200, FEED_EMPTY)), \
     mock.patch.object(ka.time, "sleep"):
    r4 = ka.fetch_sec_8k("AAPL")
check(r4 == (False, "", None) and ka._EDGAR_8K_ACCT["last_error_repr"] is None,
      "HTTP 200 ohne Eintrag → (False, '', None), kein Fehlergrund")

# 5 Form 4
ka._reset_tier3_accumulators()
with mock.patch.object(ka.requests, "get", return_value=_Resp(403, "")), mock.patch.object(ka.time, "sleep"):
    r5 = ka.fetch_sec_form4("AAPL")
check(r5 is None and ka._EDGAR_FORM4_ACCT["last_error_repr"] == "HTTP 403 (erster Fehler: AAPL)"
      and ka._EDGAR_8K_ACCT["last_error_repr"] is None,
      f"Form 4: 403 → None, Grund nur im Form-4-Akkumulator ({ka._EDGAR_FORM4_ACCT['last_error_repr']!r})")

# 6 sec_ok + Lauf-Warnung (Quelltext)
src = (ROOT / "ki_agent.py").read_text(encoding="utf-8")
blk8 = src[src.index("_EDGAR_8K_ACCT, fetch_sec_8k, ticker,"):][:600]
check(re.search(r"if _r is None:\s*(#.*\n\s*)*sec_ok = False", blk8) is not None,
      "Provider-Fehler bei 8-K setzt sec_ok False")
check('log.warning("%s: %d/%d SEC-Abrufe fehlgeschlagen' in src, "Lauf-Warnung je EDGAR-Quelle im Log")

print()
if FAILS:
    print(f"{len(FAILS)} FEHLER")
    sys.exit(1)
print("OK — alle Checks grün")
