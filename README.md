# Experimento: Detección de Comportamiento Anómalo (H710)

**Módulo 7 - Seguridad | Arquitecturas Ágiles | ASR-12 Confidencialidad**

---

## Descripción General

Sistema de microservicios que evalúa si el **Monitor de comportamiento**, integrado al componente **Cotización y Rating**, puede identificar en tiempo casi inmediato cuando un administrador realiza un volumen de consultas significativamente diferente a su comportamiento habitual.

**Objetivo del experimento:** Comprobar si un modelo del comportamiento habitual del usuario permite detectar una desviación que supere su umbral, marcar la sesión como anómala y retirarle los permisos, todo ello en **menos de 1 segundo**.

El ASR acota las dos acciones en conjunto, no solo la detección, así que la cifra que se compara contra el segundo es el **total**. El desglose entre detectar y revocar se reporta aparte para ver dónde se va el tiempo.

### Resultados Esperados

Se espera que el Monitor distinga un comportamiento habitual de un patrón de extracción masiva, marque la sesión y corte la fuga dentro del tiempo del ASR. Corte real: las consultas posteriores a la revocación deben ser rechazadas, no solo contabilizadas.

---

## Arquitectura del Sistema

### Microservicios Independientes (5 procesos)

Cada microservicio es un proceso Flask independiente con su propio puerto, comunicándose via HTTP:

| Microservicio | Puerto | Archivo | Propósito |
|---|---|---|---|
| **Dashboard** | 5000 | `main.py` | Interfaz web + orquestador del experimento |
| **Auth** | 5001 | `services/auth.py` | Registro e inicio de sesión de administradores |
| **Cotización y Rating** | 5002 | `services/cotizacion.py` | Recibe y responde consultas de clientes |
| **Monitor de Comportamiento** | 5003 | `services/monitor.py` | Detecta anomalías por tasa de consultas |
| **Autorizador** | 5004 | `services/autorizador.py` | Bloqueo/revocación de sesiones anómalas |

### Flujo de Comunicación

```
Browser → Dashboard (:5000) → Cotización (:5002) → Monitor (:5003) → Autorizador (:5004)
                                        │
Browser → Dashboard (:5000) → Auth (:5001)
```

Todos los servicios se inician con `python start.py` y se comunican via HTTP using `requests`.

### Conectores

| Conector | Tipo | Tecnología |
|---|---|---|
| Dashboard → Cualquier servicio | HTTP (proxy) | `requests` |
| Cotización → Auth | HTTP síncrono (valida la sesión) | `requests` |
| Cotización → Monitor | **Asíncrono** (cola, no bloquea la respuesta) | Redis con respaldo HTTP |
| Monitor → Autorizador | HTTP síncrono (si hay anomalía) | `requests` |

El registro de comportamiento viaja de forma asíncrona a propósito: vigilar no debe encarecer la respuesta al usuario legítimo. Si Redis no está disponible, `message_queue.py` cae a HTTP sin interrumpir el experimento.

La identidad no la decide el cliente. Cotización pregunta a Auth por cada consulta y nunca confía en una cabecera de usuario, de modo que una sesión revocada deja de pasar de inmediato.

### Modelo de Detección de Anomalías

No hay un umbral fijo para todos. Cada usuario se compara contra **su propio hábito**, que el Monitor aprende observándolo:

```
umbral = máx(20, hábito × 3)
```

| Parámetro | Valor | Descripción |
|---|---|---|
| Hábito inicial (`BASELINE_QPM`) | 50 cons/min | Supuesto para quien no tiene historial |
| Factor (`FACTOR_DESVIACION`) | 3.0 | Veces el hábito que hay que superar |
| Umbral de un usuario nuevo | 150 cons/min | 50 × 3 |
| Ventana (`VENTANA_SEGUNDOS`) | 60 s | Deslizante, cuenta las consultas del último minuto |
| Tiempo límite del ASR | < 1 s | Detectar **y** revocar |

#### Aprendizaje del hábito

Al cerrarse cada ventana el Monitor ajusta el hábito con una media móvil:

```
hábito = 0.7 × hábito_anterior + 0.3 × tasa_observada
```

