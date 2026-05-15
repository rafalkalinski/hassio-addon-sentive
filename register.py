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


SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN", "")
DATA_DIR = "/data"
_SENTIVE_HA_USERNAME = "sentive-ops"
_SENTIVE_HA_CREDS_FILE = f"{DATA_DIR}/ha-sentive-creds.json"
_SENTIVE_REFRESH_TOKEN_FILE = f"{DATA_DIR}/ha-sentive-refresh.txt"


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


async def _setup_ha_user(password: str) -> None:
    """Create or reset the sentive-ops HA user via Supervisor WS proxy."""
    import asyncio
    import json as _json

    import websockets

    async with websockets.connect(
        "ws://supervisor/core/api/websocket", open_timeout=10
    ) as ws:
        msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if msg.get("type") == "auth_required":
            await ws.send(_json.dumps({"type": "auth", "access_token": SUPERVISOR_TOKEN}))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if res.get("type") != "auth_ok":
                raise ValueError(f"Supervisor WS auth failed: {res}")
            dbg("Supervisor WS: auth_ok")

        user_id = None
        if os.path.exists(_SENTIVE_HA_CREDS_FILE):
            try:
                stored = _json.load(open(_SENTIVE_HA_CREDS_FILE))
                user_id = stored.get("user_id")
            except Exception:
                pass

        mid = 1  # message ID counter

        # Always pre-delete stale credentials before any user operations.
        # Prevents "username already exists" errors during credential creation.
        await ws.send(_json.dumps({
            "id": mid,
            "type": "config/auth_provider/homeassistant/delete",
            "username": _SENTIVE_HA_USERNAME,
        }))
        pre_del = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        dbg(f"Pre-delete stale creds: success={pre_del.get('success')}")
        mid += 1

        if user_id:
            # Try reusing the existing HA user account
            await ws.send(_json.dumps({
                "id": mid,
                "type": "config/auth_provider/homeassistant/create",
                "user_id": user_id,
                "username": _SENTIVE_HA_USERNAME,
                "password": password,
            }))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            mid += 1
            if res.get("success"):
                dbg("Reset credentials for existing Sentive HA user OK")
                return
            dbg(f"Reset creds failed: {res} — creating new user")
            user_id = None

        # Create a new HA user
        await ws.send(_json.dumps({
            "id": mid,
            "type": "config/auth/create",
            "name": "Sentive OPS",
            "group_ids": ["system-admin"],
            "local_only": False,
        }))
        res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        mid += 1
        if not res.get("success"):
            raise ValueError(f"Failed to create HA user: {res}")
        user_id = res["result"]["user"]["id"]
        dbg(f"Created HA user id={user_id}")

        # Create credentials (stale creds already deleted above)
        await ws.send(_json.dumps({
            "id": mid,
            "type": "config/auth_provider/homeassistant/create",
            "user_id": user_id,
            "username": _SENTIVE_HA_USERNAME,
            "password": password,
        }))
        res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        mid += 1
        if not res.get("success"):
            # Retry: delete once more and try again
            dbg(f"Create creds failed: {res} — retrying with explicit delete")
            await ws.send(_json.dumps({
                "id": mid,
                "type": "config/auth_provider/homeassistant/delete",
                "username": _SENTIVE_HA_USERNAME,
            }))
            await asyncio.wait_for(ws.recv(), timeout=10)
            mid += 1
            await ws.send(_json.dumps({
                "id": mid,
                "type": "config/auth_provider/homeassistant/create",
                "user_id": user_id,
                "username": _SENTIVE_HA_USERNAME,
                "password": password,
            }))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if not res.get("success"):
                raise ValueError(f"Failed to create HA credentials: {res}")

        with open(_SENTIVE_HA_CREDS_FILE, "w") as f:
            _json.dump({"user_id": user_id, "username": _SENTIVE_HA_USERNAME}, f)
        dbg(f"Sentive OPS HA user created id={user_id}")


