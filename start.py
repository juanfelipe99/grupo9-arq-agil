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
    (r"services\auth.py", 5001, "Auth"),
    (r"services\cotizacion.py", 5002, "Cotizacion"),
    (r"services\monitor.py", 5003, "Monitor"),
    (r"services\autorizador.py", 5004, "Autorizador"),
    (r"main.py", 5000, "Dashboard"),
]

processes = []

print("Iniciando servicios del experimento H710...\n")

for script, port, name in SERVICES:
    p = subprocess.Popen(
        [PYTHON, os.path.join(PROJECT_ROOT, script)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(p)
    print(f"  Puerto {port} - {name} ({script.split(os.sep)[-1]})")
    time.sleep(0.3)

print("\nEsperando que los servicios estén listos...")

for i in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/api/status", timeout=1)
        break
    except Exception:
        time.sleep(1)
else:
    print("  Aún esperando servicios...")

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
