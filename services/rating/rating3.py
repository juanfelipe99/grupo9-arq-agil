import logging

from waitress import serve
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/calcular', methods=['POST'])
def calcular():
    data = request.get_json()
    monto = data.get('monto', 0)
    tipo = data.get('tipo', 'general')
    fail_mode = request.args.get('fail', 'false').lower() == 'true'

    if fail_mode:
        score = round(-abs(monto * 0.5), 2)
        rating = 'F'
    else:
        score = round(monto * 0.15, 2)
        rating = 'A' if score > 50 else 'B' if score > 20 else 'C'

    return jsonify({
        'rating': rating,
        'score': score,
        'instancia': 'rating3',
        'monto': monto,
        'tipo': tipo,
        'fail_mode': fail_mode
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'instancia': 'rating3'})

if __name__ == '__main__':
    logging.getLogger('waitress.queue').setLevel(logging.ERROR)
    serve(app, host='0.0.0.0', port=5003, threads=32, connection_limit=512, backlog=2048)
