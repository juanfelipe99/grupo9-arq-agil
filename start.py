import subprocess
import time
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

COTIZACION_PORT = int(os.environ.get("PORT", 5000))

SERVICES = [
    (os.path.join("services", "rating", "rating1.py"), 5001),
    (os.path.join("services", "rating", "rating2.py"), 5002),
    (os.path.join("services", "rating", "rating3.py"), 5003),
    (os.path.join("services", "votacion.py"), 5004),
    (os.path.join("services", "enmascaramiento.py"), 5005),
    (os.path.join("client", "cotizacion.py"), COTIZACION_PORT),
]

processes = []

print("Iniciando servicios del experimento...\n")

for script, port in SERVICES:
    p = subprocess.Popen([sys.executable, os.path.join(PROJECT_ROOT, script)], cwd=PROJECT_ROOT)
    processes.append(p)
    print(f"  Puerto {port} - {os.path.basename(script)}", flush=True)
    time.sleep(0.3)

print("\nTodos los servicios iniciados.")
print(f"Abre http://127.0.0.1:{COTIZACION_PORT} en tu navegador", flush=True)
print("\nPresiona Ctrl+C para detener todos los servicios\n")

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nDeteniendo servicios...")
    for p in processes:
        p.terminate()
    print("Todos los servicios detenidos.")
