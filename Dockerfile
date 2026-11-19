# Ofis Asistanı (Dinyo) uygulama imajı. Ollama ayrı bir kapsayıcıdır (docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    OFIS_DATA_DIR=/data OFIS_HOST=0.0.0.0 OFIS_PORT=8443

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY run.py .

# Çalışma verisi (veritabanı, bilgi bankası, sertifika, ses/konuşma modelleri) /data altında: kalıcı birimdir.
RUN useradd -m -u 1000 ofis && mkdir -p /data && chown -R ofis:ofis /data /app
USER ofis
VOLUME /data
EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD python -c "import ssl,urllib.request as u; c=ssl.create_default_context(); c.check_hostname=False; c.verify_mode=ssl.CERT_NONE; u.urlopen('https://localhost:8443/api/health', context=c, timeout=8)" || exit 1

CMD ["python", "run.py"]
