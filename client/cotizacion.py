import logging

from waitress import serve
from flask import Flask, request, jsonify, render_template
import requests
import urllib3
import json
import time
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics
import threading
import uuid

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
sys.path.insert(0, PROJECT_ROOT)
from config import RATING_INSTANCES, VOTACION_URL, ENMASCARAMIENTO_URL, RESPONSE_TIME_LIMIT_MS

app = Flask(__name__, template_folder=os.path.join(PROJECT_ROOT, 'client', 'templates'))

PORT = int(os.environ.get('PORT', 5000))
COTIZAR_URL = f'http://127.0.0.1:{PORT}/cotizar'

COTIZACION_THREADS = int(os.environ.get('COTIZACION_THREADS', 64))
RATING_EXECUTOR = ThreadPoolExecutor(
    max_workers=COTIZACION_THREADS * len(RATING_INSTANCES))

SESION = requests.Session()
SESION.mount('http://', requests.adapters.HTTPAdapter(
    pool_connections=16, pool_maxsize=160))

POOL = urllib3.PoolManager(num_pools=16, maxsize=160, retries=False, block=False)
_JSON_HEADERS = {'Content-Type': 'application/json'}

TRABAJOS = {}
TRABAJOS_LOCK = threading.Lock()
MAX_TRABAJOS = 5

def post_json(url, obj, timeout=10):
    r = POOL.request('POST', url, body=json.dumps(obj).encode('utf-8'),
                     headers=_JSON_HEADERS, timeout=timeout)
    if r.status != 200:
        return r.status, None
    return r.status, json.loads(r.data)

def resolve_fail_rating(fail_rating):
    if fail_rating in ('', 'false', False):
        return None
    if fail_rating == 'random':
        return random.choice(['rating1', 'rating2', 'rating3'])
    if fail_rating in RATING_INSTANCES:
        return fail_rating
    return None

def call_rating(name, url, payload, fail=False):
    start = time.perf_counter()
    query = '?fail=true' if fail else ''
    _, data = post_json(f"{url}/calcular{query}", payload)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    data['tiempo_ms'] = elapsed_ms
    return data

@app.route('/cotizar', methods=['POST'])
def cotizar():
    try:
        data = request.get_json()
        monto = data.get('monto', 1000)
        tipo = data.get('tipo', 'general')
        fail_rating = data.get('fail_rating', '')

        fail_target = resolve_fail_rating(fail_rating)
        payload = {'monto': monto, 'tipo': tipo}

        start_total = time.perf_counter()

        futures = [
            RATING_EXECUTOR.submit(call_rating, name, url, payload, name == fail_target)
            for name, url in RATING_INSTANCES.items()
        ]
        resultados = [f.result() for f in futures]

        fin_rating = time.perf_counter()

        status, vote_resp = post_json(VOTACION_URL + '/votar', {'resultados': resultados})
        if vote_resp is None:
            return jsonify({'error': f'Votacion returned {status}'}), 500
        fin_votacion = time.perf_counter()

        status, mask_resp = post_json(ENMASCARAMIENTO_URL + '/enmascarar', vote_resp)
        if mask_resp is None:
            return jsonify({'error': f'Enmascaramiento returned {status}'}), 500
        fin_mask = time.perf_counter()

        rating_ms = round((fin_rating - start_total) * 1000, 2)
        votacion_ms = round((fin_votacion - fin_rating) * 1000, 2)
        enmascaramiento_ms = round((fin_mask - fin_votacion) * 1000, 2)
        total_ms = round((fin_mask - start_total) * 1000, 2)

        rating_mas_lento_ms = max((r.get('tiempo_ms', 0) for r in resultados), default=0)
        orquestacion_ms = round(rating_ms - rating_mas_lento_ms, 2)

        dentro_limite = total_ms <= RESPONSE_TIME_LIMIT_MS

        return jsonify({
            'resultado_final': mask_resp.get('resultado_final'),
            'resultado_ocultado': mask_resp.get('resultado_ocultado'),
            'voto_unanimidad': vote_resp.get('voto_unanimidad'),
            'outlier_detectado': vote_resp.get('outlier_detectado'),
            'rating_fallo': fail_target,
            'tiempo_total_ms': total_ms,
            'dentro_limite_250ms': dentro_limite,
            'scores_recibidos': vote_resp.get('scores_recibidos'),
            'latencia_enmascaramiento_ms': mask_resp.get('latencia_ms'),
            'etapas_ms': {
                'rating': rating_ms,
                'votacion': votacion_ms,
                'enmascaramiento': enmascaramiento_ms,
                'rating_mas_lento': rating_mas_lento_ms,
                'orquestacion': orquestacion_ms
            }
        })
    except Exception:
        app.logger.exception('Error procesando /cotizar')
        return jsonify({'error': 'Error interno procesando la cotizacion'}), 500

