"""Gráficas del dashboard, hechas con Plotly.

Cada función recibe datos ya filtrados y devuelve la figura en formato JSON.
La página la dibuja en el navegador con plotly.js.
Los datos siempre se agregan aquí (conteos, medianas, histogramas): nunca se envían
las filas completas al navegador.
"""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Colores de Bootstrap 5 (azul y naranja se distinguen con daltonismo)
AZUL, NARANJA, VERDE, GRIS, ROJO = '#0d6efd', '#fd7e14', '#198754', '#adb5bd', '#dc3545'
COLOR_SEXO = {'Hombres': AZUL, 'Mujeres': NARANJA}
COLOR_EQUIPO = {'Raw': GRIS, 'Single-ply': AZUL, 'Wraps': VERDE}
ORDEN_EDAD = ['Menor de 18', '18-23', '24-39', '40-49', '50-59', '60 o más']


def terminar(figura, alto=360):
    """Aplica el mismo estilo a todas las gráficas y devuelve el JSON."""
    figura.update_layout(height=alto, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor='white', paper_bgcolor='white',
                         legend_title_text='', separators=',.', font=dict(color='#212529', size=13),
                         legend=dict(orientation='h', y=-0.2))
    figura.update_xaxes(showgrid=False, linecolor='#dee2e6')
    figura.update_yaxes(gridcolor='#e9ecef', zeroline=False)
    return figura.to_json()


# ---------------------------------------------------------------------------------------------
# Página Visualizaciones
# ---------------------------------------------------------------------------------------------
def participacion_por_anio(filtrado):
    por_anio = filtrado.groupby(['anio', 'sexo'], observed=True).size().reset_index(name='participaciones')
    figura = px.line(por_anio, x='anio', y='participaciones', color='sexo', color_discrete_map=COLOR_SEXO,
                     labels={'anio': 'Año', 'participaciones': 'Participaciones', 'sexo': 'Sexo'})
    figura.update_traces(line_width=3)
    return terminar(figura)


def participacion_por_lugar(filtrado, nivel):
    """nivel es 'continente' o 'pais' (drill-down)."""
    por_lugar = (filtrado.groupby(nivel, observed=True).size().sort_values(ascending=False).head(12)
                 .sort_values().reset_index(name='participaciones'))
    figura = px.bar(por_lugar, x='participaciones', y=nivel, orientation='h', color_discrete_sequence=[AZUL],
                    labels={'participaciones': 'Participaciones', nivel: ''})
    return terminar(figura)


def dots_por_edad(rendimiento):
    con_edad = rendimiento[rendimiento['edad'].between(14, 75)]
    por_edad = con_edad.groupby(['edad', 'sexo'], observed=True)['dots'].agg(['median', 'size']).reset_index()
    por_edad = por_edad[por_edad['size'] >= 30]      # edades con pocos datos dan una curva inestable
    figura = px.line(por_edad, x='edad', y='median', color='sexo', color_discrete_map=COLOR_SEXO,
                     labels={'edad': 'Edad (años)', 'median': 'Dots (mediana)', 'sexo': 'Sexo'})
    figura.update_traces(line_width=3)
    return terminar(figura)


def total_por_equipo(rendimiento):
    comparacion = (rendimiento.groupby(['equipo', 'sexo'], observed=True)['total_kg'].median()
                   .reset_index(name='mediana_total'))
    figura = px.bar(comparacion, x='sexo', y='mediana_total', color='equipo', barmode='group',
                    color_discrete_map=COLOR_EQUIPO, text_auto='.0f',
                    labels={'sexo': '', 'mediana_total': 'Total (kg, mediana)', 'equipo': 'Equipo'})
    return terminar(figura)


def distribucion_dots(rendimiento):
    """Histograma de Dots por sexo. Se calcula aquí para no enviar un millón de valores al navegador."""
    bordes = np.linspace(0, 700, 71)
    centros = (bordes[:-1] + bordes[1:]) / 2
    figura = go.Figure()
    for sexo in ['Hombres', 'Mujeres']:
        valores = rendimiento.loc[rendimiento['sexo'] == sexo, 'dots']
        if len(valores):
            conteos, _ = np.histogram(valores, bins=bordes)
            figura.add_trace(go.Bar(x=centros, y=conteos, name=sexo, marker_color=COLOR_SEXO[sexo], opacity=0.6))
    figura.update_layout(barmode='overlay', bargap=0, xaxis_title='Dots', yaxis_title='Participaciones')
    return terminar(figura)


def dots_por_grupo_y_equipo(rendimiento):
    pivote = (rendimiento[rendimiento['grupo_edad'] != 'Sin dato']
              .pivot_table(index='grupo_edad', columns='equipo', values='dots', aggfunc='median', observed=True)
              .reindex(ORDEN_EDAD).round(0))
    figura = px.imshow(pivote, text_auto=True, color_continuous_scale='Blues', aspect='auto',
                       labels=dict(x='Equipo', y='Grupo de edad', color='Dots'))
    return terminar(figura)


