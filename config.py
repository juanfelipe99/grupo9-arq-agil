"""
Configuracion centralizada de puertos y URLs
para los microservicios del experimento H710.
"""

import os

DASHBOARD_PORT = 5000

SERVICES = {
    "auth": "http://127.0.0.1:5001",
    "cotizacion": "http://127.0.0.1:5002",
    "monitor": "http://127.0.0.1:5003",
    "autorizador": "http://127.0.0.1:5004",
}

# Parametros iniciales del experimento (sobrescribibles por env o API)
BASELINE_QPM = int(os.getenv("BASELINE_QPM", 50))
ANOMALY_THRESHOLD = int(os.getenv("ANOMALY_THRESHOLD", 150))

SCENARIO_DEFAULTS = {
    "normal": {"num_queries": 50, "delay": 1.5, "label": "Comportamiento Normal"},
    "massive": {"num_queries": 200, "delay": 0.01, "label": "Extraccion Masiva"},
    "gradual": {"num_queries": 151, "delay": 0.1, "decay": 0.95,
                "label": "Escala Gradual"},
}
