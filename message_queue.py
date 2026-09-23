"""Cola de eventos de comportamiento entre Cotizacion y el Monitor.

Usa Redis cuando esta disponible. Si no lo esta, cae en la alternativa que
describe el diseno H710 para este conector, threading + requests, de modo que
el experimento sigue siendo ejecutable sin infraestructura adicional.
"""

import json
import threading

import requests

from redis_client import redis_client, redis_disponible

BEHAVIOR_QUEUE = "registro_comportamiento"
MONITOR_URL = "http://127.0.0.1:5003"

_modo = None
_modo_lock = threading.Lock()


def modo():
    """Devuelve 'redis' o 'http'. Se resuelve una sola vez por proceso."""
    global _modo
    with _modo_lock:
        if _modo is None:
            _modo = 'redis' if redis_disponible() else 'http'
            print(f"[Cola] transporte: {_modo}")
        return _modo


def _publicar_http(event):
    try:
        requests.post(f"{MONITOR_URL}/registrar", json=event, timeout=5)
    except Exception as e:
        print(f"[Cola] No se pudo entregar el evento: {e}")


def publish_behavior_event(event):
    """Publica sin bloquear al llamador."""
    if modo() == 'redis':
        try:
            redis_client.rpush(BEHAVIOR_QUEUE, json.dumps(event))
            return
        except Exception as e:
            print(f"[Cola] Redis fallo, se usa HTTP: {e}")
    threading.Thread(target=_publicar_http, args=(event,), daemon=True).start()


def consume_behavior_event():
    """Extrae un evento de la cola. Devuelve None si no hay o no hay Redis."""
    if modo() != 'redis':
        return None
    try:
        message = redis_client.blpop(BEHAVIOR_QUEUE, timeout=1)
    except Exception as e:
        print(f"[Cola] Error consumiendo: {e}")
        return None
    if message is None:
        return None
    _, data = message
    return json.loads(data)
