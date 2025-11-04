# Imagen base liviana de Python 3.12
FROM python:3.12-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar requirements primero (para aprovechar la caché de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Exponer el puerto 5000 (Flask por defecto)
EXPOSE 5000

# Variables de entorno de Flask
ENV FLASK_APP=app
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1
ENV PYTHONUNBUFFERED=1

# Comando de inicio de la aplicación
CMD ["flask", "run", "--host=0.0.0.0"]
