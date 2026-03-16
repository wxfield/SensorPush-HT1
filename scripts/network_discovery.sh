#!/bin/bash
# Network Device Discovery - Before/After Comparison
# Usage: Boot your device after the first scan, this finds new devices

NETWORK="192.168.0.0/24"  # Change to your network
BEFORE_FILE="/tmp/nmap_before.txt"
AFTER_FILE="/tmp/nmap_after.txt"

echo "=========================================="
echo "Network Device Discovery Tool"
echo "=========================================="
echo "Network: $NETWORK"
echo ""

# Scan before
echo "[*] Scanning network (BEFORE)..."
sudo nmap -sn "$NETWORK" -oG - | grep "Up" | sed 's/Host: //g' | sed 's/ ()//g' | awk '{print $1, $2}' | sort > "$BEFORE_FILE"
BEFORE_COUNT=$(wc -l < "$BEFORE_FILE")
echo "    Found $BEFORE_COUNT devices"
echo ""

# Wait for user
echo "=========================================="
echo ">>> Boot your device NOW, then press ENTER"
echo "=========================================="
read -r

# Scan after
echo ""
echo "[*] Scanning network (AFTER)..."
sudo nmap -sn "$NETWORK" -oG - | grep "Up" | sed 's/Host: //g' | sed 's/ ()//g' | awk '{print $1, $2}' | sort > "$AFTER_FILE"
AFTER_COUNT=$(wc -l < "$AFTER_FILE")
echo "    Found $AFTER_COUNT devices"
echo ""

# Find differences
echo "=========================================="
echo "NEW DEVICES:"
echo "=========================================="

comm -13 "$BEFORE_FILE" "$AFTER_FILE" | while IFS=' ' read -r IP HOSTNAME; do
    # Clean up hostname (remove parentheses)
    HOSTNAME=$(echo "$HOSTNAME" | tr -d '()')

    echo ""
    echo "  IP:       $IP"

    if [ -n "$HOSTNAME" ] && [ "$HOSTNAME" != "Status:" ]; then
        echo "  Hostname: $HOSTNAME"
    else
        # Try reverse DNS lookup
        HOST_LOOKUP=$(host "$IP" 2>/dev/null | grep "pointer" | awk '{print $NF}' | sed 's/\.$//')
        if [ -n "$HOST_LOOKUP" ]; then
            echo "  Hostname: $HOST_LOOKUP"
        else
            echo "  Hostname: (none)"
        fi
    fi

    # Get MAC address
    MAC=$(arp -n "$IP" 2>/dev/null | grep "$IP" | awk '{print $3}')
    if [ -n "$MAC" ] && [ "$MAC" != "(incomplete)" ]; then
        echo "  MAC:      $MAC"
    fi

    # Check SSH
    if timeout 1 bash -c "echo > /dev/tcp/$IP/22" 2>/dev/null; then
        echo "  SSH:      ✓ Open"
    fi

    echo "  --------"
done

if [ -z "$(comm -13 "$BEFORE_FILE" "$AFTER_FILE")" ]; then
    echo "  (none)"
fi

echo ""
echo "=========================================="
echo "DISAPPEARED DEVICES:"
echo "=========================================="

GONE=$(comm -23 "$BEFORE_FILE" "$AFTER_FILE")
if [ -z "$GONE" ]; then
    echo "  (none)"
else
    echo "$GONE" | while read -r IP HOST; do
        HOST=$(echo "$HOST" | tr -d '()')
        echo "  $IP  ${HOST:-unknown}"
    done
fi

echo ""
echo "=========================================="
