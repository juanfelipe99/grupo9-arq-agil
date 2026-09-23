"""
Microservicio: Cotizacion y Rating - Puerto 5002
Recibe solicitudes de cotizacion, las valida con el Monitor
y Autorizador via HTTP.
"""

import os
import uuid
import time
import random
import requests
from message_queue import publish_behavior_event
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')

MONITOR_URL = "http://127.0.0.1:5003"
AUTORIZADOR_URL = "http://127.0.0.1:5004"


@app.route('/quote', methods=['GET'])
def quote():
    session_id = request.headers.get('X-Session-ID', '')
    user_id = request.headers.get('X-User-ID', 1)
    quote_id = str(uuid.uuid4())[:8]
    client_id = f"CLI-{random.randint(100, 999)}"
    risk_score = round(random.uniform(0.1, 0.9), 2)
    premium = round(random.uniform(100, 5000), 2)

    if session_id:
        try:
            check = requests.get(
                f"{AUTORIZADOR_URL}/verificar/{session_id}",
                timeout=5
            ).json()
            if check.get('bloqueada'):
                return jsonify({
                    "quote_id": quote_id, "status": "BLOCKED",
                    "message": "Sesion bloqueada por el Autorizador"
                }), 403
        except Exception as e:
            print(f"[Cotizacion] Error consultando Autorizador: {e}")

        publish_behavior_event({
            "session_id": session_id,
            "user_id": int(user_id)
        })

    return jsonify({
        "quote_id": quote_id, "client_id": client_id,
        "risk_score": risk_score, "premium": premium, "status": "OK"
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'cotizacion'})


if __name__ == '__main__':
    print("[Cotizacion] Microservicio corriendo en puerto 5002")
    app.run(host='0.0.0.0', port=5002)
