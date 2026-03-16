// Frida GATT capture v2 - safer hooking approach
// Hooks BluetoothGatt concrete methods + uses Java.choose for callback instances

Java.perform(function() {
    var BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');

    function toHex(bytes) {
        if (!bytes) return 'null';
        var hex = '';
        for (var i = 0; i < bytes.length; i++) {
            hex += ('0' + (bytes[i] & 0xFF).toString(16)).slice(-2);
        }
        return hex;
    }

    // --- Hook outgoing GATT operations (BluetoothGatt is concrete) ---

    BluetoothGatt.writeCharacteristic.overload(
        'android.bluetooth.BluetoothGattCharacteristic'
    ).implementation = function(char) {
        console.log('[GATT WRITE] uuid=' + char.getUuid() + ' data=' + toHex(char.getValue()));
        return this.writeCharacteristic(char);
    };

    BluetoothGatt.readCharacteristic.implementation = function(char) {
        console.log('[GATT READ REQUEST] uuid=' + char.getUuid());
        return this.readCharacteristic(char);
    };

    BluetoothGatt.setCharacteristicNotification.implementation = function(char, enable) {
        console.log('[GATT NOTIFY ENABLE] uuid=' + char.getUuid() + ' enable=' + enable);
        return this.setCharacteristicNotification(char, enable);
    };

    BluetoothGatt.writeDescriptor.implementation = function(desc) {
        console.log('[GATT WRITE DESC] char=' + desc.getCharacteristic().getUuid() + ' desc=' + desc.getUuid() + ' data=' + toHex(desc.getValue()));
        return this.writeDescriptor(desc);
    };

    BluetoothGatt.connect.implementation = function() {
        console.log('[GATT CONNECT] device=' + this.getDevice().getAddress());
        return this.connect();
    };

    BluetoothGatt.disconnect.implementation = function() {
        console.log('[GATT DISCONNECT]');
        return this.disconnect();
    };

    // --- Hook incoming callbacks via Java.choose on live instances ---
    // We enumerate BluetoothGattCallback subclass instances and hook them

    function hookCallbackInstance(inst) {
        var cls = inst.getClass();
        var clsName = cls.getName();

        try {
            var ConcreteClass = Java.use(clsName);

            // onCharacteristicRead
            try {
                ConcreteClass.onCharacteristicRead.overload(
                    'android.bluetooth.BluetoothGatt',
                    'android.bluetooth.BluetoothGattCharacteristic',
                    'int'
                ).implementation = function(gatt, char, status) {
                    console.log('[GATT READ RSP] uuid=' + char.getUuid() + ' status=' + status + ' data=' + toHex(char.getValue()));
                    return this.onCharacteristicRead(gatt, char, status);
                };
            } catch(e) {}

            // onCharacteristicChanged
            try {
                ConcreteClass.onCharacteristicChanged.overload(
                    'android.bluetooth.BluetoothGatt',
                    'android.bluetooth.BluetoothGattCharacteristic'
                ).implementation = function(gatt, char) {
                    console.log('[GATT NOTIFY DATA] uuid=' + char.getUuid() + ' data=' + toHex(char.getValue()));
                    return this.onCharacteristicChanged(gatt, char);
                };
            } catch(e) {}

            // onCharacteristicWrite
            try {
                ConcreteClass.onCharacteristicWrite.implementation = function(gatt, char, status) {
                    console.log('[GATT WRITE CONF] uuid=' + char.getUuid() + ' status=' + status);
                    return this.onCharacteristicWrite(gatt, char, status);
                };
            } catch(e) {}

            // onConnectionStateChange
            try {
                ConcreteClass.onConnectionStateChange.implementation = function(gatt, status, newState) {
                    console.log('[GATT CONN STATE] device=' + gatt.getDevice().getAddress() + ' status=' + status + ' state=' + newState);
                    return this.onConnectionStateChange(gatt, status, newState);
                };
            } catch(e) {}

            // onServicesDiscovered
            try {
                ConcreteClass.onServicesDiscovered.implementation = function(gatt, status) {
                    console.log('[GATT SERVICES] status=' + status);
                    var svcs = gatt.getServices();
                    var it = svcs.iterator();
                    while (it.hasNext()) {
                        var svc = it.next();
                        console.log('  SVC: ' + svc.getUuid());
                        var ci = svc.getCharacteristics().iterator();
                        while (ci.hasNext()) {
                            var c = ci.next();
                            console.log('    CHAR: ' + c.getUuid() + ' props=' + c.getProperties());
                        }
                    }
                    return this.onServicesDiscovered(gatt, status);
                };
            } catch(e) {}

            console.log('[*] Hooked callback class: ' + clsName);
        } catch(e) {
            console.log('[!] Could not hook ' + clsName + ': ' + e);
        }
    }

    // Hook any already-existing callback instances
    Java.choose('android.bluetooth.BluetoothGattCallback', {
        onMatch: function(inst) { hookCallbackInstance(inst); },
        onComplete: function() { console.log('[*] Existing callback scan done'); }
    });

    // Also intercept connectGatt so we can hook new callbacks as they're created
    var BluetoothDevice = Java.use('android.bluetooth.BluetoothDevice');
    BluetoothDevice.connectGatt.overload(
        'android.content.Context', 'boolean', 'android.bluetooth.BluetoothGattCallback'
    ).implementation = function(ctx, auto, cb) {
        console.log('[BLE] connectGatt device=' + this.getAddress());
        hookCallbackInstance(cb);
        return this.connectGatt(ctx, auto, cb);
    };

    try {
        BluetoothDevice.connectGatt.overload(
            'android.content.Context', 'boolean', 'android.bluetooth.BluetoothGattCallback', 'int'
        ).implementation = function(ctx, auto, cb, transport) {
            console.log('[BLE] connectGatt device=' + this.getAddress() + ' transport=' + transport);
            hookCallbackInstance(cb);
            return this.connectGatt(ctx, auto, cb, transport);
        };
    } catch(e) {}

    console.log('[*] GATT hooks v2 installed');
});
