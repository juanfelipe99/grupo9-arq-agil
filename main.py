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

from db import abrir
from config import (SERVICES, DASHBOARD_PORT, BASELINE_QPM, BASELINE_MAXIMO,
                    BASELINE_MINIMO, ANOMALY_THRESHOLD, FACTOR_DESVIACION,
                    SCENARIO_DEFAULTS)

import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)
try:
    from flask import cli as _cli
    _cli.show_server_banner = lambda *a, **k: None
except Exception:
    pass

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


# =============================================================================
# PARAMETROS CONFIGURABLES DEL EXPERIMENTO
# =============================================================================
def _to_int(value, default, minimo=1, maximo=10000):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimo, min(maximo, number))


def _to_float(value, default, minimo=0.001, maximo=60.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimo, min(maximo, number))


def _scenario_params(scenario, overrides=None):
    base = SCENARIO_DEFAULTS.get(scenario, {}).copy()
    overrides = overrides or {}
    params = {
        'num_queries': _to_int(overrides.get('num_queries'),
                               base.get('num_queries', 50)),
        'delay': _to_float(overrides.get('delay'), base.get('delay', 1.0)),
        'decay': _to_float(overrides.get('decay'), base.get('decay', 0.95),
                           minimo=0.5, maximo=1.0),
        'label': base.get('label', scenario),
    }
    return params


def _aplicar_baseline(baseline):
    """Propaga la linea base de arranque. El Monitor deriva el umbral."""
    try:
        requests.post(f"{SERVICES['monitor']}/config",
                      json={"baseline": baseline}, timeout=5)
    except Exception as e:
        print(f"[Experiment] No se pudo propagar la linea base: {e}")


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


@app.route('/api/auth/logout', methods=['POST'])
def proxy_logout():
    try:
        resp = requests.post(
            f"{SERVICES['auth']}/logout", json=request.json, timeout=10
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
    from concurrent.futures import ThreadPoolExecutor

    def check(item):
        name, url = item
        try:
            resp = requests.get(f"{url}/health", timeout=1)
            return name, resp.json().get('status') == 'ok'
        except Exception:
            return name, False

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = pool.map(check, SERVICES.items())
    status = dict(results)
    status['dashboard'] = True
    return jsonify(status)


def consultar_deteccion(session_id, intentos=12, pausa=0.25):
    """Pide al Monitor el tiempo de deteccion medido para la sesion.

    Con el registro asincrono, la respuesta de Cotizacion ya no trae ese
    dato: la deteccion ocurre en el Monitor poco despues de la consulta que
    cruza el umbral, asi que se consulta con unos reintentos breves.
    """
    for _ in range(intentos):
        try:
            resp = requests.get(
                f"{SERVICES['monitor']}/deteccion/{session_id}", timeout=3)
            if resp.status_code == 200:
                datos = resp.json()
                return (datos.get('tiempo_deteccion_ms', 0),
                        datos.get('tiempo_revocacion_ms', 0),
                        datos.get('tiempo_total_ms', 0))
        except Exception:
            pass
        time.sleep(pausa)
    return (0, 0, 0)


def consultar_serie(session_id):
    """Trae del Monitor la curva de tasa contra umbral de la sesion."""
    try:
        resp = requests.get(f"{SERVICES['monitor']}/serie/{session_id}",
                            timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {"puntos": [], "deteccion_t": None}


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'data', 'experiment.db')


def guardar_resultado(result):
    """Persiste el resultado de un escenario en experiment_results."""
    try:
        with abrir(DB_PATH) as db:
            # La tabla nacio sin estas dos columnas y hay bases ya creadas.
            existentes = {f[1] for f in db.execute(
                "PRAGMA table_info(experiment_results)")}
            for columna in ('revocation_time_ms', 'total_time_ms'):
                if columna not in existentes:
                    db.execute("ALTER TABLE experiment_results ADD COLUMN "
                               + columna + " REAL DEFAULT 0")
            db.execute(
                "INSERT INTO experiment_results (scenario, total_queries, "
                "successful, failed, duration_ms, detection_time_ms, "
                "revocation_time_ms, total_time_ms, is_anomaly, "
                "meets_threshold) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (result['scenario'], result['total_queries'],
                 result['successful'], result['failed'], result['duration_ms'],
                 result['detection_time_ms'], result['revocation_time_ms'],
                 result['total_time_ms'], result['is_anomalous'],
                 result['meets_threshold'])
            )
            db.commit()
    except Exception as e:
        print(f"[Experiment] Error guardando resultado: {e}")


# =============================================================================
# API - Experimento
# =============================================================================
# El normal representa a un administrador al que el sistema lleva tiempo
# observando, asi que conserva su cuenta entre corridas y su linea base se
# afina hacia su ritmo real. Los de ataque estrenan cuenta cada vez, para que
# cada corrida arranque del mismo punto.
USUARIOS_PERSISTENTES = {'normal': 'sim_normal@test.com'}


