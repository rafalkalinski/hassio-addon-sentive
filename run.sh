#!/usr/bin/env bashio
set -e

DATA_DIR=/data

# Ensure external DNS is available (HA Supervisor DNS may not resolve CF hostnames)
if ! grep -q "1.1.1.1" /etc/resolv.conf 2>/dev/null; then
    echo "nameserver 1.1.1.1" >> /etc/resolv.conf
fi

INVITE_CODE=$(bashio::config 'invite_code')
BOOTSTRAP_URL="https://bootstrap-dev.sentive.it"
API_URL="https://api-dev.sentive.it"

# Start ingress UI server immediately — panel stays accessible even during registration
python3 /addon_server.py &

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

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
