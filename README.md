# Experimento: Validación de Votación ante Resultados Inconsistentes de Rating

**Módulo 4 - EDA (Estudio de Diseño de Arquitectura)**
**ASR: HA-06 - Disponibilidad Funcional**

---

## Objetivo

Validar que la arquitectura de Cotización y Rating puede detectar y ocultar mediante votación un resultado incorrecto de una instancia de Rating, manteniendo un resultado válido en las cotizaciones con tiempo de respuesta inferior a 250 ms más del 95% de las veces.

---

## Requisitos

### Sistema Operativo
- Windows 10/11

### Software
| Componente | Versión | Propósito |
|------------|---------|-----------|
| Python | 3.10+ | Ejecución de microservicios |
| pip | Última | Gestión de dependencias |
| Apache JMeter | 5.6+ | Pruebas de carga (opcional) |

### Dependencias Python
```
flask>=3.0
requests>=2.31
```

### Instalación

```bash
cd ruta/del/proyecto
pip install -r requirements.txt
```

---

## Estructura del Proyecto

```
experimento_prueba/
├── config.py                     # Configuración centralizada (URLs, puertos)
├── requirements.txt              # Dependencias Python
├── start.py                      # Script de inicio de todos los servicios
├── services/
│   ├── rating/
│   │   ├── rating1.py            # Instancia Rating 1 (puerto 5001)
│   │   ├── rating2.py            # Instancia Rating 2 (puerto 5002)
│   │   └── rating3.py            # Instancia Rating 3 (puerto 5003)
│   ├── votacion.py               # Componente de Votación (puerto 5004)
│   └── enmascaramiento.py        # Componente de Enmascaramiento (puerto 5005)
├── client/
│   ├── cotizacion.py             # Orquestador principal + UI (puerto 5000)
│   └── templates/
│       └── index.html            # Interfaz web de prueba
└── jmeter/
    └── test_plan.jmx             # Plan de pruebas JMeter
```

---

## Modo de Uso

### 1. Iniciar todos los servicios

```bash
cd ruta/del/proyecto
python start.py
```

Los 6 servicios se iniciarán automáticamente:
| Servicio | Puerto |
|----------|--------|
| Cotización (UI) | 5000 |
| Rating 1 | 5001 |
| Rating 2 | 5002 |
| Rating 3 | 5003 |
| Votación | 5004 |
| Enmascaramiento | 5005 |

### 2. Abrir la interfaz web

Abrir en el navegador: **http://127.0.0.1:5000**

> **Nota:** Se usa `127.0.0.1` en lugar de `localhost` para evitar problemas de resolución DNS en Windows que causan lentitud.

### 3. Configurar la prueba de carga

En la interfaz web:

1. **Usuarios concurrentes**: Número de hilos simultáneos (1-1000)
2. **Iteraciones por usuario**: Peticiones por hilo (1-10000)
3. **Simular fallo en Rating**: Seleccionar cuál instancia falla
   - `Ninguna` - Sin fallo (todas calculan correctamente)
   - `Rating 1` - Fallo fijo en Rating 1
   - `Rating 2` - Fallo fijo en Rating 2
   - `Rating 3` - Fallo fijo en Rating 3
   - `Aleatorio` - Cada petición elige una instancia al azar

4. Hacer clic en **"Ejecutar Prueba de Carga"**

### 4. Ejecutar con JMeter (opcional)

1. Descargar Apache JMeter desde: https://jmeter.apache.org/download_jmeter.cgi
2. Ejecutar `bin\ApacheJMeter.bat`
3. `File → Open` → seleccionar `jmeter\test_plan.jmx`
4. Click en botón **Start** (verde)

---

## Arquitectura del Experimento

```
┌─────────────────┐
│   Cliente UI     │
│   (Puerto 5000)  │
└────────┬────────┘
         │ POST /cotizar
         ▼
┌─────────────────┐
│  Cotización      │ ◄── Orquestador
│  (Flask)         │
└────────┬────────┘
         │ Paralelo (3 hilos)
    ┌────┼────┐
    ▼    ▼    ▼
┌──────┐┌──────┐┌──────┐
│ R1   ││ R2   ││ R3   │  ← Instancias Rating
│5001  ││5002  ││5003  │    (una puede fallar)
└──┬───┘└──┬───┘└──┬───┘
   │       │       │
   └───┬───┘───────┘
       ▼
┌─────────────────┐
│   Votación       │ ◄── Compara 3 resultados
│   (Puerto 5004)  │     Detecta outlier
└────────┬────────┘
         ▼
┌─────────────────┐
│ Enmascaramiento  │ ◄── Oculta resultado incorrecto
│   (Puerto 5005)  │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Respuesta JSON   │ ◄── Resultado válido + métricas
└─────────────────┘
```

---

## Tácticas de Arquitectura Implementadas

| Táctica | Descripción | Componente |
|---------|-------------|------------|
| **Votación** | Compara las respuestas de 3 instancias y detecta el resultado que se aparta del resto | `votacion.py` |
| **Enmascaramiento** | El resultado incorrecto nunca llega al usuario, solo se entrega el resultado válido | `enmascaramiento.py` |
| **Redundancia** | 3 instancias independientes permiten continuar la operación aunque una presente degradación | `rating1.py`, `rating2.py`, `rating3.py` |

---

## Simulación de Fallo

### Comportamiento por instancia

