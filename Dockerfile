# Contenedor de procesamiento: Jupyter + pandas + scikit-learn
FROM python:3.13-slim

WORKDIR /proyecto

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El código (src/, notebooks/) y los datos llegan por volúmenes desde docker-compose.yml

EXPOSE 8888

# 1) Ejecuta el pipeline (descarga, notebook completo, MongoDB y PDF)
# 2) Deja JupyterLab abierto para revisar el notebook
CMD ["sh", "-c", "python src/pipeline.py && exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --IdentityProvider.token=\"$JUPYTER_TOKEN\" --ServerApp.root_dir=/proyecto"]
