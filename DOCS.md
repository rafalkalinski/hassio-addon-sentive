# Sentive OPS Add-on — Documentation

## Bootstrap Flow

On first start, the add-on runs `register.py` to register the HA instance with Sentive OPS:

1. Reads `invite_code`, `ops_bootstrap_url`, and `ops_api_url` from add-on options.
2. Fetches the HA instance name, version, and external URL from the Supervisor API.
3. Generates an EC P-256 keypair and a Certificate Signing Request (CSR).
4. POSTs to `{bootstrap_url}/register` with the invite code, HA metadata, and CSR.
5. Receives a signed certificate, tunnel token, client ID, and short-lived JWT.
6. Writes credentials to `/data/` (`sentive-cert.pem`, `sentive-key.pem`, `sentive-info.json`).
7. Completes registration by POSTing to `{bootstrap_url}/complete` with the Supervisor token.
8. Writes the cloudflared tunnel token to `/data/cloudflared-token`.
9. Creates `/data/registered` to prevent re-registration on subsequent starts.

If registration fails, the add-on logs the error and exits. Check the add-on logs for details.

## PIN Gate

The ingress panel is protected by a 4-digit PIN stored in `/data/pin.json` as a bcrypt hash.

- First run: you are prompted to set a PIN.
- Subsequent runs: you must enter the PIN to access the panel.
- If you forget your PIN, stop the add-on, delete `/data/pin.json` via the Supervisor file editor, and restart.

A background thread polls for a PIN reset signal from Sentive OPS. When the reset endpoint is
implemented, it will wipe `/data/pin.json` and prompt for a new PIN without requiring manual
file deletion.

## Device Certificate Management

Navigate to the **Devices** tab in the ingress panel to manage mTLS device certificates.

- **Add Device**: Issues a new certificate for a labelled device (iOS/macOS or Android).
  After issuance, a QR code is displayed for scanning the `.mobileconfig` profile.
- **Renew**: Re-issues a certificate before it expires. A new QR code is provided.
- **Revoke**: Permanently revokes the certificate. The device will lose tunnel access.

All certificate operations call `{ops_api_url}/addon/clients/{client_id}/device-certs` with
Bearer token authentication using the JWT stored in `/data/sentive-info.json`.

Note: The JWT issued during bootstrap is short-lived (30 minutes). In the current version,
refresh is not implemented — if the JWT expires, re-registration is required. A token refresh
mechanism will be added in a future release.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Add-on fails to start | Invalid or already-used invite code | Obtain a fresh invite code from Sentive OPS |
| Panel shows blank / 502 | Flask server not started | Check add-on logs for Python errors |
| Tunnel not connecting | Invalid tunnel token | Re-register by deleting `/data/registered` and restarting |
| PIN prompt loops | `pin.json` corrupted | Delete `/data/pin.json` and restart |
| Device cert list empty | JWT expired | Re-register (delete `/data/registered`) to obtain a fresh JWT |

## Data Files

All persistent state is stored under `/data/` (HA add-on data directory):

| File | Description |
|------|-------------|
| `options.json` | Add-on configuration (managed by HA) |
| `registered` | Marker file — presence means bootstrap completed |
| `sentive-cert.pem` | mTLS client certificate |
| `sentive-key.pem` | Private key (mode 0600) |
| `sentive-info.json` | Client ID, hostnames, API URL, JWT |
| `cloudflared-token` | Cloudflare tunnel token |
| `pin.json` | bcrypt-hashed PIN |
| `session-secret.key` | Flask session signing key |
