"""Dashboard del proyecto: predictor de fuerza en powerlifting (dataset OpenIPF).

Aplicación web hecha con Flask (servidor) y Bootstrap 5 (diseño).
Lee los resultados ya procesados: Parquet en data/processed/, el modelo en models/,
el PDF en reports/ y el documento de análisis en MongoDB.
No repite el ETL ni reentrena el modelo.

Archivos de la app:
- app.py         rutas de las páginas y carga de datos (este archivo)
- prediccion.py  cálculos del predictor personal
- graficas.py    gráficas de Plotly
- templates/     páginas HTML (Jinja + Bootstrap)
- static/        Bootstrap, íconos y estilos propios (no necesita internet)
"""
import os
import threading
import time
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, Response, g, render_template, request, send_file
from plotly.offline import get_plotlyjs
from pymongo import MongoClient

import graficas
import prediccion

# Carpeta raíz del proyecto (en Docker se monta en /proyecto)
RAIZ = Path(os.environ.get('DIR_PROYECTO', Path(__file__).resolve().parent.parent))
RUTA_PARQUET = RAIZ / 'data' / 'processed' / 'powerlifting_limpio.parquet'
RUTA_CUBO_PARTICIPACION = RAIZ / 'data' / 'processed' / 'cubo_participacion.parquet'
RUTA_CUBO_RENDIMIENTO = RAIZ / 'data' / 'processed' / 'cubo_rendimiento.parquet'
RUTA_MODELO = RAIZ / 'models' / 'modelo.joblib'
RUTA_PDF = RAIZ / 'reports' / 'reporte_powerlifting.pdf'

NOMBRE_TEMA = {'participacion': 'Participación', 'rendimiento': 'Rendimiento', 'modelo': 'Modelo',
               'calidad': 'Calidad de datos', 'equipo': 'Equipo', 'edad': 'Edad'}
FILAS_TABLA = 300      # máximo de filas que se muestran en cada tabla

app = Flask(__name__)


# ---------------------------------------------------------------------------------------------
# Formato de números (se usan en las plantillas como filtros: {{ valor|miles }})
# ---------------------------------------------------------------------------------------------
@app.template_filter('miles')
def miles(valor):
    """Número entero con punto de miles."""
    return f'{valor:,.0f}'.replace(',', '.')


@app.template_filter('coma')
def coma(valor, decimales=1):
    """Número con coma decimal. Si falta el dato muestra una raya."""
    if pd.isna(valor):
        return '—'
    return f'{valor:.{decimales}f}'.replace('.', ',')


@app.template_filter('posicion')
def posicion(porcentaje):
    """Texto corto de la posición: 'Top X %' en la mitad alta, 'Supera al X %' en la mitad baja."""
    if porcentaje >= 50:
        return f'Top {coma(max(0.1, 100 - porcentaje))} %'
    return f'Supera al {coma(porcentaje)} %'


def tabla_html(tabla, nombres=None):
    """Convierte un DataFrame en una tabla HTML con las clases de Bootstrap."""
    if nombres:
        tabla = tabla.rename(columns=nombres)
    return tabla.to_html(index=False, border=0, na_rep='', justify='left',
                         classes='table table-sm table-striped table-hover align-middle mb-0',
                         float_format=lambda numero: f'{numero:.1f}'.replace('.', ','))


# ---------------------------------------------------------------------------------------------
# Carga de datos: se hace una sola vez y se guarda en memoria
# ---------------------------------------------------------------------------------------------
RECURSOS = {}
CANDADO = threading.Lock()
DOCUMENTO = {'valor': None, 'hora': 0}


def cargar():
    """Devuelve los datos, el modelo y las tablas del predictor. Solo los lee la primera vez."""
    with CANDADO:
        if not RECURSOS:
            columnas = ['nombre', 'sexo', 'evento', 'equipo', 'edad', 'peso_corporal_kg', 'sentadilla_kg', 'banca_kg',
                        'peso_muerto_kg', 'total_kg', 'dots', 'pais', 'continente', 'federacion', 'fecha', 'anio',
                        'grupo_edad', 'resultado_valido', 'competencias_previas', 'anios_experiencia']
            datos = pd.read_parquet(RUTA_PARQUET, columns=columnas)
            for columna in ['sexo', 'evento', 'equipo', 'pais', 'continente', 'federacion', 'grupo_edad']:
                datos[columna] = datos[columna].astype('category')
            tabla_trayectorias, curvas_relativas = prediccion.trayectorias(datos)
            RECURSOS.update(
                datos=datos,
                cubo_participacion=pd.read_parquet(RUTA_CUBO_PARTICIPACION),
                cubo_rendimiento=pd.read_parquet(RUTA_CUBO_RENDIMIENTO),
                modelo=joblib.load(RUTA_MODELO),
                mejores=prediccion.mejores_marcas(datos),          # una fila por atleta: su mejor total
                trayectorias=tabla_trayectorias,                   # carrera de cada atleta
                curvas_relativas=curvas_relativas,                 # nivel relativo por edad
            )
    return RECURSOS


