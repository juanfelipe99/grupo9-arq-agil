"""
Microservicio: Cotizacion y Rating - Puerto 5002
Recibe solicitudes de cotizacion, las valida con el Monitor
y Autorizador via HTTP.
"""

import os
import sys
import uuid
import time
import random
import sqlite3
import requests
from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db import abrir, conectar
from message_queue import publish_behavior_event

import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)
try:
    from flask import cli as _cli
    _cli.show_server_banner = lambda *a, **k: None
except Exception:
    pass

app = Flask(__name__)

DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')

AUTH_URL = "http://127.0.0.1:5001"
MONITOR_URL = "http://127.0.0.1:5003"
AUTORIZADOR_URL = "http://127.0.0.1:5004"

def get_db():
    return conectar(DATABASE)


def resolver_sesion(session_id):
    """Obtiene el user_id preguntandole a Auth, la fuente de verdad.

    El cliente no decide quien es: si la sesion no existe o no esta activa,
    la peticion se rechaza. No se cachea el resultado a proposito, porque el
    estado de la sesion cambia por debajo: al cerrarla o al revocarla deja de
    ser valida, y una copia local dejaria pasar sesiones ya cerradas.

    Devuelve (user_id, estado). user_id es None cuando la sesion no sirve, y
    el estado permite distinguir una sesion revocada de una inexistente.
    """
    try:
        resp = requests.get(f"{AUTH_URL}/sesion/{session_id}", timeout=5)
    except Exception as e:
        print(f"[Cotizacion] Error consultando Auth: {e}")
        return None, 'Error'
    if resp.status_code != 200:
        return None, 'Inexistente'
    datos = resp.json()
    estado = datos.get('status', 'Desconocida')
    if not datos.get('valida'):
        return None, estado
    return datos['user_id'], estado


def registrar_log(session_id, tipo, tiempo_ms, es_anomalia):
    """Deja traza de cada consulta para que quede evidencia del experimento."""
    try:
        with abrir(DATABASE) as db:
            db.execute(
                "INSERT INTO logs (session_id, timestamp, query_type, "
                "response_time_ms, is_anomaly) VALUES (?, ?, ?, ?, ?)",
                (session_id, time.time(), tipo, round(tiempo_ms, 2),
                 1 if es_anomalia else 0)
            )
            db.execute(
                "UPDATE sessions SET queries_count = queries_count + 1 WHERE id = ?",
                (session_id,)
            )
            db.commit()
    except Exception as e:
        print(f"[Cotizacion] Error registrando log: {e}")


@app.route('/quote', methods=['GET'])
def quote():
    inicio = time.time()
    session_id = request.headers.get('X-Session-ID', '')
    quote_id = str(uuid.uuid4())[:8]

    if not session_id:
        return jsonify({
            "quote_id": quote_id, "status": "UNAUTHORIZED",
            "message": "Falta la cabecera X-Session-ID"
        }), 401

    user_id, estado = resolver_sesion(session_id)
    if user_id is None:
        # Una sesion revocada no es lo mismo que una inexistente: es la prueba
        # de que la contramedida corto la fuga, asi que se responde como
        # bloqueada y queda registrada en el log del experimento.
        if estado in ('Revocada', 'Bloqueada'):
            registrar_log(session_id, 'quote',
                          (time.time() - inicio) * 1000, True)
            return jsonify({
                "quote_id": quote_id, "status": "BLOCKED",
                "message": f"Sesion {estado.lower()} por comportamiento anomalo"
            }), 403
        return jsonify({
            "quote_id": quote_id, "status": "UNAUTHORIZED",
            "message": "Sesion invalida o no activa"
        }), 401

    try:
        check = requests.get(
            f"{AUTORIZADOR_URL}/verificar/{session_id}", timeout=5
        ).json()
        if check.get('bloqueada'):
            registrar_log(session_id, 'quote',
                          (time.time() - inicio) * 1000, True)
            return jsonify({
                "quote_id": quote_id, "status": "BLOCKED",
                "message": "Sesion bloqueada por el Autorizador"
            }), 403
    except Exception as e:
        print(f"[Cotizacion] Error consultando Autorizador: {e}")

    # El registro viaja de forma asincrona: el analisis de comportamiento no
    # debe retrasar la respuesta al administrador. La deteccion y la revocacion
    # ocurren en el Monitor, y esta sesion quedara bloqueada en su proxima
    # consulta al consultar al Autorizador.
    publish_behavior_event({
        "session_id": session_id,
        "user_id": int(user_id)
    })

    respuesta = {
        "quote_id": quote_id, "client_id": f"CLI-{random.randint(100, 999)}",
        "risk_score": round(random.uniform(0.1, 0.9), 2),
        "premium": round(random.uniform(100, 5000), 2), "status": "OK"
    }
    registrar_log(session_id, 'quote', (time.time() - inicio) * 1000, False)
    return jsonify(respuesta)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'cotizacion'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
