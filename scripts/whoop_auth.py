#!/usr/bin/env python
import argparse
import json
import secrets
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

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
from secret_store import (
    load_secrets,
    save_secrets,
    get_client_credentials,
    get_band_tokens,
    save_band_tokens,
    NUM_BANDS,
)


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
    next_token: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch sleep data from WHOOP API with automatic token refresh.
    
    Args:
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    
    Returns:
        Tuple of (sleep_data, access_token, refresh_token) - tokens may be updated if refreshed
    """
    url = f"{API_BASE_URL}/developer/v2/activity/sleep"
    params = {"limit": limit}
    if next_token:
        params["nextToken"] = next_token
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    
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


def get_cycle_data(
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    limit: int = 25,
    next_token: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch cycle data from WHOOP API with automatic token refresh.
    
    Args:
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    
    Returns:
        Tuple of (cycle_data, access_token, refresh_token) - tokens may be updated if refreshed
    """
    url = f"{API_BASE_URL}/developer/v2/cycle"
    params = {"limit": limit}
    if next_token:
        params["nextToken"] = next_token
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    
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


def get_recovery_data(
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    limit: int = 25,
    next_token: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch recovery data from WHOOP API with automatic token refresh.
    
    Args:
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    
    Returns:
        Tuple of (recovery_data, access_token, refresh_token) - tokens may be updated if refreshed
    """
    url = f"{API_BASE_URL}/developer/v2/recovery"
    params = {"limit": limit}
    if next_token:
        params["nextToken"] = next_token
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    
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


def get_workout_data(
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    limit: int = 25,
    next_token: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch workout data from WHOOP API with automatic token refresh.
    
    Args:
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    
    Returns:
        Tuple of (workout_data, access_token, refresh_token) - tokens may be updated if refreshed
    """
    url = f"{API_BASE_URL}/developer/v2/activity/workout"
    params = {"limit": limit}
    if next_token:
        params["nextToken"] = next_token
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    
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
            "Run OAuth flow or fetch data (sleep, cycle, recovery, workout) from WHOOP API. "
            "Supports multiple bands (1-10) with separate tokens for each."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["get_sleep", "get_cycle", "get_recovery", "get_workout", "check_daily_compliance"],
        help="Command to execute (default: run OAuth flow)",
    )
    parser.add_argument(
        "--band",
        type=int,
        choices=range(1, NUM_BANDS + 1),
        metavar=f"{{1-{NUM_BANDS}}}",
        help=f"Band number to authenticate or fetch data for (1-{NUM_BANDS}). Required for all commands except check_daily_compliance.",
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
        help="Maximum number of records per page (default: 25, max: 25)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch all pages of data (uses pagination with next_token)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (e.g., 2024-01-01). Returns records from the beginning of this day.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (e.g., 2024-12-31). Returns records until the end of this day.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date for compliance check in YYYY-MM-DD format (e.g., 2024-01-15). Required for check_daily_compliance.",
    )
    
    args = parser.parse_args()
    
    # Validate required arguments based on command
    if args.command == "check_daily_compliance":
        if not args.date:
            parser.error("--date is required for check_daily_compliance command")
    else:
        if args.band is None:
            parser.error("--band is required for this command")
    
    return args