@app.route('/load-test', methods=['POST'])
def load_test():
    data = request.get_json(silent=True) or {}
    users = data.get('users', 10)
    loops = data.get('loops', 10)

    MAX_USERS = 60
    MAX_LOOPS = 500
    if not isinstance(users, int) or not isinstance(loops, int) or users < 1 or loops < 1:
        return jsonify({'error': 'users y loops deben ser enteros mayores que cero'}), 400
    if users > MAX_USERS or loops > MAX_LOOPS:
        return jsonify({
            'error': f'Limite excedido: maximo {MAX_USERS} usuarios concurrentes '
                     f'y {MAX_LOOPS} iteraciones por usuario. '
                     f'Recibido: {users} usuarios, {loops} iteraciones.'
        }), 400

    trabajo_id = uuid.uuid4().hex[:12]
    total = users * loops
    with TRABAJOS_LOCK:
        for viejo in list(TRABAJOS)[:-(MAX_TRABAJOS - 1)] if len(TRABAJOS) >= MAX_TRABAJOS else []:
            TRABAJOS.pop(viejo, None)
        TRABAJOS[trabajo_id] = {'estado': 'ejecutando', 'completadas': 0,
                                'total': total, 'resultado': None, 'error': None}

    hilo = threading.Thread(
        target=ejecutar_prueba,
        args=(trabajo_id, users, loops, data.get('fail_mode', ''),
              data.get('monto', 1000), data.get('tipo', 'general')),
        daemon=True)
    hilo.start()

    return jsonify({'trabajo_id': trabajo_id, 'total': total}), 202


@app.route('/load-test/<trabajo_id>', methods=['GET'])
def load_test_estado(trabajo_id):
    with TRABAJOS_LOCK:
        trabajo = TRABAJOS.get(trabajo_id)
    if trabajo is None:
        return jsonify({'error': 'Trabajo no encontrado'}), 404
    return jsonify(trabajo)


def ejecutar_prueba(trabajo_id, users, loops, fail_mode, monto, tipo):
    """Corre la prueba de carga en segundo plano y publica el avance.

    Se ejecuta fuera del ciclo de peticion HTTP porque una corrida grande
    tarda mas de los 30 segundos que Heroku permite por peticion.
    """
    def avanzar():
        with TRABAJOS_LOCK:
            t = TRABAJOS.get(trabajo_id)
            if t:
                t['completadas'] += 1

    try:
        total_requests = users * loops
        results = []
        start_all = time.perf_counter()

        def single_request(_):
            start = time.perf_counter()
            try:
                current_fail = resolve_fail_rating(fail_mode)
                payload = {'monto': monto, 'tipo': tipo, 'fail_rating': current_fail or ''}
                resp = SESION.post(COTIZAR_URL, json=payload, timeout=30)
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                if resp.status_code != 200:
                    return {'ok': False, 'time_ms': elapsed, 'error': f'HTTP {resp.status_code}'}
                body = resp.json()
                return {
                    'ok': True,
                    'time_ms': body.get('tiempo_total_ms', elapsed),
                    'within_limit': body.get('dentro_limite_250ms', False),
                    'outlier': body.get('outlier_detectado', False),
                    'rating_fallo': body.get('rating_fallo'),
                    'etapas': body.get('etapas_ms')
                }
            except Exception as e:
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                return {'ok': False, 'time_ms': elapsed, 'error': str(e)}
            finally:
                avanzar()

        with ThreadPoolExecutor(max_workers=users) as executor:
            for f in as_completed([executor.submit(single_request, 0)
                                   for _ in range(total_requests)]):
                results.append(f.result())

        total_time = round((time.perf_counter() - start_all) * 1000, 2)
        times = sorted(r['time_ms'] for r in results)
        ok_results = [r for r in results if r['ok']]
        errors = len(results) - len(ok_results)
        within_limit_count = sum(1 for r in ok_results if r['within_limit'])

        etapas_mediana = {}
        muestras_etapas = [r['etapas'] for r in ok_results if r.get('etapas')]
        if muestras_etapas:
            for clave in ('rating', 'votacion', 'enmascaramiento', 'rating_mas_lento', 'orquestacion'):
                valores = [m[clave] for m in muestras_etapas if clave in m]
                if valores:
                    etapas_mediana[clave] = round(statistics.median(valores), 2)

        fail_counts = {}
        for r in ok_results:
            rf = r.get('rating_fallo')
            if rf:
                fail_counts[rf] = fail_counts.get(rf, 0) + 1

        resultado = {
            'total_requests': total_requests,
            'users': users,
            'loops': loops,
            'errors': errors,
            'success': len(ok_results),
            'total_time_ms': total_time,
            'stats': {
                'min_ms': round(times[0], 2) if times else 0,
                'max_ms': round(times[-1], 2) if times else 0,
                'avg_ms': round(statistics.mean(times), 2) if times else 0,
                'median_ms': round(statistics.median(times), 2) if times else 0,
            },
            'etapas_mediana_ms': etapas_mediana,
            'within_250ms': within_limit_count,
            'within_250ms_pct': round(within_limit_count / len(ok_results) * 100, 2) if ok_results else 0,
            'outliers_detected': sum(1 for r in ok_results if r.get('outlier', False)),
            'fail_distribution': fail_counts,
            'rps': round(len(ok_results) / (total_time / 1000), 2) if total_time else 0
        }
        with TRABAJOS_LOCK:
            t = TRABAJOS.get(trabajo_id)
            if t:
                t['resultado'] = resultado
                t['estado'] = 'terminado'
    except Exception as e:
        app.logger.exception('Error ejecutando la prueba de carga')
        with TRABAJOS_LOCK:
            t = TRABAJOS.get(trabajo_id)
            if t:
                t['estado'] = 'error'
                t['error'] = str(e)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'cotizacion'})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    logging.getLogger('waitress.queue').setLevel(logging.ERROR)
    serve(app, host='0.0.0.0', port=PORT, threads=COTIZACION_THREADS, connection_limit=512, backlog=2048)
