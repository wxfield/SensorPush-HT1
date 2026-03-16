#!/usr/bin/env python3
"""
SensorPush HT1 Direct BLE Connection - INCORRECT DECODE
RESULT: FAILED - Data was WRONG (77.9°F vs actual 72.4°F)

Why this failed:
- Could connect to HT1 and read GATT characteristics
- Successfully read binary data from characteristic
- But decode formula was WRONG
- Without official documentation, guessed wrong format
- Need to capture official app's communication via HCI snoop
"""

import asyncio
from bleak import BleakClient, BleakScanner

# HT1 BLE Configuration (from previous attempts)
HT1_MAC = "YOUR_HT1_MAC_HERE"  # Replace with your HT1's address
GATT_CHARACTERISTIC_UUID = "ef09000a"  # UNVERIFIED - may be wrong

async def discover_ht1():
    """
    Attempt to discover HT1 device
    NOTE: This will likely FAIL because HT1 doesn't advertise publicly
    """
    print("[*] Scanning for BLE devices...")
    devices = await BleakScanner.discover(timeout=10.0)

    for device in devices:
        print(f"    {device.address} - {device.name}")
        if "HT1" in str(device.name):
            print(f"[✓] Found HT1: {device.address}")
            return device.address

    print("[!] HT1 not found")
    print("[!] This is expected - HT1 doesn't advertise publicly")
    return None

async def read_ht1_data(address):
    """
    Connect to HT1 and read sensor data
    WARNING: Decode formula below is WRONG
    """
    print(f"[*] Connecting to {address}...")

    try:
        async with BleakClient(address) as client:
            print("[✓] Connected!")

            # List all services and characteristics
            print("\n[*] Services and Characteristics:")
            for service in client.services:
                print(f"\nService: {service.uuid}")
                for char in service.characteristics:
                    print(f"  Characteristic: {char.uuid}")
                    print(f"    Properties: {char.properties}")

            # Read sensor data
            print(f"\n[*] Reading from characteristic {GATT_CHARACTERISTIC_UUID}...")
            data = await client.read_gatt_char(GATT_CHARACTERISTIC_UUID)
            print(f"[✓] Raw data ({len(data)} bytes): {data.hex()}")

            # WRONG DECODE FORMULA (kept for educational purposes)
            print("\n[!] WARNING: The decode below is INCORRECT")
            print("[!] Actual reading was 72.4°F, this gives 77.9°F")
            print()

            # Incorrect temperature decode
            temp_raw = int.from_bytes(data[2:4], byteorder='little', signed=True)
            temp_f = temp_raw / 100.0
            print(f"Temperature (WRONG): {temp_f:.1f}°F")

            # Incorrect humidity decode
            humidity_raw = int.from_bytes(data[4:6], byteorder='little', signed=False)
            humidity = humidity_raw / 100.0
            print(f"Humidity (WRONG): {humidity:.1f}%")

            print()
            print("WHY THIS IS WRONG:")
            print("- Byte offsets may be incorrect")
            print("- Data format may use different encoding")
            print("- May include checksums or protocol headers")
            print("- Need to analyze official app's communication")
            print()
            print("SOLUTION:")
            print("1. Enable HCI snoop on Android phone")
            print("2. Connect with official SensorPush app")
            print("3. Capture BLE traffic to btsnoop_hci.log")
            print("4. Analyze with Wireshark to find correct format")

    except Exception as e:
        print(f"[✗] Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    print("=" * 60)
    print("SensorPush HT1 Direct Connection (INCORRECT DECODE)")
    print("=" * 60)
    print()

    # Try to discover HT1 (likely will fail)
    address = await discover_ht1()

    if not address:
        # Use hardcoded address if available
        if HT1_MAC != "YOUR_HT1_MAC_HERE":
            print(f"[*] Using hardcoded address: {HT1_MAC}")
            address = HT1_MAC
        else:
            print("[!] No HT1 found and no hardcoded address")
            print("[!] Edit script and set HT1_MAC variable")
            return

    # Attempt to connect and read (will show wrong data)
    await read_ht1_data(address)

if __name__ == "__main__":
    asyncio.run(main())
