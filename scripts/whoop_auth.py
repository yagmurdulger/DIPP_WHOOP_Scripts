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

from constants import AUTHORIZATION_URL, ACCESS_TOKEN_URL, API_BASE_URL, REDIRECT_URI, SCOPE
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

def refresh_access_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Dict[str, object]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "offline",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(token_url, data=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def authenticated_request(
    method: str,
    url: str,
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, object]] = None,
    data: Optional[Dict[str, object]] = None,
    json_data: Optional[Dict[str, object]] = None,
    timeout: int = 30,
) -> Tuple[requests.Response, str, str]:
    """Make an authenticated request to WHOOP API with automatic token refresh.
    
    This middleware function handles token refresh automatically if the access token
    has expired (401 response). It will retry the request once with the new token.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        url: Full URL to request
        token_url: WHOOP token refresh endpoint URL
        client_id: OAuth client ID
        client_secret: OAuth client secret
        access_token: Current access token
        refresh_token: Current refresh token
        headers: Optional additional headers (Authorization will be added automatically)
        params: Optional query parameters
        data: Optional form data (for POST/PUT requests)
        json_data: Optional JSON data (for POST/PUT requests)
        timeout: Request timeout in seconds
    
    Returns:
        Tuple of (response, access_token, refresh_token) - tokens may be updated if refreshed
    """
    if headers is None:
        headers = {}
    headers["Authorization"] = f"Bearer {access_token}"
    
    # Make the initial request
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        data=data,
        json=json_data,
        timeout=timeout,
    )
    
    # If 401, refresh token and retry (only once)
    if response.status_code == 401:
        print("Access token expired. Refreshing...")
        
        if not refresh_token:
            raise SystemExit(
                "Cannot refresh token: refresh_token is missing or empty. "
                "Please run OAuth flow again to get new tokens."
            )
        
        try:
            tokens = refresh_access_token(
                token_url=token_url,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                error_detail = ""
                try:
                    error_body = e.response.json()
                    error_detail = f" Error: {error_body}"
                except:
                    error_detail = f" Status: {e.response.status_code}"
                raise SystemExit(
                    f"Failed to refresh access token.{error_detail} "
                    "The refresh_token may be expired or invalid. "
                    "Please run OAuth flow again to get new tokens."
                )
            raise
        
        new_access_token = tokens.get("access_token", "")
        new_refresh_token = tokens.get("refresh_token", refresh_token)
        if not new_access_token:
            raise SystemExit("Failed to refresh access token: no access_token in response")
        
        # Retry the request with new token
        headers["Authorization"] = f"Bearer {new_access_token}"
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json_data,
            timeout=timeout,
        )
        response.raise_for_status()
        return response, new_access_token, new_refresh_token
    else:
        response.raise_for_status()
        return response, access_token, refresh_token


def get_sleep_data(
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    limit: int = 25,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch sleep data from WHOOP API with automatic token refresh.
    
    Returns:
        Tuple of (sleep_data, access_token, refresh_token) - tokens may be updated if refreshed
    """
    url = f"{API_BASE_URL}/developer/v2/activity/sleep"
    params = {"limit": limit}
    
    response, new_access_token, new_refresh_token = authenticated_request(
        method="GET",
        url=url,
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        params=params,
    )
    
    return response.json(), new_access_token, new_refresh_token



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "WHOOP API OAuth and data retrieval tool. "
            "Run OAuth flow or fetch sleep data from WHOOP API."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["get_sleep"],
        help="Command to execute (default: run OAuth flow)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser; print URL instead (only for OAuth flow)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of sleep records to fetch (default: 25, max: 25)",
    )
    return parser.parse_args()


def run_oauth_flow(no_browser: bool = False) -> None:
    """Run the OAuth 2.0 authorization flow."""
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
    if not no_browser:
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


def run_get_sleep(limit: int = 25) -> None:
    """Fetch sleep data from WHOOP API with automatic token refresh."""
    token_url = DEFAULT_TOKEN_URL
    
    secrets_obj = load_secrets()
    client_id = secrets_obj.get("client_id") or ""
    client_secret = secrets_obj.get("client_secret") or ""
    access_token = secrets_obj.get("access_token") or ""
    refresh_token = secrets_obj.get("refresh_token") or ""

    if not client_id or not client_secret:
        raise SystemExit(
            "client_id/client_secret missing in secrets.json. Please fill them and rerun."
        )

    if not access_token:
        raise SystemExit(
            "access_token missing in secrets.json. Please run OAuth flow first."
        )

    if not refresh_token:
        raise SystemExit(
            "refresh_token missing in secrets.json. Please run OAuth flow first."
        )

    # Fetch sleep data (will auto-refresh token if expired)
    sleep_data, new_access_token, new_refresh_token = get_sleep_data(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        limit=limit,
    )

    # Update secrets if tokens were refreshed
    if new_access_token != access_token or new_refresh_token != refresh_token:
        secrets_obj["access_token"] = new_access_token
        secrets_obj["refresh_token"] = new_refresh_token
        save_secrets(secrets_obj)
        print("Tokens refreshed and saved to secrets.json")

    # Print sleep data as JSON to stdout
    print(json.dumps(sleep_data, indent=2))


def main() -> None:
    args = parse_args()

    if args.command == "get_sleep":
        run_get_sleep(limit=args.limit)
    else:
        # Default: run OAuth flow
        run_oauth_flow(no_browser=args.no_browser)


if __name__ == "__main__":
    main()