def _login_and_get_tokens(password: str) -> str:
    """Login as sentive-ops, store refresh_token, return access_token."""
    client_id = "http://localhost/"

    flow_resp = httpx.post(
        "http://homeassistant:8123/auth/login_flow",
        json={
            "client_id": client_id,
            "handler": ["homeassistant", None],
            "redirect_uri": f"{client_id}?auth_callback=1",
        },
        timeout=15,
    )
    dbg(f"Login flow: HTTP {flow_resp.status_code}")
    flow_resp.raise_for_status()
    flow_id = flow_resp.json()["flow_id"]

    submit_resp = httpx.post(
        f"http://homeassistant:8123/auth/login_flow/{flow_id}",
        json={
            "client_id": client_id,
            "username": _SENTIVE_HA_USERNAME,
            "password": password,
        },
        timeout=15,
    )
    dbg(f"Login submit: HTTP {submit_resp.status_code}")
    submit_resp.raise_for_status()
    submit_data = submit_resp.json()
    if submit_data.get("type") != "create_entry":
        raise ValueError(f"Login flow failed: {submit_data}")

    raw_result = submit_data["result"]
    code = raw_result if isinstance(raw_result, str) else raw_result["code"]
    dbg(f"Auth code obtained (type={type(raw_result).__name__})")

    token_resp = httpx.post(
        "http://homeassistant:8123/auth/token",
        data={
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=15,
    )
    dbg(f"Token exchange: HTTP {token_resp.status_code}")
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data["access_token"]

    refresh_token = token_data.get("refresh_token", "")
    if refresh_token:
        with open(_SENTIVE_REFRESH_TOKEN_FILE, "w") as f:
            f.write(refresh_token)
        dbg("Refresh token stored")
    else:
        dbg("WARNING: no refresh_token in response")

    dbg("Got HA access token via login flow")
    return access_token


async def _create_llat_with_token(access_token: str) -> str:
    """Create a LLAT for sentive-ops by connecting to HA WS as that user."""
    import asyncio
    import json as _json

    import websockets

    async with websockets.connect(
        "ws://homeassistant:8123/api/websocket", open_timeout=10
    ) as ws:
        msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if msg.get("type") == "auth_required":
            await ws.send(_json.dumps({"type": "auth", "access_token": access_token}))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if res.get("type") != "auth_ok":
                raise ValueError(f"sentive-ops WS auth failed: {res}")
            dbg("sentive-ops WS: auth_ok")
        await ws.send(_json.dumps({
            "id": 1,
            "type": "auth/long_lived_access_token",
            "client_name": "Sentive OPS",
            "lifespan": 3650,
        }))
        res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if not res.get("success"):
            raise ValueError(f"LLAT creation failed: {res}")
        dbg("LLAT created for sentive-ops OK")
        return res["result"]


async def _create_token_via_user_flow() -> str:
    """Create sentive-ops user, log in, then create a real LLAT for that user."""
    import secrets
    password = secrets.token_urlsafe(32)
    await _setup_ha_user(password)
    access_token = _login_and_get_tokens(password)
    return await _create_llat_with_token(access_token)


def create_long_lived_token() -> str:
    """Create a Long-Lived Access Token for the sentive-ops service account."""
    import asyncio
    return asyncio.run(_create_token_via_user_flow())


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
    short_lived_jwt = registration["short_lived_jwt"]
    web_hostname = registration.get("web_hostname", "")
    app_hostname = registration.get("app_hostname", "")
    dbg(f"Registered client_id={client_id}, web={web_hostname}, app={app_hostname}")

    # Write client info
    with open(f"{DATA_DIR}/sentive-info.json", "w") as f:
        json.dump(
            {
                "client_id": client_id,
                "web_hostname": web_hostname,
                "app_hostname": app_hostname,
            },
            f,
        )
    dbg("Credentials written to /data")

    # Create a real long-lived access token to send to OPS server
    print("Creating long-lived access token...", file=sys.stderr)
    ha_long_lived_token = create_long_lived_token()
    dbg("Long-lived token created OK")

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
    _configure_ha_external_url(web_hostname)


def _configure_ha_trusted_proxies() -> None:
    """
    Append http.trusted_proxies to HA configuration.yaml so cloudflared
    can proxy requests without HA returning 400.
    Restarts HA core via Supervisor API to apply the change.
    """
    # HA Supervisor mounts config:rw at /config in the add-on container;
    # try /homeassistant as fallback for non-standard setups
    config_path = "/config/configuration.yaml"
    if not os.path.exists(config_path):
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

    # Signal to the UI that a HA restart is needed to apply the config change.
    try:
        open(f"{DATA_DIR}/ha-restart-needed", "w").close()
    except Exception as exc:
        dbg(f"Could not write ha-restart-needed flag: {exc}")
    print(
        "configuration.yaml updated — please restart Home Assistant to apply trusted_proxies.",
        file=sys.stderr,
    )


def _configure_ha_external_url(web_hostname: str) -> None:
    """
    Write homeassistant.external_url to HA configuration.yaml so HA validates
    the client_id correctly when browsers connect through the Sentive tunnel.
    """
    if not web_hostname:
        dbg("web_hostname is empty — skipping external_url configuration")
        return

    external_url = f"https://{web_hostname}"

    config_path = "/config/configuration.yaml"
    if not os.path.exists(config_path):
        config_path = "/homeassistant/configuration.yaml"

    try:
        with open(config_path) as f:
            content = f.read()
    except Exception as exc:
        dbg(f"Could not read HA config for external_url: {exc}")
        return

    if f'external_url: "{external_url}"' in content:
        dbg(f"HA external_url already set to {external_url} — skipping")
        return

    try:
        if re.search(r"^homeassistant:", content, re.MULTILINE):
            # homeassistant: section exists — insert external_url right after it
            new_content = re.sub(
                r'(^homeassistant:[ \t]*\n)',
                r'\g<1>  external_url: "' + external_url + '"\n',
                content,
                count=1,
                flags=re.MULTILINE,
            )
            with open(config_path, "w") as f:
                f.write(new_content)
            dbg(f"Inserted external_url into existing homeassistant: section")
        else:
            # No homeassistant: section — append it
            with open(config_path, "a") as f:
                f.write(
                    f'\n# Sentive OPS — set external_url for correct client_id validation\n'
                    f'homeassistant:\n'
                    f'  external_url: "{external_url}"\n'
                )
            dbg(f"Appended homeassistant.external_url to configuration.yaml")
    except Exception as exc:
        dbg(f"Could not write HA config for external_url: {exc}")
        return

    # Signal to the UI that a HA restart is needed to apply the config change.
    try:
        open(f"{DATA_DIR}/ha-restart-needed", "w").close()
    except Exception as exc:
        dbg(f"Could not write ha-restart-needed flag: {exc}")
    print(
        f"configuration.yaml updated — please restart Home Assistant to apply external_url.",
        file=sys.stderr,
    )


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
