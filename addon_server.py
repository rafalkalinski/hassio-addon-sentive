"""
Sentive OPS add-on ingress UI server.

Flask web server on port 8099 providing:
- PIN gate (4-digit, bcrypt-hashed, stored in /data/pin.json)
- Status page (connection info)
"""

import asyncio
import json
import os
import re
import secrets
import time
from functools import wraps
from pathlib import Path

import bcrypt
import httpx
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN", "")
_SENTIVE_HA_USERNAME = "sentive-ops"

DATA_DIR = Path("/data")
PIN_FILE = DATA_DIR / "pin.json"
HA_RESTART_NEEDED_FILE = DATA_DIR / "ha-restart-needed"

def _read_addon_version() -> str:
    try:
        text = Path("/config.yaml").read_text()
        m = re.search(r'^version:\s*["\']?([^\s"\']+)["\']?', text, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"

ADDON_VERSION = _read_addon_version()
INFO_FILE = DATA_DIR / "sentive-info.json"
SESSION_KEY_FILE = DATA_DIR / "session-secret.key"

class _IngressFix:
    """
    Set SCRIPT_NAME from X-Ingress-Path and fix redirect Location headers.

    Belt-and-suspenders: even if url_for() ignores SCRIPT_NAME and generates
    a bare path like /status, the middleware rewrites the Location header to
    include the ingress prefix before it reaches the browser.
    """
    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        ingress_path = environ.get("HTTP_X_INGRESS_PATH", "")
        if ingress_path:
            environ["SCRIPT_NAME"] = ingress_path
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(ingress_path):
                environ["PATH_INFO"] = path_info[len(ingress_path):]

            def fixing_start_response(status, headers, exc_info=None):
                if status.startswith("3"):
                    fixed = []
                    for name, value in headers:
                        if (
                            name.lower() == "location"
                            and value.startswith("/")
                            and not value.startswith(ingress_path)
                        ):
                            value = ingress_path.rstrip("/") + value
                        fixed.append((name, value))
                    return start_response(status, fixed, exc_info)
                return start_response(status, headers, exc_info)

            return self._app(environ, fixing_start_response)
        return self._app(environ, start_response)


app = Flask(__name__, template_folder="/templates")
app.wsgi_app = _IngressFix(app.wsgi_app)

# PIN brute force protection state
_pin_attempts: dict = {"count": 0, "lockout_until": 0.0}


# Load or generate session secret key
def _get_session_secret() -> str:
    if SESSION_KEY_FILE.exists():
        return SESSION_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SESSION_KEY_FILE.write_text(key)
    return key


app.secret_key = _get_session_secret()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _load_info() -> dict:
    if INFO_FILE.exists():
        return json.loads(INFO_FILE.read_text())
    return {}


def _pin_is_set() -> bool:
    return PIN_FILE.exists()


def _check_pin(pin: str) -> bool:
    if not PIN_FILE.exists():
        return False
    data = json.loads(PIN_FILE.read_text())
    stored_hash = data.get("hash", "").encode()
    return bcrypt.checkpw(pin.encode(), stored_hash)


def _set_pin(pin: str) -> None:
    hashed = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
    PIN_FILE.write_text(json.dumps({"hash": hashed}))


def _require_session(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("pin"))
        return f(*args, **kwargs)

    return decorated


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# HA cleanup helpers (used by reset_registration)
# ------------------------------------------------------------------


async def _cleanup_ha_user_async() -> dict:
    """Delete sentive-ops credentials and user via Supervisor WS."""
    import json as _json
    import websockets

    result = {"creds_deleted": False, "user_deleted": False, "error": None}
    if not SUPERVISOR_TOKEN:
        result["error"] = "No SUPERVISOR_TOKEN"
        return result

    creds_file = DATA_DIR / "ha-sentive-creds.json"
    user_id = None
    if creds_file.exists():
        try:
            user_id = _json.loads(creds_file.read_text()).get("user_id")
        except Exception:
            pass

    try:
        async with websockets.connect(
            "ws://supervisor/core/api/websocket", open_timeout=10
        ) as ws:
            msg = _json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if msg.get("type") == "auth_required":
                await ws.send(_json.dumps({"type": "auth", "access_token": SUPERVISOR_TOKEN}))
                res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if res.get("type") != "auth_ok":
                    result["error"] = f"WS auth failed: {res.get('type')}"
                    return result

            mid = 1
            await ws.send(_json.dumps({
                "id": mid,
                "type": "config/auth_provider/homeassistant/delete",
                "username": _SENTIVE_HA_USERNAME,
            }))
            del_res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            result["creds_deleted"] = bool(del_res.get("success"))
            mid += 1

            if user_id:
                await ws.send(_json.dumps({
                    "id": mid,
                    "type": "config/auth/delete",
                    "user_id": user_id,
                }))
                del_res = _json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                result["user_deleted"] = bool(del_res.get("success"))
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _cleanup_ha_user() -> dict:
    try:
        return asyncio.run(_cleanup_ha_user_async())
    except Exception as exc:
        return {"creds_deleted": False, "user_deleted": False, "error": str(exc)}


def _remove_ha_trusted_proxies() -> bool:
    """Remove 172.30.0.0/16 and the Sentive comment from HA configuration.yaml."""
    config_path = "/config/configuration.yaml"
    if not os.path.exists(config_path):
        config_path = "/homeassistant/configuration.yaml"
    try:
        with open(config_path) as f:
            lines = f.readlines()
    except Exception:
        return False

    new_lines = [
        line for line in lines
        if not re.match(r"[ \t]+-\s*172\.30\.0\.0/16\s*$", line)
        and "Sentive OPS — allow cloudflared tunnel to proxy to Home Assistant" not in line
    ]
    if new_lines == lines:
        return False
    try:
        with open(config_path, "w") as f:
            f.writelines(new_lines)
        return True
    except Exception:
        return False


def _restart_ha_core() -> bool:
    """Trigger HA core restart via Supervisor API."""
    if not SUPERVISOR_TOKEN:
        return False
    try:
        resp = httpx.post(
            "http://supervisor/core/restart",
            headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            timeout=30,
        )
        return resp.is_success
    except Exception:
        return False


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


REGISTRATION_ERROR_FILE = DATA_DIR / "registration-error.txt"
REGISTERED_FILE = DATA_DIR / "registered"


@app.route("/")
def index():
    if not REGISTERED_FILE.exists() and REGISTRATION_ERROR_FILE.exists():
        return redirect(url_for("registration_error"))
    if not _pin_is_set():
        return redirect(url_for("setup_pin"))
    return redirect(url_for("pin"))


@app.route("/registration-error")
def registration_error():
    error_text = ""
    if REGISTRATION_ERROR_FILE.exists():
        error_text = REGISTRATION_ERROR_FILE.read_text()
    return render_template("registration_error.html", error=error_text)


@app.route("/setup-pin", methods=["GET", "POST"])
def setup_pin():
    if _pin_is_set():
        return redirect(url_for("pin"))

    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "")
        confirm = request.form.get("confirm_pin", "")
        if len(pin) != 4 or not pin.isdigit():
            error = "PIN must be exactly 4 digits."
        elif pin != confirm:
            error = "PINs do not match."
        else:
            _set_pin(pin)
            session["authenticated"] = True
            return redirect(url_for("status"))

    return render_template("setup_pin.html", error=error)


