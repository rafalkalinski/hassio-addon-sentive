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

# Ensure sentive-ops HA user is not local_only (self-healing, idempotent)
bashio::log.info "Ensuring sentive-ops user is not local_only..."
python3 -c "
import asyncio, json, os, sys
sys.path.insert(0, '/')
from register import SUPERVISOR_TOKEN, _SENTIVE_HA_CREDS_FILE, _SENTIVE_HA_USERNAME

async def fix_local_only():
    if not os.path.exists(_SENTIVE_HA_CREDS_FILE):
        return
    try:
        stored = json.load(open(_SENTIVE_HA_CREDS_FILE))
        user_id = stored.get('user_id')
    except Exception:
        return
    if not user_id:
        return
    import websockets, json as _json
    try:
        async with websockets.connect('ws://supervisor/core/api/websocket', open_timeout=10) as ws:
            msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg.get('type') == 'auth_required':
                await ws.send(_json.dumps({'type': 'auth', 'access_token': SUPERVISOR_TOKEN}))
                res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if res.get('type') != 'auth_ok':
                    return
            await ws.send(_json.dumps({'id': 1, 'type': 'config/auth/update', 'user_id': user_id, 'local_only': False}))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            print(f'local_only fix: success={res.get(\"success\")}', file=sys.stderr)
    except Exception as e:
        print(f'local_only fix failed (non-fatal): {e}', file=sys.stderr)

asyncio.run(fix_local_only())
" 2>&1 || true

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
