FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Draai als non-root user, en maak een map voor persistente state
RUN useradd -m appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/data"]

# De hoofdloop schrijft na iedere iteratie een heartbeat; de check faalt
# alleen als de loop echt hangt of gestopt is. Tijdelijke uitval van de
# feed of MQTT houdt de container dus gewoon "healthy" (geen restart-loop).
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os,sys,time; p=os.environ.get('HEARTBEAT_FILE','/app/data/heartbeat'); i=int(os.environ.get('INTERVAL','60')); sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < max(3*i, 300) else 1)"]

CMD ["python", "main.py"]
