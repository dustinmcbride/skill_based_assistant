"""
One-time script to obtain a Google OAuth refresh token.
Reads GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from .env,
runs the OAuth flow, then writes GOOGLE_REFRESH_TOKEN back into .env.

Usage:
    cd assistant
    pip install google-auth-oauthlib
    python scripts/get_google_token.py
"""

import re
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ENV_FILE = Path(__file__).parent.parent / ".env"

# Parse .env directly — no dotenv dependency needed
env_vars = {}
for line in ENV_FILE.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env_vars[k.strip()] = v.strip()

client_id = env_vars["GOOGLE_CLIENT_ID"]
client_secret = env_vars["GOOGLE_CLIENT_SECRET"]

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": ["http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=["https://www.googleapis.com/auth/calendar"],
)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

refresh_token = creds.refresh_token

# Write GOOGLE_REFRESH_TOKEN into .env (add or update)
env_text = ENV_FILE.read_text()
if "GOOGLE_REFRESH_TOKEN=" in env_text:
    env_text = re.sub(r"GOOGLE_REFRESH_TOKEN=.*", f"GOOGLE_REFRESH_TOKEN={refresh_token}", env_text)
else:
    env_text += f"\nGOOGLE_REFRESH_TOKEN={refresh_token}\n"
ENV_FILE.write_text(env_text)

print(f"\nSuccess! GOOGLE_REFRESH_TOKEN written to {ENV_FILE}")
