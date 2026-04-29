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
_SENTIVE_LLAT_FILE = f"{DATA_DIR}/ha-sentive-llat.txt"


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


def create_long_lived_token() -> str:
    """
    Create a HA long-lived access token (LLAT) via a 3-phase flow:

    1. Supervisor WS proxy (auth via SUPERVISOR_TOKEN) — create a dedicated
       non-system HA user '_SENTIVE_HA_USERNAME' with a fresh random password.
       System users cannot create LLATs, so we need a real HA user.
    2. HA HTTP auth/login_flow — log in as that user to get a short-lived token.
    3. Direct HA WebSocket — use the short-lived token to create a 10-year LLAT.
    """
    import asyncio
    import json as _json
    import secrets

    import websockets

    password = secrets.token_urlsafe(32)

    async def _setup_ha_user() -> None:
        """Create or reset the sentive-ops HA user via Supervisor WS proxy."""
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

            if user_id:
                # Delete old credentials and recreate with new password
                await ws.send(_json.dumps({
                    "id": 1,
                    "type": "config/auth_provider/homeassistant/delete",
                    "username": _SENTIVE_HA_USERNAME,
                }))
                del_res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                dbg(f"Delete old creds: success={del_res.get('success')}")

                await ws.send(_json.dumps({
                    "id": 2,
                    "type": "config/auth_provider/homeassistant/create",
                    "user_id": user_id,
                    "username": _SENTIVE_HA_USERNAME,
                    "password": password,
                }))
                res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if res.get("success"):
                    dbg("Reset credentials for existing Sentive HA user OK")
                    return
                dbg(f"Reset creds failed: {res} — creating new user")
                user_id = None

            # Create a new non-system HA user (admin group so OPS has full access)
            await ws.send(_json.dumps({
                "id": 3,
                "type": "config/auth/create",
                "name": "Sentive OPS",
                "group_ids": ["system-admin"],
            }))
            res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if not res.get("success"):
                raise ValueError(f"Failed to create HA user: {res}")
            user_id = res["result"]["user"]["id"]
            dbg(f"Created HA user id={user_id}")

            await ws.send(_json.dumps({
                "id": 4,
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

    async def _login_and_create_llat() -> str:
        """Authenticate as sentive-ops via HA HTTP login flow, then create a LLAT."""
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

        # HA 2024+ returns the code as a plain string; older versions wrap it in {"code": "..."}
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
        access_token = token_resp.json()["access_token"]
        dbg("Got HA access token via login flow")

        # Connect directly to HA WS (not Supervisor proxy) with the real user token
        async with websockets.connect(
            "ws://homeassistant:8123/api/websocket", open_timeout=10
        ) as ws:
            msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg.get("type") == "auth_required":
                await ws.send(_json.dumps({"type": "auth", "access_token": access_token}))
                res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                dbg(f"Direct HA WS auth: {res.get('type')}")
                if res.get("type") != "auth_ok":
                    raise ValueError(f"Direct HA WS auth failed: {res}")

            await ws.send(_json.dumps({
                "id": 1,
                "type": "auth/long_lived_access_token",
                "client_name": "Sentive OPS",
                "lifespan": 3650,
            }))
            msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            dbg(f"LLAT creation: success={msg.get('success')}")
            if not msg.get("success"):
                raise ValueError(f"LLAT creation failed: {msg}")
            return msg["result"]

    async def _run() -> str:
        await _setup_ha_user()
        return await _login_and_create_llat()

    return asyncio.run(_run())


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
    addon_api_token = registration.get("addon_api_token", short_lived_jwt)
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
                "jwt": addon_api_token,
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


def _push_ha_token_to_ops() -> None:
    """
    Ensure OPS has a valid HA long-lived access token for monitoring.
    Uses a locally cached LLAT; creates a new one only if missing or expired.
    Called on every add-on startup — self-heals monitoring after HA restarts.
    """
    llat = None
    if os.path.exists(_SENTIVE_LLAT_FILE):
        try:
            with open(_SENTIVE_LLAT_FILE) as f:
                llat = f.read().strip()
            resp = httpx.get(
                "http://homeassistant:8123/api/config",
                headers={"Authorization": f"Bearer {llat}"},
                timeout=10,
            )
            if resp.status_code != 200:
                dbg(f"Cached LLAT rejected (HTTP {resp.status_code}) — recreating")
                llat = None
            else:
                dbg("Cached LLAT is valid")
        except Exception as exc:
            dbg(f"LLAT check failed: {exc}")
            llat = None

    if not llat:
        try:
            llat = create_long_lived_token()
            with open(_SENTIVE_LLAT_FILE, "w") as f:
                f.write(llat)
            dbg("New LLAT created and cached")
        except Exception as exc:
            print(f"WARNING: Failed to create long-lived token: {exc}", file=sys.stderr)
            return

    info_path = f"{DATA_DIR}/sentive-info.json"
    try:
        with open(info_path) as f:
            info = json.load(f)
    except Exception as exc:
        dbg(f"Could not read sentive-info.json: {exc}")
        return

    client_id = info.get("client_id")
    api_url = info.get("api_url", "").rstrip("/")
    addon_jwt = info.get("jwt")

    if not all([client_id, api_url, addon_jwt]):
        dbg("Missing client_id/api_url/jwt in sentive-info.json — skipping token push")
        return

    try:
        resp = httpx.put(
            f"{api_url}/addon/clients/{client_id}/ha-token",
            json={"ha_long_lived_token": llat},
            headers={"Authorization": f"Bearer {addon_jwt}"},
            timeout=15,
        )
        resp.raise_for_status()
        dbg("HA token pushed to OPS OK — monitoring enabled")
    except Exception as exc:
        print(f"WARNING: Failed to push HA token to OPS: {exc}", file=sys.stderr)


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
