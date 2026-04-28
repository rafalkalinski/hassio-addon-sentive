#!/usr/bin/env bashio
set -e

CONFIG_PATH=/data/options.json
DATA_DIR=/data

# Ensure external DNS is available (HA Supervisor DNS may not resolve CF hostnames)
if ! grep -q "1.1.1.1" /etc/resolv.conf 2>/dev/null; then
    echo "nameserver 1.1.1.1" >> /etc/resolv.conf
fi

INVITE_CODE=$(bashio::config 'invite_code')
BOOTSTRAP_URL="https://bootstrap-dev.sentive.it"
API_URL="https://api-dev.sentive.it"

# Run registration if not yet registered
if [ ! -f "$DATA_DIR/registered" ]; then
    bashio::log.info "Running bootstrap registration..."
    rm -f "$DATA_DIR/registration-error.txt"
    if ! python3 /register.py \
        --invite-code "$INVITE_CODE" \
        --bootstrap-url "$BOOTSTRAP_URL" \
        --api-url "$API_URL" 2>"$DATA_DIR/registration-error.txt"; then
        bashio::log.error "Bootstrap registration failed: $(cat "$DATA_DIR/registration-error.txt")"
        exit 1
    fi
fi

# Start ingress UI server in background
python3 /addon_server.py &

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
