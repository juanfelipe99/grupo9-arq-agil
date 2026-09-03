from waitress import serve
from flask import Flask, request, jsonify
import random
import time

app = Flask(__name__)

# Latencia simulada del enmascaramiento, en ms (minimo, maximo).
# Medida en ~20 ms de promedio, era el componente mas caro de toda la cadena
# sin realizar trabajo util. (0, 0) la desactiva; subelo si quieres volver a
# representar un costo de procesamiento en el experimento.
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
    serve(app, host='0.0.0.0', port=5005, threads=8)
