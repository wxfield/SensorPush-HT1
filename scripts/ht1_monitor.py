#!/usr/bin/env python3
"""
ht1_monitor.py - SensorPush HT1 combined monitor

Phase 1 (startup): GATT history backfill
  - Queries InfluxDB for the most recent timestamp already stored
  - Downloads all history records newer than that timestamp
  - Publishes each record individually to MQTT

Phase 2 (runs forever): Live monitoring
  - Every 60s: reads BLE advertisement, publishes temp/humidity to MQTT
  - Once daily at 03:00: opens GATT connection, reads and publishes:
      ef090003  battery level (raw, suspected 0-100%)
      ef090007  battery ADC + computed voltage
      ef090005  unknown characteristic (raw hex logged for future decoding)
      ef090006  unknown characteristic (raw hex logged for future decoding)
      ef09000b  unknown notify characteristic (raw hex logged for future decoding)

MQTT topics:
  sensorpush/ht1_{addr}/sensor      - live temp/humidity (every 60s)
  sensorpush/ht1_{addr}/diagnostic  - daily GATT battery + unknowns

Environment variables:
  HT1_MAC           BLE MAC address of the HT1 (required)
  MQTT_HOST         MQTT broker host (required)
  MQTT_PORT         MQTT broker port (default: 1883)
  MQTT_USER         MQTT username (default: admin)
  MQTT_PASS         MQTT password (default: "")
  MQTT_TOPIC_PREFIX MQTT topic prefix (default: sensorpush)
  INFLUX_URL        InfluxDB URL (default: http://localhost:8086)
  INFLUX_TOKEN      InfluxDB auth token (required for history backfill)
  INFLUX_ORG        InfluxDB org (default: home)
  INFLUX_BUCKET     InfluxDB bucket (default: sensors)
  SCAN_INTERVAL     Seconds between live scans (default: 60)
  DIAG_HOUR         Hour of day (UTC) for daily GATT diagnostic (default: 3)
"""

import asyncio
import json
import logging
import os
import struct
import sys
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("ht1_monitor")

# ── Config from environment ───────────────────────────────────────────────────

HT1_MAC           = os.environ.get("HT1_MAC", "").upper()
MQTT_HOST         = os.environ.get("MQTT_HOST", "")
MQTT_PORT         = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER         = os.environ.get("MQTT_USER", "admin")
MQTT_PASS         = os.environ.get("MQTT_PASS", "")
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "sensorpush")
INFLUX_URL        = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN      = os.environ.get("INFLUX_TOKEN", "")
INFLUX_ORG        = os.environ.get("INFLUX_ORG", "home")
INFLUX_BUCKET     = os.environ.get("INFLUX_BUCKET", "sensors")
SCAN_INTERVAL     = int(os.environ.get("SCAN_INTERVAL", "60"))
DIAG_HOUR         = int(os.environ.get("DIAG_HOUR", "3"))

# ── BLE UUIDs ─────────────────────────────────────────────────────────────────

SP_SERVICE        = "ef090000-11d6-42ba-93b8-9dd7ec090aa9"
SP_CMD_CHAR       = "ef090009-11d6-42ba-93b8-9dd7ec090aa9"
SP_RESP_CHAR      = "ef09000a-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_DEVICE_ID    = "ef090001-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_BATT_LEVEL   = "ef090003-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_BATT_VOLTAGE = "ef090007-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_UNKNOWN_05   = "ef090005-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_UNKNOWN_06   = "ef090006-11d6-42ba-93b8-9dd7ec090aa9"
CHAR_UNKNOWN_0B   = "ef09000b-11d6-42ba-93b8-9dd7ec090aa9"

HISTORY_CMD       = struct.pack("<I", 1)   # 0x01000000


# ── Decode helpers ────────────────────────────────────────────────────────────

def decode_si7021(data: bytes) -> dict | None:
    """Decode 4-byte Si7021-packed sensor record. Returns None for sentinel."""
    if len(data) < 4 or data == b"\xff\xff\xff\xff":
        return None
    b0, b1, b2, b3 = data[0], data[1], data[2], data[3]
    hum_raw  = b0 + ((b1 & 0x0F) << 8)
    temp_raw = (b1 >> 4) + (b2 << 4) + ((b3 & 0x03) << 12)
    humidity = round(max(0.0, min(100.0, -6.0 + 125.0 * hum_raw  / 4096.0)), 2)
    temp_c   = round(-46.85 + 175.72 * temp_raw / 16384.0, 2)
    temp_f   = round(temp_c * 9 / 5 + 32, 2)
    return {"temp_c": temp_c, "temp_f": temp_f, "humidity": humidity}


