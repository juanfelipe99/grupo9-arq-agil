# Experimento: Detección de Comportamiento Anómalo (H710)

**Módulo 7 - Seguridad | Arquitecturas Ágiles | ASR-12 Confidencialidad**

---

## Descripción General

Sistema de microservicios que evalúa si el **Monitor de comportamiento**, integrado al componente **Cotización y Rating**, puede identificar en tiempo casi inmediato cuando un administrador realiza un volumen de consultas significativamente diferente a su comportamiento habitual.

**Objetivo del experimento:** Comprobar si un modelo matemático sencillo del comportamiento normal del usuario permite detectar una desviación que supere un umbral definido y comunicar la anomalía al Autorizador, con un **tiempo de detección inferior a 1 segundo**.

### Resultados Esperados

Se espera que el Monitor de comportamiento permita diferenciar entre un comportamiento habitual y un patrón de extracción masiva de información, identificando la anomalía cuando se supera el umbral definido y marcando la sesión como anómala dentro del tiempo establecido por el ASR.

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
| Cotización → Monitor | HTTP síncrono | `requests` |
| Monitor → Autorizador | HTTP síncrono (si anomalia) | `requests` |

### Modelo de Detección de Anomalías

| Parámetro | Valor | Descripción |
|---|---|---|
| Baseline | 50 consultas/min | Comportamiento normal del administrador |
| Umbral de anomalía | 150 consultas/min | 3x el baseline → se marca sesión como anómala |
| Tiempo límite | < 1 segundo | Tiempo máximo de detección requerido |

### Escenarios de Experimentación

| Escenario | Tipo | Consultas | Delay | Descripción |
|---|---|---|---|---|
| Comportamiento Normal | Normal | 50 | 1.5s | Patrón habitual del administrador |
| Extracción Masiva | Anómalo | 200 | 0.01s | Ataque bruto, alto volumen |
| Escala Gradual | Gradual | 151 | 0.1→0.01s | Se intensifica progresivamente |

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
├── config.py                      # URLs y puertos centralizados
├── start.py                       # Lanzador de todos los servicios
├── main.py                        # Dashboard (puerto 5000)
├── services/                      # Microservicios independientes
│   ├── auth.py                    # Auth (puerto 5001)
│   ├── cotizacion.py              # Cotización y Rating (puerto 5002)
│   ├── monitor.py                 # Monitor de Comportamiento (puerto 5003)
│   └── autorizador.py             # Autorizador (puerto 5004)
├── requirements.txt               # Dependencias Python
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
| GET | `/api/cotizacion/quote` | Cotización y Rating | Consulta de cotización |
| POST | `/api/experiment/run-all` | Dashboard | Ejecuta los 3 escenarios en secuencia |
| GET | `/api/experiment/results` | Dashboard | Obtener resultados |
| GET | `/api/experiment/stats` | Dashboard | Estadísticas generales |
| GET | `/api/users` | Dashboard | Lista de usuarios registrados |
| GET | `/api/status` | Dashboard | Estado de todos los microservicios |

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

### Tiempos de Detección

| Escenario | Consultas | Duración | Detección | Anomalía | Cumple <1s |
|---|---|---|---|---|---|
| Comportamiento Normal | 50 | ~75s | 0ms | No | Sí |
| Extracción Masiva | 200 | ~6.7s | **5.13ms** | Sí | Sí |
| Escala Gradual | 151 | ~7.7s | **~5ms** | Sí | Sí |

**Resultado:** El Monitor de comportamiento detecta anomalías en **~5ms** (mucho menos de 1 segundo requerido).

### Verificación del Umbral

- Umbral requerido: < 1 segundo (1000ms)
- Tiempo de detección obtenido: ~5ms
- **Cumplimiento: SÍ** ✓

### Interpretación de Resultados

| Escenario | Resultado Esperado | Resultado Obtenido | Valido |
|---|---|---|---|
| Comportamiento Normal | No detecta anomalía | No detectó | ✓ |
| Extracción Masiva | Detecta en <1s | Detectó en ~5ms | ✓ |
| Escala Gradual | Detecta en <1s | Detectó en ~5ms | ✓ |

**Conclusión:** El Monitor cumple con el ASR-12 de confidencialidad, detectando anomalías 200 veces más rápido que el límite de 1 segundo requerido.

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
