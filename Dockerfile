# Usamos una imagen base oficial de Python ligera
FROM python:3.10-slim

# Establecemos el directorio de trabajo en el contenedor
WORKDIR /app

# Instalamos dependencias del sistema necesarias
# poppler-utils es requerido por pdf2image
# gcc y otras librerías pueden ser necesarias para compilar ciertas dependencias de Python
RUN apt-get update && apt-get install -y \
    poppler-utils \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamos primero el archivo de requerimientos para aprovechar el caché de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código de la aplicación
COPY . .

# Exponemos el puerto que usa Streamlit por defecto
EXPOSE 8501

# Usamos CMD con sh -c para permitir la expansión de variables de entorno ($PORT)
# Render asigna automáticamente la variable PORT. Si no está definida, usa 8501.
CMD sh -c "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"
