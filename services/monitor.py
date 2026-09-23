"""
Microservicio: Monitor de Comportamiento - Puerto 5003
Recibe registros de consulta, calcula tasa de requests
y detecta comportamiento anomalo.
"""

import os
import time
import threading
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')

ANOMALY_THRESHOLD = 150

user_history = {}
lock = threading.Lock()


def get_db():
    db = sqlite3.connect(DATABASE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


@app.route('/registrar', methods=['POST'])
def registrar():
    data = request.json
    session_id = data.get('session_id')
    user_id = data.get('user_id')

    now = time.time()
    with lock:
        if user_id not in user_history:
            user_history[user_id] = []
        user_history[user_id].append(now)
        user_history[user_id] = [
            t for t in user_history[user_id] if now - t < 60
        ]
        tasa = len(user_history[user_id])
        es_anomalia = tasa >= ANOMALY_THRESHOLD

    tiempo_det = 0
    if es_anomalia:
        ini = time.time()
        time.sleep(0.005)
        fin = time.time()
        tiempo_det = (fin - ini) * 1000
        try:
            db = get_db()
            db.execute(
                "UPDATE sessions SET is_anomalous=1, status='Bloqueada' WHERE id=?",
                (session_id,)
            )
            db.commit()
            db.close()
        except Exception as e:
            print(f"[Monitor] Error DB: {e}")
        print(f"[Monitor] Anomalia detectada! Sesion: {session_id[:8]}... "
              f"Tiempo: {tiempo_det:.2f}ms")

    return jsonify({
        "es_anomalia": es_anomalia,
        "tiempo_deteccion_ms": round(tiempo_det, 2),
        "tasa_actual": tasa,
        "umbral": ANOMALY_THRESHOLD
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'monitor',
                    'umbral': ANOMALY_THRESHOLD})


if __name__ == '__main__':
    print("[Monitor] Microservicio corriendo en puerto 5003")
    app.run(host='0.0.0.0', port=5003)
