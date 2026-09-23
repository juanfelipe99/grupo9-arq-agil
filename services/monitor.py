"""
Microservicio: Monitor de Comportamiento - Puerto 5003
Recibe registros de consulta, compara la tasa actual de cada usuario contra
su comportamiento habitual y detecta desviaciones anomalas.

Modelo: cada usuario tiene una linea base en consultas por minuto, aprendida
de su propia actividad. Se considera anomalo superar esa linea base por un
factor dado. La linea base se muestrea como mucho una vez por ventana y nunca
durante una anomalia, de modo que una escalada sostenida no pueda arrastrarla
hasta normalizar el ataque.
"""

import os
import sys
import time
import threading
import sqlite3
import requests
from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (ALFA_APRENDIZAJE, ANOMALY_THRESHOLD as DEFAULT_THRESHOLD,
                    BASELINE_QPM, CAMBIO_MAXIMO, DERIVA_MAXIMA,
                    FACTOR_DESVIACION, MARGEN_APRENDIZAJE, UMBRAL_MINIMO,
                    VENTANA_SEGUNDOS as DEFAULT_VENTANA)
from db import abrir, conectar
from message_queue import consume_behavior_event, modo

import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)
try:
    from flask import cli as _cli
    _cli.show_server_banner = lambda *a, **k: None
except Exception:
    pass

app = Flask(__name__)

DATABASE = os.path.join(BASE_DIR, 'data', 'experiment.db')
AUTORIZADOR_URL = "http://127.0.0.1:5004"

ANOMALY_THRESHOLD = DEFAULT_THRESHOLD
VENTANA_SEGUNDOS = DEFAULT_VENTANA
FACTOR = FACTOR_DESVIACION
BASELINE_INICIAL = BASELINE_QPM
# Hasta donde puede llegar el habito de un usuario. Se recalculan cuando
# cambia la linea base de arranque.
BASELINE_MAXIMO = BASELINE_INICIAL * DERIVA_MAXIMA
BASELINE_MINIMO = BASELINE_INICIAL / DERIVA_MAXIMA

user_history = {}
baselines = {}
ultimo_aprendizaje = {}
detecciones = {}
# Serie de la tasa observada por sesion, para poder dibujar contra que umbral
# se comparo en cada momento. Se guardan pocas sesiones: es material de
# grafica, no evidencia, y la evidencia ya queda en la base.
series = {}
MAX_SERIES = 12
MAX_PUNTOS = 600
lock = threading.Lock()


def get_db():
    return conectar(DATABASE)


