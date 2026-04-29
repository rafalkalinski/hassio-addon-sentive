"""
Bootstrap registration script for Sentive OPS add-on.

Performs a one-shot registration of the HA instance with Sentive OPS,
writing credentials and tunnel token to /data for subsequent runs.
"""

import argparse
import json
import os
import re
import socket
import sys

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import CertificateSigningRequestBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID


SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN", "")
DATA_DIR = "/data"


def dbg(msg: str) -> None:
    print(f"[DBG] {msg}", file=sys.stderr, flush=True)


print(f"[DBG] SUPERVISOR_TOKEN present: {bool(SUPERVISOR_TOKEN)}", file=sys.stderr, flush=True)


def check_connectivity(hostname: str) -> None:
    """DNS resolve + TCP connect check to port 443."""
    dbg(f"Resolving DNS for {hostname}...")
    try:
        addrs = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        ip = addrs[0][4][0]
        dbg(f"  DNS OK → {ip}")
    except Exception as exc:
        dbg(f"  DNS FAILED: {exc}")
        return

    dbg(f"TCP connect to {hostname}:443...")
    try:
        with socket.create_connection((hostname, 443), timeout=10):
            dbg("  TCP OK")
    except Exception as exc:
        dbg(f"  TCP FAILED: {exc}")