def decode_advertisement(advertisement_data) -> dict | None:
    """Decode HT1 manufacturer data from a BLE advertisement."""
    for cid, payload in (advertisement_data.manufacturer_data or {}).items():
        mfg = cid.to_bytes(2, "little") + payload
        if len(mfg) < 4:
            continue
        device_type = (mfg[3] & 0x7C) >> 2
        if device_type != 1:
            continue
        rec = decode_si7021(mfg)
        if rec:
            rec["timestamp"] = int(datetime.now(tz=timezone.utc).timestamp())
            return rec
    return None


def parse_history_notification(data: bytes) -> list[dict]:
    """Parse 20-byte history notification into up to 4 timestamped records."""
    if len(data) < 20:
        return []
    base_ts = struct.unpack_from("<I", data, 0)[0]
    records = []
    for i in range(4):
        chunk = data[4 + i*4: 4 + (i+1)*4]
        rec = decode_si7021(chunk)
        if rec is None:
            break
        rec["timestamp"] = base_ts + i * 60
        records.append(rec)
    return records


# ── MQTT ──────────────────────────────────────────────────────────────────────

def mqtt_publish(topic: str, payload: dict):
    """Publish a single JSON payload to MQTT."""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ht1-monitor")
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.publish(topic, json.dumps(payload), retain=False)
        client.disconnect()
    except Exception as e:
        log.error("MQTT publish failed: %s", e)


def mqtt_publish_batch(topic: str, records: list[dict]):
    """Publish a batch of records to MQTT, one message per record."""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ht1-monitor")
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        for rec in records:
            client.publish(topic, json.dumps(rec), retain=False)
        client.disconnect()
        log.info("Published %d records to %s", len(records), topic)
    except Exception as e:
        log.error("MQTT batch publish failed: %s", e)


def addr_short(mac: str) -> str:
    return mac.replace(":", "").replace("-", "")[-6:].lower()


# ── InfluxDB ──────────────────────────────────────────────────────────────────

def get_latest_influx_timestamp() -> int:
    """Query InfluxDB for the most recent HT1 sensor timestamp. Returns 0 if none."""
    try:
        from influxdb_client import InfluxDBClient
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            query = f'''
                from(bucket: "{INFLUX_BUCKET}")
                  |> range(start: -30d)
                  |> filter(fn: (r) => r["_measurement"] == "sensorpush_sensor")
                  |> filter(fn: (r) => r["_field"] == "temp_c")
                  |> last()
            '''
            tables = client.query_api().query(query)
            for table in tables:
                for record in table.records:
                    ts = record.get_time()
                    if ts:
                        return int(ts.timestamp())
    except Exception as e:
        log.warning("InfluxDB query failed (will backfill all history): %s", e)
    return 0


# ── Phase 1: History backfill ─────────────────────────────────────────────────

async def history_backfill(address: str):
    """Download history via GATT and publish new records to MQTT."""
    log.info("Phase 1: history backfill starting")
    since_ts = get_latest_influx_timestamp()
    if since_ts:
        log.info("Most recent InfluxDB record: %s — downloading only newer records",
                 datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat())
    else:
        log.info("No existing records found — downloading full history")

    all_records = []
    done_event  = asyncio.Event()

    def on_notify(char: BleakGATTCharacteristic, data: bytearray):
        recs = parse_history_notification(bytes(data))
        if recs:
            all_records.extend(recs)
        if len(data) >= 20 and bytes(data[16:20]) == b"\xff\xff\xff\xff":
            done_event.set()
        if not recs:
            done_event.set()

    try:
        async with BleakClient(address, timeout=30.0) as client:
            log.info("Connected for history download. MTU=%d", client.mtu_size)
            await client.start_notify(SP_RESP_CHAR, on_notify)
            await client.write_gatt_char(SP_CMD_CHAR, HISTORY_CMD, response=True)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                log.warning("History download timed out")
            await client.stop_notify(SP_RESP_CHAR)
    except Exception as e:
        log.error("History GATT connection failed: %s", e)
        return

    # Deduplicate, filter, sort oldest→newest
    seen, result = set(), []
    for r in sorted(all_records, key=lambda x: x["timestamp"]):
        key = (r["timestamp"], r["temp_c"], r["humidity"])
        if key not in seen and r["timestamp"] > since_ts:
            seen.add(key)
            result.append(r)

    log.info("History backfill: %d new records to publish", len(result))
    if result:
        topic = f"{MQTT_TOPIC_PREFIX}/ht1_{addr_short(address)}/sensor"
        mqtt_publish_batch(topic, result)

    log.info("Phase 1: history backfill complete")


# ── Phase 2a: Live advertisement scan ─────────────────────────────────────────