def validate_date_format(date_str: str) -> bool:
    """Validate that a date string is in YYYY-MM-DD format.
    
    Args:
        date_str: Date string to validate
    
    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def format_date_for_api(date_str: Optional[str], is_end: bool = False) -> Optional[str]:
    """Format a YYYY-MM-DD date string to ISO 8601 format for WHOOP API.
    
    Args:
        date_str: Date in YYYY-MM-DD format, or None
        is_end: If True, append T23:59:59.999Z (end of day), otherwise T00:00:00.000Z (start of day)
    
    Returns:
        ISO 8601 formatted date-time string, or None if input is None
    
    Raises:
        SystemExit: If date string is not in valid YYYY-MM-DD format
    """
    if not date_str:
        return None
    
    # If already in full ISO format, return as-is
    if "T" in date_str:
        return date_str
    
    # Validate YYYY-MM-DD format
    if not validate_date_format(date_str):
        raise SystemExit(
            f"Invalid date format: '{date_str}'. Please use YYYY-MM-DD format (e.g., 2024-01-15)."
        )
    
    # Append time portion based on whether it's start or end
    if is_end:
        return f"{date_str}T23:59:59.999Z"
    else:
        return f"{date_str}T00:00:00.000Z"


def filter_records_by_start_date(records: List[object], start: Optional[str]) -> List[object]:
    """Filter records to only include those that started on or after the specified start date.
    
    This is a client-side filter to handle cases where the WHOOP API returns records
    that "intersect" with the date range but actually started before the specified start date
    (e.g., ongoing cycles with null end dates).
    
    Args:
        records: List of records from WHOOP API
        start: ISO 8601 date-time string (start of date range), or None
    
    Returns:
        Filtered list of records where record["start"] >= start
    """
    if not start or not records:
        return records
    
    filtered = []
    for record in records:
        if isinstance(record, dict):
            record_start = record.get("start")
            # Include record if it started on or after the specified start date
            # ISO 8601 strings are lexicographically sortable
            if record_start and record_start >= start:
                filtered.append(record)
        else:
            # Non-dict records pass through unchanged
            filtered.append(record)
    
    return filtered


def filter_ongoing_records_before_date(records: List[object], start: str) -> List[object]:
    """Filter out ongoing records (null end date) that started before the specified start date.
    
    For daily compliance checks, we don't want to count records that:
    1. Started before the compliance check date, AND
    2. Are still ongoing (have null end date)
    
    Args:
        records: List of records from WHOOP API
        start: ISO 8601 date-time string (start of compliance date)
    
    Returns:
        Filtered list excluding ongoing records that started before the date
    """
    if not records:
        return records
    
    filtered = []
    for record in records:
        if isinstance(record, dict):
            record_start = record.get("start")
            record_end = record.get("end")
            
            # Exclude records that started before the date AND have null end (ongoing)
            if record_start and record_start < start and record_end is None:
                continue  # Skip this record
            
            filtered.append(record)
        else:
            filtered.append(record)
    
    return filtered


def run_oauth_flow(band_id: int, no_browser: bool = False) -> None:
    """Run the OAuth 2.0 authorization flow for a specific band.
    
    Args:
        band_id: Band number (1-10) to authenticate
        no_browser: If True, don't auto-open browser
    """
    # Load constants and secrets
    scope = SCOPE
    authorization_url = DEFAULT_AUTH_URL
    token_url = DEFAULT_TOKEN_URL
    redirect_uri_cfg = DEFAULT_REDIRECT_URI

    client_id, client_secret = get_client_credentials()

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

    print(f"Authenticating band {band_id}...")
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

    # Update secrets with the new tokens for this band
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if isinstance(access_token, str) and isinstance(refresh_token, str):
        save_band_tokens(band_id, access_token, refresh_token)
        print(f"Tokens saved for band {band_id}")
    else:
        raise SystemExit("Failed to get valid tokens from OAuth flow")

    # Print tokens as JSON to stdout
    print(json.dumps(tokens, indent=2))


def _fetch_all_pages(
    data_fetcher,
    token_url: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    limit: int = 25,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[Dict[str, object], str, str]:
    """Fetch all pages of data using pagination.
    
    Args:
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    
    Returns:
        Tuple of (combined_data, access_token, refresh_token) - all records combined
    """
    all_records: List[object] = []
    current_token = access_token
    current_refresh = refresh_token
    next_token: Optional[str] = None
    previous_next_token: Optional[str] = None
    seen_next_tokens: set = set()
    page_count = 0
    response_metadata: Dict[str, object] = {}
    
    while True:
        page_count += 1
        records_before = len(all_records)
        
        if next_token:
            print(f"Fetching page {page_count} with next_token: {next_token[:30]}...", file=sys.stderr)
        else:
            print(f"Fetching page {page_count} (first page, no next_token)...", file=sys.stderr)
        
        # Fetch the page
        page_data, current_token, current_refresh = data_fetcher(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=current_token,
            refresh_token=current_refresh,
            limit=limit,
            next_token=next_token,
            start=start,
            end=end,
        )
        
        # Debug: print response keys to help diagnose issues
        if page_count == 1:
            print(f"  Response keys: {list(page_data.keys()) if isinstance(page_data, dict) else 'Not a dict'}", file=sys.stderr)
        
        # Preserve metadata from first page (excluding records and next_token)
        if page_count == 1 and isinstance(page_data, dict):
            for key, value in page_data.items():
                if key not in ("records", "next_token"):
                    response_metadata[key] = value
        
        # Extract records from the response (structure may vary by endpoint)
        # Most WHOOP endpoints return records in a 'records' key
        page_records: List[object] = []
        if isinstance(page_data, dict) and "records" in page_data:
            page_records = page_data["records"] if isinstance(page_data["records"], list) else []
            all_records.extend(page_records)
        elif isinstance(page_data, list):
            page_records = page_data
            all_records.extend(page_records)
        else:
            # If structure is different, add the whole page
            all_records.append(page_data)
        
        records_after = len(all_records)
        new_records_count = records_after - records_before
        print(f"  Page {page_count}: fetched {new_records_count} records (total: {records_after})", file=sys.stderr)
        
        # Extract next_token from response
        previous_next_token = next_token
        if isinstance(page_data, dict):
            next_token = page_data.get("next_token")
            if next_token and not isinstance(next_token, str):
                next_token = str(next_token)
        else:
            next_token = None
        
        # # Debug output
        # if next_token:
        #     print(f"  Found next_token for page {page_count}: {next_token[:20]}... (will fetch next page)", file=sys.stderr)
        # else:
        #     print(f"  No next_token found for page {page_count}, pagination complete.", file=sys.stderr)
        
        # Break if no next_token (None, empty string, or falsy value)
        if not next_token or (isinstance(next_token, str) and not next_token.strip()):
            break
        
        # # Safety check: break if we got the same next_token twice (infinite loop protection)
        # if next_token == previous_next_token:
        #     print(f"  Warning: Same next_token returned twice, breaking to prevent infinite loop.", file=sys.stderr)
        #     break
        
        # # Safety check: break if we've seen this next_token before (circular pagination)
        # if next_token in seen_next_tokens:
        #     print(f"  Warning: next_token was seen before, breaking to prevent infinite loop.", file=sys.stderr)
        #     break
        # seen_next_tokens.add(next_token)
        
        # # Safety check: break if no new records were fetched (API might be returning same page)
        # if new_records_count == 0:
        #     print(f"  Warning: No new records fetched on page {page_count}, breaking to prevent infinite loop.", file=sys.stderr)
        #     break
    
    print(f"Fetched {page_count} page(s) with {len(all_records)} total records.", file=sys.stderr)
    
    # Return combined data in the same structure as a single page
    combined_data: Dict[str, object] = {
        **response_metadata,
        "records": all_records,
        "next_token": None,  # No more pages
    }
    
    return combined_data, current_token, current_refresh


def run_get_data(
    data_fetcher,
    band_id: int,
    limit: int = 25,
    fetch_all: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> None:
    """Generic helper to fetch data from WHOOP API with automatic token refresh.
    
    Args:
        data_fetcher: Function that fetches data (get_sleep_data, get_cycle_data, etc.)
        band_id: Band number (1-10) to fetch data for
        limit: Maximum number of records per page
        fetch_all: If True, fetch all pages using pagination
        start: ISO 8601 date-time string. Returns records after or during this time.
        end: ISO 8601 date-time string. Returns records that ended before this time.
    """
    token_url = DEFAULT_TOKEN_URL
    
    client_id, client_secret = get_client_credentials()
    access_token, refresh_token = get_band_tokens(band_id)

    if not client_id or not client_secret:
        raise SystemExit(
            "client_id/client_secret missing in secrets.json. Please fill them and rerun."
        )

    if not access_token:
        raise SystemExit(
            f"access_token missing for band {band_id} in secrets.json. Please run OAuth flow first."
        )

    if not refresh_token:
        raise SystemExit(
            f"refresh_token missing for band {band_id} in secrets.json. Please run OAuth flow first."
        )

    # Print info about the request
    date_range_info = ""
    if start or end:
        date_range_info = f" (date range: {start or 'any'} to {end or 'any'})"
    print(f"Fetching data for band {band_id}{date_range_info}...", file=sys.stderr)

    # Fetch data (will auto-refresh token if expired)
    if fetch_all:
        data, new_access_token, new_refresh_token = _fetch_all_pages(
            data_fetcher=data_fetcher,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            limit=limit,
            start=start,
            end=end,
        )
    else:
        data, new_access_token, new_refresh_token = data_fetcher(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            limit=limit,
            start=start,
            end=end,
        )

    # Update secrets if tokens were refreshed
    if new_access_token != access_token or new_refresh_token != refresh_token:
        save_band_tokens(band_id, new_access_token, new_refresh_token)
        print(f"Tokens refreshed and saved for band {band_id}", file=sys.stderr)

    # Client-side filter: exclude records that started before the specified start date
    if start and isinstance(data, dict) and "records" in data:
        original_count = len(data["records"]) if isinstance(data["records"], list) else 0
        data["records"] = filter_records_by_start_date(data["records"], start)
        filtered_count = len(data["records"])
        if filtered_count < original_count:
            print(f"Filtered out {original_count - filtered_count} record(s) that started before {start}", file=sys.stderr)

    # Print data as JSON to stdout
    print(json.dumps(data, indent=2))


def run_daily_compliance_check(date_str: str) -> None:
    """Check daily compliance for all bands on a specific date.
    
    Iterates through all 10 bands and checks if there is at least one record
    for sleep, cycle, and recovery endpoints for the given day.
    
    Args:
        date_str: Date in YYYY-MM-DD format
    """
    # Validate and format the date
    if not validate_date_format(date_str):
        raise SystemExit(
            f"Invalid date format: '{date_str}'. Please use YYYY-MM-DD format (e.g., 2024-01-15)."
        )
    
    start_date = f"{date_str}T00:00:00.000Z"
    end_date = f"{date_str}T23:59:59.999Z"
    
    token_url = DEFAULT_TOKEN_URL
    client_id, client_secret = get_client_credentials()
    
    if not client_id or not client_secret:
        raise SystemExit(
            "client_id/client_secret missing in secrets.json. Please fill them and rerun."
        )
    
    # Track failures: {band_id: [list of failed endpoints]}
    failures: Dict[str, List[str]] = {}
    
    # Define the endpoints to check
    endpoints = [
        ("sleep", get_sleep_data),
        ("cycle", get_cycle_data),
        ("recovery", get_recovery_data),
    ]
    
    print(f"Checking daily compliance for {date_str}...", file=sys.stderr)
    
    for band_id in range(1, NUM_BANDS + 1):
        access_token, refresh_token = get_band_tokens(band_id)
        
        if not access_token or not refresh_token:
            # Band not authenticated - mark all endpoints as failed
            failures[str(band_id)] = ["sleep", "cycle", "recovery"]
            print(f"  Band {band_id}: NOT AUTHENTICATED (missing tokens)", file=sys.stderr)
            continue
        
        band_failures: List[str] = []
        current_access_token = access_token
        current_refresh_token = refresh_token
        
        for endpoint_name, data_fetcher in endpoints:
            try:
                data, new_access_token, new_refresh_token = data_fetcher(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    access_token=current_access_token,
                    refresh_token=current_refresh_token,
                    limit=25,
                    start=start_date,
                    end=end_date,
                )
                
                # Update tokens if refreshed
                if new_access_token != current_access_token or new_refresh_token != current_refresh_token:
                    current_access_token = new_access_token
                    current_refresh_token = new_refresh_token
                    save_band_tokens(band_id, new_access_token, new_refresh_token)
                
                # Check if there is at least one valid record
                records = []
                if isinstance(data, dict) and "records" in data:
                    records = data["records"] if isinstance(data["records"], list) else []
                elif isinstance(data, list):
                    records = data
                
                # Filter out ongoing records that started before the compliance date
                records = filter_ongoing_records_before_date(records, start_date)
                
                if len(records) == 0:
                    band_failures.append(endpoint_name)
                    
            except SystemExit as e:
                # Token refresh failed or other auth error
                print(f"  Band {band_id} {endpoint_name}: AUTH ERROR - {e}", file=sys.stderr)
                band_failures.append(endpoint_name)
            except Exception as e:
                # API error or other issue
                print(f"  Band {band_id} {endpoint_name}: ERROR - {e}", file=sys.stderr)
                band_failures.append(endpoint_name)
        
        if band_failures:
            failures[str(band_id)] = band_failures
            print(f"  Band {band_id}: MISSING {band_failures}", file=sys.stderr)
        else:
            print(f"  Band {band_id}: OK", file=sys.stderr)
    
    # Output results
    if not failures:
        print("DAILY COMPLIANCE SUCCESSFUL FOR ALL BANDS")
    else:
        print(json.dumps(failures, indent=2))


def main() -> None:
    args = parse_args()

    # Format dates to ISO 8601 format for API
    start_date = format_date_for_api(args.start, is_end=False)
    end_date = format_date_for_api(args.end, is_end=True)

    if args.command == "get_sleep":
        run_get_data(
            get_sleep_data,
            band_id=args.band,
            limit=args.limit,
            fetch_all=args.all,
            start=start_date,
            end=end_date,
        )
    elif args.command == "get_cycle":
        run_get_data(
            get_cycle_data,
            band_id=args.band,
            limit=args.limit,
            fetch_all=args.all,
            start=start_date,
            end=end_date,
        )
    elif args.command == "get_recovery":
        run_get_data(
            get_recovery_data,
            band_id=args.band,
            limit=args.limit,
            fetch_all=args.all,
            start=start_date,
            end=end_date,
        )
    elif args.command == "get_workout":
        run_get_data(
            get_workout_data,
            band_id=args.band,
            limit=args.limit,
            fetch_all=args.all,
            start=start_date,
            end=end_date,
        )
    elif args.command == "check_daily_compliance":
        run_daily_compliance_check(date_str=args.date)
    else:
        # Default: run OAuth flow
        run_oauth_flow(band_id=args.band, no_browser=args.no_browser)


if __name__ == "__main__":
    main()