# ---------------------------------------------------------------------------------------------
# Página Modelo
# ---------------------------------------------------------------------------------------------
def comparacion_modelos(comparacion, mejor):
    """comparacion: lista de diccionarios del documento de MongoDB."""
    ordenado = sorted(comparacion, key=lambda fila: fila['MAE'], reverse=True)
    figura = go.Figure(go.Bar(
        x=[fila['MAE'] for fila in ordenado], y=[fila['modelo'] for fila in ordenado], orientation='h',
        marker_color=[AZUL if fila['modelo'] == mejor else GRIS for fila in ordenado],
        text=[f"{fila['MAE']:.1f} kg".replace('.', ',') for fila in ordenado], textposition='outside', cliponaxis=False))
    figura.update_layout(xaxis_title='MAE (kg)')
    figura.update_xaxes(range=[0, max(fila['MAE'] for fila in ordenado) * 1.2])
    return terminar(figura, 300)


def importancia_variables(variables):
    ordenado = sorted(variables, key=lambda fila: fila['aumento_MAE_kg'])
    figura = go.Figure(go.Bar(x=[fila['aumento_MAE_kg'] for fila in ordenado],
                              y=[fila['variable'] for fila in ordenado], orientation='h', marker_color=AZUL))
    figura.update_layout(xaxis_title='Aumento del MAE al desordenar la variable (kg)')
    return terminar(figura, 300)


# ---------------------------------------------------------------------------------------------
# Página Mi predicción
# ---------------------------------------------------------------------------------------------
def curva_por_edad(curva_poblacion, trayectoria, edad, total_hoy, edad_baja):
    """Curva del total por edad.

    curva_poblacion: modelo de cuantiles (atleta que ya compite).
    trayectoria: proyección personal con la cohorte, o None si no hay marcas.
    """
    figura = go.Figure()
    if trayectoria is not None:
        figura.add_trace(go.Scatter(x=trayectoria['edad'], y=trayectoria['p90'], line=dict(width=0),
                                    showlegend=False, hoverinfo='skip'))
        figura.add_trace(go.Scatter(x=trayectoria['edad'], y=trayectoria['p10'], line=dict(width=0), fill='tonexty',
                                    fillcolor='rgba(13,110,253,0.15)', name='Rango mínimo–máximo', hoverinfo='skip'))
        figura.add_trace(go.Scatter(x=trayectoria['edad'], y=trayectoria['p50'], line=dict(color=AZUL, width=3),
                                    name='Su proyección típica'))
        figura.add_trace(go.Scatter(x=curva_poblacion['edad'], y=curva_poblacion['p50'],
                                    line=dict(color=GRIS, width=2, dash='dash'), name='Atleta típico que ya compite'))
    else:
        figura.add_trace(go.Scatter(x=curva_poblacion['edad'], y=curva_poblacion['p90'], line=dict(width=0),
                                    showlegend=False, hoverinfo='skip'))
        figura.add_trace(go.Scatter(x=curva_poblacion['edad'], y=curva_poblacion['p10'], line=dict(width=0),
                                    fill='tonexty', fillcolor='rgba(13,110,253,0.15)', name='Rango P10–P90',
                                    hoverinfo='skip'))
        figura.add_trace(go.Scatter(x=curva_poblacion['edad'], y=curva_poblacion['p50'],
                                    line=dict(color=AZUL, width=3), name='Atleta típico'))
    figura.add_trace(go.Scatter(x=[edad], y=[total_hoy], mode='markers', name='Hoy',
                                marker=dict(color=NARANJA, size=13, line=dict(color='white', width=2))))
    if edad_baja is not None:
        figura.add_vline(x=edad_baja, line_dash='dot', line_color=ROJO,
                         annotation_text='Empieza a bajar', annotation_font_color=ROJO)
    figura.update_layout(xaxis_title='Edad (años)', yaxis_title='Total (kg)')
    return terminar(figura, 380)


def distribucion_categoria(totales, mediana, total_hoy, limite):
    """Histograma de los mejores totales de la categoría, con la posición de hoy y la del límite estimado."""
    conteos, bordes = np.histogram(totales, bins=60)
    centros = (bordes[:-1] + bordes[1:]) / 2
    figura = go.Figure(go.Bar(x=centros, y=conteos, marker_color=GRIS, name='Atletas'))
    figura.add_vline(x=mediana, line_dash='dot', line_color='#495057',
                     annotation_text='Mediana', annotation_position='top', annotation_font_color='#495057')
    figura.add_vline(x=total_hoy, line_color=NARANJA, line_width=3, annotation_text='Hoy',
                     annotation_position='top left', annotation_font_color=NARANJA)
    if limite > total_hoy * 1.02:
        figura.add_vline(x=limite, line_color=AZUL, line_width=3, annotation_text='Su límite',
                         annotation_position='top right', annotation_font_color=AZUL)
    figura.update_layout(showlegend=False, bargap=0.03, xaxis_title='Mejor total de cada atleta (kg)',
                         yaxis_title='Atletas')
    return terminar(figura, 380)
