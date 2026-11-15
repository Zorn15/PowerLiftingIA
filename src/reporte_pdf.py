"""Genera el reporte PDF a partir del documento de análisis guardado en MongoDB.

Uso desde el notebook:
    from reporte_pdf import generar_reporte
    generar_reporte(documento, carpeta_figuras, ruta_salida)

Uso desde la terminal (lee el documento directamente de MongoDB):
    python src/reporte_pdf.py
"""
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

AZUL = colors.HexColor('#0072B2')
GRIS = colors.HexColor('#666666')
GRIS_CLARO = colors.HexColor('#f0f0f0')
ANCHO_UTIL = 7.0 * inch


def miles(valor):
    """Número con punto de miles; si tiene decimales usa coma decimal."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return str(valor)
    if float(valor).is_integer():
        return f'{valor:,.0f}'.replace(',', '.')
    texto = f'{valor:,.3f}'.rstrip('0')
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def _estilos():
    base = getSampleStyleSheet()
    return {
        'titulo': ParagraphStyle('titulo', parent=base['Title'], fontSize=24, leading=30, textColor=AZUL, alignment=0),
        'subtitulo': ParagraphStyle('subtitulo', parent=base['Normal'], fontSize=14, leading=18, textColor=GRIS),
        'h1': ParagraphStyle('h1', parent=base['Heading1'], fontSize=16, leading=20, textColor=AZUL, spaceBefore=6, spaceAfter=8),
        'h2': ParagraphStyle('h2', parent=base['Heading2'], fontSize=12, leading=15, spaceBefore=8, spaceAfter=4),
        'p': ParagraphStyle('p', parent=base['Normal'], fontSize=10, leading=14, spaceAfter=6),
        'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=8.5, leading=11),
        'encabezado': ParagraphStyle('encabezado', parent=base['Normal'], fontSize=8.5, leading=11,
                                     textColor=colors.white, fontName='Helvetica-Bold'),
        'pie': ParagraphStyle('pie', parent=base['Normal'], fontSize=9, leading=12, textColor=GRIS, spaceAfter=10),
    }


def _tabla(encabezados, filas, estilos, anchos=None):
    """Tabla con encabezado azul y filas alternadas. Las celdas son párrafos para que el texto haga salto de línea."""
    datos = [[Paragraph(str(e), estilos['encabezado']) for e in encabezados]]
    for fila in filas:
        datos.append([Paragraph(miles(valor), estilos['celda']) for valor in fila])
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
    ]))
    return tabla


def _figura(ruta, descripcion, estilos, ancho=ANCHO_UTIL, alto_maximo=4.6 * inch):
    """Imagen ajustada al ancho de la página, con su descripción debajo."""
    ancho_px, alto_px = ImageReader(str(ruta)).getSize()
    alto = ancho * alto_px / ancho_px
    if alto > alto_maximo:
        ancho, alto = ancho * alto_maximo / alto, alto_maximo
    return KeepTogether([Image(str(ruta), width=ancho, height=alto), Paragraph(descripcion, estilos['pie'])])


def _pie_pagina(lienzo, documento_pdf):
    lienzo.saveState()
    lienzo.setFont('Helvetica', 8)
    lienzo.setFillColor(GRIS)
    lienzo.drawString(0.75 * inch, 0.5 * inch, 'Proyecto Final - Gerencia y Almacenamiento en Big Data')
    lienzo.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f'Página {documento_pdf.page}')
    lienzo.restoreState()


def generar_reporte(documento, carpeta_figuras, ruta_salida):
    """Arma el PDF con el contenido del documento de MongoDB y devuelve la ruta del archivo."""
    carpeta_figuras = Path(carpeta_figuras)
    ruta_salida = Path(ruta_salida)
    estilos = _estilos()
    metadata = documento['metadata']
    dataset = metadata['dataset']
    calidad = documento['calidad_datos']
    modelo = documento['modelo']
    figuras = {f['archivo']: f['descripcion'] for f in documento['visualizaciones_generadas']}
    numero_figura = [0]

    def agregar_figura(archivo):
        """Agrega la figura si existe en disco."""
        ruta = carpeta_figuras / archivo
        if ruta.exists():
            numero_figura[0] += 1
            contenido.append(_figura(ruta, f'Figura {numero_figura[0]}. {figuras.get(archivo, archivo)}', estilos))

    contenido = []

    # ---- Portada ----------------------------------------------------------------------------
    contenido += [
        Spacer(1, 1.8 * inch),
        Paragraph('Rendimiento en powerlifting', estilos['titulo']),
        Paragraph('Pipeline de Big Data con Machine Learning sobre el dataset OpenIPF', estilos['subtitulo']),
        Spacer(1, 0.6 * inch),
        Paragraph('Gerencia y Almacenamiento en Big Data - Proyecto Final', estilos['p']),
        Paragraph('Fundación Universitaria Los Libertadores - Ingeniería de Sistemas', estilos['p']),
        Spacer(1, 0.3 * inch),
        Paragraph('<b>Autor:</b> ' + ', '.join(metadata['autores']), estilos['p']),
        Paragraph(f"<b>Fecha del análisis:</b> {metadata['fecha_analisis']}", estilos['p']),
        Paragraph(f"<b>Dataset:</b> {dataset['nombre']} ({dataset['archivo']})", estilos['p']),
        Spacer(1, 0.6 * inch),
        Paragraph('Reporte generado automáticamente a partir del documento de análisis guardado en MongoDB.', estilos['pie']),
        PageBreak(),
    ]

    # ---- 1. Dataset -------------------------------------------------------------------------
    contenido.append(Paragraph('1. Resumen del dataset', estilos['h1']))
    contenido.append(_tabla(['Dato', 'Valor'], [
        ['Fuente', dataset['fuente']],
        ['URL', dataset['url']],
        ['Registros', dataset['registros']],
        ['Columnas', dataset['columnas']],
        ['Peso en disco (MB)', dataset['peso_disco_mb']],
        ['Memoria en pandas (MB)', dataset['memoria_mb']],
        ['Periodo', f"{dataset['fecha_minima']} a {dataset['fecha_maxima']}"],
        ['Herramienta de procesamiento', metadata['herramienta_procesamiento']],
        ['Registros después de la limpieza', calidad['registros_limpios']],
        ['Registros usados para medir rendimiento', calidad['registros_rendimiento']],
    ], estilos, [2.6 * inch, 4.4 * inch]))

    # ---- 2. Calidad -------------------------------------------------------------------------
    contenido.append(Spacer(1, 12))
    contenido.append(Paragraph('2. Problemas de calidad resueltos', estilos['h1']))
    contenido.append(_tabla(['Problema', 'Cantidad', 'Solución'],
                            [[p['problema'], p['cantidad'], p['solucion']] for p in calidad['problemas_detectados']],
                            estilos, [2.7 * inch, 1.0 * inch, 3.3 * inch]))
    contenido.append(Spacer(1, 10))
    contenido.append(Paragraph('Pasos del ETL con conteos antes y después', estilos['h2']))
    contenido.append(_tabla(['Técnica', 'Paso', 'Antes', 'Después', 'Unidad'],
                            [[p['tecnica'], p['paso'], p['antes'], p['despues'], p['detalle']] for p in calidad['pasos_etl']],
                            estilos, [1.1 * inch, 2.7 * inch, 0.8 * inch, 0.8 * inch, 1.6 * inch]))
    contenido.append(PageBreak())
    agregar_figura('fig01_nulos.png')
    contenido.append(PageBreak())

    # ---- 3. Agregaciones --------------------------------------------------------------------
    contenido.append(Paragraph('3. Tablas de agregación', estilos['h1']))
    for agregacion in documento['agregaciones']:
        filas = agregacion['datos']
        if len(filas) > 12:   # tablas largas: una fila de cada cinco y la última
            filas = filas[::5] + ([filas[-1]] if (len(filas) - 1) % 5 else [])
        encabezados = list(filas[0].keys())
        contenido.append(KeepTogether([
            Paragraph(agregacion['nombre'], estilos['h2']),
            _tabla(encabezados, [[fila[e] for e in encabezados] for fila in filas], estilos),
            Spacer(1, 8),
        ]))
    contenido.append(PageBreak())

    # ---- 4. Visualizaciones -----------------------------------------------------------------
    contenido.append(Paragraph('4. Visualizaciones', estilos['h1']))
    for archivo in ['fig03_p1_participacion.png', 'fig04_p2_edad.png', 'fig05_p3_equipo.png',
                    'fig02_distribucion_dots.png', 'fig06_peso_vs_total.png']:
        agregar_figura(archivo)
    contenido.append(PageBreak())

    # ---- 5. Modelo --------------------------------------------------------------------------
    contenido.append(Paragraph('5. Resultados del modelo', estilos['h1']))
    criterio = modelo['criterio_exito']
    contenido.append(Paragraph(
        f"<b>Tarea:</b> {modelo['tarea']} sobre <i>{modelo['objetivo']}</i>. "
        f"<b>Mejor modelo:</b> {modelo['algoritmo']}. "
        f"<b>Entrenamiento:</b> {miles(modelo['filas_entrenamiento'])} filas. "
        f"<b>Prueba:</b> {miles(modelo['filas_prueba'])} filas.", estilos['p']))
    contenido.append(Paragraph(
        f"<b>Criterio de éxito:</b> reducir el MAE de la línea base en al menos {criterio['mejora_MAE_minima_%']} % "
        f"y lograr un R2 de al menos {miles(criterio['R2_minimo'])}. "
        f"<b>Resultado:</b> {'se cumple' if criterio['cumple'] else 'no se cumple'} "
        f"(mejora de {miles(modelo['metricas']['mejora_MAE_%'])} %, R2 de {miles(modelo['metricas']['R2'])}).",
        estilos['p']))
    contenido.append(_tabla(['Modelo', 'MAE (kg)', 'RMSE (kg)', 'R2', 'Mejora del MAE (%)'],
                            [[m['modelo'], m['MAE'], m['RMSE'], m['R2'], m['mejora_MAE_%']]
                             for m in modelo['comparacion']], estilos))
    contenido.append(Spacer(1, 8))
    contenido.append(Paragraph('Variables más importantes (aumento del MAE al desordenar cada una)', estilos['h2']))
    contenido.append(_tabla(['Variable', 'Aumento del MAE (kg)'],
                            [[v['variable'], v['aumento_MAE_kg']] for v in modelo['variables_importantes']],
                            estilos, [3.5 * inch, 3.5 * inch]))
    contenido.append(Spacer(1, 8))
    for archivo in ['fig07_comparacion_modelos.png', 'fig08_real_vs_predicho.png', 'fig09_importancia_variables.png']:
        agregar_figura(archivo)
    contenido.append(PageBreak())

    # ---- 6. Insights y recomendaciones ------------------------------------------------------
    contenido.append(Paragraph('6. Insights', estilos['h1']))
    for numero, insight in enumerate(documento['insights'], 1):
        contenido.append(KeepTogether([Paragraph(f"{numero}. {insight['titulo']}", estilos['h2']),
                                       Paragraph(insight['texto'], estilos['p'])]))
    contenido.append(Spacer(1, 10))
    contenido.append(Paragraph('7. Recomendaciones', estilos['h1']))
    for numero, recomendacion in enumerate(documento['recomendaciones'], 1):
        contenido.append(Paragraph(f"{numero}. <b>{recomendacion['dirigida_a']}:</b> {recomendacion['texto']}", estilos['p']))

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    pdf = SimpleDocTemplate(str(ruta_salida), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                            title='Rendimiento en powerlifting - Reporte', author=', '.join(metadata['autores']))
    pdf.build(contenido, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return ruta_salida


if __name__ == '__main__':
    from pymongo import MongoClient

    raiz = Path(__file__).resolve().parent.parent
    cliente = MongoClient(host=os.environ.get('MONGO_HOST', 'localhost'), port=int(os.environ.get('MONGO_PORT', 27017)),
                          username=os.environ.get('MONGO_USER') or None, password=os.environ.get('MONGO_PASSWORD') or None)
    documento = cliente[os.environ.get('MONGO_DB', 'powerlifting')]['analisis'].find_one({'_id': 'analisis_powerlifting'})
    cliente.close()
    if documento is None:
        raise SystemExit('No hay documento de análisis en MongoDB. Ejecute primero el notebook.')
    print('Reporte generado:', generar_reporte(documento, raiz / 'reports' / 'figuras', raiz / 'reports' / 'reporte_powerlifting.pdf'))
