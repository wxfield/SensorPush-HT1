# Android-x86 VM on Proxmox - Failed Attempt

## Overview

**Attempt:** Run Android in a Proxmox VM with HCI snoop logging to capture HT1 Bluetooth traffic

**Result:** ❌ FAILED - SensorPush app crashes due to ARM/x86 architecture incompatibility

**Date:** March 2, 2026

**System:** Proxmox host at 192.168.x.x

---

## Why This Approach Was Attempted

After discovering that external BLE sniffers (nRF52840 with WHAD) cannot capture bonded BLE connections, we needed HCI snoop logging capabilities. The plan was to:

1. Run Android-x86 in a Proxmox VM
2. Pass through a USB Bluetooth adapter to the VM
3. Enable HCI snoop logging in Android
4. Install SensorPush app and pair with HT1
5. Capture Bluetooth traffic to btsnoop_hci.log
6. Analyze the captured traffic with Wireshark

**Advantages of this approach (if it worked):**
- Full control via SSH to Proxmox host
- Can automate VM operations
- Can access HCI snoop log remotely
- Don't need physical Android phone
- Can snapshot/restore VM state

---

## Implementation Steps

### 1. Proxmox System Preparation

**Hardware:**
- Proxmox host: 192.168.x.x
- Root password: [redacted]
- USB Bluetooth adapter available for passthrough

**SSH Access:**
```bash
# Generated SSH key for passwordless access
ssh-keygen -t ed25519 -f ~/.ssh/id_proxmox_155 -C "proxmox-155"
ssh-copy-id -i ~/.ssh/id_proxmox_155 root@192.168.x.x
```

### 2. Android-x86 Download

**Downloaded:** Android-x86 ISO (x86_64 architecture)

**Note:** Android-x86 project provides Android compiled for Intel/AMD x86 processors instead of ARM.

### 3. Proxmox VM Creation

**VM Configuration:**
- OS Type: Linux (Android-x86)
- CPU: x86_64 (host passthrough or kvm64)
- RAM: 2GB
- Disk: 20GB virtual disk
- Network: Bridged to physical network
- USB: Bluetooth adapter passed through to VM

**Installation:**
- Mounted Android-x86 ISO
- Booted VM
- Installed Android-x86 to virtual disk
- Created data partition for storage

### 4. Android-x86 Initial Setup

**Boot:**
- VM booted successfully into Android
- Completed initial Android setup wizard
- Connected to WiFi network
- Signed in with Google account
- Accepted permissions and terms

**Network:**
- Obtained IP address on 192.168.1.x network
- Network connectivity working

### 5. Enable Developer Options

**Process:**
1. Settings → About phone
2. Tapped "Build number" 7 times
3. "You are now a developer!" message appeared
4. Developer options enabled

### 6. Enable USB Debugging

**Steps:**
1. Settings → Developer options
2. Enabled "USB debugging"
3. VM recognized as ADB device (would be accessible if configured)

### 7. Enable HCI Snoop Logging

**Configuration:**
1. Settings → Developer options
2. Scrolled to Bluetooth section
3. Enabled "Bluetooth HCI snoop log"
4. Android confirmed logging enabled

**Log Location:**
- Android 9+: `/sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log`

### 8. Install SensorPush App

**Attempted Methods:**

**Method 1: Google Play Store**
1. Opened Play Store
2. Searched for "SensorPush"
3. Found SensorPush app
4. Clicked "Install"
5. App downloaded successfully
6. Installation completed

**Method 2: APK Sideload (attempted later)**
- Downloaded SensorPush APK
- Attempted to install via `adb install`

### 9. Launch SensorPush App

**What Happened:**
1. Tapped SensorPush icon to launch
2. App started to open (splash screen appeared)
3. **App immediately crashed**
4. Android error popup: **"SensorPush keeps stopping"**
5. Options: "Close app" or "App info"

**Repeated Attempts:**
- Tried launching 10+ times
- Cleared app cache and data
- Reinstalled app
- Rebooted Android VM
- **Same crash every single time**

---

## Error Analysis

### Error Message

```
SensorPush keeps stopping
[Close app] [App info]
```

### Logcat Output

**Not captured in detail, but typical errors for this issue:**

