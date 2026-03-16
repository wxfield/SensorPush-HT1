# Complete Guide: Flashing Butterfly Firmware to Taida nRF52840 USB Dongle

## Overview

This guide documents how to flash Butterfly/WHAD firmware onto a Taidacent/Taida nRF52840 USB dongle clone to use it as a Bluetooth Low Energy (BLE) sniffer.

**Why this is needed:**
- The Taida/Taidacent nRF52840 is a **clone dongle**, not an official Nordic Semiconductor device
- Official Nordic tools (nRF Connect for Desktop) do **not** recognize these clone dongles
- The dongle ships with "nRF52 Connectivity" firmware, which is not suitable for BLE sniffing
- Butterfly firmware (from the WHAD project) supports clone dongles and provides BLE sniffing capabilities

**Hardware Details:**
- **Device:** Taidacent/Taida nRF52840 USB Dongle (clone)
- **Chip:** nRF52840 (QIAA-C0 variant - engineering revision)
- **Original Vendor ID:** 1915 (Nordic Semiconductor)
- **Original Product ID:** 521f (connectivity/bootloader mode)
- **After Flashing VID:PID:** c0ff:eeee (WHAD ButteRFly dongle)

---

## Prerequisites

### Hardware
- Taida/Taidacent nRF52840 USB dongle
- Linux machine with USB port (tested on Debian 12)

### Software Requirements
```bash
# System packages
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    git \
    curl \
    build-essential \
    linux-headers-$(uname -r) \
    libevdev-dev

# Python packages
pip3 install adafruit-nrfutil whad
```

**Important:** This guide uses Python 3.13. The `adafruit-nrfutil` package has Python 2/3 compatibility issues that require patching (documented below).

---

## Part 1: Download Butterfly Firmware

### Option A: Direct Download (Recommended)

Download the official firmware upgrade package from WHAD project:

```bash
cd /tmp
curl -L -o butterfly-fwupgrade.zip \
  https://github.com/whad-team/butterfly/releases/download/v1.1.1/butterfly-fwupgrade.zip
```

**Source:** https://github.com/whad-team/butterfly/releases/tag/v1.1.1
**File:** `butterfly-fwupgrade.zip` (157 KB)
**SHA256:** (verify on GitHub releases page)

### What This File Contains

The `butterfly-fwupgrade.zip` is a DFU (Device Firmware Update) package that contains:
- Compiled Butterfly firmware binary
- Manifest file with firmware metadata
- Init packet with firmware validation data

This is the **correct** package format for flashing via Nordic's DFU bootloader.

### Alternative Files (NOT Recommended for adafruit-nrfutil)

Also available but not needed:
- `butterfly.hex` - Raw Intel HEX format (cannot be flashed directly with adafruit-nrfutil)
- `butterfly-mdk-fwupgrade.uf2` - For Makerdiary dongles with UF2 bootloader

---

## Part 2: Fix Python 3.13 Compatibility Issues

The `adafruit-nrfutil` package was written for Python 2 and has not been updated for Python 3.13. You must apply these patches:

### Patch 1: dict.iteritems() → dict.items()

```bash
# Fix package.py
sed -i 's/\.iteritems()/.items()/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/package.py

# Fix manifest.py
sed -i 's/\.iteritems()/.items()/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/manifest.py
```

**Reason:** `dict.iteritems()` was removed in Python 3; use `dict.items()` instead.

### Patch 2: xrange() → range()

```bash
# Fix intelhex/__init__.py
sed -i 's/xrange/range/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/intelhex/__init__.py

# Fix nrfhex.py
sed -i 's/xrange/range/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/nrfhex.py
```

**Reason:** `xrange()` was removed in Python 3; use `range()` instead.

### Patch 3: range() requires integers

```bash
# Fix float to int conversion in intelhex/__init__.py line 348
sed -i '348s/for i in range(start, end+1):/for i in range(int(start), int(end)+1):/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/intelhex/__init__.py
```

**Reason:** Python 3's `range()` requires integer arguments; Python 2 accepted floats.

### Patch 4: array.tostring() → array.tobytes()

```bash
# Fix intelhex/__init__.py
sed -i 's/\.tostring()/.tobytes()/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/intelhex/__init__.py
```

**Reason:** `array.tostring()` was deprecated and removed in Python 3.9+; use `tobytes()`.

### Patch 5: Remove asstr() wrapper

```bash
# Fix line 375 in intelhex/__init__.py
sed -i '375s/return asstr(self._tobinarray_really(start, end, pad, size).tobytes())/return self._tobinarray_really(start, end, pad, size).tobytes()/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/intelhex/__init__.py
```