def leer_documento():
    """Lee el documento de análisis desde MongoDB y cierra la conexión. Se guarda 60 segundos."""
    if DOCUMENTO['valor'] is not None and time.time() - DOCUMENTO['hora'] < 60:
        return DOCUMENTO['valor']
    cliente = MongoClient(host=os.environ.get('MONGO_HOST', 'localhost'),
                          port=int(os.environ.get('MONGO_PORT', 27017)),
                          username=os.environ.get('MONGO_USER') or None,
                          password=os.environ.get('MONGO_PASSWORD') or None,
                          serverSelectionTimeoutMS=5000)
    try:
        base = cliente[os.environ.get('MONGO_DB', 'powerlifting')]
        DOCUMENTO['valor'] = base['analisis'].find_one({'_id': 'analisis_powerlifting'})
        DOCUMENTO['hora'] = time.time()
        return DOCUMENTO['valor']
    finally:
        cliente.close()


@app.before_request
def comprobar():
    """Antes de cada página: verifica que existan los resultados y que MongoDB responda."""
    if request.endpoint in ('static', 'plotly_js', 'icono'):
        return None
    faltantes = [ruta.name for ruta in [RUTA_PARQUET, RUTA_MODELO, RUTA_PDF] if not ruta.exists()]
    if faltantes:
        return render_template('espera.html', titulo='El procesamiento todavía no ha terminado',
                               mensaje='Faltan: ' + ', '.join(faltantes) + '. Revise el avance con '
                                       '"docker compose logs -f procesamiento" y recargue la página.'), 503
    try:
        documento = leer_documento()
    except Exception as error:
        return render_template('espera.html', titulo='No se pudo conectar a MongoDB',
                               mensaje=f'Error: {type(error).__name__}. Verifique que el servicio "mongo" esté activo.'), 503
    if documento is None:
        return render_template('espera.html', titulo='MongoDB todavía no tiene el documento de análisis',
                               mensaje='Ejecute el notebook para generarlo.'), 503
    g.documento = documento
    return None


@app.context_processor
def datos_comunes():
    """Variables disponibles en todas las plantillas (barra superior)."""
    documento = g.get('documento')
    if documento is None:
        return {'doc': None}
    dataset = documento['metadata']['dataset']
    return {'doc': documento, 'info_modelo': documento['modelo'], 'dataset': dataset,
            'periodo': f"{dataset['fecha_minima'][:4]}–{dataset['fecha_maxima'][:4]}"}


# ---------------------------------------------------------------------------------------------
# Lectura de formularios
# ---------------------------------------------------------------------------------------------
def numero(origen, clave, defecto, minimo, maximo):
    """Lee un número de un formulario. Acepta coma decimal y lo limita al rango permitido."""
    try:
        valor = float(str(origen.get(clave, defecto)).replace(',', '.'))
    except ValueError:
        valor = defecto
    return min(max(valor, minimo), maximo)


def leer_filtros(recursos):
    """Filtros de las páginas Datos y Visualizaciones (operaciones OLAP: slice, dice y drill-down)."""
    datos = recursos['datos']
    anio_min, anio_max = int(datos['anio'].min()), int(datos['anio'].max())
    desde = int(numero(request.args, 'desde', 2000, anio_min, anio_max))
    hasta = int(numero(request.args, 'hasta', min(2025, anio_max), anio_min, anio_max))
    enviados = 'desde' in request.args      # la primera vez se usan los valores por defecto
    return {
        'anio_min': anio_min, 'anio_max': anio_max,
        'desde': min(desde, hasta), 'hasta': max(desde, hasta),
        'sexos': request.args.getlist('sexo') if enviados else ['Hombres', 'Mujeres'],
        'equipos': request.args.getlist('equipo') if enviados else ['Raw', 'Single-ply'],
        'continente': request.args.get('continente', 'Todos'),
        'continentes': sorted(datos['continente'].cat.categories),
    }


