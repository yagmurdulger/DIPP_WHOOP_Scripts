import json
import os
from typing import Any, Dict, Tuple


DEFAULT_SECRETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "secrets.json")

# Number of bands supported
NUM_BANDS = 10


def ensure_secrets_file(path: str = DEFAULT_SECRETS_PATH) -> None:
    """Ensure secrets file exists with correct structure for multi-band support."""
    if os.path.exists(path):
        return
    initial: Dict[str, Any] = {
        "client_id": "",
        "client_secret": "",
    }
    # Add empty token entries for each band (1-10)
    for band_id in range(1, NUM_BANDS + 1):
        initial[str(band_id)] = {
            "access_token": "",
            "refresh_token": "",
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(initial, f, indent=2)


def load_secrets(path: str = DEFAULT_SECRETS_PATH) -> Dict[str, Any]:
    """Load the full secrets file."""
    ensure_secrets_file(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_secrets(data: Dict[str, Any], path: str = DEFAULT_SECRETS_PATH) -> None:
    """Save the full secrets file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_client_credentials(path: str = DEFAULT_SECRETS_PATH) -> Tuple[str, str]:
    """Get client_id and client_secret from secrets file.
    
    Returns:
        Tuple of (client_id, client_secret)
    """
    secrets = load_secrets(path)
    client_id = secrets.get("client_id") or ""
    client_secret = secrets.get("client_secret") or ""
    return client_id, client_secret


def get_band_tokens(band_id: int, path: str = DEFAULT_SECRETS_PATH) -> Tuple[str, str]:
    """Get access_token and refresh_token for a specific band.
    
    Args:
        band_id: Band number (1-10)
        path: Path to secrets file
    
    Returns:
        Tuple of (access_token, refresh_token)
    """
    if not 1 <= band_id <= NUM_BANDS:
        raise ValueError(f"band_id must be between 1 and {NUM_BANDS}, got {band_id}")
    
    secrets = load_secrets(path)
    band_key = str(band_id)
    
    if band_key not in secrets:
        secrets[band_key] = {"access_token": "", "refresh_token": ""}
        save_secrets(secrets, path)
    
    band_data = secrets.get(band_key, {})
    access_token = band_data.get("access_token") or ""
    refresh_token = band_data.get("refresh_token") or ""
    return access_token, refresh_token


def save_band_tokens(
    band_id: int,
    access_token: str,
    refresh_token: str,
    path: str = DEFAULT_SECRETS_PATH,
) -> None:
    """Save access_token and refresh_token for a specific band.
    
    Args:
        band_id: Band number (1-10)
        access_token: New access token
        refresh_token: New refresh token
        path: Path to secrets file
    """
    if not 1 <= band_id <= NUM_BANDS:
        raise ValueError(f"band_id must be between 1 and {NUM_BANDS}, got {band_id}")
    
    secrets = load_secrets(path)
    band_key = str(band_id)
    
    if band_key not in secrets:
        secrets[band_key] = {}
    
    secrets[band_key]["access_token"] = access_token
    secrets[band_key]["refresh_token"] = refresh_token
    save_secrets(secrets, path)
