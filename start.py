"""
Lanzador de todos los microservicios del experimento H710.
Ejecuta cada servicio como un proceso independiente.
"""

import subprocess
import time
import sys
import os
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

DASHBOARD_PORT = int(os.environ.get("PORT", 5000))

SERVICES = [
    (os.path.join("services", "monitor.py"), 5003, "Monitor"),
    (os.path.join("services", "auth.py"), 5001, "Auth"),
    (os.path.join("services", "cotizacion.py"), 5002, "Cotizacion"),
    (os.path.join("services", "autorizador.py"), 5004, "Autorizador"),
    ("main.py", DASHBOARD_PORT, "Dashboard"),
]

processes = []

CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + CHILD_ENV.get("PYTHONPATH", "")
# sin esto los mensajes de los servicios quedan en el buffer y no se ven
CHILD_ENV["PYTHONUNBUFFERED"] = "1"


def wait_for_health(port, name, tries=30, pause=1.0, timeout=2):
    url = f"http://127.0.0.1:{port}/health"
    for attempt in range(1, tries + 1):
        try:
            urllib.request.urlopen(url, timeout=timeout)
            print(f"  OK   - {name} (puerto {port}) listo en ~{attempt * pause:.0f}s", flush=True)
            return True
        except Exception:
            time.sleep(pause)
    print(f"  FAIL - {name} (puerto {port}) no respondio tras {tries * pause:.0f}s", flush=True)
    return False

print("Iniciando servicios del experimento H710...\n", flush=True)

for script, port, name in SERVICES:
    p = subprocess.Popen(
        [PYTHON, os.path.join(PROJECT_ROOT, script)],
        cwd=PROJECT_ROOT,
        env=CHILD_ENV,
    )
    processes.append(p)
    print(f"  Puerto {port} - {name} ({os.path.basename(script)})", flush=True)
    time.sleep(1.0)

print("\nEsperando que los servicios esten listos...", flush=True)

all_ok = True
for script, port, name in SERVICES:
    if not wait_for_health(port, name):
        all_ok = False

if not all_ok:
    print("  Algunos servicios no respondieron (revisa puertos ocupados).", flush=True)

print(f"\nListo -> http://127.0.0.1:{DASHBOARD_PORT}   (Ctrl+C para detener)\n",
      flush=True)

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nDeteniendo servicios...")
    for p in processes:
        p.terminate()
    print("Todos los servicios detenidos.")
