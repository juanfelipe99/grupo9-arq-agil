from flask import Flask, request, jsonify
import random
import time

app = Flask(__name__)

@app.route('/enmascarar', methods=['POST'])
def enmascarar():
    data = request.get_json()
    resultado_valido = data.get('resultado_valido')
    descartado = data.get('descartado')

    if resultado_valido is None:
        return jsonify({'error': 'No se recibio resultado valido'}), 400

   

    return jsonify({
        'resultado_final': resultado_valido,
        'resultado_ocultado': descartado,
        'enmascarado': True,
        'latencia_ms': 0
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'enmascaramiento'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, threaded=True)