def _sesion_simulada(scenario):
    """Devuelve (user_id, session_id) del usuario de simulacion."""
    email = (USUARIOS_PERSISTENTES.get(scenario)
             or f"sim_{scenario}_{uuid.uuid4().hex[:6]}@test.com")
    try:
        # Si ya existe, el registro falla y no pasa nada: lo que importa es
        # el login, que es lo que abre la sesion.
        requests.post(
            f"{SERVICES['auth']}/register",
            json={"name": f"Sim {scenario}", "email": email,
                  "password": "pass"},
            timeout=10
        )
        login_resp = requests.post(
            f"{SERVICES['auth']}/login",
            json={"email": email, "password": "pass"},
            timeout=10
        )
        if login_resp.status_code == 200:
            user_data = login_resp.json()
            return (user_data.get('user', {}).get('id', 1),
                    user_data.get('session_id', str(uuid.uuid4())))
    except Exception:
        pass
    return 1, str(uuid.uuid4())


def ejecutar_escenario(scenario, params):
    """Corre un escenario completo y devuelve su resultado ya persistido.

    La misma rutina sirve para una corrida suelta y para la tanda de los tres
    escenarios, asi que el experimento mide siempre exactamente lo mismo.
    """
    num_queries = params['num_queries']
    delay_between = params['delay']
    user_id, sess_id = _sesion_simulada(scenario)

    start_time = time.time()
    success_count = 0
    fail_count = 0
    detection_time = 0
    revocation_time = 0
    total_time = 0

    for _ in range(num_queries):
        if scenario == 'gradual':
            delay_between *= params.get('decay', 0.95)
        time.sleep(delay_between)

        # Cualquier respuesta que no sea una cotizacion servida significa que
        # la sesion ya no pasa: se corta ahi, que es justo lo que el
        # experimento debe demostrar.
        try:
            resp = requests.get(
                f"{SERVICES['cotizacion']}/quote",
                headers={'X-Session-ID': sess_id},
                timeout=10
            )
            cot_resp = resp.json()
            if resp.status_code != 200 or cot_resp.get('status') != 'OK':
                (detection_time, revocation_time,
                 total_time) = consultar_deteccion(sess_id)
                fail_count += 1
                break
            success_count += 1
        except Exception:
            fail_count += 1

    if detection_time == 0:
        (detection_time, revocation_time,
         total_time) = consultar_deteccion(sess_id, intentos=8)

    duration_ms = (time.time() - start_time) * 1000
    is_anomalous = 1 if detection_time > 0 else 0
    # El ASR acota detectar y retirar permisos en conjunto, asi que se juzga
    # el total. El escenario normal cumple justamente por no disparar nada.
    corrio = success_count > 0
    if not corrio:
        # Sin una sola consulta servida no hay nada que juzgar. Darlo por
        # cumplido dejaria pasar en silencio una corrida que fallo entera.
        print(f"[Experiment] {scenario}: ninguna consulta pudo servirse")
    meets_threshold = (
        1 if (detection_time > 0 and total_time < 1000)
        else (1 if (scenario == 'normal' and corrio) else 0)
    )

    result = {
        "scenario": scenario,
        "label": params.get('label', scenario),
        "session_id": sess_id,
        "planned_queries": num_queries,
        "total_queries": success_count + fail_count,
        "successful": success_count,
        "failed": fail_count,
        "duration_ms": round(duration_ms, 2),
        "detection_time_ms": round(detection_time, 2),
        "revocation_time_ms": round(revocation_time, 2),
        "total_time_ms": round(total_time, 2),
        "is_anomalous": is_anomalous,
        "meets_threshold": meets_threshold
    }
    guardar_resultado(result)
    latencia = latencia_de(sess_id)
    result['latencia_p50_ms'] = latencia['p50']
    result['latencia_p95_ms'] = latencia['p95']
    result['serie'] = consultar_serie(sess_id)
    return result


@app.route('/api/experiment/config', methods=['GET'])
def get_experiment_config():
    return jsonify({
        "baseline_qpm": BASELINE_QPM,
        "threshold_qpm": ANOMALY_THRESHOLD,
        "factor": FACTOR_DESVIACION,
        "umbral_maximo": round(BASELINE_MAXIMO * FACTOR_DESVIACION),
        "umbral_piso": round(BASELINE_MINIMO * FACTOR_DESVIACION),
        "scenarios": SCENARIO_DEFAULTS,
    })


