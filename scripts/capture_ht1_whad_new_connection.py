#!/usr/bin/env python3
"""
SensorPush HT1 BLE Sniffer - New Connection Monitor
RESULT: FAILED - Captured 0 packets

Why this failed:
- sniff_new_connection() monitors for NEW connection establishments
- HT1 uses existing bond, not new connections
- Bonded reconnections bypass advertisement phase
- Uses directed advertising (invisible to sniffers)
"""

from whad.ble import Sniffer
from whad.device import WhadDevice
import time

def main():
    print("=" * 60)
    print("SensorPush HT1 BLE Sniffer - New Connection Monitor")
    print("=" * 60)
    print("[*] Initializing WHAD device...")

    try:
        device = WhadDevice.create('uart0')
        print("[✓] Device found: uart0")

        sniffer = Sniffer(device)
        print("[✓] Sniffer initialized")

        print("[*] Monitoring for NEW BLE connections...")
        print("[!] This captures connection establishment packets")
        print("[!] Now connect your PHONE to the HT1")
        print()

        # Sniff for new connections
        sniffer.sniff_new_connection()
        sniffer.start()

        start_time = time.time()
        duration = 60  # seconds
        packet_count = 0

        print(f"[*] Sniffing for {duration} seconds...")
        print("[*] Connect with your phone NOW")
        print()

        while time.time() - start_time < duration:
            try:
                packet = sniffer.wait_packet(timeout=1.0)
                if packet:
                    packet_count += 1
                    print(f"[{packet_count}] New connection: {packet}")

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
            print("[!] No new connections detected")
            print()
            print("WHY THIS FAILED:")
            print("- HT1 uses bonded device reconnection (not NEW connections)")
            print("- Bonded devices skip the public advertisement phase")
            print("- Use directed advertising (specific MAC address)")
            print("- Reconnection handshake is encrypted and invisible")
            print("- External sniffers cannot intercept bonded reconnections")
            print()
            print("SOLUTION: HCI snoop on the paired device (Android/iPhone)")

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
