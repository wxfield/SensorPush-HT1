#!/usr/bin/env python3
"""
SensorPush HT1 BLE Sniffer - Access Address Discovery
RESULT: FAILED - Captured 0 packets

Why this failed:
- discover_access_addresses() finds BLE connection identifiers
- Requires seeing the connection establishment packet
- HT1's bonded reconnection is invisible to external sniffers
- Access addresses are exchanged in encrypted handshake
"""

from whad.ble import Sniffer
from whad.device import WhadDevice
import time

def main():
    print("=" * 60)
    print("SensorPush HT1 BLE Sniffer - Access Address Discovery")
    print("=" * 60)
    print("[*] Initializing WHAD device...")

    try:
        device = WhadDevice.create('uart0')
        print("[✓] Device found: uart0")

        sniffer = Sniffer(device)
        print("[✓] Sniffer initialized")

        print("[*] Discovering BLE access addresses...")
        print("[!] This finds active BLE connections")
        print("[!] Now connect your PHONE to the HT1")
        print()

        # Discover access addresses (connection identifiers)
        # This scans all 40 BLE channels looking for data packets
        access_addresses = sniffer.discover_access_addresses(timeout=60)

        print()
        print(f"[*] Access addresses found: {len(access_addresses)}")

        if access_addresses:
            for aa in access_addresses:
                print(f"    - 0x{aa:08X}")
                # Follow this connection
                print(f"[*] Following connection 0x{aa:08X}...")
                sniffer.sniff_connection_by_aa(aa)
                sniffer.start()

                # Capture packets for 30 seconds
                start = time.time()
                packet_count = 0
                while time.time() - start < 30:
                    try:
                        packet = sniffer.wait_packet(timeout=1.0)
                        if packet:
                            packet_count += 1
                            print(f"[{packet_count}] {packet}")
                    except TimeoutError:
                        continue

                sniffer.stop()
                print(f"    Captured {packet_count} packets")
        else:
            print("[!] No access addresses found")
            print()
            print("WHY THIS FAILED:")
            print("- HT1 uses bonded reconnection (directed, encrypted)")
            print("- Connection establishment invisible to external sniffer")
            print("- Access address exchange happens in encrypted handshake")
            print("- External sniffers can only see unencrypted, public connections")

    except Exception as e:
        print(f"[✗] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        device.close()
        print("[*] Done")

if __name__ == "__main__":
    main()