def aplicar_filtros(tabla, filtros):
    """Devuelve las filas de la tabla que cumplen los filtros."""
    condicion = (tabla['anio'].between(filtros['desde'], filtros['hasta']) &
                 tabla['sexo'].isin(filtros['sexos']) & tabla['equipo'].isin(filtros['equipos']))
    if filtros['continente'] != 'Todos':
        condicion &= tabla['continente'] == filtros['continente']
    return tabla[condicion]


# ---------------------------------------------------------------------------------------------
# Página 1: Mi predicción
# ---------------------------------------------------------------------------------------------
PERFIL_INICIAL = {'nombre': '', 'sexo': 'Hombres', 'edad': 22, 'peso': 75.0, 'altura': 172, 'equipo': 'Raw',
                  'previas': 0, 'experiencia': 0.0, 'sentadilla': 0.0, 'banca': 0.0, 'muerto': 0.0}


def leer_perfil(formulario):
    """Lee y valida los datos que la persona escribió."""
    return {
        'nombre': formulario.get('nombre', '').strip()[:40],
        'sexo': formulario.get('sexo') if formulario.get('sexo') in ('Hombres', 'Mujeres') else 'Hombres',
        'edad': int(numero(formulario, 'edad', 22, 14, 75)),
        'peso': numero(formulario, 'peso', 75, 35, 200),
        'altura': int(numero(formulario, 'altura', 172, 130, 220)),
        'equipo': formulario.get('equipo') if formulario.get('equipo') in ('Raw', 'Single-ply') else 'Raw',
        'previas': int(numero(formulario, 'previas', 0, 0, 200)),
        'experiencia': numero(formulario, 'experiencia', 0, 0, 50),
        'sentadilla': numero(formulario, 'sentadilla', 0, 0, 600),
        'banca': numero(formulario, 'banca', 0, 0, 450),
        'muerto': numero(formulario, 'muerto', 0, 0, 600),
    }


def calcular_prediccion(perfil, recursos):
    """Hace todos los cálculos del predictor y devuelve un diccionario para la plantilla."""
    datos, paquete, mejores = recursos['datos'], recursos['modelo'], recursos['mejores']
    curva_relativa = recursos['curvas_relativas'][perfil['sexo']]

    # Si dio las tres marcas, se usan como total actual; si no, se usa el total estimado
    marcas = {'Sentadilla': perfil['sentadilla'], 'Press de banca': perfil['banca'], 'Peso muerto': perfil['muerto']}
    tiene_marcas = all(kilos > 0 for kilos in marcas.values())
    total_real = sum(marcas.values()) if tiene_marcas else None

    # Modelo de la población: describe a un atleta que ya compite con ese perfil
    proyeccion = prediccion.proyectar(paquete, perfil['sexo'], perfil['equipo'], perfil['edad'], perfil['peso'],
                                      perfil['previas'], perfil['experiencia'], anio=int(datos['anio'].max()),
                                      total_actual=total_real)

    # Con marcas propias: cohorte de atletas que empezaron con un nivel parecido
    grupo, ventana_dots, ventana_edad = None, None, None
    if tiene_marcas:
        dots_marcas = float(prediccion.calcular_dots(total_real, perfil['peso'], perfil['sexo']))
        grupo, ventana_dots, ventana_edad = prediccion.cohorte(recursos['trayectorias'], perfil['sexo'],
                                                               perfil['equipo'], perfil['edad'], dots_marcas)
        if len(grupo) < prediccion.MIN_COHORTE:
            grupo = None
    por_cohorte = grupo is not None

    if por_cohorte:
        total_hoy = total_real
        potencial = prediccion.potencial(grupo, total_hoy)
        limites = {c: potencial[c] for c in ['p10', 'p50', 'p90']}
        edad_pico = max(potencial['edad_pico'], perfil['edad'])
        trayectoria = prediccion.trayectoria_personal(perfil['edad'], total_hoy, limites, edad_pico, curva_relativa)
    else:
        total_hoy = total_real if tiene_marcas else proyeccion['hoy']['p50']
        limites = {c: max(proyeccion['pico'][c], total_hoy) for c in ['p10', 'p50', 'p90']}
        edad_pico = max(proyeccion['edad_pico'], perfil['edad'])
        trayectoria = None

    limite = limites['p50']
    edad_baja = prediccion.edad_descenso(curva_relativa, edad_pico)
    dots_hoy = float(prediccion.calcular_dots(total_hoy, perfil['peso'], perfil['sexo']))
    puesto = prediccion.ranking(mejores, perfil['sexo'], perfil['equipo'], perfil['peso'], total_hoy, dots_hoy,
                                marcas=marcas if tiene_marcas else None)
    similares = prediccion.atletas_similares(mejores, perfil['sexo'], perfil['equipo'], perfil['peso'],
                                             perfil['edad'], total_hoy)

    return {
        'nombre': perfil['nombre'] or 'Atleta',
        'tiene_marcas': tiene_marcas, 'por_cohorte': por_cohorte,
        'total_hoy': total_hoy, 'limite': limite, 'limites': limites,
        'edad_pico': edad_pico, 'en_pico': edad_pico <= perfil['edad'], 'faltan_pico': edad_pico - perfil['edad'],
        'edad_baja': edad_baja, 'faltan_baja': None if edad_baja is None else edad_baja - perfil['edad'],
        'dots': dots_hoy, 'relativa': total_hoy / perfil['peso'],
        'imc': perfil['peso'] / (perfil['altura'] / 100) ** 2,
        'nivel': prediccion.nivel(puesto['percentil_dots']),
        'puesto': puesto,
        'percentil_limite': prediccion.percentil(puesto['totales_categoria'], limite),
        'atletas_cohorte': len(grupo) if por_cohorte else 0,
        'ventana_dots': ventana_dots, 'ventana_edad': ventana_edad,
        'anios_carrera': prediccion.MIN_ANIOS_CARRERA,
        'mae': paquete['mae'],
        'similares': similares.to_dict('records'),
        'grafica_curva': graficas.curva_por_edad(proyeccion['curva'], trayectoria, perfil['edad'], total_hoy, edad_baja),
        'grafica_categoria': graficas.distribucion_categoria(puesto['totales_categoria'], puesto['mediana_categoria'],
                                                             total_hoy, limite),
    }


