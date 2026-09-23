"""
Configuracion centralizada de puertos y URLs
para los microservicios del experimento H710.
"""

DASHBOARD_PORT = 5000

SERVICES = {
    "auth": "http://127.0.0.1:5001",
    "cotizacion": "http://127.0.0.1:5002",
    "monitor": "http://127.0.0.1:5003",
    "autorizador": "http://127.0.0.1:5004",
}

ANOMALY_THRESHOLD = 150
