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
- Put reusable modules in `src/`
- Put runnable utilities/scripts in `scripts/`

To import from modules in `src/` in your scripts, use the `PYTHONPATH` approach when needed:
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
│  ├─ __init__.py
│  ├─ constants.py
│  └─ secret_store.py
└─ scripts/
   ├─ hello.py
   └─ whoop_auth.py
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

This project includes a CLI to run a local OAuth 2.0 authorization flow for WHOOP and exchange the authorization code for tokens. It also supports fetching data (sleep, cycle, recovery, workout) and checking daily compliance across all bands. References: [WHOOP OAuth 2.0 docs](https://developer.whoop.com/docs/developing/oauth), [Passport tutorial](https://developer.whoop.com/docs/tutorials/access-token-passport).

### Multi-Band Support

The tool supports **up to 10 different WHOOP bands** connected to the same client app. Each band has its own `access_token` and `refresh_token`, while sharing the same `client_id` and `client_secret`.

### Prerequisites

- Register an app in the WHOOP Developer Dashboard and add a Redirect URL of `http://localhost:8765/callback`.
- Ensure your app requests the `offline` scope to receive a refresh token.

### Configuration files

- `src/constants.py`: static config like URLs, redirect URI, scope.
- `secrets.json`: stores credentials for the client app and tokens for each band (1-10). This file is ignored by git.

Set your client credentials and band tokens in `secrets.json` (auto-created on first run if missing):
```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "1": {
    "access_token": "",
    "refresh_token": ""
  },
  "2": {
    "access_token": "",
    "refresh_token": ""
  },
  "3": {
    "access_token": "",
    "refresh_token": ""
  }
}
```
(Bands 4-10 follow the same pattern)

### Install dependency (if not already)

```bash
pip install -r requirements.txt
```

### Usage

All commands require the `--band` argument to specify which band (1-10) you're working with.

**Run OAuth flow for a band:**
```bash
python scripts/whoop_auth.py --band 1
python scripts/whoop_auth.py --band 2
```

**Fetch sleep data for a band:**
```bash
python scripts/whoop_auth.py get_sleep --band 1
python scripts/whoop_auth.py get_sleep --band 1 --all
python scripts/whoop_auth.py get_sleep --band 1 --all --limit 25
```

**Fetch cycle data for a band:**
```bash
python scripts/whoop_auth.py get_cycle --band 2
python scripts/whoop_auth.py get_cycle --band 2 --all
```

**Fetch recovery data for a band:**
```bash
python scripts/whoop_auth.py get_recovery --band 3
python scripts/whoop_auth.py get_recovery --band 3 --all
```

**Fetch workout data for a band:**
```bash
python scripts/whoop_auth.py get_workout --band 1
python scripts/whoop_auth.py get_workout --band 1 --all
python scripts/whoop_auth.py get_workout --band 1 --start 2024-01-01 --end 2024-12-31
```

### Date Range Filtering

You can filter data by date range using `--start` and `--end` arguments. Simply provide dates in `YYYY-MM-DD` format.

- `--start`: Returns records from the **beginning** of this day (00:00:00)
- `--end`: Returns records until the **end** of this day (23:59:59)

Both arguments are optional and can be used independently or together.

**Note:** The WHOOP API may return records that "intersect" with the date range but actually started before your specified start date (e.g., ongoing cycles). The script applies **client-side filtering** to exclude records where the `start` field is before your specified `--start` date. If any records are filtered out, you'll see a message like:
```
Filtered out 1 record(s) that started before 2024-01-01T00:00:00.000Z
```

**Examples:**

```bash
# Fetch sleep data for January 2024
python scripts/whoop_auth.py get_sleep --band 1 --start 2024-01-01 --end 2024-01-31

# Fetch all cycle data for Q1 2024
python scripts/whoop_auth.py get_cycle --band 2 --all --start 2024-01-01 --end 2024-03-31

# Fetch recovery data from June 1st onwards (no end date)
python scripts/whoop_auth.py get_recovery --band 3 --start 2024-06-01

# Fetch sleep data up to end of 2024 (no start date)
python scripts/whoop_auth.py get_sleep --band 1 --all --end 2024-12-31

# Fetch all sleep data for a single day
python scripts/whoop_auth.py get_sleep --band 1 --start 2024-07-15 --end 2024-07-15

# Combine with pagination
python scripts/whoop_auth.py get_sleep --band 1 --all --limit 25 --start 2024-01-01 --end 2024-06-30
```

### Daily Compliance Check

Check if all 10 bands have data for a specific day across sleep, cycle, and recovery endpoints:

```bash
python scripts/whoop_auth.py check_daily_compliance --date 2024-01-15
```

**How it works:**
- Iterates through all 10 bands
- For each band, checks sleep, cycle, and recovery endpoints for the specified date
- Reports which bands are missing data

**Output:**

✅ If all bands have at least one record for all three endpoints:
```
DAILY COMPLIANCE SUCCESSFUL FOR ALL BANDS
```

❌ If some bands are missing data, outputs JSON showing which endpoints failed:
```json
{
  "3": ["sleep", "recovery"],
  "7": ["cycle"]
}
```
This means band 3 is missing sleep and recovery data, and band 7 is missing cycle data.

**Filtering behavior:** The compliance check excludes records that started **before** the specified date AND have a `null` end date (ongoing/incomplete records). This ensures only records that actually started or ended on the compliance date are counted.

### Options

- `--band {1-10}`: Band number to authenticate or fetch data for (required for all commands except `check_daily_compliance`)
- `--no-browser`: Don't auto-open browser; print URL instead (OAuth flow only)
- `--limit N`: Maximum records per page (default: 25, max: 25)
- `--all`: Fetch all pages of data using pagination
- `--start YYYY-MM-DD`: Start date for filtering (returns records from beginning of this day)
- `--end YYYY-MM-DD`: End date for filtering (returns records until end of this day)
- `--date YYYY-MM-DD`: Date for compliance check (required for `check_daily_compliance`)

The script will open a browser window to WHOOP's authorization screen, receive the redirect locally, verify the state, and print a JSON object containing `access_token`, `refresh_token`, `expires_in`, and `token_type`. It will save tokens to the appropriate band entry in `secrets.json` automatically.
