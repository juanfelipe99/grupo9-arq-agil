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
VENV_PYTHON = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
PYTHON = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable

SERVICES = [
    (r"services\monitor.py", 5003, "Monitor"),
    (r"services\auth.py", 5001, "Auth"),
    (r"services\cotizacion.py", 5002, "Cotizacion"),
    (r"services\autorizador.py", 5004, "Autorizador"),
    (r"main.py", 5000, "Dashboard"),
]

processes = []

CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + CHILD_ENV.get("PYTHONPATH", "")


def wait_for_health(port, name, tries=30, pause=1.0, timeout=2):
    url = f"http://127.0.0.1:{port}/health"
    for attempt in range(1, tries + 1):
        try:
            urllib.request.urlopen(url, timeout=timeout)
            print(f"  OK   - {name} (puerto {port}) listo en ~{attempt * pause:.0f}s")
            return True
        except Exception:
            time.sleep(pause)
    print(f"  FAIL - {name} (puerto {port}) no respondio tras {tries * pause:.0f}s")
    return False

print("Iniciando servicios del experimento H710...\n")

for script, port, name in SERVICES:
    p = subprocess.Popen(
        [PYTHON, os.path.join(PROJECT_ROOT, script)],
        cwd=PROJECT_ROOT,
        env=CHILD_ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(p)
    print(f"  Puerto {port} - {name} ({script.split(os.sep)[-1]})")
    time.sleep(1.0)

print("\nEsperando que los servicios estén listos...")

all_ok = True
for script, port, name in SERVICES:
    if not wait_for_health(port, name):
        all_ok = False

if not all_ok:
    print("  Algunos servicios no respondieron (revisa puertos ocupados).")

print("\n" + "=" * 60)
print("  Todos los servicios iniciados.")
print("  Abre http://127.0.0.1:5000 en tu navegador")
print("=" * 60)
print("\nPresiona Ctrl+C para detener todos los servicios\n")

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nDeteniendo servicios...")
    for p in processes:
        p.terminate()
    print("Todos los servicios detenidos.")
