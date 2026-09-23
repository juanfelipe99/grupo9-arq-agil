"""
Microservicio: Autorizador - Puerto 5004
Recibe notificaciones de anomalias y bloquea/revoca sesiones.
"""

import os
import time
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')

blocked_sessions = set()


def get_db():
    db = sqlite3.connect(DATABASE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


@app.route('/revocar', methods=['POST'])
def revocar():
    data = request.json
    session_id = data.get('session_id')
    motivo = data.get('motivo', 'Comportamiento anomalo detectado')

    blocked_sessions.add(session_id)
    try:
        db = get_db()
        db.execute(
            "UPDATE sessions SET status='Revocada', is_anomalous=1 WHERE id=?",
            (session_id,)
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[Autorizador] Error DB: {e}")

    print(f"[Autorizador] Sesion {session_id[:8]}... revocada.")
    return jsonify({
        "message": "Sesion revocada",
        "session_id": session_id,
        "motivo": motivo
    })


@app.route('/verificar/<session_id>', methods=['GET'])
def verificar(session_id):
    is_blocked = session_id in blocked_sessions
    return jsonify({
        "session_id": session_id,
        "bloqueada": is_blocked
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'autorizador',
                    'sesiones_bloqueadas': len(blocked_sessions)})


if __name__ == '__main__':
    print("[Autorizador] Microservicio corriendo en puerto 5004")
    app.run(host='0.0.0.0', port=5004)
