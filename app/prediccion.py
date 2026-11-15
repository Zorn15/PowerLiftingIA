"""Cálculos del predictor personal del dashboard.

No entrena nada. Hay dos formas de estimar el límite de fuerza:
- Con marcas propias: se buscan atletas del dataset que empezaron con un nivel parecido (mismo sexo y equipo,
  Dots y edad similares) y siguieron compitiendo al menos 4 años, y se ve cuánto mejoraron (cohorte).
- Sin marcas: se usan los modelos de cuantiles guardados en models/modelo.joblib (P10, P50, P90),
  que describen a un atleta que ya compite con ese perfil.
"""
import numpy as np
import pandas as pd

# Categorías de peso de la IPF (límite superior en kg; la última no tiene límite)
CATEGORIAS = {'Hombres': [59, 66, 74, 83, 93, 105, 120],
              'Mujeres': [47, 52, 57, 63, 69, 76, 84]}

# Coeficientes oficiales de la fórmula Dots: (a, b, c, d, e, peso máximo)
COEFICIENTES_DOTS = {'Hombres': (-0.000001093, 0.0007391293, -0.1918759221, 24.0900756, -307.75076, 210),
                     'Mujeres': (-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288, 150)}

COMPETENCIAS_POR_ANIO = 2      # supuesto para proyectar la experiencia hacia el futuro
EDAD_MAXIMA = 75               # hasta qué edad se proyecta
CAIDA_DESCENSO = 0.03          # el descenso (modelo de la población) empieza cuando la curva baja 3 % desde el pico
CAIDA_RELATIVA = 0.02          # el descenso (curva relativa) empieza cuando el nivel baja 2 % desde su pico
MIN_ANIOS_CARRERA = 4          # la cohorte solo incluye atletas que compitieron al menos 4 años
MIN_COHORTE = 15               # con menos atletas que esto la cohorte no es confiable
OBJETIVO_COHORTE = 40          # se amplía la ventana de búsqueda hasta tener al menos estos atletas


def calcular_dots(total, peso, sexo):
    """Puntaje Dots: permite comparar la fuerza de atletas de distinto peso corporal."""
    a, b, c, d, e, peso_maximo = COEFICIENTES_DOTS[sexo]
    x = np.clip(peso, 40, peso_maximo)
    return total * 500 / (a * x**4 + b * x**3 + c * x**2 + d * x + e)


def categoria_ipf(peso, sexo):
    """Devuelve (nombre de la categoría, peso mínimo, peso máximo) según el peso corporal."""
    limites = CATEGORIAS[sexo]
    minimo = 0
    for limite in limites:
        if peso <= limite:
            return f'-{limite} kg', minimo, limite
        minimo = limite
    return f'+{limites[-1]} kg', minimo, 1000


def mejores_marcas(datos):
    """Deja una sola fila por atleta: la de su mejor total en competencia completa y válida."""
    validos = datos[(datos['evento'] == 'SBD') & datos['resultado_valido'] &
                    datos['total_kg'].notna() & datos['dots'].notna()]
    columnas = ['nombre', 'sexo', 'equipo', 'edad', 'peso_corporal_kg', 'sentadilla_kg', 'banca_kg',
                'peso_muerto_kg', 'total_kg', 'dots', 'pais', 'anio']
    mejores = validos.sort_values('total_kg', ascending=False).drop_duplicates('nombre')[columnas]
    mejores['fuerza_relativa'] = mejores['total_kg'] / mejores['peso_corporal_kg']
    return mejores.reset_index(drop=True)


def percentil(valores, valor):
    """Porcentaje de valores que quedan por debajo de 'valor' (0 a 100)."""
    valores = np.asarray(valores, dtype=float)
    valores = valores[~np.isnan(valores)]
    if len(valores) == 0:
        return float('nan')
    return float((valores < valor).mean() * 100)


def nivel(percentil_dots):
    """Nombre del nivel según el percentil de Dots frente a todos los atletas del mismo sexo."""
    for limite, nombre in [(99, 'Élite'), (90, 'Avanzado alto'), (75, 'Avanzado'), (50, 'Intermedio alto'),
                           (25, 'Intermedio'), (10, 'Principiante alto')]:
        if percentil_dots >= limite:
            return nombre
    return 'Principiante'