@app.route('/', methods=['GET', 'POST'])
def pagina_prediccion():
    recursos = cargar()
    perfil, resultado = PERFIL_INICIAL, None
    if request.method == 'POST':
        perfil = leer_perfil(request.form)
        resultado = calcular_prediccion(perfil, recursos)
    return render_template('prediccion.html', pagina='prediccion', perfil=perfil, r=resultado,
                           total_atletas=len(recursos['mejores']))


# ---------------------------------------------------------------------------------------------
# Página 2: Resumen
# ---------------------------------------------------------------------------------------------
@app.route('/resumen')
def pagina_resumen():
    datos = cargar()['datos']
    return render_template('resumen.html', pagina='resumen',
                           paises=datos['pais'].nunique() - 1, federaciones=datos['federacion'].nunique(),
                           mujeres=(datos['sexo'] == 'Mujeres').mean() * 100,
                           hombres=(datos['sexo'] == 'Hombres').mean() * 100)


# ---------------------------------------------------------------------------------------------
# Página 3: Datos
# ---------------------------------------------------------------------------------------------
@app.route('/datos')
def pagina_datos():
    recursos = cargar()
    filtros = leer_filtros(recursos)
    filtrado = aplicar_filtros(recursos['datos'], filtros)
    muestra = filtrado.sample(min(FILAS_TABLA, len(filtrado)), random_state=1) if len(filtrado) else filtrado
    cubo = aplicar_filtros(recursos['cubo_participacion'], filtros).sort_values('participaciones', ascending=False)
    pasos = pd.DataFrame(g.documento['calidad_datos']['pasos_etl'])
    return render_template(
        'datos.html', pagina='datos', filtros=filtros, participaciones=len(filtrado), filas_tabla=FILAS_TABLA,
        tabla_muestra=tabla_html(muestra), filas_cubo=len(cubo),
        tabla_cubo=tabla_html(cubo.head(FILAS_TABLA)),
        tabla_rendimiento=tabla_html(recursos['cubo_rendimiento']),
        tabla_etl=tabla_html(pasos, {'tecnica': 'Técnica', 'paso': 'Paso', 'antes': 'Antes', 'despues': 'Después',
                                     'cambio': 'Cambio', 'detalle': 'Detalle'}))


