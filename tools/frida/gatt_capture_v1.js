// Frida script to capture GATT traffic from SensorPush HT1 history sync
// Hooks Android BluetoothGatt API to log all characteristic reads/writes/notifications

Java.perform(function() {
    var BluetoothGattCallback = Java.use('android.bluetooth.BluetoothGattCallback');
    var BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');
    var BluetoothGattCharacteristic = Java.use('android.bluetooth.BluetoothGattCharacteristic');

    // Helper to convert byte array to hex string
    function toHex(bytes) {
        if (!bytes) return 'null';
        var hex = '';
        for (var i = 0; i < bytes.length; i++) {
            var b = bytes[i] & 0xFF;
            hex += ('0' + b.toString(16)).slice(-2);
        }
        return hex;
    }

    // Hook writeCharacteristic
    BluetoothGatt.writeCharacteristic.overload(
        'android.bluetooth.BluetoothGattCharacteristic'
    ).implementation = function(char) {
        var uuid = char.getUuid().toString();
        var value = char.getValue();
        console.log('[GATT WRITE] uuid=' + uuid + ' data=' + toHex(value));
        return this.writeCharacteristic(char);
    };

    // Hook readCharacteristic
    BluetoothGatt.readCharacteristic.implementation = function(char) {
        var uuid = char.getUuid().toString();
        console.log('[GATT READ REQUEST] uuid=' + uuid);
        return this.readCharacteristic(char);
    };

    // Hook setCharacteristicNotification
    BluetoothGatt.setCharacteristicNotification.implementation = function(char, enable) {
        var uuid = char.getUuid().toString();
        console.log('[GATT NOTIFY] uuid=' + uuid + ' enable=' + enable);
        return this.setCharacteristicNotification(char, enable);
    };

    // Hook writeDescriptor
    BluetoothGatt.writeDescriptor.implementation = function(desc) {
        var uuid = desc.getUuid().toString();
        var charUuid = desc.getCharacteristic().getUuid().toString();
        var value = desc.getValue();
        console.log('[GATT WRITE DESCRIPTOR] char=' + charUuid + ' desc=' + uuid + ' data=' + toHex(value));
        return this.writeDescriptor(desc);
    };

    // Hook onCharacteristicRead response
    var callbacks = Java.use('android.bluetooth.BluetoothGattCallback');
    callbacks.onCharacteristicRead.implementation = function(gatt, char, status) {
        var uuid = char.getUuid().toString();
        var value = char.getValue();
        console.log('[GATT READ RESPONSE] uuid=' + uuid + ' status=' + status + ' data=' + toHex(value));
        return this.onCharacteristicRead(gatt, char, status);
    };

    // Hook onCharacteristicChanged (notifications)
    callbacks.onCharacteristicChanged.implementation = function(gatt, char) {
        var uuid = char.getUuid().toString();
        var value = char.getValue();
        console.log('[GATT NOTIFY DATA] uuid=' + uuid + ' data=' + toHex(value));
        return this.onCharacteristicChanged(gatt, char);
    };

    // Hook onCharacteristicWrite confirmation
    callbacks.onCharacteristicWrite.implementation = function(gatt, char, status) {
        var uuid = char.getUuid().toString();
        console.log('[GATT WRITE CONFIRM] uuid=' + uuid + ' status=' + status);
        return this.onCharacteristicWrite(gatt, char, status);
    };

    // Hook connection state changes
    callbacks.onConnectionStateChange.implementation = function(gatt, status, newState) {
        var device = gatt.getDevice();
        var addr = device.getAddress();
        console.log('[GATT CONNECTION] device=' + addr + ' status=' + status + ' newState=' + newState);
        return this.onConnectionStateChange(gatt, status, newState);
    };

    // Hook service discovery
    callbacks.onServicesDiscovered.implementation = function(gatt, status) {
        console.log('[GATT SERVICES DISCOVERED] status=' + status);
        var services = gatt.getServices();
        var iter = services.iterator();
        while (iter.hasNext()) {
            var svc = iter.next();
            console.log('  SERVICE: ' + svc.getUuid().toString());
            var chars = svc.getCharacteristics();
            var citer = chars.iterator();
            while (citer.hasNext()) {
                var c = citer.next();
                console.log('    CHAR: ' + c.getUuid().toString() + ' props=' + c.getProperties());
            }
        }
        return this.onServicesDiscovered(gatt, status);
    };

    console.log('[*] GATT hooks installed - waiting for SensorPush BLE activity...');
});