@app.route("/pin", methods=["GET", "POST"])
def pin():
    if not _pin_is_set():
        return redirect(url_for("setup_pin"))

    error = None
    if request.method == "POST":
        now = time.time()
        if now < _pin_attempts["lockout_until"]:
            remaining = int(_pin_attempts["lockout_until"] - now)
            error = f"Too many failed attempts. Try again in {remaining} seconds."
        else:
            entered = request.form.get("pin", "")
            if _check_pin(entered):
                _pin_attempts["count"] = 0
                _pin_attempts["lockout_until"] = 0.0
                session["authenticated"] = True
                return redirect(url_for("status"))
            else:
                _pin_attempts["count"] += 1
                if _pin_attempts["count"] >= 5:
                    _pin_attempts["lockout_until"] = now + 60.0
                    error = "Too many failed attempts. Try again in 60 seconds."
                else:
                    error = "Incorrect PIN. Please try again."

    return render_template("pin_gate.html", error=error)


@app.route("/status")
@_require_session
def status():
    info = _load_info()
    return render_template(
        "status.html",
        info=info,
        version=ADDON_VERSION,
        ha_restart_needed=HA_RESTART_NEEDED_FILE.exists(),
    )


@app.route("/restart-ha", methods=["POST"])
@_require_session
def restart_ha():
    restarted = _restart_ha_core()
    if restarted:
        HA_RESTART_NEEDED_FILE.unlink(missing_ok=True)
    return render_template("restart_ha.html", restarted=restarted)


@app.route("/reset-registration", methods=["POST"])
@_require_session
def reset_registration():
    ha_result = _cleanup_ha_user()
    config_cleaned = _remove_ha_trusted_proxies()
    ha_restarted = _restart_ha_core() if config_cleaned else False

    for f in [
        DATA_DIR / "registered",
        DATA_DIR / "cloudflared-token",
        DATA_DIR / "sentive-info.json",
        DATA_DIR / "registration-error.txt",
        DATA_DIR / "ha-sentive-creds.json",
        DATA_DIR / "ha-sentive-refresh.txt",
        HA_RESTART_NEEDED_FILE,
    ]:
        f.unlink(missing_ok=True)

    return render_template(
        "reset_done.html",
        ha_user_deleted=ha_result.get("user_deleted", False),
        ha_creds_deleted=ha_result.get("creds_deleted", False),
        ha_error=ha_result.get("error"),
        config_cleaned=config_cleaned,
        ha_restarted=ha_restarted,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False)