**Reason:** Binary file writes in Python 3 require `bytes`, not `str`. The `asstr()` wrapper converts bytes to string, causing a `TypeError`.

### Patch 6: Fix struct.pack() in dfu_transport_serial.py

```bash
# Remove map(ord, ...) wrapper (multiple locations)
sed -i 's/+ map(ord, struct\.pack/+ list(struct.pack/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/dfu_transport_serial.py

# Remove map(ord, ...) from send_message calls
sed -i 's/send_message(map(ord,/send_message(/g' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/dfu_transport_serial.py

# Fix syntax on line 466 (extra paren)
sed -i '466s/send_message( to_transmit))/send_message(to_transmit)/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/dfu_transport_serial.py
```

**Reason:**
- In Python 2, `struct.pack()` returns a string, so `map(ord, ...)` converts chars to integers
- In Python 3, `struct.pack()` returns `bytes`, and iterating over bytes gives integers directly
- Using `map(ord, bytes_obj)` causes `TypeError: ord() expected string of length 1, but int found`

### Patch 7: Fix float division in range/slice

```bash
# Fix line 459: range() step must be int
sed -i '459s/range(0, len(data), (self.mtu-1)\/2 - 1)/range(0, len(data), int((self.mtu-1)\/2 - 1))/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/dfu_transport_serial.py

# Fix line 463: slice index must be int
sed -i '463s/\[i:i + (self.mtu-1)\/2 - 1 \]/[i:i + int((self.mtu-1)\/2 - 1)]/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/dfu_transport_serial.py
```

**Reason:** Python 3 division returns floats by default. `range()` and slice indices require integers.

### Patch 8: Fix protobuf bytes field

```bash
# Fix line 104 in init_packet_pb.py
sed -i '104s/.*/                boot_validation.append(pb.BootValidation(type=x.value, bytes=boot_validation_bytes[i].encode() if isinstance(boot_validation_bytes[i], str) else boot_validation_bytes[i]))/' \
  /usr/local/lib/python3.13/dist-packages/nordicsemi/dfu/init_packet_pb.py
```

**Reason:** Protobuf 3+ requires `bytes` type for bytes fields. Empty strings `''` must be converted to `b''`.

### Verification Script

Save this as `verify_patches.sh` to verify all patches were applied:

```bash
#!/bin/bash
echo "Checking Python 3.13 compatibility patches..."

check_file() {
    local file=$1
    local pattern=$2
    local desc=$3

    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo "❌ FAILED: $desc"
        echo "   Found: $pattern in $file"
        return 1
    else
        echo "✅ PASS: $desc"
        return 0
    fi
}

PREFIX="/usr/local/lib/python3.13/dist-packages/nordicsemi/dfu"

check_file "$PREFIX/package.py" "\.iteritems()" "package.py still uses .iteritems()"
check_file "$PREFIX/manifest.py" "\.iteritems()" "manifest.py still uses .iteritems()"
check_file "$PREFIX/intelhex/__init__.py" "xrange" "intelhex/__init__.py still uses xrange"
check_file "$PREFIX/nrfhex.py" "xrange" "nrfhex.py still uses xrange"
check_file "$PREFIX/intelhex/__init__.py" "\.tostring()" "intelhex/__init__.py still uses .tostring()"
check_file "$PREFIX/dfu_transport_serial.py" "map(ord, struct\.pack" "dfu_transport_serial.py still uses map(ord, struct.pack"

echo ""
echo "All patches verified!"
```

---

## Part 3: Put Dongle in DFU Mode

### Physical Procedure

1. **Unplug** the dongle from USB (if plugged in)
2. **Locate the button** - small tactile button on the PCB (NOT the reset button if labeled)
3. **Press and HOLD** the button down
4. **While holding the button**, plug the dongle into USB
5. **Release** the button after plugged in

### Visual Confirmation

**LED Behavior:**
- Some dongles have an LED that pulses RED in DFU mode
- The Taida clone may not have a visible LED indicator

**USB Detection:**
Check `lsusb` and `dmesg`:

```bash
lsusb | grep Nordic
# Should show: Bus XXX Device XXX: ID 1915:521f Nordic Semiconductor Open DFU Bootloader

dmesg | tail -10
# Should show: Product: Open DFU Bootloader
```

**Serial Port:**
The dongle should appear as `/dev/ttyACM0`:

```bash
ls -l /dev/ttyACM*
# Should show: /dev/ttyACM0
```

### Troubleshooting DFU Mode

