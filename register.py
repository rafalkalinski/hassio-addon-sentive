"""
Bootstrap registration script for Sentive OPS add-on.

Performs a one-shot registration of the HA instance with Sentive OPS,
writing credentials and tunnel token to /data for subsequent runs.
"""

import argparse
import json
import os
import sys

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import CertificateSigningRequestBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID


SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN", "")
DATA_DIR = "/data"


def get_supervisor_config() -> dict:
    """Read HA instance config from Supervisor API. Returns empty dict on failure."""
    if not SUPERVISOR_TOKEN:
        print("WARNING: SUPERVISOR_TOKEN not set, skipping Supervisor config fetch", file=sys.stderr)
        return {}
    try:
        headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
        resp = httpx.get("http://supervisor/core/api/config", headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"WARNING: Failed to fetch Supervisor config: {exc}", file=sys.stderr)
        return {}


def generate_keypair_and_csr(ha_instance_name: str) -> tuple[str, str]:
    """Generate EC P-256 keypair and CSR. Returns (csr_pem, private_key_pem)."""
    private_key = ec.generate_private_key(ec.SECP256R1())

    csr = (
        CertificateSigningRequestBuilder()
        .subject_name(
            Name([NameAttribute(NameOID.COMMON_NAME, ha_instance_name or "sentive-client")])
        )
        .sign(private_key, hashes.SHA256())
    )

    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return csr_pem, private_key_pem


def create_long_lived_token() -> str:
    """Create a real HA long-lived access token via Supervisor proxy."""
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
    resp = httpx.post(
        "http://supervisor/core/api/auth/long_lived_access_token",
        headers=headers,
        json={"client_name": "Sentive OPS", "lifespan": 365},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def register(invite_code: str, bootstrap_url: str, api_url: str) -> None:
    """Perform the full bootstrap registration flow."""

    if not bootstrap_url.startswith("https://"):
        print("ERROR: Bootstrap URL must use HTTPS", file=sys.stderr)
        sys.exit(1)

    # Fetch HA instance info from Supervisor
    print("Fetching HA instance info from Supervisor...", file=sys.stderr)
    ha_config = get_supervisor_config()

    ha_url = ha_config.get("external_url") or ha_config.get("internal_url") or ""
    ha_version = ha_config.get("version", "unknown")
    ha_instance_name = ha_config.get("location_name", "Home Assistant")

    print(
        f"HA instance: {ha_instance_name}, version: {ha_version}, url: {ha_url}",
        file=sys.stderr,
    )

    # Generate keypair and CSR
    print("Generating EC P-256 keypair and CSR...", file=sys.stderr)
    try:
        csr_pem, private_key_pem = generate_keypair_and_csr(ha_instance_name)
    except Exception as exc:
        print(f"ERROR: Failed to generate keypair: {exc}", file=sys.stderr)
        sys.exit(1)

    # POST /register to bootstrap server
    print(f"Registering with bootstrap server: {bootstrap_url}...", file=sys.stderr)
    try:
        resp = httpx.post(
            f"{bootstrap_url}/bootstrap/register",
            json={
                "invite_code": invite_code,
                "ha_url": ha_url,
                "ha_instance_name": ha_instance_name,
                "ha_version": ha_version,
                "csr_pem": csr_pem,
            },
            timeout=30,
        )
        resp.raise_for_status()
        registration = resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"ERROR: Bootstrap /register failed: {exc}", file=sys.stderr)
        print(f"ERROR: Response body: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Bootstrap /register failed: {exc}", file=sys.stderr)
        sys.exit(1)

    client_id = registration["client_id"]
    tunnel_token = registration["tunnel_token"]
    cert_pem = registration["cert_pem"]
    short_lived_jwt = registration["short_lived_jwt"]
    web_hostname = registration.get("web_hostname", "")
    app_hostname = registration.get("app_hostname", "")

    # Write client certificate and private key
    with open(f"{DATA_DIR}/sentive-cert.pem", "w") as f:
        f.write(cert_pem)
    with open(f"{DATA_DIR}/sentive-key.pem", "w") as f:
        f.write(private_key_pem)
    os.chmod(f"{DATA_DIR}/sentive-key.pem", 0o600)

    # Write client info
    with open(f"{DATA_DIR}/sentive-info.json", "w") as f:
        json.dump(
            {
                "client_id": client_id,
                "web_hostname": web_hostname,
                "app_hostname": app_hostname,
                "jwt": short_lived_jwt,
                "api_url": api_url,
            },
            f,
        )

    # Create a real long-lived access token to send to OPS server
    print("Creating long-lived access token...", file=sys.stderr)
    try:
        ha_long_lived_token = create_long_lived_token()
    except Exception as exc:
        print(f"WARNING: Failed to create long-lived token: {exc}. Proceeding without it.", file=sys.stderr)
        ha_long_lived_token = ""

    # POST /complete with real long-lived token
    print("Completing registration...", file=sys.stderr)
    try:
        resp = httpx.post(
            f"{bootstrap_url}/bootstrap/complete",
            json={
                "ha_long_lived_token": ha_long_lived_token,
                "ha_version": ha_version,
            },
            headers={"Authorization": f"Bearer {short_lived_jwt}"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"ERROR: Bootstrap /complete failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Write cloudflared tunnel token
    with open(f"{DATA_DIR}/cloudflared-token", "w") as f:
        f.write(tunnel_token)

    # Mark registration complete
    open(f"{DATA_DIR}/registered", "w").close()

    print("Bootstrap registration complete.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentive OPS bootstrap registration")
    parser.add_argument("--invite-code", required=True, help="Invite code from Sentive OPS")
    parser.add_argument(
        "--bootstrap-url",
        required=True,
        help="Bootstrap server base URL",
    )
    parser.add_argument("--api-url", required=True, help="Sentive OPS API base URL")
    args = parser.parse_args()

    register(
        invite_code=args.invite_code,
        bootstrap_url=args.bootstrap_url,
        api_url=args.api_url,
    )


if __name__ == "__main__":
    main()
