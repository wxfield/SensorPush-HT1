# Android HCI Snoop Logging - Complete Guide

## Overview

HCI (Host Controller Interface) snoop logging is the **ONLY** way to capture Bluetooth traffic from bonded BLE devices like the SensorPush HT1.

## Why HCI Snoop is Necessary

### The Problem with External Sniffers

External BLE sniffers (nRF52840, Ubertooth, etc.) **cannot** capture:
- Bonded device reconnections
- Directed BLE advertisements
- Encrypted link-layer traffic
- GATT operations on bonded connections

### How HCI Snoop Works

HCI snoop logging runs **on the paired device** (Android/iPhone) and captures:
- All Bluetooth communication at the HCI layer
- Decrypted GATT read/write operations
- Full protocol stack communication
- Every packet sent/received by the Bluetooth controller

**Analogy:** External sniffers are like trying to eavesdrop from outside a building. HCI snoop is like having a recording device inside the room.

## Android HCI Snoop Setup

### Requirements

- Android phone (any version 4.4+)
- USB cable (data transfer, not charge-only)
- ADB installed on computer
- SensorPush app installed

### Recommended Hardware

**For this project: Samsung Galaxy S6**
- Android 5.0-7.0
- BLE 4.2
- Cost: ~$49
- Perfect for HCI snoop capture

### Step 1: Enable Developer Options

1. Go to **Settings → About phone**
2. Tap **Build number** 7 times
3. "You are now a developer!" message appears
4. Developer options now available in Settings

### Step 2: Enable USB Debugging

1. Go to **Settings → Developer options**
2. Enable **USB debugging**
3. Connect phone to computer via USB
4. Accept "Allow USB debugging" popup on phone

### Step 3: Verify ADB Connection

```bash
# Check ADB detects phone
adb devices

# Expected output:
# List of devices attached
# A1B2C3D4E5F6  device
```

If phone not detected:
```bash
# Kill and restart ADB server
adb kill-server
adb start-server
adb devices
```

### Step 4: Enable HCI Snoop Logging

**Method 1: Via GUI**
1. Go to **Settings → Developer options**
2. Scroll down to **Bluetooth HCI snoop log**
3. Toggle **ON**
4. Reboot phone (may not be required on all devices)

**Method 2: Via ADB**
```bash
# Enable HCI snoop logging
adb shell settings put secure bluetooth_hci_log 1

# Restart Bluetooth to activate
adb shell svc bluetooth disable
sleep 2
adb shell svc bluetooth enable
```

### Step 5: Install SensorPush App

```bash
# Option 1: Download from Play Store manually
# Option 2: Use ADB to install APK

# If you have the APK file:
adb install SensorPush.apk
```

### Step 6: Pair with HT1

1. Open SensorPush app
2. Add new HT1 device
3. Follow pairing process
4. Verify HT1 appears in app

### Step 7: Capture HCI Log

```bash
# Check HCI log location (varies by Android version)
# Android 9+:
adb shell ls -la /sdcard/Android/data/com.android.bluetooth/files/

# Android 4.4-8.1:
adb shell ls -la /sdcard/btsnoop_hci.log

# Pull the log file
adb pull /sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log ./

# Or for older Android:
adb pull /sdcard/btsnoop_hci.log ./
```

### Step 8: Automated Capture Script

Save this as `capture_ht1_hci.sh`:

