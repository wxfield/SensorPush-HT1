#!/usr/bin/env python3
"""
SensorPush HT1 BLE probe from macOS - history protocol discovery.
Scans by service UUID, discovers all chars, enables all notifications,
then systematically probes ef090009 to find history download commands.
"""

import asyncio
import struct
import time
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

SP_SERVICE   = "ef090000-11d6-42ba-93b8-9dd7ec090aa9"
SP_CMD_CHAR  = "ef090009-11d6-42ba-93b8-9dd7ec090aa9"
SP_RESP_CHAR = "ef09000a-11d6-42ba-93b8-9dd7ec090aa9"

received = []

def ts():
    return time.strftime("%H:%M:%S")

def hex_dump(data: bytes, label: str):
    h = data.hex()
    a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    print(f"[{ts()}] {label} ({len(data)}B): {h}  |{a}|", flush=True)
    received.append((ts(), label, data.hex()))


def on_notify(char: BleakGATTCharacteristic, data: bytearray):
    hex_dump(bytes(data), f"NOTIFY {char.uuid[-8:]}")


async def find_ht1(timeout=15.0):
    """Scan for HT1 by service UUID or name 's'."""
    print(f"[*] Scanning {timeout}s for HT1 (service={SP_SERVICE[:8]}...)...", flush=True)
    found = None

    def cb(dev, adv):
        nonlocal found
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        name = adv.local_name or ""
        if SP_SERVICE.lower() in uuids or name == "s":
            if found is None:
                print(f"[+] Found: {dev.address}  name={repr(name)}  RSSI={adv.rssi}", flush=True)
                found = dev.address

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    deadline = asyncio.get_event_loop().time() + timeout
    while found is None and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    await scanner.stop()
    return found


async def probe(address):
    print(f"\n[*] Connecting to {address}...", flush=True)
    async with BleakClient(address, timeout=30.0) as client:
        print(f"[*] Connected! MTU={client.mtu_size}", flush=True)

        # Full service/characteristic table
        print("\n=== SERVICE DISCOVERY ===", flush=True)
        for svc in client.services:
            print(f"SVC {svc.uuid}", flush=True)
            for char in svc.characteristics:
                props = ",".join(char.properties)
                print(f"  CHAR {char.uuid}  [{props}]", flush=True)
                for desc in char.descriptors:
                    print(f"    DESC {desc.uuid}", flush=True)

        # Read every readable characteristic
        print("\n=== READ ALL ===", flush=True)
        for svc in client.services:
            for char in svc.characteristics:
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        hex_dump(bytes(val), f"READ {char.uuid[-8:]}")
                    except Exception as e:
                        print(f"  READ {char.uuid[-8:]} FAILED: {e}", flush=True)

        # Enable notifications on everything that supports it
        print("\n=== ENABLE ALL NOTIFICATIONS ===", flush=True)
        for svc in client.services:
            for char in svc.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    try:
                        await client.start_notify(char.uuid, on_notify)
                        print(f"  NOTIFY ON: {char.uuid}", flush=True)
                    except Exception as e:
                        print(f"  NOTIFY FAIL {char.uuid[-8:]}: {e}", flush=True)

        print(f"\n[*] Waiting 3s for spontaneous notifications...", flush=True)
        await asyncio.sleep(3)

        # Probe ef090009 with various commands
        if any(SP_CMD_CHAR.lower() in c.uuid.lower()
               for svc in client.services for c in svc.characteristics):
            print(f"\n=== PROBING ef090009 COMMANDS ===", flush=True)

            # Known SensorPush read trigger = 0x01000000 (uint32 LE)
            # ef090009/ef09000a are RESERVED ... probing common patterns
            cmds = [
                (b"\x01\x00\x00\x00",             "std-trigger"),
                (b"\x00",                          "0x00"),
                (b"\x01",                          "0x01"),
                (b"\x02",                          "0x02"),
                (b"\x03",                          "0x03"),
                (b"\x04",                          "0x04"),
                (b"\x10",                          "0x10"),
                (b"\x20",                          "0x20"),
                (b"\x50",                          "0x50"),
                (struct.pack("<I", 0),             "ts=0"),
                (struct.pack("<I", 0xFFFFFFFF),    "ts=max"),
                (b"\x01\x00",                      "0x01 0x00"),
                (b"\x02\x00",                      "0x02 0x00"),
                (b"\x01\x00\x00\x00\x00\x00",     "0x01 + 5x00"),
                (b"\x02\x00\x00\x00\x00\x00",     "0x02 + 5x00"),
            ]

            for cmd, label in cmds:
                prev_count = len(received)
                print(f"\n  >> CMD {label}: {cmd.hex()}", flush=True)
                for response in [True, False]:
                    try:
                        await client.write_gatt_char(SP_CMD_CHAR, cmd, response=response)
                        rsp_type = "write-req" if response else "write-cmd"
                        print(f"     {rsp_type} OK", flush=True)
                        await asyncio.sleep(2)
                        new = len(received) - prev_count
                        if new > 0:
                            print(f"     >>> {new} notification(s) received!", flush=True)
                        break
                    except Exception as e:
                        print(f"     {'write-req' if response else 'write-cmd'} FAILED: {e}", flush=True)
        else:
            print(f"\n[!] ef090009 not found in this device's service table", flush=True)

        print(f"\n=== PROBE COMPLETE ===", flush=True)
        print(f"Total notifications received: {len(received)}", flush=True)
        for entry in received:
            print(f"  [{entry[0]}] {entry[1]}: {entry[2]}", flush=True)


async def main():
    addr = await find_ht1(timeout=20.0)
    if not addr:
        print("[!] HT1 not found. Make sure it is unpaired from the tablet.", flush=True)
        return
    await probe(addr)


if __name__ == "__main__":
    asyncio.run(main())
