FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BULKEDIT_HOST=0.0.0.0 \
    BULKEDIT_PORT=8080 \
    BULKEDIT_DB_PATH=/data/bulkedit.sqlite3

WORKDIR /app

# 1) Abhaengigkeiten (pixxio-client kommt ungepinnt von PyPI)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2) Anwendung inklusive Migrationen; der Start fuehrt `alembic upgrade head` aus
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY app/ ./app/

# Datenbank liegt unter /data, NiceGUI-Sitzungen unter /app/.nicegui
VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read()"

CMD ["python", "-m", "app", "serve"]
