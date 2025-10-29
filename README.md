# DIPP_WHOOP_Scripts (Python Project Barebones)

A minimal Python project scaffold with a simple example script and clear setup/run instructions.

## Requirements
- Python 3.9+ (recommended)
- macOS/Linux/Windows supported

## Quick Start

### 1) Open this folder
Ensure you are in the project root:
```bash
cd /Users/yagmurdulger/Desktop/DIPP_WHOOP_Scripts
```

### 2) Create and activate a virtual environment
macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

Verify you see `(.venv)` in your shell prompt.

### 3) Upgrade pip and install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Run the example script
```bash
python scripts/hello.py --name "World"
```
Expected output:
```text
Hello, World!
```

### 5) Add your own code
- Put reusable modules in `src/your_project/`
- Put runnable utilities/scripts in `scripts/`

To import from `src/your_project` in your scripts, use the `PYTHONPATH` approach when needed:
```bash
PYTHONPATH=src python scripts/hello.py
```
(Windows PowerShell):
```powershell
$env:PYTHONPATH = "src"; python scripts/hello.py
```

## Project Structure
```
DIPP_WHOOP_Scripts/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ src/
│  └─ your_project/
│     └─ __init__.py
└─ scripts/
   └─ hello.py
```

## Common Commands
- Activate venv (macOS/Linux): `source .venv/bin/activate`
- Activate venv (Windows PowerShell): `.venv\Scripts\Activate.ps1`
- Install deps: `pip install -r requirements.txt`
- Freeze deps: `pip freeze > requirements.txt`
- Run example: `python scripts/hello.py --name You`

## Notes
- Keep dependencies minimal; add as you need and run `pip freeze > requirements.txt` to pin versions.
- Consider using tools like `ruff`, `black`, or `pytest` as the project grows.

## WHOOP OAuth Helper

This project includes a CLI to run a local OAuth 2.0 authorization flow for WHOOP and exchange the authorization code for tokens. References: [WHOOP OAuth 2.0 docs](https://developer.whoop.com/docs/developing/oauth), [Passport tutorial](https://developer.whoop.com/docs/tutorials/access-token-passport).

Prerequisites:
- Register an app in the WHOOP Developer Dashboard and add a Redirect URL of `http://localhost:8765/callback`.
- Ensure your app requests the `offline` scope to receive a refresh token.

Install dependency (if not already):
```bash
pip install -r requirements.txt
```

Run the CLI:
```bash
python scripts/whoop_auth.py \
  --client-id CLIENT_ID \
  --client-secret CLIENT_SECRET \
  --scope "offline" \
  --authorization-url https://api.prod.whoop.com/oauth/oauth2/auth \
  --access-token-url https://api.prod.whoop.com/oauth/oauth2/token \
  --redirect-uri http://localhost:8765/callback
```

The script will open a browser window to WHOOP's authorization screen, receive the redirect locally, verify the state, and print a JSON object containing `access_token`, `refresh_token`, `expires_in`, and `token_type`.