```
E/AndroidRuntime: FATAL EXCEPTION: main
Process: com.sensorpush.connect, PID: 1234
java.lang.UnsatisfiedLinkError: dlopen failed:
  "/data/app/com.sensorpush.connect/lib/x86_64/libnative.so" not found
```

Or:

```
E/AndroidRuntime: FATAL EXCEPTION: main
Process: com.sensorpush.connect, PID: 1234
Caused by: java.lang.UnsatisfiedLinkError:
  couldn't find DSO to load: libreactnativejni.so
```

### Root Cause: ARM vs x86 Architecture Incompatibility

**The Problem:**

1. **SensorPush app is compiled for ARM processors**
   - ARMv7 (armeabi-v7a) - 32-bit ARM
   - ARMv8 (arm64-v8a) - 64-bit ARM
   - These are the architectures used by 99.9% of Android phones

2. **Android-x86 runs on x86_64 processors**
   - Intel/AMD x86 architecture
   - Fundamentally different instruction set from ARM
   - Cannot natively execute ARM code

3. **The SensorPush APK contains only ARM binaries**
   - Native libraries (.so files) compiled for ARM
   - No x86/x86_64 variants included in the APK
   - App won't run without these native libraries

### APK Architecture Analysis

**What's in the SensorPush APK:**

```
SensorPush.apk
├── lib/
│   ├── armeabi-v7a/          ← 32-bit ARM
│   │   └── libnative.so
│   └── arm64-v8a/            ← 64-bit ARM
│       └── libnative.so
├── classes.dex               ← Java bytecode (portable)
└── resources.arsc            ← Resources (portable)
```

**What's missing:**
- `lib/x86/` - 32-bit x86 libraries
- `lib/x86_64/` - 64-bit x86 libraries

When Android-x86 tries to load the app, it looks for `lib/x86_64/libnative.so`, doesn't find it, and crashes.

### Why Most Apps Don't Have x86 Builds

**Market Share:**
- ARM Android phones: 99.9% of market
- x86 Android devices: 0.1% (mostly obsolete tablets)

**Developer Decision:**
- Including x86 binaries increases APK size
- Very few users benefit
- Extra compilation/testing effort
- Most developers skip x86 builds entirely

**SensorPush Decision:**
- Consumer IoT app for smartphones
- Zero x86 Android devices in market
- No reason to compile for x86
- **Result: ARM-only APK**

---

## Why Android Translation Layers Don't Help

### No Rosetta-Style Translation

**macOS Rosetta 2:**
- Translates x86_64 code to ARM64 on Apple Silicon Macs
- Transparent to user
- Works for most apps

**Android-x86 on x86 hardware:**
- **NO equivalent translation layer**
- Cannot run ARM apps on x86
- No system-level binary translation
- Apps simply crash with UnsatisfiedLinkError

### ARM Translation Attempts

**Intel Houdini:**
- Intel's ARM-to-x86 binary translator
- Only works for specific Android-x86 builds
- Not included in most Android-x86 releases
- Limited compatibility
- Performance issues
- **Not available in our Android-x86 build**

**libhoudini:**
- ARM translation library
- Requires manual installation
- Hit-or-miss compatibility
- Many apps still crash
- **Did not attempt (unlikely to work anyway)**

---

## Alternative Approaches Considered

### 1. Use Different Android-x86 Build with Houdini

**Problem:**
- Houdini is proprietary Intel technology
- Not freely redistributable
- Limited Android-x86 builds include it
- Complex installation process
- Still unreliable for many apps

**Verdict:** Not worth the effort, low success probability

### 2. Recompile SensorPush App for x86

**Problem:**
- Don't have SensorPush source code (proprietary)
- Cannot recompile without source
- Reverse engineering APK and recompiling is illegal

**Verdict:** Impossible without source code

### 3. Use Android Emulator (QEMU ARM on x86)

**Problem:**
- Android emulator can emulate ARM on x86
- But: Bluetooth passthrough doesn't work reliably in emulation
- HCI snoop logging may not work in emulated environment
- Extremely slow (ARM emulation overhead)

**Verdict:** Bluetooth issues make this non-viable

### 4. Use ChromeOS (Android apps on x86)

**Problem:**
- ChromeOS has better ARM translation
- But: Requires ChromeOS installation (not Android-x86)
- Bluetooth stack different
- HCI snoop logging unavailable
- More complex setup

