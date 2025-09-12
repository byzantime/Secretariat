#!/bin/bash
set -e

# Setup VPN if config provided
if [ ! -z "$WIREGUARD_CONF" ]; then
    echo "WireGuard config found, setting up VPN..."
    mkdir -p /etc/wireguard
    echo "$WIREGUARD_CONF" > /etc/wireguard/wg0.conf
    chmod 600 /etc/wireguard/wg0.conf
    wg-quick up wg0
    echo "VPN setup complete"
fi

# Start app
echo "Starting application..."
exec hypercorn main:app --bind 0.0.0.0:8080