```bash
#!/bin/bash
# Automated HCI snoop capture for SensorPush HT1

set -e

PACKAGE="com.sensorpush.connect"
LOG_PATH_NEW="/sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log"
LOG_PATH_OLD="/sdcard/btsnoop_hci.log"
OUTPUT_FILE="ht1_capture_$(date +%Y%m%d_%H%M%S).log"

echo "SensorPush HT1 HCI Capture Script"
echo "=================================="

# Check ADB connection
if ! adb devices | grep -q "device$"; then
    echo "ERROR: No Android device connected"
    exit 1
fi

echo "[✓] Android device connected"

# Enable HCI snoop
echo "[*] Enabling HCI snoop logging..."
adb shell settings put secure bluetooth_hci_log 1

# Restart Bluetooth
echo "[*] Restarting Bluetooth..."
adb shell svc bluetooth disable
sleep 2
adb shell svc bluetooth enable
sleep 3

echo "[*] HCI snoop logging active"
echo ""

# Launch SensorPush app
echo "[*] Launching SensorPush app..."
adb shell am start -n "$PACKAGE/.MainActivity"
sleep 2

echo ""
echo "=================================="
echo ">>> NOW CONNECT TO HT1 IN THE APP"
echo ">>> Press ENTER when done"
echo "=================================="
read -r

# Pull HCI log
echo ""
echo "[*] Pulling HCI snoop log..."
if adb shell ls "$LOG_PATH_NEW" 2>/dev/null; then
    adb pull "$LOG_PATH_NEW" "$OUTPUT_FILE"
elif adb shell ls "$LOG_PATH_OLD" 2>/dev/null; then
    adb pull "$LOG_PATH_OLD" "$OUTPUT_FILE"
else
    echo "ERROR: Could not find HCI log file"
    exit 1
fi

echo "[✓] Captured to: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "  1. Open in Wireshark: wireshark $OUTPUT_FILE"
echo "  2. Filter for ATT protocol: att"
echo "  3. Look for GATT read/write operations"
echo "  4. Find characteristic reads with sensor data"
```

## Analyzing the HCI Log

### Open in Wireshark

```bash
# Install Wireshark
# macOS: brew install --cask wireshark
# Debian: sudo apt install wireshark

# Open the log
wireshark ht1_capture_*.log
```

### Find HT1 Communication

**Filter for Bluetooth Low Energy:**
```
btle
```

**Filter for ATT protocol (GATT operations):**
```
att
```

**Find device by name:**
```
bluetooth.device_name contains "HT1"
```

### Identify GATT Characteristics

