import json
import os
from typing import Any, Dict


DEFAULT_SECRETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "secrets.json")


def ensure_secrets_file(path: str = DEFAULT_SECRETS_PATH) -> None:
    if os.path.exists(path):
        return
    initial = {
        "client_id": "",
        "client_secret": "",
        "access_token": "",
        "refresh_token": "",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(initial, f, indent=2)


def load_secrets(path: str = DEFAULT_SECRETS_PATH) -> Dict[str, Any]:
    ensure_secrets_file(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_secrets(data: Dict[str, Any], path: str = DEFAULT_SECRETS_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