Con tres frenos para que una escalada paciente no pueda subir su propio umbral hasta normalizar el ataque:

| Freno | Valor | Qué impide |
|---|---|---|
| `MARGEN_APRENDIZAJE` | 1.5 | Solo se aprende de tasas cercanas al hábito. Una ráfaga que roza el umbral no cuenta como costumbre nueva |
| `CAMBIO_MAXIMO` | 10% por ventana | Mover el hábito cuesta minutos, no una ráfaga |
| `DERIVA_MAXIMA` | 2.0 | El hábito no se aleja más del doble ni de la mitad del inicial |

Además no se aprende durante una anomalía, ni antes de que la ventana esté llena.

Consecuencia: el hábito vive entre 25 y 100 cons/min, así que el umbral vive entre **75 y 300**. Un atacante que se mantenga justo por debajo de su umbral **no consigue moverlo**; sin el margen de aprendizaje alcanzaría el techo en dos minutos.

### Escenarios de Experimentación

| Escenario | Tipo | Consultas | Delay | Descripción |
|---|---|---|---|---|
| Comportamiento Normal | Normal | 50 | 1.5s | Patrón habitual, unas 39 cons/min |
| Extracción Masiva | Anómalo | 200 | 0.01s | Ataque bruto, alto volumen |
| Escala Gradual | Gradual | 200 | 0.1s con decaimiento 0.95 | Cada consulta espera un 5% menos que la anterior |

Los dos escenarios de ataque comparten el número de consultas para que lo que los distinga sea el ritmo y no el volumen. Ninguno de los dos llega a las 200, porque la revocación los corta antes, y ese margen es la medida de la fuga contenida.

**Cuentas de simulación.** El escenario normal conserva la suya entre corridas (`sim_normal@test.com`), de modo que su hábito se afina hacia su ritmo real corrida tras corrida. Los de ataque estrenan cuenta cada vez para que cada corrida arranque del mismo punto.

---

## Tecnologías Utilizadas (Diap. 8)

| Categoría | Tecnología | Justificación |
|---|---|---|
| Lenguajes | Python 3.10+, HTML/CSS/JavaScript | Alto nivel, ideal para prototipos |
| Framework | Flask 3.0+ | Endpoints REST rápidos |
| Comunicación | requests 2.31+ | Comunicación síncrona entre servicios |
| Base de datos | SQLite (sqlite3) | Sin servidor dedicado, ideal para pruebas |
| Análisis de carga | Apache JMeter 5.6+ | Generación de escenarios y medición |
| Despliegue | Local + Heroku | Desarrollo local y producción en la nube |

---

## Requisitos Previos

- **Python 3.10** o superior
- **Git** para clonar el repositorio
- **Apache JMeter 5.6+** (opcional, para scripts de carga)
- **Navegador web** moderno (Chrome, Firefox, Edge)

---

## Instalación Local

### 1. Clonar o copiar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd grupo9_arq_agiles
```

### 2. Crear entorno virtual

```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Base de datos

La base de datos se crea automáticamente al iniciar el servicio Auth con 2 usuarios pre-cargados:

| Nombre | Email | Contraseña |
|---|---|---|
| Administrador | admin@ejemplo.com | admin123 |
| Investigador | investigador@ejemplo.com | demo123 |

### 5. Ejecutar todos los servicios

```bash
python start.py
```

Esto lanza los 5 microservicios como procesos independientes:

| Servicio | Puerto |
|---|---|
| Dashboard | http://localhost:5000 |
| Auth | http://localhost:5001 |
| Cotización | http://localhost:5002 |
| Monitor | http://localhost:5003 |
| Autorizador | http://localhost:5004 |

Presiona `Ctrl+C` para detener todos los servicios.

---

## Uso del Sistema

1. Abrir **http://localhost:5000** en el navegador
2. **Iniciar sesión** con las credenciales de ejemplo (admin@ejemplo.com / admin123)
3. Navegar al **Dashboard** (se accede automáticamente tras login)
4. Hacer clic en **"Ejecutar Experimentos"**
5. Observar los resultados en tiempo real por escenario (gráficas y métricas)

