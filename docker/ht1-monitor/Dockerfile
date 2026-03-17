FROM python:3.11-slim

# BlueZ and D-Bus dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    bleak==0.22.3 \
    paho-mqtt==2.1.0 \
    influxdb-client==1.44.0

COPY scripts/ht1_monitor.py .

CMD ["python3", "-u", "ht1_monitor.py"]
