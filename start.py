import subprocess
import time
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

SERVICES = [
    (r"services\rating\rating1.py", 5001),
    (r"services\rating\rating2.py", 5002),
    (r"services\rating\rating3.py", 5003),
    (r"services\votacion.py", 5004),
    (r"services\enmascaramiento.py", 5005),
    (r"client\cotizacion.py", 5000),
]

processes = []

print("Iniciando servicios del experimento...\n")

for script, port in SERVICES:
    p = subprocess.Popen([sys.executable, os.path.join(PROJECT_ROOT, script)], cwd=PROJECT_ROOT)
    processes.append(p)
    print(f"  Puerto {port} - {script.split(chr(92))[-1]}")
    time.sleep(0.3)

print("\nTodos los servicios iniciados.")
print("Abre http://127.0.0.1:5000 en tu navegador")
print("\nPresiona Ctrl+C para detener todos los servicios\n")

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nDeteniendo servicios...")
    for p in processes:
        p.terminate()
    print("Todos los servicios detenidos.")
