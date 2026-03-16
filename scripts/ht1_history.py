#!/usr/bin/env python3
"""
SensorPush HT1 - BLE History Download

Downloads full historical sensor readings directly from the HT1 via BLE.
No cloud account required.

Protocol (reverse-engineered 2026-03-12):
  Service:         ef090000-11d6-42ba-93b8-9dd7ec090aa9
  Command char:    ef090009  (write-with-response)
  Response char:   ef09000a  (notify + read)

  To trigger history download:
    Write 0x01000000 (uint32 LE) to ef090009.

  Response format (20 bytes per notification):
    Bytes  0- 3: uint32 LE Unix timestamp of oldest record in this batch
    Bytes  4- 7: sensor record 1 (Si7021 packed, same as advertisement)
    Bytes  8-11: sensor record 2
    Bytes 12-15: sensor record 3
    Bytes 16-19: sensor record 4

  Records within each notification go forward in time (+60s each).
  Notifications are sent newest-first (timestamps decrease each packet).
  0xFFFFFFFF in a data slot = end of history (no more records).

  Sensor data packing (Si7021 format, same as BLE advertisement):
    hum_raw  = byte0 + ((byte1 & 0x0F) << 8)
    temp_raw = (byte1 >> 4) + (byte2 << 4) + ((byte3 & 0x03) << 12)
    humidity = -6.0 + (125.0 * hum_raw  / 4096.0)     [%RH]
    temp_c   = -46.85 + (175.72 * temp_raw / 16384.0)  [°C]

Usage:
    python3 ht1_history.py                   # print to stdout
    python3 ht1_history.py --csv out.csv     # save as CSV
    python3 ht1_history.py --json out.json   # save as JSON
    python3 ht1_history.py --mqtt            # publish to MQTT
    python3 ht1_history.py --since 2026-03-10  # records since date (local time)
"""

import asyncio
import argparse
import csv
import json
import os
import struct
import sys
from datetime import datetime, timezone
from typing import Iterator

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

# UUIDs
SP_SERVICE   = "ef090000-11d6-42ba-93b8-9dd7ec090aa9"
SP_CMD_CHAR  = "ef090009-11d6-42ba-93b8-9dd7ec090aa9"
SP_RESP_CHAR = "ef09000a-11d6-42ba-93b8-9dd7ec090aa9"

# History download trigger command
HISTORY_CMD  = struct.pack("<I", 1)   # 0x01000000

# MQTT config
MQTT_HOST    = os.environ.get("MQTT_HOST", "")
MQTT_PORT    = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER    = os.environ.get("MQTT_USER", "admin")
MQTT_PASS    = os.environ.get("MQTT_PASS", "")
MQTT_TOPIC   = os.environ.get("MQTT_TOPIC", "sensorpush/ht1_history")


# ─── Decode ──────────────────────────────────────────────────────────────────

def decode_record(data: bytes) -> dict | None:
    """
    Decode a 4-byte Si7021-packed sensor record from HT1 history.
    Returns None for 0xFFFFFFFF (end-of-history sentinel) or unsupported types.
    """
    if len(data) < 4:
        return None
    if data == b"\xff\xff\xff\xff":
        return None  # end-of-history marker

    b0, b1, b2, b3 = data[0], data[1], data[2], data[3]
    hum_raw  = b0 + ((b1 & 0x0F) << 8)
    temp_raw = (b1 >> 4) + (b2 << 4) + ((b3 & 0x03) << 12)

    humidity = round(max(0.0, min(100.0, -6.0 + 125.0 * hum_raw  / 4096.0)), 2)
    temp_c   = round(-46.85 + 175.72 * temp_raw / 16384.0, 2)
    temp_f   = round(temp_c * 9 / 5 + 32, 2)

    return {"temp_c": temp_c, "temp_f": temp_f, "humidity": humidity}