---

## Estructura del Proyecto

```
grupo9_arq_agiles/
├── venv/                          # Entorno virtual Python
├── config.py                      # Puertos, URLs y parámetros del modelo
├── db.py                          # Conexión compartida a SQLite (WAL, cierre seguro)
├── message_queue.py               # Cola de eventos con respaldo HTTP
├── redis_client.py                # Cliente Redis opcional
├── start.py                       # Lanzador de todos los servicios
├── main.py                        # Dashboard (puerto 5000)
├── services/                      # Microservicios independientes
│   ├── auth.py                    # Auth (puerto 5001)
│   ├── cotizacion.py              # Cotización y Rating (puerto 5002)
│   ├── monitor.py                 # Monitor de Comportamiento (puerto 5003)
│   └── autorizador.py             # Autorizador (puerto 5004)
├── requirements.txt               # Dependencias Python
├── .python-version                # Versión de Python para Heroku
├── Procfile                       # Configuración Heroku
├── README.md                      # Esta documentación
├── data/
│   └── experiment.db              # Base de datos SQLite compartida
├── templates/
│   ├── index.html                 # Página principal (registro/login)
│   └── dashboard.html             # Dashboard de resultados
├── static/
│   └── css/
│       └── style.css              # Estilos dark theme
├── jmeter/
│   ├── normal_behavior.jmx        # Script JMeter: comportamiento normal
│   ├── massive_extraction.jmx     # Script JMeter: extracción masiva
│   └── gradual_stair.jmx         # Script JMeter: escala gradual
└── scripts/
    └── run_jmeter.py              # Ejecuta JMeter y recopila resultados
```

---

## API Endpoints

| Método | Ruta | Microservicio | Descripción |
|---|---|---|---|
| GET | `/` | Dashboard | Página principal (registro + login) |
| GET | `/dashboard` | Dashboard | Dashboard de resultados |
| POST | `/api/auth/register` | Auth | Registrar administrador |
| POST | `/api/auth/login` | Auth | Iniciar sesión |
| POST | `/api/auth/logout` | Auth | Cerrar sesión en el servidor |
| GET | `/api/cotizacion/quote` | Cotización y Rating | Consulta de cotización |
| POST | `/api/experiment/run` | Dashboard | Ejecuta un solo escenario |
| POST | `/api/experiment/run-all` | Dashboard | Ejecuta los 3 escenarios en secuencia |
| GET | `/api/experiment/config` | Dashboard | Parámetros vigentes del modelo |
| GET | `/api/experiment/results` | Dashboard | Obtener resultados |
| GET | `/api/experiment/stats` | Dashboard | Estadísticas generales |
| GET | `/api/users` | Dashboard | Lista de usuarios registrados |
| GET | `/api/status` | Dashboard | Estado de todos los microservicios |

Endpoints internos del Monitor, útiles para inspeccionar el modelo:

| Método | Ruta | Descripción |
|---|---|---|
| GET | `:5003/baseline/<user_id>` | Hábito aprendido y umbral de ese usuario |
| POST | `:5003/baseline/<user_id>` | Fija un hábito conocido |
| GET | `:5003/deteccion/<session_id>` | Tiempos medidos de esa sesión |
| GET | `:5003/serie/<session_id>` | Curva de tasa contra umbral |
| GET | `:5003/health` | Parámetros vigentes del modelo |

---

## Scripts JMeter

Los scripts JMeter se encuentran en la carpeta `jmeter/` y se pueden ejecutar con:

```bash
# Comportamiento normal
jmeter -n -t jmeter/normal_behavior.jmx -l results/normal.jtl

# Extracción masiva
jmeter -n -t jmeter/massive_extraction.jmx -l results/massive.jtl

# Escala gradual
jmeter -n -t jmeter/gradual_stair.jmx -l results/gradual.jtl
```

O ejecutar el script Python integrado:

```bash
python scripts/run_jmeter.py --scenario normal
python scripts/run_jmeter.py --scenario massive
python scripts/run_jmeter.py --scenario gradual
```

---

## Despliegue en Heroku

