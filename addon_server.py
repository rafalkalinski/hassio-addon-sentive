"""
Sentive OPS add-on ingress UI server.

Flask web server on port 8099 providing:
- PIN gate (4-digit, bcrypt-hashed, stored in /data/pin.json)
- Status page (connection info)
- Device cert management (list/add/revoke/renew via Sentive OPS API)
"""

import base64
import io
import json
import os
import secrets
import threading
import time
from functools import wraps
from pathlib import Path

import bcrypt
import httpx
import qrcode
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

DATA_DIR = Path("/data")
PIN_FILE = DATA_DIR / "pin.json"
INFO_FILE = DATA_DIR / "sentive-info.json"
SESSION_KEY_FILE = DATA_DIR / "session-secret.key"

app = Flask(__name__, template_folder="/templates")


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


def _api_headers() -> dict:
    info = _load_info()
    jwt = info.get("jwt", "")
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}


def _api_url() -> str:
    info = _load_info()
    return info.get("api_url", "")


def _client_id() -> str:
    info = _load_info()
    return info.get("client_id", "")


# ------------------------------------------------------------------
# Background heartbeat thread
# ------------------------------------------------------------------


def _heartbeat_loop() -> None:
    """Background thread — polls OPS for pin_reset_required flag.

    TODO: poll /addon/clients/{client_id}/pin-reset-required once endpoint exists.
    """
    while True:
        time.sleep(30)
        try:
            client = _client_id()
            api = _api_url()
            if not client or not api:
                continue
            # Placeholder — replace with actual pin-reset-required endpoint
            # resp = httpx.get(
            #     f"{api}/addon/clients/{client}/pin-reset-required",
            #     headers=_api_headers(),
            #     timeout=10,
            # )
            # if resp.status_code == 200 and resp.json().get("pin_reset_required"):
            #     PIN_FILE.unlink(missing_ok=True)
        except Exception:
            pass


threading.Thread(target=_heartbeat_loop, daemon=True).start()


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@app.route("/")
def index():
    if not _pin_is_set():
        return redirect(url_for("setup_pin"))
    return redirect(url_for("pin"))


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
        entered = request.form.get("pin", "")
        if _check_pin(entered):
            session["authenticated"] = True
            return redirect(url_for("status"))
        error = "Incorrect PIN. Please try again."

    return render_template("pin_gate.html", error=error)


@app.route("/status")
@_require_session
def status():
    info = _load_info()
    return render_template("status.html", info=info)


@app.route("/devices")
@_require_session
def devices():
    info = _load_info()
    client = info.get("client_id", "")
    api = _api_url()
    certs = []
    fetch_error = None

    if client and api:
        try:
            resp = httpx.get(
                f"{api}/addon/clients/{client}/device-certs",
                headers=_api_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            certs = resp.json().get("certs", [])
        except Exception as exc:
            fetch_error = str(exc)

    return render_template("devices.html", certs=certs, error=fetch_error, info=info)


@app.route("/devices/add", methods=["POST"])
@_require_session
def devices_add():
    info = _load_info()
    client = info.get("client_id", "")
    api = _api_url()

    label = request.form.get("label", "My Device").strip()
    platform = request.form.get("platform", "ios")

    result = None
    error = None

    if client and api:
        try:
            resp = httpx.post(
                f"{api}/addon/clients/{client}/device-certs",
                headers=_api_headers(),
                json={"label": label, "platform": platform},
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()

            # Generate QR code from mobileconfig URL or base64 payload
            mobileconfig = result.get("mobileconfig_b64") or result.get("mobileconfig_url", "")
            if mobileconfig:
                qr = qrcode.make(mobileconfig)
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                result["qr_data_uri"] = (
                    "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
                )
        except Exception as exc:
            error = str(exc)
    else:
        error = "Add-on is not registered yet."

    certs = []
    if client and api:
        try:
            r = httpx.get(
                f"{api}/addon/clients/{client}/device-certs",
                headers=_api_headers(),
                timeout=10,
            )
            r.raise_for_status()
            certs = r.json().get("certs", [])
        except Exception:
            pass

    return render_template(
        "devices.html",
        certs=certs,
        new_cert=result,
        error=error,
        info=info,
    )


@app.route("/devices/<cert_id>/revoke", methods=["POST"])
@_require_session
def devices_revoke(cert_id: str):
    info = _load_info()
    client = info.get("client_id", "")
    api = _api_url()

    if client and api:
        try:
            resp = httpx.post(
                f"{api}/addon/clients/{client}/device-certs/{cert_id}/revoke",
                headers=_api_headers(),
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            pass

    return redirect(url_for("devices"))


@app.route("/devices/<cert_id>/renew", methods=["POST"])
@_require_session
def devices_renew(cert_id: str):
    info = _load_info()
    client = info.get("client_id", "")
    api = _api_url()

    result = None
    error = None

    if client and api:
        try:
            resp = httpx.post(
                f"{api}/addon/clients/{client}/device-certs/{cert_id}/renew",
                headers=_api_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()

            mobileconfig = result.get("mobileconfig_b64") or result.get("mobileconfig_url", "")
            if mobileconfig:
                qr = qrcode.make(mobileconfig)
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                result["qr_data_uri"] = (
                    "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
                )
        except Exception as exc:
            error = str(exc)
    else:
        error = "Add-on is not registered yet."

    certs = []
    if client and api:
        try:
            r = httpx.get(
                f"{api}/addon/clients/{client}/device-certs",
                headers=_api_headers(),
                timeout=10,
            )
            r.raise_for_status()
            certs = r.json().get("certs", [])
        except Exception:
            pass

    return render_template(
        "devices.html",
        certs=certs,
        new_cert=result,
        error=error,
        info=info,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False)