def init_baselines():
    """Crea la tabla de lineas base y carga las que ya existan.

    El comportamiento habitual se construye entre sesiones, asi que tiene que
    sobrevivir a los reinicios del servicio.
    """
    try:
        with abrir(DATABASE) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS user_baselines (
                user_id INTEGER PRIMARY KEY, baseline_qpm REAL NOT NULL,
                muestras INTEGER DEFAULT 0, updated_at TEXT)""")
            db.commit()
            for fila in db.execute("SELECT user_id, baseline_qpm FROM user_baselines"):
                baselines[fila['user_id']] = float(fila['baseline_qpm'])
        print(f"[Monitor] lineas base cargadas: {len(baselines)}")
    except Exception as e:
        print(f"[Monitor] Error cargando lineas base: {e}")


def guardar_baseline(user_id, valor):
    try:
        with abrir(DATABASE) as db:
            db.execute(
                "INSERT INTO user_baselines (user_id, baseline_qpm, muestras, updated_at) "
                "VALUES (?, ?, 1, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
                "baseline_qpm=excluded.baseline_qpm, muestras=muestras+1, "
                "updated_at=excluded.updated_at",
                (user_id, valor)
            )
            db.commit()
    except Exception as e:
        print(f"[Monitor] Error guardando linea base: {e}")


def umbral_de(user_id):
    """Umbral del usuario: su linea base por el factor de desviacion.

    No hay techo aparte: el umbral es siempre el triple del habito. Lo que
    esta acotado es el habito, que no puede alejarse mas de DERIVA_MAXIMA de
    la suposicion inicial, asi que el umbral queda acotado por consecuencia.
    """
    base = baselines.get(user_id, float(BASELINE_INICIAL))
    return max(UMBRAL_MINIMO, base * FACTOR)


def procesar_evento(session_id, user_id):
    """Cuenta la consulta y, si se desvia del habito, revoca y mide.

    El ASR acota las dos acciones juntas: detectar la desviacion y dejar la
    sesion sin permisos. El origen se fija dentro del lock y cada tramo se
    mide por separado, de modo que los dos suman el total exigido.
    """
    ahora = time.time()
    aprendido = None
    with lock:
        historial = user_history.setdefault(user_id, [])
        historial.append(ahora)
        user_history[user_id] = [t for t in historial
                                 if ahora - t < VENTANA_SEGUNDOS]
        tasa = len(user_history[user_id])

        base = baselines.setdefault(user_id, float(BASELINE_INICIAL))
        umbral_usuario = umbral_de(user_id)
        es_anomalia = tasa >= umbral_usuario
        ts_umbral = time.time() if es_anomalia else None

        # Se muestrea como mucho una vez por ventana y solo fuera de una
        # anomalia. Aprender en cada consulta dejaria que una escalada
        # continua arrastre el habito hasta normalizar el ataque.
        # La ventana esta llena cuando la consulta mas vieja que sigue dentro
        # ya tiene su edad. Mirar desde cuando se conoce al usuario daria por
        # llena una ventana con dos consultas sueltas.
        mas_vieja = user_history[user_id][0]
        ventana_llena = ahora - mas_vieja >= VENTANA_SEGUNDOS * 0.9
        if not es_anomalia and ventana_llena:
            desde = ultimo_aprendizaje.get(user_id, 0)
            # Solo cuenta como habito lo que se parece al habito. Una tasa muy
            # por encima puede ser legitima, pero no prueba una costumbre
            # nueva, y aceptarla es la palanca de una escalada paciente.
            cerca_del_habito = tasa <= base * MARGEN_APRENDIZAJE
            if ahora - desde >= VENTANA_SEGUNDOS and cerca_del_habito:
                propuesta = ((1 - ALFA_APRENDIZAJE) * base
                             + ALFA_APRENDIZAJE * tasa)
                # Se mueve despacio en los dos sentidos. Hacia arriba para
                # que no se pueda empujar, y hacia abajo para que una
                # temporada tranquila no deje el umbral tan bajo que el ritmo
                # normal lo dispare al volver.
                propuesta = min(base * (1 + CAMBIO_MAXIMO),
                                max(base * (1 - CAMBIO_MAXIMO), propuesta))
                base = min(BASELINE_MAXIMO, max(BASELINE_MINIMO, propuesta))
                baselines[user_id] = base
                ultimo_aprendizaje[user_id] = ahora
                aprendido = base

        baseline_actual = round(base, 2)
        ya_medida = session_id in detecciones

        serie = series.get(session_id)
        if serie is None:
            if len(series) >= MAX_SERIES:
                del series[next(iter(series))]
            serie = series[session_id] = {"t0": ahora, "puntos": [],
                                          "deteccion_t": None}
        if len(serie['puntos']) < MAX_PUNTOS:
            serie['puntos'].append({
                "t": round(ahora - serie['t0'], 3),
                "tasa": tasa,
                "umbral": round(umbral_usuario, 2),
            })
        if es_anomalia and serie['deteccion_t'] is None:
            serie['deteccion_t'] = round(ahora - serie['t0'], 3)

    if aprendido is not None:
        guardar_baseline(user_id, aprendido)

    if not es_anomalia:
        return {"es_anomalia": False, "tasa_actual": tasa,
                "baseline_usuario": baseline_actual,
                "umbral_usuario": round(umbral_usuario, 2),
                "umbral_maximo": ANOMALY_THRESHOLD,
                "ventana_segundos": VENTANA_SEGUNDOS}

    # Deteccion: el ASR pide identificar la desviacion y marcar la sesion
    # como anomala. El cronometro se detiene aqui, cuando eso ya ocurrio.
    try:
        with abrir(DATABASE) as db:
            db.execute(
                "UPDATE sessions SET is_anomalous=1, status='Bloqueada' WHERE id=?",
                (session_id,)
            )
            db.commit()
    except Exception as e:
        print(f"[Monitor] Error DB: {e}")
    ts_marcada = time.time()
    deteccion_ms = round((ts_marcada - ts_umbral) * 1000, 2)

    # Revocacion: es la reaccion posterior, una tactica distinta segun el
    # diseno, asi que se cronometra desde que la sesion quedo marcada. Asi
    # los dos tramos son sumandos y no hitos solapados.
    try:
        requests.post(
            f"{AUTORIZADOR_URL}/revocar",
            json={"session_id": session_id,
                  "motivo": "Desviacion del comportamiento habitual"},
            timeout=5
        )
    except Exception as e:
        print(f"[Monitor] Error notificando al Autorizador: {e}")
    revocacion_ms = round((time.time() - ts_marcada) * 1000, 2)
    total_ms = round(deteccion_ms + revocacion_ms, 2)
    if not ya_medida:
        with lock:
            detecciones[session_id] = {"deteccion_ms": deteccion_ms,
                                       "revocacion_ms": revocacion_ms,
                                       "total_ms": total_ms}
        try:
            with abrir(DATABASE) as db:
                db.executemany(
                    "INSERT INTO logs (session_id, timestamp, query_type, "
                    "response_time_ms, is_anomaly) VALUES (?, ?, ?, ?, ?)",
                    [(session_id, time.time(), 'deteccion', deteccion_ms, 1),
                     (session_id, time.time(), 'revocacion', revocacion_ms, 1),
                     (session_id, time.time(), 'total', total_ms, 1)]
                )
                db.commit()
        except Exception as e:
            print(f"[Monitor] Error registrando deteccion: {e}")
        print(f"[Monitor] Anomalia! sesion={str(session_id)[:8]} usuario={user_id} "
              f"tasa={tasa} habitual={baseline_actual} umbral={umbral_usuario:.1f} "
              f"deteccion={deteccion_ms} ms + revocacion={revocacion_ms} ms "
              f"= {total_ms} ms")

    return {"es_anomalia": True, "ts_umbral": ts_umbral,
            "tiempo_deteccion_ms": deteccion_ms,
            "tiempo_revocacion_ms": revocacion_ms,
            "tiempo_total_ms": total_ms,
            "tasa_actual": tasa,
            "baseline_usuario": baseline_actual,
            "umbral_usuario": round(umbral_usuario, 2),
            "umbral_maximo": ANOMALY_THRESHOLD,
            "ventana_segundos": VENTANA_SEGUNDOS}


def behavior_worker():
    while True:
        evento = consume_behavior_event()
        if evento:
            procesar_evento(evento.get('session_id'), evento.get('user_id'))


@app.route('/registrar', methods=['POST'])
def registrar():
    data = request.json or {}
    return jsonify(procesar_evento(data.get('session_id'), data.get('user_id')))


@app.route('/deteccion/<session_id>', methods=['GET'])
def consultar_deteccion(session_id):
    """Tiempo de deteccion medido para una sesion, en milisegundos."""
    with lock:
        medidas = detecciones.get(session_id)
    if medidas is None:
        return jsonify({"session_id": session_id, "detectada": False}), 404
    return jsonify({
        "session_id": session_id, "detectada": True,
        "tiempo_deteccion_ms": medidas['deteccion_ms'],
        "tiempo_revocacion_ms": medidas['revocacion_ms'],
        "tiempo_total_ms": medidas['total_ms']
    })


@app.route('/serie/<session_id>', methods=['GET'])
def consultar_serie(session_id):
    """Tasa observada y umbral vigente a lo largo de la sesion.

    Permite ver por que salto la alarma, con la curva del comportamiento
    contra la linea que no debia cruzar.
    """
    with lock:
        serie = series.get(session_id)
        if serie is None:
            return jsonify({"session_id": session_id, "puntos": []}), 404
        datos = {"session_id": session_id,
                 "puntos": list(serie['puntos']),
                 "deteccion_t": serie['deteccion_t'],
                 "ventana_segundos": VENTANA_SEGUNDOS}
    return jsonify(datos)


@app.route('/baseline/<int:user_id>', methods=['GET'])
def consultar_baseline(user_id):
    """Comportamiento habitual del usuario y el umbral que le corresponde."""
    with lock:
        base = baselines.get(user_id)
        umbral = umbral_de(user_id)
        tasa = len(user_history.get(user_id, []))
    return jsonify({
        "user_id": user_id,
        "baseline_qpm": round(base, 2) if base is not None else None,
        "umbral_usuario": round(umbral, 2),
        "tasa_actual": tasa,
        "factor": FACTOR,
        "sin_historial": base is None
    })


@app.route('/baseline/<int:user_id>', methods=['POST'])
def fijar_baseline(user_id):
    """Fija el comportamiento habitual de un usuario.

    Representa el perfil ya aprendido de su historico, que en produccion se
    construiria a lo largo de dias. Permite montar escenarios reproducibles.
    """
    data = request.json or {}
    try:
        valor = float(data.get('baseline_qpm'))
    except (TypeError, ValueError):
        return jsonify({"error": "baseline_qpm invalido"}), 400
    if valor < 0 or valor > 10000:
        return jsonify({"error": "baseline_qpm fuera de rango"}), 400
    with lock:
        baselines[user_id] = valor
        ultimo_aprendizaje[user_id] = time.time()
        umbral = umbral_de(user_id)
    guardar_baseline(user_id, valor)
    return jsonify({"user_id": user_id, "baseline_qpm": valor,
                    "umbral_usuario": round(umbral, 2)})


@app.route('/config', methods=['POST'])
def set_config():
    global ANOMALY_THRESHOLD, FACTOR, BASELINE_INICIAL
    global BASELINE_MAXIMO, BASELINE_MINIMO
    data = request.json or {}
    try:
        umbral = int(data.get('umbral', ANOMALY_THRESHOLD))
        factor = float(data.get('factor', FACTOR))
        base = float(data.get('baseline', BASELINE_INICIAL))
    except (TypeError, ValueError):
        return jsonify({"error": "Parametro invalido"}), 400
    if umbral < 1 or umbral > 10000:
        return jsonify({"error": "Umbral fuera de rango (1-10000)"}), 400
    if factor < 1.0 or factor > 100.0:
        return jsonify({"error": "Factor fuera de rango (1-100)"}), 400
    if base < 1 or base > 10000:
        return jsonify({"error": "Linea base fuera de rango (1-10000)"}), 400
    with lock:
        FACTOR = factor
        BASELINE_INICIAL = base
        # El umbral de referencia y las cotas del habito se derivan de la
        # linea base: no son parametros independientes.
        ANOMALY_THRESHOLD = round(BASELINE_INICIAL * FACTOR)
        BASELINE_MAXIMO = BASELINE_INICIAL * DERIVA_MAXIMA
        BASELINE_MINIMO = BASELINE_INICIAL / DERIVA_MAXIMA
        user_history.clear()
        detecciones.clear()
    return jsonify({"umbral": ANOMALY_THRESHOLD, "factor": FACTOR,
                    "baseline": BASELINE_INICIAL,
                    "umbral_maximo": round(BASELINE_MAXIMO * FACTOR),
                    "umbral_minimo_habito": round(BASELINE_MINIMO * FACTOR)})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'componente': 'monitor',
                    'umbral_referencia': ANOMALY_THRESHOLD,
                    'baseline_inicial': BASELINE_INICIAL,
                    'factor_desviacion': FACTOR,
                    'umbral_minimo': UMBRAL_MINIMO,
                    'baseline_maximo': BASELINE_MAXIMO,
                    'baseline_minimo': BASELINE_MINIMO,
                    'margen_aprendizaje': MARGEN_APRENDIZAJE,
                    'cambio_maximo': CAMBIO_MAXIMO,
                    'ventana_segundos': VENTANA_SEGUNDOS,
                    'transporte': modo()})


if __name__ == '__main__':
    init_baselines()
    print(f"[Monitor] modelo: habitual {BASELINE_INICIAL} qpm x factor {FACTOR} "
          f"= {BASELINE_INICIAL * FACTOR:.0f} para usuarios sin historial "
          f"(el umbral aprende entre {BASELINE_MINIMO * FACTOR:.0f} y "
          f"{BASELINE_MAXIMO * FACTOR:.0f}, suelo {UMBRAL_MINIMO}, "
          f"ventana {VENTANA_SEGUNDOS}s)")
    if modo() == 'redis':
        threading.Thread(target=behavior_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5003, threaded=True, use_reloader=False)
