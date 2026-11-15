# Rendimiento en powerlifting: pipeline de Big Data con Machine Learning (dataset OpenIPF)

**Proyecto final — Gerencia y Almacenamiento en Big Data**
Oscar Alejandro Morales Calderón · Ingeniería de Sistemas · Fundación Universitaria Los Libertadores

**Enlace al video de sustentación:**

## Qué hace

Toma los resultados históricos de competencias de powerlifting de la IPF (1,5 millones de registros), los limpia, los analiza, entrena un modelo que estima el total que levanta un atleta y publica todo en un dashboard.

| Elemento | Detalle |
|---|---|
| Dataset | OpenIPF, del proyecto [OpenPowerlifting](https://openpowerlifting.gitlab.io/opl-csv/bulk-csv.html). Dominio público. |
| Volumen | 1.535.307 filas, 42 columnas, 315 MB en CSV |
| Pregunta de negocio | ¿Qué factores explican el rendimiento de un atleta y se puede estimar su total antes de que compita? |
| Procesamiento | pandas (justificación con mediciones en la sección 2 del notebook) |
| Machine Learning | Regresión del total (kg). Línea base, regresión lineal, Random Forest y Gradient Boosting. Modelos de cuantiles (P10, P50, P90) para el rango de fuerza |
| Resultado del modelo | MAE de 57,2 kg y R² de 0,80 en prueba; 59 % menos error que la línea base |
| Almacenamiento | Parquet para los datos y MongoDB para insights, métricas y metadatos |
| Dashboard | Aplicación web con Flask y Bootstrap 5, 6 páginas: predictor personal más las 5 secciones de la guía (resumen, datos, visualizaciones, modelo, insights). Gráficas con Plotly |

## Arquitectura

```
                         docker compose up --build
 ┌───────────────────┐      ┌───────────────┐      ┌────────────────────┐
 │  procesamiento    │ ───► │    mongo      │ ───► │        app         │ ──► navegador
 │  Jupyter + pandas │      │  documento de │      │ Flask + Bootstrap  │     puerto 8501
 │  ETL, modelo, PDF │      │   análisis    │      │ solo lee resultados│
 └─────────┬─────────┘      └───────────────┘      └─────────▲──────────┘
           │                                                 │
           ▼                                                 │
   Volúmenes: data/raw · data/processed · models/ · reports/ ┘
```

| Servicio | Imagen | Puerto | Qué hace |
|---|---|---|---|
| `mongo` | `mongo:7` | 27017 | Guarda el documento de análisis. Sus datos persisten en el volumen `mongo_datos`. |
| `procesamiento` | `Dockerfile` (raíz) | 8888 | Descarga el dataset si falta, ejecuta el notebook completo y deja JupyterLab abierto. |
| `app` | `app/Dockerfile` | 8501 | Dashboard. Lee Parquet, modelo, PDF y MongoDB. No repite el ETL ni reentrena. |

## Requisitos

- Docker Desktop (o Docker Engine con el plugin Compose).
- 4 GB de RAM libres para Docker y 2 GB de disco.
- Conexión a internet la primera vez (imágenes, librerías y dataset).

## Cómo ejecutar

1. Crear el archivo de credenciales a partir del ejemplo y cambiar la clave:

   ```
   copy .env.example .env        (Windows)
   cp .env.example .env          (Linux / macOS)
   ```

2. Levantar todo:

   ```
   docker compose up --build
   ```

### Orden de ejecución (automático)

1. Arranca `mongo` y Docker espera a que responda.
2. Arranca `procesamiento`, que ejecuta `src/pipeline.py`:
   - descarga el dataset a `data/raw/` si no está (`src/descargar_datos.py`);
   - ejecuta el notebook de principio a fin: ETL, gráficas, modelo, documento en MongoDB y PDF;
   - crea `reports/.pipeline_ok` y abre JupyterLab.
3. Cuando existe `reports/.pipeline_ok`, arranca `app`.

La primera vez tarda varios minutos (construcción de imágenes, descarga y procesamiento). Las siguientes veces el pipeline detecta que los resultados ya existen y no los repite. Para forzar una nueva ejecución, borrar `reports/.pipeline_ok` y `reports/reporte_powerlifting.pdf`.

### Dataset

`data/raw/` va vacía en la entrega. El script descarga la versión más reciente de OpenIPF. El análisis se hizo con la versión del **7 de noviembre de 2026** (`openipf-2026-11-07-f93a530c.csv`); con una versión más nueva las cifras cambian un poco, y los insights y el PDF se recalculan solos.

Si la descarga automática falla, descargar el ZIP de OpenIPF desde https://openpowerlifting.gitlab.io/opl-csv/bulk-csv.html y dejar el archivo `openipf-AAAA-MM-DD-xxxx.csv` en `data/raw/`.

## Cómo verificar que funciona

| Qué | Cómo | Resultado esperado |
|---|---|---|
| Estado de los servicios | `docker compose ps` | `mongo` y `procesamiento` en `healthy`; `app` en `running` |
| Avance del procesamiento | `docker compose logs -f procesamiento` | Termina con `Pipeline terminado.` |
| Dashboard | http://localhost:8501 | Abre el predictor; la página Resumen muestra los indicadores |
| Notebook | http://localhost:8888 (clave: valor de `JUPYTER_TOKEN`) | `notebooks/Morales_Oscar_BigData_ProyectoFinal.ipynb` con todas las celdas ejecutadas |
| MongoDB | `docker compose exec mongo mongosh -u admin -p --eval "db.getSiblingDB('powerlifting').analisis.countDocuments()"` | `1` |
| Reporte | Página «Insights y reporte» → Descargar reporte PDF | PDF de 11 páginas |

Para detener: `Ctrl + C` y luego `docker compose down`. Para borrar también los datos de MongoDB: `docker compose down -v`.

## Estructura

```
Morales_Oscar_BigData_ProyectoFinal/
├── README.md
├── docker-compose.yml
├── Dockerfile                  # imagen del servicio procesamiento
├── requirements.txt            # librerías del procesamiento
├── .env.example
├── data/
│   ├── raw/                    # vacía en la entrega; la llena el script de descarga
│   └── processed/              # Parquet limpio y cubos OLAP
├── notebooks/
│   └── Morales_Oscar_BigData_ProyectoFinal.ipynb   # CRISP-DM completo: ETL, análisis, modelo, MongoDB
├── src/
│   ├── descargar_datos.py      # descarga del dataset
│   ├── pipeline.py             # ejecuta descarga + notebook dentro del contenedor
│   └── reporte_pdf.py          # genera el PDF a partir del documento de MongoDB
├── models/
│   └── modelo.joblib           # modelo entrenado
├── reports/
│   ├── reporte_powerlifting.pdf
│   └── figuras/                # las 9 gráficas en PNG
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py                  # servidor Flask: rutas de las páginas y carga de datos
    ├── prediccion.py           # cálculos del predictor personal (límite, rango, ranking, Dots)
    ├── graficas.py             # gráficas de Plotly
    ├── templates/              # páginas HTML (Jinja + Bootstrap 5)
    └── static/                 # Bootstrap 5, íconos y estilos propios (no necesita internet)
```

El ETL y el entrenamiento están en el notebook, documentados celda por celda. `src/pipeline.py` lo ejecuta completo, de modo que hay una sola versión del código.

## Dashboard

| Página | Contenido |
|---|---|
| Mi predicción | Predictor personal: con sexo, edad, peso, altura, equipo, experiencia y marcas actuales muestra el límite estimado, el rango alcanzable (mínimo, típico y máximo), la edad en la que el nivel empieza a bajar, Dots, fuerza relativa, el ranking frente a los atletas del dataset y atletas reales con perfil parecido |
| Resumen | Indicadores del dataset y del modelo |
| Datos | Muestra filtrable del dataset limpio, cubos OLAP y pasos del ETL |
| Visualizaciones | 6 gráficas interactivas que responden a los filtros |
| Modelo | Comparación de modelos, variables importantes y formulario para estimar el total de un atleta |
| Insights y reporte | Insights y recomendaciones leídos de MongoDB, y descarga del PDF |

Cómo calcula el predictor (`app/prediccion.py`, no reentrena nada):

- **Con marcas propias:** busca en el dataset atletas con su mismo sexo y equipo, edad de inicio y Dots parecidos a los suyos, que compitieron al menos 4 años, y mide cuánto mejoró cada uno frente a su primera competencia. El mínimo, el típico y el máximo son los percentiles 10, 50 y 90 de esa mejora aplicados a su total. La edad del pico es la mediana de edad en la que esos atletas lograron su mejor marca.
- **Sin marcas:** usa los modelos de cuantiles guardados en `models/modelo.joblib`, que describen a un atleta que ya compite con ese perfil.
- **Edad de descenso:** edad en la que el nivel de un atleta baja 2 % frente a su mejor marca, comparando a cada atleta consigo mismo.
- **Limitación:** solo incluye atletas que siguieron compitiendo, así que el resultado es optimista. La altura solo se usa para el IMC, porque el dataset no la registra.

Los filtros de las páginas Datos y Visualizaciones son las operaciones OLAP: elegir un rango de años o un sexo es un *slice*, combinar varios es un *dice*, y elegir un continente hace *drill-down* a sus países.

## Problema de infraestructura: la app arrancaba antes de que existieran los datos

**Síntoma.** Con `depends_on: [mongo, procesamiento]` en su forma simple, Docker solo espera a que el contenedor de procesamiento *arranque*, no a que *termine*. La app iniciaba mientras el notebook todavía se estaba ejecutando y fallaba al abrir la página con `FileNotFoundError: .../data/processed/powerlifting_limpio.parquet`.

**Diagnóstico.**

1. `docker compose ps` mostraba los tres servicios en `running`, así que no era un contenedor caído.
2. `docker compose logs app` mostraba el `FileNotFoundError` al leer el Parquet.
3. `docker compose logs procesamiento` seguía en `Ejecutando el notebook...`: el archivo aún no existía.
4. Conclusión: es un problema de orden de arranque. `depends_on` sin condición no conoce el estado interno del servicio.

**Solución.**

1. `src/pipeline.py` crea el archivo `reports/.pipeline_ok` al terminar (y lo borra al empezar).
2. El servicio `procesamiento` tiene un `healthcheck` que revisa si ese archivo existe.
3. La app usa `depends_on: procesamiento: condition: service_healthy`, así que arranca solo cuando el pipeline terminó. Lo mismo se hizo con `mongo` (healthcheck con `mongosh ping`), porque el contenedor de MongoDB arranca varios segundos antes de aceptar conexiones.
4. Como segunda protección, `app.py` revisa que existan el Parquet, el modelo y el PDF, y muestra un aviso en vez de un error si falta alguno.

**Otro punto de red entre contenedores.** Dentro de Docker, `localhost` es el propio contenedor. Por eso el notebook y la app leen el servidor de MongoDB de la variable `MONGO_HOST`, que en `docker-compose.yml` vale `mongo` (el nombre del servicio). Fuera de Docker el valor por defecto es `localhost`.

## Fuente de datos y licencia

Este proyecto usa datos de OpenPowerlifting, https://www.openpowerlifting.org. Los datos son de dominio público.