async def live_scan_once(address: str, timeout: float = 15.0) -> dict | None:
    """Scan for a single HT1 advertisement and return decoded reading."""
    result = None

    def callback(device, advertisement_data):
        nonlocal result
        if device.address.upper() != address.upper():
            return
        rec = decode_advertisement(advertisement_data)
        if rec:
            rec["rssi"] = advertisement_data.rssi
            result = rec

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return result


# ── Phase 2b: Daily GATT diagnostic ──────────────────────────────────────────

async def read_diagnostic(address: str):
    """Open GATT connection, read battery + unknown characteristics, publish to MQTT."""
    log.info("Daily diagnostic: connecting via GATT")
    try:
        async with BleakClient(address, timeout=30.0) as client:
            await asyncio.sleep(1)

            # ef090001 device ID
            try:
                id_data   = await client.read_gatt_char(CHAR_DEVICE_ID)
                device_id = int.from_bytes(id_data[0:3], "little")
            except Exception:
                device_id = None

            # ef090003 battery level (raw — suspected 0-100%)
            try:
                batt_level_raw = (await client.read_gatt_char(CHAR_BATT_LEVEL))[0]
            except Exception:
                batt_level_raw = None

            # ef090007 battery voltage ADC
            try:
                v_data      = await client.read_gatt_char(CHAR_BATT_VOLTAGE)
                raw_adc     = int.from_bytes(v_data[0:2], "little") & 0x7FFF
                voltage     = round(raw_adc * 3.6 / 1024.0, 2)
            except Exception:
                raw_adc = voltage = None

            # ef090005 unknown
            try:
                unk05 = (await client.read_gatt_char(CHAR_UNKNOWN_05)).hex()
            except Exception:
                unk05 = None

            # ef090006 unknown
            try:
                unk06 = (await client.read_gatt_char(CHAR_UNKNOWN_06)).hex()
            except Exception:
                unk06 = None

            # ef09000b unknown notify — attempt a read (may not support it)
            try:
                unk0b = (await client.read_gatt_char(CHAR_UNKNOWN_0B)).hex()
            except Exception:
                unk0b = None

    except Exception as e:
        log.error("Diagnostic GATT connection failed: %s", e)
        return

    payload = {
        "timestamp":      int(datetime.now(tz=timezone.utc).timestamp()),
        "device_id":      device_id,
        "ef090003_raw":   batt_level_raw,
        "ef090007_raw":   raw_adc,
        "ef090007_volts": voltage,
        "ef090005_hex":   unk05,
        "ef090006_hex":   unk06,
        "ef09000b_hex":   unk0b,
    }

    topic = f"{MQTT_TOPIC_PREFIX}/ht1_{addr_short(address)}/diagnostic"
    mqtt_publish(topic, payload)
    log.info("Diagnostic published: level_raw=%s  adc=%s  volts=%s  05=%s  06=%s  0b=%s",
             batt_level_raw, raw_adc, voltage, unk05, unk06, unk0b)


# ── Phase 2: Live loop ────────────────────────────────────────────────────────

async def live_loop(address: str):
    """Continuous live monitoring loop."""
    log.info("Phase 2: live monitoring starting (interval=%ds, diag_hour=%d UTC)",
             SCAN_INTERVAL, DIAG_HOUR)
    last_diag_day = None
    topic_sensor  = f"{MQTT_TOPIC_PREFIX}/ht1_{addr_short(address)}/sensor"

    while True:
        # Daily diagnostic check
        now = datetime.now(tz=timezone.utc)
        if now.hour == DIAG_HOUR and now.date() != last_diag_day:
            await read_diagnostic(address)
            last_diag_day = now.date()
            await asyncio.sleep(5)  # let BT stack settle after GATT

        # Live advertisement scan
        reading = await live_scan_once(address, timeout=15.0)
        if reading:
            mqtt_publish(topic_sensor, reading)
            log.info("Live: %.2f°F  %.2f°C  %.1f%%RH  RSSI=%s",
                     reading["temp_f"], reading["temp_c"], reading["humidity"],
                     reading.get("rssi", "?"))
        else:
            log.warning("No advertisement received from %s", address)

        await asyncio.sleep(max(0, SCAN_INTERVAL - 15))


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    if not HT1_MAC:
        log.error("HT1_MAC environment variable is required")
        sys.exit(1)
    if not MQTT_HOST:
        log.error("MQTT_HOST environment variable is required")
        sys.exit(1)

    log.info("Starting ht1_monitor  MAC=%s  MQTT=%s:%d  InfluxDB=%s",
             HT1_MAC, MQTT_HOST, MQTT_PORT, INFLUX_URL)

    await history_backfill(HT1_MAC)
    await live_loop(HT1_MAC)


if __name__ == "__main__":
    asyncio.run(main())