def proyectar(paquete, sexo, equipo, edad, peso, competencias_previas, anios_experiencia, anio, total_actual=None):
    """Proyecta el total desde la edad actual hasta los 75 años con los modelos de cuantiles.

    Supuestos: el peso corporal se mantiene y la persona sigue entrenando y compitiendo
    (la experiencia sube un año por año y dos competencias por año).
    """
    edades = np.arange(int(edad), max(int(edad), EDAD_MAXIMA) + 1)
    transcurridos = edades - int(edad)
    entrada = pd.DataFrame({
        'edad': edades,
        'peso_corporal_kg': peso,
        'anio': anio,
        'competencias_previas': competencias_previas + COMPETENCIAS_POR_ANIO * transcurridos,
        'anios_experiencia': anios_experiencia + transcurridos,
        'sexo': sexo,
        'equipo': equipo,
    })[paquete['variables']]

    curva = pd.DataFrame({'edad': edades})
    for cuantil in [10, 50, 90]:
        cruda = paquete['cuantiles'][cuantil].predict(entrada)
        # Los árboles dan una curva con escalones: se suaviza con un promedio móvil de 5 años
        curva[f'p{cuantil}'] = pd.Series(cruda).rolling(5, center=True, min_periods=1).mean().to_numpy()
        curva.loc[0, f'p{cuantil}'] = cruda[0]      # el valor de hoy se deja sin suavizar

    # Si la persona dio sus marcas, su curva mantiene la misma distancia frente al atleta típico
    hoy_tipico = float(curva.loc[0, 'p50'])
    factor = total_actual / hoy_tipico if total_actual else 1.0
    curva['personal'] = curva['p50'] * factor

    pico = int(curva['p50'].idxmax())
    despues = curva.iloc[pico:]
    bajan = despues[despues['p50'] < curva.loc[pico, 'p50'] * (1 - CAIDA_DESCENSO)]
    edad_descenso = int(bajan['edad'].iloc[0]) if len(bajan) else None

    return {
        'curva': curva,
        'factor': factor,
        'hoy': {c: float(curva.loc[0, c]) for c in ['p10', 'p50', 'p90', 'personal']},
        'edad_pico': int(curva.loc[pico, 'edad']),
        'pico': {c: float(curva.loc[pico, c]) for c in ['p10', 'p50', 'p90', 'personal']},
        'edad_descenso': edad_descenso,
    }


def ranking(mejores, sexo, equipo, peso, total, dots, marcas=None):
    """Compara a la persona con las mejores marcas de los atletas del dataset."""
    nombre_categoria, minimo, maximo = categoria_ipf(peso, sexo)
    mismo_sexo = mejores[mejores['sexo'] == sexo]
    grupo = mismo_sexo[mismo_sexo['equipo'] == equipo]
    categoria = grupo[(grupo['peso_corporal_kg'] > minimo) & (grupo['peso_corporal_kg'] <= maximo)]

    resultado = {
        'categoria': nombre_categoria,
        'atletas_categoria': len(categoria),
        'atletas_sexo': len(mismo_sexo),
        'percentil_categoria': percentil(categoria['total_kg'], total),
        'puesto_categoria': int((categoria['total_kg'] > total).sum()) + 1,
        'percentil_dots': percentil(mismo_sexo['dots'], dots),
        'percentil_relativa': percentil(mismo_sexo['fuerza_relativa'], total / peso),
        'mediana_categoria': float(categoria['total_kg'].median()) if len(categoria) else float('nan'),
        'totales_categoria': categoria['total_kg'].to_numpy(),
    }

    # Reparto del total entre los tres levantamientos
    columnas = {'Sentadilla': 'sentadilla_kg', 'Press de banca': 'banca_kg', 'Peso muerto': 'peso_muerto_kg'}
    completos = categoria.dropna(subset=list(columnas.values()))
    levantamientos = []
    for nombre, columna in columnas.items():
        if marcas:
            kilos = marcas[nombre]
        else:
            # Sin marcas propias: se reparte el total con la proporción típica de la categoría
            proporcion = (completos[columna] / completos['total_kg']).median() if len(completos) else 1 / 3
            kilos = total * proporcion
        levantamientos.append({'nombre': nombre, 'kg': float(kilos), 'veces_peso': float(kilos / peso),
                               'percentil': percentil(completos[columna], kilos)})
    resultado['levantamientos'] = levantamientos
    return resultado


def atletas_similares(mejores, sexo, equipo, peso, edad, total, cantidad=5):
    """Atletas reales del dataset con sexo, equipo, peso y edad parecidos, y el total más cercano."""
    parecidos = mejores[(mejores['sexo'] == sexo) & (mejores['equipo'] == equipo) &
                        mejores['peso_corporal_kg'].between(peso - 2.5, peso + 2.5) &
                        mejores['edad'].between(edad - 3, edad + 3)].copy()
    parecidos['diferencia'] = (parecidos['total_kg'] - total).abs()
    return parecidos.sort_values('diferencia').head(cantidad).drop(columns='diferencia')


