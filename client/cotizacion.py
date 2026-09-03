from concurrent import futures

from flask import Flask, request, jsonify, render_template
import requests
import time
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import statistics

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
sys.path.insert(0, PROJECT_ROOT)
from config import RATING_INSTANCES, VOTACION_URL, ENMASCARAMIENTO_URL, RESPONSE_TIME_LIMIT_MS

app = Flask(__name__, template_folder=os.path.join(PROJECT_ROOT, 'client', 'templates'))

COTIZAR_URL = 'http://127.0.0.1:5000/cotizar'
RATING_EXECUTOR = ThreadPoolExecutor(max_workers=30)


def resolve_fail_rating(fail_rating):
    if fail_rating in ('', 'false', False):
        return None
    if fail_rating == 'random':
        return random.choice(['rating1', 'rating2', 'rating3'])
    if fail_rating in RATING_INSTANCES:
        return fail_rating
    return None

def call_rating(name, url, payload, fail=False):
    start = time.time()
    query = '?fail=true' if fail else ''
    resp = requests.post(f"{url}/calcular{query}", json=payload, timeout=10)
    elapsed_ms = round((time.time() - start) * 1000, 2)
    data = resp.json()
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

        start_total = time.time()

        futures = {}
        for name, url in RATING_INSTANCES.items():
            use_fail = (name == fail_target)
            futures[name] = RATING_EXECUTOR.submit(
                call_rating, name, url, payload, use_fail
            )

        resultados = [f.result() for f in futures.values()]
        rating_end = time.time()
        rating_ms = round((rating_end - start_total) * 1000, 2)
        vote_start = time.time()
        vote_resp_raw = requests.post(
            VOTACION_URL + '/votar',
            json={'resultados': resultados},
            timeout=10
        )
        if vote_resp_raw.status_code != 200:
            return jsonify({'error': f'Votacion returned {vote_resp_raw.status_code}', 'body': vote_resp_raw.text}), 500
        vote_resp = vote_resp_raw.json()
        vote_ms = round((time.time() - vote_start) * 1000, 2)

        mask_start = time.time()
        mask_resp_raw = requests.post(
            ENMASCARAMIENTO_URL + '/enmascarar',
            json=vote_resp,
            timeout=10
        )
        if mask_resp_raw.status_code != 200:
            return jsonify({'error': f'Enmascaramiento returned {mask_resp_raw.status_code}', 'body': mask_resp_raw.text}), 500
        mask_resp = mask_resp_raw.json()
        mask_ms = round((time.time() - mask_start) * 1000, 2)
        total_ms = round((time.time() - start_total) * 1000, 2)
        print(
            f"[TIEMPOS] Rating={rating_ms} ms | "
            f"Votacion={vote_ms} ms | "
            f"Enmascaramiento={mask_ms} ms | "
            f"Total={total_ms} ms"
        )
        
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
            'rating_ms': rating_ms,
            'votacion_ms': vote_ms,
            'enmascaramiento_ms': mask_ms
        })
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/load-test', methods=['POST'])
def load_test():
    try:
        data = request.get_json()
        users = data.get('users', 10)
        loops = data.get('loops', 10)
        fail_mode = data.get('fail_mode', '')
        monto = data.get('monto', 1000)
        tipo = data.get('tipo', 'general')

        MAX_TOTAL = 500
        total_requests = users * loops
        if total_requests > MAX_TOTAL:
            return jsonify({
                'error': f'Total de peticiones ({total_requests}) excede el limite de {MAX_TOTAL}. Reduce usuarios o iteraciones.'
            }), 400

        results = []
        errors = 0
        start_all = time.time()

        def single_request(idx):
            start = time.time()
            try:
                current_fail = resolve_fail_rating(fail_mode)
                payload = {
                    'monto': monto,
                    'tipo': tipo,
                    'fail_rating': current_fail or ''
                }
                resp = requests.post(COTIZAR_URL, json=payload, timeout=30)
                elapsed = round((time.time() - start) * 1000, 2)
                if resp.status_code == 200:
                    body = resp.json()
                    return {
                        'ok': True,
                        'time_ms': body.get('tiempo_total_ms', elapsed),
                        'within_limit': body.get('dentro_limite_250ms', False),
                        'outlier': body.get('outlier_detectado', False),
                        'rating_fallo': body.get('rating_fallo')
                    }
                else:
                    return {'ok': False, 'time_ms': elapsed, 'error': f'HTTP {resp.status_code}'}
            except Exception as e:
                elapsed = round((time.time() - start) * 1000, 2)
                return {'ok': False, 'time_ms': elapsed, 'error': str(e)}

        with ThreadPoolExecutor(max_workers=users) as executor:
            futures = []
            for _ in range(total_requests):
                futures.append(executor.submit(single_request, 0))

            for f in as_completed(futures):
                r = f.result()
                results.append(r)
                if not r['ok']:
                    errors += 1

        total_time = round((time.time() - start_all) * 1000, 2)
        times = [r['time_ms'] for r in results]
        ok_results = [r for r in results if r['ok']]

        within_limit_count = sum(1 for r in ok_results if r['within_limit'])
        outlier_count = sum(1 for r in ok_results if r.get('outlier', False))

        fail_counts = {}
        for r in ok_results:
            rf = r.get('rating_fallo')
            if rf:
                fail_counts[rf] = fail_counts.get(rf, 0) + 1

        response = {
            'total_requests': total_requests,
            'users': users,
            'loops': loops,
            'errors': errors,
            'success': total_requests - errors,
            'total_time_ms': total_time,
            'stats': {
                'min_ms': round(min(times), 2) if times else 0,
                'max_ms': round(max(times), 2) if times else 0,
                'avg_ms': round(statistics.mean(times), 2) if times else 0,
                'median_ms': round(statistics.median(times), 2) if times else 0,
            },
            'within_250ms': within_limit_count,
            'within_250ms_pct': round(within_limit_count / (total_requests - errors) * 100, 2) if (total_requests - errors) > 0 else 0,
            'outliers_detected': outlier_count,
            'fail_distribution': fail_counts,
            'rps': round((total_requests - errors) / (total_time / 1000), 2) if total_time > 0 else 0
        }

        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'cotizacion'})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