def get_supervisor_config() -> dict:
    """Read HA instance config from Supervisor API. Returns empty dict on failure."""
    if not SUPERVISOR_TOKEN:
        dbg("SUPERVISOR_TOKEN not set — skipping Supervisor config fetch")
        print("WARNING: SUPERVISOR_TOKEN not set, skipping Supervisor config fetch", file=sys.stderr)
        return {}
    dbg(f"SUPERVISOR_TOKEN present (len={len(SUPERVISOR_TOKEN)}), fetching HA config...")
    try:
        headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
        resp = httpx.get("http://supervisor/core/api/config", headers=headers, timeout=10)
        dbg(f"Supervisor response: HTTP {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        dbg(f"Supervisor config keys: {list(data.keys())}")
        return data
    except Exception as exc:
        dbg(f"Supervisor config fetch failed: {exc}")
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
    dbg("Requesting long-lived token from Supervisor...")
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
    resp = httpx.post(
        "http://supervisor/core/api/auth/long_lived_access_token",
        headers=headers,
        json={"client_name": "Sentive OPS", "lifespan": 365},
        timeout=10,
    )
    dbg(f"Long-lived token response: HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()["access_token"]


def register(invite_code: str, bootstrap_url: str, api_url: str) -> None:
    """Perform the full bootstrap registration flow."""

    if not bootstrap_url.startswith("https://"):
        print("ERROR: Bootstrap URL must use HTTPS", file=sys.stderr)
        sys.exit(1)

    from urllib.parse import urlparse
    bootstrap_host = urlparse(bootstrap_url).hostname
    dbg(f"Bootstrap host: {bootstrap_host}")
    check_connectivity(bootstrap_host)

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
        dbg("Keypair generated OK")
    except Exception as exc:
        print(f"ERROR: Failed to generate keypair: {exc}", file=sys.stderr)
        sys.exit(1)

    # POST /register to bootstrap server
    register_url = f"{bootstrap_url}/bootstrap/register"
    dbg(f"POST {register_url}")
    print(f"Registering with bootstrap server: {bootstrap_url}...", file=sys.stderr)
    try:
        resp = httpx.post(
            register_url,
            json={
                "invite_code": invite_code,
                "ha_url": ha_url,
                "ha_instance_name": ha_instance_name,
                "ha_version": ha_version,
                "csr_pem": csr_pem,
            },
            timeout=30,
        )
        dbg(f"/register response: HTTP {resp.status_code}")
        dbg(f"/register response headers: {dict(resp.headers)}")
        if not resp.is_success:
            dbg(f"/register response body: {resp.text[:500]}")
        resp.raise_for_status()
        registration = resp.json()
        dbg(f"/register response keys: {list(registration.keys())}")
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
    dbg(f"Registered client_id={client_id}, web={web_hostname}, app={app_hostname}")

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
    dbg("Credentials written to /data")

    # Create a real long-lived access token to send to OPS server
    print("Creating long-lived access token...", file=sys.stderr)
    try:
        ha_long_lived_token = create_long_lived_token()
        dbg("Long-lived token created OK")
    except Exception as exc:
        dbg(f"Long-lived token creation failed: {exc}")
        print(f"WARNING: Failed to create long-lived token: {exc}. Proceeding without it.", file=sys.stderr)
        ha_long_lived_token = ""

    # POST /complete with real long-lived token
    complete_url = f"{bootstrap_url}/bootstrap/complete"
    dbg(f"POST {complete_url}")
    print("Completing registration...", file=sys.stderr)
    try:
        resp = httpx.post(
            complete_url,
            json={
                "ha_long_lived_token": ha_long_lived_token,
                "ha_version": ha_version,
            },
            headers={"Authorization": f"Bearer {short_lived_jwt}"},
            timeout=30,
        )
        dbg(f"/complete response: HTTP {resp.status_code}")
        if not resp.is_success:
            dbg(f"/complete response body: {resp.text[:500]}")
        resp.raise_for_status()
        dbg("/complete OK")
    except Exception as exc:
        print(f"ERROR: Bootstrap /complete failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Write cloudflared tunnel token
    with open(f"{DATA_DIR}/cloudflared-token", "w") as f:
        f.write(tunnel_token)

    # Mark registration complete
    open(f"{DATA_DIR}/registered", "w").close()

    print("Bootstrap registration complete.", file=sys.stderr)
    _configure_ha_trusted_proxies()


def _configure_ha_trusted_proxies() -> None:
    """
    Append http.trusted_proxies to HA configuration.yaml so cloudflared
    can proxy requests without HA returning 400.
    Restarts HA core via Supervisor API to apply the change.
    """
    config_path = "/homeassistant/configuration.yaml"
    try:
        with open(config_path) as f:
            content = f.read()
    except Exception as exc:
        dbg(f"Could not read HA config: {exc}")
        return

    if re.search(r"172\.30\.0\.0/16", content):
        dbg("HA trusted_proxies already contains 172.30.0.0/16 — skipping")
        return

    if re.search(r"^http:", content, re.MULTILINE):
        if re.search(r"^\s+trusted_proxies:", content, re.MULTILINE):
            # trusted_proxies key exists, insert the IP
            new_content = re.sub(
                r'([ \t]+trusted_proxies:[ \t]*\n)',
                r'\g<1>    - 172.30.0.0/16\n',
                content,
                count=1,
                flags=re.MULTILINE,
            )
        elif re.search(r"^\s+use_x_forwarded_for:", content, re.MULTILINE):
            # has use_x_forwarded_for but no trusted_proxies
            new_content = re.sub(
                r'([ \t]+use_x_forwarded_for:.*\n)',
                r'\g<1>  trusted_proxies:\n    - 172.30.0.0/16\n',
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # http: exists but no recognisable sub-keys — insert right after http:
            new_content = re.sub(
                r'(^http:[ \t]*\n)',
                r'\g<1>  use_x_forwarded_for: true\n  trusted_proxies:\n    - 172.30.0.0/16\n',
                content,
                count=1,
                flags=re.MULTILINE,
            )
        try:
            with open(config_path, "w") as f:
                f.write(new_content)
            dbg("Updated trusted_proxies in existing http: section")
        except Exception as exc:
            dbg(f"Could not write HA config: {exc}")
            return
    else:
        # no http: section — append
        try:
            with open(config_path, "a") as f:
                f.write(
                    "\n# Sentive OPS — allow cloudflared tunnel to proxy to Home Assistant\n"
                    "http:\n"
                    "  use_x_forwarded_for: true\n"
                    "  trusted_proxies:\n"
                    "    - 172.30.0.0/16\n"
                )
            dbg("Appended http trusted_proxies to configuration.yaml")
        except Exception as exc:
            dbg(f"Could not write HA config: {exc}")
            return

    if not SUPERVISOR_TOKEN:
        print("WARNING: Cannot restart HA automatically — no SUPERVISOR_TOKEN.", file=sys.stderr)
        return

    dbg("Restarting HA core to apply trusted_proxies...")
    try:
        resp = httpx.post(
            "http://supervisor/core/restart",
            headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            timeout=60,
        )
        dbg(f"HA restart triggered: {resp.status_code}")
    except Exception as exc:
        dbg(f"HA restart failed — please restart HA manually: {exc}")


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

    invite_code = args.invite_code.strip()
    print(f"Using invite code: {invite_code!r}", file=sys.stderr)
    register(
        invite_code=invite_code,
        bootstrap_url=args.bootstrap_url,
        api_url=args.api_url,
    )


if __name__ == "__main__":
    main()
