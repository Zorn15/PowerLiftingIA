# Contenedor de la app: dashboard web con Flask y Bootstrap 5
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código, páginas HTML y archivos estáticos (Bootstrap, íconos y estilos)
COPY app.py prediccion.py graficas.py ./
COPY templates ./templates
COPY static ./static

EXPOSE 8501

# Un solo proceso: los datos se cargan una vez en memoria y se comparten entre las peticiones
CMD ["gunicorn", "--bind", "0.0.0.0:8501", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
