# Sentive OPS Add-on for Home Assistant

Connect your Home Assistant instance to the Sentive OPS fleet management platform.

## Features

- Automatic registration via invite code (one-shot bootstrap)
- Persistent `cloudflared` tunnel for secure remote access
- Ingress UI panel with PIN gate
- Device certificate management (issue, revoke, renew mTLS certs for mobile/desktop clients)

## Installation

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Click the three-dot menu and select **Repositories**.
3. Add the repository URL: `https://github.com/rafalkalinski/hassio-addon-sentive`
4. Find **Sentive OPS** in the store and click **Install**.

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `invite_code` | Invite code provided by Sentive OPS | (required) |
| `ops_bootstrap_url` | Bootstrap server URL | `https://bootstrap.dev.sentive.it` |
| `ops_api_url` | Sentive OPS API URL | `https://api.dev.sentive.it` |

## First-Run Steps

1. Set your `invite_code` in the add-on configuration.
2. Start the add-on.
3. Open the **Sentive OPS** panel in the HA sidebar.
4. Set a 4-digit PIN when prompted — this protects the ingress panel.
5. The add-on registers automatically and starts the cloudflared tunnel.

## Support

For issues, visit the [GitHub repository](https://github.com/rafalkalinski/hassio-addon-sentive).