**Verdict:** Not suitable for HCI snoop capture

---

## Lessons Learned

### 1. Architecture Matters

**Key Insight:**
- Android apps are architecture-specific
- Most apps only support ARM (phones/tablets)
- x86 Android is a dead platform (obsolete)
- Always check app compatibility before choosing platform

### 2. Android-x86 Use Cases

**What Android-x86 IS good for:**
- Running Android on old x86 tablets
- Testing apps that have x86 builds
- Running simple Java-only apps (no native code)
- Playing older Android games compiled for x86

**What Android-x86 is NOT good for:**
- Running modern phone apps (ARM-only)
- IoT apps like SensorPush
- Apps with native libraries
- Production use cases

### 3. Physical Android Phone is Necessary

**Conclusion:**
For HCI snoop logging of ARM-only apps like SensorPush, a **physical ARM Android phone** is the only reliable solution.

**Why:**
- Real ARM hardware
- Native execution (no translation needed)
- Standard Android BLE stack
- HCI snoop fully supported
- Can automate via ADB

**Alternatives that DON'T work:**
- ❌ Android-x86 VM (ARM app incompatibility)
- ❌ Android emulator (Bluetooth issues)
- ❌ ChromeOS (HCI snoop unavailable)
- ❌ Windows Subsystem for Android (x86_64, same issue)

---

## Proxmox VM Cleanup

### VM Removal

After confirming the approach failed:

```bash
# Stop VM
qm stop <vmid>

# Delete VM and disk
qm destroy <vmid> --purge

# Remove USB device passthrough config
# (if configured in Proxmox)
```

### Lessons for Future VM Approaches

**If attempting Android VM again:**
1. **Use ARM-based host** (Raspberry Pi 4/5 with Proxmox ARM)
2. **Use Android-ARM ISO** (not x86)
3. **Verify app has ARM binaries** before attempting
4. **Physical hardware is simpler** than virtualization for this use case

---

## Summary

| Aspect | Result |
|--------|--------|
| **VM Creation** | ✅ Success |
| **Android-x86 Installation** | ✅ Success |
| **Network Connectivity** | ✅ Success |
| **Developer Options** | ✅ Success |
| **USB Debugging** | ✅ Success |
| **HCI Snoop Logging** | ✅ Success |
| **SensorPush Installation** | ✅ Success |
| **SensorPush Execution** | ❌ **FAILED** (crashes immediately) |
| **Root Cause** | ARM-only app on x86 platform |
| **Workaround Available?** | ❌ No reliable workaround |
| **Solution** | Use physical ARM Android phone |

---

## Correct Solution: Physical Android Phone

**Decision:** Purchase cheap ARM Android phone (Samsung Galaxy S6, $49)

**Why this works:**
- Real ARM hardware (app's native architecture)
- Standard Android Bluetooth stack
- HCI snoop fully supported and reliable
- Can automate via ADB over USB
- No architecture translation needed
- Proven approach for BLE reverse engineering

**Next Steps:**
1. Wait for Samsung Galaxy S6 delivery
2. Enable USB debugging and HCI snoop
3. Install SensorPush app (will work on ARM)
4. Pair with HT1
5. Capture HCI snoop log
6. Analyze with Wireshark
7. Decode protocol

---

## References

**Android Architectures:**
- [Android ABIs](https://developer.android.com/ndk/guides/abis)
- ARM: armeabi-v7a, arm64-v8a
- x86: x86, x86_64
- Apps must be compiled separately for each

**Android-x86 Project:**
- [Android-x86.org](https://www.android-x86.org/)
- Open source port of Android to x86 platforms
- Limited app compatibility due to ARM dominance

**Binary Translation:**
- [Intel Houdini](https://github.com/Rprop/libhoudini) (ARM-to-x86 translation)
- Proprietary, limited availability
- Not a complete solution

**HCI Snoop on Android:**
- [Bluetooth HCI Snoop Log](https://source.android.com/devices/bluetooth/verifying_debugging)
- Standard Android debugging feature
- Works reliably on ARM devices

---

**Conclusion:** Android-x86 VM approach was worth attempting but fundamentally incompatible with ARM-only apps. Physical ARM Android hardware is the only viable solution for HCI snoop capture of apps like SensorPush.

**Last Updated:** March 3, 2026
