"""Ejecuta el pipeline completo dentro del contenedor de procesamiento.

Pasos:
    1. Descarga el dataset si no está en data/raw/.
    2. Espera a que MongoDB responda.
    3. Ejecuta el notebook de principio a fin (ETL, gráficas, modelo, MongoDB y PDF).
    4. Crea el archivo reports/.pipeline_ok, que le indica a Docker que la app ya puede arrancar.

Si los resultados ya existen (archivos y documento en MongoDB), no repite el trabajo.
Para forzar una nueva ejecución: FORZAR_PIPELINE=1.

Uso:
    python src/pipeline.py
"""
import os
import sys
import time
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
from pymongo import MongoClient

from descargar_datos import descargar

RAIZ = Path(__file__).resolve().parent.parent
NOTEBOOK = RAIZ / 'notebooks' / 'Morales_Oscar_BigData_ProyectoFinal.ipynb'
MARCA_OK = RAIZ / 'reports' / '.pipeline_ok'
RESULTADOS = [RAIZ / 'data' / 'processed' / 'powerlifting_limpio.parquet',
              RAIZ / 'models' / 'modelo.joblib',
              RAIZ / 'reports' / 'reporte_powerlifting.pdf']


def conectar_mongo(intentos=30, espera=2):
    """Devuelve un cliente de MongoDB. Reintenta porque el servidor puede tardar en arrancar."""
    for intento in range(1, intentos + 1):
        try:
            cliente = MongoClient(host=os.environ.get('MONGO_HOST', 'localhost'),
                                  port=int(os.environ.get('MONGO_PORT', 27017)),
                                  username=os.environ.get('MONGO_USER') or None,
                                  password=os.environ.get('MONGO_PASSWORD') or None,
                                  serverSelectionTimeoutMS=2000)
            cliente.admin.command('ping')
            return cliente
        except Exception as error:
            print(f'MongoDB aún no responde (intento {intento}/{intentos}): {type(error).__name__}')
            time.sleep(espera)
    sys.exit('No se pudo conectar a MongoDB.')


def hay_documento(cliente):
    """True si el documento de análisis ya está en MongoDB."""
    coleccion = cliente[os.environ.get('MONGO_DB', 'powerlifting')]['analisis']
    return coleccion.count_documents({'_id': 'analisis_powerlifting'}) == 1


def ejecutar_notebook():
    """Ejecuta el notebook completo y lo guarda con sus resultados."""
    print('Ejecutando el notebook (tarda unos minutos)...')
    inicio = time.time()
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    ejecutor = ExecutePreprocessor(timeout=3600, kernel_name='python3')
    ejecutor.preprocess(notebook, {'metadata': {'path': str(NOTEBOOK.parent)}})
    nbformat.write(notebook, NOTEBOOK)
    print(f'Notebook ejecutado en {time.time() - inicio:.0f} s')


def main():
    MARCA_OK.unlink(missing_ok=True)
    descargar()

    cliente = conectar_mongo()
    forzar = os.environ.get('FORZAR_PIPELINE', '0') == '1'
    listo = all(ruta.exists() for ruta in RESULTADOS) and hay_documento(cliente)
    cliente.close()

    if listo and not forzar:
        print('Los resultados ya existen: no se repite el procesamiento.')
    else:
        ejecutar_notebook()

    MARCA_OK.parent.mkdir(parents=True, exist_ok=True)
    MARCA_OK.write_text('ok')
    print('Pipeline terminado.')


if __name__ == '__main__':
    main()
