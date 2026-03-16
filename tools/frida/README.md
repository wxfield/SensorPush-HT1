# Frida GATT Capture Scripts — Research Artifacts

These scripts were written on 2026-03-12 to intercept the SensorPush app's BLE GATT
traffic on a rooted Lenovo Tab M8 (TB-8505F, Android 10). All three failed due to
DexProtector anti-tamper protection in the SensorPush APK.

They are preserved here as documentation of the approach taken and lessons learned.

## Versions

### gatt_capture_v1.js
First attempt. Hooks `BluetoothGattCallback` abstract methods directly.
**Failed:** Calling `return this.onCharacteristicRead(...)` on the abstract base
class crashes the JVM — the abstract method has no implementation to dispatch to.
App crashed to home screen on inject.

### gatt_capture_v2.js
Fixed the abstract-method crash. Uses `Java.choose` to find live callback instances,
hooks only concrete `BluetoothGatt` methods (not abstract base), and hooks
`BluetoothDevice.connectGatt` to intercept new connections.
**Failed:** `BluetoothGatt.connect.implementation` triggered overload ambiguity:
`"connect(): has more than one overload"` — crash at load time.

### gatt_capture_v3.js
All hooks wrapped in try/catch. Explicit `.overload(...)` signatures on every method
to avoid ambiguity. 3-arg and 4-arg `connectGatt` both covered. `Java.choose` for
existing callback instances.
**Failed:** DexProtector (`lib/arm64-v8a/libdexprotector.so`) detects the Frida
runtime at native library constructor level — before any Java hooks execute.
The app calls `exit()` immediately. No GATT data was ever captured.

### run_capture.py
Python script that bypasses the `frida-tools` CLI. The `frida-tools==12.5.0` CLI
(`frida-ps`, `frida` REPL) has a Python 3.14 incompatibility in `_is_java_available()`
that causes `frida.InvalidOperationError: script is destroyed` at startup.

This script uses the `frida` Python API directly:
```python
dev = frida.get_usb_device()
proc = find_sensorpush(dev)
session = dev.attach(proc.pid)
script = session.create_script(open('gatt_capture_v3.js').read())
```

Also used TCP transport for more reliable attachment:
```bash
adb forward tcp:27042 tcp:27042
# then in Python:
dev = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
```

## Setup That Was Required

```bash
# On the tablet (rooted Magisk, frida-server-16.5.9-android-arm64 at /data/local/tmp/frida-server-16)
adb shell su -c 'setenforce 0'
adb shell su -c '/data/local/tmp/frida-server-16 &'

# On Mac, TCP forward
adb forward tcp:27042 tcp:27042

# Python venv with matching versions
python3 -m venv /tmp/frida16-env
source /tmp/frida16-env/bin/activate
pip install frida==16.5.9 frida-tools==12.5.0
```

## Why frida-server 16.5.9 (Not Latest)

frida-server 17.x (current) crashes on Android 10 MT6761 with:
```
unable to load libart.so: ANDROID_DLEXT_USE_NAMESPACE is set but
extinfo->library_namespace is null
```
Version 16.5.9 works correctly on Android 10.

## Conclusion

DexProtector makes Frida-based GATT hooking impractical without significant
additional work (embedding Frida gadget in APK + re-signing + integrity bypass patch).

The HT1 GATT characteristics require no authentication. The protocol was ultimately
discovered by connecting directly from macOS using `bleak` — see `../../scripts/ht1_probe.py`.
