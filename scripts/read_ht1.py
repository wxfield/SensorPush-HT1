#!/usr/bin/env python3
"""
SensorPush HT1 - Passive BLE Advertisement Reader

Reads temperature and humidity from SensorPush HT1 by passively
listening to its BLE advertisements. No pairing, no GATT connection,
no cloud required.

Protocol Notes:
- HT1 broadcasts passive advertisements continuously (even while bonded
  to the SensorPush app on a phone)
- Sensor data is in 4-byte manufacturer-specific advertisement data
- Uses packed 12-bit humidity + 14-bit temperature (Si7021-style encoding)
- Identified by local_name == "s" and service UUID ef090000-11d6-42ba-93b8-9dd7ec090aa9

Validated: 2026-03-08
  Our reading: 71.29°F / 34.01% RH
  SensorPush app: 71.8°F / 34% RH
  Delta: ~0.5°F (expected...app gets fresh GATT read; we read cached advertisement)

Usage:
    python3 read_ht1.py                    # scan and print once
    python3 read_ht1.py --continuous       # keep scanning
    python3 read_ht1.py --mqtt             # publish to MQTT
"""

import asyncio
import argparse
import json
import logging
import os
from datetime import datetime

from bleak import BleakScanner, BleakClient

logging.basicConfig(level=logging.WARNING)

# SensorPush HT1 BLE constants
SENSORPUSH_SERVICE_UUID_HT1 = "ef090000-11d6-42ba-93b8-9dd7ec090aa9"
HT1_LOCAL_NAME = "s"

# MQTT config (optional)
MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "admin")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "sensorpush")


# =============================================================================
# DECODE FORMULA
# =============================================================================

def relative_humidity_from_raw(num: int) -> float:
    """Convert 12-bit raw humidity to percentage (Si7021 formula)."""
    v = -6.0 + (125.0 * (num / 4096.0))
    return round(max(0.0, min(100.0, v)), 2)


def temperature_celsius_from_raw(num: int) -> float:
    """Convert 14-bit raw temperature to Celsius (Si7021 formula)."""
    return round(-46.85 + (175.72 * (num / 16384.0)), 2)


