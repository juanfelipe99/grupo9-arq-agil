"""Acceso comun a la base del experimento.

Cinco procesos escriben sobre el mismo archivo SQLite. Sin WAL y sin una
espera generosa se bloquean entre ellos, y una conexion que quede abierta
tras un error deja el bloqueo puesto para siempre, con el experimento
reportando aunque ya no escriba nada. Por eso se abren desde aqui y se
cierran siempre.
"""

import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(BASE_DIR, 'data', 'experiment.db')

ESPERA_MS = 15000


def conectar(ruta=None):
    """Conexion lista para concurrencia entre procesos."""
    destino = ruta or RUTA
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    db = sqlite3.connect(destino, check_same_thread=False,
                         timeout=ESPERA_MS / 1000)
    db.row_factory = sqlite3.Row
    # WAL deja leer mientras alguien escribe. Sin el, cada lectura del
    # dashboard frena a los servicios.
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"PRAGMA busy_timeout={ESPERA_MS}")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


@contextmanager
def abrir(ruta=None):
    """Conexion que se cierra pase lo que pase."""
    db = conectar(ruta)
    try:
        yield db
    finally:
        db.close()
