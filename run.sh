#!/usr/bin/with-contenv bashio
set -e

DATA_DIR=/data

# Resolve homeassistant IP before modifying DNS resolvers
HA_IP=$(python3 -c "import socket; print(socket.gethostbyname('homeassistant'))" 2>/dev/null || true)

# Ensure external DNS is first (HA Supervisor DNS returns empty answers for external hostnames)
if ! grep -q "1.1.1.1" /etc/resolv.conf 2>/dev/null; then
    { echo "nameserver 1.1.1.1"; cat /etc/resolv.conf 2>/dev/null; } | tee /etc/resolv.conf > /dev/null || true
fi

# Pin internal hostname so cloudflared can reach HA even after DNS change
# (1.1.1.1 returns NXDOMAIN for 'homeassistant' and does not fall back to Supervisor DNS)
if [ -n "$HA_IP" ] && ! grep -q "homeassistant" /etc/hosts 2>/dev/null; then
    echo "$HA_IP homeassistant" >> /etc/hosts
fi

INVITE_CODE=$(python3 -c "import json,sys; d=json.load(open('/data/options.json')); sys.stdout.write(d.get('invite_code','').strip())" 2>/dev/null || true)
BOOTSTRAP_URL="https://bootstrap-dev.sentive.it"
API_URL="https://api-dev.sentive.it"

# Start ingress UI server immediately — panel stays accessible even during registration
gunicorn --chdir / --bind 0.0.0.0:8099 --workers 2 --timeout 30 addon_server:app &

# Run registration if not yet registered
if [ ! -f "$DATA_DIR/registered" ]; then
    bashio::log.info "Running bootstrap registration..."
    rm -f "$DATA_DIR/registration-error.txt"
    if ! python3 /register.py \
        --invite-code "$INVITE_CODE" \
        --bootstrap-url "$BOOTSTRAP_URL" \
        --api-url "$API_URL" 2>"$DATA_DIR/registration-error.txt"; then
        bashio::log.error "Bootstrap registration failed: $(cat "$DATA_DIR/registration-error.txt")"
        bashio::log.info "Fix the invite code in add-on configuration and restart the add-on."
        # Keep addon alive via ingress server so HA does not restart in a crash loop
        wait
        exit 1
    fi
fi

# Ensure HA trusted_proxies is configured on every startup (self-healing, idempotent)
bashio::log.info "Ensuring HA trusted_proxies configuration..."
python3 -c "import sys; sys.path.insert(0, '/'); from register import _configure_ha_trusted_proxies; _configure_ha_trusted_proxies()" 2>&1 || true

# Refresh HA token in OPS on every startup (self-healing)
bashio::log.info "Refreshing HA token in OPS..."
INFO_FILE="$DATA_DIR/sentive-info.json"
if [ -f "$INFO_FILE" ]; then
    CLIENT_ID=$(python3 -c "import json; d=json.load(open('$INFO_FILE')); print(d.get('client_id',''))" 2>/dev/null || true)
    ADDON_JWT=$(python3 -c "import json; d=json.load(open('$INFO_FILE')); print(d.get('jwt',''))" 2>/dev/null || true)
    if [ -n "$CLIENT_ID" ] && [ -n "$ADDON_JWT" ]; then
        python3 -c "
import sys
sys.path.insert(0, '/')
from register import refresh_ha_token
refresh_ha_token('$CLIENT_ID', '$ADDON_JWT', '$API_URL')
" 2>&1 || true
    fi
fi

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