```bash
# Crear app en Heroku
heroku create nombre-app-experimento

# Desplegar
git push heroku main

# Abrir en el navegador
heroku open
```

---

## Resultados del Experimento

Corrida sobre base limpia. Los dos tiempos son consecutivos y **su suma es la cifra que el ASR acota**.

### Tiempos

| Escenario | Consultas servidas | Detección | Revocación | **Total** | Cumple < 1s |
|---|---|---|---|---|---|
| Comportamiento Normal | 50 de 50 | n/a | n/a | n/a | Sí, no dispara |
| Extracción Masiva | 150 de 200 | 0.004 s | 0.007 s | **0.011 s** | Sí |
| Escala Gradual | 150 de 200 | 0.006 s | 0.007 s | **0.012 s** | Sí |

Detección es el tiempo desde que se cruza el umbral hasta que la sesión queda marcada. Revocación es desde ahí hasta que el Autorizador confirma que quedó sin permisos.

**Resultado:** el total queda unas 80 veces por debajo del segundo exigido.

### Fuga contenida

Los dos ataques pretendían 200 consultas y alcanzaron 150. Las 50 restantes fueron rechazadas: Cotización consulta a Auth en cada petición, y una sesión revocada deja de ser válida de inmediato. El corte es real, no contable.

### Costo de vigilar

| Escenario | Mediana | p95 |
|---|---|---|
| Comportamiento Normal | 0.032 s | 0.049 s |
| Extracción Masiva | 0.032 s | 0.049 s |
| Escala Gradual | 0.032 s | 0.049 s |

La latencia de las cotizaciones es la misma bajo ataque que en reposo, que es lo que se buscaba al publicar el evento de comportamiento de forma asíncrona.

### Comportamiento del modelo

El escenario normal corre a unas 39 cons/min, por debajo de las 50 supuestas, así que el Monitor corrige su hábito al cerrarse cada ventana. Conservando la cuenta entre corridas:

| Corrida | Hábito aprendido | Umbral |
|---|---|---|
| 1 | 45.8 cons/min | 137.4 |
| 2 | 42.9 cons/min | 128.6 |
| 3 | 40.8 cons/min | 122.4 |

Converge hacia el ritmo real del usuario. Los escenarios de ataque duran unos 10 segundos, nunca completan una ventana y por tanto nunca aprenden: se quedan en el umbral de referencia de 150.

### Resistencia a la normalización

Simulación del modelo con distintas estrategias de ataque:

| Estrategia | Resultado |
|---|---|
| Atacante justo por debajo de su umbral | No consigue mover su hábito |
| El mismo, sin `MARGEN_APRENDIZAJE` | Alcanza el techo en 2 minutos |
| Atacante al límite de lo que se aprende | Tarda 11 minutos en llegar al techo, a un ritmo que no extrae |
| Usuario legítimo que crece 5% por minuto | El modelo lo acomoda |
| Extracción masiva de golpe | Detectado en la primera ventana |

### Interpretación

| Escenario | Esperado | Obtenido | Válido |
|---|---|---|---|
| Comportamiento Normal | No detecta anomalía | No detectó, y afinó el hábito | Sí |
| Extracción Masiva | Detecta y revoca en < 1s | 0.011 s, cortada en la consulta 151 | Sí |
| Escala Gradual | Detecta y revoca en < 1s | 0.012 s, cortada en la consulta 151 | Sí |

**Conclusión:** el sistema cumple el ASR-12. Detecta la desviación sobre el comportamiento habitual, marca la sesión y le retira los permisos en menos de un segundo, y corta la extracción mientras está ocurriendo.

### Alcance de la medición

Cada cifra proviene de una corrida. Con el margen disponible, unas dos órdenes de magnitud por debajo del límite, la conclusión no depende de esa precisión, pero la variabilidad entre corridas no está caracterizada.

---

## Créditos

**Grupo 9 - Arquitecturas Ágiles**
- Jesús Gómez
- Miguel Higuera
- Juan Pablo Vargas
- Juan Felipe Quiñonez

**Universidad de los Andes** - Módulo 7: Seguridad

---

## Licencia

Derechos Reservados - Universidad de los Andes
