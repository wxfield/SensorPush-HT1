// Frida GATT capture v3 - robust, no ambiguous overloads, all try/catch

Java.perform(function() {

    function toHex(bytes) {
        if (!bytes) return 'null';
        var hex = '';
        for (var i = 0; i < bytes.length; i++) {
            hex += ('0' + (bytes[i] & 0xFF).toString(16)).slice(-2);
        }
        return hex;
    }

    var BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');
    var BluetoothDevice = Java.use('android.bluetooth.BluetoothDevice');

    // writeCharacteristic
    try {
        BluetoothGatt.writeCharacteristic.overload(
            'android.bluetooth.BluetoothGattCharacteristic'
        ).implementation = function(char) {
            console.log('[WRITE] uuid=' + char.getUuid() + ' data=' + toHex(char.getValue()));
            return this.writeCharacteristic(char);
        };
        console.log('[*] hooked writeCharacteristic');
    } catch(e) { console.log('[!] writeCharacteristic: ' + e); }

    // readCharacteristic
    try {
        BluetoothGatt.readCharacteristic.overload(
            'android.bluetooth.BluetoothGattCharacteristic'
        ).implementation = function(char) {
            console.log('[READ REQ] uuid=' + char.getUuid());
            return this.readCharacteristic(char);
        };
        console.log('[*] hooked readCharacteristic');
    } catch(e) { console.log('[!] readCharacteristic: ' + e); }

    // setCharacteristicNotification
    try {
        BluetoothGatt.setCharacteristicNotification.overload(
            'android.bluetooth.BluetoothGattCharacteristic', 'boolean'
        ).implementation = function(char, enable) {
            console.log('[NOTIFY EN] uuid=' + char.getUuid() + ' enable=' + enable);
            return this.setCharacteristicNotification(char, enable);
        };
        console.log('[*] hooked setCharacteristicNotification');
    } catch(e) { console.log('[!] setCharacteristicNotification: ' + e); }

    // writeDescriptor
    try {
        BluetoothGatt.writeDescriptor.overload(
            'android.bluetooth.BluetoothGattDescriptor'
        ).implementation = function(desc) {
            console.log('[WRITE DESC] char=' + desc.getCharacteristic().getUuid() +
                        ' desc=' + desc.getUuid() + ' data=' + toHex(desc.getValue()));
            return this.writeDescriptor(desc);
        };
        console.log('[*] hooked writeDescriptor');
    } catch(e) { console.log('[!] writeDescriptor: ' + e); }

    // Hook connectGatt to intercept callback object when new connection made
    function hookCallback(cb) {
        var clsName = cb.getClass().getName();
        try {
            var Cls = Java.use(clsName);

            try {
                Cls.onCharacteristicRead.overload(
                    'android.bluetooth.BluetoothGatt',
                    'android.bluetooth.BluetoothGattCharacteristic',
                    'int'
                ).implementation = function(gatt, char, status) {
                    console.log('[READ RSP] uuid=' + char.getUuid() + ' status=' + status + ' data=' + toHex(char.getValue()));
                    return this.onCharacteristicRead(gatt, char, status);
                };
            } catch(e) {}

            try {
                Cls.onCharacteristicChanged.overload(
                    'android.bluetooth.BluetoothGatt',
                    'android.bluetooth.BluetoothGattCharacteristic'
                ).implementation = function(gatt, char) {
                    console.log('[NOTIFY DATA] uuid=' + char.getUuid() + ' data=' + toHex(char.getValue()));
                    return this.onCharacteristicChanged(gatt, char);
                };
            } catch(e) {}

            try {
                Cls.onCharacteristicWrite.overload(
                    'android.bluetooth.BluetoothGatt',
                    'android.bluetooth.BluetoothGattCharacteristic',
                    'int'
                ).implementation = function(gatt, char, status) {
                    console.log('[WRITE CONF] uuid=' + char.getUuid() + ' status=' + status);
                    return this.onCharacteristicWrite(gatt, char, status);
                };
            } catch(e) {}

            try {
                Cls.onConnectionStateChange.overload(
                    'android.bluetooth.BluetoothGatt', 'int', 'int'
                ).implementation = function(gatt, status, newState) {
                    console.log('[CONN STATE] device=' + gatt.getDevice().getAddress() +
                                ' status=' + status + ' newState=' + newState);
                    return this.onConnectionStateChange(gatt, status, newState);
                };
            } catch(e) {}

            try {
                Cls.onServicesDiscovered.overload(
                    'android.bluetooth.BluetoothGatt', 'int'
                ).implementation = function(gatt, status) {
                    console.log('[SERVICES] status=' + status);
                    var it = gatt.getServices().iterator();
                    while (it.hasNext()) {
                        var svc = it.next();
                        console.log('  SVC=' + svc.getUuid());
                        var ci = svc.getCharacteristics().iterator();
                        while (ci.hasNext()) {
                            var c = ci.next();
                            console.log('    CHAR=' + c.getUuid() + ' props=' + c.getProperties());
                        }
                    }
                    return this.onServicesDiscovered(gatt, status);
                };
            } catch(e) {}

            console.log('[*] hooked callback class: ' + clsName);
        } catch(e) {
            console.log('[!] hookCallback failed for ' + clsName + ': ' + e);
        }
    }

    // Hook connectGatt (2-arg transport overload - Android 6+)
    try {
        BluetoothDevice.connectGatt.overload(
            'android.content.Context', 'boolean',
            'android.bluetooth.BluetoothGattCallback', 'int'
        ).implementation = function(ctx, auto, cb, transport) {
            console.log('[connectGatt] device=' + this.getAddress() + ' transport=' + transport);
            hookCallback(cb);
            return this.connectGatt(ctx, auto, cb, transport);
        };
        console.log('[*] hooked connectGatt(4-arg)');
    } catch(e) { console.log('[!] connectGatt 4-arg: ' + e); }

    // Hook connectGatt (3-arg legacy)
    try {
        BluetoothDevice.connectGatt.overload(
            'android.content.Context', 'boolean',
            'android.bluetooth.BluetoothGattCallback'
        ).implementation = function(ctx, auto, cb) {
            console.log('[connectGatt] device=' + this.getAddress());
            hookCallback(cb);
            return this.connectGatt(ctx, auto, cb);
        };
        console.log('[*] hooked connectGatt(3-arg)');
    } catch(e) { console.log('[!] connectGatt 3-arg: ' + e); }

    // Scan for any already-live callback instances
    try {
        Java.choose('android.bluetooth.BluetoothGattCallback', {
            onMatch: function(inst) {
                console.log('[*] Found live callback: ' + inst.getClass().getName());
                hookCallback(inst);
            },
            onComplete: function() { console.log('[*] Live callback scan done'); }
        });
    } catch(e) { console.log('[!] Java.choose: ' + e); }

    console.log('[*] GATT v3 hooks installed - waiting for BLE activity...');
});
