"""
Microservicio: Autenticacion (Auth) - Puerto 5001
Registra administradores y maneja login.
Accede directamente a la DB compartida.
"""

import os
import uuid
import datetime
import hashlib
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')


def get_db():
    db = sqlite3.connect(DATABASE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
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
        pw1 = hashlib.sha256("admin123".encode()).hexdigest()
        pw2 = hashlib.sha256("demo123".encode()).hexdigest()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                   ("Administrador", "admin@ejemplo.com", pw1))
        db.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                   ("Investigador", "investigador@ejemplo.com", pw2))
        db.commit()
        print("[Auth] 2 usuarios ejemplo creados")
    db.close()
    print("[Auth] Base de datos inicializada.")


@app.route('/register', methods=['POST'])
def register():
    data = request.json
    nombre = data.get('name')
    email = data.get('email')
    password = data.get('password')
    if not nombre or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (nombre, email, pw_hash)
        )
        db.commit()
        db.close()
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
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ? AND password_hash = ?",
        (email, pw_hash)
    ).fetchone()
    if user:
        session_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO sessions (id, user_id, start_time) VALUES (?, ?, ?)",
            (session_id, user['id'], datetime.datetime.now().isoformat())
        )
        db.commit()
        db.close()
        print(f"[Auth] Login exitoso: {email}")
        return jsonify({
            "message": "Inicio de sesion exitoso",
            "user": {"id": user['id'], "name": user['name'],
                     "email": user['email']},
            "session_id": session_id
        })
    else:
        db.close()
        return jsonify({"error": "Credenciales invalidas"}), 401


@app.route('/users', methods=['GET'])
def get_users():
    db = get_db()
    users = db.execute(
        "SELECT id, name, email, role, created_at FROM users"
    ).fetchall()
    db.close()
    return jsonify([dict(u) for u in users])


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'auth'})


if __name__ == '__main__':
    init_db()
    print("[Auth] Microservicio corriendo en puerto 5001")
    app.run(host='0.0.0.0', port=5001)
