import logging

from waitress import serve
from flask import Flask, request, jsonify
import random
import time

app = Flask(__name__)

LATENCIA_SIMULADA_MS = (0, 0)
_LAT_MIN, _LAT_MAX = LATENCIA_SIMULADA_MS

@app.route('/enmascarar', methods=['POST'])
def enmascarar():
    data = request.get_json()
    resultado_valido = data.get('resultado_valido')
    descartado = data.get('descartado')

    if resultado_valido is None:
        return jsonify({'error': 'No se recibio resultado valido'}), 400

    latencia_ms = 0
    if _LAT_MAX > 0:
        espera = random.uniform(_LAT_MIN, _LAT_MAX) / 1000
        time.sleep(espera)
        latencia_ms = round(espera * 1000, 2)

    return jsonify({
        'resultado_final': resultado_valido,
        'resultado_ocultado': descartado,
        'enmascarado': True,
        'latencia_ms': latencia_ms
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'enmascaramiento'})

if __name__ == '__main__':
    logging.getLogger('waitress.queue').setLevel(logging.ERROR)
    serve(app, host='0.0.0.0', port=5005, threads=32, connection_limit=512, backlog=2048)
