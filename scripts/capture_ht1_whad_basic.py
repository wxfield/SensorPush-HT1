#!/usr/bin/env python3
"""
SensorPush HT1 BLE Sniffer - Basic Advertisement Capture
RESULT: FAILED - Captured 0 packets

Why this failed:
- HT1 uses bonded device reconnection
- Does NOT advertise publicly after initial pairing
- Only connects to already-paired devices
- External sniffers cannot see bonded reconnections
"""

from whad.ble import Sniffer
from whad.device import WhadDevice
import time

def main():
    print("=" * 60)
    print("SensorPush HT1 BLE Sniffer - Advertisement Capture")
    print("=" * 60)
    print("[*] Initializing WHAD device...")

    try:
        # Create WHAD device (nRF52840 with Butterfly firmware)
        device = WhadDevice.create('uart0')
        print("[✓] Device found: uart0")

        # Create sniffer
        sniffer = Sniffer(device)
        print("[✓] Sniffer initialized")

        # Sniff on channel 37 (primary advertising channel)
        print("[*] Sniffing BLE advertisements on channel 37...")
        print("[!] Now connect your PHONE to the HT1 with SensorPush app")
        sniffer.sniff_advertisements(channel=37)
        sniffer.start()

        packet_count = 0
        start_time = time.time()
        duration = 60  # seconds

        print(f"[*] Sniffing for {duration} seconds...")
        print("[*] Connect with your phone NOW")
        print()

        while time.time() - start_time < duration:
            try:
                packet = sniffer.wait_packet(timeout=1.0)
                if packet:
                    packet_count += 1
                    print(f"[{packet_count}] Packet: {packet}")

                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"[{elapsed}s] Still listening... (connect with phone now)")

            except TimeoutError:
                continue
            except KeyboardInterrupt:
                print("\n[!] Interrupted by user")
                break

        print()
        print(f"[*] Total packets captured: {packet_count}")

        if packet_count == 0:
            print("[!] No packets captured - HT1 might not be advertising")
            print("[!] This is expected if HT1 uses bonded reconnection")
            print()
            print("WHY THIS FAILED:")
            print("- HT1 uses bonded device reconnection (paired devices only)")
            print("- Does NOT broadcast public advertisements")
            print("- External sniffers cannot see bonded connections")
            print("- Need HCI snoop on the paired device instead")

    except Exception as e:
        print(f"[✗] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sniffer.stop()
        device.close()
        print("[*] Sniffer stopped")

if __name__ == "__main__":
    main()
