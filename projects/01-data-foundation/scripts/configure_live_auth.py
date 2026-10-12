#!/usr/bin/env python3
"""Configure ignored local credentials for P1.6 without printing secrets."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIAL_DIR = PROJECT.parents[1] / "generated-data" / "p16-live" / "credentials"


def _write_secret(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def configure_hubspot(path: Path, tenant: str) -> None:
    token = getpass.getpass("HubSpot Service Key or existing private-app token (input hidden): ").strip()
    if not token:
        raise SystemExit("No HubSpot token was entered.")
    _write_secret(path, {"access_token": token, "tenant": tenant})
    print("Saved HubSpot credentials to ignored local storage with mode 600.")


class _CallbackHandler(BaseHTTPRequestHandler):
    result: Dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        query = parse_qs(urlparse(self.path).query)
        for name in ("code", "state", "error", "error_description"):
            values = query.get(name)
            if values:
                self.result[name] = values[0]
        message = b"Salesforce authorization received. You can close this browser tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def log_message(self, _format: str, *args: object) -> None:
        return


def _post_form(url: str, form: Dict[str, str]) -> Dict[str, Any]:
    request = Request(
        url,
        data=urlencode(form).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def configure_salesforce(path: Path, login_url: str, client_id: str, port: int) -> None:
    client_secret = getpass.getpass(
        "Salesforce client secret (input hidden; press Enter if your PKCE app does not require one): "
    ).strip()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(32)
    redirect_uri = "http://localhost:%d/callback" % port
    authorize_url = "%s/services/oauth2/authorize?%s" % (
        login_url.rstrip("/"),
        urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "api refresh_token offline_access",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        ),
    )
    _CallbackHandler.result = {}
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = 300
    print("Opening Salesforce sign-in in your browser; this local callback waits up to five minutes.")
    webbrowser.open(authorize_url)
    server.handle_request()
    server.server_close()
    result = _CallbackHandler.result
    if result.get("state") != state:
        raise SystemExit("Salesforce callback state did not match; no credential was saved.")
    if "error" in result:
        raise SystemExit("Salesforce authorization failed: %s" % result.get("error_description", result["error"]))
    code = result.get("code")
    if not code:
        raise SystemExit("Salesforce authorization timed out or returned no code.")
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    response = _post_form("%s/services/oauth2/token" % login_url.rstrip("/"), form)
    required = ("access_token", "refresh_token", "instance_url", "id")
    if any(not isinstance(response.get(name), str) for name in required):
        raise SystemExit("Salesforce did not return the required OAuth fields; no credential was saved.")
    identity_parts = str(response["id"]).rstrip("/").split("/")
    tenant = identity_parts[-2] if len(identity_parts) >= 2 else ""
    if not tenant:
        raise SystemExit("Salesforce OAuth identity did not contain an org ID.")
    document = {
        "access_token": response["access_token"],
        "refresh_token": response["refresh_token"],
        "instance_url": response["instance_url"],
        "client_id": client_id,
        "login_url": login_url.rstrip("/"),
        "tenant": tenant,
    }
    if client_secret:
        document["client_secret"] = client_secret
    _write_secret(path, document)
    print("Salesforce OAuth succeeded; credentials were saved locally with mode 600.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("salesforce", "hubspot"))
    parser.add_argument("--credential-dir", type=Path, default=DEFAULT_CREDENTIAL_DIR)
    parser.add_argument("--tenant", help="HubSpot portal/account ID used as the source tenant.")
    parser.add_argument("--client-id", help="Salesforce External Client App consumer key.")
    parser.add_argument("--login-url", default="https://login.salesforce.com")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.platform == "hubspot":
        tenant = args.tenant or input("HubSpot portal/account ID: ").strip()
        if not tenant:
            parser.error("HubSpot tenant is required")
        configure_hubspot(args.credential_dir / "hubspot.json", tenant)
    else:
        client_id = args.client_id or input("Salesforce External Client App consumer key: ").strip()
        if not client_id:
            parser.error("Salesforce client ID is required")
        configure_salesforce(
            args.credential_dir / "salesforce.json",
            args.login_url,
            client_id,
            args.port,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