# ---------------------------------------------------------------------------------------------
# Estimación con marcas propias: cohorte de atletas que empezaron con un nivel parecido
# ---------------------------------------------------------------------------------------------
def trayectorias(datos):
    """Resume la carrera de cada atleta: su primera competencia, su mejor Dots y cuántos años compitió.

    Devuelve (tabla por atleta, curva relativa por edad). La curva relativa es el Dots de cada
    competencia dividido por el mejor Dots de ese mismo atleta, para atletas con 3 competencias o más.
    Sirve para ver cómo cambia el nivel con la edad sin mezclar atletas distintos.
    """
    validos = datos[(datos['evento'] == 'SBD') & datos['resultado_valido'] & datos['total_kg'].notna() &
                    datos['dots'].notna() & datos['edad'].notna()]
    validos = validos[['nombre', 'sexo', 'equipo', 'edad', 'dots', 'fecha']].copy()
    validos['fecha'] = pd.to_datetime(validos['fecha'])
    validos = validos.sort_values(['nombre', 'fecha'])

    grupo = validos.groupby('nombre', observed=True)
    primera = grupo.first()
    mejor = validos.loc[grupo['dots'].idxmax()].set_index('nombre')
    tabla = pd.DataFrame({'sexo': primera['sexo'], 'equipo': primera['equipo'], 'edad0': primera['edad'],
                          'dots0': primera['dots'], 'dots_mejor': mejor['dots'], 'edad_mejor': mejor['edad'],
                          'competencias': grupo.size()})
    tabla['anios_carrera'] = (grupo['fecha'].last() - primera['fecha']).dt.days / 365.25
    tabla['ratio'] = tabla['dots_mejor'] / tabla['dots0']

    # Curva relativa por edad (mediana de Dots / mejor Dots del mismo atleta)
    largas = validos.merge(tabla[['dots_mejor', 'competencias']], left_on='nombre', right_index=True)
    largas = largas[largas['competencias'] >= 3]
    largas['relativo'] = largas['dots'] / largas['dots_mejor']
    largas['edad_entera'] = largas['edad'].round().astype(int)
    curvas = {}
    for sexo in ['Hombres', 'Mujeres']:
        por_edad = largas[(largas['sexo'] == sexo) & largas['edad_entera'].between(14, 75)] \
            .groupby('edad_entera')['relativo'].median()
        por_edad = por_edad.reindex(range(14, 76)).interpolate(limit_direction='both')
        curvas[sexo] = por_edad.rolling(3, center=True, min_periods=1).mean()
    return tabla, curvas


def cohorte(tabla, sexo, equipo, edad, dots):
    """Atletas que empezaron con sexo, equipo, edad y Dots parecidos y compitieron al menos 4 años.

    La ventana de búsqueda se amplía hasta reunir al menos 40 atletas.
    Devuelve (cohorte, tolerancia de Dots, tolerancia de edad).
    """
    base = tabla[(tabla['sexo'] == sexo) & (tabla['equipo'] == equipo) & (tabla['anios_carrera'] >= MIN_ANIOS_CARRERA)]
    for tolerancia, margen_edad in [(0.10, 3), (0.15, 4), (0.20, 5), (0.30, 6), (0.40, 8)]:
        grupo = base[base['edad0'].between(edad - margen_edad, edad + margen_edad) &
                     base['dots0'].between(dots * (1 - tolerancia), dots * (1 + tolerancia))]
        if len(grupo) >= OBJETIVO_COHORTE:
            break
    return grupo, tolerancia, margen_edad


def potencial(grupo, total_hoy):
    """Límite de fuerza según la cohorte: cuánto mejoró cada atleta frente a su primera competencia."""
    razones = grupo['ratio'].quantile([0.1, 0.5, 0.9]).to_numpy()
    return {'p10': float(total_hoy * razones[0]), 'p50': float(total_hoy * razones[1]),
            'p90': float(total_hoy * razones[2]),
            'razon_p50': float(razones[1]), 'edad_pico': int(round(grupo['edad_mejor'].median()))}


def edad_descenso(curva_relativa, edad_pico):
    """Edad en la que el nivel baja 2 % respecto a su máximo, después de la edad del pico. None si no baja hasta los 75."""
    despues = curva_relativa[curva_relativa.index >= edad_pico]
    nivel_pico = despues.max()
    bajan = despues[(despues.index > despues.idxmax()) & (despues < nivel_pico * (1 - CAIDA_RELATIVA))]
    return int(bajan.index[0]) if len(bajan) else None


def trayectoria_personal(edad, total_hoy, limites, edad_pico, curva_relativa):
    """Curva estimada del total por edad: sube hasta el límite en la edad del pico y luego baja con la curva relativa."""
    edades = np.arange(int(edad), EDAD_MAXIMA + 1)
    edad_pico = max(int(edad_pico), int(edad))
    nivel_pico = float(curva_relativa.loc[min(edad_pico, 75)])
    resultado = pd.DataFrame({'edad': edades})
    for nombre, limite in limites.items():
        valores = []
        for a in edades:
            if a < edad_pico:
                avance = (a - edad) / (edad_pico - edad)
                valores.append(total_hoy + (limite - total_hoy) * (1 - (1 - avance) ** 2))   # sube rápido y luego se frena
            else:
                valores.append(limite * min(1.0, float(curva_relativa.loc[min(a, 75)]) / nivel_pico))
        resultado[nombre] = valores
    return resultado
