#!/usr/bin/env bash
# Totmann-Signal an healthchecks.io (Easy-Entscheid 02.11.2026).
#
# Wird als LETZTER Schritt von daily-squeeze-report.yml und ki_agent.yml
# aufgerufen, nur bei erfolgreichem Lauf. Bleibt der Ping zu lange aus,
# alarmiert healthchecks.io von außen (ntfy/E-Mail) — auch wenn GitHub gar
# keine Läufe mehr startet (Zeitplan-Stillstand 02.11.2026).
#
# Eingabe: Umgebungsvariable HC_PING_URL (aus dem Secret HC_PING_URL_DAILY
# bzw. HC_PING_URL_KI). Erwartete Form: https://hc-ping.com/<uuid>
#
# Garantien:
#   * FAIL-SOFT: endet IMMER mit Exit-Code 0 — der Lauf bleibt grün.
#   * Secret leer           → überspringen, eine Log-Zeile.
#   * fremde/kaputte URL    → überspringen, Warn-Zeile (kein Request).
#   * Ping-Fehler           → Warn-Zeile.
#   * Die URL wird NIE ausgegeben (auch curl-Fehlertexte werden verschluckt).
#   * Kein Inhalt im Ping (leerer GET), keine weiteren Secrets.
#   * curl: 10 s Timeout pro Versuch, höchstens 2 Wiederholungen.
set -u

url="${HC_PING_URL:-}"

if [ -z "$url" ]; then
  echo "healthchecks.io-Ping übersprungen: Secret nicht gesetzt."
  exit 0
fi

case "$url" in
  https://hc-ping.com/?*) ;;
  *)
    echo "WARNUNG: healthchecks.io-Ping übersprungen: URL ist keine https-Adresse bei hc-ping.com (Wert wird nicht ausgegeben)."
    exit 0
    ;;
esac

if curl -fsS -m 10 --retry 2 --retry-max-time 25 -o /dev/null "$url" >/dev/null 2>&1; then
  echo "Lebenszeichen an healthchecks.io gesendet."
else
  rc=$?
  echo "WARNUNG: healthchecks.io-Ping fehlgeschlagen (curl-Code $rc) — Lauf bleibt grün."
fi
exit 0