**Look for "Read By Type Request" (characteristic discovery):**
1. Find packet with "Read By Type Request"
2. Response lists characteristics and their UUIDs
3. Note UUIDs (e.g., `ef09000a-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

**Look for "Read Response" (sensor data):**
1. Find "Read Request" packets
2. Corresponding "Read Response" contains raw data
3. Note the hex bytes in the response

### Correlate with App Readings

**Critical step:**
1. Note temperature/humidity shown in SensorPush app
2. Find corresponding GATT "Read Response" in Wireshark
3. Compare raw bytes with displayed values
4. Reverse engineer the formula

**Example:**
- App shows: 72.4°F, 45.2% RH
- GATT response: `01 00 d4 02 c4 01 ...`
- Try: `int.from_bytes(bytes[2:4], 'little') / 10.0 = 72.4`
- Verify: If formula works, repeat with more readings

### Export Data for Analysis

**Export as JSON:**
```
File → Export Packet Dissections → As JSON
```

**Export specific packets:**
```bash
# Use tshark (command-line Wireshark)
tshark -r ht1_capture.log -Y "att.opcode == 0x0b" -T json > read_responses.json
# 0x0b = ATT Read Response opcode
```

## Automation with ADB

### Launch App and Trigger Connection

```bash
# Start SensorPush app
adb shell am start -n com.sensorpush.connect/.MainActivity

# Wait for app to load
sleep 3

# Simulate tap on "Connect" button (coordinates need to be found via UI inspector)
adb shell input tap 540 1200

# Wait for connection
sleep 5

# Trigger refresh (swipe down gesture)
adb shell input swipe 540 300 540 800 500
```

### Find UI Coordinates

**Method 1: UI Automator Viewer (Android SDK)**
```bash
# Dump UI hierarchy
adb shell uiautomator dump
adb pull /sdcard/window_dump.xml

# Open in UI Automator Viewer (part of Android SDK)
# Shows clickable elements and their coordinates
```

**Method 2: Screenshot + Manual Measurement**
```bash
# Take screenshot
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png

# Open in image editor, note button coordinates
```

### Full Automated Capture

```python
#!/usr/bin/env python3
"""
Fully automated HCI snoop capture for SensorPush HT1
"""
import subprocess
import time
from datetime import datetime

def adb(cmd):
    """Run ADB command"""
    result = subprocess.run(f"adb {cmd}", shell=True, capture_output=True, text=True)
    return result.stdout

def main():
    print("Automated HT1 HCI Capture")
    print("=" * 40)

    # Enable HCI snoop
    print("[*] Enabling HCI snoop...")
    adb("shell settings put secure bluetooth_hci_log 1")

    # Restart Bluetooth
    print("[*] Restarting Bluetooth...")
    adb("shell svc bluetooth disable")
    time.sleep(2)
    adb("shell svc bluetooth enable")
    time.sleep(3)

    # Launch app
    print("[*] Launching SensorPush...")
    adb("shell am start -n com.sensorpush.connect/.MainActivity")
    time.sleep(3)

    # Tap connect (example coordinates, adjust for your device)
    print("[*] Tapping Connect button...")
    adb("shell input tap 540 1200")
    time.sleep(5)

    # Trigger refresh
    print("[*] Refreshing data...")
    adb("shell input swipe 540 300 540 800 500")
    time.sleep(3)

    # Pull log
    print("[*] Pulling HCI log...")
    output_file = f"ht1_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    log_path = "/sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log"
    adb(f"pull {log_path} {output_file}")

    print(f"[✓] Captured to: {output_file}")
    print(f"\nAnalyze with: wireshark {output_file}")

if __name__ == "__main__":
    main()
```

## Troubleshooting

### USB Debugging Not Working

**Problem:** "Unauthorized" or "no permissions"

**Fix:**
1. Unplug and replug USB cable
2. Accept "Allow USB debugging" on phone
3. Check "Always allow from this computer"

### HCI Log File Not Found

**Problem:** Cannot find btsnoop_hci.log

**Check Android version:**
```bash
adb shell getprop ro.build.version.release
```

**Log locations by version:**
- Android 4.4-8.1: `/sdcard/btsnoop_hci.log`
- Android 9+: `/sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log`
- Some devices: `/data/log/bt/btsnoop_hci.log` (requires root)

### HCI Log is Empty

**Problem:** Log file exists but is 0 bytes or very small

**Causes:**
1. HCI snoop not actually enabled (reboot phone)
2. Bluetooth not restarted after enabling
3. No Bluetooth activity occurred
4. Log file permissions issue

**Fix:**
```bash
# Clear old log
adb shell rm /sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log

# Re-enable HCI snoop
adb shell settings put secure bluetooth_hci_log 1

# Reboot phone
adb reboot

# Recapture
```

### App Automation Fails

**Problem:** Tap coordinates don't work

**Cause:** Screen resolution/density differs

**Fix:**
```bash
# Get screen density
adb shell wm size
# Output: Physical size: 1440x2560

# Adjust tap coordinates proportionally
# If UI Automator shows coords for 1080x1920, scale by ratio
```

## iOS Alternative (More Complex)

### Requirements
- iPhone/iPad
- macOS with Xcode installed
- USB cable

### Process
1. Connect iPhone to Mac
2. Open Xcode → Window → Devices and Simulators
3. Select your iPhone
4. Click "⚙️" under "Installed Apps"
5. Select "Bluetooth Packet Capture"
6. Start recording
7. Connect to HT1 on iPhone
8. Stop recording
9. Save .btsnoop file
10. Open in Wireshark

**Downsides:**
- Requires Mac + Xcode (large download)
- More manual steps
- Cannot automate easily
- Harder to script

**Conclusion:** Android with ADB is far superior for automation

## Next Steps After Capture

1. **Analyze GATT services/characteristics**
2. **Identify sensor data format**
3. **Reverse engineer decode formulas**
4. **Validate with multiple readings**
5. **Implement Python BLE client**
6. **Create MQTT bridge**
7. **Integrate with Home Assistant**

## Resources

- [Android HCI Logging Documentation](https://source.android.com/devices/bluetooth/verifying_debugging)
- [Wireshark BLE Analysis](https://wiki.wireshark.org/Bluetooth)
- [ADB Documentation](https://developer.android.com/tools/adb)
- [GATT Specification](https://www.bluetooth.com/specifications/specs/core-specification/)

---

**This is the ONLY viable approach for capturing bonded BLE device traffic.**
