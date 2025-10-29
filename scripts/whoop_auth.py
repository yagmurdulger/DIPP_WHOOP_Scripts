#!/usr/bin/env python
import argparse
import json
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple

import os
import sys

# Ensure src/ is importable when running this as a script
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import requests

from constants import AUTHORIZATION_URL, ACCESS_TOKEN_URL, REDIRECT_URI, SCOPE
from secret_store import load_secrets, save_secrets


DEFAULT_AUTH_URL = AUTHORIZATION_URL
DEFAULT_TOKEN_URL = ACCESS_TOKEN_URL
DEFAULT_REDIRECT_URI = REDIRECT_URI


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server signature)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        # Store on server instance for retrieval
        self.server.auth_result = {  # type: ignore[attr-defined]
            "code": code,
            "state": state,
            "error": params.get("error", [None])[0],
        }

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h3>WHOOP authorization received.</h3>"
            b"<p>You can return to the terminal.</p></body></html>"
        )

    def log_message(self, format, *args):  # noqa: A003 (shadow builtins)
        # Silence default HTTPServer logging for cleaner CLI UX
        return


def start_local_server(host: str, port: int) -> Tuple[HTTPServer, str]:
    server = HTTPServer((host, port), OAuthCallbackHandler)
    url = f"http://{host}:{port}/callback"
    return server, url


def build_authorize_url(
    authorization_url: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return f"{authorization_url}?{urllib.parse.urlencode(query)}"


def exchange_code_for_tokens(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> Dict[str, object]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(token_url, data=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local OAuth 2.0 flow for WHOOP, retrieve tokens, and update secrets.json."
        )
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser; print URL instead",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load constants and secrets
    scope = SCOPE
    authorization_url = DEFAULT_AUTH_URL
    token_url = DEFAULT_TOKEN_URL
    redirect_uri_cfg = DEFAULT_REDIRECT_URI

    secrets_obj = load_secrets()
    client_id = secrets_obj.get("client_id") or ""
    client_secret = secrets_obj.get("client_secret") or ""

    if not client_id or not client_secret:
        raise SystemExit(
            "client_id/client_secret missing in secrets.json. Please fill them and rerun."
        )

    parsed_redirect = urllib.parse.urlparse(redirect_uri_cfg)
    if parsed_redirect.hostname is None or parsed_redirect.port is None:
        raise SystemExit(
            "REDIRECT_URI must include a hostname and port, e.g. http://localhost:8765/callback"
        )

    state = secrets.token_urlsafe(16)

    server, redirect_uri = start_local_server(parsed_redirect.hostname, parsed_redirect.port)

    auth_url = build_authorize_url(
        authorization_url=authorization_url,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
    )

    print("Opening WHOOP authorization URL...")
    print(auth_url)
    if not args.no_browser:
        webbrowser.open(auth_url, new=2)

    try:
        # Handle a single request (the OAuth redirect)
        server.handle_request()
    finally:
        server.server_close()

    result: Optional[Dict[str, Optional[str]]] = getattr(server, "auth_result", None)  # type: ignore[attr-defined]
    if not result:
        raise SystemExit("No authorization response was received.")

    if result.get("error"):
        raise SystemExit(f"Authorization failed: {result['error']}")

    if result.get("state") != state:
        raise SystemExit("State mismatch. Aborting.")

    code = result.get("code")
    if not code:
        raise SystemExit("Missing authorization code in callback.")

    tokens = exchange_code_for_tokens(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )

    # Update secrets with the new tokens
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if isinstance(access_token, str):
        secrets_obj["access_token"] = access_token
    if isinstance(refresh_token, str):
        secrets_obj["refresh_token"] = refresh_token
    save_secrets(secrets_obj)

    # Print tokens as JSON to stdout
    print(json.dumps(tokens, indent=2))


if __name__ == "__main__":
    main()
