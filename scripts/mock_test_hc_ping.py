#!/usr/bin/env python3
"""Mock-Test: Totmann-Signal an healthchecks.io (02.11.2026).

Deterministisch, ohne Netz: curl wird per PATH-Shim ersetzt. Läuft auf
stdlib + pyyaml + bash (CI-tauglich).

  01 Beide Workflows: Ping ist der LETZTE Schritt, ``if: success()``,
     ``continue-on-error: true``, richtiges Secret, ruft scripts/hc_ping.sh
  02 Kein anderer Schritt nach dem Ping, kein ``always()``/``failure()``-Ping,
     kein ``/fail``-Pfad, genau ein Ping-Schritt je Workflow
  03 Echtes Bash: Secret leer → übersprungen, Exit 0, kein curl-Aufruf
  04 Echtes Bash: Erfolg → „Lebenszeichen …“, Exit 0, curl mit -m 10 und
     --retry 2, GET ohne Daten (kein -d/--data/-X POST)
  05 Echtes Bash: curl-Fehler (nicht erreichbar / HTTP-Fehler) → Warnung,
     Exit 0
  06 Echtes Bash: fremde Host-URL → kein Request, Warnung, Exit 0
  07 Die URL erscheint in KEINEM Fall in der Ausgabe
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "hc_ping.sh"
WORKFLOWS = {
    ".github/workflows/ki_agent.yml": "HC_PING_URL_KI",
    ".github/workflows/daily-squeeze-report.yml": "HC_PING_URL_DAILY",
}
FAKE_URL = "https://hc-ping.com/00000000-1111-2222-3333-444444444444"

_fails: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        _fails.append(name)


def _steps(path: str) -> list[dict]:
    d = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    jobs = list(d["jobs"].values())
    assert len(jobs) == 1, path
    return jobs[0]["steps"]


def test_01_02_yaml():
    for path, secret in WORKFLOWS.items():
        steps = _steps(path)
        last = steps[-1]
        tag = path.split("/")[-1]
        _check(f"01 {tag}: letzter Schritt ist der Ping", last.get("name") == "Totmann-Ping healthchecks.io")
        _check(f"01 {tag}: nur bei Erfolg", str(last.get("if", "")).strip() == "success()")
        _check(f"01 {tag}: continue-on-error", last.get("continue-on-error") is True)
        _check(f"01 {tag}: Secret {secret}",
               (last.get("env") or {}).get("HC_PING_URL") == "${{ secrets.%s }}" % secret)
        _check(f"01 {tag}: ruft hc_ping.sh", str(last.get("run", "")).strip() == "bash scripts/hc_ping.sh")
        pings = [s for s in steps if "hc_ping" in str(s.get("run", "")) or "hc-ping" in str(s.get("run", ""))]
        _check(f"02 {tag}: genau ein Ping-Schritt", len(pings) == 1)
        raw = (ROOT / path).read_text(encoding="utf-8")
        _check(f"02 {tag}: kein /fail-Ping", "/fail" not in raw)
        _check(f"02 {tag}: kein always()/failure() am Ping",
               not any(k in str(last.get("if", "")) for k in ("always", "failure", "cancelled")))


def _run(env_url: str | None, curl_exit: int | None):
    """Führt hc_ping.sh in echtem Bash aus. curl ist ein Shim, das seine
    Argumente protokolliert und mit ``curl_exit`` endet (None = kein Shim
    → curl darf gar nicht aufgerufen werden; Shim protokolliert trotzdem)."""
    with tempfile.TemporaryDirectory() as td:
        log = pathlib.Path(td) / "curl_args.log"
        shim = pathlib.Path(td) / "curl"
        code = 0 if curl_exit is None else curl_exit
        shim.write_text(
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$@" >> "{log}"\n'
            'echo "curl: (6) Could not resolve host: $*" >&2\n'
            f"exit {code}\n",
            encoding="utf-8")
        shim.chmod(0o755)
        env = {"PATH": f"{td}:{os.environ.get('PATH', '')}"}
        if env_url is not None:
            env["HC_PING_URL"] = env_url
        p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
        args = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return p.returncode, p.stdout + p.stderr, args


def test_03_to_07_bash():
    rc, out, args = _run(None, None)
    _check("03 Secret fehlt → Exit 0", rc == 0, out)
    _check("03 Secret fehlt → übersprungen", "übersprungen: Secret nicht gesetzt" in out, out)
    _check("03 Secret fehlt → kein curl", args == [], repr(args))
    rc, out, args = _run("", None)
    _check("03 Secret leer → Exit 0 + kein curl", rc == 0 and args == [], out)

    rc, out, args = _run(FAKE_URL, 0)
    _check("04 Erfolg → Exit 0", rc == 0, out)
    _check("04 Erfolg → Lebenszeichen", "Lebenszeichen an healthchecks.io gesendet" in out, out)
    _check("04 curl -m 10", "-m" in args and args[args.index("-m") + 1] == "10", repr(args))
    _check("04 curl --retry 2", "--retry" in args and args[args.index("--retry") + 1] == "2", repr(args))
    _check("04 kein Inhalt / kein POST", not any(a in args for a in ("-d", "--data", "-X", "--data-binary", "-F")), repr(args))
    out_all = [out]

    for code, label in ((6, "nicht erreichbar"), (28, "Timeout"), (22, "HTTP-Fehler")):
        rc, out, _ = _run(FAKE_URL, code)
        _check(f"05 {label} → Exit 0", rc == 0, out)
        _check(f"05 {label} → Warnung", "WARNUNG: healthchecks.io-Ping fehlgeschlagen" in out, out)
        out_all.append(out)

    for bad in ("https://evil.example.com/x", "http://hc-ping.com/abc", "https://hc-ping.com/", "hc-ping.com/abc"):
        rc, out, args = _run(bad, 0)
        _check(f"06 fremde/kaputte URL {bad!r} → kein Request, Exit 0",
               rc == 0 and args == [] and "WARNUNG" in out, out)
        _check(f"07 fremde URL nicht im Log ({bad!r})", bad not in out, out)

    _check("07 Ping-URL in keinem Lauf im Log", all(FAKE_URL not in o for o in out_all))
    _check("07 UUID in keinem Lauf im Log", all("00000000-1111" not in o for o in out_all))


def main() -> int:
    for t in (test_01_02_yaml, test_03_to_07_bash):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} ohne Exception", False, f"{type(exc).__name__}: {exc}")
    print()
    if _fails:
        print(f"{len(_fails)} FAIL")
        return 1
    print("Alle hc_ping-Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
