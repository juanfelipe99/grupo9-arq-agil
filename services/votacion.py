from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/votar', methods=['POST'])
def votar():
    data = request.get_json()
    resultados = data.get('resultados', [])

    if len(resultados) != 3:
        return jsonify({'error': 'Se esperan exactamente 3 resultados'}), 400

    scores = [r.get('score', 0) for r in resultados]
    ratings = [r.get('rating', '') for r in resultados]

    score_counts = {}
    for s in scores:
        rounded = round(s, 2)
        score_counts[rounded] = score_counts.get(rounded, 0) + 1

    unanimous = len(score_counts) == 1

    outlier_idx = None
    resultado_valido = None
    descartado = None

    if unanimous:
        resultado_valido = resultados[0]
        descartado = None
    else:
        for i, s in enumerate(scores):
            rounded = round(s, 2)
            if score_counts[rounded] == 1:
                outlier_idx = i
                descartado = resultados[i]
                break

        valid_scores = [s for i, s in enumerate(scores) if i != outlier_idx]
        resultado_valido = next(
            (r for r in resultados if round(r.get('score', 0), 2) == round(valid_scores[0], 2)),
            resultados[0]
        )

    return jsonify({
        'resultado_valido': resultado_valido,
        'descartado': descartado,
        'voto_unanimidad': unanimous,
        'scores_recibidos': scores,
        'outlier_detectado': outlier_idx is not None
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'votacion'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, threaded=True)