def decode_ht1(mfg_data: bytes) -> dict | None:
    """
    Decode HT1 manufacturer data from BLE advertisement.

    mfg_data is 4 bytes: 2-byte company ID (little-endian) prepended
    to the advertisement payload. The full 4 bytes encode:

    Byte 0:    humidity bits [7:0]
    Byte 1:    temperature bits [3:0] | humidity bits [11:8]
    Byte 2:    temperature bits [11:4]
    Byte 3:    0 | device_type[4:0] | temperature bits [13:12] | 0

    Returns dict with temp_c, temp_f, humidity, or None if not HT1.
    """
    if len(mfg_data) < 4:
        return None

    device_type = (mfg_data[3] & 0x7C) >> 2
    if device_type != 1:
        return None

    hum_raw  = (mfg_data[0] & 0xFF) + ((mfg_data[1] & 0x0F) << 8)
    temp_raw = ((mfg_data[1] & 0xFF) >> 4) + ((mfg_data[2] & 0xFF) << 4) + ((mfg_data[3] & 0x03) << 12)

    temp_c   = temperature_celsius_from_raw(temp_raw)
    temp_f   = round(temp_c * 9 / 5 + 32, 2)
    humidity = relative_humidity_from_raw(hum_raw)

    return {
        "temp_c":    temp_c,
        "temp_f":    temp_f,
        "humidity":  humidity,
        "raw_hex":   mfg_data.hex(),
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# GATT READS (device ID, TX power, battery voltage)
# =============================================================================

CHAR_DEVICE_ID       = "ef090001-11d6-42ba-93b8-9dd7ec090aa9"  # 4 bytes, [0:3] = device ID
CHAR_TX_POWER        = "ef090003-11d6-42ba-93b8-9dd7ec090aa9"  # 1 byte, int8 signed, dBm
CHAR_BATTERY_VOLTAGE = "ef090007-11d6-42ba-93b8-9dd7ec090aa9"  # 4 bytes: uint16 ADC_raw + uint16 die_temp_raw

# Battery voltage formula: ADC gain=1/6, reference=0.6V → 3.6V full-scale, 10-bit
# Confirmed by behavioral testing and client application analysis
def battery_voltage_from_raw(raw: int) -> float:
    return round(raw * 3.6 / 1024.0, 2)


async def read_gatt_info(address: str, retries: int = 3) -> dict | None:
    """Open a quick GATT connection to read device ID, TX power, and battery voltage."""
    for attempt in range(retries):
        try:
            async with BleakClient(address, timeout=15.0) as client:
                await asyncio.sleep(1)
                id_data      = await client.read_gatt_char(CHAR_DEVICE_ID)
                tx_data      = await client.read_gatt_char(CHAR_TX_POWER)
                voltage_data = await client.read_gatt_char(CHAR_BATTERY_VOLTAGE)
                device_id    = int.from_bytes(id_data[0:3], "little")       # 24-bit LE
                tx_power_dbm = tx_data[0] if tx_data[0] < 128 else tx_data[0] - 256  # int8 signed
                raw_voltage  = int.from_bytes(voltage_data[0:2], "little") & 0x7FFF  # 15-bit raw ADC
                voltage      = battery_voltage_from_raw(raw_voltage)
                return {"device_id": device_id, "tx_power_dbm": tx_power_dbm,
                        "raw_adc": raw_voltage, "voltage": voltage}
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(3)
            else:
                _LOGGER.debug("GATT read failed after %d attempts: %s", retries, e)
    return None


# =============================================================================
# SCANNER
# =============================================================================

def is_ht1(advertisement_data) -> bool:
    name  = advertisement_data.local_name or ""
    uuids = [u.lower() for u in (advertisement_data.service_uuids or [])]
    return name == HT1_LOCAL_NAME or SENSORPUSH_SERVICE_UUID_HT1.lower() in uuids


async def scan_once(timeout: float = 15.0) -> list[dict]:
    """Scan for HT1 advertisements, return list of decoded readings."""
    results = {}

    def callback(device, advertisement_data):
        if not is_ht1(advertisement_data):
            return
        for cid, payload in (advertisement_data.manufacturer_data or {}).items():
            mfg_data = cid.to_bytes(2, "little") + payload
            reading = decode_ht1(mfg_data)
            if reading:
                reading["address"] = device.address
                reading["rssi"]    = advertisement_data.rssi
                results[device.address] = reading

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    await asyncio.sleep(3)  # allow BT stack to settle before opening GATT connection

    # Fetch battery via GATT for each found device
    for reading in results.values():
        gatt = await read_gatt_info(reading["address"])
        if gatt:
            reading["device_id"]    = gatt["device_id"]
            reading["tx_power_dbm"] = gatt["tx_power_dbm"]
            reading["battery"]      = {"raw_adc": gatt["raw_adc"], "voltage": gatt["voltage"]}

    return list(results.values())


# =============================================================================
# MQTT PUBLISHER
# =============================================================================

def publish_mqtt(readings: list[dict]):
    """Publish readings to MQTT."""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ht1-reader")
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST, MQTT_PORT, 60)

        for r in readings:
            addr_short = r["address"].replace(":", "").replace("-", "")[-6:].lower()
            topic = f"{MQTT_TOPIC_PREFIX}/ht1_{addr_short}"
            batt = r.get("battery", {})
            payload = json.dumps({
                "device_id":      r.get("device_id"),
                "temperature":    r["temp_f"],
                "temperature_c":  r["temp_c"],
                "humidity":       r["humidity"],
                "tx_power_dbm":   r.get("tx_power_dbm"),
                "battery_voltage": batt.get("voltage"),
                "battery_adc":    batt.get("raw_adc"),
                "timestamp":      r["timestamp"],
            })
            client.publish(topic, payload, retain=True)
            print(f"Published to {topic}: {payload}")

        client.disconnect()

    except ImportError:
        print("paho-mqtt not installed. Run: pip install paho-mqtt")
    except Exception as e:
        print(f"MQTT error: {e}")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Read SensorPush HT1 via BLE")
    parser.add_argument("--continuous",  action="store_true", help="Keep scanning continuously")
    parser.add_argument("--mqtt",        action="store_true", help="Publish readings to MQTT")
    parser.add_argument("--mqtt-host",   default=None, metavar="HOST", help="MQTT broker host (overrides MQTT_HOST env var)")
    parser.add_argument("--mqtt-port",   type=int, default=None, metavar="PORT", help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-topic",  default=None, metavar="TOPIC", help="MQTT topic prefix (overrides MQTT_TOPIC_PREFIX env var)")
    parser.add_argument("--mqtt-user",   default=None, metavar="USER", help="MQTT username (overrides MQTT_USER env var)")
    parser.add_argument("--mqtt-pass",   default=None, metavar="PASS", help="MQTT password (overrides MQTT_PASS env var)")
    parser.add_argument("--interval",    type=int, default=60, help="Seconds between scans in continuous mode (default: 60)")
    parser.add_argument("--timeout",     type=int, default=15, help="Seconds to scan per cycle (default: 15)")
    parser.add_argument("--json",        action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.mqtt_host:  MQTT_HOST         = args.mqtt_host
    if args.mqtt_port:  MQTT_PORT         = args.mqtt_port
    if args.mqtt_topic: MQTT_TOPIC_PREFIX = args.mqtt_topic
    if args.mqtt_user:  MQTT_USER         = args.mqtt_user
    if args.mqtt_pass:  MQTT_PASS         = args.mqtt_pass

    while True:
        print(f"Scanning {args.timeout}s...", flush=True)
        readings = await scan_once(timeout=args.timeout)

        if not readings:
            print("No HT1 found.")
        else:
            for r in readings:
                if args.json:
                    print(json.dumps(r))
                else:
                    batt     = r.get("battery")
                    batt_str = f"{batt['voltage']}V  (raw={batt['raw_adc']})" if batt else "unavailable"
                    tx_power = r.get("tx_power_dbm")
                    tx_str   = f"{tx_power} dBm" if tx_power is not None else "unavailable"
                    dev_id   = r.get("device_id", "unavailable")
                    print(f"[{r['timestamp']}] {r['address']}")
                    print(f"  Device ID:   {dev_id}")
                    print(f"  Temperature: {r['temp_f']}°F ({r['temp_c']}°C)")
                    print(f"  Humidity:    {r['humidity']}%")
                    print(f"  Battery:     {batt_str}")
                    print(f"  TX Power:    {tx_str}")
                    print(f"  RSSI:        {r['rssi']} dBm")
                    print(f"  Raw:         {r['raw_hex']}")

            if args.mqtt:
                publish_mqtt(readings)

        if not args.continuous:
            break

        await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
