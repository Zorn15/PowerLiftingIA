"""Descarga el dataset OpenIPF y lo deja en data/raw/.

Si ya hay un archivo openipf-*.csv en data/raw/, no descarga nada.

Uso:
    python src/descargar_datos.py
"""
import glob
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL_ZIP = 'https://openpowerlifting.gitlab.io/opl-csv/files/openipf-latest.zip'
RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / 'data' / 'raw'


def descargar():
    """Devuelve la ruta del CSV en data/raw/. Lo descarga si no existe."""
    DIR_RAW.mkdir(parents=True, exist_ok=True)

    existentes = sorted(glob.glob(str(DIR_RAW / 'openipf-*.csv')))
    if existentes:
        print('Ya existe el dataset:', Path(existentes[-1]).name, '- no se descarga.')
        return Path(existentes[-1])

    ruta_zip = DIR_RAW / 'openipf-latest.zip'
    print('Descargando', URL_ZIP)
    with urllib.request.urlopen(URL_ZIP) as respuesta, open(ruta_zip, 'wb') as salida:
        shutil.copyfileobj(respuesta, salida)
    print('Descarga terminada:', round(ruta_zip.stat().st_size / 1024**2), 'MB')

    # El ZIP trae una carpeta con el CSV y archivos de licencia: solo se extrae el CSV
    with zipfile.ZipFile(ruta_zip) as archivo_zip:
        nombres_csv = [nombre for nombre in archivo_zip.namelist() if nombre.endswith('.csv')]
        if not nombres_csv:
            sys.exit('El ZIP descargado no contiene un CSV.')
        destino = DIR_RAW / Path(nombres_csv[0]).name
        with archivo_zip.open(nombres_csv[0]) as origen, open(destino, 'wb') as salida:
            shutil.copyfileobj(origen, salida)

    ruta_zip.unlink()
    print('Dataset listo:', destino.name, '-', round(destino.stat().st_size / 1024**2), 'MB')
    return destino


if __name__ == '__main__':
    descargar()