def parse_notification(data: bytes, interval: int = 60) -> list[dict]:
    """
    Parse a 20-byte history notification into up to 4 timestamped records.
    Returns a list of records (may be fewer than 4 if sentinel found).
    """
    if len(data) < 20:
        return []

    base_ts = struct.unpack_from("<I", data, 0)[0]
    records = []
    for i in range(4):
        chunk = data[4 + i*4 : 4 + (i+1)*4]
        rec = decode_record(chunk)
        if rec is None:
            break   # sentinel hit...no more records
        ts = base_ts + i * interval
        rec["timestamp"]   = ts
        rec["datetime_utc"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        records.append(rec)
    return records


# ─── BLE ─────────────────────────────────────────────────────────────────────

async def find_ht1(timeout: float = 20.0) -> str | None:
    """Scan for HT1 by service UUID or local name 's'."""
    print(f"[*] Scanning {timeout:.0f}s for HT1...", file=sys.stderr, flush=True)
    found = None

    def cb(dev, adv):
        nonlocal found
        if found:
            return
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        name  = adv.local_name or ""
        if SP_SERVICE.lower() in uuids or name == "s":
            found = dev.address
            print(f"[+] Found HT1: {dev.address}  RSSI={adv.rssi}", file=sys.stderr, flush=True)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    deadline = asyncio.get_event_loop().time() + timeout
    while found is None and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    await scanner.stop()
    return found


async def download_history(address: str, since_ts: int = 0) -> list[dict]:
    """
    Connect to HT1 and download full history.
    Returns list of dicts sorted oldest→newest.
    since_ts: Unix timestamp; discard records older than this.
    """
    all_records = []
    done_event  = asyncio.Event()

    def on_notify(char: BleakGATTCharacteristic, data: bytearray):
        recs = parse_notification(bytes(data))
        if recs:
            all_records.extend(recs)
        else:
            # Empty parse = all-sentinel notification = download complete
            done_event.set()
        # Also detect completion when the last record is a sentinel
        if len(data) >= 20:
            last = bytes(data[16:20])
            if last == b"\xff\xff\xff\xff":
                done_event.set()

    print(f"[*] Connecting to {address}...", file=sys.stderr, flush=True)
    async with BleakClient(address, timeout=30.0) as client:
        print(f"[*] Connected. MTU={client.mtu_size}", file=sys.stderr, flush=True)

        await client.start_notify(SP_RESP_CHAR, on_notify)
        print(f"[*] Notifications enabled on ef09000a", file=sys.stderr, flush=True)

        print(f"[*] Requesting history (writing 0x01000000 to ef090009)...", file=sys.stderr, flush=True)
        await client.write_gatt_char(SP_CMD_CHAR, HISTORY_CMD, response=True)

        print(f"[*] Downloading history (waiting for completion)...", file=sys.stderr, flush=True)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            print(f"[!] Timeout waiting for history completion", file=sys.stderr, flush=True)

        await client.stop_notify(SP_RESP_CHAR)

    # Sort oldest→newest, deduplicate, apply since filter
    all_records.sort(key=lambda r: r["timestamp"])
    seen = set()
    result = []
    for r in all_records:
        key = (r["timestamp"], r["temp_c"], r["humidity"])
        if key not in seen and r["timestamp"] >= since_ts:
            seen.add(key)
            result.append(r)

    print(f"[*] Downloaded {len(result)} records", file=sys.stderr, flush=True)
    return result


# ─── Output ──────────────────────────────────────────────────────────────────

def print_table(records: list[dict]):
    print(f"{'Timestamp':<12}  {'UTC Time':<25}  {'Temp °F':>8}  {'Temp °C':>8}  {'Humidity':>9}")
    print("-" * 70)
    for r in records:
        print(f"{r['timestamp']:<12}  {r['datetime_utc']:<25}  {r['temp_f']:>8.2f}  {r['temp_c']:>8.2f}  {r['humidity']:>8.2f}%")


def write_csv(records: list[dict], path: str):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "datetime_utc", "temp_f", "temp_c", "humidity"])
        w.writeheader()
        w.writerows(records)
    print(f"[*] Saved {len(records)} records to {path}", file=sys.stderr)


def write_json(records: list[dict], path: str):
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"[*] Saved {len(records)} records to {path}", file=sys.stderr)


def publish_mqtt(records: list[dict], address: str):
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ht1-history")
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST, MQTT_PORT, 60)

        addr_short = address.replace(":", "").replace("-", "")[-6:].lower()
        topic = f"{MQTT_TOPIC}/{addr_short}"
        payload = json.dumps(records)
        client.publish(topic, payload, retain=True)
        print(f"[*] Published {len(records)} records to {topic}", file=sys.stderr)
        client.disconnect()
    except ImportError:
        print("[!] paho-mqtt not installed. Run: pip install paho-mqtt", file=sys.stderr)
    except Exception as e:
        print(f"[!] MQTT error: {e}", file=sys.stderr)


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Download SensorPush HT1 history via BLE")
    parser.add_argument("--csv",        metavar="FILE", help="Save as CSV")
    parser.add_argument("--json",       metavar="FILE", help="Save as JSON")
    parser.add_argument("--mqtt",       action="store_true", help="Publish to MQTT")
    parser.add_argument("--mqtt-host",  default=None, metavar="HOST", help="MQTT broker host (overrides MQTT_HOST env var)")
    parser.add_argument("--mqtt-port",  type=int, default=None, metavar="PORT", help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-topic", default=None, metavar="TOPIC", help="MQTT topic (overrides MQTT_TOPIC env var)")
    parser.add_argument("--mqtt-user",  default=None, metavar="USER", help="MQTT username (overrides MQTT_USER env var)")
    parser.add_argument("--mqtt-pass",  default=None, metavar="PASS", help="MQTT password (overrides MQTT_PASS env var)")
    parser.add_argument("--since",      metavar="DATE", help="Only records since YYYY-MM-DD (local time)")
    parser.add_argument("--scan-timeout", type=float, default=20.0, help="BLE scan timeout (default: 20s)")
    args = parser.parse_args()

    if args.mqtt_host:  MQTT_HOST  = args.mqtt_host
    if args.mqtt_port:  MQTT_PORT  = args.mqtt_port
    if args.mqtt_topic: MQTT_TOPIC = args.mqtt_topic
    if args.mqtt_user:  MQTT_USER  = args.mqtt_user
    if args.mqtt_pass:  MQTT_PASS  = args.mqtt_pass

    since_ts = 0
    if args.since:
        try:
            since_ts = int(datetime.strptime(args.since, "%Y-%m-%d")
                           .replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            print(f"[!] Invalid date format: {args.since}. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)

    address = await find_ht1(timeout=args.scan_timeout)
    if not address:
        print("[!] HT1 not found. Make sure it is unpaired from any other device.", file=sys.stderr)
        sys.exit(1)

    records = await download_history(address, since_ts=since_ts)

    if not records:
        print("[!] No records downloaded.", file=sys.stderr)
        sys.exit(1)

    if args.csv:
        write_csv(records, args.csv)
    elif args.json:
        write_json(records, args.json)
    elif args.mqtt:
        publish_mqtt(records, address)
    else:
        print_table(records)


if __name__ == "__main__":
    asyncio.run(main())
