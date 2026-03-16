#!/usr/bin/env python3
import frida
import sys
import time

script_src = open('/tmp/gatt_capture.js').read()

def on_message(message, data):
    if message['type'] == 'send':
        print(message['payload'])
    elif message['type'] == 'error':
        print('[ERROR]', message['stack'])
    else:
        print(message)

def find_sensorpush(device):
    for proc in device.enumerate_processes():
        if 'SensorPush' in proc.name or 'sensor' in proc.name.lower() or 'thermometer' in proc.name.lower() or 'beacon' in proc.name.lower():
            return proc
    return None

def main():
    dev = frida.get_usb_device()
    print(f'[*] Connected to {dev.name}')

    proc = find_sensorpush(dev)
    if not proc:
        print('[!] SensorPush process not found')
        procs = [(p.pid, p.name) for p in dev.enumerate_processes() if p.name]
        print('[*] Running processes:', procs[:20])
        sys.exit(1)

    print(f'[*] Found target: {proc.name} (PID {proc.pid})')
    session = dev.attach(proc.pid)
    print(f'[*] Attached! Loading hooks...')

    script = session.create_script(script_src)
    script.on('message', on_message)
    script.load()

    print('[*] Hooks active. Trigger HT1 pairing/sync now...')
    print('[*] Press Ctrl+C to stop')

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print('\n[*] Stopping')
        session.detach()

if __name__ == '__main__':
    main()
