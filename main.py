"""
Experimento H710 - Dashboard (Puerto 5000)
Interfaz web + orquestador de experimentos.
Comunica con microservicios independientes via HTTP.
"""

import os
import uuid
import time
import threading
import random
import requests
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

from config import SERVICES, DASHBOARD_PORT

app = Flask(__name__)
app.config['SECRET_KEY'] = 'h710-experiment-secret-key-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


# =============================================================================
# PAGINAS WEB
# =============================================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'dashboard'})


# =============================================================================
# API PROXY - Auth (puerto 5001)
# =============================================================================
@app.route('/api/auth/register', methods=['POST'])
def proxy_register():
    try:
        resp = requests.post(
            f"{SERVICES['auth']}/register",
            json=request.json, timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except requests.ConnectionError:
        return jsonify({"error": "Servicio Auth no disponible"}), 503


@app.route('/api/auth/login', methods=['POST'])
def proxy_login():
    try:
        resp = requests.post(
            f"{SERVICES['auth']}/login",
            json=request.json, timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except requests.ConnectionError:
        return jsonify({"error": "Servicio Auth no disponible"}), 503


@app.route('/api/users', methods=['GET'])
def proxy_users():
    try:
        resp = requests.get(
            f"{SERVICES['auth']}/users", timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except requests.ConnectionError:
        return jsonify([]), 503


# =============================================================================
# API PROXY - Cotizacion (puerto 5002)
# =============================================================================
@app.route('/api/cotizacion/quote', methods=['GET'])
def proxy_quote():
    session_id = request.headers.get('X-Session-ID', '')
    user_id = request.headers.get('X-User-ID', 1)
    try:
        resp = requests.get(
            f"{SERVICES['cotizacion']}/quote",
            headers={'X-Session-ID': session_id, 'X-User-ID': str(user_id)},
            timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except requests.ConnectionError:
        return jsonify({"error": "Servicio Cotizacion no disponible"}), 503


# =============================================================================
# API - Estado de servicios
# =============================================================================
@app.route('/api/status', methods=['GET'])
def get_status():
    status = {}
    for name, url in SERVICES.items():
        try:
            resp = requests.get(f"{url}/health", timeout=3)
            status[name] = resp.json().get('status') == 'ok'
        except Exception:
            status[name] = False
    status['dashboard'] = True
    return jsonify(status)


# =============================================================================
# API - Experimento
# =============================================================================
@app.route('/api/experiment/run', methods=['POST'])
def run_experiment():
    data = request.json
    scenario = data.get('scenario', 'normal')

    def run_simulation():
        print(f"[Experiment] Iniciando escenario: {scenario}")
        time.sleep(1)
        num_queries = 0
        delay_between = 0
        if scenario == 'normal':
            num_queries = 50
            delay_between = 1.5
        elif scenario == 'massive':
            num_queries = 200
            delay_between = 0.01
        elif scenario == 'gradual':
            num_queries = 151
            delay_between = 0.1

        start_time = time.time()
        success_count = 0
        fail_count = 0

        # Registrar usuario de simulacion via Auth service
        sim_email = f"sim_{scenario}_{uuid.uuid4().hex[:6]}@test.com"
        try:
            reg_resp = requests.post(
                f"{SERVICES['auth']}/register",
                json={"name": f"Sim {scenario}", "email": sim_email,
                      "password": "pass"},
                timeout=10
            )
            if reg_resp.status_code == 201:
                login_resp = requests.post(
                    f"{SERVICES['auth']}/login",
                    json={"email": sim_email, "password": "pass"},
                    timeout=10
                )
                user_data = login_resp.json()
                user_id = user_data.get('user', {}).get('id', 1)
                sess_id = user_data.get('session_id', str(uuid.uuid4()))
            else:
                user_id = 1
                sess_id = str(uuid.uuid4())
        except Exception:
            user_id = 1
            sess_id = str(uuid.uuid4())

        socketio.emit('experiment_started', {
            'scenario': scenario, 'session_id': sess_id
        })
        detection_time = 0

        for i in range(num_queries):
            if scenario == 'gradual':
                delay_between *= 0.95
            time.sleep(delay_between)

            # Llamar a cotizacion via HTTP
            try:
                cot_resp = requests.get(
                    f"{SERVICES['cotizacion']}/quote",
                    headers={'X-Session-ID': sess_id,
                             'X-User-ID': str(user_id)},
                    timeout=10
                ).json()

                if cot_resp.get('status') == 'ANOMALY_DETECTED':
                    detection_time = cot_resp.get('detection_time_ms', 0)
                    fail_count += 1
                    break
                elif cot_resp.get('status') == 'BLOCKED':
                    fail_count += 1
                    break
                else:
                    success_count += 1
            except Exception:
                fail_count += 1

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        is_anomalous = 1 if detection_time > 0 else 0
        meets_threshold = (
            1 if (detection_time > 0 and detection_time < 1000)
            else (1 if scenario == 'normal' else 0)
        )

        result = {
            "scenario": scenario,
            "total_queries": success_count + fail_count,
            "successful": success_count,
            "failed": fail_count,
            "duration_ms": round(duration_ms, 2),
            "detection_time_ms": round(detection_time, 2),
            "is_anomalous": is_anomalous,
            "meets_threshold": meets_threshold
        }
        socketio.emit('experiment_finished', result)
        print(f"[Experiment] Finalizado: {result}")

    threading.Thread(target=run_simulation, daemon=True).start()
    return jsonify({
        "message": "Experimento iniciado", "scenario": scenario
    })


@app.route('/api/experiment/run-all', methods=['POST'])
def run_all_experiments():
    SCENARIOS = ['normal', 'massive', 'gradual']
    SCENARIO_PARAMS = {
        'normal': {'num_queries': 50, 'delay': 1.5, 'label': 'Comportamiento Normal'},
        'massive': {'num_queries': 200, 'delay': 0.01, 'label': 'Extraccion Masiva'},
        'gradual': {'num_queries': 151, 'delay': 0.1, 'label': 'Escala Gradual'},
    }

    def run_all():
        results = []
        for idx, scenario in enumerate(SCENARIOS):
            params = SCENARIO_PARAMS[scenario]
            print(f"[Experiment] ({idx+1}/3) Iniciando: {params['label']}")
            socketio.emit('experiment_started', {
                'scenario': scenario,
                'current': idx + 1,
                'total': 3,
                'label': params['label']
            })
            time.sleep(1)

            num_queries = params['num_queries']
            delay_between = params['delay']

            sim_email = f"sim_{scenario}_{uuid.uuid4().hex[:6]}@test.com"
            try:
                reg_resp = requests.post(
                    f"{SERVICES['auth']}/register",
                    json={"name": f"Sim {scenario}", "email": sim_email,
                          "password": "pass"},
                    timeout=10
                )
                if reg_resp.status_code == 201:
                    login_resp = requests.post(
                        f"{SERVICES['auth']}/login",
                        json={"email": sim_email, "password": "pass"},
                        timeout=10
                    )
                    user_data = login_resp.json()
                    user_id = user_data.get('user', {}).get('id', 1)
                    sess_id = user_data.get('session_id', str(uuid.uuid4()))
                else:
                    user_id = 1
                    sess_id = str(uuid.uuid4())
            except Exception:
                user_id = 1
                sess_id = str(uuid.uuid4())

            start_time = time.time()
            success_count = 0
            fail_count = 0
            detection_time = 0

            for i in range(num_queries):
                if scenario == 'gradual':
                    delay_between *= 0.95
                time.sleep(delay_between)
                try:
                    cot_resp = requests.get(
                        f"{SERVICES['cotizacion']}/quote",
                        headers={'X-Session-ID': sess_id,
                                 'X-User-ID': str(user_id)},
                        timeout=10
                    ).json()
                    if cot_resp.get('status') == 'ANOMALY_DETECTED':
                        detection_time = cot_resp.get('detection_time_ms', 0)
                        fail_count += 1
                        break
                    elif cot_resp.get('status') == 'BLOCKED':
                        fail_count += 1
                        break
                    else:
                        success_count += 1
                except Exception:
                    fail_count += 1

            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            is_anomalous = 1 if detection_time > 0 else 0
            meets_threshold = (
                1 if (detection_time > 0 and detection_time < 1000)
                else (1 if scenario == 'normal' else 0)
            )

            result = {
                "scenario": scenario,
                "label": params['label'],
                "total_queries": success_count + fail_count,
                "successful": success_count,
                "failed": fail_count,
                "duration_ms": round(duration_ms, 2),
                "detection_time_ms": round(detection_time, 2),
                "is_anomalous": is_anomalous,
                "meets_threshold": meets_threshold
            }
            results.append(result)
            socketio.emit('experiment_finished', result)
            print(f"[Experiment] ({idx+1}/3) Finalizado: {result}")

        all_meet = all(r['meets_threshold'] for r in results)
        verdict = {
            "cumple": all_meet,
            "results": results,
            "message": ("Todos los escenarios detectaron correctamente"
                        if all_meet
                        else "Al menos un escenario no cumple el umbral")
        }
        socketio.emit('experiment_all_finished', verdict)
        print(f"[Experiment] Veredicto: {'CUMPLE' if all_meet else 'NO CUMPLE'}")

    threading.Thread(target=run_all, daemon=True).start()
    return jsonify({"message": "Experimentos iniciados", "total": 3})


@app.route('/api/experiment/results', methods=['GET'])
def get_results():
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'experiment.db')
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        results = db.execute(
            "SELECT * FROM experiment_results ORDER BY id DESC LIMIT 20"
        ).fetchall()
        db.close()
        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/experiment/stats', methods=['GET'])
def get_stats():
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'experiment.db')
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        total = db.execute(
            "SELECT COUNT(*) FROM experiment_results"
        ).fetchone()[0]
        anomalous = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE is_anomalous = 1"
        ).fetchone()[0]
        avg_det = db.execute(
            "SELECT AVG(detection_time_ms) FROM experiment_results "
            "WHERE detection_time_ms > 0"
        ).fetchone()[0]
        if avg_det is None:
            avg_det = 0
        scenarios = db.execute(
            "SELECT scenario, COUNT(*) as count "
            "FROM experiment_results GROUP BY scenario"
        ).fetchall()
        db.close()
        return jsonify({
            "total_experiments": total,
            "anomalous_sessions": anomalous,
            "avg_detection_time": round(avg_det, 2),
            "scenarios": [dict(s) for s in scenarios]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("  Experimento H710 - Deteccion de Comportamiento Anomalo")
    print("  Dashboard (Puerto 5000) - Microservicios independientes")
    print(f"  Auth:       {SERVICES['auth']}")
    print(f"  Cotizacion: {SERVICES['cotizacion']}")
    print(f"  Monitor:    {SERVICES['monitor']}")
    print(f"  Autorizador:{SERVICES['autorizador']}")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=DASHBOARD_PORT, debug=True,
                 allow_unsafe_werkzeug=True)
