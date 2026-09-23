"""
Configuracion centralizada de puertos y URLs
para los microservicios del experimento H710.
"""

import os

DASHBOARD_PORT = int(os.getenv("PORT", 5000))

SERVICES = {
    "auth": "http://127.0.0.1:5001",
    "cotizacion": "http://127.0.0.1:5002",
    "monitor": "http://127.0.0.1:5003",
    "autorizador": "http://127.0.0.1:5004",
}

# Parametros del experimento, sobrescribibles por env o API.
#
# No hay umbral fijo: cada usuario se compara contra su propio habito.
# BASELINE_QPM es el habito supuesto de quien no tiene historial y
# FACTOR_DESVIACION cuantas veces debe superarlo para marcarse. Por defecto,
# un usuario nuevo salta a 50 x 3 = 150 consultas por minuto.
BASELINE_QPM = int(os.getenv("BASELINE_QPM", 50))
FACTOR_DESVIACION = float(os.getenv("FACTOR_DESVIACION", 3.0))

# Piso absoluto, para que alguien muy poco activo no salte por una rafaga.
UMBRAL_MINIMO = int(os.getenv("UMBRAL_MINIMO", 20))

# Cuanto pesa lo recien observado frente a lo que ya se creia del usuario.
ALFA_APRENDIZAJE = float(os.getenv("ALFA_APRENDIZAJE", 0.3))

# El umbral es siempre el triple del habito actual. Lo acotado no es el
# umbral sino el habito, que no puede alejarse mas del doble ni de la mitad
# de la suposicion inicial. Por defecto el habito vive entre 25 y 100, o sea
# que el umbral vive entre 75 y 300, y quien no tiene historial arranca en 150.
DERIVA_MAXIMA = float(os.getenv("DERIVA_MAXIMA", 2.0))
BASELINE_MAXIMO = float(os.getenv("BASELINE_MAXIMO", BASELINE_QPM * DERIVA_MAXIMA))
BASELINE_MINIMO = float(os.getenv("BASELINE_MINIMO", BASELINE_QPM / DERIVA_MAXIMA))

# Dos frenos contra una escalada que quiera normalizarse a si misma. Solo se
# aprende de tasas cercanas al habito, porque una rafaga que roza el umbral es
# lo que se quiere detectar y no un habito nuevo. Y el cambio por ventana esta
# limitado en ambos sentidos, de modo que mover el habito cuesta minutos.
MARGEN_APRENDIZAJE = float(os.getenv("MARGEN_APRENDIZAJE", 1.5))
CAMBIO_MAXIMO = float(os.getenv("CAMBIO_MAXIMO", 0.10))

# Umbral de referencia: el que le toca a un usuario del que no se sabe nada.
ANOMALY_THRESHOLD = int(os.getenv(
    "ANOMALY_THRESHOLD", round(BASELINE_QPM * FACTOR_DESVIACION)))

VENTANA_SEGUNDOS = int(os.getenv("VENTANA_SEGUNDOS", 60))

# Los dos escenarios de ataque arrancan con el mismo numero de consultas, para
# que lo que los distinga sea el ritmo y no el volumen. Ninguno llega a las 200
# porque la revocacion los corta antes, y ese margen es lo que se quiere ver.
CONSULTAS_POR_ESCENARIO = int(os.getenv("CONSULTAS_POR_ESCENARIO", 200))

# El normal va aparte porque nadie lo corta y su numero solo decide cuanto
# dura. A 1.5s por consulta, 50 cubren mas de una ventana, que es lo que hace
# falta para probar que no dispara nada.
CONSULTAS_NORMAL = int(os.getenv("CONSULTAS_NORMAL", 50))

SCENARIO_DEFAULTS = {
    "normal": {"num_queries": CONSULTAS_NORMAL, "delay": 1.5,
               "label": "Comportamiento Normal"},
    "massive": {"num_queries": CONSULTAS_POR_ESCENARIO, "delay": 0.01,
                "label": "Extraccion Masiva"},
    "gradual": {"num_queries": CONSULTAS_POR_ESCENARIO, "delay": 0.1,
                "decay": 0.95, "label": "Escala Gradual"},
}