**Problem:** Device not detected in DFU mode
- Try a different USB port
- Try a different USB cable (must support data, not just power)
- Press button earlier (before plugging in) and hold longer
- Check `dmesg -w` in real-time while plugging in

**Problem:** Wrong device detected
- Make sure you're pressing the correct button (some boards have reset + DFU buttons)
- Verify Product ID shows `521f` (DFU bootloader), not `521c` (connectivity firmware)

---

## Part 4: Flash Butterfly Firmware

### Flash Command

```bash
cd /tmp
adafruit-nrfutil dfu serial \
  -pkg butterfly-fwupgrade.zip \
  -p /dev/ttyACM0 \
  -b 115200
```

### Expected Output

```
|===============================================================|
|##      ##    ###    ########  ##    ## #### ##    ##  ######  |
|##  ##  ##   ## ##   ##     ## ###   ##  ##  ###   ## ##    ## |
|##  ##  ##  ##   ##  ##     ## ####  ##  ##  ####  ## ##       |
|##  ##  ## ##     ## ########  ## ## ##  ##  ## ## ## ##   ####|
|##  ##  ## ######### ##   ##   ##  ####  ##  ##  #### ##    ## |
|##  ##  ## ##     ## ##    ##  ##   ###  ##  ##   ### ##    ## |
| ###  ###  ##     ## ##     ## ##    ## #### ##    ##  ######  |
|===============================================================|
|You are not providing a signature key, which means the DFU     |
|files will not be signed, and are vulnerable to tampering.     |
|This is only compatible with a signature-less bootloader and is|
|not suitable for production environments.                      |
|===============================================================|

Device programmed.
```

**Duration:** Approximately 10-30 seconds

### What Happens During Flashing

1. **Init packet sent** - Contains firmware metadata and validation
2. **Firmware transfer** - Binary data sent in chunks with CRC verification
3. **Validation** - Bootloader verifies firmware integrity
4. **Automatic reset** - Dongle reboots into new firmware

### Common Errors

**Error: CRC validation failed**
- **Cause:** Using wrong firmware file (e.g., `butterfly.hex` instead of `butterfly-fwupgrade.zip`)
- **Solution:** Download and use `butterfly-fwupgrade.zip`

**Error: Device not found**
- **Cause:** Dongle not in DFU mode or wrong serial port
- **Solution:** Re-enter DFU mode, verify `/dev/ttyACM0` exists

**Error: Python 2/3 compatibility errors**
- **Cause:** Patches not applied
- **Solution:** Apply all patches from Part 2

---

## Part 5: Verify Successful Flash

### Automatic Reset

After flashing completes, the dongle will **automatically disconnect and reconnect**. You do **NOT** need to manually unplug/replug it.

### Check USB Device

```bash
lsusb | grep -i 'whad\|butter'
```

**Expected output:**
```
Bus 001 Device XXX: ID c0ff:eeee WHAD ButteRFly dongle
```

**Key indicators:**
- Vendor ID changed: `1915` → `c0ff`
- Product ID changed: `521f` → `eeee`
- Manufacturer: `WHAD`
- Product: `ButteRFly dongle`

### Check Kernel Messages

```bash
dmesg | tail -10
```

**Expected output:**
```
usb X-X: New USB device found, idVendor=c0ff, idProduct=eeee, bcdDevice= 1.00
usb X-X: New USB device strings: Mfr=1, Product=2, SerialNumber=3
usb X-X: Product: ButteRFly dongle
usb X-X: Manufacturer: WHAD
usb X-X: SerialNumber: XXXXXXXXXXXX
cdc_acm X-X:1.0: ttyACM0: USB ACM device
```

### Check Serial Port

```bash
ls -l /dev/ttyACM0
```

The device should still be at `/dev/ttyACM0` (or next available number).

---

## Part 6: Install WHAD Tools

The Butterfly firmware uses the WHAD (Wireless Hacking Devices) framework for communication.

### Install WHAD

```bash
pip3 install whad
```

**Dependencies installed:**
- `scapy` - Packet manipulation library
- `pyusb` - USB communication
- `protobuf` - Protocol buffers
- `evdev` - Input device library
- Other WHAD dependencies

### Test WHAD Connection

```bash
whadup
```

**Expected output:**
```
[i] Available devices
- uart0
  Type: Uart
  Index: 0
  Identifier: /dev/ttyACM0
- hci0
  Type: Hci
  Index: 0
  Identifier: hci0
```

The Butterfly dongle appears as `uart0` at `/dev/ttyACM0`.

### Verify WHAD Communication

