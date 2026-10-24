#!/usr/bin/env python3
"""AFG TLS-Monitor: 3 neue HTTPS-Verbindungen; Bericht an AFG ohne zusätzliche Pakete."""
import json
import os
import statistics
import subprocess
import sys
import urllib.error
import urllib.request

TARGET = "https://airfryerguide.de/assets/css/style.css"
WEBHOOK = "https://airfryerguide.de/api/tls-monitor.php"
SLOW_THRESHOLD_MS = 1800
SAMPLES = 3


def measure():
    command = [
        "curl", "-4", "--silent", "--show-error",
        "--output", "/dev/null", "--max-time", "14", "--connect-timeout", "4",
        "--write-out", "%{time_connect}|%{time_appconnect}|%{http_code}", TARGET,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=17, check=False)
        if result.returncode != 0:
            print(f"Messung fehlgeschlagen: curl Exitcode {result.returncode}")
            return None
        tcp, appconnect, http_code = result.stdout.strip().split("|")
        tcp_ms = float(tcp) * 1000
        tls_ms = (float(appconnect) * 1000) - tcp_ms
        if tls_ms < 0 or appconnect == "0.000000":
            print("Kein gültiger TLS-Messwert")
            return None
        print(f"TCP {tcp_ms:.0f} ms | TLS {tls_ms:.0f} ms | HTTP {http_code}")
        return tls_ms
    except (ValueError, subprocess.TimeoutExpired, OSError) as error:
        print(f"Messung fehlgeschlagen: {type(error).__name__}")
        return None


def main():
    token = os.environ.get("AFG_MONITOR_TOKEN", "")
    if len(token) != 64:
        print("Fehler: GitHub Secret AFG_MONITOR_TOKEN fehlt oder ist ungültig.", file=sys.stderr)
        return 2

    timings = [measure() for _ in range(SAMPLES)]
    valid = [value for value in timings if value is not None]
    # Ausfälle beim Verbindungsaufbau gelten als schlechte Messungen.
    slow = sum(value is None or value >= SLOW_THRESHOLD_MS for value in timings)
    status = "slow" if slow >= 2 else "ok"
    median = round(statistics.median(valid), 1) if valid else None
    print(f"Ergebnis: {status} ({slow}/{SAMPLES} auffällig, Median {median} ms)")

    payload = json.dumps({"status": status, "median_tls_ms": median}).encode("utf-8")
    request = urllib.request.Request(
        WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json", "X-AFG-Monitor-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=22) as response:
            body = response.read(1024).decode("utf-8", errors="replace")
            print("AFG-Rückmeldung:", response.status, body)
    except urllib.error.HTTPError as error:
        print(f"AFG-Rückmeldung: HTTP {error.code}. Endpoint, Bot-Schutz und Schlüssel prüfen.", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(f"AFG konnte nicht benachrichtigt werden: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
