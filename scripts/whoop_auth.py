#!/usr/bin/env python
import argparse
import json
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple

import requests


DEFAULT_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
DEFAULT_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"


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
            "Run a local OAuth 2.0 flow for WHOOP, retrieve access and refresh tokens."
        )
    )
    parser.add_argument("--client-id", required=True, help="WHOOP OAuth client ID")
    parser.add_argument("--client-secret", required=True, help="WHOOP OAuth client secret")
    parser.add_argument(
        "--authorization-url",
        default=DEFAULT_AUTH_URL,
        help="WHOOP authorization URL (default: %(default)s)",
    )
    parser.add_argument(
        "--access-token-url",
        default=DEFAULT_TOKEN_URL,
        help="WHOOP token URL (default: %(default)s)",
    )
    parser.add_argument(
        "--scope",
        default="offline",
        help="Requested scopes (space-separated string). Default: offline",
    )
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help="Redirect URI that must be registered in WHOOP dashboard",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser; print URL instead",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    parsed_redirect = urllib.parse.urlparse(args.redirect_uri)
    if parsed_redirect.hostname is None or parsed_redirect.port is None:
        raise SystemExit(
            "redirect_uri must include a hostname and port, e.g. http://localhost:8765/callback"
        )

    state = secrets.token_urlsafe(16)

    server, redirect_uri = start_local_server(parsed_redirect.hostname, parsed_redirect.port)
    if args.redirect_uri != redirect_uri:
        # Harmonize if user specified slightly different path; enforce /callback
        args.redirect_uri = redirect_uri

    auth_url = build_authorize_url(
        authorization_url=args.authorization_url,
        client_id=args.client_id,
        redirect_uri=args.redirect_uri,
        scope=args.scope,
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
        token_url=args.access_token_url,
        client_id=args.client_id,
        client_secret=args.client_secret,
        code=code,
        redirect_uri=args.redirect_uri,
    )

    # Print tokens as JSON to stdout
    print(json.dumps(tokens, indent=2))


if __name__ == "__main__":
    main()
