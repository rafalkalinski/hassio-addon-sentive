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
if [ -n "$HA_IP" ] && ! grep -q "homeassistant" /etc/hosts 2>/dev/null; then
    echo "$HA_IP homeassistant" >> /etc/hosts
fi

# Start ingress UI server immediately — panel stays accessible during registration
gunicorn --chdir / --bind 0.0.0.0:8099 --workers 2 --timeout 60 addon_server:app &

# Ensure HA HTTP configuration is applied on every startup if already registered (self-healing, idempotent)
if [ -f "$DATA_DIR/registered" ]; then
    bashio::log.info "Ensuring HA HTTP configuration..."
    python3 -c "
import sys, json
sys.path.insert(0, '/')
from register import _configure_ha_trusted_proxies, _configure_ha_external_url
_configure_ha_trusted_proxies()
try:
    info = json.load(open('/data/sentive-info.json'))
    _configure_ha_external_url(info.get('web_hostname', ''))
except Exception as e:
    print(f'[DBG] Could not configure external_url: {e}', flush=True)
" 2>&1 || true
fi

# Wait for registration (triggered via addon UI)
if [ ! -f "$DATA_DIR/registered" ]; then
    bashio::log.info "Not registered — open the add-on panel to register."
    while [ ! -f "$DATA_DIR/registered" ]; do
        sleep 2
    done
fi

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