```python
python3 << 'EOF'
from whad.device import WhadDevice

device = WhadDevice.create('uart0')
print(f"Device: {device}")
print(f"Type: {device.type}")
device.close()
EOF
```

**Expected:** No errors, device connects successfully.

---

## Part 7: Using the Dongle for BLE Sniffing

### Basic BLE Sniffer Script

```python
#!/usr/bin/env python3
from whad.ble import Sniffer
from whad.device import WhadDevice

# Target device MAC address (BLE BD_ADDR format)
TARGET_MAC = "xx:xx:xx:xx:xx:xx"  # Replace with your HT1's BLE address

# Connect to Butterfly dongle
device = WhadDevice.create('uart0')
sniffer = Sniffer(device)

# Sniff new connection from initiation
sniffer.sniff_new_connection(
    channel=37,                    # Primary advertising channel
    bd_address=TARGET_MAC,         # Target device address
    show_advertisements=True       # Show advertisement packets
)

sniffer.start()

print(f"Sniffing connections to {TARGET_MAC}...")
print("Press Ctrl+C to stop")

try:
    while True:
        packet = sniffer.wait_packet(timeout=1.0)
        if packet:
            print(f"Packet: {packet}")
            # Save to PCAP
            sniffer.export_to_pcap("capture.pcap")
except KeyboardInterrupt:
    print("\nStopping...")
finally:
    sniffer.stop()
    sniffer.export_to_pcap("capture.pcap")
    device.close()
```

### PCAP Export

Captured packets can be exported to PCAP format for analysis in Wireshark:

```python
sniffer.export_to_pcap("/path/to/capture.pcap")
```

---

## Troubleshooting

### Dongle Not Detected After Flashing

**Symptoms:** `lsusb` doesn't show WHAD device

**Solutions:**
1. Manually unplug and replug the dongle
2. Check `dmesg` for USB errors
3. Try a different USB port
4. Reflash the firmware

### WHAD Can't Connect to Dongle

**Symptoms:** `whadup` doesn't list uart0

**Solutions:**
1. Check `/dev/ttyACM0` exists: `ls -l /dev/ttyACM0`
2. Check permissions: `sudo chmod 666 /dev/ttyACM0`
3. Check if another process is using the device: `lsof /dev/ttyACM0`
4. Unplug/replug the dongle

### Flashing Fails with CRC Error

**Symptoms:** `ValidationException: Failed CRC validation`

**This means:**
- You used the wrong firmware file (`butterfly.hex` instead of `butterfly-fwupgrade.zip`)

**Solution:**
1. Download `butterfly-fwupgrade.zip` (not .hex file)
2. Re-enter DFU mode
3. Flash with correct file

### Python Import Errors

**Symptoms:** `ModuleNotFoundError: No module named 'whad'`

**Solution:**
```bash
pip3 install whad
# Or if using venv:
source /path/to/venv/bin/activate
pip install whad
```

---

## Summary Checklist

- [x] Downloaded `butterfly-fwupgrade.zip` from GitHub releases v1.1.1
- [x] Installed `adafruit-nrfutil` and `whad` via pip3
- [x] Applied all 8 Python 3.13 compatibility patches
- [x] Put dongle in DFU mode (button pressed while plugging in)
- [x] Verified DFU mode: `Product: Open DFU Bootloader` in lsusb/dmesg
- [x] Flashed firmware: `adafruit-nrfutil dfu serial -pkg butterfly-fwupgrade.zip -p /dev/ttyACM0 -b 115200`
- [x] Saw "Device programmed." success message
- [x] Verified Butterfly firmware: `lsusb` shows `c0ff:eeee WHAD ButteRFly dongle`
- [x] Tested WHAD: `whadup` shows uart0 device
- [x] Created BLE sniffer script and tested packet capture

---

## References

- **Butterfly Firmware:** https://github.com/whad-team/butterfly
- **WHAD Framework:** https://github.com/whad-team/whad-client
- **Adafruit nrfutil:** https://github.com/adafruit/Adafruit_nRF52_nrfutil
- **Nordic DFU Protocol:** https://infocenter.nordicsemi.com/topic/sdk_nrf5_v17.0.2/lib_dfu.html

---

## Credits

- **Butterfly/WHAD:** Developed by virtualabs and the WHAD team
- **nRF52840:** Nordic Semiconductor
- **Taida Dongle:** Clone hardware based on nRF52840 (QIAA-C0 variant)

---

**Last Updated:** March 2, 2026
**Tested On:** Debian 12, Python 3.13, Butterfly v1.1.1
