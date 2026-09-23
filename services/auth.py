"""
Microservicio: Autenticacion (Auth) - Puerto 5001
Registra administradores y maneja login.
Accede directamente a la DB compartida.
"""

import os
import uuid
import datetime
import sqlite3
from flask import Flask, request, jsonify

from db import abrir, conectar
from werkzeug.security import check_password_hash, generate_password_hash

import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)
try:
    from flask import cli as _cli
    _cli.show_server_banner = lambda *a, **k: None
except Exception:
    pass

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')


def get_db():
    return conectar(DATABASE)


def init_db():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    with abrir(DATABASE) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'Administrador',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, user_id INTEGER, start_time TEXT,
            status TEXT DEFAULT 'Activa', queries_count INTEGER DEFAULT 0,
            is_anomalous INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
            timestamp REAL, query_type TEXT,
            response_time_ms REAL DEFAULT 0, is_anomaly INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions (id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS experiment_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scenario TEXT,
            total_queries INTEGER, successful INTEGER, failed INTEGER,
            duration_ms REAL, detection_time_ms REAL, is_anomaly INTEGER,
            meets_threshold INTEGER,
            run_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            for nombre, email, clave in [
                ("Administrador", "admin@ejemplo.com", os.environ.get("ADMIN_PASSWORD", "admin123")),
                ("Investigador", "investigador@ejemplo.com", os.environ.get("DEMO_PASSWORD", "demo123")),
            ]:
                db.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (nombre, email, generate_password_hash(clave))
                )
            db.commit()
            print("[Auth] 2 usuarios ejemplo creados")
    print("[Auth] Base de datos inicializada.")


@app.route('/register', methods=['POST'])
def register():
    data = request.json
    nombre = data.get('name')
    email = data.get('email')
    password = data.get('password')
    if not nombre or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400
    pw_hash = generate_password_hash(password)
    try:
        with abrir(DATABASE) as db:
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (nombre, email, pw_hash)
            )
            db.commit()
        print(f"[Auth] Administrador registrado: {email}")
        return jsonify({"message": "Administrador registrado exitosamente"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "El correo electronico ya esta registrado"}), 400


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"error": "Email y contrasena son obligatorios"}), 400
    with abrir(DATABASE) as db:
        user = db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not (user and check_password_hash(user['password_hash'], password)):
            return jsonify({"error": "Credenciales invalidas"}), 401
        session_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO sessions (id, user_id, start_time) VALUES (?, ?, ?)",
            (session_id, user['id'], datetime.datetime.now().isoformat())
        )
        db.commit()
        datos = {"id": user['id'], "name": user['name'], "email": user['email']}
    print(f"[Auth] Login exitoso: {email}")
    return jsonify({
        "message": "Inicio de sesion exitoso",
        "user": datos,
        "session_id": session_id
    })


@app.route('/logout', methods=['POST'])
def logout():
    """Cierra la sesion en el servidor, no solo en el navegador.

    Deja de estar 'Activa', asi que Cotizacion la rechazara aunque alguien
    conserve el identificador.
    """
    data = request.json or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"error": "Falta session_id"}), 400
    with abrir(DATABASE) as db:
        fila = db.execute("SELECT status FROM sessions WHERE id = ?",
                          (session_id,)).fetchone()
        if fila is None:
            return jsonify({"error": "Sesion inexistente"}), 404
        db.execute("UPDATE sessions SET status='Cerrada' WHERE id = ?", (session_id,))
        db.commit()
    return jsonify({"message": "Sesion cerrada", "session_id": session_id})


@app.route('/sesion/<session_id>', methods=['GET'])
def consultar_sesion(session_id):
    """Valida una sesion contra la base de datos.

    Es la fuente de verdad de la identidad: Cotizacion obtiene de aqui el
    user_id en vez de confiar en una cabecera que el cliente puede escribir.
    """
    with abrir(DATABASE) as db:
        fila = db.execute(
            "SELECT s.id, s.user_id, s.status, u.email, u.role "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?",
            (session_id,)
        ).fetchone()
    if fila is None:
        return jsonify({"valida": False, "motivo": "Sesion inexistente"}), 404
    return jsonify({
        "valida": fila['status'] == 'Activa',
        "session_id": fila['id'],
        "user_id": fila['user_id'],
        "email": fila['email'],
        "role": fila['role'],
        "status": fila['status'],
    })


@app.route('/users', methods=['GET'])
def get_users():
    with abrir(DATABASE) as db:
        users = db.execute(
            "SELECT id, name, email, role, created_at FROM users"
        ).fetchall()
    return jsonify([dict(u) for u in users])


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'auth'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5001)