| Instancia | Modo Normal | Modo Fallo (`?fail=true`) |
|-----------|-------------|---------------------------|
| Rating 1 | `score = monto × 0.15` | `score = -500` |
| Rating 2 | `score = monto × 0.15` | `score = -500` |
| Rating 3 | `score = monto × 0.15` | `score = -500` |

Cuando una instancia falla:
- Retorna `score: -500` y `rating: F`
- La votación lo identifica como outlier (score diferente al resto)
- El enmascaramiento oculta este resultado
- El cliente recibe el resultado válido de las otras dos instancias

---

## Interpretación de Resultados

### Tarjeta 1: Resultados de la Prueba

| Métrica | Descripción |
|---------|-------------|
| Total Peticiones | Total de peticiones realizadas |
| Exitosas | Peticiones que respondieron HTTP 200 |
| Errores | Peticiones fallidas (timeout, error de servidor) |
| Tiempo Total | Duración total de la prueba |
| Requests/segundo | Throughput del sistema |

**Criterio de Éxito:** 100% de las peticiones responden correctamente.
**Criterio de Error:** Cualquier petición retorna error o timeout.

---

### Tarjeta 2: Enmascaramiento y Votación

| Métrica | Descripción |
|---------|-------------|
| Outliers Detectados | Número de resultados incorrectos detectados por la votación |
| Distribución de Fallos | Cuántas veces falló cada instancia (ej: `rating1: 6, rating2: 2, rating3: 2`) |
| Resultado Final Válido | Siempre se entrega un resultado correcto al cliente |

**Criterio de Éxito:** Todos los outliers son detectados y el resultado incorrecto nunca llega al cliente.
**Criterio de Error:** Algún resultado incorrecto se entrega al usuario.

**Nota:** Con modo "Aleatorio", la distribución de fallos varía entre instancias, demostrando que la votación funciona independientemente de cuál instancia falle.

---

### Tarjeta 3: Tiempo de Respuesta

| Métrica | Descripción |
|---------|-------------|
| Mínimo | Tiempo de respuesta más rápido |
| Máximo | Tiempo de respuesta más lento |
| Promedio | Tiempo promedio de respuesta |
| Mediana (P50) | 50% de las peticiones son más rápidas que este valor |
| Dentro de 250ms | Peticiones que cumplieron el límite |
| % Cumplimiento | Porcentaje de peticiones dentro del límite |

**Criterio de Éxito:** ≥ 95% de las peticiones con tiempo < 250 ms.
**Criterio de Error:** < 95% de las peticiones dentro del límite.

---

## Veredicto Automático

La interfaz muestra automáticamente:

- **CUMPLE** (verde) cuando se cumplen todos los criterios
- **NO CUMPLE** (rojo) cuando algún criterio falla

### Ejemplo de resultado exitoso

```
Resultados de la Prueba
  Criterios
    Exito: 100% peticiones responden correctamente (HTTP 200)
    Error: Cualquier peticion retorna error o timeout
  CUMPLE - 1000/1000 exitosas

Enmascaramiento y Votacion
  Criterios
    Exito: Outliers detectados y resultado incorrecto nunca llega al cliente
    Error: Resultado incorrecto se entrega al usuario
  CUMPLE - Votacion y enmascaramiento funcionales

Tiempo de Respuesta
  Criterios
    Exito: >= 95% peticiones con tiempo < 250ms
    Error: < 95% peticiones dentro del limite
  CUMPLE - 99.8% dentro de 250ms
```

---

## Limitaciones del Servidor de Desarrollo

El servidor incluido en Flask (`app.run()`) es de un **solo hilo** y no está diseñado para manejar alta concurrencia. Bajo carga elevada, cada petición a `/cotizar` genera internamente hasta 5 llamadas HTTP adicionales (3 ratings + votación + enmascaramiento), lo que satura rápidamente el servidor.

### Relación usuarios → peticiones internas

```
N usuarios concurrentes
  → N peticiones a /cotizar
    → N × 3 llamadas a rating (paralelas)
    → N llamadas a votación
    → N llamadas a enmascaramiento
    ─────────────────────────────────
    Total conexiones simultáneas: N × 5
```

### Límites recomendados con Flask dev server

| Usuarios concurrentes | Comportamiento esperado |
|-----------------------|------------------------|
| 1 – 20 | Estable, sin errores |
| 20 – 50 | Errores intermitentes por saturación |
| 50+ | Alta tasa de errores (timeout / connection refused) |

> **Nota:** Las métricas de Enmascaramiento y Votación solo se calculan sobre peticiones **exitosas**. Los errores de conexión indican que el servidor no procesó la petición, no que la votación haya fallado.

### Solución para pruebas con alta concurrencia

Reemplazar el servidor de desarrollo por **gunicorn**:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "client.cotizacion:app"
```

| Parámetro | Descripción |
|-----------|-------------|
| `-w 4` | 4 workers (procesos paralelos) |
| `-b 0.0.0.0:5000` | Puerto de escucha |

Con gunicorn se pueden manejar varios cientos de usuarios concurrentes sin errores.

---

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| Servicios no inician | Verificar que Python 3.10+ está instalado: `python --version` |
| Puerto en uso | Matar procesos anteriores: `Get-Process python \| Stop-Process -Force` |
| Lentitud en respuestas | Usar `127.0.0.1` en lugar de `localhost` en las URLs |
| JMeter no encuentra el plan | Verificar la ruta en `File → Open` |
| Error de conexión | Asegurar que todos los servicios estén corriendo: `http://127.0.0.1:5000/health` |

---

## Derechos Reservados

Universidad de los Andes - Módulo 4 EDA