@app.route('/api/experiment/run', methods=['POST'])
def run_experiment():
    data = request.json or {}
    scenario = data.get('scenario', 'normal')
    params = _scenario_params(scenario, data)
    baseline = _to_int(data.get('baseline_qpm'), BASELINE_QPM)
    if scenario not in SCENARIO_DEFAULTS:
        return jsonify({"error": f"Escenario desconocido: {scenario}"}), 400
    _aplicar_baseline(baseline)

    def run_simulation():
        print(f"[Experiment] Iniciando escenario: {scenario}")
        time.sleep(1)
        socketio.emit('experiment_started', {'scenario': scenario})
        result = ejecutar_escenario(scenario, params)
        socketio.emit('experiment_finished', result)
        print(f"[Experiment] Finalizado: {result}")

    threading.Thread(target=run_simulation, daemon=True).start()
    return jsonify({
        "message": "Experimento iniciado", "scenario": scenario,
        "num_queries": params['num_queries'], "delay": params['delay'],
        "threshold_qpm": round(baseline * FACTOR_DESVIACION),
    })


@app.route('/api/experiment/run-all', methods=['POST'])
def run_all_experiments():
    data = request.json or {}
    baseline = _to_int(data.get('baseline_qpm'), BASELINE_QPM)
    overrides = data.get('scenarios', {})
    SCENARIOS = ['normal', 'massive', 'gradual']
    SCENARIO_PARAMS = {
        key: _scenario_params(key, (overrides.get(key) or {}))
        for key in SCENARIOS
    }
    _aplicar_baseline(baseline)

    def run_all():
        results = []
        for idx, scenario in enumerate(SCENARIOS):
            params = SCENARIO_PARAMS[scenario]
            print(f"[Experiment] ({idx+1}/{len(SCENARIOS)}) Iniciando: {params['label']}")
            socketio.emit('experiment_started', {
                'scenario': scenario,
                'current': idx + 1,
                'total': len(SCENARIOS),
                'label': params['label']
            })
            time.sleep(1)

            result = ejecutar_escenario(scenario, params)
            results.append(result)
            socketio.emit('experiment_finished', result)
            print(f"[Experiment] ({idx+1}/{len(SCENARIOS)}) Finalizado: {result}")

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
    return jsonify({"message": "Experimentos iniciados", "total": len(SCENARIOS),
                    "threshold_qpm": round(baseline * FACTOR_DESVIACION),
                    "scenarios": SCENARIO_PARAMS})


def latencia_de(session_id):
    """Percentiles del tiempo de respuesta de las cotizaciones servidas.

    Mide el costo de vigilar. El registro de comportamiento viaja asincrono
    para no encarecer la respuesta, y esto lo comprueba en vez de suponerlo.
    """
    try:
        with abrir(DB_PATH) as db:
            filas = db.execute(
                "SELECT response_time_ms FROM logs "
                "WHERE session_id = ? AND query_type = 'quote' "
                "AND is_anomaly = 0",
                (session_id,)
            ).fetchall()
    except Exception as e:
        print(f"[Experiment] Error leyendo latencias: {e}")
        return {"p50": 0, "p95": 0}
    valores = sorted(f[0] for f in filas if f[0] is not None)
    return {"p50": round(_percentil(valores, 50), 2),
            "p95": round(_percentil(valores, 95), 2)}


def _percentil(valores, pct):
    """Percentil por rango mas cercano sobre una lista ya ordenada."""
    if not valores:
        return 0
    idx = max(0, min(len(valores) - 1,
                     int(round(pct / 100.0 * len(valores) + 0.5)) - 1))
    return valores[idx]


@app.route('/api/experiment/results', methods=['GET'])
def get_results():
    try:
        with abrir(DB_PATH) as db:
            results = db.execute(
                "SELECT * FROM experiment_results ORDER BY id DESC LIMIT 20"
            ).fetchall()
        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/experiment/stats', methods=['GET'])
def get_stats():
    try:
        with abrir(DB_PATH) as db:
            total = db.execute(
                "SELECT COUNT(*) FROM experiment_results"
            ).fetchone()[0]
            anomalous = db.execute(
                "SELECT COUNT(*) FROM sessions WHERE is_anomalous = 1"
            ).fetchone()[0]
            avg_det = db.execute(
                "SELECT AVG(total_time_ms) FROM experiment_results "
                "WHERE total_time_ms > 0"
            ).fetchone()[0] or 0
            scenarios = db.execute(
                "SELECT scenario, COUNT(*) as count "
                "FROM experiment_results GROUP BY scenario"
            ).fetchall()
        return jsonify({
            "total_experiments": total,
            "anomalous_sessions": anomalous,
            "avg_detection_time": round(avg_det, 2),
            "scenarios": [dict(s) for s in scenarios]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print(f"[Dashboard] escuchando en el puerto {DASHBOARD_PORT}")
    socketio.run(app, host='0.0.0.0', port=DASHBOARD_PORT,
                 debug=os.environ.get('FLASK_DEBUG') == '1',
                 allow_unsafe_werkzeug=True)