# ---------------------------------------------------------------------------------------------
# Página 4: Visualizaciones
# ---------------------------------------------------------------------------------------------
@app.route('/visualizaciones')
def pagina_visualizaciones():
    recursos = cargar()
    filtros = leer_filtros(recursos)
    filtrado = aplicar_filtros(recursos['datos'], filtros)
    # Para medir rendimiento: competencia completa, resultado válido y medidas completas
    rendimiento = filtrado[(filtrado['evento'] == 'SBD') & filtrado['resultado_valido'] &
                           filtrado['total_kg'].notna() & filtrado['dots'].notna()]
    nivel = 'continente' if filtros['continente'] == 'Todos' else 'pais'      # drill-down

    figuras = {}
    if len(filtrado):
        figuras['anio'] = graficas.participacion_por_anio(filtrado)
        figuras['lugar'] = graficas.participacion_por_lugar(filtrado, nivel)
    if len(rendimiento):
        figuras['edad'] = graficas.dots_por_edad(rendimiento)
        figuras['equipo'] = graficas.total_por_equipo(rendimiento)
        figuras['dots'] = graficas.distribucion_dots(rendimiento)
        figuras['grupo'] = graficas.dots_por_grupo_y_equipo(rendimiento)
    return render_template('visualizaciones.html', pagina='visualizaciones', filtros=filtros,
                           participaciones=len(filtrado), figuras=figuras)


# ---------------------------------------------------------------------------------------------
# Página 5: Modelo
# ---------------------------------------------------------------------------------------------
@app.route('/modelo', methods=['GET', 'POST'])
def pagina_modelo():
    paquete = cargar()['modelo']
    info = g.documento['modelo']
    entrada = {'sexo': 'Hombres', 'equipo': 'Raw', 'anio': 2026, 'edad': 25, 'peso': 80.0, 'previas': 3, 'experiencia': 2.0}
    estimado = None
    if request.method == 'POST':
        entrada = {
            'sexo': request.form.get('sexo') if request.form.get('sexo') in ('Hombres', 'Mujeres') else 'Hombres',
            'equipo': request.form.get('equipo') if request.form.get('equipo') in ('Raw', 'Single-ply') else 'Raw',
            'anio': int(numero(request.form, 'anio', 2026, 1970, 2030)),
            'edad': int(numero(request.form, 'edad', 25, 10, 85)),
            'peso': numero(request.form, 'peso', 80, 30, 200),
            'previas': int(numero(request.form, 'previas', 3, 0, 200)),
            'experiencia': numero(request.form, 'experiencia', 2, 0, 50),
        }
        # El modelo guardado se usa tal cual; no se reentrena
        fila = pd.DataFrame([{'edad': entrada['edad'], 'peso_corporal_kg': entrada['peso'], 'anio': entrada['anio'],
                              'competencias_previas': entrada['previas'], 'anios_experiencia': entrada['experiencia'],
                              'sexo': entrada['sexo'], 'equipo': entrada['equipo']}])[paquete['variables']]
        estimado = float(paquete['modelo'].predict(fila)[0])
    return render_template('modelo.html', pagina='modelo', entrada=entrada, estimado=estimado, mae=paquete['mae'],
                           grafica_comparacion=graficas.comparacion_modelos(info['comparacion'], info['algoritmo']),
                           grafica_importancia=graficas.importancia_variables(info['variables_importantes']))


# ---------------------------------------------------------------------------------------------
# Página 6: Insights y reporte
# ---------------------------------------------------------------------------------------------
@app.route('/insights')
def pagina_insights():
    insights = g.documento['insights']
    temas = sorted({insight['tema'] for insight in insights})
    tema = request.args.get('tema', 'Todos')
    visibles = [insight for insight in insights if tema in ('Todos', insight['tema'])]
    return render_template('insights.html', pagina='insights', temas=temas, tema=tema, insights=visibles,
                           nombre_tema=NOMBRE_TEMA)


@app.route('/reporte.pdf')
def descargar_reporte():
    return send_file(RUTA_PDF, as_attachment=True, download_name=RUTA_PDF.name)


@app.route('/plotly.js')
def plotly_js():
    """Entrega plotly.js desde la librería instalada, para no depender de internet."""
    respuesta = Response(get_plotlyjs(), mimetype='application/javascript')
    respuesta.headers['Cache-Control'] = 'public, max-age=86400'
    return respuesta


@app.route('/favicon.ico')
def icono():
    """El proyecto no tiene ícono de pestaña; se responde vacío para que el navegador no marque error."""
    return '', 204


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501)
