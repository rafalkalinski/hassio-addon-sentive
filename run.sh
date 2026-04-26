#!/usr/bin/env bashio
set -e

CONFIG_PATH=/data/options.json
DATA_DIR=/data
INVITE_CODE=$(bashio::config 'invite_code')
BOOTSTRAP_URL=$(bashio::config 'ops_bootstrap_url')
API_URL=$(bashio::config 'ops_api_url')

# Run registration if not yet registered
if [ ! -f "$DATA_DIR/registered" ]; then
    bashio::log.info "Running bootstrap registration..."
    python3 /register.py \
        --invite-code "$INVITE_CODE" \
        --bootstrap-url "$BOOTSTRAP_URL" \
        --api-url "$API_URL"
fi

# Start ingress UI server in background
python3 /addon_server.py &

# Start cloudflared tunnel
TUNNEL_TOKEN=$(cat "$DATA_DIR/cloudflared-token")
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
